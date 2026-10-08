import logging
from datetime import date
from typing import Any, Awaitable, Callable, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.cache.config import cache_settings, is_force_refresh
from app.cache.errors import is_tally_connectivity_error
from app.cache.keys import build_cache_key
from app.cache.manager import cache_manager, CacheResult
from app.security.auth import (
    UserContext,
    get_authorized_company,
    get_current_user,
)
from app.security.config import get_auth_settings

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
    effective_org_id = _resolve_org_id(current_user)
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

from app.tally.service import (
    fetch_profit_loss,
    fetch_group_summary,
    fetch_trial_balance,
    fetch_balance_sheet,
    fetch_balance_sheet_report,
    fetch_bill_allocations,
    fetch_bills_receivable,
    fetch_bills_payable,
    fetch_ledger_list,
    fetch_ledger_report,
    fetch_voucher_detail,
    fetch_stock_summary,
    fetch_stock_item,
    fetch_stock_groups,
    fetch_stock_categories,
    fetch_godowns,
    fetch_stock_movement,
    fetch_stock_valuation,
    fetch_negative_stock,
    fetch_inventory_register,
    fetch_stock_group_items,
    fetch_inventory_voucher_detail,
    fetch_stock_group_summary,
    fetch_stock_category_summary,
    fetch_godown_summary,
    fetch_stock_item_monthly,
    fetch_register_months,
    fetch_register_voucher_list,
    fetch_godown_item_monthly,
)

from app.tally.parsers.inventory_summary import with_root_row

from app.financial.service import (
    build_outstanding_summary,
    build_receivables_from_tally_report,
    build_payables_from_tally_report,
    build_pending_invoices_from_reports,
)

from app.export.exporter import build_excel, build_pdf


router = APIRouter()


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


def _export_response(
    file_format: str,
    title: str,
    columns: list,
    rows: list,
    company_name: str | None,
    filename_base: str,
    footer: dict | None = None,
    period: str | None = None,
):
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


# ============================================================
# PROFIT & LOSS
# ============================================================

@router.get("/profit-loss")
async def get_profit_loss_report(
    from_date: date | None = None,
    to_date: date | None = None,
    company_name: str | None = Depends(get_authorized_company),
    current_user: UserContext = Depends(get_current_user),
    force_refresh: bool = False,
    refresh: str | int | None = None,
):
    if from_date and to_date and from_date > to_date:
        raise HTTPException(
            status_code=400,
            detail="from_date cannot be later than to_date",
        )

    async def _fetch():
        return await fetch_profit_loss(
            from_date=from_date,
            to_date=to_date,
            company_name=company_name,
        )

    try:
        cache_res = await _cached_report(
            report_name="profit_loss",
            company_name=company_name,
            current_user=current_user,
            params={
                "from_date": from_date.isoformat() if from_date else None,
                "to_date": to_date.isoformat() if to_date else None,
            },
            fetcher=_fetch,
            force_refresh=force_refresh,
            refresh=refresh,
            ttl_name="profit_loss",
        )
        report = cache_res.data
        formatted_report = (
            {
                "left": report.get("left", []),
                "right": report.get("right", []),
                "total_left": report.get("total_left", 0),
                "total_right": report.get("total_right", 0),
            }
            if isinstance(report, dict)
            else report
        )

        return {
            "success": True,
            "source": cache_res.source,
            "is_stale": cache_res.is_stale,
            "cached_at": cache_res.cached_at,
            "report": formatted_report,
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Profit & Loss error: %r", e)

        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Profit & Loss from Tally",
        )


@router.get("/profit-loss/export/{file_format}")
async def export_profit_loss_report(
    file_format: str,
    from_date: date | None = None,
    to_date: date | None = None,
    company_name: str | None = Depends(get_authorized_company),
    current_user: UserContext = Depends(get_current_user),
):
    async def _fetch():
        return await fetch_profit_loss(
            from_date=from_date,
            to_date=to_date,
            company_name=company_name,
        )

    try:
        cache_res = await _cached_report(
            report_name="profit_loss",
            company_name=company_name,
            current_user=current_user,
            params={
                "from_date": from_date.isoformat() if from_date else None,
                "to_date": to_date.isoformat() if to_date else None,
            },
            fetcher=_fetch,
            ttl_name="profit_loss",
        )
        report = cache_res.data

    except Exception as e:
        logger.error("Profit & Loss export error: %r", e)

        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Profit & Loss from Tally",
        )

    return _export_response(
        file_format=file_format,
        title="Profit & Loss",
        columns=PROFIT_LOSS_COLUMNS,
        rows=_pl_rows_to_two_columns(report),
        company_name=company_name,
        filename_base="profit_and_loss",
        period=_period_label(from_date=from_date, to_date=to_date),
    )


# ============================================================
# GROUP SUMMARY (Profit & Loss / Balance Sheet drill-down)
# ============================================================

@router.get("/group-summary")
async def get_group_summary_report(
    group: str,
    company_name: str | None = Depends(get_authorized_company),
    from_date: date | None = None,
    to_date: date | None = None,
    current_user: UserContext = Depends(get_current_user),
    force_refresh: bool = False,
    refresh: str | int | None = None,
):
    """
    The screen Tally shows when you double-click a P&L/Balance Sheet
    group line (Direct Expenses, Indirect Expenses, Sales Accounts,
    Purchase Accounts, or any sub-group reached by drilling further,
    e.g. Office Exp). Each row is either another sub-group (drill
    again into /group-summary?group=<row.name>) or a ledger (drill
    into /ledger?ledger_name=<row.name>&view=monthly) - we mark
    which is which by checking the row name against the company's
    ledger list, since Tally's Group Summary XML doesn't flag it
    directly.
    """
    if from_date and to_date and from_date > to_date:
        raise HTTPException(
            status_code=400,
            detail="from_date cannot be later than to_date",
        )

    async def _fetch():
        report = await fetch_group_summary(
            group_name=group,
            from_date=from_date,
            to_date=to_date,
            company_name=company_name,
        )

        try:
            ledgers = await fetch_ledger_list(company_name=company_name)
            ledger_names = {
                (l.get("name") or "").strip().casefold()
                for l in ledgers
                if l.get("name")
            }
        except Exception:
            # If the ledger list call fails, fall back to treating
            # every row as a group rather than breaking the page -
            # the row is still clickable, just drills one level
            # further into Group Summary instead of the ledger.
            ledger_names = set()

        rows = []
        for row in report.get("rows", []):
            is_ledger = (row.get("name") or "").strip().casefold() in ledger_names
            rows.append({**row, "is_ledger": is_ledger, "is_group": not is_ledger})

        return {
            "group_name": report.get("group_name", group),
            "report": rows,
            "total_debit": report.get("total_debit", 0),
            "total_credit": report.get("total_credit", 0),
        }

    try:
        cache_res = await _cached_report(
            report_name="group_summary",
            company_name=company_name,
            current_user=current_user,
            params={
                "group": group,
                "from_date": from_date.isoformat() if from_date else None,
                "to_date": to_date.isoformat() if to_date else None,
            },
            fetcher=_fetch,
            force_refresh=force_refresh,
            refresh=refresh,
            ttl_name="group_summary",
        )
        data = cache_res.data
        return {
            "success": True,
            "source": cache_res.source,
            "is_stale": cache_res.is_stale,
            "cached_at": cache_res.cached_at,
            "group_name": data.get("group_name", group),
            "report": data.get("report", []),
            "total_debit": data.get("total_debit", 0),
            "total_credit": data.get("total_credit", 0),
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Group Summary error: %r", e)

        raise HTTPException(
            status_code=502,
            detail=f"Unable to fetch Group Summary for '{group}' from Tally",
        )


# ============================================================
# TRIAL BALANCE
# ============================================================

def _trial_balance_kwargs(
    company_name: str | None,
    from_date: date | None,
    to_date: date | None,
) -> dict:
    """
    Keyword arguments for fetch_trial_balance().

    from_date is only forwarded when the caller actually supplied
    one, so a request without a From Date behaves exactly as it did
    before the From/To filter was added.
    """
    kwargs = {
        "company_name": company_name,
        "to_date": to_date,
    }

    if from_date:
        kwargs["from_date"] = from_date

    return kwargs


@router.get("/trial-balance")
async def get_trial_balance_report(
    company_name: str | None = Depends(get_authorized_company),
    to_date: date | None = None,
    from_date: date | None = None,
    current_user: UserContext = Depends(get_current_user),
    force_refresh: bool = False,
    refresh: str | int | None = None,
):
    if from_date and to_date and from_date > to_date:
        raise HTTPException(
            status_code=400,
            detail="from_date cannot be later than to_date",
        )

    async def _fetch():
        return await fetch_trial_balance(
            **_trial_balance_kwargs(
                company_name, from_date, to_date
            )
        )

    try:
        cache_res = await _cached_report(
            report_name="trial_balance",
            company_name=company_name,
            current_user=current_user,
            params={
                "from_date": from_date.isoformat() if from_date else None,
                "to_date": to_date.isoformat() if to_date else None,
            },
            fetcher=_fetch,
            force_refresh=force_refresh,
            refresh=refresh,
            ttl_name="trial_balance",
        )
        report = cache_res.data

        return {
            "success": True,
            "source": cache_res.source,
            "is_stale": cache_res.is_stale,
            "cached_at": cache_res.cached_at,
            "from_date": from_date.isoformat() if from_date else None,
            "to_date": to_date.isoformat() if to_date else None,
            "report": _as_rows(report),
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Trial Balance error: %r", e)

        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Trial Balance from Tally",
        )


@router.get("/trial-balance/export/{file_format}")
async def export_trial_balance_report(
    file_format: str,
    company_name: str | None = Depends(get_authorized_company),
    to_date: date | None = None,
    from_date: date | None = None,
    current_user: UserContext = Depends(get_current_user),
):
    if from_date and to_date and from_date > to_date:
        raise HTTPException(
            status_code=400,
            detail="from_date cannot be later than to_date",
        )

    async def _fetch():
        return await fetch_trial_balance(
            **_trial_balance_kwargs(
                company_name, from_date, to_date
            )
        )

    try:
        cache_res = await _cached_report(
            report_name="trial_balance",
            company_name=company_name,
            current_user=current_user,
            params={
                "from_date": from_date.isoformat() if from_date else None,
                "to_date": to_date.isoformat() if to_date else None,
            },
            fetcher=_fetch,
            ttl_name="trial_balance",
        )
        report = cache_res.data

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Trial Balance export error: %r", e)

        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Trial Balance from Tally",
        )

    rows = _as_rows(report)

    # See parse_group_summary in parsers/financial.py: Tally's own
    # footer sums the magnitude of each row, not the signed value, so
    # a negative ("(-)") row still adds its full amount to the total.
    total_debit = sum(
        abs(row.get("debit") or 0)
        for row in rows
    )

    total_credit = sum(
        abs(row.get("credit") or 0)
        for row in rows
    )

    return _export_response(
        file_format=file_format,
        title="Trial Balance",
        columns=TRIAL_BALANCE_COLUMNS,
        rows=rows,
        company_name=company_name,
        filename_base="trial_balance",
        footer={
            "label": f"Total (Credit: {total_credit:,.2f})",
            "key": "debit",
            "value": total_debit,
        },
        period=_period_label(from_date=from_date, to_date=to_date),
    )


