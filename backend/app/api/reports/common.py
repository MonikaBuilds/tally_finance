"""
Shared constants, columns, and export/caching helper utilities for reports.
"""

import logging
import re
import sys
from datetime import date, timedelta
from typing import Any, Awaitable, Callable, TypeVar

from fastapi import HTTPException
from fastapi.responses import Response

from app.cache.config import cache_settings, is_force_refresh
from app.cache.keys import build_cache_key
from app.cache.manager import cache_manager, CacheResult
from app.security.auth import UserContext
from app.security.config import get_auth_settings
from app.export import report_specs as specs
from app.export.exporter import build_excel, build_pdf, build_report_excel, build_report_pdf

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _resolve_org_id(current_user: UserContext) -> str:
    """Resolve organization ID only from the authenticated user."""
    from app.security.user_store import get_user_organization_id

    organization_id = get_user_organization_id(current_user.user_id)
    if not organization_id:
        settings = get_auth_settings()
        if not settings.auth_enabled or current_user.user_id == "development-user":
            return "default"
        raise HTTPException(
            status_code=500,
            detail="Unable to resolve user organization.",
        )
    return str(organization_id)


async def _cached_report(
    report_name: str,
    company_name: str | None,
    current_user: UserContext,
    params: dict[str, Any],
    fetcher: Callable[[], Awaitable[T]],
    force_refresh: bool = False,
    refresh: str | int | None = None,
    ttl_name: str | None = None,
) -> CacheResult[T]:
    reports_mod = sys.modules.get("app.api.reports")
    resolve_fn = getattr(reports_mod, "_resolve_org_id", _resolve_org_id) if reports_mod else _resolve_org_id
    effective_org_id = resolve_fn(current_user)

    is_force = is_force_refresh(force_refresh=force_refresh, refresh=refresh)
    cache_key = build_cache_key(
        report_name=report_name,
        company_name=company_name,
        org_id=effective_org_id,
        params=params,
    )
    fresh_ttl = cache_settings.get_fresh_ttl(ttl_name or report_name)
    stale_ttl = cache_settings.REDIS_CACHE_STALE_RETENTION_TTL

    return await cache_manager.get_or_fetch(
        cache_key=cache_key,
        fetcher=fetcher,
        fresh_ttl=fresh_ttl,
        stale_retention_ttl=stale_ttl,
        force_refresh=is_force,
        metadata={
            "report": report_name,
            "company": company_name,
            "org_id": effective_org_id,
            **{k: v for k, v in params.items() if v is not None},
        },
    )

# ============================================================
# COLUMNS
# ============================================================

LEDGER_COLUMNS = [
    {"key": "date", "label": "Date"},
    {"key": "particulars", "label": "Particulars"},
    {"key": "voucher_type", "label": "Vch Type"},
    {"key": "voucher_number", "label": "Vch No."},
    {"key": "debit", "label": "Debit"},
    {"key": "credit", "label": "Credit"},
    {"key": "running_balance", "label": "Balance"},
]

# P&L is a two-column (Dr | Cr) report - see get_profit_loss_report /
# export_profit_loss_report below for how "left"/"right" become
# actual columns for both the JSON API and the PDF/Excel export.
PROFIT_LOSS_COLUMNS = [
    {"key": "left_name", "label": "Particulars"},
    {"key": "left_amount", "label": "Amount"},
    {"key": "right_name", "label": "Particulars"},
    {"key": "right_amount", "label": "Amount"},
]

TRIAL_BALANCE_COLUMNS = [
    {"key": "name", "label": "Ledger"},
    {"key": "debit", "label": "Debit"},
    {"key": "credit", "label": "Credit"},
]

# Balance Sheet is two-sided (Liabilities | Assets), like Tally's own
# screen, so the export uses four columns - see _bs_rows_to_two_columns.
BALANCE_SHEET_COLUMNS = [
    {"key": "left_name", "label": "Liabilities"},
    {"key": "left_amount", "label": "Amount"},
    {"key": "right_name", "label": "Assets"},
    {"key": "right_amount", "label": "Amount"},
]

