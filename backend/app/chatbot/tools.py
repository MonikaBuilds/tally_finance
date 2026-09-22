from app.chatbot.resolver import resolve_party_name, resolve_name
from datetime import date
from app.tally.parsers.common import to_optional_float
from calendar import monthrange
import re
import asyncio
import time

from app.tally.service import fetch_stock_item_list

from app.tally.service import (
    fetch_profit_loss,
    fetch_trial_balance,
    fetch_balance_sheet,
    fetch_bill_allocations,
    fetch_bills_receivable,
    fetch_bills_payable,
    fetch_ledger_list,
    fetch_ledger_report
)

from app.financial.service import (
    build_outstanding_summary,
    build_receivables_from_tally_report,
    build_payables_from_tally_report,
    build_pending_invoices_from_reports
)

from app.financial.calculations import (
    build_dashboard_financials
)


def _success(data: dict) -> dict:
    return {
        "success": True,
        "source": "tally",
        "data": data
    }


def _no_data(message: str) -> dict:
    return {
        "success": False,
        "source": "tally",
        "message": message,
        "data": None
    }

def _recalculate_statement_balances(
    transactions: list[dict],
    opening_balance: float = 0.0,
) -> tuple[list[dict], float]:
    """
    Recalculate running balances after non-posted vouchers
    such as orders are removed from a party statement.
    """

    running_balance = float(
        opening_balance or 0
    )

    recalculated_transactions = []

    for transaction in transactions:

        row = dict(transaction)

        debit = float(
            row.get("debit", 0) or 0
        )

        credit = float(
            row.get("credit", 0) or 0
        )

        running_balance += (
            debit - credit
        )

        row["running_balance"] = round(
            running_balance,
            2,
        )

        recalculated_transactions.append(
            row
        )

    return (
        recalculated_transactions,
        round(running_balance, 2),
    )
def _parse_tally_quantity(value: str | None) -> float:
    """
    Convert a Tally quantity such as '18 NOS' or '-5 NOS'
    into a numeric value.

    The unit is kept out of the calculation because different
    stock items may use different units.
    """

    if value is None:
        return 0.0

    text = str(value).strip()

    if not text:
        return 0.0

    match = re.search(
        r"[-+]?\d[\d,]*(?:\.\d+)?",
        text,
    )

    if not match:
        return 0.0

    try:
        return float(
            match.group(0).replace(",", "")
        )
    except ValueError:
        return 0.0
    
async def _load_receivables(
    company_name: str | None = None
):
    receivable_bills = await fetch_bills_receivable(
        company_name=company_name
    )

    allocations = await fetch_bill_allocations(
        company_name=company_name
    )

    outstanding = build_outstanding_summary(
        allocations
    )

    return build_receivables_from_tally_report(
        receivable_bills,
        outstanding
    )


async def _load_payables(
    company_name: str | None = None
):
    payable_bills = await fetch_bills_payable(
        company_name=company_name
    )

    allocations = await fetch_bill_allocations(
        company_name=company_name
    )

    outstanding = build_outstanding_summary(
        allocations
    )

    return build_payables_from_tally_report(
        payable_bills,
        outstanding
    )
    
async def _timed_call(name: str, coro):
    start = time.perf_counter()

    try:
        result = await coro
        duration = time.perf_counter() - start

        # Temporary log to check how long each Tally request takes.
        print(f"OUTSTANDING DEBUG: {name} completed in {duration:.2f}s")

        return result

    except Exception as exc:
        duration = time.perf_counter() - start

        print(
            f"OUTSTANDING DEBUG: {name} failed after "
            f"{duration:.2f}s -> {type(exc).__name__}: {exc}"
        )
        raise
    
async def _load_outstanding_data(
    company_name: str | None = None,
):
    """
    Load receivables, payables and bill allocations from Tally.

    These reports can be heavy for Tally, so we request them
    one at a time instead of sending all three together.
    """

    # Tally may process heavy XML reports slowly when several
    # requests arrive at the same time, so keep these sequential.
    receivable_bills = await _timed_call(
        "receivables",
        fetch_bills_receivable(
            company_name=company_name,
        ),
    )

    payable_bills = await _timed_call(
        "payables",
        fetch_bills_payable(
            company_name=company_name,
        ),
    )

    allocations = await _timed_call(
        "bill_allocations",
        fetch_bill_allocations(
            company_name=company_name,
        ),
    )

    # Bill allocations tell us how much is still outstanding
    # after receipts, payments and other adjustments.
    outstanding = build_outstanding_summary(
        allocations,
    )

    receivables = build_receivables_from_tally_report(
        receivable_bills,
        outstanding,
    )

    payables = build_payables_from_tally_report(
        payable_bills,
        outstanding,
    )

    return receivables, payables

