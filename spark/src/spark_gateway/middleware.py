from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from spark_gateway.config import Settings


class EdgeTokenMiddleware(BaseHTTPMiddleware):
    """Reject /v1 traffic that bypasses API Gateway when a shared token is configured.

    Admin routes are excluded so localhost admin keeps working without the edge token.
    """

    def __init__(self, app, settings: Settings) -> None:  # noqa: ANN001
        super().__init__(app)
        self._token = settings.edge_shared_token

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        if not self._token or path.startswith("/admin") or path in {"/docs", "/openapi.json", "/redoc"}:
            return await call_next(request)

        # Direct tunnel path for the agent-dashboard iframe (see
        # routes/agents.py) -- reached straight over the tunnel hostname
        # rather than through API Gateway, so it never carries the edge
        # token; it has its own short-lived signed-token check instead.
        if path.startswith("/agents/"):
            return await call_next(request)

        if path.startswith("/v1"):
            provided = request.headers.get("x-itah-edge-token", "")
            if provided != self._token:
                return Response(content='{"detail":"invalid edge token"}', status_code=401, media_type="application/json")

        return await call_next(request)
