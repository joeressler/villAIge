from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class Resources(BaseModel):
    food: int = 0
    wood: int = 0
    stone: int = 0
    gold: int = 0


class ElectionState(BaseModel):
    active: bool = False
    candidates: list[str] = Field(default_factory=list)
    days_remaining: int = 0


class WorldState(BaseModel):
    tick: int = 0
    population: int = 0
    resources: Resources = Field(default_factory=Resources)
    chief: Optional[str] = None
    election_state: ElectionState = Field(default_factory=ElectionState)


class AgentPersonality(BaseModel):
    greed: float = 0.5
    sociability: float = 0.5
    aggression: float = 0.5
    honesty: float = 0.5


class AgentStats(BaseModel):
    wealth: int = 10
    reputation: int = 50
    influence: int = 10


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


class Action(BaseModel):
    type: str
    target: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)


VALID_ACTIONS = frozenset(
    {"trade", "talk", "campaign", "vote", "gift", "steal", "build", "persuade"}
)

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
