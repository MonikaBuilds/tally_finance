import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from pydantic import BaseModel, Field

from app.security.auth import (
    UserContext,
    create_access_token,
    get_current_user,
    is_secure_cookie,
)
from app.security.config import get_auth_settings
from app.security.csrf import generate_csrf_token
from app.security.passwords import verify_password
from app.security.permissions import get_user_access
from app.security.user_store import (
    authenticate_user,
    get_user_by_id,
    get_user_companies,
    get_user_organization_id,
    update_user_password,
)
from app.security.refresh_store import (
    create_refresh_session,
    generate_refresh_token,
    get_refresh_session,
    revoke_refresh_session,
    rotate_refresh_session,
)

router = APIRouter()


class LoginRequest(BaseModel):
    username: str = Field(
        min_length=1,
        max_length=100,
    )
    password: str = Field(
        min_length=1,
        max_length=256,
    )


class LoginResponse(BaseModel):
    user_id: str
    username: str
    companies: list[str]
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)


class CurrentUserResponse(BaseModel):
    user_id: str
    username: str
    companies: list[str]
    roles: list[str]
    permissions: list[str]


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(
        min_length=1,
        max_length=256,
    )
    new_password: str = Field(
        min_length=8,
        max_length=256,
    )


@router.post(
    "/login",
    response_model=LoginResponse,
)
def login(
    request: LoginRequest,
    response: Response,
    http_request: Request,
) -> LoginResponse:
    """
    Authenticate a user and issue the JWT access token
    through an HttpOnly cookie.
    """

    result = authenticate_user(
        request.username,
        request.password,
    )

    if result is None:
        logger.warning(
            "Authentication failed: Invalid credentials for username '%s'.",
            request.username,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    user, companies = result

    if not companies:
        logger.warning(
            "Authentication forbidden: User '%s' has no company access.",
            user.username,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This user does not have access to any company.",
        )

    org_id = get_user_organization_id(user.user_id) or "default"
    access_token = create_access_token(
        user_id=user.user_id,
        companies=companies,
        organization_id=org_id,
    )

    settings = get_auth_settings()
    refresh_token = generate_refresh_token()
    csrf_token = generate_csrf_token()

    refresh_expires_at = (
        datetime.now(timezone.utc)
        + timedelta(
            days=settings.refresh_token_expire_days
        )
    )

    create_refresh_session(
        user_id=user.user_id,
        token=refresh_token,
        expires_at=refresh_expires_at,
    )

    secure_cookie = is_secure_cookie(
        http_request, settings.cookie_secure
    )

    access_max_age = settings.jwt_expire_minutes * 60
    refresh_max_age = settings.refresh_token_expire_days * 86400

    response.set_cookie(
        key=settings.access_token_cookie_name,
        value=access_token,
        max_age=access_max_age,
        httponly=True,
        secure=secure_cookie,
        samesite=settings.cookie_samesite,
        path=settings.cookie_path,
    )

    response.set_cookie(
        key=settings.refresh_token_cookie_name,
        value=refresh_token,
        max_age=refresh_max_age,
        httponly=True,
        secure=secure_cookie,
        samesite=settings.cookie_samesite,
        path=settings.refresh_cookie_path,
    )

    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf_token,
        max_age=refresh_max_age,
        httponly=False,
        secure=secure_cookie,
        samesite=settings.cookie_samesite,
        path=settings.cookie_path,
    )

    access = get_user_access(user.user_id)
    roles = access.get("roles", [])
    permissions = access.get("permissions", [])

    logger.info("User '%s' authenticated successfully.", user.username)

    return LoginResponse(
        user_id=user.user_id,
        username=user.username,
        companies=list(companies),
        roles=roles,
        permissions=permissions,
    )


@router.get(
    "/me",
    response_model=CurrentUserResponse,
)
def get_me(
    current_user: UserContext = Depends(
        get_current_user
    ),
) -> CurrentUserResponse:
    """
    Return the authenticated user's current access information.
    """

    user = get_user_by_id(
        current_user.user_id
    )

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is unavailable.",
        )

    access = get_user_access(
        current_user.user_id
    )

    return CurrentUserResponse(
        user_id=current_user.user_id,
        username=user.username,
        companies=list(
            current_user.allowed_companies
        ),
        roles=access["roles"],
        permissions=access["permissions"],
    )

