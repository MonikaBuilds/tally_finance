import pytest

import app.chatbot.tools as tools
from app.chatbot.formatter import format_tool_response


@pytest.mark.asyncio
async def test_cash_balance(monkeypatch):
    async def fake_fetch_ledger_list(
        company_name=None
    ):
        return [
            {
                "name": "Cash",
                "parent": "Cash-in-Hand",
                "opening_balance": 100000.0,
                "closing_balance": 125000.0,
            },
            {
                "name": "Petty Cash",
                "parent": "Cash-in-Hand",
                "opening_balance": 10000.0,
                "closing_balance": 15000.0,
            },
            {
                "name": "HDFC Bank",
                "parent": "Bank Accounts",
                "opening_balance": 200000.0,
                "closing_balance": 300000.0,
            },
        ]

    monkeypatch.setattr(
        tools,
        "fetch_ledger_list",
        fake_fetch_ledger_list
    )

    result = await tools.get_cash_balance_tool()

    assert result["success"] is True
    assert result["source"] == "tally"
    assert result["data"]["ledger_count"] == 2
    assert result["data"]["total_balance"] == 140000.0


@pytest.mark.asyncio
async def test_bank_balance(monkeypatch):
    async def fake_fetch_ledger_list(
        company_name=None
    ):
        return [
            {
                "name": "HDFC Bank",
                "parent": "Bank Accounts",
                "opening_balance": 100000.0,
                "closing_balance": 250000.0,
            },
            {
                "name": "SBI Bank",
                "parent": "Bank Accounts",
                "opening_balance": 50000.0,
                "closing_balance": 150000.0,
            },
            {
                "name": "Cash",
                "parent": "Cash-in-Hand",
                "opening_balance": 10000.0,
                "closing_balance": 20000.0,
            },
        ]

    monkeypatch.setattr(
        tools,
        "fetch_ledger_list",
        fake_fetch_ledger_list
    )

    result = await tools.get_bank_balance_tool()

    assert result["success"] is True
    assert result["data"]["ledger_count"] == 2
    assert result["data"]["total_balance"] == 400000.0


@pytest.mark.asyncio
async def test_specific_bank_balance(monkeypatch):
    async def fake_fetch_ledger_list(
        company_name=None
    ):
        return [
            {
                "name": "HDFC Bank",
                "parent": "Bank Accounts",
                "opening_balance": 100000.0,
                "closing_balance": 250000.0,
            },
            {
                "name": "SBI Bank",
                "parent": "Bank Accounts",
                "opening_balance": 50000.0,
                "closing_balance": 150000.0,
            },
        ]

    monkeypatch.setattr(
        tools,
        "fetch_ledger_list",
        fake_fetch_ledger_list
    )

    result = await tools.get_bank_balance_tool(
        ledger_name="HDFC"
    )

    assert result["success"] is True
    assert result["data"]["ledger_name"] == "HDFC Bank"
    assert result["data"]["closing_balance"] == 250000.0


@pytest.mark.asyncio
async def test_bank_balance_excludes_cash(monkeypatch):
    async def fake_fetch_ledger_list(
        company_name=None
    ):
        return [
            {
                "name": "Cash",
                "parent": "Cash-in-Hand",
                "opening_balance": 0.0,
                "closing_balance": 900000.0,
            },
            {
                "name": "Axis Bank",
                "parent": "Bank Accounts",
                "opening_balance": 0.0,
                "closing_balance": 100000.0,
            },
        ]

    monkeypatch.setattr(
        tools,
        "fetch_ledger_list",
        fake_fetch_ledger_list
    )

    result = await tools.get_bank_balance_tool()

    assert result["data"]["total_balance"] == 100000.0
    assert result["data"]["ledger_count"] == 1


def test_cash_balance_formatter():
    result = {
        "success": True,
        "source": "tally",
        "data": {
            "total_balance": 140000.0,
            "ledger_count": 2,
            "ledgers": [
                {
                    "name": "Cash",
                    "closing_balance": 125000.0,
                },
                {
                    "name": "Petty Cash",
                    "closing_balance": 15000.0,
                },
            ],
        },
    }

    answer = format_tool_response(
        "get_cash_balance",
        result
    )

    assert "₹1,40,000" in answer
    assert "Cash" in answer
    assert "Petty Cash" in answer


def test_bank_balance_formatter():
    result = {
        "success": True,
        "source": "tally",
        "data": {
            "total_balance": 400000.0,
            "ledger_count": 2,
            "ledgers": [
                {
                    "name": "HDFC Bank",
                    "closing_balance": 250000.0,
                },
                {
                    "name": "SBI Bank",
                    "closing_balance": 150000.0,
                },
            ],
        },
    }

    answer = format_tool_response(
        "get_bank_balance",
        result
    )

    assert "₹4,00,000" in answer
    assert "HDFC Bank" in answer
    assert "SBI Bank" in answer