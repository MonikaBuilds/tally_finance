from datetime import date

import pytest

import app.chatbot.service as service
from app.chatbot.date_resolver import resolve_date_range


@pytest.mark.asyncio
async def test_financial_summary_service_resolves_dates(
    monkeypatch
):
    async def fake_select_tool(message):
        return {
            "tool_name": "get_financial_summary",
            "arguments": {}
        }

    captured = {}

    async def fake_execute_tool(
        tool_name,
        arguments,
        user_id=None,
    ):
        captured["tool_name"] = tool_name
        captured["arguments"] = arguments.copy()

        return {
            "success": True,
            "source": "tally",
            "data": {
                "from_date": "2026-07-01",
                "to_date": "2026-07-31",
                "revenue": 700000,
                "expenses": 500000,
                "net_profit": 200000,
                "receivables": 80000,
                "payables": 117000,
                "pending_invoices": 2
            }
        }

    monkeypatch.setattr(
        service,
        "select_tool",
        fake_select_tool
    )

    monkeypatch.setattr(
        service,
        "execute_tool",
        fake_execute_tool
    )

    monkeypatch.setattr(
        service,
        "resolve_date_range",
        lambda message: resolve_date_range(
            message,
            today=date(2026, 8, 31)
        )
    )

    result = await service.process_chat_message(
        "Give me the financial summary for last month"
    )

    assert result["success"] is True
    assert result["source"] == "tally"
    assert result["intent"] == "get_financial_summary"

    arguments = captured["arguments"]

    assert captured["tool_name"] == "get_financial_summary"
    assert arguments["from_date"] == "01-07-2026"
    assert arguments["to_date"] == "31-07-2026"

    assert "Financial summary:" in result["answer"]
    assert "₹7,00,000" in result["answer"]
    assert "₹5,00,000" in result["answer"]
    assert "₹2,00,000" in result["answer"]
    assert "₹80,000" in result["answer"]
    assert "₹1,17,000" in result["answer"]