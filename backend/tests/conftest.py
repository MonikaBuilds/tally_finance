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
