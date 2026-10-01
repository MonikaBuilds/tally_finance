import os
from dataclasses import dataclass


def _required_env(name: str) -> str:
    value = os.getenv(name)

    if value is None or not value.strip():
        raise RuntimeError(
            f"Required environment variable '{name}' is not configured."
        )

    return value.strip()

def _required_csv(name: str) -> tuple[str, ...]:
    value = _required_env(name)

    items = tuple(
        item.strip()
        for item in value.split(",")
        if item.strip()
    )

    if not items:
        raise RuntimeError(
            f"Environment variable '{name}' must contain "
            "at least one value."
        )

    return items

def _required_bool(name: str) -> bool:
    value = _required_env(name).lower()

    if value in {"true", "1", "yes", "on"}:
        return True

    if value in {"false", "0", "no", "off"}:
        return False

    raise RuntimeError(
        f"Environment variable '{name}' must be a valid boolean."
    )


def _required_positive_int(name: str) -> int:
    value = _required_env(name)

    try:
        parsed = int(value)
    except ValueError as exc:
        raise RuntimeError(
            f"Environment variable '{name}' must be an integer."
        ) from exc

    if parsed <= 0:
        raise RuntimeError(
            f"Environment variable '{name}' must be greater than zero."
        )

    return parsed


@dataclass(frozen=True)
class AuthSettings:
    # Authentication
    auth_enabled: bool

    # Access JWT
    jwt_secret: str
    jwt_algorithm: str
    jwt_expire_minutes: int

    # Access-token cookie
    access_token_cookie_name: str

    # Refresh token
    refresh_token_expire_days: int

    # Refresh-token cookie
    refresh_token_cookie_name: str
    refresh_cookie_path: str

    # Shared cookie security
    cookie_secure: bool
    cookie_samesite: str
    cookie_path: str

    # CORS
    cors_allowed_origins: tuple[str, ...]

    # CSRF protection
    csrf_cookie_name: str
    csrf_header_name: str


def get_auth_settings() -> AuthSettings:
    cookie_samesite = _required_env(
        "AUTH_COOKIE_SAMESITE"
    ).lower()

    if cookie_samesite not in {
        "lax",
        "strict",
        "none",
    }:
        raise RuntimeError(
            "AUTH_COOKIE_SAMESITE must be "
            "'lax', 'strict', or 'none'."
        )

    return AuthSettings(
        auth_enabled=_required_bool(
            "CHAT_AUTH_ENABLED"
        ),

        jwt_secret=_required_env(
            "CHAT_JWT_SECRET"
        ),

        jwt_algorithm=_required_env(
            "CHAT_JWT_ALGORITHM"
        ),

        jwt_expire_minutes=_required_positive_int(
            "CHAT_JWT_EXPIRE_MINUTES"
        ),

        access_token_cookie_name=_required_env(
            "AUTH_ACCESS_COOKIE_NAME"
        ),

        refresh_token_expire_days=_required_positive_int(
            "AUTH_REFRESH_TOKEN_EXPIRE_DAYS"
        ),

        refresh_token_cookie_name=_required_env(
            "AUTH_REFRESH_COOKIE_NAME"
        ),

        refresh_cookie_path=_required_env(
            "AUTH_REFRESH_COOKIE_PATH"
        ),

        cookie_secure=_required_bool(
            "AUTH_COOKIE_SECURE"
        ),

        cookie_samesite=cookie_samesite,

        cookie_path=_required_env(
            "AUTH_COOKIE_PATH"
        ),
        cors_allowed_origins=_required_csv(
            "CORS_ALLOWED_ORIGINS"
        ),

        csrf_cookie_name=_required_env(
            "AUTH_CSRF_COOKIE_NAME"
        ),

        csrf_header_name=_required_env(
            "AUTH_CSRF_HEADER_NAME"
        ),
    )
