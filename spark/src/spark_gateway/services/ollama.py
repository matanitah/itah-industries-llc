from typing import Any

import httpx

from spark_gateway.config import Settings


def _model_matches(configured: str, available: list[str]) -> bool:
    if not configured:
        return bool(available)
    if configured in available:
        return True
    # Allow "llama3.2" to match "llama3.2:latest"
    base = configured.split(":")[0]
    return any(m == configured or m.startswith(f"{base}:") or m == base for m in available)


class OllamaService:
    def __init__(self, settings: Settings) -> None:
        self._base = settings.ollama_base_url.rstrip("/")
        self._configured_model = (settings.ollama_model or "").strip()
        self._resolved_model: str | None = self._configured_model or None

    @property
    def model(self) -> str:
        return self._resolved_model or self._configured_model or "(auto)"

    async def list_models(self) -> list[str]:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{self._base}/api/tags")
            response.raise_for_status()
            return [m.get("name") for m in response.json().get("models", []) if m.get("name")]

    async def resolve_model(self) -> str:
        if self._resolved_model:
            return self._resolved_model
        models = await self.list_models()
        if self._configured_model:
            if not _model_matches(self._configured_model, models):
                raise RuntimeError(
                    f"Configured model {self._configured_model!r} not found in Ollama. "
                    f"Available: {models}"
                )
            # Prefer exact tag if present, else first matching family.
            if self._configured_model in models:
                self._resolved_model = self._configured_model
            else:
                base = self._configured_model.split(":")[0]
                self._resolved_model = next(
                    m for m in models if m == base or m.startswith(f"{base}:")
                )
            return self._resolved_model
        if not models:
            raise RuntimeError("No Ollama models installed. Run: ollama pull <model>")
        self._resolved_model = models[0]
        return self._resolved_model

    async def health(self) -> dict[str, Any]:
        try:
            models = await self.list_models()
            if self._configured_model:
                ok = _model_matches(self._configured_model, models)
                model = self._configured_model
            else:
                ok = bool(models)
                model = models[0] if models else "(none)"
                if models:
                    self._resolved_model = models[0]
            return {"ok": ok, "model": model, "models": models}
        except httpx.HTTPError as exc:
            return {"ok": False, "model": self.model, "error": str(exc)}

    async def chat(self, messages: list[dict[str, str]], stream: bool = False) -> dict[str, Any]:
        model = await self.resolve_model()
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(f"{self._base}/api/chat", json=payload)
            response.raise_for_status()
            return response.json()
