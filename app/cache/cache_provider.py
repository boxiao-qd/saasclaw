"""Cache provider -- Redis with MySQL fallback."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.config import settings

log = logging.getLogger(__name__)


class CacheProvider:
    """Redis async client with graceful MySQL fallback.

    - Read: Redis first → None if unavailable → caller should fallback to DB
    - Write: Redis if available → skip if unavailable (no blocking)
    - Health: lazy connection with 2s timeout, auto-retry on next access
    """

    def __init__(self, redis_url: str = "", session_factory=None, employee_id: int = 0):
        self._redis_url = redis_url or settings.redis_url
        self._session_factory = session_factory
        self._employee_id = employee_id
        self._redis = None
        self._available: bool | None = None  # None = not checked yet

    async def _ensure_redis(self):
        if self._available is False:
            return None
        if self._redis is not None:
            return self._redis
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            await self._redis.ping()
            self._available = True
            log.info("Redis cache connected")
        except Exception as e:
            log.warning(f"Redis unavailable, fallback to direct DB queries: {e}")
            self._available = False
            self._redis = None
        return self._redis

    def _prefixed_key(self, key: str) -> str:
        prefix = str(self._employee_id) if self._employee_id else "shared"
        return f"bx-sa:{prefix}:{key}"

    async def get(self, key: str) -> Any | None:
        redis_conn = await self._ensure_redis()
        if redis_conn:
            try:
                value = await redis_conn.get(self._prefixed_key(key))
                if value:
                    return json.loads(value)
            except Exception:
                pass  # degraded: return None, caller fallbacks to DB
        return None

    async def set(self, key: str, value: Any, ttl: int = 300) -> None:
        redis_conn = await self._ensure_redis()
        if redis_conn:
            try:
                await redis_conn.setex(self._prefixed_key(key), ttl, json.dumps(value, ensure_ascii=False))
            except Exception:
                pass  # write failure does not block

    async def delete(self, key: str) -> None:
        redis_conn = await self._ensure_redis()
        if redis_conn:
            try:
                await redis_conn.delete(self._prefixed_key(key))
            except Exception:
                pass

    async def clear_pattern(self, pattern: str) -> int:
        redis_conn = await self._ensure_redis()
        if not redis_conn:
            return 0
        try:
            keys = []
            async for k in redis_conn.scan_iter(match=pattern):
                keys.append(k)
            if keys:
                return await redis_conn.delete(*keys)
            return 0
        except Exception:
            return 0

    async def health_check(self) -> bool:
        redis_conn = await self._ensure_redis()
        if redis_conn:
            try:
                return await redis_conn.ping()
            except Exception:
                self._available = False
                return False
        return False


def create_cache_provider(session_factory=None, employee_id: int = 0) -> CacheProvider:
    return CacheProvider(
        redis_url=settings.redis_url,
        session_factory=session_factory,
        employee_id=employee_id,
    )