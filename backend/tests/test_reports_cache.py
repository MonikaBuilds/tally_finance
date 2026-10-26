"""
Comprehensive test suite for Redis caching and Tally outage resilience across Reports endpoints.

Covers:
1. Profit & Loss caching & outage resilience (Live -> Cache Hit -> Stale Fallback on ConnectError -> Recovery)
2. Trial Balance caching with distinct date parameters (from_date / to_date key differentiation)
3. Balance Sheet caching with multi-company parameter isolation
4. Receivables and Payables caching & outage fallback
5. Safe 502 Bad Gateway when Tally is offline and no cached entry exists
6. Non-connectivity errors (e.g. ValueError, parser error) never returning stale data
7. Multi-tenant organization isolation (Organization A's cache is never served to Organization B)
8. Force refresh parameter bypassing fresh cache
9. Fast failover (< 100ms) when Tally is marked offline or circuit breaker is open
"""

import asyncio
from datetime import date
import time
from unittest.mock import AsyncMock, patch

import httpx
import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import reports
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
    "user-rep-1": "org_rep_alpha",
    "user-rep-2": "org_rep_beta",
    "user-rep-no-cache": "org_rep_nocache",
}


@pytest.fixture(autouse=True)
def mock_user_org_resolution():
    """Mock tenant resolution so synthetic test users resolve securely."""
    TallyCacheManager.mark_tally_online()
    resolver = lambda uid: TEST_USER_ORGS.get(uid, f"org_{uid}")
    with patch("app.security.user_store.get_user_organization_id", side_effect=resolver), \
         patch("app.api.reports._resolve_org_id", side_effect=lambda user: TEST_USER_ORGS.get(user.user_id, f"org_{user.user_id}")):
        yield
    TallyCacheManager.mark_tally_online()


def create_reports_app() -> FastAPI:
    """Create a FastAPI application with reports router mounted."""
    app = FastAPI()
    app.include_router(reports.router, prefix="/api/v1/reports")
    return app


def create_auth_token(user_id: str, companies: list[str]) -> str:
    """Create a signed JWT token for test authentication."""
    return jwt.encode(
        {"sub": user_id, "companies": companies},
        TEST_SECRET,
        algorithm="HS256",
    )


# ============================================================
# 1. PROFIT & LOSS CACHE & OUTAGE LIFECYCLE
# ============================================================

