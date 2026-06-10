from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, TypedDict

from db.repository import Repository
from models.schemas import Action, Agent, Relationship


class RelationshipDelta(TypedDict, total=False):
    trust: float
    respect: float
    fear: float
    friendship: float


@dataclass(frozen=True)
class SentimentRule:
    """A normalized intensity for how far a relationship field crosses a threshold."""

    field: str
    threshold: float
    high: bool  # True: intensity grows as value exceeds threshold; False: as it falls below

    def intensity(self, relationship: Relationship) -> float | None:
        value = getattr(relationship, self.field)
        if self.high:
            if value < self.threshold:
                return None
            span = 1.0 - self.threshold
            return (value - self.threshold) / span if span > 0 else 1.0
        if value > self.threshold:
            return None
        return (self.threshold - value) / self.threshold if self.threshold > 0 else 1.0


@dataclass(frozen=True)
class ActionRelationshipEffects:
    actor: RelationshipDelta = field(default_factory=dict)
    witness_penalty: RelationshipDelta | None = None
    witness_approval: RelationshipDelta | None = None


# Witnesses who fear or distrust the other party.
DISLIKE_RULES: tuple[SentimentRule, ...] = (
    SentimentRule("fear", 0.35, high=True),
    SentimentRule("trust", 0.25, high=False),
    SentimentRule("friendship", 0.25, high=False),
)

# Witnesses who trust or are close to the other party.
LIKE_RULES: tuple[SentimentRule, ...] = (
    SentimentRule("trust", 0.6, high=True),
    SentimentRule("friendship", 0.6, high=True),
)

ACTION_RELATIONSHIP_EFFECTS: dict[str, ActionRelationshipEffects] = {
    "trade": ActionRelationshipEffects(
        actor={"trust": 0.05, "respect": 0.03, "friendship": 0.02},
        witness_penalty={"trust": -0.02, "friendship": -0.02, "respect": -0.01},
    ),
    "talk": ActionRelationshipEffects(
        actor={"trust": 0.03, "friendship": 0.05},
        witness_penalty={"trust": -0.02, "friendship": -0.03},
    ),
    "gift": ActionRelationshipEffects(
        actor={"trust": 0.04, "friendship": 0.05, "respect": 0.03},
        witness_penalty={"trust": -0.03, "friendship": -0.04, "respect": -0.02},
    ),
    "steal": ActionRelationshipEffects(
        actor={"trust": -0.2, "fear": 0.15, "friendship": -0.15},
        witness_penalty={"trust": -0.08, "fear": 0.1, "friendship": -0.08, "respect": -0.05},
        witness_approval={"trust": 0.05, "respect": 0.04},
    ),
    "sabotage": ActionRelationshipEffects(
        actor={"trust": -0.15, "fear": 0.1, "friendship": -0.12, "respect": -0.05},
        witness_penalty={"trust": -0.06, "fear": 0.08, "friendship": -0.06, "respect": -0.04},
        witness_approval={"trust": 0.04, "respect": 0.03},
    ),
    "persuade": ActionRelationshipEffects(
        actor={"trust": 0.02, "respect": 0.04},
        witness_penalty={"trust": -0.015, "respect": -0.02},
    ),
    "campaign": ActionRelationshipEffects(
        actor={"respect": 0.05},
        witness_penalty={"respect": -0.025},
    ),
    "build": ActionRelationshipEffects(
        actor={"respect": 0.03, "trust": 0.02},
        witness_penalty={"trust": -0.02, "respect": -0.02},
    ),
    "quarry": ActionRelationshipEffects(
        actor={"respect": 0.03, "trust": 0.02},
        witness_penalty={"trust": -0.02, "respect": -0.02},
    ),
    "vote": ActionRelationshipEffects(
        witness_penalty={"trust": -0.02, "respect": -0.02},
    ),
}


@dataclass
class InteractionOutcome:
    positive_success: bool = False
    hostile_success: bool = False
    hostile_approval_enabled: bool = True
    apply_actor_deltas: bool = True
    delta_scale: float = 1.0
    witnesses_defending: int = 0


