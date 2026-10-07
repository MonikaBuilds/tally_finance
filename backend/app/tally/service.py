import re
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
)
from app.tally.parsers.inventory import (
    filter_stock_movement_by_godown,
)
from app.tally.parsers.financial import (
    parse_balance_sheet_report,
)
from app.tally.parsers.ledger import (
    _parse_custom_voucher_ledger_rows,
)


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
        report_name="companies",
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
    Fetch one accounting voucher with every ledger line inside it.
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
# STOCK SUMMARY
# ============================================================

async def fetch_stock_summary(
    company_name: str | None = None,
    to_date: date | None = None,
):
    response = await client.send_xml(
        build_stock_summary_request(
            company_name=company_name,
            to_date=to_date,
        )
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

    print(
        "\n========== TALLY RAW STOCK GROUP XML =========="
    )
    print(response)
    print(
        "========== END TALLY RAW STOCK GROUP XML ==========\n"
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
    if godown_name:
        rows = filter_stock_movement_by_godown(
            result.get("rows", []),
            godown_name,
        )

        result = {
            "success": True,
            "rows": rows,
            "count": len(rows),
        }

    return result


# ============================================================
# STOCK GROUP ITEMS
# ============================================================

async def fetch_stock_group_items(
    group_name: str,
    company_name: str | None = None,
    to_date: date | None = None,
):
    response = await client.send_xml(
        build_stock_group_items_request(
            group_name=group_name,
            company_name=company_name,
            to_date=to_date,
        )
    )

    return parse_stock_summary(response)


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
        )
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
        )
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