from __future__ import annotations

import random

from config import AppConfig
from models.schemas import Agent, WorldState, coerce_stat_int


class Economy:
    def __init__(self, config: AppConfig):
        self.config = config

    def _food_demand(self, agents: dict[str, Agent]) -> int:
        per_agent = self.config.economy.consumption_per_agent
        if per_agent <= 0:
            per_agent = self.config.economy.food_per_agent
        return len(agents) * per_agent

    def food_demand(self, agents: dict[str, Agent]) -> int:
        return self._food_demand(agents)

    def produce(self, agents: dict[str, Agent], state: WorldState) -> WorldState:
        cfg = self.config.economy
        food_produced = 0
        wood_produced = 0

        for agent in agents.values():
            if agent.role == "farmer":
                produced = cfg.farmer_production
                food_produced += produced
                agent.stats.wealth += 1
                agent.stats.reputation += min(produced, 2)
            elif agent.role == "woodcutter":
                wood_produced += cfg.woodcutter_production
                agent.stats.wealth += 1
            elif agent.role == "builder":
                if state.threat.level != "crisis":
                    if state.resources.stone >= 1 and state.resources.wood >= 2:
                        state.resources.stone -= 1
                        state.resources.wood -= 2
                        agent.stats.wealth += 3
                        agent.stats.reputation += 1
            elif agent.role == "trader":
                if (
                    state.resources.food < self._food_demand(agents)
                    and state.resources.gold >= cfg.trader_gold_cost
                ):
                    state.resources.gold -= cfg.trader_gold_cost
                    state.resources.food += cfg.trader_conversion_rate
                    agent.stats.wealth += 2
                    agent.stats.reputation += 1
                elif state.resources.wood < cfg.threat_wood_strained and state.resources.gold >= cfg.trader_gold_cost:
                    state.resources.gold -= cfg.trader_gold_cost
                    state.resources.wood += cfg.trader_conversion_rate
                    agent.stats.wealth += 2

        state.resources.food += food_produced
        state.resources.wood += wood_produced
        return state

    def consume(self, agents: dict[str, Agent], state: WorldState) -> WorldState:
        demand = self._food_demand(agents)
        available = state.resources.food
        consumed = min(available, demand)
        state.resources.food -= consumed

        if self.config.economy.scarcity_enabled and consumed < demand:
            self._apply_scarcity_effects(agents, demand - consumed)
        return state

    def _apply_scarcity_effects(self, agents: dict[str, Agent], shortage: int) -> None:
        sorted_agents = sorted(agents.values(), key=lambda a: a.stats.wealth, reverse=True)
        affected = min(shortage, len(sorted_agents))
        for agent in sorted_agents[-affected:]:
            agent.stats.reputation = max(0, agent.stats.reputation - 2)
            if random.random() < 0.3:
                agent.stats.wealth = max(0, agent.stats.wealth - 1)

    def apply_rep_decay(self, agents: dict[str, Agent]) -> None:
        rate = self.config.election.rep_decay_rate
        if rate <= 0 or not agents:
            return
        reps = sorted(a.stats.reputation for a in agents.values())
        if not reps:
            return
        mid = len(reps) // 2
        if len(reps) % 2 == 0:
            median = (reps[mid - 1] + reps[mid]) / 2
        else:
            median = reps[mid]
        for agent in agents.values():
            delta = median - agent.stats.reputation
            agent.stats.reputation = max(0, round(agent.stats.reputation + delta * rate))

    def guard_count(self, agents: dict[str, Agent]) -> int:
        return sum(1 for a in agents.values() if a.role == "guard")

    def apply_trade(
        self, buyer: Agent, seller: Agent, resource: str, amount: int, price: int
    ) -> bool:
        price = coerce_stat_int(price, default=0)
        if price <= 0 or buyer.stats.wealth < price:
            return False
        buyer.stats.wealth = coerce_stat_int(buyer.stats.wealth - price)
        seller.stats.wealth = coerce_stat_int(seller.stats.wealth + price)
        buyer.stats.reputation = coerce_stat_int(buyer.stats.reputation + 1)
        seller.stats.reputation = coerce_stat_int(seller.stats.reputation + 2)
        return True

    def apply_steal(self, thief: Agent, victim: Agent, amount: int) -> int:
        amount = coerce_stat_int(amount, default=0)
        stolen = min(amount, victim.stats.wealth)
        victim.stats.wealth = coerce_stat_int(victim.stats.wealth - stolen)
        thief.stats.wealth = coerce_stat_int(thief.stats.wealth + stolen)
        thief.stats.reputation = coerce_stat_int(thief.stats.reputation - 5)
        return stolen

    def apply_gift(self, giver: Agent, receiver: Agent, amount: int) -> int:
        amount = coerce_stat_int(amount, default=0)
        given = min(amount, giver.stats.wealth)
        giver.stats.wealth = coerce_stat_int(giver.stats.wealth - given)
        receiver.stats.wealth = coerce_stat_int(receiver.stats.wealth + given)
        giver.stats.reputation = coerce_stat_int(giver.stats.reputation + 2)
        return given
