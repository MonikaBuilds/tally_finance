"""
End-to-end tests for Tally outage fallback and resilience flow across all cached APIs.

Covers:
1. Live request: exact response stored in Redis with fresh provenance
2. Cache hit: served directly from Redis without upstream Tally query
3. Stale fallback: recognized Tally connectivity failures return retained Redis data with clear stale provenance
4. No-cache: connectivity failures with no prior cached data fail cleanly (502 / safe error, no hallucination)
5. Redis failure: fail-open resilience when Redis is disabled/unreachable, falling back to live Tally
6. Tally recovery: after outage, fresh data replaces stale cache and updates provenance
7. Never serve stale for: authorization, RBAC, parser, business validation, or application errors
8. Tenant organization and company isolation preserved under outage conditions
"""

import asyncio
from datetime import date
from unittest.mock import AsyncMock, patch

import httpx
import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import chat, dashboard, tally
from app.cache import (
    CacheResult,
    TallyCacheManager,
    build_cache_key,
    cache_manager,
    cache_settings,
)
from app.security.config import AuthSettings


TEST_SECRET = "test-secret-key-that-is-long-enough-32-chars-min"

TEST_AUTH_SETTINGS = AuthSettings(
    auth_enabled=True,
    jwt_secret=TEST_SECRET,
    jwt_algorithm="HS256",
    jwt_expire_minutes=60,
    access_token_cookie_name="access_token",
    refresh_token_expire_days=7,
    refresh_token_cookie_name="refresh_token",
    refresh_cookie_path="/",
    cookie_secure=False,
    cookie_samesite="lax",
    cookie_path="/",
    cors_allowed_origins=("*",),
    csrf_cookie_name="csrf",
    csrf_header_name="x-csrf-token",
)

TEST_USER_ORGS = {
    "user-1": "e2e_co_org",
    "user-no-cache": "no_cache_org",
    "user-dash": "e2e_dash_org",
    "user-no-dash": "no_cache_dash_org",
    "user-monthly": "e2e_month_org",
    "user-no-month": "no_cache_month_org",
    "user-a": "tenant_alpha",
    "user-b": "tenant_beta",
    "user-valid": "e2e_dash_org",
    "user-x": "e2e_dash_org",
}


@pytest.fixture(autouse=True)
def mock_user_org_resolution():
    """Mock tenant resolution so synthetic test users resolve securely without touching production database."""
    resolver = lambda uid: TEST_USER_ORGS.get(uid, f"org_{uid}")
    with patch("app.security.user_store.get_user_organization_id", side_effect=resolver), \
         patch("app.api.chat.get_user_organization_id", side_effect=resolver):
        yield



def create_test_app() -> FastAPI:
    """Create a FastAPI application with all cached routers mounted."""
    app = FastAPI()
    app.include_router(tally.router, prefix="/api/v1/tally")
    app.include_router(dashboard.router, prefix="/api/v1/dashboard")
    app.include_router(chat.router, prefix="/api/v1")
    return app


def create_auth_token(user_id: str, companies: list[str]) -> str:
    """Create a signed JWT token for test authentication."""
    return jwt.encode(
        {"sub": user_id, "companies": companies},
        TEST_SECRET,
        algorithm="HS256",
    )


# ============================================================
# 1. TALLY COMPANIES ENDPOINT OUTAGE LIFECYCLE
# ============================================================

