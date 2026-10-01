import hmac
import secrets

from fastapi import Request
from fastapi.responses import JSONResponse

from app.security.config import get_auth_settings


SAFE_METHODS = {
    "GET",
    "HEAD",
    "OPTIONS",
}

CSRF_EXEMPT_PATHS = {
    "/api/v1/auth/login",
}


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


async def csrf_protection_middleware(
    request: Request,
    call_next,
):
    settings = get_auth_settings()

    # Preserve existing development behavior when
    # authentication is disabled.
    if not settings.auth_enabled:
        return await call_next(request)

    # Safe HTTP methods do not require CSRF validation.
    if request.method.upper() in SAFE_METHODS:
        return await call_next(request)

    # Login occurs before an authenticated browser session
    # exists, so it must remain exempt.
    if request.url.path in CSRF_EXEMPT_PATHS:
        return await call_next(request)

    # CSRF protection is required for cookie-authenticated
    # requests. If no auth cookie exists, allow the normal
    # authentication layer to return its own 401/403 response.
    has_auth_cookie = (
        settings.access_token_cookie_name
        in request.cookies
        or settings.refresh_token_cookie_name
        in request.cookies
    )

    if not has_auth_cookie:
        return await call_next(request)

    csrf_cookie = request.cookies.get(
        settings.csrf_cookie_name
    )

    csrf_header = request.headers.get(
        settings.csrf_header_name
    )

    if not csrf_cookie or not csrf_header:
        return JSONResponse(
            status_code=403,
            content={
                "detail": "CSRF validation failed."
            },
        )

    if not hmac.compare_digest(
        csrf_cookie,
        csrf_header,
    ):
        return JSONResponse(
            status_code=403,
            content={
                "detail": "CSRF validation failed."
            },
        )

    return await call_next(request)