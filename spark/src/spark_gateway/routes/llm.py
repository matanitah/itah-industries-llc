from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from spark_gateway.services.ollama import OllamaService

router = APIRouter(prefix="/v1/llm", tags=["llm"])


class ChatMessage(BaseModel):
    role: str
    content: str


class CompletionsRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    stream: bool = False


@router.post("/completions")
async def completions(body: CompletionsRequest, request: Request) -> dict[str, Any]:
    ollama: OllamaService = request.app.state.ollama
    try:
        result = await ollama.chat(
            messages=[m.model_dump() for m in body.messages],
            stream=body.stream,
        )
    except Exception as exc:  # noqa: BLE001 — surface upstream errors to edge
        raise HTTPException(status_code=502, detail=f"Ollama error: {exc}") from exc

    message = result.get("message") or {}
    return {
        "id": result.get("created_at") or "ollama",
        "model": ollama.model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": message.get("role", "assistant"),
                    "content": message.get("content", ""),
                },
                "finish_reason": "stop",
            }
        ],
        "raw": result,
    }
