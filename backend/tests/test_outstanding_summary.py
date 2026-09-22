import pytest

import app.chatbot.tools as chatbot_tools
from app.chatbot.formatter import format_tool_response


@pytest.mark.asyncio
async def test_outstanding_summary_tool(
    monkeypatch
):
    async def fake_load_outstanding_data(
        company_name=None
    ):
        receivables = {
            "total_receivable": 80000,
            "count": 1,
            "bills": []
        }

        payables = {
            "total_payable": 1170000,
            "count": 1,
            "bills": []
        }

        return receivables, payables

    monkeypatch.setattr(
        chatbot_tools,
        "_load_outstanding_data",
        fake_load_outstanding_data
    )

    result = await (
        chatbot_tools
        .get_outstanding_summary_tool()
    )

    assert result["success"] is True
    assert (
        result["data"]["total_receivable"]
        == 80000
    )
    assert (
        result["data"]["total_payable"]
        == 1170000
    )
    assert (
        result["data"]["receivable_count"]
        == 1
    )
    assert (
        result["data"]["payable_count"]
        == 1
    )


def test_outstanding_summary_formatter():
    answer = format_tool_response(
        "get_outstanding_summary",
        {
            "success": True,
            "source": "tally",
            "data": {
                "total_receivable": 80000,
                "receivable_count": 1,
                "total_payable": 1170000,
                "payable_count": 1
            }
        }
    )

    assert "₹80,000" in answer
    assert "₹11,70,000" in answer