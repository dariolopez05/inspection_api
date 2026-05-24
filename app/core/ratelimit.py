import time
from threading import Lock


class RateLimiter:
    def __init__(self, limit: int, window: int = 60) -> None:
        self.limit = limit
        self.window = window
        self._hits: dict[str, tuple[float, int]] = {}
        self._lock = Lock()

    def hit(self, key: str) -> tuple[bool, int, int]:
        now = time.monotonic()
        with self._lock:
            start, count = self._hits.get(key, (now, 0))
            if now - start >= self.window:
                start, count = now, 0
            count += 1
            self._hits[key] = (start, count)
        allowed = count <= self.limit
        remaining = max(0, self.limit - count)
        retry_after = max(1, int(self.window - (now - start))) if not allowed else 0
        return allowed, remaining, retry_after
