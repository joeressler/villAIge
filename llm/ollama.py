from __future__ import annotations

import time
from typing import Any

import httpx

from llm.provider import LLMProvider, LLMResponse


class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.1:8b"):
        self.base_url = base_url.rstrip("/")
        self.model = model

    @property
    def name(self) -> str:
        return "ollama"

    def generate(self, prompt: str, **kwargs: Any) -> LLMResponse:
        model = kwargs.get("model", self.model)
        start = time.perf_counter()
        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {"temperature": kwargs.get("temperature", 0.7)},
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                text = data.get("response", "")
                tokens = data.get("eval_count", 0) + data.get("prompt_eval_count", 0)
        except (httpx.HTTPError, httpx.TimeoutException):
            text = ""
            tokens = 0
        elapsed = (time.perf_counter() - start) * 1000
        return LLMResponse(text=text, latency_ms=elapsed, token_usage=tokens, model=model)
