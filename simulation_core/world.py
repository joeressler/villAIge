from __future__ import annotations

import random
import uuid
from typing import Optional

from config import AppConfig
from db.repository import Repository
from models.schemas import (
    FIRST_NAMES,
    ROLE_DISTRIBUTION,
    Agent,
    AgentGoals,
    AgentPersonality,
    AgentStats,
    ElectionState,
    Relationship,
    Resources,
    WorldState,
)


class World:
    def __init__(self, config: AppConfig, repo: Repository):
        self.config = config
        self.repo = repo
        self.state: WorldState = WorldState()
        self.agents: dict[str, Agent] = {}

    def initialize(self) -> WorldState:
        self.repo.initialize()
        existing = self.repo.get_world_state()
        if existing and self.repo.get_all_agents():
            self.state = existing
            self.agents = {a.id: a for a in self.repo.get_all_agents()}
            return self.state

        res = self.config.world.initial_resources
        self.state = WorldState(
            tick=0,
            population=self.config.world.initial_population,
            resources=Resources(**res),
            chief=None,
            election_state=ElectionState(),
        )
        self._spawn_agents()
        self._init_relationships()
        self.repo.save_world_state(self.state)
        return self.state

    def _spawn_agents(self) -> None:
        names = random.sample(
            FIRST_NAMES, min(self.config.world.initial_population, len(FIRST_NAMES))
        )
        roles = self._assign_roles(self.config.world.initial_population)

        for i in range(self.config.world.initial_population):
            name = names[i % len(names)]
            agent = Agent(
                id=str(uuid.uuid4())[:8],
                name=name,
                role=roles[i],
                stats=AgentStats(
                    wealth=random.randint(5, 30),
                    reputation=random.randint(30, 70),
                    influence=random.randint(5, 20),
                ),
                personality=AgentPersonality(
                    greed=round(random.uniform(0.1, 0.9), 2),
                    sociability=round(random.uniform(0.1, 0.9), 2),
                    aggression=round(random.uniform(0.1, 0.9), 2),
                    honesty=round(random.uniform(0.1, 0.9), 2),
                ),
                goals=AgentGoals(
                    primary="become_chief",
                    secondary=random.sample(
                        ["accumulate_wealth", "build_alliances", "help_community"],
                        k=random.randint(1, 2),
                    ),
                ),
            )
            self.agents[agent.id] = agent
            self.repo.save_agent(agent)

    def _assign_roles(self, count: int) -> list[str]:
        roles: list[str] = []
        for role, fraction in ROLE_DISTRIBUTION.items():
            roles.extend([role] * max(1, int(count * fraction)))
        while len(roles) < count:
            roles.append("farmer")
        return roles[:count]

    def _init_relationships(self) -> None:
        agent_ids = list(self.agents.keys())
        for i, a_id in enumerate(agent_ids):
            for b_id in agent_ids[i + 1 :]:
                rel = Relationship(
                    a_id=a_id,
                    b_id=b_id,
                    trust=round(random.uniform(0.2, 0.6), 2),
                    respect=round(random.uniform(0.2, 0.6), 2),
                    fear=round(random.uniform(0.0, 0.2), 2),
                    friendship=round(random.uniform(0.1, 0.4), 2),
                )
                self.repo.save_relationship(rel)

    def get_agent(self, agent_id: str) -> Optional[Agent]:
        return self.agents.get(agent_id)

    def update_agent(self, agent: Agent) -> None:
        self.agents[agent.id] = agent
        self.repo.save_agent(agent)

    def set_chief(self, agent_id: str) -> None:
        self.state.chief = agent_id
        agent = self.agents.get(agent_id)
        if agent:
            agent.stats.influence += 20
            agent.stats.reputation += 10
            self.update_agent(agent)
