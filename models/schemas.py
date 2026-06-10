from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator


def coerce_stat_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return max(0, round(float(value)))
    except (TypeError, ValueError):
        return default


class Resources(BaseModel):
    food: int = 0
    wood: int = 0
    stone: int = 0
    gold: int = 0


class ElectionState(BaseModel):
    active: bool = False
    candidates: list[str] = Field(default_factory=list)
    days_remaining: int = 0
    ballots: dict[str, str] = Field(default_factory=dict)
    campaign_support: dict[str, int] = Field(default_factory=dict)
    prior_chief: Optional[str] = None


class ThreatState(BaseModel):
    level: str = "stable"
    food_days_remaining: float = 0.0
    wood_days_remaining: float = 0.0
    stone_days_remaining: float = 0.0
    gold_days_remaining: float = 0.0
    message: str = "Village resources are stable."


THREAT_LEVELS = ("stable", "strained", "critical", "crisis")

PRIMARY_GOALS = [
    "become_chief",
    "accumulate_wealth",
    "build_alliances",
    "help_community",
]


class WorldState(BaseModel):
    tick: int = 0
    population: int = 0
    resources: Resources = Field(default_factory=Resources)
    chief: Optional[str] = None
    chief_history: list[str] = Field(default_factory=list)
    threat: ThreatState = Field(default_factory=ThreatState)
    election_state: ElectionState = Field(default_factory=ElectionState)


class AgentPersonality(BaseModel):
    greed: float = 0.5
    sociability: float = 0.5
    aggression: float = 0.5
    honesty: float = 0.5


class AgentStats(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    wealth: int = 10
    reputation: int = 50
    influence: int = 10
    supply_credit: int = 0

    @field_validator("wealth", "reputation", "influence", "supply_credit", mode="before")
    @classmethod
    def _coerce_int_stats(cls, value: Any) -> Any:
        if isinstance(value, float):
            return round(value)
        return value

    def normalized(self) -> "AgentStats":
        return AgentStats(
            wealth=coerce_stat_int(self.wealth),
            reputation=coerce_stat_int(self.reputation),
            influence=coerce_stat_int(self.influence),
            supply_credit=coerce_stat_int(self.supply_credit),
        )


def normalize_agent_stats(agent: "Agent") -> None:
    agent.stats = agent.stats.normalized()


class AgentGoals(BaseModel):
    primary: str = "become_chief"
    secondary: list[str] = Field(default_factory=list)


class Agent(BaseModel):
    id: str
    name: str
    role: str
    stats: AgentStats = Field(default_factory=AgentStats)
    personality: AgentPersonality = Field(default_factory=AgentPersonality)
    goals: AgentGoals = Field(default_factory=AgentGoals)


class MemoryEvent(BaseModel):
    id: str
    agent_id: str
    tick: int
    text: str
    importance: float = 0.5
    emotion: str = "neutral"


class Relationship(BaseModel):
    a_id: str
    b_id: str
    trust: float = 0.5
    respect: float = 0.5
    fear: float = 0.0
    friendship: float = 0.3


ACTION_CATEGORIES: dict[str, str] = {
    "trade": "economic",
    "gift": "economic",
    "steal": "hostile",
    "sabotage": "hostile",
    "talk": "social",
    "persuade": "social",
    "campaign": "political",
    "vote": "political",
    "build": "civic",
    "quarry": "civic",
}


def get_action_category(action_type: str) -> str:
    return ACTION_CATEGORIES.get(action_type, "unknown")


class Action(BaseModel):
    type: str
    target: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def category(self) -> str:
        return get_action_category(self.type)


VALID_ACTIONS = frozenset(ACTION_CATEGORIES.keys())

# Every action must involve another villager — no solo gathering, building, etc.
ACTIONS_REQUIRING_TARGET: frozenset[str] = VALID_ACTIONS

ACTION_ALIASES: dict[str, str] = {
    "craft": "build",
    "chat": "talk",
    "speak": "talk",
    "gather": "trade",
    "hunt": "trade",
    "forage": "trade",
    "collect": "trade",
    "harvest": "trade",
}


def normalize_action_type(action_type: str) -> str:
    from agents.action_vocab import resolve_action_type_alias

    cleaned = action_type.strip().lower()
    mapped = resolve_action_type_alias(cleaned)
    return mapped if mapped is not None else cleaned

ROLE_DISTRIBUTION = {
    "farmer": 0.4,
    "woodcutter": 0.25,
    "trader": 0.15,
    "builder": 0.1,
    "guard": 0.1,
}

FIRST_NAMES = [
    "Alden", "Bryn", "Cora", "Dara", "Ewan", "Faye", "Gareth", "Hilda",
    "Ivor", "Juna", "Kael", "Lira", "Maren", "Nils", "Orin", "Petra",
    "Quinn", "Rhea", "Soren", "Tilda", "Ulric", "Vera", "Wynn", "Yara",
    "Zane",
]
