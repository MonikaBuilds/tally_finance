import pytest
from app.chatbot.intent_router import detect_local_intent
from app.chatbot.tools import (
    get_ledger_balance_tool,
    get_ledger_transactions_tool,
    get_stock_item_details_tool,
)
from unittest.mock import patch, AsyncMock


def test_profit_and_loss_with_financial_year_routes_to_pl():
    """Verify 'Show me the Profit and Loss statement for this financial year.' routes to get_profit_loss."""
    intent = detect_local_intent("Show me the Profit and Loss statement for this financial year.")
    assert intent == "get_profit_loss"


def test_profit_and_loss_variations_route_to_pl():
    """Verify various natural language P&L queries route to get_profit_loss."""
    queries = [
        "Show me the Profit and Loss statement.",
        "Show me all 6 items from the Profit and Loss report.",
        "Show me P&L.",
        "Show profit and loss",
        "Show my P&L statement.",
        "P&L for this financial year.",
        "Profit and loss for FY 2026-27.",
    ]
    for q in queries:
        assert detect_local_intent(q) == "get_profit_loss", f"Failed for query: {q}"


def test_balance_sheet_and_trial_balance_routes():
    """Verify Balance Sheet and Trial Balance route directly to their respective tools."""
    assert detect_local_intent("Show me the Balance Sheet for this financial year.") == "get_balance_sheet"
    assert detect_local_intent("Show me the Trial Balance.") == "get_trial_balance"


def test_bank_details_query_routes_to_ledger_report():
    """Verify 'Show me the complete details of HDFC Bank' routes to get_ledger_report, not stock item."""
    intent = detect_local_intent("Show me the complete details of HDFC Bank")
    assert isinstance(intent, dict)
    assert intent["tool_name"] == "get_ledger_report"
    assert intent["arguments"]["ledger_name"] == "HDFC Bank"


def test_stock_details_query_routes_with_correct_item_name_param():
    """Verify stock item details routes with 'item_name' argument to avoid TypeError."""
    intent = detect_local_intent("Show stock details of Steel Rod")
    assert isinstance(intent, dict)
    assert intent["tool_name"] == "get_stock_item_details"
    assert "item_name" in intent["arguments"]
    assert intent["arguments"]["item_name"] == "Steel Rod"


def test_sales_account_closing_balance_routes_correctly():
    """Verify 'What is the closing balance of Sales Account?' routes to get_ledger_balance."""
    intent = detect_local_intent("What is the closing balance of Sales Account?")
    assert isinstance(intent, dict)
    assert intent["tool_name"] == "get_ledger_balance"
    assert intent["arguments"]["ledger_name"] == "Sales Account"


@pytest.mark.asyncio
async def test_ledger_balance_resolves_accounting_suffixes():
    """Verify Sales Account resolves to Sales A/c in Tally and returns direct Tally values."""
    # Ledger masters carry Tally's sign: Cr positive, Dr negative.
    # The tool returns the ledger-report convention (Dr positive).
    mock_ledgers = [
        {
            "name": "Sales A/c",
            "parent": "Sales Accounts",
            "opening_balance": 0.0,
            "closing_balance": 7410000.0,
        },
        {
            "name": "HDFC Bank A/c",
            "parent": "Bank Accounts",
            "opening_balance": -50000.0,
            "closing_balance": -450000.0,
        },
    ]

    with patch("app.chatbot.tools.fetch_ledger_list", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_ledgers

        result = await get_ledger_balance_tool("Sales Account")
        assert result["success"] is True
        assert result["source"] == "tally"
        assert result["data"]["ledger_name"] == "Sales A/c"
        assert result["data"]["closing_balance"] == -7410000.0

        hdfc_result = await get_ledger_balance_tool("HDFC Bank")
        assert hdfc_result["success"] is True
        assert hdfc_result["data"]["ledger_name"] == "HDFC Bank A/c"
        assert hdfc_result["data"]["closing_balance"] == 450000.0


@pytest.mark.asyncio
async def test_ledger_transactions_resolves_accounting_suffixes():
    """Verify get_ledger_transactions_tool resolves ledger name and calls Tally report."""
    mock_ledgers = [
        {"name": "HDFC Bank A/c", "parent": "Bank Accounts"},
    ]
    mock_report = {
        "ledger_name": "HDFC Bank A/c",
        "opening_balance": 100000.0,
        "closing_balance": 450000.0,
        "entries": [
            {"date": "2026-04-01", "voucher_type": "Receipt", "amount": 350000.0}
        ],
    }

    with patch("app.chatbot.tools.fetch_ledger_list", new_callable=AsyncMock) as mock_list, \
         patch("app.chatbot.tools.fetch_ledger_report", new_callable=AsyncMock) as mock_rep:
        mock_list.return_value = mock_ledgers
        mock_rep.return_value = mock_report

        result = await get_ledger_transactions_tool("HDFC Bank")
        assert result["success"] is True
        assert result["source"] == "tally"
        assert result["data"]["ledger_name"] == "HDFC Bank A/c"
        assert result["data"]["count"] == 1
        assert len(result["data"]["transactions"]) == 1
