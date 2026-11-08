import time
from collections import defaultdict

from app.shared.errors import RateLimitExceededError


class RateLimiter:
    """Sliding-window rate limiter keyed by scope + subject/tenant identifier."""

    def __init__(self) -> None:
        self._buckets: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str, limit: int, window_seconds: int = 60) -> None:
        now = time.monotonic()
        cutoff = now - window_seconds
        timestamps = self._buckets[key]
        while timestamps and timestamps[0] < cutoff:
            timestamps.pop(0)
        if len(timestamps) >= limit:
            raise RateLimitExceededError(
                f"Rate limit exceeded ({limit} requests per {window_seconds}s). Please retry shortly."
            )
        timestamps.append(now)

    def reset(self) -> None:
        self._buckets.clear()


rate_limiter = RateLimiter()
