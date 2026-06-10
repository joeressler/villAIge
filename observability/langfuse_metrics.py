from __future__ import annotations

from typing import Any

from config import LangfuseConfig


def get_metrics_dashboard(config: LangfuseConfig, *, hours: int = 24) -> dict[str, Any]:
    if not config.enabled or not (config.public_key and config.secret_key):
        return {
            "enabled": False,
            "hours": hours,
            "message": "Langfuse metrics unavailable (tracing disabled or missing keys).",
        }
    return {
        "enabled": True,
        "hours": hours,
        "message": "Connect Langfuse UI for live metrics; dashboard API stub is active.",
        "base_url": config.resolved_base_url,
    }
