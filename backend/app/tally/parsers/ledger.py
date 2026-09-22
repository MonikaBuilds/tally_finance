"""
Ledger and voucher parsers for Tally XML responses.

This module contains parsing logic related to:
- Ledger master information
- Ledger transactions
- Voucher details
- Cost centre allocations
- Ledger row merging
- Ledger monthly summary
- Ledger reports

Important:
This file currently preserves the behaviour of the original parser.py.
The purpose of this step is only to separate the large parser into
smaller modules.

Financial calculation behaviour inside the old ledger parser is not
being changed during this refactor.
"""

from datetime import date, datetime

from app.tally.parsers.common import (
    parse_xml,
    to_float,
    to_optional_float,
    _text,
    _first_text,
    format_tally_date,
)


# ============================================================
# LEDGER MASTER LIST
# ============================================================

def parse_ledger_list(xml_response: str) -> dict:
    """
    Parse ledger master information returned by Tally.

    This is useful for finding:
    - ledger name
    - parent group
    - opening balance
    - closing balance
    - GUID

    Missing balances remain None instead of being converted to zero.
    """

    root = parse_xml(xml_response)

    ledgers = []
    seen = set()

    for ledger in root.findall(".//LEDGER"):

        # Tally may provide the ledger name as either an XML
        # attribute or a child NAME element.
        name = (
            ledger.get("NAME")
            or ledger.findtext("NAME")
            or ""
        ).strip()

        if not name:
            continue

        # Avoid returning the same ledger more than once.
        key = name.casefold()

        if key in seen:
            continue

        seen.add(key)

        # Depending on the Tally response, the parent group can be
        # available under either of these fields.
        parent = (
            ledger.findtext("CHATPARENTGROUP")
            or ledger.findtext("PARENT")
            or ""
        ).strip()

        opening_balance = to_optional_float(
            ledger.findtext("OPENINGBALANCE")
        )

        closing_balance = to_optional_float(
            ledger.findtext("CLOSINGBALANCE")
        )

        ledgers.append(
            {
                "name": name,
                "parent": parent,

                # Keep missing Tally values as None.
                "opening_balance": (
                    round(opening_balance, 2)
                    if opening_balance is not None
                    else None
                ),

                "closing_balance": (
                    round(closing_balance, 2)
                    if closing_balance is not None
                    else None
                ),

                "guid": (
                    ledger.findtext("GUID")
                    or ""
                ).strip(),
            }
        )

    return {
        "success": True,
        "ledgers": ledgers,
        "count": len(ledgers),
    }


# ============================================================
# LEDGER / VOUCHER HELPERS
# ============================================================

def _same_ledger_name(
    value: str,
    target: str,
) -> bool:
    """
    Compare two ledger names without being affected by
    capitalization or extra spaces.
    """

    return (
        str(value or "").strip().casefold()
        == str(target or "").strip().casefold()
    )


def _ledger_entry_nodes(voucher):
    """
    Return all ledger-entry nodes inside a voucher.

    Different Tally exports may use either:
        ALLLEDGERENTRIES.LIST
        LEDGERENTRIES.LIST

    Both direct and nested forms are checked.
    """

    result = []
    seen = set()

    paths = [
        "./ALLLEDGERENTRIES.LIST",
        "./LEDGERENTRIES.LIST",
        ".//ALLLEDGERENTRIES.LIST",
        ".//LEDGERENTRIES.LIST",
    ]

    for path in paths:

        for node in voucher.findall(path):

            object_id = id(node)

            if object_id in seen:
                continue

            seen.add(object_id)
            result.append(node)

    return result


def _inventory_entry_nodes(voucher):
    """
    Return inventory-entry nodes from a voucher.

    This helper is also useful for inventory reports because
    stock information can be embedded inside accounting vouchers.
    """

    result = []
    seen = set()

    paths = [
        "./ALLINVENTORYENTRIES.LIST",
        "./INVENTORYENTRIES.LIST",
        ".//ALLINVENTORYENTRIES.LIST",
        ".//INVENTORYENTRIES.LIST",
    ]

    for path in paths:

        for node in voucher.findall(path):

            object_id = id(node)

            if object_id in seen:
                continue

            seen.add(object_id)
            result.append(node)

    return result