# ------------------------------------------------------------
# Trial Balance drill-down: Purchase Bills Pending
#
# Reached from Trial Balance -> Purchase Accounts -> Purchase Bills
# to Come. Tally's "Purchase Bills Pending" screen lists goods that
# have been received (Receipt Notes) but not yet billed, item by
# item. The rows are built from the company's real Receipt Note
# vouchers for the selected period, using the same voucher/stock
# parser the Stock Item Vouchers screen already uses.
# ------------------------------------------------------------

@router.get("/trial-balance/purchase-bills-pending")
async def get_trial_balance_purchase_bills_pending(
    company_name: str | None = Depends(get_authorized_company),
    from_date: date | None = None,
    to_date: date | None = None,
    current_user: UserContext = Depends(get_current_user),
    force_refresh: bool = False,
    refresh: str | int | None = None,
):
    if from_date and to_date and from_date > to_date:
        raise HTTPException(
            status_code=400,
            detail="from_date cannot be later than to_date",
        )

    async def _fetch():
        report = await fetch_stock_movement(
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
        )

        # Tally's "Purchase Bills Pending" screen is built from its
        # Tracking Number (Order/Bill pending) feature: goods received
        # against a tracking number (usually a Receipt Note) minus
        # whatever has since been billed against that same tracking
        # number (a Purchase voucher referencing it). Filtering by
        # voucher type name (e.g. only "Receipt Note") dropped items
        # whose bill has been partially raised, which is exactly the
        # case Tally's own screen is meant to surface - so every
        # voucher type is considered here and the two are netted per
        # (stock item, tracking number) instead.
        groups: dict[tuple[str, str], dict] = {}

        for row in report.get("rows", []):
            tracking_number = row.get("tracking_number")
            stock_item = row.get("stock_item")

            if not tracking_number or not stock_item:
                continue

            key = (stock_item, tracking_number)

            quantity = row.get("quantity", 0) or 0
            amount = row.get("amount", 0) or 0

            if key not in groups:
                groups[key] = {
                    "date": row.get("date"),
                    "tracking_number": tracking_number,
                    "stock_item": stock_item,
                    "party": row.get("party"),
                    "rate": row.get("rate", 0),
                    "initial_quantity": 0,
                    "pending_quantity": 0,
                    "value": 0,
                }

            group = groups[key]

            # The largest single movement against a tracking number is
            # the original goods-received quantity; later, smaller
            # movements are partial billings against it.
            if abs(quantity) > abs(group["initial_quantity"]):
                group["initial_quantity"] = quantity
                group["date"] = row.get("date")
                group["party"] = row.get("party") or group["party"]
                group["rate"] = row.get("rate", 0) or group["rate"]

            group["pending_quantity"] += quantity
            group["value"] += amount

        # Only tracking numbers that still have an outstanding
        # quantity are "pending" - a fully billed one has netted to
        # zero and Tally would no longer show it on this screen.
        rows = [
            group
            for group in groups.values()
            if round(group["pending_quantity"], 4) != 0
        ]

        rows.sort(key=lambda r: (r["date"] or "", r["tracking_number"] or ""))

        return {
            "report": rows,
            "count": len(rows),
            "total_value": sum(row["value"] or 0 for row in rows),
        }

    try:
        cache_res = await _cached_report(
            report_name="purchase_bills_pending",
            company_name=company_name,
            current_user=current_user,
            params={
                "from_date": from_date.isoformat() if from_date else None,
                "to_date": to_date.isoformat() if to_date else None,
            },
            fetcher=_fetch,
            force_refresh=force_refresh,
            refresh=refresh,
            ttl_name="purchase_bills_pending",
        )
        data = cache_res.data

        return {
            "success": True,
            "source": cache_res.source,
            "is_stale": cache_res.is_stale,
            "cached_at": cache_res.cached_at,
            "report": data.get("report", []),
            "count": data.get("count", 0),
            "total_value": data.get("total_value", 0),
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Trial Balance Purchase Bills Pending error: %r", e)

        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Purchase Bills Pending from Tally",
        )


# ============================================================
# BALANCE SHEET
# ============================================================

def _bs_rows_to_two_columns(report: dict) -> list:
    """
    Lay the Balance Sheet out the way Tally prints it: Liabilities on
    the left, Assets on the right, sub-lines (e.g. Profit & Loss A/c ->
    Current Period) directly under their parent, and a Total row.
    """

    def flatten(rows):
        flat = []
        for row in rows:
            flat.append((row["name"], row["amount"]))
            for child in row.get("children", []):
                flat.append((f"    {child['name']}", child["amount"]))
        return flat

    left = flatten(report.get("liabilities", []))
    right = flatten(report.get("assets", []))

    rows = []

    for i in range(max(len(left), len(right))):
        l_name, l_amount = left[i] if i < len(left) else ("", "")
        r_name, r_amount = right[i] if i < len(right) else ("", "")
        rows.append(
            {
                "left_name": l_name,
                "left_amount": l_amount,
                "right_name": r_name,
                "right_amount": r_amount,
            }
        )

    rows.append(
        {
            "left_name": "Total",
            "left_amount": report.get("total_liabilities", 0),
            "right_name": "Total",
            "right_amount": report.get("total_assets", 0),
        }
    )

    return rows


@router.get("/balance-sheet")
async def get_balance_sheet_report(
    company_name: str | None = Depends(get_authorized_company),
    from_date: date | None = None,
    to_date: date | None = None,
    current_user: UserContext = Depends(get_current_user),
    force_refresh: bool = False,
    refresh: str | int | None = None,
):
    if from_date and to_date and from_date > to_date:
        raise HTTPException(
            status_code=400,
            detail="from_date cannot be later than to_date",
        )

    async def _fetch():
        return await fetch_balance_sheet_report(
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
        )

    try:
        cache_res = await _cached_report(
            report_name="balance_sheet",
            company_name=company_name,
            current_user=current_user,
            params={
                "from_date": from_date.isoformat() if from_date else None,
                "to_date": to_date.isoformat() if to_date else None,
            },
            fetcher=_fetch,
            force_refresh=force_refresh,
            refresh=refresh,
            ttl_name="balance_sheet",
        )
        report = cache_res.data

        return {
            "success": True,
            "source": cache_res.source,
            "is_stale": cache_res.is_stale,
            "cached_at": cache_res.cached_at,
            "company_name": company_name,
            "from_date": from_date.isoformat() if from_date else None,
            "to_date": to_date.isoformat() if to_date else None,
            "report": {
                "liabilities": report["liabilities"],
                "assets": report["assets"],
                "total_liabilities": report["total_liabilities"],
                "total_assets": report["total_assets"],
                "difference": report["difference"],
            },
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Balance Sheet error: %r", e)

        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Balance Sheet from Tally",
        )


