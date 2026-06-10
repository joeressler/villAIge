from __future__ import annotations

from models.schemas import Action, Agent


def other_agents(agents: list[Agent], agent_id: str) -> list[Agent]:
    return [agent for agent in agents if agent.id != agent_id]


def default_talk_action(agent: Agent, agents: list[Agent]) -> Action:
    others = other_agents(agents, agent.id)
    target = others[0].id if others else None
    return Action(type="talk", target=target, payload={"topic": "greetings"})
