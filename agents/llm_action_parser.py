from __future__ import annotations

import json
import re
from typing import Any


_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)
_THINKING_RE = re.compile(r"<think(?:ing)?>(.*?)</think(?:ing)?>", re.DOTALL | re.IGNORECASE)


def extract_inline_thinking(response: str) -> str:
    match = _THINKING_RE.search(response or "")
    return match.group(1).strip() if match else ""


def _strip_thinking_blocks(text: str) -> str:
    return _THINKING_RE.sub("", text or "").strip()


def _try_parse_json_object(candidate: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _find_balanced_json_object(text: str) -> str | None:
    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escape = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]
        start = text.find("{", start + 1)
    return None


def extract_action_dict(response: str, fallback_text: str = "") -> dict[str, Any] | None:
    for source in (response, fallback_text):
        if not source:
            continue
        cleaned = _strip_thinking_blocks(source)
        block_match = _JSON_BLOCK_RE.search(cleaned)
        if block_match:
            parsed = _try_parse_json_object(block_match.group(1))
            if parsed is not None:
                return parsed
        candidate = _find_balanced_json_object(cleaned)
        if candidate:
            parsed = _try_parse_json_object(candidate)
            if parsed is not None:
                return parsed
    return None
