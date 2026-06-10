from __future__ import annotations

from config import AppConfig
from models.schemas import Agent, ThreatState, WorldState
from simulation_core.economy import Economy


class ThreatEngine:
    def __init__(self, config: AppConfig):
        self.config = config
        self.economy = Economy(config)

    def compute_threat(
        self,
        state: WorldState,
        agents: dict[str, Agent],
        food_demand: int,
    ) -> ThreatState:
        cfg = self.config.economy
        demand = max(food_demand, 1)
        food_days = state.resources.food / demand
        balance = self.economy.resource_balance_summary(agents, state)

        levels = [
            balance.food_tier,
            balance.wood_tier,
            balance.stone_tier,
            balance.gold_tier,
        ]
        severity = ("stable", "strained", "critical", "crisis")
        overall = max(levels, key=lambda level: severity.index(level))

        wood_days = (
            state.resources.wood / max(balance.wood_consumption, 1)
            if balance.wood_consumption > 0
            else float(state.resources.wood)
        )
        stone_days = (
            state.resources.stone / max(balance.stone_consumption, 1)
            if balance.stone_consumption > 0
            else float(state.resources.stone)
        )
        gold_days = (
            state.resources.gold / max(cfg.trader_gold_cost, 1)
            if cfg.trader_gold_cost > 0
            else float(state.resources.gold)
        )

        message = self._threat_message(overall, balance, food_days)
        return ThreatState(
            level=overall,
            food_days_remaining=food_days,
            wood_days_remaining=wood_days,
            stone_days_remaining=stone_days,
            gold_days_remaining=gold_days,
            message=message,
        )

    @staticmethod
    def _threat_message(overall: str, balance, food_days: float) -> str:
        if overall == "stable":
            return "Village resources are stable."
        if overall == "strained":
            return (
                f"Resources are strained — food lasts ~{food_days:.1f} days at current demand."
            )
        if overall == "critical":
            return (
                f"Critical shortage — food ~{food_days:.1f}d, wood {balance.wood_stock}, "
                f"stone {balance.stone_stock}, gold {balance.gold_stock}."
            )
        return (
            f"Crisis — immediate action needed. Food ~{food_days:.1f}d remaining; "
            "village survival is at risk."
        )

    def apply_threat_effects(self, state: WorldState, agents: dict[str, Agent]) -> None:
        if state.threat.level not in {"critical", "crisis"}:
            return
        for agent in agents.values():
            if agent.stats.supply_credit > 0:
                agent.stats.supply_credit = max(0, agent.stats.supply_credit - 1)
            elif agent.stats.reputation > 0:
                agent.stats.reputation = max(0, agent.stats.reputation - 1)
