import jwt
from fastapi.testclient import TestClient

from app.main import app

from app.security.permissions import (
    assign_permission_to_user,
    get_user_access,
    remove_permission_from_user,
)
from app.security.user_store import get_user_companies

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

    assert set(users_by_id["user-001"]["roles"]).intersection(
        {"admin", "superadmin"}
    )

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
    assert "not found" in response.json()["detail"].lower()
    
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
    from app.security.db import get_connection
    _conn = get_connection()
    _cur = _conn.cursor()
    _cur.execute("DELETE FROM users WHERE username = %s OR user_id = %s", (test_username, test_user_id))
    _conn.commit()
    _cur.close()
    _conn.close()

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
        _conn = get_connection()
        _cur = _conn.cursor()
        _cur.execute("DELETE FROM users WHERE username = %s OR user_id = %s", (test_username, test_user_id))
        _conn.commit()
        _cur.close()
        _conn.close()


def test_admin_can_update_user_companies(monkeypatch):
    _enable_auth(monkeypatch)

    admin_token = _create_token(
        user_id="user-001",
        companies=["ABC Pvt Ltd"],
    )

    with TestClient(app) as client:
        # Update user-002 companies
        response = client.put(
            "/api/v1/admin/users/user-002/companies",
            headers={
                "Authorization": f"Bearer {admin_token}",
            },
            json={
                "companies": ["ABC Pvt Ltd"],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["companies"] == ["ABC Pvt Ltd"]

        # Verify get_user_companies reflects update
        companies = get_user_companies("user-002")
        assert "ABC Pvt Ltd" in companies

        # Verify list_users reflects companies
        list_resp = client.get(
            "/api/v1/admin/users",
            headers={
                "Authorization": f"Bearer {admin_token}",
            },
        )
        assert list_resp.status_code == 200
        users_list = list_resp.json()
        target_user = next((u for u in users_list if u["user_id"] == "user-002"), None)
        assert target_user is not None
        assert "ABC Pvt Ltd" in target_user["companies"]


def test_admin_cannot_assign_unauthorized_company(monkeypatch):
    _enable_auth(monkeypatch)

    admin_token = _create_token(
        user_id="user-001",
        companies=["ABC Pvt Ltd"],
    )

    with TestClient(app) as client:
        response = client.put(
            "/api/v1/admin/users/user-002/companies",
            headers={
                "Authorization": f"Bearer {admin_token}",
            },
            json={
                "companies": ["Rogue Company Not In Scope"],
            },
        )

        assert response.status_code == 403


def test_normal_user_cannot_update_user_companies(monkeypatch):
    _enable_auth(monkeypatch)

    user_token = _create_token(
        user_id="user-002",
        companies=["ABC Pvt Ltd"],
    )

    with TestClient(app) as client:
        response = client.put(
            "/api/v1/admin/users/user-002/companies",
            headers={
                "Authorization": f"Bearer {user_token}",
            },
            json={
                "companies": ["ABC Pvt Ltd"],
            },
        )

        assert response.status_code == 403


def test_set_user_companies_revokes_active_sessions():
    from datetime import datetime, timedelta, timezone
    from app.security.refresh_store import (
        create_refresh_session,
        generate_refresh_token,
        get_refresh_session,
    )
    from app.security.user_store import set_user_companies

    token = generate_refresh_token()
    expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    session_id = create_refresh_session(
        user_id="user-002",
        token=token,
        expires_at=expires_at,
    )
    assert session_id is not None

    # Verify session is initially active
    active_sess = get_refresh_session(token)
    assert active_sess is not None

    # Call set_user_companies
    set_user_companies("user-002", ["ABC Pvt Ltd"])

    # Active session must be revoked
    revoked_sess = get_refresh_session(token)
    assert revoked_sess is None


def test_user_change_password_and_invalidates_old_sessions(monkeypatch):
    from app.security.refresh_store import (
        create_refresh_session,
        generate_refresh_token,
        get_refresh_session,
    )
    from app.security.user_store import authenticate_user, update_user_password
    from datetime import datetime, timedelta, timezone

    _enable_auth(monkeypatch)

    # Initialize user-002 password to known baseline
    update_user_password(user_id="user-002", new_password="password")

    token = _create_token(
        user_id="user-002",
        companies=["ABC Pvt Ltd"],
    )

    old_refresh_token = generate_refresh_token()
    create_refresh_session(
        user_id="user-002",
        token=old_refresh_token,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    assert get_refresh_session(old_refresh_token) is not None

    with TestClient(app) as client:
        # Wrong current password
        resp_wrong = client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "current_password": "WrongPassword123!",
                "new_password": "NewSecretPassword2026!",
            },
        )
        assert resp_wrong.status_code == 400

        # Too short new password
        resp_short = client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "current_password": "password",
                "new_password": "short",
            },
        )
        assert resp_short.status_code in (400, 422)

        # Successful change
        resp_ok = client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "current_password": "password",
                "new_password": "NewSecretPassword2026!",
            },
        )
        assert resp_ok.status_code == 200
        assert resp_ok.json()["success"] is True

        # Old refresh session must be revoked
        assert get_refresh_session(old_refresh_token) is None

        # Verify authentication works with new password
        auth_new = authenticate_user("user2", "NewSecretPassword2026!")
        assert auth_new is not None

        # Restore original password for other tests
        update_user_password(user_id="user-002", new_password="password")


def test_admin_reset_user_password(monkeypatch):
    from app.security.user_store import authenticate_user, update_user_password

    _enable_auth(monkeypatch)

    admin_token = _create_token(
        user_id="user-001",
        companies=["ABC Pvt Ltd"],
    )
    user_token = _create_token(
        user_id="user-002",
        companies=["ABC Pvt Ltd"],
    )

    with TestClient(app) as client:
        # Normal user cannot reset passwords
        resp_forbidden = client.post(
            "/api/v1/admin/users/user-002/reset-password",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"new_password": "AdminResetPassword2026!"},
        )
        assert resp_forbidden.status_code == 403

        # Admin cannot reset their own password via admin reset
        resp_self = client.post(
            "/api/v1/admin/users/user-001/reset-password",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"new_password": "AdminResetPassword2026!"},
        )
        assert resp_self.status_code == 403

        # Admin resets user-002 password
        resp_ok = client.post(
            "/api/v1/admin/users/user-002/reset-password",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"new_password": "AdminResetPassword2026!"},
        )
        assert resp_ok.status_code == 200
        assert resp_ok.json()["success"] is True

        # Verify authentication with new password
        auth_res = authenticate_user("user2", "AdminResetPassword2026!")
        assert auth_res is not None

        # Restore password
        update_user_password(user_id="user-002", new_password="password")


def test_admin_update_user_role(monkeypatch):
    from app.security.permissions import assign_role_to_user, remove_role_from_user

    _enable_auth(monkeypatch)

    admin_token = _create_token(
        user_id="user-001",
        companies=["ABC Pvt Ltd"],
    )
    user_token = _create_token(
        user_id="user-002",
        companies=["ABC Pvt Ltd"],
    )

    try:
        with TestClient(app) as client:
            # Normal user cannot update role
            resp_forbidden = client.put(
                "/api/v1/admin/users/user-002/role",
                headers={"Authorization": f"Bearer {user_token}"},
                json={"role_name": "admin"},
            )
            assert resp_forbidden.status_code == 403

            # Invalid role returns 400
            resp_invalid = client.put(
                "/api/v1/admin/users/user-002/role",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={"role_name": "non_existent_role_999"},
            )
            assert resp_invalid.status_code == 400

            # Superadmin can update user role to admin
            resp_ok = client.put(
                "/api/v1/admin/users/user-002/role",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={"role_name": "admin"},
            )
            assert resp_ok.status_code == 200
            assert resp_ok.json()["success"] is True

    finally:
        # Restore user-002 role to user
        remove_role_from_user("user-002", "admin")
        assign_role_to_user("user-002", "user")


def test_admin_delete_user(monkeypatch):
    from app.security.permissions import assign_role_to_user
    from app.security.user_store import create_user, delete_user, get_user_organization_id

    _enable_auth(monkeypatch)

    admin_token = _create_token(
        user_id="user-001",
        companies=["ABC Pvt Ltd"],
    )
    org_id = get_user_organization_id("user-001") or "default"

    # Create temporary user for deletion test
    temp_user_id = "test-temp-user-del"
    delete_user(temp_user_id)
    create_user(
        user_id=temp_user_id,
        username="temp_del_user",
        password="TempPassword123!",
        companies=["ABC Pvt Ltd"],
        organization_id=org_id,
    )
    assign_role_to_user(temp_user_id, "user")

    with TestClient(app) as client:
        # Admin deletes temporary user
        resp = client.delete(
            f"/api/v1/admin/users/{temp_user_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        # Deleting non-existent user returns 404
        resp_404 = client.delete(
            f"/api/v1/admin/users/{temp_user_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp_404.status_code == 404

        # Admin cannot delete self
        resp_self = client.delete(
            "/api/v1/admin/users/user-001",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp_self.status_code == 403