@pytest.mark.asyncio
async def test_companies_outage_fallback_and_recovery_lifecycle():
    """
    Complete lifecycle for GET /api/v1/tally/companies:
    Live -> Cache-Hit -> Outage (Stale Fallback) -> Tally Recovery -> Fresh Hit
    """
    app = create_test_app()
    token = create_auth_token("user-1", ["Alpha Corp", "Beta LLC"])
    org_id = "e2e_co_org"

    await cache_manager.invalidate_prefix(f"tally:cache:{org_id}")

    raw_companies_initial = [{"name": "Alpha Corp"}, {"name": "Beta LLC"}]
    raw_companies_recovered = [{"name": "Alpha Corp"}, {"name": "Beta LLC"}, {"name": "Gamma Inc"}]

    with patch("app.security.auth.get_auth_settings", return_value=TEST_AUTH_SETTINGS):
        client = TestClient(app)
        client.cookies.set("access_token", token)

        # -------------------------------------------------------------
        # STEP 1: Live request -> Tally succeeds, exact response cached
        # -------------------------------------------------------------
        with patch("app.tally.service.client.send_xml", AsyncMock(return_value="<ENVELOPE></ENVELOPE>")):
            with patch("app.tally.service.parse_companies", return_value={"companies": raw_companies_initial}):
                res1 = client.get("/api/v1/tally/companies", params={"force_refresh": "true"})
                assert res1.status_code == 200
                data1 = res1.json()
                assert data1["success"] is True
                assert data1["source"] == "tally"
                assert data1["is_stale"] is False
                assert data1["cached_at"] is not None
                assert len(data1["companies"]) == 2

        # -------------------------------------------------------------
        # STEP 2: Cache Hit -> Redis returns data without calling Tally
        # -------------------------------------------------------------
        with patch("app.tally.service.client.send_xml", AsyncMock(side_effect=Exception("Tally should not be queried on cache hit"))):
            res2 = client.get("/api/v1/tally/companies")
            assert res2.status_code == 200
            data2 = res2.json()
            assert data2["success"] is True
            assert data2["source"] == "cache"
            assert data2["is_stale"] is False
            assert data2["cached_at"] == data1["cached_at"]
            assert data2["companies"] == data1["companies"]

        # -------------------------------------------------------------
        # STEP 3: Outage -> Tally fails with ConnectError -> Stale Fallback
        # -------------------------------------------------------------
        with patch("app.tally.service.client.send_xml", AsyncMock(side_effect=httpx.ConnectError("Tally service offline"))):
            res3 = client.get("/api/v1/tally/companies", params={"force_refresh": "true"})
            assert res3.status_code == 200
            data3 = res3.json()
            assert data3["success"] is True
            assert data3["source"] == "stale_cache"
            assert data3["is_stale"] is True
            assert data3["cached_at"] == data1["cached_at"]
            assert data3["companies"] == data1["companies"]

        # -------------------------------------------------------------
        # STEP 4: Tally Recovery -> Tally comes back online, cache refreshed
        # -------------------------------------------------------------
        with patch("app.tally.service.client.send_xml", AsyncMock(return_value="<ENVELOPE></ENVELOPE>")):
            with patch("app.tally.service.parse_companies", return_value={"companies": raw_companies_recovered}):
                # user-1 has access to Alpha Corp and Beta LLC
                res4 = client.get("/api/v1/tally/companies", params={"force_refresh": "true"})
                assert res4.status_code == 200
                data4 = res4.json()
                assert data4["success"] is True
                assert data4["source"] == "tally"
                assert data4["is_stale"] is False
                assert data4["cached_at"] != data1["cached_at"]

        # -------------------------------------------------------------
        # STEP 5: Subsequent fresh cache hit with newly cached data
        # -------------------------------------------------------------
        with patch("app.tally.service.client.send_xml", AsyncMock(side_effect=Exception("Should hit fresh cache"))):
            res5 = client.get("/api/v1/tally/companies")
            assert res5.status_code == 200
            data5 = res5.json()
            assert data5["success"] is True
            assert data5["source"] == "cache"
            assert data5["is_stale"] is False
            assert data5["cached_at"] == data4["cached_at"]


