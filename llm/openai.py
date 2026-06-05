from __future__ import annotations

import time
from typing import Any

import httpx

from llm.provider import LLMProvider, LLMResponse


class OpenAIProvider(LLMProvider):
    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    @property
    def name(self) -> str:
        return "openai"

    def generate(self, prompt: str, **kwargs: Any) -> LLMResponse:
        model = kwargs.get("model", self.model)
        start = time.perf_counter()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": kwargs.get("temperature", 0.7),
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                text = data["choices"][0]["message"]["content"]
                tokens = data.get("usage", {}).get("total_tokens", 0)
        except (httpx.HTTPError, httpx.TimeoutException, KeyError):
            text = ""
            tokens = 0
        elapsed = (time.perf_counter() - start) * 1000
        return LLMResponse(text=text, latency_ms=elapsed, token_usage=tokens, model=model)
