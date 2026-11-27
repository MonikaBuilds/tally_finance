"""Monthly reports from scoped Tally ledger movements or verified native P&L."""
from calendar import monthrange
from datetime import date

from app.tally.service import client, fetch_ledger_list, fetch_ledger_report
from app.tally.xml_builders.company import build_company_request
from app.tally.parsers.company import parse_companies
from app.tally.native_reports import fetch_native_balances, ledgers_under_groups, fetch_native_profit_loss_summary


async def company_financial_year(company_name):
    companies = parse_companies(await client.send_xml(build_company_request()))["companies"]
    company = next((c for c in companies if c["name"].casefold() == (company_name or "").casefold()), None)
    if not company:
        raise ValueError("The selected company is not open in Tally.")
    raw = company.get("starting_from") or company.get("books_from")
    if not raw:
        native = await fetch_native_profit_loss_summary(company_name, None, None)
        if native.get("period_verified") and native.get("tally_from_date") and native.get("tally_to_date"):
            return date.fromisoformat(native["tally_from_date"]), date.fromisoformat(native["tally_to_date"])
        raise ValueError("Tally did not return the company's current period; specify a period.")
    anchor = date.fromisoformat(raw)
    year = anchor.year - (anchor.month < 4)
    return date(year, 4, 1), date(year + 1, 3, 31)


def month_periods(start, end):
    cursor = start.replace(day=1)
    while cursor <= end:
        last = date(cursor.year, cursor.month, monthrange(cursor.year, cursor.month)[1])
        yield max(start, cursor), min(end, last)
        cursor = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)


async def get_monthly_summary_tool(company_name=None, from_date=None, to_date=None, metric="revenue"):
    if metric not in {"revenue", "expenses", "purchases", "net_profit"}:
        raise ValueError("Choose sales, purchases, expenses, or net profit for a monthly report.")
    default_from, default_to = (None, None)
    if not from_date or not to_date:
        default_from, default_to = await company_financial_year(company_name)
    start, end = from_date or default_from, to_date or default_to
    if start > end:
        raise ValueError("The start date must not be after the end date.")
    if (end.year - start.year) * 12 + end.month - start.month >= (24 if metric == "net_profit" else 120):
        raise ValueError("Select at most 24 months for monthly profit or 120 months for ledger movements.")
    periods = [{"month": a.strftime("%Y-%m"), "from_date": a.isoformat(), "to_date": b.isoformat(), "value": 0.0}
               for a, b in month_periods(start, end)]
    ledger_names = []
    if metric == "net_profit":
        for row in periods:
            native = await fetch_native_profit_loss_summary(company_name, date.fromisoformat(row["from_date"]), date.fromisoformat(row["to_date"]))
            profit, loss = native.get("nett_profit"), native.get("nett_loss")
            if not native.get("period_verified") or not (profit or loss):
                row.update(value=None, status="unavailable", reason="Tally did not verify a net result for this exact month.")
            elif profit and profit.get("amount") is not None:
                row.update(value=abs(profit["amount"]), status="verified")
            elif loss and loss.get("amount") is not None:
                row.update(value=-abs(loss["amount"]), status="verified")
            else:
                row.update(value=None, status="unavailable", reason="Tally left the result amount blank.")
        method = "tally_report_rows"
        source = "Tally's Nett Profit / Nett Loss row, with each month's period verified"
    else:
        roots = {"Sales Accounts"} if metric == "revenue" else {"Purchase Accounts"} if metric == "purchases" else {"Purchase Accounts", "Direct Expenses", "Indirect Expenses"}
        ledgers = await fetch_ledger_list(company_name=company_name)
        groups = await fetch_native_balances("Group", company_name, end)
        matched = ledgers_under_groups(groups, ledgers, roots)
        ledger_names = [ledger["name"] for ledger, _root in matched]
        if not ledger_names:
            return {"success": False, "source": "tally", "message": "Tally has no ledgers for the requested monthly metric.", "data": None}
        values = {row["month"]: row for row in periods}
        for name in ledger_names:
            report = await fetch_ledger_report(ledger_name=name, company_name=company_name, from_date=start, to_date=end)
            if not isinstance(report.get("entries"), list):
                raise ValueError("Tally did not return complete ledger movements; no monthly figures are shown.")
            for entry in report["entries"]:
                raw = str(entry.get("date") or "")
                try:
                    posted = date.fromisoformat(raw)
                except ValueError:
                    raise ValueError("A ledger movement has no valid date; monthly figures cannot be verified.") from None
                if not start <= posted <= end:
                    continue
                if entry.get("is_cancelled") or entry.get("is_optional"):
                    continue
                if entry.get("debit") is None and entry.get("credit") is None:
                    raise ValueError("A ledger movement has no debit/credit amount; no monthly figures are shown.")
                debit, credit = float(entry.get("debit") or 0), float(entry.get("credit") or 0)
                values[posted.strftime("%Y-%m")]["value"] += credit - debit if metric == "revenue" else debit - credit
        for row in periods:
            row.update(value=round(row["value"], 2), status="verified")
        method = "application_aggregation"
        source = "Monthly net ledger movements: credits minus debits for sales; debits minus credits for purchases/expenses. Taxes outside these groups are excluded."
    return {"success": True, "source": "tally", "calculation_method": method, "data": {
        "metric": metric, "periods": periods, "count": len(periods), "ledgers": ledger_names,
        "from_date": start.isoformat(), "to_date": end.isoformat(), "method": source,
    }}