class RelationshipManager:
    def __init__(self, repo: Repository):
        self.repo = repo

    def get_trust(self, a_id: str, b_id: str) -> float:
        stored = self.repo.get_relationship(a_id, b_id)
        return stored.trust if stored else 0.3

    def get_relationship(self, a_id: str, b_id: str) -> Relationship:
        relationship = self.repo.get_relationship(a_id, b_id)
        if relationship:
            return relationship
        return Relationship(a_id=a_id, b_id=b_id)

    @staticmethod
    def _apply_deltas(
        relationship: Relationship, deltas: RelationshipDelta, *, scale: float = 1.0
    ) -> None:
        for field_name, delta in deltas.items():
            current = getattr(relationship, field_name)
            setattr(
                relationship,
                field_name,
                max(0.0, min(1.0, current + delta * scale)),
            )

    @staticmethod
    def _effects_for(action_type: str) -> ActionRelationshipEffects | None:
        return ACTION_RELATIONSHIP_EFFECTS.get(action_type)

    def _sentiment_intensity(
        self, rules: tuple[SentimentRule, ...], witness_id: str, target_id: str
    ) -> float:
        relationship = self.get_relationship(witness_id, target_id)
        intensities = [
            value
            for rule in rules
            if (value := rule.intensity(relationship)) is not None
        ]
        return min(1.0, max(intensities)) if intensities else 0.0

    def _witness_dislike_intensity(self, witness_id: str, target_id: str) -> float:
        return self._sentiment_intensity(DISLIKE_RULES, witness_id, target_id)

    def _witness_like_intensity(self, witness_id: str, target_id: str) -> float:
        return self._sentiment_intensity(LIKE_RULES, witness_id, target_id)

    def _update_pair(
        self,
        a_id: str,
        b_id: str,
        deltas: RelationshipDelta,
        *,
        scale: float = 1.0,
        agent_exists: Callable[[str], bool] | None = None,
    ) -> None:
        if a_id == b_id:
            return
        exists = agent_exists or self.repo.get_agent
        if not exists(b_id):
            return
        relationship = self.get_relationship(a_id, b_id)
        self._apply_deltas(relationship, deltas, scale=scale)
        self.repo.save_relationship(relationship)

    def update_from_action(
        self, agent_id: str, action: Action, *, delta_scale: float = 1.0
    ) -> None:
        effects = self._effects_for(action.type)
        if not effects or not action.target:
            return
        self._update_pair(agent_id, action.target, effects.actor, scale=delta_scale)

    def apply_association_penalties(
        self,
        actor_id: str,
        action: Action,
        agents: dict[str, Agent],
        *,
        delta_scale: float = 1.0,
    ) -> None:
        effects = self._effects_for(action.type)
        if (
            not effects
            or not effects.witness_penalty
            or not action.target
            or not self.repo.get_agent(action.target)
        ):
            return

        for witness_id in agents:
            if witness_id in (actor_id, action.target):
                continue
            intensity = self._witness_dislike_intensity(witness_id, action.target)
            if intensity <= 0.0:
                continue
            self._update_pair(
                witness_id,
                actor_id,
                effects.witness_penalty,
                scale=delta_scale * intensity,
                agent_exists=agents.__contains__,
            )

    def apply_witness_hostile_reactions(
        self,
        actor_id: str,
        action: Action,
        agents: dict[str, Agent],
        *,
        delta_scale: float = 1.0,
        approval_enabled: bool = True,
    ) -> int:
        """React to a hostile act against a target.

        Witnesses who fear or dislike the victim warm to the aggressor; witnesses
        who like the victim condemn it. Returns how many witnesses defended the
        victim so the resolver can apply an extra reputation penalty.
        """
        effects = self._effects_for(action.type)
        if (
            not effects
            or not action.target
            or not self.repo.get_agent(action.target)
        ):
            return 0

        victim_id = action.target
        defenders = 0
        for witness_id in agents:
            if witness_id in (actor_id, victim_id):
                continue
            dislike = self._witness_dislike_intensity(witness_id, victim_id)
            if dislike > 0.0:
                if approval_enabled and effects.witness_approval:
                    self._update_pair(
                        witness_id,
                        actor_id,
                        effects.witness_approval,
                        scale=delta_scale * dislike,
                        agent_exists=agents.__contains__,
                    )
                continue
            like = self._witness_like_intensity(witness_id, victim_id)
            if like > 0.0:
                defenders += 1
                if effects.witness_penalty:
                    self._update_pair(
                        witness_id,
                        actor_id,
                        effects.witness_penalty,
                        scale=delta_scale * like,
                        agent_exists=agents.__contains__,
                    )
        return defenders

    def finalize_action_relationships(
        self,
        actor_id: str,
        action: Action,
        agents: dict[str, Agent],
        outcome: InteractionOutcome,
    ) -> None:
        if not action.target:
            return
        if outcome.apply_actor_deltas:
            self.update_from_action(
                actor_id, action, delta_scale=outcome.delta_scale
            )
        if outcome.positive_success:
            self.apply_association_penalties(
                actor_id, action, agents, delta_scale=outcome.delta_scale
            )
        if outcome.hostile_success:
            outcome.witnesses_defending = self.apply_witness_hostile_reactions(
                actor_id,
                action,
                agents,
                delta_scale=outcome.delta_scale,
                approval_enabled=outcome.hostile_approval_enabled,
            )

    def decay_all(self, factor: float = 0.99) -> None:
        for relationship in self.repo.get_all_relationships():
            relationship.trust *= factor
            relationship.friendship *= factor
            self.repo.save_relationship(relationship)
