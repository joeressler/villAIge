from __future__ import annotations

import random
from typing import Any

from db.repository import Repository
from models.schemas import WorldState


WORLD_EVENT_TYPES = [
    ("harvest_bounty", "A bountiful harvest increases village morale.", {"food_bonus": 10}),
    ("storm", "A fierce storm damages stored resources.", {"wood_loss": 5}),
    ("traveler", "A traveler brings news from distant lands.", {"reputation_shift": 1}),
    ("disease", "Illness spreads through the village.", {"food_loss": 5}),
    ("discovery", "Villagers discover a rich stone deposit nearby.", {"stone_bonus": 10}),
    ("festival", "The village holds a festival, boosting spirits.", {"morale_boost": True}),
    ("bandits", "Bandits threaten the village outskirts.", {"fear_increase": True}),
    ("trade_caravan", "A trade caravan arrives with goods.", {"gold_bonus": 15}),
]


class EventGenerator:
    def __init__(self, repo: Repository):
        self.repo = repo

    def generate(self, state: WorldState) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        if random.random() < 0.25:
            event_type, description, effects = random.choice(WORLD_EVENT_TYPES)
            self._apply_effects(state, effects)
            event = {
                "tick": state.tick,
                "event_type": event_type,
                "description": description,
                "effects": effects,
            }
            self.repo.save_world_event(state.tick, event_type, description, effects)
            events.append(event)
        return events

    def _apply_effects(self, state: WorldState, effects: dict[str, Any]) -> None:
        if "food_bonus" in effects:
            state.resources.food += effects["food_bonus"]
        if "food_loss" in effects:
            state.resources.food = max(0, state.resources.food - effects["food_loss"])
        if "wood_loss" in effects:
            state.resources.wood = max(0, state.resources.wood - effects["wood_loss"])
        if "stone_bonus" in effects:
            state.resources.stone += effects["stone_bonus"]
        if "gold_bonus" in effects:
            state.resources.gold += effects["gold_bonus"]
