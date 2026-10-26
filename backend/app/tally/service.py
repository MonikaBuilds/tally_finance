import re
import logging
from datetime import date, datetime

from app.cache.config import cache_settings
from app.cache.keys import build_cache_key
from app.cache.manager import cache_manager, CacheResult
from app.tally.client import TallyClient
from app.tally.xml_builders import (
    build_company_request,
    build_profit_loss_request,
    build_group_summary_request,
    build_trial_balance_request,
    build_balance_sheet_request,
    build_voucher_bills_request,
    build_bills_receivable_request,
    build_bills_payable_request,
    build_ledger_list_request,
    build_single_ledger_request,
    build_ledger_report_request,
    build_ledger_voucher_collection_request,
    build_voucher_detail_request,
    build_stock_summary_request,
    build_stock_item_request,
    build_stock_group_request,
    build_stock_category_request,
    build_godown_request,
    build_stock_movement_request,
    build_inventory_register_request,
    build_stock_item_list_request,
    build_chatbot_ledger_request,
    build_stock_group_items_request,
    build_inventory_voucher_detail_request,
    build_register_vouchers_request,
)
from app.tally.parsers import (
    parse_companies,
    parse_profit_loss,
    parse_group_summary,
    parse_trial_balance,
    parse_balance_sheet,
    parse_bill_allocations,
    parse_outstanding_report,
    parse_ledger_list,
    parse_ledger_report,
    parse_voucher_detail,
    build_continuous_monthly_summary,
    parse_stock_summary,
    parse_stock_groups,
    parse_stock_categories,
    parse_godowns,
    parse_stock_movement,
    parse_inventory_register,
    parse_inventory_register_summary,
    parse_stock_valuation,
    parse_negative_stock,
    parse_stock_item_list,
    parse_inventory_voucher_detail,
)
from app.tally.parsers.inventory import (
    filter_stock_movement_by_godown,
)

from app.tally.parsers.inventory_registers import (
    build_register_months,
    build_voucher_register,
    clip_vouchers,
    parse_register_vouchers,
)

from app.tally.parsers.stock_item_ledger import (
    build_monthly_summary,
    build_voucher_ledger,
    default_period,
)

from app.tally.parsers.inventory_summary import (
    build_godown_balances,
    build_hierarchy_summary,
    month_starts,
    movement_effect,
    parse_item_godown_openings,
    pick_default_godown,
)

from app.tally.parsers.financial import (
    parse_balance_sheet_report,
)
from app.tally.parsers.ledger import (
    _parse_custom_voucher_ledger_rows,
)

_log = logging.getLogger(__name__)


client = TallyClient()


# ============================================================
# COMPANIES
# ============================================================

async def fetch_companies_result(
    force_refresh: bool = False,
    org_id: str | None = None,
) -> CacheResult:
    if not org_id:
        raise ValueError("org_id is required for cached company data")

    cache_key = build_cache_key(
        report_name="companies_v2",
        company_name=None,
        org_id=str(org_id),
    )

    async def _fetch():
        response = await client.send_xml(
            build_company_request()
        )
        return parse_companies(response)["companies"]

    result = await cache_manager.get_or_fetch(
        cache_key=cache_key,
        fetcher=_fetch,
        fresh_ttl=cache_settings.get_fresh_ttl("companies"),
        stale_retention_ttl=cache_settings.REDIS_CACHE_STALE_RETENTION_TTL,
        force_refresh=force_refresh,
        metadata={
            "report": "companies",
            "org_id": str(org_id),
        },
    )

    return result


async def fetch_companies(
    force_refresh: bool = False,
    org_id: str | None = None,
) -> list[dict]:
    result = await fetch_companies_result(
        force_refresh=force_refresh,
        org_id=org_id,
    )

    return result.data

# ============================================================
# PROFIT & LOSS
# ============================================================

async def fetch_profit_loss(
    from_date: date | None = None,
    to_date: date | None = None,
    company_name: str | None = None,
):
    request_xml = build_profit_loss_request(
        from_date=from_date,
        to_date=to_date,
        company_name=company_name,
    )

    print("\n========== PROFIT & LOSS REQUEST ==========")
    print(request_xml)
    print("========== END PROFIT & LOSS REQUEST ==========\n")

    response = await client.send_xml(request_xml)

    print("\n========== PROFIT & LOSS RESPONSE ==========")
    print(response)
    print("========== END PROFIT & LOSS RESPONSE ==========\n")

    return parse_profit_loss(response)


# ============================================================
# GROUP SUMMARY (Profit & Loss drill-down)
# ============================================================

async def fetch_group_summary(
    group_name: str,
    from_date: date | None = None,
    to_date: date | None = None,
    company_name: str | None = None,
):
    request_xml = build_group_summary_request(
        group_name=group_name,
        from_date=from_date,
        to_date=to_date,
        company_name=company_name,
    )

    print("\n========== GROUP SUMMARY REQUEST ==========")
    print(request_xml)
    print("========== END GROUP SUMMARY REQUEST ==========\n")

    response = await client.send_xml(request_xml)

    print("\n========== GROUP SUMMARY RESPONSE ==========")
    print(response)
    print("========== END GROUP SUMMARY RESPONSE ==========\n")

    return parse_group_summary(
        response,
        group_name=group_name,
    )


# ============================================================
# TRIAL BALANCE
# ============================================================

async def fetch_trial_balance(
    from_date: date | None = None,
    to_date: date | None = None,
    company_name: str | None = None,
):
    response = await client.send_xml(
        build_trial_balance_request(
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
        )
    )

    return parse_trial_balance(response)


# ============================================================
# BALANCE SHEET
# ============================================================

async def fetch_balance_sheet(
    from_date: date | None = None,
    to_date: date | None = None,
    company_name: str | None = None,
):
    response = await client.send_xml(
        build_balance_sheet_request(
            company_name=company_name,
            to_date=to_date,
        )
    )

    return parse_balance_sheet(response)


async def fetch_balance_sheet_report(
    from_date: date | None = None,
    to_date: date | None = None,
    company_name: str | None = None,
):
    """
    Balance Sheet page / export: both From Date and To Date are sent to
    Tally as SVFROMDATE / SVTODATE, and the response is parsed into the
    two-sided (Liabilities | Assets) structure Tally displays.

    fetch_balance_sheet() above is left untouched for the chatbot tool.
    """

    request_xml = build_balance_sheet_request(
        company_name=company_name,
        from_date=from_date,
        to_date=to_date,
    )

    print("\n========== BALANCE SHEET REQUEST ==========")
    print(request_xml)
    print("========== END BALANCE SHEET REQUEST ==========\n")

    response = await client.send_xml(request_xml)

    report = parse_balance_sheet_report(response)

    # Tally's screen prints "Opening Balance" / "Current Period" under
    # Profit & Loss A/c, but its XML export does not always carry those
    # two sub-lines. When they are missing, rebuild them from Tally's own
    # Profit & Loss for the same period.
    await _add_profit_loss_sublines(
        report,
        from_date=from_date,
        to_date=to_date,
        company_name=company_name,
    )

    return report


_PROFIT_LOSS_LINE = re.compile(
    r"^profit\s+(&|and)\s+loss(\s+(a/c|account))?$",
    re.IGNORECASE,
)


def _apply_profit_loss_sublines(
    report: dict,
    net_result: float,
) -> bool:
    """
    Give the Profit & Loss A/c line of a parsed Balance Sheet its two
    sub-lines, exactly as Tally shows them.

    Returns True when a line was filled in.
    """

    changed = False

    for side in ("liabilities", "assets"):
        for line in report.get(side, []):
            if not _PROFIT_LOSS_LINE.match(
                (line.get("name") or "").strip()
            ):
                continue

            if line.get("children"):
                continue

            amount = line.get("amount") or 0.0

            # Credit balance -> Liabilities side (positive).
            # Debit balance -> Assets side (negative).
            direction = 1 if side == "liabilities" else -1

            closing = amount * direction

            def _relative(value):
                value = round(value * direction, 2)
                return value if abs(value) >= 0.005 else None

            line["children"] = [
                {
                    "name": "Opening Balance",
                    "amount": _relative(
                        closing - net_result
                    ),
                    "is_group": False,
                    "derived": True,
                },
                {
                    "name": "Current Period",
                    "amount": _relative(net_result),
                    "is_group": False,
                    "derived": True,
                },
            ]

            changed = True

    return changed


