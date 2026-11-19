import pytest
from datetime import date
from unittest.mock import patch, AsyncMock

from app.chatbot.intent_router import detect_local_intent, _clean_ledger_name
from app.chatbot.date_resolver import resolve_date_range
from app.chatbot.formatter import format_tool_response
from app.chatbot.executor import execute_tool, APPLICATION_AGGREGATION_TOOLS
from app.chatbot.tools import get_day_book_tool, get_stock_summary_tool


# ============================================================
# 1. INTENT ROUTING TESTS
# ============================================================

def test_day_book_routing_variations():
    """Verify Day Book, daybook, dairy, diary all route to get_day_book."""
    queries = [
        "Show the day book for 01-04-2025",
        "Show the day book for December 2025",
        "Show the day book",
        "daybook",
        "Show the day book dairy",
        "Show the day book diary",
        "day book dairy",
        "day book diary",
        "dairy",
        "daily dairy",
        "Show today's day book",
    ]
    for q in queries:
        intent = detect_local_intent(q)
        assert intent == "get_day_book", f"Failed for query: {q}"


def test_closing_stock_and_inventory_routing():
    """Verify closing stock and inventory valuation queries route to get_stock_summary."""
    queries = [
        "What is my closing stock?",
        "What is our closing stock?",
        "Show closing stock",
        "closing stock",
        "Show stock summary",
        "What is my stock value?",
        "Show the stock summary of SmartMind AI - Old Version as on 31-03-2026",
    ]
    for q in queries:
        intent = detect_local_intent(q)
        assert intent == "get_stock_summary", f"Failed for query: {q}"

    # Inventory valuation routes with valuation_only=True
    val_intent = detect_local_intent("inventory valuation")
    assert isinstance(val_intent, dict)
    assert val_intent["tool_name"] == "get_stock_summary"
    assert val_intent["arguments"]["valuation_only"] is True


def test_voucher_entries_routing():
    """Verify voucher and transaction queries cleanly extract ledger name."""
    cases = [
        (
            "Show all transactions of Eagle Paradise Pvt. Ltd.",
            "Eagle Paradise Pvt. Ltd.",
        ),
        (
            "List the 10 vouchers in the Eagle Paradise Pvt. Ltd. ledger",
            "Eagle Paradise Pvt. Ltd.",
        ),
        (
            "Show the voucher-wise entries of Eagle Paradise Pvt. Ltd. with date, voucher type, voucher number and amount",
            "Eagle Paradise Pvt. Ltd.",
        ),
        (
            "Show transactions of HDFC Bank",
            "HDFC Bank",
        ),
    ]
    for q, expected_ledger in cases:
        intent = detect_local_intent(q)
        assert isinstance(intent, dict), f"Expected dict intent for '{q}', got {intent}"
        assert intent["tool_name"] == "get_ledger_transactions", f"Failed tool name for '{q}'"
        assert intent["arguments"]["ledger_name"] == expected_ledger, f"Failed ledger name for '{q}'"


def test_clean_ledger_name():
    """Verify trailing instructions and decorators are stripped cleanly."""
    assert _clean_ledger_name("Eagle Paradise Pvt. Ltd. ledger") == "Eagle Paradise Pvt. Ltd."
    assert _clean_ledger_name("Eagle Paradise Pvt. Ltd. with date, voucher type, voucher number and amount") == "Eagle Paradise Pvt. Ltd."
    assert _clean_ledger_name("HDFC Bank with details") == "HDFC Bank"


# ============================================================
# 2. DATE RESOLUTION TESTS
# ============================================================

def test_single_date_resolution():
    """Verify single dates format as both from_date and to_date."""
    dr1 = resolve_date_range("Show the day book for 01-04-2025")
    assert dr1 is not None
    assert dr1.from_date == date(2025, 4, 1)
    assert dr1.to_date == date(2025, 4, 1)

    dr2 = resolve_date_range("Show the stock summary as on 31-03-2026")
    assert dr2 is not None
    assert dr2.from_date == date(2026, 3, 31)
    assert dr2.to_date == date(2026, 3, 31)


def test_month_date_resolution():
    """Verify month names resolve to full month range."""
    dr = resolve_date_range("Show the day book for December 2025")
    assert dr is not None
    assert dr.from_date == date(2025, 12, 1)
    assert dr.to_date == date(2025, 12, 31)


# ============================================================
# 3. EXECUTOR AND AGGREGATION DISCLAIMER TESTS
# ============================================================

def test_get_ledger_transactions_not_in_aggregation_disclaimer():
    """Verify get_ledger_transactions is NOT tagged as application aggregation."""
    assert "get_ledger_transactions" not in APPLICATION_AGGREGATION_TOOLS