# ============================================================
# COST CENTRE ALLOCATIONS
# ============================================================

def _cost_centre_allocations(ledger_entry):
    """
    Extract cost-centre allocations attached to a ledger entry.

    Tally normally places these under:
        CATEGORYALLOCATIONS.LIST
            -> COSTCENTREALLOCATIONS.LIST
    """

    allocations = []

    for category in ledger_entry.findall(
        ".//CATEGORYALLOCATIONS.LIST"
    ):

        category_name = category.findtext(
            "CATEGORY",
            "",
        ).strip()

        for allocation in category.findall(
            ".//COSTCENTREALLOCATIONS.LIST"
        ):

            cost_centre_name = allocation.findtext(
                "NAME",
                "",
            ).strip()

            if not cost_centre_name:
                continue

            amount = to_float(
                allocation.findtext("AMOUNT")
            )

            allocations.append(
                {
                    "cost_centre_name": cost_centre_name,
                    "category_name": category_name,
                    "amount": round(amount, 2),
                }
            )

    return allocations


def _parse_signed_tally_amount(
    amount_text: str,
    is_deemed_positive: str | None = None,
):
    """
    Convert the existing Tally voucher amount representation into
    the debit/credit structure expected by the application.

    This is existing parser behaviour and is intentionally preserved
    during the modularization.
    """

    amount = abs(
        to_float(amount_text)
    )

    deemed = str(
        is_deemed_positive or ""
    ).strip().casefold()

    if deemed in {
        "yes",
        "y",
        "true",
        "1",
    }:
        return amount, 0.0

    return 0.0, amount


def _ledger_entry_particular(
    voucher,
    target_ledger,
):
    """
    Find a useful 'particulars' value for a ledger transaction.

    Existing priority:
    1. Party ledger
    2. Another ledger in the voucher
    3. Stock item
    4. Voucher type
    """

    party = _first_text(
        voucher,
        "PARTYLEDGERNAME",
        "PARTYNAME",
    )

    if (
        party
        and not _same_ledger_name(
            party,
            target_ledger,
        )
    ):
        return party

    # If party is not useful, look for another ledger entry.
    for entry in _ledger_entry_nodes(voucher):

        name = _first_text(
            entry,
            "LEDGERNAME",
            "LEDGER",
        )

        if (
            name
            and not _same_ledger_name(
                name,
                target_ledger,
            )
        ):
            return name

    # Inventory vouchers may provide a stock item instead.
    for entry in _inventory_entry_nodes(voucher):

        item_name = _first_text(
            entry,
            "STOCKITEMNAME",
            "STOCKITEM",
        )

        if item_name:
            return item_name

    return _first_text(
        voucher,
        "VOUCHERTYPENAME",
        default="",
    )


# ============================================================
# NATIVE LEDGER REPORT ROW
# ============================================================