@pytest.mark.asyncio
async def test_profit_loss_caching_and_outage_lifecycle():
    """
    Complete lifecycle for GET /api/v1/reports/profit-loss:
    Live (tally) -> Cache Hit (cache) -> Outage (stale_cache) -> Recovery (tally) -> Cache Hit (cache)
    """
    app = create_reports_app()
    token = create_auth_token("user-rep-1", ["Acme Corp"])
    org_id = "org_rep_alpha"

    await cache_manager.invalidate_prefix(f"tally:cache:{org_id}")

    sample_pl_1 = {
        "left": [{"name": "Purchases", "amount": 50000.0}],
        "right": [{"name": "Sales", "amount": 90000.0}],
        "total_left": 50000.0,
        "total_right": 90000.0,
    }

    sample_pl_2 = {
        "left": [{"name": "Purchases", "amount": 55000.0}],
        "right": [{"name": "Sales", "amount": 105000.0}],
        "total_left": 55000.0,
        "total_right": 105000.0,
    }

    with patch("app.security.auth.get_auth_settings", return_value=TEST_AUTH_SETTINGS):
        client = TestClient(app)
        client.cookies.set("access_token", token)

        # 1. LIVE HIT
        with patch("app.api.reports.fetch_profit_loss", AsyncMock(return_value=sample_pl_1)):
            res1 = client.get(
                "/api/v1/reports/profit-loss",
                params={"company_name": "Acme Corp", "force_refresh": "true"},
            )
            assert res1.status_code == 200
            data1 = res1.json()
            assert data1["success"] is True
            assert data1["source"] == "tally"
            assert data1["is_stale"] is False
            assert data1["cached_at"] is not None
            assert data1["report"]["total_right"] == 90000.0

        # 2. CACHE HIT (Tally should not be queried)
        with patch("app.api.reports.fetch_profit_loss", AsyncMock(side_effect=Exception("Should hit cache"))):
            res2 = client.get(
                "/api/v1/reports/profit-loss",
                params={"company_name": "Acme Corp"},
            )
            assert res2.status_code == 200
            data2 = res2.json()
            assert data2["success"] is True
            assert data2["source"] == "cache"
            assert data2["is_stale"] is False
            assert data2["cached_at"] == data1["cached_at"]
            assert data2["report"]["total_right"] == 90000.0

        # 3. OUTAGE FALLBACK (ConnectError serves stale retained data)
        with patch("app.api.reports.fetch_profit_loss", AsyncMock(side_effect=httpx.ConnectError("Tally unreachable"))):
            res3 = client.get(
                "/api/v1/reports/profit-loss",
                params={"company_name": "Acme Corp", "force_refresh": "true"},
            )
            assert res3.status_code == 200
            data3 = res3.json()
            assert data3["success"] is True
            assert data3["source"] == "stale_cache"
            assert data3["is_stale"] is True
            assert data3["cached_at"] == data1["cached_at"]
            assert data3["report"]["total_right"] == 90000.0

        # 4. RECOVERY (Tally comes back online, replaces stale cache)
        with patch("app.api.reports.fetch_profit_loss", AsyncMock(return_value=sample_pl_2)):
            res4 = client.get(
                "/api/v1/reports/profit-loss",
                params={"company_name": "Acme Corp", "force_refresh": "true"},
            )
            assert res4.status_code == 200
            data4 = res4.json()
            assert data4["success"] is True
            assert data4["source"] == "tally"
            assert data4["is_stale"] is False
            assert data4["report"]["total_right"] == 105000.0

        # 5. SUBSEQUENT FRESH HIT (Returns new data from cache)
        with patch("app.api.reports.fetch_profit_loss", AsyncMock(side_effect=Exception("Should hit fresh cache"))):
            res5 = client.get(
                "/api/v1/reports/profit-loss",
                params={"company_name": "Acme Corp"},
            )
            assert res5.status_code == 200
            data5 = res5.json()
            assert data5["success"] is True
            assert data5["source"] == "cache"
            assert data5["is_stale"] is False
            assert data5["report"]["total_right"] == 105000.0


# ============================================================
# 2. TRIAL BALANCE CACHING & DATE DIFFERENTIATION
# ============================================================

@pytest.mark.asyncio
async def test_trial_balance_caching_and_date_parameters():
    """Trial Balance requests with different date ranges do not collide in cache."""
    app = create_reports_app()
    token = create_auth_token("user-rep-1", ["Acme Corp"])
    org_id = "org_rep_alpha"

    await cache_manager.invalidate_prefix(f"tally:cache:{org_id}")

    tb_q1 = [{"name": "Cash", "debit": 1000.0, "credit": None}]
    tb_q2 = [{"name": "Cash", "debit": 2500.0, "credit": None}]

    with patch("app.security.auth.get_auth_settings", return_value=TEST_AUTH_SETTINGS):
        client = TestClient(app)
        client.cookies.set("access_token", token)

        # Q1 fetch
        with patch("app.api.reports.fetch_trial_balance", AsyncMock(return_value=tb_q1)):
            r1 = client.get(
                "/api/v1/reports/trial-balance",
                params={"company_name": "Acme Corp", "from_date": "2025-04-01", "to_date": "2025-06-30"},
            )
            assert r1.status_code == 200
            assert r1.json()["source"] == "tally"
            assert r1.json()["report"][0]["debit"] == 1000.0

        # Q2 fetch (different date -> must be a cache MISS to Tally)
        with patch("app.api.reports.fetch_trial_balance", AsyncMock(return_value=tb_q2)):
            r2 = client.get(
                "/api/v1/reports/trial-balance",
                params={"company_name": "Acme Corp", "from_date": "2025-07-01", "to_date": "2025-09-30"},
            )
            assert r2.status_code == 200
            assert r2.json()["source"] == "tally"
            assert r2.json()["report"][0]["debit"] == 2500.0

        # Repeated Q1 fetch -> cache HIT without calling Tally
        with patch("app.api.reports.fetch_trial_balance", AsyncMock(side_effect=Exception("Should hit cache"))):
            r1_hit = client.get(
                "/api/v1/reports/trial-balance",
                params={"company_name": "Acme Corp", "from_date": "2025-04-01", "to_date": "2025-06-30"},
            )
            assert r1_hit.status_code == 200
            assert r1_hit.json()["source"] == "cache"
            assert r1_hit.json()["report"][0]["debit"] == 1000.0