@pytest.mark.asyncio
async def test_companies_no_cache_during_outage_fails_cleanly():
    """When cache is empty and Tally has an outage, endpoint returns 502 without hallucinating."""
    app = create_test_app()
    token = create_auth_token("user-no-cache", ["Alpha Corp"])
    org_id = "no_cache_org"

    await cache_manager.invalidate_prefix(f"tally:cache:{org_id}")

    with patch("app.security.auth.get_auth_settings", return_value=TEST_AUTH_SETTINGS):
        client = TestClient(app)
        client.cookies.set("access_token", token)

        with patch("app.tally.service.client.send_xml", AsyncMock(side_effect=httpx.ConnectTimeout("Tally timeout"))):
            res = client.get("/api/v1/tally/companies")
            assert res.status_code == 502
            assert "Unable to fetch companies" in res.json()["detail"]


@pytest.mark.asyncio
async def test_companies_redis_failure_fails_open_to_live_tally():
    """When Redis is unavailable, endpoint fails open: queries Tally and returns live data."""
    app = create_test_app()
    token = create_auth_token("user-1", ["Alpha Corp"])
    raw_companies = [{"name": "Alpha Corp"}]

    with patch("app.security.auth.get_auth_settings", return_value=TEST_AUTH_SETTINGS):
        client = TestClient(app)
        client.cookies.set("access_token", token)

        # Simulate Redis connection failure
        with patch("app.cache.manager.get_redis_client", AsyncMock(return_value=None)):
            with patch("app.tally.service.client.send_xml", AsyncMock(return_value="<ENVELOPE></ENVELOPE>")):
                with patch("app.tally.service.parse_companies", return_value={"companies": raw_companies}):
                    res = client.get("/api/v1/tally/companies")
                    assert res.status_code == 200
                    data = res.json()
                    assert data["success"] is True
                    assert data["source"] == "tally"
                    assert data["is_stale"] is False
                    assert len(data["companies"]) == 1


# ============================================================
# 2. DASHBOARD SUMMARY ENDPOINT OUTAGE LIFECYCLE
# ============================================================

