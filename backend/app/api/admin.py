from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.security.auth import UserContext
from app.security.permissions import (
    assign_permission_to_user,
    assign_role_to_user,
    get_all_permissions,
    get_all_roles,
    get_user_access,
    remove_permission_from_user,
    require_admin,
    role_exists,
)
from app.security.user_store import (
    create_user,
    get_all_users,
)


router = APIRouter()


class PermissionResponse(BaseModel):
    permission_id: int
    permission_code: str
    permission_name: str
    category: str
    subcategory: str | None = None
    description: str | None = None

class RoleResponse(BaseModel):
    role_id: int
    role_name: str

class AdminUserResponse(BaseModel):
    user_id: str
    username: str
    is_active: bool
    roles: list[str]
    permissions: list[str]


class AssignPermissionRequest(BaseModel):
    permission_code: str


class CreateUserRequest(BaseModel):
    user_id: str
    username: str
    password: str
    companies: list[str]
    role_name: str


@router.get(
    "/permissions",
    response_model=list[PermissionResponse],
)
def list_permissions(
    current_user: UserContext = Depends(require_admin),
) -> list[PermissionResponse]:
    """
    Return all available permissions.

    Only authenticated administrators may access
    this endpoint.
    """
    permissions = get_all_permissions()

    return [
        PermissionResponse(**permission)
        for permission in permissions
    ]

@router.get(
    "/roles",
    response_model=list[RoleResponse],
)
def list_roles(
    current_user: UserContext = Depends(require_admin),
):
    """
    Return all roles available for user management.

    Only authenticated administrators may access
    this endpoint.
    """
    return get_all_roles()

@router.get(
    "/users",
    response_model=list[AdminUserResponse],
)
def list_users(
    current_user: UserContext = Depends(require_admin),
) -> list[AdminUserResponse]:
    """
    Return all users with their assigned roles
    and direct permissions.

    Only authenticated administrators may access
    this endpoint.
    """
    users = get_all_users()

    result = []

    for user in users:
        access = get_user_access(
            user["user_id"]
        )

        result.append(
            AdminUserResponse(
                user_id=user["user_id"],
                username=user["username"],
                is_active=user["is_active"],
                roles=access["roles"],
                permissions=access["permissions"],
            )
        )

    return result


@router.post(
    "/users",
    status_code=201,
)
def create_admin_user(
    request: CreateUserRequest,
    current_user: UserContext = Depends(require_admin),
):
    """
    Create a new user and assign an existing role.

    Only authenticated administrators may perform
    this operation.
    """
    if not role_exists(request.role_name):
        raise HTTPException(
            status_code=400,
            detail="Invalid role.",
        )

    try:
        create_user(
            user_id=request.user_id,
            username=request.username,
            password=request.password,
            companies=request.companies,
        )

        role_assigned = assign_role_to_user(
            user_id=request.user_id,
            role_name=request.role_name,
        )

        if not role_assigned:
            raise HTTPException(
                status_code=500,
                detail="Unable to assign role to user.",
            )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return {
        "success": True,
        "message": "User created successfully.",
        "user_id": request.user_id,
        "username": request.username,
        "role_name": request.role_name,
    }


@router.post(
    "/users/{user_id}/permissions",
)
def assign_user_permission(
    user_id: str,
    request: AssignPermissionRequest,
    current_user: UserContext = Depends(require_admin),
):
    """
    Assign a permission to a user.

    Only authenticated administrators may perform
    this operation.
    """
    assigned = assign_permission_to_user(
        user_id=user_id,
        permission_code=request.permission_code,
    )

    if not assigned:
        raise HTTPException(
            status_code=404,
            detail="User or permission not found.",
        )

    return {
        "success": True,
        "message": "Permission assigned successfully.",
        "user_id": user_id,
        "permission_code": request.permission_code,
    }


@router.delete(
    "/users/{user_id}/permissions/{permission_code}",
)
def remove_user_permission(
    user_id: str,
    permission_code: str,
    current_user: UserContext = Depends(require_admin),
):
    """
    Remove a directly assigned permission from a user.

    Only authenticated administrators may perform
    this operation.
    """
    removed = remove_permission_from_user(
        user_id=user_id,
        permission_code=permission_code,
    )

    if not removed:
        raise HTTPException(
            status_code=404,
            detail="Permission assignment not found.",
        )

    return {
        "success": True,
        "message": "Permission removed successfully.",
        "user_id": user_id,
        "permission_code": permission_code,
    }