from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class SimulationConfig(BaseModel):
    tick_duration_seconds: float = 0.5
    election_interval_ticks: int = 30


class WorldConfig(BaseModel):
    initial_population: int = 20
    initial_resources: dict[str, int] = Field(
        default_factory=lambda: {"food": 50, "wood": 100, "stone": 50, "gold": 200}
    )


class LLMConfig(BaseModel):
    default_provider: str = "ollama"
    default_model: str = "llama3.1:8b"
    ollama_base_url: str = "http://localhost:11434"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str = ""


class MemoryConfig(BaseModel):
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    vector_store: str = "sqlite-vss"
    embedding_dim: int = 384
    max_retrieval: int = 10


class EconomyConfig(BaseModel):
    food_per_agent: int = 1
    scarcity_enabled: bool = True
    farmer_production: int = 2
    woodcutter_production: int = 3
    consumption_per_agent: int = 3


class LangfuseConfig(BaseModel):
    enabled: bool = False
    public_key: str = ""
    secret_key: str = ""
    host: str = "https://cloud.langfuse.com"


class DatabaseConfig(BaseModel):
    path: str = "data/village.db"


class AppConfig(BaseModel):
    simulation: SimulationConfig = Field(default_factory=SimulationConfig)
    world: WorldConfig = Field(default_factory=WorldConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    economy: EconomyConfig = Field(default_factory=EconomyConfig)
    langfuse: LangfuseConfig = Field(default_factory=LangfuseConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    config_path = Path(path)
    if not config_path.exists():
        return AppConfig()
    with config_path.open() as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}
    return AppConfig(**raw)