@pytest.mark.asyncio
async def test_dashboard_summary_outage_fallback_and_recovery_lifecycle():
    """
    Complete lifecycle for GET /api/v1/dashboard/summary:
    Live -> Cache-Hit -> Outage (Stale Fallback) -> Tally Recovery -> Fresh Hit
    """
    app = create_test_app()
    token = create_auth_token("user-dash", ["Demo Co"])
    org_id = "e2e_dash_org"

    await cache_manager.invalidate_prefix(f"tally:cache:{org_id}")

    initial_summary = {
        "revenue": 1250000.0,
        "expense": 950000.0,
        "net_profit": 300000.0,
        "cash_balance": 150000.0,
    }
    recovered_summary = {
        "revenue": 1400000.0,
        "expense": 1000000.0,
        "net_profit": 400000.0,
        "cash_balance": 200000.0,
    }

    with patch("app.security.auth.get_auth_settings", return_value=TEST_AUTH_SETTINGS):
        client = TestClient(app)
        client.cookies.set("access_token", token)

        # -------------------------------------------------------------
        # STEP 1: Live request -> Tally succeeds, exact response cached
        # -------------------------------------------------------------
        with patch("app.api.dashboard.fetch_dashboard_reports", AsyncMock(return_value=({"pl": {}}, {}))):
            with patch("app.api.dashboard.map_dashboard_summary", return_value=dict(initial_summary)):
                res1 = client.get(
                    "/api/v1/dashboard/summary",
                    params={"company_name": "Demo Co", "force_refresh": "true"},
                )
                assert res1.status_code == 200
                data1 = res1.json()
                assert data1["success"] is True
                assert data1["source"] == "tally"
                assert data1["is_stale"] is False
                assert data1["data"]["revenue"] == 1250000.0

        # -------------------------------------------------------------
        # STEP 2: Cache Hit -> Redis returns data without calling Tally
        # -------------------------------------------------------------
        with patch("app.api.dashboard.fetch_dashboard_reports", AsyncMock(side_effect=Exception("Should hit cache"))):
            res2 = client.get(
                "/api/v1/dashboard/summary",
                params={"company_name": "Demo Co"},
            )
            assert res2.status_code == 200
            data2 = res2.json()
            assert data2["success"] is True
            assert data2["source"] == "cache"
            assert data2["is_stale"] is False
            assert data2["data"]["revenue"] == 1250000.0
            assert data2["cached_at"] == data1["cached_at"]

        # -------------------------------------------------------------
        # STEP 3: Outage -> Tally fails with ConnectError -> Stale Fallback
        # -------------------------------------------------------------
        with patch("app.api.dashboard.fetch_dashboard_reports", AsyncMock(side_effect=httpx.ConnectError("Tally offline"))):
            res3 = client.get(
                "/api/v1/dashboard/summary",
                params={"company_name": "Demo Co", "force_refresh": "true"},
            )
            assert res3.status_code == 200
            data3 = res3.json()
            assert data3["success"] is True
            assert data3["source"] == "stale_cache"
            assert data3["is_stale"] is True
            assert data3["data"]["revenue"] == 1250000.0
            assert data3["cached_at"] == data1["cached_at"]

        # -------------------------------------------------------------
        # STEP 4: Tally Recovery -> Fresh data updates Redis cache
        # -------------------------------------------------------------
        with patch("app.api.dashboard.fetch_dashboard_reports", AsyncMock(return_value=({"pl": {}}, {}))):
            with patch("app.api.dashboard.map_dashboard_summary", return_value=dict(recovered_summary)):
                res4 = client.get(
                    "/api/v1/dashboard/summary",
                    params={"company_name": "Demo Co", "force_refresh": "true"},
                )
                assert res4.status_code == 200
                data4 = res4.json()
                assert data4["success"] is True
                assert data4["source"] == "tally"
                assert data4["is_stale"] is False
                assert data4["data"]["revenue"] == 1400000.0
                assert data4["cached_at"] != data1["cached_at"]

        # -------------------------------------------------------------
        # STEP 5: Fresh cache hit with updated data
        # -------------------------------------------------------------
        with patch("app.api.dashboard.fetch_dashboard_reports", AsyncMock(side_effect=Exception("Should hit fresh cache"))):
            res5 = client.get(
                "/api/v1/dashboard/summary",
                params={"company_name": "Demo Co"},
            )
            assert res5.status_code == 200
            data5 = res5.json()
            assert data5["success"] is True
            assert data5["source"] == "cache"
            assert data5["is_stale"] is False
            assert data5["data"]["revenue"] == 1400000.0


@pytest.mark.asyncio
async def test_dashboard_summary_no_cache_during_outage_fails_cleanly():
    """Empty cache during Tally outage returns 502 Bad Gateway without fabricating values."""
    app = create_test_app()
    token = create_auth_token("user-no-dash", ["Demo Co"])
    org_id = "no_cache_dash_org"

    await cache_manager.invalidate_prefix(f"tally:cache:{org_id}")

    with patch("app.security.auth.get_auth_settings", return_value=TEST_AUTH_SETTINGS):
        client = TestClient(app)
        client.cookies.set("access_token", token)

        with patch("app.api.dashboard.fetch_dashboard_reports", AsyncMock(side_effect=httpx.ConnectTimeout("Tally timed out"))):
            res = client.get(
                "/api/v1/dashboard/summary",
                params={"company_name": "Demo Co"},
            )
            assert res.status_code == 502
            assert "Unable to read dashboard reports" in res.json()["detail"]


@pytest.mark.asyncio
async def test_dashboard_summary_redis_failure_fails_open():
    """When Redis fails, GET /dashboard/summary still succeeds live from Tally."""
    app = create_test_app()
    token = create_auth_token("user-dash", ["Demo Co"])
    summary = {"revenue": 500000.0, "expense": 300000.0, "net_profit": 200000.0}

    with patch("app.security.auth.get_auth_settings", return_value=TEST_AUTH_SETTINGS):
        client = TestClient(app)
        client.cookies.set("access_token", token)

        with patch("app.cache.manager.get_redis_client", AsyncMock(return_value=None)):
            with patch("app.api.dashboard.fetch_dashboard_reports", AsyncMock(return_value=({"pl": {}}, {}))):
                with patch("app.api.dashboard.map_dashboard_summary", return_value=dict(summary)):
                    res = client.get(
                        "/api/v1/dashboard/summary",
                        params={"company_name": "Demo Co"},
                    )
                    assert res.status_code == 200
                    data = res.json()
                    assert data["success"] is True
                    assert data["source"] == "tally"
                    assert data["data"]["revenue"] == 500000.0


