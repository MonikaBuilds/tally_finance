import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request, status
from starlette.concurrency import run_in_threadpool

from app.security.config import get_auth_settings


@dataclass(frozen=True)
class UserContext:
    user_id: str
    allowed_companies: tuple[str, ...]
    organization_id: str = "default"


# Every authenticated request re-checks the account against MySQL so that a
# deactivated user, or a user whose company access was removed, loses
# access at once instead of when the 60-minute token expires. The lookup is
# one query, cached briefly per user and cleared on every account change.
LIVE_USER_CHECK = True

USER_STATE_TTL_SECONDS = float(
    os.getenv("AUTH_USER_STATE_TTL_SECONDS", "15") or 15
)

_user_state_cache: dict[str, tuple[float, object]] = {}


def invalidate_user_state(user_id: str | None = None) -> None:
    """Forget cached account state (one user, or everyone)."""
    if user_id is None:
        _user_state_cache.clear()
    else:
        _user_state_cache.pop(str(user_id), None)


def _fetch_user_state(user_id: str):
    from app.security.user_store import get_user_access_state

    return get_user_access_state(user_id)


async def _get_user_state(user_id: str):
    now = time.monotonic()
    cached = _user_state_cache.get(user_id)

    if cached and cached[0] > now:
        return cached[1]

    # MySQL calls are blocking; keep them off the event loop.
    state = await run_in_threadpool(_fetch_user_state, user_id)

    if len(_user_state_cache) > 10_000:
        _user_state_cache.clear()

    _user_state_cache[user_id] = (now + USER_STATE_TTL_SECONDS, state)
    return state


def _auth_enabled() -> bool:
    """
    Return whether authentication enforcement is enabled.
    """
    settings = get_auth_settings()

    return settings.auth_enabled


def is_secure_cookie(request: Request | None, default_secure: bool) -> bool:
    """
    Determine whether cookies should carry the Secure flag.
    Returns True if explicitly enabled in configuration or if the incoming
    request arrived over HTTPS (including TLS-terminating reverse proxies).
    """
    if default_secure:
        return True
    if request is not None:
        forwarded_proto = request.headers.get("x-forwarded-proto", "").lower()
        if forwarded_proto == "https" or request.url.scheme == "https":
            return True
    return False


def create_access_token(
    *,
    user_id: str,
    companies: tuple[str, ...],
    organization_id: str = "default",
) -> str:
    """
    Create a signed JWT access token for an authenticated user.

    The token stores:
    - user identity
    - companies the user is allowed to access
    - organization scope
    - token creation time
    - token expiration time

    Passwords and financial data must never be stored in the token.
    """

    settings = get_auth_settings()

    now = datetime.now(timezone.utc)

    expires_at = now + timedelta(
        minutes=settings.jwt_expire_minutes
    )

    payload = {
        "sub": user_id,
        "companies": list(companies),
        "org": organization_id,
        "iat": now,
        "exp": expires_at,
    }

    return jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def _decode_token(token: str) -> dict:
    """
    Verify and decode an incoming JWT access token.
    """

    try:
        settings = get_auth_settings()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication configuration error.",
        ) from exc

    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[
                settings.jwt_algorithm,
            ],
            leeway=10,
        )

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired.",
        )

    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
        )


async def get_current_user(
    request: Request,
) -> UserContext:
    """
    Resolve the authenticated user from the HttpOnly
    access-token cookie.

    When authentication is explicitly disabled, a
    development context is returned for local testing only.
    """

    settings = get_auth_settings()

    # Development-only fallback.
    # Production must keep authentication enabled.
    if not settings.auth_enabled:
        return UserContext(
            user_id="development-user",
            allowed_companies=("*",),
        )

    access_token = request.cookies.get(
        settings.access_token_cookie_name
    )

    if not access_token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            access_token = auth_header[7:].strip()

    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    payload = _decode_token(access_token)

    user_id = payload.get("sub")
    companies = payload.get("companies", [])

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token does not contain a valid user identity.",
        )

    if not isinstance(companies, list):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid company permissions in token.",
        )

    org = payload.get("org") or "default"

    if not LIVE_USER_CHECK:
        return UserContext(
            user_id=str(user_id),
            allowed_companies=tuple(
                str(company)
                for company in companies
            ),
            organization_id=str(org),
        )

    state = await _get_user_state(str(user_id))

    if state is None or not state.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is unavailable.",
        )

    # MySQL is authoritative for company access; the token's list may be
    # out of date after an administrator changed it.
    return UserContext(
        user_id=str(user_id),
        allowed_companies=tuple(state.companies),
        organization_id=str(state.organization_id or org),
    )


async def get_authorized_company(
    company_name: str | None = None,
    current_user: UserContext = Depends(
        get_current_user
    ),
) -> str | None:
    """
    Resolve the requested company and verify that the
    logged-in user is allowed to access it.

    This dependency is shared by dashboard and report
    routes so company-level authorization is enforced
    consistently.
    """

    return authorize_company(
        user=current_user,
        requested_company=company_name,
    )


def authorize_company(
    user: UserContext,
    requested_company: str | None,
) -> str | None:
    """
    Verify that the authenticated user is allowed to
    access the requested Tally company.
    """

    allowed = user.allowed_companies

    # Development/admin-style wildcard.
    if "*" in allowed:
        return requested_company

    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to any company.",
        )

    # If the user only has one company,
    # select it automatically.
    if requested_company is None:
        if len(allowed) == 1:
            return allowed[0]

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please select a company.",
        )

    requested_key = requested_company.casefold()

    for company in allowed:
        if company.casefold() == requested_key:
            return company

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You are not authorized to access this company.",
    )