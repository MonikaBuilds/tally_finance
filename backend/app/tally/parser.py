import re
import xml.etree.ElementTree as ET
from datetime import date, datetime

from app.financial.calculations import normalize_account_name


# ============================================================
# XML CLEANING / BASIC HELPERS
# ============================================================

_INVALID_CHAR_REF = re.compile(r"&#(?:x([0-9A-Fa-f]+)|([0-9]+));")


def _is_valid_xml_char(code_point: int) -> bool:
    return (
        code_point in (0x9, 0xA, 0xD)
        or 0x20 <= code_point <= 0xD7FF
        or 0xE000 <= code_point <= 0xFFFD
        or 0x10000 <= code_point <= 0x10FFFF
    )


def _drop_invalid_char_ref(match: re.Match) -> str:
    hex_digits, decimal_digits = match.groups()

    code_point = (
        int(hex_digits, 16)
        if hex_digits is not None
        else int(decimal_digits)
    )

    if _is_valid_xml_char(code_point):
        return match.group(0)

    return ""


def clean_tally_xml(xml_text: str) -> str:
    """
    Clean common invalid XML characters returned by Tally.
    """
    if not xml_text:
        return ""

    # Remove invalid XML control characters
    xml_text = re.sub(
        r"[\x00-\x08\x0B\x0C\x0E-\x1F]",
        "",
        xml_text,
    )

    # Tally sometimes returns numeric references to characters XML
    # forbids, e.g. "<GSTCLASS>&#4; Not Applicable</GSTCLASS>" on
    # inventory entries. Drop them all in one pass (decimal and hex) -
    # a large voucher export can contain hundreds, far more than the
    # one-at-a-time repair loop in parse_xml() is allowed to fix.
    xml_text = _INVALID_CHAR_REF.sub(
        _drop_invalid_char_ref,
        xml_text,
    )

    # Make UDF tags XML-safe
    xml_text = xml_text.replace("<UDF:", "<UDF_")
    xml_text = xml_text.replace("</UDF:", "</UDF_")

    return xml_text


def _line_col_to_offset(text: str, lineno: int, col: int):
    """Convert an ElementTree ParseError (line, column) into an absolute
    character offset into `text`, so we can locate the exact character
    the parser choked on."""

    lines = text.split("\n")

    if lineno < 1 or lineno > len(lines):
        return None

    return sum(len(line) + 1 for line in lines[:lineno - 1]) + col


def _heal_one_error(text: str, exc: ET.ParseError):
    """
    Given a ParseError, try to surgically fix just the single offending
    spot and return the repaired text. Returns None if this isn't an
    error class we know how to safely auto-heal (caller then falls back
    to the ENVELOPE-trimming recovery, or re-raises).
    """

    message = str(exc)

    # Junk before/after the actual <ENVELOPE>...</ENVELOPE> payload
    # (some Tally builds prepend/append stray bytes). Trim to just the
    # envelope and let the caller retry.
    if "junk after document element" in message:
        start = text.find("<ENVELOPE")
        end = text.rfind("</ENVELOPE>")

        if start >= 0 and end >= 0:
            trimmed = text[start:end + len("</ENVELOPE>")]

            if trimmed != text:
                return trimmed

        return None

    if not exc.position:
        return None

    lineno, col = exc.position
    offset = _line_col_to_offset(text, lineno, col)

    if offset is None:
        return None

    # Case 1: a well-formed numeric character reference (e.g. "&#4;")
    # that points at a code point the XML spec forbids (stray control
    # characters that sneak into Tally narrations/party names from
    # copy-pasted Word/Excel/PDF text). This is a catch-all for
    # variants clean_tally_xml()'s regex above doesn't already catch -
    # drop just that one reference and keep going.
    if "invalid character number" in message and text[offset:offset + 2] == "&#":
        semicolon = text.find(";", offset)

        if semicolon == -1:
            return None

        return text[:offset] + text[semicolon + 1:]

    # Case 2: a bare, unescaped "&" in field data (very common in Indian
    # business names, e.g. "Sharma & Sons") that Tally failed to escape
    # as "&amp;" when generating the XML. Expat reports the position of
    # the character *after* the "&" (the point where it stopped looking
    # like a valid entity name), so scan a short window backwards for
    # the "&" that started the invalid token.
    if "not well-formed" in message:
        # Junk *before* <ENVELOPE> is also reported as "not well-formed"
        # at the point that breaks tokenizing - try the envelope trim
        # first since it's the more likely real cause near start of doc.
        if offset < 200:
            start = text.find("<ENVELOPE")

            if start > 0:
                trimmed = text[start:]

                if trimmed != text:
                    return trimmed

        search_start = max(0, offset - 40)
        window = text[search_start:offset]
        amp_pos = window.rfind("&")

        if amp_pos != -1 and ";" not in window[amp_pos:]:
            amp_offset = search_start + amp_pos
            return text[:amp_offset] + "&amp;" + text[amp_offset + 1:]

    return None


def parse_xml(xml_text: str, max_heal_attempts: int = 200):
    """
    Parse Tally XML safely, self-healing common real-world corruption
    (stray control characters, invalid numeric character references,
    unescaped "&" in field data, and junk before/after the envelope)
    instead of failing on the very first ledger/voucher that has it.
    """

    text = clean_tally_xml(xml_text)

    for _ in range(max_heal_attempts):
        try:
            return ET.fromstring(text)

        except ET.ParseError as exc:
            healed = _heal_one_error(text, exc)

            if healed is None:
                raise

            text = healed

    raise ET.ParseError(
        f"Tally XML still invalid after {max_heal_attempts} automatic "
        f"repair attempts - the export is more corrupted than usual"
    )


def to_float(value) -> float:
    """
    Convert Tally numeric values into float.

    Handles:
      1,23,456.00
      -100
      ₹100
      100 Dr
      100 Cr
    """
    if value is None:
        return 0.0

    text = str(value).strip()

    if not text:
        return 0.0

    # Remove currency symbols and commas
    text = text.replace(",", "")
    text = text.replace("₹", "")
    text = text.replace("$", "")

    # Remove Dr/Cr
    text = re.sub(r"\bDR\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bCR\b", "", text, flags=re.IGNORECASE)

    match = re.search(
        r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)",
        text,
    )

    if not match:
        return 0.0

    try:
        return float(match.group(0))
    except (ValueError, TypeError):
        return 0.0


