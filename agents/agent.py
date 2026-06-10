from __future__ import annotations

import logging

from agents.action_normalize import NormalizedAction, normalize_action
from agents.llm_action_parser import extract_action_dict, extract_inline_thinking
from exceptions import LLMParseError
from models.schemas import Action, Agent

logger = logging.getLogger(__name__)


class AgentRunner:
    def __init__(self, aliases: dict[str, str] | None = None) -> None:
        self.aliases = aliases

    def normalize(
        self,
        raw_action_dict: dict,
        *,
        agents: list[Agent] | None = None,
        valid_agent_ids: frozenset[str] | None = None,
        acting_agent_id: str | None = None,
        forbidden_gift_targets: frozenset[str] | None = None,
        trade_catalog: dict | None = None,
        stewardship_mode: bool = True,
    ) -> NormalizedAction:
        return normalize_action(
            raw_action_dict,
            agents=agents,
            valid_agent_ids=valid_agent_ids,
            aliases=self.aliases,
            acting_agent_id=acting_agent_id,
            forbidden_gift_targets=forbidden_gift_targets,
            trade_catalog=trade_catalog,
            stewardship_mode=stewardship_mode,
        )

    def validate_action(
        self,
        action: Action,
        valid_agent_ids: frozenset[str] | None = None,
        agents: list[Agent] | None = None,
        acting_agent_id: str | None = None,
    ) -> Action:
        return self.normalize(
            action.model_dump(),
            agents=agents,
            valid_agent_ids=valid_agent_ids,
            acting_agent_id=acting_agent_id,
        ).action

    @staticmethod
    def extract_inline_thinking(response: str) -> str:
        return extract_inline_thinking(response)

    def extract_action_dict(self, response: str, fallback_text: str = "") -> dict | None:
        return extract_action_dict(response, fallback_text)

    def action_from_dict(self, raw_action_dict: dict) -> Action:
        return self.normalize(raw_action_dict).action

    def parse_llm_action(
        self,
        response: str,
        fallback_text: str = "",
        *,
        agents: list[Agent] | None = None,
        acting_agent_id: str | None = None,
        forbidden_gift_targets: frozenset[str] | None = None,
        trade_catalog: dict | None = None,
        stewardship_mode: bool = True,
    ) -> NormalizedAction:
        raw_action_dict = extract_action_dict(response, fallback_text)
        if raw_action_dict is None:
            snippet = response[:200] if response else "(empty)"
            logger.error("No JSON object found in LLM response snippet=%r", snippet)
            raise LLMParseError(f"No JSON object found in LLM response: {snippet!r}")
        return self.normalize(
            raw_action_dict,
            agents=agents,
            acting_agent_id=acting_agent_id,
            forbidden_gift_targets=forbidden_gift_targets,
            trade_catalog=trade_catalog,
            stewardship_mode=stewardship_mode,
        )