@router.get("/balance-sheet/export/{file_format}")
async def export_balance_sheet_report(
    file_format: str,
    company_name: str | None = Depends(get_authorized_company),
    from_date: date | None = None,
    to_date: date | None = None,
    current_user: UserContext = Depends(get_current_user),
):
    if from_date and to_date and from_date > to_date:
        raise HTTPException(
            status_code=400,
            detail="from_date cannot be later than to_date",
        )

    async def _fetch():
        return await fetch_balance_sheet_report(
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
        )

    try:
        cache_res = await _cached_report(
            report_name="balance_sheet",
            company_name=company_name,
            current_user=current_user,
            params={
                "from_date": from_date.isoformat() if from_date else None,
                "to_date": to_date.isoformat() if to_date else None,
            },
            fetcher=_fetch,
            ttl_name="balance_sheet",
        )
        report = cache_res.data

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Balance Sheet export error: %r", e)

        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Balance Sheet from Tally",
        )

    return _export_response(
        file_format=file_format,
        title="Balance Sheet",
        columns=BALANCE_SHEET_COLUMNS,
        rows=_bs_rows_to_two_columns(report),
        company_name=company_name,
        filename_base="balance_sheet",
        period=_period_label(from_date=from_date, to_date=to_date),
    )


# ============================================================
# BILL ALLOCATIONS
# ============================================================

