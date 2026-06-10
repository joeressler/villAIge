from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LLMActionProposal(BaseModel):
    """Structured action proposal returned by the decision agent."""

    type: str
    target: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