# ============================================================
# 3. DASHBOARD MONTHLY ENDPOINT OUTAGE LIFECYCLE
# ============================================================

@pytest.mark.asyncio
async def test_dashboard_monthly_outage_fallback_and_recovery_lifecycle():
    """
    Complete lifecycle for GET /api/v1/dashboard/monthly:
    Live -> Cache-Hit -> Outage (Stale Fallback) -> Tally Recovery -> Fresh Hit
    """
    app = create_test_app()
    token = create_auth_token("user-monthly", ["Demo Co"])
    org_id = "e2e_month_org"

    await cache_manager.invalidate_prefix(f"tally:cache:{org_id}")

    series_initial = [{"month": "2024-04", "income": 100000.0, "expense": 80000.0}]
    series_recovered = [{"month": "2024-04", "income": 120000.0, "expense": 90000.0}]

    with patch("app.security.auth.get_auth_settings", return_value=TEST_AUTH_SETTINGS):
        client = TestClient(app)
        client.cookies.set("access_token", token)

        # 1. Live fetch
        with patch("app.api.dashboard._fetch_monthly_income_expense_series", AsyncMock(return_value=series_initial)):
            res1 = client.get(
                "/api/v1/dashboard/monthly",
                params={"company_name": "Demo Co", "force_refresh": "true"},
            )
            assert res1.status_code == 200
            data1 = res1.json()
            assert data1["success"] is True
            assert data1["source"] == "tally"
            assert data1["is_stale"] is False
            assert data1["data"]["income_vs_expense"] == series_initial

        # 2. Cache Hit
        with patch("app.api.dashboard._fetch_monthly_income_expense_series", AsyncMock(side_effect=Exception("Should hit cache"))):
            res2 = client.get(
                "/api/v1/dashboard/monthly",
                params={"company_name": "Demo Co"},
            )
            assert res2.status_code == 200
            data2 = res2.json()
            assert data2["success"] is True
            assert data2["source"] == "cache"
            assert data2["is_stale"] is False
            assert data2["data"]["income_vs_expense"] == series_initial

        # 3. Outage -> Stale Fallback
        with patch("app.api.dashboard._fetch_monthly_income_expense_series", AsyncMock(side_effect=httpx.ConnectError("Tally down"))):
            res3 = client.get(
                "/api/v1/dashboard/monthly",
                params={"company_name": "Demo Co", "force_refresh": "true"},
            )
            assert res3.status_code == 200
            data3 = res3.json()
            assert data3["success"] is True
            assert data3["source"] == "stale_cache"
            assert data3["is_stale"] is True
            assert data3["data"]["income_vs_expense"] == series_initial

        # 4. Recovery
        with patch("app.api.dashboard._fetch_monthly_income_expense_series", AsyncMock(return_value=series_recovered)):
            res4 = client.get(
                "/api/v1/dashboard/monthly",
                params={"company_name": "Demo Co", "force_refresh": "true"},
            )
            assert res4.status_code == 200
            data4 = res4.json()
            assert data4["success"] is True
            assert data4["source"] == "tally"
            assert data4["is_stale"] is False
            assert data4["data"]["income_vs_expense"] == series_recovered


