from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field


class SimulationConfig(BaseModel):
    tick_duration_seconds: float = 0.5
    election_interval_ticks: int = 30
    profile_ticks: bool = True


class WorldConfig(BaseModel):
    initial_population: int = 20
    initial_resources: dict[str, int] = Field(
        default_factory=lambda: {"food": 30, "wood": 100, "stone": 50, "gold": 200}
    )


class LLMConfig(BaseModel):
    default_provider: str = "ollama"
    default_model: str = "granite4.1:8b"
    ollama_base_url: str = "http://localhost:11434"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str = ""
    reasoning_enabled: bool = True
    ollama_think: bool = True
    temperature: float = 0.7
    openai_reasoning_effort: str = "medium"
    store_reasoning_memory: bool = True
    reasoning_memory_importance: float = 0.75
    request_timeout_seconds: float = 120.0
    reasoning_request_timeout_seconds: float = 300.0
    action_aliases: dict[str, str] = Field(default_factory=dict)
    max_decision_attempts: int = 3
    structured_output_enabled: bool = True


class MemoryConfig(BaseModel):
    embedding_provider: str = "ollama"
    embedding_model: str = "nomic-embed-text"
    vector_store: str = "chromadb"
    embedding_dim: int = 768
    max_retrieval: int = 10
    chroma_host: str = "localhost"
    chroma_port: int = 8100
    chroma_collection: str = "village_memories"


class ElectionConfig(BaseModel):
    standing_wealth_weight: float = 0.45
    standing_reputation_weight: float = 0.55
    candidate_count: int = 5
    wildcard_slots: int = 1
    chief_cooldown_terms: int = 1
    max_campaign_rep_per_tick: int = 1
    max_campaign_rep_per_election: int = 3
    winner_rep_bonus: int = 5
    chief_bonus_rep: int = 5
    chief_bonus_influence: int = 10
    rep_decay_rate: float = 0.02
    abstain_fallback: str = "weighted"


class TradeResourceConfig(BaseModel):
    seller_roles: list[str] = Field(default_factory=list)
    default_amount: int = 1
    default_price: int = 3


def _default_trade_catalog() -> dict[str, TradeResourceConfig]:
    return {
        "food": TradeResourceConfig(
            seller_roles=["farmer", "trader"], default_amount=1, default_price=3
        ),
        "wood": TradeResourceConfig(
            seller_roles=["woodcutter", "trader"], default_amount=1, default_price=4
        ),
        "stone": TradeResourceConfig(
            seller_roles=["builder", "trader"], default_amount=1, default_price=5
        ),
    }


class EconomyConfig(BaseModel):
    stewardship_mode: bool = True
    food_per_agent: int = 1
    scarcity_enabled: bool = True
    farmer_production: int = 3
    farmer_max_food_sale_per_tick: int = 1
    woodcutter_production: int = 3
    builder_quarry_wood_cost: int = 1
    builder_quarry_stone_per_unit: int = 3
    builder_quarry_max_per_action: int = 1
    builder_stone_production: int = 2
    consumption_per_agent: int = 1
    trader_conversion_rate: int = 2
    trader_gold_cost: int = 5
    gift_rep_gain: int = 1
    gift_pair_cooldown_ticks: int = 8
    gift_reciprocal_window_ticks: int = 5
    gift_reciprocal_relationship_multiplier: float = 0.25
    trade_catalog: dict[str, TradeResourceConfig] = Field(
        default_factory=_default_trade_catalog
    )
    trade_buyer_rep: int = 1
    trade_seller_rep: int = 1
    trade_supply_credit_per_unit: int = 1
    steal_rep_penalty_base: int = 2
    steal_rep_penalty_if_liked_target: int = 4
    steal_gold_cap: int = 3
    sabotage_rep_penalty_base: int = 1
    sabotage_rep_penalty_if_liked_target: int = 3
    sabotage_max_amount: int = 2
    guard_mitigation_factor: float = 0.5
    threat_food_stable_days: float = 5.0
    threat_food_strained_days: float = 2.0
    threat_food_critical_days: float = 1.0
    threat_wood_stable: int = 20
    threat_wood_strained: int = 10
    threat_wood_critical: int = 5
    threat_stone_stable: int = 10
    threat_stone_strained: int = 5
    threat_stone_critical: int = 2
    threat_gold_stable: int = 50
    threat_gold_strained: int = 25
    threat_gold_critical: int = 10


