import jwt
from fastapi.testclient import TestClient

from app.main import app

from app.security.permissions import (
    assign_permission_to_user,
    get_user_access,
    remove_permission_from_user,
)

TEST_SECRET = (
    "test-chatbot-jwt-secret-key-that-is-long-enough-123456"
)


def _create_token(
    user_id: str,
    companies: list[str],
) -> str:
    return jwt.encode(
        {
            "sub": user_id,
            "companies": companies,
        },
        TEST_SECRET,
        algorithm="HS256",
    )


def _enable_auth(monkeypatch):
    monkeypatch.setenv(
        "CHAT_AUTH_ENABLED",
        "true",
    )
    monkeypatch.setenv(
        "CHAT_JWT_SECRET",
        TEST_SECRET,
    )
    monkeypatch.setenv(
        "CHAT_JWT_ALGORITHM",
        "HS256",
    )


def test_admin_can_list_permissions(monkeypatch):
    _enable_auth(monkeypatch)

    token = _create_token(
        user_id="user-001",
        companies=["ABC Pvt Ltd"],
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/admin/permissions",
            headers={
                "Authorization": f"Bearer {token}",
            },
        )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 4

    permission_codes = {
        permission["permission_code"]
        for permission in data
    }

    assert permission_codes == {
        "financial",
        "inventory",
        "banking",
        "tax",
    }


def test_normal_user_cannot_list_permissions(monkeypatch):
    _enable_auth(monkeypatch)

    token = _create_token(
        user_id="user-002",
        companies=["ABC Pvt Ltd"],
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/admin/permissions",
            headers={
                "Authorization": f"Bearer {token}",
            },
        )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "Administrator access required."
    )


def test_permissions_endpoint_requires_authentication(
    monkeypatch,
):
    _enable_auth(monkeypatch)

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/admin/permissions",
        )

    assert response.status_code == 401
    assert response.json()["detail"] == (
        "Authentication required."
    )
    
def test_admin_can_list_users(monkeypatch):
    _enable_auth(monkeypatch)

    token = _create_token(
        user_id="user-001",
        companies=["ABC Pvt Ltd"],
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/admin/users",
            headers={
                "Authorization": f"Bearer {token}",
            },
        )

    assert response.status_code == 200

    data = response.json()

    users_by_id = {
        user["user_id"]: user
        for user in data
    }

    assert "user-001" in users_by_id
    assert "user-002" in users_by_id

    assert users_by_id["user-001"]["roles"] == [
        "admin"
    ]

    assert users_by_id["user-002"]["roles"] == [
        "user"
    ]

    assert set(
        users_by_id["user-002"]["permissions"]
    ) == {
        "financial",
        "inventory",
    }


def test_normal_user_cannot_list_users(monkeypatch):
    _enable_auth(monkeypatch)

    token = _create_token(
        user_id="user-002",
        companies=["ABC Pvt Ltd"],
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/admin/users",
            headers={
                "Authorization": f"Bearer {token}",
            },
        )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "Administrator access required."
    )
    
def test_admin_can_assign_permission(monkeypatch):
    _enable_auth(monkeypatch)

    # Start from a known state.
    remove_permission_from_user(
        "user-002",
        "banking",
    )

    token = _create_token(
        user_id="user-001",
        companies=["ABC Pvt Ltd"],
    )

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/admin/users/user-002/permissions",
                headers={
                    "Authorization": f"Bearer {token}",
                },
                json={
                    "permission_code": "banking",
                },
            )

        assert response.status_code == 200

        data = response.json()

        assert data["success"] is True
        assert data["user_id"] == "user-002"
        assert data["permission_code"] == "banking"

        access = get_user_access("user-002")

        assert "banking" in access["permissions"]

    finally:
        # Restore baseline even if the test fails.
        remove_permission_from_user(
            "user-002",
            "banking",
        )
    
def test_admin_can_remove_permission(monkeypatch):
    _enable_auth(monkeypatch)

    token = _create_token(
        user_id="user-001",
        companies=["ABC Pvt Ltd"],
    )

    # Give Banking permission first so this test
    # does not depend on another test.
    from app.security.permissions import (
        assign_permission_to_user,
    )

    assign_permission_to_user(
        "user-002",
        "banking",
    )

    try:
        with TestClient(app) as client:
            response = client.delete(
                "/api/v1/admin/users/user-002/permissions/banking",
                headers={
                    "Authorization": f"Bearer {token}",
                },
            )

        assert response.status_code == 200

        data = response.json()

        assert data["success"] is True
        assert data["user_id"] == "user-002"
        assert data["permission_code"] == "banking"

        access = get_user_access("user-002")

        assert "banking" not in access["permissions"]

    finally:
        # Ensure database is clean even if test fails.
        remove_permission_from_user(
            "user-002",
            "banking",
        )
        
