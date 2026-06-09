from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from exceptions import LLMEmptyResponseError, LLMProviderError
from llm.provider import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)

_REASONING_MODEL_PREFIXES = ("o1", "o3", "o4")


def _is_reasoning_model(model: str) -> bool:
    base = model.split(":")[0].lower()
    return any(base.startswith(prefix) for prefix in _REASONING_MODEL_PREFIXES)


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
        reasoning_enabled = kwargs.get("reasoning_enabled", False)
        use_reasoning = reasoning_enabled and _is_reasoning_model(model)
        start = time.perf_counter()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        }
        if use_reasoning:
            body["reasoning_effort"] = kwargs.get("reasoning_effort", "medium")
        else:
            body["temperature"] = kwargs.get("temperature", 0.7)
        timeout = float(kwargs.get("timeout", 120.0))
        try:
            with httpx.Client(timeout=httpx.Timeout(timeout, connect=10.0)) as client:
                resp = client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=body,
                )
                resp.raise_for_status()
                data = resp.json()
                message = data["choices"][0]["message"]
                text = message.get("content", "") or ""
                thinking = message.get("reasoning_content", "") or ""
                usage = data.get("usage", {})
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)
                completion_details = usage.get("completion_tokens_details", {}) or {}
                reasoning_tokens = completion_details.get("reasoning_tokens", 0)
                tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)
        except httpx.TimeoutException as e:
            logger.error(
                "OpenAI request timed out model=%s url=%s timeout=%ss reasoning=%s",
                model,
                self.base_url,
                timeout,
                use_reasoning,
            )
            raise LLMProviderError(
                f"OpenAI request timed out after {timeout}s for model={model}; "
                "increase llm.reasoning_request_timeout_seconds in config.yaml"
            ) from e
        except httpx.HTTPError as e:
            logger.exception(
                "OpenAI request failed model=%s url=%s", model, self.base_url
            )
            raise LLMProviderError(f"OpenAI request failed: {e}") from e
        except (KeyError, IndexError, TypeError) as e:
            logger.exception(
                "OpenAI response parse failed model=%s url=%s", model, self.base_url
            )
            raise LLMProviderError(f"OpenAI response parse failed: {e}") from e
        elapsed = (time.perf_counter() - start) * 1000

        if (not text or not text.strip()) and thinking.strip():
            logger.warning(
                "OpenAI returned empty content but non-empty reasoning model=%s; "
                "using reasoning as fallback text",
                model,
            )
            text = thinking

        if not text or not text.strip():
            logger.error(
                "OpenAI returned empty response model=%s url=%s", model, self.base_url
            )
            raise LLMEmptyResponseError(
                f"OpenAI returned empty response for model={model}"
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
