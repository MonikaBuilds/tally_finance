"""
TallyCacheManager: High-performance, freshness-aware caching manager.
Implements dual-TTL caching, single-flight stampede prevention,
fail-open Redis resilience, and connectivity-only stale failover.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Generic, Optional, TypeVar

from redis.exceptions import RedisError

from app.cache.client import get_redis_client
from app.cache.config import cache_settings
from app.cache.errors import is_tally_connectivity_error

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CacheState(str, Enum):
    MISS = "miss"
    FRESH = "fresh"
    STALE = "stale"


@dataclass
class CacheResult(Generic[T]):
    """Standard container for cached or fresh Tally responses with provenance."""
    data: T
    source: str  # "tally" | "cache" | "stale_cache"
    cached_at: Optional[str] = None  # ISO 8601 string
    is_stale: bool = False

    def to_dict(self) -> dict[str, Any]:
        result = {
            "source": self.source,
            "data": self.data,
            "is_stale": self.is_stale,
        }
        if self.cached_at:
            result["cached_at"] = self.cached_at
        return result


class TallyCacheManager:
    """
    Manages caching of authoritative Tally data in Redis.
    Preserves exact Tally responses without modifying financial values.
    """

    _global_outage_until: float = 0.0

    @classmethod
    def mark_tally_offline(cls, cooldown_seconds: float | None = None) -> None:
        cooldown = (
            cooldown_seconds
            if cooldown_seconds is not None
            else max(0, cache_settings.TALLY_UNAVAILABLE_COOLDOWN_SECONDS)
        )
        cls._global_outage_until = max(cls._global_outage_until, time.monotonic() + cooldown)

    @classmethod
    def mark_tally_online(cls) -> None:
        cls._global_outage_until = 0.0

    @classmethod
    def is_tally_known_offline(cls) -> bool:
        if cls._global_outage_until <= time.monotonic():
            cls._global_outage_until = 0.0
            return False
        return True

    def __init__(self):
        # Per-key in-flight locks to prevent cache stampedes
        self._locks: dict[str, asyncio.Lock] = {}
        self._locks_mutex = asyncio.Lock()
        # Avoid repeating a known-failing Tally request for a stale key.
        self._connectivity_failures: dict[str, float] = {}

    async def _get_lock(self, key: str) -> asyncio.Lock:
        """Get or create an asyncio.Lock for a specific cache key."""
        async with self._locks_mutex:
            if key not in self._locks:
                self._locks[key] = asyncio.Lock()
            return self._locks[key]

    async def _cleanup_lock(self, key: str) -> None:
        """Remove lock entry if no coroutines are waiting."""
        async with self._locks_mutex:
            lock = self._locks.get(key)
            if lock and not lock.locked():
                self._locks.pop(key, None)

    async def get_entry(self, key: str) -> tuple[Optional[Any], CacheState, Optional[str]]:
        """
        Retrieve entry from Redis and evaluate freshness.
        Returns: (data, state, cached_at_iso)
        """
        redis = await get_redis_client()
        if redis is None:
            return None, CacheState.MISS, None

        try:
            raw_payload = await redis.get(key)
            if not raw_payload:
                return None, CacheState.MISS, None

            entry = json.loads(raw_payload)
            data = entry.get("data")
            cached_at = entry.get("cached_at")
            fresh_until = entry.get("fresh_until", 0.0)

            current_ts = time.time()
            if current_ts <= fresh_until:
                return data, CacheState.FRESH, cached_at
            else:
                return data, CacheState.STALE, cached_at

        except RedisError as redis_err:
            logger.warning("Redis read error for key %s: %s", key, redis_err)
            return None, CacheState.MISS, None
        except Exception as parse_err:
            logger.warning("Corrupt cache payload for key %s: %s", key, parse_err)
            return None, CacheState.MISS, None

    async def set_entry(
        self,
        key: str,
        data: Any,
        fresh_ttl: Optional[int] = None,
        retention_ttl: Optional[int] = None,
        metadata: Optional[dict[str, Any]] = None,
        cached_at: Optional[str] = None,
        cached_ts: Optional[float] = None,
    ) -> bool:
        """
        Store authoritative data in Redis with dual-TTL metadata.
        Redis key expires after retention_ttl; freshness is tracked in payload.
        """
        redis = await get_redis_client()
        if redis is None:
            return False

        fresh_seconds = fresh_ttl if fresh_ttl is not None else cache_settings.REDIS_CACHE_DEFAULT_FRESH_TTL
        retention_seconds = retention_ttl if retention_ttl is not None else cache_settings.REDIS_CACHE_STALE_RETENTION_TTL

        now = datetime.now(timezone.utc)
        ts = cached_ts if cached_ts is not None else now.timestamp()
        iso = cached_at if cached_at is not None else now.isoformat()

        entry = {
            "version": 1,
            "cached_at": iso,
            "fresh_until": ts + fresh_seconds,
            "metadata": metadata or {},
            "data": data,
        }

        try:
            payload = json.dumps(entry, default=str)
            await redis.set(key, payload, ex=retention_seconds)
            return True
        except RedisError as redis_err:
            logger.warning("Redis write error for key %s: %s", key, redis_err)
            return False
        except Exception as exc:
            logger.warning("Failed serializing cache entry for %s: %s", key, exc)
            return False

    async def get_or_fetch(
        self,
        cache_key: str,
        fetcher: Callable[[], Awaitable[T]],
        fresh_ttl: Optional[int] = None,
        stale_retention_ttl: Optional[int] = None,
        force_refresh: bool = False,
        metadata: Optional[dict[str, Any]] = None,
    ) -> CacheResult[T]:
        """
        Get fresh data from cache, or fetch from Tally with single-flight stampede
        prevention and connectivity-failure stale fallback.
        """
        # 1. If cache enabled and not forcing refresh, check cache first
        if cache_settings.REDIS_CACHE_ENABLED and not force_refresh:
            cached_data, state, cached_at = await self.get_entry(cache_key)
            if state == CacheState.FRESH and cached_data is not None:
                return CacheResult(
                    data=cached_data,
                    source="cache",
                    cached_at=cached_at,
                    is_stale=False,
                )
            # Fast failover: if Tally is already known to be offline and we have retained data,
            # serve stale immediately (< 2ms) without waiting for a TCP connect timeout.
            if cached_data is not None and self.is_tally_known_offline():
                logger.debug(
                    "Tally is known offline (circuit open); fast-serving retained stale data for key %s",
                    cache_key,
                )
                return CacheResult(
                    data=cached_data,
                    source="stale_cache",
                    cached_at=cached_at,
                    is_stale=True,
                )
        else:
            if force_refresh:
                self.mark_tally_online()
            cached_data, state, cached_at = None, CacheState.MISS, None

        # 2. Acquire per-key in-flight lock to prevent cache stampedes
        key_lock = await self._get_lock(cache_key)
        try:
            async with key_lock:
                # Double-check cache in case a concurrent request already fetched fresh data
                if cache_settings.REDIS_CACHE_ENABLED and not force_refresh:
                    recheck_data, recheck_state, recheck_at = await self.get_entry(cache_key)
                    if recheck_state == CacheState.FRESH and recheck_data is not None:
                        return CacheResult(
                            data=recheck_data,
                            source="cache",
                            cached_at=recheck_at,
                            is_stale=False,
                        )
                    # Keep any stale data found for failover
                    if recheck_data is not None:
                        cached_data = recheck_data
                        cached_at = recheck_at

                # If we didn't have cached data yet, check if there's any retained stale data
                if cached_data is None and cache_settings.REDIS_CACHE_ENABLED:
                    retained_data, _, retained_at = await self.get_entry(cache_key)
                    if retained_data is not None:
                        cached_data = retained_data
                        cached_at = retained_at

                now_monotonic = time.monotonic()
                failure_until = self._connectivity_failures.get(cache_key, 0)
                if force_refresh:
                    self._connectivity_failures.pop(cache_key, None)
                elif failure_until > now_monotonic:
                    if cached_data is not None:
                        logger.debug(
                            "Serving retained stale data during Tally retry cooldown for key %s",
                            cache_key,
                        )
                        return CacheResult(
                            data=cached_data,
                            source="stale_cache",
                            cached_at=cached_at,
                            is_stale=True,
                        )
                elif failure_until:
                    self._connectivity_failures.pop(cache_key, None)

                # 3. Fetch from authoritative Tally source
                try:
                    fresh_data = await fetcher()

                    now = datetime.now(timezone.utc)
                    now_iso = now.isoformat()
                    now_ts = now.timestamp()

                    # Cache successful exact response
                    if cache_settings.REDIS_CACHE_ENABLED:
                        await self.set_entry(
                            key=cache_key,
                            data=fresh_data,
                            fresh_ttl=fresh_ttl,
                            retention_ttl=stale_retention_ttl,
                            metadata=metadata,
                            cached_at=now_iso,
                            cached_ts=now_ts,
                        )

                    self._connectivity_failures.pop(cache_key, None)

                    return CacheResult(
                        data=fresh_data,
                        source="tally",
                        cached_at=now_iso,
                        is_stale=False,
                    )

                except Exception as fetch_exc:
                    # 4. Check if error is an eligible infrastructure/connectivity failure
                    if is_tally_connectivity_error(fetch_exc):
                        cooldown = max(
                            0,
                            cache_settings.TALLY_UNAVAILABLE_COOLDOWN_SECONDS,
                        )
                        self.mark_tally_offline(cooldown)
                        if cooldown:
                            self._connectivity_failures[cache_key] = (
                                time.monotonic() + cooldown
                            )

                    if is_tally_connectivity_error(fetch_exc) and cached_data is not None:
                        logger.warning(
                            "Tally server connectivity failure (%s: %s). Serving retained stale data for key %s (cached at %s).",
                            type(fetch_exc).__name__,
                            fetch_exc,
                            cache_key,
                            cached_at,
                        )
                        return CacheResult(
                            data=cached_data,
                            source="stale_cache",
                            cached_at=cached_at,
                            is_stale=True,
                        )

                    # Non-connectivity errors (parser bugs, XML errors, LINEERROR, etc.)
                    # or no stale data available -> propagate exception unmodified
                    logger.debug(
                        "Propagating Tally exception for %s (%s: %s)",
                        cache_key,
                        type(fetch_exc).__name__,
                        fetch_exc,
                    )
                    raise

        finally:
            await self._cleanup_lock(cache_key)

    async def invalidate(self, cache_key: str) -> bool:
        """Invalidate a specific cache key."""
        redis = await get_redis_client()
        if redis is None:
            return False
        try:
            await redis.delete(cache_key)
            return True
        except RedisError as exc:
            logger.warning("Error deleting cache key %s: %s", cache_key, exc)
            return False

    async def invalidate_prefix(self, prefix: str) -> int:
        """Invalidate all keys matching a prefix pattern."""
        redis = await get_redis_client()
        if redis is None:
            return 0
        try:
            pattern = f"{prefix}*"
            keys = await redis.keys(pattern)
            if keys:
                return await redis.delete(*keys)
            return 0
        except RedisError as exc:
            logger.warning("Error invalidating prefix %s: %s", prefix, exc)
            return 0


# Shared singleton instance
cache_manager = TallyCacheManager()
