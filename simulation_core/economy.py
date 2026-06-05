from __future__ import annotations

import random

from config import AppConfig
from models.schemas import Agent, WorldState


class Economy:
    def __init__(self, config: AppConfig):
        self.config = config

    def produce(self, agents: dict[str, Agent], state: WorldState) -> WorldState:
        food_produced = 0
        wood_produced = 0

        for agent in agents.values():
            if agent.role == "farmer":
                food_produced += self.config.economy.farmer_production
                agent.stats.wealth += 1
            elif agent.role == "woodcutter":
                wood_produced += self.config.economy.woodcutter_production
                agent.stats.wealth += 1
            elif agent.role == "builder":
                if state.resources.stone >= 1 and state.resources.wood >= 2:
                    state.resources.stone -= 1
                    state.resources.wood -= 2
                    agent.stats.wealth += 3
                    agent.stats.reputation += 1

        state.resources.food += food_produced
        state.resources.wood += wood_produced
        return state

    def consume(self, agents: dict[str, Agent], state: WorldState) -> WorldState:
        demand = len(agents) * self.config.economy.consumption_per_agent
        if self.config.economy.scarcity_enabled:
            available = state.resources.food
            if available < demand:
                shortage = demand - available
                state.resources.food = 0
                self._apply_scarcity_effects(agents, shortage)
            else:
                state.resources.food -= demand
        else:
            state.resources.food = max(0, state.resources.food - demand)
        return state

    def _apply_scarcity_effects(self, agents: dict[str, Agent], shortage: int) -> None:
        sorted_agents = sorted(agents.values(), key=lambda a: a.stats.wealth, reverse=True)
        affected = min(shortage, len(sorted_agents))
        for agent in sorted_agents[-affected:]:
            agent.stats.reputation = max(0, agent.stats.reputation - 2)
            if random.random() < 0.3:
                agent.stats.wealth = max(0, agent.stats.wealth - 1)

    def apply_trade(
        self, buyer: Agent, seller: Agent, resource: str, amount: int, price: int
    ) -> bool:
        if buyer.stats.wealth < price:
            return False
        buyer.stats.wealth -= price
        seller.stats.wealth += price
        return True

    def apply_steal(self, thief: Agent, victim: Agent, amount: int) -> int:
        stolen = min(amount, victim.stats.wealth)
        victim.stats.wealth -= stolen
        thief.stats.wealth += stolen
        thief.stats.reputation = max(0, thief.stats.reputation - 5)
        return stolen

    def apply_gift(self, giver: Agent, receiver: Agent, amount: int) -> int:
        given = min(amount, giver.stats.wealth)
        giver.stats.wealth -= given
        receiver.stats.wealth += given
        giver.stats.reputation += 2
        return given
