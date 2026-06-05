from __future__ import annotations

from typing import Any, Optional

from config import LangfuseConfig
from db.repository import Repository


class LangfuseTracer:
    def __init__(self, config: LangfuseConfig, repo: Repository):
        self.config = config
        self.repo = repo
        self._client: Any = None
        if config.enabled and config.public_key and config.secret_key:
            try:
                from langfuse import Langfuse

                self._client = Langfuse(
                    public_key=config.public_key,
                    secret_key=config.secret_key,
                    host=config.host,
                )
            except Exception:
                self._client = None

    def trace_decision(
        self,
        agent_id: str,
        tick: int,
        prompt: str,
        response: str,
        latency_ms: float = 0.0,
        token_usage: int = 0,
        action_type: str = "",
        metadata: Optional[dict] = None,
    ) -> str:
        trace_id = self.repo.save_llm_trace(
            agent_id=agent_id,
            tick=tick,
            prompt=prompt,
            response=response,
            latency_ms=latency_ms,
            token_usage=token_usage,
            action_type=action_type,
        )
        if self._client:
            try:
                trace = self._client.trace(
                    name=f"agent_decision_{agent_id}_tick_{tick}",
                    metadata=metadata or {},
                )
                trace.generation(
                    name="llm_decision",
                    input=prompt,
                    output=response,
                    model="village-agent",
                    usage={"total": token_usage},
                    metadata={"latency_ms": latency_ms, "action_type": action_type},
                )
            except Exception:
                pass
        return trace_id
