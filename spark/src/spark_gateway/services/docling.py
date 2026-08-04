from typing import Any

import httpx

from spark_gateway.config import Settings


class DoclingService:
    def __init__(self, settings: Settings) -> None:
        self._base = settings.docling_base_url.rstrip("/")

    async def health(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                response = await client.get(f"{self._base}/health")
                response.raise_for_status()
                body: dict[str, Any]
                try:
                    body = response.json()
                except ValueError:
                    body = {"raw": response.text}
                return {"ok": True, "upstream": body}
            except httpx.HTTPError as exc:
                return {"ok": False, "error": str(exc)}

    async def convert(self, content: bytes, filename: str) -> dict[str, Any]:
        """Proxy convert call to the local Docling service.

        Exact Docling HTTP contract may vary by deployment; this is the scaffold hook.
        """
        files = {"file": (filename, content)}
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(f"{self._base}/v1/convert/file", files=files)
            response.raise_for_status()
            return response.json()
