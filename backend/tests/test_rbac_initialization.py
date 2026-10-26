"""
Test suite verifying automated RBAC table initialization and baseline seeding.
"""

import pytest
from app.security.db import get_connection
from app.security.permissions import (
    DEFAULT_PERMISSIONS,
    DEFAULT_ROLES,
    DEFAULT_TOOL_PERMISSIONS,
    get_all_permissions,
    get_all_roles,
    get_required_permission,
    initialize_rbac_store,
    role_exists,
)


def test_initialize_rbac_store_creates_tables_and_seeds_data():
    """Verify that initialize_rbac_store creates all 5 tables and seeds roles, permissions, tools."""
    # 1. Execute initialization
    initialize_rbac_store()

    # 2. Verify tables exist
    connection = get_connection()
    cursor = connection.cursor()
    try:
        cursor.execute("SHOW TABLES")
        tables = {row[0].lower() for row in cursor.fetchall()}
        for expected_table in ["roles", "permissions", "tool_permissions", "user_roles", "user_permissions"]:
            assert expected_table in tables, f"Table {expected_table} was not created by initialize_rbac_store!"
    finally:
        cursor.close()
        connection.close()

    # 3. Verify roles exist
    for role_name in DEFAULT_ROLES:
        assert role_exists(role_name) is True, f"Role {role_name} was not seeded!"

    all_roles = get_all_roles()
    role_names = {r["role_name"] for r in all_roles}
    assert {"admin", "user", "superadmin"}.issubset(role_names)

    # 4. Verify permissions exist
    all_perms = get_all_permissions()
    perm_codes = {p["permission_code"] for p in all_perms}
    for perm_tuple in DEFAULT_PERMISSIONS:
        assert perm_tuple[0] in perm_codes, f"Permission {perm_tuple[0]} was not seeded!"

    # 5. Verify all 70 chatbot tools are mapped to their correct permissions
    for tool_name, expected_perm in DEFAULT_TOOL_PERMISSIONS.items():
        mapped_perm = get_required_permission(tool_name)
        assert mapped_perm == expected_perm, (
            f"Tool {tool_name} was expected to map to {expected_perm}, but got {mapped_perm}!"
        )


def test_initialize_rbac_store_is_idempotent():
    """Verify that re-running initialize_rbac_store does not duplicate or corrupt data."""
    # Run once
    initialize_rbac_store()
    initial_roles = get_all_roles()
    initial_perms = get_all_permissions()

    # Run again
    initialize_rbac_store()
    subsequent_roles = get_all_roles()
    subsequent_perms = get_all_permissions()

    assert len(initial_roles) == len(subsequent_roles)
    assert len(initial_perms) == len(subsequent_perms)


def test_initialize_organization_store_seeds_defaults():
    """Verify that initialize_organization_store creates organizations and seeds defaults."""
    from app.security.organization_store import initialize_organization_store, get_organization

    initialize_organization_store()

    infintrix_org = get_organization("e7747b1f-36c9-4ea1-85d9-965f5c55d679")
    assert infintrix_org is not None
    assert infintrix_org.organization_name == "Infintrix"
    assert infintrix_org.is_active is True

    default_org = get_organization("default")
    assert default_org is not None
    assert default_org.organization_name == "Default Organization"


def test_bootstrap_initial_admin_skips_when_users_exist():
    """Verify that bootstrap_initial_admin safely returns None when users already exist in DB."""
    from app.security.user_store import bootstrap_initial_admin

    result = bootstrap_initial_admin()
    # Since test DB already contains users, bootstrap must skip
    assert result is None


