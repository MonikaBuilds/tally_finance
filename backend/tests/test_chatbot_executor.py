import pytest

import app.chatbot.executor as executor
from app.chatbot.executor import execute_tool


@pytest.mark.asyncio
async def test_unknown_tool_is_blocked():
    result = await execute_tool(
        "delete_invoice",
        {}
    )

    assert result["success"] is False
    assert result["source"] is None
    assert result["data"] is None

    assert (
        "read-only assistant"
        in result["message"]
    )


@pytest.mark.asyncio
async def test_update_tool_is_blocked():
    result = await execute_tool(
        "update_ledger",
        {}
    )

    assert result["success"] is False
    assert result["data"] is None


@pytest.mark.asyncio
async def test_invalid_date_is_rejected(
    monkeypatch,
):
    monkeypatch.setattr(
        executor,
        "can_execute_tool",
        lambda user_id, tool_name: True,
    )

    result = await execute_tool(
        "get_revenue",
        {
            "from_date": "2025-04-01",
            "to_date": "30-04-2025",
        },
        user_id="test-user",
    )

    assert result["success"] is False

    assert (
        "DD-MM-YYYY"
        in result["message"]
    )

@pytest.mark.asyncio
async def test_impossible_date_is_rejected(
    monkeypatch,
):
    monkeypatch.setattr(
        executor,
        "can_execute_tool",
        lambda user_id, tool_name: True,
    )

    result = await execute_tool(
        "get_revenue",
        {
            "from_date": "31-02-2025",
            "to_date": "30-04-2025",
        },
        user_id="test-user",
    )

    assert result["success"] is False

    assert (
        "valid date"
        in result["message"]
    )

@pytest.mark.asyncio
async def test_invalid_company_type_is_rejected(
    monkeypatch,
):
    monkeypatch.setattr(
        executor,
        "can_execute_tool",
        lambda user_id, tool_name: True,
    )

    result = await execute_tool(
        "get_payables",
        {
            "company_name": 12345,
        },
        user_id="test-user",
    )

    assert result["success"] is False

    assert (
        "company_name must be a string"
        in result["message"]
    )
    
@pytest.mark.asyncio
async def test_unauthorized_tool_is_blocked(
    monkeypatch,
):
    monkeypatch.setattr(
        executor,
        "can_execute_tool",
        lambda user_id, tool_name: False,
    )

    result = await execute_tool(
        "get_bank_balance",
        {},
        user_id="test-user",
    )

    assert result["success"] is False
    assert result["source"] == "authorization"
    assert result["data"] is None
    assert "not authorized" in result["message"]