@pytest.mark.asyncio
async def test_dashboard_monthly_no_cache_during_outage_fails_cleanly():
    """Empty cache during Tally outage on /monthly returns 502 Bad Gateway."""
    app = create_test_app()
    token = create_auth_token("user-no-month", ["Demo Co"])
    org_id = "no_cache_month_org"

    await cache_manager.invalidate_prefix(f"tally:cache:{org_id}")

    with patch("app.security.auth.get_auth_settings", return_value=TEST_AUTH_SETTINGS):
        client = TestClient(app)
        client.cookies.set("access_token", token)

        with patch("app.api.dashboard._fetch_monthly_income_expense_series", AsyncMock(side_effect=httpx.ConnectError("Tally down"))):
            res = client.get(
                "/api/v1/dashboard/monthly",
                params={"company_name": "Demo Co"},
            )
            assert res.status_code == 502
            assert "Unable to read monthly figures" in res.json()["detail"]


@pytest.mark.asyncio
async def test_dashboard_monthly_redis_failure_fails_open():
    """When Redis is down, GET /dashboard/monthly fails open to live Tally."""
    app = create_test_app()
    token = create_auth_token("user-dash", ["Demo Co"])
    series = [{"month": "2024-04", "income": 50000.0, "expense": 40000.0}]

    with patch("app.security.auth.get_auth_settings", return_value=TEST_AUTH_SETTINGS):
        client = TestClient(app)
        client.cookies.set("access_token", token)

        with patch("app.cache.manager.get_redis_client", AsyncMock(return_value=None)):
            with patch("app.api.dashboard._fetch_monthly_income_expense_series", AsyncMock(return_value=series)):
                res = client.get(
                    "/api/v1/dashboard/monthly",
                    params={"company_name": "Demo Co"},
                )
                assert res.status_code == 200
                data = res.json()
                assert data["success"] is True
                assert data["source"] == "tally"
                assert data["data"]["income_vs_expense"] == series


# ============================================================
# 4. CHATBOT TOOL OUTAGE LIFECYCLE
# ============================================================

@pytest.mark.asyncio
async def test_chat_tool_outage_fallback_and_recovery_lifecycle():
    """
    Complete lifecycle for Chatbot Tool execution:
    Live -> Cache-Hit -> Outage (Stale Fallback) -> Tally Recovery -> Fresh Hit
    """
    from app.chatbot.executor import execute_tool

    org_id = "e2e_chat_tool_org"
    await cache_manager.invalidate_prefix(f"tally:cache:{org_id}")

    initial_result = {
        "success": True,
        "source": "tally",
        "data": {"total_receivable": 850000.0, "count": 5},
    }
    recovered_result = {
        "success": True,
        "source": "tally",
        "data": {"total_receivable": 720000.0, "count": 4},
    }

    with patch("app.chatbot.executor.can_execute_tool", return_value=True):
        # 1. Live execution
        with patch.dict("app.chatbot.executor.TOOL_FUNCTIONS", {"get_receivables": AsyncMock(return_value=initial_result)}):
            res1 = await execute_tool(
                tool_name="get_receivables",
                arguments={"company_name": "Chat Co"},
                user_id="user-1",
                org_id=org_id,
                force_refresh=True,
            )
            assert res1["success"] is True
            assert res1["source"] == "tally"
            assert res1["is_stale"] is False
            assert res1["data"]["total_receivable"] == 850000.0

        # 2. Cache Hit
        with patch.dict("app.chatbot.executor.TOOL_FUNCTIONS", {"get_receivables": AsyncMock(side_effect=Exception("Should hit cache"))}):
            res2 = await execute_tool(
                tool_name="get_receivables",
                arguments={"company_name": "Chat Co"},
                user_id="user-1",
                org_id=org_id,
                force_refresh=False,
            )
            assert res2["success"] is True
            assert res2["source"] == "cache"
            assert res2["is_stale"] is False
            assert res2["data"]["total_receivable"] == 850000.0

        # 3. Outage -> Stale Fallback
        with patch.dict("app.chatbot.executor.TOOL_FUNCTIONS", {"get_receivables": AsyncMock(side_effect=httpx.ConnectError("Tally down"))}):
            res3 = await execute_tool(
                tool_name="get_receivables",
                arguments={"company_name": "Chat Co"},
                user_id="user-1",
                org_id=org_id,
                force_refresh=True,
            )
            assert res3["success"] is True
            assert res3["source"] == "stale_cache"
            assert res3["is_stale"] is True
            assert res3["data"]["total_receivable"] == 850000.0

        # 4. Recovery
        with patch.dict("app.chatbot.executor.TOOL_FUNCTIONS", {"get_receivables": AsyncMock(return_value=recovered_result)}):
            res4 = await execute_tool(
                tool_name="get_receivables",
                arguments={"company_name": "Chat Co"},
                user_id="user-1",
                org_id=org_id,
                force_refresh=True,
            )
            assert res4["success"] is True
            assert res4["source"] == "tally"
            assert res4["is_stale"] is False
            assert res4["data"]["total_receivable"] == 720000.0


