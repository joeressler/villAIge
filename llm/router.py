from __future__ import annotations

from typing import Any, Optional

from config import LLMConfig
from llm.ollama import OllamaProvider
from llm.openai import OpenAIProvider
from llm.provider import LLMProvider, LLMResponse


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
        return self._providers.get(provider_name, self._providers["ollama"])

    def generate(self, prompt: str, model_hint: Optional[str] = None, **kwargs: Any) -> LLMResponse:
        provider = self.get_provider(model_hint)
        return provider.generate(prompt, **kwargs)
