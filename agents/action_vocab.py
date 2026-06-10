from __future__ import annotations

from models.schemas import ACTION_ALIASES, VALID_ACTIONS


def resolve_action_type_alias(action_type: str) -> str | None:
    """Map common LLM aliases to canonical action types."""
    cleaned = action_type.strip().lower()
    if cleaned in VALID_ACTIONS:
        return cleaned
    return ACTION_ALIASES.get(cleaned)