async def _add_profit_loss_sublines(
    report: dict,
    from_date: date | None,
    to_date: date | None,
    company_name: str | None,
) -> None:
    """
    Fetch Tally's Profit & Loss for the Balance Sheet's period and use its
    net result for the Profit & Loss A/c sub-lines.

    Only does anything when the Balance Sheet has a Profit & Loss A/c
    line without sub-lines.
    """

    needs_sublines = any(
        _PROFIT_LOSS_LINE.match(
            (line.get("name") or "").strip()
        )
        and not line.get("children")
        for side in ("liabilities", "assets")
        for line in report.get(side, [])
    )

    if not needs_sublines:
        return

    try:
        profit_loss = await fetch_profit_loss(
            from_date=from_date,
            to_date=to_date,
            company_name=company_name,
        )

        net_result = (
            (profit_loss.get("summary") or {})
            .get("net_result")
        )

        if net_result is None:
            return

        _apply_profit_loss_sublines(
            report,
            float(net_result),
        )

    except Exception as e:
        print(
            "Balance Sheet: could not add Profit & Loss sub-lines:",
            repr(e),
        )


# ============================================================
# BILL ALLOCATIONS
# ============================================================

async def fetch_bill_allocations(
    from_date: date | None = None,
    to_date: date | None = None,
    company_name: str | None = None,
):
    response = await client.send_xml(
        build_voucher_bills_request(
            from_date=from_date,
            to_date=to_date,
            company_name=company_name,
        )
    )

    # parse_bill_allocations() returns:
    # {"success": ..., "rows": [...], "count": ...}
    return parse_bill_allocations(response).get(
        "rows",
        [],
    )


# ============================================================
# RECEIVABLES
# ============================================================

async def fetch_bills_receivable_result(
    company_name: str | None = None,
    org_id: str | None = None,
    force_refresh: bool = False,
) -> CacheResult:
    """
    Fetch Bills Receivable from Tally with Redis caching.

    Redis stores the exact Tally XML response.
    Parsing happens only after the cached/Tally response is retrieved.
    """

    if not org_id:
        raise ValueError(
            "org_id is required for cached receivables data"
        )

    effective_org_id = str(org_id)

    cache_key = build_cache_key(
        report_name="receivables",
        company_name=company_name,
        org_id=effective_org_id,
    )

    async def _fetch():
        return await client.send_xml(
            build_bills_receivable_request(
                company_name=company_name,
            )
        )

    cache_result = await cache_manager.get_or_fetch(
        cache_key=cache_key,
        fetcher=_fetch,
        fresh_ttl=cache_settings.get_fresh_ttl(
            "receivables"
        ),
        stale_retention_ttl=(
            cache_settings.REDIS_CACHE_STALE_RETENTION_TTL
        ),
        force_refresh=force_refresh,
        metadata={
            "report": "receivables",
            "company": company_name,
            "org_id": effective_org_id,
        },
    )

    # Parse only after retrieving the exact XML
    # from Tally or Redis.
    parsed = parse_outstanding_report(
        cache_result.data,
        report_type="receivable",
    )

    return CacheResult(
        data=parsed.get("rows", []),
        source=cache_result.source,
        cached_at=cache_result.cached_at,
        is_stale=cache_result.is_stale,
    )


async def fetch_bills_receivable(
    company_name: str | None = None,
    org_id: str | None = None,
    force_refresh: bool = False,
):
    """
    Fetch Bills Receivable.

    Existing callers continue receiving a plain list of
    bill dictionaries.

    Cache metadata remains available through
    fetch_bills_receivable_result().
    """

    # Do not silently create a shared/default cache namespace.
    # If organization context is unavailable, preserve the
    # existing direct-Tally behavior instead of risking
    # cross-tenant cache leakage.
    if not org_id:
        response = await client.send_xml(
            build_bills_receivable_request(
                company_name=company_name,
            )
        )

        return parse_outstanding_report(
            response,
            report_type="receivable",
        ).get("rows", [])

    result = await fetch_bills_receivable_result(
        company_name=company_name,
        org_id=org_id,
        force_refresh=force_refresh,
    )

    return result.data


# ============================================================
# PAYABLES
# ============================================================

async def fetch_bills_payable(
    company_name: str | None = None,
    timeout: float = 30.0,
):
    response = await client.send_xml(
        build_bills_payable_request(
            company_name=company_name,
        ),
        timeout=timeout,
    )

    return parse_outstanding_report(
        response,
        report_type="payable",
    ).get("rows", [])


# ============================================================
# LEDGER LIST
# ============================================================

async def fetch_ledger_list(
    company_name: str | None = None,
):
    response = await client.send_xml(
        build_ledger_list_request(
            company_name=company_name,
        )
    )

    # parse_ledger_list() returns:
    # {"success": ..., "ledgers": [...], "count": ...}
    return parse_ledger_list(response).get(
        "ledgers",
        [],
    )


# ============================================================
# LEDGER REPORT
# ============================================================

def _financial_year_start(value: date) -> date:
    """
    Return the Indian financial year start for a given date.

    Example:
        2026-08-27 -> 2026-04-01
        2026-02-15 -> 2025-04-01
    """

    return date(
        value.year if value.month >= 4 else value.year - 1,
        4,
        1,
    )


