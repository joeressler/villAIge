from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from exceptions import LLMEmptyResponseError, LLMProviderError
from llm.provider import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.1:8b"):
        self.base_url = base_url.rstrip("/")
        self.model = model

    @property
    def name(self) -> str:
        return "ollama"

    def generate(self, prompt: str, **kwargs: Any) -> LLMResponse:
        model = kwargs.get("model", self.model)
        reasoning_enabled = kwargs.get("reasoning_enabled", False)
        think = kwargs.get("think", False) if reasoning_enabled else False
        timeout = float(kwargs.get("timeout", 120.0))
        start = time.perf_counter()
        try:
            with httpx.Client(timeout=httpx.Timeout(timeout, connect=10.0)) as client:
                payload: dict[str, Any] = {
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "think": think,
                    "options": {"temperature": kwargs.get("temperature", 0.7)},
                }
                resp = client.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                text = data.get("response", "")
                thinking = data.get("thinking", "") or ""
                prompt_tokens = data.get("prompt_eval_count", 0)
                completion_tokens = data.get("eval_count", 0)
                reasoning_tokens = data.get("thinking_eval_count", 0)
                tokens = prompt_tokens + completion_tokens + reasoning_tokens
        except httpx.TimeoutException as e:
            logger.error(
                "Ollama request timed out model=%s url=%s timeout=%ss think=%s",
                model,
                self.base_url,
                timeout,
                think,
            )
            raise LLMProviderError(
                f"Ollama request timed out after {timeout}s for model={model} "
                f"(reasoning={think}); increase llm.reasoning_request_timeout_seconds "
                "in config.yaml or set LLM_REASONING_REQUEST_TIMEOUT_SECONDS"
            ) from e
        except httpx.HTTPError as e:
            logger.exception(
                "Ollama request failed model=%s url=%s", model, self.base_url
            )
            raise LLMProviderError(f"Ollama request failed: {e}") from e
        elapsed = (time.perf_counter() - start) * 1000

        if (not text or not text.strip()) and thinking.strip():
            logger.warning(
                "Ollama returned empty response but non-empty thinking model=%s; "
                "using thinking as fallback text",
                model,
            )
            text = thinking

        if not text or not text.strip():
            logger.error(
                "Ollama returned empty response model=%s url=%s", model, self.base_url
            )
            raise LLMEmptyResponseError(
                f"Ollama returned empty response for model={model}"
            )
        return LLMResponse(
            text=text,
            thinking=thinking,
            latency_ms=elapsed,
            token_usage=tokens,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            reasoning_tokens=reasoning_tokens,
            model=model,
        )
