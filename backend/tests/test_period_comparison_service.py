from datetime import date

import pytest

import app.chatbot.service as service
from app.chatbot.date_resolver import (
    resolve_comparison_ranges
)


@pytest.mark.asyncio
async def test_period_comparison_service_resolves_dates(
    monkeypatch
):
    async def fake_select_tool(message):
        return {
            "tool_name": "get_period_comparison",
            "arguments": {
                "metric": "revenue"
            }
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
                "metric": "revenue",
                "first_period": {
                    "from_date": "2026-08-01",
                    "to_date": "2026-08-31",
                    "value": 800000
                },
                "second_period": {
                    "from_date": "2026-07-01",
                    "to_date": "2026-07-31",
                    "value": 700000
                },
                "difference": 100000,
                "percentage_change": 14.29
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
        "resolve_comparison_ranges",
        lambda message: resolve_comparison_ranges(
            message,
            today=date(2026, 8, 31)
        )
    )

    result = await service.process_chat_message(
        "Compare revenue this month vs last month"
    )

    assert result["success"] is True
    assert result["source"] == "tally"
    assert result["intent"] == "get_period_comparison"

    assert (
        captured["tool_name"]
        == "get_period_comparison"
    )

    arguments = captured["arguments"]

    assert arguments["metric"] == "revenue"

    assert (
        arguments["first_from_date"]
        == "01-08-2026"
    )

    assert (
        arguments["first_to_date"]
        == "31-08-2026"
    )

    assert (
        arguments["second_from_date"]
        == "01-07-2026"
    )

    assert (
        arguments["second_to_date"]
        == "31-07-2026"
    )

    assert "Revenue comparison:" in result["answer"]

    assert "₹8,00,000" in result["answer"]

    assert "₹7,00,000" in result["answer"]

    assert "14.29%" in result["answer"]