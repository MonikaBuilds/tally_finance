"""
Ledgers reports router: Ledger reports, voucher detail, ledger lists.
"""

import logging
import sys
from datetime import date, datetime
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
    _resolve_org_id,
    _cached_report,
    _check_format,
    _safe_name,
    _spec_response,
    _export_response,
    _period_label,
    _as_rows,
    _fmt_period,
    _check_period,
    LEDGER_COLUMNS,
)

from app.tally.service import (
    fetch_ledger_list as _real_fetch_ledger_list,
    fetch_ledger_report as _real_fetch_ledger_report,
    fetch_voucher_detail as _real_fetch_voucher_detail,
    fetch_companies as _real_fetch_companies,
)
from app.tally.parsers.ledger import financial_year_bounds

logger = logging.getLogger(__name__)

router = APIRouter()

def _get_fetcher(name, default):
    reports_mod = sys.modules.get("app.api.reports")
    return getattr(reports_mod, name, default) if reports_mod else default

async def fetch_ledger_list(*args, **kwargs):
    return await _get_fetcher("fetch_ledger_list", _real_fetch_ledger_list)(*args, **kwargs)

async def fetch_ledger_report(*args, **kwargs):
    return await _get_fetcher("fetch_ledger_report", _real_fetch_ledger_report)(*args, **kwargs)

async def fetch_voucher_detail(*args, **kwargs):
    return await _get_fetcher("fetch_voucher_detail", _real_fetch_voucher_detail)(*args, **kwargs)

async def fetch_companies(*args, **kwargs):
    return await _get_fetcher("fetch_companies", _real_fetch_companies)(*args, **kwargs)

LEDGER_LIST_COLUMNS = [
    {"key": "name", "label": "Ledger Name"},
    {"key": "parent", "label": "Group"},
    {"key": "closing_balance", "label": "Closing Balance"},
]

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

async def _company_financial_year(
    company_name: str | None,
    current_user: UserContext,
):
    """
    The company's current financial year (start, end) from Tally's own
    company data (STARTINGFROM, else BOOKSFROM). (None, None) when
    Tally does not provide it.
    """
    from datetime import datetime as _datetime
    from app.tally.service import fetch_companies
    from app.tally.parsers.ledger import financial_year_bounds

    try:
        companies = await fetch_companies(
            org_id=_resolve_org_id(current_user),
        )

        company = next(
            (
                c for c in companies
                if company_name
                and (c.get("name") or "").strip().casefold()
                == company_name.strip().casefold()
            ),
            companies[0] if companies else None,
        )

        anchor_text = (
            (company or {}).get("starting_from")
            or (company or {}).get("books_from")
        )

        if not anchor_text:
            return None, None

        return financial_year_bounds(
            _datetime.strptime(anchor_text, "%Y-%m-%d").date()
        )

    except Exception as exc:
        logger.warning("Company financial year unavailable: %r", exc)
        return None, None


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
        report = await fetch_ledger_report(
            ledger_name=ledger_name,
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
        )

        # No explicit period requested: show every month of the
        # company's financial year (Tally's Apr..Mar monthly summary),
        # not only the months that happen to have transactions.
        if from_date is None and to_date is None and isinstance(report, dict):
            from app.tally.parsers.ledger import (
                extend_monthly_summary_to_period,
            )

            fy_start, fy_end = await _company_financial_year(
                company_name,
                current_user,
            )

            extend_monthly_summary_to_period(report, fy_start, fy_end)

        return report

    try:
        cache_res = await _cached_report(
            # v2: monthly_summary now spans the full financial year.
            report_name="ledger_report_v2",
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

async def _legacy_export_ledger_report(
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
            # v2: response now carries layout/role, bill refs, tax %
            # and current balances - don't serve older cached shapes.
            report_name="voucher_detail_v2",
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



@router.get("/ledger/export/{file_format}")
async def export_ledger_report(
    file_format: str,
    ledger_name: str = Query(...),
    company_name: str | None = Depends(get_authorized_company),
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    view: str = Query(default="monthly"),
    current_user: UserContext = Depends(get_current_user),
):
    _check_format(file_format)
    resp = await invoke_endpoint(
        get_ledger_report,
        ledger_name=ledger_name,
        company_name=company_name,
        from_date=from_date,
        to_date=to_date,
        current_user=current_user,
    )
    return _export_response(
        file_format=file_format,
        company_name=company_name,
        filename_base=_safe_name(
            ledger_name, "ledger", "monthly" if view == "monthly" else "vouchers"
        ),
        spec=specs.ledger_spec(
            resp["report"],
            ledger_name,
            company_name,
            _period_label(from_date=from_date, to_date=to_date),
            view if view in ("monthly", "detailed", "both") else "monthly",
        ),
    )



@router.get("/voucher/export/{file_format}")
async def export_voucher_detail(
    file_format: str,
    voucher_type: str = Query(...),
    voucher_number: str = Query(...),
    voucher_date: date | None = Query(default=None, alias="date"),
    ledger_name: str | None = Query(default=None),
    company_name: str | None = Depends(get_authorized_company),
    current_user: UserContext = Depends(get_current_user),
):
    _check_format(file_format)
    resp = await invoke_endpoint(
        get_voucher_detail,
        voucher_type=voucher_type,
        voucher_number=voucher_number,
        date=voucher_date,
        ledger_name=ledger_name,
        company_name=company_name,
        current_user=current_user,
    )
    return _export_response(
        file_format=file_format,
        company_name=company_name,
        filename_base=_safe_name(voucher_type, voucher_number),
        spec=specs.voucher_spec(resp["voucher"], company_name),
    )



@router.get("/ledgers/export/{file_format}")
async def export_ledger_list(
    file_format: str,
    company_name: str | None = Depends(get_authorized_company),
    current_user: UserContext = Depends(get_current_user),
):
    _check_format(file_format)
    resp = await invoke_endpoint(
        get_ledger_list, company_name=company_name, current_user=current_user
    )
    return _export_response(
        file_format=file_format,
        company_name=company_name,
        filename_base="ledgers",
        spec=specs.ledger_list_spec(resp.get("ledgers", []), company_name),
    )


