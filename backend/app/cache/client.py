"""
Resilient asynchronous Redis client connection management.
Fail-open: Redis failures will never crash live Tally requests.
"""

import asyncio
import logging
from typing import Optional

import redis.asyncio as aioredis
from redis.exceptions import AuthenticationError, RedisError

from app.cache.config import cache_settings

logger = logging.getLogger(__name__)

_redis_client: Optional[aioredis.Redis] = None
_redis_available: bool = False
_redis_loop: Optional[asyncio.AbstractEventLoop] = None

def set_redis_client_override(
    client: Optional[aioredis.Redis],
) -> None:
    """
    Override the Redis client for tests or controlled application setup.

    Passing None clears the override.
    """
    global _redis_client, _redis_available, _redis_loop

    _redis_client = client
    _redis_available = client is not None
    try:
        _redis_loop = asyncio.get_running_loop() if client is not None else None
    except RuntimeError:
        _redis_loop = None

async def init_redis_client() -> Optional[aioredis.Redis]:
    """
    Initialize and test the Redis client connection.
    Returns the client instance if reachable, or None if unavailable.
    """
    global _redis_client, _redis_available, _redis_loop

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
                _redis_available = True
                _redis_loop = current_loop
                return _redis_client
            except Exception:
                _redis_available = False
                _redis_client = None
                _redis_loop = None

    conn_kwargs = {
        "socket_connect_timeout": cache_settings.REDIS_CONNECT_TIMEOUT,
        "socket_timeout": cache_settings.REDIS_CONNECT_TIMEOUT,
        "protocol": cache_settings.REDIS_PROTOCOL,
        "decode_responses": True,
    }
    raw_password = (cache_settings.REDIS_PASSWORD or "").strip()
    if raw_password:
        conn_kwargs["password"] = raw_password

    # Connect with configured parameters
    try:
        client = aioredis.from_url(
            cache_settings.REDIS_URL,
            **conn_kwargs,
        )
        await client.ping()
        _redis_client = client
        _redis_available = True
        _redis_loop = current_loop
        logger.info("Redis cache connected successfully (protocol=%d).", cache_settings.REDIS_PROTOCOL)
        return _redis_client

    except AuthenticationError as auth_err:
        if "Client sent AUTH, but no password is set" in str(auth_err):
            # Redis server requires no password, retry without auth
            logger.info("Redis server does not require password. Connecting without AUTH.")
            try:
                conn_kwargs.pop("password", None)
                client = aioredis.from_url(
                    cache_settings.REDIS_URL,
                    **conn_kwargs,
                )
                await client.ping()
                _redis_client = client
                _redis_available = True
                _redis_loop = current_loop
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

    _redis_client = None
    _redis_available = False
    _redis_loop = None
    return None


async def get_redis_client() -> Optional[aioredis.Redis]:
    """
    Get the active Redis client, attempting connection if not yet connected.
    Returns None if Redis is unavailable (fail-open).
    """
    global _redis_client, _redis_available, _redis_loop

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

    return await init_redis_client()


async def close_redis_client() -> None:
    """
    Gracefully close the Redis client pool on application shutdown.
    """
    global _redis_client, _redis_available, _redis_loop

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
