import time
from collections import defaultdict, deque


class InMemoryRateLimiter:
    def __init__(self, max_events: int, window_seconds: int):
        if max_events <= 0:
            raise ValueError("max_events must be positive")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")

        self.max_events = max_events
        self.window_seconds = window_seconds
        self._events = defaultdict(deque)

    def allow(self, key: str | int) -> bool:
        now = time.monotonic()
        bucket = self._events[str(key)]
        cutoff = now - self.window_seconds

        while bucket and bucket[0] <= cutoff:
            bucket.popleft()

        if len(bucket) >= self.max_events:
            return False

        bucket.append(now)
        return True

    def reset(self, key: str | int) -> None:
        self._events.pop(str(key), None)
