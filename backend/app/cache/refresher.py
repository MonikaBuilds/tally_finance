"""
Background cache refresher for high-value Tally endpoints.
Refreshes loaded companies and primary dashboard reports during idle intervals
with pre-flight connectivity checks and staggered request throttling.
"""

import asyncio
import logging
from datetime import date
from typing import Optional

from app.cache.config import cache_settings

logger = logging.getLogger(__name__)

_refresher_task: Optional[asyncio.Task] = None


class TallyBackgroundRefresher:
    """
    Background worker that keeps frequently-requested Tally data warm in Redis cache.
    """

    def __init__(self, org_id: str = "default"):
        self._running = False
        self._tally_client = None
        self._org_id = org_id

    @property
    def _client(self):
        if self._tally_client is None:
            from app.tally.client import TallyClient
            self._tally_client = TallyClient()
        return self._tally_client

    async def _is_tally_reachable(self) -> bool:
        """Lightweight connectivity check before launching report refreshes."""
        try:
            status = await self._client.check_connection()
            return status.get("connected", False)
        except Exception:
            return False

    async def run_refresh_cycle(self) -> None:
        """
        Execute a single refresh cycle for high-value reports.
        Uses delayed execution between requests to preserve Tally responsiveness.
        """
        from app.tally.service import fetch_companies

        logger.info("Starting background cache refresh cycle...")

        # 1. Pre-flight check: don't attempt if Tally is offline
        if not await self._is_tally_reachable():
            logger.info("Tally server unreachable; skipping background refresh cycle.")
            return

        try:
            # 2. Refresh loaded companies list (force_refresh=True)
            companies = await fetch_companies(force_refresh=True, org_id=self._org_id)
            logger.info("Background refreshed companies: %d loaded.", len(companies))

            if not companies:
                return

            # Short polite pause between Tally requests
            await asyncio.sleep(2.0)

            # 3. Refresh primary loaded company dashboard summary
            from app.tally.dashboard import fetch_dashboard_reports
            from app.cache.keys import build_cache_key
            from app.cache.manager import cache_manager

            today = date.today()
            # Default financial year start (April 1st)
            start_year = today.year if today.month >= 4 else today.year - 1
            default_start = date(start_year, 4, 1)
            default_end = today

            primary_company = companies[0].get("name")
            if primary_company:
                dashboard_key = build_cache_key(
                    report_name="dashboard_summary",
                    company_name=primary_company,
                    org_id=self._org_id,
                    params={
                        "from_date": default_start.isoformat(),
                        "to_date": default_end.isoformat(),
                    },
                )

                async def _refresh_dashboard():
                    from app.api.dashboard_mapper import map_dashboard_summary
                    from datetime import datetime, timezone

                    reports, errors = await fetch_dashboard_reports(
                        primary_company,
                        default_start,
                        default_end,
                    )
                    if not reports:
                        raise RuntimeError(f"No dashboard reports returned for {primary_company}")
                    summary = map_dashboard_summary(
                        reports,
                        default_start,
                        default_end,
                        primary_company,
                    )
                    summary['report_errors'] = errors
                    summary['fetched_at'] = datetime.now(timezone.utc).isoformat()
                    return summary

                await cache_manager.get_or_fetch(
                    cache_key=dashboard_key,
                    fetcher=_refresh_dashboard,
                    fresh_ttl=cache_settings.get_fresh_ttl("dashboard_summary"),
                    force_refresh=True,
                    metadata={
                        "report": "dashboard_summary",
                        "company": primary_company,
                        "org_id": self._org_id,
                    },
                )
                logger.info(
                    "Background refreshed dashboard summary for primary company '%s'.",
                    primary_company,
                )

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Error during background cache refresh cycle: %s", exc)

    async def start(self) -> None:
        """Main loop of the background refresher task."""
        self._running = True
        interval = max(60, cache_settings.REDIS_CACHE_REFRESH_INTERVAL_SECONDS)
        logger.info("Background cache refresher started (interval: %ds).", interval)

        # Allow FastAPI app to finish initial startup before first background refresh
        await asyncio.sleep(10.0)

        while self._running:
            try:
                await self.run_refresh_cycle()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Unexpected error in background refresher: %s", exc)

            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break

        logger.info("Background cache refresher stopped.")

    def stop(self) -> None:
        self._running = False


refresher = TallyBackgroundRefresher()


def start_background_refresher() -> Optional[asyncio.Task]:
    """Start background refresher if enabled."""
    global _refresher_task

    if not cache_settings.REDIS_CACHE_ENABLED or not cache_settings.REDIS_CACHE_REFRESH_ENABLED:
        logger.info("Background cache refresher is disabled in settings.")
        return None

    if _refresher_task is None or _refresher_task.done():
        _refresher_task = asyncio.create_task(refresher.start())

    return _refresher_task


async def stop_background_refresher() -> None:
    """Stop the running background refresher task."""
    global _refresher_task

    refresher.stop()
    if _refresher_task is not None and not _refresher_task.done():
        _refresher_task.cancel()
        try:
            await _refresher_task
        except asyncio.CancelledError:
            pass
        _refresher_task = None
