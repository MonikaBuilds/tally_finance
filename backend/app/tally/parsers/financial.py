"""
Financial report parsers for Tally XML responses.

This module contains parsers for financial reports such as:
- Profit & Loss
- Trial Balance
- Group Summary
- Balance Sheet
- Bill Allocations
- Outstanding / Receivable / Payable reports

The common XML handling functions are kept in common.py so that
this file stays focused on financial report parsing.

Important:
This file currently preserves the behaviour of the original parser.py.
Financial calculation logic is not being redesigned during this
modularization.
"""

import re

from app.financial.calculations import normalize_account_name

from app.tally.parsers.common import (
    parse_xml,
    to_float,
    _text,
    _first_text,
    format_tally_date,
)


_TRADING_PREFIX_RE = re.compile(r"^(add:|less:)\s*", re.IGNORECASE)


def _strip_trading_prefix(name):
    return _TRADING_PREFIX_RE.sub("", name or "").strip()


def _move_closing_stock_last(rows):
    """
    Tally's raw XML feed emits trading-section rows in a different order
    than Tally's own screen: 'Less: Closing Stock' arrives right after
    Purchase Accounts, before Direct Expenses. But Tally always
    *displays* Closing Stock as the last Dr-side line, after Direct
    Expenses. Re-order the left column to match what Tally shows.
    """
    closing = []
    rest = []

    for row in rows:
        if _strip_trading_prefix(row["name"]).lower() == "closing stock":
            closing.append(row)
        else:
            rest.append(row)

    return rest + closing


# ============================================================
# FINANCIAL REPORT HELPERS
# ============================================================

def _nested_amount_text(node, *tags):
    """
    Read an amount from Tally's nested financial report structure.

    Some Tally reports do not place the amount directly inside a tag.

    For example:

        <DSPCLDRAMT>
            <DSPCLDRAMTA>-6305000.00</DSPCLDRAMTA>
        </DSPCLDRAMT>

    So we first check the nested tag and then fall back to the
    direct value when required.
    """
    if node is None:
        return ""

    for tag in tags:

        nested_value = _text(
            node,
            f"{tag}/{tag}A",
            "",
        )

        if nested_value:
            return nested_value

        direct_value = _text(
            node,
            tag,
            "",
        )

        if direct_value:
            return direct_value

    return ""


