"""
Unit and integration tests for Redis caching and backend refresh mechanism.
Verifies freshness TTL, stale failover, stampede protection, fail-open,
and multi-tenant/company key isolation.
"""

import asyncio
from datetime import date
from unittest.mock import AsyncMock, patch
from app.security.auth import UserContext
import httpx
import pytest

from app.cache import (
    CacheResult,
    CacheState,
    TallyCacheManager,
    build_cache_key,
    build_lock_key,
    cache_manager,
    cache_settings,
    is_tally_connectivity_error,
)
from app.cache.keys import clean_segment, hash_params

TEST_USER_ORGS = {
    "user_a": "tenant_a",
    "user_b": "tenant_b",
    "iso_user_1": "iso_org1",
    "iso_user_2": "iso_org2",
    "iso_month_user_1": "iso_month_org1",
    "iso_month_user_2": "iso_month_org2",
    "user_test": "comp_test_org",
    "test_user": "test_org",
    "user-1": "test_org",
    "user-restricted": "test_org",
    "user-admin": "test_org",
    "user-chat": "chat_org",
    "admin-user": "chat_test_org",
    "u1": "chat_org_1",
}


@pytest.fixture(autouse=True)
def mock_user_org_resolution():
    """Mock tenant resolution so synthetic test users resolve securely without touching production database."""
    TallyCacheManager.mark_tally_online()
    resolver = lambda uid: TEST_USER_ORGS.get(uid, f"org_{uid}")
    with patch("app.security.user_store.get_user_organization_id", side_effect=resolver), \
         patch("app.api.chat.get_user_organization_id", side_effect=resolver):
        yield
    TallyCacheManager.mark_tally_online()



@pytest.mark.asyncio
async def test_cache_hit_and_miss():
    """Cache returns tally source on first request and cache source on subsequent fresh request."""
    manager = TallyCacheManager()
    key = build_cache_key("test_hit_miss", "Company A")

    fetch_mock = AsyncMock(return_value={"revenue": 50000.0})

    # Miss -> Fetch from live
    res1 = await manager.get_or_fetch(key, fetch_mock, fresh_ttl=60)
    assert res1.source == "tally"
    assert res1.data == {"revenue": 50000.0}
    assert res1.is_stale is False
    assert res1.cached_at is not None
    assert fetch_mock.call_count == 1

    # Hit -> Served from cache
    res2 = await manager.get_or_fetch(key, fetch_mock, fresh_ttl=60)
    assert res2.source == "cache"
    assert res2.data == {"revenue": 50000.0}
    assert res2.is_stale is False
    assert res2.cached_at == res1.cached_at
    assert fetch_mock.call_count == 1  # No additional live call!

    await manager.invalidate(key)


@pytest.mark.asyncio
async def test_freshness_expiry_and_refresh():
    """When fresh TTL expires, next request fetches fresh data from live source."""
    manager = TallyCacheManager()
    key = build_cache_key("test_freshness_expiry", "Company A")

    # Initial populate with 1-second freshness
    await manager.get_or_fetch(
        key,
        AsyncMock(return_value={"counter": 1}),
        fresh_ttl=1,
        stale_retention_ttl=60,
    )

    # Wait for freshness to expire (retention still active)
    await asyncio.sleep(1.2)

    # Next call should fetch fresh data (counter: 2)
    refresh_mock = AsyncMock(return_value={"counter": 2})
    res = await manager.get_or_fetch(
        key,
        refresh_mock,
        fresh_ttl=60,
    )
    assert res.source == "tally"
    assert res.data == {"counter": 2}
    assert res.is_stale is False
    assert refresh_mock.call_count == 1

    await manager.invalidate(key)


@pytest.mark.asyncio
async def test_stale_fallback_on_connectivity_error():
    """During verified Tally connectivity failure, retained stale cache is served with provenance."""
    manager = TallyCacheManager()
    key = build_cache_key("test_stale_fallback", "Company A")

    # Initial populate
    init_res = await manager.get_or_fetch(
        key,
        AsyncMock(return_value={"data": "retained_value"}),
        fresh_ttl=1,
        stale_retention_ttl=60,
    )
    original_cached_at = init_res.cached_at

    # Wait for freshness to expire
    await asyncio.sleep(1.2)

    # Simulate network outage (Tally unreachable)
    failing_fetcher = AsyncMock(
        side_effect=httpx.ConnectError("Failed to connect to Tally on port 9000")
    )

    res = await manager.get_or_fetch(key, failing_fetcher)
    assert res.source == "stale_cache"
    assert res.data == {"data": "retained_value"}
    assert res.is_stale is True
    assert res.cached_at == original_cached_at

    await manager.invalidate(key)


@pytest.mark.asyncio
async def test_non_connectivity_error_does_not_serve_stale():
    """Business, parser, and runtime errors must NOT silently serve stale data."""
    manager = TallyCacheManager()
    key = build_cache_key("test_business_error", "Company A")

    # Initial populate
    await manager.get_or_fetch(
        key,
        AsyncMock(return_value={"data": "authoritative"}),
        fresh_ttl=1,
        stale_retention_ttl=60,
    )

    # Wait for freshness to expire
    await asyncio.sleep(1.2)

    # Simulate Tally business error (LINEERROR / STATUS 0)
    business_error_fetcher = AsyncMock(
        side_effect=RuntimeError("Tally Line Error: Invalid XML request")
    )

    with pytest.raises(RuntimeError, match="Tally Line Error"):
        await manager.get_or_fetch(key, business_error_fetcher)

    # Simulate ValueError (parser bug)
    parser_error_fetcher = AsyncMock(
        side_effect=ValueError("Failed parsing Tally date")
    )

    with pytest.raises(ValueError, match="Failed parsing"):
        await manager.get_or_fetch(key, parser_error_fetcher)

    await manager.invalidate(key)


@pytest.mark.asyncio
async def test_fail_open_when_redis_disabled():
    """When cache is disabled in settings, live requests continue working without error."""
    manager = TallyCacheManager()
    key = build_cache_key("test_fail_open", "Company A")

    fetch_mock = AsyncMock(return_value={"live": True})

    with patch.object(cache_settings, "REDIS_CACHE_ENABLED", False):
        res = await manager.get_or_fetch(key, fetch_mock)
        assert res.source == "tally"
        assert res.data == {"live": True}
        assert fetch_mock.call_count == 1


@pytest.mark.asyncio
async def test_stampede_single_flight_protection():
    """Multiple concurrent requests for the same key trigger only one live fetch."""
    manager = TallyCacheManager()
    key = build_cache_key("test_stampede_protection", "Company A")

    execution_count = 0

    async def slow_fetch():
        nonlocal execution_count
        execution_count += 1
        await asyncio.sleep(0.05)
        return {"value": 42}

    # 10 concurrent requests for the same cache key
    tasks = [
        manager.get_or_fetch(key, slow_fetch, fresh_ttl=60)
        for _ in range(10)
    ]
    results = await asyncio.gather(*tasks)

    # Exactly one live execution must have occurred
    assert execution_count == 1
    # All 10 callers must have received identical authoritative data
    for res in results:
        assert res.data == {"value": 42}

    await manager.invalidate(key)


def test_cache_key_isolation_across_companies_and_params():
    """Keys for different companies, tenants, and date parameters must never collide."""
    key_comp_a = build_cache_key("profit_loss", "Company Alpha")
    key_comp_b = build_cache_key("profit_loss", "Company Beta")
    assert key_comp_a != key_comp_b

    # Date ranges
    key_period_1 = build_cache_key(
        "profit_loss",
        "Company Alpha",
        params={"from_date": date(2024, 4, 1), "to_date": date(2025, 3, 31)},
    )
    key_period_2 = build_cache_key(
        "profit_loss",
        "Company Alpha",
        params={"from_date": date(2025, 4, 1), "to_date": date(2026, 3, 31)},
    )
    assert key_period_1 != key_period_2
    assert key_period_1 != key_comp_a

    # Multi-tenant isolation
    key_org_1 = build_cache_key("profit_loss", "Company Alpha", org_id="org_1")
    key_org_2 = build_cache_key("profit_loss", "Company Alpha", org_id="org_2")
    assert key_org_1 != key_org_2


def test_tally_connectivity_error_classification():
    """Verify exact categorization of connectivity vs non-connectivity exceptions."""
    assert is_tally_connectivity_error(httpx.ConnectError("refused")) is True
    assert is_tally_connectivity_error(httpx.ConnectTimeout("timeout")) is True
    assert is_tally_connectivity_error(httpx.ReadTimeout("timeout")) is True
    assert is_tally_connectivity_error(ConnectionRefusedError("refused")) is True
    assert is_tally_connectivity_error(TimeoutError("timeout")) is True

    # Non-connectivity errors
    assert is_tally_connectivity_error(RuntimeError("LINEERROR")) is False
    assert is_tally_connectivity_error(ValueError("invalid date")) is False
    assert is_tally_connectivity_error(KeyError("missing key")) is False
    assert is_tally_connectivity_error(asyncio.CancelledError()) is False


@pytest.mark.asyncio
async def test_force_refresh_bypasses_cache():
    """Manual or forced refresh bypasses fresh cache and updates Redis."""
    manager = TallyCacheManager()
    key = build_cache_key("test_force_refresh", "Company A")

    # Initial call
    fetch_mock = AsyncMock(side_effect=[{"value": 1}, {"value": 2}])
    res1 = await manager.get_or_fetch(key, fetch_mock, fresh_ttl=60)
    assert res1.source == "tally"
    assert res1.data == {"value": 1}

    # Second call without force_refresh (cache hit)
    res2 = await manager.get_or_fetch(key, fetch_mock, fresh_ttl=60)
    assert res2.source == "cache"
    assert res2.data == {"value": 1}

    # Third call with force_refresh=True
    res3 = await manager.get_or_fetch(key, fetch_mock, fresh_ttl=60, force_refresh=True)
    assert res3.source == "tally"
    assert res3.data == {"value": 2}

    await manager.invalidate(key)


@pytest.mark.asyncio
async def test_background_refresher_skips_when_tally_offline():
    """Background refresher pre-flight check prevents redundant attempts when Tally is offline."""
    from app.cache.refresher import TallyBackgroundRefresher

    worker = TallyBackgroundRefresher()
    with patch.object(worker, "_is_tally_reachable", AsyncMock(return_value=False)):
        with patch("app.tally.service.fetch_companies", AsyncMock()) as mock_fetch:
            await worker.run_refresh_cycle()
            mock_fetch.assert_not_called()


@pytest.mark.asyncio
async def test_background_refresher_executes_when_tally_online():
    """Background refresher executes companies and dashboard refresh when Tally is online."""
    from app.cache.refresher import TallyBackgroundRefresher

    worker = TallyBackgroundRefresher()
    with patch.object(worker, "_is_tally_reachable", AsyncMock(return_value=True)):
        with patch("app.tally.service.fetch_companies", AsyncMock(return_value=[{"name": "Test Co"}])) as mock_fetch:
            with patch("asyncio.sleep", AsyncMock()):
                with patch("app.tally.dashboard.fetch_dashboard_reports", AsyncMock(return_value=({}, {}))) as mock_dash:
                    await worker.run_refresh_cycle()
                    mock_fetch.assert_called_once_with(force_refresh=True, org_id="default")
                    mock_dash.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_companies_service_caching():
    """fetch_companies correctly uses Redis cache and supports force_refresh."""
    from app.tally.service import fetch_companies

    with patch("app.tally.service.client.send_xml", AsyncMock(side_effect=[
        "<ENVELOPE><BODY><DATA><COLLECTION><COMPANY><NAME>Company 1</NAME></COMPANY></COLLECTION></DATA></BODY></ENVELOPE>",
        "<ENVELOPE><BODY><DATA><COLLECTION><COMPANY><NAME>Company 2</NAME></COMPANY></COLLECTION></DATA></BODY></ENVELOPE>",
    ])) as mock_send:
        # First call: hits Tally
        res1 = await fetch_companies(force_refresh=True, org_id="test_org")
        assert len(res1) == 1
        assert res1[0]["name"] == "Company 1"
        assert mock_send.call_count == 1

        # Second call: served from Redis cache (no send_xml call)
        res2 = await fetch_companies(force_refresh=False, org_id="test_org")
        assert len(res2) == 1
        assert res2[0]["name"] == "Company 1"
        assert mock_send.call_count == 1

        # Third call: force_refresh=True bypasses cache
        res3 = await fetch_companies(force_refresh=True, org_id="test_org")
        assert len(res3) == 1
        assert res3[0]["name"] == "Company 2"
        assert mock_send.call_count == 2


@pytest.mark.asyncio
async def test_dashboard_summary_caching_and_stale_fallback():
    """get_dashboard_summary caches response and falls back to stale cache on connectivity outage."""
    from app.api.dashboard import get_dashboard_summary
    from app.security.auth import UserContext

    user = UserContext(user_id="test_user", allowed_companies=("Test Co",))
    dummy_summary = {
        "company_name": "Test Co",
        "total_sales": 150000.0,
        "total_purchases": 50000.0,
    }

    # 1. First fetch populates cache
    with patch("app.api.dashboard.fetch_dashboard_reports", AsyncMock(return_value=({"dummy": {}}, {}))):
        with patch("app.api.dashboard.map_dashboard_summary", return_value=dummy_summary):
            res1 = await get_dashboard_summary(company_name="Test Co", current_user=user, force_refresh=True)
            assert res1["success"] is True
            assert res1["source"] == "tally"
            assert res1["data"]["total_sales"] == 150000.0

    # 2. Second fetch hits cache
    with patch("app.api.dashboard.fetch_dashboard_reports", AsyncMock(side_effect=Exception("Should not be called"))):
        res2 = await get_dashboard_summary(company_name="Test Co", current_user=user, force_refresh=False)
        assert res2["success"] is True
        assert res2["source"] == "cache"
        assert res2["data"]["total_sales"] == 150000.0

    # 3. Third fetch: live Tally fails with ReadTimeout, serves stale cache
    timeout_err = httpx.ReadTimeout("Tally timed out")
    with patch("app.api.dashboard.fetch_dashboard_reports", AsyncMock(side_effect=timeout_err)):
        # force_refresh=True forces attempt to live Tally, but outage triggers stale fallback
        res3 = await get_dashboard_summary(company_name="Test Co", current_user=user, force_refresh=True)
        assert res3["success"] is True
        assert res3["source"] == "stale_cache"
        assert res3["is_stale"] is True
        assert res3["data"]["total_sales"] == 150000.0


@pytest.mark.asyncio
async def test_dashboard_summary_isolation_across_dates_companies_and_orgs():
    """get_dashboard_summary generates distinct keys for companies, dates, and orgs."""
    from app.api.dashboard import get_dashboard_summary
    from app.security.auth import UserContext
    from app.cache import cache_manager

    await cache_manager.invalidate_prefix("tally:cache:iso_org")

    user_org1 = UserContext(user_id="iso_user_1", allowed_companies=("*",))
    user_org2 = UserContext(user_id="iso_user_2", allowed_companies=("*",))

    fetch_mock = AsyncMock(return_value=({"report": {}}, {}))
    map_mock = lambda r, s, e, c: {"company_name": c, "start": str(s), "end": str(e)}

    with patch("app.api.dashboard.fetch_dashboard_reports", fetch_mock):
        with patch("app.api.dashboard.map_dashboard_summary", side_effect=map_mock):
            # Company A, date range 1, org1
            res_a = await get_dashboard_summary(
                company_name="Iso Company A",
                from_date=date(2025, 4, 1),
                to_date=date(2025, 6, 30),
                current_user=user_org1,
                force_refresh=True,
            )
            assert res_a["data"]["company_name"] == "Iso Company A"

            # Company B (different company), org1 -> miss, live fetch
            res_b = await get_dashboard_summary(
                company_name="Iso Company B",
                from_date=date(2025, 4, 1),
                to_date=date(2025, 6, 30),
                current_user=user_org1,
                force_refresh=False,
            )
            assert res_b["source"] == "tally"
            assert res_b["data"]["company_name"] == "Iso Company B"

            # Company A with different dates, org1 -> miss, live fetch
            res_a_dates = await get_dashboard_summary(
                company_name="Iso Company A",
                from_date=date(2025, 7, 1),
                to_date=date(2025, 9, 30),
                current_user=user_org1,
                force_refresh=False,
            )
            assert res_a_dates["source"] == "tally"

            # Company A with different org (user_org2) -> miss, live fetch
            res_a_org2 = await get_dashboard_summary(
                company_name="Iso Company A",
                from_date=date(2025, 4, 1),
                to_date=date(2025, 6, 30),
                current_user=user_org2,
                force_refresh=False,
            )
            assert res_a_org2["source"] == "tally"

            # Repeat Company A, date range 1, org1 -> cache hit!
            res_a_repeat = await get_dashboard_summary(
                company_name="Iso Company A",
                from_date=date(2025, 4, 1),
                to_date=date(2025, 6, 30),
                current_user=user_org1,
                force_refresh=False,
            )
            assert res_a_repeat["source"] == "cache"
            assert res_a_repeat["data"]["company_name"] == "Iso Company A"

    await cache_manager.invalidate_prefix("tally:cache:iso_org")



