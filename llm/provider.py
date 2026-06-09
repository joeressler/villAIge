from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


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


class LLMProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, **kwargs: Any) -> LLMResponse:
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass
