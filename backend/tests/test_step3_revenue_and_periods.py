import pytest
from datetime import date
from unittest.mock import AsyncMock, patch

from app.chatbot.date_resolver import (
    resolve_date_range,
    get_current_financial_year_range,
    _financial_year_start,
)
from app.chatbot.intent_router import detect_local_intent
from app.financial.calculations import build_dashboard_financials
from app.chatbot.formatter import format_tool_response
from app.chatbot.service import process_chat_message


def test_explicit_financial_year_resolution():
    """Verify various formats of explicit Financial Year notation."""
    r1 = resolve_date_range("Profit and loss for FY 2025-26")
    assert r1 is not None
    assert r1.from_date == date(2025, 4, 1)
    assert r1.to_date == date(2026, 3, 31)
    assert "2025" in r1.label

    r2 = resolve_date_range("Profit and loss for FY 2026–27")  # en-dash
    assert r2 is not None
    assert r2.from_date == date(2026, 4, 1)
    assert r2.to_date == date(2027, 3, 31)

    r3 = resolve_date_range("Show revenue for FY 25-26")
    assert r3 is not None
    assert r3.from_date == date(2025, 4, 1)
    assert r3.to_date == date(2026, 3, 31)

    r4 = resolve_date_range("financial year 2025-26")
    assert r4 is not None
    assert r4.from_date == date(2025, 4, 1)
    assert r4.to_date == date(2026, 3, 31)


def test_between_and_natural_date_ranges():
    """Verify between ... and ... and month-to-month ranges."""
    r1 = resolve_date_range("Show P&L between 01-04-2026 and 30-09-2026")
    assert r1 is not None
    assert r1.from_date == date(2026, 4, 1)
    assert r1.to_date == date(2026, 9, 30)

    r2 = resolve_date_range("Show P&L from 01/04/2026 to 30/09/2026")
    assert r2 is not None
    assert r2.from_date == date(2026, 4, 1)
    assert r2.to_date == date(2026, 9, 30)

    r3 = resolve_date_range("Show the P&L from April to September", today=date(2026, 11, 18))
    assert r3 is not None
    assert r3.from_date == date(2026, 4, 1)
    assert r3.to_date == date(2026, 9, 30)

    r4 = resolve_date_range("between 1 April 2026 and 30 September 2026")
    assert r4 is not None
    assert r4.from_date == date(2026, 4, 1)
    assert r4.to_date == date(2026, 9, 30)


def test_financial_year_start_and_default_range():
    """Verify Indian financial year start calculation."""
    # In Nov 2026, FY started on 1-Apr-2026
    nov_date = date(2026, 11, 18)
    assert _financial_year_start(nov_date) == date(2026, 4, 1)
    fy_nov = get_current_financial_year_range(today=nov_date)
    assert fy_nov.from_date == date(2026, 4, 1)
    assert fy_nov.to_date == date(2026, 11, 18)

    # In Feb 2026, FY started on 1-Apr-2025
    feb_date = date(2026, 2, 10)
    assert _financial_year_start(feb_date) == date(2025, 4, 1)


def test_calculations_revenue_broad_matching():
    """Verify build_dashboard_financials detects Sales, Revenue from Operations, and Direct Incomes."""
    # Test 1: Standard 'Sales Accounts'
    pl1 = [
        {"name": "Sales Accounts", "main_amount": 7410000.0},
        {"name": "Cost of Sales", "main_amount": 5000000.0},
        {"name": "Indirect Expenses", "main_amount": 500000.0},
    ]
    res1 = build_dashboard_financials(pl1, {}, {}, {})
    assert res1["revenue"] == 7410000.0

    # Test 2: 'Revenue from Operations'
    pl2 = [
        {"name": "Revenue from Operations", "main_amount": 8500000.0},
        {"name": "Cost of Sales", "main_amount": 6000000.0},
    ]
    res2 = build_dashboard_financials(pl2, {}, {}, {})
    assert res2["revenue"] == 8500000.0

    # Test 3: 'Sales' + 'Direct Incomes'
    pl3 = [
        {"name": "Sales", "main_amount": 7000000.0},
        {"name": "Direct Incomes", "main_amount": 410000.0},
        {"name": "Cost of Sales", "main_amount": 5000000.0},
    ]
    res3 = build_dashboard_financials(pl3, {}, {}, {})
    assert res3["revenue"] == 7410000.0


def test_intent_routing_earnings_and_variations():
    """Verify net profit/earnings intent routing."""
    intent1 = detect_local_intent("How much did I earn this financial year?")
    assert intent1 == "get_net_profit"

    intent2 = detect_local_intent("What was my net profit this year?")
    assert intent2 == "get_net_profit"

    intent3 = detect_local_intent("Show me my earnings")
    assert intent3 == "get_net_profit"


def test_formatter_includes_period_for_revenue_and_expenses():
    """Verify formatter displays the resolved period transparently."""
    rev_result = {
        "success": True,
        "source": "tally",
        "data": {
            "revenue": 7410000.0,
            "from_date": "2026-04-01",
            "to_date": "2026-11-18",
        },
    }
    msg = format_tool_response("get_revenue", rev_result)
    assert "₹74,10,000" in msg
    assert "01-04-2026 to 18-11-2026" in msg

    exp_result = {
        "success": True,
        "source": "tally",
        "data": {
            "expenses": 1500000.0,
            "from_date": "2026-04-01",
            "to_date": "2026-11-18",
        },
    }
    exp_msg = format_tool_response("get_expenses", exp_result)
    assert "₹15,00,000" in exp_msg
    assert "01-04-2026 to 18-11-2026" in exp_msg


@pytest.mark.asyncio
async def test_process_chat_revenue_applies_default_current_fy():
    """Verify process_chat_message defaults to current FY for revenue without date."""
    mock_revenue = {
        "success": True,
        "source": "tally",
        "data": {
            "revenue": 7410000.0,
            "from_date": "2026-04-01",
            "to_date": "2026-11-18",
        },
    }

    with patch("app.chatbot.service.execute_tool", AsyncMock(return_value=mock_revenue)) as mock_exec:
        res = await process_chat_message(
            "What is my revenue?",
            company_name="BC Pvt Ltd",
            allowed_companies=["BC Pvt Ltd"],
            user_id="test_user",
        )

        assert res["success"] is True
        assert "₹74,10,000" in res["answer"]
        # Check that execute_tool received from_date and to_date
        kwargs = mock_exec.call_args.kwargs
        assert kwargs.get("tool_name") == "get_revenue"
        tool_args = kwargs.get("arguments", {})
        assert "from_date" in tool_args
        assert "to_date" in tool_args
