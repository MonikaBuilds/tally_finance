import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

_BACKEND_ENV = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_BACKEND_ENV)
load_dotenv()


def _env_or_default(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip()


def _required_env(name: str) -> str:
    value = os.getenv(name)

    if value is None or not value.strip():
        raise RuntimeError(
            f"Required environment variable '{name}' is not configured."
        )

    return value.strip()


def _required_csv(name: str, default: str | None = None) -> tuple[str, ...]:
    val = os.getenv(name)
    if val is None or not val.strip():
        if default is not None:
            val = default
        else:
            raise RuntimeError(f"Required environment variable '{name}' is not configured.")

    items = tuple(
        item.strip()
        for item in val.split(",")
        if item.strip()
    )

    if not items:
        raise RuntimeError(
            f"Environment variable '{name}' must contain "
            "at least one value."
        )

    return items


def _required_bool(name: str, default: bool | None = None) -> bool:
    val = os.getenv(name)
    if val is None or not val.strip():
        if default is not None:
            return default
        raise RuntimeError(f"Required environment variable '{name}' is not configured.")

    value = val.strip().lower()

    if value in {"true", "1", "yes", "on"}:
        return True

    if value in {"false", "0", "no", "off"}:
        return False

    raise RuntimeError(
        f"Environment variable '{name}' must be a valid boolean."
    )


def _required_positive_int(name: str, default: int | None = None) -> int:
    val = os.getenv(name)
    if val is None or not val.strip():
        if default is not None:
            return default
        raise RuntimeError(f"Required environment variable '{name}' is not configured.")

    try:
        parsed = int(val.strip())
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
    cookie_samesite = _env_or_default(
        "AUTH_COOKIE_SAMESITE", "lax"
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
            "CHAT_AUTH_ENABLED", default=True
        ),

        jwt_secret=_required_env(
            "CHAT_JWT_SECRET"
        ),

        jwt_algorithm=_env_or_default(
            "CHAT_JWT_ALGORITHM", "HS256"
        ),

        jwt_expire_minutes=_required_positive_int(
            "CHAT_JWT_EXPIRE_MINUTES", default=60
        ),

        access_token_cookie_name=_env_or_default(
            "AUTH_ACCESS_COOKIE_NAME", "access_token"
        ),

        refresh_token_expire_days=_required_positive_int(
            "AUTH_REFRESH_TOKEN_EXPIRE_DAYS", default=7
        ),

        refresh_token_cookie_name=_env_or_default(
            "AUTH_REFRESH_COOKIE_NAME", "refresh_token"
        ),

        refresh_cookie_path=_env_or_default(
            "AUTH_REFRESH_COOKIE_PATH", "/"
        ),

        cookie_secure=_required_bool(
            "AUTH_COOKIE_SECURE", default=False
        ),

        cookie_samesite=cookie_samesite,

        cookie_path=_env_or_default(
            "AUTH_COOKIE_PATH", "/"
        ),
        cors_allowed_origins=_required_csv(
            "CORS_ALLOWED_ORIGINS", default="http://localhost:5173,http://127.0.0.1:5173"
        ),

        csrf_cookie_name=_env_or_default(
            "AUTH_CSRF_COOKIE_NAME", "csrf_token"
        ),

        csrf_header_name=_env_or_default(
            "AUTH_CSRF_HEADER_NAME", "X-CSRF-Token"
        ),
    )