@router.post(
    "/refresh",
    status_code=status.HTTP_204_NO_CONTENT,
)
def refresh_access_token(
    request: Request,
    response: Response,
) -> None:
    """
    Rotate the refresh session and issue a new access token.
    """

    settings = get_auth_settings()

    refresh_token = request.cookies.get(
        settings.refresh_token_cookie_name
    )

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is required.",
        )

    refresh_session = get_refresh_session(
        refresh_token
    )

    if refresh_session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh session.",
        )

    user = get_user_by_id(
        refresh_session.user_id
    )

    if user is None or not user.is_active:
        revoke_refresh_session(refresh_token)

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is unavailable.",
        )

    companies = get_user_companies(
        user.user_id
    )

    if not companies:
        revoke_refresh_session(refresh_token)

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This user does not have access to any company.",
        )

    new_refresh_token = generate_refresh_token()

    new_refresh_expires_at = (
        datetime.now(timezone.utc)
        + timedelta(
            days=settings.refresh_token_expire_days
        )
    )

    rotated_session = rotate_refresh_session(
        old_token=refresh_token,
        new_token=new_refresh_token,
        expires_at=new_refresh_expires_at,
    )

    if rotated_session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh session is no longer valid.",
        )

    org_id = get_user_organization_id(user.user_id) or "default"
    new_access_token = create_access_token(
        user_id=user.user_id,
        companies=companies,
        organization_id=org_id,
    )

    secure_cookie = is_secure_cookie(
        request, settings.cookie_secure
    )

    access_max_age = settings.jwt_expire_minutes * 60
    refresh_max_age = settings.refresh_token_expire_days * 86400

    response.set_cookie(
        key=settings.access_token_cookie_name,
        value=new_access_token,
        max_age=access_max_age,
        httponly=True,
        secure=secure_cookie,
        samesite=settings.cookie_samesite,
        path=settings.cookie_path,
    )

    response.set_cookie(
        key=settings.refresh_token_cookie_name,
        value=new_refresh_token,
        max_age=refresh_max_age,
        httponly=True,
        secure=secure_cookie,
        samesite=settings.cookie_samesite,
        path=settings.refresh_cookie_path,
    )

@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
)
def logout(
    request: Request,
    response: Response,
) -> None:
    """
    Log out the current browser session.

    Revoke the current refresh session and remove
    both authentication cookies.
    """

    settings = get_auth_settings()

    refresh_token = request.cookies.get(
        settings.refresh_token_cookie_name
    )

    if refresh_token:
        revoke_refresh_session(
            refresh_token
        )

    response.delete_cookie(
        key=settings.access_token_cookie_name,
        path=settings.cookie_path,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )

    response.delete_cookie(
        key=settings.refresh_token_cookie_name,
        path=settings.refresh_cookie_path,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )

    # Clean up legacy root-scoped refresh cookie if path is different
    if settings.refresh_cookie_path != "/":
        response.delete_cookie(
            key=settings.refresh_token_cookie_name,
            path="/",
            httponly=True,
            secure=settings.cookie_secure,
            samesite=settings.cookie_samesite,
        )

    response.delete_cookie(
        key=settings.csrf_cookie_name,
        path=settings.cookie_path,
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )


@router.post(
    "/change-password",
    status_code=status.HTTP_200_OK,
)
def change_password(
    request: ChangePasswordRequest,
    response: Response,
    http_request: Request,
    current_user: UserContext = Depends(get_current_user),
):
    """
    Allow an authenticated user to change their own password.

    Verifies the current password, updates the password hash, revokes
    all prior refresh sessions across all devices, and issues a fresh
    access token and refresh session for the current client.
    """
    user = get_user_by_id(current_user.user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is unavailable.",
        )

    if not verify_password(request.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )

    try:
        update_user_password(
            user_id=current_user.user_id,
            new_password=request.new_password,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    # Issue fresh tokens for the current session
    companies = get_user_companies(user.user_id)
    settings = get_auth_settings()
    org_id = current_user.organization_id or get_user_organization_id(user.user_id) or "default"
    new_access_token = create_access_token(
        user_id=user.user_id,
        companies=companies,
        organization_id=org_id,
    )
    new_refresh_token = generate_refresh_token()
    csrf_token = generate_csrf_token()

    refresh_expires_at = (
        datetime.now(timezone.utc)
        + timedelta(days=settings.refresh_token_expire_days)
    )

    create_refresh_session(
        user_id=user.user_id,
        token=new_refresh_token,
        expires_at=refresh_expires_at,
    )

    secure_cookie = is_secure_cookie(
        http_request, settings.cookie_secure
    )

    access_max_age = settings.jwt_expire_minutes * 60
    refresh_max_age = settings.refresh_token_expire_days * 86400

    response.set_cookie(
        key=settings.access_token_cookie_name,
        value=new_access_token,
        max_age=access_max_age,
        httponly=True,
        secure=secure_cookie,
        samesite=settings.cookie_samesite,
        path=settings.cookie_path,
    )

    response.set_cookie(
        key=settings.refresh_token_cookie_name,
        value=new_refresh_token,
        max_age=refresh_max_age,
        httponly=True,
        secure=secure_cookie,
        samesite=settings.cookie_samesite,
        path=settings.refresh_cookie_path,
    )

    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf_token,
        max_age=refresh_max_age,
        httponly=False,
        secure=secure_cookie,
        samesite=settings.cookie_samesite,
        path=settings.cookie_path,
    )

    return {
        "success": True,
        "message": "Password changed successfully.",
    }

