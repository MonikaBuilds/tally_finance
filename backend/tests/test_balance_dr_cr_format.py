"""Ledger-report balances are shown as "₹X Dr/Cr", never with a minus sign."""

from app.chatbot.formatter import format_dr_cr_balance, format_tool_response


def test_positive_balance_is_debit():
    assert format_dr_cr_balance(450000) == "₹4,50,000 Dr"


def test_negative_balance_is_credit():
    assert format_dr_cr_balance(-616200) == "₹6,16,200 Cr"


def test_zero_and_missing_balance_have_no_side():
    assert format_dr_cr_balance(0) == "₹0"
    assert format_dr_cr_balance(None) == "₹0"
    assert format_dr_cr_balance(-0.001) == "₹0"


def test_paise_are_kept():
    assert format_dr_cr_balance(-1234.5) == "₹1,234.50 Cr"


def test_ledger_transactions_show_closing_side_instead_of_minus():
    output = format_tool_response("get_ledger_transactions", {
        "success": True,
        "source": "tally",
        "data": {
            "ledger_name": "Eagle Paradise Pvt. Ltd.",
            "opening_balance": 0.0,
            # Sales ₹3,00,000 Dr, Receipt ₹9,16,200 Cr -> ₹6,16,200 Cr
            "closing_balance": -616200.0,
            "count": 0,
            "transactions": [],
        },
    })

    assert "Opening Balance: ₹0" in output
    assert "Closing Balance: ₹6,16,200 Cr" in output
    assert "-₹" not in output


def test_bank_transactions_show_debit_closing_balance():
    output = format_tool_response("get_bank_transactions", {
        "success": True,
        "source": "tally",
        "data": {
            "ledger_name": "HDFC Bank",
            "opening_balance": 0.0,
            "closing_balance": 3285000.0,
            "total_debit": 4500000.0,
            "total_credit": 1215000.0,
            "transactions": [{
                "date": "2025-04-01", "voucher_type": "Receipt",
                "voucher_number": "4", "particulars": "Bajaj Finance",
                "debit": 2000000.0, "credit": 0.0,
            }],
        },
    })

    assert "Closing balance: ₹32,85,000 Dr" in output
    assert "Opening balance: ₹0" in output


# ------------------------------------------------------------------
# Sign conventions at the source
# ------------------------------------------------------------------

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.chatbot import tools
from app.tally import service


@pytest.mark.asyncio
async def test_ledger_report_flips_master_opening_to_report_convention(monkeypatch):
    """Tally's master says -50,000 (= Dr); the report must start at +50,000 (Dr)."""
    monkeypatch.setattr(service.client, "send_xml", AsyncMock(return_value="<ENVELOPE/>"))
    monkeypatch.setattr(service, "parse_ledger_list", MagicMock(return_value={
        "ledgers": [{"name": "HDFC Bank", "opening_balance": -50000.0, "closing_balance": -90000.0}],
    }))
    parse_report = MagicMock(return_value={"entries": [{"debit": 40000.0, "credit": 0.0}]})
    monkeypatch.setattr(service, "parse_ledger_report", parse_report)

    await service.fetch_ledger_report("HDFC Bank")

    assert parse_report.call_args.kwargs["opening_balance"] == 50000.0


@pytest.mark.asyncio
async def test_zero_master_opening_stays_plain_zero(monkeypatch):
    monkeypatch.setattr(service.client, "send_xml", AsyncMock(return_value="<ENVELOPE/>"))
    monkeypatch.setattr(service, "parse_ledger_list", MagicMock(return_value={
        "ledgers": [{"name": "Cash", "opening_balance": 0.0}],
    }))
    parse_report = MagicMock(return_value={"entries": [{"debit": 1.0}]})
    monkeypatch.setattr(service, "parse_ledger_report", parse_report)

    await service.fetch_ledger_report("Cash")

    opening = parse_report.call_args.kwargs["opening_balance"]
    assert opening == 0 and str(opening) == "0.0"


@pytest.mark.asyncio
async def test_ledger_balance_without_dates_reads_master_as_dr_cr(monkeypatch):
    monkeypatch.setattr(tools, "fetch_ledger_list", AsyncMock(return_value=[
        {"name": "Sales A/c", "opening_balance": 0.0, "closing_balance": 7410000.0},
        {"name": "HDFC Bank", "opening_balance": -50000.0, "closing_balance": -450000.0},
    ]))

    sales = await tools.get_ledger_balance_tool("Sales A/c")
    hdfc = await tools.get_ledger_balance_tool("HDFC Bank", balance_type="opening")

    assert "is ₹74,10,000 Cr." in format_tool_response("get_ledger_balance", sales)
    assert "is ₹50,000 Dr." in format_tool_response("get_ledger_balance", hdfc)


@pytest.mark.asyncio
async def test_ledger_balance_for_a_period_uses_report_sign_unchanged(monkeypatch):
    from datetime import date

    monkeypatch.setattr(tools, "fetch_ledger_list", AsyncMock(return_value=[{"name": "HDFC Bank"}]))
    monkeypatch.setattr(tools, "fetch_ledger_report", AsyncMock(return_value={
        "opening_balance": 50000.0, "closing_balance": -10000.0,
    }))

    result = await tools.get_ledger_balance_tool(
        "HDFC Bank", None, date(2025, 4, 1), date(2026, 3, 31), "closing",
    )

    assert result["data"]["closing_balance"] == -10000.0
    assert "is ₹10,000 Cr." in format_tool_response("get_ledger_balance", result)
