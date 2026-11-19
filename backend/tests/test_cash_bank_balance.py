"""
Cash and bank balance tools.

TEST FIXTURES ONLY (not Tally data). Balances use Tally's export sign
convention: a Dr balance is negative, a Cr balance positive. Totals must be
Tally's own group closing balance, never a Python sum of ledgers.
"""

import pytest

from app.chatbot import tools
from app.chatbot.formatter import format_tool_response


GROUPS = [
    {"name": "Current Assets", "reserved_name": "Current Assets", "parent": "", "amount": -900000.0, "raw": "-900000.00"},
    {"name": "Cash-in-Hand", "reserved_name": "Cash-in-Hand", "parent": "Current Assets", "amount": -140000.0, "raw": "-140000.00"},
    {"name": "Bank Accounts", "reserved_name": "Bank Accounts", "parent": "Current Assets", "amount": -400000.0, "raw": "-400000.00"},
    # A user-created sub-group under Bank Accounts.
    {"name": "Nationalised Banks", "reserved_name": None, "parent": "Bank Accounts", "amount": -150000.0, "raw": "-150000.00"},
    {"name": "Bank OD A/c", "reserved_name": "Bank OD A/c", "parent": "Loans (Liability)", "amount": 50000.0, "raw": "50000.00"},
    {"name": "Sundry Debtors", "reserved_name": "Sundry Debtors", "parent": "Current Assets", "amount": -360000.0, "raw": "-360000.00"},
]

LEDGERS = [
    {"name": "Cash", "parent": "Cash-in-Hand", "amount": -150000.0, "raw": "-150000.00"},
    {"name": "Petty Cash", "parent": "Cash-in-Hand", "amount": 10000.0, "raw": "10000.00"},
    {"name": "HDFC Bank", "parent": "Bank Accounts", "amount": -250000.0, "raw": "-250000.00"},
    {"name": "SBI Current", "parent": "Nationalised Banks", "amount": -150000.0, "raw": "-150000.00"},
    {"name": "ICICI OD", "parent": "Bank OD A/c", "amount": 50000.0, "raw": "50000.00"},
    {"name": "Customer A", "parent": "Sundry Debtors", "amount": -360000.0, "raw": "-360000.00"},
]


@pytest.fixture
def native_balances(monkeypatch):
    calls = []

    async def fake(kind, company_name, as_of=None):
        calls.append((kind, company_name))
        return GROUPS if kind == "Group" else LEDGERS

    monkeypatch.setattr(tools, "fetch_native_balances", fake)
    return calls


@pytest.mark.asyncio
async def test_cash_total_is_tallys_group_balance_not_a_sum(native_balances):
    result = await tools.get_cash_balance_tool(company_name="Test Co")

    data = result["data"]
    assert result["success"] is True
    # Tally's Cash-in-Hand group balance (Dr 1,40,000), not abs() of each ledger.
    assert data["total_balance"] == 140000.0
    assert data["balance_type"] == "Dr"
    assert data["total_source"] == "Tally group closing balance: Cash-in-Hand"
    assert {l["name"] for l in data["ledgers"]} == {"Cash", "Petty Cash"}


@pytest.mark.asyncio
async def test_cash_ledger_with_credit_balance_keeps_its_side(native_balances):
    result = await tools.get_cash_balance_tool(
        ledger_name="Petty Cash", company_name="Test Co"
    )

    data = result["data"]
    # A Cr cash balance is shown as Cr (negative Dr-positive value),
    # not silently turned into a positive amount.
    assert data["closing_balance"] == -10000.0
    assert data["balance_type"] == "Cr"


@pytest.mark.asyncio
async def test_bank_includes_ledgers_in_sub_groups(native_balances):
    result = await tools.get_bank_balance_tool(company_name="Test Co")

    names = {l["name"] for l in result["data"]["ledgers"]}
    assert "SBI Current" in names  # under Bank Accounts > Nationalised Banks
    assert "HDFC Bank" in names
    assert "ICICI OD" in names
    assert "Cash" not in names
    assert "Customer A" not in names


@pytest.mark.asyncio
async def test_bank_accounts_and_od_are_not_added_together(native_balances):
    result = await tools.get_bank_balance_tool(company_name="Test Co")

    data = result["data"]
    totals = {g["group"]: g for g in data["group_totals"]}
    assert totals["Bank Accounts"]["closing_balance"] == 400000.0
    assert totals["Bank Accounts"]["balance_type"] == "Dr"
    assert totals["Bank OD A/c"]["closing_balance"] == -50000.0
    assert totals["Bank OD A/c"]["balance_type"] == "Cr"
    # The headline is Tally's Bank Accounts group, not Bank Accounts + OD.
    assert data["total_balance"] == 400000.0


@pytest.mark.asyncio
async def test_specific_bank_balance(native_balances):
    result = await tools.get_bank_balance_tool(
        ledger_name="hdfc", company_name="Test Co"
    )

    data = result["data"]
    assert data["ledger_name"] == "HDFC Bank"
    assert data["closing_balance"] == 250000.0
    assert data["balance_type"] == "Dr"


@pytest.mark.asyncio
async def test_unknown_bank_ledger_is_not_found(native_balances):
    result = await tools.get_bank_balance_tool(
        ledger_name="Axis Bank", company_name="Test Co"
    )
    assert result["success"] is False


def test_cash_balance_formatter_shows_dr_cr_and_source():
    answer = format_tool_response(
        "get_cash_balance",
        {
            "success": True,
            "source": "tally",
            "data": {
                "total_balance": 140000.0,
                "balance_type": "Dr",
                "group_totals": [
                    {"group": "Cash-in-Hand", "closing_balance": 140000.0, "balance_type": "Dr"}
                ],
                "ledgers": [
                    {"name": "Cash", "closing_balance": 150000.0, "balance_type": "Dr"},
                    {"name": "Petty Cash", "closing_balance": -10000.0, "balance_type": "Cr"},
                ],
                "ledger_count": 2,
            },
        },
    )

    assert "Cash-in-Hand (Tally group closing balance): ₹1,40,000 Dr" in answer
    assert "Cash: ₹1,50,000 Dr" in answer
    assert "Petty Cash: ₹10,000 Cr" in answer


def test_bank_balance_formatter_explains_od_is_separate():
    answer = format_tool_response(
        "get_bank_balance",
        {
            "success": True,
            "source": "tally",
            "data": {
                "total_balance": 400000.0,
                "group_totals": [
                    {"group": "Bank Accounts", "closing_balance": 400000.0, "balance_type": "Dr"},
                    {"group": "Bank OD A/c", "closing_balance": -50000.0, "balance_type": "Cr"},
                ],
                "ledgers": [],
            },
        },
    )

    assert "₹4,00,000 Dr" in answer
    assert "₹50,000 Cr" in answer
    assert "not added together" in answer
