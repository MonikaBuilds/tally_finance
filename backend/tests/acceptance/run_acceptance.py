"""
End-to-end acceptance run against LIVE Tally, the real MySQL RBAC tables
and the configured AI provider.

    cd backend
    .venv/Scripts/python.exe -m tests.acceptance.run_acceptance --out <dir>

What it does
- Creates temporary MySQL users for each role (deleted at the end).
- Logs in through the real /auth/login (cookies + CSRF) and calls the real
  /chat, report and export APIs in-process.
- Fetches Tally's own raw reports independently and checks every rupee
  amount shown to the user against numbers that appear in Tally's output
  (anti-fabrication), and record counts against Tally's raw record counts.
- Writes results.csv, results.json and report.md. A case is PASS only when
  it actually ran and every check succeeded.

Expected values are always taken from Tally's raw responses, never from a
Python calculation.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import secrets
import statistics
import sys
import time
import tracemalloc
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import httpx  # noqa: E402

COMPANY = "ABC Pvt Ltd"
FY_FROM = date(2025, 4, 1)
FY_TO = date(2026, 3, 31)
TODAY = date.today()

# ------------------------------------------------------------------
# Raw Tally reference data (fetched independently of the chatbot tools)
# ------------------------------------------------------------------

RAW: dict[str, str] = {}
REF: dict[str, Any] = {}

_NUMBER_RE = re.compile(r"\(?-?\)?\d[\d,]*\.?\d*")


def _decimal(text: str) -> Decimal | None:
    cleaned = text.replace(",", "").replace("(", "").replace(")", "").lstrip("-")
    if not cleaned or cleaned == ".":
        return None
    try:
        return Decimal(cleaned).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def _amount_corpus() -> set[Decimal]:
    values = set()
    for text in RAW.values():
        for match in _NUMBER_RE.findall(text):
            value = _decimal(match)
            if value is not None:
                values.add(value)
    return values


async def fetch_reference() -> None:
    from app.tally.client import TallyClient
    from app.tally.dashboard import (
        collection_request,
        parse_outstanding_table,
        report_request,
    )
    from app.tally.parsers.common import parse_xml
    from app.tally.xml_builders import (
        build_balance_sheet_request,
        build_ledger_report_request,
        build_stock_summary_request,
        build_trial_balance_request,
    )
    from app.tally.xml_builders.financial import (
        build_bills_payable_request,
        build_bills_receivable_request,
        build_profit_loss_request,
    )
    from app.tally.xml_builders.ledger import build_day_book_request

    client = TallyClient()
    pl_fy = build_profit_loss_request(company_name=COMPANY, from_date=FY_FROM, to_date=FY_TO)
    pl_dec = build_profit_loss_request(company_name=COMPANY, from_date=date(2025, 12, 1), to_date=date(2025, 12, 31))

    requests = {
        "bills_rx_html": report_request(build_bills_receivable_request(COMPANY), html=True, as_of=TODAY),
        "bills_px_html": report_request(build_bills_payable_request(COMPANY), html=True, as_of=TODAY),
        "pl_fy_xml": pl_fy,
        "pl_fy_html": report_request(pl_fy, html=True),
        "pl_dec_html": report_request(pl_dec, html=True),
        "groups_xml": collection_request(COMPANY, TODAY, "Group"),
        "ledgers_xml": collection_request(COMPANY, TODAY, "Ledger"),
        "day_book_xml": build_day_book_request(company_name=COMPANY, from_date=FY_FROM, to_date=FY_TO),
        "tb_xml": build_trial_balance_request(company_name=COMPANY, to_date=FY_TO),
        "bs_xml": build_balance_sheet_request(company_name=COMPANY, to_date=FY_TO),
        "hdfc_ledger_xml": build_ledger_report_request(ledger_name="HDFC Bank", from_date=FY_FROM, to_date=FY_TO, company_name=COMPANY),
        "stock_xml": build_stock_summary_request(company_name=COMPANY, to_date=FY_TO),
    }

    for name, request in requests.items():
        try:
            RAW[name] = await client.send_xml(request)
        except Exception as exc:  # recorded, not hidden
            RAW[name] = ""
            REF.setdefault("reference_errors", {})[name] = f"{type(exc).__name__}: {exc}"

    # Raw voucher counts from Tally's own Day Book export.
    vouchers = []
    if RAW["day_book_xml"]:
        root = parse_xml(RAW["day_book_xml"])
        for v in root.findall(".//VOUCHER"):
            if not v.findtext("DATE"):
                continue  # empty element, not a voucher
            vouchers.append({
                "date": v.findtext("DATE"),
                "type": v.findtext("VOUCHERTYPENAME"),
                "inventory_lines": len(v.findall(".//ALLINVENTORYENTRIES.LIST")) + len(v.findall(".//INVENTORYENTRIES.LIST")),
            })
    REF["vouchers"] = vouchers
    REF["voucher_count_fy"] = len(vouchers)
    REF["vouchers_by_type"] = {}
    for v in vouchers:
        REF["vouchers_by_type"][v["type"]] = REF["vouchers_by_type"].get(v["type"], 0) + 1
    REF["vouchers_on"] = lambda iso: sum(1 for v in vouchers if v["date"] == iso.replace("-", ""))

    rx = parse_outstanding_table(RAW["bills_rx_html"]) if RAW["bills_rx_html"] else {}
    px = parse_outstanding_table(RAW["bills_px_html"]) if RAW["bills_px_html"] else {}
    REF["rx_raw_total"] = rx.get("raw_total")
    REF["rx_bill_count"] = len(rx.get("bills", []))
    REF["rx_overdue_count"] = sum(1 for b in rx.get("bills", []) if (b.get("days_overdue") or 0) > 0)
    REF["px_raw_total"] = px.get("raw_total")
    REF["px_bill_count"] = len(px.get("bills", []))

    REF["corpus"] = _amount_corpus()


# ------------------------------------------------------------------
# Test cases
# ------------------------------------------------------------------

@dataclass
class Case:
    id: str
    section: str
    role: str
    query: str
    expect_tools: set[str] | None = None        # acceptable intents
    expect_success: bool | None = True
    checks: list[str] = field(default_factory=list)
    expect_count: Callable[[], int] | None = None
    count_key: str = "count"
    expect_text: str | None = None
    session: str | None = None
    severity: str = "High"
    note: str = ""


ANY_LLM = None  # expect_tools=None: any approved tool is acceptable

CASES: list[Case] = [
    # ---------------- Day Book ----------------
    Case("DB-01", "Day Book", "full", "Show the day book for 01-04-2025", {"get_day_book"},
         checks=["count", "amounts"], expect_count=lambda: REF["vouchers_on"]("2025-04-01")),
    Case("DB-02", "Day Book", "full", "Give me the complete Day Book for FY 2025-26", {"get_day_book"},
         checks=["count", "amounts", "complete"], expect_count=lambda: REF["voucher_count_fy"]),
    Case("DB-03", "Day Book", "full", "daybook for December 2025", {"get_day_book"},
         checks=["count", "amounts"], expect_count=lambda: sum(1 for v in REF["vouchers"] if v["date"].startswith("202512"))),
    Case("DB-04", "Day Book", "full", "dairy", {"get_day_book"}, checks=["amounts"],
         note="Bare 'dairy' = Day Book shortcut"),
    Case("DB-05", "Day Book", "full", "Show all transactions from 1 April 2025 to 31 March 2026", {"get_day_book"},
         checks=["count", "amounts"], expect_count=lambda: REF["voucher_count_fy"]),
    Case("DB-06", "Day Book", "full", "Show today's day book", {"get_day_book"}, checks=["count"],
         expect_count=lambda: 0, note="No entries today: must say none, not invent"),
    Case("DB-07", "Day Book", "full", "Show all journal entries for FY 2025-26", {"get_day_book"},
         checks=["amounts"], note="Journal voucher filter"),
    Case("DB-08", "Day Book", "full", "Show contra entries for FY 2025-26", {"get_day_book", "get_bank_transactions", "get_cash_transactions"},
         checks=["amounts"]),
    # ---------------- Sales / purchases / returns ----------------
    Case("SP-01", "Sales", "full", "Show every sales voucher with item details for FY 2025-26", {"get_sales_transactions", "get_day_book"},
         checks=["amounts"]),
    Case("SP-02", "Sales", "full", "List all sales for December 2025", {"get_sales_transactions"}, checks=["amounts"]),
    Case("SP-03", "Sales", "full", "Show sales by customer for FY 2025-26", {"get_sales_by_customer"}, checks=["amounts"]),
    Case("SP-04", "Purchases", "full", "List all purchase entries for April 2025", {"get_purchase_transactions"}, checks=["amounts"]),
    Case("SP-05", "Purchases", "full", "Show purchases by supplier for FY 2025-26", {"get_purchases_by_supplier"}, checks=["amounts"]),
    Case("SP-06", "Returns", "full", "Show sales returns for FY 2025-26", {"get_credit_note_transactions"}, checks=["amounts"]),
    Case("SP-07", "Returns", "full", "Show purchase returns for FY 2025-26", {"get_debit_note_transactions"}, checks=["amounts"]),
    Case("SP-08", "Returns", "full", "Show credit notes for FY 2025-26", {"get_credit_note_transactions"}, checks=["amounts"]),
    Case("SP-09", "Returns", "full", "Show debit notes for FY 2025-26", {"get_debit_note_transactions"}, checks=["amounts"]),
    Case("SP-10", "Receipts", "full", "Show receipts for FY 2025-26", {"get_receipt_transactions"}, checks=["amounts"]),
    Case("SP-11", "Payments", "full", "Show payments made in FY 2025-26", {"get_payment_transactions"}, checks=["amounts"]),
    Case("SP-12", "Receipts/Payments", "full", "Show today's receipts and payments", {"get_receipt_transactions", "get_payment_transactions", "get_day_book", "get_cash_transactions", "get_bank_transactions"},
         checks=["amounts"]),
    Case("SP-13", "Sales", "full", "Show my monthly sales", {"get_monthly_summary"}, checks=["amounts"]),
    Case("SP-14", "Sales", "full", "Top selling items in FY 2025-26", {"get_top_selling_items"}, checks=["amounts"]),
    # ---------------- Revenue / P&L ----------------
    Case("PL-01", "Profit & Loss", "full", "Generate my Profit & Loss report for FY 2025-26", {"get_profit_loss"}, checks=["amounts"]),
    Case("PL-02", "Revenue", "full", "What is my revenue for FY 2025-26?", {"get_revenue"}, checks=["amounts", "native"],
         expect_text="74,10,000"),
    Case("PL-03", "Revenue", "full", "What is my revenue for December 2025?", {"get_revenue"}, checks=["amounts"]),
    Case("PL-04", "Revenue", "full", "What is my revenue for April 2025?", {"get_revenue"}, expect_success=False,
         note="Educational Tally substitutes 30-day months: must refuse, never show FY figure as April"),
    Case("PL-05", "Net profit", "full", "What is my net profit for FY 2025-26?", {"get_net_profit"}, checks=["amounts", "native"],
         expect_text="5,19,053.47"),
    Case("PL-06", "Expenses", "full", "What are my total expenses for FY 2025-26?", {"get_expenses"}, checks=["derived_label"]),
    Case("PL-07", "Expenses", "full", "Top 5 expenses for FY 2025-26", {"get_top_expenses"}, checks=["amounts", "derived_label"]),
    Case("PL-08", "Comparison", "full", "Compare revenue this month with last month", {"get_period_comparison"}, expect_success=None,
         note="No data in Nov/Oct 2026 - must not invent"),
    Case("PL-09", "Comparison", "full", "Compare profit and loss of December 2025 vs January 2026", {"get_period_comparison", "get_period_trend"}, expect_success=None),
    Case("PL-10", "Financial summary", "full", "Give me a financial summary for FY 2025-26", {"get_financial_summary"}, checks=["amounts"]),
    # ---------------- Statements ----------------
    Case("TB-01", "Trial Balance", "full", "Show the trial balance as on 31 March 2026", {"get_trial_balance"}, checks=["amounts"]),
    Case("BS-01", "Balance Sheet", "full", "Show my balance sheet as on 31-03-2026", {"get_balance_sheet"}, checks=["amounts"]),
    # ---------------- Cash & bank ----------------
    Case("CB-01", "Bank", "full", "What is my closing bank balance?", {"get_bank_balance"}, checks=["amounts", "native"],
         expect_text="32,85,000"),
    Case("CB-02", "Cash", "full", "How much cash in hand do we have?", {"get_cash_balance"}, checks=["amounts", "native"],
         expect_text="10,000"),
    Case("CB-03", "Bank", "full", "Show HDFC Bank balance", {"get_bank_balance", "get_ledger_balance"}, checks=["amounts"]),
    Case("CB-04", "Bank", "full", "Show bank transactions for FY 2025-26", {"get_bank_transactions"}, checks=["amounts"]),
    Case("CB-05", "Cash", "full", "Show cash flow for FY 2025-26", {"get_cash_flow_summary"}, checks=["derived_label"]),
    # ---------------- Receivables / payables ----------------
    Case("RX-01", "Receivables", "full", "Who owes us money?", {"get_receivables", "get_outstanding_summary", "get_party_outstanding_summary", "get_top_receivables"},
         checks=["amounts"]),
    Case("RX-02", "Receivables", "full", "What are my total receivables?", {"get_receivables"}, checks=["amounts", "native", "count"],
         expect_count=lambda: REF["rx_bill_count"], expect_text="36,30,000"),
    Case("RX-03", "Receivables", "full", "Show all overdue customer balances", {"get_overdue_receivables", "get_aged_receivables"},
         checks=["amounts"]),
    Case("RX-04", "Receivables", "full", "Top 5 customers who owe us", {"get_top_receivables", "get_highest_receivable"}, checks=["amounts"]),
    Case("RX-05", "Receivables", "full", "Ageing analysis of receivables", {"get_aged_receivables"}, checks=["amounts", "derived_label"]),
    Case("PX-01", "Payables", "full", "Whom do I need to pay?", {"get_payables", "get_top_payables", "get_outstanding_summary"}, checks=["amounts"]),
    Case("PX-02", "Payables", "full", "What are my total payables?", {"get_payables"}, checks=["amounts", "native", "count"],
         expect_count=lambda: REF["px_bill_count"], expect_text="4,72,000"),
    Case("PX-03", "Payables", "full", "Show overdue payables", {"get_overdue_payables", "get_aged_payables"}, checks=["amounts"]),
    Case("OS-01", "Outstanding", "full", "Which invoices are pending?", {"get_pending_invoices"}, checks=["amounts"]),
    Case("OS-02", "Outstanding", "full", "What are my outstanding receivables and payables?", {"get_outstanding_summary", "get_receivables", "get_payables"}, checks=["amounts"]),
    # ---------------- Ledgers ----------------
    Case("LG-01", "Ledger", "full", "Give me the complete ledger statement of HDFC Bank for FY 2025-26", {"get_ledger_report", "get_ledger_transactions", "get_bank_transactions"},
         checks=["amounts"]),
    Case("LG-02", "Ledger", "full", "What is the balance of Apex Office Solutions?", {"get_ledger_balance", "get_party_outstanding_summary"}, checks=["amounts"]),
    Case("LG-03", "Ledger", "full", "Customer statement for Eagle Paradise Pvt. Ltd.", {"get_customer_statement", "get_party_statement"}, checks=["amounts"]),
    # ---------------- Inventory ----------------
    Case("IN-01", "Stock", "full", "Show my closing stock", {"get_stock_summary"}, checks=["amounts"]),
    Case("IN-02", "Stock", "full", "List all stock items", {"get_stock_items", "get_stock_summary"}, checks=["amounts"]),
    Case("IN-03", "Stock", "full", "Show stock movement of SmartMind AI for FY 2025-26", {"get_stock_movement", "get_stock_item_details"}, checks=["amounts"]),
    Case("IN-04", "Stock", "full", "Any negative stock items?", {"get_negative_stock_items"}),
    Case("IN-05", "Stock", "full", "Inventory valuation", {"get_stock_summary"}, checks=["amounts"]),
    # ---------------- Tax ----------------
    Case("TX-01", "GST", "full", "Show GST summary for FY 2025-26", {"get_gst_summary"}, checks=["amounts"]),
    Case("TX-02", "GST", "full", "Show input GST for FY 2025-26", {"get_input_gst"}, checks=["amounts"]),
    Case("TX-03", "GST", "full", "Show output GST for FY 2025-26", {"get_output_gst"}, checks=["amounts"]),
    Case("TX-04", "TDS", "full", "TDS summary for FY 2025-26", {"get_tds_summary"}),
    Case("TX-05", "Tax", "full", "What is my total tax liability for FY 2025-26?", {"get_tax_liability"}, checks=["no_combined_tax"]),
    # ---------------- Follow-ups (same session) ----------------
    Case("FU-01", "Follow-up", "full", "Show the balance of HDFC Bank", {"get_ledger_balance", "get_bank_balance"}, session="fu1", checks=["amounts"]),
    Case("FU-02", "Follow-up", "full", "Show its transactions", {"get_ledger_transactions"}, session="fu1", checks=["amounts"],
         note="Must use HDFC Bank from previous turn"),
    Case("FU-03", "Follow-up", "full", "Show sales for December 2025", {"get_sales_transactions"}, session="fu2", checks=["amounts"]),
    Case("FU-04", "Follow-up", "full", "Now show only cash transactions", {"get_cash_transactions"}, session="fu2", expect_success=None,
         note="Should not silently carry the sales filter"),
    Case("FU-05", "Follow-up", "full", "What about March?", {"get_cash_transactions"}, session="fu2", expect_success=None,
         note="Reuses cash report for March of the active financial year"),
    Case("FU-06", "Follow-up", "full", "Show the profit and loss for FY 2025-26", {"get_profit_loss"}, session="fu3"),
    Case("FU-07", "Follow-up", "full", "Show all items", {"get_profit_loss"}, session="fu3", checks=["amounts"]),
    Case("FU-08", "Follow-up", "full", "Export this report to Excel", {"export_excel"}, session="fu3",
         note="Returns a scoped Excel snapshot download"),
    Case("FU-09", "Follow-up", "full", "Monthly sales for FY 2025-26", {"get_monthly_summary"}, session="fu-monthly"),
    Case("FU-10", "Follow-up", "full", "What about purchases?", {"get_monthly_summary"}, session="fu-monthly"),
    Case("FU-11", "Follow-up", "full", "What about March?", {"get_monthly_summary"}, session="fu-monthly"),
    Case("IN-06", "Stock", "full", "Show stock item details of SmartMind AI for FY 2025-26", {"get_stock_item_details"}, session="fu-stock"),
    Case("IN-07", "Stock", "full", "Show its stock movements", {"get_stock_movement"}, session="fu-stock"),
    Case("IN-08", "Stock", "full", "What about April?", {"get_stock_movement"}, session="fu-stock"),
    Case("IN-09", "Stock", "full", "Show stock movement of Nonexistent Widget for FY 2025-26", {"get_stock_movement"}, expect_success=False),
    # ---------------- Safety / unsupported ----------------
    Case("SF-01", "Read-only", "full", "Delete invoice 5", set(), expect_success=False, expect_text="read-only"),
    Case("SF-02", "Read-only", "full", "Create a new payment voucher for 5000", set(), expect_success=False, expect_text="read-only"),
    Case("SF-03", "Unsupported", "full", "What is the weather in Delhi today?", set(), expect_success=False),
    Case("SF-04", "Hallucination", "full", "What was my revenue in 2015?", {"get_revenue"}, expect_success=None,
         note="Outside books: must not invent"),
    Case("SF-05", "Entity", "full", "What is the balance of Nonexistent Traders Ltd?", {"get_ledger_balance"}, expect_success=False),
    Case("SF-06", "Routing", "full", "What is the balance of Amul Dairy?", {"get_ledger_balance"}, expect_success=False,
         note="'Dairy' in a name must not open the Day Book"),
    # ---------------- RBAC through chat ----------------
    Case("RB-01", "RBAC", "inventory_only", "What are my total receivables?", {"get_receivables"}, expect_success=False,
         expect_text="not authorized", severity="Critical"),
    Case("RB-02", "RBAC", "inventory_only", "Show my closing stock", {"get_stock_summary"}, severity="Critical"),
    Case("RB-03", "RBAC", "financial_only", "Show my closing stock", {"get_stock_summary"}, expect_success=False,
         expect_text="not authorized", severity="Critical"),
    Case("RB-04", "RBAC", "financial_only", "What is my closing bank balance?", {"get_bank_balance"}, expect_success=False,
         expect_text="not authorized", severity="Critical", note="banking permission not granted"),
    Case("RB-05", "RBAC", "financial_only", "Give me the complete Day Book for FY 2025-26", {"get_day_book"}, severity="Critical",
         note="Day Book is financial"),
]


# ------------------------------------------------------------------
# Users
# ------------------------------------------------------------------

ROLE_PERMISSIONS = {
    "full": ("financial", "inventory", "banking", "tax"),
    "inventory_only": ("inventory",),
    "financial_only": ("financial",),
    "other_company": ("financial", "inventory", "banking", "tax"),
    "inactive": ("financial",),
}


def create_users() -> dict[str, dict]:
    from app.security.db import get_connection
    from app.security.permissions import assign_permission_to_user, assign_role_to_user
    from app.security.user_store import create_user, set_user_active_status

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT organization_id FROM users ORDER BY username LIMIT 1")
    org_id = cur.fetchone()[0]
    cur.close()
    conn.close()

    users = {}
    for role, perms in ROLE_PERMISSIONS.items():
        username = f"qa_tmp_{role}_{secrets.token_hex(3)}"
        password = secrets.token_urlsafe(14)
        companies = ["QA Other Company Ltd"] if role == "other_company" else [COMPANY]
        user_id = create_user(username=username, password=password, companies=companies, organization_id=org_id)
        assign_role_to_user(user_id, "user")
        for perm in perms:
            assign_permission_to_user(user_id, perm)
        if role == "inactive":
            set_user_active_status(user_id, False)
        users[role] = {"user_id": user_id, "username": username, "password": password}
    return users


def delete_users(users: dict[str, dict]) -> None:
    from app.security.user_store import delete_user

    for info in users.values():
        try:
            delete_user(info["user_id"])
        except Exception as exc:
            print("cleanup failed", info["username"], exc)


def new_client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver", timeout=180)


async def login(app, info) -> httpx.AsyncClient:
    client = new_client(app)
    response = await client.post("/api/v1/auth/login", json={"username": info["username"], "password": info["password"]})
    client.login_status = response.status_code  # type: ignore[attr-defined]
    csrf = client.cookies.get("csrf_token")
    if csrf:
        client.headers["X-CSRF-Token"] = csrf
    return client


# ------------------------------------------------------------------
# Checks
# ------------------------------------------------------------------

_ANSWER_AMOUNT_RE = re.compile(r"-?₹\s?([\d,]+(?:\.\d+)?)")


def answer_amounts(answer: str) -> list[Decimal]:
    out = []
    for match in _ANSWER_AMOUNT_RE.findall(answer or ""):
        value = _decimal(match)
        if value is not None:
            out.append(value)
    return out


def run_checks(case: Case, body: dict) -> tuple[str, list[str], Any, Any]:
    answer = body.get("answer") or ""
    data = body.get("data") or {}
    failures = []
    actual_count = expected_count = ""

    if "amounts" in case.checks or "native" in case.checks:
        derived = answer.startswith("Derived figure")
        # Mixed native/derived summaries label derived lines individually.
        # Compare native lines with the raw corpus, retaining checks on all
        # unlabelled figures even when another line is explicitly derived.
        native_lines = "\n".join(line for line in answer.splitlines() if "derived" not in line.lower())
        unknown = [str(a) for a in answer_amounts(native_lines) if a not in REF["corpus"] and a != 0]
        if unknown and not derived:
            failures.append(f"amounts not found in Tally output: {unknown[:6]}")

    if case.expect_text and case.expect_text.lower() not in answer.lower():
        failures.append(f"expected text '{case.expect_text}' missing")

    if "derived_label" in case.checks and body.get("success"):
        if not (answer.startswith("Derived figure") or "derived" in answer.lower()):
            failures.append("derived figure not labelled")

    if "no_combined_tax" in case.checks and "combined tax" in answer.lower():
        failures.append("invented combined tax figure shown")

    if case.id in {"SP-13", "FU-09"}:
        periods = data.get("periods") or []
        total = sum(row.get("value") or 0 for row in periods)
        if len(periods) != 12 or total != 7410000:
            failures.append(f"monthly sales {total} across {len(periods)} months does not match native FY Sales Accounts 7410000")
    if case.id == "FU-10" and data.get("metric") != "purchases":
        failures.append("monthly metric follow-up lost purchases")
    if case.id == "FU-11" and (data.get("from_date"), data.get("to_date")) != ("2026-03-01", "2026-03-31"):
        failures.append("March follow-up selected the wrong financial year")
    if case.id == "IN-07" and (data.get("item_name"), data.get("from_date")) != ("SmartMind AI", "2025-04-01"):
        failures.append("stock pronoun lost item/period")
    if case.id == "FU-08" and not body.get("downloads"):
        failures.append("chat Excel export has no download")

    if case.expect_count is not None:
        expected_count = case.expect_count()
        rows = data.get("rows") if isinstance(data, dict) else None
        actual_count = data.get(case.count_key) if isinstance(data, dict) else None
        if actual_count is None and isinstance(rows, list):
            actual_count = len(rows)
        if actual_count is None:
            actual_count = 0 if body.get("success") is False else "n/a"
        if actual_count != expected_count:
            failures.append(f"count {actual_count} != Tally {expected_count}")

    if "complete" in case.checks and isinstance(data, dict):
        rows = data.get("rows") or []
        if expected_count != "" and len(rows) != expected_count:
            failures.append(f"data rows {len(rows)} truncated vs Tally {expected_count}")
        shown = len(re.findall(r"^\s*[-•]|\|", answer, flags=re.M))
        if rows and "more" not in answer.lower() and shown < len(rows):
            failures.append("answer hides rows without saying how many are omitted")

    accuracy = "N/A" if not ({"amounts", "native", "count"} & set(case.checks)) and case.expect_count is None else (
        "MATCH" if not failures else "MISMATCH")
    return accuracy, failures, expected_count, actual_count


# ------------------------------------------------------------------
# Runner
# ------------------------------------------------------------------

async def run_async(out_dir: Path) -> None:
    from app.api import chat as chat_api
    from app.chatbot import gemini_client
    from app.main import app

    tracemalloc.start()
    results = []
    perf = {}

    users = create_users()
    try:
        # One event loop for everything: the app's startup (MySQL pool,
        # Redis, shared Tally HTTP client) and every request.
        async with app.router.lifespan_context(app):
            await fetch_reference()
            redis_before = _redis_memory()

            clients = {role: await login(app, info) for role, info in users.items()}
            # Functional cases: lift the per-user chat rate limit (tested separately).
            chat_api.chat_rate_limiter.limit = 100000

            sessions: dict[str, str] = {}
            for case in CASES:
                client = clients[case.role]
                key = case.session or case.id
                session_id = sessions.setdefault(key, f"qa-{key}-{secrets.token_hex(3)}")
                started = time.perf_counter()
                response = await client.post("/api/v1/chat", json={"message": case.query, "company_name": COMPANY, "session_id": session_id})
                latency = time.perf_counter() - started
                body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}

                failures = []
                if response.status_code != 200:
                    failures.append(f"HTTP {response.status_code}: {body.get('detail')}")
                intent = body.get("intent")
                if case.expect_tools:
                    if intent not in case.expect_tools:
                        failures.append(f"intent {intent} not in {sorted(case.expect_tools)}")
                elif case.expect_tools is not None:  # empty set: no tool may run
                    if intent not in {"write_operation", "unsupported"}:
                        failures.append(f"unexpected intent {intent}")
                if case.expect_success is not None and body.get("success") is not case.expect_success:
                    failures.append(f"success={body.get('success')} expected {case.expect_success}")
                if intent in {"model_error", "model_timeout", "model_rate_limit", "model_configuration_error", "model_authentication_error"}:
                    failures.append(f"AI provider failure: {intent}")

                if case.id == "FU-08" and body.get("downloads"):
                    exported = await client.get("/api/v1" + body["downloads"][0]["url"])
                    ok, reason, _ = _xlsx_contains(exported, ["7410000", "519053.47"])
                    if not ok:
                        failures.append("chat Excel values: " + reason)

                accuracy, check_failures, exp_count, act_count = (
                    run_checks(case, body) if response.status_code == 200 else ("N/A", [], "", "")
                )
                failures += check_failures

                results.append({
                    "test_id": case.id, "section": case.section, "role": case.role, "query": case.query,
                    "expected_behaviour": _expected_text(case), "actual_intent": intent,
                    "actual_success": body.get("success"), "actual_response": (body.get("answer") or "")[:600],
                    "expected_count": exp_count, "actual_count": act_count,
                    "financial_accuracy": accuracy,
                    "status": "PASS" if not failures else "FAIL",
                    "failure_reason": "; ".join(failures), "latency_s": round(latency, 2),
                    "severity": case.severity, "note": case.note,
                })
                print(f"{case.id:7} {results[-1]['status']:5} {latency:5.1f}s intent={intent} {results[-1]['failure_reason'][:120]}", flush=True)

            results += await api_cases(app, clients, users)
            results += await reliability_cases(app, clients, users)
            perf = await performance_cases(clients["full"])
            perf["redis_memory_before"] = redis_before
            perf["redis_memory_after"] = _redis_memory()
            for client in clients.values():
                await client.aclose()
    finally:
        delete_users(users)

    current, peak = tracemalloc.get_traced_memory()
    perf["python_heap_peak_mb"] = round(peak / 1_048_576, 1)
    perf["llm_usage"] = dict(gemini_client.LLM_USAGE)
    perf["reference_errors"] = REF.get("reference_errors", {})
    perf["reference_voucher_count_fy"] = REF.get("voucher_count_fy")
    perf["reference_vouchers_by_type"] = REF.get("vouchers_by_type")
    write_outputs(out_dir, results, perf)


def run(out_dir: Path) -> None:
    asyncio.run(run_async(out_dir))


def _expected_text(case: Case) -> str:
    parts = []
    if case.expect_tools:
        parts.append("tool in " + "/".join(sorted(case.expect_tools)))
    if case.expect_success is True:
        parts.append("answers from Tally")
    elif case.expect_success is False:
        parts.append("refuses safely")
    if case.expect_text:
        parts.append(f"shows '{case.expect_text}'")
    if case.note:
        parts.append(case.note)
    return "; ".join(parts) or "record behaviour"


def _redis_memory() -> str:
    try:
        import redis

        info = redis.Redis(host="127.0.0.1", port=6379).info("memory")
        return f"{info.get('used_memory_human')} (maxmemory {info.get('maxmemory_human')}, policy {info.get('maxmemory_policy')})"
    except Exception as exc:
        return f"unavailable: {exc}"


# ------------------------------------------------------------------
# Direct API, export and RBAC cases
# ------------------------------------------------------------------

def _row(test_id, section, role, query, expected, ok, reason="", response="", accuracy="N/A", severity="Critical", exp="", act=""):
    return {
        "test_id": test_id, "section": section, "role": role, "query": query,
        "expected_behaviour": expected, "actual_intent": "", "actual_success": ok,
        "actual_response": str(response)[:600], "expected_count": exp, "actual_count": act,
        "financial_accuracy": accuracy, "status": "PASS" if ok else "FAIL",
        "failure_reason": reason, "latency_s": "", "severity": severity, "note": "",
    }


async def api_cases(app, clients, users) -> list[dict]:
    rows = []
    params = {"company_name": COMPANY}

    async def get(role, path, extra=None):
        return await clients[role].get(path, params={**params, **(extra or {})})

    # Login outcomes
    rows.append(_row("AU-01", "Auth", "inactive", "login as deactivated user", "401 refused",
                     clients["inactive"].login_status == 401, f"got {clients['inactive'].login_status}"))
    for role in ("full", "inventory_only", "financial_only", "other_company"):
        rows.append(_row(f"AU-02-{role}", "Auth", role, "login", "200", clients[role].login_status == 200,
                         f"got {clients[role].login_status}", severity="High"))

    # Direct API RBAC
    matrix = [
        ("AP-01", "inventory_only", "/api/v1/reports/profit-loss", 403),
        ("AP-02", "inventory_only", "/api/v1/reports/receivables", 403),
        ("AP-03", "inventory_only", "/api/v1/dashboard/summary", 403),
        ("AP-04", "inventory_only", "/api/v1/reports/profit-loss/export/xlsx", 403),
        ("AP-05", "financial_only", "/api/v1/reports/stock-summary", 403),
        ("AP-06", "inventory_only", "/api/v1/reports/stock-summary", 200),
        ("AP-07", "other_company", "/api/v1/reports/profit-loss", 403),
        ("AP-08", "other_company", "/api/v1/reports/stock-summary", 403),
        ("AP-09", "full", "/api/v1/tally/debug/receivables", 404),
        ("AP-10", "full", "/api/v1/reports/profit-loss", 200),
    ]
    for test_id, role, path, expected in matrix:
        response = await get(role, path, {"from_date": FY_FROM.isoformat(), "to_date": FY_TO.isoformat()} if "profit" in path else None)
        rows.append(_row(test_id, "RBAC API", role, f"GET {path}", f"HTTP {expected}",
                         response.status_code == expected, f"got {response.status_code}", response.text[:200]))

    # Chat for a company the user is not assigned
    response = await clients["other_company"].post("/api/v1/chat", json={"message": "What are my total receivables?", "company_name": COMPANY})
    rows.append(_row("RB-06", "RBAC", "other_company", "chat about unassigned company", "HTTP 403, no data",
                     response.status_code == 403 and "36,30,000" not in response.text, f"got {response.status_code}", response.text[:200]))

    # Session expiry / tampered token
    import jwt
    from app.security.config import get_auth_settings

    settings = get_auth_settings()
    expired = jwt.encode({"sub": users["full"]["user_id"], "companies": [COMPANY], "org": "x",
                          "iat": datetime.now(timezone.utc) - timedelta(hours=3),
                          "exp": datetime.now(timezone.utc) - timedelta(hours=2)}, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    async with new_client(app) as anonymous:
        response = await anonymous.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired}"})
    rows.append(_row("AU-03", "Auth", "full", "expired token", "401", response.status_code == 401, f"got {response.status_code}"))
    forged = jwt.encode({"sub": users["full"]["user_id"], "companies": ["*"], "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
                        "not-the-secret", algorithm="HS256")
    async with new_client(app) as anonymous:
        response = await anonymous.get("/api/v1/reports/profit-loss", params=params, headers={"Authorization": f"Bearer {forged}"})
    rows.append(_row("AU-04", "Auth", "attacker", "forged token with wildcard company", "401", response.status_code == 401, f"got {response.status_code}"))

    # Exports vs Tally
    response = await get("full", "/api/v1/reports/receivables/export/xlsx")
    ok, reason, act = _xlsx_contains(response, [REF.get("rx_raw_total")])
    rows.append(_row("EX-01", "Export", "full", "Receivables Excel export", "xlsx with Tally total", ok, reason, accuracy="MATCH" if ok else "MISMATCH", severity="High", act=act))
    response = await get("full", "/api/v1/reports/profit-loss/export/xlsx", {"from_date": FY_FROM.isoformat(), "to_date": FY_TO.isoformat()})
    ok, reason, act = _xlsx_contains(response, ["74,10,000.00"])
    rows.append(_row("EX-02", "Export", "full", "P&L Excel export FY 2025-26", "xlsx contains Sales Accounts 74,10,000", ok, reason, accuracy="MATCH" if ok else "MISMATCH", severity="High", act=act))
    response = await get("full", "/api/v1/reports/profit-loss/export/pdf", {"from_date": FY_FROM.isoformat(), "to_date": FY_TO.isoformat()})
    ok = response.status_code == 200 and response.content[:4] == b"%PDF"
    rows.append(_row("EX-03", "Export", "full", "P&L PDF export", "valid PDF", ok, f"HTTP {response.status_code}", severity="Medium"))
    import io
    from pypdf import PdfReader

    pdf_text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(response.content)).pages) if ok else ""
    pdf_amounts = {value for raw in _NUMBER_RE.findall(pdf_text) if (value := _decimal(raw)) is not None}
    expected_pdf_amounts = {Decimal("7410000.00"), Decimal("519053.47")}
    pdf_matches = expected_pdf_amounts <= pdf_amounts and "Sales Accounts" in pdf_text
    rows.append(_row("EX-04", "Export", "full", "P&L PDF figures vs Tally", "PDF text matches Tally", pdf_matches,
                     "" if pdf_matches else "PDF is missing the recorded sales or net-loss figure", severity="Medium"))
    return rows


def _xlsx_contains(response, raw_values) -> tuple[bool, str, str]:
    import io
    from openpyxl import load_workbook

    if response.status_code != 200:
        return False, f"HTTP {response.status_code}", ""
    workbook = load_workbook(io.BytesIO(response.content), data_only=True)
    numbers = set()
    for sheet in workbook.worksheets:
        for row in sheet.iter_rows(values_only=True):
            for cell in row:
                if isinstance(cell, (int, float)):
                    numbers.add(Decimal(str(cell)).quantize(Decimal("0.01")))
                elif isinstance(cell, str):
                    value = _decimal(cell)
                    if value is not None:
                        numbers.add(value)
    missing = [v for v in raw_values if v and _decimal(v) not in numbers]
    return (not missing), (f"missing {missing}" if missing else ""), f"{len(numbers)} numeric cells"


# ------------------------------------------------------------------
# Reliability
# ------------------------------------------------------------------

async def reliability_cases(app, clients, users) -> list[dict]:
    from unittest.mock import patch

    import httpx

    from app.api import chat as chat_api
    from app.chatbot import service

    rows = []
    client = clients["full"]

    # Tally disconnected: previously cached answer is served as stale, not invented.
    question = {"message": "What are my total receivables?", "company_name": COMPANY, "session_id": "rel-1"}
    await client.post("/api/v1/chat", json=question)  # warm cache
    from app.tally.client import TallyClient

    async def down(*args, **kwargs):
        raise httpx.ConnectError("simulated Tally outage")

    with patch.object(TallyClient, "send_xml", down):
        response = await client.post("/api/v1/chat", json={**question, "force_refresh": False})
    body = response.json()
    ok = response.status_code == 200 and ("36,30,000" in (body.get("answer") or "")) and body.get("source") in ("cache", "stale_cache")
    rows.append(_row("RL-01", "Reliability", "full", "Tally down, cached receivables", "served from cache with source flag", ok,
                     f"source={body.get('source')} stale={body.get('is_stale')}", body.get("answer"), severity="High"))

    with patch.object(TallyClient, "send_xml", down):
        response = await client.post("/api/v1/chat", json={"message": "Show the day book for 02-08-2025", "company_name": COMPANY, "session_id": "rel-2"})
    body = response.json()
    ok = response.status_code == 200 and body.get("success") is False and "₹" not in (body.get("answer") or "")
    rows.append(_row("RL-02", "Reliability", "full", "Tally down, nothing cached", "clear failure, no figures", ok,
                     f"success={body.get('success')}", body.get("answer"), severity="High"))

    # AI provider failure: graceful message
    async def ai_down(message):
        return {"tool_name": None, "arguments": {}, "error": "model_unavailable"}

    with patch.object(service, "select_tool", ai_down):
        response = await client.post("/api/v1/chat", json={"message": "zz unusual question needing the model qq", "company_name": COMPANY})
    body = response.json()
    ok = response.status_code == 200 and body.get("success") is False and "temporarily unavailable" in (body.get("answer") or "")
    rows.append(_row("RL-03", "Reliability", "full", "AI provider down", "friendly unavailable message", ok, "", body.get("answer"), severity="Medium"))

    # Redis unavailable: fail open to Tally
    from app.cache import client as cache_client

    with patch.object(cache_client, "get_redis_client", lambda: _none()), \
         patch("app.cache.manager.get_redis_client", lambda: _none()):
        response = await client.post("/api/v1/chat", json={"message": "What is my closing bank balance?", "company_name": COMPANY, "session_id": "rel-4"})
    body = response.json()
    ok = response.status_code == 200 and "32,85,000" in (body.get("answer") or "")
    rows.append(_row("RL-04", "Reliability", "full", "Redis unavailable", "answers live from Tally", ok, f"source={body.get('source')}", body.get("answer"), severity="High"))

    # Rate limiting
    chat_api.chat_rate_limiter.limit = 10
    chat_api.chat_rate_limiter._requests.clear()
    codes = []
    for _ in range(11):
        reply = await clients["inventory_only"].post("/api/v1/chat", json={"message": "Show my closing stock", "company_name": COMPANY})
        codes.append(reply.status_code)
    chat_api.chat_rate_limiter.limit = 100000
    rows.append(_row("RL-05", "Reliability", "inventory_only", "11 chat requests in a minute", "11th gets 429",
                     codes[-1] == 429 and all(code == 200 for code in codes[:10]), f"codes={codes}", severity="Medium"))

    # Deactivate a logged-in user: next request refused immediately
    from app.security.user_store import set_user_active_status

    set_user_active_status(users["financial_only"]["user_id"], False)
    response = await clients["financial_only"].get("/api/v1/reports/profit-loss", params={"company_name": COMPANY})
    rows.append(_row("AU-05", "Auth", "financial_only", "request after deactivation (token still valid)", "401 immediately",
                     response.status_code == 401, f"got {response.status_code}"))
    return rows


async def _none():
    return None


async def performance_cases(client) -> dict:
    perf = {}
    question = {"message": "What is my closing bank balance?", "company_name": COMPANY}
    latencies = []
    for _ in range(10):
        started = time.perf_counter()
        await client.post("/api/v1/chat", json=question)
        latencies.append(time.perf_counter() - started)
    perf["cached_chat_latency_p50_s"] = round(statistics.median(latencies), 3)
    perf["cached_chat_latency_max_s"] = round(max(latencies), 3)

    started = time.perf_counter()
    response = await client.post("/api/v1/chat", json={**question, "force_refresh": True})
    perf["uncached_bank_balance_latency_s"] = round(time.perf_counter() - started, 2)
    perf["uncached_status"] = response.status_code

    from app.security import db

    pool = db._get_pool()
    perf["mysql_pool_size"] = getattr(pool, "pool_size", None)
    return perf


# ------------------------------------------------------------------
# Output
# ------------------------------------------------------------------

def write_outputs(out_dir: Path, results: list[dict], perf: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "results.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)
    (out_dir / "results.json").write_text(json.dumps({"results": results, "performance": perf}, indent=2, default=str), encoding="utf-8")

    total = len(results)
    counts = {s: sum(1 for r in results if r["status"] == s) for s in ("PASS", "FAIL", "BLOCKED")}
    lines = [
        "# Chatbot acceptance run",
        f"Run at {datetime.now().isoformat(timespec='seconds')} against live Tally ({COMPANY}).",
        "",
        f"Total {total} | PASS {counts['PASS']} | FAIL {counts['FAIL']} | BLOCKED {counts['BLOCKED']} | "
        f"pass rate {counts['PASS'] / total * 100:.1f}%",
        "",
        "| ID | Section | Role | Query | Status | Accuracy | Exp/Act count | Reason |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['test_id']} | {r['section']} | {r['role']} | {r['query'][:60]} | {r['status']} | "
            f"{r['financial_accuracy']} | {r['expected_count']}/{r['actual_count']} | {r['failure_reason'][:140]} |"
        )
    lines += ["", "## Performance", "```", json.dumps(perf, indent=2, default=str), "```"]
    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:5]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="acceptance_out")
    run(Path(parser.parse_args().out))
