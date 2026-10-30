"""
Inventory reports router: Stock Summary, Godowns, Groups, Categories, Movement, Registers.
"""

import logging
import sys
from datetime import date
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
    _fmt_period,
    _check_period,
    STOCK_SUMMARY_COLUMNS,
    STOCK_GROUP_COLUMNS,
    STOCK_CATEGORY_COLUMNS,
    GODOWN_COLUMNS,
    STOCK_MOVEMENT_COLUMNS,
    STOCK_VALUATION_COLUMNS,
    NEGATIVE_STOCK_COLUMNS,
    INVENTORY_REGISTER_COLUMNS,
)

from app.tally.service import (
    fetch_stock_summary as _real_fetch_stock_summary,
    fetch_stock_item as _real_fetch_stock_item,
    fetch_stock_groups as _real_fetch_stock_groups,
    fetch_stock_categories as _real_fetch_stock_categories,
    fetch_godowns as _real_fetch_godowns,
    fetch_stock_movement as _real_fetch_stock_movement,
    fetch_stock_valuation as _real_fetch_stock_valuation,
    fetch_negative_stock as _real_fetch_negative_stock,
    fetch_inventory_register as _real_fetch_inventory_register,
    fetch_stock_group_items as _real_fetch_stock_group_items,
    fetch_inventory_voucher_detail as _real_fetch_inventory_voucher_detail,
    fetch_stock_group_summary as _real_fetch_stock_group_summary,
    fetch_stock_category_summary as _real_fetch_stock_category_summary,
    fetch_godown_summary as _real_fetch_godown_summary,
    fetch_stock_item_monthly as _real_fetch_stock_item_monthly,
    fetch_stock_item_vouchers as _real_fetch_stock_item_vouchers,
    fetch_sales_bills_pending as _real_fetch_sales_bills_pending,
    fetch_register_months as _real_fetch_register_months,
    fetch_register_voucher_list as _real_fetch_register_voucher_list,
    fetch_godown_item_monthly as _real_fetch_godown_item_monthly,
)

from app.tally.parsers.inventory_summary import with_root_row

logger = logging.getLogger(__name__)

router = APIRouter()

def _get_fetcher(name, default):
    reports_mod = sys.modules.get("app.api.reports")
    return getattr(reports_mod, name, default) if reports_mod else default

async def fetch_stock_summary(*args, **kwargs):
    return await _get_fetcher("fetch_stock_summary", _real_fetch_stock_summary)(*args, **kwargs)

async def fetch_stock_item(*args, **kwargs):
    return await _get_fetcher("fetch_stock_item", _real_fetch_stock_item)(*args, **kwargs)

async def fetch_stock_groups(*args, **kwargs):
    return await _get_fetcher("fetch_stock_groups", _real_fetch_stock_groups)(*args, **kwargs)

async def fetch_stock_categories(*args, **kwargs):
    return await _get_fetcher("fetch_stock_categories", _real_fetch_stock_categories)(*args, **kwargs)

async def fetch_godowns(*args, **kwargs):
    return await _get_fetcher("fetch_godowns", _real_fetch_godowns)(*args, **kwargs)

async def fetch_stock_movement(*args, **kwargs):
    return await _get_fetcher("fetch_stock_movement", _real_fetch_stock_movement)(*args, **kwargs)

async def fetch_stock_valuation(*args, **kwargs):
    return await _get_fetcher("fetch_stock_valuation", _real_fetch_stock_valuation)(*args, **kwargs)

async def fetch_negative_stock(*args, **kwargs):
    return await _get_fetcher("fetch_negative_stock", _real_fetch_negative_stock)(*args, **kwargs)

async def fetch_inventory_register(*args, **kwargs):
    return await _get_fetcher("fetch_inventory_register", _real_fetch_inventory_register)(*args, **kwargs)

async def fetch_stock_group_items(*args, **kwargs):
    return await _get_fetcher("fetch_stock_group_items", _real_fetch_stock_group_items)(*args, **kwargs)