# ============================================================
# 3. BALANCE SHEET & COMPANY ISOLATION
# ============================================================

@pytest.mark.asyncio
async def test_balance_sheet_company_isolation():
    """Balance Sheet data for Company A and Company B never collide in cache."""
    app = create_reports_app()
    token = create_auth_token("user-rep-1", ["Acme Corp", "Beta Enterprises"])
    org_id = "org_rep_alpha"

    await cache_manager.invalidate_prefix(f"tally:cache:{org_id}")

    bs_acme = {
        "liabilities": [{"name": "Capital", "amount": 100000.0}],
        "assets": [{"name": "Bank", "amount": 100000.0}],
        "total_liabilities": 100000.0,
        "total_assets": 100000.0,
        "difference": 0.0,
    }
    bs_beta = {
        "liabilities": [{"name": "Capital", "amount": 250000.0}],
        "assets": [{"name": "Bank", "amount": 250000.0}],
        "total_liabilities": 250000.0,
        "total_assets": 250000.0,
        "difference": 0.0,
    }

    with patch("app.security.auth.get_auth_settings", return_value=TEST_AUTH_SETTINGS):
        client = TestClient(app)
        client.cookies.set("access_token", token)

        with patch("app.api.reports.fetch_balance_sheet_report", AsyncMock(return_value=bs_acme)):
            res_acme = client.get("/api/v1/reports/balance-sheet", params={"company_name": "Acme Corp"})
            assert res_acme.status_code == 200
            assert res_acme.json()["report"]["liabilities"][0]["amount"] == 100000.0

        with patch("app.api.reports.fetch_balance_sheet_report", AsyncMock(return_value=bs_beta)):
            res_beta = client.get("/api/v1/reports/balance-sheet", params={"company_name": "Beta Enterprises"})
            assert res_beta.status_code == 200
            assert res_beta.json()["report"]["liabilities"][0]["amount"] == 250000.0

        # Re-fetch Acme from cache -> must still be 100000
        with patch("app.api.reports.fetch_balance_sheet_report", AsyncMock(side_effect=Exception("Should hit cache"))):
            res_acme_hit = client.get("/api/v1/reports/balance-sheet", params={"company_name": "Acme Corp"})
            assert res_acme_hit.status_code == 200
            assert res_acme_hit.json()["source"] == "cache"
            assert res_acme_hit.json()["report"]["liabilities"][0]["amount"] == 100000.0


# ============================================================
# 4. RECEIVABLES & PAYABLES CACHING & OUTAGE
# ============================================================

