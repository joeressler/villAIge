from __future__ import annotations

import logging
import random
from contextlib import contextmanager

from agents.memory import AgentMemory
from agents.relationships import InteractionOutcome, RelationshipManager
from db.repository import Repository
from models.schemas import Action, Agent, WorldState, coerce_stat_int, normalize_agent_stats
from simulation_core.economy import Economy, FoodTradeTracker
from simulation_core.elections import ElectionSystem

logger = logging.getLogger(__name__)

# Talk grants reputation only to agents this sociable (or with the alliance goal).
TALK_REP_SOCIABILITY_THRESHOLD = 0.6

# Extra reputation penalty when witnesses defend the victim of a hostile act.
_HOSTILE_CONDEMN_LABELS: dict[str, str] = {
    "steal": "condemn the theft",
    "sabotage": "condemn the sabotage",
}


@contextmanager
def _noop_context():
    yield


class ActionResolver:
    def __init__(
        self,
        repo: Repository,
        economy: Economy,
        relationships: RelationshipManager,
        memory: AgentMemory,
        elections: ElectionSystem,
        tracer=None,
    ):
        self.repo = repo
        self.economy = economy
        self.relationships = relationships
        self.memory = memory
        self.elections = elections
        self.tracer = tracer
        self._food_trade_tracker = FoodTradeTracker()

    def begin_tick(self) -> None:
        self._food_trade_tracker = FoodTradeTracker()

    def resolve(
        self,
        tick: int,
        agent_id: str,
        action: Action,
        agents: dict[str, Agent],
        state: WorldState,
    ) -> str:
        agent = agents.get(agent_id)
        if not agent:
            return "Agent not found"

        trace_ctx = (
            self.tracer.trace_action_resolution(
                agent_name=agent.name,
                action_type=action.type,
                action_category=action.category,
                tick=tick,
            )
            if self.tracer
            else _noop_context()
        )
        with trace_ctx:
            return self._resolve_action(tick, agent_id, action, agent, agents, state)

    def _resolve_action(
        self,
        tick: int,
        agent_id: str,
        action: Action,
        agent: Agent,
        agents: dict[str, Agent],
        state: WorldState,
    ) -> str:
        self.repo.save_action(tick, agent_id, action)
        description = f"{agent.name} performed {action.type}"
        outcome = InteractionOutcome()

        if action.type == "trade" and action.target:
            target = agents.get(action.target)
            if target:
                price = coerce_stat_int(action.payload.get("price"), default=3)
                resource = action.payload.get("resource", "food")
                amount = coerce_stat_int(action.payload.get("amount"), default=0)
                result = self.economy.apply_commodity_trade(
                    agent,
                    target,
                    state,
                    resource,
                    amount,
                    price,
                    agents=agents,
                    food_trade_tracker=self._food_trade_tracker,
                )
                if result.success:
                    outcome.positive_success = True
                    description = (
                        f"{agent.name} bought {result.amount} {result.resource} "
                        f"from {target.name} for {result.price} gold"
                    )
                    self.memory.store(
                        agent_id, tick,
                        f"I bought {result.amount} {result.resource} from "
                        f"{target.name} for {result.price} gold",
                        importance=0.6, emotion="neutral",
                    )
                    stock = coerce_stat_int(
                        getattr(state.resources, result.resource, 0)
                    )
                    tier = self.economy.resource_tier(
                        result.resource, state, agents
                    )
                    if tier in ("critical", "crisis"):
                        self.memory.store(
                            agent_id,
                            tick,
                            f"I bought {result.amount} {result.resource}; "
                            f"village stock is now {stock} ({tier})",
                            importance=0.75,
                            emotion="fear",
                        )
                else:
                    outcome.apply_actor_deltas = False
                    description = (
                        f"{agent.name}'s trade with {target.name} failed ({result.reason})"
                    )

        elif action.type == "talk" and action.target:
            target = agents.get(action.target)
            if target:
                topic = action.payload.get("topic", "greetings")
                outcome.positive_success = True
                # Talk only builds standing for naturally social agents or alliance-builders;
                # otherwise it strengthens the relationship without free reputation.
                if (
                    agent.personality.sociability >= TALK_REP_SOCIABILITY_THRESHOLD
                    or agent.goals.primary == "build_alliances"
                ):
                    agent.stats.reputation += 1
                description = f"{agent.name} talked with {target.name} about {topic}"
                self.memory.store(
                    agent_id, tick,
                    f"I talked with {target.name} about {topic}",
                    importance=0.4, emotion="neutral",
                )

        elif action.type == "campaign" and action.target:
            target = agents.get(action.target)
            if target:
                rep_gain = self.elections.campaign_rep_gain(state, agent_id)
                if rep_gain:
                    agent.stats.reputation += rep_gain
                agent.stats.influence += 1
                self.elections.record_campaign(state, agent_id)
                outcome.positive_success = True
                msg = action.payload.get("message", "Vote for me!")
                description = f"{agent.name} campaigned to {target.name}: {msg}"
                self.memory.store(
                    agent_id,
                    tick,
                    f"I campaigned to {target.name}: {msg}",
                    importance=0.7,
                    emotion="hope",
                )

        elif action.type == "vote" and action.target:
            target = agents.get(action.target)
            if target:
                recorded = self.elections.record_vote(state, agent_id, action.target)
                if recorded:
                    agent.stats.reputation += 1
                    target.stats.reputation += 1
                    outcome.positive_success = True
                    description = f"{agent.name} voted for {target.name}"
                else:
                    description = f"{agent.name} already voted or vote invalid"
                self.memory.store(
                    agent_id, tick,
                    f"I voted for {target.name} as chief",
                    importance=0.8, emotion="hope",
                )

        elif action.type == "gift" and action.target:
            target = agents.get(action.target)
            if target:
                amount = coerce_stat_int(action.payload.get("amount"), default=1)
                rep_gain, outcome.delta_scale = self.economy.gift_benefits(
                    tick=tick,
                    giver_id=agent_id,
                    receiver_id=action.target,
                    repo=self.repo,
                )
                # During scarcity, giving gold away earns no standing — trade/build do.
                if state.threat.level in ("strained", "critical", "crisis"):
                    rep_gain = 0
                given = self.economy.apply_gift(
                    agent, target, amount, rep_gain=rep_gain
                )
                if given > 0:
                    outcome.positive_success = True
                    suffix = "" if rep_gain > 0 else " (no standing gain)"
                    description = (
                        f"{agent.name} gifted {given} gold to {target.name}{suffix}"
                    )
                    self.memory.store(
                        agent_id, tick,
                        f"I gifted {given} gold to {target.name}",
                        importance=0.5, emotion="joy",
                    )
                    if outcome.delta_scale < 1.0:
                        self.relationships.update_from_action(
                            agent_id, action, delta_scale=outcome.delta_scale
                        )
                        outcome.apply_actor_deltas = False
                else:
                    outcome.apply_actor_deltas = False
                    description = (
                        f"{agent.name}'s gift to {target.name} failed (no gold to give)"
                    )

        elif action.type == "steal" and action.target:
            target = agents.get(action.target)
            if target:
                amount = coerce_stat_int(action.payload.get("amount"), default=2)
                stolen = self.economy.apply_steal(agent, target, amount)
                if stolen > 0:
                    outcome.hostile_success = True
                    description = f"{agent.name} stole {stolen} gold from {target.name}"
                    self.memory.store(
                        agent_id, tick,
                        f"I stole {stolen} gold from {target.name}",
                        importance=0.9, emotion="fear",
                    )
                    self.memory.store(
                        action.target, tick,
                        f"{agent.name} stole from me!",
                        importance=0.9, emotion="anger",
                    )
                else:
                    outcome.apply_actor_deltas = False
                    description = (
                        f"{agent.name}'s steal from {target.name} failed (nothing to take)"
                    )

        elif action.type == "sabotage" and action.target:
            target = agents.get(action.target)
            if target:
                resource = action.payload.get("resource", "wood")
                amount = coerce_stat_int(action.payload.get("amount"), default=1)
                destroyed = self.economy.apply_sabotage(agent, state, resource, amount)
                if destroyed > 0:
                    outcome.hostile_success = True
                    outcome.hostile_approval_enabled = state.threat.level in (
                        "strained",
                        "critical",
                        "crisis",
                    )
                    description = (
                        f"{agent.name} sabotaged {destroyed} {resource} "
                        f"to undermine {target.name}"
                    )
                    self.memory.store(
                        agent_id, tick,
                        f"I sabotaged {destroyed} {resource} to undermine {target.name}",
                        importance=0.9, emotion="fear",
                    )
                    self.memory.store(
                        action.target, tick,
                        f"{agent.name} sabotaged village {resource} to undermine me!",
                        importance=0.9, emotion="anger",
                    )
                else:
                    outcome.apply_actor_deltas = False
                    description = (
                        f"{agent.name}'s sabotage against {target.name} failed "
                        f"(no {resource} to destroy)"
                    )

        elif action.type == "build" and action.target:
            target = agents.get(action.target)
            if target:
                structure = action.payload.get("structure", "shed")
                if state.resources.wood >= 2:
                    state.resources.wood -= 2
                    agent.stats.reputation += 2
                    target.stats.reputation += 1
                    outcome.positive_success = True
                    description = f"{agent.name} built a {structure} with {target.name}"
                    self.memory.store(
                        agent_id, tick,
                        f"I built a {structure} with {target.name}",
                        importance=0.5, emotion="joy",
                    )
                    self.memory.store(
                        action.target, tick,
                        f"{agent.name} and I built a {structure} together",
                        importance=0.4, emotion="joy",
                    )

        elif action.type == "quarry" and action.target:
            target = agents.get(action.target)
            if target:
                amount = coerce_stat_int(action.payload.get("amount"), default=1)
                result = self.economy.apply_quarry(agent, state, amount)
                if result.success:
                    agent.stats.reputation += 2
                    target.stats.reputation += 1
                    outcome.positive_success = True
                    description = (
                        f"{agent.name} quarried {result.stone_yield} stone "
                        f"with {target.name}"
                    )
                    self.memory.store(
                        agent_id,
                        tick,
                        f"I quarried {result.stone_yield} stone with {target.name}; "
                        f"village stone is now {state.resources.stone}",
                        importance=0.6,
                        emotion="joy",
                    )
                    self.memory.store(
                        action.target,
                        tick,
                        f"{agent.name} and I quarried {result.stone_yield} stone together",
                        importance=0.5,
                        emotion="joy",
                    )
                else:
                    outcome.apply_actor_deltas = False
                    description = (
                        f"{agent.name}'s quarry with {target.name} failed "
                        f"({result.reason})"
                    )

        elif action.type == "persuade" and action.target:
            target = agents.get(action.target)
            if target:
                outcome.positive_success = True
                if random.random() < agent.stats.influence / 100:
                    target.stats.reputation += 1
                description = f"{agent.name} persuaded {target.name}"
                self.memory.store(
                    agent_id, tick,
                    f"I persuaded {target.name}",
                    importance=0.5, emotion="neutral",
                )

        self.relationships.finalize_action_relationships(
            agent_id, action, agents, outcome
        )
        if outcome.hostile_success and outcome.witnesses_defending > 0:
            cfg = self.economy.config.economy
            penalty_by_type = {
                "steal": (
                    cfg.steal_rep_penalty_base,
                    cfg.steal_rep_penalty_if_liked_target,
                ),
                "sabotage": (
                    cfg.sabotage_rep_penalty_base,
                    cfg.sabotage_rep_penalty_if_liked_target,
                ),
            }
            if action.type in penalty_by_type:
                base_penalty, liked_penalty = penalty_by_type[action.type]
                extra_penalty = max(0, liked_penalty - base_penalty)
                if extra_penalty:
                    agent.stats.reputation = max(
                        0, agent.stats.reputation - extra_penalty
                    )
                    condemn_label = _HOSTILE_CONDEMN_LABELS.get(
                        action.type, "condemn the act"
                    )
                    description += (
                        f" — {outcome.witnesses_defending} villager(s) {condemn_label}"
                    )
        normalize_agent_stats(agent)
        self.repo.save_agent(agent)
        if action.target and action.target in agents:
            normalize_agent_stats(agents[action.target])
            self.repo.save_agent(agents[action.target])

        logger.info(
            "action resolved tick=%s agent=%s type=%s category=%s target=%s | %s",
            tick,
            agent.name,
            action.type,
            action.category,
            action.target or "-",
            description,
        )
        return description
