from pathlib import Path
from typing import Any

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from spark_gateway.services.control_plane import AGENT_SLUGS, SCOPES, ControlPlane

router = APIRouter(prefix="/admin", tags=["admin"])

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _control_plane(request: Request) -> ControlPlane:
    return request.app.state.control_plane


def _truthy(value: str) -> bool:
    return value.lower() in {"1", "true", "on", "yes"}


def _admin_context(
    request: Request,
    *,
    active_tab: str | None = None,
    created_key: str | None = None,
    created_portal_user: str | None = None,
    created_invite_url: str | None = None,
    created_invite_email: str | None = None,
    invite_email_sent: bool = False,
    invite_email_error: str | None = None,
    flash: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    cp = _control_plane(request)
    snapshot: dict[str, Any] = {
        "status": {"online": False},
        "customers": [],
        "entitlements": [],
        "api_keys": [],
        "portal_users": [],
        "portal_invites": [],
        "customer_agents": [],
        "by_customer": {},
        "scopes": SCOPES,
        "agent_slugs": AGENT_SLUGS,
    }
    try:
        snapshot = cp.dashboard_snapshot()
    except Exception as exc:  # noqa: BLE001
        error = error or str(exc)
        try:
            snapshot["status"] = cp.get_spark_status()
        except Exception:  # noqa: BLE001
            pass
    return {
        **snapshot,
        "active_tab": active_tab,
        "error": error,
        "flash": flash,
        "created_key": created_key,
        "created_portal_user": created_portal_user,
        "created_invite_url": created_invite_url,
        "created_invite_email": created_invite_email,
        "invite_email_sent": invite_email_sent,
        "invite_email_error": invite_email_error,
        "portal_url": "https://spark-origin.matanitah.com/login",
    }


def _render(
    request: Request,
    *,
    status_code: int = 200,
    **kwargs: Any,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "admin/index.html",
        _admin_context(request, **kwargs),
        status_code=status_code,
    )


def _redirect() -> RedirectResponse:
    return RedirectResponse(url="/admin/", status_code=303)


@router.get("/", response_class=HTMLResponse)
async def admin_home(request: Request) -> HTMLResponse:
    return _render(request)


# --- Spark --------------------------------------------------------------


@router.post("/spark/online")
async def spark_go_online(request: Request, origin_base_url: str = Form("")) -> RedirectResponse:
    try:
        _control_plane(request).set_spark_online(True, origin_base_url=origin_base_url.strip())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return _redirect()


@router.post("/spark/offline")
async def spark_go_offline(request: Request) -> RedirectResponse:
    try:
        _control_plane(request).set_spark_online(False)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return _redirect()


# --- Customers ----------------------------------------------------------


@router.post("/customers")
async def create_customer(
    request: Request,
    customer_id: str = Form(...),
    name: str = Form(...),
    enabled: str = Form("true"),
) -> RedirectResponse:
    _control_plane(request).upsert_customer(
        customer_id=customer_id.strip(),
        name=name.strip(),
        enabled=_truthy(enabled),
    )
    return _redirect()


@router.post("/customers/enable")
async def enable_customer(request: Request, customer_id: str = Form(...)) -> RedirectResponse:
    _control_plane(request).set_customer_enabled(customer_id, True)
    return _redirect()


@router.post("/customers/disable")
async def disable_customer(request: Request, customer_id: str = Form(...)) -> RedirectResponse:
    _control_plane(request).set_customer_enabled(customer_id, False)
    return _redirect()


@router.post("/customers/delete")
async def delete_customer(
    request: Request,
    customer_id: str = Form(...),
    cascade: str = Form("true"),
) -> HTMLResponse:
    try:
        _control_plane(request).delete_customer(customer_id, cascade=_truthy(cascade))
    except Exception as exc:  # noqa: BLE001
        return _render(request, active_tab="customers", error=str(exc), status_code=400)
    return _render(request, active_tab="customers", flash=f"Deleted customer {customer_id.strip()}")


@router.post("/customers/grant-all")
async def grant_all(request: Request, customer_id: str = Form(...)) -> RedirectResponse:
    _control_plane(request).grant_all_scopes(customer_id.strip(), enabled=True)
    return _redirect()


@router.post("/customers/revoke-all")
async def revoke_all(request: Request, customer_id: str = Form(...)) -> RedirectResponse:
    _control_plane(request).revoke_all_scopes(customer_id.strip())
    return _redirect()


# --- Entitlements -------------------------------------------------------


@router.post("/entitlements")
async def set_entitlement(
    request: Request,
    customer_id: str = Form(...),
    scope: str = Form(...),
    enabled: str = Form("true"),
) -> HTMLResponse:
    try:
        _control_plane(request).set_entitlement(
            customer_id=customer_id.strip(),
            scope=scope.strip(),
            enabled=_truthy(enabled),
        )
    except Exception as exc:  # noqa: BLE001
        return _render(request, active_tab="entitlements", error=str(exc), status_code=400)
    return _redirect()


@router.post("/entitlements/delete")
async def delete_entitlement(
    request: Request,
    customer_id: str = Form(...),
    scope: str = Form(...),
) -> RedirectResponse:
    _control_plane(request).delete_entitlement(customer_id, scope)
    return _redirect()


# --- Agent-spark agent entitlements --------------------------------------


@router.post("/agents")
async def set_customer_agent(
    request: Request,
    customer_id: str = Form(...),
    agent_slug: str = Form(...),
    enabled: str = Form("true"),
) -> HTMLResponse:
    try:
        _control_plane(request).set_customer_agent(
            customer_id=customer_id.strip(),
            agent_slug=agent_slug.strip(),
            enabled=_truthy(enabled),
        )
    except Exception as exc:  # noqa: BLE001
        return _render(request, active_tab="agents", error=str(exc), status_code=400)
    return _redirect()


@router.post("/agents/delete")
async def delete_customer_agent(
    request: Request,
    customer_id: str = Form(...),
    agent_slug: str = Form(...),
) -> RedirectResponse:
    _control_plane(request).delete_customer_agent(customer_id, agent_slug)
    return _redirect()


# --- API keys -----------------------------------------------------------


@router.post("/keys", response_class=HTMLResponse)
async def create_key(
    request: Request,
    customer_id: str = Form(...),
    label: str = Form(""),
) -> HTMLResponse:
    raw, _meta = _control_plane(request).create_api_key(
        customer_id=customer_id.strip(),
        label=label.strip(),
    )
    return _render(request, active_tab="api-keys", created_key=raw)


@router.post("/keys/enable")
async def enable_key(request: Request, key_hash: str = Form(...)) -> RedirectResponse:
    _control_plane(request).set_api_key_enabled(key_hash, True)
    return _redirect()


@router.post("/keys/disable")
async def disable_key(request: Request, key_hash: str = Form(...)) -> RedirectResponse:
    _control_plane(request).set_api_key_enabled(key_hash, False)
    return _redirect()


@router.post("/keys/delete")
async def delete_key(request: Request, key_hash: str = Form(...)) -> RedirectResponse:
    _control_plane(request).delete_api_key(key_hash)
    return _redirect()


# --- Portal users -------------------------------------------------------


@router.post("/portal-users", response_class=HTMLResponse)
async def create_portal_user(
    request: Request,
    username: str = Form(...),
    customer_id: str = Form(...),
    password: str = Form(...),
    enabled: str = Form("true"),
) -> HTMLResponse:
    try:
        user = _control_plane(request).upsert_portal_user(
            username=username.strip(),
            customer_id=customer_id.strip(),
            password=password,
            enabled=_truthy(enabled),
        )
    except Exception as exc:  # noqa: BLE001
        return _render(request, active_tab="users", error=str(exc), status_code=400)
    return _render(request, active_tab="users", created_portal_user=user["username"])


@router.post("/portal-users/enable")
async def enable_portal_user(request: Request, username: str = Form(...)) -> RedirectResponse:
    _control_plane(request).set_portal_user_enabled(username, True)
    return _redirect()


@router.post("/portal-users/disable")
async def disable_portal_user(request: Request, username: str = Form(...)) -> RedirectResponse:
    _control_plane(request).set_portal_user_enabled(username, False)
    return _redirect()


@router.post("/portal-users/reassign")
async def reassign_portal_user(
    request: Request,
    username: str = Form(...),
    customer_id: str = Form(...),
) -> RedirectResponse:
    _control_plane(request).reassign_portal_user(username, customer_id)
    return _redirect()


@router.post("/portal-users/delete")
async def delete_portal_user(request: Request, username: str = Form(...)) -> RedirectResponse:
    _control_plane(request).delete_portal_user(username)
    return _redirect()


# --- Portal invites -----------------------------------------------------


@router.post("/invites", response_class=HTMLResponse)
async def create_invite(
    request: Request,
    email: str = Form(...),
    customer_id: str = Form(...),
) -> HTMLResponse:
    try:
        result = _control_plane(request).create_portal_invite(
            email=email.strip(),
            customer_id=customer_id.strip(),
        )
    except Exception as exc:  # noqa: BLE001
        return _render(request, active_tab="invites", error=str(exc), status_code=400)
    return _render(
        request,
        active_tab="invites",
        created_invite_url=result["invite_url"],
        created_invite_email=result["email"],
        invite_email_sent=bool(result.get("email_sent")),
        invite_email_error=result.get("email_error") or None,
    )


@router.post("/invites/revoke")
async def revoke_invite(request: Request, token_hash: str = Form(...)) -> RedirectResponse:
    _control_plane(request).revoke_portal_invite(token_hash)
    return _redirect()


@router.get("/api/status")
async def api_status(request: Request) -> dict[str, Any]:
    return _control_plane(request).get_spark_status()