async def fetch_inventory_voucher_detail(*args, **kwargs):
    return await _get_fetcher("fetch_inventory_voucher_detail", _real_fetch_inventory_voucher_detail)(*args, **kwargs)

async def fetch_stock_group_summary(*args, **kwargs):
    return await _get_fetcher("fetch_stock_group_summary", _real_fetch_stock_group_summary)(*args, **kwargs)

async def fetch_stock_category_summary(*args, **kwargs):
    return await _get_fetcher("fetch_stock_category_summary", _real_fetch_stock_category_summary)(*args, **kwargs)

async def fetch_godown_summary(*args, **kwargs):
    return await _get_fetcher("fetch_godown_summary", _real_fetch_godown_summary)(*args, **kwargs)

async def fetch_stock_item_monthly(*args, **kwargs):
    return await _get_fetcher("fetch_stock_item_monthly", _real_fetch_stock_item_monthly)(*args, **kwargs)

async def fetch_stock_item_vouchers(*args, **kwargs):
    return await _get_fetcher("fetch_stock_item_vouchers", _real_fetch_stock_item_vouchers)(*args, **kwargs)

async def fetch_sales_bills_pending(*args, **kwargs):
    return await _get_fetcher("fetch_sales_bills_pending", _real_fetch_sales_bills_pending)(*args, **kwargs)

async def fetch_register_months(*args, **kwargs):
    return await _get_fetcher("fetch_register_months", _real_fetch_register_months)(*args, **kwargs)

async def fetch_register_voucher_list(*args, **kwargs):
    return await _get_fetcher("fetch_register_voucher_list", _real_fetch_register_voucher_list)(*args, **kwargs)

async def fetch_godown_item_monthly(*args, **kwargs):
    return await _get_fetcher("fetch_godown_item_monthly", _real_fetch_godown_item_monthly)(*args, **kwargs)

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


