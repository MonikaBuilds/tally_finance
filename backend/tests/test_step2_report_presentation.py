import pytest
from app.chatbot.formatter import format_tool_response
from app.chatbot.tools import get_profit_loss_tool, get_trial_balance_tool, get_balance_sheet_tool
from unittest.mock import patch, AsyncMock


def test_profit_loss_formatter_displays_all_items_and_no_placeholder():
    """Verify P&L formatter presents full report items and does not output placeholder count message."""
    pl_result = {
        "success": True,
        "source": "tally",
        "data": {
            "from_date": "2026-04-01",
            "to_date": "2026-11-18",
            "left": [
                {"name": "Cost of Sales", "amount": 10500000.0, "is_group": True},
                {"name": "Indirect Expenses", "amount": 270000.0, "is_group": True},
                {"name": "Net Profit", "amount": 23940000.0, "is_group": True},
            ],
            "right": [
                {"name": "Sales Accounts", "amount": 7410000.0, "is_group": True},
                {"name": "Direct Incomes", "amount": 500000.0, "is_group": True},
                {"name": "Closing Stock", "amount": 26800000.0, "is_group": True},
            ],
            "summary": {
                "gross_result": {"type": "profit", "amount": 24210000.0},
                "net_result": {"type": "profit", "amount": 23940000.0},
            },
            "total_left": 34710000.0,
            "total_right": 34710000.0,
            "count": 6,
        },
    }

    answer = format_tool_response("get_profit_loss", pl_result)

    # 1. Must NOT contain the old placeholder string
    assert "was retrieved successfully from Tally with" not in answer
    assert "6 item(s)" not in answer

    # 2. Must contain actual report rows directly from Tally
    assert "Sales Accounts: ₹74,10,000" in answer
    assert "Direct Incomes: ₹5,00,000" in answer
    assert "Closing Stock: ₹2,68,00,000" in answer
    assert "Cost of Sales: ₹1,05,00,000" in answer
    assert "Indirect Expenses: ₹2,70,000" in answer
    assert "Net Profit: ₹2,39,40,000" in answer
    assert "Period: 2026-04-01 to 2026-11-18" in answer


def test_trial_balance_formatter_displays_rows_and_totals():
    """Verify Trial Balance formatter presents accounts, debits, credits, and totals."""
    tb_result = {
        "success": True,
        "source": "tally",
        "data": {
            "to_date": "2026-11-18",
            "rows": [
                {"name": "Capital Account", "debit": 0.0, "credit": 500000.0},
                {"name": "HDFC Bank", "debit": 500000.0, "credit": 0.0},
            ],
            "count": 2,
        },
    }

    answer = format_tool_response("get_trial_balance", tb_result)

    assert "was retrieved successfully from Tally" not in answer
    assert "Capital Account" in answer
    assert "HDFC Bank" in answer
    assert "Total Debit: ₹5,00,000" in answer
    assert "Total Credit: ₹5,00,000" in answer


def test_balance_sheet_formatter_displays_rows():
    """Verify Balance Sheet formatter displays account heads and amounts."""
    bs_result = {
        "success": True,
        "source": "tally",
        "data": {
            "to_date": "2026-11-18",
            "rows": [
                {"name": "Capital Account", "amount": 500000.0},
                {"name": "Current Assets", "amount": 500000.0},
            ],
            "count": 2,
        },
    }

    answer = format_tool_response("get_balance_sheet", bs_result)

    assert "was retrieved successfully from Tally" not in answer
    assert "Capital Account: ₹5,00,000" in answer
    assert "Current Assets: ₹5,00,000" in answer


@pytest.mark.asyncio
async def test_get_profit_loss_tool_returns_structured_tally_data():
    """Verify get_profit_loss_tool surfaces left, right, and summary from Tally parser."""
    mock_tally_pl = {
        "success": True,
        "left": [{"name": "Indirect Expenses", "amount": 270000.0, "is_group": True}],
        "right": [{"name": "Sales Accounts", "amount": 7410000.0, "is_group": True}],
        "total_left": 270000.0,
        "total_right": 7410000.0,
        "summary": {"net_result": 7140000.0},
    }

    with patch("app.chatbot.tools.fetch_profit_loss", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_tally_pl

        res = await get_profit_loss_tool()
        assert res["success"] is True
        assert res["source"] == "tally"
        assert res["data"]["count"] == 2
        assert len(res["data"]["left"]) == 1
        assert len(res["data"]["right"]) == 1
        assert res["data"]["left"][0]["name"] == "Indirect Expenses"
        assert res["data"]["right"][0]["name"] == "Sales Accounts"