@router.get("/bill-allocations")
async def get_bill_allocations(
    company_name: str | None = Depends(get_authorized_company),
    current_user: UserContext = Depends(get_current_user),
    force_refresh: bool = False,
    refresh: str | int | None = None,
):
    async def _fetch():
        return await fetch_bill_allocations(
            company_name=company_name,
        )

    try:
        cache_res = await _cached_report(
            report_name="bill_allocations",
            company_name=company_name,
            current_user=current_user,
            params={},
            fetcher=_fetch,
            force_refresh=force_refresh,
            refresh=refresh,
            ttl_name="bill_allocations",
        )
        bills = cache_res.data

        return {
            "success": True,
            "source": cache_res.source,
            "is_stale": cache_res.is_stale,
            "cached_at": cache_res.cached_at,
            "count": len(bills),
            "bills": bills,
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Bill allocations error: %r", e)

        raise HTTPException(
            status_code=502,
            detail="Unable to fetch bill allocations from Tally",
        )


# ============================================================
# RECEIVABLES
# ============================================================

@router.get("/receivables")
async def get_receivables_report(
    company_name: str | None = Depends(get_authorized_company),
    current_user: UserContext = Depends(get_current_user),
    force_refresh: bool = False,
    refresh: str | int | None = None,
):
    async def _fetch():
        tally_bills = await fetch_bills_receivable(
            company_name=company_name,
        )

        allocations = await fetch_bill_allocations(
            company_name=company_name,
        )

        outstanding = build_outstanding_summary(
            allocations
        )

        return build_receivables_from_tally_report(
            tally_bills,
            outstanding,
        )

    try:
        cache_res = await _cached_report(
            report_name="bills_receivable",
            company_name=company_name,
            current_user=current_user,
            params={},
            fetcher=_fetch,
            force_refresh=force_refresh,
            refresh=refresh,
            ttl_name="bills_receivable",
        )

        return {
            "success": True,
            "source": cache_res.source,
            "is_stale": cache_res.is_stale,
            "cached_at": cache_res.cached_at,
            "data": cache_res.data,
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Receivables error: %r", e)

        raise HTTPException(
            status_code=502,
            detail="Unable to fetch receivables from Tally",
        )


@router.get("/receivables/export/{file_format}")
async def export_receivables_report(
    file_format: str,
    company_name: str | None = Depends(get_authorized_company),
    current_user: UserContext = Depends(get_current_user),
):
    async def _fetch():
        tally_bills = await fetch_bills_receivable(
            company_name=company_name,
        )

        allocations = await fetch_bill_allocations(
            company_name=company_name,
        )

        outstanding = build_outstanding_summary(
            allocations
        )

        return build_receivables_from_tally_report(
            tally_bills,
            outstanding,
        )

    try:
        cache_res = await _cached_report(
            report_name="bills_receivable",
            company_name=company_name,
            current_user=current_user,
            params={},
            fetcher=_fetch,
            ttl_name="bills_receivable",
        )
        data = cache_res.data

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Receivables export error: %r", e)

        raise HTTPException(
            status_code=502,
            detail="Unable to fetch receivables from Tally",
        )

    return _export_response(
        file_format=file_format,
        title="Receivables",
        columns=BILLS_COLUMNS,
        rows=data["bills"],
        company_name=company_name,
        filename_base="receivables",
        footer={
            "label": "Total Receivable",
            "key": "outstanding_amount",
            "value": data["total_receivable"],
        },
    )


# ============================================================
# PAYABLES
# ============================================================

@router.get("/payables")
async def get_payables_report(
    company_name: str | None = Depends(get_authorized_company),
    current_user: UserContext = Depends(get_current_user),
    force_refresh: bool = False,
    refresh: str | int | None = None,
):
    async def _fetch():
        tally_bills = await fetch_bills_payable(
            company_name=company_name,
        )

        allocations = await fetch_bill_allocations(
            company_name=company_name,
        )

        outstanding = build_outstanding_summary(
            allocations
        )

        return build_payables_from_tally_report(
            tally_bills,
            outstanding,
        )

    try:
        cache_res = await _cached_report(
            report_name="bills_payable",
            company_name=company_name,
            current_user=current_user,
            params={},
            fetcher=_fetch,
            force_refresh=force_refresh,
            refresh=refresh,
            ttl_name="bills_payable",
        )

        return {
            "success": True,
            "source": cache_res.source,
            "is_stale": cache_res.is_stale,
            "cached_at": cache_res.cached_at,
            "data": cache_res.data,
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Payables error: %r", e)

        raise HTTPException(
            status_code=502,
            detail="Unable to fetch payables from Tally",
        )


@router.get("/payables/export/{file_format}")
async def export_payables_report(
    file_format: str,
    company_name: str | None = Depends(get_authorized_company),
    current_user: UserContext = Depends(get_current_user),
):
    async def _fetch():
        tally_bills = await fetch_bills_payable(
            company_name=company_name,
        )

        allocations = await fetch_bill_allocations(
            company_name=company_name,
        )

        outstanding = build_outstanding_summary(
            allocations
        )

        return build_payables_from_tally_report(
            tally_bills,
            outstanding,
        )

    try:
        cache_res = await _cached_report(
            report_name="bills_payable",
            company_name=company_name,
            current_user=current_user,
            params={},
            fetcher=_fetch,
            ttl_name="bills_payable",
        )
        data = cache_res.data

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Payables export error: %r", e)

        raise HTTPException(
            status_code=502,
            detail="Unable to fetch payables from Tally",
        )

    return _export_response(
        file_format=file_format,
        title="Payables",
        columns=BILLS_COLUMNS,
        rows=data["bills"],
        company_name=company_name,
        filename_base="payables",
        footer={
            "label": "Total Payable",
            "key": "outstanding_amount",
            "value": data["total_payable"],
        },
    )


# ============================================================
# LEDGER LIST
# ============================================================

@router.get("/ledgers")
async def get_ledger_list(
    company_name: str | None = Depends(get_authorized_company),
    current_user: UserContext = Depends(get_current_user),
    force_refresh: bool = False,
    refresh: str | int | None = None,
):
    async def _fetch():
        return await fetch_ledger_list(
            company_name=company_name,
        )

    try:
        cache_res = await _cached_report(
            report_name="ledger_list",
            company_name=company_name,
            current_user=current_user,
            params={},
            fetcher=_fetch,
            force_refresh=force_refresh,
            refresh=refresh,
            ttl_name="ledger_list",
        )
        ledgers = cache_res.data

        return {
            "success": True,
            "source": cache_res.source,
            "is_stale": cache_res.is_stale,
            "cached_at": cache_res.cached_at,
            "count": len(ledgers),
            "ledgers": ledgers,
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Ledger list error: %r", e)

        raise HTTPException(
            status_code=502,
            detail="Unable to fetch ledger list from Tally",
        )


# ============================================================
# LEDGER REPORT
# ============================================================

@router.get("/ledger")
async def get_ledger_report(
    ledger_name: str,
    company_name: str | None = Depends(get_authorized_company),
    from_date: date | None = None,
    to_date: date | None = None,
    current_user: UserContext = Depends(get_current_user),
    force_refresh: bool = False,
    refresh: str | int | None = None,
):
    if from_date and to_date and from_date > to_date:
        raise HTTPException(
            status_code=400,
            detail="from_date cannot be later than to_date",
        )

    async def _fetch():
        return await fetch_ledger_report(
            ledger_name=ledger_name,
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
        )

    try:
        cache_res = await _cached_report(
            report_name="ledger_report",
            company_name=company_name,
            current_user=current_user,
            params={
                "ledger_name": ledger_name,
                "from_date": from_date.isoformat() if from_date else None,
                "to_date": to_date.isoformat() if to_date else None,
            },
            fetcher=_fetch,
            force_refresh=force_refresh,
            refresh=refresh,
            ttl_name="ledger_report",
        )

        return {
            "success": True,
            "source": cache_res.source,
            "is_stale": cache_res.is_stale,
            "cached_at": cache_res.cached_at,
            "report": cache_res.data,
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Ledger report error: %r", e)

        raise HTTPException(
            status_code=502,
            detail=(
                f"Unable to fetch ledger "
                f"'{ledger_name}' from Tally: {str(e)}"
            ),
        )


# ============================================================
# LEDGER EXPORT
# ============================================================

@router.get("/ledger/export/{file_format}")
async def export_ledger_report(
    file_format: str,
    ledger_name: str,
    company_name: str | None = Depends(get_authorized_company),
    from_date: date | None = None,
    to_date: date | None = None,
    current_user: UserContext = Depends(get_current_user),
):
    if from_date and to_date and from_date > to_date:
        raise HTTPException(
            status_code=400,
            detail="from_date cannot be later than to_date",
        )

    async def _fetch():
        return await fetch_ledger_report(
            ledger_name=ledger_name,
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
        )

    try:
        cache_res = await _cached_report(
            report_name="ledger_report",
            company_name=company_name,
            current_user=current_user,
            params={
                "ledger_name": ledger_name,
                "from_date": from_date.isoformat() if from_date else None,
                "to_date": to_date.isoformat() if to_date else None,
            },
            fetcher=_fetch,
            ttl_name="ledger_report",
        )
        report = cache_res.data

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Ledger export error: %r", e)

        raise HTTPException(
            status_code=502,
            detail=(
                f"Unable to fetch ledger "
                f"'{ledger_name}' from Tally: {str(e)}"
            ),
        )

    opening_balance = report.get(
        "opening_balance",
        0
    ) or 0

    opening_row = {
        "date": "",
        "particulars": "Opening Balance",
        "voucher_type": "",
        "voucher_number": "",
        "debit": (
            opening_balance
            if opening_balance > 0
            else 0
        ),
        "credit": (
            abs(opening_balance)
            if opening_balance < 0
            else 0
        ),
        "running_balance": opening_balance,
        "diff_in_tax_amount": 0,
        "balance_after_diff_in_tax": opening_balance,
        "status": "",
        "reference_number": "",
        "narration": "",
    }

    rows = [
        opening_row
    ] + report.get("entries", [])

    return _export_response(
        file_format=file_format,
        title=f"Ledger: {ledger_name}",
        columns=LEDGER_COLUMNS,
        rows=rows,
        company_name=company_name,
        filename_base=(
            f"{ledger_name.strip()}"
            .replace(" ", "_")
            .replace("/", "-")
            + "_ledger"
        ),
        footer={
            "label": "Closing Balance",
            "key": "running_balance",
            "value": report.get(
                "closing_balance"
            ),
        },
        period=_period_label(from_date=from_date, to_date=to_date),
    )


# ============================================================
# VOUCHER DETAIL (drill-down from a Ledger transaction row)
# ============================================================

@router.get("/voucher")
async def get_voucher_detail(
    voucher_type: str,
    voucher_number: str,
    date: date | None = None,
    ledger_name: str | None = None,
    company_name: str | None = Depends(get_authorized_company),
    current_user: UserContext = Depends(get_current_user),
    force_refresh: bool = False,
    refresh: str | int | None = None,
):
    """
    Full accounting voucher (every ledger allocation, narration,
    reference) for one transaction - what you land on when you
    click a row in a Ledger report, matching Tally's own
    "Accounting Voucher Alteration" screen.

    ledger_name is optional context: when supplied, the response
    marks which ledger line is the one the user drilled in from, so
    the frontend can show it as "Account" the way Tally does, with
    the other ledger line(s) as "Particulars".
    """
    async def _fetch():
        vouchers = await fetch_voucher_detail(
            voucher_type=voucher_type,
            voucher_number=voucher_number,
            voucher_date=date,
            company_name=company_name,
        )

        if not vouchers:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Voucher '{voucher_type} {voucher_number}' "
                    f"was not found in Tally."
                ),
            )

        voucher = vouchers[0]

        if ledger_name:
            target = ledger_name.strip().casefold()

            for entry in voucher.get("entries", []):
                entry["is_selected_ledger"] = (
                    (entry.get("ledger_name") or "")
                    .strip()
                    .casefold()
                    == target
                )

        return voucher

    try:
        cache_res = await _cached_report(
            report_name="voucher_detail",
            company_name=company_name,
            current_user=current_user,
            params={
                "voucher_type": voucher_type,
                "voucher_number": voucher_number,
                "date": date.isoformat() if date else None,
                "ledger_name": ledger_name,
            },
            fetcher=_fetch,
            force_refresh=force_refresh,
            refresh=refresh,
            ttl_name="voucher_detail",
        )

        return {
            "success": True,
            "source": cache_res.source,
            "is_stale": cache_res.is_stale,
            "cached_at": cache_res.cached_at,
            "voucher": cache_res.data,
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Voucher detail error: %r", e)

        raise HTTPException(
            status_code=502,
            detail=(
                f"Unable to fetch voucher "
                f"'{voucher_type} {voucher_number}' from Tally: {str(e)}"
            ),
        )


# ============================================================
# PENDING INVOICES
# ============================================================

@router.get("/pending-invoices")
async def get_pending_invoices_report(
    company_name: str | None = Depends(get_authorized_company),
    current_user: UserContext = Depends(get_current_user),
    force_refresh: bool = False,
    refresh: str | int | None = None,
):
    async def _fetch():
        receivable_bills = await fetch_bills_receivable(
            company_name=company_name,
        )

        payable_bills = await fetch_bills_payable(
            company_name=company_name,
        )

        allocations = await fetch_bill_allocations(
            company_name=company_name,
        )

        outstanding = build_outstanding_summary(
            allocations
        )

        receivables_data = (
            build_receivables_from_tally_report(
                receivable_bills,
                outstanding,
            )
        )

        payables_data = (
            build_payables_from_tally_report(
                payable_bills,
                outstanding,
            )
        )

        return build_pending_invoices_from_reports(
            receivables_data,
            payables_data,
        )

    try:
        cache_res = await _cached_report(
            report_name="pending_invoices",
            company_name=company_name,
            current_user=current_user,
            params={},
            fetcher=_fetch,
            force_refresh=force_refresh,
            refresh=refresh,
            ttl_name="pending_invoices",
        )

        return {
            "success": True,
            "source": cache_res.source,
            "is_stale": cache_res.is_stale,
            "cached_at": cache_res.cached_at,
            "data": cache_res.data,
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Pending invoices error: %r", e)

        raise HTTPException(
            status_code=502,
            detail="Unable to fetch pending invoices from Tally",
        )


@router.get("/pending-invoices/export/{file_format}")
async def export_pending_invoices_report(
    file_format: str,
    company_name: str | None = Depends(get_authorized_company),
    current_user: UserContext = Depends(get_current_user),
):
    async def _fetch():
        receivable_bills = await fetch_bills_receivable(
            company_name=company_name,
        )

        payable_bills = await fetch_bills_payable(
            company_name=company_name,
        )

        allocations = await fetch_bill_allocations(
            company_name=company_name,
        )

        outstanding = build_outstanding_summary(
            allocations
        )

        receivables_data = (
            build_receivables_from_tally_report(
                receivable_bills,
                outstanding,
            )
        )

        payables_data = (
            build_payables_from_tally_report(
                payable_bills,
                outstanding,
            )
        )

        return build_pending_invoices_from_reports(
            receivables_data,
            payables_data,
        )

    try:
        cache_res = await _cached_report(
            report_name="pending_invoices",
            company_name=company_name,
            current_user=current_user,
            params={},
            fetcher=_fetch,
            ttl_name="pending_invoices",
        )
        data = cache_res.data

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Pending invoices export error: %r", e)

        raise HTTPException(
            status_code=502,
            detail="Unable to fetch pending invoices from Tally",
        )

    return _export_response(
        file_format=file_format,
        title="Pending Invoices",
        columns=PENDING_INVOICES_COLUMNS,
        rows=data["invoices"],
        company_name=company_name,
        filename_base="pending_invoices",
    )


# ============================================================
# STOCK & INVENTORY
# ============================================================
#
# These endpoints back the "Stock" section of the app:
#   Stock -> Stock Summary
#   Inventory:
#     1. Stock Item     -> List of Stock Items -> Stock Monthly Summary
#     2. Location        -> Select Location -> Location Summary
#                            -> Location Monthly Summary
#     3. Stock Group     -> Stock Group Summary -> Stock Monthly Summary
#
# All data is fetched live from the Tally server via app.tally.service
# (which in turn uses the same TallyClient/XML pipeline as every other
# report in this file) - nothing here is hardcoded.


def _stock_summary_row(row: dict) -> dict:
    """
    Normalize one Stock Summary row.

    All values originate from the Tally Stock Summary response.
    No stock values are calculated or hardcoded here.
    """

    return {
        "stock_item": row.get("name"),
        "stock_group": row.get("parent"),
        "unit": row.get("base_units"),
        "opening_quantity": row.get("opening_quantity"),
        "opening_value": row.get("opening_value"),
        "closing_quantity": row.get("closing_quantity"),
        "closing_rate": row.get("closing_rate"),
        "closing_value": row.get("closing_value"),
    }

# The three master lists below always start with Tally's implicit
# "Primary" root (see with_root_row) - Tally shows it in "List of Stock
# Groups / Categories / Godowns" even though it is not a master object.

def _stock_group_row(row: dict) -> dict:
    return {
        "stock_group": row.get("name"),
        "parent": row.get("parent"),
        "base_units": row.get("base_units"),
        "is_primary": bool(row.get("is_primary")),
    }


def _stock_category_row(row: dict) -> dict:
    return {
        "stock_category": row.get("name"),
        "parent": row.get("parent"),
        "is_primary": bool(row.get("is_primary")),
    }


def _godown_row(row: dict) -> dict:
    return {
        "godown": row.get("name"),
        "parent": row.get("parent"),
        "is_internal": row.get("is_internal"),
        "is_primary": bool(row.get("is_primary")),
    }


def _summary_response(summary: dict | None, label: str, selected: str | None) -> dict:
    """Shared 404 / payload shape for the three <X> Summary endpoints."""
    if summary is None:
        raise HTTPException(
            status_code=404,
            detail=f"{label} '{selected}' was not found in Tally",
        )

    return {
        "success": True,
        "source": "tally",
        "selected": summary["selected"],
        "report": summary["rows"],
        "totals": summary["totals"],
        "count": len(summary["rows"]),
    }


def _check_period(from_date: date | None, to_date: date | None) -> None:
    if from_date and to_date and from_date > to_date:
        raise HTTPException(
            status_code=400,
            detail="from_date cannot be later than to_date",
        )


def _stock_movement_row(row: dict) -> dict:
    quantity = row.get("quantity", 0) or 0

    # Tally's ACTUALQTY is unsigned; ISDEEMEDPOSITIVE says whether the
    # entry brought stock in (Yes) or took it out (No). Sign the
    # quantity so the monthly / location pages, which split inward and
    # outward on the sign, classify every entry correctly.
    deemed = row.get("is_deemed_positive")

    if deemed is True:
        quantity = abs(quantity)
    elif deemed is False:
        quantity = -abs(quantity)

    row = {**row, "quantity": quantity}

    return {
        **row,
        "value": row.get("amount", 0),
        "direction": "Inward" if quantity >= 0 else "Outward",
    }


def _stock_valuation_row(row: dict) -> dict:
    return {
        "stock_item": row.get("name"),
        "unit": row.get("base_units"),
        "closing_quantity": row.get("quantity", 0),
        "valuation_rate": row.get("rate", 0),
        "valuation_value": row.get("value", 0),
    }


@router.get("/stock-summary")
async def get_stock_summary_report(
    company_name: str | None = Depends(get_authorized_company),
    to_date: date | None = None,
    from_date: date | None = None,
    current_user: UserContext = Depends(get_current_user),
    force_refresh: bool = False,
    refresh: str | int | None = None,
):
    _check_period(from_date, to_date)

    async def _fetch():
        report = await fetch_stock_summary(
            company_name=company_name,
            to_date=to_date,
            from_date=from_date,
        )
        return [_stock_summary_row(r) for r in report.get("rows", [])]

    try:
        cache_res = await _cached_report(
            report_name="stock_summary",
            company_name=company_name,
            current_user=current_user,
            params={
                "from_date": from_date.isoformat() if from_date else None,
                "to_date": to_date.isoformat() if to_date else None,
            },
            fetcher=_fetch,
            force_refresh=force_refresh,
            refresh=refresh,
            ttl_name="stock_summary",
        )
        rows = cache_res.data

        return {
            "success": True,
            "source": cache_res.source,
            "is_stale": cache_res.is_stale,
            "cached_at": cache_res.cached_at,
            "report": rows,
            "count": len(rows),
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Stock Summary error: %r", e)
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Stock Summary from Tally",
        )


@router.get("/stock-summary/export/{file_format}")
async def export_stock_summary_report(
    file_format: str,
    company_name: str | None = Depends(get_authorized_company),
    to_date: date | None = None,
    from_date: date | None = None,
    current_user: UserContext = Depends(get_current_user),
):
    _check_period(from_date, to_date)

    async def _fetch():
        report = await fetch_stock_summary(
            company_name=company_name,
            to_date=to_date,
            from_date=from_date,
        )
        return [_stock_summary_row(r) for r in report.get("rows", [])]

    try:
        cache_res = await _cached_report(
            report_name="stock_summary",
            company_name=company_name,
            current_user=current_user,
            params={
                "from_date": from_date.isoformat() if from_date else None,
                "to_date": to_date.isoformat() if to_date else None,
            },
            fetcher=_fetch,
            ttl_name="stock_summary",
        )
        rows = cache_res.data
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Stock Summary export error: %r", e)
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Stock Summary from Tally",
        )

    total_value = sum(row.get("closing_value") or 0 for row in rows)

    return _export_response(
        file_format=file_format,
        title="Stock Summary",
        columns=STOCK_SUMMARY_COLUMNS,
        rows=rows,
        company_name=company_name,
        filename_base="stock_summary",
        footer={
            "label": "Total Closing Value",
            "key": "closing_value",
            "value": total_value,
        },
        period=_period_label(from_date=from_date, to_date=to_date),
    )


# ------------------------------------------------------------------
# Stock Item (single item detail - used to seed "opening balance"
# for the Stock Item Monthly Summary screen)
# ------------------------------------------------------------------

@router.get("/stock-item")
async def get_stock_item_report(
    stock_item_name: str,
    company_name: str | None = Depends(get_authorized_company),
    from_date: date | None = None,
    to_date: date | None = None,
    current_user: UserContext = Depends(get_current_user),
    force_refresh: bool = False,
    refresh: str | int | None = None,
):
    async def _fetch():
        report = await fetch_stock_item(
            company_name=company_name,
            stock_item_name=stock_item_name,
            from_date=from_date,
            to_date=to_date,
        )
        return [_stock_summary_row(r) for r in report.get("rows", [])]

    try:
        cache_res = await _cached_report(
            report_name="stock_item",
            company_name=company_name,
            current_user=current_user,
            params={
                "stock_item_name": stock_item_name,
                "from_date": from_date.isoformat() if from_date else None,
                "to_date": to_date.isoformat() if to_date else None,
            },
            fetcher=_fetch,
            force_refresh=force_refresh,
            refresh=refresh,
            ttl_name="stock_item",
        )
        rows = cache_res.data

        return {
            "success": True,
            "source": cache_res.source,
            "is_stale": cache_res.is_stale,
            "cached_at": cache_res.cached_at,
            "report": rows,
            "item": rows[0] if rows else None,
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Stock Item error: %r", e)
        raise HTTPException(
            status_code=502,
            detail=f"Unable to fetch stock item '{stock_item_name}' from Tally",
        )


# ------------------------------------------------------------------
# Inventory Voucher Alteration (Stock/Inventory drill-down)
# ------------------------------------------------------------------

@router.get("/inventory-voucher")
async def get_inventory_voucher_detail_report(
    voucher_type: str,
    voucher_number: str,
    voucher_date: date | None = None,
    company_name: str | None = Depends(get_authorized_company),
    current_user: UserContext = Depends(get_current_user),
    force_refresh: bool = False,
    refresh: str | int | None = None,
):
    async def _fetch():
        return await fetch_inventory_voucher_detail(
            voucher_type=voucher_type,
            voucher_number=voucher_number,
            voucher_date=voucher_date,
            company_name=company_name,
        )

    try:
        cache_res = await _cached_report(
            report_name="inventory_voucher",
            company_name=company_name,
            current_user=current_user,
            params={
                "voucher_type": voucher_type,
                "voucher_number": voucher_number,
                "voucher_date": voucher_date.isoformat() if voucher_date else None,
            },
            fetcher=_fetch,
            force_refresh=force_refresh,
            refresh=refresh,
            ttl_name="inventory_voucher",
        )
        report = cache_res.data

        return {
            "success": True,
            "source": cache_res.source,
            "is_stale": cache_res.is_stale,
            "cached_at": cache_res.cached_at,
            "voucher": report.get("voucher") if isinstance(report, dict) else report,
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Inventory Voucher Detail error: %r", e)
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Inventory Voucher Alteration from Tally",
        )


# ------------------------------------------------------------------
# Stock Group Summary (list) + Stock Group Items (drill-down)
# ------------------------------------------------------------------

@router.get("/stock-groups")
async def get_stock_groups_report(
    company_name: str | None = Depends(get_authorized_company),
    current_user: UserContext = Depends(get_current_user),
    force_refresh: bool = False,
    refresh: str | int | None = None,
):
    async def _fetch():
        report = await fetch_stock_groups(company_name=company_name)
        return [
            _stock_group_row(r)
            for r in with_root_row(report.get("rows", []), "name")
        ]

    try:
        cache_res = await _cached_report(
            report_name="stock_groups",
            company_name=company_name,
            current_user=current_user,
            params={},
            fetcher=_fetch,
            force_refresh=force_refresh,
            refresh=refresh,
            ttl_name="stock_groups",
        )
        rows = cache_res.data

        return {
            "success": True,
            "source": cache_res.source,
            "is_stale": cache_res.is_stale,
            "cached_at": cache_res.cached_at,
            "report": rows,
            "count": len(rows),
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Stock Groups error: %r", e)
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Stock Group Summary from Tally",
        )


@router.get("/stock-groups/export/{file_format}")
async def export_stock_groups_report(
    file_format: str,
    company_name: str | None = Depends(get_authorized_company),
    current_user: UserContext = Depends(get_current_user),
):
    async def _fetch():
        report = await fetch_stock_groups(company_name=company_name)
        return [_stock_group_row(r) for r in report.get("rows", [])]

    try:
        cache_res = await _cached_report(
            report_name="stock_groups",
            company_name=company_name,
            current_user=current_user,
            params={},
            fetcher=_fetch,
            ttl_name="stock_groups",
        )
        rows = cache_res.data
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Stock Groups export error: %r", e)
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Stock Group Summary from Tally",
        )

    return _export_response(
        file_format=file_format,
        title="Stock Group Summary",
        columns=STOCK_GROUP_COLUMNS,
        rows=rows,
        company_name=company_name,
        filename_base="stock_group_summary",
    )


@router.get("/stock-item-monthly")
async def get_stock_item_monthly_report(
    stock_item_name: str,
    from_date: date | None = None,
    to_date: date | None = None,
    godown_name: str | None = None,
    company_name: str | None = Depends(get_authorized_company),
    current_user: UserContext = Depends(get_current_user),
    force_refresh: bool = False,
    refresh: str | int | None = None,
):
    _check_period(from_date, to_date)

    async def _fetch():
        if godown_name:
            summary = await fetch_godown_item_monthly(
                godown_name=godown_name,
                stock_item_name=stock_item_name,
                from_date=from_date,
                to_date=to_date,
                company_name=company_name,
            )
        else:
            summary = await fetch_stock_item_monthly(
                stock_item_name=stock_item_name,
                from_date=from_date,
                to_date=to_date,
                company_name=company_name,
            )
        return summary

    try:
        cache_res = await _cached_report(
            report_name="stock_item_monthly",
            company_name=company_name,
            current_user=current_user,
            params={
                "stock_item_name": stock_item_name,
                "godown_name": godown_name,
                "from_date": from_date.isoformat() if from_date else None,
                "to_date": to_date.isoformat() if to_date else None,
            },
            fetcher=_fetch,
            force_refresh=force_refresh,
            refresh=refresh,
            ttl_name="stock_item_monthly",
        )
        summary = cache_res.data

        if not summary or not summary.get("item_found"):
            raise HTTPException(
                status_code=404,
                detail=f"Stock item '{stock_item_name}' was not found in Tally",
            )

        return {
            "success": True,
            "source": cache_res.source,
            "is_stale": cache_res.is_stale,
            "cached_at": cache_res.cached_at,
            "item": stock_item_name,
            "godown": summary.get("godown"),
            "approximate": bool(summary.get("approximate")),
            "from": summary.get("from"),
            "to": summary.get("to"),
            "unit": summary.get("unit"),
            "opening": summary.get("opening"),
            "report": summary.get("rows", []),
            "count": len(summary.get("rows", [])),
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Stock Item Monthly error: %r", e)
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Stock Item Monthly Summary from Tally",
        )


@router.get("/stock-group-summary")
async def get_stock_group_summary_report(
    group: str | None = None,
    company_name: str | None = Depends(get_authorized_company),
    from_date: date | None = None,
    to_date: date | None = None,
    include_zero: bool = False,
    current_user: UserContext = Depends(get_current_user),
    force_refresh: bool = False,
    refresh: str | int | None = None,
):
    _check_period(from_date, to_date)

    async def _fetch():
        return await fetch_stock_group_summary(
            group_name=group,
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
            include_zero=include_zero,
        )

    try:
        cache_res = await _cached_report(
            report_name="stock_group_summary",
            company_name=company_name,
            current_user=current_user,
            params={
                "group": group,
                "from_date": from_date.isoformat() if from_date else None,
                "to_date": to_date.isoformat() if to_date else None,
                "include_zero": include_zero,
            },
            fetcher=_fetch,
            force_refresh=force_refresh,
            refresh=refresh,
            ttl_name="stock_group_summary",
        )
        summary = cache_res.data
        resp = _summary_response(summary, "Stock group", group)
        resp["source"] = cache_res.source
        resp["is_stale"] = cache_res.is_stale
        resp["cached_at"] = cache_res.cached_at
        return resp

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Stock Group Summary error: %r", e)
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Stock Group Summary from Tally",
        )


@router.get("/stock-category-summary")
async def get_stock_category_summary_report(
    category: str | None = None,
    company_name: str | None = Depends(get_authorized_company),
    from_date: date | None = None,
    to_date: date | None = None,
    include_zero: bool = False,
    current_user: UserContext = Depends(get_current_user),
    force_refresh: bool = False,
    refresh: str | int | None = None,
):
    _check_period(from_date, to_date)

    async def _fetch():
        return await fetch_stock_category_summary(
            category_name=category,
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
            include_zero=include_zero,
        )

    try:
        cache_res = await _cached_report(
            report_name="stock_category_summary",
            company_name=company_name,
            current_user=current_user,
            params={
                "category": category,
                "from_date": from_date.isoformat() if from_date else None,
                "to_date": to_date.isoformat() if to_date else None,
                "include_zero": include_zero,
            },
            fetcher=_fetch,
            force_refresh=force_refresh,
            refresh=refresh,
            ttl_name="stock_category_summary",
        )
        summary = cache_res.data
        resp = _summary_response(summary, "Stock category", category)
        resp["source"] = cache_res.source
        resp["is_stale"] = cache_res.is_stale
        resp["cached_at"] = cache_res.cached_at
        return resp

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Stock Category Summary error: %r", e)
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Stock Category Summary from Tally",
        )


@router.get("/godown-summary")
async def get_godown_summary_report(
    godown: str | None = None,
    company_name: str | None = Depends(get_authorized_company),
    from_date: date | None = None,
    to_date: date | None = None,
    include_zero: bool = False,
    current_user: UserContext = Depends(get_current_user),
    force_refresh: bool = False,
    refresh: str | int | None = None,
):
    _check_period(from_date, to_date)

    async def _fetch():
        return await fetch_godown_summary(
            godown_name=godown,
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
            include_zero=include_zero,
        )

    try:
        cache_res = await _cached_report(
            report_name="godown_summary",
            company_name=company_name,
            current_user=current_user,
            params={
                "godown": godown,
                "from_date": from_date.isoformat() if from_date else None,
                "to_date": to_date.isoformat() if to_date else None,
                "include_zero": include_zero,
            },
            fetcher=_fetch,
            force_refresh=force_refresh,
            refresh=refresh,
            ttl_name="godown_summary",
        )
        summary = cache_res.data
        resp = _summary_response(summary, "Godown", godown)
        resp["source"] = cache_res.source
        resp["is_stale"] = cache_res.is_stale
        resp["cached_at"] = cache_res.cached_at
        return resp

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Godown Summary error: %r", e)
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Godown Summary from Tally",
        )


@router.get("/stock-group-items")
async def get_stock_group_items_report(
    group: str,
    company_name: str | None = Depends(get_authorized_company),
    to_date: date | None = None,
    current_user: UserContext = Depends(get_current_user),
    force_refresh: bool = False,
    refresh: str | int | None = None,
):
    async def _fetch():
        report = await fetch_stock_group_items(
            group_name=group,
            company_name=company_name,
            to_date=to_date,
        )
        return [_stock_summary_row(r) for r in report.get("rows", [])]

    try:
        cache_res = await _cached_report(
            report_name="stock_group_items",
            company_name=company_name,
            current_user=current_user,
            params={
                "group": group,
                "to_date": to_date.isoformat() if to_date else None,
            },
            fetcher=_fetch,
            force_refresh=force_refresh,
            refresh=refresh,
            ttl_name="stock_group_items",
        )
        rows = cache_res.data

        return {
            "success": True,
            "source": cache_res.source,
            "is_stale": cache_res.is_stale,
            "cached_at": cache_res.cached_at,
            "group_name": group,
            "report": rows,
            "count": len(rows),
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Stock Group Items error: %r", e)
        raise HTTPException(
            status_code=502,
            detail=f"Unable to fetch items for stock group '{group}' from Tally",
        )


@router.get("/stock-group-items/export/{file_format}")
async def export_stock_group_items_report(
    file_format: str,
    group: str,
    company_name: str | None = Depends(get_authorized_company),
    to_date: date | None = None,
    current_user: UserContext = Depends(get_current_user),
):
    async def _fetch():
        report = await fetch_stock_group_items(
            group_name=group,
            company_name=company_name,
            to_date=to_date,
        )
        return [_stock_summary_row(r) for r in report.get("rows", [])]

    try:
        cache_res = await _cached_report(
            report_name="stock_group_items",
            company_name=company_name,
            current_user=current_user,
            params={
                "group": group,
                "to_date": to_date.isoformat() if to_date else None,
            },
            fetcher=_fetch,
            ttl_name="stock_group_items",
        )
        rows = cache_res.data
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Stock Group Items export error: %r", e)
        raise HTTPException(
            status_code=502,
            detail=f"Unable to fetch items for stock group '{group}' from Tally",
        )

    return _export_response(
        file_format=file_format,
        title=f"Stock Group: {group}",
        columns=STOCK_SUMMARY_COLUMNS,
        rows=rows,
        company_name=company_name,
        filename_base=f"stock_group_{group.strip().replace(' ', '_')}",
        period=_period_label(to_date=to_date),
    )


# ------------------------------------------------------------------
# Stock Categories
# ------------------------------------------------------------------

@router.get("/stock-categories")
async def get_stock_categories_report(
    company_name: str | None = Depends(get_authorized_company),
    current_user: UserContext = Depends(get_current_user),
    force_refresh: bool = False,
    refresh: str | int | None = None,
):
    async def _fetch():
        report = await fetch_stock_categories(company_name=company_name)
        return [
            _stock_category_row(r)
            for r in with_root_row(report.get("rows", []), "name")
        ]

    try:
        cache_res = await _cached_report(
            report_name="stock_categories",
            company_name=company_name,
            current_user=current_user,
            params={},
            fetcher=_fetch,
            force_refresh=force_refresh,
            refresh=refresh,
            ttl_name="stock_categories",
        )
        rows = cache_res.data

        return {
            "success": True,
            "source": cache_res.source,
            "is_stale": cache_res.is_stale,
            "cached_at": cache_res.cached_at,
            "report": rows,
            "count": len(rows),
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Stock Categories error: %r", e)
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Stock Category Summary from Tally",
        )


@router.get("/stock-categories/export/{file_format}")
async def export_stock_categories_report(
    file_format: str,
    company_name: str | None = Depends(get_authorized_company),
    current_user: UserContext = Depends(get_current_user),
):
    async def _fetch():
        report = await fetch_stock_categories(company_name=company_name)
        return [_stock_category_row(r) for r in report.get("rows", [])]

    try:
        cache_res = await _cached_report(
            report_name="stock_categories",
            company_name=company_name,
            current_user=current_user,
            params={},
            fetcher=_fetch,
            ttl_name="stock_categories",
        )
        rows = cache_res.data
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Stock Categories export error: %r", e)
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Stock Category Summary from Tally",
        )

    return _export_response(
        file_format=file_format,
        title="Stock Category Summary",
        columns=STOCK_CATEGORY_COLUMNS,
        rows=rows,
        company_name=company_name,
        filename_base="stock_category_summary",
    )


# ------------------------------------------------------------------
# Locations (Godowns)
# ------------------------------------------------------------------

@router.get("/godowns")
async def get_godowns_report(
    company_name: str | None = Depends(get_authorized_company),
    current_user: UserContext = Depends(get_current_user),
    force_refresh: bool = False,
    refresh: str | int | None = None,
):
    async def _fetch():
        report = await fetch_godowns(company_name=company_name)
        return [
            _godown_row(r)
            for r in with_root_row(report.get("rows", []), "name")
        ]

    try:
        cache_res = await _cached_report(
            report_name="godowns",
            company_name=company_name,
            current_user=current_user,
            params={},
            fetcher=_fetch,
            force_refresh=force_refresh,
            refresh=refresh,
            ttl_name="godowns",
        )
        rows = cache_res.data

        return {
            "success": True,
            "source": cache_res.source,
            "is_stale": cache_res.is_stale,
            "cached_at": cache_res.cached_at,
            "report": rows,
            "count": len(rows),
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Locations error: %r", e)
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Locations from Tally",
        )


@router.get("/godowns/export/{file_format}")
async def export_godowns_report(
    file_format: str,
    company_name: str | None = Depends(get_authorized_company),
    current_user: UserContext = Depends(get_current_user),
):
    async def _fetch():
        report = await fetch_godowns(company_name=company_name)
        return [_godown_row(r) for r in report.get("rows", [])]

    try:
        cache_res = await _cached_report(
            report_name="godowns",
            company_name=company_name,
            current_user=current_user,
            params={},
            fetcher=_fetch,
            ttl_name="godowns",
        )
        rows = cache_res.data
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Locations export error: %r", e)
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Locations from Tally",
        )

    return _export_response(
        file_format=file_format,
        title="Locations",
        columns=GODOWN_COLUMNS,
        rows=rows,
        company_name=company_name,
        filename_base="locations",
    )


