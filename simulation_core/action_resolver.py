from __future__ import annotations

import logging
import random
from contextlib import contextmanager

from agents.memory import AgentMemory
from agents.relationships import RelationshipManager
from db.repository import Repository
from models.schemas import Action, Agent, WorldState, coerce_stat_int, normalize_agent_stats
from simulation_core.economy import Economy
from simulation_core.elections import ElectionSystem

logger = logging.getLogger(__name__)


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

        if action.type == "trade" and action.target:
            target = agents.get(action.target)
            if target:
                price = coerce_stat_int(action.payload.get("price"), default=3)
                resource = action.payload.get("resource", "food")
                if self.economy.apply_trade(agent, target, resource, 1, price):
                    description = f"{agent.name} traded with {target.name} for {price} gold"
                    self.memory.store(
                        agent_id, tick,
                        f"I traded with {target.name} for {price} gold",
                        importance=0.6, emotion="neutral",
                    )

        elif action.type == "talk" and action.target:
            target = agents.get(action.target)
            if target:
                topic = action.payload.get("topic", "greetings")
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
                given = self.economy.apply_gift(agent, target, amount)
                description = f"{agent.name} gifted {given} gold to {target.name}"
                self.memory.store(
                    agent_id, tick,
                    f"I gifted {given} gold to {target.name}",
                    importance=0.6, emotion="joy",
                )

        elif action.type == "steal" and action.target:
            target = agents.get(action.target)
            if target:
                amount = coerce_stat_int(action.payload.get("amount"), default=2)
                stolen = self.economy.apply_steal(agent, target, amount)
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

        elif action.type == "build" and action.target:
            target = agents.get(action.target)
            if target:
                structure = action.payload.get("structure", "shed")
                if state.resources.wood >= 2:
                    state.resources.wood -= 2
                    agent.stats.reputation += 2
                    target.stats.reputation += 1
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

        elif action.type == "persuade" and action.target:
            target = agents.get(action.target)
            if target:
                if random.random() < agent.stats.influence / 100:
                    target.stats.reputation += 1
                description = f"{agent.name} persuaded {target.name}"
                self.memory.store(
                    agent_id, tick,
                    f"I persuaded {target.name}",
                    importance=0.5, emotion="neutral",
                )

        self.relationships.update_from_action(agent_id, action)
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
