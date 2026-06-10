from __future__ import annotations

import random
from dataclasses import dataclass, field

from config import AppConfig
from models.schemas import Agent, WorldState, coerce_stat_int


SABOTAGE_RESOURCES: frozenset[str] = frozenset({"food", "wood"})


@dataclass
class TradeResult:
    success: bool
    resource: str = ""
    amount: int = 0
    price: int = 0
    reason: str = ""


@dataclass
class QuarryResult:
    success: bool
    amount: int = 0
    stone_yield: int = 0
    wood_cost: int = 0
    reason: str = ""


@dataclass
class ResourceBalance:
    food_production: int = 0
    food_demand: int = 0
    food_net: int = 0
    wood_production: int = 0
    wood_consumption: int = 0
    wood_net: int = 0
    stone_production: int = 0
    stone_consumption: int = 0
    stone_net: int = 0
    food_stock: int = 0
    wood_stock: int = 0
    stone_stock: int = 0
    gold_stock: int = 0
    food_tier: str = "stable"
    wood_tier: str = "stable"
    stone_tier: str = "stable"
    gold_tier: str = "stable"


@dataclass
class FoodTradeTracker:
    """Per-tick counters for food sales; reset at the start of each tick."""

    total_sold: int = 0
    by_farmer: dict[str, int] = field(default_factory=dict)


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

    @staticmethod
    def _tier_from_amount(
        amount: int, stable: int, strained: int, critical: int
    ) -> str:
        if amount >= stable:
            return "stable"
        if amount >= strained:
            return "strained"
        if amount >= critical:
            return "critical"
        return "crisis"

    @staticmethod
    def _tier_from_food_days(days: float, cfg) -> str:
        if days >= cfg.threat_food_stable_days:
            return "stable"
        if days >= cfg.threat_food_strained_days:
            return "strained"
        if days >= cfg.threat_food_critical_days:
            return "critical"
        return "crisis"

    def resource_balance_summary(
        self, agents: dict[str, Agent], state: WorldState
    ) -> ResourceBalance:
        cfg = self.config.economy
        food_demand = self._food_demand(agents)
        food_production = self._expected_food_production(agents, state)
        builder_count = sum(1 for a in agents.values() if a.role == "builder")
        woodcutter_count = sum(
            1 for a in agents.values() if a.role == "woodcutter"
        )
        wood_production = woodcutter_count * cfg.woodcutter_production
        wood_consumption = builder_count * 2
        stone_production = builder_count * cfg.builder_stone_production
        stone_consumption = builder_count

        demand = max(food_demand, 1)
        food_days = state.resources.food / demand

        return ResourceBalance(
            food_production=food_production,
            food_demand=food_demand,
            food_net=food_production - food_demand,
            wood_production=wood_production,
            wood_consumption=wood_consumption,
            wood_net=wood_production - wood_consumption,
            stone_production=stone_production,
            stone_consumption=stone_consumption,
            stone_net=stone_production - stone_consumption,
            food_stock=state.resources.food,
            wood_stock=state.resources.wood,
            stone_stock=state.resources.stone,
            gold_stock=state.resources.gold,
            food_tier=self._tier_from_food_days(food_days, cfg),
            wood_tier=self._tier_from_amount(
                state.resources.wood,
                cfg.threat_wood_stable,
                cfg.threat_wood_strained,
                cfg.threat_wood_critical,
            ),
            stone_tier=self._tier_from_amount(
                state.resources.stone,
                cfg.threat_stone_stable,
                cfg.threat_stone_strained,
                cfg.threat_stone_critical,
            ),
            gold_tier=self._tier_from_amount(
                state.resources.gold,
                cfg.threat_gold_stable,
                cfg.threat_gold_strained,
                cfg.threat_gold_critical,
            ),
        )

    def format_balance_line(self, balance: ResourceBalance) -> str:
        demand = max(balance.food_demand, 1)
        food_days = balance.food_stock / demand
        parts = [
            (
                f"Food: {balance.food_net:+d} net/tick "
                f"({food_days:.1f}d supply, {balance.food_tier})"
            ),
            (
                f"Wood: {balance.wood_net:+d} net/tick "
                f"({balance.wood_stock} units, {balance.wood_tier})"
            ),
            (
                f"Stone: {balance.stone_net:+d} net/tick "
                f"({balance.stone_stock} units, {balance.stone_tier}; "
                "quarry action adds stone)"
            ),
            (
                f"Gold: ({balance.gold_stock} units, {balance.gold_tier}; "
                "trader conversions cost 5 each)"
            ),
        ]
        return ". ".join(parts) + "."

    def _trader_conversions_allowed(self, state: WorldState) -> bool:
        cfg = self.config.economy
        return (
            state.resources.gold >= cfg.trader_gold_cost
            and state.resources.gold >= cfg.threat_gold_critical
        )

    def _expected_food_production(
        self, agents: dict[str, Agent], state: WorldState
    ) -> int:
        cfg = self.config.economy
        produced = sum(
            cfg.farmer_production for agent in agents.values() if agent.role == "farmer"
        )
        if (
            state.resources.food < self._food_demand(agents)
            and self._trader_conversions_allowed(state)
        ):
            produced += cfg.trader_conversion_rate
        return produced

    def _remaining_food_trade_quota(
        self,
        agents: dict[str, Agent],
        state: WorldState,
        tracker: FoodTradeTracker | None,
    ) -> int:
        surplus = self._expected_food_production(agents, state) - self._food_demand(agents)
        already = tracker.total_sold if tracker else 0
        return max(0, surplus - already)

    def _remaining_farmer_food_sale(
        self, seller: Agent, tracker: FoodTradeTracker | None
    ) -> int | None:
        if seller.role != "farmer":
            return None
        cfg = self.config.economy
        max_sale = cfg.farmer_max_food_sale_per_tick
        if max_sale <= 0:
            return 0
        already = tracker.by_farmer.get(seller.id, 0) if tracker else 0
        return max(0, max_sale - already)

    def _record_food_trade(
        self, seller: Agent, amount: int, tracker: FoodTradeTracker | None
    ) -> None:
        if tracker is None:
            return
        tracker.total_sold += amount
        if seller.role == "farmer":
            tracker.by_farmer[seller.id] = tracker.by_farmer.get(seller.id, 0) + amount

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
                if state.threat.level != "crisis" and state.resources.wood >= 2:
                    state.resources.wood -= 2
                    if state.resources.stone >= 1:
                        state.resources.stone -= 1
                    state.resources.stone += cfg.builder_stone_production
                    agent.stats.wealth += 3
                    agent.stats.reputation += 1
            elif agent.role == "trader":
                if not self._trader_conversions_allowed(state):
                    continue
                if state.resources.food < self._food_demand(agents):
                    state.resources.gold -= cfg.trader_gold_cost
                    state.resources.food += cfg.trader_conversion_rate
                    agent.stats.wealth += 2
                    agent.stats.reputation += 1
                elif state.resources.wood < cfg.threat_wood_strained:
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
            if agent.stats.supply_credit > 0:
                # Provisions secured via trade shield the agent from the shortage.
                agent.stats.supply_credit = coerce_stat_int(
                    agent.stats.supply_credit - 1
                )
                continue
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

    def apply_commodity_trade(
        self,
        buyer: Agent,
        seller: Agent,
        state: WorldState,
        resource: str,
        amount: int,
        price: int,
        *,
        agents: dict[str, Agent] | None = None,
        food_trade_tracker: FoodTradeTracker | None = None,
    ) -> TradeResult:
        cfg = self.config.economy
        catalog = cfg.trade_catalog.get(resource)
        if catalog is None:
            return TradeResult(False, reason=f"{resource!r} is not a tradable commodity")
        if seller.role not in catalog.seller_roles:
            return TradeResult(
                False,
                reason=f"{seller.name} ({seller.role}) cannot sell {resource}",
            )

        amount = coerce_stat_int(amount, default=catalog.default_amount)
        if amount <= 0:
            amount = catalog.default_amount

        available = coerce_stat_int(getattr(state.resources, resource, 0))
        if available <= 0:
            return TradeResult(False, reason=f"village has no {resource} in stock")

        if resource == "food" and agents is not None and not cfg.stewardship_mode:
            surplus_quota = self._remaining_food_trade_quota(
                agents, state, food_trade_tracker
            )
            if surplus_quota <= 0:
                return TradeResult(
                    False,
                    reason=(
                        "village food surplus is reserved for consumption — "
                        "production does not exceed demand"
                    ),
                )
            amount = min(amount, surplus_quota)
            farmer_quota = self._remaining_farmer_food_sale(seller, food_trade_tracker)
            if farmer_quota is not None:
                if farmer_quota <= 0:
                    return TradeResult(
                        False,
                        reason=(
                            f"{seller.name} has already sold their modest food surplus "
                            "for this tick"
                        ),
                    )
                amount = min(amount, farmer_quota)

        amount = min(amount, available)
        if amount <= 0:
            return TradeResult(False, reason=f"village has no {resource} in stock")

        price = coerce_stat_int(price, default=catalog.default_price)
        if price <= 0 or buyer.stats.wealth < price:
            return TradeResult(False, reason="buyer cannot afford the price")

        buyer.stats.wealth = coerce_stat_int(buyer.stats.wealth - price)
        seller.stats.wealth = coerce_stat_int(seller.stats.wealth + price)
        setattr(state.resources, resource, available - amount)
        if resource == "food":
            self._record_food_trade(seller, amount, food_trade_tracker)
        buyer.stats.supply_credit = coerce_stat_int(
            buyer.stats.supply_credit + amount * cfg.trade_supply_credit_per_unit
        )
        buyer.stats.reputation = coerce_stat_int(
            buyer.stats.reputation + cfg.trade_buyer_rep
        )
        seller.stats.reputation = coerce_stat_int(
            seller.stats.reputation + cfg.trade_seller_rep
        )
        return TradeResult(True, resource=resource, amount=amount, price=price)

    def apply_quarry(
        self, actor: Agent, state: WorldState, amount: int
    ) -> QuarryResult:
        cfg = self.config.economy
        if actor.role != "builder":
            return QuarryResult(False, reason="only builders can quarry stone")

        amount = coerce_stat_int(amount, default=1)
        if amount <= 0:
            amount = 1
        if cfg.builder_quarry_max_per_action > 0:
            amount = min(amount, cfg.builder_quarry_max_per_action)

        wood_cost = cfg.builder_quarry_wood_cost
        if wood_cost > 0 and state.resources.wood < wood_cost:
            return QuarryResult(
                False,
                reason=f"not enough wood for quarry tools (need {wood_cost})",
            )

        stone_yield = amount * cfg.builder_quarry_stone_per_unit
        if wood_cost > 0:
            state.resources.wood -= wood_cost
        state.resources.stone += stone_yield
        return QuarryResult(
            True,
            amount=amount,
            stone_yield=stone_yield,
            wood_cost=wood_cost,
        )

    def resource_tier(self, resource: str, state: WorldState, agents: dict[str, Agent]) -> str:
        balance = self.resource_balance_summary(agents, state)
        return getattr(balance, f"{resource}_tier", "stable")

    def apply_sabotage(
        self, actor: Agent, state: WorldState, resource: str, amount: int
    ) -> int:
        cfg = self.config.economy
        cleaned = str(resource).strip().lower()
        if cleaned not in SABOTAGE_RESOURCES:
            return 0

        amount = coerce_stat_int(amount, default=1)
        if amount <= 0:
            amount = 1
        if cfg.sabotage_max_amount > 0:
            amount = min(amount, cfg.sabotage_max_amount)

        available = coerce_stat_int(getattr(state.resources, cleaned, 0))
        if available <= 0:
            return 0

        destroyed = min(amount, available)
        setattr(state.resources, cleaned, available - destroyed)
        actor.stats.reputation = max(
            0, actor.stats.reputation - cfg.sabotage_rep_penalty_base
        )
        return destroyed

    def apply_steal(self, thief: Agent, victim: Agent, amount: int) -> int:
        cfg = self.config.economy
        amount = coerce_stat_int(amount, default=0)
        if cfg.steal_gold_cap > 0:
            amount = min(amount, cfg.steal_gold_cap)
        stolen = min(amount, victim.stats.wealth)
        victim.stats.wealth = coerce_stat_int(victim.stats.wealth - stolen)
        thief.stats.wealth = coerce_stat_int(thief.stats.wealth + stolen)
        thief.stats.reputation = max(
            0, thief.stats.reputation - cfg.steal_rep_penalty_base
        )
        return stolen

    def apply_gift(
        self, giver: Agent, receiver: Agent, amount: int, *, rep_gain: int | None = None
    ) -> int:
        amount = coerce_stat_int(amount, default=0)
        given = min(amount, giver.stats.wealth)
        giver.stats.wealth = coerce_stat_int(giver.stats.wealth - given)
        receiver.stats.wealth = coerce_stat_int(receiver.stats.wealth + given)
        actual_rep = (
            self.config.economy.gift_rep_gain if rep_gain is None else rep_gain
        )
        if actual_rep > 0:
            giver.stats.reputation = coerce_stat_int(
                giver.stats.reputation + actual_rep
            )
        return given

    def gift_benefits(
        self,
        *,
        tick: int,
        giver_id: str,
        receiver_id: str,
        repo,
    ) -> tuple[int, float]:
        cfg = self.config.economy
        rep_gain = cfg.gift_rep_gain
        relationship_scale = 1.0

        reciprocal_since = tick - cfg.gift_reciprocal_window_ticks
        if repo.has_gift_between_since(
            giver_id=receiver_id,
            receiver_id=giver_id,
            since_tick=reciprocal_since,
        ):
            rep_gain = 0
            relationship_scale = cfg.gift_reciprocal_relationship_multiplier

        return rep_gain, relationship_scale