# ------------------------------------------------------------------
# Stock Movement - powers Stock Item Monthly Summary (stock_item_name),
# Stock Item Vouchers (stock_item_name + from/to = one month) and
# Location Summary / Location Monthly Summary (godown_name).
# ------------------------------------------------------------------

@router.get("/stock-movement")
async def get_stock_movement_report(
    company_name: str | None = Depends(get_authorized_company),
    from_date: date | None = None,
    to_date: date | None = None,
    stock_item_name: str | None = None,
    godown_name: str | None = None,
    current_user: UserContext = Depends(get_current_user),
    force_refresh: bool = False,
    refresh: str | int | None = None,
):
    if from_date and to_date and from_date > to_date:
        raise HTTPException(
            status_code=400,
            detail="from_date cannot be later than to_date",
        )

    async def _fetch():
        report = await fetch_stock_movement(
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
            stock_item_name=stock_item_name,
            godown_name=godown_name,
        )
        return [_stock_movement_row(r) for r in report.get("rows", [])]

    try:
        cache_res = await _cached_report(
            report_name="stock_movement",
            company_name=company_name,
            current_user=current_user,
            params={
                "from_date": from_date.isoformat() if from_date else None,
                "to_date": to_date.isoformat() if to_date else None,
                "stock_item_name": stock_item_name,
                "godown_name": godown_name,
            },
            fetcher=_fetch,
            force_refresh=force_refresh,
            refresh=refresh,
            ttl_name="stock_movement",
        )
        rows = cache_res.data

        return {
            "success": True,
            "source": cache_res.source,
            "is_stale": cache_res.is_stale,
            "cached_at": cache_res.cached_at,
            "report": rows,
            "count": len(rows),
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Stock Movement error: %r", e)
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Stock Movement from Tally",
        )