def _ledger_report_row_from_node(
    node,
    target_ledger="",
):
    """
    Parse one row from Tally's native ledger report structure.
    """

    date_value = _first_text(
        node,
        "DSPVCHDATE",
        "DATE",
    )

    voucher_type = _first_text(
        node,
        "DSPVCHTYPE",
        "VOUCHERTYPENAME",
    )

    voucher_number = _first_text(
        node,
        "DSPVCHNO",
        "VOUCHERNUMBER",
    )

    particulars = _first_text(
        node,
        "DSPPARTY",
        "DSPLEDGERNAME",
        "LEDGERNAME",
        "DSPDISPNAME",
    )

    narration = _first_text(
        node,
        "DSPNARRATION",
        "NARRATION",
    )

    debit_text = _first_text(
        node,
        "DSPDEBIT",
        "DEBIT",
    )

    credit_text = _first_text(
        node,
        "DSPCREDIT",
        "CREDIT",
    )

    running_text = _first_text(
        node,
        "DSPCLAMT",
        "DSPRUNBAL",
        "RUNNINGBALANCE",
        "BALANCE",
    )

    diff_tax_text = _first_text(
        node,
        "DSPDIFFTAXAMT",
        "DIFFTAXAMOUNT",
    )

    balance_after_text = _first_text(
        node,
        "DSPBALAFTERDIFFTAX",
        "BALANCEAFTERDIFFTAX",
    )

    status = _first_text(
        node,
        "DSPSTATUS",
        "STATUS",
    )

    reference = _first_text(
        node,
        "DSPREFERENCE",
        "REFERENCE",
    )

    debit = to_float(debit_text)
    credit = to_float(credit_text)

    return {
        "date": format_tally_date(date_value),
        "particulars": particulars or target_ledger,
        "voucher_type": voucher_type,
        "voucher_number": voucher_number,
        "reference_number": reference,
        "debit": debit,
        "credit": credit,

        "running_balance": (
            to_float(running_text)
            if running_text
            else None
        ),

        "diff_in_tax_amount": (
            to_float(diff_tax_text)
            if diff_tax_text
            else 0.0
        ),

        "balance_after_diff_in_tax": (
            to_float(balance_after_text)
            if balance_after_text
            else None
        ),

        "status": status,
        "narration": narration,
    }


def _parse_native_ledger_rows(
    root,
    target_ledger,
):
    """
    Parse ledger rows when Tally returns its native LEDINFO structure.
    """

    rows = []

    # Preferred native ledger structure.
    for node in root.findall(".//LEDINFO"):

        row = _ledger_report_row_from_node(
            node,
            target_ledger,
        )

        if row["date"]:
            rows.append(row)

    # Some Tally responses expose DSPVCHDATE blocks without LEDINFO.
    # Keep the existing fallback behaviour.
    if not rows:

        for node in root.findall(
            ".//DSPVCHDATE"
        ):

            row = _ledger_report_row_from_node(
                node,
                target_ledger,
            )

            if row["date"]:
                rows.append(row)

    return rows


# ============================================================
# CUSTOM VOUCHER LEDGER PARSER
# ============================================================

# These voucher types are treated by the existing application as
# non-accounting / inventory-oriented vouchers. Keep this list exactly
# with the ledger parser so the current behaviour does not change.
NON_ACCOUNTING_VOUCHER_TYPES = {
    "sales order",
    "purchase order",
    "delivery note",
    "receipt note",
    "rejections in",
    "rejections out",
    "stock journal",
    "physical stock",
    "material out",
    "material in",
}