def _parse_dspacc_rows(root, preserve_sign=False):
    """
    Parse the common DSPACCNAME / DSPACCINFO structure used by
    Tally's Trial Balance and Group Summary reports.

    Tally provides the account name in DSPACCNAME and the financial
    values in the following DSPACCINFO element.

    This function preserves the behaviour of the original parser.

    preserve_sign:
        False (default, unchanged): every debit/credit value is
        returned as a positive magnitude, exactly as before. Used by
        Group Summary (shared with the Profit & Loss drill-down) -
        left untouched.

        True (Trial Balance only): the debit/credit value is returned
        exactly as Tally's own DSPCLDRAMT/DSPCLDRAMT-style tag sent it,
        sign included. Tally itself sometimes reports a group's
        debit or credit as negative (shown on-screen as "(-)") when
        that group's ledgers net to the opposite of what that column
        normally holds - e.g. this company's Purchase Accounts shows
        as (-)1,68,00,000 Debit, and Current Liabilities shows as
        (-)1,43,21,300 Credit, on the live Tally screen. Parsing this
        with abs() (the old behaviour) silently turned those into
        positive numbers instead of matching Tally.
    """
    rows = []
    pending_name = None

    # DEBUG: exact raw text Tally sent for debit/credit per row, so
    # the correct sign mapping can be worked out from real data
    # instead of guessed. Printed unconditionally (matching this
    # project's existing debug-print convention elsewhere, e.g. the
    # Ledger report) - safe to leave in, and remove once the sign
    # rule is confirmed and implemented for good.
    debug_rows = []

    for node in root.iter():

        if node.tag == "DSPACCNAME":

            name = _first_text(
                node,
                "DSPDISPNAME",
                "NAME",
            )

            if name:
                pending_name = name

            continue

        if node.tag != "DSPACCINFO":
            continue

        # An amount should only be attached to a name that was
        # previously found in DSPACCNAME.
        if pending_name is None:
            continue

        debit_text = _nested_amount_text(
            node,
            "DSPCLDRAMT",
            "DSPDRAMT",
        )

        credit_text = _nested_amount_text(
            node,
            "DSPCLCRAMT",
            "DSPCRAMT",
        )

        if debit_text or credit_text:

            # Read the amount exactly as Tally sent it (sign included).
            # preserve_sign decides, per caller, whether that sign is
            # then kept (Trial Balance) or discarded via abs() (Group
            # Summary / Profit & Loss, unchanged from before) - see the
            # preserve_sign note in this function's docstring.
            debit = to_float(debit_text)
            credit = to_float(credit_text)

            if not preserve_sign:
                debit = abs(debit)
                credit = abs(credit)

            debug_rows.append(
                {
                    "name": pending_name,
                    "debit_text": debit_text,
                    "credit_text": credit_text,
                }
            )

        else:
            # Some Tally report formats provide one signed amount
            # instead of separate debit and credit fields.
            signed_text = (
                _nested_amount_text(
                    node,
                    "DSPCLAMT",
                    "DSPAMOUNT",
                )
                or _first_text(
                    node,
                    "AMOUNT",
                )
            )

            signed_amount = to_float(
                signed_text
            )

            # Preserve the existing fallback behaviour.
            if signed_amount >= 0:
                debit = signed_amount
                credit = 0.0
            else:
                debit = 0.0
                credit = abs(signed_amount)

        rows.append(
            {
                "name": pending_name,
                "debit": debit,
                "credit": credit,
            }
        )

        pending_name = None

    print("\n========== TRIAL BALANCE / GROUP SUMMARY - RAW SIGN DEBUG ==========")
    for row in debug_rows:
        print(
            f'{row["name"]!r}: debit_text={row["debit_text"]!r}  '
            f'credit_text={row["credit_text"]!r}'
        )
    print("========== END RAW SIGN DEBUG ==========\n")

    return rows


# ============================================================
# PROFIT & LOSS
# ============================================================