class LangfuseConfig(BaseModel):
    """Langfuse tracing settings.

    Loaded from config.yaml, then overridden by .env:
    LANGFUSE_ENABLED, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY,
    LANGFUSE_BASE_URL (or LANGFUSE_HOST), LANGFUSE_SIMULATE_COST,
    LANGFUSE_INPUT_COST_PER_MILLION_USD, LANGFUSE_OUTPUT_COST_PER_MILLION_USD.
    API keys must match LANGFUSE_INIT_PROJECT_* in .env; UI login uses
    LANGFUSE_INIT_USER_*.
    """

    enabled: bool = False
    public_key: str = ""
    secret_key: str = ""
    base_url: str = ""
    host: str = ""
    simulate_cost: bool = True
    input_cost_per_million_usd: float = 1.50
    output_cost_per_million_usd: float = 9.00

    @property
    def resolved_base_url(self) -> str:
        return self.base_url or self.host


class DatabaseConfig(BaseModel):
    path: str = "data/village.db"


class AppConfig(BaseModel):
    simulation: SimulationConfig = Field(default_factory=SimulationConfig)
    world: WorldConfig = Field(default_factory=WorldConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    election: ElectionConfig = Field(default_factory=ElectionConfig)
    economy: EconomyConfig = Field(default_factory=EconomyConfig)
    langfuse: LangfuseConfig = Field(default_factory=LangfuseConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)


def _env_bool(name: str) -> bool | None:
    value = os.environ.get(name)
    if value is None:
        return None
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _apply_env_overrides(config: AppConfig) -> AppConfig:
    langfuse_enabled = _env_bool("LANGFUSE_ENABLED")
    if langfuse_enabled is not None:
        config.langfuse.enabled = langfuse_enabled
    if public_key := os.environ.get("LANGFUSE_PUBLIC_KEY"):
        config.langfuse.public_key = public_key
    if secret_key := os.environ.get("LANGFUSE_SECRET_KEY"):
        config.langfuse.secret_key = secret_key
    if base_url := os.environ.get("LANGFUSE_BASE_URL"):
        config.langfuse.base_url = base_url
    elif host := os.environ.get("LANGFUSE_HOST"):
        config.langfuse.host = host
    simulate_cost = _env_bool("LANGFUSE_SIMULATE_COST")
    if simulate_cost is not None:
        config.langfuse.simulate_cost = simulate_cost
    if input_cost := os.environ.get("LANGFUSE_INPUT_COST_PER_MILLION_USD"):
        config.langfuse.input_cost_per_million_usd = float(input_cost)
    if output_cost := os.environ.get("LANGFUSE_OUTPUT_COST_PER_MILLION_USD"):
        config.langfuse.output_cost_per_million_usd = float(output_cost)
    if db_path := os.environ.get("DATABASE_PATH"):
        config.database.path = db_path
    if ollama_url := os.environ.get("OLLAMA_BASE_URL"):
        config.llm.ollama_base_url = ollama_url
    reasoning_enabled = _env_bool("LLM_REASONING_ENABLED")
    if reasoning_enabled is not None:
        config.llm.reasoning_enabled = reasoning_enabled
    ollama_think = _env_bool("OLLAMA_THINK")
    if ollama_think is not None:
        config.llm.ollama_think = ollama_think
    if temperature := os.environ.get("LLM_TEMPERATURE"):
        config.llm.temperature = float(temperature)
    if reasoning_effort := os.environ.get("OPENAI_REASONING_EFFORT"):
        config.llm.openai_reasoning_effort = reasoning_effort
    if timeout := os.environ.get("LLM_REQUEST_TIMEOUT_SECONDS"):
        config.llm.request_timeout_seconds = float(timeout)
    if reasoning_timeout := os.environ.get("LLM_REASONING_REQUEST_TIMEOUT_SECONDS"):
        config.llm.reasoning_request_timeout_seconds = float(reasoning_timeout)
    if chroma_host := os.environ.get("CHROMA_HOST"):
        config.memory.chroma_host = chroma_host
    if chroma_port := os.environ.get("CHROMA_PORT"):
        config.memory.chroma_port = int(chroma_port)
    if chroma_collection := os.environ.get("CHROMA_COLLECTION"):
        config.memory.chroma_collection = chroma_collection
    if embedding_provider := os.environ.get("EMBEDDING_PROVIDER"):
        config.memory.embedding_provider = embedding_provider
    if embedding_model := os.environ.get("EMBEDDING_MODEL"):
        config.memory.embedding_model = embedding_model
    if embedding_dim := os.environ.get("EMBEDDING_DIM"):
        config.memory.embedding_dim = int(embedding_dim)
    return config


def load_config(path: str | Path | None = None) -> AppConfig:
    load_dotenv()
    config_path = Path(path or os.environ.get("CONFIG_PATH", "config.yaml"))
    if not config_path.exists():
        return _apply_env_overrides(AppConfig())
    with config_path.open() as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}
    return _apply_env_overrides(AppConfig(**raw))
