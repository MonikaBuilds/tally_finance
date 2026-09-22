from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.security.auth import create_access_token
from app.security.user_store import authenticate_user


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
    access_token: str
    token_type: str = "bearer"
    user_id: str
    username: str
    companies: list[str]


@router.post(
    "/login",
    response_model=LoginResponse,
)
def login(request: LoginRequest) -> LoginResponse:
    """
    Authenticate a chatbot user and issue a JWT access token.
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

    return LoginResponse(
        access_token=access_token,
        user_id=user.user_id,
        username=user.username,
        companies=list(companies),
    )