"""
Agent-spark integration routes.

Two families, deliberately on different auth models (see services/agents.py
module docstring for the WebSocket/API-Gateway rationale):

  /v1/agents/*        -- behind API Gateway + Lambda authorizer, same as
                         /v1/llm and /v1/docling. Used by the website BFF to
                         list entitled agents, start/stop the (shared) crawl
                         loop, and mint a short-lived iframe token.

  /agents/{slug}/*     -- NOT behind API Gateway. Reached directly over the
                         Cloudflare Tunnel hostname (same one the portal BFF
                         already uses for everything else), so the browser's
                         <iframe> can hold a real WebSocket open to Streamlit.
                         Guarded by the signed token minted above instead of
                         the edge/portal headers, since API Gateway's headers
                         never reach this path. The entitlement is
                         re-checked live (not just the token's validity) on
                         every proxied request/connect, so a revoked
                         entitlement takes effect immediately rather than
                         waiting out the token's TTL.

Every agent has exactly one shared instance (see services/agents.py) -- the
dashboard shown, and the crawl-loop's running/stopped state, are the same
for every customer entitled to a given agent.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import Response
from starlette.websockets import WebSocket, WebSocketDisconnect

from spark_gateway.services.agents import TOKEN_TTL_S, AgentError, AgentRegistry, AgentToken
from spark_gateway.services.control_plane import ControlPlane

router = APIRouter(tags=["agents"])


def _registry(request: Request) -> AgentRegistry:
    reg = getattr(request.app.state, "agents", None)
    if reg is None:
        reg = AgentRegistry(request.app.state.settings)
        request.app.state.agents = reg
    return reg


def _control_plane(request: Request) -> ControlPlane:
    return request.app.state.control_plane


def _require_entitlement(request: Request, customer_id: str, agent_slug: str) -> None:
    if not _control_plane(request).customer_has_agent(customer_id, agent_slug):
        raise HTTPException(status_code=403, detail=f"not entitled to agent '{agent_slug}'")


# --- /v1/agents/* — behind API Gateway, same auth as llm/docling -----------


@router.get("/v1/agents")
async def list_agents(request: Request, customer_id: str = Header(..., alias="X-Itah-Customer-Id")) -> dict[str, Any]:
    from spark_gateway.services.agents import AGENT_SLUGS

    reg = _registry(request)
    cp = _control_plane(request)
    entitled = {a["agent_slug"] for a in cp.list_customer_agents(customer_id) if a.get("enabled", True)}

    agents = []
    for slug in AGENT_SLUGS:
        if slug not in entitled:
            continue
        try:
            status = reg.status(slug)
        except AgentError as exc:
            status = {"agent_slug": slug, "running": False, "error": str(exc)}
        agents.append(status)
    return {"agents": agents}


@router.post("/v1/agents/{agent_slug}/start")
async def start_agent(agent_slug: str, request: Request, customer_id: str = Header(..., alias="X-Itah-Customer-Id")) -> dict[str, Any]:
    """Starts the one shared crawl loop for this agent -- affects every
    customer entitled to it, not just the caller."""
    _require_entitlement(request, customer_id, agent_slug)
    try:
        return _registry(request).start(agent_slug)
    except AgentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/v1/agents/{agent_slug}/stop")
async def stop_agent(agent_slug: str, request: Request, customer_id: str = Header(..., alias="X-Itah-Customer-Id")) -> dict[str, Any]:
    """Stops the one shared crawl loop for this agent -- affects every
    customer entitled to it, not just the caller."""
    _require_entitlement(request, customer_id, agent_slug)
    try:
        return _registry(request).stop(agent_slug)
    except AgentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/v1/agents/{agent_slug}/status")
async def agent_status(agent_slug: str, request: Request, customer_id: str = Header(..., alias="X-Itah-Customer-Id")) -> dict[str, Any]:
    _require_entitlement(request, customer_id, agent_slug)
    try:
        return _registry(request).status(agent_slug)
    except AgentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/v1/agents/{agent_slug}/dashboard-url")
async def dashboard_url(agent_slug: str, request: Request, customer_id: str = Header(..., alias="X-Itah-Customer-Id")) -> dict[str, Any]:
    """Ensures this agent's one shared Streamlit dashboard process is running
    and returns a short-lived-token URL for the portal's <iframe src>. Called
    by the BFF (which already verified the session), not the browser directly."""
    _require_entitlement(request, customer_id, agent_slug)
    reg = _registry(request)
    try:
        reg.ensure_dashboard_running(agent_slug)
        token = reg.mint_token(customer_id, agent_slug)
    except AgentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    settings = request.app.state.settings
    base = settings.portal_public_base_url.rstrip("/")
    return {"url": f"{base}/agents/{agent_slug}/?t={token}"}


# --- /agents/{slug}/* — direct tunnel path, token-gated, HTTP + WebSocket ---


def _verify_and_check_entitlement(request_like, reg: AgentRegistry, cp: ControlPlane, agent_slug: str, token: str) -> AgentToken:
    """Verifies the token's signature/expiry AND re-checks the DynamoDB
    entitlement live, so revoking a customer's access takes effect
    immediately rather than waiting out the token's few-minute TTL."""
    try:
        claims = reg.verify_token(token)
    except AgentError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if claims.agent_slug != agent_slug:
        raise HTTPException(status_code=403, detail="token is for a different agent")
    if not cp.customer_has_agent(claims.customer_id, agent_slug):
        raise HTTPException(status_code=403, detail=f"not entitled to agent '{agent_slug}'")
    return claims


def _dashboard_cookie_name(agent_slug: str) -> str:
    return f"itah_agent_t_{agent_slug}"


_HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "host", "content-length",
}


@router.api_route(
    "/agents/{agent_slug}/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    include_in_schema=False,  # internal reverse-proxy passthrough, not a documented API
)
async def proxy_dashboard_http(
    agent_slug: str, path: str, request: Request, t: str | None = Query(default=None)
) -> Response:
    """Note on auth: the `t` query param is only present on the iframe's
    *initial* navigation (Streamlit's own frontend JS opens the follow-up
    `_stcore/stream` WebSocket itself and has no idea to carry our custom
    query param along). So on a query-token request we also drop an
    agent-scoped, httponly cookie carrying the same token -- same-origin
    requests after that, including the WS upgrade, present it automatically
    even though they never sent `?t=`. See proxy_dashboard_ws below."""
    reg = _registry(request)
    cookie_name = _dashboard_cookie_name(agent_slug)
    token = t or request.cookies.get(cookie_name, "")
    if not token:
        raise HTTPException(status_code=403, detail="missing dashboard token")
    claims = _verify_and_check_entitlement(request, reg, _control_plane(request), agent_slug, token)
    port = reg.dashboard_port(agent_slug)

    upstream_url = f"http://127.0.0.1:{port}/{path}"
    body = await request.body()
    headers = {k: v for k, v in request.headers.items() if k.lower() not in _HOP_BY_HOP}

    async with httpx.AsyncClient(timeout=30.0) as client:
        upstream = await client.request(
            request.method,
            upstream_url,
            params={k: v for k, v in request.query_params.items() if k != "t"},
            content=body,
            headers=headers,
        )
    resp_headers = {k: v for k, v in upstream.headers.items() if k.lower() not in _HOP_BY_HOP}
    response = Response(content=upstream.content, status_code=upstream.status_code, headers=resp_headers)
    if t:
        response.set_cookie(
            cookie_name,
            t,
            max_age=max(claims.exp - int(time.time()), 0) or TOKEN_TTL_S,
            path=f"/agents/{agent_slug}/",
            httponly=True,
            secure=True,
            samesite="lax",
        )
    return response


@router.websocket("/agents/{agent_slug}/{path:path}")
async def proxy_dashboard_ws(websocket: WebSocket, agent_slug: str, path: str):
    """Bridges the browser's Streamlit WebSocket connection to the local
    Streamlit process's WebSocket -- the whole reason this path exists
    outside API Gateway (HTTP APIs can't proxy WebSocket frames).

    Streamlit's frontend opens this connection itself and never attaches our
    `?t=` query param, so the token normally arrives via the agent-scoped
    cookie set by proxy_dashboard_http on the initial page load instead (the
    query param is still accepted as a fallback, e.g. for direct testing)."""
    import websockets as ws_client

    reg = _registry(websocket)
    cp = _control_plane(websocket)
    cookie_name = _dashboard_cookie_name(agent_slug)
    token = websocket.query_params.get("t") or websocket.cookies.get(cookie_name, "")
    try:
        _verify_and_check_entitlement(websocket, reg, cp, agent_slug, token)
        port = reg.dashboard_port(agent_slug)
    except HTTPException:
        await websocket.close(code=4403)
        return

    upstream_uri = f"ws://127.0.0.1:{port}/{path}"
    # Streamlit's client requests the `streamlit` subprotocol (see
    # WebSocketConnection.ts: `new WebSocket(url, ['streamlit', ...sessionTokens])`)
    # and treats a handshake response that doesn't echo one of its offered
    # subprotocols as a failure ("Sent non-empty 'Sec-WebSocket-Protocol'
    # header but no response was received"). Forward the client's offered
    # subprotocols to the real Streamlit server and echo back whatever it
    # negotiates, rather than guessing one ourselves.
    requested_subprotocols = [
        p.strip() for p in websocket.headers.get("sec-websocket-protocol", "").split(",") if p.strip()
    ]

    try:
        async with ws_client.connect(upstream_uri, subprotocols=requested_subprotocols or None) as upstream:
            await websocket.accept(subprotocol=upstream.subprotocol)

            async def client_to_upstream():
                try:
                    while True:
                        msg = await websocket.receive_bytes()
                        await upstream.send(msg)
                except WebSocketDisconnect:
                    pass

            async def upstream_to_client():
                async for msg in upstream:
                    await websocket.send_bytes(msg if isinstance(msg, bytes) else msg.encode())

            import asyncio

            done, pending = await asyncio.wait(
                [asyncio.create_task(client_to_upstream()), asyncio.create_task(upstream_to_client())],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
    except Exception:
        await websocket.close(code=1011)
