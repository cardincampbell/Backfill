from __future__ import annotations

from collections import defaultdict, deque
from threading import Lock
from time import monotonic
from typing import Callable

from fastapi import HTTPException, Request

_WINDOWS: dict[tuple[str, str], deque[float]] = defaultdict(deque)
_LOCK = Lock()


def _client_key(request: Request) -> str:
    forwarded_for = (request.headers.get("x-forwarded-for") or "").split(",", 1)[0].strip()
    if forwarded_for:
        return forwarded_for
    client = request.client
    return client.host if client else "unknown"


def limit_by_request_key(
    scope: str,
    *,
    limit: int,
    window_seconds: int,
    key_func: Callable[[Request], str] | None = None,
):
    async def dependency(request: Request) -> None:
        key = (key_func or _client_key)(request)
        bucket = (scope, key)
        now = monotonic()
        cutoff = now - window_seconds
        with _LOCK:
            timestamps = _WINDOWS[bucket]
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            if len(timestamps) >= limit:
                retry_after = max(1, int(window_seconds - (now - timestamps[0])))
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded",
                    headers={"Retry-After": str(retry_after)},
                )
            timestamps.append(now)

    return dependency
