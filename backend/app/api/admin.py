from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.security.auth import UserContext
from app.security.permissions import (
    assign_permission_to_user,
    assign_role_to_user,
    can_manage_role,
    get_all_permissions,
    get_all_roles,
    get_user_access,
    is_admin,
    is_superadmin,
    remove_permission_from_user,
    remove_role_from_user,
    require_admin,
    role_exists,
    user_has_permission,
)

from app.security.user_store import (
    create_user,
    delete_user,
    get_all_users,
    get_user_by_id,
    get_user_companies,
    get_user_organization_id,
    set_user_active_status,
    set_user_companies,
    update_user_password,
    user_belongs_to_organization,
)


router = APIRouter()


def ensure_same_organization(
    *,
    current_user: UserContext,
    target_user_id: str,
) -> None:
    """
    Ensure the target user belongs to the same
    organization as the authenticated manager.
    """
    organization_id = get_user_organization_id(
        current_user.user_id
    )

    if organization_id is None:
        raise HTTPException(
            status_code=403,
            detail="Organization access is not configured.",
        )

    if not user_belongs_to_organization(
        target_user_id,
        organization_id,
    ):
        raise HTTPException(
            status_code=404,
            detail="User not found.",
        )


def ensure_can_manage_user(
    *,
    current_user: UserContext,
    target_user_id: str,
) -> None:
    """
    Enforce the user-management role hierarchy.

    Superadmin may manage Admins and Users within
    the same organization.

    Admin may manage Users only.

    Admin may not manage another Admin or a
    Superadmin.
    """
    ensure_same_organization(
        current_user=current_user,
        target_user_id=target_user_id,
    )

    # Prevent a manager from modifying their own
    # account through User Management.
    if current_user.user_id == target_user_id:
        raise HTTPException(
            status_code=403,
            detail=(
                "You cannot modify your own account "
                "through User Management."
            ),
        )

    target_access = get_user_access(
        target_user_id
    )

    target_roles = set(
        target_access.get("roles", [])
    )

    # Superadmin may manage Admin and User accounts,
    # but another Superadmin must never be managed
    # through these endpoints.
    if is_superadmin(current_user.user_id):
        if "superadmin" in target_roles:
            raise HTTPException(
                status_code=403,
                detail=(
                    "A Superadmin account cannot be "
                    "modified through User Management."
                ),
            )

        return

    # Admin may manage normal User accounts only.
    if is_admin(current_user.user_id):
        if (
            "superadmin" in target_roles
            or "admin" in target_roles
        ):
            raise HTTPException(
                status_code=403,
                detail=(
                    "Admins may manage User accounts only."
                ),
            )

        # Fail closed if the target has no normal
        # user role.
        if "user" not in target_roles:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Admins may manage User accounts only."
                ),
            )

        return

    raise HTTPException(
        status_code=403,
        detail="User management access denied.",
    )


def ensure_can_manage_permission(
    *,
    current_user: UserContext,
    permission_code: str,
) -> None:
    """
    Ensure the current manager may manage the
    requested permission.

    Superadmin may manage any permission.

    Admin may manage only permissions that are
    directly assigned to the Admin.
    """
    if is_superadmin(current_user.user_id):
        return

    if not user_has_permission(
        current_user.user_id,
        permission_code,
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "You cannot manage a permission "
                "that is outside your own access scope."
            ),
        )


def ensure_can_assign_companies(
    *,
    current_user: UserContext,
    companies: list[str],
) -> list[str]:
    """
    Ensure requested company access is within the
    authenticated manager's own company scope.

    Company names come from existing company
    assignments and are never hardcoded.
    """
    requested_companies = []

    for company in companies:
        clean_company = company.strip()

        if (
            clean_company
            and clean_company not in requested_companies
        ):
            requested_companies.append(clean_company)

    if not requested_companies:
        raise HTTPException(
            status_code=400,
            detail="At least one company is required.",
        )

    allowed_companies = set(
        get_user_companies(current_user.user_id)
    )

    unauthorized_companies = [
        company
        for company in requested_companies
        if company not in allowed_companies
    ]

    if unauthorized_companies:
        raise HTTPException(
            status_code=403,
            detail=(
                "You cannot assign company access "
                "outside your own company scope."
            ),
        )

    return requested_companies

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
    companies: list[str] = []


class AssignPermissionRequest(BaseModel):
    permission_code: str


