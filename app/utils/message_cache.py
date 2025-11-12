from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict
import threading


class MessageCache:
    """In-memory TTL cache for deduplicating incoming messages.

    Not process-safe. Intended for single-process uvicorn workers.
    """

    def __init__(self, ttl_seconds: int = 60) -> None:
        self._cache: Dict[str, datetime] = {}
        self._ttl = timedelta(seconds=ttl_seconds)
        self._lock = threading.Lock()

    def is_duplicate(self, msg_id: str) -> bool:
        now = datetime.now()
        with self._lock:
            self._cleanup_locked(now)
            return msg_id in self._cache

    def mark_processed(self, msg_id: str) -> None:
        with self._lock:
            self._cache[msg_id] = datetime.now()

    def _cleanup_locked(self, now: datetime) -> None:
        expired = [k for k, v in self._cache.items() if now - v > self._ttl]
        for k in expired:
            self._cache.pop(k, None)


# module-level instance
message_cache = MessageCache()

