from __future__ import annotations

from dataclasses import dataclass, field


REASONING_INSTRUCTION = (
    "Before choosing your action, reason briefly about village needs, your goals, "
    "and relationships. Put reasoning inside ... tags, then output "
    "only the JSON action."
)

TARGETING_INSTRUCTION = (
    "Every action requires a target villager from the roster (not yourself)."
)


@dataclass
class DecisionPromptContext:
    agent_name: str
    agent_role: str
    tick: int
    chief: str
    wealth: int
    reputation: int
    supply_credit: int
    greed: float
    sociability: float
    aggression: float
    honesty: float
    primary_goal: str
    food: int
    wood: int
    stone: int
    gold: int
    resource_balance_line: str
    role_stewardship_line: str
    threat_level: str
    threat_message: str
    food_days_remaining: float
    election_active: bool
    candidates: list[str]
    roster_line: str
    relationships_json: str
    recent_memories_json: str
    semantic_memories_json: str
    action_schema_block: str
    reasoning_instruction: str = ""


def format_constraint_notes(notes: list[str]) -> str:
    if not notes:
        return ""
    return "CONSTRAINTS: " + " | ".join(notes)


def render_decision_prompt(context: DecisionPromptContext) -> str:
    election_line = (
        f"Election active. Candidates: {', '.join(context.candidates) or 'none'}."
        if context.election_active
        else "No election is active."
    )
    sections = [
        f"You are {context.agent_name}, a {context.agent_role} in an emergent village simulation.",
        f"Tick {context.tick}. Chief: {context.chief}.",
        (
            f"Your stats — wealth: {context.wealth}, reputation: {context.reputation}, "
            f"supply_credit: {context.supply_credit}."
        ),
        (
            f"Personality — greed: {context.greed:.2f}, sociability: {context.sociability:.2f}, "
            f"aggression: {context.aggression:.2f}, honesty: {context.honesty:.2f}."
        ),
        f"Primary goal: {context.primary_goal}.",
        (
            f"Village stock — food: {context.food}, wood: {context.wood}, "
            f"stone: {context.stone}, gold: {context.gold}."
        ),
        context.resource_balance_line,
        context.role_stewardship_line,
        f"Threat: {context.threat_level} — {context.threat_message} "
        f"(food days remaining: {context.food_days_remaining:.1f}).",
        election_line,
        context.roster_line,
        f"Top relationships: {context.relationships_json}",
        f"Recent memories: {context.recent_memories_json}",
        f"Relevant memories: {context.semantic_memories_json}",
        context.action_schema_block,
    ]
    if context.reasoning_instruction:
        sections.append(context.reasoning_instruction)
    return "\n\n".join(section for section in sections if section)


def render_retry_prompt(
    context: DecisionPromptContext,
    *,
    base_prompt: str,
    attempt: int,
    max_attempts: int,
    error: str,
    valid_types: str,
    constraints: str,
    snippet: str,
) -> str:
    parts = [
        base_prompt,
        (
            f"RETRY {attempt}/{max_attempts}: Your previous response was invalid "
            f"({error})."
        ),
        f"Valid action types: {valid_types}.",
    ]
    if constraints:
        parts.append(constraints)
    if snippet:
        parts.append(f"Previous invalid snippet: {snippet}")
    parts.append("Respond with ONLY valid JSON for your next action.")
    return "\n\n".join(parts)