def test_normal_user_cannot_assign_permission(monkeypatch):
    _enable_auth(monkeypatch)

    token = _create_token(
        user_id="user-002",
        companies=["ABC Pvt Ltd"],
    )

    # Make sure Banking is not assigned before the test.
    remove_permission_from_user(
        "user-002",
        "banking",
    )

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/admin/users/user-002/permissions",
                headers={
                    "Authorization": f"Bearer {token}",
                },
                json={
                    "permission_code": "banking",
                },
            )

        assert response.status_code == 403
        assert response.json()["detail"] == (
            "Administrator access required."
        )

        # Most important check:
        # unauthorized request must not modify MySQL.
        access = get_user_access("user-002")

        assert "banking" not in access["permissions"]

    finally:
        remove_permission_from_user(
            "user-002",
            "banking",
        )
        
def test_normal_user_cannot_remove_permission(monkeypatch):
    _enable_auth(monkeypatch)

    token = _create_token(
        user_id="user-002",
        companies=["ABC Pvt Ltd"],
    )

    # Banking must exist first so we can prove that
    # the unauthorized DELETE does not remove it.
    assign_permission_to_user(
        "user-002",
        "banking",
    )

    try:
        with TestClient(app) as client:
            response = client.delete(
                "/api/v1/admin/users/user-002/permissions/banking",
                headers={
                    "Authorization": f"Bearer {token}",
                },
            )

        assert response.status_code == 403
        assert response.json()["detail"] == (
            "Administrator access required."
        )

        # Verify unauthorized request did not change MySQL.
        access = get_user_access("user-002")

        assert "banking" in access["permissions"]

    finally:
        # Restore the normal baseline.
        remove_permission_from_user(
            "user-002",
            "banking",
        )
        
def test_admin_cannot_assign_invalid_permission(monkeypatch):
    _enable_auth(monkeypatch)

    token = _create_token(
        user_id="user-001",
        companies=["ABC Pvt Ltd"],
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/admin/users/user-002/permissions",
            headers={
                "Authorization": f"Bearer {token}",
            },
            json={
                "permission_code": "does-not-exist",
            },
        )

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "User or permission not found."
    )

    # Invalid permission must not change user access.
    access = get_user_access("user-002")

    assert set(access["permissions"]) == {
        "financial",
        "inventory",
    }
    
def test_admin_cannot_assign_permission_to_invalid_user(
    monkeypatch,
):
    _enable_auth(monkeypatch)

    token = _create_token(
        user_id="user-001",
        companies=["ABC Pvt Ltd"],
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/admin/users/does-not-exist/permissions",
            headers={
                "Authorization": f"Bearer {token}",
            },
            json={
                "permission_code": "banking",
            },
        )

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "User or permission not found."
    )
    
def test_assign_permission_requires_authentication(
    monkeypatch,
):
    _enable_auth(monkeypatch)

    # Ensure known baseline.
    remove_permission_from_user(
        "user-002",
        "banking",
    )

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/admin/users/user-002/permissions",
                json={
                    "permission_code": "banking",
                },
            )

        assert response.status_code == 401
        assert response.json()["detail"] == (
            "Authentication required."
        )

        # Unauthenticated request must not modify MySQL.
        access = get_user_access("user-002")

        assert "banking" not in access["permissions"]

    finally:
        remove_permission_from_user(
            "user-002",
            "banking",
        )
        
def test_remove_permission_requires_authentication(
    monkeypatch,
):
    _enable_auth(monkeypatch)

    # Banking must exist first so we can prove that
    # an unauthenticated request cannot remove it.
    assign_permission_to_user(
        "user-002",
        "banking",
    )

    try:
        with TestClient(app) as client:
            response = client.delete(
                "/api/v1/admin/users/user-002/permissions/banking",
            )

        assert response.status_code == 401
        assert response.json()["detail"] == (
            "Authentication required."
        )

        # Permission must still exist because the
        # unauthorized DELETE must not modify MySQL.
        access = get_user_access("user-002")

        assert "banking" in access["permissions"]

    finally:
        # Restore original baseline.
        remove_permission_from_user(
            "user-002",
            "banking",
        )
        
def test_admin_can_create_user(monkeypatch):
    _enable_auth(monkeypatch)

    from app.security.user_store import (
        authenticate_user,
        delete_user,
        get_user_companies,
    )

    test_user_id = "rbac-create-test-user"
    test_username = "rbac-create-test"
    test_password = "TestPassword123!"
    test_company = "ABC Pvt Ltd"

    # Ensure a previous failed test run did not leave
    # the temporary user behind.
    delete_user(test_user_id)

    token = _create_token(
        user_id="user-001",
        companies=["ABC Pvt Ltd"],
    )

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/admin/users",
                headers={
                    "Authorization": f"Bearer {token}",
                },
                json={
                    "user_id": test_user_id,
                    "username": test_username,
                    "password": test_password,
                    "companies": [test_company],
                    "role_name": "user",
                },
            )

        assert response.status_code == 201

        data = response.json()

        assert data["success"] is True
        assert data["user_id"] == test_user_id
        assert data["username"] == test_username
        assert data["role_name"] == "user"

        access = get_user_access(test_user_id)

        assert access["roles"] == ["user"]
        assert access["permissions"] == []

        companies = get_user_companies(test_user_id)

        assert test_company in companies

        authenticated = authenticate_user(
            test_username,
            test_password,
        )

        assert authenticated is not None

    finally:
        # Always restore the database even if an
        # assertion fails.
        delete_user(test_user_id)