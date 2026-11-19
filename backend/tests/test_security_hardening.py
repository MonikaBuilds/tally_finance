"""
Security hardening tests: report-category permissions on every API route,
live account checks, debug endpoints, secrets defaults, login throttling
order and chatbot tool permission coverage.

Users here are synthetic (TEST FIXTURES); MySQL lookups are replaced so the
tests run offline. tests/live/ repeats the important cases against MySQL.
"""

from types import SimpleNamespace

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

import app.security.auth as auth
import app.security.permissions as permissions
from app.main import app
from app.security.auth import UserContext, get_current_user


# ------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------

def _dependency_names(route: APIRoute) -> set[str]:
    names = set()

    def walk(dependant):
        for dep in dependant.dependencies:
            if dep.call is not None:
                names.add(getattr(dep.call, "__name__", ""))
            walk(dep)

    walk(route.dependant)
    return names


def _api_routes(prefix: str):
    return [
        route for route in app.routes
        if isinstance(route, APIRoute) and route.path.startswith(prefix)
    ]


@pytest.fixture
def as_user(monkeypatch):
    """Sign in as a synthetic user holding only the given permissions."""

    def _sign_in(*granted: str, roles: tuple[str, ...] = ()):
        user = UserContext(
            user_id="qa-user",
            allowed_companies=("ABC Pvt Ltd",),
            organization_id="qa-org",
        )
        app.dependency_overrides[get_current_user] = lambda: user
        monkeypatch.setattr(
            permissions,
            "user_has_permission",
            lambda user_id, code: "superadmin" in roles or code in granted,
        )
        return user

    yield _sign_in
    app.dependency_overrides.pop(get_current_user, None)


# ------------------------------------------------------------------
# S1 - every report / dashboard / export route needs a permission
# ------------------------------------------------------------------

def _get_paths(prefix: str) -> list[str]:
    """Every GET path the API publishes under `prefix` (path params filled)."""
    import re

    paths = []
    for path, operations in app.openapi()["paths"].items():
        if path.startswith(prefix) and "get" in operations:
            paths.append(re.sub(r"\{[^}]+\}", "xlsx", path))
    return paths


def test_every_report_route_refuses_a_user_without_permissions(as_user):
    """Behavioural check of S1 across the whole report API surface."""
    as_user()  # signed in, company access, but NO permission category

    paths = _get_paths("/api/v1/reports/")
    assert len(paths) > 40

    client = TestClient(app)
    leaked = [
        (path, response.status_code)
        for path in paths
        for response in [client.get(path, params={"company_name": "ABC Pvt Ltd"})]
        if response.status_code != 403
    ]
    assert leaked == []


def test_every_dashboard_route_refuses_a_user_without_financial(as_user):
    as_user("inventory")

    paths = _get_paths("/api/v1/dashboard")
    assert paths

    client = TestClient(app)
    leaked = [
        (path, client.get(path, params={"company_name": "ABC Pvt Ltd"}).status_code)
        for path in paths
    ]
    assert all(code == 403 for _path, code in leaked), leaked


def test_inventory_routes_require_inventory_not_financial(as_user):
    as_user("financial")

    response = TestClient(app).get(
        "/api/v1/reports/stock-summary", params={"company_name": "ABC Pvt Ltd"}
    )
    assert response.status_code == 403


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/reports/profit-loss",
        "/api/v1/reports/balance-sheet",
        "/api/v1/reports/trial-balance",
        "/api/v1/reports/receivables",
        "/api/v1/reports/payables",
        "/api/v1/reports/day-book",
        "/api/v1/reports/profit-loss/export/xlsx",
        "/api/v1/dashboard/summary",
    ],
)
def test_inventory_only_user_is_refused_financial_data(as_user, path):
    as_user("inventory")

    response = TestClient(app).get(path, params={"company_name": "ABC Pvt Ltd"})

    assert response.status_code == 403
    assert "financial" in response.json()["detail"]


def test_financial_only_user_is_refused_inventory_data(as_user):
    as_user("financial")

    response = TestClient(app).get(
        "/api/v1/reports/stock-summary", params={"company_name": "ABC Pvt Ltd"}
    )

    assert response.status_code == 403
    assert "inventory" in response.json()["detail"]


def test_permitted_user_reaches_the_report(as_user, monkeypatch):
    from app.api import reports
    from app.cache.config import cache_settings

    as_user("financial")
    monkeypatch.setattr(cache_settings, "REDIS_CACHE_ENABLED", False)
    monkeypatch.setattr(reports, "_resolve_org_id", lambda user: "qa-org")

    async def fake_pl(**kwargs):
        return {"left": [], "right": [], "total_left": 0, "total_right": 0}

    monkeypatch.setattr(reports, "fetch_profit_loss", fake_pl)

    response = TestClient(app).get(
        "/api/v1/reports/profit-loss", params={"company_name": "ABC Pvt Ltd"}
    )
    assert response.status_code == 200


def test_unauthorized_company_still_refused_with_permission(as_user):
    as_user("financial", "inventory")

    response = TestClient(app).get(
        "/api/v1/reports/profit-loss", params={"company_name": "Other Company"}
    )
    assert response.status_code == 403