@router.get("/stock-movement/export/{file_format}")
async def export_stock_movement_report(
    file_format: str,
    company_name: str | None = Depends(get_authorized_company),
    from_date: date | None = None,
    to_date: date | None = None,
    stock_item_name: str | None = None,
    godown_name: str | None = None,
    current_user: UserContext = Depends(get_current_user),
):
    async def _fetch():
        report = await fetch_stock_movement(
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
            stock_item_name=stock_item_name,
            godown_name=godown_name,
        )
        return [_stock_movement_row(r) for r in report.get("rows", [])]

    try:
        cache_res = await _cached_report(
            report_name="stock_movement",
            company_name=company_name,
            current_user=current_user,
            params={
                "from_date": from_date.isoformat() if from_date else None,
                "to_date": to_date.isoformat() if to_date else None,
                "stock_item_name": stock_item_name,
                "godown_name": godown_name,
            },
            fetcher=_fetch,
            ttl_name="stock_movement",
        )
        rows = cache_res.data
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Stock Movement export error: %r", e)
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Stock Movement from Tally",
        )

    title = "Stock Movement"
    if stock_item_name:
        title = f"Stock Movement: {stock_item_name}"
    elif godown_name:
        title = f"Stock Movement: {godown_name}"

    return _export_response(
        file_format=file_format,
        title=title,
        columns=STOCK_MOVEMENT_COLUMNS,
        rows=rows,
        company_name=company_name,
        filename_base="stock_movement",
        period=_period_label(from_date=from_date, to_date=to_date),
    )


