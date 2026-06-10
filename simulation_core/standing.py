from __future__ import annotations

from config import ElectionConfig
from models.schemas import Agent


def _rank_value(value: int, values: list[int]) -> float:
    if not values:
        return 0.0
    unique_sorted = sorted(set(values), reverse=True)
    if value not in unique_sorted:
        return 0.0
    rank = unique_sorted.index(value)
    if len(unique_sorted) == 1:
        return 1.0
    return 1.0 - (rank / (len(unique_sorted) - 1))


def compute_standing(
    agent: Agent,
    agents: dict[str, Agent],
    election_config: ElectionConfig,
) -> float:
    wealth_values = [a.stats.wealth for a in agents.values()]
    rep_values = [a.stats.reputation for a in agents.values()]
    wealth_rank = _rank_value(agent.stats.wealth, wealth_values)
    rep_rank = _rank_value(agent.stats.reputation, rep_values)
    return (
        election_config.standing_wealth_weight * wealth_rank
        + election_config.standing_reputation_weight * rep_rank
    )


def standings_for_agents(
    agents: dict[str, Agent],
    election_config: ElectionConfig,
) -> dict[str, float]:
    return {
        agent_id: compute_standing(agent, agents, election_config)
        for agent_id, agent in agents.items()
    }


def standing_details_for_agents(
    agents: dict[str, Agent],
    election_config: ElectionConfig,
) -> dict[str, dict[str, float]]:
    wealth_values = [agent.stats.wealth for agent in agents.values()]
    rep_values = [agent.stats.reputation for agent in agents.values()]
    details: dict[str, dict[str, float]] = {}
    for agent_id, agent in agents.items():
        wealth_rank = _rank_value(agent.stats.wealth, wealth_values)
        rep_rank = _rank_value(agent.stats.reputation, rep_values)
        standing = (
            election_config.standing_wealth_weight * wealth_rank
            + election_config.standing_reputation_weight * rep_rank
        )
        details[agent_id] = {
            "standing": round(standing, 4),
            "wealth_rank": round(wealth_rank, 4),
            "reputation_rank": round(rep_rank, 4),
        }
    return details
