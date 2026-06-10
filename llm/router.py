from __future__ import annotations

import logging
from typing import Any, Optional

from pydantic import BaseModel

from config import LLMConfig
from exceptions import ConfigurationError, LLMParseError
from llm.ollama import OllamaProvider
from llm.openai import OpenAIProvider
from llm.provider import LLMProvider, LLMResponse, StructuredLLMResult

logger = logging.getLogger(__name__)


class LLMRouter:
    def __init__(self, config: LLMConfig):
        self.config = config
        self._providers: dict[str, LLMProvider] = {
            "ollama": OllamaProvider(
                base_url=config.ollama_base_url,
                model=config.default_model,
            ),
            "openai": OpenAIProvider(
                api_key=config.openai_api_key,
                base_url=config.openai_base_url,
                model=config.default_model,
            ),
        }

    def get_provider(self, name: Optional[str] = None) -> LLMProvider:
        provider_name = name or self.config.default_provider
        if provider_name not in self._providers:
            valid = ", ".join(sorted(self._providers))
            logger.error(
                "Unknown LLM provider=%s; valid providers: %s", provider_name, valid
            )
            raise ConfigurationError(
                f"Unknown LLM provider '{provider_name}'. Valid providers: {valid}"
            )
        return self._providers[provider_name]

    def _request_timeout(self) -> float:
        if self.config.reasoning_enabled:
            return self.config.reasoning_request_timeout_seconds
        return self.config.request_timeout_seconds

    def _generation_kwargs(self, **kwargs: Any) -> dict[str, Any]:
        merged: dict[str, Any] = {
            "temperature": self.config.temperature,
            "reasoning_enabled": self.config.reasoning_enabled,
            "think": self.config.ollama_think,
            "reasoning_effort": self.config.openai_reasoning_effort,
            "timeout": self._request_timeout(),
        }
        merged.update(kwargs)
        return merged

    def generate(self, prompt: str, model_hint: Optional[str] = None, **kwargs: Any) -> LLMResponse:
        provider = self.get_provider(model_hint)
        return provider.generate(prompt, **self._generation_kwargs(**kwargs))

    def generate_structured(
        self,
        prompt: str,
        schema: type[BaseModel],
        model_hint: Optional[str] = None,
        **kwargs: Any,
    ) -> StructuredLLMResult:
        provider = self.get_provider(model_hint)
        try:
            return provider.generate_structured(
                prompt, schema, **self._generation_kwargs(**kwargs)
            )
        except LLMParseError:
            raise
        except Exception as e:
            logger.exception("Structured output failed via provider=%s", provider.name)
            raise LLMParseError(f"Structured output failed: {e}") from e
