"""
Natural-language routing (offline, no AI calls).

1. The local router must send common phrasings to the right Tally tool.
2. Questions it leaves to the AI must still get the right tool in the
   reduced tool list sent to the model (cost optimisation must never hide
   the correct tool).
3. Write requests are blocked; unsafe words in names do not mis-route.
"""

import pytest

from app.chatbot.gemini_client import relevant_tool_names
from app.chatbot.intent_router import detect_local_intent
from app.chatbot.policy import is_write_request


def _tool(result):
    return result.get("tool_name") if isinstance(result, dict) else result


@pytest.mark.parametrize(
    "query",
    [
        "Compare this month's revenue with last month.",
        "Compare this month's revenue with last month",
        "compare this month's expenses with last month",
        "Compare revenue this month with last month",
        "compare revenue this month vs last month",
    ],
)
def test_month_comparison_phrasings_all_reach_the_comparison_tool(query):
    """
    The possessive form ("this month's revenue") is how people actually
    write it. It used to fall through to the single-period revenue tool,
    which answered for one month instead of comparing two.
    """
    assert _tool(detect_local_intent(query)) == "get_period_comparison"


LOCAL_ROUTES = [
    # Day Book
    ("Show the day book for 01-04-2025", "get_day_book"),
    ("Give me the complete Day Book", "get_day_book"),
    ("daybook", "get_day_book"),
    ("dairy", "get_day_book"),
    ("Show today's day book", "get_day_book"),
    # Statements
    ("Generate my Profit & Loss report", "get_profit_loss"),
    ("show p&l for this year", "get_profit_loss"),
    ("Show the trial balance as on 31 March 2026", "get_trial_balance"),
    ("Show my balance sheet", "get_balance_sheet"),
    # Stock
    ("Show my closing stock", "get_stock_summary"),
    ("Inventory valuation", "get_stock_summary"),
    # Outstanding
    pytest.param(
        "Which invoices are pending?", "get_pending_invoices",
        marks=pytest.mark.xfail(strict=True, reason="DEF-RT-01: built-in chat suggestion not routed locally (extra AI call)"),
    ),
    # Cash flow
    ("Show cash flow for this year", "get_cash_flow_summary"),
    # Returns
    ("Show sales returns", "get_credit_note_transactions"),
    ("Show purchase returns", "get_debit_note_transactions"),
    # GST
    ("Show input GST", "get_input_gst"),
    ("show output gst for this month", "get_output_gst"),
]


@pytest.mark.parametrize(("query", "tool"), LOCAL_ROUTES)
def test_local_router_sends_query_to_the_right_tool(query, tool):
    assert _tool(detect_local_intent(query)) == tool


@pytest.mark.parametrize(
    "query",
    [
        "What is the balance of Amul Dairy?",
        "sales of dairy products this month",
        "Mother Dairy ledger",
    ],
)
def test_dairy_in_a_name_does_not_open_the_day_book(query):
    assert _tool(detect_local_intent(query)) != "get_day_book"


@pytest.mark.parametrize(
    "query",
    [
        "Compare profit and loss this month vs last month",
        "balance sheet vs last year",
        "trial balance comparison with March",
    ],
)
def test_comparison_is_not_answered_with_a_single_statement(query):
    assert _tool(detect_local_intent(query)) not in {
        "get_profit_loss", "get_balance_sheet", "get_trial_balance",
    }


def test_customer_statement_extracts_the_party_name():
    result = detect_local_intent("customer statement for Eagle Paradise Pvt. Ltd.")
    assert _tool(result) == "get_customer_statement"
    assert "Eagle Paradise" in str(result.get("arguments"))


@pytest.mark.parametrize(
    ("query", "intent"),
    [
        ("show its transactions", "follow_up_entity_transactions"),
        ("what is its balance", "follow_up_entity_balance"),
        ("show all items", "follow_up_show_all_items"),
    ],
)
def test_follow_up_phrases_are_recognised(query, intent):
    assert detect_local_intent(query) == intent


# ------------------------------------------------------------------
# Questions left to the AI: the reduced tool list must contain the answer
# ------------------------------------------------------------------

AI_ROUTES = [
    ("Who owes us money?", {"get_receivables", "get_outstanding_summary", "get_party_outstanding_summary"}),
    ("Whom do I need to pay?", {"get_payables", "get_outstanding_summary"}),
    ("Which customers have not paid us for more than 60 days?", {"get_aged_receivables", "get_overdue_receivables"}),
    ("What is my closing bank balance?", {"get_bank_balance"}),
    ("How much cash do we have?", {"get_cash_balance"}),
    ("List all purchase entries for April", {"get_purchase_transactions"}),
    ("Show every sales voucher with item details", {"get_sales_transactions"}),
    ("Show my monthly sales", {"get_financial_trends", "get_period_trend", "get_sales_transactions"}),
    ("How much did we spend last month?", {"get_expenses"}),
    pytest.param(
        "Which products sell the most?", {"get_top_selling_items"},
        marks=pytest.mark.xfail(strict=True, reason="DEF-LLM-01: tool pre-selection omits get_top_selling_items"),
    ),
    pytest.param(
        "What do we owe Apex Office Solutions?", {"get_ledger_balance", "get_party_outstanding_summary", "get_supplier_statement", "get_payables"},
        marks=pytest.mark.xfail(strict=True, reason="DEF-LLM-02: 'owe' maps only to receivable tools"),
    ),
    ("Show TDS deducted this year", {"get_tds_summary", "get_tds_transactions"}),
]


@pytest.mark.parametrize(("query", "acceptable"), AI_ROUTES)
def test_reduced_tool_list_contains_the_right_tool(query, acceptable):
    names = relevant_tool_names(query)

    # None means every tool is sent, which is always safe.
    if names is None:
        return

    assert set(names) & acceptable, f"{query!r} -> {names}"
    assert len(names) <= 15


def test_reduced_tool_list_is_much_smaller_than_the_full_schema():
    import json

    from app.chatbot.tool_registry import TOOL_DEFINITIONS

    full = len(json.dumps(TOOL_DEFINITIONS))
    names = relevant_tool_names("Which customers have not paid us for more than 60 days?")
    subset = len(json.dumps([d for d in TOOL_DEFINITIONS if d["name"] in names]))

    assert subset < full * 0.35


# ------------------------------------------------------------------
# Read-only safety
# ------------------------------------------------------------------

@pytest.mark.parametrize(
    "query",
    [
        "Delete invoice 5",
        "create a new payment voucher",
        "update the ledger of Apex",
        "post payment to HDFC",
        "cancel invoice 12",
        "remove the sales entry",
    ],
)
def test_write_requests_are_blocked(query):
    assert is_write_request(query)


@pytest.mark.parametrize(
    "query",
    [
        "any update on receivables",
        "what changed in net profit",
        "show payments",
        "create a report of my sales",
    ],
)
def test_questions_are_not_mistaken_for_writes(query):
    assert not is_write_request(query)
