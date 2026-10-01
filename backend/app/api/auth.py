from datetime import datetime, timedelta, timezone
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
)
from app.security.config import get_auth_settings
from app.security.csrf import generate_csrf_token
from app.security.permissions import get_user_access
from app.security.user_store import (
    authenticate_user,
    get_user_by_id,
    get_user_companies,
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


class CurrentUserResponse(BaseModel):
    user_id: str
    username: str
    companies: list[str]
    roles: list[str]
    permissions: list[str]


@router.post(
    "/login",
    response_model=LoginResponse,
)
def login(
    request: LoginRequest,
    response: Response,
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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    user, companies = result

    if not companies:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This user does not have access to any company.",
        )

    access_token = create_access_token(
        user_id=user.user_id,
        companies=companies,
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

    response.set_cookie(
        key=settings.access_token_cookie_name,
        value=access_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path=settings.cookie_path,
    )

    response.set_cookie(
        key=settings.refresh_token_cookie_name,
        value=refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path=settings.refresh_cookie_path,
    )

    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf_token,
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path=settings.cookie_path,
    )

    return LoginResponse(
        user_id=user.user_id,
        username=user.username,
        companies=list(companies),
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

    new_access_token = create_access_token(
        user_id=user.user_id,
        companies=companies,
    )

    response.set_cookie(
        key=settings.access_token_cookie_name,
        value=new_access_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path=settings.cookie_path,
    )

    response.set_cookie(
        key=settings.refresh_token_cookie_name,
        value=new_refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
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

    response.delete_cookie(
        key=settings.csrf_cookie_name,
        path=settings.cookie_path,
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )
