from __future__ import annotations

import random
from typing import Callable, Optional

from config import AppConfig
from db.repository import Repository
from models.schemas import Agent, ElectionState, WorldState
from simulation_core.standing import compute_standing, standings_for_agents


class ElectionSystem:
    ELECTION_DURATION = 5

    def __init__(self, config: AppConfig, repo: Repository):
        self.config = config
        self.repo = repo

    @property
    def election_config(self):
        return self.config.election

    def maybe_start_election(self, state: WorldState, agents: dict[str, Agent]) -> bool:
        interval = self.config.simulation.election_interval_ticks
        if state.election_state.active:
            return False
        if state.tick > 0 and state.tick % interval == 0:
            prior_chief = state.chief
            candidates = self._select_candidates(state, agents)
            state.election_state = ElectionState(
                active=True,
                candidates=candidates,
                days_remaining=self.ELECTION_DURATION,
                ballots={},
                campaign_support={c: 0 for c in candidates},
                prior_chief=prior_chief,
            )
            candidate_names = [
                agents[c].name if c in agents else c for c in candidates
            ]
            self.repo.save_world_event(
                state.tick,
                "election_started",
                f"Election started with candidates: {', '.join(candidate_names)}",
                {"candidates": candidates},
            )
            return True
        return False

    def _excluded_from_candidacy(
        self, state: WorldState, agents: dict[str, Agent]
    ) -> set[str]:
        excluded: set[str] = set()
        cooldown = self.election_config.chief_cooldown_terms
        if cooldown <= 0:
            return excluded
        history = state.chief_history[-cooldown:] if state.chief_history else []
        if state.chief and cooldown >= 1:
            history = list(dict.fromkeys(history + [state.chief]))
        for chief_id in history[-cooldown:]:
            if chief_id in agents:
                excluded.add(chief_id)
        return excluded

    def _select_candidates(
        self, state: WorldState, agents: dict[str, Agent]
    ) -> list[str]:
        cfg = self.election_config
        excluded = self._excluded_from_candidacy(state, agents)
        eligible = [a for a in agents.values() if a.id not in excluded]
        if not eligible:
            eligible = list(agents.values())

        standings = standings_for_agents(agents, cfg)
        by_standing = sorted(
            eligible, key=lambda a: standings[a.id], reverse=True
        )
        selected: list[str] = []

        for agent in by_standing[:2]:
            if agent.id not in selected:
                selected.append(agent.id)

        remaining = [a for a in eligible if a.id not in selected]
        if remaining:
            top_rep = max(remaining, key=lambda a: a.stats.reputation)
            selected.append(top_rep.id)
            remaining = [a for a in remaining if a.id != top_rep.id]

        if remaining:
            top_wealth = max(remaining, key=lambda a: a.stats.wealth)
            selected.append(top_wealth.id)
            remaining = [a for a in remaining if a.id != top_wealth.id]

        wildcard_pool = [a for a in remaining if a.id not in selected]
        if wildcard_pool and len(selected) < cfg.candidate_count:
            weights = [
                standings[a.id] + random.uniform(0.05, 0.15)
                for a in wildcard_pool
            ]
            picks = min(cfg.wildcard_slots, cfg.candidate_count - len(selected))
            for _ in range(picks):
                if not wildcard_pool:
                    break
                chosen = random.choices(wildcard_pool, weights=weights, k=1)[0]
                selected.append(chosen.id)
                idx = wildcard_pool.index(chosen)
                wildcard_pool.pop(idx)
                weights.pop(idx)

        while len(selected) < min(cfg.candidate_count, len(eligible)):
            for agent in by_standing:
                if agent.id not in selected:
                    selected.append(agent.id)
                    break
            else:
                break

        return selected[: cfg.candidate_count]

    def record_vote(
        self, state: WorldState, voter_id: str, candidate_id: str
    ) -> bool:
        if not state.election_state.active:
            return False
        if candidate_id not in state.election_state.candidates:
            return False
        if voter_id in state.election_state.ballots:
            return False
        state.election_state.ballots[voter_id] = candidate_id
        return True

    def record_campaign(self, state: WorldState, candidate_id: str) -> int:
        if not state.election_state.active:
            return 0
        if candidate_id not in state.election_state.candidates:
            return 0
        support = state.election_state.campaign_support
        support[candidate_id] = support.get(candidate_id, 0) + 1
        return support[candidate_id]

    def campaign_rep_gain(self, state: WorldState, candidate_id: str) -> int:
        cfg = self.election_config
        count = state.election_state.campaign_support.get(candidate_id, 0)
        if count > cfg.max_campaign_rep_per_election:
            return 0
        if state.threat.level == "crisis":
            return max(0, cfg.max_campaign_rep_per_tick // 2)
        return cfg.max_campaign_rep_per_tick

    def tick_election(self, state: WorldState) -> bool:
        if not state.election_state.active:
            return False
        state.election_state.days_remaining -= 1
        return state.election_state.days_remaining <= 0

    def finalize_election(
        self,
        state: WorldState,
        agents: dict[str, Agent],
        get_trust: Callable[[str, str], float],
    ) -> tuple[Optional[str], dict[str, float]]:
        candidates = list(state.election_state.candidates)
        ballots = dict(state.election_state.ballots)
        state.election_state.active = False
        state.election_state.days_remaining = 0
        state.election_state.ballots = {}
        state.election_state.campaign_support = {}

        if not candidates:
            return None, {}

        scores: dict[str, float] = {c: 0.0 for c in candidates}
        for candidate_id in ballots.values():
            if candidate_id in scores:
                scores[candidate_id] += 1.0

        abstainers = [
            a for a in agents.values() if a.id not in ballots
        ]
        if (
            abstainers
            and self.election_config.abstain_fallback == "weighted"
        ):
            self._apply_abstain_fallback(
                abstainers, candidates, agents, scores, get_trust
            )

        if not any(scores.values()):
            winner = self._pick_by_standing(candidates, agents)
        else:
            winner = self._resolve_winner(scores, candidates, agents)

        self._apply_election_reputation(agents, scores, winner)
        return winner, scores

    def _apply_abstain_fallback(
        self,
        abstainers: list[Agent],
        candidates: list[str],
        agents: dict[str, Agent],
        scores: dict[str, float],
        get_trust: Callable[[str, str], float],
    ) -> None:
        cfg = self.election_config
        for voter in abstainers:
            best_candidate = None
            best_score = -1.0
            for cid in candidates:
                candidate = agents.get(cid)
                if not candidate:
                    continue
                trust = get_trust(voter.id, cid)
                standing = compute_standing(candidate, agents, cfg)
                score = trust * 0.4 + standing * 0.6
                if voter.id == cid:
                    score += 0.05
                if score > best_score:
                    best_score = score
                    best_candidate = cid
            if best_candidate:
                scores[best_candidate] += 1.0

    def _resolve_winner(
        self,
        scores: dict[str, float],
        candidates: list[str],
        agents: dict[str, Agent],
    ) -> str:
        max_score = max(scores.values())
        tied = [c for c in candidates if scores.get(c, 0) == max_score]
        if len(tied) == 1:
            return tied[0]
        return self._pick_by_standing(tied, agents)

    def _pick_by_standing(
        self, candidates: list[str], agents: dict[str, Agent]
    ) -> str:
        cfg = self.election_config
        best = candidates[0]
        best_standing = -1.0
        for cid in candidates:
            agent = agents.get(cid)
            if not agent:
                continue
            standing = compute_standing(agent, agents, cfg)
            if standing > best_standing:
                best_standing = standing
                best = cid
        return best

    def _apply_election_reputation(
        self,
        agents: dict[str, Agent],
        scores: dict[str, float],
        winner_id: Optional[str],
    ) -> None:
        cfg = self.election_config
        if winner_id and winner_id in agents:
            agents[winner_id].stats.reputation += cfg.winner_rep_bonus
        for cid, vote_count in scores.items():
            if cid == winner_id:
                continue
            agent = agents.get(cid)
            if agent and vote_count > 0:
                agent.stats.reputation += min(int(vote_count), 3)

    def ballot_tally(self, state: WorldState) -> dict[str, int]:
        counts: dict[str, int] = {}
        for candidate_id in state.election_state.ballots.values():
            counts[candidate_id] = counts.get(candidate_id, 0) + 1
        return counts
