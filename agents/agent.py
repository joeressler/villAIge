from __future__ import annotations

import json
import logging
import re

from agents.action_normalize import NormalizedAction, normalize_action
from exceptions import InvalidActionError, LLMParseError
from models.schemas import Action, Agent

logger = logging.getLogger(__name__)

_TARGET_BARE_RE = re.compile(
    r'("target"\s*:\s*)([A-Za-z0-9_-]+)(\s*[,}])',
    re.IGNORECASE,
)

_THINKING_BLOCK_PATTERNS = (
    re.compile(r".*?", re.DOTALL | re.IGNORECASE),
    re.compile(
        r"<\s*redacted_thinking\s*>.*?<\s*/\s*redacted_thinking\s*>",
        re.DOTALL | re.IGNORECASE,
    ),
    re.compile(
        r"<\s*think(?:ing)?\s*>.*?<\s*/\s*think(?:ing)?\s*>",
        re.DOTALL | re.IGNORECASE,
    ),
)


class AgentRunner:
    def __init__(self, aliases: dict[str, str] | None = None) -> None:
        self.aliases = aliases

    def normalize(
        self,
        data: dict,
        *,
        agents: list[Agent] | None = None,
        valid_agent_ids: frozenset[str] | None = None,
        acting_agent_id: str | None = None,
    ) -> NormalizedAction:
        return normalize_action(
            data,
            agents=agents,
            valid_agent_ids=valid_agent_ids,
            aliases=self.aliases,
            acting_agent_id=acting_agent_id,
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
        parts: list[str] = []
        for pattern in _THINKING_BLOCK_PATTERNS:
            for match in pattern.finditer(response):
                block = match.group(0)
                inner = re.sub(
                    r"^<\s*[^>]+>\s*|\s*<\s*/\s*[^>]+>\s*$",
                    "",
                    block,
                    flags=re.IGNORECASE | re.DOTALL,
                ).strip()
                if inner:
                    parts.append(inner)
        return "\n".join(parts).strip()

    @staticmethod
    def _strip_reasoning(response: str) -> str:
        text = response
        for pattern in _THINKING_BLOCK_PATTERNS:
            text = pattern.sub("", text)
        return text.strip()

    @staticmethod
    def _repair_llm_json(text: str) -> str:
        def quote_bare_target(match: re.Match[str]) -> str:
            prefix, value, suffix = match.groups()
            if value.lower() in {"null", "true", "false"}:
                return match.group(0)
            try:
                float(value)
                return match.group(0)
            except ValueError:
                return f'{prefix}"{value}"{suffix}'

        return _TARGET_BARE_RE.sub(quote_bare_target, text)

    @staticmethod
    def _loads_action_json(snippet: str) -> dict | None:
        for candidate in (snippet, AgentRunner._repair_llm_json(snippet)):
            try:
                obj = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                return obj
        return None

    @staticmethod
    def _parse_action_loose(text: str) -> dict | None:
        type_match = re.search(r'"type"\s*:\s*"([^"]+)"', text, re.IGNORECASE)
        if not type_match:
            return None
        result: dict = {"type": type_match.group(1)}
        target_match = re.search(
            r'"target"\s*:\s*(?:"([^"]*)"|null|([A-Za-z0-9_-]+))',
            text,
            re.IGNORECASE,
        )
        if target_match:
            quoted, bare = target_match.groups()
            value = quoted if quoted is not None else bare
            if value and value.lower() not in {"null", "none"}:
                result["target"] = value
            else:
                result["target"] = None
        payload_match = re.search(r'"payload"\s*:\s*(\{[^}]*\})', text)
        if payload_match:
            payload = AgentRunner._loads_action_json(payload_match.group(1))
            if payload is not None:
                result["payload"] = payload
            else:
                result["payload"] = {}
        else:
            result["payload"] = {}
        return result

    @staticmethod
    def _extract_json_objects(text: str) -> list[dict]:
        objects: list[dict] = []
        i = 0
        while i < len(text):
            start = text.find("{", i)
            if start < 0:
                break
            depth = 0
            in_string = False
            escape = False
            parsed: dict | None = None
            for j in range(start, len(text)):
                ch = text[j]
                if in_string:
                    if escape:
                        escape = False
                    elif ch == "\\":
                        escape = True
                    elif ch == '"':
                        in_string = False
                    continue
                if ch == '"':
                    in_string = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        parsed = AgentRunner._loads_action_json(text[start : j + 1])
                        break
            if parsed is not None:
                objects.append(parsed)
                i = start + 1
            else:
                i = start + 1
        return objects

    @classmethod
    def _select_action_payload(cls, response: str) -> dict | None:
        cleaned = cls._strip_reasoning(response)
        for source in (cleaned, response):
            candidates = cls._extract_json_objects(source)
            typed = [obj for obj in candidates if obj.get("type")]
            if typed:
                return typed[-1]
            loose = cls._parse_action_loose(source)
            if loose:
                return loose
            substantive = [obj for obj in candidates if obj]
            if substantive:
                return substantive[-1]
        return None

    def action_from_dict(self, data: dict) -> Action:
        return self.normalize(data).action

    def parse_llm_action(self, response: str, fallback_text: str = "") -> Action:
        data = self._select_action_payload(response)
        if data is None and fallback_text and fallback_text != response:
            data = self._select_action_payload(fallback_text)
        if data is None:
            snippet = response[:200] if response else "(empty)"
            logger.error("No JSON object found in LLM response snippet=%r", snippet)
            raise LLMParseError(f"No JSON object found in LLM response: {snippet!r}")
        return self.action_from_dict(data)