async def fetch_ledger_report(
    ledger_name: str,
    from_date: date | None = None,
    to_date: date | None = None,
    company_name: str | None = None,
):
    """
    Fetch a ledger report from Tally.

    Flow:
    1. Fetch this one ledger's master info.
    2. Try Tally's native Ledger Vouchers report.
    3. If native report gives no usable rows, fetch actual vouchers.
    4. Parse only vouchers belonging to the requested ledger.
    5. Filter rows by requested date range.
    6. Calculate running balance from actual debit/credit values.
    """

    print("\n==============================================")
    print("           LEDGER REPORT REQUEST")
    print("==============================================")
    print(f"Ledger    : {ledger_name}")
    print(f"Company   : {company_name}")
    print(f"From Date : {from_date}")
    print(f"To Date   : {to_date}")
    print("==============================================\n")

    # --------------------------------------------------------
    # 1. Get THIS ledger's master information
    # --------------------------------------------------------

    opening_balance = 0.0
    closing_balance = None

    try:
        master_response = await client.send_xml(
            build_single_ledger_request(
                ledger_name=ledger_name,
                company_name=company_name,
            )
        )

        master = parse_ledger_list(master_response)
        matched_ledgers = master.get("ledgers", [])

        if matched_ledgers:
            opening_balance = float(
                matched_ledgers[0].get(
                    "opening_balance",
                    0,
                )
                or 0
            )

            closing_balance = matched_ledgers[0].get(
                "closing_balance"
            )

    except Exception as exc:
        print(
            f"WARNING: Unable to fetch ledger master: {exc}"
        )

    print(
        f"Ledger opening balance: {opening_balance}"
    )

    # --------------------------------------------------------
    # 2. Determine the Tally query period
    # --------------------------------------------------------

    query_from_date = from_date

    if from_date or to_date:
        anchor = from_date or to_date

        query_from_date = _financial_year_start(
            anchor
        )

    print(
        f"Ledger query from date: {query_from_date}"
    )

    # --------------------------------------------------------
    # 3. Try native Tally Ledger Vouchers report
    # --------------------------------------------------------

    try:
        request_xml = build_ledger_report_request(
            ledger_name=ledger_name,
            from_date=query_from_date,
            to_date=to_date,
            company_name=company_name,
        )

        print(
            "\n========== LEDGER NATIVE REQUEST =========="
        )
        print(request_xml)
        print(
            "========== END LEDGER NATIVE REQUEST ==========\n"
        )

        response = await client.send_xml(
            request_xml
        )

        print(
            "\n========== LEDGER NATIVE RESPONSE =========="
        )
        print(response)
        print(
            "========== END LEDGER NATIVE RESPONSE ==========\n"
        )

        report = parse_ledger_report(
            response,
            ledger_name,
            opening_balance=opening_balance,
            closing_balance=closing_balance,
            from_date=(
                from_date.isoformat()
                if from_date
                else None
            ),
            to_date=(
                to_date.isoformat()
                if to_date
                else None
            ),
        )

        native_entries = report.get(
            "entries",
            [],
        )

        print(
            f"Native ledger entries found: "
            f"{len(native_entries)}"
        )

        if native_entries:
            print(
                "Native Tally ledger report returned "
                "usable entries."
            )
            return report

        print(
            "Native ledger report returned no entries."
        )
        print(
            "Trying voucher collection fallback..."
        )

    except Exception as exc:
        print(
            f"WARNING: Native ledger report failed: "
            f"{exc}"
        )

    # --------------------------------------------------------
    # 4. Fallback: fetch actual voucher collection
    # --------------------------------------------------------

    try:
        print("\n==============================================")
        print("       LEDGER VOUCHER FALLBACK")
        print("==============================================")

        voucher_request = (
            build_ledger_voucher_collection_request(
                ledger_name=ledger_name,
                from_date=query_from_date,
                to_date=to_date,
                company_name=company_name,
            )
        )

        print(
            "\n========== LEDGER FALLBACK REQUEST =========="
        )
        print(voucher_request)
        print(
            "========== END LEDGER FALLBACK REQUEST ==========\n"
        )

        voucher_response = await client.send_xml(
            voucher_request
        )

        print(
            "\n========== LEDGER FALLBACK RESPONSE =========="
        )
        print(voucher_response)
        print(
            "========== END LEDGER FALLBACK RESPONSE ==========\n"
        )

        voucher_rows = (
            _parse_custom_voucher_ledger_rows(
                voucher_response,
                ledger_name,
            )
        )

        print(
            f"Voucher fallback rows parsed: "
            f"{len(voucher_rows)}"
        )

        # ----------------------------------------------------
        # 5. Filter rows by requested date range
        # ----------------------------------------------------

        filtered_rows = []

        for row in voucher_rows:
            row_date = row.get("date")

            if not row_date:
                continue

            current_date = None

            if isinstance(row_date, date):
                current_date = row_date

            elif isinstance(row_date, str):
                try:
                    current_date = datetime.strptime(
                        row_date,
                        "%Y-%m-%d",
                    ).date()

                except ValueError:
                    try:
                        current_date = datetime.strptime(
                            row_date,
                            "%Y%m%d",
                        ).date()

                    except ValueError:
                        continue

            if current_date is None:
                continue

            if (
                from_date is not None
                and current_date < from_date
            ):
                continue

            if (
                to_date is not None
                and current_date > to_date
            ):
                continue

            row["date"] = current_date.isoformat()

            filtered_rows.append(row)

        # ----------------------------------------------------
        # 6. Sort chronologically
        # ----------------------------------------------------

        filtered_rows.sort(
            key=lambda row: row.get("date") or ""
        )

        print(
            f"Rows after date filtering: "
            f"{len(filtered_rows)}"
        )

        # ----------------------------------------------------
        # 7. Calculate running balance
        # ----------------------------------------------------

        running_balance = opening_balance
        total_debit = 0.0
        total_credit = 0.0

        for row in filtered_rows:
            debit = float(
                row.get("debit", 0) or 0
            )

            credit = float(
                row.get("credit", 0) or 0
            )

            total_debit += debit
            total_credit += credit

            running_balance += (
                debit - credit
            )

            row["running_balance"] = (
                running_balance
            )

            if row.get(
                "diff_in_tax_amount"
            ) is None:
                row[
                    "diff_in_tax_amount"
                ] = 0.0

            if row.get(
                "balance_after_diff_in_tax"
            ) is None:
                row[
                    "balance_after_diff_in_tax"
                ] = running_balance

        # ----------------------------------------------------
        # 8. Closing balance
        # ----------------------------------------------------

        if filtered_rows:
            calculated_closing_balance = (
                running_balance
            )
        else:
            calculated_closing_balance = (
                opening_balance
            )

        # ----------------------------------------------------
        # 9. Monthly summary
        # ----------------------------------------------------

        monthly_summary = build_continuous_monthly_summary(
            filtered_rows,
            opening_balance,
            start_date=from_date,
            end_date=to_date,
        )

        # ----------------------------------------------------
        # 10. Final report
        # ----------------------------------------------------

        report = {
            "ledger_name": ledger_name,
            "opening_balance": opening_balance,
            "closing_balance": calculated_closing_balance,
            "total_debit": total_debit,
            "total_credit": total_credit,
            "entries": filtered_rows,
            "monthly_summary": monthly_summary,
            "entry_count": len(filtered_rows),
            "from_date": (
                from_date.isoformat()
                if from_date
                else None
            ),
            "to_date": (
                to_date.isoformat()
                if to_date
                else None
            ),
        }

        print(
            "\n=============================================="
        )
        print(
            "       LEDGER FALLBACK SUCCESS"
        )
        print(
            "=============================================="
        )
        print(
            f"Ledger       : {ledger_name}"
        )
        print(
            f"Entries      : {len(filtered_rows)}"
        )
        print(
            f"Total Debit  : {total_debit}"
        )
        print(
            f"Total Credit : {total_credit}"
        )
        print(
            f"Opening      : {opening_balance}"
        )
        print(
            f"Closing      : {calculated_closing_balance}"
        )
        print(
            "==============================================\n"
        )

        return report

    except Exception as exc:
        print(
            f"LEDGER FALLBACK FAILED: {exc}"
        )

        raise RuntimeError(
            f"Unable to fetch ledger "
            f"'{ledger_name}' from Tally: {exc}"
        )


# ============================================================
# VOUCHER DETAIL
# ============================================================

async def fetch_voucher_detail(
    voucher_type: str,
    voucher_number: str,
    voucher_date: date | None = None,
    company_name: str | None = None,
):
    """
    Fetch one accounting voucher with every ledger line inside it,
    plus each ledger's current (closing) balance from Tally - the
    "Current balance" / "Cur Bal" figures on Tally's own voucher
    screen.
    """

    vouchers = await _fetch_voucher_detail_raw(
        voucher_type=voucher_type,
        voucher_number=voucher_number,
        voucher_date=voucher_date,
        company_name=company_name,
    )

    if not vouchers:
        return vouchers

    try:
        ledgers = await fetch_ledger_list(
            company_name=company_name,
        )
    except Exception as exc:
        # The voucher itself is still correct without balances.
        logging.getLogger(__name__).warning(
            "Voucher current balances unavailable: %r",
            exc,
        )
        return vouchers

    closing_by_name = {
        str(ledger.get("name") or "").strip().casefold():
            ledger.get("closing_balance")
        for ledger in ledgers
        if ledger.get("name")
    }

    for voucher in vouchers:
        for entry in voucher.get("entries", []):
            closing = closing_by_name.get(
                str(entry.get("ledger_name") or "")
                .strip()
                .casefold()
            )

            if closing is None:
                continue

            # Tally's signed closing balance: negative = debit.
            entry["current_balance"] = round(abs(closing), 2)
            entry["current_balance_type"] = (
                "" if closing == 0
                else "Dr" if closing < 0
                else "Cr"
            )

    return vouchers


