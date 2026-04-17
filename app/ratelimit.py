"""
Einfacher In-Memory Rate Limiter (Sliding Window)
Kein Redis nötig – funktioniert für Single-Process Umgebungen
"""

import time
from collections import defaultdict, deque
from threading import Lock


class RateLimiter:
    def __init__(self, max_requests: int = 30, window: int = 60):
        self.max_requests = max_requests
        self.window = window  # Sekunden
        self._buckets: dict[str, deque] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self.window

        with self._lock:
            bucket = self._buckets[key]

            # Alte Einträge entfernen
            while bucket and bucket[0] < cutoff:
                bucket.popleft()

            if len(bucket) >= self.max_requests:
                return False

            bucket.append(now)
            return True

    def remaining(self, key: str) -> int:
        now = time.monotonic()
        cutoff = now - self.window
        with self._lock:
            bucket = self._buckets[key]
            active = sum(1 for t in bucket if t >= cutoff)
            return max(0, self.max_requests - active)
