"""
Outstandings reports router: Receivables, Payables, Bill Allocations, Pending Invoices.
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
    BILLS_COLUMNS,
    PENDING_INVOICES_COLUMNS,
)

from app.tally.service import (
    fetch_bill_allocations as _real_fetch_bill_allocations,
    fetch_bills_receivable as _real_fetch_bills_receivable,
    fetch_bills_payable as _real_fetch_bills_payable,
)

from app.financial.service import (
    build_outstanding_summary,
    build_receivables_from_tally_report,
    build_payables_from_tally_report,
    build_pending_invoices_from_reports,
)

logger = logging.getLogger(__name__)

router = APIRouter()

def _get_fetcher(name, default):
    reports_mod = sys.modules.get("app.api.reports")
    return getattr(reports_mod, name, default) if reports_mod else default

async def fetch_bill_allocations(*args, **kwargs):
    return await _get_fetcher("fetch_bill_allocations", _real_fetch_bill_allocations)(*args, **kwargs)

async def fetch_bills_receivable(*args, **kwargs):
    return await _get_fetcher("fetch_bills_receivable", _real_fetch_bills_receivable)(*args, **kwargs)

async def fetch_bills_payable(*args, **kwargs):
    return await _get_fetcher("fetch_bills_payable", _real_fetch_bills_payable)(*args, **kwargs)

BILL_ALLOCATIONS_COLUMNS = [
    {"key": "bill_date", "label": "Date"},
    {"key": "bill_reference", "label": "Ref No."},
    {"key": "party", "label": "Party"},
    {"key": "pending_amount", "label": "Pending Amount"},
    {"key": "due_date", "label": "Due Date"},
    {"key": "overdue_days", "label": "Overdue Days"},
]

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
        company_name=company_name,
        filename_base="receivables",
        spec=specs.bills_spec(
            "Receivables",
            data["bills"],
            "Total Receivable",
            data["total_receivable"],
            company_name,
        ),
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
        company_name=company_name,
        filename_base="payables",
        spec=specs.bills_spec(
            "Payables",
            data["bills"],
            "Total Payable",
            data["total_payable"],
            company_name,
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
        company_name=company_name,
        filename_base="pending_invoices",
        spec=specs.bills_spec(
            "Pending Invoices",
            data["invoices"],
            "Total",
            None,
            company_name,
            with_type=True,
        ),
    )



@router.get("/bill-allocations/export/{file_format}")
async def export_bill_allocations(
    file_format: str,
    company_name: str | None = Depends(get_authorized_company),
    current_user: UserContext = Depends(get_current_user),
):
    _check_format(file_format)
    resp = await invoke_endpoint(
        get_bill_allocations, company_name=company_name, current_user=current_user
    )
    return _export_response(
        file_format=file_format,
        company_name=company_name,
        filename_base="purchase_bills",
        spec=specs.bill_allocations_spec(resp.get("bills", []), company_name),
    )
