"""Deterministic follow-up periods and entity changes within one chat."""
from calendar import monthrange
from datetime import date, datetime
import re

from app.chatbot.date_resolver import MONTHS, DateRange, resolve_date_range


FOLLOW_UP = re.compile(r"^(?:now\s+)?(?:what\s+about|how\s+about|and|for)\s+(.+?)[?.!]*$", re.I)


def is_follow_up(message):
    match = FOLLOW_UP.match(message.strip())
    if not match:
        return False
    if re.match(r"^(?:show|list|get|display|export)\b", match.group(1), re.I):
        return False
    return match.group(1).strip(" ?.!").casefold() not in {
        "receivables", "payables", "cash transactions", "bank transactions",
        "sales", "purchases", "expenses", "revenue", "net profit",
    }


def parse_context_date(value):
    if isinstance(value, date):
        return value
    for pattern in ("%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(str(value), pattern).date()
        except ValueError:
            continue
    return None


def follow_up_selection(message, session, date_aware_tools):
    match = FOLLOW_UP.match(message.strip())
    if not match or not session or session.get("last_tool") not in date_aware_tools:
        return None
    target = match.group(1).strip(" ?.!")
    arguments = dict(session.get("last_arguments") or {})
    metric = {"sales": "revenue", "revenue": "revenue", "purchases": "purchases", "expenses": "expenses", "net profit": "net_profit", "profit": "net_profit"}.get(target.casefold())
    if session["last_tool"] == "get_monthly_summary" and metric:
        arguments["metric"] = metric
        return {"tool_name": session["last_tool"], "arguments": arguments, "error": None}
    period = session.get("last_period") or {}
    start = parse_context_date(period.get("from_date"))
    end = parse_context_date(period.get("to_date"))
    relative_month = re.fullmatch(r"(?:the\s+)?(next|previous|last)\s+month", target, re.I)
    if relative_month and (start or end):
        anchor = start or end
        offset = 1 if relative_month.group(1).lower() == "next" else -1
        year, month_index = divmod(anchor.year * 12 + anchor.month - 1 + offset, 12)
        month = month_index + 1
        resolved = DateRange(date(year, month, 1), date(year, month, monthrange(year, month)[1]), target)
    elif re.fullmatch(r"(?:the\s+)?same\s+(?:period|month)\s+last\s+year", target, re.I) and start and end:
        def previous(value):
            return value.replace(year=value.year - 1, day=min(value.day, monthrange(value.year - 1, value.month)[1]))
        resolved = DateRange(previous(start), previous(end), "same period last year")
    else:
        resolved = resolve_date_range(target)
        # A bare month belongs to the active Indian financial year of the
        # previous report. Thus December 2025 -> March means March 2026.
        bare_month = re.fullmatch("(" + "|".join(MONTHS) + ")", target, re.I)
        if bare_month and (start or end):
            anchor = start or end
            month = MONTHS[bare_month.group(1).lower()]
            calendar_year = bool(start and end and start.month == 1 and start.day == 1 and end.month == 12 and end.day == 31 and start.year == end.year)
            fy_year = anchor.year - (anchor.month < 4)
            year = anchor.year if calendar_year else fy_year + (month < 4)
            resolved = DateRange(date(year, month, 1), date(year, month, monthrange(year, month)[1]), target)
    if resolved:
        if session["last_tool"] in {"get_trial_balance", "get_balance_sheet"} and resolved.from_date == resolved.to_date:
            arguments.pop("from_date", None)
        else:
            arguments["from_date"] = resolved.from_date.strftime("%d-%m-%Y")
        arguments["to_date"] = resolved.to_date.strftime("%d-%m-%Y")
        return {"tool_name": session["last_tool"], "arguments": arguments, "error": None}
    for key in ("ledger_name", "party_name", "customer_name", "supplier_name", "item_name"):
        if arguments.get(key):
            arguments[key] = target
            return {"tool_name": session["last_tool"], "arguments": arguments, "error": None}
    return None
