from __future__ import annotations

import json
import random
from typing import Any, Optional

from models.schemas import VALID_ACTIONS, Action, Agent, WorldState


class HeuristicAgent:
    """Fallback decision maker when LLM is unavailable."""

    def decide(self, agent: Agent, world: WorldState, context: dict[str, Any]) -> Action:
        relationships = context.get("relationships", [])
        candidates = context.get("election_candidates", [])
        other_agents = context.get("other_agents", [])

        if world.election_state.active and candidates:
            if agent.id in candidates:
                return Action(type="campaign", payload={"message": f"{agent.name} for chief!"})
            if candidates:
                best = self._pick_vote_target(agent, candidates, relationships)
                return Action(type="vote", target=best)

        roll = random.random()
        if roll < 0.2 and other_agents:
            target = random.choice(other_agents)["id"]
            return Action(
                type="trade",
                target=target,
                payload={"resource": "food", "amount": 1, "price": 3},
            )
        if roll < 0.35 and other_agents:
            target = random.choice(other_agents)["id"]
            return Action(type="talk", target=target, payload={"topic": "village affairs"})
        if roll < 0.45 and agent.personality.greed > 0.6 and other_agents:
            target = random.choice(other_agents)["id"]
            return Action(type="steal", target=target, payload={"amount": 2})
        if roll < 0.55 and agent.personality.sociability > 0.5 and other_agents:
            target = random.choice(other_agents)["id"]
            return Action(type="gift", target=target, payload={"amount": 1})
        if roll < 0.65:
            return Action(type="build", payload={"structure": "shed"})
        if roll < 0.75 and other_agents:
            target = random.choice(other_agents)["id"]
            return Action(type="persuade", target=target, payload={"topic": "support me"})
        if other_agents:
            target = random.choice(other_agents)["id"]
            return Action(type="talk", target=target, payload={"topic": "greetings"})
        return Action(type="build", payload={"structure": "fence"})

    def _pick_vote_target(
        self, agent: Agent, candidates: list[str], relationships: list[dict]
    ) -> str:
        best_id = candidates[0]
        best_score = -1.0
        rel_map = {}
        for r in relationships:
            other = r["b_id"] if r["a_id"] == agent.id else r["a_id"]
            rel_map[other] = r
        for cid in candidates:
            rel = rel_map.get(cid, {})
            score = rel.get("trust", 0.3) * 0.5 + rel.get("respect", 0.3) * 0.3
            if cid == agent.id:
                score += 0.2
            if score > best_score:
                best_score = score
                best_id = cid
        return best_id


class AgentRunner:
    def __init__(self, heuristic: Optional[HeuristicAgent] = None):
        self.heuristic = heuristic or HeuristicAgent()

    def validate_action(self, action: Action) -> Action:
        if action.type not in VALID_ACTIONS:
            return Action(type="talk", payload={"topic": "idle"})
        return action

    def parse_llm_action(self, response: str) -> Action:
        try:
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(response[start:end])
                return Action(
                    type=data.get("type", "talk"),
                    target=data.get("target"),
                    payload=data.get("payload", {}),
                )
        except (json.JSONDecodeError, KeyError):
            pass
        return Action(type="talk", payload={"topic": "uncertain"})
