"""PDF / Excel export of the dashboard.

Runs the dashboard's own /summary and /monthly endpoint functions, so
the file shows the same (cached) figures as the screen. dashboard.py is
not modified.
"""

import logging
from datetime import date

from fastapi import APIRouter, Depends, Query

from app.api import dashboard as dashboard_api
from app.api.reports import _check_format, _safe_name, _spec_response
from app.export import report_specs as specs
from app.export.invoke import invoke_endpoint
from app.security.auth import (
    UserContext,
    get_authorized_company,
    get_current_user,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/export/{file_format}")
async def export_dashboard(
    file_format: str,
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    company_name: str | None = Depends(get_authorized_company),
    current_user: UserContext = Depends(get_current_user),
):
    _check_format(file_format)

    given = {
        "request": None,
        "from_date": from_date,
        "to_date": to_date,
        "company_name": company_name,
        "current_user": current_user,
    }
    summary = await invoke_endpoint(dashboard_api.get_dashboard_summary, **given)

    monthly = None
    try:
        monthly = await invoke_endpoint(dashboard_api.get_dashboard_monthly, **given)
    except Exception:
        # The monthly trend is a nice-to-have; the rest of the dashboard
        # should still export if Tally cannot produce it.
        logger.warning("Dashboard export: monthly trend unavailable", exc_info=True)

    data = summary.get("data") or {}
    name = data.get("company_name") or company_name
    start, end = dashboard_api._resolve_period(from_date, to_date)
    period = specs.period_label(start, end)

    return _spec_response(
        file_format,
        specs.dashboard_spec(data, (monthly or {}).get("data"), name, period),
        _safe_name("dashboard", start.isoformat(), end.isoformat()),
    )
