"""Thin wrapper around a local ollama server, shared by every agent."""

import json
import logging

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

log = logging.getLogger("agent_spark_core.llm")


class LLMError(Exception):
    pass


class LLMClient:
    def __init__(self, host: str, model: str, timeout_s: float, ctx: int):
        self.host = host.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s
        self.ctx = ctx

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=30))
    def chat(self, messages: list[dict], json_mode: bool = False, temperature: float = 0.2) -> str:
        """Send a chat completion to ollama, return the response text."""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_ctx": self.ctx},
        }
        if json_mode:
            payload["format"] = "json"

        try:
            resp = httpx.post(f"{self.host}/api/chat", json=payload, timeout=self.timeout_s)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise LLMError(f"ollama request failed: {e}") from e

        data = resp.json()
        content = data.get("message", {}).get("content", "")
        if not content:
            raise LLMError(f"empty response from ollama: {data}")
        return content

    def chat_json(self, messages: list[dict], temperature: float = 0.1) -> dict:
        """Chat completion constrained to JSON output; returns parsed dict."""
        raw = self.chat(messages, json_mode=True, temperature=temperature)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Sometimes models wrap JSON in prose/fences despite format=json; try to salvage.
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1:
                try:
                    return json.loads(raw[start : end + 1])
                except json.JSONDecodeError:
                    pass
            log.warning("failed to parse JSON from LLM, raw=%r", raw[:500])
            raise LLMError(f"could not parse JSON response: {raw[:500]}")