@pytest.mark.asyncio
async def test_execute_tool_inspect_filters_unexpected_kwargs():
    """Verify execute_tool uses inspect.signature so extra kwargs don't raise TypeError."""
    mock_stock_data = {
        "success": True,
        "source": "tally",
        "data": {
            "total_items": 1,
            "items_with_stock": 1,
            "total_stock_value": 10000.0,
            "items": [],
        },
    }
    with patch("app.chatbot.executor.TOOL_FUNCTIONS") as mock_tools:
        mock_fn = AsyncMock(return_value=mock_stock_data)
        # Define mock function signature with only company_name and to_date
        import inspect
        mock_tools.__getitem__.return_value = get_stock_summary_tool
        mock_tools.__contains__.return_value = True

        with patch("app.chatbot.executor.can_execute_tool", return_value=True), \
             patch("app.chatbot.executor.cache_manager.get_or_fetch") as mock_cache:
            from app.cache.manager import CacheResult
            mock_cache.return_value = CacheResult(
                data=mock_stock_data,
                source="live",
                cached_at=None,
                is_stale=False,
            )
            # Pass extra from_date to get_stock_summary_tool which only takes to_date
            res = await execute_tool(
                "get_stock_summary",
                {"company_name": "Test Co", "from_date": "01-04-2025", "to_date": "31-03-2026"},
                user_id="test-user",
            )
            assert res["success"] is True
            assert "Invalid arguments were supplied" not in res.get("message", "")


# ============================================================
# 4. FORMATTER TESTS
# ============================================================

def test_day_book_formatter():
    """Verify Day Book formats vouchers cleanly."""
    tool_result = {
        "success": True,
        "source": "tally",
        "data": {
            "from_date": "01-04-2025",
            "to_date": "01-04-2025",
            "count": 2,
            "rows": [
                {
                    "date": "01-04-2025",
                    "voucher_type": "Payment",
                    "voucher_number": "101",
                    "particulars": "Office Rent Exp",
                    "debit": 25000.0,
                    "credit": 0.0,
                    "is_cancelled": False,
                },
                {
                    "date": "01-04-2025",
                    "voucher_type": "Receipt",
                    "voucher_number": "202",
                    "particulars": "Client Alpha",
                    "debit": 0.0,
                    "credit": 50000.0,
                    "is_cancelled": False,
                },
            ],
        },
    }
    output = format_tool_response("get_day_book", tool_result)
    assert "Day Book (from Tally) for 01-04-2025:" in output
    assert "Total Vouchers: 2" in output
    assert "• 01-04-2025 | Payment #101 | Office Rent Exp | ₹25,000 Dr" in output
    assert "• 01-04-2025 | Receipt #202 | Client Alpha | ₹50,000 Cr" in output


def test_ledger_transactions_formatter():
    """Verify ledger transactions displays vouchers and opening/closing balances."""
    tool_result = {
        "success": True,
        "source": "tally",
        "data": {
            "ledger_name": "Eagle Paradise Pvt. Ltd.",
            "opening_balance": 0.0,
            "closing_balance": -616200.0,
            "count": 2,
            "transactions": [
                {
                    "date": "2025-05-10",
                    "voucher_type": "Sales",
                    "voucher_number": "INV-001",
                    "particulars": "Eagle Paradise Pvt. Ltd.",
                    "debit": 300000.0,
                    "credit": 0.0,
                },
                {
                    "date": "2025-05-20",
                    "voucher_type": "Receipt",
                    "voucher_number": "REC-001",
                    "particulars": "Bank Account",
                    "debit": 0.0,
                    "credit": 916200.0,
                },
            ],
        },
    }
    output = format_tool_response("get_ledger_transactions", tool_result)
    assert "Eagle Paradise Pvt. Ltd. Transactions (from Tally):" in output
    assert "Opening Balance: ₹0" in output
    assert "Total Transactions: 2" in output
    assert "• 2025-05-10 | Sales #INV-001 | Eagle Paradise Pvt. Ltd. | ₹3,00,000 Dr" in output
    assert "• 2025-05-20 | Receipt #REC-001 | Bank Account | ₹9,16,200 Cr" in output
    assert "These figures are aggregated by the application" not in output


def test_stock_summary_formatter_with_items():
    """Verify stock summary displays total items, stock value, and item breakdown."""
    tool_result = {
        "success": True,
        "source": "tally",
        "data": {
            "total_items": 2,
            "items_with_stock": 2,
            "total_stock_value": 5545947.0,
            "items": [
                {
                    "name": "SmartMind Enterprise License",
                    "closing_balance": "10 Nos",
                    "closing_rate": "3,00,000/Nos",
                    "closing_value": "30,00,000",
                },
                {
                    "name": "SmartMind Cloud Addon",
                    "closing_balance": "5 Nos",
                    "closing_rate": "5,09,189.40/Nos",
                    "closing_value": "25,45,947",
                },
            ],
        },
    }
    output = format_tool_response("get_stock_summary", tool_result)
    assert "Stock Summary:" in output
    assert "Total Stock Items: 2" in output
    assert "Items with Stock: 2" in output
    assert "Stock Value: ₹55,45,947" in output
    assert "Items Breakdown:" in output
    assert "• SmartMind Enterprise License: 10 Nos @ 3,00,000/Nos | Value: ₹30,00,000" in output
    assert "• SmartMind Cloud Addon: 5 Nos @ 5,09,189.40/Nos | Value: ₹25,45,947" in output