async def _fetch_voucher_detail_raw(
    voucher_type: str,
    voucher_number: str,
    voucher_date: date | None = None,
    company_name: str | None = None,
):
    """
    Fetch and parse one accounting voucher (no balances).
    """

    request_xml = build_voucher_detail_request(
        voucher_type=voucher_type,
        voucher_number=voucher_number,
        voucher_date=voucher_date,
        company_name=company_name,
    )

    print(
        "\n========== VOUCHER DETAIL REQUEST =========="
    )
    print(request_xml)
    print(
        "========== END VOUCHER DETAIL REQUEST ==========\n"
    )

    response = await client.send_xml(request_xml)

    print(
        "\n========== VOUCHER DETAIL RESPONSE =========="
    )
    print(response)
    print(
        "========== END VOUCHER DETAIL RESPONSE ==========\n"
    )

    vouchers = parse_voucher_detail(
        response,
        voucher_type=voucher_type,
        voucher_number=voucher_number,
        voucher_date=(
            voucher_date.isoformat()
            if voucher_date
            else None
        ),
    )

    if vouchers:
        return vouchers

    # ----------------------------------------------------------
    # Fallback: retry without date restriction.
    # ----------------------------------------------------------

    if voucher_date is not None:
        request_xml = build_voucher_detail_request(
            voucher_type=voucher_type,
            voucher_number=voucher_number,
            voucher_date=None,
            company_name=company_name,
        )

        response = await client.send_xml(
            request_xml
        )

        vouchers = parse_voucher_detail(
            response,
            voucher_type=voucher_type,
            voucher_number=voucher_number,
            voucher_date=None,
        )

    return vouchers




# ============================================================
# INVENTORY VOUCHER DETAIL
# ============================================================

async def fetch_inventory_voucher_detail(
    voucher_type: str,
    voucher_number: str,
    voucher_date: date | None = None,
    company_name: str | None = None,
):
    response = await client.send_xml(
        build_inventory_voucher_detail_request(
            voucher_type=voucher_type,
            voucher_number=voucher_number,
            voucher_date=voucher_date,
            company_name=company_name,
        )
    )

    result = parse_inventory_voucher_detail(
        response,
        voucher_type=voucher_type,
        voucher_number=voucher_number,
        voucher_date=(
            voucher_date.isoformat() if voucher_date else None
        ),
    )

    # Some Tally installations are less consistent about applying
    # date variables to custom collections. Retry with only the
    # voucher type/number filter if the dated request found nothing.
    if result.get("voucher") is None and voucher_date is not None:
        response = await client.send_xml(
            build_inventory_voucher_detail_request(
                voucher_type=voucher_type,
                voucher_number=voucher_number,
                voucher_date=None,
                company_name=company_name,
            )
        )

        result = parse_inventory_voucher_detail(
            response,
            voucher_type=voucher_type,
            voucher_number=voucher_number,
        )

    return await _attach_ledger_balances(result, company_name)


async def _attach_ledger_balances(result: dict, company_name: str | None) -> dict:
    """
    Add Tally's "Current balance" to the party and the other ledgers of
    the voucher, as on the voucher date. The voucher is still returned
    (without balances) if Tally cannot answer.
    """
    voucher = result.get("voucher")

    if not voucher:
        return result

    names = [e["ledger"] for e in voucher.get("ledger_entries", [])]

    if voucher.get("party"):
        names.append(voucher["party"])

    if not names:
        return result

    try:
        from app.tally.xml_builders.inventory import build_ledger_balances_request
        from app.tally.parsers.inventory import parse_ledger_balances
        from app.tally.parsers.inventory_summary import normalize_master_name

        as_on = (
            date.fromisoformat(voucher["date"]) if voucher.get("date") else None
        )

        balances = parse_ledger_balances(
            await client.send_xml(
                build_ledger_balances_request(
                    names, as_on=as_on, company_name=company_name
                )
            )
        )
    except Exception as e:
        _log.warning("Could not fetch ledger balances for voucher: %r", e)
        return result

    def balance_of(name):
        return balances.get(normalize_master_name(name or "").casefold())

    for entry in voucher.get("ledger_entries", []):
        entry["balance"] = balance_of(entry["ledger"])

    voucher["party_balance"] = balance_of(voucher.get("party"))

    return result

# ============================================================
# STOCK SUMMARY
# ============================================================

# Stock Summary makes Tally calculate closing figures for every stock
# item, which can take far longer than the default 30 seconds.
STOCK_SUMMARY_TIMEOUT = 120.0

async def fetch_stock_summary(
    company_name: str | None = None,
    to_date: date | None = None,
    from_date: date | None = None,
):
    response = await client.send_xml(
        build_stock_summary_request(
            company_name=company_name,
            to_date=to_date,
            from_date=from_date,
        ),
        timeout=STOCK_SUMMARY_TIMEOUT,
    )

    return parse_stock_summary(response)


