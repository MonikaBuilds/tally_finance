"""
Native Tally figures shared by the chatbot.

These helpers send exactly the requests the dashboard already uses and
return the totals Tally itself prints (report footers, group closing
balances, Nett Profit/Loss rows). Nothing here adds, nets or rebuilds
an amount: Python only selects rows and checks which period Tally used.
"""

from __future__ import annotations

import logging
from datetime import date

from app.api.dashboard_mapper import exact_row, purchase_row, verified_period
from app.tally.client import TallyClient
from app.tally.dashboard import (
    collection_request,
    html_amount,
    parse_balances,
    parse_native_table,
    parse_outstanding_table,
    parse_profit_loss_rows,
    report_request,
)
from app.tally.xml_builders.financial import (
    build_bills_payable_request,
    build_bills_receivable_request,
    build_profit_loss_request,
)

logger = logging.getLogger(__name__)

_client = TallyClient()

CASH_GROUP = "Cash-in-Hand"
BANK_GROUPS = ("Bank Accounts", "Bank OD A/c")


# ============================================================
# OUTSTANDING BILLS (Bills Receivable / Bills Payable)
# ============================================================

async def fetch_native_outstanding(
    kind: str,
    company_name: str | None,
    as_of: date | None = None,
) -> dict:
    """
    Native Bills Receivable / Bills Payable as on a date.

    Returns the bills exactly as Tally lists them (signed amounts: an
    advance stays negative) and the report's own Pending Amount footer.
    """
    builder = (
        build_bills_receivable_request
        if kind == "receivable"
        else build_bills_payable_request
    )
    as_of = as_of or date.today()

    raw = await _client.send_xml(
        report_request(builder(company_name), html=True, as_of=as_of)
    )

    try:
        report = parse_outstanding_table(raw)
    except ValueError:
        table = parse_native_table(raw)
        has_pending_column = any(
            "Pending" in (cell or "")
            for row in table["rows"]
            for cell in row
        )
        if has_pending_column:
            # Columns exist but were not understood: never guess.
            raise
        # Tally printed the report without any bill table: no pending bills.
        report = {**table, "bills": [], "total": None, "raw_total": None}

    return {
        "bills": report.get("bills", []),
        "total": report.get("total"),
        "raw_total": report.get("raw_total"),
        "tally_from_date": report.get("from_date"),
        "tally_to_date": report.get("to_date"),
        "requested_as_of": as_of.isoformat(),
    }


# ============================================================
# GROUP / LEDGER CLOSING BALANCES
# ============================================================

async def fetch_native_balances(
    kind: str,
    company_name: str | None,
    as_of: date | None = None,
) -> list[dict]:
    """Closing balances of every Group or Ledger (Tally sign: negative = Dr)."""
    raw = await _client.send_xml(
        collection_request(company_name, as_of or date.today(), kind)
    )
    return parse_balances(raw, kind)


def group_identity(group: dict) -> str:
    return (group.get("reserved_name") or group.get("name") or "").strip()


def ledgers_under_groups(
    groups: list[dict],
    ledgers: list[dict],
    root_groups: set[str],
) -> list[tuple[dict, str]]:
    """
    Ledgers whose parent chain reaches one of root_groups, at any depth.
    Returns (ledger, root_group) pairs.
    """
    by_name = {group.get("name"): group for group in groups if group.get("name")}
    roots = {name.casefold() for name in root_groups}

    def root_of(parent: str | None) -> str | None:
        seen = set()
        while parent and parent not in seen:
            seen.add(parent)
            group = by_name.get(parent, {"name": parent})
            identity = group_identity(group)
            if identity.casefold() in roots:
                return identity
            if parent.casefold() in roots:
                return parent
            parent = group.get("parent")
        return None

    matched = []
    for ledger in ledgers:
        root = root_of(ledger.get("parent"))
        if root:
            matched.append((ledger, root))
    return matched


def dr_cr(amount: float | None) -> tuple[float | None, str | None]:
    """Tally exports Dr balances as negative numbers. Present them as Dr/Cr."""
    if amount is None:
        return None, None
    if amount == 0:
        return 0.0, None
    return (abs(amount), "Dr") if amount < 0 else (abs(amount), "Cr")


# ============================================================
# PROFIT & LOSS
# ============================================================

def _html_result(native_pl: dict, *names: str) -> dict | None:
    matches = []
    for cells in native_pl.get("rows", []):
        nonempty = [cell for cell in cells if cell]
        if len(nonempty) == 2 and nonempty[0] in names:
            matches.append({
                "name": nonempty[0],
                "amount": html_amount(nonempty[1]),
                "raw": nonempty[1],
            })
    return matches[0] if len(matches) == 1 else None


def _line(rows: list[dict], *names: str) -> dict | None:
    row = exact_row(rows, *names)
    if row is None:
        return None
    return {"name": row["name"], "amount": row.get("amount"), "raw": row.get("raw")}


async def fetch_native_profit_loss_summary(
    company_name: str | None,
    from_date: date | None,
    to_date: date | None,
) -> dict:
    """
    Headline P&L lines exactly as Tally prints them.

    `period_verified` is False when Tally used a different period than
    requested (it does so silently); callers must then not present the
    figures as belonging to the requested period.
    """
    request = build_profit_loss_request(
        company_name=company_name,
        from_date=from_date,
        to_date=to_date,
    )

    rows = parse_profit_loss_rows(await _client.send_xml(request))
    native = parse_native_table(
        await _client.send_xml(report_request(request, html=True))
    )

    if from_date and to_date:
        period_verified = verified_period(native, from_date, to_date, company_name)
    else:
        period_verified = bool(native.get("from_date") and native.get("to_date"))

    nett_profit = _html_result(native, "Nett Profit", "Net Profit")
    nett_loss = _html_result(native, "Nett Loss", "Net Loss")

    purchases = purchase_row(rows)

    return {
        "period_verified": period_verified,
        "tally_from_date": native.get("from_date"),
        "tally_to_date": native.get("to_date"),
        "requested_from_date": from_date.isoformat() if from_date else None,
        "requested_to_date": to_date.isoformat() if to_date else None,
        "lines": {
            "sales_accounts": _line(rows, "Sales Accounts"),
            "direct_incomes": _line(rows, "Direct Incomes", "Direct Income"),
            "indirect_incomes": _line(rows, "Indirect Incomes", "Indirect Income"),
            "cost_of_sales": _line(rows, "Cost of Sales :", "Cost of Sales", "Cost of Sales:"),
            "purchase_accounts": (
                {"name": purchases["name"], "amount": purchases.get("amount"), "raw": purchases.get("raw")}
                if purchases else None
            ),
            "direct_expenses": _line(rows, "Direct Expenses", "Direct Expense"),
            "indirect_expenses": _line(rows, "Indirect Expenses", "Indirect Expense"),
            "opening_stock": _line(rows, "Opening Stock"),
            "closing_stock": _line(rows, "Closing Stock", "Less: Closing Stock"),
        },
        "nett_profit": nett_profit,
        "nett_loss": nett_loss,
    }