def parse_ledger_voucher_details(
    root,
    target_ledger,
):
    """
    Parse regular VOUCHER XML and return rows belonging to one ledger.

    The function preserves the existing application's debit/credit,
    stock-item and cost-centre structure.
    """

    rows = []

    for voucher in root.findall(
        ".//VOUCHER"
    ):

        voucher_type_check = _text(
            voucher,
            "VOUCHERTYPENAME",
        )

        if (
            (voucher_type_check or "")
            .strip()
            .casefold()
            in NON_ACCOUNTING_VOUCHER_TYPES
        ):
            continue

        voucher_date = format_tally_date(
            _text(
                voucher,
                "DATE",
            )
        )

        if not voucher_date:
            continue

        entries = _ledger_entry_nodes(
            voucher
        )

        target_entries = []

        # A voucher can contain many ledger entries.
        # Keep only entries belonging to the requested ledger.
        for entry in entries:

            ledger_name = _first_text(
                entry,
                "LEDGERNAME",
                "LEDGER",
            )

            if _same_ledger_name(
                ledger_name,
                target_ledger,
            ):
                target_entries.append(
                    entry
                )

        if not target_entries:
            continue

        voucher_type = _text(
            voucher,
            "VOUCHERTYPENAME",
        )

        voucher_number = _text(
            voucher,
            "VOUCHERNUMBER",
        )

        reference = _first_text(
            voucher,
            "REFERENCE",
            "REFERENCEDATE",
        )

        narration = _text(
            voucher,
            "NARRATION",
        )

        particulars = _ledger_entry_particular(
            voucher,
            target_ledger,
        )

        # Keep party information separately because other parts
        # of the application use it for party analysis.
        party_name = _first_text(
            voucher,
            "PARTYLEDGERNAME",
            "PARTYNAME",
        )

        # ----------------------------------------------------
        # STOCK DETAILS ATTACHED TO THE VOUCHER
        # ----------------------------------------------------

        stock_items = []

        for inventory_node in _inventory_entry_nodes(
            voucher
        ):

            stock_name = inventory_node.findtext(
                "STOCKITEMNAME",
                "",
            ).strip()

            if not stock_name:
                continue

            stock_items.append(
                {
                    "stock_item_name": stock_name,

                    "actual_quantity": inventory_node.findtext(
                        "ACTUALQTY",
                        "",
                    ).strip(),

                    "billed_quantity": inventory_node.findtext(
                        "BILLEDQTY",
                        "",
                    ).strip(),

                    "rate": inventory_node.findtext(
                        "RATE",
                        "",
                    ).strip(),

                    "amount": round(
                        to_float(
                            inventory_node.findtext(
                                "AMOUNT"
                            )
                        ),
                        2,
                    ),
                }
            )

        # One voucher may contain more than one entry for the
        # requested ledger, so process each matching entry.
        for entry in target_entries:

            amount_text = _first_text(
                entry,
                "AMOUNT",
            )

            deemed = _first_text(
                entry,
                "ISDEEMEDPOSITIVE",
            )

            debit, credit = _parse_signed_tally_amount(
                amount_text,
                deemed,
            )

            rows.append(
                {
                    "date": voucher_date,
                    "particulars": particulars,
                    "voucher_type": voucher_type,
                    "voucher_number": voucher_number,
                    "reference_number": reference,

                    # Preserve the actual numeric amount parsed from
                    # the AMOUNT field in the Tally response.
                    "tally_amount": round(
                        to_float(amount_text),
                        2,
                    ),

                    "debit": debit,
                    "credit": credit,

                    # These values are not available in this custom
                    # voucher path, so preserve the original defaults.
                    "running_balance": None,
                    "diff_in_tax_amount": 0.0,
                    "balance_after_diff_in_tax": None,
                    "status": "",

                    "narration": narration,
                    "party_name": party_name,
                    "stock_items": stock_items,

                    "cost_centre_allocations": (
                        _cost_centre_allocations(
                            entry
                        )
                    ),
                }
            )

    return rows


def _parse_custom_voucher_ledger_rows(
    xml_text: str,
    target_ledger,
):
    """
    Convenience entry point when the caller has raw XML instead
    of an already parsed ElementTree.
    """

    root = parse_xml(
        xml_text
    )

    return parse_ledger_voucher_details(
        root,
        target_ledger,
    )


# ============================================================
# VOUCHER DETAIL
# ============================================================

