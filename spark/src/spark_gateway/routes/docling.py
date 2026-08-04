from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from spark_gateway.services.docling import DoclingService

router = APIRouter(prefix="/v1/docling", tags=["docling"])


@router.get("/health")
async def docling_health(request: Request) -> dict[str, Any]:
    docling: DoclingService = request.app.state.docling
    result = await docling.health()
    if not result.get("ok"):
        raise HTTPException(status_code=503, detail=result)
    return result


@router.post("/convert")
async def convert(request: Request, file: UploadFile = File(...)) -> dict[str, Any]:
    docling: DoclingService = request.app.state.docling
    content = await file.read()
    filename = file.filename or "document"
    try:
        return await docling.convert(content=content, filename=filename)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Docling error: {exc}") from exc
