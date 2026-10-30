"""
Financial reports router: Profit & Loss, Balance Sheet, Trial Balance, Group Summary.
"""

import logging
import sys
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.security.auth import (
    UserContext,
    get_authorized_company,
    get_current_user,
)
from app.export import report_specs as specs
from app.export.invoke import invoke_endpoint
from app.api.reports.common import (
    _cached_report,
    _check_format,
    _safe_name,
    _spec_response,
    _export_response,
    _period_label,
    _as_rows,
    _pl_rows_to_two_columns,
    _fmt_period,
    _check_period,
    PROFIT_LOSS_COLUMNS,
    TRIAL_BALANCE_COLUMNS,
    BALANCE_SHEET_COLUMNS,
)

from app.tally.service import (
    fetch_profit_loss as _real_fetch_profit_loss,
    fetch_group_summary as _real_fetch_group_summary,
    fetch_trial_balance as _real_fetch_trial_balance,
    fetch_balance_sheet as _real_fetch_balance_sheet,
    fetch_balance_sheet_report as _real_fetch_balance_sheet_report,
    fetch_stock_movement as _real_fetch_stock_movement,
)

logger = logging.getLogger(__name__)

router = APIRouter()

def _get_fetcher(name, default):
    reports_mod = sys.modules.get("app.api.reports")
    return getattr(reports_mod, name, default) if reports_mod else default

async def fetch_profit_loss(*args, **kwargs):
    return await _get_fetcher("fetch_profit_loss", _real_fetch_profit_loss)(*args, **kwargs)

async def fetch_group_summary(*args, **kwargs):
    return await _get_fetcher("fetch_group_summary", _real_fetch_group_summary)(*args, **kwargs)

async def fetch_trial_balance(*args, **kwargs):
    return await _get_fetcher("fetch_trial_balance", _real_fetch_trial_balance)(*args, **kwargs)

async def fetch_balance_sheet(*args, **kwargs):
    return await _get_fetcher("fetch_balance_sheet", _real_fetch_balance_sheet)(*args, **kwargs)

async def fetch_balance_sheet_report(*args, **kwargs):
    return await _get_fetcher("fetch_balance_sheet_report", _real_fetch_balance_sheet_report)(*args, **kwargs)

async def fetch_stock_movement(*args, **kwargs):
    return await _get_fetcher("fetch_stock_movement", _real_fetch_stock_movement)(*args, **kwargs)

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
        company_name=company_name,
        filename_base="profit_and_loss",
        spec=specs.profit_loss_spec(
            report,
            company_name,
            _period_label(from_date=from_date, to_date=to_date),
        ),
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
        company_name=company_name,
        filename_base="trial_balance",
        spec=specs.trial_balance_spec(
            rows,
            company_name,
            _period_label(from_date=from_date, to_date=to_date),
        ),
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
        company_name=company_name,
        filename_base="balance_sheet",
        spec=specs.balance_sheet_spec(
            report,
            company_name,
            _period_label(from_date=from_date, to_date=to_date),
        ),
    )



@router.get("/group-summary/export/{file_format}")
async def export_group_summary_report(
    file_format: str,
    group: str = Query(...),
    company_name: str | None = Depends(get_authorized_company),
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    current_user: UserContext = Depends(get_current_user),
):
    _check_format(file_format)
    resp = await invoke_endpoint(
        get_group_summary_report,
        group=group,
        company_name=company_name,
        from_date=from_date,
        to_date=to_date,
        current_user=current_user,
    )
    return _export_response(
        file_format=file_format,
        company_name=company_name,
        filename_base=_safe_name("group", group),
        spec=specs.group_summary_spec(
            resp, group, company_name,
            _period_label(from_date=from_date, to_date=to_date),
        ),
    )



@router.get("/trial-balance/purchase-bills-pending/export/{file_format}")
async def export_trial_balance_purchase_bills_pending(
    file_format: str,
    company_name: str | None = Depends(get_authorized_company),
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    current_user: UserContext = Depends(get_current_user),
):
    _check_format(file_format)
    resp = await invoke_endpoint(
        get_trial_balance_purchase_bills_pending,
        company_name=company_name,
        from_date=from_date,
        to_date=to_date,
        current_user=current_user,
    )
    return _export_response(
        file_format=file_format,
        company_name=company_name,
        filename_base="purchase_bills_pending",
        spec=specs.purchase_bills_pending_spec(
            resp, company_name,
            _period_label(from_date=from_date, to_date=to_date),
        ),
    )



@router.get("/trial-balance/opening-stock/export/{file_format}")
async def export_trial_balance_opening_stock(
    file_format: str,
    company_name: str | None = Depends(get_authorized_company),
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    current_user: UserContext = Depends(get_current_user),
):
    """Same arithmetic as the Trial Balance > Opening Stock page: the
    stock as at the day before the period starts (or each item's
    opening balance when no From Date is in play)."""
    _check_format(file_format)
    as_on = from_date - timedelta(days=1) if from_date else None
    from app.api.reports.inventory import get_stock_summary_report
    resp = await invoke_endpoint(
        get_stock_summary_report,
        company_name=company_name,
        to_date=as_on,
        current_user=current_user,
    )

    def number(value):
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    rows = []
    for item in resp.get("report", []):
        quantity = number(item.get("closing_quantity" if as_on else "opening_quantity"))
        value = number(item.get("closing_value" if as_on else "opening_value"))
        if as_on:
            rate = number(item.get("closing_rate"))
        else:
            rate = abs(value / quantity) if quantity else 0.0
        if quantity != 0 or value != 0:
            rows.append({
                "stock_item": item.get("stock_item"), "unit": item.get("unit"),
                "quantity": quantity, "rate": rate, "value": value,
            })

    return _export_response(
        file_format=file_format,
        company_name=company_name,
        filename_base="opening_stock_summary",
        spec=specs.trial_balance_opening_stock_spec(
            rows, company_name,
            _period_label(from_date=from_date, to_date=to_date),
        ),
    )