async def _load_profit_loss_summary(
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Load only the Profit & Loss data required for revenue,
    expenses and net-profit queries.

    These queries do not need receivables, payables or bill allocations,
    so keeping this path lightweight avoids unnecessary Tally requests.
    """

    profit_loss = await fetch_profit_loss(
        from_date=from_date,
        to_date=to_date,
        company_name=company_name,
    )

    # Reuse the existing accounting calculation logic instead of
    # duplicating revenue and expense calculations in the chatbot.
    return build_dashboard_financials(
        profit_loss=profit_loss,
        receivables={},
        payables={},
        pending_invoices={},
    )

async def _load_financial_summary(
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None
) -> dict:
    profit_loss = await fetch_profit_loss(
        from_date=from_date,
        to_date=to_date,
        company_name=company_name
    )

    receivables, payables = await _load_outstanding_data(
        company_name=company_name
    )

    pending_invoices = build_pending_invoices_from_reports(
        receivables,
        payables
    )

    return build_dashboard_financials(
        profit_loss=profit_loss,
        receivables=receivables,
        payables=payables,
        pending_invoices=pending_invoices
    )

def _build_aging_summary(
    bills: list[dict],
    minimum_days: int | None = None
) -> dict:
    overdue_bills = [
        bill
        for bill in bills
        if bill.get("overdue_days", 0) > 0
    ]

    if minimum_days is not None:
        minimum_days = max(
            1,
            min(int(minimum_days), 3650)
        )

        overdue_bills = [
            bill
            for bill in overdue_bills
            if bill.get("overdue_days", 0) >= minimum_days
        ]

    overdue_bills = sorted(
        overdue_bills,
        key=lambda bill: (
            bill.get("overdue_days", 0),
            bill.get("outstanding_amount", 0.0)
        ),
        reverse=True
    )

    buckets = {
        "1_30": {
            "count": 0,
            "amount": 0.0
        },
        "31_60": {
            "count": 0,
            "amount": 0.0
        },
        "61_90": {
            "count": 0,
            "amount": 0.0
        },
        "91_plus": {
            "count": 0,
            "amount": 0.0
        }
    }

    for bill in overdue_bills:
        days = bill.get(
            "overdue_days",
            0
        )

        amount = bill.get(
            "outstanding_amount",
            0.0
        )

        if days <= 30:
            bucket = "1_30"
        elif days <= 60:
            bucket = "31_60"
        elif days <= 90:
            bucket = "61_90"
        else:
            bucket = "91_plus"

        buckets[bucket]["count"] += 1
        buckets[bucket]["amount"] += amount

    for bucket in buckets.values():
        bucket["amount"] = round(
            bucket["amount"],
            2
        )

    total = sum(
        bill.get(
            "outstanding_amount",
            0.0
        )
        for bill in overdue_bills
    )

    return {
        "minimum_days": minimum_days,
        "total_overdue": round(total, 2),
        "count": len(overdue_bills),
        "buckets": buckets,
        "bills": overdue_bills
    }
    
async def get_receivables_tool(
    company_name: str | None = None
) -> dict:
    receivables = await _load_receivables(
        company_name=company_name
    )

    return _success(receivables)
 

async def get_payables_tool(
    company_name: str | None = None
) -> dict:
    payables = await _load_payables(
        company_name=company_name
    )

    return _success(payables)


async def get_pending_invoices_tool(
    company_name: str | None = None
) -> dict:
    receivables, payables = await _load_outstanding_data(
        company_name=company_name
    )

    pending = build_pending_invoices_from_reports(
        receivables,
        payables
    )

    return _success(pending)


async def get_invoice_status_tool(
    invoice_reference: str,
    company_name: str | None = None,
) -> dict:
    """
    Search for an invoice in the current Tally
    receivable and payable outstanding data.
    """

    if (
        not invoice_reference
        or not invoice_reference.strip()
    ):
        return _no_data(
            "Please provide an invoice or bill reference."
        )

    receivables, payables = await _load_outstanding_data(
        company_name=company_name
    )

    requested_reference = (
        invoice_reference.strip().casefold()
    )

    matches = []

    for bill in receivables.get(
        "bills",
        [],
    ) or []:
        bill_reference = str(
            bill.get(
                "bill_reference",
                "",
            )
            or ""
        ).strip()

        if (
            bill_reference.casefold()
            != requested_reference
        ):
            continue

        outstanding_amount = float(
            bill.get(
                "outstanding_amount",
                0,
            )
            or 0
        )

        overdue_days = int(
            bill.get(
                "overdue_days",
                0,
            )
            or 0
        )

        status = (
            "overdue"
            if overdue_days > 0
            else "outstanding"
        )

        matches.append({
            "party": bill.get("party"),
            "bill_reference": bill_reference,
            "bill_date": bill.get("bill_date"),
            "due_date": bill.get("due_date"),
            "outstanding_amount": round(
                outstanding_amount,
                2,
            ),
            "overdue_days": overdue_days,
            "type": bill.get("type"),
            "status": status,
        })

    for bill in payables.get(
        "bills",
        [],
    ) or []:
        bill_reference = str(
            bill.get(
                "bill_reference",
                "",
            )
            or ""
        ).strip()

        if (
            bill_reference.casefold()
            != requested_reference
        ):
            continue

        outstanding_amount = float(
            bill.get(
                "outstanding_amount",
                0,
            )
            or 0
        )

        overdue_days = int(
            bill.get(
                "overdue_days",
                0,
            )
            or 0
        )

        status = (
            "overdue"
            if overdue_days > 0
            else "outstanding"
        )

        matches.append({
            "party": bill.get("party"),
            "bill_reference": bill_reference,
            "bill_date": bill.get("bill_date"),
            "due_date": bill.get("due_date"),
            "outstanding_amount": round(
                outstanding_amount,
                2,
            ),
            "overdue_days": overdue_days,
            "type": bill.get("type"),
            "status": status,
        })

    if not matches:
        return _no_data(
            "This invoice was not found in the current "
            "outstanding receivable or payable data. "
            "Its paid or cancelled status cannot be "
            "confirmed from the outstanding report alone."
        )

    return _success({
        "invoice_reference": invoice_reference.strip(),
        "matches": matches,
        "count": len(matches),
    })
    
async def get_overdue_invoices_tool(
    company_name: str | None = None
) -> dict:
    # Temporary logs to see where the Tally request is getting stuck.
    print("OVERDUE: starting outstanding fetch")

    receivables, payables = await _load_outstanding_data(
        company_name=company_name
    )

    print("OVERDUE: outstanding fetch completed")
    print("OVERDUE: receivables =", len(receivables))
    print("OVERDUE: payables =", len(payables))

    pending = build_pending_invoices_from_reports(
        receivables,
        payables
    )

    overdue = [
        invoice
        for invoice in pending
        if invoice.get("overdue_days", 0) > 0
    ]

    return _success({
        "count": len(overdue),
        "invoices": overdue,
    })
    
    
async def get_highest_receivable_tool(
    company_name: str | None = None
) -> dict:
    receivables = await _load_receivables(
        company_name=company_name
    )

    bills = receivables.get("bills", [])

    if not bills:
        return _no_data(
            "No outstanding receivables were found in Tally."
        )

    highest = max(
        bills,
        key=lambda bill: bill.get(
            "outstanding_amount",
            0.0
        )
    )

    return _success({
        "party": highest.get("party"),
        "bill_reference": highest.get(
            "bill_reference"
        ),
        "amount": highest.get(
            "outstanding_amount",
            0.0
        ),
        "due_date": highest.get("due_date"),
        "overdue_days": highest.get(
            "overdue_days",
            0
        )
    })


async def get_highest_payable_tool(
    company_name: str | None = None
) -> dict:
    payables = await _load_payables(
        company_name=company_name
    )

    bills = payables.get("bills", [])

    if not bills:
        return _no_data(
            "No outstanding payables were found in Tally."
        )

    highest = max(
        bills,
        key=lambda bill: bill.get(
            "outstanding_amount",
            0.0
        )
    )

    return _success({
        "party": highest.get("party"),
        "bill_reference": highest.get(
            "bill_reference"
        ),
        "amount": highest.get(
            "outstanding_amount",
            0.0
        ),
        "due_date": highest.get("due_date"),
        "overdue_days": highest.get(
            "overdue_days",
            0
        )
    })


async def get_overdue_receivables_tool(
    company_name: str | None = None
) -> dict:
    receivables = await _load_receivables(
        company_name=company_name
    )

    overdue_bills = [
        bill
        for bill in receivables.get("bills", [])
        if bill.get("overdue_days", 0) > 0
    ]

    total = sum(
        bill.get("outstanding_amount", 0.0)
        for bill in overdue_bills
    )

    return _success({
        "total_overdue": round(total, 2),
        "count": len(overdue_bills),
        "bills": overdue_bills
    })


async def get_overdue_payables_tool(
    company_name: str | None = None
) -> dict:
    payables = await _load_payables(
        company_name=company_name
    )

    overdue_bills = [
        bill
        for bill in payables.get("bills", [])
        if bill.get("overdue_days", 0) > 0
    ]

    total = sum(
        bill.get("outstanding_amount", 0.0)
        for bill in overdue_bills
    )

    return _success({
        "total_overdue": round(total, 2),
        "count": len(overdue_bills),
        "bills": overdue_bills
    })


async def get_revenue_tool(
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None
) -> dict:
    # Revenue/expense/profit values come from the P&L report.
    # Avoid loading unrelated outstanding data for these simple queries.
    summary = await _load_profit_loss_summary(
        company_name=company_name,
        from_date=from_date,
        to_date=to_date,
    )

    return _success({
        "revenue": summary.get(
            "revenue",
            0.0
        ),
        "from_date": (
            from_date.isoformat()
            if from_date
            else None
        ),
        "to_date": (
            to_date.isoformat()
            if to_date
            else None
        )
    })


async def get_expenses_tool(
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None
) -> dict:
    summary = await _load_financial_summary(
        company_name=company_name,
        from_date=from_date,
        to_date=to_date
    )

    return _success({
        "expenses": summary.get(
            "expenses",
            0.0
        ),
        "from_date": (
            from_date.isoformat()
            if from_date
            else None
        ),
        "to_date": (
            to_date.isoformat()
            if to_date
            else None
        )
    })


async def get_net_profit_tool(
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None
) -> dict:
    summary = await _load_financial_summary(
        company_name=company_name,
        from_date=from_date,
        to_date=to_date
    )

    net_profit = summary.get(
        "net_profit",
        0.0
    )

    result_type = (
        "profit"
        if net_profit >= 0
        else "loss"
    )

    return _success({
        "net_profit": net_profit,
        "result_type": result_type,
        "amount": abs(net_profit),
        "from_date": (
            from_date.isoformat()
            if from_date
            else None
        ),
        "to_date": (
            to_date.isoformat()
            if to_date
            else None
        )
    })


async def get_profit_loss_tool(
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None
) -> dict:
    report = await fetch_profit_loss(
        from_date=from_date,
        to_date=to_date,
        company_name=company_name
    )

    return _success({
        "report": report,
        "count": len(report),
        "from_date": (
            from_date.isoformat()
            if from_date
            else None
        ),
        "to_date": (
            to_date.isoformat()
            if to_date
            else None
        )
    })


async def get_trial_balance_tool(
    company_name: str | None = None,
    to_date: date | None = None
) -> dict:
    report = await fetch_trial_balance(
        company_name=company_name,
        to_date=to_date
    )

    return _success({
        "report": report,
        "count": len(report),
        "to_date": (
            to_date.isoformat()
            if to_date
            else None
        )
    })


async def get_balance_sheet_tool(
    company_name: str | None = None,
    to_date: date | None = None
) -> dict:
    report = await fetch_balance_sheet(
        company_name=company_name,
        to_date=to_date
    )

    return _success({
        "report": report,
        "count": len(report),
        "to_date": (
            to_date.isoformat()
            if to_date
            else None
        )
    })
    
def _collect_party_names(
    receivables: dict,
    payables: dict
) -> list[str]:
    names = []

    for bill in receivables.get("bills", []):
        party = bill.get("party")

        if party:
            names.append(party)

    for bill in payables.get("bills", []):
        party = bill.get("party")

        if party:
            names.append(party)

    return list(dict.fromkeys(names))


async def get_party_outstanding_summary_tool(
    party_name: str,
    company_name: str | None = None
) -> dict:
    if not party_name or not party_name.strip():
        return _no_data(
            "Please provide a party name."
        )

    receivables, payables = await _load_outstanding_data(
        company_name=company_name
    )

    available_party_names = _collect_party_names(
        receivables,
        payables
    )

    resolution = resolve_party_name(
        requested_name=party_name,
        party_names=available_party_names
    )

    if resolution.status == "not_found":
        return _no_data(
            "No matching party was found in Tally."
        )

    if resolution.status == "ambiguous":
        return {
            "success": False,
            "source": "tally",
            "message": (
                "Multiple matching parties were found. "
                "Please provide a more specific party name."
            ),
            "data": {
                "matches": resolution.matches or []
            }
        }

    if resolution.status != "resolved":
        return _no_data(
            "Unable to resolve the requested party."
        )

    resolved_party = resolution.value

    receivable_bills = [
        bill
        for bill in receivables.get("bills", [])
        if bill.get("party") == resolved_party
    ]

    payable_bills = [
        bill
        for bill in payables.get("bills", [])
        if bill.get("party") == resolved_party
    ]

    total_receivable = sum(
        bill.get(
            "outstanding_amount",
            0.0
        )
        for bill in receivable_bills
    )

    total_payable = sum(
        bill.get(
            "outstanding_amount",
            0.0
        )
        for bill in payable_bills
    )

    return _success({
        "party": resolved_party,
        "total_receivable": round(
            total_receivable,
            2
        ),
        "total_payable": round(
            total_payable,
            2
        ),
        "receivable_count": len(
            receivable_bills
        ),
        "payable_count": len(
            payable_bills
        ),
        "receivable_bills": receivable_bills,
        "payable_bills": payable_bills
    })

async def get_ledger_report_tool(
    ledger_name: str,
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None
) -> dict:
    if not ledger_name or not ledger_name.strip():
        return _no_data(
            "Please provide a ledger name."
        )

    ledgers = await fetch_ledger_list(
        company_name=company_name
    )

    available_ledger_names = [
        ledger["name"]
        for ledger in ledgers
        if ledger.get("name")
    ]

    resolution = resolve_name(
        requested_name=ledger_name,
        available_names=available_ledger_names
    )

    if resolution.status == "not_found":
        return _no_data(
            "No matching ledger was found in Tally."
        )

    if resolution.status == "ambiguous":
        return {
            "success": False,
            "source": "tally",
            "message": (
                "Multiple matching ledgers were found. "
                "Please provide a more specific ledger name."
            ),
            "data": {
                "matches": resolution.matches or []
            }
        }

    if resolution.status != "resolved":
        return _no_data(
            "Unable to resolve the requested ledger."
        )

    resolved_ledger = resolution.value

    report = await fetch_ledger_report(
        ledger_name=resolved_ledger,
        company_name=company_name,
        from_date=from_date,
        to_date=to_date
    )

    entries = report.get("entries", [])

    return _success({
        "ledger_name": report.get(
            "ledger_name",
            resolved_ledger
        ),
        "opening_balance": report.get(
            "opening_balance",
        ),
        "closing_balance": report.get(
            "closing_balance",
        ),
        "entry_count": len(entries),
        "entries": entries,
        "from_date": (
            from_date.isoformat()
            if from_date
            else None
        ),
        "to_date": (
            to_date.isoformat()
            if to_date
            else None
        )
    })

async def get_bank_transactions_tool(
    ledger_name: str,
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Return transaction history for a cash or bank ledger
    using actual Tally ledger voucher data.
    """

    if not ledger_name or not ledger_name.strip():
        return _no_data(
            "Please provide a cash or bank ledger name."
        )

    ledgers = await fetch_ledger_list(
        company_name=company_name
    )

    available_ledger_names = [
        ledger["name"]
        for ledger in ledgers
        if ledger.get("name")
    ]

    resolution = resolve_name(
        requested_name=ledger_name,
        available_names=available_ledger_names,
    )

    if resolution.status == "not_found":
        return _no_data(
            "No matching cash or bank ledger was found in Tally."
        )

    if resolution.status == "ambiguous":
        return {
            "success": False,
            "source": "tally",
            "message": (
                "Multiple matching ledgers were found. "
                "Please provide a more specific ledger name."
            ),
            "data": {
                "matches": resolution.matches or [],
            },
        }

    if resolution.status != "resolved":
        return _no_data(
            "Unable to resolve the requested ledger."
        )

    resolved_ledger = resolution.value

    report = await fetch_ledger_report(
        ledger_name=resolved_ledger,
        company_name=company_name,
        from_date=from_date,
        to_date=to_date,
    )

    if not isinstance(report, dict):
        return _no_data(
            "No transaction data was found for this ledger."
        )

    entries = report.get(
        "entries",
        [],
    ) or []

    transactions = []

    total_debit = 0.0
    total_credit = 0.0

    for entry in entries:
        debit = float(
            entry.get(
                "debit",
                0,
            )
            or 0
        )

        credit = float(
            entry.get(
                "credit",
                0,
            )
            or 0
        )

        total_debit += debit
        total_credit += credit

        transactions.append({
            "date": entry.get("date"),
            "voucher_type": entry.get("voucher_type"),
            "voucher_number": entry.get("voucher_number"),
            "particulars": entry.get("particulars"),
            "narration": entry.get("narration"),
            "debit": round(debit, 2),
            "credit": round(credit, 2),
            "running_balance": entry.get(
                "running_balance"
            ),
        })

    if not transactions:
        return _no_data(
            "No transactions were found for the selected ledger "
            "and period."
        )

    return _success({
        "ledger_name": resolved_ledger,
        "opening_balance": round(
            float(
                report.get(
                    "opening_balance",
                    0,
                )
                or 0
            ),
            2,
        ),
        "closing_balance": round(
            float(
                report.get(
                    "closing_balance",
                    0,
                )
                or 0
            ),
            2,
        ),
        "total_debit": round(
            total_debit,
            2,
        ),
        "total_credit": round(
            total_credit,
            2,
        ),
        "transactions": transactions,
        "count": len(transactions),
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
    })
    

# Customer/Supplier Statement Tool
async def get_party_statement_tool(
    party_name: str,
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Return the chronological ledger statement of a
    customer or supplier using actual Tally data.
    """

    if not party_name or not party_name.strip():
        return _no_data(
            "Please provide a customer or supplier name."
        )

    ledgers = await fetch_ledger_list(
        company_name=company_name
    )

    available_names = [
        ledger.get("name")
        for ledger in ledgers
        if ledger.get("name")
    ]

    if not available_names:
        return _no_data(
            "No ledgers were found in Tally."
        )

    resolution = resolve_name(
        requested_name=party_name,
        available_names=available_names,
    )

    if resolution.status == "not_found":
        return _no_data(
            "No matching customer or supplier ledger "
            "was found in Tally."
        )

    if resolution.status == "ambiguous":
        return {
            "success": False,
            "source": "tally",
            "message": (
                "Multiple matching ledgers were found. "
                "Please provide a more specific party name."
            ),
            "data": {
                "matches": resolution.matches or [],
            },
        }

    if resolution.status != "resolved":
        return _no_data(
            "Unable to resolve the requested party."
        )

    resolved_party = resolution.value

    report = await fetch_ledger_report(
        ledger_name=resolved_party,
        company_name=company_name,
        from_date=from_date,
        to_date=to_date,
    )

    if not isinstance(report, dict):
        return _no_data(
            "No statement data was found for this party."
        )

    entries = report.get(
        "entries",
        [],
    ) or []

    return _success({
        "party_name": resolved_party,
        "opening_balance": round(
            float(
                report.get(
                    "opening_balance",
                    0,
                )
                or 0
            ),
            2,
        ),
        "closing_balance": round(
            float(
                report.get(
                    "closing_balance",
                    0,
                )
                or 0
            ),
            2,
        ),
        "entries": entries,
        "count": len(entries),
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
    })

async def get_outstanding_summary_tool(
    company_name: str | None = None
) -> dict:
    receivables, payables = await _load_outstanding_data(
        company_name=company_name
    )

    return _success({
        "total_receivable": receivables.get(
            "total_receivable",
            0.0
        ),
        "receivable_count": receivables.get(
            "count",
            0
        ),
        "total_payable": payables.get(
            "total_payable",
            0.0
        ),
        "payable_count": payables.get(
            "count",
            0
        )
    })


async def get_top_receivables_tool(
    limit: int = 5,
    company_name: str | None = None
) -> dict:
    receivables = await _load_receivables(
        company_name=company_name
    )

    bills = receivables.get(
        "bills",
        []
    )

    if not bills:
        return _no_data(
            "No outstanding receivables were found in Tally."
        )

    limit = max(
        1,
        min(int(limit or 5), 20)
    )

    sorted_bills = sorted(
        bills,
        key=lambda bill: bill.get(
            "outstanding_amount",
            0.0
        ),
        reverse=True
    )

    top_bills = sorted_bills[:limit]

    return _success({
        "requested_limit": limit,
        "count": len(top_bills),
        "bills": top_bills
    })


async def get_top_payables_tool(
    limit: int = 5,
    company_name: str | None = None
) -> dict:
    payables = await _load_payables(
        company_name=company_name
    )

    bills = payables.get(
        "bills",
        []
    )

    if not bills:
        return _no_data(
            "No outstanding payables were found in Tally."
        )

    limit = max(
        1,
        min(int(limit or 5), 20)
    )

    sorted_bills = sorted(
        bills,
        key=lambda bill: bill.get(
            "outstanding_amount",
            0.0
        ),
        reverse=True
    )

    top_bills = sorted_bills[:limit]

    return _success({
        "requested_limit": limit,
        "count": len(top_bills),
        "bills": top_bills
    })
    
    
async def get_aged_receivables_tool(
    minimum_days: int | None = None,
    company_name: str | None = None
) -> dict:
    receivables = await _load_receivables(
        company_name=company_name
    )

    bills = receivables.get(
        "bills",
        []
    )

    aging = _build_aging_summary(
        bills=bills,
        minimum_days=minimum_days
    )

    return _success(aging)


async def get_aged_payables_tool(
    minimum_days: int | None = None,
    company_name: str | None = None
) -> dict:
    payables = await _load_payables(
        company_name=company_name
    )

    bills = payables.get(
        "bills",
        []
    )

    aging = _build_aging_summary(
        bills=bills,
        minimum_days=minimum_days
    )

    return _success(aging)

async def get_period_comparison_tool(
    metric: str,
    first_from_date: date,
    first_to_date: date,
    second_from_date: date,
    second_to_date: date,
    company_name: str | None = None
) -> dict:
    allowed_metrics = {
        "revenue",
        "expenses",
        "net_profit"
    }

    normalized_metric = metric.strip().lower()

    if normalized_metric not in allowed_metrics:
        return {
            "success": False,
            "source": "tally",
            "message": "Unsupported comparison metric.",
            "data": None
        }

    # Period comparison currently supports only revenue, expenses
    # and net profit. All three values come from the P&L report,
    # so outstanding data is not required here.
    #
    # Both periods are independent, so fetch them concurrently
    # instead of waiting for the first period before loading the second.
    first_summary, second_summary = await asyncio.gather(
        _load_profit_loss_summary(
            company_name=company_name,
            from_date=first_from_date,
            to_date=first_to_date,
        ),
        _load_profit_loss_summary(
            company_name=company_name,
            from_date=second_from_date,
            to_date=second_to_date,
        ),
    )

    first_value = float(
        first_summary.get(
            normalized_metric,
            0.0
        )
    )

    second_value = float(
        second_summary.get(
            normalized_metric,
            0.0
        )
    )

    difference = first_value - second_value

    percentage_change = None

    if second_value != 0:
        percentage_change = (
            difference / abs(second_value)
        ) * 100

    return _success({
        "metric": normalized_metric,
        "first_period": {
            "from_date": first_from_date.isoformat(),
            "to_date": first_to_date.isoformat(),
            "value": round(first_value, 2)
        },
        "second_period": {
            "from_date": second_from_date.isoformat(),
            "to_date": second_to_date.isoformat(),
            "value": round(second_value, 2)
        },
        "difference": round(
            difference,
            2
        ),
        "percentage_change": (
            round(
                percentage_change,
                2
            )
            if percentage_change is not None
            else None
        )
    })
    
async def get_financial_summary_tool(
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Return a combined financial summary for the selected company.

    The main financial loader already fetches and calculates all required
    values, so we reuse that result instead of fetching receivables,
    payables and pending invoices again.
    """

    # Load the complete financial summary only once.
    financial_summary = await _load_financial_summary(
        company_name=company_name,
        from_date=from_date,
        to_date=to_date,
    )

    # Reuse the values already calculated by build_dashboard_financials().
    # This avoids duplicate Tally requests and improves response time.
    return _success({
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
        "revenue": round(
            float(
                financial_summary.get(
                    "revenue",
                    0.0,
                )
            ),
            2,
        ),
        "expenses": round(
            float(
                financial_summary.get(
                    "expenses",
                    0.0,
                )
            ),
            2,
        ),
        "net_profit": round(
            float(
                financial_summary.get(
                    "net_profit",
                    0.0,
                )
            ),
            2,
        ),
        "receivables": round(
            float(
                financial_summary.get(
                    "receivables",
                    0.0,
                )
            ),
            2,
        ),
        "payables": round(
            float(
                financial_summary.get(
                    "payables",
                    0.0,
                )
            ),
            2,
        ),
        "pending_invoices": int(
            financial_summary.get(
                "pending_invoices",
                0,
            )
        ),
    })
    
async def _load_ledgers_by_parent(
    parent_names: set[str],
    company_name: str | None = None
) -> list[dict]:
    """
    Load ledgers from Tally whose parent group matches
    one of the supplied accounting groups.
    """

    ledgers = await fetch_ledger_list(
        company_name=company_name
    )
    
    # TEMPORARY DEBUG:
    # Print the ledger name and its parent group so we can check
    # how Tally is actually classifying bank accounts.
    for ledger in ledgers:
        print(
            "LEDGER DEBUG:",
            ledger.get("name"),
            "| parent:",
            ledger.get("parent"),
        )

    normalized_parents = {
        parent.strip().casefold()
        for parent in parent_names
    }

    return [
        ledger
        for ledger in ledgers
        if (
            ledger.get("parent", "")
            .strip()
            .casefold()
            in normalized_parents
        )
    ]

async def get_financial_trends_tool(
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Return a period-wise financial trend using existing
    revenue, expense, and net profit calculations.
    """

    if not from_date or not to_date:
        return _no_data(
            "A valid date range is required for financial trends."
        )

    periods = []

    current_year = from_date.year
    current_month = from_date.month

    while (
        current_year < to_date.year
        or (
            current_year == to_date.year
            and current_month <= to_date.month
        )
    ):
        period_from = date(
            current_year,
            current_month,
            1,
        )

        last_day = monthrange(
            current_year,
            current_month,
        )[1]

        period_to = date(
            current_year,
            current_month,
            last_day,
        )

        if period_from < from_date:
            period_from = from_date

        if period_to > to_date:
            period_to = to_date

        revenue_result, expense_result, profit_result = await asyncio.gather(
            get_revenue_tool(
                company_name=company_name,
                from_date=period_from,
                to_date=period_to,
            ),
            get_expenses_tool(
                company_name=company_name,
                from_date=period_from,
                to_date=period_to,
            ),
            get_net_profit_tool(
                company_name=company_name,
                from_date=period_from,
                to_date=period_to,
            ),
        )

        revenue = 0.0
        expenses = 0.0
        net_profit = 0.0

        if revenue_result.get("success"):
            revenue = float(
                revenue_result.get("data", {}).get(
                    "revenue",
                    0,
                )
                or 0
            )

        if expense_result.get("success"):
            expenses = float(
                expense_result.get("data", {}).get(
                    "expenses",
                    0,
                )
                or 0
            )

        if profit_result.get("success"):
            net_profit = float(
                profit_result.get("data", {}).get(
                    "net_profit",
                    0,
                )
                or 0
            )

        periods.append({
            "from_date": period_from.isoformat(),
            "to_date": period_to.isoformat(),
            "revenue": round(revenue, 2),
            "total_expenses": round(expenses, 2),
            "net_profit": round(net_profit, 2),
        })

        if current_month == 12:
            current_month = 1
            current_year += 1
        else:
            current_month += 1

    return _success({
        "periods": periods,
        "count": len(periods),
        "from_date": from_date.isoformat(),
        "to_date": to_date.isoformat(),
    })
    
async def get_company_comparison_tool(
    company_names: list[str],
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Compare financial performance across multiple Tally companies
    using the existing revenue, expense, and net profit tools.
    """

    if not company_names:
        return _no_data(
            "At least one company name is required for comparison."
        )

    companies = []

    for company_name in company_names:
        revenue_result, expense_result, profit_result = await asyncio.gather(
            get_revenue_tool(
                company_name=company_name,
                from_date=from_date,
                to_date=to_date,
            ),
            get_expenses_tool(
                company_name=company_name,
                from_date=from_date,
                to_date=to_date,
            ),
            get_net_profit_tool(
                company_name=company_name,
                from_date=from_date,
                to_date=to_date,
            ),
        )

        revenue = 0.0
        total_expenses = 0.0
        net_profit = 0.0

        if revenue_result.get("success"):
            revenue = float(
                revenue_result.get("data", {}).get(
                    "revenue",
                    0,
                )
                or 0
            )

        if expense_result.get("success"):
            total_expenses = float(
                expense_result.get("data", {}).get(
                    "expenses",
                    0,
                )
                or 0
            )

        if profit_result.get("success"):
            net_profit = float(
                profit_result.get("data", {}).get(
                    "net_profit",
                    0,
                )
                or 0
            )

        companies.append({
            "company_name": company_name,
            "revenue": round(revenue, 2),
            "total_expenses": round(
                total_expenses,
                2,
            ),
            "net_profit": round(
                net_profit,
                2,
            ),
        })

    return _success({
        "companies": companies,
        "count": len(companies),
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
    })
    
    
async def get_cost_centre_analysis_tool(
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Aggregate actual Tally cost centre allocations
    across ledger transactions.
    """

    ledgers = await fetch_ledger_list(
        company_name=company_name
    )

    ledger_names = [
        ledger.get("name")
        for ledger in ledgers
        if ledger.get("name")
    ]

    if not ledger_names:
        return _no_data(
            "No ledgers were found in Tally."
        )

    # Avoid sending too many requests to Tally at once.
    tally_request_limit = asyncio.Semaphore(5)

    async def load_ledger_report(
        ledger_name: str,
    ):
        async with tally_request_limit:
            return await fetch_ledger_report(
                ledger_name=ledger_name,
                company_name=company_name,
                from_date=from_date,
                to_date=to_date,
            )

    reports = await asyncio.gather(
        *[
            load_ledger_report(ledger_name)
            for ledger_name in ledger_names
        ],
        return_exceptions=True,
    )

    cost_centres: dict[str, dict] = {}

    for ledger_name, report in zip(
        ledger_names,
        reports,
    ):
        # One failed ledger request should not make
        # the entire cost centre analysis fail.
        if isinstance(report, Exception):
            continue

        if not isinstance(report, dict):
            continue

        entries = report.get(
            "entries",
            [],
        ) or []

        for entry in entries:
            allocations = entry.get(
                "cost_centre_allocations",
                [],
            ) or []

            for allocation in allocations:
                cost_centre_name = allocation.get(
                    "cost_centre_name",
                    "",
                ).strip()

                if not cost_centre_name:
                    continue

                category_name = allocation.get(
                    "category_name",
                    "",
                ).strip()

                amount = float(
                    allocation.get(
                        "amount",
                        0,
                    )
                    or 0
                )

                key = cost_centre_name.casefold()

                if key not in cost_centres:
                    cost_centres[key] = {
                        "cost_centre_name": (
                            cost_centre_name
                        ),
                        "net_amount": 0.0,
                        "allocation_count": 0,
                        "transactions": [],
                    }

                centre = cost_centres[key]

                centre["net_amount"] += amount
                centre["allocation_count"] += 1

                centre["transactions"].append({
                    "date": entry.get("date"),
                    "voucher_type": entry.get(
                        "voucher_type"
                    ),
                    "voucher_number": entry.get(
                        "voucher_number"
                    ),
                    "ledger_name": ledger_name,
                    "party_name": entry.get(
                        "party_name"
                    ),
                    "category_name": category_name,
                    "amount": round(
                        amount,
                        2,
                    ),
                })

    results = []

    for centre in cost_centres.values():
        centre["net_amount"] = round(
            centre["net_amount"],
            2,
        )

        results.append(centre)

    results.sort(
        key=lambda item: abs(
            item.get(
                "net_amount",
                0,
            )
        ),
        reverse=True,
    )

    if not results:
        return _no_data(
            "No cost centre allocations were found "
            "for the selected period."
        )

    return _success({
        "cost_centres": results,
        "count": len(results),
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
    })
    
    
async def get_cash_balance_tool(
    ledger_name: str | None = None,
    company_name: str | None = None
) -> dict:
    """
    Return current Cash-in-Hand ledger balances from Tally.
    """

    cash_ledgers = await _load_ledgers_by_parent(
        parent_names={
            "Cash-in-Hand",
        },
        company_name=company_name
    )

    if not cash_ledgers:
        return _no_data(
            "No Cash-in-Hand ledger was found in Tally."
        )

    # If the user asked for one particular cash ledger,
    # resolve it safely against actual Tally ledger names.
    if ledger_name and ledger_name.strip():
        available_names = [
            ledger["name"]
            for ledger in cash_ledgers
            if ledger.get("name")
        ]

        resolution = resolve_name(
            requested_name=ledger_name,
            available_names=available_names
        )

        if resolution.status == "not_found":
            return _no_data(
                "No matching cash ledger was found in Tally."
            )

        if resolution.status == "ambiguous":
            return {
                "success": False,
                "source": "tally",
                "message": (
                    "Multiple matching cash ledgers were found. "
                    "Please provide a more specific ledger name."
                ),
                "data": {
                    "matches": resolution.matches or []
                }
            }

        if resolution.status != "resolved":
            return _no_data(
                "Unable to resolve the requested cash ledger."
            )

        resolved_name = resolution.value

        selected_ledger = next(
            (
                ledger
                for ledger in cash_ledgers
                if ledger.get("name") == resolved_name
            ),
            None
        )

        if selected_ledger is None:
            return _no_data(
                "No matching cash ledger was found in Tally."
            )

        return _success({
            "ledger_name": selected_ledger.get("name"),
            # Tally may return Cash-in-Hand debit balances as negative values.
            # For the user, show the actual available cash as a positive amount.
            "closing_balance": round(
                abs(
                    float(
                        selected_ledger.get(
                            "closing_balance",
                            0.0
                        )
                    )
                ),
                2
            ),
            "ledger_count": 1,
            "ledgers": [
                selected_ledger
            ]
        })

    # Cash-in-Hand is an asset balance.
    # Tally can represent its debit balance with a negative sign,
    # so we convert each cash balance to a positive usable amount.
    total_balance = sum(
        abs(
            float(
                ledger.get(
                    "closing_balance",
                    0.0
                )
            )
        )
        for ledger in cash_ledgers
    )

    return _success({
        "total_balance": round(
            total_balance,
            2
        ),
        "ledger_count": len(
            cash_ledgers
        ),
        "ledgers": cash_ledgers
    })


async def get_bank_balance_tool(
    ledger_name: str | None = None,
    company_name: str | None = None
) -> dict:
    """
    Return current bank ledger balances from Tally.
    """

    bank_ledgers = await _load_ledgers_by_parent(
        parent_names={
            "Bank Accounts",
            "Bank OD A/c",
        },
        company_name=company_name
    )

    if not bank_ledgers:
        return _no_data(
            "No bank ledger was found in Tally."
        )

    # A specific bank/account was requested.
    if ledger_name and ledger_name.strip():
        available_names = [
            ledger["name"]
            for ledger in bank_ledgers
            if ledger.get("name")
        ]

        resolution = resolve_name(
            requested_name=ledger_name,
            available_names=available_names
        )

        if resolution.status == "not_found":
            return _no_data(
                "No matching bank ledger was found in Tally."
            )

        if resolution.status == "ambiguous":
            return {
                "success": False,
                "source": "tally",
                "message": (
                    "Multiple matching bank ledgers were found. "
                    "Please provide a more specific bank or account name."
                ),
                "data": {
                    "matches": resolution.matches or []
                }
            }

        if resolution.status != "resolved":
            return _no_data(
                "Unable to resolve the requested bank ledger."
            )

        resolved_name = resolution.value

        selected_ledger = next(
            (
                ledger
                for ledger in bank_ledgers
                if ledger.get("name") == resolved_name
            ),
            None
        )

        if selected_ledger is None:
            return _no_data(
                "No matching bank ledger was found in Tally."
            )

        return _success({
            "ledger_name": selected_ledger.get("name"),
            # Tally represents debit balances with a negative sign.
            # Reverse the Tally sign so the user sees the actual bank balance.
            "closing_balance": round(
                -float(
                    selected_ledger.get(
                        "closing_balance",
                        0.0
                    )
                ),
                2
            ),
            "ledger_count": 1,
            "ledgers": [
                selected_ledger
            ]
        })

    # Reverse Tally's accounting sign for the user-facing bank balance.
    # A normal debit bank balance becomes positive, while a credit
    # balance such as an overdraft can remain negative.
    total_balance = sum(
        -float(
            ledger.get(
                "closing_balance",
                0.0
            )
        )
        for ledger in bank_ledgers
    )

    return _success({
        "total_balance": round(
            total_balance,
            2
        ),
        "ledger_count": len(
            bank_ledgers
        ),
        "ledgers": bank_ledgers
    })
    
async def get_bank_transactions_tool(
    ledger_name: str | None = None,
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Return bank transactions from Tally.

    If a specific bank ledger is requested, only that ledger is used.
    Otherwise, transactions from all bank ledgers are combined.
    """

    bank_ledgers = await _load_ledgers_by_parent(
        parent_names={
            "Bank Accounts",
            "Bank OD A/c",
        },
        company_name=company_name,
    )

    if not bank_ledgers:
        return _no_data(
            "No bank ledger was found in Tally."
        )

    selected_ledgers = bank_ledgers

    # If the user asks for one specific bank account,
    # resolve it against the actual ledger names in Tally.
    if ledger_name and ledger_name.strip():
        available_names = [
            ledger["name"]
            for ledger in bank_ledgers
            if ledger.get("name")
        ]

        resolution = resolve_name(
            requested_name=ledger_name,
            available_names=available_names,
        )

        if resolution.status == "not_found":
            return _no_data(
                "No matching bank ledger was found in Tally."
            )

        if resolution.status == "ambiguous":
            return {
                "success": False,
                "source": "tally",
                "message": (
                    "Multiple matching bank ledgers were found. "
                    "Please provide a more specific bank or account name."
                ),
                "data": {
                    "matches": resolution.matches or []
                },
            }

        if resolution.status != "resolved":
            return _no_data(
                "Unable to resolve the requested bank ledger."
            )

        resolved_name = resolution.value

        selected_ledger = next(
            (
                ledger
                for ledger in bank_ledgers
                if ledger.get("name") == resolved_name
            ),
            None,
        )

        if selected_ledger is None:
            return _no_data(
                "No matching bank ledger was found in Tally."
            )

        selected_ledgers = [
            selected_ledger
        ]

    transactions = []

    for ledger in selected_ledgers:
        current_ledger_name = ledger.get("name")

        if not current_ledger_name:
            continue

        report = await fetch_ledger_report(
            ledger_name=current_ledger_name,
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
        )

        entries = (
            report.get("transactions")
            or report.get("entries")
            or []
        )

        for entry in entries:
            # Add the ledger name so we still know which
            # bank account each transaction belongs to.
            transaction = dict(entry)
            transaction["ledger_name"] = current_ledger_name

            transactions.append(transaction)

    # Keep transactions in date order.
    transactions.sort(
        key=lambda item: (
            item.get("date")
            or item.get("voucher_date")
            or ""
        )
    )

    # Tally represents a normal debit bank balance with a negative sign.
    # Reverse that sign for the balance shown to the user.
    opening_balance = sum(
        -float(
            ledger.get(
                "opening_balance",
                0.0,
            )
            or 0.0
        )
        for ledger in selected_ledgers
    )

    closing_balance = sum(
        -float(
            ledger.get(
                "closing_balance",
                0.0,
            )
            or 0.0
        )
        for ledger in selected_ledgers
    )

    # Use the real bank name when only one account is involved.
    # For multiple accounts, show a general label.
    display_ledger_name = (
        selected_ledgers[0].get(
            "name",
            "Bank account",
        )
        if len(selected_ledgers) == 1
        else "Bank accounts"
    )

    return _success({
        "ledger_name": display_ledger_name,
        "opening_balance": round(
            opening_balance,
            2,
        ),
        "closing_balance": round(
            closing_balance,
            2,
        ),
        "ledger_count": len(
            selected_ledgers
        ),
        "transaction_count": len(
            transactions
        ),
        "transactions": transactions,
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
    })
    
    
async def get_cash_transactions_tool(
    ledger_name: str | None = None,
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Return transactions from Cash-in-Hand ledgers in Tally.

    If a particular cash ledger is requested, only that ledger is used.
    Otherwise, transactions from all available cash ledgers are combined.
    """

    # Identify all ledgers that belong to Tally's Cash-in-Hand group.
    cash_ledgers = await _load_ledgers_by_parent(
        parent_names={
            "Cash-in-Hand",
        },
        company_name=company_name,
    )

    if not cash_ledgers:
        return _no_data(
            "No Cash-in-Hand ledger was found in Tally."
        )

    # If the user mentions a specific cash ledger,
    # resolve it safely against the actual names in Tally.
    if ledger_name and ledger_name.strip():
        available_names = [
            ledger["name"]
            for ledger in cash_ledgers
            if ledger.get("name")
        ]

        resolution = resolve_name(
            requested_name=ledger_name,
            available_names=available_names,
        )

        if resolution.status == "not_found":
            return _no_data(
                "No matching cash ledger was found in Tally."
            )

        if resolution.status == "ambiguous":
            return {
                "success": False,
                "source": "tally",
                "message": (
                    "Multiple matching cash ledgers were found. "
                    "Please provide a more specific cash ledger name."
                ),
                "data": {
                    "matches": resolution.matches or []
                },
            }

        if resolution.status != "resolved":
            return _no_data(
                "Unable to resolve the requested cash ledger."
            )

        selected_names = [
            resolution.value
        ]

    else:
        # No specific cash ledger was requested,
        # so include transactions from all Cash-in-Hand ledgers.
        selected_names = [
            ledger["name"]
            for ledger in cash_ledgers
            if ledger.get("name")
        ]

    all_transactions = []

    # Load the transaction report for each selected cash ledger.
    for cash_name in selected_names:
        report = await fetch_ledger_report(
            ledger_name=cash_name,
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
        )

        for entry in report.get("entries", []):
            transaction = dict(entry)

            # Keep the source cash ledger with every transaction.
            transaction["ledger_name"] = cash_name

            all_transactions.append(
                transaction
            )

    return _success({
        "ledger_name": (
            selected_names[0]
            if len(selected_names) == 1
            else None
        ),
        "ledger_count": len(selected_names),
        "transaction_count": len(all_transactions),
        "transactions": all_transactions,
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
    })
    
async def get_sales_transactions_tool(
    ledger_name: str | None = None,
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Return transactions from Sales Accounts ledgers in Tally.

    If a specific sales ledger is requested, only that ledger is used.
    Otherwise, transactions from all sales ledgers are combined.
    """

    # Find all ledgers that belong to Tally's Sales Accounts group.
    sales_ledgers = await _load_ledgers_by_parent(
        parent_names={
            "Sales Accounts",
        },
        company_name=company_name,
    )

    if not sales_ledgers:
        return _no_data(
            "No sales ledger was found in Tally."
        )

    # If the user requests a specific sales ledger,
    # resolve it against the actual Tally ledger names.
    if ledger_name and ledger_name.strip():
        available_names = [
            ledger["name"]
            for ledger in sales_ledgers
            if ledger.get("name")
        ]

        resolution = resolve_name(
            requested_name=ledger_name,
            available_names=available_names,
        )

        if resolution.status == "not_found":
            return _no_data(
                "No matching sales ledger was found in Tally."
            )

        if resolution.status == "ambiguous":
            return {
                "success": False,
                "source": "tally",
                "message": (
                    "Multiple matching sales ledgers were found. "
                    "Please provide a more specific sales ledger name."
                ),
                "data": {
                    "matches": resolution.matches or []
                },
            }

        if resolution.status != "resolved":
            return _no_data(
                "Unable to resolve the requested sales ledger."
            )

        selected_names = [
            resolution.value
        ]

    else:
        # No specific ledger requested, so include
        # transactions from all Sales Accounts ledgers.
        selected_names = [
            ledger["name"]
            for ledger in sales_ledgers
            if ledger.get("name")
        ]

    all_transactions = []

    # Fetch ledger transactions for every selected sales ledger.
    for sales_name in selected_names:
        report = await fetch_ledger_report(
            ledger_name=sales_name,
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
        )

        for entry in report.get("entries", []):
            voucher_type = (
                entry.get("voucher_type")
                or entry.get("type")
                or ""
            ).strip().lower()

            # Keep only posted sales-related vouchers.
            # Sales Orders are only orders and should not be treated
            # as actual sales transactions.
            if voucher_type not in {
                "sales",
                "credit note",
                "creditnote",
            }:
                continue

            transaction = dict(entry)

            # Preserve the originating sales ledger.
            transaction["ledger_name"] = sales_name

            all_transactions.append(
                transaction
            )

    return _success({
        "ledger_name": (
            selected_names[0]
            if len(selected_names) == 1
            else None
        ),
        "ledger_count": len(selected_names),
        "transaction_count": len(all_transactions),
        "transactions": all_transactions,
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
    })
async def get_purchase_transactions_tool(
    ledger_name: str | None = None,
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Return transactions from Purchase Accounts ledgers in Tally.

    If a specific purchase ledger is requested, only that ledger is used.
    Otherwise, transactions from all purchase ledgers are combined.
    """

    purchase_ledgers = await _load_ledgers_by_parent(
        parent_names={
            "Purchase Accounts",
        },
        company_name=company_name,
    )

    if not purchase_ledgers:
        return _no_data(
            "No purchase ledger was found in Tally."
        )

    if ledger_name and ledger_name.strip():
        available_names = [
            ledger["name"]
            for ledger in purchase_ledgers
            if ledger.get("name")
        ]

        resolution = resolve_name(
            requested_name=ledger_name,
            available_names=available_names,
        )

        if resolution.status == "not_found":
            return _no_data(
                "No matching purchase ledger was found in Tally."
            )

        if resolution.status == "ambiguous":
            return {
                "success": False,
                "source": "tally",
                "message": (
                    "Multiple matching purchase ledgers were found. "
                    "Please provide a more specific purchase ledger name."
                ),
                "data": {
                    "matches": resolution.matches or []
                },
            }

        if resolution.status != "resolved":
            return _no_data(
                "Unable to resolve the requested purchase ledger."
            )

        selected_names = [
            resolution.value
        ]

    else:
        selected_names = [
            ledger["name"]
            for ledger in purchase_ledgers
            if ledger.get("name")
        ]

    all_transactions = []

    for purchase_name in selected_names:
        report = await fetch_ledger_report(
            ledger_name=purchase_name,
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
        )

        for entry in report.get("entries", []):
            voucher_type = (
                entry.get("voucher_type")
                or entry.get("type")
                or ""
            ).strip().lower()

            # Keep only actual purchase-related vouchers.
            # Purchase Orders and Receipt Notes are not posted
            # purchase transactions, so they should not appear here.
            if voucher_type not in {
                "purchase",
                "debit note",
                "debitnote",
            }:
                continue

            transaction = dict(entry)

            # Keep the purchase ledger name with each transaction.
            transaction["ledger_name"] = purchase_name

            all_transactions.append(
                transaction
            )

    return _success({
        "ledger_name": (
            selected_names[0]
            if len(selected_names) == 1
            else None
        ),
        "ledger_count": len(selected_names),
        "transaction_count": len(all_transactions),
        "transactions": all_transactions,
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
    })
    
async def get_stock_movement_tool(
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Show item-wise stock movement from posted sales
    and purchase transactions.

    Purchase increases stock.
    Sales reduce stock.
    Credit Note normally brings sold stock back.
    Debit Note normally sends purchased stock back.
    """

    sales_result, purchase_result = await asyncio.gather(
        get_sales_transactions_tool(
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
        ),
        get_purchase_transactions_tool(
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
        ),
    )

    movements = {}

    def add_movement(
        transaction: dict,
        movement_type: str,
    ):
        voucher_type = (
            transaction.get("voucher_type")
            or ""
        ).strip().casefold()

        stock_items = transaction.get(
            "stock_items",
            [],
        )

        for stock_item in stock_items:

            item_name = (
                stock_item.get("stock_item_name")
                or ""
            ).strip()

            if not item_name:
                continue

            quantity_text = (
                stock_item.get("actual_quantity")
                or stock_item.get("billed_quantity")
                or ""
            )

            quantity = abs(
                _parse_tally_quantity(
                    quantity_text
                )
            )

            if quantity <= 0:
                continue

            if item_name not in movements:
                movements[item_name] = {
                    "stock_item_name": item_name,
                    "inward_quantity": 0.0,
                    "outward_quantity": 0.0,
                }

            item = movements[item_name]

            if movement_type == "sales":

                if voucher_type in {
                    "credit note",
                    "creditnote",
                }:
                    # Sales return brings stock back.
                    item["inward_quantity"] += quantity
                else:
                    # Normal sale sends stock out.
                    item["outward_quantity"] += quantity

            elif movement_type == "purchase":

                if voucher_type in {
                    "debit note",
                    "debitnote",
                }:
                    # Purchase return sends stock back
                    # to the supplier.
                    item["outward_quantity"] += quantity
                else:
                    # Normal purchase brings stock in.
                    item["inward_quantity"] += quantity

    if sales_result.get("success"):
        for transaction in (
            sales_result.get("data", {})
            .get("transactions", [])
        ):
            add_movement(
                transaction,
                "sales",
            )

    if purchase_result.get("success"):
        for transaction in (
            purchase_result.get("data", {})
            .get("transactions", [])
        ):
            add_movement(
                transaction,
                "purchase",
            )

    items = []

    for item in movements.values():

        inward = item["inward_quantity"]
        outward = item["outward_quantity"]

        item["inward_quantity"] = round(
            inward,
            3,
        )

        item["outward_quantity"] = round(
            outward,
            3,
        )

        item["net_movement"] = round(
            inward - outward,
            3,
        )

        items.append(item)

    items.sort(
        key=lambda item: (
            item["inward_quantity"]
            + item["outward_quantity"]
        ),
        reverse=True,
    )

    return _success({
        "items": items,
        "count": len(items),
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
    })

async def get_receipt_transactions_tool(
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Return receipt voucher transactions from Tally.

    This is used when the user asks about money received,
    receipt entries, or customer receipts.
    """

    receipt_ledgers = await _load_ledgers_by_parent(
        parent_names={
            "Bank Accounts",
            "Cash-in-Hand",
        },
        company_name=company_name,
    )

    if not receipt_ledgers:
        return _no_data(
            "No cash or bank ledger was found in Tally."
        )

    all_transactions = []

    for ledger in receipt_ledgers:
        ledger_name = ledger.get("name")

        if not ledger_name:
            continue

        report = await fetch_ledger_report(
            ledger_name=ledger_name,
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
        )

        for entry in report.get("entries", []):
            voucher_type = (
                entry.get("voucher_type")
                or entry.get("type")
                or ""
            )

            if voucher_type.strip().lower() != "receipt":
                continue

            transaction = dict(entry)
            transaction["ledger_name"] = ledger_name

            all_transactions.append(
                transaction
            )

    return _success({
        "transaction_count": len(all_transactions),
        "transactions": all_transactions,
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
    })

async def get_payment_transactions_tool(
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Return payment voucher transactions from Tally.

    This is used when the user asks about payments made,
    outgoing payments, supplier payments, or payment entries.
    """

    payment_ledgers = await _load_ledgers_by_parent(
        parent_names={
            "Bank Accounts",
            "Cash-in-Hand",
        },
        company_name=company_name,
    )

    if not payment_ledgers:
        return _no_data(
            "No cash or bank ledger was found in Tally."
        )

    all_transactions = []

    for ledger in payment_ledgers:
        ledger_name = ledger.get("name")

        if not ledger_name:
            continue

        report = await fetch_ledger_report(
            ledger_name=ledger_name,
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
        )

        for entry in report.get("entries", []):
            voucher_type = (
                entry.get("voucher_type")
                or entry.get("type")
                or ""
            )

            if voucher_type.strip().lower() != "payment":
                continue

            transaction = dict(entry)
            transaction["ledger_name"] = ledger_name

            all_transactions.append(
                transaction
            )

    return _success({
        "transaction_count": len(all_transactions),
        "transactions": all_transactions,
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
    })
    
async def get_credit_note_transactions_tool(
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Return Credit Note voucher transactions from Tally.
    """

    ledgers = await _load_ledgers_by_parent(
        parent_names={
            "Bank Accounts",
            "Cash-in-Hand",
            "Sundry Debtors",
            "Sales Accounts",
        },
        company_name=company_name,
    )

    if not ledgers:
        return _no_data(
            "No relevant ledger was found in Tally."
        )

    all_transactions = []
    seen_vouchers = set()

    for ledger in ledgers:
        ledger_name = ledger.get("name")

        if not ledger_name:
            continue

        report = await fetch_ledger_report(
            ledger_name=ledger_name,
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
        )

        for entry in report.get("entries", []):
            voucher_type = (
                entry.get("voucher_type")
                or entry.get("type")
                or ""
            ).strip().lower()

            if voucher_type not in {
                "credit note",
                "creditnote",
            }:
                continue

            voucher_key = (
                entry.get("date"),
                entry.get("voucher_number")
                or entry.get("voucher_no"),
                voucher_type,
            )

            # Avoid showing the same voucher multiple times
            # when it appears in more than one ledger report.
            if voucher_key in seen_vouchers:
                continue

            seen_vouchers.add(voucher_key)

            transaction = dict(entry)
            transaction["ledger_name"] = ledger_name

            all_transactions.append(transaction)

    return _success({
        "transaction_count": len(all_transactions),
        "transactions": all_transactions,
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
    })


async def get_debit_note_transactions_tool(
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Return Debit Note voucher transactions from Tally.
    """

    ledgers = await _load_ledgers_by_parent(
        parent_names={
            "Bank Accounts",
            "Cash-in-Hand",
            "Sundry Creditors",
            "Purchase Accounts",
        },
        company_name=company_name,
    )

    if not ledgers:
        return _no_data(
            "No relevant ledger was found in Tally."
        )

    all_transactions = []
    seen_vouchers = set()

    for ledger in ledgers:
        ledger_name = ledger.get("name")

        if not ledger_name:
            continue

        report = await fetch_ledger_report(
            ledger_name=ledger_name,
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
        )

        for entry in report.get("entries", []):
            voucher_type = (
                entry.get("voucher_type")
                or entry.get("type")
                or ""
            ).strip().lower()

            if voucher_type not in {
                "debit note",
                "debitnote",
            }:
                continue

            voucher_key = (
                entry.get("date"),
                entry.get("voucher_number")
                or entry.get("voucher_no"),
                voucher_type,
            )

            if voucher_key in seen_vouchers:
                continue

            seen_vouchers.add(voucher_key)

            transaction = dict(entry)
            transaction["ledger_name"] = ledger_name

            all_transactions.append(transaction)

    return _success({
        "transaction_count": len(all_transactions),
        "transactions": all_transactions,
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
    })
    
def _get_invoice_payment_status(
    original_amount: float,
    outstanding_amount: float,
) -> str:
    """
    Return a consistent payment status for an invoice.
    """

    original_amount = abs(float(original_amount or 0))
    outstanding_amount = abs(float(outstanding_amount or 0))

    # Small decimal differences should not make a fully
    # settled invoice appear as unpaid.
    tolerance = 0.01

    if outstanding_amount <= tolerance:
        return "Paid"

    if (
        original_amount > tolerance
        and outstanding_amount < original_amount
    ):
        return "Partially Paid"

    return "Unpaid"
async def get_invoice_details_tool(
    invoice_number: str,
    company_name: str | None = None,
) -> dict:
    """
    Return consolidated details of a specific invoice from Tally.
    """

    if not invoice_number or not invoice_number.strip():
        return _no_data(
            "Please provide an invoice number."
        )

    # Tally can return the same bill reference in multiple vouchers.
    # For example, the original Sales voucher and later Receipts can
    # all contain the same bill reference.
    bill_allocations = await fetch_bill_allocations(
        company_name=company_name,
    )

    # Combine all allocations belonging to the same bill.
    # This gives us the current outstanding balance instead of
    # accidentally using only the first transaction.
    outstanding_bills = build_outstanding_summary(
        bill_allocations
    )

    requested_reference = (
        invoice_number
        .strip()
        .lower()
    )

    matches = []

    for bill in outstanding_bills:
        bill_reference = str(
            bill.get("bill_reference")
            or ""
        ).strip()

        if (
            bill_reference.lower()
            == requested_reference
        ):
            matches.append(bill)

    if not matches:
        return _no_data(
            f"Invoice {invoice_number} was not found in Tally."
        )

    # A bill reference may theoretically be reused by different
    # parties, so keep the matching consolidated bill here.
    invoice = matches[0]

    transactions = (
        invoice.get("transactions")
        or []
    )

    # Find the original New Ref allocation.
    # Its amount represents the amount of the original invoice.
    original_amount = 0.0

    for transaction in transactions:
        bill_type = str(
            transaction.get("bill_type")
            or ""
        ).strip().lower()

        if bill_type == "new ref":
            original_amount = abs(
                float(
                    transaction.get("amount")
                    or 0
                )
            )
            break

    # Current outstanding comes from the consolidated bill balance,
    # which includes later receipts or adjustments against the invoice.
    outstanding_amount = float(
        invoice.get("outstanding_amount")
        or 0
    )
    
    # Use the same payment status everywhere in the chatbot.
    status = _get_invoice_payment_status(
        original_amount=original_amount,
        outstanding_amount=outstanding_amount,
    )

    return _success({
        "invoice_number": (
            invoice.get("bill_reference")
            or invoice_number
        ),
        "party_name": invoice.get("party"),
        "invoice_date": invoice.get("bill_date"),
        "original_voucher_type": (
            invoice.get("original_voucher_type")
        ),
        "original_voucher_number": (
            invoice.get("original_voucher_number")
        ),
        "original_amount": round(
            original_amount,
            2,
        ),
        "outstanding_amount": round(
            outstanding_amount,
            2,
        ),
        "status": status,
        "type": invoice.get("type"),
        "transactions": transactions,
    })


async def get_invoice_status_tool(
    invoice_number: str,
    company_name: str | None = None,
) -> dict:
    """
    Return the payment status of a specific invoice.
    """

    # Reuse invoice details so all invoice information
    # comes from the same Tally data.
    result = await get_invoice_details_tool(
        invoice_number=invoice_number,
        company_name=company_name,
    )

    if not result.get("success"):
        return result

    data = result.get("data", {})

    # Use one common status calculation so invoice
    # details and invoice status always give the same result.
    status = _get_invoice_payment_status(
        original_amount=data.get("original_amount", 0),
        outstanding_amount=data.get("outstanding_amount", 0),
    )

    data["status"] = status

    return _success(data)

async def get_customer_statement_tool(
    party_name: str,
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Return the posted ledger statement for a customer.

    Order and inventory-only vouchers are removed because
    they should not be treated as customer account movements.
    """

    if not party_name or not party_name.strip():
        return _no_data(
            "Please provide a customer name."
        )

    customer_ledgers = await _load_ledgers_by_parent(
        parent_names={
            "Sundry Debtors",
        },
        company_name=company_name,
    )

    available_names = [
        ledger["name"]
        for ledger in customer_ledgers
        if ledger.get("name")
    ]

    resolution = resolve_name(
        requested_name=party_name,
        available_names=available_names,
    )

    if resolution.status == "not_found":
        return _no_data(
            f"Customer {party_name} was not found in Tally."
        )

    if resolution.status == "ambiguous":
        return {
            "success": False,
            "source": "tally",
            "message": (
                "Multiple matching customers were found. "
                "Please provide a more specific customer name."
            ),
            "data": {
                "matches": resolution.matches or []
            },
        }

    if resolution.status != "resolved":
        return _no_data(
            "Unable to resolve the requested customer."
        )

    resolved_name = resolution.value

    report = await fetch_ledger_report(
        ledger_name=resolved_name,
        company_name=company_name,
        from_date=from_date,
        to_date=to_date,
    )

    raw_entries = report.get(
        "entries",
        [],
    )

    # These vouchers represent orders or inventory movement.
    # They should not be counted as posted customer account activity.
    excluded_voucher_types = {
        "sales order",
        "receipt note",
    }

    transactions = []

    for entry in raw_entries:
        voucher_type = (
            entry.get("voucher_type")
            or entry.get("type")
            or ""
        ).strip().lower()

        if voucher_type in excluded_voucher_types:
            continue

        transactions.append(entry)

    opening_balance = float(
        report.get("opening_balance", 0) or 0
    )

    transactions, closing_balance = (
        _recalculate_statement_balances(
            transactions=transactions,
            opening_balance=opening_balance,
        )
    )
    return _success({
        "party_name": resolved_name,
        "party_type": "customer",

        # Keep Tally's original opening and closing balances.
        # We should not recalculate them from the filtered list
        # because the ledger balance must remain consistent with Tally.
        "opening_balance": opening_balance,
        "closing_balance": closing_balance,

        "transaction_count": len(
            transactions
        ),
        "transactions": transactions,

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
    })


async def get_supplier_statement_tool(
    party_name: str,
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Return the posted ledger statement for a supplier.

    Order and inventory-only vouchers are removed because
    they should not be treated as supplier account movements.
    """

    if not party_name or not party_name.strip():
        return _no_data(
            "Please provide a supplier name."
        )

    supplier_ledgers = await _load_ledgers_by_parent(
        parent_names={
            "Sundry Creditors",
        },
        company_name=company_name,
    )

    available_names = [
        ledger["name"]
        for ledger in supplier_ledgers
        if ledger.get("name")
    ]

    resolution = resolve_name(
        requested_name=party_name,
        available_names=available_names,
    )

    if resolution.status == "not_found":
        return _no_data(
            f"Supplier {party_name} was not found in Tally."
        )

    if resolution.status == "ambiguous":
        return {
            "success": False,
            "source": "tally",
            "message": (
                "Multiple matching suppliers were found. "
                "Please provide a more specific supplier name."
            ),
            "data": {
                "matches": resolution.matches or []
            },
        }

    if resolution.status != "resolved":
        return _no_data(
            "Unable to resolve the requested supplier."
        )

    resolved_name = resolution.value

    print(
        "SUPPLIER NAME DEBUG:",
        "requested=", repr(party_name),
        "| available=", [repr(name) for name in available_names],
        "| resolved=", repr(resolved_name),
    )

    report = await fetch_ledger_report(
        ledger_name=resolved_name,
        company_name=company_name,
        from_date=from_date,
        to_date=to_date,
    )

    raw_entries = report.get(
        "entries",
        [],
    )

    # These vouchers represent order or inventory movement.
    # They should not appear as posted supplier account activity.
    excluded_voucher_types = {
        "purchase order",
        "material in",
        "receipt note",
    }

    transactions = []

    for entry in raw_entries:
        voucher_type = (
            entry.get("voucher_type")
            or entry.get("type")
            or ""
        ).strip().lower()

        if voucher_type in excluded_voucher_types:
            continue

        transactions.append(entry)

    opening_balance = to_optional_float(
        report.get("opening_balance")
    )

    transactions, closing_balance = (
        _recalculate_statement_balances(
            transactions=transactions,
            opening_balance=opening_balance,
        )
    )
    return _success({
        "party_name": resolved_name,
        "party_type": "supplier",

        # Keep the balance returned by Tally.
        # We will validate the sign separately against the ledger.
        "opening_balance": opening_balance,
        "closing_balance": closing_balance,

        "transaction_count": len(
            transactions
        ),
        "transactions": transactions,

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
    })
    
async def get_input_gst_tool(
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Return Input GST balances and transactions from Tally.
    """

    # GST ledgers are normally kept under the "Duties & Taxes" group in Tally.
    gst_ledgers = await _load_ledgers_by_parent(
        parent_names={"Duties & Taxes"},
        company_name=company_name,
    )

    # Keep only Input GST ledgers.
    # Example: Input CGST, Input SGST, Input IGST.
    input_ledgers = [
        ledger
        for ledger in gst_ledgers
        if (
            ledger.get("name")
            and ledger["name"].strip().lower().startswith("input ")
        )
    ]

    # If the company has no Input GST ledgers,
    # return a clear no-data response.
    if not input_ledgers:
        return _no_data(
            "No Input GST ledgers were found in Tally."
        )

    ledger_results = []
    total_input_gst = 0.0

    # Read each Input GST ledger separately because
    # every tax component can have its own balance and transactions.
    for ledger in input_ledgers:
        ledger_name = ledger["name"]

        report = await fetch_ledger_report(
            ledger_name=ledger_name,
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
        )

        # Closing balance shows the current balance of this GST ledger.
        closing_balance = float(
            report.get("closing_balance", 0) or 0
        )

        # Use the absolute value while calculating the total
        # so Tally's debit/credit sign does not reduce the GST amount.
        total_input_gst += abs(closing_balance)

        # Keep ledger-wise details so the chatbot can also show
        # individual CGST, SGST or IGST values if required.
        ledger_results.append({
            "ledger_name": ledger_name,
            "closing_balance": closing_balance,
            "transactions": report.get("entries", []),
        })

    return _success({
        "gst_type": "input",
        "total_input_gst": total_input_gst,
        "ledgers": ledger_results,
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
    })


async def get_output_gst_tool(
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Return Output GST balances and transactions from Tally.
    """

    # Load all GST-related ledgers from the Duties & Taxes group.
    gst_ledgers = await _load_ledgers_by_parent(
        parent_names={"Duties & Taxes"},
        company_name=company_name,
    )

    # Keep only Output GST ledgers.
    # Example: Output CGST, Output SGST, Output IGST.
    output_ledgers = [
        ledger
        for ledger in gst_ledgers
        if (
            ledger.get("name")
            and ledger["name"].strip().lower().startswith("output ")
        )
    ]

    # Return a clear response if Output GST is not configured in Tally.
    if not output_ledgers:
        return _no_data(
            "No Output GST ledgers were found in Tally."
        )

    ledger_results = []
    total_output_gst = 0.0

    # Read every Output GST ledger separately.
    for ledger in output_ledgers:
        ledger_name = ledger["name"]

        report = await fetch_ledger_report(
            ledger_name=ledger_name,
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
        )

        # Get the current balance of this GST ledger.
        closing_balance = float(
            report.get("closing_balance", 0) or 0
        )

        # Add all Output GST balances together.
        total_output_gst += abs(closing_balance)

        # Save ledger-level data for detailed chatbot responses.
        ledger_results.append({
            "ledger_name": ledger_name,
            "closing_balance": closing_balance,
            "transactions": report.get("entries", []),
        })

    return _success({
        "gst_type": "output",
        "total_output_gst": total_output_gst,
        "ledgers": ledger_results,
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
    })


async def get_gst_summary_tool(
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Return a combined Input GST, Output GST and Net GST summary.
    """

    # Get Input GST details for the requested period.
    input_result = await get_input_gst_tool(
        company_name=company_name,
        from_date=from_date,
        to_date=to_date,
    )

    # Get Output GST details for the same period.
    output_result = await get_output_gst_tool(
        company_name=company_name,
        from_date=from_date,
        to_date=to_date,
    )

    # Use an empty dictionary if Input GST data is not available.
    input_data = (
        input_result.get("data", {})
        if input_result.get("success")
        else {}
    )

    # Use an empty dictionary if Output GST data is not available.
    output_data = (
        output_result.get("data", {})
        if output_result.get("success")
        else {}
    )

    total_input_gst = float(
        input_data.get("total_input_gst", 0) or 0
    )

    total_output_gst = float(
        output_data.get("total_output_gst", 0) or 0
    )

    # Net GST is the difference between tax collected on sales
    # and input tax available from purchases.
    net_gst = total_output_gst - total_input_gst

    return _success({
        "total_input_gst": total_input_gst,
        "total_output_gst": total_output_gst,
        "net_gst": net_gst,

        # Keep ledger-wise details so the response can show
        # CGST, SGST and IGST separately when needed.
        "input_ledgers": input_data.get(
            "ledgers",
            [],
        ),
        "output_ledgers": output_data.get(
            "ledgers",
            [],
        ),

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
    })
    
async def get_stock_items_tool(
    company_name: str | None = None,
) -> dict:
    """
    Return all stock items available in Tally.
    """

    # Fetch the latest stock item list directly from Tally.
    stock_items = await fetch_stock_item_list(
        company_name=company_name
    )

    if not stock_items:
        return _no_data(
            "No stock items were found in Tally."
        )

    return _success({
        "items": stock_items,
        "count": len(stock_items),
    })


async def get_stock_summary_tool(
    company_name: str | None = None,
) -> dict:
    """
    Return a simple summary of the current stock available in Tally.
    """

    stock_items = await fetch_stock_item_list(
        company_name=company_name
    )

    if not stock_items:
        return _no_data(
            "No stock items were found in Tally."
        )

    total_items = len(stock_items)
    stock_with_balance = 0

    # Keep the total value as raw text for now because
    # Tally can return signed values and formatted numbers.
    total_stock_value = 0.0

    for item in stock_items:
        closing_balance = item.get(
            "closing_balance",
            ""
        )

        closing_value = item.get(
            "closing_value",
            ""
        )

        # Consider the item as having stock when Tally
        # returns a non-empty closing quantity.
        if closing_balance:
            stock_with_balance += 1

        # Tally may return commas or spaces in amount fields.
        # Remove basic formatting before converting to a number.
        if closing_value:
            try:
                clean_value = (
                    str(closing_value)
                    .replace(",", "")
                    .strip()
                )

                total_stock_value += float(clean_value)

            except ValueError:
                # If Tally sends an unexpected format,
                # skip that value instead of failing the whole chatbot query.
                pass

    return _success({
        "total_items": total_items,
        "items_with_stock": stock_with_balance,
        "total_stock_value": total_stock_value,
        "items": stock_items,
    })


async def get_stock_item_details_tool(
    item_name: str,
    company_name: str | None = None,
) -> dict:
    """
    Return details of one stock item from Tally.
    """

    stock_items = await fetch_stock_item_list(
        company_name=company_name
    )

    if not stock_items:
        return _no_data(
            "No stock items were found in Tally."
        )

    requested_name = " ".join(
        item_name.strip().split()
    ).casefold()

    # First try an exact match so we do not return
    # the wrong product when names are similar.
    for item in stock_items:
        current_name = " ".join(
            item.get("name", "").strip().split()
        ).casefold()

        if current_name == requested_name:
            return _success({
                "item": item
            })

    # If there is no exact match, check for a partial match.
    # This helps when the user types only part of the product name.
    partial_matches = []

    for item in stock_items:
        current_name = item.get(
            "name",
            ""
        )

        if requested_name in current_name.casefold():
            partial_matches.append(item)

    # Return the item directly when there is only one clear match.
    if len(partial_matches) == 1:
        return _success({
            "item": partial_matches[0]
        })

    # If multiple items match, return them so the chatbot
    # can ask the user which product they meant.
    if len(partial_matches) > 1:
        return _success({
            "multiple_matches": True,
            "matches": partial_matches,
        })

    return _no_data(
        f"No stock item named '{item_name}' was found in Tally."
    )


def _extract_quantity_number(value: str | None) -> float | None:
    """
    Extract the numeric part from a Tally quantity.

    Examples:
    "10 Nos"   -> 10
    "-18 NOS"  -> -18
    "25 Pcs"   -> 25
    """

    if not value:
        return None

    # Tally quantity fields may contain both number and unit.
    # We only need the numeric part for comparisons.
    match = re.search(
        r"-?\d+(?:\.\d+)?",
        str(value).replace(",", ""),
    )

    if not match:
        return None

    try:
        return float(match.group())
    except ValueError:
        return None


def _parse_stock_value(value: str | None) -> float | None:
    """
    Convert a Tally stock value into a number when possible.
    """

    if not value:
        return None

    clean_value = (
        str(value)
        .replace(",", "")
        .strip()
    )

    try:
        return float(clean_value)
    except ValueError:
        return None


async def get_top_stock_items_tool(
    company_name: str | None = None,
    limit: int = 5,
) -> dict:
    """
    Return stock items with the highest closing stock value.
    """

    stock_items = await fetch_stock_item_list(
        company_name=company_name
    )

    if not stock_items:
        return _no_data(
            "No stock items were found in Tally."
        )

    ranked_items = []

    # Convert stock values into numbers before sorting.
    for item in stock_items:
        closing_value = _parse_stock_value(
            item.get("closing_value")
        )

        if closing_value is None:
            continue

        ranked_items.append({
            **item,
            "numeric_closing_value": closing_value,
        })

    if not ranked_items:
        return _no_data(
            "Stock value information is not available in Tally."
        )

    # Highest absolute value is useful here because Tally
    # may show negative stock values for abnormal inventory.
    ranked_items.sort(
        key=lambda item: abs(
            item["numeric_closing_value"]
        ),
        reverse=True,
    )

    # Keep the result size controlled so chatbot responses
    # do not become unnecessarily large.
    safe_limit = max(
        1,
        min(int(limit or 5), 20),
    )

    return _success({
        "items": ranked_items[:safe_limit],
        "count": min(
            safe_limit,
            len(ranked_items),
        ),
    })
    
async def get_ledger_balance_tool(
    ledger_name: str,
    company_name: str | None = None,
) -> dict:
    """
    Return the current balance of any Tally ledger.
    """

    ledger_name = (ledger_name or "").strip()

    if not ledger_name:
        return _no_data(
            "Please provide a ledger name."
        )

    # Load the ledger list first so we do not send
    # an invalid or misspelled ledger name to Tally.
    ledgers = await fetch_ledger_list(
        company_name=company_name
    )

    matched_ledger = None

    for ledger in ledgers:
        name = (
            ledger.get("name")
            or ""
        ).strip()

        if name.lower() == ledger_name.lower():
            matched_ledger = ledger
            break

    if not matched_ledger:
        return _no_data(
            f"Ledger '{ledger_name}' was not found in Tally."
        )

    # The ledger master already contains the current
    # opening and closing balance in most cases.
    opening_balance = float(
        matched_ledger.get(
            "opening_balance",
            0,
        )
        or 0
    )

    closing_balance = float(
        matched_ledger.get(
            "closing_balance",
            0,
        )
        or 0
    )

    return _success({
        "ledger_name": matched_ledger.get(
            "name"
        ),
        "parent": matched_ledger.get(
            "parent"
        ),
        "opening_balance": opening_balance,
        "closing_balance": closing_balance,
    })


async def get_ledger_transactions_tool(
    ledger_name: str,
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Return transactions posted to a particular Tally ledger.
    """

    ledger_name = (ledger_name or "").strip()

    if not ledger_name:
        return _no_data(
            "Please provide a ledger name."
        )

    # Confirm that the requested ledger exists before
    # trying to load its transactions.
    ledgers = await fetch_ledger_list(
        company_name=company_name
    )

    matched_name = None

    for ledger in ledgers:
        name = (
            ledger.get("name")
            or ""
        ).strip()

        if name.lower() == ledger_name.lower():
            matched_name = name
            break

    if not matched_name:
        return _no_data(
            f"Ledger '{ledger_name}' was not found in Tally."
        )

    # Reuse the common ledger report service.
    # This keeps bank, cash and generic ledger queries
    # consistent with the same Tally data source.
    report = await fetch_ledger_report(
        ledger_name=matched_name,
        company_name=company_name,
        from_date=from_date,
        to_date=to_date,
    )

    entries = report.get(
        "entries",
        [],
    )

    return _success({
        "ledger_name": matched_name,
        "opening_balance": float(
            report.get(
                "opening_balance",
            )
        ),
        "closing_balance": float(
            report.get(
                "closing_balance",
            
            )

        ),
        "count": len(entries),
        "transactions": entries,
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
    })


async def get_negative_stock_items_tool(
    company_name: str | None = None,
) -> dict:
    """
    Return stock items whose closing quantity is below zero.
    """

    stock_items = await fetch_stock_item_list(
        company_name=company_name
    )

    if not stock_items:
        return _no_data(
            "No stock items were found in Tally."
        )

    negative_items = []

    for item in stock_items:
        quantity = _extract_quantity_number(
            item.get("closing_balance")
        )

        # Negative quantity usually needs attention because
        # it can indicate stock issued before receipt or
        # an inventory entry mismatch.
        if quantity is not None and quantity < 0:
            negative_items.append({
                **item,
                "numeric_closing_quantity": quantity,
            })

    if not negative_items:
        return _success({
            "items": [],
            "count": 0,
            "message": "No negative stock items were found.",
        })

    return _success({
        "items": negative_items,
        "count": len(negative_items),
    })
    
def _is_tds_ledger(ledger_name: str | None) -> bool:
    """
    Check whether a ledger name looks like a TDS ledger.
    """

    if not ledger_name:
        return False

    name = ledger_name.strip().lower()

    # TDS ledgers can have different names depending on
    # how the company configured them in Tally.
    return (
        name.startswith("tds")
        or "tds payable" in name
        or "tax deducted at source" in name
    )


async def get_tds_summary_tool(
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Return a summary of TDS ledgers available in Tally.
    """

    # TDS ledgers are normally grouped under Duties & Taxes.
    tax_ledgers = await _load_ledgers_by_parent(
        parent_names={"Duties & Taxes"},
        company_name=company_name,
    )

    # Keep only ledgers that clearly look related to TDS.
    tds_ledgers = [
        ledger
        for ledger in tax_ledgers
        if _is_tds_ledger(
            ledger.get("name")
        )
    ]

    if not tds_ledgers:
        return _no_data(
            "No TDS ledgers were found in Tally."
        )

    ledger_results = []
    total_tds = 0.0

    for ledger in tds_ledgers:
        ledger_name = ledger["name"]

        # Read the ledger report so we can return both
        # the balance and the underlying TDS transactions.
        report = await fetch_ledger_report(
            ledger_name=ledger_name,
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
        )

        closing_balance = float(
            report.get("closing_balance", 0) or 0
        )

        total_tds += abs(closing_balance)

        ledger_results.append({
            "ledger_name": ledger_name,
            "closing_balance": closing_balance,
            "transactions": report.get("entries", []),
        })

    return _success({
        "total_tds": total_tds,
        "ledgers": ledger_results,
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
    })

                # TDS / TAX TOOLS
                
# The following function is used when the user asks about TDS transactions,
# TDS deductions, or TDS entries in Tally.
# It returns all transactions recorded in TDS ledgers for the requested period.

async def get_tds_transactions_tool(
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Return transactions recorded in TDS ledgers.
    """

    tax_ledgers = await _load_ledgers_by_parent(
        parent_names={"Duties & Taxes"},
        company_name=company_name,
    )

    tds_ledgers = [
        ledger
        for ledger in tax_ledgers
        if _is_tds_ledger(
            ledger.get("name")
        )
    ]

    if not tds_ledgers:
        return _no_data(
            "No TDS ledgers were found in Tally."
        )

    transactions = []

    # Read each TDS ledger separately because a company
    # may maintain different TDS sections in different ledgers.
    for ledger in tds_ledgers:
        ledger_name = ledger["name"]

        report = await fetch_ledger_report(
            ledger_name=ledger_name,
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
        )

        for entry in report.get("entries", []):
            transactions.append({
                **entry,
                "ledger_name": ledger_name,
            })

    return _success({
        "transactions": transactions,
        "count": len(transactions),
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
    })

async def get_tds_receivable_tool(
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Return TDS receivable balances.

    A positive TDS ledger closing balance represents
    a debit balance and is treated as TDS receivable.
    """

    tax_ledgers = await _load_ledgers_by_parent(
        parent_names={"Duties & Taxes"},
        company_name=company_name,
    )

    tds_ledgers = [
        ledger
        for ledger in tax_ledgers
        if _is_tds_ledger(
            ledger.get("name")
        )
    ]

    if not tds_ledgers:
        return _no_data(
            "No TDS ledgers were found in Tally."
        )

    receivable_ledgers = []
    total_receivable = 0.0

    for ledger in tds_ledgers:

        ledger_name = ledger.get("name")

        if not ledger_name:
            continue

        report = await fetch_ledger_report(
            ledger_name=ledger_name,
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
        )

        closing_balance = float(
            report.get("closing_balance", 0)
            or 0
        )

        # Debit balance means TDS is receivable.
        if closing_balance <= 0:
            continue

        receivable_amount = abs(
            closing_balance
        )

        total_receivable += (
            receivable_amount
        )

        receivable_ledgers.append({
            "ledger_name": ledger_name,
            "closing_balance": round(
                closing_balance,
                2
            ),
            "receivable_amount": round(
                receivable_amount,
                2
            ),
            "transactions": report.get(
                "entries",
                []
            ),
        })

    if not receivable_ledgers:
        return _no_data(
            "No TDS receivable balance was found "
            "for the selected period."
        )

    return _success({
        "total_tds_receivable": round(
            total_receivable,
            2
        ),
        "ledgers": receivable_ledgers,
        "count": len(
            receivable_ledgers
        ),
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
    })
    
async def get_tds_payable_tool(
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Return TDS payable balances.

    A negative TDS ledger closing balance represents
    a credit balance and is treated as TDS payable.
    """

    tax_ledgers = await _load_ledgers_by_parent(
        parent_names={"Duties & Taxes"},
        company_name=company_name,
    )

    tds_ledgers = [
        ledger
        for ledger in tax_ledgers
        if _is_tds_ledger(
            ledger.get("name")
        )
    ]

    if not tds_ledgers:
        return _no_data(
            "No TDS ledgers were found in Tally."
        )

    payable_ledgers = []
    total_payable = 0.0

    for ledger in tds_ledgers:

        ledger_name = ledger.get("name")

        if not ledger_name:
            continue

        report = await fetch_ledger_report(
            ledger_name=ledger_name,
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
        )

        closing_balance = float(
            report.get("closing_balance", 0)
            or 0
        )

        # Credit balance means TDS is payable.
        if closing_balance >= 0:
            continue

        payable_amount = abs(
            closing_balance
        )

        total_payable += (
            payable_amount
        )

        payable_ledgers.append({
            "ledger_name": ledger_name,
            "closing_balance": round(
                closing_balance,
                2
            ),
            "payable_amount": round(
                payable_amount,
                2
            ),
            "transactions": report.get(
                "entries",
                []
            ),
        })

    if not payable_ledgers:
        return _no_data(
            "No TDS payable balance was found "
            "for the selected period."
        )

    return _success({
        "total_tds_payable": round(
            total_payable,
            2
        ),
        "ledgers": payable_ledgers,
        "count": len(
            payable_ledgers
        ),
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
    })
    
# CASH FLOW TOOLS

async def get_cash_flow_summary_tool(
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Build a simple cash flow summary using Cash and Bank ledgers.
    """

    # Cash flow should come from actual cash and bank movement,
    # because these ledgers represent money coming in and going out.
    money_ledgers = await _load_ledgers_by_parent(
        parent_names={
            "Cash-in-Hand",
            "Bank Accounts",
            "Bank OD A/c",
        },
        company_name=company_name,
    )

    if not money_ledgers:
        return _no_data(
            "No cash or bank ledgers were found in Tally."
        )

    total_inflow = 0.0
    total_outflow = 0.0
    transactions = []

    seen_vouchers = set()

    for ledger in money_ledgers:
        ledger_name = ledger.get("name")

        if not ledger_name:
            continue

        report = await fetch_ledger_report(
            ledger_name=ledger_name,
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
        )

        for entry in report.get("entries", []):
            debit = float(
                entry.get("debit", 0) or 0
            )

            credit = float(
                entry.get("credit", 0) or 0
            )

            # The same voucher can appear through more than one
            # cash or bank ledger, so avoid counting it twice.
            voucher_key = (
                entry.get("date"),
                entry.get("voucher_number")
                or entry.get("voucher_no"),
                entry.get("voucher_type"),
                debit,
                credit,
            )

            if voucher_key in seen_vouchers:
                continue

            seen_vouchers.add(voucher_key)

            total_inflow += abs(debit)
            total_outflow += abs(credit)

            transactions.append({
                **entry,
                "ledger_name": ledger_name,
            })

    net_flow = (
        total_inflow
        - total_outflow
    )

    return _success({
        "total_inflow": total_inflow,
        "total_outflow": total_outflow,
        "net_flow": net_flow,
        "transactions": transactions,
        "count": len(transactions),
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
    })
  
  

async def get_tax_liability_tool(
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Show a combined tax overview using existing
    GST and TDS calculations.

    This tool does not invent statutory values.
    It only combines values returned by the
    existing GST and TDS tools.
    """

    gst_result, tds_result = await asyncio.gather(
        get_gst_summary_tool(
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
        ),
        get_tds_summary_tool(
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
        ),
    )

    # --------------------------------------------------------
    # GST
    # --------------------------------------------------------

    gst_data = {}

    if gst_result.get("success"):
        gst_data = gst_result.get("data", {}) or {}

    gst_input = float(
        gst_data.get("gst_input", 0)
        or gst_data.get("input_tax", 0)
        or 0
    )

    gst_output = float(
        gst_data.get("gst_output", 0)
        or gst_data.get("output_tax", 0)
        or 0
    )

    net_gst = float(
        gst_data.get("net_gst", 0)
        or gst_data.get("net_tax", 0)
        or gst_data.get("net_gst_payable", 0)
        or 0
    )

    # --------------------------------------------------------
    # TDS
    # --------------------------------------------------------

    tds_data = {}

    if tds_result.get("success"):
        tds_data = tds_result.get("data", {}) or {}

    total_tds = float(
        tds_data.get("total_tds", 0)
        or tds_data.get("tds_amount", 0)
        or 0
    )

    # --------------------------------------------------------
    # Combined overview
    # --------------------------------------------------------

    combined_tax_amount = (
        max(net_gst, 0.0)
        + max(total_tds, 0.0)
    )

    return _success({
        "gst": {
            "input_tax": round(
                gst_input,
                2
            ),
            "output_tax": round(
                gst_output,
                2
            ),
            "net_gst_payable": round(
                net_gst,
                2
            ),
        },
        "tds": {
            "total_tds": round(
                total_tds,
                2
            ),
        },
        "combined_tax_amount": round(
            combined_tax_amount,
            2
        ),
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
        "note": (
            "Combined tax amount is an informational overview "
            "based on existing GST and TDS results and should "
            "not be treated as a statutory filing calculation."
        ),
    })
# ============================================================
# PROFITABILITY TOOLS
# ============================================================

async def get_profitability_summary_tool(
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Return a simple profitability summary for the selected period.
    """

    # Reuse the existing financial tools so all chatbot
    # responses follow the same accounting calculations.
    revenue_result = await get_revenue_tool(
        company_name=company_name,
        from_date=from_date,
        to_date=to_date,
    )

    expenses_result = await get_expenses_tool(
        company_name=company_name,
        from_date=from_date,
        to_date=to_date,
    )

    profit_result = await get_net_profit_tool(
        company_name=company_name,
        from_date=from_date,
        to_date=to_date,
    )

    # The financial tools return their values inside "data".
    # Read from that section instead of the top-level response.
    revenue_data = revenue_result.get("data") or {}
    expenses_data = expenses_result.get("data") or {}
    profit_data = profit_result.get("data") or {}

    revenue = revenue_data.get("revenue", 0) or 0
    expenses = expenses_data.get("expenses", 0) or 0
    net_profit = profit_data.get("net_profit", 0) or 0

    # Profit margin tells us how much profit or loss
    # is generated for every rupee of revenue.
    profit_margin = (
        (net_profit / revenue) * 100
        if revenue
        else 0
    )

    return _success({
        "revenue": revenue,
        "expenses": expenses,
        "net_profit": net_profit,
        "profit_margin": profit_margin,
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
    })
    

# TOP BUSINESS ANALYSIS TOOLS

async def get_top_expenses_tool(
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    limit: int = 5,
) -> dict:
    """
    Return the highest expense ledgers for the selected period.
    """

    expense_ledgers = await _load_ledgers_by_parent(
        parent_names={
            "Direct Expenses",
            "Indirect Expenses",
        },
        company_name=company_name,
    )

    if not expense_ledgers:
        return _no_data(
            "No expense ledgers were found in Tally."
        )

    results = []

    for ledger in expense_ledgers:
        ledger_name = ledger.get("name")

        if not ledger_name:
            continue

        report = await fetch_ledger_report(
            ledger_name=ledger_name,
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
        )

        closing_balance = float(
            report.get("closing_balance", 0) or 0
        )

        results.append({
            "ledger_name": ledger_name,
            "amount": abs(closing_balance),
        })

    # Show the largest expense balances first.
    results.sort(
        key=lambda item: item["amount"],
        reverse=True,
    )

    safe_limit = max(
        1,
        min(limit, 20),
    )

    return _success({
        "items": results[:safe_limit],
        "count": len(results[:safe_limit]),
    })


async def get_top_customers_tool(
    company_name: str | None = None,
    limit: int = 5,
) -> dict:
    """
    Return customers with the highest outstanding receivable.
    """

    # Reuse the existing receivables calculation so
    # top customers matches the normal receivables report.
    result = await get_receivables_tool(
        company_name=company_name,
    )

    # get_receivables_tool returns:
    # data -> bills -> list of pending customer bills
    receivables_data = result.get("data") or {}
    items = receivables_data.get("bills", [])

    if not items:
        return _no_data(
            "No customer receivables were found."
        )

    # Rank customers by their outstanding amount.
    items = sorted(
        items,
        key=lambda item: abs(
            float(
                item.get("outstanding_amount", 0) or 0
            )
        ),
        reverse=True,
    )

    # Keep the result size safe and reasonable.
    safe_limit = max(
        1,
        min(limit, 20),
    )

    selected_items = items[:safe_limit]

    return _success({
        "items": selected_items,
        "count": len(selected_items),
    })


async def get_top_suppliers_tool(
    company_name: str | None = None,
    limit: int = 5,
) -> dict:
    """
    Return suppliers with the highest outstanding payable.
    """

    # Reuse the existing payables logic so this ranking
    # matches the normal supplier outstanding report.
    result = await get_payables_tool(
        company_name=company_name,
    )

    # get_payables_tool returns:
    # data -> bills -> list of pending supplier bills
    payables_data = result.get("data") or {}
    items = payables_data.get("bills", [])

    if not items:
        return _no_data(
            "No supplier payables were found."
        )

    # Rank suppliers by the size of their outstanding amount.
    items = sorted(
        items,
        key=lambda item: abs(
            float(
                item.get("outstanding_amount", 0) or 0
            )
        ),
        reverse=True,
    )

    # Keep the result size reasonable.
    safe_limit = max(
        1,
        min(limit, 20),
    )

    selected_items = items[:safe_limit]

    return _success({
        "items": selected_items,
        "count": len(selected_items),
    })
    

# TREND / PERIOD COMPARISON TOOLS


async def get_period_trend_tool(
    company_name: str | None = None,
    current_from_date: date | None = None,
    current_to_date: date | None = None,
    previous_from_date: date | None = None,
    previous_to_date: date | None = None,
) -> dict:
    """
    Compare revenue, expenses and net profit between two periods.
    """

    # Read the current period first.
    current_revenue = await get_revenue_tool(
        company_name=company_name,
        from_date=current_from_date,
        to_date=current_to_date,
    )

    current_expenses = await get_expenses_tool(
        company_name=company_name,
        from_date=current_from_date,
        to_date=current_to_date,
    )

    current_profit = await get_net_profit_tool(
        company_name=company_name,
        from_date=current_from_date,
        to_date=current_to_date,
    )

    # Read the previous period using the same accounting logic.
    previous_revenue = await get_revenue_tool(
        company_name=company_name,
        from_date=previous_from_date,
        to_date=previous_to_date,
    )

    previous_expenses = await get_expenses_tool(
        company_name=company_name,
        from_date=previous_from_date,
        to_date=previous_to_date,
    )

    previous_profit = await get_net_profit_tool(
        company_name=company_name,
        from_date=previous_from_date,
        to_date=previous_to_date,
    )

    current = {
        "revenue": current_revenue.get("revenue", 0) or 0,
        "expenses": current_expenses.get("expenses", 0) or 0,
        "net_profit": current_profit.get("net_profit", 0) or 0,
    }

    previous = {
        "revenue": previous_revenue.get("revenue", 0) or 0,
        "expenses": previous_expenses.get("expenses", 0) or 0,
        "net_profit": previous_profit.get("net_profit", 0) or 0,
    }

    def percentage_change(current_value, previous_value):
        # Avoid division by zero when the previous period has no value.
        if not previous_value:
            return None

        return (
            (current_value - previous_value)
            / abs(previous_value)
        ) * 100

    return _success({
        "current": current,
        "previous": previous,
        "changes": {
            "revenue": percentage_change(
                current["revenue"],
                previous["revenue"],
            ),
            "expenses": percentage_change(
                current["expenses"],
                previous["expenses"],
            ),
            "net_profit": percentage_change(
                current["net_profit"],
                previous["net_profit"],
            ),
        },
    })
    
async def get_sales_by_customer_tool(
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Group posted sales transactions customer-wise.

    Credit Notes reduce customer sales because they
    represent sales returns.
    """

    result = await get_sales_transactions_tool(
        company_name=company_name,
        from_date=from_date,
        to_date=to_date,
    )

    if not result.get("success"):
        return result

    transactions = result.get("data", {}).get(
        "transactions",
        []
    )

    customer_totals = {}

    for transaction in transactions:

        customer_name = (
            transaction.get("party_name")
            or ""
        ).strip()

        if not customer_name:
            continue

        voucher_type = (
            transaction.get("voucher_type")
            or ""
        ).strip().casefold()

        # The sales ledger normally appears on the
        # credit side, so use the available transaction value.
        amount = abs(
            float(
                transaction.get("credit")
                or transaction.get("debit")
                or 0
            )
        )

        # Credit Note means sales return,
        # so it reduces the customer's sales.
        if voucher_type in {
            "credit note",
            "creditnote",
        }:
            amount = -amount

        customer_totals[customer_name] = (
            customer_totals.get(
                customer_name,
                0.0
            )
            + amount
        )

    customers = [
        {
            "customer_name": customer_name,
            "net_sales": round(amount, 2),
        }
        for customer_name, amount
        in customer_totals.items()
    ]

    # Highest sales customer appears first.
    customers.sort(
        key=lambda item: item["net_sales"],
        reverse=True,
    )

    return _success({
        "customers": customers,
        "count": len(customers),
        "total_net_sales": round(
            sum(
                item["net_sales"]
                for item in customers
            ),
            2,
        ),
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
    })

async def get_product_profitability_tool(
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Show product-wise sales contribution.

    True product profitability requires reliable
    product-level cost/COGS data.
    """

    result = await get_sales_by_item_tool(
        company_name=company_name,
        from_date=from_date,
        to_date=to_date,
    )

    if not result.get("success"):
        return result

    data = result.get("data", {})

    items = (
        data.get("items")
        or data.get("products")
        or []
    )

    if not items:
        return _no_data(
            "No product sales data was found for the selected period."
        )

    total_net_sales = sum(
        float(
            item.get("net_sales", 0)
            or 0
        )
        for item in items
    )

    product_analysis = []

    for item in items:

        product_name = (
            item.get("stock_item_name")
            or item.get("item_name")
            or item.get("product_name")
            or "Unknown Product"
        )

        net_sales = float(
            item.get("net_sales", 0)
            or 0
        )

        contribution_percent = (
            (net_sales / total_net_sales) * 100
            if total_net_sales
            else 0.0
        )

        product_analysis.append({
            "product_name": product_name,
            "net_sales": round(
                net_sales,
                2
            ),
            "sales_contribution_percent": round(
                contribution_percent,
                2
            ),

            # Product-level cost data is required
            # before calculating true profitability.
            "cost_of_goods_sold": None,
            "gross_profit": None,
            "profit_margin_percent": None,
        })

    product_analysis.sort(
        key=lambda item: item["net_sales"],
        reverse=True,
    )

    return _success({
        "products": product_analysis,
        "count": len(product_analysis),
        "total_net_sales": round(
            total_net_sales,
            2
        ),
        "profit_calculation_available": False,
        "profit_calculation_note": (
            "Product-level cost of goods sold is not currently "
            "available, so gross profit and profit margin "
            "are not estimated."
        ),
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
    })
async def get_customer_profitability_tool(
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Show customer-wise sales contribution.

    True customer profitability requires customer-specific
    cost/COGS data. Until that is available, the tool does
    not estimate profit or margin.
    """

    result = await get_sales_by_customer_tool(
        company_name=company_name,
        from_date=from_date,
        to_date=to_date,
    )

    if not result.get("success"):
        return result

    data = result.get("data", {})
    customers = data.get("customers", [])

    if not customers:
        return _no_data(
            "No customer sales data was found for the selected period."
        )

    total_net_sales = float(
        data.get("total_net_sales", 0) or 0
    )

    customer_analysis = []

    for customer in customers:

        customer_name = customer.get(
            "customer_name",
            "Unknown Customer"
        )

        net_sales = float(
            customer.get("net_sales", 0) or 0
        )

        contribution_percent = (
            (net_sales / total_net_sales) * 100
            if total_net_sales
            else 0.0
        )

        customer_analysis.append({
            "customer_name": customer_name,
            "net_sales": round(
                net_sales,
                2
            ),
            "sales_contribution_percent": round(
                contribution_percent,
                2
            ),

            # Do not estimate profit without
            # customer-specific cost information.
            "gross_profit": None,
            "profit_margin_percent": None,
        })

    customer_analysis.sort(
        key=lambda item: item["net_sales"],
        reverse=True,
    )

    return _success({
        "customers": customer_analysis,
        "count": len(customer_analysis),
        "total_net_sales": round(
            total_net_sales,
            2
        ),
        "profit_calculation_available": False,
        "profit_calculation_note": (
            "Customer-level cost of goods sold is not available, "
            "so gross profit and profit margin are not estimated."
        ),
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
    })

async def get_discount_analysis_tool(
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Analyze discounts available in posted sales transactions.

    The tool uses only discount values explicitly returned
    from Tally transaction or inventory data.
    """

    result = await get_sales_transactions_tool(
        company_name=company_name,
        from_date=from_date,
        to_date=to_date,
    )

    if not result.get("success"):
        return result

    transactions = (
        result.get("data", {})
        .get("transactions", [])
    )

    if not transactions:
        return _no_data(
            "No sales transactions were found "
            "for the selected period."
        )

    total_discount = 0.0
    discount_transactions = []
    customer_totals = {}
    item_totals = {}

    for transaction in transactions:

        voucher_type = (
            transaction.get("voucher_type")
            or ""
        ).strip().casefold()

        # Ignore sales returns in the first version
        # unless explicit return-discount handling is added.
        if voucher_type in {
            "credit note",
            "creditnote",
        }:
            continue

        party_name = (
            transaction.get("party_name")
            or "Unknown Customer"
        ).strip()

        voucher_number = (
            transaction.get("voucher_number")
            or ""
        )

        transaction_discount = 0.0

        # Some parsers may expose voucher-level discount.
        voucher_discount = transaction.get(
            "discount_amount"
        )

        if voucher_discount is not None:
            try:
                transaction_discount += abs(
                    float(voucher_discount)
                )
            except (TypeError, ValueError):
                pass

        stock_items = transaction.get(
            "stock_items",
            []
        )

        for stock_item in stock_items:

            item_name = (
                stock_item.get("stock_item_name")
                or stock_item.get("item_name")
                or "Unknown Item"
            ).strip()

            item_discount = (
                stock_item.get("discount_amount")
                or stock_item.get("discount")
            )

            if item_discount is None:
                continue

            try:
                discount_value = abs(
                    float(item_discount)
                )
            except (TypeError, ValueError):
                continue

            transaction_discount += discount_value

            item_totals[item_name] = (
                item_totals.get(item_name, 0.0)
                + discount_value
            )

        if transaction_discount <= 0:
            continue

        total_discount += transaction_discount

        customer_totals[party_name] = (
            customer_totals.get(
                party_name,
                0.0
            )
            + transaction_discount
        )

        discount_transactions.append({
            "voucher_number": voucher_number,
            "party_name": party_name,
            "discount_amount": round(
                transaction_discount,
                2
            ),
        })

    customers = [
        {
            "customer_name": customer,
            "discount_amount": round(
                amount,
                2
            ),
        }
        for customer, amount
        in customer_totals.items()
    ]

    customers.sort(
        key=lambda item: item["discount_amount"],
        reverse=True,
    )

    items = [
        {
            "item_name": item,
            "discount_amount": round(
                amount,
                2
            ),
        }
        for item, amount
        in item_totals.items()
    ]

    items.sort(
        key=lambda item: item["discount_amount"],
        reverse=True,
    )

    return _success({
        "total_discount": round(
            total_discount,
            2
        ),
        "discount_transactions": discount_transactions,
        "customers": customers,
        "items": items,
        "transaction_count": len(
            discount_transactions
        ),
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
        "source_note": (
            "Discount values are reported only when "
            "explicit discount data is available from Tally."
        ),
    })
    
async def get_purchases_by_supplier_tool(
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Group posted purchase transactions supplier-wise.

    Debit Notes reduce purchases because they normally
    represent purchase returns.
    """

    result = await get_purchase_transactions_tool(
        company_name=company_name,
        from_date=from_date,
        to_date=to_date,
    )

    if not result.get("success"):
        return result

    transactions = result.get("data", {}).get(
        "transactions",
        []
    )

    supplier_totals = {}

    for transaction in transactions:

        supplier_name = (
            transaction.get("party_name")
            or ""
        ).strip()

        if not supplier_name:
            continue

        voucher_type = (
            transaction.get("voucher_type")
            or ""
        ).strip().casefold()

        amount = abs(
            float(
                transaction.get("debit")
                or transaction.get("credit")
                or 0
            )
        )

        # Debit Note represents a purchase return,
        # so reduce the supplier's purchase total.
        if voucher_type in {
            "debit note",
            "debitnote",
        }:
            amount = -amount

        supplier_totals[supplier_name] = (
            supplier_totals.get(
                supplier_name,
                0.0
            )
            + amount
        )

    suppliers = [
        {
            "supplier_name": supplier_name,
            "net_purchases": round(amount, 2),
        }
        for supplier_name, amount
        in supplier_totals.items()
    ]

    # Highest purchase value appears first.
    suppliers.sort(
        key=lambda item: item["net_purchases"],
        reverse=True,
    )

    return _success({
        "suppliers": suppliers,
        "count": len(suppliers),
        "total_net_purchases": round(
            sum(
                item["net_purchases"]
                for item in suppliers
            ),
            2,
        ),
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
    })
    
async def get_sales_by_item_tool(
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Group posted sales transactions item-wise.

    Sales increase the item's sales value.
    Credit Notes reduce it because they represent sales returns.
    """

    result = await get_sales_transactions_tool(
        company_name=company_name,
        from_date=from_date,
        to_date=to_date,
    )

    if not result.get("success"):
        return result

    transactions = (
        result.get("data", {})
        .get("transactions", [])
    )

    item_totals = {}
    seen_rows = set()

    for transaction in transactions:

        voucher_type = (
            transaction.get("voucher_type")
            or ""
        ).strip().casefold()

        voucher_number = (
            transaction.get("voucher_number")
            or ""
        ).strip()

        voucher_date = (
            transaction.get("date")
            or ""
        )

        party_name = (
            transaction.get("party_name")
            or ""
        ).strip()

        stock_items = transaction.get(
            "stock_items",
            [],
        )

        for stock_item in stock_items:

            item_name = (
                stock_item.get("stock_item_name")
                or ""
            ).strip()

            if not item_name:
                continue

            raw_amount = float(
                stock_item.get("amount", 0)
                or 0
            )

            amount = abs(raw_amount)

            # Credit Notes reduce net sales.
            if voucher_type in {
                "credit note",
                "creditnote",
            }:
                amount = -amount

            # A voucher may be returned while processing
            # more than one sales ledger. Avoid counting
            # the same inventory row twice.
            row_key = (
                voucher_date,
                voucher_type,
                voucher_number,
                party_name.casefold(),
                item_name.casefold(),
                round(raw_amount, 2),
                stock_item.get("actual_quantity", ""),
                stock_item.get("billed_quantity", ""),
            )

            if row_key in seen_rows:
                continue

            seen_rows.add(row_key)

            if item_name not in item_totals:
                item_totals[item_name] = {
                    "sales_value": 0.0,
                    "transaction_count": 0,
                }

            item_totals[item_name][
                "sales_value"
            ] += amount

            item_totals[item_name][
                "transaction_count"
            ] += 1

    items = []

    for item_name, values in item_totals.items():

        items.append({
            "stock_item_name": item_name,
            "net_sales": round(
                values["sales_value"],
                2,
            ),
            "transaction_count": (
                values["transaction_count"]
            ),
        })

    # Highest sales-value item appears first.
    items.sort(
        key=lambda item: item["net_sales"],
        reverse=True,
    )

    return _success({
        "items": items,
        "count": len(items),
        "total_net_sales": round(
            sum(
                item["net_sales"]
                for item in items
            ),
            2,
        ),
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
    })


async def get_purchases_by_item_tool(
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Group posted purchase transactions item-wise.

    Purchases increase the item's purchase value.
    Debit Notes reduce it because they represent purchase returns.
    """

    result = await get_purchase_transactions_tool(
        company_name=company_name,
        from_date=from_date,
        to_date=to_date,
    )

    if not result.get("success"):
        return result

    transactions = (
        result.get("data", {})
        .get("transactions", [])
    )

    item_totals = {}
    seen_rows = set()

    for transaction in transactions:

        voucher_type = (
            transaction.get("voucher_type")
            or ""
        ).strip().casefold()

        voucher_number = (
            transaction.get("voucher_number")
            or ""
        ).strip()

        voucher_date = (
            transaction.get("date")
            or ""
        )

        party_name = (
            transaction.get("party_name")
            or ""
        ).strip()

        stock_items = transaction.get(
            "stock_items",
            [],
        )

        for stock_item in stock_items:

            item_name = (
                stock_item.get("stock_item_name")
                or ""
            ).strip()

            if not item_name:
                continue

            raw_amount = float(
                stock_item.get("amount", 0)
                or 0
            )

            amount = abs(raw_amount)

            # Debit Notes reduce net purchases.
            if voucher_type in {
                "debit note",
                "debitnote",
            }:
                amount = -amount

            # Avoid counting the same inventory row twice
            # when one voucher appears through multiple ledgers.
            row_key = (
                voucher_date,
                voucher_type,
                voucher_number,
                party_name.casefold(),
                item_name.casefold(),
                round(raw_amount, 2),
                stock_item.get("actual_quantity", ""),
                stock_item.get("billed_quantity", ""),
            )

            if row_key in seen_rows:
                continue

            seen_rows.add(row_key)

            if item_name not in item_totals:
                item_totals[item_name] = {
                    "purchase_value": 0.0,
                    "transaction_count": 0,
                }

            item_totals[item_name][
                "purchase_value"
            ] += amount

            item_totals[item_name][
                "transaction_count"
            ] += 1

    items = []

    for item_name, values in item_totals.items():

        items.append({
            "stock_item_name": item_name,
            "net_purchases": round(
                values["purchase_value"],
                2,
            ),
            "transaction_count": (
                values["transaction_count"]
            ),
        })

    # Highest purchase-value item appears first.
    items.sort(
        key=lambda item: item["net_purchases"],
        reverse=True,
    )

    return _success({
        "items": items,
        "count": len(items),
        "total_net_purchases": round(
            sum(
                item["net_purchases"]
                for item in items
            ),
            2,
        ),
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
    })
async def get_top_selling_items_tool(
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    limit: int = 5,
) -> dict:
    """
    Return the highest-selling items based on net sales value.

    This reuses the item-wise sales result so we do not
    make another separate Tally request.
    """

    result = await get_sales_by_item_tool(
        company_name=company_name,
        from_date=from_date,
        to_date=to_date,
    )

    if not result.get("success"):
        return result

    items = (
        result.get("data", {})
        .get("items", [])
    )

    # Keep limit within a safe range.
    limit = max(
        1,
        min(
            int(limit or 5),
            20,
        ),
    )

    top_items = sorted(
        items,
        key=lambda item: float(
            item.get("net_sales", 0)
            or 0
        ),
        reverse=True,
    )[:limit]

    return _success({
        "items": top_items,
        "count": len(top_items),
        "limit": limit,
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
    })


async def get_low_selling_items_tool(
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    limit: int = 5,
) -> dict:
    """
    Return the lowest-selling items based on net sales value.

    Items with smaller positive sales values appear first.
    """

    result = await get_sales_by_item_tool(
        company_name=company_name,
        from_date=from_date,
        to_date=to_date,
    )

    if not result.get("success"):
        return result

    items = (
        result.get("data", {})
        .get("items", [])
    )

    limit = max(
        1,
        min(
            int(limit or 5),
            20,
        ),
    )

    # Ignore items with zero or negative net sales here.
    # Returns are handled separately through Credit Notes.
    positive_items = [
        item
        for item in items
        if float(
            item.get("net_sales", 0)
            or 0
        ) > 0
    ]

    low_items = sorted(
        positive_items,
        key=lambda item: float(
            item.get("net_sales", 0)
            or 0
        ),
    )[:limit]

    return _success({
        "items": low_items,
        "count": len(low_items),
        "limit": limit,
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
    })
