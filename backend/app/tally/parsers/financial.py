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

from app.financial.calculations import normalize_account_name

from app.tally.parsers.common import (
    parse_xml,
    to_float,
    _text,
    _first_text,
    format_tally_date,
)


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


def _parse_dspacc_rows(root):
    """
    Parse the common DSPACCNAME / DSPACCINFO structure used by
    Tally's Trial Balance and Group Summary reports.

    Tally provides the account name in DSPACCNAME and the financial
    values in the following DSPACCINFO element.

    This function preserves the behaviour of the original parser.
    """
    rows = []
    pending_name = None

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

            # Preserve the existing parser behaviour.
            debit = abs(
                to_float(debit_text)
            )

            credit = abs(
                to_float(credit_text)
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
        """
        side = (
            "right"
            if entry["amount"] >= 0
            else "left"
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

        left_rows.extend(
            trading_left
        )

        right_rows.extend(
            trading_right
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

    return {
        "success": True,
        "left": left_rows,
        "right": right_rows,
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
        root
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

    # Preserve the totals returned by the existing parser.
    total_debit = round(
        sum(
            row["debit"]
            for row in rows
        ),
        2,
    )

    total_credit = round(
        sum(
            row["credit"]
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