# ------------------------------------------------------------------
# Stock Valuation / Negative Stock (additional reports already
# wired into the Inventory Books screen)
# ------------------------------------------------------------------

@router.get("/stock-valuation")
async def get_stock_valuation_report(
    company_name: str | None = Depends(get_authorized_company),
    to_date: date | None = None,
    current_user: UserContext = Depends(get_current_user),
    force_refresh: bool = False,
    refresh: str | int | None = None,
):
    async def _fetch():
        report = await fetch_stock_valuation(
            company_name=company_name,
            to_date=to_date,
        )
        return [_stock_valuation_row(r) for r in report.get("rows", [])]

    try:
        cache_res = await _cached_report(
            report_name="stock_valuation",
            company_name=company_name,
            current_user=current_user,
            params={"to_date": to_date.isoformat() if to_date else None},
            fetcher=_fetch,
            force_refresh=force_refresh,
            refresh=refresh,
            ttl_name="stock_valuation",
        )
        rows = cache_res.data

        return {
            "success": True,
            "source": cache_res.source,
            "is_stale": cache_res.is_stale,
            "cached_at": cache_res.cached_at,
            "report": rows,
            "count": len(rows),
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Stock Valuation error: %r", e)
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Stock Valuation from Tally",
        )


@router.get("/stock-valuation/export/{file_format}")
async def export_stock_valuation_report(
    file_format: str,
    company_name: str | None = Depends(get_authorized_company),
    to_date: date | None = None,
    current_user: UserContext = Depends(get_current_user),
):
    async def _fetch():
        report = await fetch_stock_valuation(
            company_name=company_name,
            to_date=to_date,
        )
        return [_stock_valuation_row(r) for r in report.get("rows", [])]

    try:
        cache_res = await _cached_report(
            report_name="stock_valuation",
            company_name=company_name,
            current_user=current_user,
            params={"to_date": to_date.isoformat() if to_date else None},
            fetcher=_fetch,
            ttl_name="stock_valuation",
        )
        rows = cache_res.data
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Stock Valuation export error: %r", e)
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Stock Valuation from Tally",
        )

    total_value = sum(row.get("valuation_value") or 0 for row in rows)

    return _export_response(
        file_format=file_format,
        title="Stock Valuation",
        columns=STOCK_VALUATION_COLUMNS,
        rows=rows,
        company_name=company_name,
        filename_base="stock_valuation",
        footer={
            "label": "Total Valuation",
            "key": "valuation_value",
            "value": total_value,
        },
        period=_period_label(to_date=to_date),
    )


