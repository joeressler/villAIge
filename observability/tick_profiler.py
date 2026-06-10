from __future__ import annotations

import time
from collections import defaultdict, deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Generator


@dataclass
class TickProfile:
    tick: int = 0
    population: int = 0
    phases: dict[str, float] = field(default_factory=dict)
    agents: dict[str, dict[str, float]] = field(default_factory=dict)
    total_ms: float = 0.0


class TickProfiler:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._lock = Lock()
        self._current: TickProfile | None = None
        self._phase_stack: list[tuple[str, float]] = []
        self._agent_stack: list[tuple[str, str, float]] = []
        self._recent: deque[dict[str, Any]] = deque(maxlen=50)

    def clear(self) -> None:
        with self._lock:
            self._current = None
            self._phase_stack.clear()
            self._agent_stack.clear()
            self._recent.clear()

    def begin_tick(self, tick: int, *, population: int) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._current = TickProfile(tick=tick, population=population)
            self._phase_stack = [("tick_total", time.perf_counter())]

    @contextmanager
    def phase(self, name: str) -> Generator[None, None, None]:
        if not self.enabled or self._current is None:
            yield
            return
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            with self._lock:
                if self._current is not None:
                    self._current.phases[name] = (
                        self._current.phases.get(name, 0.0) + elapsed_ms
                    )

    @contextmanager
    def agent_phase(self, agent_id: str, phase: str) -> Generator[None, None, None]:
        if not self.enabled or self._current is None:
            yield
            return
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            with self._lock:
                if self._current is not None:
                    agent_phases = self._current.agents.setdefault(agent_id, {})
                    agent_phases[phase] = agent_phases.get(phase, 0.0) + elapsed_ms

    def end_tick(self) -> dict[str, Any] | None:
        if not self.enabled or self._current is None:
            return None
        with self._lock:
            profile = self._current
            if profile is None:
                return None
            if self._phase_stack:
                start = self._phase_stack[0][1]
                profile.total_ms = (time.perf_counter() - start) * 1000
            payload = {
                "tick": profile.tick,
                "population": profile.population,
                "total_ms": round(profile.total_ms, 2),
                "phases": {key: round(value, 2) for key, value in profile.phases.items()},
                "agents": {
                    agent_id: {key: round(value, 2) for key, value in phases.items()}
                    for agent_id, phases in profile.agents.items()
                },
            }
            self._recent.append(payload)
            self._current = None
            return payload

    def get_recent(self, *, limit: int = 10) -> list[dict[str, Any]]:
        with self._lock:
            return list(reversed(self._recent))[:limit]

    def get_summary(self, *, limit: int = 10) -> dict[str, Any]:
        recent = self.get_recent(limit=limit)
        if not recent:
            return {"ticks": 0, "avg_total_ms": 0.0}
        totals = [entry.get("total_ms", 0.0) for entry in recent]
        return {
            "ticks": len(recent),
            "avg_total_ms": round(sum(totals) / len(totals), 2),
            "max_total_ms": round(max(totals), 2),
        }


_profiler = TickProfiler(enabled=True)


def configure_profiler(enabled: bool) -> None:
    _profiler.enabled = enabled


def get_profiler() -> TickProfiler:
    return _profiler
