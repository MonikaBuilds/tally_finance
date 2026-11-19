"""
Native-figure tests on RECORDED TallyPrime responses (tests/fixtures/tally_abc,
test company "ABC Pvt Ltd"). Expected values are the strings Tally itself
printed in those responses - never values computed in Python.
"""

from datetime import date
from pathlib import Path

import pytest

from app.chatbot import tools
from app.chatbot.formatter import format_indian_currency, format_tool_response
from app.tally import native_reports
from app.tally.dashboard import (
    parse_balances,
    parse_native_table,
    parse_outstanding_table,
)

FIXTURES = Path(__file__).parent / "fixtures" / "tally_abc"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# ------------------------------------------------------------------
# Bills Receivable / Payable: the total is Tally's footer
# ------------------------------------------------------------------

def test_receivables_total_is_tallys_footer_text():
    report = parse_outstanding_table(fixture("bills_receivable.html"))

    assert report["raw_total"] == "36,30,000.00"  # Tally's own footer
    assert report["total"] == 3630000.0
    assert len(report["bills"]) == 2
    assert {b["party"] for b in report["bills"]} == {
        "Apex Office Solutions",
        "Eagle Paradise Pvt. Ltd.",
    }


def test_payables_total_is_tallys_footer_text():
    report = parse_outstanding_table(fixture("bills_payable.html"))

    assert report["raw_total"] == "4,72,000.00"
    assert len(report["bills"]) == 1


@pytest.mark.asyncio
async def test_receivables_tool_uses_footer_and_keeps_every_bill(monkeypatch):
    async def send(_xml, *args, **kwargs):
        return fixture("bills_receivable.html")

    monkeypatch.setattr(native_reports._client, "send_xml", send)

    result = await tools.get_receivables_tool(company_name="ABC Pvt Ltd")
    data = result["data"]

    assert data["total_receivable"] == 3630000.0
    assert data["raw_total"] == "36,30,000.00"
    assert data["count"] == 2
    assert data["total_source"].startswith("Tally report footer")

    answer = format_tool_response("get_receivables", result)
    assert "₹36,30,000" in answer


def test_advance_bill_keeps_negative_sign():
    """An advance (Tally shows (-)) must not become money owed to you."""
    native = {
        "bills": [
            {"party": "A", "reference": "1", "amount": 50000.0, "raw": "50,000.00"},
            {"party": "B", "reference": "ADV", "amount": -20000.0, "raw": "(-)20,000.00"},
        ],
        "total": 30000.0,  # TEST FIXTURE footer
        "raw_total": "30,000.00",
    }

    shaped = tools._bills_from_native(native, "receivable")

    amounts = {b["bill_reference"]: b["outstanding_amount"] for b in shaped["bills"]}
    assert amounts["ADV"] == -20000.0
    assert shaped["total_receivable"] == 30000.0  # the footer, not a re-sum


def test_missing_footer_is_reported_not_invented():
    shaped = tools._bills_from_native(
        {"bills": [{"party": "A", "reference": "1", "amount": 10.0}], "total": None},
        "payable",
    )
    assert shaped["total_payable"] is None

    answer = format_tool_response(
        "get_payables", {"success": True, "source": "tally", "data": shaped}
    )
    assert "did not return a total" in answer


# ------------------------------------------------------------------
# Group / ledger balances
# ------------------------------------------------------------------

def test_group_balances_from_recorded_collection():
    groups = parse_balances(fixture("groups.xml"), "Group")
    by_name = {g["name"]: g for g in groups}

    assert by_name["Cash-in-Hand"]["raw"] == "-10000.00"
    assert by_name["Bank Accounts"]["raw"] == "-3285000.00"
    assert native_reports.dr_cr(by_name["Bank Accounts"]["amount"]) == (3285000.0, "Dr")


def test_ledgers_under_groups_on_recorded_data():
    groups = parse_balances(fixture("groups.xml"), "Group")
    ledgers = parse_balances(fixture("ledgers.xml"), "Ledger")

    cash = [l["name"] for l, _ in native_reports.ledgers_under_groups(groups, ledgers, {"Cash-in-Hand"})]
    bank = [l["name"] for l, _ in native_reports.ledgers_under_groups(groups, ledgers, {"Bank Accounts", "Bank OD A/c"})]

    assert cash == ["Cash"]
    assert bank == ["HDFC Bank"]


