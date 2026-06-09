from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Callable, Generator, Optional

from config import LangfuseConfig
from db.repository import Repository
from llm.provider import LLMResponse
from models.schemas import Agent, WorldState
from observability.feed import feed

logger = logging.getLogger(__name__)


class LangfuseTracer:
    """Langfuse v4 tracing for village simulation (LangGraph + custom LLM calls)."""

    def __init__(self, config: LangfuseConfig, repo: Repository):
        self.config = config
        self.repo = repo
        self._client: Any = None
        self._enabled = self._configure(config)

    def _configure(self, config: LangfuseConfig) -> bool:
        if not config.enabled:
            return False

        if config.public_key:
            os.environ.setdefault("LANGFUSE_PUBLIC_KEY", config.public_key)
        if config.secret_key:
            os.environ.setdefault("LANGFUSE_SECRET_KEY", config.secret_key)
        if config.resolved_base_url:
            os.environ.setdefault("LANGFUSE_BASE_URL", config.resolved_base_url)
        os.environ.setdefault(
            "LANGFUSE_TRACING_ENVIRONMENT",
            os.environ.get("ENVIRONMENT", "development"),
        )

        if not (config.public_key and config.secret_key):
            logger.info("Langfuse tracing disabled: missing API keys")
            return False

        try:
            from langfuse import get_client

            self._client = get_client()
            logger.info("Langfuse tracing enabled")
            return True
        except Exception:
            logger.exception("Langfuse client initialization failed")
            return False

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def flush(self) -> None:
        if not self._client:
            return
        try:
            self._client.flush()
        except Exception:
            logger.exception("Langfuse flush failed")

    def _metadata(self, **kwargs: Any) -> dict[str, str]:
        result: dict[str, str] = {}
        for key, value in kwargs.items():
            if value is None:
                continue
            result[key] = str(value)[:200]
        return result

    @contextmanager
    def trace_tick(self, tick: int, population: int) -> Generator[None, None, None]:
        if not self.enabled:
            yield
            return

        from langfuse import propagate_attributes

        with self._client.start_as_current_observation(
            as_type="span",
            name="simulation-tick",
            input={"tick": tick, "population": population},
        ):
            with propagate_attributes(
                trace_name=f"village-tick-{tick}",
                session_id=f"simulation-tick-{tick}",
                tags=["village-sim", "tick"],
                metadata=self._metadata(tick=tick, population=population),
            ):
                yield

    def run_agent_decision(
        self,
        agent: Agent,
        world: WorldState,
        graph_invoke: Callable[[Optional[Any]], dict],
    ) -> dict:
        if not self.enabled:
            return graph_invoke(None)

        from langfuse import propagate_attributes

        try:
            from langfuse.langchain import CallbackHandler
        except ModuleNotFoundError:
            logger.warning(
                "langchain not installed; LangGraph callback tracing disabled"
            )
            return graph_invoke(None)

        session_id = f"tick-{world.tick}"
        tags = ["village-sim", "agent-decision", agent.role]
        if world.election_state.active:
            tags.append("election-active")

        with self._client.start_as_current_observation(
            as_type="span",
            name="agent-decision",
            input={
                "agent_id": agent.id,
                "agent_name": agent.name,
                "role": agent.role,
                "tick": world.tick,
            },
        ) as decision_span:
            with propagate_attributes(
                trace_name="agent-decision",
                session_id=session_id,
                user_id=agent.id,
                tags=tags,
                metadata=self._metadata(
                    agent_name=agent.name,
                    role=agent.role,
                    tick=world.tick,
                    goal=agent.goals.primary,
                ),
            ):
                handler = CallbackHandler()
                result = graph_invoke(handler)
                action = result.get("action", {})
                decision_span.update(
                    output={
                        "action_type": action.get("type"),
                        "action_category": action.get("category"),
                        "target": action.get("target"),
                    }
                )
                return result

    def trace_llm_decision(
        self,
        *,
        agent_id: str,
        agent_name: str,
        tick: int,
        provider: str,
        prompt: str,
        response: LLMResponse,
        thinking: str = "",
        action_type: str,
        action_category: str,
        action_target: Optional[str],
    ) -> str:
        trace_id = self.repo.save_llm_trace(
            agent_id=agent_id,
            tick=tick,
            prompt=prompt,
            response=response.text,
            thinking=thinking,
            latency_ms=response.latency_ms,
            token_usage=response.token_usage,
            action_type=action_type,
        )
        if not self.enabled:
            return trace_id

        try:
            with self._client.start_as_current_observation(
                as_type="generation",
                name="llm-decision",
                model=response.model or "unknown",
                input={"prompt": prompt[:500]},
                metadata=self._metadata(
                    provider=provider,
                    agent_id=agent_id,
                    agent_name=agent_name,
                    action_type=action_type,
                    action_category=action_category,
                    action_target=action_target or "-",
                    has_thinking=str(bool(thinking.strip())),
                    reasoning_tokens=response.reasoning_tokens,
                ),
            ) as generation:
                generation.update(
                    output={
                        "response": response.text[:500],
                        "action_type": action_type,
                        "action_category": action_category,
                    },
                    usage_details=self._usage_details(response),
                )
                if thinking.strip():
                    with self._client.start_as_current_observation(
                        as_type="generation",
                        name="agent-reasoning",
                        model=response.model or "unknown",
                        input={"prompt": prompt[:500]},
                        metadata=self._metadata(
                            provider=provider,
                            agent_id=agent_id,
                            agent_name=agent_name,
                        ),
                    ) as reasoning_span:
                        reasoning_span.update(
                            output={"thinking": thinking[:2000]},
                        )
        except Exception:
            logger.exception("Langfuse LLM trace failed for agent %s", agent_id)
        return trace_id

    def trace_decision_retry(
        self,
        *,
        agent_id: str,
        tick: int,
        attempt: int,
        max_attempts: int,
        error_type: str,
        message: str,
        raw_response: Optional[str] = None,
    ) -> None:
        logger.warning(
            "Decision retry agent_id=%s tick=%s attempt=%s/%s error_type=%s message=%s",
            agent_id,
            tick,
            attempt,
            max_attempts,
            error_type,
            message,
        )
        feed.record_log(
            level="WARNING",
            logger="agents.decision_graph",
            message=(
                f"tick={tick} agent={agent_id} attempt={attempt}/{max_attempts} "
                f"{error_type}: {message}"
            ),
        )
        if not self.enabled:
            return
        try:
            with self._client.start_as_current_observation(
                as_type="span",
                name="decision-retry",
                level="WARNING",
                input={
                    "agent_id": agent_id,
                    "tick": tick,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "error_type": error_type,
                    "message": message[:500],
                    "raw_response": (raw_response or "")[:500],
                },
            ) as span:
                span.update(
                    output={
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "error_type": error_type,
                    }
                )
        except Exception:
            logger.exception(
                "Langfuse decision retry trace failed for agent %s", agent_id
            )

    def trace_action_normalization(
        self,
        *,
        agent_id: str,
        tick: int,
        adjustments: list[str],
    ) -> None:
        message = "; ".join(adjustments)
        logger.info(
            "Action normalized agent_id=%s tick=%s adjustments=%s",
            agent_id,
            tick,
            message,
        )
        feed.record_log(
            level="INFO",
            logger="agents.action_normalize",
            message=f"tick={tick} agent={agent_id}: {message}",
        )
        if not self.enabled:
            return
        try:
            with self._client.start_as_current_observation(
                as_type="span",
                name="action-normalization",
                input={
                    "agent_id": agent_id,
                    "tick": tick,
                    "adjustments": adjustments,
                },
            ) as span:
                span.update(output={"adjustments": adjustments})
        except Exception:
            logger.exception(
                "Langfuse action normalization trace failed for agent %s", agent_id
            )

    def trace_decision_error(
        self,
        *,
        agent_id: str,
        tick: int,
        error_type: str,
        message: str,
        raw_response: Optional[str] = None,
    ) -> None:
        logger.error(
            "Decision error agent_id=%s tick=%s error_type=%s message=%s",
            agent_id,
            tick,
            error_type,
            message,
        )
        feed.record_error(
            source="decision",
            error_type=error_type,
            message=message,
            tick=tick,
            agent_id=agent_id,
            raw_response=raw_response,
        )
        if not self.enabled:
            return
        try:
            with self._client.start_as_current_observation(
                as_type="span",
                name="decision-error",
                level="ERROR",
                input={
                    "agent_id": agent_id,
                    "tick": tick,
                    "error_type": error_type,
                    "message": message[:500],
                    "raw_response": (raw_response or "")[:500],
                },
            ) as span:
                span.update(
                    output={
                        "error_type": error_type,
                        "message": message[:500],
                    }
                )
        except Exception:
            logger.exception("Langfuse decision error trace failed for agent %s", agent_id)

    @contextmanager
    def trace_action_resolution(
        self,
        *,
        agent_name: str,
        action_type: str,
        action_category: str,
        tick: int,
        description: str = "",
    ) -> Generator[None, None, None]:
        if not self.enabled:
            yield
            return
        with self._client.start_as_current_observation(
            as_type="span",
            name="action-resolution",
            input={
                "agent": agent_name,
                "type": action_type,
                "category": action_category,
                "tick": tick,
            },
        ) as span:
            yield
            if description:
                try:
                    span.update(output={"description": description[:500]})
                except Exception:
                    logger.exception("Langfuse action resolution trace failed")

    def _usage_details(self, response: LLMResponse) -> dict[str, int]:
        details: dict[str, int] = {}
        if response.prompt_tokens > 0:
            details["input"] = response.prompt_tokens
        if response.completion_tokens > 0:
            details["output"] = response.completion_tokens
        if response.reasoning_tokens > 0:
            details["reasoning"] = response.reasoning_tokens
        if response.token_usage > 0:
            details["total"] = response.token_usage
        return details