def to_optional_float(value: str | None) -> float | None:
    """
    Parse a financial value supplied by Tally.

    A genuine Tally value such as "0.00" remains 0.0.
    Missing, blank, or invalid values remain unavailable as None.
    """
    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    normalized = value.replace(",", "").replace(" ", "")

    upper = normalized.upper()

    if upper.endswith("DR") or upper.endswith("CR"):
        normalized = normalized[:-2]

    normalized = normalized.strip()

    if not normalized:
        return None

    try:
        return float(normalized)
    except (TypeError, ValueError):
        return None


def _text(node, tag: str, default=""):
    """
    Return child text safely.
    """
    if node is None:
        return default

    child = node.find(tag)

    if child is None or child.text is None:
        return default

    return child.text.strip()


def _first_text(node, *tags, default=""):
    """
    Return the first non-empty matching child text.
    """
    for tag in tags:
        value = _text(node, tag, "")

        if value:
            return value

    return default


def _nested_amount_text(node, *tags):
    """
    Tally's Trial Balance / Group Summary XML doesn't put the amount
    directly on DSPCLDRAMT/DSPCLCRAMT/DSPCLAMT etc - it nests it one
    level deeper, in a child with the same name plus an "A" suffix
    (e.g. <DSPCLDRAMT><DSPCLDRAMTA>-6305000.00</DSPCLDRAMTA></DSPCLDRAMT>).
    Try that nested form first, then fall back to the tag's own text
    in case a differently-built report puts it there directly.
    """
    if node is None:
        return ""

    for tag in tags:
        nested = _text(node, f"{tag}/{tag}A", "")

        if nested:
            return nested

        direct = _text(node, tag, "")

        if direct:
            return direct

    return ""


def _parse_dspacc_rows(root):
    """
    Shared row-builder for Trial Balance and Group Summary - both
    report types lay their data out the same way in Tally's XML:
    a <DSPACCNAME> element (carrying just the ledger/group name)
    immediately followed by a sibling <DSPACCINFO> element (carrying
    the Debit/Credit closing amounts, nested one level deeper - see
    _nested_amount_text). They are NOT nested inside each other, so
    this walks the document in order and pairs each DSPACCNAME with
    the DSPACCINFO that follows it.

    Amounts come through with Tally's internal sign convention
    (Dr negative, Cr positive) rather than the sign implied by which
    column they're in - abs() them once assigned to the correct
    column so the UI shows plain positive figures, the same way
    Tally's own screen does.
    """
    rows = []
    pending_name = None

    for node in root.iter():
        tag = node.tag

        if tag == "DSPACCNAME":
            name = _first_text(node, "DSPDISPNAME", "NAME")

            if name:
                pending_name = name

            continue

        if tag == "DSPACCINFO":
            if pending_name is None:
                continue

            debit_text = _nested_amount_text(node, "DSPCLDRAMT", "DSPDRAMT")
            credit_text = _nested_amount_text(node, "DSPCLCRAMT", "DSPCRAMT")

            if debit_text or credit_text:
                debit = abs(to_float(debit_text))
                credit = abs(to_float(credit_text))
            else:
                # Fallback: single signed amount, some report builds
                # only carry one closing figure per row rather than
                # a separate Dr/Cr pair - positive -> Debit column,
                # negative -> Credit column (absolute value).
                signed_text = _nested_amount_text(
                    node, "DSPCLAMT", "DSPAMOUNT"
                ) or _first_text(node, "AMOUNT")
                signed_amount = to_float(signed_text)

                if signed_amount >= 0:
                    debit, credit = signed_amount, 0.0
                else:
                    debit, credit = 0.0, abs(signed_amount)

            rows.append(
                {
                    "name": pending_name,
                    "debit": debit,
                    "credit": credit,
                }
            )

            pending_name = None

    return rows


