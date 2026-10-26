"""
Public interface for the Redis caching layer.
"""

from app.cache.client import (
    close_redis_client,
    get_redis_client,
    init_redis_client,
    is_redis_available,
    set_redis_client_override,
)
from app.cache.config import CacheSettings, cache_settings
from app.cache.errors import is_tally_connectivity_error
from app.cache.keys import build_cache_key, build_lock_key
from app.cache.manager import (
    CacheResult,
    CacheState,
    TallyCacheManager,
    cache_manager,
)
from app.cache.refresher import (
    TallyBackgroundRefresher,
    start_background_refresher,
    stop_background_refresher,
)

__all__ = [
    "CacheResult",
    "CacheSettings",
    "CacheState",
    "TallyBackgroundRefresher",
    "TallyCacheManager",
    "build_cache_key",
    "build_lock_key",
    "cache_manager",
    "cache_settings",
    "close_redis_client",
    "get_redis_client",
    "init_redis_client",
    "is_redis_available",
    "is_tally_connectivity_error",
    "set_redis_client_override",
    "start_background_refresher",
    "stop_background_refresher",
]