BILLS_COLUMNS = [
    {"key": "party", "label": "Party"},
    {"key": "bill_reference", "label": "Bill Ref."},
    {"key": "bill_date", "label": "Bill Date"},
    {"key": "due_date", "label": "Due Date"},
    {"key": "overdue_days", "label": "Overdue Days"},
    {"key": "outstanding_amount", "label": "Outstanding"},
]

STOCK_SUMMARY_COLUMNS = [
    {"key": "stock_item", "label": "Stock Item"},
    {"key": "stock_group", "label": "Stock Group"},
    {"key": "unit", "label": "Unit"},
    {"key": "opening_quantity", "label": "Opening Qty"},
    {"key": "opening_value", "label": "Opening Value"},
    {"key": "closing_quantity", "label": "Closing Qty"},
    {"key": "closing_rate", "label": "Closing Rate"},
    {"key": "closing_value", "label": "Closing Value"},
]

STOCK_GROUP_COLUMNS = [
    {"key": "stock_group", "label": "Stock Group"},
    {"key": "parent", "label": "Parent"},
    {"key": "base_units", "label": "Base Units"},
]

STOCK_CATEGORY_COLUMNS = [
    {"key": "stock_category", "label": "Stock Category"},
    {"key": "parent", "label": "Parent"},
]

GODOWN_COLUMNS = [
    {"key": "godown", "label": "Godown"},
    {"key": "parent", "label": "Parent"},
    {"key": "is_internal", "label": "Internal"},
]

STOCK_MOVEMENT_COLUMNS = [
    {"key": "date", "label": "Date"},
    {"key": "stock_item", "label": "Stock Item"},
    {"key": "voucher_type", "label": "Vch Type"},
    {"key": "voucher_number", "label": "Vch No."},
    {"key": "party", "label": "Party"},
    {"key": "quantity", "label": "Quantity"},
    {"key": "rate", "label": "Rate"},
    {"key": "value", "label": "Value"},
    {"key": "direction", "label": "Movement"},
]

STOCK_VALUATION_COLUMNS = [
    {"key": "stock_item", "label": "Stock Item"},
    {"key": "unit", "label": "Unit"},
    {"key": "closing_quantity", "label": "Closing Qty"},
    {"key": "valuation_rate", "label": "Valuation Rate"},
    {"key": "valuation_value", "label": "Valuation Value"},
]

NEGATIVE_STOCK_COLUMNS = [
    {"key": "stock_item", "label": "Stock Item"},
    {"key": "stock_group", "label": "Stock Group"},
    {"key": "unit", "label": "Unit"},
    {"key": "closing_quantity", "label": "Closing Qty"},
    {"key": "closing_rate", "label": "Closing Rate"},
    {"key": "closing_value", "label": "Closing Value"},
]

PENDING_INVOICES_COLUMNS = [
    {"key": "type", "label": "Type"},
    {"key": "party", "label": "Party"},
    {"key": "bill_reference", "label": "Bill Ref."},
    {"key": "bill_date", "label": "Bill Date"},
    {"key": "due_date", "label": "Due Date"},
    {"key": "overdue_days", "label": "Overdue Days"},
    {"key": "outstanding_amount", "label": "Outstanding"},
]



# ============================================================
# EXPORT HELPERS
# ============================================================

def _period_label(from_date=None, to_date=None, as_on=None) -> str | None:
    """Tally-style period line for a report header, e.g.
    '1-Apr-2024 to 31-Mar-2025' or 'as on 31-Mar-2025'."""
    if as_on:
        return f"as on {as_on.strftime('%d-%b-%Y')}"
    if from_date and to_date:
        return f"{from_date.strftime('%d-%b-%Y')} to {to_date.strftime('%d-%b-%Y')}"
    if to_date:
        return f"as on {to_date.strftime('%d-%b-%Y')}"
    return None


def _as_rows(report) -> list:
    """Some parsers return a flat list; others return
    {"success": ..., "rows": [...], "count": ...}. Normalize to a
    flat list either way so callers never have to care."""
    if isinstance(report, dict):
        return report.get("rows", [])
    return report or []