def test_bootstrap_initial_admin_empty_db_simulation(monkeypatch):
    """Verify bootstrap_initial_admin creates user, assigns superadmin/admin roles and all permissions on empty DB."""
    from unittest.mock import MagicMock
    from app.security import user_store

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    # Return count = 0, then org row
    mock_cursor.fetchone.side_effect = [(0,), ("e7747b1f-36c9-4ea1-85d9-965f5c55d679",)]
    mock_conn.cursor.return_value = mock_cursor

    created_users = []
    assigned_roles = []
    assigned_permissions = []

    def mock_create_user(*, username, password, companies, organization_id):
        created_users.append((username, password, companies, organization_id))
        return "synthetic-bootstrapped-admin-id"

    def mock_assign_role(user_id, role_name):
        assigned_roles.append((user_id, role_name))
        return True

    def mock_assign_perm(user_id, perm_code):
        assigned_permissions.append((user_id, perm_code))
        return True

    monkeypatch.setattr(user_store, "get_connection", lambda: mock_conn)
    monkeypatch.setattr(user_store, "create_user", mock_create_user)
    monkeypatch.setattr("app.security.permissions.assign_role_to_user", mock_assign_role)
    monkeypatch.setattr("app.security.permissions.assign_permission_to_user", mock_assign_perm)

    admin_id = user_store.bootstrap_initial_admin()
    assert admin_id == "synthetic-bootstrapped-admin-id"
    assert len(created_users) == 1
    assert created_users[0][0] == "admin"
    assert "ABC Pvt Ltd" in created_users[0][2]
    assert ("synthetic-bootstrapped-admin-id", "superadmin") in assigned_roles
    assert ("synthetic-bootstrapped-admin-id", "admin") in assigned_roles
    for perm in ["financial", "inventory", "banking", "tax"]:
        assert ("synthetic-bootstrapped-admin-id", perm) in assigned_permissions


def test_cleanup_expired_sessions_prunes_dead_sessions():
    """Verify that cleanup_expired_sessions removes expired and old revoked sessions while keeping active ones."""
    from datetime import datetime, timedelta, timezone
    import uuid
    from app.security.refresh_store import cleanup_expired_sessions, initialize_refresh_store

    initialize_refresh_store()

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        # Find a valid user in DB to attach test sessions to
        cursor.execute("SELECT user_id FROM users LIMIT 1")
        user_row = cursor.fetchone()
        assert user_row is not None, "At least one user must exist in DB for testing session cleanup"
        test_user_id = user_row["user_id"]

        now = datetime.now(timezone.utc)
        expired_id = f"test-exp-{uuid.uuid4()}"
        revoked_old_id = f"test-rev-{uuid.uuid4()}"
        active_id = f"test-act-{uuid.uuid4()}"

        cursor.execute(
            """
            INSERT INTO refresh_sessions (session_id, user_id, token_hash, expires_at, revoked_at)
            VALUES 
                (%s, %s, %s, %s, NULL),
                (%s, %s, %s, %s, %s),
                (%s, %s, %s, %s, NULL)
            """,
            (
                expired_id, test_user_id, f"hash_{expired_id}"[:64], now - timedelta(days=2),
                revoked_old_id, test_user_id, f"hash_{revoked_old_id}"[:64], now + timedelta(days=10), now - timedelta(days=10),
                active_id, test_user_id, f"hash_{active_id}"[:64], now + timedelta(days=7),
            )
        )
        connection.commit()

        # Run cleanup with 7-day retention
        purged = cleanup_expired_sessions(retention_days=7)
        assert purged >= 2, f"Expected at least 2 sessions to be purged, got {purged}"

        # Verify active session still exists
        cursor.execute("SELECT session_id FROM refresh_sessions WHERE session_id = %s", (active_id,))
        assert cursor.fetchone() is not None, "Active session was incorrectly deleted!"

        # Verify expired session was purged
        cursor.execute("SELECT session_id FROM refresh_sessions WHERE session_id = %s", (expired_id,))
        assert cursor.fetchone() is None, "Expired session was not purged!"

        # Verify old revoked session was purged
        cursor.execute("SELECT session_id FROM refresh_sessions WHERE session_id = %s", (revoked_old_id,))
        assert cursor.fetchone() is None, "Old revoked session was not purged!"

    finally:
        # Cleanup active test session
        cursor.execute("DELETE FROM refresh_sessions WHERE session_id = %s", (active_id,))
        connection.commit()
        cursor.close()
        connection.close()


def test_mysql_session_timezone_is_utc():
    """Verify that MySQL connections are explicitly set to UTC (+00:00)."""
    connection = get_connection()
    cursor = connection.cursor()
    try:
        cursor.execute("SELECT @@session.time_zone")
        tz = cursor.fetchone()[0]
        assert tz == "+00:00", f"Expected MySQL session timezone '+00:00', got '{tz}'"
    finally:
        cursor.close()
        connection.close()


def test_revoke_all_user_sessions():
    """Verify that revoke_all_user_sessions invalidates all active sessions for a user."""
    from datetime import datetime, timedelta, timezone
    import uuid
    from app.security.refresh_store import (
        create_refresh_session,
        generate_refresh_token,
        revoke_all_user_sessions,
    )

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT user_id FROM users LIMIT 1")
        test_user_id = cursor.fetchone()["user_id"]

        token1 = generate_refresh_token()
        token2 = generate_refresh_token()
        expires = datetime.now(timezone.utc) + timedelta(days=7)

        create_refresh_session(user_id=test_user_id, token=token1, expires_at=expires)
        create_refresh_session(user_id=test_user_id, token=token2, expires_at=expires)

        revoked_count = revoke_all_user_sessions(test_user_id)
        assert revoked_count >= 2

        # Verify no active sessions remain for this user
        connection.commit()
        cursor.execute(
            "SELECT COUNT(*) FROM refresh_sessions WHERE user_id = %s AND revoked_at IS NULL",
            (test_user_id,),
        )
        active_remaining = cursor.fetchone()["COUNT(*)"]
        assert active_remaining == 0
    finally:
        cursor.close()
        connection.close()


def test_refresh_token_reuse_detection_revokes_all_sessions():
    """Verify OAuth 2.1 RFC 6819 token reuse detection: replaying a revoked token invalidates all user sessions."""
    from datetime import datetime, timedelta, timezone
    from app.security.refresh_store import (
        create_refresh_session,
        generate_refresh_token,
        rotate_refresh_session,
        get_refresh_session,
    )

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT user_id FROM users LIMIT 1")
        test_user_id = cursor.fetchone()["user_id"]

        token_a = generate_refresh_token()
        token_b = generate_refresh_token()
        token_c = generate_refresh_token()
        expires = datetime.now(timezone.utc) + timedelta(days=7)

        # 1. Create initial session A
        create_refresh_session(user_id=test_user_id, token=token_a, expires_at=expires)

        # 2. Legitimate client rotates A -> B
        rotated_b = rotate_refresh_session(old_token=token_a, new_token=token_b, expires_at=expires)
        assert rotated_b is not None

        # Session B is active, Session A is revoked
        assert get_refresh_session(token_b) is not None
        assert get_refresh_session(token_a) is None

        # 3. Attacker replays revoked token A!
        replay_result = rotate_refresh_session(old_token=token_a, new_token=token_c, expires_at=expires)
        # Replay must be rejected
        assert replay_result is None

        # 4. Critical: Replay MUST have triggered automatic compromise invalidation of session B!
        session_b_after = get_refresh_session(token_b)
        assert session_b_after is None, "Session B should have been revoked after token A reuse detection!"

    finally:
        cursor.close()
        connection.close()


def test_deactivating_user_revokes_active_sessions():
    """Verify that deactivating a user immediately revokes all their active sessions."""
    from datetime import datetime, timedelta, timezone
    from app.security.refresh_store import (
        create_refresh_session,
        generate_refresh_token,
        get_refresh_session,
    )
    from app.security.user_store import set_user_active_status

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT user_id, is_active FROM users LIMIT 1")
        row = cursor.fetchone()
        test_user_id = row["user_id"]
        original_status = row["is_active"]

        token = generate_refresh_token()
        expires = datetime.now(timezone.utc) + timedelta(days=7)
        create_refresh_session(user_id=test_user_id, token=token, expires_at=expires)

        assert get_refresh_session(token) is not None

        # Deactivate user
        set_user_active_status(test_user_id, is_active=False)

        # Session must now be revoked
        assert get_refresh_session(token) is None

    finally:
        # Restore active status
        set_user_active_status(test_user_id, is_active=bool(original_status))
        cursor.close()
        connection.close()