@pytest.mark.asyncio
async def test_chat_tool_no_cache_during_outage_fails_cleanly():
    """Empty cache during Tally outage returns clean error without hallucinated values."""
    from app.chatbot.executor import execute_tool

    org_id = "no_cache_chat_org"
    await cache_manager.invalidate_prefix(f"tally:cache:{org_id}")

    with patch("app.chatbot.executor.can_execute_tool", return_value=True):
        with patch.dict("app.chatbot.executor.TOOL_FUNCTIONS", {"get_receivables": AsyncMock(side_effect=httpx.ConnectError("Tally down"))}):
            res = await execute_tool(
                tool_name="get_receivables",
                arguments={"company_name": "Chat Co"},
                user_id="user-1",
                org_id=org_id,
            )
            assert res["success"] is False
            assert res["source"] == "tally"
            assert res["data"] is None
            assert "Unable to retrieve the requested financial data" in res["message"]


@pytest.mark.asyncio
async def test_chat_tool_redis_failure_fails_open():
    """When Redis is down, chatbot tool executes live from Tally directly."""
    from app.chatbot.executor import execute_tool

    tool_result = {"success": True, "source": "tally", "data": {"net_profit": 180000.0}}

    with patch("app.chatbot.executor.can_execute_tool", return_value=True):
        with patch("app.cache.manager.get_redis_client", AsyncMock(return_value=None)):
            with patch.dict("app.chatbot.executor.TOOL_FUNCTIONS", {"get_net_profit": AsyncMock(return_value=tool_result)}):
                res = await execute_tool(
                    tool_name="get_net_profit",
                    arguments={"company_name": "Chat Co"},
                    user_id="user-1",
                )
                assert res["success"] is True
                assert res["source"] == "tally"
                assert res["data"]["net_profit"] == 180000.0


# ============================================================
# 5. SECURITY & APPLICATION ERROR INTEGRITY TESTS
# ============================================================

def test_outage_never_serves_stale_for_authorization_errors():
    """Authorization and authentication failures strictly reject requests before cache is accessed."""
    app = create_test_app()

    with patch("app.security.auth.get_auth_settings", return_value=TEST_AUTH_SETTINGS):
        client = TestClient(app)

        # 1. Unauthenticated -> 401 Unauthorized
        res_no_auth = client.get("/api/v1/tally/companies")
        assert res_no_auth.status_code == 401

        # 2. Forbidden Company -> 403 Forbidden
        token = create_auth_token("user-x", ["Allowed Company"])
        client.cookies.set("access_token", token)

        res_forbidden_dash = client.get(
            "/api/v1/dashboard/summary",
            params={"company_name": "Secret Company"},
        )
        assert res_forbidden_dash.status_code == 403

        res_forbidden_chat = client.post(
            "/api/v1/chat",
            json={"message": "What is my revenue?", "company_name": "Secret Company"},
        )
        assert res_forbidden_chat.status_code == 403


