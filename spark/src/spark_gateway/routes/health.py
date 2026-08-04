from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from spark_gateway.config import Settings
from spark_gateway.services.docling import DoclingService
from spark_gateway.services.ollama import OllamaService

router = APIRouter(tags=["health"])


@router.get("/v1/health")
async def spark_health(request: Request) -> JSONResponse:
    settings: Settings = request.app.state.settings
    ollama: OllamaService = request.app.state.ollama
    docling: DoclingService = request.app.state.docling

    ollama_health = await ollama.health()
    docling_health = await docling.health()
    ok = bool(ollama_health.get("ok"))
    status_code = 200 if ok else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "ok": ok,
            "service": settings.app_name,
            "ollama": ollama_health,
            "docling": docling_health,
        },
    )