def parse_profit_loss(xml_text: str):
    """
    Parse Tally's Profit & Loss report.

    Tally sends the account name in DSPACCNAME and its amount in
    the following PLAMT element.

    The existing application also prepares left/right display rows
    and summary values here. That behaviour is intentionally kept
    unchanged during this refactor.
    """
    root = parse_xml(xml_text)

    children = list(root)

    # First convert Tally's DSPACCNAME / PLAMT pairs into a simpler
    # internal list that can be processed by the existing report logic.
    entries = []
    i = 0

    while i < len(children):

        node = children[i]

        if node.tag.upper() != "DSPACCNAME":
            i += 1
            continue

        name = _first_text(
            node,
            "DSPDISPNAME",
            "NAME",
        )

        amount_node = (
            children[i + 1]
            if i + 1 < len(children)
            else None
        )

        main_text = ""
        sub_text = ""

        if (
            amount_node is not None
            and amount_node.tag.upper() == "PLAMT"
        ):
            main_text = _text(
                amount_node,
                "BSMAINAMT",
            )

            sub_text = _text(
                amount_node,
                "PLSUBAMT",
            )

        is_top_level = bool(
            main_text.strip()
        )

        if is_top_level:

            # Look at the next account row to determine whether this
            # row is acting as a container for child entries.
            j = i + 2

            while (
                j < len(children)
                and children[j].tag.upper() != "DSPACCNAME"
            ):
                j += 1

            next_main = ""

            if j < len(children):

                next_amount_node = (
                    children[j + 1]
                    if j + 1 < len(children)
                    else None
                )

                if (
                    next_amount_node is not None
                    and next_amount_node.tag.upper() == "PLAMT"
                ):
                    next_main = _text(
                        next_amount_node,
                        "BSMAINAMT",
                    )

            is_container = (
                j < len(children)
                and not bool(next_main.strip())
            )

            entries.append(
                {
                    "name": name,
                    "amount": to_float(main_text),
                    "is_group": True,
                    "is_container": is_container,
                }
            )

        else:

            entries.append(
                {
                    "name": name,
                    "amount": to_float(sub_text),
                    "is_group": False,
                    "is_container": False,
                }
            )

        i += 2

    # --------------------------------------------------------
    # Separate trading section and P&L section
    # --------------------------------------------------------

    has_container = any(
        entry["is_container"]
        for entry in entries
    )

    trading_entries = []
    pl_entries = []

    in_container_children = False
    exited_trading = not has_container

    for entry in entries:

        if entry["is_container"]:
            in_container_children = True
            continue

        if (
            entry["is_group"]
            and in_container_children
        ):
            in_container_children = False
            exited_trading = True

        if exited_trading:
            pl_entries.append(entry)
        else:
            trading_entries.append(entry)

    def _rendered_row(entry):
        """
        Convert an internal entry into the left/right row structure
        expected by the existing frontend.

        'Less:' is a real operator, not decoration - it means "subtract
        from whichever side the raw sign would put it on", which is the
        same as placing it on the *opposite* side. 'Add:' needs no
        special handling; a naturally positive/negative amount already
        lands on the correct side by sign alone.
        """
        naive_side = (
            "right"
            if entry["amount"] >= 0
            else "left"
        )

        is_less = (entry["name"] or "").strip().lower().startswith("less:")

        side = (
            ("left" if naive_side == "right" else "right")
            if is_less
            else naive_side
        )

        row = {
            "name": entry["name"],
            "amount": round(
                abs(entry["amount"]),
                2,
            ),
            "is_group": entry["is_group"],
        }

        return side, row

    def _split(entry_list):
        """
        Split report entries into the existing left and right columns.
        """
        left = []
        right = []

        for entry in entry_list:

            side, row = _rendered_row(
                entry
            )

            if side == "right":
                right.append(row)
            else:
                left.append(row)

        return left, right

    left_rows = []
    right_rows = []

    # --------------------------------------------------------
    # Trading section
    # --------------------------------------------------------

    trading_income_total = 0.0
    trading_expense_total = 0.0
    gross_result = None

    if trading_entries:

        trading_left, trading_right = _split(
            trading_entries
        )

        trading_left = _move_closing_stock_last(
            trading_left
        )

        total_left = round(
            sum(
                row["amount"]
                for row in trading_left
            ),
            2,
        )

        total_right = round(
            sum(
                row["amount"]
                for row in trading_right
            ),
            2,
        )

        trading_income_total = total_right
        trading_expense_total = total_left

        gross_result = round(
            total_right - total_left,
            2,
        )

        if gross_result >= 0:

            trading_left.append(
                {
                    "name": "Gross Profit c/o",
                    "amount": gross_result,
                    "is_group": True,
                }
            )

            carry_row = {
                "name": "Gross Profit b/f",
                "amount": gross_result,
                "is_group": True,
            }

            carry_side = "right"

        else:

            trading_right.append(
                {
                    "name": "Gross Loss c/o",
                    "amount": abs(gross_result),
                    "is_group": True,
                }
            )

            carry_row = {
                "name": "Gross Loss b/f",
                "amount": abs(gross_result),
                "is_group": True,
            }

            carry_side = "left"

        # Tally shows an unlabelled subtotal row right after the trading
        # section, on both sides, before the Indirect Expenses / P&L
        # section starts. It's guaranteed to be equal on both sides by
        # construction (that's exactly what Gross Profit c/o balances),
        # so one shared amount serves both columns.
        trading_subtotal = round(
            sum(
                row["amount"]
                for row in trading_left
            ),
            2,
        )

        left_rows.extend(
            trading_left
        )

        left_rows.append(
            {
                "name": "",
                "amount": trading_subtotal,
                "is_group": True,
                "is_subtotal": True,
            }
        )

        right_rows.extend(
            trading_right
        )

        right_rows.append(
            {
                "name": "",
                "amount": trading_subtotal,
                "is_group": True,
                "is_subtotal": True,
            }
        )

    else:
        carry_row = None
        carry_side = None

    # --------------------------------------------------------
    # Profit & Loss section
    # --------------------------------------------------------

    pl_left, pl_right = _split(
        pl_entries
    )

    indirect_expenses_amount = 0.0

    for entry in pl_entries:

        if (
            normalize_account_name(
                entry["name"]
            )
            == "indirect expenses"
        ):
            indirect_expenses_amount = abs(
                entry["amount"]
            )

    # Carry the gross result into the P&L section.
    if carry_row is not None:

        if carry_side == "right":
            pl_right.append(carry_row)
        else:
            pl_left.append(carry_row)

    total_pl_left = round(
        sum(
            row["amount"]
            for row in pl_left
        ),
        2,
    )

    total_pl_right = round(
        sum(
            row["amount"]
            for row in pl_right
        ),
        2,
    )

    net_result = round(
        total_pl_right - total_pl_left,
        2,
    )

    if net_result >= 0:

        pl_left.append(
            {
                "name": "Net Profit",
                "amount": net_result,
                "is_group": True,
            }
        )

    else:

        pl_right.append(
            {
                "name": "Nett Loss",
                "amount": abs(net_result),
                "is_group": True,
            }
        )

    left_rows.extend(pl_left)
    right_rows.extend(pl_right)

    final_total_left = round(
        sum(
            row["amount"]
            for row in pl_left
        ),
        2,
    )

    final_total_right = round(
        sum(
            row["amount"]
            for row in pl_right
        ),
        2,
    )

    return {
        "success": True,
        "left": left_rows,
        "right": right_rows,
        "total_left": final_total_left,
        "total_right": final_total_right,
        "summary": {
            "trading_income_total": trading_income_total,
            "trading_expense_total": trading_expense_total,
            "gross_result": gross_result,
            "indirect_expenses_amount": indirect_expenses_amount,
            "net_result": net_result,
        },
    }


