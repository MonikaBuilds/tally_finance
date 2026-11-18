"""
Structured Session Store for Chatbot Conversational Context.

Tracks the user's active financial session state:
- last_tool
- last_intent
- last_data
- last_period (from_date, to_date)
- last_entity (ledger name, stock item name, etc.)
- last_answer
"""

from datetime import datetime, timezone
import json
import logging
import time
from typing import Any, Optional

from app.cache.manager import cache_manager

logger = logging.getLogger(__name__)

SESSION_TTL_SECONDS = 3600  # 1 hour session TTL

_local_session_memory: dict[str, dict[str, Any]] = {}


def build_session_key(
    user_id: str | None,
    company: str | None,
    session_id: str | None = None,
) -> str:
    clean_user = (user_id or "anonymous").strip()
    clean_company = (company or "default").strip().lower()
    clean_sid = (session_id or "default").strip()
    return f"chat:session:{clean_user}:{clean_company}:{clean_sid}"


async def get_session_state(
    user_id: str | None,
    company: str | None,
    session_id: str | None = None,
) -> dict[str, Any] | None:
    key = build_session_key(user_id, company, session_id)
    try:
        data, state, _ = await cache_manager.get_entry(key)
        if data and isinstance(data, dict):
            return data
    except Exception as exc:
        logger.debug("Error getting session from cache_manager: %s", exc)

    # Local fallback
    entry = _local_session_memory.get(key)
    if entry:
        if time.time() - entry.get("_timestamp", 0) < SESSION_TTL_SECONDS:
            return entry.get("data")
        else:
            _local_session_memory.pop(key, None)
    return None


async def save_session_state(
    user_id: str | None,
    company: str | None,
    state_data: dict[str, Any],
    session_id: str | None = None,
) -> None:
    key = build_session_key(user_id, company, session_id)
    try:
        await cache_manager.set_entry(
            key=key,
            data=state_data,
            fresh_ttl=SESSION_TTL_SECONDS,
            retention_ttl=SESSION_TTL_SECONDS,
        )
    except Exception as exc:
        logger.debug("Error saving session to cache_manager: %s", exc)

    # Local fallback
    _local_session_memory[key] = {
        "data": state_data,
        "_timestamp": time.time(),
    }