async def _legacy_export_stock_summary_report(
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
            report_name="inventory_voucher_v4",
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


async def _legacy_export_stock_groups_report(
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


@router.get("/stock-item-monthly-debug")
async def get_stock_item_monthly_debug(
    stock_item_name: str,
    company_name: str | None = Depends(get_authorized_company),
    current_user: UserContext = Depends(get_current_user),
):
    """Raw rows behind the monthly summary, for checking against Tally."""
    from app.tally.service import _load_item_vouchers, _load_item_master

    item_rows, _all = await _load_item_vouchers(stock_item_name, company_name)
    masters = await fetch_godowns(company_name=company_name)
    master = await _load_item_master(stock_item_name, company_name, as_on=date.today())

    keep = (
        "date", "voucher_type", "voucher_number", "party", "quantity",
        "rate", "amount", "is_deemed_positive", "godown", "tracking_number",
    )

    return {
        "item_master": master,
        "godown_masters": [g.get("name") or g.get("godown") for g in masters.get("rows", [])],
        "row_count": len(item_rows),
        "rows": [{k: r.get(k) for k in keep} for r in item_rows],
    }


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
            report_name="stock_item_monthly_v4",
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
            "reconciled": summary.get("reconciled", True),
            "tally_closing": summary.get("tally_closing"),
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


@router.get("/stock-item-vouchers")
async def get_stock_item_vouchers_report(
    stock_item_name: str,
    from_date: date | None = None,
    to_date: date | None = None,
    godown_name: str | None = None,
    company_name: str | None = Depends(get_authorized_company),
    current_user: UserContext = Depends(get_current_user),
    force_refresh: bool = False,
    refresh: str | int | None = None,
):
    """
    Tally's "Stock Item Vouchers": opening balance, the item's vouchers
    with Inwards / Outwards / Closing, the Bills Pending roll-up and the
    totals for the period.
    """
    _check_period(from_date, to_date)

    async def _fetch():
        return await fetch_stock_item_vouchers(
            stock_item_name=stock_item_name,
            from_date=from_date,
            to_date=to_date,
            company_name=company_name,
            godown_name=godown_name,
        )

    try:
        cache_res = await _cached_report(
            report_name="stock_item_vouchers_v3",
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
            ttl_name="stock_movement",
        )
        ledger = cache_res.data

        if not ledger or not ledger.get("item_found"):
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
            "from": ledger.get("from"),
            "to": ledger.get("to"),
            "unit": ledger.get("unit"),
            "opening": ledger.get("opening"),
            "report": ledger.get("rows", []),
            "totals": ledger.get("totals"),
            "count": len(ledger.get("rows", [])),
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Stock Item Vouchers error: %r", e)
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Stock Item Vouchers from Tally",
        )


@router.get("/stock-item-bills-pending")
async def get_stock_item_bills_pending_report(
    stock_item_name: str,
    from_date: date | None = None,
    to_date: date | None = None,
    tracking_number: str | None = None,
    party: str | None = None,
    company_name: str | None = Depends(get_authorized_company),
    current_user: UserContext = Depends(get_current_user),
    force_refresh: bool = False,
    refresh: str | int | None = None,
):
    """Sale Bills Pending for one stock item (opened from Stock Item Vouchers)."""
    _check_period(from_date, to_date)

    async def _fetch():
        return await fetch_sales_bills_pending(
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
            stock_item_name=stock_item_name,
            tracking_number=tracking_number,
            party=party,
        )

    try:
        cache_res = await _cached_report(
            report_name="stock_item_bills_pending_v3",
            company_name=company_name,
            current_user=current_user,
            params={
                "stock_item_name": stock_item_name,
                "from_date": from_date.isoformat() if from_date else None,
                "to_date": to_date.isoformat() if to_date else None,
                "tracking_number": tracking_number,
                "party": party,
            },
            fetcher=_fetch,
            force_refresh=force_refresh,
            refresh=refresh,
            ttl_name="stock_movement",
        )
        result = cache_res.data

        return {
            "success": True,
            "source": cache_res.source,
            "is_stale": cache_res.is_stale,
            "cached_at": cache_res.cached_at,
            "report": result.get("rows", []),
            "details": result.get("details", []),
            "count": result.get("count", 0),
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Stock Item Bills Pending error: %r", e)
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Bills Pending from Tally",
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


async def _legacy_export_stock_categories_report(
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


async def _legacy_export_godowns_report(
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
        company_name=company_name,
        filename_base=register["filename"],
        spec=specs.register_months_spec(
            register["title"],
            result,
            company_name,
            _period_label(
                from_date=date.fromisoformat(result["from"]),
                to_date=date.fromisoformat(result["to"]),
            ),
        ),
    )



# ======================================================================
# PDF / Excel exports that read the page's own data
#
# Each endpoint below runs the matching JSON endpoint of this module
# (same cache key, same Tally fetch), so the file always shows exactly
# what the screen shows.
# ======================================================================

def _fmt_period(resp: dict) -> str | None:
    return specs.period_label(resp.get("from"), resp.get("to"))


async def _master_export(
    file_format, endpoint, title, columns, filename, company_name, current_user
):
    _check_format(file_format)
    resp = await invoke_endpoint(
        endpoint, company_name=company_name, current_user=current_user
    )
    rows = []
    for row in resp.get("report", []):
        row = dict(row)
        if row.get("is_primary"):
            row["_style"] = "bold"
        rows.append(row)
    return _export_response(
        file_format=file_format,
        title=title,
        columns=columns,
        rows=rows,
        company_name=company_name,
        filename_base=filename,
    )


@router.get("/stock-groups/export/{file_format}")
async def export_stock_groups_report(
    file_format: str,
    company_name: str | None = Depends(get_authorized_company),
    current_user: UserContext = Depends(get_current_user),
):
    return await _master_export(
        file_format, get_stock_groups_report, "Stock Group Summary",
        STOCK_GROUP_COLUMNS, "stock_group_summary", company_name, current_user,
    )


@router.get("/stock-categories/export/{file_format}")
async def export_stock_categories_report(
    file_format: str,
    company_name: str | None = Depends(get_authorized_company),
    current_user: UserContext = Depends(get_current_user),
):
    return await _master_export(
        file_format, get_stock_categories_report, "Stock Category Summary",
        STOCK_CATEGORY_COLUMNS, "stock_category_summary", company_name, current_user,
    )


@router.get("/godowns/export/{file_format}")
async def export_godowns_report(
    file_format: str,
    company_name: str | None = Depends(get_authorized_company),
    current_user: UserContext = Depends(get_current_user),
):
    return await _master_export(
        file_format, get_godowns_report, "Locations",
        GODOWN_COLUMNS, "locations", company_name, current_user,
    )


@router.get("/stock-summary/export/{file_format}")
async def export_stock_summary_report(
    file_format: str,
    company_name: str | None = Depends(get_authorized_company),
    to_date: date | None = Query(default=None),
    from_date: date | None = Query(default=None),
    view: str = Query(default="full"),
    current_user: UserContext = Depends(get_current_user),
):
    _check_format(file_format)
    resp = await invoke_endpoint(
        get_stock_summary_report,
        company_name=company_name,
        to_date=to_date,
        from_date=from_date,
        current_user=current_user,
    )
    view = view if view in ("full", "opening", "closing") else "full"
    title = {"full": "Stock Summary", "opening": "Opening Stock Summary",
             "closing": "Closing Stock Summary"}[view]
    period = _period_label(from_date=from_date, to_date=to_date)
    return _export_response(
        file_format=file_format,
        company_name=company_name,
        filename_base=_safe_name(title.lower()),
        spec=specs.stock_summary_spec(
            resp.get("report", []), title, company_name, period, view
        ),
    )



@router.get("/inventory-voucher/export/{file_format}")
async def export_inventory_voucher_detail(
    file_format: str,
    voucher_type: str = Query(...),
    voucher_number: str = Query(...),
    voucher_date: date | None = Query(default=None),
    company_name: str | None = Depends(get_authorized_company),
    current_user: UserContext = Depends(get_current_user),
):
    _check_format(file_format)
    resp = await invoke_endpoint(
        get_inventory_voucher_detail_report,
        voucher_type=voucher_type,
        voucher_number=voucher_number,
        voucher_date=voucher_date,
        company_name=company_name,
        current_user=current_user,
    )
    return _export_response(
        file_format=file_format,
        company_name=company_name,
        filename_base=_safe_name(voucher_type, voucher_number),
        spec=specs.inventory_voucher_spec(resp["voucher"], company_name),
    )


@router.get("/stock-item-monthly/export/{file_format}")
async def export_stock_item_monthly(
    file_format: str,
    stock_item_name: str = Query(...),
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    godown_name: str | None = Query(default=None),
    company_name: str | None = Depends(get_authorized_company),
    current_user: UserContext = Depends(get_current_user),
):
    _check_format(file_format)
    resp = await invoke_endpoint(
        get_stock_item_monthly_report,
        stock_item_name=stock_item_name,
        from_date=from_date,
        to_date=to_date,
        godown_name=godown_name,
        company_name=company_name,
        current_user=current_user,
    )
    return _export_response(
        file_format=file_format,
        company_name=company_name,
        filename_base=_safe_name(stock_item_name, godown_name, "monthly"),
        spec=specs.stock_item_monthly_spec(
            resp, stock_item_name, godown_name, company_name, _fmt_period(resp)
        ),
    )


@router.get("/stock-item-vouchers/export/{file_format}")
async def export_stock_item_vouchers(
    file_format: str,
    stock_item_name: str = Query(...),
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    godown_name: str | None = Query(default=None),
    company_name: str | None = Depends(get_authorized_company),
    current_user: UserContext = Depends(get_current_user),
):
    _check_format(file_format)
    resp = await invoke_endpoint(
        get_stock_item_vouchers_report,
        stock_item_name=stock_item_name,
        from_date=from_date,
        to_date=to_date,
        godown_name=godown_name,
        company_name=company_name,
        current_user=current_user,
    )
    return _export_response(
        file_format=file_format,
        company_name=company_name,
        filename_base=_safe_name(stock_item_name, godown_name, "vouchers"),
        spec=specs.stock_item_vouchers_spec(
            resp, stock_item_name, godown_name, company_name, _fmt_period(resp)
        ),
    )


@router.get("/stock-item-bills-pending/export/{file_format}")
async def export_stock_item_bills_pending(
    file_format: str,
    stock_item_name: str = Query(...),
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    tracking_number: str | None = Query(default=None),
    party: str | None = Query(default=None),
    company_name: str | None = Depends(get_authorized_company),
    current_user: UserContext = Depends(get_current_user),
):
    _check_format(file_format)
    resp = await invoke_endpoint(
        get_stock_item_bills_pending_report,
        stock_item_name=stock_item_name,
        from_date=from_date,
        to_date=to_date,
        tracking_number=tracking_number,
        party=party,
        company_name=company_name,
        current_user=current_user,
    )
    return _export_response(
        file_format=file_format,
        company_name=company_name,
        filename_base=_safe_name(stock_item_name, "bills_pending"),
        spec=specs.stock_item_bills_pending_spec(
            resp, stock_item_name, company_name,
            _period_label(from_date=from_date, to_date=to_date),
        ),
    )



async def _summary_export(
    file_format, endpoint, label, selected_kw, selected, company_name,
    from_date, to_date, include_zero, current_user,
):
    _check_format(file_format)
    given = {
        selected_kw: selected,
        "company_name": company_name,
        "from_date": from_date,
        "to_date": to_date,
        "current_user": current_user,
    }
    if include_zero is not None:
        given["include_zero"] = include_zero
    resp = await invoke_endpoint(endpoint, **given)
    return _export_response(
        file_format=file_format,
        company_name=company_name,
        filename_base=_safe_name(label, resp.get("selected")),
        spec=specs.summary_drill_spec(
            label, resp.get("selected") or selected or "", resp, company_name,
            _period_label(from_date=from_date, to_date=to_date),
        ),
    )


@router.get("/stock-group-summary/export/{file_format}")
async def export_stock_group_summary(
    file_format: str,
    group: str | None = Query(default=None),
    company_name: str | None = Depends(get_authorized_company),
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    include_zero: bool | None = Query(default=None),
    current_user: UserContext = Depends(get_current_user),
):
    return await _summary_export(
        file_format, get_stock_group_summary_report, "Stock Group Summary",
        "group", group, company_name, from_date, to_date, include_zero, current_user,
    )


@router.get("/stock-category-summary/export/{file_format}")
async def export_stock_category_summary(
    file_format: str,
    category: str | None = Query(default=None),
    company_name: str | None = Depends(get_authorized_company),
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    include_zero: bool | None = Query(default=None),
    current_user: UserContext = Depends(get_current_user),
):
    return await _summary_export(
        file_format, get_stock_category_summary_report, "Stock Category Summary",
        "category", category, company_name, from_date, to_date, include_zero, current_user,
    )


@router.get("/godown-summary/export/{file_format}")
async def export_godown_summary(
    file_format: str,
    godown: str | None = Query(default=None),
    company_name: str | None = Depends(get_authorized_company),
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    include_zero: bool | None = Query(default=None),
    current_user: UserContext = Depends(get_current_user),
):
    return await _summary_export(
        file_format, get_godown_summary_report, "Godown Summary",
        "godown", godown, company_name, from_date, to_date, include_zero, current_user,
    )


@router.get("/inventory-register/{register_key}/vouchers/export/{file_format}")
async def export_inventory_register_vouchers(
    register_key: str,
    file_format: str,
    from_date: date = Query(...),
    to_date: date = Query(...),
    company_name: str | None = Depends(get_authorized_company),
    current_user: UserContext = Depends(get_current_user),
):
    _check_format(file_format)
    resp = await invoke_endpoint(
        get_inventory_register_vouchers,
        register_key=register_key,
        from_date=from_date,
        to_date=to_date,
        company_name=company_name,
        current_user=current_user,
    )
    return _export_response(
        file_format=file_format,
        company_name=company_name,
        filename_base=_safe_name(register_key, "vouchers"),
        spec=specs.register_vouchers_spec(
            resp, company_name,
            _period_label(from_date=from_date, to_date=to_date),
        ),
    )


