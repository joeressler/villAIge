from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from threading import Lock
from typing import Any


_LEVEL_ORDER = {
    "DEBUG": 10,
    "INFO": 20,
    "WARNING": 30,
    "ERROR": 40,
}


@dataclass
class FeedEntry:
    level: str
    logger: str
    message: str
    extra: dict[str, Any] = field(default_factory=dict)


class ObservabilityFeed:
    def __init__(self, max_entries: int = 500):
        self._max_entries = max_entries
        self._logs: deque[FeedEntry] = deque(maxlen=max_entries)
        self._errors: deque[dict[str, Any]] = deque(maxlen=max_entries)
        self._lock = Lock()

    def record_log(self, *, level: str, logger: str, message: str, **extra: Any) -> None:
        with self._lock:
            self._logs.append(
                FeedEntry(level=level.upper(), logger=logger, message=message, extra=extra)
            )

    def record_error(
        self,
        *,
        source: str,
        error_type: str,
        message: str,
        **extra: Any,
    ) -> None:
        entry = {
            "source": source,
            "error_type": error_type,
            "message": message,
            **extra,
        }
        with self._lock:
            self._errors.append(entry)
            self._logs.append(
                FeedEntry(level="ERROR", logger=source, message=message, extra=entry)
            )

    def get_logs(self, *, limit: int = 100, min_level: str = "INFO") -> list[dict[str, Any]]:
        threshold = _LEVEL_ORDER.get(min_level.upper(), 20)
        with self._lock:
            entries = [
                {
                    "level": entry.level,
                    "logger": entry.logger,
                    "message": entry.message,
                    **entry.extra,
                }
                for entry in reversed(self._logs)
                if _LEVEL_ORDER.get(entry.level, 0) >= threshold
            ]
        return entries[:limit]

    def get_errors(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            return list(reversed(self._errors))[:limit]

    def clear(self) -> None:
        with self._lock:
            self._logs.clear()
            self._errors.clear()


feed = ObservabilityFeed()
