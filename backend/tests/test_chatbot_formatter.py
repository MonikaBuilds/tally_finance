from app.chatbot.formatter import (
    format_indian_currency,
    format_tool_response
)


def test_indian_currency_format():
    assert (
        format_indian_currency(1170000)
        == "₹11,70,000"
    )


def test_receivables_response():
    result = format_tool_response(
        "get_receivables",
        {
            "success": True,
            "source": "tally",
            "data": {
                "total_receivable": 80000,
                "count": 1
            }
        }
    )

    assert "₹80,000" in result


def test_highest_payable_response():
    result = format_tool_response(
        "get_highest_payable",
        {
            "success": True,
            "source": "tally",
            "data": {
                "party": "Test Supplier",
                "amount": 1170000
            }
        }
    )

    assert "Test Supplier" in result
    assert "₹11,70,000" in result


def test_unverified_source_is_rejected():
    result = format_tool_response(
        "get_payables",
        {
            "success": True,
            "source": "unknown",
            "data": {
                "total_payable": 500000
            }
        }
    )

    assert "could not verify" in result