# ============================================================
# TRIAL BALANCE
# ============================================================

def parse_trial_balance(xml_text: str):
    """
    Parse Tally's Trial Balance report.

    Trial Balance uses separate debit and credit fields.
    """
    root = parse_xml(xml_text)

    rows = _parse_dspacc_rows(
        root,
        # preserve_sign is temporarily False again: an initial attempt
        # to pass Tally's raw DSPCLDRAMT/DSPCLCRAMT sign straight
        # through (preserve_sign=True) was tested against the live
        # server and got MORE rows wrong than it fixed (Current
        # Liabilities Debit, Current Assets Debit+Credit, Purchase
        # Accounts Debit, Direct/Indirect Expenses Debit all came out
        # with the wrong sign - only Loans, Sales and Current
        # Liabilities Credit were right). So Tally's raw tag sign does
        # NOT map 1:1 onto the "(-)" shown on screen, confirming the
        # concern already raised above. Flip this back to True only
        # once the correct mapping has been worked out from the
        # debug_rows console output above (see chat/README) - guessing
        # a third time is not worth the risk of a wrong TB going live.
        preserve_sign=False,
    )

    return {
        "success": True,
        "rows": rows,
        "count": len(rows),
    }


# ============================================================
# GROUP SUMMARY
# ============================================================