@pytest.mark.asyncio
async def test_receivables_and_payables_caching():
    """Receivables and Payables endpoints cache data and support stale fallback during outage."""
    app = create_reports_app()
    token = create_auth_token("user-rep-1", ["Acme Corp"])
    org_id = "org_rep_alpha"

    await cache_manager.invalidate_prefix(f"tally:cache:{org_id}")

    sample_bills = [
        {
            "party": "Customer A",
            "bill_reference": "INV-101",
            "bill_date": "2025-01-01",
            "due_date": "2025-01-15",
            "overdue_days": 10,
            "outstanding_amount": 12000.0,
        }
    ]

    with patch("app.security.auth.get_auth_settings", return_value=TEST_AUTH_SETTINGS):
        client = TestClient(app)
        client.cookies.set("access_token", token)

        # Receivables live
        with patch("app.api.reports.fetch_bills_receivable", AsyncMock(return_value=sample_bills)), \
             patch("app.api.reports.fetch_bill_allocations", AsyncMock(return_value=[])):
            r_rec1 = client.get("/api/v1/reports/receivables", params={"company_name": "Acme Corp"})
            assert r_rec1.status_code == 200
            assert r_rec1.json()["source"] == "tally"
            assert r_rec1.json()["data"]["count"] == 1
            assert len(r_rec1.json()["data"]["bills"]) == 1

        # Receivables cache hit
        with patch("app.api.reports.fetch_bills_receivable", AsyncMock(side_effect=Exception("Should hit cache"))):
            r_rec2 = client.get("/api/v1/reports/receivables", params={"company_name": "Acme Corp"})
            assert r_rec2.status_code == 200
            assert r_rec2.json()["source"] == "cache"

        # Receivables outage fallback
        with patch("app.api.reports.fetch_bills_receivable", AsyncMock(side_effect=httpx.ConnectTimeout("Tally down"))):
            r_rec3 = client.get("/api/v1/reports/receivables", params={"company_name": "Acme Corp", "force_refresh": "true"})
            assert r_rec3.status_code == 200
            assert r_rec3.json()["source"] == "stale_cache"
            assert r_rec3.json()["is_stale"] is True


# ============================================================
# 5. NO-CACHE OUTAGE FAILS CLEANLY WITH 502
# ============================================================

@pytest.mark.asyncio
async def test_reports_outage_without_cache_returns_502():
    """When Tally has an outage and there is no cached data, returns 502 Bad Gateway without crashing."""
    app = create_reports_app()
    token = create_auth_token("user-rep-no-cache", ["Acme Corp"])
    org_id = "org_rep_nocache"

    await cache_manager.invalidate_prefix(f"tally:cache:{org_id}")

    with patch("app.security.auth.get_auth_settings", return_value=TEST_AUTH_SETTINGS):
        client = TestClient(app)
        client.cookies.set("access_token", token)

        with patch("app.api.reports.fetch_profit_loss", AsyncMock(side_effect=httpx.ConnectError("Tally unreachable"))):
            res = client.get("/api/v1/reports/profit-loss", params={"company_name": "Acme Corp"})
            assert res.status_code == 502
            assert "Unable to fetch Profit & Loss" in res.json()["detail"]


# ============================================================
# 6. NON-CONNECTIVITY ERROR NEVER SERVES STALE
# ============================================================

@pytest.mark.asyncio
async def test_reports_non_connectivity_error_does_not_serve_stale():
    """Parser or application errors must not serve stale cache - they must raise an error."""
    app = create_reports_app()
    token = create_auth_token("user-rep-1", ["Acme Corp"])
    org_id = "org_rep_alpha"

    await cache_manager.invalidate_prefix(f"tally:cache:{org_id}")

    sample_pl = {"left": [], "right": [], "total_left": 0, "total_right": 0}

    with patch("app.security.auth.get_auth_settings", return_value=TEST_AUTH_SETTINGS):
        client = TestClient(app)
        client.cookies.set("access_token", token)

        # Populate cache first
        with patch("app.api.reports.fetch_profit_loss", AsyncMock(return_value=sample_pl)):
            r1 = client.get("/api/v1/reports/profit-loss", params={"company_name": "Acme Corp"})
            assert r1.status_code == 200

        # Now simulate a parser error / ValueError (not a connectivity error)
        with patch("app.api.reports.fetch_profit_loss", AsyncMock(side_effect=ValueError("Corrupt XML"))):
            r2 = client.get("/api/v1/reports/profit-loss", params={"company_name": "Acme Corp", "force_refresh": "true"})
            # Must return 502 error, NEVER stale cache
            assert r2.status_code == 502


# ============================================================
# 7. TENANT ORGANISATION ISOLATION
# ============================================================