def parse_voucher_detail(
    xml_text: str,
    voucher_type: str,
    voucher_number: str,
    voucher_date: str | None = None,
):
    """
    Parse one accounting voucher and return all of its ledger lines.

    The voucher is matched using:
    - voucher type
    - voucher number
    - optionally voucher date

    The date check is useful because voucher numbers may repeat
    across different periods.
    """

    root = parse_xml(
        xml_text
    )

    vouchers = []

    for voucher in root.findall(
        ".//VOUCHER"
    ):

        current_type = _text(
            voucher,
            "VOUCHERTYPENAME",
        )

        current_number = _text(
            voucher,
            "VOUCHERNUMBER",
        )

        if not _same_ledger_name(
            current_type,
            voucher_type,
        ):
            continue

        if (
            str(current_number or "").strip()
            != str(voucher_number or "").strip()
        ):
            continue

        current_date = format_tally_date(
            _text(
                voucher,
                "DATE",
            )
        )

        if (
            voucher_date
            and current_date
            and current_date != voucher_date
        ):
            continue

        is_deleted = _text(
            voucher,
            "ISDELETED",
        )

        is_cancelled = _text(
            voucher,
            "ISCANCELLED",
        )

        reference = _first_text(
            voucher,
            "REFERENCE",
        )

        reference_date = format_tally_date(
            _first_text(
                voucher,
                "REFERENCEDATE",
            )
        )

        narration = _text(
            voucher,
            "NARRATION",
        )

        party_name = _first_text(
            voucher,
            "PARTYLEDGERNAME",
            "PARTYNAME",
        )

        entries = []

        for entry in _ledger_entry_nodes(
            voucher
        ):

            ledger_name = _first_text(
                entry,
                "LEDGERNAME",
                "LEDGER",
            )

            if not ledger_name:
                continue

            amount_text = _first_text(
                entry,
                "AMOUNT",
            )

            deemed = _first_text(
                entry,
                "ISDEEMEDPOSITIVE",
            )

            debit, credit = _parse_signed_tally_amount(
                amount_text,
                deemed,
            )

            entries.append(
                {
                    "ledger_name": ledger_name,
                    "debit": debit,
                    "credit": credit,

                    # Preserve the existing application's signed
                    # representation for voucher detail rows.
                    "amount": (
                        debit
                        if debit
                        else -credit
                    ),

                    "is_party_ledger": _same_ledger_name(
                        ledger_name,
                        party_name,
                    ),
                }
            )

        total_debit = sum(
            entry["debit"]
            for entry in entries
        )

        total_credit = sum(
            entry["credit"]
            for entry in entries
        )

        vouchers.append(
            {
                "date": current_date,
                "voucher_type": current_type,
                "voucher_number": current_number,
                "reference_number": reference,
                "reference_date": reference_date,
                "narration": narration,
                "party_name": party_name,

                "is_deleted": (
                    str(is_deleted or "")
                    .strip()
                    .lower()
                    in {
                        "yes",
                        "1",
                        "true",
                    }
                ),

                "is_cancelled": (
                    str(is_cancelled or "")
                    .strip()
                    .lower()
                    in {
                        "yes",
                        "1",
                        "true",
                    }
                ),

                "entries": entries,
                "total_debit": total_debit,
                "total_credit": total_credit,
            }
        )

    return vouchers


# ============================================================
# LEDGER ROW MERGING
# ============================================================

def _ledger_row_key(row):
    """
    Build a stable key used to detect duplicate ledger rows.
    """

    return (
        row.get("date"),
        row.get("particulars"),
        row.get("voucher_type"),
        row.get("voucher_number"),
        round(
            float(
                row.get("debit", 0)
                or 0
            ),
            2,
        ),
        round(
            float(
                row.get("credit", 0)
                or 0
            ),
            2,
        ),
        row.get("reference_number"),
        row.get("narration"),
    )


def merge_ledger_rows(
    native_rows,
    custom_rows,
):
    """
    Merge native and custom ledger rows while avoiding duplicate
    transactions.
    """

    merged = []
    seen = set()

    for row in (
        list(native_rows)
        + list(custom_rows)
    ):

        key = _ledger_row_key(
            row
        )

        if key in seen:
            continue

        seen.add(key)
        merged.append(row)

    return merged


# ============================================================
# MONTH / DATE HELPERS
# ============================================================

def _financial_year_start(value):
    """
    Return the April 1 start date for the financial year containing
    the supplied date.

    This helper is preserved from the original parser.
    """

    return datetime(
        (
            value.year
            if value.month >= 4
            else value.year - 1
        ),
        4,
        1,
    ).date()


def _first_of_month(
    value: date,
) -> date:
    """Return the first day of the supplied month."""

    return date(
        value.year,
        value.month,
        1,
    )


def _next_month(
    value: date,
) -> date:
    """Return the first day of the next month."""

    if value.month == 12:
        return date(
            value.year + 1,
            1,
            1,
        )

    return date(
        value.year,
        value.month + 1,
        1,
    )


# ============================================================
# MONTHLY LEDGER SUMMARY
# ============================================================

