import pytest
from unittest.mock import AsyncMock, patch

from app.chatbot.session_store import (
    get_session_state,
    save_session_state,
    build_session_key,
)
from app.chatbot.service import process_chat_message


@pytest.mark.asyncio
async def test_session_store_save_and_get():
    """Verify storing and retrieving session state."""
    state = {
        "last_tool": "get_profit_loss",
        "last_entity": "HDFC Bank",
        "last_data": {"count": 6},
    }
    await save_session_state("user1", "Company A", state, session_id="s1")

    res = await get_session_state("user1", "Company A", session_id="s1")
    assert res is not None
    assert res["last_tool"] == "get_profit_loss"
    assert res["last_entity"] == "HDFC Bank"
    assert res["last_data"] == {"count": 6}

    # Different company or session should be isolated
    diff_comp = await get_session_state("user1", "Company B", session_id="s1")
    assert diff_comp is None

    diff_sess = await get_session_state("user1", "Company A", session_id="s2")
    assert diff_sess is None


@pytest.mark.asyncio
async def test_follow_up_show_all_items_from_session():
    """Verify 'Show all items' resolves from session memory without extra Tally calls."""
    session_id = "test_sess_pnl"
    mock_pnl_data = {
        "left": [
            {"name": "Purchase Accounts", "amount": 5000000.0, "is_group": True},
            {"name": "Direct Expenses", "amount": 500000.0, "is_group": True},
        ],
        "right": [
            {"name": "Sales Accounts", "amount": 7410000.0, "is_group": True},
        ],
        "summary": {
            "gross_result": 1910000.0,
            "net_result": 1500000.0,
        },
        "total_left": 7410000.0,
        "total_right": 7410000.0,
        "count": 3,
    }

    mock_exec_result = {
        "success": True,
        "source": "tally",
        "data": mock_pnl_data,
    }

    # Turn 1: Ask for P&L
    with patch("app.chatbot.service.execute_tool", AsyncMock(return_value=mock_exec_result)):
        res1 = await process_chat_message(
            "Show me the Profit and Loss statement.",
            company_name="BC Pvt Ltd",
            allowed_companies=["BC Pvt Ltd"],
            user_id="user_test",
            session_id=session_id,
        )
        assert res1["success"] is True
        assert "Sales Accounts" in res1["answer"]

    # Turn 2: Follow-up "Show all items" -> Handled via session memory
    with patch("app.chatbot.service.execute_tool", AsyncMock(side_effect=Exception("Should not call Tally"))) as mock_exec2:
        res2 = await process_chat_message(
            "Show all items",
            company_name="BC Pvt Ltd",
            allowed_companies=["BC Pvt Ltd"],
            user_id="user_test",
            session_id=session_id,
        )
        assert res2["success"] is True
        assert "Sales Accounts" in res2["answer"]
        assert "₹74,10,000" in res2["answer"]
        # Ensure execute_tool was never called
        mock_exec2.assert_not_called()


@pytest.mark.asyncio
async def test_follow_up_ledger_context_continuity():
    """Verify follow-up ledger queries carry over the entity from previous turn."""
    session_id = "test_sess_bank"

    # Turn 1: Ask details of HDFC Bank
    mock_ledger_report = {
        "success": True,
        "source": "tally",
        "data": {
            "ledger_name": "HDFC Bank",
            "opening_balance": 100000.0,
            "closing_balance": 250000.0,
            "total_debit": 300000.0,
            "total_credit": 150000.0,
            "vouchers": [],
        },
    }

    with patch("app.chatbot.service.execute_tool", AsyncMock(return_value=mock_ledger_report)):
        res1 = await process_chat_message(
            "Show me the complete details of HDFC Bank",
            company_name="BC Pvt Ltd",
            allowed_companies=["BC Pvt Ltd"],
            user_id="user_test",
            session_id=session_id,
        )
        assert res1["success"] is True

    # Turn 2: Ask "What is its balance?"
    mock_balance = {
        "success": True,
        "source": "tally",
        "data": {
            "ledger_name": "HDFC Bank",
            "closing_balance": 250000.0,
        },
    }

    with patch("app.chatbot.service.execute_tool", AsyncMock(return_value=mock_balance)) as mock_exec_bal:
        res2 = await process_chat_message(
            "What is its balance?",
            company_name="BC Pvt Ltd",
            allowed_companies=["BC Pvt Ltd"],
            user_id="user_test",
            session_id=session_id,
        )
        assert res2["success"] is True
        # Check that execute_tool received HDFC Bank as ledger_name
        tool_name = mock_exec_bal.call_args.kwargs.get("tool_name")
        args = mock_exec_bal.call_args.kwargs.get("arguments", {})
        assert tool_name == "get_ledger_balance"
        assert args.get("ledger_name") == "HDFC Bank"