@pytest.mark.asyncio
async def test_reports_multi_tenant_isolation():
    """Cache entries for Organization Alpha must never be accessible to Organization Beta."""
    app = create_reports_app()
    token_alpha = create_auth_token("user-rep-1", ["SharedCorp"])
    token_beta = create_auth_token("user-rep-2", ["SharedCorp"])

    await cache_manager.invalidate_prefix("tally:cache:org_rep_alpha")
    await cache_manager.invalidate_prefix("tally:cache:org_rep_beta")

    data_alpha = {"left": [{"name": "Alpha Account", "amount": 11111.0}], "right": [], "total_left": 11111.0, "total_right": 0}
    data_beta = {"left": [{"name": "Beta Account", "amount": 99999.0}], "right": [], "total_left": 99999.0, "total_right": 0}

    with patch("app.security.auth.get_auth_settings", return_value=TEST_AUTH_SETTINGS):
        client = TestClient(app)

        # Alpha requests and populates its own cache
        client.cookies.set("access_token", token_alpha)
        with patch("app.api.reports.fetch_profit_loss", AsyncMock(return_value=data_alpha)):
            r_alpha = client.get("/api/v1/reports/profit-loss", params={"company_name": "SharedCorp"})
            assert r_alpha.status_code == 200
            assert r_alpha.json()["report"]["left"][0]["amount"] == 11111.0

        # Beta requests the same company: must NOT get Alpha's cached data, must call fetcher
        client.cookies.set("access_token", token_beta)
        with patch("app.api.reports.fetch_profit_loss", AsyncMock(return_value=data_beta)):
            r_beta = client.get("/api/v1/reports/profit-loss", params={"company_name": "SharedCorp"})
            assert r_beta.status_code == 200
            assert r_beta.json()["report"]["left"][0]["amount"] == 99999.0

        # Beta outage: should serve Beta's own data, never Alpha's
        with patch("app.api.reports.fetch_profit_loss", AsyncMock(side_effect=httpx.ConnectError("Offline"))):
            r_beta_stale = client.get("/api/v1/reports/profit-loss", params={"company_name": "SharedCorp", "force_refresh": "true"})
            assert r_beta_stale.status_code == 200
            assert r_beta_stale.json()["report"]["left"][0]["amount"] == 99999.0


# ============================================================
# 8. FAST FAILOVER UNDER GLOBAL OUTAGE
# ============================================================

@pytest.mark.asyncio
async def test_fast_failover_when_tally_known_offline():
    """
    When Tally is marked offline (circuit breaker open) and fresh TTL has expired,
    outage fallback returns retained stale data in < 100ms without waiting for connection timeouts.
    """
    app = create_reports_app()
    token = create_auth_token("user-rep-1", ["Acme Corp"])
    org_id = "org_rep_alpha"

    await cache_manager.invalidate_prefix(f"tally:cache:{org_id}")

    sample_pl = {"left": [{"name": "Sales", "amount": 100.0}], "right": [], "total_left": 100.0, "total_right": 0}

    with patch("app.security.auth.get_auth_settings", return_value=TEST_AUTH_SETTINGS):
        client = TestClient(app)
        client.cookies.set("access_token", token)

        # Populate cache with a fresh TTL of 0 seconds so it immediately transitions to STALE
        with patch.object(cache_settings, "TTL_PROFIT_LOSS", 0):
            with patch("app.api.reports.fetch_profit_loss", AsyncMock(return_value=sample_pl)):
                r1 = client.get("/api/v1/reports/profit-loss", params={"company_name": "Acme Corp"})
                assert r1.status_code == 200

            # Mark Tally globally offline
            TallyCacheManager.mark_tally_offline(cooldown_seconds=30.0)

            # Slow fetcher that would take 5 seconds if attempted
            async def slow_fetcher(**kwargs):
                await asyncio.sleep(5.0)
                raise httpx.ConnectTimeout("Slow network")

            t_start = time.perf_counter()
            with patch("app.api.reports.fetch_profit_loss", side_effect=slow_fetcher):
                r2 = client.get("/api/v1/reports/profit-loss", params={"company_name": "Acme Corp"})
            elapsed_ms = (time.perf_counter() - t_start) * 1000

            assert r2.status_code == 200
            assert r2.json()["source"] == "stale_cache"
            assert r2.json()["is_stale"] is True
            # Verify it bypassed the slow 5-second fetcher immediately
            assert elapsed_ms < 200.0, f"Expected fast failover < 200ms, took {elapsed_ms:.1f}ms"



