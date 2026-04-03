from __future__ import annotations

import logging
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock
from time import monotonic, time
from uuid import uuid4

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.config import settings

_LOGGER = logging.getLogger(__name__)

_WINDOWS: dict[tuple[str, str], deque[float]] = defaultdict(deque)
_LOCK = Lock()
_REDIS_CLIENT: Redis | None = None

_SLIDING_WINDOW_SCRIPT = """
local key = KEYS[1]
local now_ms = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
local cutoff = now_ms - window_ms

redis.call("ZREMRANGEBYSCORE", key, 0, cutoff)

local count = redis.call("ZCARD", key)
if count >= limit then
  local oldest = redis.call("ZRANGE", key, 0, 0, "WITHSCORES")
  local retry_after = 1
  if oldest[2] then
    retry_after = math.max(1, math.ceil((window_ms - (now_ms - tonumber(oldest[2]))) / 1000))
  end
  return {0, retry_after}
end

redis.call("ZADD", key, now_ms, member)
redis.call("EXPIRE", key, math.max(1, math.ceil(window_ms / 1000)))
return {1, 0}
"""


@dataclass
class RateLimitExceededError(Exception):
    detail: str
    retry_after: int


def _normalize_key(value: str | None) -> str:
    text = (value or "").strip()
    return text or "unknown"


def _redis_bucket_key(scope: str, key: str | None) -> str:
    normalized_key = _normalize_key(key)
    return f"{settings.rate_limit_key_prefix}:{scope}:{normalized_key}"


async def _get_redis_client() -> Redis | None:
    if not settings.rate_limit_redis_url:
        return None

    global _REDIS_CLIENT
    if _REDIS_CLIENT is None:
        _REDIS_CLIENT = Redis.from_url(
            settings.rate_limit_redis_url,
            encoding="utf-8",
            decode_responses=True,
            health_check_interval=30,
        )
    return _REDIS_CLIENT


def _assert_within_memory_limit(
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


async def _assert_within_redis_limit(
    scope: str,
    key: str | None,
    *,
    limit: int,
    window_seconds: int,
    detail: str,
) -> bool:
    client = await _get_redis_client()
    if client is None:
        return False

    now_ms = int(time() * 1000)
    bucket_key = _redis_bucket_key(scope, key)
    member = f"{now_ms}:{uuid4()}"

    try:
        allowed, retry_after = await client.eval(
            _SLIDING_WINDOW_SCRIPT,
            1,
            bucket_key,
            now_ms,
            int(window_seconds * 1000),
            limit,
            member,
        )
    except RedisError:
        _LOGGER.warning("Falling back to in-memory rate limit for scope=%s key=%s", scope, _normalize_key(key))
        return False

    if int(allowed) == 0:
        raise RateLimitExceededError(detail=detail, retry_after=max(1, int(retry_after)))
    return True


async def assert_within_limit(
    scope: str,
    key: str | None,
    *,
    limit: int,
    window_seconds: int,
    detail: str,
) -> None:
    if limit <= 0 or window_seconds <= 0:
        return
    if await _assert_within_redis_limit(
        scope,
        key,
        limit=limit,
        window_seconds=window_seconds,
        detail=detail,
    ):
        return
    _assert_within_memory_limit(
        scope,
        key,
        limit=limit,
        window_seconds=window_seconds,
        detail=detail,
    )


def reset_state_for_tests() -> None:
    global _REDIS_CLIENT
    _WINDOWS.clear()
    _REDIS_CLIENT = None
