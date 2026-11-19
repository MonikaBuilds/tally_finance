import logging
import os
import threading
from pathlib import Path

from dotenv import load_dotenv
import mysql.connector
from mysql.connector import errors as mysql_errors
from mysql.connector import pooling

_BACKEND_ENV = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_BACKEND_ENV)
load_dotenv()

logger = logging.getLogger(__name__)

_pool: pooling.MySQLConnectionPool | None = None
_pool_lock = threading.Lock()
_pool_failed = False


def _connection_settings() -> dict:
    password = os.getenv("DB_PASSWORD")

    # No built-in fallback password: a missing setting must fail loudly
    # instead of silently trying a password that is published in Git.
    if password is None:
        raise RuntimeError(
            "Required environment variable 'DB_PASSWORD' is not configured."
        )

    return {
        "host": os.getenv("DB_HOST", "127.0.0.1") or "127.0.0.1",
        "port": int(os.getenv("DB_PORT", "3306")),
        "user": os.getenv("DB_USER", "tally_app"),
        "password": password,
        "database": os.getenv("DB_NAME", "tally_financial_intelligence"),
        "time_zone": "+00:00",
    }


def _get_pool() -> pooling.MySQLConnectionPool | None:
    """
    One shared pool per process. Opening a fresh MySQL connection for every
    permission check was the main per-request database cost.
    """
    global _pool, _pool_failed

    if _pool is not None or _pool_failed:
        return _pool

    with _pool_lock:
        if _pool is None and not _pool_failed:
            try:
                _pool = pooling.MySQLConnectionPool(
                    pool_name="tfi_pool",
                    pool_size=max(1, min(32, int(os.getenv("DB_POOL_SIZE", "10")))),
                    pool_reset_session=True,
                    **_connection_settings(),
                )
            except mysql_errors.Error:
                # Fall back to direct connections; never block startup on the pool.
                _pool_failed = True
                logger.warning("MySQL pool unavailable; using direct connections", exc_info=True)

    return _pool


def get_connection():
    """
    Return a MySQL connection. Calling .close() on it returns it to the pool.

    When every pooled connection is busy, a direct connection is opened
    instead of failing the request.
    """
    pool = _get_pool()

    if pool is not None:
        try:
            return pool.get_connection()
        except mysql_errors.PoolError:
            logger.debug("MySQL pool exhausted; opening a direct connection")

    return mysql.connector.connect(**_connection_settings())