@pytest.mark.asyncio
async def test_outage_never_serves_stale_for_parser_or_application_errors():
    """Parser errors (e.g. malformed response / ValueError) never trigger stale cache fallback."""
    from app.chatbot.executor import execute_tool

    org_id = "parser_err_org"
    await cache_manager.invalidate_prefix(f"tally:cache:{org_id}")

    valid_res = {"success": True, "source": "tally", "data": {"revenue": 500000.0}}

    with patch("app.chatbot.executor.can_execute_tool", return_value=True):
        # 1. Warm cache
        with patch.dict("app.chatbot.executor.TOOL_FUNCTIONS", {"get_revenue": AsyncMock(return_value=valid_res)}):
            await execute_tool(
                tool_name="get_revenue",
                arguments={"company_name": "Parser Co"},
                user_id="user-1",
                org_id=org_id,
                force_refresh=True,
            )

        # 2. Subsequent call encounters parser/ValueError -> must NOT serve stale data
        with patch.dict("app.chatbot.executor.TOOL_FUNCTIONS", {"get_revenue": AsyncMock(side_effect=ValueError("Malformed XML table from Tally"))}):
            err_res = await execute_tool(
                tool_name="get_revenue",
                arguments={"company_name": "Parser Co"},
                user_id="user-1",
                org_id=org_id,
                force_refresh=True,
            )
            assert err_res["success"] is False
            assert err_res["data"] is None
            assert "Malformed XML" in err_res["message"]


def test_outage_never_serves_stale_for_business_validation_errors():
    """Business validation errors (from_date > to_date) return 400 Bad Request and never serve stale cache."""
    app = create_test_app()
    token = create_auth_token("user-valid", ["Demo Co"])

    with patch("app.security.auth.get_auth_settings", return_value=TEST_AUTH_SETTINGS):
        client = TestClient(app)
        client.cookies.set("access_token", token)

        # Invalid inverted date range
        res = client.get(
            "/api/v1/dashboard/summary",
            params={
                "company_name": "Demo Co",
                "from_date": "2025-05-01",
                "to_date": "2025-04-01",
            },
        )
        assert res.status_code in (400, 422)
        assert "must not be after" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_outage_fallback_strictly_preserves_tenant_and_company_isolation():
    """Cached/stale data from Org A / Company A is never leaked or served to Org B / Company B."""
    app = create_test_app()
    token_a = create_auth_token("user-a", ["Company A"])
    token_b = create_auth_token("user-b", ["Company B"])

    await cache_manager.invalidate_prefix("tally:cache:tenant_alpha")
    await cache_manager.invalidate_prefix("tally:cache:tenant_beta")

    summary_a = {"revenue": 999999.0, "company": "Company A"}

    with patch("app.security.auth.get_auth_settings", return_value=TEST_AUTH_SETTINGS):
        # 1. Warm cache for Tenant Alpha / Company A
        client_a = TestClient(app)
        client_a.cookies.set("access_token", token_a)

        with patch("app.api.dashboard.fetch_dashboard_reports", AsyncMock(return_value=({"pl": {}}, {}))):
            with patch("app.api.dashboard.map_dashboard_summary", return_value=dict(summary_a)):
                res_a = client_a.get(
                    "/api/v1/dashboard/summary",
                    params={"company_name": "Company A", "force_refresh": "true"},
                )
                assert res_a.status_code == 200
                assert res_a.json()["data"]["revenue"] == 999999.0

        # 2. Outage occurs. Tenant Beta / Company B makes request with empty cache.
        client_b = TestClient(app)
        client_b.cookies.set("access_token", token_b)

        with patch("app.api.dashboard.fetch_dashboard_reports", AsyncMock(side_effect=httpx.ConnectError("Tally down"))):
            res_b = client_b.get(
                "/api/v1/dashboard/summary",
                params={"company_name": "Company B"},
            )
            # Tenant Beta must NOT receive Tenant Alpha's cached data! It must fail with 502.
            assert res_b.status_code == 502
            assert "Unable to read dashboard reports" in res_b.json()["detail"]
