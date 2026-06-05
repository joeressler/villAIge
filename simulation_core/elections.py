from __future__ import annotations

import random
from typing import Optional

from config import AppConfig
from db.repository import Repository
from models.schemas import Agent, ElectionState, WorldState


class ElectionSystem:
    ELECTION_DURATION = 5

    def __init__(self, config: AppConfig, repo: Repository):
        self.config = config
        self.repo = repo

    def maybe_start_election(self, state: WorldState, agents: dict[str, Agent]) -> bool:
        interval = self.config.simulation.election_interval_ticks
        if state.election_state.active:
            return False
        if state.tick > 0 and state.tick % interval == 0:
            candidates = self._select_candidates(agents)
            state.election_state = ElectionState(
                active=True,
                candidates=candidates,
                days_remaining=self.ELECTION_DURATION,
            )
            self.repo.save_world_event(
                state.tick,
                "election_started",
                f"Election started with candidates: {', '.join(candidates)}",
                {"candidates": candidates},
            )
            return True
        return False

    def _select_candidates(self, agents: dict[str, Agent]) -> list[str]:
        sorted_by_rep = sorted(
            agents.values(), key=lambda a: a.stats.reputation, reverse=True
        )
        top = [a.id for a in sorted_by_rep[:3]]
        ambitious = [
            a.id
            for a in agents.values()
            if a.goals.primary == "become_chief" and a.id not in top
        ]
        candidates = list(dict.fromkeys(top + random.sample(ambitious, min(2, len(ambitious)))))
        return candidates[:5]

    def tick_election(self, state: WorldState) -> bool:
        """Returns True when election period ends this tick."""
        if not state.election_state.active:
            return False
        state.election_state.days_remaining -= 1
        return state.election_state.days_remaining <= 0

    def finalize_election(
        self,
        state: WorldState,
        agents: dict[str, Agent],
        get_trust,
    ) -> tuple[Optional[str], dict[str, float]]:
        candidates = list(state.election_state.candidates)
        state.election_state.active = False
        state.election_state.days_remaining = 0
        if not candidates:
            return None, {}
        winner, scores = self.tally_votes(agents, candidates, get_trust)
        return winner, scores

    def compute_vote_score(
        self,
        voter: Agent,
        candidate: Agent,
        trust: float,
    ) -> float:
        wealth_influence = min(candidate.stats.wealth / 100.0, 1.0)
        reputation_norm = candidate.stats.reputation / 100.0
        return trust * 0.4 + reputation_norm * 0.3 + wealth_influence * 0.3

    def tally_votes(
        self,
        agents: dict[str, Agent],
        candidates: list[str],
        get_trust,
    ) -> tuple[str, dict[str, float]]:
        scores: dict[str, float] = {c: 0.0 for c in candidates}
        for voter in agents.values():
            best_candidate = None
            best_score = -1.0
            for cid in candidates:
                candidate = agents.get(cid)
                if not candidate:
                    continue
                trust = get_trust(voter.id, cid)
                score = self.compute_vote_score(voter, candidate, trust)
                if voter.id == cid:
                    score += 0.1
                if score > best_score:
                    best_score = score
                    best_candidate = cid
            if best_candidate:
                scores[best_candidate] += 1.0

        winner = max(scores, key=scores.get)  # type: ignore[arg-type]
        return winner, scores
