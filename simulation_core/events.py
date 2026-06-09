from __future__ import annotations

import random
from typing import Any

from config import AppConfig
from db.repository import Repository
from models.schemas import Agent, WorldState


WORLD_EVENT_TYPES = [
    ("harvest_bounty", "A bountiful harvest increases village morale.", {"food_bonus": 10}),
    ("storm", "A fierce storm damages stored resources.", {"wood_loss": 5}),
    ("traveler", "A traveler brings news from distant lands.", {"reputation_shift": 1}),
    ("disease", "Illness spreads through the village.", {"food_loss": 5}),
    ("discovery", "Villagers discover a rich stone deposit nearby.", {"stone_bonus": 10}),
    ("festival", "The village holds a festival, boosting spirits.", {"morale_boost": True}),
    ("bandits", "Bandits threaten the village outskirts.", {"fear_increase": True, "wood_loss": 3}),
    ("trade_caravan", "A trade caravan arrives with goods.", {"gold_bonus": 15}),
]

THREAT_EVENT_WEIGHTS: dict[str, dict[str, int]] = {
    "stable": {
        "harvest_bounty": 3,
        "festival": 3,
        "trade_caravan": 2,
        "discovery": 2,
        "traveler": 2,
        "storm": 1,
        "disease": 1,
        "bandits": 1,
    },
    "strained": {
        "storm": 2,
        "disease": 2,
        "bandits": 2,
        "traveler": 2,
        "trade_caravan": 2,
        "harvest_bounty": 1,
        "festival": 1,
        "discovery": 1,
    },
    "critical": {
        "disease": 3,
        "storm": 3,
        "bandits": 3,
        "food_loss": 2,
        "traveler": 1,
        "trade_caravan": 1,
    },
    "crisis": {
        "disease": 4,
        "storm": 4,
        "bandits": 3,
        "food_loss": 3,
        "traveler": 1,
    },
}


class EventGenerator:
    def __init__(self, config: AppConfig, repo: Repository):
        self.config = config
        self.repo = repo
        self._events_by_type = {e[0]: e for e in WORLD_EVENT_TYPES}

    def generate(
        self, state: WorldState, agents: dict[str, Agent]
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        threat = state.threat.level
        base_chance = {"stable": 0.2, "strained": 0.25, "critical": 0.3, "crisis": 0.35}
        if random.random() >= base_chance.get(threat, 0.25):
            return events

        event_type = self._pick_event_type(threat)
        entry = self._events_by_type.get(event_type)
        if not entry:
            return events

        _, description, effects = entry
        self._apply_effects(state, effects, agents)
        event = {
            "tick": state.tick,
            "event_type": event_type,
            "description": description,
            "effects": effects,
        }
        self.repo.save_world_event(state.tick, event_type, description, effects)
        events.append(event)
        return events

    def _pick_event_type(self, threat: str) -> str:
        weights = THREAT_EVENT_WEIGHTS.get(threat, THREAT_EVENT_WEIGHTS["stable"])
        types = list(weights.keys())
        if "food_loss" in types:
            return random.choices(
                ["disease", "storm", "bandits"],
                weights=[weights.get("disease", 1), weights.get("storm", 1), weights.get("bandits", 1)],
                k=1,
            )[0]
        type_weights = [weights[t] for t in types]
        return random.choices(types, weights=type_weights, k=1)[0]

    def _mitigation_factor(self, agents: dict[str, Agent]) -> float:
        guards = sum(1 for a in agents.values() if a.role == "guard")
        if guards == 0:
            return 1.0
        factor = self.config.economy.guard_mitigation_factor
        reduction = min(0.8, guards * factor * 0.1)
        return max(0.2, 1.0 - reduction)

    def _apply_effects(
        self,
        state: WorldState,
        effects: dict[str, Any],
        agents: dict[str, Agent],
    ) -> None:
        mitigation = self._mitigation_factor(agents)
        if "food_bonus" in effects:
            state.resources.food += effects["food_bonus"]
        if "food_loss" in effects:
            loss = int(effects["food_loss"] * mitigation)
            state.resources.food = max(0, state.resources.food - loss)
        if "wood_loss" in effects:
            loss = int(effects["wood_loss"] * mitigation)
            state.resources.wood = max(0, state.resources.wood - loss)
        if "stone_bonus" in effects:
            state.resources.stone += effects["stone_bonus"]
        if "gold_bonus" in effects:
            state.resources.gold += effects["gold_bonus"]
        if "reputation_shift" in effects:
            shift = effects["reputation_shift"]
            for agent in random.sample(list(agents.values()), k=min(3, len(agents))):
                agent.stats.reputation = max(0, agent.stats.reputation + shift)
        if effects.get("morale_boost"):
            for agent in agents.values():
                agent.stats.reputation = max(0, agent.stats.reputation + 1)
        if effects.get("fear_increase"):
            for agent in random.sample(list(agents.values()), k=min(5, len(agents))):
                agent.stats.reputation = max(0, agent.stats.reputation - 1)
