import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


security = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class UserContext:
    user_id: str
    allowed_companies: tuple[str, ...]


def _auth_enabled() -> bool:
    """
    Return whether authentication enforcement is enabled.

    The flag is configurable so local development and automated
    tests can explicitly control authentication behaviour.
    """ 
    return os.getenv("CHAT_AUTH_ENABLED", "false").lower() == "true"


def create_access_token(
    *,
    user_id: str,
    companies: tuple[str, ...],
) -> str:
    """
    Create a signed JWT access token for an authenticated user.

    The token stores:
    - user identity
    - companies the user is allowed to access
    - token creation time
    - token expiration time

    Passwords and financial data must never be stored in the token.
    """

    secret = os.getenv("CHAT_JWT_SECRET")

    if not secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT secret is not configured.",
        )

    algorithm = os.getenv("CHAT_JWT_ALGORITHM", "HS256")

    try:
        expire_minutes = int(
            os.getenv("CHAT_JWT_EXPIRE_MINUTES", "60")
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invalid JWT expiry configuration.",
        ) from exc

    if expire_minutes <= 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT expiry must be greater than zero.",
        )

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=expire_minutes)

    payload = {
        "sub": user_id,
        "companies": list(companies),
        "iat": now,
        "exp": expires_at,
    }

    return jwt.encode(
        payload,
        secret,
        algorithm=algorithm,
    )


def _decode_token(token: str) -> dict:
    """
    Verify and decode an incoming JWT access token.
    """

    secret = os.getenv("CHAT_JWT_SECRET")
    algorithm = os.getenv("CHAT_JWT_ALGORITHM", "HS256")

    if not secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT secret is not configured.",
        )

    try:
        return jwt.decode(
            token,
            secret,
            algorithms=[algorithm],
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
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> UserContext:
    """
    Resolve the authenticated user from the Bearer token.

    When authentication is disabled explicitly, a development
    context is returned for local testing only.
    """

    # Development-only fallback. Production environments should keep
    # CHAT_AUTH_ENABLED=true.
    if not _auth_enabled():
        return UserContext(
            user_id="development-user",
            allowed_companies=("*",),
        )

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    payload = _decode_token(
        credentials.credentials
    )

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

    return UserContext(
        user_id=str(user_id),
        allowed_companies=tuple(
            str(company)
            for company in companies
        ),
    )

async def get_authorized_company(
    company_name: str | None = None,
    current_user: UserContext = Depends(get_current_user),
) -> str | None:
    """
    Resolve the requested company and verify that the logged-in
    user is allowed to access it.

    This dependency is shared by dashboard and report routes so
    company-level authorization is enforced consistently.
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
    Verify that the authenticated user is allowed to access
    the requested Tally company.
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