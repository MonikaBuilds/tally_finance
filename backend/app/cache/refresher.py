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

# Dashboards opened by real users: (org_id, company, start, end) -> last seen.
RECENT_ACCESS_WINDOW_SECONDS = 2 * 3600
MAX_TRACKED_DASHBOARDS = 20
_recent_dashboards: dict[tuple, float] = {}


def note_dashboard_access(org_id, company, start, end) -> None:
    """Record that a user opened this dashboard (called by the API)."""
    import time

    if not org_id or not company or start is None or end is None:
        return
    _recent_dashboards[(str(org_id), company, start, end)] = time.monotonic()
    if len(_recent_dashboards) > MAX_TRACKED_DASHBOARDS:
        oldest = min(_recent_dashboards, key=_recent_dashboards.get)
        _recent_dashboards.pop(oldest, None)


def recent_dashboard_targets() -> list[tuple]:
    import time

    cutoff = time.monotonic() - RECENT_ACCESS_WINDOW_SECONDS
    for key in [k for k, seen in _recent_dashboards.items() if seen < cutoff]:
        _recent_dashboards.pop(key, None)
    return sorted(_recent_dashboards, key=_recent_dashboards.get, reverse=True)


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
        Refresh only the dashboards real users opened recently, under their
        real organization. With no recent activity this makes no Tally
        request at all (the previous version warmed an organization and
        company no user was reading, every 10 minutes, all day).
        """
        targets = recent_dashboard_targets()

        if not targets:
            logger.debug("No recently used dashboards; skipping background refresh.")
            return

        if not await self._is_tally_reachable():
            logger.info("Tally server unreachable; skipping background refresh cycle.")
            return

        from app.api.dashboard_mapper import map_dashboard_summary
        from app.cache.keys import build_cache_key
        from app.cache.manager import cache_manager
        from app.tally.dashboard import fetch_dashboard_reports
        from datetime import datetime, timezone

        for org_id, company, start, end in targets:
            cache_key = build_cache_key(
                report_name="dashboard_summary",
                company_name=company,
                org_id=org_id,
                params={
                    "from_date": start.isoformat(),
                    "to_date": end.isoformat(),
                },
            )

            async def _refresh(company=company, start=start, end=end):
                reports, errors = await fetch_dashboard_reports(company, start, end)
                if not reports:
                    raise RuntimeError(f"No dashboard reports returned for {company}")
                summary = map_dashboard_summary(reports, start, end, company)
                summary["report_errors"] = errors
                summary["fetched_at"] = datetime.now(timezone.utc).isoformat()
                return summary

            try:
                await cache_manager.get_or_fetch(
                    cache_key=cache_key,
                    fetcher=_refresh,
                    fresh_ttl=cache_settings.get_fresh_ttl("dashboard_summary"),
                    force_refresh=True,
                    metadata={
                        "report": "dashboard_summary",
                        "company": company,
                        "org_id": org_id,
                    },
                )
                logger.info("Background refreshed dashboard for '%s'.", company)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Background refresh failed for '%s': %s", company, exc)

            # Short polite pause so user requests are not starved.
            await asyncio.sleep(2.0)

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
