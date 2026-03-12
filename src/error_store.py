"""In-memory error log store — keeps recent errors searchable by request_id."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ErrorEntry:
    request_id: str
    timestamp: float
    event: str  # e.g. "ask_timeout", "inference_error", "auth_failed"
    detail: str
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "timestamp": self.timestamp,
            "iso_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.timestamp)),
            "event": self.event,
            "detail": self.detail,
            **self.extra,
        }


class ErrorStore:
    """Ring-buffer of recent errors, queryable by request_id or event type."""

    def __init__(self, max_size: int = 1000) -> None:
        self._entries: deque[ErrorEntry] = deque(maxlen=max_size)
        self._by_request_id: dict[str, list[ErrorEntry]] = {}

    def add(
        self,
        request_id: str,
        event: str,
        detail: str,
        **extra: Any,
    ) -> ErrorEntry:
        entry = ErrorEntry(
            request_id=request_id,
            timestamp=time.time(),
            event=event,
            detail=detail,
            extra=extra,
        )
        self._entries.append(entry)
        self._by_request_id.setdefault(request_id, []).append(entry)
        # Evict old index entries when ring buffer wraps
        self._cleanup_index()
        return entry

    def get_by_request_id(self, request_id: str) -> list[dict]:
        entries = self._by_request_id.get(request_id, [])
        return [e.to_dict() for e in entries]

    def get_by_event(self, event: str) -> list[dict]:
        return [e.to_dict() for e in self._entries if e.event == event]

    def get_recent(self, limit: int = 50) -> list[dict]:
        items = list(self._entries)[-limit:]
        return [e.to_dict() for e in reversed(items)]

    def count(self) -> int:
        return len(self._entries)

    def _cleanup_index(self) -> None:
        """Remove index entries that have been evicted from the ring buffer."""
        live_ids = {e.request_id for e in self._entries}
        stale = [rid for rid in self._by_request_id if rid not in live_ids]
        for rid in stale:
            del self._by_request_id[rid]


error_store = ErrorStore()
