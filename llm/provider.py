from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel

LLMResponsePath = Literal["structured", "freeform", "structured_fallback"]


@dataclass
class LLMResponse:
    text: str
    thinking: str = ""
    latency_ms: float = 0.0
    token_usage: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    model: str = ""


@dataclass
class StructuredLLMResult:
    response: LLMResponse
    parsed: BaseModel


class LLMProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, **kwargs: Any) -> LLMResponse:
        pass

    @abstractmethod
    def generate_structured(
        self,
        prompt: str,
        schema: type[BaseModel],
        **kwargs: Any,
    ) -> StructuredLLMResult:
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass
