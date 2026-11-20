"""
Shared test fixtures.

Many API tests use synthetic users that exist only inside a test JWT (no
MySQL row). Production now re-checks every request against MySQL (account
active, current companies) and checks the report permission category.
Those tests are about caching / outage / report behaviour, not account
state, so they opt in to `token_only_auth`, which restores the token-only
behaviour for the duration of the test. The live checks themselves are
covered by tests/test_security_hardening.py.
"""

import pytest


# The admin/RBAC and protected-chat tests sign in as these two accounts but
# nothing in the application seeds them. They are created here so the suite
# runs on a clean database, and removed again unless they existed already.
_SEED_USERS = {
    # Mirrors bootstrap_initial_admin: the manager account holds both roles,
    # so it can see, promote and demote the admin/user accounts it manages.
    "user-001": {"username": "user1", "roles": ("superadmin", "admin")},
    "user-002": {"username": "user2", "roles": ("user",)},
}
_SEED_PASSWORD = "password"
_SEED_COMPANY = "ABC Pvt Ltd"


def _delete_seed_user(user_id: str, username: str) -> None:
    from app.security.db import get_connection

    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            "DELETE FROM users WHERE user_id = %s OR username = %s",
            (user_id, username),
        )
        connection.commit()
    finally:
        cursor.close()
        connection.close()


@pytest.fixture(scope="session", autouse=True)
def seed_test_users():
    """
    Create the two accounts the admin / chat tests authenticate as.

    Session-scoped and automatic: the assertions read live MySQL state, so
    the rows have to exist for the whole run. Accounts that were already
    present are left untouched and are not removed afterwards.
    """
    from app.security.db import get_connection
    from app.security.organization_store import (
        initialize_organization_store,
    )
    from app.security.permissions import (
        assign_permission_to_user,
        assign_role_to_user,
        initialize_rbac_store,
    )
    from app.security.user_store import (
        create_user,
        initialize_user_store,
        set_user_active_status,
        update_user_password,
    )

    # The schema must exist before anything can be inserted.
    initialize_organization_store()
    initialize_user_store()
    initialize_rbac_store()

    connection = get_connection()
    cursor = connection.cursor()
    try:
        cursor.execute("SELECT organization_id FROM organizations LIMIT 1")
        row = cursor.fetchone()
    finally:
        cursor.close()
        connection.close()

    org_id = row[0] if row else "default"

    created = []

    for user_id, config in _SEED_USERS.items():
        existing = None
        connection = get_connection()
        cursor = connection.cursor()
        try:
            cursor.execute(
                "SELECT user_id FROM users WHERE user_id = %s OR username = %s LIMIT 1",
                (user_id, config["username"]),
            )
            existing = cursor.fetchone()
        finally:
            cursor.close()
            connection.close()

        if existing is not None:
            continue

        _delete_seed_user(user_id, config["username"])

        create_user(
            user_id=user_id,
            username=config["username"],
            password=_SEED_PASSWORD,
            companies=[_SEED_COMPANY],
            organization_id=org_id,
        )

        for role_name in config["roles"]:
            assign_role_to_user(user_id, role_name)

        if "superadmin" in config["roles"] or "admin" in config["roles"]:
            for permission in ("financial", "inventory", "banking", "tax"):
                assign_permission_to_user(user_id, permission)
        else:
            for permission in ("financial", "inventory"):
                assign_permission_to_user(user_id, permission)

        created.append((user_id, config["username"]))

    # A previous test may have left these accounts deactivated.
    for user_id in _SEED_USERS:
        set_user_active_status(user_id, True)

    # The admin/user password tests change this password and restore it.
    for user_id in _SEED_USERS:
        update_user_password(user_id=user_id, new_password=_SEED_PASSWORD)

    yield

    for user_id, username in created:
        _delete_seed_user(user_id, username)


@pytest.fixture
def token_only_auth(monkeypatch):
    """Trust the test JWT's claims and grant every report permission."""
    import app.security.auth as auth
    import app.security.permissions as permissions

    monkeypatch.setattr(auth, "LIVE_USER_CHECK", False)
    monkeypatch.setattr(
        permissions,
        "user_has_permission",
        lambda user_id, permission_code: True,
    )
    auth.invalidate_user_state()
    yield
    auth.invalidate_user_state()


@pytest.fixture
def signed_in_superadmin(token_only_auth):
    """
    For tests that call the real app without logging in: act as a signed-in
    user with access to every company and every permission.
    """
    from app.main import app
    from app.security.auth import UserContext, get_current_user

    user = UserContext(
        user_id="test-superadmin",
        allowed_companies=("*",),
        organization_id="test-org",
    )

    # These API tests mock the Tally fetchers; a real local Redis must not
    # serve them data cached by an earlier test.
    from app.cache.config import cache_settings

    monkeypatch_cache = pytest.MonkeyPatch()
    monkeypatch_cache.setattr(cache_settings, "REDIS_CACHE_ENABLED", False)

    app.dependency_overrides[get_current_user] = lambda: user

    from app.api import dashboard, reports

    original_reports = getattr(reports, "_resolve_org_id", None)
    original_dashboard = getattr(dashboard, "_resolve_org_id", None)
    reports._resolve_org_id = lambda current_user: "test-org"
    dashboard._resolve_org_id = lambda current_user: "test-org"

    yield user

    monkeypatch_cache.undo()
    app.dependency_overrides.pop(get_current_user, None)
    if original_reports is not None:
        reports._resolve_org_id = original_reports
    if original_dashboard is not None:
        dashboard._resolve_org_id = original_dashboard