def _pl_rows_to_two_columns(report: dict) -> list:
    """
    parse_profit_loss() returns {"left": [...], "right": [...]} - two
    independently-lengthed columns. Zip them side by side into one
    row-per-line-pair list so the existing flat-table exporter
    (build_excel/build_pdf) can render it, padding the shorter side
    with blanks.
    """
    left = report.get("left", []) if isinstance(report, dict) else []
    right = report.get("right", []) if isinstance(report, dict) else []

    row_count = max(len(left), len(right))

    rows = []

    for i in range(row_count):
        left_row = left[i] if i < len(left) else None
        right_row = right[i] if i < len(right) else None

        rows.append(
            {
                "left_name": left_row["name"] if left_row else "",
                "left_amount": left_row["amount"] if left_row else "",
                "right_name": right_row["name"] if right_row else "",
                "right_amount": right_row["amount"] if right_row else "",
            }
        )

    return rows


def _download_headers(filename: str) -> dict:
    return {
        "Content-Disposition": f'attachment; filename="{filename}"'
    }


def _check_format(file_format: str) -> None:
    if file_format not in ("pdf", "xlsx"):
        raise HTTPException(
            status_code=400,
            detail="format must be 'pdf' or 'xlsx'",
        )


def _safe_name(*parts) -> str:
    text = "_".join(str(p) for p in parts if p not in (None, ""))
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_")
    return text or "report"


def _spec_response(file_format: str, spec: dict, filename_base: str):
    _check_format(file_format)

    if file_format == "xlsx":
        return Response(
            content=build_report_excel(spec),
            media_type=(
                "application/vnd.openxmlformats-officedocument"
                ".spreadsheetml.sheet"
            ),
            headers=_download_headers(f"{filename_base}.xlsx"),
        )

    return Response(
        content=build_report_pdf(spec),
        media_type="application/pdf",
        headers=_download_headers(f"{filename_base}.pdf"),
    )


def _export_response(
    file_format: str,
    title: str | None = None,
    columns: list | None = None,
    rows: list | None = None,
    company_name: str | None = None,
    filename_base: str = "report",
    footer: dict | None = None,
    period: str | None = None,
    spec: dict | None = None,
):
    if spec is not None:
        return _spec_response(file_format, spec, filename_base)

    if file_format not in ("pdf", "xlsx"):
        raise HTTPException(
            status_code=400,
            detail="format must be 'pdf' or 'xlsx'",
        )

    if file_format == "xlsx":
        content = build_excel(
            title=title,
            columns=columns,
            rows=rows,
            company_name=company_name,
            footer=footer,
            period=period,
        )

        return Response(
            content=content,
            media_type=(
                "application/vnd.openxmlformats-officedocument"
                ".spreadsheetml.sheet"
            ),
            headers=_download_headers(
                f"{filename_base}.xlsx"
            ),
        )

    content = build_pdf(
        title=title,
        columns=columns,
        rows=rows,
        company_name=company_name,
        footer=footer,
        period=period,
    )

    return Response(
        content=content,
        media_type="application/pdf",
        headers=_download_headers(
            f"{filename_base}.pdf"
        ),
    )




def _check_period(from_date: date | None, to_date: date | None) -> None:
    if from_date and to_date and from_date > to_date:
        raise HTTPException(
            status_code=400,
            detail="from_date cannot be later than to_date",
        )


def _fmt_period(resp: dict) -> str | None:
    return specs.period_label(resp.get("from"), resp.get("to"))


INVENTORY_REGISTER_COLUMNS = [
    {"key": "date", "label": "Date"},
    {"key": "particulars", "label": "Particulars"},
    {"key": "voucher_type", "label": "Vch Type"},
    {"key": "voucher_number", "label": "Vch No."},
    {"key": "item_name", "label": "Item Name"},
    {"key": "quantity", "label": "Quantity"},
    {"key": "rate", "label": "Rate"},
    {"key": "unit", "label": "Unit"},
    {"key": "amount", "label": "Amount"},
]
