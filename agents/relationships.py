from __future__ import annotations

from db.repository import Repository
from models.schemas import Action, Relationship


class RelationshipManager:
    DELTAS = {
        "trade": {"trust": 0.05, "respect": 0.03, "friendship": 0.02},
        "talk": {"trust": 0.03, "friendship": 0.05},
        "gift": {"trust": 0.08, "friendship": 0.1, "respect": 0.05},
        "steal": {"trust": -0.2, "fear": 0.15, "friendship": -0.15},
        "persuade": {"trust": 0.02, "respect": 0.04},
        "campaign": {"respect": 0.05},
        "build": {"respect": 0.03, "trust": 0.02},
    }

    def __init__(self, repo: Repository):
        self.repo = repo

    def get_trust(self, a_id: str, b_id: str) -> float:
        rel = self.repo.get_relationship(a_id, b_id)
        return rel.trust if rel else 0.3

    def get_relationship(self, a_id: str, b_id: str) -> Relationship:
        rel = self.repo.get_relationship(a_id, b_id)
        if rel:
            return rel
        return Relationship(a_id=a_id, b_id=b_id)

    def update_from_action(self, agent_id: str, action: Action) -> None:
        if not action.target or action.target == agent_id:
            return
        rel = self.get_relationship(agent_id, action.target)
        deltas = self.DELTAS.get(action.type, {})
        for key, delta in deltas.items():
            current = getattr(rel, key)
            setattr(rel, key, max(0.0, min(1.0, current + delta)))
        self.repo.save_relationship(rel)

    def decay_all(self, factor: float = 0.99) -> None:
        for rel in self.repo.get_all_relationships():
            rel.trust *= factor
            rel.friendship *= factor
            self.repo.save_relationship(rel)
