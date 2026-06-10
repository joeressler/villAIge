from __future__ import annotations

import time
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage
from pydantic import BaseModel

from exceptions import LLMEmptyResponseError, LLMParseError
from llm.provider import LLMResponse, StructuredLLMResult


def _message_text(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts).strip()
    return str(content or "").strip()


def _usage_value(usage: Any, *keys: str) -> int:
    if usage is None:
        return 0
    if isinstance(usage, dict):
        for key in keys:
            value = usage.get(key)
            if isinstance(value, int):
                return value
        return 0
    for key in keys:
        value = getattr(usage, key, None)
        if isinstance(value, int):
            return value
    return 0


def message_to_llm_response(
    message: BaseMessage,
    *,
    model: str = "",
    latency_ms: float = 0.0,
) -> LLMResponse:
    text = _message_text(message)
    if not text and not isinstance(message, AIMessage):
        raise LLMEmptyResponseError("LLM returned empty response")

    usage = getattr(message, "usage_metadata", None) or getattr(message, "response_metadata", {}).get("token_usage")
    prompt_tokens = _usage_value(usage, "input_tokens", "prompt_tokens")
    completion_tokens = _usage_value(usage, "output_tokens", "completion_tokens")
    reasoning_tokens = _usage_value(usage, "reasoning_tokens")
    total_tokens = _usage_value(usage, "total_tokens")
    if total_tokens <= 0:
        total_tokens = prompt_tokens + completion_tokens + reasoning_tokens

    thinking = ""
    if isinstance(message, AIMessage):
        additional = getattr(message, "additional_kwargs", {}) or {}
        thinking = str(additional.get("reasoning_content") or additional.get("thinking") or "")

    return LLMResponse(
        text=text,
        thinking=thinking,
        latency_ms=latency_ms,
        token_usage=total_tokens,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        reasoning_tokens=reasoning_tokens,
        model=model,
    )


def invoke_with_timing(model: Any, prompt: str) -> tuple[BaseMessage, float]:
    start = time.perf_counter()
    message = model.invoke(prompt)
    elapsed = (time.perf_counter() - start) * 1000
    response = message_to_llm_response(message, latency_ms=elapsed)
    if not response.text:
        raise LLMEmptyResponseError("LLM returned empty response")
    return message, elapsed


def salvage_structured_result(
    result: dict[str, Any],
    schema: type[BaseModel],
    *,
    model_name: str,
    elapsed: float,
) -> StructuredLLMResult | None:
    raw_message = result.get("raw")
    if raw_message is None:
        return None
    response = message_to_llm_response(raw_message, model=model_name, latency_ms=elapsed)
    from agents.llm_action_parser import extract_action_dict

    action_dict = extract_action_dict(response.text)
    if action_dict is None:
        return None
    try:
        parsed = schema.model_validate(action_dict)
    except Exception as error:
        raise LLMParseError(f"Salvage parse failed: {error}") from error
    response.text = parsed.model_dump_json()
    return StructuredLLMResult(response=response, parsed=parsed)
