from __future__ import annotations

import logging
import time
from typing import Any

from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from exceptions import LLMEmptyResponseError, LLMParseError, LLMProviderError
from llm.langchain_utils import (
    invoke_with_timing,
    message_to_llm_response,
    salvage_structured_result,
)
from llm.provider import LLMProvider, LLMResponse, StructuredLLMResult

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

    def _build_model(self, **kwargs: Any) -> ChatOpenAI:
        model_name = kwargs.get("model", self.model)
        reasoning_enabled = kwargs.get("reasoning_enabled", False)
        use_reasoning = reasoning_enabled and _is_reasoning_model(model_name)
        timeout = float(kwargs.get("timeout", 120.0))

        model_kwargs: dict[str, Any] = {}
        if use_reasoning:
            model_kwargs["reasoning_effort"] = kwargs.get("reasoning_effort", "medium")

        return ChatOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            model=model_name,
            temperature=None if use_reasoning else kwargs.get("temperature", 0.7),
            timeout=timeout,
            model_kwargs=model_kwargs or None,
        )

    def generate(self, prompt: str, **kwargs: Any) -> LLMResponse:
        model = self._build_model(**kwargs)
        model_name = kwargs.get("model", self.model)
        try:
            message, elapsed = invoke_with_timing(model, prompt)
            return message_to_llm_response(message, model=model_name, latency_ms=elapsed)
        except LLMEmptyResponseError:
            raise
        except LLMParseError:
            raise
        except Exception as e:
            logger.exception(
                "OpenAI request failed model=%s url=%s", model_name, self.base_url
            )
            raise LLMProviderError(f"OpenAI request failed: {e}") from e

    def generate_structured(
        self,
        prompt: str,
        schema: type[BaseModel],
        **kwargs: Any,
    ) -> StructuredLLMResult:
        model = self._build_model(**kwargs)
        model_name = kwargs.get("model", self.model)
        structured = model.with_structured_output(schema, include_raw=True)
        start = time.perf_counter()
        try:
            result = structured.invoke(prompt)
        except Exception as e:
            logger.exception(
                "OpenAI structured output failed model=%s url=%s",
                model_name,
                self.base_url,
            )
            raise LLMParseError(f"Structured output failed: {e}") from e
        elapsed = (time.perf_counter() - start) * 1000

        parsing_error = result.get("parsing_error") if isinstance(result, dict) else None
        if parsing_error:
            salvaged = (
                salvage_structured_result(
                    result, schema, model_name=model_name, elapsed=elapsed
                )
                if isinstance(result, dict)
                else None
            )
            if salvaged is not None:
                logger.info(
                    "Recovered structured output from raw JSON model=%s", model_name
                )
                return salvaged
            raise LLMParseError(f"Structured output parse failed: {parsing_error}")

        parsed = result.get("parsed") if isinstance(result, dict) else result
        if parsed is None:
            raise LLMParseError("Structured output returned no parsed object")

        raw_message = result.get("raw") if isinstance(result, dict) else None
        if raw_message is not None:
            response = message_to_llm_response(
                raw_message, model=model_name, latency_ms=elapsed
            )
            response.text = parsed.model_dump_json()
        else:
            response = LLMResponse(
                text=parsed.model_dump_json(),
                latency_ms=elapsed,
                model=model_name,
            )

        return StructuredLLMResult(response=response, parsed=parsed)
