from __future__ import annotations

import random

from agents.memory import AgentMemory
from agents.relationships import RelationshipManager
from db.repository import Repository
from models.schemas import Action, Agent, WorldState
from simulation_core.economy import Economy


class ActionResolver:
    def __init__(
        self,
        repo: Repository,
        economy: Economy,
        relationships: RelationshipManager,
        memory: AgentMemory,
    ):
        self.repo = repo
        self.economy = economy
        self.relationships = relationships
        self.memory = memory

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

        self.repo.save_action(tick, agent_id, action)
        description = f"{agent.name} performed {action.type}"

        if action.type == "trade" and action.target:
            target = agents.get(action.target)
            if target:
                price = action.payload.get("price", 3)
                resource = action.payload.get("resource", "food")
                if self.economy.apply_trade(agent, target, resource, 1, price):
                    if resource == "food" and state.resources.food >= 1:
                        state.resources.food -= 1
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

        elif action.type == "campaign":
            agent.stats.reputation += 3
            agent.stats.influence += 2
            msg = action.payload.get("message", "Vote for me!")
            description = f"{agent.name} campaigned: {msg}"
            self.memory.store(agent_id, tick, f"I campaigned: {msg}", importance=0.7, emotion="hope")

        elif action.type == "vote" and action.target:
            target = agents.get(action.target)
            if target:
                description = f"{agent.name} voted for {target.name}"
                self.memory.store(
                    agent_id, tick,
                    f"I voted for {target.name} as chief",
                    importance=0.8, emotion="hope",
                )

        elif action.type == "gift" and action.target:
            target = agents.get(action.target)
            if target:
                amount = action.payload.get("amount", 1)
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
                amount = action.payload.get("amount", 2)
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

        elif action.type == "build":
            structure = action.payload.get("structure", "shed")
            if state.resources.wood >= 2:
                state.resources.wood -= 2
                agent.stats.reputation += 2
                description = f"{agent.name} built a {structure}"
                self.memory.store(
                    agent_id, tick,
                    f"I built a {structure}",
                    importance=0.5, emotion="joy",
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
        self.repo.save_agent(agent)
        if action.target and action.target in agents:
            self.repo.save_agent(agents[action.target])
        return description