def build_continuous_monthly_summary(
    rows,
    opening_balance: float,
    start_date: date | None = None,
    end_date: date | None = None,
):
    """
    Build the monthly ledger summary used by the existing application.

    Months without transactions are also included when they fall
    inside the requested date range, with the previous closing balance
    carried forward.

    Note:
    This function performs balance calculations in Python because that
    is how the current parser works. We are preserving it during this
    structural refactor. Tally-only financial mapping will be handled
    separately.
    """

    raw_months = {}
    row_dates = []

    for row in rows:

        row_date_text = row.get(
            "date"
        )

        if not row_date_text:
            continue

        try:
            row_date = datetime.strptime(
                row_date_text,
                "%Y-%m-%d",
            ).date()

        except ValueError:
            continue

        row_dates.append(
            row_date
        )

        key = row_date.strftime(
            "%Y-%m"
        )

        bucket = raw_months.setdefault(
            key,
            {
                "debit": 0.0,
                "credit": 0.0,
                "last_balance": None,
            },
        )

        bucket["debit"] += float(
            row.get("debit", 0)
            or 0
        )

        bucket["credit"] += float(
            row.get("credit", 0)
            or 0
        )

        running_balance = row.get(
            "running_balance"
        )

        if running_balance is not None:
            bucket["last_balance"] = float(
                running_balance
            )

    period_start = (
        start_date
        or (
            min(row_dates)
            if row_dates
            else None
        )
    )

    period_end = (
        end_date
        or (
            max(row_dates)
            if row_dates
            else None
        )
    )

    if (
        period_start is None
        or period_end is None
    ):
        return {}

    result = {}

    cursor = _first_of_month(
        period_start
    )

    running_balance = float(
        opening_balance
        or 0
    )

    # Protect against an accidental infinite loop if invalid dates
    # somehow reach this function.
    max_iterations = 600
    iterations = 0

    while (
        cursor <= period_end
        and iterations < max_iterations
    ):

        iterations += 1

        key = cursor.strftime(
            "%Y-%m"
        )

        label = cursor.strftime(
            "%b-%Y"
        )

        month_opening = (
            running_balance
        )

        bucket = raw_months.get(
            key
        )

        if bucket:

            debit = bucket["debit"]
            credit = bucket["credit"]

            if (
                bucket["last_balance"]
                is not None
            ):
                closing_balance = (
                    bucket["last_balance"]
                )

            else:
                closing_balance = (
                    month_opening
                    + debit
                    - credit
                )

        else:

            debit = 0.0
            credit = 0.0
            closing_balance = (
                month_opening
            )

        result[key] = {
            "month": label,
            "opening_balance": month_opening,
            "debit": debit,
            "credit": credit,
            "closing_balance": closing_balance,
        }

        running_balance = (
            closing_balance
        )

        cursor = _next_month(
            cursor
        )

    return result


# ============================================================
# LEDGER REPORT
# ============================================================

