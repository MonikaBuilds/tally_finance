"""
Deterministic, collision-free cache key generation.
Guarantees tenant, company, report, and parameter isolation.
"""

import hashlib
import json
import re
from datetime import date, datetime
from typing import Any, Optional

from app.cache.config import cache_settings


def _json_default(obj: Any) -> str:
    """Serialize dates and other non-standard types deterministically."""
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    return str(obj)


def clean_segment(text: Optional[str], default: str = "_") -> str:
    """Normalize a string segment for use in a Redis key."""
    if not text:
        return default
    # Replace colons, spaces, and non-alphanumeric chars with underscore
    normalized = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", text.strip().casefold())
    # Collapse multiple underscores
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized or default


def _isolated_segment(text: Optional[str], default: str) -> str:
    """
    A readable segment plus a short hash of the exact original text.

    clean_segment() alone maps different names to one key ("Reon (India)"
    and "Reon India" both become "reon_india"), which would hand one
    company's cached report to another. The hash keeps them apart; the
    original is only lower-cased, the way names are compared elsewhere.
    """
    if not text or not text.strip():
        return default

    digest = hashlib.sha256(
        text.strip().casefold().encode("utf-8")
    ).hexdigest()[:8]

    return f"{clean_segment(text, default)}~{digest}"


def hash_params(params: Optional[dict[str, Any]]) -> str:
    """
    Generate a deterministic SHA256 hex digest for request parameters.
    Empty or None params return 'default'.
    """
    if not params:
        return "default"

    # Filter out None values to treat None consistently
    cleaned = {
        str(k): v
        for k, v in params.items()
        if v is not None
    }
    if not cleaned:
        return "default"

    canonical_json = json.dumps(
        cleaned,
        sort_keys=True,
        default=_json_default,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    return digest[:16]


def build_cache_key(
    report_name: str,
    company_name: Optional[str] = None,
    org_id: Optional[str] = None,
    params: Optional[dict[str, Any]] = None,
    prefix: Optional[str] = None,
) -> str:
    """
    Build a deterministic, fully isolated Redis cache key.
    Format: {prefix}:{tenant_or_org}:{company}:{report}:{params_hash}
    """
    key_prefix = prefix or cache_settings.REDIS_CACHE_KEY_PREFIX
    clean_org = _isolated_segment(org_id, default="default")
    clean_company = _isolated_segment(company_name, default="_all_")
    clean_report = clean_segment(report_name, default="unknown")
    param_hash = hash_params(params)

    return f"{key_prefix}:{clean_org}:{clean_company}:{clean_report}:{param_hash}"


def build_lock_key(cache_key: str) -> str:
    """Generate in-flight lock key corresponding to a cache key."""
    return f"lock:{cache_key}"