@pytest.mark.asyncio
async def test_dashboard_summary_non_connectivity_error_does_not_serve_stale():
    """Non-connectivity error (e.g. ValueError or report parser exception) never serves stale cache."""
    from app.api.dashboard import get_dashboard_summary
    from app.security.auth import UserContext
    from fastapi import HTTPException

    user = UserContext(user_id="test_user", allowed_companies=("Test Co",))
    dummy_summary = {"company_name": "Test Co", "total_sales": 100.0}

    # 1. Warm the cache
    with patch("app.api.dashboard.fetch_dashboard_reports", AsyncMock(return_value=({"dummy": {}}, {}))):
        with patch("app.api.dashboard.map_dashboard_summary", return_value=dummy_summary):
            await get_dashboard_summary(company_name="Test Co", current_user=user, force_refresh=True)

    # 2. Simulate non-connectivity error on force_refresh (e.g., ValueError)
    with patch("app.api.dashboard.fetch_dashboard_reports", AsyncMock(side_effect=ValueError("Corrupted XML report"))):
        with pytest.raises(HTTPException) as exc_info:
            await get_dashboard_summary(company_name="Test Co", current_user=user, force_refresh=True)
        assert exc_info.value.status_code == 502


def test_dashboard_summary_auth_and_company_authorization_enforced():
    """Authentication and company authorization are evaluated before any cache access."""
    import jwt
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import dashboard
    from app.security.config import AuthSettings

    app = FastAPI()
    app.include_router(dashboard.router)

    test_secret = "test-secret-key-that-is-long-enough-32-chars-min"
    mock_settings = AuthSettings(
        auth_enabled=True,
        jwt_secret=test_secret,
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

    with patch("app.security.auth.get_auth_settings", return_value=mock_settings):
        client = TestClient(app)

        # 1. No token -> 401 Unauthorized
        res_no_auth = client.get("/summary", params={"company_name": "Allowed Co"})
        assert res_no_auth.status_code == 401

        # 2. Token with "Allowed Co" requesting "Forbidden Co" -> 403 Forbidden
        forbidden_token = jwt.encode(
            {"sub": "user-1", "companies": ["Allowed Co"]},
            test_secret,
            algorithm="HS256",
        )
        client.cookies.set("access_token", forbidden_token)
        res_forbidden = client.get("/summary", params={"company_name": "Forbidden Co"})
        assert res_forbidden.status_code == 403

        # 3. Token with "Allowed Co" requesting "Allowed Co" -> 200 OK (reaches cache/live)
        with patch("app.api.dashboard.fetch_dashboard_reports", AsyncMock(return_value=({"r": {}}, {}))):
            with patch("app.api.dashboard.map_dashboard_summary", return_value={"company_name": "Allowed Co"}):
                res_ok = client.get("/summary", params={"company_name": "Allowed Co"})
                assert res_ok.status_code == 200
                assert res_ok.json()["success"] is True
                assert res_ok.json()["data"]["company_name"] == "Allowed Co"


@pytest.mark.asyncio
async def test_dashboard_monthly_caching_and_stale_fallback():
    """get_dashboard_monthly caches response and falls back to stale cache on connectivity outage."""
    from app.api.dashboard import get_dashboard_monthly
    from app.security.auth import UserContext

    user = UserContext(user_id="test_user", allowed_companies=("Monthly Co",))
    dummy_series = [
        {"month": "Apr 2025", "income": 10000.0, "expense": 5000.0, "status": "available"},
        {"month": "May 2025", "income": 12000.0, "expense": 6000.0, "status": "available"},
    ]

    # 1. First fetch populates cache
    with patch("app.api.dashboard._fetch_monthly_income_expense_series", AsyncMock(return_value=dummy_series)) as mock_series:
        res1 = await get_dashboard_monthly(company_name="Monthly Co", current_user=user, force_refresh=True)
        assert res1["success"] is True
        assert res1["source"] == "tally"
        assert res1["data"]["income_vs_expense"] == dummy_series
        assert mock_series.call_count == 1

    # 2. Second fetch hits cache
    with patch("app.api.dashboard._fetch_monthly_income_expense_series", AsyncMock(side_effect=Exception("Should not be called"))):
        res2 = await get_dashboard_monthly(company_name="Monthly Co", current_user=user, force_refresh=False)
        assert res2["success"] is True
        assert res2["source"] == "cache"
        assert res2["is_stale"] is False
        assert res2["data"]["income_vs_expense"] == dummy_series

    # 3. Third fetch: live Tally fails with ConnectError, serves stale cache
    connect_err = httpx.ConnectError("Tally connection refused")
    with patch("app.api.dashboard._fetch_monthly_income_expense_series", AsyncMock(side_effect=connect_err)):
        res3 = await get_dashboard_monthly(company_name="Monthly Co", current_user=user, force_refresh=True)
        assert res3["success"] is True
        assert res3["source"] == "stale_cache"
        assert res3["is_stale"] is True
        assert res3["data"]["income_vs_expense"] == dummy_series


@pytest.mark.asyncio
async def test_dashboard_monthly_isolation_across_dates_companies_and_orgs():
    """get_dashboard_monthly generates distinct keys for companies, dates, and orgs."""
    from app.api.dashboard import get_dashboard_monthly
    from app.security.auth import UserContext
    from app.cache import cache_manager

    await cache_manager.invalidate_prefix("tally:cache:iso_month_org")

    user_org1 = UserContext(user_id="iso_month_user_1", allowed_companies=("*",))
    user_org2 = UserContext(user_id="iso_month_user_2", allowed_companies=("*",))

    def make_series(co):
        return [{"month": "Apr 2025", "income": 1.0, "expense": 1.0, "status": co}]

    with patch("app.api.dashboard._fetch_monthly_income_expense_series", AsyncMock(side_effect=lambda c, s, e, **kw: make_series(c))):
        # Co A, date range 1, org1
        res_a = await get_dashboard_monthly(
            company_name="Monthly Co A",
            from_date=date(2025, 4, 1),
            to_date=date(2025, 6, 30),
            current_user=user_org1,
            force_refresh=True,
        )
        assert res_a["data"]["income_vs_expense"][0]["status"] == "Monthly Co A"

        # Co B (different company), org1 -> miss, live fetch
        res_b = await get_dashboard_monthly(
            company_name="Monthly Co B",
            from_date=date(2025, 4, 1),
            to_date=date(2025, 6, 30),
            current_user=user_org1,
            force_refresh=False,
        )
        assert res_b["source"] == "tally"
        assert res_b["data"]["income_vs_expense"][0]["status"] == "Monthly Co B"

        # Co A with different dates, org1 -> miss, live fetch
        res_a_dates = await get_dashboard_monthly(
            company_name="Monthly Co A",
            from_date=date(2025, 7, 1),
            to_date=date(2025, 9, 30),
            current_user=user_org1,
            force_refresh=False,
        )
        assert res_a_dates["source"] == "tally"

        # Co A with different org (user_org2) -> miss, live fetch
        res_a_org2 = await get_dashboard_monthly(
            company_name="Monthly Co A",
            from_date=date(2025, 4, 1),
            to_date=date(2025, 6, 30),
            current_user=user_org2,
            force_refresh=False,
        )
        assert res_a_org2["source"] == "tally"

        # Repeat Co A, date range 1, org1 -> cache hit!
        res_a_repeat = await get_dashboard_monthly(
            company_name="Monthly Co A",
            from_date=date(2025, 4, 1),
            to_date=date(2025, 6, 30),
            current_user=user_org1,
            force_refresh=False,
        )
        assert res_a_repeat["source"] == "cache"
        assert res_a_repeat["data"]["income_vs_expense"][0]["status"] == "Monthly Co A"

    await cache_manager.invalidate_prefix("tally:cache:iso_month_org")


def test_dashboard_monthly_auth_and_company_authorization_enforced():
    """Authentication and company authorization are evaluated before any cache access on /monthly."""
    import jwt
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import dashboard
    from app.security.config import AuthSettings

    app = FastAPI()
    app.include_router(dashboard.router)

    test_secret = "test-secret-key-that-is-long-enough-32-chars-min"
    mock_settings = AuthSettings(
        auth_enabled=True,
        jwt_secret=test_secret,
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

    with patch("app.security.auth.get_auth_settings", return_value=mock_settings):
        client = TestClient(app)

        # 1. No token -> 401 Unauthorized
        res_no_auth = client.get("/monthly", params={"company_name": "Allowed Co"})
        assert res_no_auth.status_code == 401

        # 2. Token with "Allowed Co" requesting "Forbidden Co" -> 403 Forbidden
        forbidden_token = jwt.encode(
            {"sub": "user-1", "companies": ["Allowed Co"]},
            test_secret,
            algorithm="HS256",
        )
        client.cookies.set("access_token", forbidden_token)
        res_forbidden = client.get("/monthly", params={"company_name": "Forbidden Co"})
        assert res_forbidden.status_code == 403

        # 3. Token with "Allowed Co" requesting "Allowed Co" -> 200 OK (reaches cache/live)
        with patch("app.api.dashboard._fetch_monthly_income_expense_series", AsyncMock(return_value=[])):
            res_ok = client.get("/monthly", params={"company_name": "Allowed Co"})
            assert res_ok.status_code == 200
            assert res_ok.json()["success"] is True
            assert res_ok.json()["data"]["company_name"] == "Allowed Co"


@pytest.mark.asyncio
async def test_get_companies_endpoint_caching_and_stale_fallback():
    """get_companies caches response, serves from Redis, and falls back to stale on outage."""
    from app.api.tally import get_companies
    from app.security.auth import UserContext
    from app.cache import cache_manager

    user = UserContext(user_id="user_test", allowed_companies=("*",))
    dummy_companies = [{"name": "Company Alpha"}, {"name": "Company Beta"}]

    await cache_manager.invalidate_prefix("tally:cache:comp_test_org")

    # 1. First fetch: live from Tally
    with patch("app.tally.service.client.send_xml", AsyncMock(return_value="<ENVELOPE></ENVELOPE>")) as mock_send:
        with patch("app.tally.service.parse_companies", return_value={"companies": dummy_companies}):
            res1 = await get_companies(
                current_user=user,
                force_refresh=True,
            )
            assert res1["success"] is True
            assert res1["source"] == "tally"
            assert res1["companies"] == dummy_companies
            assert res1["is_stale"] is False
            assert mock_send.call_count == 1

    # 2. Second fetch: hit Redis cache (mock_send not called)
    with patch("app.tally.service.client.send_xml", AsyncMock(side_effect=Exception("Should not be called"))) as mock_send:
        res2 = await get_companies(
            current_user=user,
            force_refresh=False,
        )
        assert res2["success"] is True
        assert res2["source"] == "cache"
        assert res2["companies"] == dummy_companies
        assert res2["is_stale"] is False
        assert mock_send.call_count == 0

    # 3. Third fetch: live Tally fails with ConnectError -> serves stale cache
    connect_err = httpx.ConnectError("Tally connection refused")
    with patch("app.tally.service.client.send_xml", AsyncMock(side_effect=connect_err)):
        res3 = await get_companies(
            current_user=user,
            force_refresh=True,
        )
        assert res3["success"] is True
        assert res3["source"] == "stale_cache"
        assert res3["companies"] == dummy_companies
        assert res3["is_stale"] is True


@pytest.mark.asyncio
async def test_get_companies_non_connectivity_error_does_not_serve_stale():
    """Non-connectivity errors (e.g. malformed response / ValueError) never serve stale cache."""
    from app.api.tally import get_companies
    from app.security.auth import UserContext
    from app.cache import cache_manager
    from fastapi import HTTPException

    user = UserContext(user_id="user_test", allowed_companies=("*",))
    dummy_companies = [{"name": "Company Alpha"}]

    await cache_manager.invalidate_prefix("tally:cache:comp_err_org")

    # 1. Warm cache
    with patch("app.tally.service.client.send_xml", AsyncMock(return_value="<ENVELOPE></ENVELOPE>")):
        with patch("app.tally.service.parse_companies", return_value={"companies": dummy_companies}):
            await get_companies(
                current_user=user,
                force_refresh=True,
            )

    # 2. Non-connectivity error -> must raise HTTPException(502), not serve stale cache
    with patch("app.tally.service.client.send_xml", AsyncMock(side_effect=ValueError("Invalid XML"))):
        with pytest.raises(HTTPException) as exc_info:
            await get_companies(
                current_user=user,
                force_refresh=True,
            )
        assert exc_info.value.status_code == 502


@pytest.mark.asyncio
async def test_get_companies_isolation_across_organizations():
    """get_companies isolates cache keys across tenant organizations."""
    from app.api.tally import get_companies
    from app.security.auth import UserContext
    from app.cache import cache_manager

    await cache_manager.invalidate_prefix("tally:cache:tenant_a")
    await cache_manager.invalidate_prefix("tally:cache:tenant_b")

    user_a = UserContext(user_id="user_a", allowed_companies=("*",))
    user_b = UserContext(user_id="user_b", allowed_companies=("*",))

    companies_a = [{"name": "Tenant A Co"}]
    companies_b = [{"name": "Tenant B Co"}]

    # Org A populates Org A cache
    with patch("app.tally.service.client.send_xml", AsyncMock(return_value="<ENVELOPE></ENVELOPE>")):
        with patch("app.tally.service.parse_companies", return_value={"companies": companies_a}):
            res_a = await get_companies(current_user=user_a, force_refresh=True)
            assert res_a["companies"] == companies_a

    # Org B must miss Org A cache and fetch live
    with patch("app.tally.service.client.send_xml", AsyncMock(return_value="<ENVELOPE></ENVELOPE>")):
        with patch("app.tally.service.parse_companies", return_value={"companies": companies_b}):
            res_b = await get_companies(current_user=user_b, force_refresh=False)
            assert res_b["source"] == "tally"
            assert res_b["companies"] == companies_b


def test_get_companies_auth_and_rbac_enforcement():
    """Endpoint enforces authentication before cache lookup and filters by allowed_companies."""
    import jwt
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import tally
    from app.security.config import AuthSettings

    app = FastAPI()
    app.include_router(tally.router)

    test_secret = "test-secret-key-that-is-long-enough-32-chars-min"
    mock_settings = AuthSettings(
        auth_enabled=True,
        jwt_secret=test_secret,
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

    all_tally_companies = [
        {"name": "Authorized Company"},
        {"name": "Secret Company"},
    ]

    with patch("app.security.auth.get_auth_settings", return_value=mock_settings):
        client = TestClient(app)

        # 1. No token -> 401 Unauthorized before cache access
        with patch("app.tally.service.client.send_xml", AsyncMock()) as mock_send:
            res_no_auth = client.get("/companies")
            assert res_no_auth.status_code == 401
            mock_send.assert_not_called()

        # 2. Token with restricted company -> strictly filtered by RBAC
        token_restricted = jwt.encode(
            {"sub": "user-restricted", "companies": ["Authorized Company"]},
            test_secret,
            algorithm="HS256",
        )
        client.cookies.set("access_token", token_restricted)
        with patch("app.tally.service.client.send_xml", AsyncMock(return_value="<ENVELOPE></ENVELOPE>")):
            with patch("app.tally.service.parse_companies", return_value={"companies": all_tally_companies}):
                res_restricted = client.get("/companies", params={"force_refresh": "true"})
                assert res_restricted.status_code == 200
                data = res_restricted.json()
                assert data["success"] is True
                assert len(data["companies"]) == 1
                assert data["companies"][0]["name"] == "Authorized Company"

        # 3. Token with wildcard -> sees all loaded companies
        token_wildcard = jwt.encode(
            {"sub": "user-admin", "companies": ["*"]},
            test_secret,
            algorithm="HS256",
        )
        client.cookies.set("access_token", token_wildcard)
        res_wildcard = client.get("/companies")
        assert res_wildcard.status_code == 200
        data_wildcard = res_wildcard.json()
        assert len(data_wildcard["companies"]) == 2


# ============================================================
# CHATBOT TOOL CACHING TESTS
# ============================================================

@pytest.mark.asyncio
async def test_chat_tool_caching_and_stale_fallback():
    """execute_tool caches tool result, serves from Redis, and falls back to stale on outage."""
    from app.chatbot.executor import execute_tool

    await cache_manager.invalidate_prefix("tally:cache:chat_test_org")

    fake_result = {
        "success": True,
        "source": "tally",
        "data": {"revenue": 950000.0, "count": 12},
    }

    with patch("app.chatbot.executor.can_execute_tool", return_value=True):
        # 1. First execution: live fetch from Tally tool
        with patch.dict("app.chatbot.executor.TOOL_FUNCTIONS", {"get_revenue": AsyncMock(return_value=fake_result)}):
            res1 = await execute_tool(
                tool_name="get_revenue",
                arguments={"company_name": "Chat Co"},
                user_id="admin-user",
                org_id="chat_test_org",
                force_refresh=True,
            )
            assert res1["success"] is True
            assert res1["source"] == "tally"
            assert res1["data"]["revenue"] == 950000.0
            assert res1["is_stale"] is False

        # 2. Second execution: hits Redis cache (tool function not called)
        with patch.dict("app.chatbot.executor.TOOL_FUNCTIONS", {"get_revenue": AsyncMock(side_effect=Exception("Should not be called"))}):
            res2 = await execute_tool(
                tool_name="get_revenue",
                arguments={"company_name": "Chat Co"},
                user_id="admin-user",
                org_id="chat_test_org",
                force_refresh=False,
            )
            assert res2["success"] is True
            assert res2["source"] == "cache"
            assert res2["data"]["revenue"] == 950000.0
            assert res2["is_stale"] is False

        # 3. Third execution: Tally fails with ConnectError -> serves retained stale cache
        with patch.dict("app.chatbot.executor.TOOL_FUNCTIONS", {"get_revenue": AsyncMock(side_effect=httpx.ConnectError("Tally unreachable"))}):
            res3 = await execute_tool(
                tool_name="get_revenue",
                arguments={"company_name": "Chat Co"},
                user_id="admin-user",
                org_id="chat_test_org",
                force_refresh=True,
            )
            assert res3["success"] is True
            assert res3["source"] == "stale_cache"
            assert res3["is_stale"] is True
            assert res3["data"]["revenue"] == 950000.0


@pytest.mark.asyncio
async def test_chat_tool_isolation_across_orgs_companies_and_params():
    """Chatbot tools isolate cache entries across tenants, companies, and date parameters."""
    from app.chatbot.executor import execute_tool

    await cache_manager.invalidate_prefix("tally:cache:chat_org_1")
    await cache_manager.invalidate_prefix("tally:cache:chat_org_2")

    res_co_a = {"success": True, "source": "tally", "data": {"val": "A"}}
    res_co_b = {"success": True, "source": "tally", "data": {"val": "B"}}
    res_date_1 = {"success": True, "source": "tally", "data": {"period": "2024"}}
    res_date_2 = {"success": True, "source": "tally", "data": {"period": "2025"}}

    with patch("app.chatbot.executor.can_execute_tool", return_value=True):
        # Company isolation
        with patch.dict("app.chatbot.executor.TOOL_FUNCTIONS", {"get_receivables": AsyncMock(return_value=res_co_a)}):
            await execute_tool("get_receivables", {"company_name": "Co Alpha"}, user_id="u1", org_id="chat_org_1", force_refresh=True)

        with patch.dict("app.chatbot.executor.TOOL_FUNCTIONS", {"get_receivables": AsyncMock(return_value=res_co_b)}):
            await execute_tool("get_receivables", {"company_name": "Co Beta"}, user_id="u1", org_id="chat_org_1", force_refresh=True)

        # Cache check: Co Alpha gets res_co_a from cache
        with patch.dict("app.chatbot.executor.TOOL_FUNCTIONS", {"get_receivables": AsyncMock(side_effect=Exception("Should not be called"))}):
            cached_a = await execute_tool("get_receivables", {"company_name": "Co Alpha"}, user_id="u1", org_id="chat_org_1")
            cached_b = await execute_tool("get_receivables", {"company_name": "Co Beta"}, user_id="u1", org_id="chat_org_1")
            assert cached_a["data"]["val"] == "A"
            assert cached_b["data"]["val"] == "B"

        # Tenant Org isolation: org_2 misses org_1 cache
        with patch.dict("app.chatbot.executor.TOOL_FUNCTIONS", {"get_receivables": AsyncMock(return_value={"success": True, "source": "tally", "data": {"val": "Org2"}})}):
            res_org2 = await execute_tool("get_receivables", {"company_name": "Co Alpha"}, user_id="u1", org_id="chat_org_2")
            assert res_org2["source"] == "tally"
            assert res_org2["data"]["val"] == "Org2"

        # Date isolation
        with patch.dict("app.chatbot.executor.TOOL_FUNCTIONS", {"get_revenue": AsyncMock(return_value=res_date_1)}):
            await execute_tool("get_revenue", {"company_name": "Co Alpha", "from_date": "01-04-2024", "to_date": "31-03-2025"}, user_id="u1", org_id="chat_org_1", force_refresh=True)

        with patch.dict("app.chatbot.executor.TOOL_FUNCTIONS", {"get_revenue": AsyncMock(return_value=res_date_2)}):
            await execute_tool("get_revenue", {"company_name": "Co Alpha", "from_date": "01-04-2025", "to_date": "31-03-2026"}, user_id="u1", org_id="chat_org_1", force_refresh=True)

        with patch.dict("app.chatbot.executor.TOOL_FUNCTIONS", {"get_revenue": AsyncMock(side_effect=Exception("Should not be called"))}):
            cached_d1 = await execute_tool("get_revenue", {"company_name": "Co Alpha", "from_date": "01-04-2024", "to_date": "31-03-2025"}, user_id="u1", org_id="chat_org_1")
            cached_d2 = await execute_tool("get_revenue", {"company_name": "Co Alpha", "from_date": "01-04-2025", "to_date": "31-03-2026"}, user_id="u1", org_id="chat_org_1")
            assert cached_d1["data"]["period"] == "2024"
            assert cached_d2["data"]["period"] == "2025"


@pytest.mark.asyncio
async def test_chat_tool_non_connectivity_error_does_not_serve_stale():
    """Non-connectivity errors in chatbot tool execution do not serve stale cache."""
    from app.chatbot.executor import execute_tool

    await cache_manager.invalidate_prefix("tally:cache:chat_err_org")

    fake_result = {
        "success": True,
        "source": "tally",
        "data": {"payables": 50000.0},
    }

    with patch("app.chatbot.executor.can_execute_tool", return_value=True):
        # 1. Warm cache
        with patch.dict("app.chatbot.executor.TOOL_FUNCTIONS", {"get_payables": AsyncMock(return_value=fake_result)}):
            await execute_tool("get_payables", {"company_name": "Err Co"}, user_id="u1", org_id="chat_err_org", force_refresh=True)

        # 2. ValueError raises -> does NOT serve stale cache
        with patch.dict("app.chatbot.executor.TOOL_FUNCTIONS", {"get_payables": AsyncMock(side_effect=ValueError("Corrupt JSON"))}):
            err_res = await execute_tool("get_payables", {"company_name": "Err Co"}, user_id="u1", org_id="chat_err_org", force_refresh=True)
            assert err_res["success"] is False
            assert "Corrupt JSON" in err_res["message"]


@pytest.mark.asyncio
async def test_chat_tool_rbac_and_auth_enforced_before_cache_lookup():
    """Chatbot tool execution strictly enforces RBAC authorization before cache access."""
    from app.chatbot.executor import execute_tool

    # When user is not authorized, execute_tool fails closed without cache access
    with patch("app.chatbot.executor.can_execute_tool", return_value=False):
        res = await execute_tool(
            tool_name="get_profit_loss",
            arguments={"company_name": "Any Co"},
            user_id="unauthorized_user",
        )
        assert res["success"] is False
        assert res["source"] == "authorization"
        assert "not authorized" in res["message"].lower()


def test_chat_endpoint_e2e_caching_and_force_refresh():
    """POST /api/v1/chat endpoint enforces auth/company check and returns cached provenance."""
    import jwt
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import chat
    from app.security.config import AuthSettings

    app = FastAPI()
    app.include_router(chat.router)

    test_secret = "test-secret-key-that-is-long-enough-32-chars-min"
    mock_settings = AuthSettings(
        auth_enabled=True,
        jwt_secret=test_secret,
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

    with patch("app.security.auth.get_auth_settings", return_value=mock_settings):
        client = TestClient(app)

        # 1. No token -> 401 Unauthorized
        res_no_auth = client.post("/chat", json={"message": "What is my revenue?", "company_name": "Allowed Co"})
        assert res_no_auth.status_code == 401

        # 2. Token with forbidden company -> 403 Forbidden
        token = jwt.encode(
            {"sub": "user-chat", "companies": ["Allowed Co"]},
            test_secret,
            algorithm="HS256",
        )
        client.cookies.set("access_token", token)
        res_forbidden = client.post("/chat", json={"message": "What is my revenue?", "company_name": "Forbidden Co"})
        assert res_forbidden.status_code == 403

        # 3. Valid user -> calls process_chat_message and returns ChatResponse
        mock_result = {
            "success": True,
            "answer": "Your revenue is ₹9,50,000.",
            "intent": "get_revenue",
            "source": "cache",
            "data": {"revenue": 950000.0},
            "is_stale": False,
        }
        with patch("app.api.chat.process_chat_message", AsyncMock(return_value=mock_result)):
            res_ok = client.post("/chat", json={"message": "What is my revenue?", "company_name": "Allowed Co"})
            assert res_ok.status_code == 200
            data = res_ok.json()
            assert data["success"] is True
            assert data["source"] == "cache"
            assert "₹9,50,000" in data["answer"]
