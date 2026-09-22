from datetime import date, datetime

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

from app.tally.parsers.ledger import (
    _parse_custom_voucher_ledger_rows,
)


client = TallyClient()


# ============================================================
# COMPANIES
# ============================================================

async def fetch_companies():
    response = await client.send_xml(
        build_company_request()
    )

    return parse_companies(response)


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

    return parse_group_summary(response, group_name=group_name)


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

    # parse_bill_allocations() returns {"success": ..., "rows": [...],
    # "count": ...} - same wrapper shape as parse_ledger_list(). Every
    # caller (build_outstanding_summary, dashboard summary) expects a
    # plain list of bill dicts, so unwrap it here once - matching the
    # fetch_ledger_list() fix above. Returning the wrapper dict as-is
    # made callers iterate over its keys ("success", "rows", "count")
    # as if they were bill dicts, causing
    # AttributeError("'str' object has no attribute 'get'").
    return parse_bill_allocations(response).get("rows", [])


# ============================================================
# RECEIVABLES
# ============================================================

async def fetch_bills_receivable(
    company_name: str | None = None,
):
    response = await client.send_xml(
        build_bills_receivable_request(
            company_name=company_name,
        )
    )

    # Same wrapper-dict unwrap as fetch_bill_allocations() above -
    # callers expect a plain list of bill dicts, not the
    # {"success", "rows", "count"} wrapper.
    return parse_outstanding_report(
        response,
        report_type="receivable",
    ).get("rows", [])


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

    # Same wrapper-dict unwrap as fetch_bill_allocations() above.
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

    # parse_ledger_list() returns {"success": ..., "ledgers": [...],
    # "count": ...} - every caller (the /ledgers endpoint, the Group
    # Summary ledger/group check, the chatbot tool) expects a plain
    # list of ledger dicts, so unwrap it here once instead of
    # returning the whole wrapper (which was silently making the
    # ledger dropdown empty and the Group Summary ledger check
    # throw/fall back to "treat everything as a group").
    return parse_ledger_list(response).get("ledgers", [])


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

    1. Fetch this one ledger's master info (opening/closing
       balance) via a targeted, filtered collection - NOT the
       full company Ledger List, which is a much heavier query
       and was causing repeated ReadTimeouts.
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
    # 1. Get THIS ledger's master information (opening/closing
    #    balance) - a lightweight, filtered request instead of
    #    pulling every ledger in the company.
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
                matched_ledgers[0].get("opening_balance", 0) or 0
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

        print("\n========== LEDGER NATIVE REQUEST ==========")
        print(request_xml)
        print("========== END LEDGER NATIVE REQUEST ==========\n")

        response = await client.send_xml(
            request_xml
        )

        print("\n========== LEDGER NATIVE RESPONSE ==========")
        print(response)
        print("========== END LEDGER NATIVE RESPONSE ==========\n")

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
            []
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

        # IMPORTANT:
        # Pass the actual XML response to the parser.
        # Never pass None here.
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

            # Keep date consistently formatted.
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
        #
        # Only actual Tally debit/credit rows are used.
        # No transactions are fabricated.
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
        #
        # Continuous month-by-month buckets (carrying the closing
        # balance forward through months with zero transactions),
        # matching Tally's own "Ledger Monthly Summary" screen.
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
            "from_date": from_date.isoformat() if from_date else None,
            "to_date": to_date.isoformat() if to_date else None,
        }

        print("\n==============================================")
        print("       LEDGER FALLBACK SUCCESS")
        print("==============================================")
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
        print("==============================================\n")

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
# VOUCHER DETAIL - single accounting voucher, all ledger lines
# ============================================================

async def fetch_voucher_detail(
    voucher_type: str,
    voucher_number: str,
    voucher_date: date | None = None,
    company_name: str | None = None,
):
    """
    Fetch one accounting voucher with every ledger line inside it -
    the same data Tally's "Accounting Voucher Alteration" screen
    shows when you drill into a single transaction from a ledger
    report row.
    """

    request_xml = build_voucher_detail_request(
        voucher_type=voucher_type,
        voucher_number=voucher_number,
        voucher_date=voucher_date,
        company_name=company_name,
    )

    print("\n========== VOUCHER DETAIL REQUEST ==========")
    print(request_xml)
    print("========== END VOUCHER DETAIL REQUEST ==========\n")

    response = await client.send_xml(request_xml)

    print("\n========== VOUCHER DETAIL RESPONSE ==========")
    print(response)
    print("========== END VOUCHER DETAIL RESPONSE ==========\n")

    vouchers = parse_voucher_detail(
        response,
        voucher_type=voucher_type,
        voucher_number=voucher_number,
        voucher_date=(
            voucher_date.isoformat() if voucher_date else None
        ),
    )

    if vouchers:
        return vouchers

    # ----------------------------------------------------------
    # Fallback: some Tally versions won't restrict a Collection by
    # SVFROMDATE/SVTODATE the same way a native report does, or the
    # requested date didn't line up exactly (e.g. post-dated /
    # optional vouchers). Retry once without the date restriction so
    # the type + number formula filter alone finds it.
    # ----------------------------------------------------------

    if voucher_date is not None:
        request_xml = build_voucher_detail_request(
            voucher_type=voucher_type,
            voucher_number=voucher_number,
            voucher_date=None,
            company_name=company_name,
        )

        response = await client.send_xml(request_xml)

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
):
    response = await client.send_xml(
        build_stock_movement_request(
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
            stock_item_name=stock_item_name,
        )
    )

    return parse_stock_movement(response)


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

    # Convert the XML response into Python dictionaries
    # so other parts of the application can use the stock data easily.
    return parse_stock_item_list(response)
