from __future__ import annotations


class VillageSimulationError(Exception):
    """Base error for village simulation failures."""


class ConfigurationError(VillageSimulationError):
    """Invalid or unknown configuration."""


class LLMProviderError(VillageSimulationError):
    """LLM provider HTTP or transport failure."""


class LLMEmptyResponseError(VillageSimulationError):
    """LLM returned whitespace-only content."""


class LLMParseError(VillageSimulationError):
    """Could not parse LLM output into a valid action."""


class InvalidActionError(VillageSimulationError):
    """Action failed validation against game rules."""


class VectorStoreError(VillageSimulationError):
    """ChromaDB or vector operation failure."""
