from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from spark_gateway.config import Settings, get_settings
from spark_gateway.middleware import EdgeTokenMiddleware
from spark_gateway.routes import admin, docling, health, llm
from spark_gateway.services.control_plane import ControlPlane
from spark_gateway.services.docling import DoclingService
from spark_gateway.services.ollama import OllamaService


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0")
    app.state.settings = settings
    app.state.ollama = OllamaService(settings)
    app.state.docling = DoclingService(settings)
    app.state.control_plane = ControlPlane(settings)

    app.add_middleware(EdgeTokenMiddleware, settings=settings)

    app.include_router(health.router)
    app.include_router(llm.router)
    app.include_router(docling.router)
    app.include_router(admin.router)

    static_dir = Path(__file__).resolve().parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    return app


app = create_app()