def parse_ledger_report(
    xml_text: str,
    ledger_name: str,
    opening_balance: float = 0.0,
    closing_balance=None,
    from_date: str | None = None,
    to_date: str | None = None,
):
    """
    Parse the existing ledger-report response.

    The current implementation:
    - reads native/custom Tally transaction rows
    - filters transactions by date
    - calculates period opening balance
    - calculates missing running balances
    - calculates debit/credit totals
    - calculates closing balance
    - builds monthly summary

    These calculations are existing behaviour and are intentionally
    preserved during this file-division refactor.
    """

    root = parse_xml(
        xml_text
    )

    native_rows = _parse_native_ledger_rows(
        root,
        ledger_name,
    )

    custom_rows = []

    # Prefer the native Tally report when it contains usable rows.
    # Otherwise use the existing voucher fallback.
    if not native_rows:

        custom_rows = parse_ledger_voucher_details(
            root,
            ledger_name,
        )

    rows = merge_ledger_rows(
        native_rows,
        custom_rows,
    )

    # --------------------------------------------------------
    # REQUESTED DATE RANGE
    # --------------------------------------------------------

    start_date = None
    end_date = None

    if from_date:

        try:
            start_date = datetime.strptime(
                from_date,
                "%Y-%m-%d",
            ).date()

        except ValueError:
            pass

    if to_date:

        try:
            end_date = datetime.strptime(
                to_date,
                "%Y-%m-%d",
            ).date()

        except ValueError:
            pass

    # Convert row dates to date objects so transactions can be
    # sorted and filtered reliably.
    normalized_rows = []

    for row in rows:

        row_date_text = row.get(
            "date"
        )

        if not row_date_text:
            continue

        try:
            row_date = datetime.strptime(
                row_date_text,
                "%Y-%m-%d",
            ).date()

        except ValueError:
            continue

        row["_date_obj"] = (
            row_date
        )

        normalized_rows.append(
            row
        )

    normalized_rows.sort(
        key=lambda row: row["_date_obj"]
    )

    # --------------------------------------------------------
    # PERIOD OPENING BALANCE
    # --------------------------------------------------------

    # Existing behaviour:
    # start with the supplied opening balance and apply transactions
    # occurring before the requested start date.
    period_opening = float(
        opening_balance
        or 0
    )

    if start_date:

        for row in normalized_rows:

            if (
                row["_date_obj"]
                >= start_date
            ):
                break

            period_opening += (
                float(
                    row.get("debit", 0)
                    or 0
                )
                - float(
                    row.get("credit", 0)
                    or 0
                )
            )

    # --------------------------------------------------------
    # FILTER TRANSACTIONS TO THE REQUESTED PERIOD
    # --------------------------------------------------------

    period_rows = []

    for row in normalized_rows:

        row_date = row[
            "_date_obj"
        ]

        if (
            start_date
            and row_date < start_date
        ):
            continue

        if (
            end_date
            and row_date > end_date
        ):
            continue

        period_rows.append(
            row
        )

    # --------------------------------------------------------
    # RUNNING BALANCE
    # --------------------------------------------------------

    running_balance = (
        period_opening
    )

    final_rows = []

    for row in period_rows:

        debit = float(
            row.get("debit", 0)
            or 0
        )

        credit = float(
            row.get("credit", 0)
            or 0
        )

        calculated_balance = (
            running_balance
            + debit
            - credit
        )

        # Prefer the running balance from Tally when it exists.
        # Otherwise preserve the old fallback calculation.
        tally_balance = row.get(
            "running_balance"
        )

        if tally_balance is not None:

            display_balance = float(
                tally_balance
            )

        else:

            display_balance = (
                calculated_balance
            )

        running_balance = (
            calculated_balance
        )

        # Remove the temporary date object before returning the row.
        clean_row = {
            key: value
            for key, value in row.items()
            if key != "_date_obj"
        }

        clean_row[
            "running_balance"
        ] = display_balance

        final_rows.append(
            clean_row
        )

    # --------------------------------------------------------
    # TOTALS
    # --------------------------------------------------------

    total_debit = sum(
        float(
            row.get("debit", 0)
            or 0
        )
        for row in final_rows
    )

    total_credit = sum(
        float(
            row.get("credit", 0)
            or 0
        )
        for row in final_rows
    )

    calculated_closing = (
        period_opening
        + total_debit
        - total_credit
    )

    if final_rows:
        period_closing = (
            calculated_closing
        )
    else:
        period_closing = (
            period_opening
        )

    # --------------------------------------------------------
    # MONTHLY SUMMARY
    # --------------------------------------------------------

    monthly_summary = (
        build_continuous_monthly_summary(
            final_rows,
            period_opening,
            start_date=start_date,
            end_date=end_date,
        )
    )

    return {
        "ledger_name": ledger_name,
        "opening_balance": period_opening,
        "closing_balance": period_closing,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "entries": final_rows,
        "monthly_summary": monthly_summary,
        "entry_count": len(final_rows),

        "from_date": (
            start_date.isoformat()
            if start_date
            else None
        ),

        "to_date": (
            end_date.isoformat()
            if end_date
            else None
        ),
    }