def test_debug_endpoints_hidden_by_default(as_user, monkeypatch):
    monkeypatch.delenv("TALLY_DEBUG_ENDPOINTS", raising=False)
    as_user("financial", roles=("superadmin",))

    client = TestClient(app)
    assert client.get("/api/v1/tally/debug/receivables").status_code == 404
    assert client.get("/api/v1/tally/debug/bill-allocations").status_code == 404


# ------------------------------------------------------------------
# S2 - account changes take effect immediately
# ------------------------------------------------------------------

def _token(companies=("ABC Pvt Ltd",)):
    return auth.create_access_token(
        user_id="qa-live-user", companies=companies, organization_id="qa-org"
    )


@pytest.fixture
def live_check(monkeypatch):
    monkeypatch.setattr(auth, "LIVE_USER_CHECK", True)
    auth.invalidate_user_state()
    state = {"value": None}
    monkeypatch.setattr(auth, "_fetch_user_state", lambda user_id: state["value"])
    yield state
    auth.invalidate_user_state()


def _request_with(token):
    return SimpleNamespace(cookies={"access_token": token}, headers={})


@pytest.mark.asyncio
async def test_deactivated_user_is_rejected_before_token_expiry(live_check):
    from fastapi import HTTPException

    live_check["value"] = SimpleNamespace(is_active=False, organization_id="qa-org", companies=("ABC Pvt Ltd",))

    with pytest.raises(HTTPException) as exc:
        await get_current_user(_request_with(_token()))
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_deleted_user_is_rejected(live_check):
    from fastapi import HTTPException

    live_check["value"] = None
    with pytest.raises(HTTPException) as exc:
        await get_current_user(_request_with(_token()))
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_removed_company_is_dropped_even_if_still_in_token(live_check):
    live_check["value"] = SimpleNamespace(is_active=True, organization_id="qa-org", companies=("New Co",))

    user = await get_current_user(_request_with(_token(companies=("ABC Pvt Ltd", "New Co"))))

    assert user.allowed_companies == ("New Co",)


@pytest.mark.asyncio
async def test_state_cache_is_cleared_on_account_change(live_check):
    live_check["value"] = SimpleNamespace(is_active=True, organization_id="qa-org", companies=("ABC Pvt Ltd",))
    await get_current_user(_request_with(_token()))

    live_check["value"] = SimpleNamespace(is_active=False, organization_id="qa-org", companies=())
    auth.invalidate_user_state("qa-live-user")  # what user_store calls on change

    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        await get_current_user(_request_with(_token()))


# ------------------------------------------------------------------
# Secrets and login
# ------------------------------------------------------------------

def test_database_has_no_builtin_password(monkeypatch):
    from app.security import db

    monkeypatch.delenv("DB_PASSWORD", raising=False)
    with pytest.raises(RuntimeError):
        db._connection_settings()


def test_bootstrap_never_uses_the_published_password(monkeypatch):
    from app.security import user_store

    class Cursor:
        def __init__(self):
            self.calls = 0

        def execute(self, *args):
            self.calls += 1

        def fetchone(self):
            return (0,) if self.calls == 1 else ("qa-org",)

        def close(self):
            pass

    class Connection:
        def cursor(self):
            return Cursor()

        def close(self):
            pass

    captured = {}

    def fake_create_user(**kwargs):
        captured.update(kwargs)
        return "qa-admin"

    monkeypatch.setattr(user_store, "get_connection", lambda: Connection())
    monkeypatch.setattr(user_store, "create_user", fake_create_user)
    monkeypatch.setattr(permissions, "assign_role_to_user", lambda *a: True)
    monkeypatch.setattr(permissions, "assign_permission_to_user", lambda *a: True)
    monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "Admin@2026!")

    user_store.bootstrap_initial_admin()

    assert captured["password"] != "Admin@2026!"
    assert len(captured["password"]) >= 12


def test_blocked_login_does_not_run_the_password_hash(monkeypatch):
    from app.api import auth as auth_api
    from app.security.login_limiter import login_rate_limiter

    calls = []
    monkeypatch.setattr(auth_api, "authenticate_user", lambda u, p: calls.append(u))
    monkeypatch.setattr(login_rate_limiter, "is_blocked", lambda host, user: True)

    response = TestClient(app).post(
        "/api/v1/auth/login", json={"username": "qa", "password": "x"}
    )

    assert response.status_code == 429
    assert calls == []


# ------------------------------------------------------------------
# Chatbot tool permissions
# ------------------------------------------------------------------

def test_every_chatbot_tool_has_a_permission_mapping():
    from app.chatbot.tool_registry import TOOL_DEFINITIONS, TOOL_FUNCTIONS

    registered = set(TOOL_FUNCTIONS) | {d["name"] for d in TOOL_DEFINITIONS}
    unmapped = sorted(registered - set(permissions.DEFAULT_TOOL_PERMISSIONS))

    assert unmapped == []


def test_day_book_is_a_financial_tool():
    assert permissions.DEFAULT_TOOL_PERMISSIONS["get_day_book"] == "financial"


def test_openrouter_fallback_is_off_by_default(monkeypatch):
    import importlib
    import app.chatbot.gemini_client as gemini_client

    monkeypatch.delenv("OPENROUTER_FALLBACK_ENABLED", raising=False)
    reloaded = importlib.reload(gemini_client)
    try:
        assert reloaded.OPENROUTER_FALLBACK_ENABLED is False
    finally:
        importlib.reload(gemini_client)
