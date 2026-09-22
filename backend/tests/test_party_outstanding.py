import pytest

import app.chatbot.tools as chatbot_tools
from app.chatbot.formatter import format_tool_response


@pytest.mark.asyncio
async def test_party_outstanding_summary_receivable_only(
    monkeypatch
):
    async def fake_load_outstanding_data(
        company_name=None
    ):
        receivables = {
            "total_receivable": 80000,
            "count": 1,
            "bills": [
                {
                    "party": "Eagle Paradise Pvt. Ltd.",
                    "outstanding_amount": 80000
                }
            ]
        }

        payables = {
            "total_payable": 0,
            "count": 0,
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
        .get_party_outstanding_summary_tool(
            party_name="Eagle Paradise"
        )
    )

    assert result["success"] is True
    assert (
        result["data"]["party"]
        == "Eagle Paradise Pvt. Ltd."
    )
    assert (
        result["data"]["total_receivable"]
        == 80000
    )
    assert (
        result["data"]["total_payable"]
        == 0
    )


def test_party_outstanding_formatter():
    result = format_tool_response(
        "get_party_outstanding_summary",
        {
            "success": True,
            "source": "tally",
            "data": {
                "party": "Eagle Paradise Pvt. Ltd.",
                "total_receivable": 80000,
                "total_payable": 0,
                "receivable_count": 1,
                "payable_count": 0
            }
        }
    )

    assert "Eagle Paradise Pvt. Ltd." in result
    assert "₹80,000" in result
    assert "no outstanding payable" in result