# ------------------------------------------------------------------
# Profit & Loss
# ------------------------------------------------------------------

def _pl_sender(xml_name: str, html_name: str):
    async def send(xml, *args, **kwargs):
        return fixture(html_name if "$$SysName:HTML" in xml else xml_name)

    return send


@pytest.mark.asyncio
async def test_revenue_is_sales_accounts_not_sales_plus_closing_stock(monkeypatch):
    monkeypatch.setattr(
        native_reports._client, "send_xml",
        _pl_sender("pl_fy2526.xml", "pl_fy2526.html"),
    )

    result = await tools.get_revenue_tool(
        company_name="ABC Pvt Ltd",
        from_date=date(2025, 4, 1),
        to_date=date(2026, 3, 31),
    )

    # Tally prints "Sales Accounts 74,10,000.00". The old code reported
    # 1,29,55,946.53 (Sales + Closing Stock 55,45,946.53).
    assert result["data"]["revenue"] == 7410000.0


@pytest.mark.asyncio
async def test_net_profit_is_tallys_nett_loss_row_with_paise(monkeypatch):
    monkeypatch.setattr(
        native_reports._client, "send_xml",
        _pl_sender("pl_fy2526.xml", "pl_fy2526.html"),
    )

    result = await tools.get_net_profit_tool(
        company_name="ABC Pvt Ltd",
        from_date=date(2025, 4, 1),
        to_date=date(2026, 3, 31),
    )

    assert result["data"]["result_type"] == "loss"
    assert result["data"]["amount"] == 519053.47  # Tally: Nett Loss 5,19,053.47

    answer = format_tool_response("get_net_profit", result)
    assert "₹5,19,053.47" in answer  # paise are not dropped


@pytest.mark.asyncio
async def test_period_tally_did_not_use_is_refused(monkeypatch):
    """Tally silently substituted a period; no figure may be shown."""
    monkeypatch.setattr(
        native_reports._client, "send_xml",
        _pl_sender("pl_fy2627_partial.xml", "pl_fy2627_partial.html"),
    )

    result = await tools.get_revenue_tool(
        company_name="ABC Pvt Ltd",
        from_date=date(2026, 4, 1),
        to_date=date(2026, 11, 19),
    )

    assert result["success"] is False
    assert result["data"] is None
    assert "No figures are shown" in result["message"]


def test_recorded_html_names_the_period_tally_used():
    native = parse_native_table(fixture("pl_fy2526.html"))
    assert (native["from_date"], native["to_date"]) == ("2025-04-01", "2026-03-31")

    substituted = parse_native_table(fixture("pl_fy2627_partial.html"))
    assert substituted["to_date"] != "2026-11-19"


@pytest.mark.asyncio
async def test_expenses_are_labelled_derived_with_native_lines(monkeypatch):
    monkeypatch.setattr(
        native_reports._client, "send_xml",
        _pl_sender("pl_fy2526.xml", "pl_fy2526.html"),
    )

    result = await tools.get_expenses_tool(
        company_name="ABC Pvt Ltd",
        from_date=date(2025, 4, 1),
        to_date=date(2026, 3, 31),
    )

    data = result["data"]
    assert data["expenses_source"].startswith("Derived: sum of Tally P&L lines")
    assert {line["name"] for line in data["expense_lines"]} >= {"Direct Expenses", "Indirect Expenses"}


# ------------------------------------------------------------------
# Display never alters a Tally amount
# ------------------------------------------------------------------

@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (519053.47, "₹5,19,053.47"),
        (1170000, "₹11,70,000"),
        (-2000000, "-₹20,00,000"),
        (0.5, "₹0.50"),
        (None, "₹0"),
        (12345678.9, "₹1,23,45,678.90"),
    ],
)
def test_currency_display_is_exact(value, expected):
    assert format_indian_currency(value) == expected
