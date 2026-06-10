from __future__ import annotations

import logging
import time
from typing import Any

from langchain_ollama import ChatOllama
from pydantic import BaseModel

from exceptions import LLMEmptyResponseError, LLMParseError, LLMProviderError
from llm.langchain_utils import (
    invoke_with_timing,
    message_to_llm_response,
    salvage_structured_result,
)
from llm.provider import LLMProvider, LLMResponse, StructuredLLMResult

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.1:8b"):
        self.base_url = base_url.rstrip("/")
        self.model = model

    @property
    def name(self) -> str:
        return "ollama"

    def _build_model(self, **kwargs: Any) -> ChatOllama:
        reasoning_enabled = kwargs.get("reasoning_enabled", False)
        think = kwargs.get("think", False)
        reasoning = think if reasoning_enabled else False
        timeout = float(kwargs.get("timeout", 120.0))
        model_name = kwargs.get("model", self.model)
        return ChatOllama(
            base_url=self.base_url,
            model=model_name,
            temperature=kwargs.get("temperature", 0.7),
            reasoning=reasoning,
            client_kwargs={"timeout": timeout},
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
                "Ollama request failed model=%s url=%s", model_name, self.base_url
            )
            raise LLMProviderError(f"Ollama request failed: {e}") from e

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
                "Ollama structured output failed model=%s url=%s",
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