async def fetch_chatbot_ledger_raw(
    ledger_name: str,
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> str:
    """
    Fetch the ledger-scoped XML response directly from Tally
    for chatbot use.

    No financial values are calculated in this function.
    """

    response = await client.send_xml(
        build_chatbot_ledger_request(
            ledger_name=ledger_name,
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
        )
    )

    return response


# ============================================================
# STOCK ITEM
# ============================================================

async def fetch_stock_item(
    company_name: str | None = None,
    stock_item_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
):
    response = await client.send_xml(
        build_stock_item_request(
            company_name=company_name,
            stock_item_name=stock_item_name,
            from_date=from_date,
            to_date=to_date,
        )
    )

    return parse_stock_summary(response)


# ============================================================
# STOCK GROUPS
# ============================================================

async def fetch_stock_groups(
    company_name: str | None = None,
):
    response = await client.send_xml(
        build_stock_group_request(
            company_name=company_name,
        )
    )

    return parse_stock_groups(response)


# ============================================================
# STOCK CATEGORIES
# ============================================================

async def fetch_stock_categories(
    company_name: str | None = None,
):
    response = await client.send_xml(
        build_stock_category_request(
            company_name=company_name,
        )
    )

    return parse_stock_categories(response)


# ============================================================
# GODOWNS
# ============================================================

async def fetch_godowns(
    company_name: str | None = None,
):
    response = await client.send_xml(
        build_godown_request(
            company_name=company_name,
        )
    )

    return parse_godowns(response)


# ============================================================
# SALES BILLS PENDING (STOCK ITEM)
# ============================================================

async def fetch_sales_bills_pending(
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    stock_item_name: str | None = None,
    tracking_number: str | None = None,
    party: str | None = None,
):
    report = await fetch_stock_movement(
        company_name=company_name,
        from_date=from_date,
        to_date=to_date,
        stock_item_name=stock_item_name,
    )

    rows = report.get("rows", [])

    if tracking_number:
        target = tracking_number.strip().casefold()
        rows = [
            r for r in rows
            if (r.get("tracking_number") or r.get("voucher_number") or "").strip().casefold() == target
        ]

    groups = {}
    details = []

    for row in rows:
        voucher_type = (row.get("voucher_type") or "").strip().casefold()
        item = row.get("stock_item")

        is_delivery = "delivery note" in voucher_type
        is_rejection_in = "rejections in" in voucher_type

        if not item or not (is_delivery or is_rejection_in):
            continue

        # A return belongs to the delivery it was booked against; with
        # no tracking number it is netted against the item's delivery.
        tracking = (row.get("tracking_number") or "").strip()

        if not tracking and is_delivery:
            tracking = (row.get("voucher_number") or "").strip()

        key = (item.strip().casefold(), tracking.casefold())

        group = groups.setdefault(key, {
            "date": row.get("date"),
            "tracking_number": tracking,
            "stock_item": item,
            "party": row.get("party"),
            "initial_quantity": 0.0,
            "pending_quantity": 0.0,
            "rate": row.get("rate") or 0.0,
            "value": 0.0,
            "_has_delivery": False,
        })

        quantity = abs(row.get("quantity") or 0.0)
        amount = abs(row.get("amount") or 0.0)

        if is_delivery:
            group["initial_quantity"] += quantity
            group["pending_quantity"] += quantity
            group["value"] += amount

            if not group["_has_delivery"]:
                group.update(
                    _has_delivery=True,
                    date=row.get("date"),
                    party=row.get("party"),
                    rate=row.get("rate") or 0.0,
                )
        else:
            group["pending_quantity"] -= quantity
            group["value"] -= amount

        details.append({
            "date": row.get("date"),
            "tracking_number": tracking,
            "party": row.get("party"),
            "stock_item": item,
            "voucher_type": row.get("voucher_type"),
            "voucher_number": row.get("voucher_number"),
            "quantity": row.get("quantity"),
            "rate": row.get("rate"),
            "value": row.get("amount"),
            "reference": row.get("reference"),
            "godown": row.get("godown"),
            "batch": row.get("batch"),
            "narration": row.get("narration"),
        })

    # The party narrows down which bills are shown. It is judged on the
    # bill (its delivery note), not on every note: a return booked
    # against the bill may carry no party or another one, and must still
    # be listed under it.
    if party:
        wanted = party.strip().casefold()
        kept = {
            key for key, g in groups.items()
            if (g.get("party") or "").strip().casefold() == wanted
        }
        details = [
            d for d in details
            if (
                (d["stock_item"] or "").strip().casefold(),
                (d["tracking_number"] or "").strip().casefold(),
            ) in kept
        ]
        groups = {key: g for key, g in groups.items() if key in kept}

    summary = [
        {k: v for k, v in g.items() if not k.startswith("_")}
        for g in groups.values()
        if abs(g["pending_quantity"]) > 0.0001
    ]
    summary.sort(key=lambda r: (r.get("date") or "", r.get("tracking_number") or ""))
    details.sort(key=lambda r: (r.get("date") or "", r.get("voucher_number") or ""))

    # Tally prints the unit after each quantity ("5 NOS @"): it is the
    # stock item's own unit. The bills still list without it if the
    # item master cannot be read.
    unit = ""

    if stock_item_name:
        try:
            master = await _load_item_master(
                stock_item_name, company_name, as_on=to_date
            )
            unit = (master or {}).get("base_units") or ""
        except Exception as e:
            _log.warning("Could not read the unit of %r: %r", stock_item_name, e)

    return {
        "success": True,
        "rows": summary,
        "details": details,
        "count": len(summary),
        "unit": unit,
    }


# ============================================================
# STOCK MOVEMENT
# ============================================================

async def fetch_stock_movement(
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    stock_item_name: str | None = None,
    godown_name: str | None = None,
):
    response = await client.send_xml(
        build_stock_movement_request(
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
            stock_item_name=stock_item_name,
        )
    )

    result = parse_stock_movement(response)

    # Tally's TDL formulas cannot easily filter vouchers by
    # godown of a nested inventory entry, so apply the location
    # filter in Python after parsing.
    # The voucher collection returns WHOLE vouchers, so the item and
    # period filters have to be applied to the parsed entries: a
    # voucher that merely contains the item also brings its other
    # items, and Tally does not clip vouchers to SVFROMDATE/SVTODATE.
    result = _clip_movement(
        result,
        stock_item_name=stock_item_name,
        from_date=from_date,
        to_date=to_date,
    )

    # Tally's TDL formulas cannot easily filter vouchers by the
    # godown of a nested inventory entry, so a location (godown)
    # is applied here in Python, against the already-parsed rows,
    # for the Location Summary / Location Monthly Summary screens.
    if godown_name:
        # Entries saved without a godown belong to the default
        # location, which must be resolved from the godown masters.
        masters = await fetch_godowns(company_name=company_name)

        rows = filter_stock_movement_by_godown(
            result.get("rows", []),
            godown_name,
            default_godown=pick_default_godown(
                masters.get("rows", [])
            ),
        )

        result = {
            "success": True,
            "rows": rows,
            "count": len(rows),
        }

    return result


def _clip_movement(result, stock_item_name, from_date, to_date):
    rows = result.get("rows", [])

    if stock_item_name:
        target = stock_item_name.strip().casefold()
        rows = [
            r for r in rows
            if (r.get("stock_item") or "").strip().casefold() == target
        ]

    if from_date:
        rows = [r for r in rows if (r.get("date") or "") >= from_date.isoformat()]

    if to_date:
        rows = [r for r in rows if (r.get("date") or "") <= to_date.isoformat()]

    return {"success": True, "rows": rows, "count": len(rows)}


# ============================================================
# STOCK ITEM MONTHLY SUMMARY
# ============================================================

async def resolve_stock_period(
    company_name: str | None = None,
    stock_item_name: str | None = None,
) -> tuple[date, date]:
    """
    Financial year (1 Apr - 31 Mar) to use when the caller gave no
    period: the year of the latest stock voucher in Tally, or - for a
    company with no stock vouchers - the year containing today. Using
    today's year blindly gives an empty report once you are past the
    last year that has data.
    """
    movement = await fetch_stock_movement(
        company_name=company_name,
        stock_item_name=stock_item_name,
    )

    dates = [r["date"] for r in movement.get("rows", []) if r.get("date")]
    latest = date.fromisoformat(max(dates)) if dates else date.today()

    start_year = latest.year if latest.month >= 4 else latest.year - 1

    return date(start_year, 4, 1), date(start_year + 1, 3, 31)


async def _load_item_vouchers(
    stock_item_name: str,
    company_name: str | None = None,
) -> tuple[list[dict], list[dict]]:
    """
    Every inventory entry Tally holds for one stock item, plus all the
    entries of those same vouchers (the other items of a Stock Journal
    are needed to name the voucher's counterpart).

    No period is sent: Tally answers for its current period, which also
    carries the item's opening balance (see _load_item_master).
    """
    response = await client.send_xml(
        build_stock_movement_request(
            company_name=company_name,
            stock_item_name=stock_item_name,
        )
    )

    all_rows = parse_stock_movement(response).get("rows", [])
    target = stock_item_name.strip().casefold()

    item_rows = [
        r for r in all_rows
        if (r.get("stock_item") or "").strip().casefold() == target
    ]

    return item_rows, all_rows


async def _load_item_master(
    stock_item_name: str,
    company_name: str | None = None,
    as_on: date | None = None,
) -> dict | None:
    """
    The stock item as Tally reports it: opening balance / value at the
    start of Tally's current period, unit, and the closing balance as on
    `as_on`.

    Only the to-date is sent. Tally stops answering the Stock Item
    collection when a from-date is sent with it (see
    STOCK_COLLECTION_SEND_FROM_DATE), and a from-date = to-date request
    returned the same balance for every date.
    """
    report = await fetch_stock_item(
        company_name=company_name,
        stock_item_name=stock_item_name,
        to_date=as_on,
    )

    target = stock_item_name.strip().casefold()

    for row in report.get("rows", []):
        if (row.get("name") or "").strip().casefold() == target:
            return row

    return None


async def fetch_stock_item_monthly(
    stock_item_name: str,
    from_date: date | None,
    to_date: date | None,
    company_name: str | None = None,
):
    """
    Tally's "Stock Item Monthly Summary": every month of the period,
    with Inwards / Outwards and the Closing Balance of each month.
    Directly fetches Tally's native Item Monthly Summary report.
    """
    item_rows, _all_rows = await _load_item_vouchers(
        stock_item_name, company_name
    )

    if not from_date or not to_date:
        default_from, default_to = default_period(item_rows)
        from_date = from_date or default_from
        to_date = to_date or default_to

    try:
        from app.tally.xml_builders.inventory import build_item_monthly_summary_request
        from app.tally.parsers.inventory import parse_item_monthly_summary

        xml_request = build_item_monthly_summary_request(
            stock_item_name=stock_item_name,
            from_date=from_date,
            to_date=to_date,
            company_name=company_name,
        )
        xml_response = await client.send_xml(xml_request)
        start_year = (
            from_date.year
            if from_date
            else (date.today().year if date.today().month >= 4 else date.today().year - 1)
        )
        native_rows = parse_item_monthly_summary(xml_response, start_year=start_year)
        if native_rows:
            master = await _load_item_master(
                stock_item_name, company_name, as_on=to_date
            )
            opening_qty = (master or {}).get("opening_quantity") or 0.0
            opening_val = (master or {}).get("opening_value") or 0.0
            tally_closing = (
                {
                    "quantity": master.get("closing_quantity"),
                    "value": master.get("closing_value"),
                }
                if master
                else None
            )
            return {
                "from": from_date.isoformat() if from_date else f"{start_year}-04-01",
                "to": to_date.isoformat() if to_date else f"{start_year + 1}-03-31",
                "opening": {
                    "quantity": opening_qty,
                    "value": opening_val,
                },
                "unit": (master or {}).get("base_units", ""),
                "rows": native_rows,
                "item_found": bool(master or native_rows),
                "tally_closing": tally_closing,
                "reconciled": True,
            }
    except Exception as e:
        _log.warning("Native Stock Item Monthly Summary fetch failed, falling back: %r", e)

    master = await _load_item_master(
        stock_item_name, company_name, as_on=to_date
    )

    summary = build_monthly_summary(
        item_rows,
        opening_quantity=(master or {}).get("opening_quantity") or 0.0,
        opening_value=(master or {}).get("opening_value") or 0.0,
        from_date=from_date,
        to_date=to_date,
    )

    tally_closing = (
        {
            "quantity": master.get("closing_quantity"),
            "value": master.get("closing_value"),
        }
        if master
        else None
    )

    return {
        "from": from_date.isoformat(),
        "to": to_date.isoformat(),
        "opening": summary["opening"],
        "unit": (master or {}).get("base_units", ""),
        "rows": summary["rows"],
        "item_found": bool(master or item_rows),
        "tally_closing": tally_closing,
        "reconciled": (
            tally_closing is None
            or abs(
                (tally_closing["quantity"] or 0.0)
                - summary["closing"]["quantity"]
            ) < 1e-6
        ),
    }


async def fetch_stock_item_vouchers(
    stock_item_name: str,
    from_date: date | None,
    to_date: date | None,
    company_name: str | None = None,
    godown_name: str | None = None,
):
    """
    Tally's "Stock Item Vouchers" for one item and period: Opening
    Balance, the vouchers with their Inwards / Outwards, the Bills
    Pending roll-up and the totals.
    """
    item_rows, all_rows = await _load_item_vouchers(
        stock_item_name, company_name
    )

    if not from_date or not to_date:
        default_from, default_to = default_period(item_rows)
        from_date = from_date or default_from
        to_date = to_date or default_to

    try:
        from app.tally.xml_builders.inventory import build_stock_vouchers_request
        from app.tally.parsers.inventory import parse_tally_vouchers_report
        from app.tally.parsers.inventory_summary import name_key, resolve_godown

        xml_request = build_stock_vouchers_request(
            stock_item_name=stock_item_name,
            from_date=from_date,
            to_date=to_date,
            company_name=company_name,
            godown_name=godown_name,
        )
        xml_response = await client.send_xml(xml_request)
        native_vouchers = parse_tally_vouchers_report(xml_response)
        if native_vouchers:
            master = await _load_item_master(
                stock_item_name, company_name, as_on=to_date
            )
            if from_date or to_date:
                f_str = from_date.isoformat() if from_date else ""
                t_str = to_date.isoformat() if to_date else "9999-12-31"
                filtered_vouchers = [
                    v for v in native_vouchers
                    if v.get("date") and f_str <= v["date"] <= t_str
                ]
            else:
                filtered_vouchers = native_vouchers

            # Voucher numbers are not part of Tally's report lines; take
            # them from the item's own voucher entries so a line can
            # open its voucher.
            used_indices = set()
            for v in filtered_vouchers:
                if v.get("kind") == "pending":
                    continue

                v_type = (v.get("voucher_type") or "").strip().casefold()

                candidates = [
                    idx for idx, r in enumerate(item_rows)
                    if idx not in used_indices
                    and r.get("date") == v.get("date")
                    and (r.get("voucher_type") or "").strip().casefold() == v_type
                ]

                # Several vouchers of one type on one day: take the one
                # whose quantity is the line's, so the line opens its
                # own voucher.
                line_quantity = abs(
                    v.get("inward_quantity") or v.get("outward_quantity") or 0.0
                )
                match = next(
                    (
                        idx for idx in candidates
                        if abs(item_rows[idx].get("quantity") or 0.0) == line_quantity
                    ),
                    candidates[0] if candidates else None,
                )

                if match is not None:
                    r = item_rows[match]
                    v["voucher_number"] = r.get("voucher_number", "")
                    v["guid"] = r.get("guid", "")
                    used_indices.add(match)

            opening_q = (master or {}).get("opening_quantity") or 0.0
            opening_v = (master or {}).get("opening_value") or 0.0

            scoped_rows = item_rows

            if godown_name:
                masters = await fetch_godowns(company_name=company_name)
                default_godown = pick_default_godown(masters.get("rows", []))
                known_godowns = {
                    name_key(g.get("name") or g.get("godown"))
                    for g in masters.get("rows", [])
                }
                def r_godown(value):
                    k = name_key(resolve_godown(value, default_godown))
                    return k if k in known_godowns else name_key(default_godown)
                alloc_res = await client.send_xml(
                    build_stock_summary_request(
                        company_name=company_name,
                        include_godown_allocations=True,
                    ),
                    timeout=STOCK_SUMMARY_TIMEOUT,
                )
                openings = [
                    a for a in parse_item_godown_openings(alloc_res)
                    if a["stock_item"].strip().casefold() == stock_item_name.strip().casefold()
                ]
                godown_openings = [
                    a for a in openings
                    if r_godown(a.get("godown")) == name_key(godown_name)
                ]
                if godown_openings:
                    opening_q = sum(a["quantity"] for a in godown_openings)
                    rate = (master or {}).get("opening_rate") or ((master or {}).get("closing_rate") or 0.0)
                    opening_v = opening_q * rate
                elif openings:
                    opening_q = 0.0
                    opening_v = 0.0

                scoped_rows = [
                    r for r in item_rows
                    if r_godown(r.get("godown")) == name_key(godown_name)
                ]

            # The Bills Pending line: Tally's own line is kept (quantity,
            # closing); what the report does not print - the value, and
            # the delivery / return notes behind the line with their
            # tracking numbers - is worked out from the voucher entries.
            pending_notes = {}

            try:
                derived = build_voucher_ledger(
                    scoped_rows,
                    all_rows=all_rows,
                    stock_item_name=stock_item_name,
                    opening_quantity=opening_q,
                    opening_value=opening_v,
                    from_date=from_date,
                    to_date=to_date,
                )

                for line in derived.get("rows", []):
                    if line.get("kind") == "pending":
                        pending_notes[line.get("pending_side")] = line
            except Exception as e:
                _log.warning("Could not derive Bills Pending detail: %r", e)

            # Tally's Stock / Godown Vouchers screen shows only the
            # "(Sale Bills Pending)" line; the purchase side is a toggle
            # (F5) that is off by default. The purchase notes are already
            # listed as ordinary voucher lines (Receipt Note, Rejections
            # Out), so adding a "(Purchase Bills Pending)" line would
            # count them twice in the totals.
            def _is_purchase_pending(v):
                return (
                    v.get("kind") == "pending"
                    and "purchase" in (v.get("particulars") or "").casefold()
                )

            filtered_vouchers = [
                v for v in filtered_vouchers if not _is_purchase_pending(v)
            ]

            native_pending = [v for v in filtered_vouchers if v.get("kind") == "pending"]

            for v in native_pending:
                v["pending_side"] = "sale"
                note = pending_notes.get("sale")

                if note:
                    v["children"] = note.get("children") or v.get("children") or []
                    if v.get("outward_value") is None:
                        v["outward_value"] = note.get("outward_value")
                        v["inward_value"] = note.get("inward_value")

            # No Sale Bills Pending line in Tally's report for the
            # period: add the one the delivery notes call for.
            if not native_pending and pending_notes.get("sale"):
                filtered_vouchers.append({**pending_notes["sale"], "derived": True})

            # The pending line closes on the balance of the line above
            # it, moved by the pending quantity. Tally carries the
            # closing value across unchanged.
            previous = None

            for v in filtered_vouchers:
                if v.get("kind") != "pending":
                    if v.get("closing_quantity") is not None:
                        previous = v
                    continue

                if previous is not None and (
                    v.get("derived") or v.get("closing_quantity") is None
                ):
                    v["closing_quantity"] = (
                        (previous.get("closing_quantity") or 0.0)
                        + (v.get("inward_quantity") or 0.0)
                        - (v.get("outward_quantity") or 0.0)
                    )
                    v["closing_value"] = previous.get("closing_value")

            # Tally prints no value on a Bills Pending line, but its totals
            # do include it (the returns booked against the delivery
            # notes make it negative).
            def _sum(key):
                return sum(v.get(key) or 0.0 for v in filtered_vouchers)

            # Tally's totals count the opening balance as Inwards.
            last_closing = next(
                (
                    v for v in reversed(filtered_vouchers)
                    if v.get("closing_quantity") is not None
                ),
                None,
            )

            return {
                "from": from_date.isoformat() if from_date else "",
                "to": to_date.isoformat() if to_date else "",
                "unit": (master or {}).get("base_units", ""),
                "item_found": bool(master or filtered_vouchers),
                "opening": {
                    "quantity": opening_q,
                    "value": opening_v,
                },
                "rows": filtered_vouchers,
                "totals": {
                    "inward_quantity": opening_q + _sum("inward_quantity"),
                    "inward_value": opening_v + _sum("inward_value"),
                    "outward_quantity": _sum("outward_quantity"),
                    "outward_value": _sum("outward_value"),
                    "closing_quantity": (
                        last_closing["closing_quantity"]
                        if last_closing
                        else (master or {}).get("closing_quantity")
                    ),
                    "closing_value": (
                        last_closing["closing_value"]
                        if last_closing
                        else (master or {}).get("closing_value")
                    ),
                },
            }
    except Exception as e:
        _log.warning("Native Stock Vouchers fetch failed, falling back: %r", e)

    master = await _load_item_master(
        stock_item_name, company_name, as_on=to_date
    )

    ledger = build_voucher_ledger(
        item_rows,
        all_rows=all_rows,
        stock_item_name=stock_item_name,
        opening_quantity=(master or {}).get("opening_quantity") or 0.0,
        opening_value=(master or {}).get("opening_value") or 0.0,
        from_date=from_date,
        to_date=to_date,
    )

    return {
        "from": from_date.isoformat(),
        "to": to_date.isoformat(),
        "unit": (master or {}).get("base_units", ""),
        "item_found": bool(master or item_rows),
        **ledger,
    }


async def fetch_godown_item_monthly(
    godown_name: str,
    stock_item_name: str,
    from_date: date | None,
    to_date: date | None,
    company_name: str | None = None,
):
    """
    Tally's "Godown Monthly Summary" for one item in one godown.
    Directly fetches Tally's native Item Monthly Summary report scoped
    to the given godown.
    """
    from app.tally.parsers.inventory_summary import (
        name_key,
        resolve_godown,
    )

    item_rows, _all_rows = await _load_item_vouchers(
        stock_item_name, company_name
    )

    if not from_date or not to_date:
        default_from, default_to = default_period(item_rows)
        from_date = from_date or default_from
        to_date = to_date or default_to

    try:
        from app.tally.xml_builders.inventory import build_item_monthly_summary_request
        from app.tally.parsers.inventory import parse_item_monthly_summary

        xml_request = build_item_monthly_summary_request(
            stock_item_name=stock_item_name,
            from_date=from_date,
            to_date=to_date,
            company_name=company_name,
            godown_name=godown_name,
        )
        xml_response = await client.send_xml(xml_request)
        start_year = (
            from_date.year
            if from_date
            else (date.today().year if date.today().month >= 4 else date.today().year - 1)
        )
        native_rows = parse_item_monthly_summary(xml_response, start_year=start_year)
        if native_rows:
            master = await _load_item_master(
                stock_item_name, company_name, as_on=to_date
            )
            opening_quantity = (master or {}).get("opening_quantity") or 0.0
            opening_value = (master or {}).get("opening_value") or 0.0

            if godown_name:
                masters = await fetch_godowns(company_name=company_name)
                default_godown = pick_default_godown(masters.get("rows", []))
                known_godowns = {
                    name_key(g.get("name") or g.get("godown"))
                    for g in masters.get("rows", [])
                }
                def r_godown(value):
                    k = name_key(resolve_godown(value, default_godown))
                    return k if k in known_godowns else name_key(default_godown)
                alloc_res = await client.send_xml(
                    build_stock_summary_request(
                        company_name=company_name,
                        include_godown_allocations=True,
                    ),
                    timeout=STOCK_SUMMARY_TIMEOUT,
                )
                openings = [
                    a for a in parse_item_godown_openings(alloc_res)
                    if a["stock_item"].strip().casefold() == stock_item_name.strip().casefold()
                ]
                godown_openings = [
                    a for a in openings
                    if r_godown(a.get("godown")) == name_key(godown_name)
                ]
                if godown_openings:
                    opening_quantity = sum(a["quantity"] for a in godown_openings)
                    rate = (master or {}).get("opening_rate") or ((master or {}).get("closing_rate") or 0.0)
                    opening_value = opening_quantity * rate
                elif openings:
                    opening_quantity = 0.0
                    opening_value = 0.0

            return {
                "from": from_date.isoformat() if from_date else f"{start_year}-04-01",
                "to": to_date.isoformat() if to_date else f"{start_year + 1}-03-31",
                "godown": godown_name,
                "unit": (master or {}).get("base_units", ""),
                "item_found": bool(master or native_rows),
                "approximate": False,
                "opening": {
                    "quantity": opening_quantity,
                    "value": opening_value,
                },
                "rows": native_rows,
            }
    except Exception as e:
        _log.warning("Native Godown Monthly Summary fetch failed, falling back: %r", e)

    base = await fetch_stock_item_monthly(
        stock_item_name=stock_item_name,
        from_date=from_date,
        to_date=to_date,
        company_name=company_name,
    )

    masters = await fetch_godowns(company_name=company_name)
    default_godown = pick_default_godown(masters.get("rows", []))
    target = name_key(godown_name)

    known_godowns = {
        name_key(g.get("name") or g.get("godown"))
        for g in masters.get("rows", [])
    }

    def row_godown(value):
        """Godown of a voucher line; anything that is not a real godown
        master (blank, Not Applicable, a batch label ...) sits in the
        company's default location, as in Tally."""
        key = name_key(resolve_godown(value, default_godown))
        return key if key in known_godowns else name_key(default_godown)

    response = await client.send_xml(
        build_stock_summary_request(
            company_name=company_name,
            include_godown_allocations=True,
        ),
        timeout=STOCK_SUMMARY_TIMEOUT,
    )

    openings = [
        a for a in parse_item_godown_openings(response)
        if a["stock_item"].strip().casefold() == stock_item_name.strip().casefold()
    ]

    history = await fetch_stock_movement(
        company_name=company_name,
        stock_item_name=stock_item_name,
    )

    stock_rows = [
        r for r in history.get("rows", [])
        if movement_effect(r) is not None
    ]

    touched = {
        row_godown(a.get("godown"))
        for a in openings
        if a.get("quantity")
    } | {
        row_godown(r.get("godown"))
        for r in stock_rows
    }

    zero = {
        "inward_quantity": 0.0,
        "inward_value": 0.0,
        "outward_quantity": 0.0,
        "outward_value": 0.0,
        "pending_bills_quantity": 0.0,
        "closing_quantity": 0.0,
        "closing_value": 0.0,
    }

    if len(touched) <= 1:
        only = next(iter(touched), name_key(default_godown))

        if only == target:
            return {**base, "godown": godown_name, "approximate": False}

        return {
            **base,
            "godown": godown_name,
            "approximate": False,
            "opening": {"quantity": 0.0, "value": 0.0},
            "rows": [{**row, **zero} for row in base["rows"]],
        }

    def in_godown(row):
        return row_godown(row.get("godown")) == target

    # Same engine as the Stock Item Monthly Summary, fed only with this
    # godown's openings and vouchers, so Bills Pending, returns and the
    # average-cost closing behave exactly as they do for the item.
    opening_quantity = sum(
        a["quantity"] for a in openings
        if row_godown(a.get("godown")) == target
    )
    item_opening = base["opening"]
    opening_rate = (
        item_opening["value"] / item_opening["quantity"]
        if item_opening["quantity"]
        else 0.0
    )

    summary = build_monthly_summary(
        [r for r in history.get("rows", []) if in_godown(r)],
        opening_quantity=opening_quantity,
        opening_value=opening_quantity * opening_rate,
        from_date=date.fromisoformat(base["from"]),
        to_date=date.fromisoformat(base["to"]),
    )

    return {
        **base,
        "godown": godown_name,
        "approximate": True,
        "opening": summary["opening"],
        "rows": summary["rows"],
    }


# ============================================================
# STOCK GROUP ITEMS
# ============================================================

async def fetch_stock_group_items(
    group_name: str,
    company_name: str | None = None,
    to_date: date | None = None,
    from_date: date | None = None,
):
    """
    Items sitting directly in one stock group. Kept for the existing
    /stock-group-items endpoint; it now goes through the same
    Primary-aware summary as the Stock Group Summary screen.
    """
    summary = await fetch_stock_group_summary(
        group_name=group_name,
        company_name=company_name,
        from_date=from_date,
        to_date=to_date,
        include_zero=True,
    )

    if summary is None:
        return {"success": True, "rows": [], "count": 0}

    items = [
        {
            "name": r["name"],
            "parent": r.get("stock_group") or r["parent"],
            "base_units": r.get("unit"),
            "opening_quantity": r.get("opening_quantity"),
            "opening_value": r.get("opening_value"),
            "closing_quantity": r.get("closing_quantity"),
            "closing_rate": r.get("closing_rate"),
            "closing_value": r.get("closing_value"),
        }
        for r in summary["rows"]
        if r["kind"] == "item"
    ]

    return {"success": True, "rows": items, "count": len(items)}


# ============================================================
# STOCK GROUP / CATEGORY / GODOWN SUMMARIES
# ============================================================
#
# Each of these is Tally's "<X> Summary" screen for one node of the
# Primary-rooted tree. They return None when the requested node does
# not exist (the API turns that into a 404) and an empty row list when
# the node exists but holds no stock.

async def fetch_stock_group_summary(
    group_name: str | None = None,
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    include_zero: bool = False,
):
    masters = await fetch_stock_groups(company_name=company_name)
    items = await fetch_stock_summary(
        company_name=company_name,
        from_date=from_date,
        to_date=to_date,
    )

    return build_hierarchy_summary(
        selected=group_name,
        masters=masters.get("rows", []),
        name_field="name",
        leaf_rows=_items_as_leaf_rows(items.get("rows", [])),
        node_field="stock_group",
        na_is_root=False,
        include_zero=include_zero,
        kind_label="group",
    )


async def fetch_stock_category_summary(
    category_name: str | None = None,
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    include_zero: bool = False,
):
    masters = await fetch_stock_categories(company_name=company_name)
    items = await fetch_stock_summary(
        company_name=company_name,
        from_date=from_date,
        to_date=to_date,
    )

    return build_hierarchy_summary(
        selected=category_name,
        masters=masters.get("rows", []),
        name_field="name",
        leaf_rows=_items_as_leaf_rows(items.get("rows", [])),
        node_field="category",
        na_is_root=True,
        include_zero=include_zero,
        kind_label="category",
    )


async def fetch_godown_summary(
    godown_name: str | None = None,
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    include_zero: bool = False,
):
    masters = await fetch_godowns(company_name=company_name)

    response = await client.send_xml(
        build_stock_summary_request(
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
            include_godown_allocations=True,
        ),
        timeout=STOCK_SUMMARY_TIMEOUT,
    )

    items = parse_stock_summary(response)
    openings = parse_item_godown_openings(response)

    movement = await fetch_stock_movement(
        company_name=company_name,
        from_date=from_date,
        to_date=to_date,
    )

    balances = build_godown_balances(
        items=items.get("rows", []),
        godown_masters=masters.get("rows", []),
        opening_allocations=openings,
        movement_rows=movement.get("rows", []),
    )

    return build_hierarchy_summary(
        selected=godown_name,
        masters=masters.get("rows", []),
        name_field="name",
        leaf_rows=balances,
        node_field="godown",
        na_is_root=True,
        include_zero=include_zero,
        kind_label="godown",
    )


def _items_as_leaf_rows(rows: list[dict]) -> list[dict]:
    """Stock Summary rows in the shape build_hierarchy_summary reads."""
    return [
        {
            "stock_item": r.get("name"),
            "stock_group": r.get("parent"),
            "category": r.get("category"),
            "unit": r.get("base_units"),
            "opening_quantity": r.get("opening_quantity"),
            "opening_value": r.get("opening_value"),
            "closing_quantity": r.get("closing_quantity"),
            "closing_rate": r.get("closing_rate"),
            "closing_value": r.get("closing_value"),
        }
        for r in rows
    ]


# ============================================================
# INVENTORY BOOKS / REGISTERS
# ============================================================

async def fetch_inventory_register(
    voucher_type: str,
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
):
    response = await client.send_xml(
        build_inventory_register_request(
            voucher_type=voucher_type,
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
        )
    )

    return parse_inventory_register_summary(
        response
    )


async def fetch_register_vouchers(
    voucher_type: str,
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
):
    """All vouchers of one type within the period (period applied here)."""
    response = await client.send_xml(
        build_register_vouchers_request(
            voucher_type=voucher_type,
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
        )
    )

    return clip_vouchers(parse_register_vouchers(response), from_date, to_date)


async def fetch_register_months(
    voucher_type: str,
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
):
    """
    Register screen (month-wise voucher counts). Without a period the
    latest financial year with stock activity is used, so a register
    that is empty today still shows the year the company works in.
    """
    if not from_date or not to_date:
        default_from, default_to = await resolve_stock_period(
            company_name=company_name
        )
        from_date = from_date or default_from
        to_date = to_date or default_to

    vouchers = await fetch_register_vouchers(
        voucher_type=voucher_type,
        company_name=company_name,
        from_date=from_date,
        to_date=to_date,
    )

    return {
        "from": from_date.isoformat(),
        "to": to_date.isoformat(),
        **build_register_months(vouchers, from_date, to_date),
    }


async def fetch_register_voucher_list(
    register_key: str,
    voucher_type: str,
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
):
    """"List of All <X> Vouchers" for one register and period."""
    vouchers = await fetch_register_vouchers(
        voucher_type=voucher_type,
        company_name=company_name,
        from_date=from_date,
        to_date=to_date,
    )

    return build_voucher_register(register_key, vouchers)


# ============================================================
# STOCK VALUATION
# ============================================================

async def fetch_stock_valuation(
    company_name: str | None = None,
    to_date: date | None = None,
):
    response = await client.send_xml(
        build_stock_summary_request(
            company_name=company_name,
            to_date=to_date,
        ),
        timeout=STOCK_SUMMARY_TIMEOUT,
    )

    return parse_stock_valuation(response)


# ============================================================
# NEGATIVE STOCK
# ============================================================

async def fetch_negative_stock(
    company_name: str | None = None,
    to_date: date | None = None,
):
    response = await client.send_xml(
        build_stock_summary_request(
            company_name=company_name,
            to_date=to_date,
        ),
        timeout=STOCK_SUMMARY_TIMEOUT,
    )

    return parse_negative_stock(response)


# ============================================================
# STOCK ITEM LIST
# ============================================================

async def fetch_stock_item_list(
    company_name: str | None = None,
) -> list[dict]:
    """
    Fetch stock item details from Tally and return them
    as a clean Python list.
    """

    # Build the XML request for inventory items.
    xml_request = build_stock_item_list_request(
        company_name=company_name
    )

    # Use the same Tally client used by the other service functions.
    response = await client.send_xml(
        xml_request
    )

    # Convert the XML response into Python dictionaries.
    return parse_stock_item_list(response)