def parse_group_summary(
    xml_text: str,
    group_name: str | None = None,
):
    """
    Parse a Tally Group Summary report.

    This report is commonly used when drilling down into a financial
    group such as Indirect Expenses.
    """
    root = parse_xml(xml_text)

    rows = _parse_dspacc_rows(
        root
    )

    # Tally's own Group Summary footer sums the magnitude of each
    # row's debit/credit, even though a row itself can show a
    # negative ("(-)") amount when that account's true balance runs
    # the other way (e.g. Sundry Creditors showing a negative credit
    # because it actually carries a debit balance) - verified against
    # a live Tally screen: Duties & Taxes 13,33,800 + Provisions
    # 2,05,000 + Sundry Creditors (-)1,58,60,100 still totals
    # 1,73,98,900, not a netted 0. Summing abs() here matches that;
    # summing the signed values would not.
    total_debit = round(
        sum(
            abs(row["debit"])
            for row in rows
        ),
        2,
    )

    total_credit = round(
        sum(
            abs(row["credit"])
            for row in rows
        ),
        2,
    )

    return {
        "success": True,
        "group_name": group_name,
        "rows": rows,
        "count": len(rows),
        "total_debit": total_debit,
        "total_credit": total_credit,
    }


# ============================================================
# BALANCE SHEET
# ============================================================

def parse_balance_sheet(xml_text: str):
    """
    Parse rows returned by Tally's Balance Sheet report.
    """
    root = parse_xml(xml_text)

    rows = []

    for node in root.findall(
        ".//DSPACCNAME"
    ):

        name = _first_text(
            node,
            "DSPDISPNAME",
            "NAME",
        )

        if not name:
            continue

        amount = _first_text(
            node,
            "DSPCLAMT",
            "DSPAMOUNT",
            "AMOUNT",
        )

        rows.append(
            {
                "name": name,
                "amount": to_float(amount),
            }
        )

    return {
        "success": True,
        "rows": rows,
        "count": len(rows),
    }


# ============================================================
# BILL ALLOCATIONS
# ============================================================

def parse_bill_allocations(xml_text: str):
    """
    Parse bill/voucher information returned by Tally.

    Values are read from the voucher XML and returned in the same
    structure expected by the existing application.
    """
    root = parse_xml(xml_text)

    rows = []

    for voucher in root.findall(
        ".//VOUCHER"
    ):

        rows.append(
            {
                "date": format_tally_date(
                    _text(
                        voucher,
                        "DATE",
                    )
                ),

                "guid": _text(
                    voucher,
                    "GUID",
                ),

                "voucher_type": _text(
                    voucher,
                    "VOUCHERTYPENAME",
                ),

                "voucher_number": _text(
                    voucher,
                    "VOUCHERNUMBER",
                ),

                "party_ledger_name": _text(
                    voucher,
                    "PARTYLEDGERNAME",
                ),

                "party_name": _text(
                    voucher,
                    "PARTYNAME",
                ),

                "reference": _text(
                    voucher,
                    "REFERENCE",
                ),

                "narration": _text(
                    voucher,
                    "NARRATION",
                ),
            }
        )

    return {
        "success": True,
        "rows": rows,
        "count": len(rows),
    }


# ============================================================
# OUTSTANDING / RECEIVABLE / PAYABLE
# ============================================================

def parse_outstanding_report(
    xml_text: str,
    report_type: str = "receivable",
):
    """
    Parse Tally's outstanding report.

    The report_type tells the caller whether these rows belong to
    a receivable or payable request.
    """
    root = parse_xml(xml_text)

    rows = []

    for node in root.findall(
        ".//DSPACCNAME"
    ):

        name = _first_text(
            node,
            "DSPDISPNAME",
            "NAME",
        )

        if not name:
            continue

        amount = _first_text(
            node,
            "DSPCLAMT",
            "DSPAMOUNT",
            "AMOUNT",
        )

        rows.append(
            {
                "name": name,
                "amount": to_float(amount),
                "type": report_type,
            }
        )

    return {
        "success": True,
        "report_type": report_type,
        "rows": rows,
        "count": len(rows),
    }