def format_tally_date(value: str | None):
    """
    Convert Tally dates to YYYY-MM-DD.
    """
    if not value:
        return None

    value = str(value).strip()

    formats = [
        "%Y%m%d",
        "%d-%b-%y",
        "%d-%b-%Y",
        "%Y-%m-%d",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue

    return value


# ============================================================
# COMPANIES
# ============================================================

def parse_companies(xml_text: str):
    root = parse_xml(xml_text)

    companies = []

    for node in root.findall(".//COMPANY"):
        name = _first_text(node, "NAME")

        if not name:
            name = node.attrib.get("NAME", "")

        if not name:
            continue

        companies.append(
            {
                "name": name,
                "guid": _text(node, "GUID"),
                "books_from": format_tally_date(
                    _text(node, "BOOKSFROM")
                ),
                "starting_from": format_tally_date(
                    _text(node, "STARTINGFROM")
                ),
                "gst_registration_type": _text(
                    node,
                    "GSTREGISTRATIONTYPE",
                ),
                "gstin": _text(node, "GSTIN"),
            }
        )

    return {
        "success": True,
        "companies": companies,
        "count": len(companies),
    }


# ============================================================
# PROFIT & LOSS
# ============================================================

def parse_profit_loss(xml_text: str):
    """
    Tally's Profit & Loss XML pairs each <DSPACCNAME> (the row label,
    in <DSPDISPNAME>) with the NEXT sibling <PLAMT>, which holds the
    actual amount - never inside DSPACCNAME itself:

        <DSPACCNAME><DSPDISPNAME>Sales Accounts</DSPDISPNAME></DSPACCNAME>
        <PLAMT><PLSUBAMT></PLSUBAMT><BSMAINAMT>7410000.00</BSMAINAMT></PLAMT>

    <BSMAINAMT> holds top-level line amounts (Sales Accounts, Cost of
    Sales, Indirect Expenses); <PLSUBAMT> holds the indented breakdown
    lines that follow a top-level line which has no BSMAINAMT of its
    own child rows (e.g. Cost of Sales explodes into Opening Stock,
    Purchases, Direct Expenses, Closing Stock).

    THE COLUMN RULE (fixed here):
    Every row - top-level AND sub-item alike - goes on the LEFT or
    RIGHT purely by the sign of *its own* amount (negative -> left,
    positive -> right). A sub-item does NOT inherit its parent
    group's side. This is what real Tally does, and it's the reason
    "Purchase Accounts" can sit on the right next to "Sales Accounts"
    even though it is one of Cost of Sales's children: in this
    company's data Purchase Accounts nets to a credit balance (its
    own PLSUBAMT is positive), so it stands on the right, while
    Closing Stock nets to a debit in this data (its own PLSUBAMT is
    negative) and stays on the left - exactly matching the printed
    Tally PDF. The previous version of this parser inherited the
    parent ("Cost of Sales") side for every sub-item, which is why
    Purchase Accounts was stuck on the left and the column totals
    didn't reconcile with Tally's own export.

    CONTAINER ROWS ARE NEVER RENDERED:
    A top-level row whose immediate next DSPACCNAME sibling is a
    sub-item (no BSMAINAMT of its own) is a *container* - Tally
    explodes it into its children on-screen instead of showing it as
    its own line (e.g. "Cost of Sales :" itself never appears in the
    PDF, only Opening Stock / Purchases / Direct Expenses / Closing
    Stock do). We detect this structurally (by peeking at the next
    row) instead of matching on the English label, so it keeps
    working regardless of language/company chart of accounts.

    TWO BALANCING SECTIONS:
    Tally's P&L is really two stacked T-accounts:
      1. Trading section: every row up to and including a container's
         exploded children (income rows + Cost-of-Sales breakdown).
         Balanced with a computed "Gross Profit/Loss c/o" (added to
         the smaller side) carried forward as "Gross Profit/Loss b/f"
         into section 2.
      2. P&L section: everything after the trading section (e.g.
         Indirect Expenses), plus the carried-forward gross result.
         Balanced with a computed "Net Profit"/"Nett Loss".
    If the document has no container at all (a simple company with
    no stock/direct expenses), there is no trading section - every
    row is balanced in one pass, exactly like Tally shows for such
    companies (no separate Gross Profit line).

    Verified against a real Tally PDF export line-for-line (ABC Pvt
    Ltd, FY 25-26): Opening Stock 1,05,00,000 (L), Direct Expenses
    63,05,000 (L), Closing Stock 74,00,000 (L), Purchase Accounts
    1,68,00,000 (R), Sales Accounts 74,10,000 (R), Gross Profit
    5,000, Indirect Expenses 2,70,000 (L), Nett Loss 2,65,000 - both
    totals reconcile to 2,42,10,000 and 2,70,000 exactly as printed.
    """
    root = parse_xml(xml_text)

    children = list(root)

    # ------------------------------------------------------------
    # Pass 1: flatten <DSPACCNAME>/<PLAMT> pairs into entries, and
    # mark which top-level rows are containers (never rendered).
    # ------------------------------------------------------------

    entries = []
    i = 0

    while i < len(children):
        node = children[i]

        if node.tag.upper() != "DSPACCNAME":
            i += 1
            continue

        name = _first_text(node, "DSPDISPNAME", "NAME")
        amount_node = children[i + 1] if i + 1 < len(children) else None

        main_text = ""
        sub_text = ""

        if amount_node is not None and amount_node.tag.upper() == "PLAMT":
            main_text = _text(amount_node, "BSMAINAMT")
            sub_text = _text(amount_node, "PLSUBAMT")

        is_top_level = bool(main_text.strip())

        if is_top_level:
            # Peek at the next DSPACCNAME row: if it has no BSMAINAMT
            # of its own, this row is a container being exploded into
            # the rows that follow it.
            j = i + 2

            while j < len(children) and children[j].tag.upper() != "DSPACCNAME":
                j += 1

            next_main = ""

            if j < len(children):
                next_amount_node = (
                    children[j + 1] if j + 1 < len(children) else None
                )

                if (
                    next_amount_node is not None
                    and next_amount_node.tag.upper() == "PLAMT"
                ):
                    next_main = _text(next_amount_node, "BSMAINAMT")

            is_container = j < len(children) and not bool(next_main.strip())

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

    # ------------------------------------------------------------
    # Pass 2: split into the trading section vs the P&L section.
    # Container rows are dropped (never rendered) - their children
    # (already flattened above) stand in for them.
    # ------------------------------------------------------------

    has_container = any(entry["is_container"] for entry in entries)

    trading_entries = []
    pl_entries = []

    in_container_children = False
    exited_trading = not has_container

    for entry in entries:
        if entry["is_container"]:
            in_container_children = True
            continue

        if entry["is_group"] and in_container_children:
            # A fresh top-level row right after a container's children
            # ends the trading section - everything from here on
            # belongs to the P&L section proper.
            in_container_children = False
            exited_trading = True

        (pl_entries if exited_trading else trading_entries).append(entry)

    def _rendered_row(entry):
        side = "right" if entry["amount"] >= 0 else "left"

        row = {
            "name": entry["name"],
            "amount": round(abs(entry["amount"]), 2),
            "is_group": entry["is_group"],
        }

        return side, row

    def _split(entry_list):
        left, right = [], []

        for entry in entry_list:
            side, row = _rendered_row(entry)

            (right if side == "right" else left).append(row)

        return left, right

    left_rows, right_rows = [], []

    # --- Trading section (only present when a container was found) ---

    # Note: these are the FULL trading-section totals (all income-side
    # rows vs all expense-side rows in that section), not just the
    # "Sales Accounts" / "Cost of Sales" figures in isolation - a row
    # like Purchase Accounts can land on either side depending on its
    # own sign, so it's folded into whichever total it actually landed
    # in, same as Tally's own screen.
    trading_income_total = 0.0
    trading_expense_total = 0.0
    gross_result = None

    if trading_entries:
        trading_left, trading_right = _split(trading_entries)

        total_left = round(sum(r["amount"] for r in trading_left), 2)
        total_right = round(sum(r["amount"] for r in trading_right), 2)

        trading_income_total = total_right
        trading_expense_total = total_left
        gross_result = round(total_right - total_left, 2)

        if gross_result >= 0:
            trading_left.append(
                {"name": "Gross Profit c/o", "amount": gross_result, "is_group": True}
            )
            carry_row = {"name": "Gross Profit b/f", "amount": gross_result, "is_group": True}
            carry_side = "right"
        else:
            trading_right.append(
                {"name": "Gross Loss c/o", "amount": abs(gross_result), "is_group": True}
            )
            carry_row = {"name": "Gross Loss b/f", "amount": abs(gross_result), "is_group": True}
            carry_side = "left"

        left_rows.extend(trading_left)
        right_rows.extend(trading_right)
    else:
        carry_row = None
        carry_side = None

    # --- P&L section (Indirect Expenses etc., plus the carried-forward
    #     gross result when there was a trading section) ---

    pl_left, pl_right = _split(pl_entries)

    indirect_expenses_amount = 0.0

    for entry in pl_entries:
        if normalize_account_name(entry["name"]) == "indirect expenses":
            indirect_expenses_amount = abs(entry["amount"])

    if carry_row is not None:
        (pl_right if carry_side == "right" else pl_left).append(carry_row)

    total_pl_left = round(sum(r["amount"] for r in pl_left), 2)
    total_pl_right = round(sum(r["amount"] for r in pl_right), 2)

    net_result = round(total_pl_right - total_pl_left, 2)

    if net_result >= 0:
        pl_left.append({"name": "Net Profit", "amount": net_result, "is_group": True})
    else:
        pl_right.append({"name": "Nett Loss", "amount": abs(net_result), "is_group": True})

    left_rows.extend(pl_left)
    right_rows.extend(pl_right)

    return {
        "success": True,
        "left": left_rows,
        "right": right_rows,
        # Extra, non-visual summary fields for callers that need the
        # underlying totals (dashboard cards, chatbot, etc.) without
        # having to re-scan the rendered rows for a "Cost of Sales"
        # line that (correctly) no longer exists in the row list.
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
    Trial Balance rows have separate Debit and Credit columns
    (unlike P&L/Balance Sheet, which are single-amount). Tally's XML
    pairs a <DSPACCNAME> (name) with a sibling <DSPACCINFO> (the
    Dr/Cr amounts, nested one level deeper) - see
    _parse_dspacc_rows / _nested_amount_text for exactly how that's
    unpacked, confirmed against a real raw XML dump.
    """
    root = parse_xml(xml_text)

    rows = _parse_dspacc_rows(root)

    return {
        "success": True,
        "rows": rows,
        "count": len(rows),
    }


# ============================================================
# GROUP SUMMARY (Profit & Loss drill-down)
# ============================================================

def parse_group_summary(xml_text: str, group_name: str | None = None):
    """
    Parse Tally's "Group Summary" display report - the same screen
    Tally shows when you double-click a P&L/Balance Sheet line to see
    the ledgers (or sub-groups) that make it up, e.g. clicking
    "Indirect Expenses" and landing on Office Rent Exp / Sweeper
    Salary / Travelling Expense with their closing Debit/Credit
    balances.

    Same underlying XML shape as Trial Balance - a <DSPACCNAME>
    (name) paired with a sibling <DSPACCINFO> (Dr/Cr amounts, nested
    one level deeper) - see _parse_dspacc_rows / _nested_amount_text.
    """
    root = parse_xml(xml_text)

    rows = _parse_dspacc_rows(root)

    total_debit = round(sum(r["debit"] for r in rows), 2)
    total_credit = round(sum(r["credit"] for r in rows), 2)

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
    root = parse_xml(xml_text)

    rows = []

    for node in root.findall(".//DSPACCNAME"):
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
    root = parse_xml(xml_text)

    rows = []

    for voucher in root.findall(".//VOUCHER"):
        rows.append(
            {
                "date": format_tally_date(
                    _text(voucher, "DATE")
                ),
                "guid": _text(voucher, "GUID"),
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
    root = parse_xml(xml_text)

    rows = []

    # Native outstanding report
    for node in root.findall(".//DSPACCNAME"):
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


# ============================================================
# LEDGER LIST
# ============================================================

def parse_ledger_list(xml_response: str) -> dict:
    """
    Parse ledger master details returned by Tally.

    This is used by chatbot tools to find ledgers,
    their parent groups and opening/closing balances.

    Returns {"success": ..., "ledgers": [...], "count": ...}.
    """

    root = parse_xml(xml_response)

    ledgers = []

    seen = set()

    for ledger in root.findall(".//LEDGER"):
        name = (
            ledger.get("NAME")
            or ledger.findtext("NAME")
            or ""
        ).strip()

        if not name:
            continue

        key = name.casefold()

        if key in seen:
            continue

        seen.add(key)

        # Tally may return the parent group using
        # either CHATPARENTGROUP or PARENT.
        parent = (
            ledger.findtext("CHATPARENTGROUP")
            or ledger.findtext("PARENT")
            or ""
        ).strip()

        opening_balance = to_optional_float(
            ledger.findtext(
                "OPENINGBALANCE"
            )
        )

        closing_balance = to_optional_float(
            ledger.findtext(
                "CLOSINGBALANCE"
            )
        )

        ledgers.append({
            "name": name,
            "parent": parent,
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
            "guid": (ledger.findtext("GUID") or "").strip(),
        })

    return {
        "success": True,
        "ledgers": ledgers,
        "count": len(ledgers),
    }

# STOCK ITEM LIST

def parse_stock_item_list(xml_text: str) -> list[dict]:
    """
    Parse stock item details returned by Tally XML.
    """

    # Clean Tally XML before parsing because inventory data
    # can sometimes contain invalid XML characters.
    root = parse_xml(xml_text)

    stock_items = []

    # Tally returns every inventory item inside a STOCKITEM node.
    for item in root.findall(".//STOCKITEM"):
        name = (
            item.get("NAME")
            or item.findtext("NAME")
            or ""
        ).strip()

        if not name:
            continue

        # Parent normally tells us the stock group/category.
        parent = (
            item.findtext("PARENT")
            or ""
        ).strip()

        # Base unit can be Nos, Pcs, Kg, etc.
        base_unit = (
            item.findtext("BASEUNITS")
            or item.findtext("BASEUNIT")
            or ""
        ).strip()

        # Keep Tally quantity text as-is for now.
        # Example: "10 Nos" or "25 Pcs".
        # We will normalize quantity only after checking real Tally output.
        opening_balance = (
            item.findtext("OPENINGBALANCE")
            or ""
        ).strip()

        closing_balance = (
            item.findtext("CLOSINGBALANCE")
            or ""
        ).strip()

        # Rate and value are also kept as strings first.
        # Tally may include signs or formatting in these fields.
        opening_rate = (
            item.findtext("OPENINGRATE")
            or ""
        ).strip()

        closing_rate = (
            item.findtext("CLOSINGRATE")
            or ""
        ).strip()

        opening_value = (
            item.findtext("OPENINGVALUE")
            or ""
        ).strip()

        closing_value = (
            item.findtext("CLOSINGVALUE")
            or ""
        ).strip()

        stock_items.append({
            "name": name,
            "parent": parent,
            "base_unit": base_unit,
            "opening_balance": opening_balance,
            "opening_rate": opening_rate,
            "opening_value": opening_value,
            "closing_balance": closing_balance,
            "closing_rate": closing_rate,
            "closing_value": closing_value,
        })

    return stock_items


# ============================================================
# LEDGER HELPERS
# ============================================================

def _same_ledger_name(value: str, target: str) -> bool:
    return (
        str(value or "").strip().casefold()
        == str(target or "").strip().casefold()
    )


def _ledger_entry_nodes(voucher):
    """
    Find all ledger entries in a voucher.

    Supports both:
        ALLLEDGERENTRIES.LIST
        LEDGERENTRIES.LIST
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
    Find all inventory entries.
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
    Extract cost centre allocations from a Tally ledger entry.
    """

    allocations = []

    # Tally may place cost centre allocations inside
    # CATEGORYALLOCATIONS.LIST -> COSTCENTREALLOCATIONS.LIST.
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
                allocation.findtext(
                    "AMOUNT"
                )
            )

            allocations.append({
                "cost_centre_name": cost_centre_name,
                "category_name": category_name,
                "amount": round(
                    amount,
                    2,
                ),
            })

    return allocations


def _parse_signed_tally_amount(
    amount_text: str,
    is_deemed_positive: str | None = None,
):
    """
    Convert Tally amount into debit / credit.

    Tally commonly stores:
        ISDEEMEDPOSITIVE = Yes -> debit
        ISDEEMEDPOSITIVE = No  -> credit

    The absolute amount is used for display.
    """

    amount = abs(to_float(amount_text))

    deemed = str(
        is_deemed_positive or ""
    ).strip().casefold()

    if deemed in {"yes", "y", "true", "1"}:
        return amount, 0.0

    return 0.0, amount


def _ledger_entry_particular(
    voucher,
    target_ledger,
):
    """
    Find a useful particular for the ledger row.

    Prefer:
      - party ledger
      - another ledger entry
      - inventory item
      - voucher type
    """

    party = _first_text(
        voucher,
        "PARTYLEDGERNAME",
        "PARTYNAME",
    )

    if party and not _same_ledger_name(
        party,
        target_ledger,
    ):
        return party

    for entry in _ledger_entry_nodes(voucher):
        name = _first_text(
            entry,
            "LEDGERNAME",
            "LEDGER",
        )

        if name and not _same_ledger_name(
            name,
            target_ledger,
        ):
            return name

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
# LEDGER NATIVE ROW PARSER
# ============================================================

def _ledger_report_row_from_node(
    node,
    target_ledger="",
):
    """
    Parse one native Tally LEDINFO/DSP row.
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
    rows = []

    # Primary native ledger structure
    for node in root.findall(".//LEDINFO"):
        row = _ledger_report_row_from_node(
            node,
            target_ledger,
        )

        if row["date"]:
            rows.append(row)

    # Some Tally responses expose DSPVCHDATE blocks
    # without LEDINFO.
    if not rows:
        for node in root.findall(".//DSPVCHDATE"):
            parent = node

            row = _ledger_report_row_from_node(
                parent,
                target_ledger,
            )

            if row["date"]:
                rows.append(row)

    return rows


# ============================================================
# CUSTOM VOUCHER LEDGER PARSER
# ============================================================

# Voucher types that Tally treats as non-accounting (orders /
# pure inventory movement). These vouchers can carry an
# <LEDGERNAME> entry referencing a party for tracking purposes,
# but Tally itself never posts them to that ledger's real Dr/Cr
# balance - so the fallback parser below must not either. This
# mirrors INVENTORY_REGISTERS in app/api/reports.py, which already
# treats these as separate, non-ledger-affecting registers.
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
    Parse normal VOUCHER XML into actual ledger rows.
    """

    rows = []

    for voucher in root.findall(".//VOUCHER"):
        voucher_type_check = _text(
            voucher, "VOUCHERTYPENAME"
        )

        if (voucher_type_check or "").strip().casefold() in NON_ACCOUNTING_VOUCHER_TYPES:
            # Orders and pure inventory vouchers never post to a
            # ledger's real balance in Tally - skip before we even
            # look at its entries.
            continue

        voucher_date = format_tally_date(
            _text(voucher, "DATE")
        )

        if not voucher_date:
            continue

        entries = _ledger_entry_nodes(voucher)

        target_entries = []

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
                target_entries.append(entry)

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

        # Keep party separately for customer and supplier analysis.
        party_name = _first_text(
            voucher,
            "PARTYLEDGERNAME",
            "PARTYNAME",
        )

        # ----------------------------------------------------
        # Read stock item details from this voucher.
        #
        # These details are used later for item-wise sales,
        # purchases and stock movement analysis.
        # ----------------------------------------------------

        stock_items = []

        for inventory_node in _inventory_entry_nodes(
            voucher
        ):
            stock_name = inventory_node.findtext(
                "STOCKITEMNAME",
                ""
            ).strip()

            if not stock_name:
                continue

            stock_items.append({
                "stock_item_name": stock_name,
                "actual_quantity": inventory_node.findtext(
                    "ACTUALQTY",
                    ""
                ).strip(),
                "billed_quantity": inventory_node.findtext(
                    "BILLEDQTY",
                    ""
                ).strip(),
                "rate": inventory_node.findtext(
                    "RATE",
                    ""
                ).strip(),
                "amount": round(
                    to_float(
                        inventory_node.findtext("AMOUNT")
                    ),
                    2
                ),
            })

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
                    # Keep actual Tally amount
                    "tally_amount": round(to_float(amount_text), 2),
                    "debit": debit,
                    "credit": credit,
                    "running_balance": None,
                    "diff_in_tax_amount": 0.0,
                    "balance_after_diff_in_tax": None,
                    "status": "",
                    "narration": narration,
                    "party_name": party_name,
                    # Keep inventory details for item-wise analysis.
                    "stock_items": stock_items,
                    # Keep actual Tally cost centre allocations.
                    "cost_centre_allocations": _cost_centre_allocations(
                        entry
                    ),
                }
            )

    return rows


# ============================================================
# CUSTOM VOUCHER PARSER - XML STRING ENTRY POINT
# ============================================================

def _parse_custom_voucher_ledger_rows(
    xml_text: str,
    target_ledger,
):
    root = parse_xml(xml_text)

    return parse_ledger_voucher_details(
        root,
        target_ledger,
    )


# ============================================================
# VOUCHER DETAIL - single accounting voucher, all ledger lines
#
# Mirrors Tally's "Accounting Voucher Alteration" screen: every
# ledger entry inside one voucher (not just the one ledger being
# browsed), with the amount split into debit / credit, plus the
# voucher's narration / reference. Used by the Ledger report's
# transaction drill-down.
# ============================================================

def parse_voucher_detail(
    xml_text: str,
    voucher_type: str,
    voucher_number: str,
    voucher_date: str | None = None,
):
    root = parse_xml(xml_text)

    vouchers = []

    for voucher in root.findall(".//VOUCHER"):
        v_type = _text(voucher, "VOUCHERTYPENAME")
        v_number = _text(voucher, "VOUCHERNUMBER")

        if not _same_ledger_name(v_type, voucher_type):
            continue

        if str(v_number or "").strip() != str(
            voucher_number or ""
        ).strip():
            continue

        v_date = format_tally_date(_text(voucher, "DATE"))

        if voucher_date and v_date and v_date != voucher_date:
            # Same type/number but a different date - most likely a
            # different voucher (voucher numbers can repeat across
            # periods). Skip it and keep looking for an exact match.
            continue

        is_deleted = _text(voucher, "ISDELETED")
        is_cancelled = _text(voucher, "ISCANCELLED")

        reference = _first_text(
            voucher,
            "REFERENCE",
        )

        reference_date = format_tally_date(
            _first_text(voucher, "REFERENCEDATE")
        )

        narration = _text(voucher, "NARRATION")

        party_name = _first_text(
            voucher,
            "PARTYLEDGERNAME",
            "PARTYNAME",
        )

        entries = []

        for entry in _ledger_entry_nodes(voucher):
            ledger_name = _first_text(
                entry,
                "LEDGERNAME",
                "LEDGER",
            )

            if not ledger_name:
                continue

            amount_text = _first_text(entry, "AMOUNT")
            deemed = _first_text(entry, "ISDEEMEDPOSITIVE")

            debit, credit = _parse_signed_tally_amount(
                amount_text,
                deemed,
            )

            entries.append(
                {
                    "ledger_name": ledger_name,
                    "debit": debit,
                    "credit": credit,
                    "amount": debit if debit else -credit,
                    "is_party_ledger": _same_ledger_name(
                        ledger_name, party_name
                    ),
                }
            )

        total_debit = sum(e["debit"] for e in entries)
        total_credit = sum(e["credit"] for e in entries)

        vouchers.append(
            {
                "date": v_date,
                "voucher_type": v_type,
                "voucher_number": v_number,
                "reference_number": reference,
                "reference_date": reference_date,
                "narration": narration,
                "party_name": party_name,
                "is_deleted": str(is_deleted or "").strip().lower()
                in {"yes", "1", "true"},
                "is_cancelled": str(is_cancelled or "").strip().lower()
                in {"yes", "1", "true"},
                "entries": entries,
                "total_debit": total_debit,
                "total_credit": total_credit,
            }
        )

    return vouchers


# ============================================================
# LEDGER ROW KEY / MERGING
# ============================================================

def _ledger_row_key(row):
    return (
        row.get("date"),
        row.get("particulars"),
        row.get("voucher_type"),
        row.get("voucher_number"),
        round(float(row.get("debit", 0) or 0), 2),
        round(float(row.get("credit", 0) or 0), 2),
        row.get("reference_number"),
        row.get("narration"),
    )


def merge_ledger_rows(
    native_rows,
    custom_rows,
):
    """
    Merge native and fallback rows without duplicating
    identical transactions.
    """

    merged = []
    seen = set()

    for row in list(native_rows) + list(custom_rows):
        key = _ledger_row_key(row)

        if key in seen:
            continue

        seen.add(key)
        merged.append(row)

    return merged


# ============================================================
# LEDGER REPORT
# ============================================================

def _financial_year_start(value):
    return datetime(
        value.year if value.month >= 4 else value.year - 1,
        4,
        1,
    ).date()


def _first_of_month(value: date) -> date:
    return date(value.year, value.month, 1)


def _next_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)

    return date(value.year, value.month + 1, 1)


def build_continuous_monthly_summary(
    rows,
    opening_balance: float,
    start_date: date | None = None,
    end_date: date | None = None,
):
    """
    Build a Tally-style "Ledger Monthly Summary": one row for every
    calendar month between start_date and end_date (inclusive), even
    months with zero transactions - carrying the previous month's
    closing balance forward exactly like Tally does (e.g. July to
    November showing the same closing balance because nothing moved
    in those months).

    rows must already be the final, date-filtered, chronologically
    sorted entries for the ledger (as produced by parse_ledger_report),
    each with 'date' (YYYY-MM-DD), 'debit', 'credit', 'running_balance'.

    If start_date / end_date are not supplied, the range is derived
    from the actual entry dates so months are never fabricated outside
    real data.

    Returns an ordered dict keyed "YYYY-MM" ->
        {
            "month": "Apr-2025",
            "opening_balance": ...,
            "debit": ...,
            "credit": ...,
            "closing_balance": ...,
        }
    """

    raw_months = {}
    row_dates = []

    for row in rows:
        row_date_text = row.get("date")

        if not row_date_text:
            continue

        try:
            row_date = datetime.strptime(
                row_date_text,
                "%Y-%m-%d",
            ).date()
        except ValueError:
            continue

        row_dates.append(row_date)

        key = row_date.strftime("%Y-%m")

        bucket = raw_months.setdefault(
            key,
            {"debit": 0.0, "credit": 0.0, "last_balance": None},
        )

        bucket["debit"] += float(row.get("debit", 0) or 0)
        bucket["credit"] += float(row.get("credit", 0) or 0)

        running_balance = row.get("running_balance")

        if running_balance is not None:
            bucket["last_balance"] = float(running_balance)

    period_start = start_date or (
        min(row_dates) if row_dates else None
    )

    period_end = end_date or (
        max(row_dates) if row_dates else None
    )

    if period_start is None or period_end is None:
        return {}

    result = {}

    cursor = _first_of_month(period_start)
    running_balance = float(opening_balance or 0)

    # Safety cap - never loop more than ~50 years of months even if
    # bad dates somehow slip through.
    max_iterations = 600
    iterations = 0

    while cursor <= period_end and iterations < max_iterations:
        iterations += 1

        key = cursor.strftime("%Y-%m")
        label = cursor.strftime("%b-%Y")

        month_opening = running_balance
        bucket = raw_months.get(key)

        if bucket:
            debit = bucket["debit"]
            credit = bucket["credit"]

            closing_balance = (
                bucket["last_balance"]
                if bucket["last_balance"] is not None
                else (month_opening + debit - credit)
            )
        else:
            debit = 0.0
            credit = 0.0
            closing_balance = month_opening

        result[key] = {
            "month": label,
            "opening_balance": month_opening,
            "debit": debit,
            "credit": credit,
            "closing_balance": closing_balance,
        }

        running_balance = closing_balance
        cursor = _next_month(cursor)

    return result


def parse_ledger_report(
    xml_text: str,
    ledger_name: str,
    opening_balance: float = 0.0,
    closing_balance=None,
    from_date: str | None = None,
    to_date: str | None = None,
):
    """
    Parse ledger report from Tally.

    Important:
    - Does NOT fabricate transactions.
    - Uses actual Tally rows.
    - Calculates running balance only from actual
      debit / credit values when Tally doesn't provide it.
    - Filters rows strictly according to requested dates.
    """

    root = parse_xml(xml_text)

    native_rows = _parse_native_ledger_rows(
        root,
        ledger_name,
    )

    custom_rows = []

    # Native response is preferred.
    # Custom parsing is used if native response does
    # not provide usable rows.
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
    # DATE FILTER
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

    # Normalize rows and sort
    normalized_rows = []

    for row in rows:
        row_date_text = row.get("date")

        if not row_date_text:
            continue

        try:
            row_date = datetime.strptime(
                row_date_text,
                "%Y-%m-%d",
            ).date()
        except ValueError:
            continue

        row["_date_obj"] = row_date

        normalized_rows.append(row)

    normalized_rows.sort(
        key=lambda r: r["_date_obj"]
    )

    # --------------------------------------------------------
    # CALCULATE OPENING BALANCE FOR REQUESTED PERIOD
    #
    # Transactions before from_date are used only to derive
    # the actual opening balance. They are NOT returned as
    # ledger rows.
    # --------------------------------------------------------

    period_opening = float(
        opening_balance or 0
    )

    if start_date:
        for row in normalized_rows:
            if row["_date_obj"] >= start_date:
                break

            period_opening += (
                float(row.get("debit", 0) or 0)
                - float(row.get("credit", 0) or 0)
            )

    # --------------------------------------------------------
    # FILTER TO REQUESTED PERIOD
    # --------------------------------------------------------

    period_rows = []

    for row in normalized_rows:
        row_date = row["_date_obj"]

        if start_date and row_date < start_date:
            continue

        if end_date and row_date > end_date:
            continue

        period_rows.append(row)

    # --------------------------------------------------------
    # RUNNING BALANCE
    # --------------------------------------------------------

    running_balance = period_opening

    final_rows = []

    for row in period_rows:
        debit = float(
            row.get("debit", 0) or 0
        )

        credit = float(
            row.get("credit", 0) or 0
        )

        calculated_balance = (
            running_balance
            + debit
            - credit
        )

        # Use Tally's running balance when it exists.
        # Otherwise use the calculated balance from actual
        # transaction values.
        tally_balance = row.get(
            "running_balance"
        )

        if tally_balance is not None:
            display_balance = float(
                tally_balance
            )
        else:
            display_balance = calculated_balance

        running_balance = calculated_balance

        clean_row = {
            key: value
            for key, value in row.items()
            if key != "_date_obj"
        }

        clean_row["running_balance"] = (
            display_balance
        )

        final_rows.append(clean_row)

    # --------------------------------------------------------
    # TOTALS
    # --------------------------------------------------------

    total_debit = sum(
        float(row.get("debit", 0) or 0)
        for row in final_rows
    )

    total_credit = sum(
        float(row.get("credit", 0) or 0)
        for row in final_rows
    )

    calculated_closing = (
        period_opening
        + total_debit
        - total_credit
    )

    # If no rows exist in requested period, don't blindly
    # return a master closing balance from another period.
    if final_rows:
        period_closing = calculated_closing
    else:
        period_closing = period_opening

    # --------------------------------------------------------
    # MONTHLY SUMMARY
    #
    # Continuous month-by-month buckets (Apr..Mar or whatever range
    # was requested) with the closing balance carried forward through
    # months that had no transactions - matching Tally's own "Ledger
    # Monthly Summary" screen exactly.
    # --------------------------------------------------------

    monthly_summary = build_continuous_monthly_summary(
        final_rows,
        period_opening,
        start_date=start_date,
        end_date=end_date,
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
        "from_date": start_date.isoformat() if start_date else None,
        "to_date": end_date.isoformat() if end_date else None,
    }


# ============================================================
# STOCK SUMMARY
# ============================================================

def _stock_quantity_value(value):
    """
    Extract numeric quantity from strings such as:
        100 Nos
        25.50 Kg
        -10 Nos
    """

    if value is None:
        return 0.0

    text = str(value).strip()

    match = re.search(
        r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)",
        text,
    )

    if not match:
        return 0.0

    return to_float(match.group(0))


def _stock_numeric_value(value):
    """
    Extract numeric stock value/rate.
    """
    return _stock_quantity_value(value)


def parse_stock_summary(xml_text: str):
    root = parse_xml(xml_text)

    rows = []
    seen = set()

    nodes = []

    for node in root.findall(".//STOCKITEM"):
        nodes.append(node)

    for node in root.findall(".//STOCKITEM.LIST"):
        nodes.append(node)

    for node in nodes:
        name = _first_text(
            node,
            "NAME",
            "STOCKITEMNAME",
        )

        if not name:
            continue

        key = name.casefold()

        if key in seen:
            continue

        seen.add(key)

        opening_balance = _stock_quantity_value(
            _text(node, "OPENINGBALANCE")
        )

        closing_balance = _stock_quantity_value(
            _text(node, "CLOSINGBALANCE")
        )

        opening_value = _stock_numeric_value(
            _text(node, "OPENINGVALUE")
        )

        closing_value = _stock_numeric_value(
            _text(node, "CLOSINGVALUE")
        )

        rate = _stock_numeric_value(
            _text(node, "RATE")
        )

        rows.append(
            {
                "name": name,
                "parent": _text(node, "PARENT"),
                "base_units": _text(
                    node,
                    "BASEUNITS",
                ),
                "opening_quantity": opening_balance,
                "opening_value": opening_value,
                "closing_quantity": closing_balance,
                "closing_value": closing_value,
                "rate": rate,
            }
        )

    return {
        "success": True,
        "rows": rows,
        "count": len(rows),
    }


# ============================================================
# STOCK GROUPS
# ============================================================

def parse_stock_groups(xml_text: str):
    root = parse_xml(xml_text)

    rows = []
    seen = set()

    for node in root.findall(".//STOCKGROUP"):
        name = _first_text(
            node,
            "NAME",
        )

        if not name:
            continue

        key = name.casefold()

        if key in seen:
            continue

        seen.add(key)

        rows.append(
            {
                "name": name,
                "parent": _text(
                    node,
                    "PARENT",
                ),
                "is_addable": _text(
                    node,
                    "ISADDABLE",
                ),
                "base_units": _text(
                    node,
                    "BASEUNITS",
                ),
            }
        )

    return {
        "success": True,
        "rows": rows,
        "count": len(rows),
    }


# ============================================================
# STOCK CATEGORIES
# ============================================================

def parse_stock_categories(xml_text: str):
    root = parse_xml(xml_text)

    rows = []
    seen = set()

    for node in root.findall(".//STOCKCATEGORY"):
        name = _first_text(
            node,
            "NAME",
        )

        if not name:
            continue

        key = name.casefold()

        if key in seen:
            continue

        seen.add(key)

        rows.append(
            {
                "name": name,
                "parent": _text(
                    node,
                    "PARENT",
                ),
            }
        )

    return {
        "success": True,
        "rows": rows,
        "count": len(rows),
    }


# ============================================================
# GODOWNS
# ============================================================

def parse_godowns(xml_text: str):
    root = parse_xml(xml_text)

    rows = []
    seen = set()

    for node in root.findall(".//GODOWN"):
        name = _first_text(
            node,
            "NAME",
        )

        if not name:
            continue

        key = name.casefold()

        if key in seen:
            continue

        seen.add(key)

        rows.append(
            {
                "name": name,
                "parent": _text(
                    node,
                    "PARENT",
                ),
                "is_internal": _text(
                    node,
                    "ISINTERNAL",
                ),
            }
        )

    return {
        "success": True,
        "rows": rows,
        "count": len(rows),
    }


# ============================================================
# STOCK MOVEMENT
# ============================================================

def parse_stock_movement(xml_text: str):
    root = parse_xml(xml_text)

    rows = []
    seen = set()

    vouchers = root.findall(".//VOUCHER")

    for voucher in vouchers:
        voucher_date = format_tally_date(
            _text(voucher, "DATE")
        )

        voucher_type = _text(
            voucher,
            "VOUCHERTYPENAME",
        )

        voucher_number = _text(
            voucher,
            "VOUCHERNUMBER",
        )

        guid = _text(
            voucher,
            "GUID",
        )

        reference = _text(
            voucher,
            "REFERENCE",
        )

        party = _first_text(
            voucher,
            "PARTYLEDGERNAME",
            "PARTYNAME",
        )

        narration = _text(
            voucher,
            "NARRATION",
        )

        inventory_entries = _inventory_entry_nodes(
            voucher
        )

        for entry in inventory_entries:
            stock_item = _first_text(
                entry,
                "STOCKITEMNAME",
                "STOCKITEM",
            )

            if not stock_item:
                continue

            quantity = _stock_quantity_value(
                _text(entry, "ACTUALQTY")
                or _text(entry, "BILLEDQTY")
                or _text(entry, "QTY")
            )

            rate = _stock_numeric_value(
                _text(entry, "RATE")
            )

            amount = _stock_numeric_value(
                _text(entry, "AMOUNT")
            )

            godown = _first_text(
                entry,
                "GODOWNNAME",
                "GODOWN",
            )

            batch = _first_text(
                entry,
                "BATCHNAME",
                "BATCH",
            )

            key = (
                guid,
                voucher_date,
                voucher_type,
                voucher_number,
                stock_item,
                quantity,
                amount,
            )

            if key in seen:
                continue

            seen.add(key)

            rows.append(
                {
                    "date": voucher_date,
                    "guid": guid,
                    "voucher_type": voucher_type,
                    "voucher_number": voucher_number,
                    "reference": reference,
                    "party": party,
                    "stock_item": stock_item,
                    "quantity": quantity,
                    "rate": rate,
                    "amount": amount,
                    "godown": godown,
                    "batch": batch,
                    "narration": narration,
                }
            )

    return {
        "success": True,
        "rows": rows,
        "count": len(rows),
    }


# ============================================================
# INVENTORY REGISTER
# ============================================================

def parse_inventory_register(xml_text: str):
    root = parse_xml(xml_text)

    rows = []
    seen = set()

    for voucher in root.findall(".//VOUCHER"):
        voucher_date = format_tally_date(
            _text(voucher, "DATE")
        )

        guid = _text(
            voucher,
            "GUID",
        )

        voucher_type = _text(
            voucher,
            "VOUCHERTYPENAME",
        )

        voucher_number = _text(
            voucher,
            "VOUCHERNUMBER",
        )

        party = _first_text(
            voucher,
            "PARTYLEDGERNAME",
            "PARTYNAME",
        )

        narration = _text(
            voucher,
            "NARRATION",
        )

        for entry in _inventory_entry_nodes(
            voucher
        ):
            stock_item = _first_text(
                entry,
                "STOCKITEMNAME",
                "STOCKITEM",
            )

            if not stock_item:
                continue

            quantity = _stock_quantity_value(
                _text(entry, "ACTUALQTY")
                or _text(entry, "BILLEDQTY")
                or _text(entry, "QTY")
            )

            rate = _stock_numeric_value(
                _text(entry, "RATE")
            )

            amount = _stock_numeric_value(
                _text(entry, "AMOUNT")
            )

            key = (
                guid,
                voucher_date,
                voucher_type,
                voucher_number,
                stock_item,
                quantity,
                amount,
            )

            if key in seen:
                continue

            seen.add(key)

            rows.append(
                {
                    "date": voucher_date,
                    "guid": guid,
                    "voucher_type": voucher_type,
                    "voucher_number": voucher_number,
                    "party": party,
                    "stock_item": stock_item,
                    "quantity": quantity,
                    "rate": rate,
                    "amount": amount,
                    "narration": narration,
                }
            )

    return {
        "success": True,
        "rows": rows,
        "count": len(rows),
    }


# ============================================================
# INVENTORY REGISTER SUMMARY
# ============================================================

def parse_inventory_register_summary(xml_text: str):
    detail = parse_inventory_register(
        xml_text
    )

    rows = detail.get("rows", [])

    voucher_keys = set()

    for row in rows:
        voucher_keys.add(
            (
                row.get("guid"),
                row.get("date"),
                row.get("voucher_type"),
                row.get("voucher_number"),
            )
        )

    return {
        "success": True,
        "rows": rows,
        "count": len(rows),
        "voucher_count": len(voucher_keys),
    }


# ============================================================
# STOCK VALUATION
# ============================================================

def parse_stock_valuation(xml_text: str):
    summary = parse_stock_summary(
        xml_text
    )

    rows = []

    for row in summary.get("rows", []):
        rows.append(
            {
                "name": row.get("name"),
                "quantity": row.get(
                    "closing_quantity",
                    0,
                ),
                "rate": row.get(
                    "rate",
                    0,
                ),
                "value": row.get(
                    "closing_value",
                    0,
                ),
                "base_units": row.get(
                    "base_units",
                    "",
                ),
            }
        )

    return {
        "success": True,
        "rows": rows,
        "count": len(rows),
    }


# ============================================================
# NEGATIVE STOCK
# ============================================================

def parse_negative_stock(xml_text: str):
    summary = parse_stock_summary(
        xml_text
    )

    rows = []

    for row in summary.get("rows", []):
        quantity = float(
            row.get(
                "closing_quantity",
                0,
            )
            or 0
        )

        if quantity < 0:
            rows.append(
                row
            )

    return {
        "success": True,
        "rows": rows,
        "count": len(rows),
    }