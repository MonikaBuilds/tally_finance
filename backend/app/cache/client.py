"""
Resilient asynchronous Redis client connection management.
Fail-open: Redis failures will never crash live Tally requests.
"""

import asyncio
import logging
import time
from typing import Optional

import redis.asyncio as aioredis
from redis.exceptions import AuthenticationError, RedisError

from app.cache.config import cache_settings

logger = logging.getLogger(__name__)

_redis_client: Optional[aioredis.Redis] = None
_redis_available: bool = False
_redis_loop: Optional[asyncio.AbstractEventLoop] = None
_redis_unavailable_until: float = 0.0


def mark_redis_unavailable(cooldown_seconds: Optional[float] = None) -> None:
    """
    Mark Redis connection as down and activate cooldown.
    During cooldown, get_redis_client() immediately returns None (0ms fail-open)
    without repeatedly blocking API requests on socket timeouts.
    """
    global _redis_client, _redis_available, _redis_loop, _redis_unavailable_until

    cooldown = (
        cooldown_seconds
        if cooldown_seconds is not None
        else cache_settings.REDIS_UNAVAILABLE_COOLDOWN_SECONDS
    )
    _redis_unavailable_until = time.monotonic() + max(1.0, cooldown)
    _redis_available = False
    _redis_client = None
    _redis_loop = None


def mark_redis_available(client: aioredis.Redis) -> None:
    """Mark Redis connection as healthy and clear any active cooldown."""
    global _redis_client, _redis_available, _redis_loop, _redis_unavailable_until

    _redis_client = client
    _redis_available = True
    _redis_unavailable_until = 0.0
    try:
        _redis_loop = asyncio.get_running_loop()
    except RuntimeError:
        _redis_loop = None


def set_redis_client_override(
    client: Optional[aioredis.Redis],
) -> None:
    """
    Override the Redis client for tests or controlled application setup.

    Passing None clears the override.
    """
    global _redis_client, _redis_available, _redis_loop, _redis_unavailable_until

    _redis_client = client
    _redis_available = client is not None
    _redis_unavailable_until = 0.0
    try:
        _redis_loop = asyncio.get_running_loop() if client is not None else None
    except RuntimeError:
        _redis_loop = None


async def init_redis_client() -> Optional[aioredis.Redis]:
    """
    Initialize and test the Redis client connection.
    Returns the client instance if reachable, or None if unavailable.
    """
    global _redis_client, _redis_available, _redis_loop, _redis_unavailable_until

    if not cache_settings.REDIS_CACHE_ENABLED:
        logger.info("Redis cache is explicitly disabled in configuration.")
        _redis_available = False
        _redis_loop = None
        return None

    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if _redis_client is not None:
        if _redis_loop is not None and _redis_loop is not current_loop:
            _redis_client = None
            _redis_available = False
            _redis_loop = None
        else:
            try:
                await _redis_client.ping()
                mark_redis_available(_redis_client)
                return _redis_client
            except Exception:
                mark_redis_unavailable()

    conn_kwargs = {
        "socket_connect_timeout": cache_settings.REDIS_CONNECT_TIMEOUT,
        "socket_timeout": cache_settings.REDIS_CONNECT_TIMEOUT,
        "protocol": cache_settings.REDIS_PROTOCOL,
        "decode_responses": True,
    }
    raw_password = (cache_settings.REDIS_PASSWORD or "").strip()
    if raw_password:
        conn_kwargs["password"] = raw_password

    effective_url = cache_settings.effective_redis_url

    # Connect with configured parameters
    try:
        client = aioredis.from_url(
            effective_url,
            **conn_kwargs,
        )
        await client.ping()
        mark_redis_available(client)
        logger.info("Redis cache connected successfully (protocol=%d).", cache_settings.REDIS_PROTOCOL)
        return _redis_client

    except AuthenticationError as auth_err:
        if "Client sent AUTH, but no password is set" in str(auth_err):
            # Redis server requires no password, retry without auth
            logger.info("Redis server does not require password. Connecting without AUTH.")
            try:
                conn_kwargs.pop("password", None)
                client = aioredis.from_url(
                    effective_url,
                    **conn_kwargs,
                )
                await client.ping()
                mark_redis_available(client)
                logger.info("Redis cache connected successfully without password.")
                return _redis_client
            except Exception as retry_err:
                logger.warning("Failed connecting to Redis without password: %s", retry_err)
        else:
            logger.warning("Redis authentication failed: %s", auth_err)

    except Exception as exc:
        logger.warning(
            "Redis cache unavailable (%s: %s). Operating in fail-open mode directly with Tally.",
            type(exc).__name__,
            exc,
        )

    mark_redis_unavailable()
    return None


async def get_redis_client() -> Optional[aioredis.Redis]:
    """
    Get the active Redis client, attempting connection if not yet connected.
    Returns None if Redis is unavailable (fail-open) without blocking requests.
    """
    global _redis_client, _redis_available, _redis_loop, _redis_unavailable_until

    if not cache_settings.REDIS_CACHE_ENABLED:
        return None

    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if _redis_client is not None and _redis_available:
        if _redis_loop is not None and _redis_loop is not current_loop:
            _redis_client = None
            _redis_available = False
            _redis_loop = None
        else:
            return _redis_client

    # If Redis is in cooldown, fast-fail without blocking for socket timeouts
    if time.monotonic() < _redis_unavailable_until:
        return None

    return await init_redis_client()


async def close_redis_client() -> None:
    """
    Gracefully close the Redis client pool on application shutdown.
    """
    global _redis_client, _redis_available, _redis_loop, _redis_unavailable_until

    if _redis_client is not None:
        try:
            await _redis_client.aclose()
            logger.info("Redis client closed cleanly.")
        except Exception as exc:
            logger.warning("Error closing Redis client: %s", exc)
        finally:
            _redis_client = None
            _redis_available = False
            _redis_loop = None


def is_redis_available() -> bool:
    """Check if Redis connection is currently healthy."""
    return _redis_available and cache_settings.REDIS_CACHE_ENABLED