class UpdateUserStatusRequest(BaseModel):
    is_active: bool


class CreateUserRequest(BaseModel):
    user_id: str | None = None
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
    Return permissions available to the current
    manager.

    Superadmin sees all permissions.

    Admin sees only permissions within the Admin's
    own access scope.
    """
    permissions = get_all_permissions()

    if is_superadmin(current_user.user_id):
        visible_permissions = permissions
    else:
        visible_permissions = [
            permission
            for permission in permissions
            if user_has_permission(
                current_user.user_id,
                permission["permission_code"],
            )
        ]

    return [
        PermissionResponse(**permission)
        for permission in visible_permissions
    ]


@router.get(
    "/roles",
    response_model=list[RoleResponse],
)
def list_roles(
    current_user: UserContext = Depends(require_admin),
):
    """
    Return roles available for user management.

    Backend role assignment remains protected by
    can_manage_role().
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
    Return organization users with their roles
    and direct permissions.
    """
    organization_id = get_user_organization_id(
        current_user.user_id
    )

    if organization_id is None:
        raise HTTPException(
            status_code=403,
            detail="Organization access is not configured.",
        )

    users = get_all_users(
        organization_id
    )

    result = []

    for user in users:
        access = get_user_access(
            user["user_id"]
        )

        roles = access["roles"]

        # Admin manages normal User accounts only.
        # Do not expose Admin/Superadmin accounts
        # as manageable rows to an Admin.
        if (
            is_admin(current_user.user_id)
            and not is_superadmin(current_user.user_id)
        ):
            if (
                "admin" in roles
                or "superadmin" in roles
            ):
                continue

        user_companies = list(
            get_user_companies(user["user_id"])
        )

        result.append(
            AdminUserResponse(
                user_id=user["user_id"],
                username=user["username"],
                is_active=user["is_active"],
                roles=roles,
                permissions=access["permissions"],
                companies=user_companies,
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

    Superadmin may create Admin or User accounts.
    Admin may create User accounts only.

    Company access must remain within the
    authenticated manager's company scope.
    """
    if not role_exists(request.role_name):
        raise HTTPException(
            status_code=400,
            detail="Invalid role.",
        )

    if not can_manage_role(
        current_user.user_id,
        request.role_name,
    ):
        raise HTTPException(
            status_code=403,
            detail="You are not allowed to assign this role.",
        )

    organization_id = get_user_organization_id(
        current_user.user_id
    )

    if organization_id is None:
        raise HTTPException(
            status_code=403,
            detail="Organization access is not configured.",
        )

    companies = ensure_can_assign_companies(
        current_user=current_user,
        companies=request.companies,
    )

    try:
        user_id = create_user(
            user_id=request.user_id,
            username=request.username,
            password=request.password,
            companies=companies,
            organization_id=organization_id,
        )

        role_assigned = assign_role_to_user(
            user_id=user_id,
            role_name=request.role_name,
        )

        if not role_assigned:
            raise HTTPException(
                status_code=500,
                detail="Unable to assign role to user.",
            )

        if request.role_name in ("admin", "superadmin"):
            for perm in ("financial", "inventory", "banking", "tax"):
                assign_permission_to_user(user_id, perm)

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return {
        "success": True,
        "message": "User created successfully.",
        "user_id": user_id,
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
    Assign a permission to a manageable user.

    Superadmin may assign any permission.

    Admin may assign permissions only to User
    accounts and only within the Admin's own
    permission scope.
    """
    ensure_can_manage_user(
        current_user=current_user,
        target_user_id=user_id,
    )

    ensure_can_manage_permission(
        current_user=current_user,
        permission_code=request.permission_code,
    )

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
    Remove a directly assigned permission.

    Superadmin may remove permissions from Admin
    and User accounts.

    Admin may remove permissions from User accounts
    only and only within the Admin's own scope.
    """
    ensure_can_manage_user(
        current_user=current_user,
        target_user_id=user_id,
    )

    ensure_can_manage_permission(
        current_user=current_user,
        permission_code=permission_code,
    )

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


@router.patch(
    "/users/{user_id}/status",
)
def update_user_status(
    user_id: str,
    request: UpdateUserStatusRequest,
    current_user: UserContext = Depends(require_admin),
):
    """
    Activate or deactivate a manageable account.

    Superadmin may manage Admin and User accounts.

    Admin may manage User accounts only.
    """
    ensure_can_manage_user(
        current_user=current_user,
        target_user_id=user_id,
    )

    updated = set_user_active_status(
        user_id=user_id,
        is_active=request.is_active,
    )

    if not updated:
        raise HTTPException(
            status_code=404,
            detail="User not found.",
        )

    return {
        "success": True,
        "message": (
            "User activated successfully."
            if request.is_active
            else "User deactivated successfully."
        ),
        "user_id": user_id,
        "is_active": request.is_active,
    }


class UpdateUserCompaniesRequest(BaseModel):
    companies: list[str]


@router.put(
    "/users/{user_id}/companies",
)
def update_user_companies(
    user_id: str,
    request: UpdateUserCompaniesRequest,
    current_user: UserContext = Depends(require_admin),
):
    """
    Update company access for an existing manageable user.

    The authenticated manager may only assign companies that exist
    within their own allowed company access scope.
    """
    ensure_can_manage_user(
        current_user=current_user,
        target_user_id=user_id,
    )

    validated_companies = ensure_can_assign_companies(
        current_user=current_user,
        companies=request.companies,
    )

    try:
        updated_companies = set_user_companies(
            user_id=user_id,
            companies=validated_companies,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return {
        "success": True,
        "message": "User company access updated successfully.",
        "user_id": user_id,
        "companies": list(updated_companies),
    }


class UpdateUserRoleRequest(BaseModel):
    role_name: str


@router.put(
    "/users/{user_id}/role",
)
def update_user_role(
    user_id: str,
    request: UpdateUserRoleRequest,
    current_user: UserContext = Depends(require_admin),
):
    """
    Update or change the role for an existing manageable user.

    Superadmin may assign 'admin' or 'user' roles.
    Admin may only manage 'user' accounts and cannot promote to 'admin'.
    """
    ensure_can_manage_user(
        current_user=current_user,
        target_user_id=user_id,
    )

    if not role_exists(request.role_name):
        raise HTTPException(
            status_code=400,
            detail="Invalid role.",
        )

    if not can_manage_role(
        current_user.user_id,
        request.role_name,
    ):
        raise HTTPException(
            status_code=403,
            detail="You are not allowed to assign this role.",
        )

    target_access = get_user_access(user_id)
    existing_roles = target_access.get("roles", [])

    for existing_role in existing_roles:
        remove_role_from_user(user_id, existing_role)

    assigned = assign_role_to_user(user_id, request.role_name)
    if not assigned:
        raise HTTPException(
            status_code=500,
            detail="Unable to assign role to user.",
        )

    from app.security.refresh_store import revoke_all_user_sessions
    revoke_all_user_sessions(user_id)

    return {
        "success": True,
        "message": "User role updated successfully.",
        "user_id": user_id,
        "role_name": request.role_name,
    }


class ResetUserPasswordRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=256)


@router.post(
    "/users/{user_id}/reset-password",
)
def reset_user_password(
    user_id: str,
    request: ResetUserPasswordRequest,
    current_user: UserContext = Depends(require_admin),
):
    """
    Reset a user's password.

    Superadmin may reset Admin and User passwords.
    Admin may reset User passwords only.
    Revokes all active sessions for the target user immediately.
    """
    ensure_can_manage_user(
        current_user=current_user,
        target_user_id=user_id,
    )

    user = get_user_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=404,
            detail="User not found.",
        )

    try:
        update_user_password(
            user_id=user_id,
            new_password=request.new_password,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return {
        "success": True,
        "message": f"Password reset successfully for user {user.username}.",
        "user_id": user_id,
    }


@router.delete(
    "/users/{user_id}",
)
def delete_admin_user(
    user_id: str,
    current_user: UserContext = Depends(require_admin),
):
    """
    Permanently delete a user account and associated assignments.

    Superadmin may delete Admin and User accounts.
    Admin may delete User accounts only.
    A manager cannot delete their own account.
    Revokes all active refresh sessions prior to deletion.
    """
    ensure_can_manage_user(
        current_user=current_user,
        target_user_id=user_id,
    )

    from app.security.refresh_store import revoke_all_user_sessions
    revoke_all_user_sessions(user_id)

    deleted = delete_user(user_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="User not found.",
        )

    return {
        "success": True,
        "message": "User deleted successfully.",
        "user_id": user_id,
    }


