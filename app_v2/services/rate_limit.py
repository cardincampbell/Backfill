from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock
from time import monotonic


_WINDOWS: dict[tuple[str, str], deque[float]] = defaultdict(deque)
_LOCK = Lock()


@dataclass
class RateLimitExceededError(Exception):
    detail: str
    retry_after: int


def _normalize_key(value: str | None) -> str:
    text = (value or "").strip()
    return text or "unknown"


def assert_within_limit(
    scope: str,
    key: str | None,
    *,
    limit: int,
    window_seconds: int,
    detail: str,
) -> None:
    bucket = (scope, _normalize_key(key))
    now = monotonic()
    cutoff = now - window_seconds
    with _LOCK:
        timestamps = _WINDOWS[bucket]
        while timestamps and timestamps[0] <= cutoff:
            timestamps.popleft()
        if len(timestamps) >= limit:
            retry_after = max(1, int(window_seconds - (now - timestamps[0])))
            raise RateLimitExceededError(detail=detail, retry_after=retry_after)
        timestamps.append(now)
