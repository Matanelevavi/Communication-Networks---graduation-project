"""
A per visitor rate limit.

Every forecast costs a call to Open-Meteo, and possibly one to Gemini, so one
visitor must not be able to spend the whole quota. A sliding window over the
last minute is enough for one instance; it lives in memory and resets with the
process, which is the right trade for a demo with no database.
"""
import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    """At most ``limit`` requests per ``window`` seconds for each key."""

    def __init__(self, limit: int, window: float = 60.0, clock=time.monotonic) -> None:
        self.limit = limit
        self.window = window
        self.clock = clock
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        """Record one request. False when this key is over its limit."""
        now = self.clock()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] >= self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            self._forget_idle(now)
            return True

    def retry_after(self, key: str) -> int:
        """Seconds until this key may send again."""
        with self._lock:
            hits = self._hits.get(key)
            if not hits:
                return 0
            return max(1, int(self.window - (self.clock() - hits[0])) + 1)

    def _forget_idle(self, now: float) -> None:
        """Drop visitors with nothing in the window, so memory stays bounded."""
        if len(self._hits) < 1024:
            return
        for key in [k for k, hits in self._hits.items()
                    if not hits or now - hits[-1] >= self.window]:
            del self._hits[key]