@router.get("/negative-stock")
async def get_negative_stock_report(
    company_name: str | None = Depends(get_authorized_company),
    to_date: date | None = None,
    current_user: UserContext = Depends(get_current_user),
    force_refresh: bool = False,
    refresh: str | int | None = None,
):
    async def _fetch():
        report = await fetch_negative_stock(
            company_name=company_name,
            to_date=to_date,
        )
        return [_stock_summary_row(r) for r in report.get("rows", [])]

    try:
        cache_res = await _cached_report(
            report_name="negative_stock",
            company_name=company_name,
            current_user=current_user,
            params={"to_date": to_date.isoformat() if to_date else None},
            fetcher=_fetch,
            force_refresh=force_refresh,
            refresh=refresh,
            ttl_name="negative_stock",
        )
        rows = cache_res.data

        return {
            "success": True,
            "source": cache_res.source,
            "is_stale": cache_res.is_stale,
            "cached_at": cache_res.cached_at,
            "report": rows,
            "count": len(rows),
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Negative Stock error: %r", e)
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Negative Stock from Tally",
        )


@router.get("/negative-stock/export/{file_format}")
async def export_negative_stock_report(
    file_format: str,
    company_name: str | None = Depends(get_authorized_company),
    to_date: date | None = None,
    current_user: UserContext = Depends(get_current_user),
):
    async def _fetch():
        report = await fetch_negative_stock(
            company_name=company_name,
            to_date=to_date,
        )
        return [_stock_summary_row(r) for r in report.get("rows", [])]

    try:
        cache_res = await _cached_report(
            report_name="negative_stock",
            company_name=company_name,
            current_user=current_user,
            params={"to_date": to_date.isoformat() if to_date else None},
            fetcher=_fetch,
            ttl_name="negative_stock",
        )
        rows = cache_res.data
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Negative Stock export error: %r", e)
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Negative Stock from Tally",
        )

    return _export_response(
        file_format=file_format,
        title="Negative Stock",
        columns=NEGATIVE_STOCK_COLUMNS,
        rows=rows,
        company_name=company_name,
        filename_base="negative_stock",
        period=_period_label(to_date=to_date),
    )


# ============================================================
# INVENTORY BOOKS REGISTERS
# ============================================================

INVENTORY_REGISTER_COLUMNS = [
    {"key": "month", "label": "Particulars"},
    {"key": "total_vouchers", "label": "Total Vouchers"},
]

INVENTORY_REGISTERS = {
    "sales-orders": {"title": "Sales Orders Book", "voucher_type": "Sales Order", "filename": "sales_orders_book"},
    "purchase-orders": {"title": "Purchase Orders Book", "voucher_type": "Purchase Order", "filename": "purchase_orders_book"},
    "delivery-note": {"title": "Delivery Note Register", "voucher_type": "Delivery Note", "filename": "delivery_note_register"},
    "receipt-note": {"title": "Receipt Note Register", "voucher_type": "Receipt Note", "filename": "receipt_note_register"},
    "rejections-in": {"title": "Rejections In Register", "voucher_type": "Rejections In", "filename": "rejections_in_register"},
    "rejections-out": {"title": "Rejections Out Register", "voucher_type": "Rejections Out", "filename": "rejections_out_register"},
    "stock-journal": {"title": "Stock Transfer Journal Register", "voucher_type": "Stock Journal", "filename": "stock_transfer_journal_register"},
    "physical-stock": {"title": "Physical Stock Register", "voucher_type": "Physical Stock", "filename": "physical_stock_register"},
    "material-out": {"title": "Material Out Register", "voucher_type": "Material Out", "filename": "material_out_register"},
    "material-in": {"title": "Material In Register", "voucher_type": "Material In", "filename": "material_in_register"},
}


def _get_register(register_key: str) -> dict:
    register = INVENTORY_REGISTERS.get(register_key)

    if not register:
        raise HTTPException(status_code=404, detail="Unknown Inventory Books register")

    return register


@router.get("/inventory-register/{register_key}")
async def get_inventory_register(
    register_key: str,
    company_name: str | None = Depends(get_authorized_company),
    from_date: date | None = None,
    to_date: date | None = None,
    current_user: UserContext = Depends(get_current_user),
    force_refresh: bool = False,
    refresh: str | int | None = None,
):
    """
    Register screen: one row per month of the period with the number
    of vouchers (and how many are cancelled). Without a period the
    latest financial year with stock activity is used and returned as
    from / to.
    """
    register = _get_register(register_key)
    _check_period(from_date, to_date)

    async def _fetch():
        return await fetch_register_months(
            voucher_type=register["voucher_type"],
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
        )

    try:
        cache_res = await _cached_report(
            report_name=f"inventory_register_{register_key}",
            company_name=company_name,
            current_user=current_user,
            params={
                "from_date": from_date.isoformat() if from_date else None,
                "to_date": to_date.isoformat() if to_date else None,
            },
            fetcher=_fetch,
            force_refresh=force_refresh,
            refresh=refresh,
            ttl_name="inventory_register",
        )
        report = cache_res.data

        return {
            "success": True,
            "source": cache_res.source,
            "is_stale": cache_res.is_stale,
            "cached_at": cache_res.cached_at,
            "report_name": register["title"],
            "register_key": register_key,
            "from": report["from"],
            "to": report["to"],
            "count": len(report["rows"]),
            "report": report["rows"],
            "grand_total": report["grand_total"],
            "grand_total_cancelled": report["grand_total_cancelled"],
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error("%s error: %r", register["title"], e)
        raise HTTPException(
            status_code=502,
            detail=f'Unable to fetch {register["title"]} from Tally',
        )


@router.get("/inventory-register/{register_key}/vouchers")
async def get_inventory_register_vouchers(
    register_key: str,
    from_date: date,
    to_date: date,
    company_name: str | None = Depends(get_authorized_company),
    current_user: UserContext = Depends(get_current_user),
    force_refresh: bool = False,
    refresh: str | int | None = None,
):
    """
    "List of All <X> Vouchers": the vouchers of one register in the
    period (normally one month). Each row carries voucher_type /
    voucher_number / date for the voucher alteration screen.
    """
    register = _get_register(register_key)
    _check_period(from_date, to_date)

    async def _fetch():
        return await fetch_register_voucher_list(
            register_key=register_key,
            voucher_type=register["voucher_type"],
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
        )

    try:
        cache_res = await _cached_report(
            report_name=f"inventory_register_vouchers_{register_key}",
            company_name=company_name,
            current_user=current_user,
            params={
                "from_date": from_date.isoformat(),
                "to_date": to_date.isoformat(),
            },
            fetcher=_fetch,
            force_refresh=force_refresh,
            refresh=refresh,
            ttl_name="inventory_register",
        )
        result = cache_res.data

        return {
            "success": True,
            "source": cache_res.source,
            "is_stale": cache_res.is_stale,
            "cached_at": cache_res.cached_at,
            "report_name": register["title"],
            "register_key": register_key,
            "voucher_type": register["voucher_type"],
            "kind": result["kind"],
            "from": from_date.isoformat(),
            "to": to_date.isoformat(),
            "count": len(result["rows"]),
            "report": result["rows"],
            "totals": result["totals"],
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error("%s vouchers error: %r", register["title"], e)
        raise HTTPException(
            status_code=502,
            detail=f'Unable to fetch {register["title"]} vouchers from Tally',
        )


@router.get("/inventory-register/{register_key}/export/{file_format}")
async def export_inventory_register(
    register_key: str,
    file_format: str,
    company_name: str | None = Depends(get_authorized_company),
    from_date: date | None = None,
    to_date: date | None = None,
    current_user: UserContext = Depends(get_current_user),
):
    register = _get_register(register_key)
    _check_period(from_date, to_date)

    async def _fetch():
        return await fetch_register_months(
            voucher_type=register["voucher_type"],
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
        )

    try:
        cache_res = await _cached_report(
            report_name=f"inventory_register_{register_key}",
            company_name=company_name,
            current_user=current_user,
            params={
                "from_date": from_date.isoformat() if from_date else None,
                "to_date": to_date.isoformat() if to_date else None,
            },
            fetcher=_fetch,
            ttl_name="inventory_register",
        )
        result = cache_res.data

    except HTTPException:
        raise

    except Exception as e:
        logger.error("%s export error: %r", register["title"], e)
        raise HTTPException(
            status_code=502,
            detail=f'Unable to fetch {register["title"]} from Tally',
        )

    return _export_response(
        file_format=file_format,
        title=register["title"],
        columns=INVENTORY_REGISTER_COLUMNS,
        rows=result["rows"],
        company_name=company_name,
        filename_base=register["filename"],
        period=_period_label(
            from_date=date.fromisoformat(result["from"]),
            to_date=date.fromisoformat(result["to"]),
        ),
    )