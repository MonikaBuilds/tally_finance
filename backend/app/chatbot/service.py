from app.chatbot.executor import execute_tool
from app.chatbot.formatter import format_tool_response
from app.chatbot.intent_router import detect_local_intent
from app.chatbot.gemini_client import select_tool
from app.chatbot.date_resolver import (
    resolve_date_range,
    resolve_comparison_ranges,
)
from app.chatbot.logging_utils import (
    create_request_id,
    log_chat_event,
)
from app.chatbot.policy import (
    READ_ONLY_MESSAGE,
    is_write_request,
)


UNSUPPORTED_MESSAGE = (
    "I can help with read-only Tally financial queries such as "
    "receivables, payables, pending invoices, revenue, expenses, "
    "profit or loss, Trial Balance, Balance Sheet, overdue and aging "
    "analysis, top outstanding bills, and financial period comparisons."
)


# These tools can understand date ranges such as
# today, this month, last month or a custom period.
DATE_AWARE_TOOLS = {
    "get_revenue",
    "get_expenses",
    "get_net_profit",
    "get_profit_loss",
    "get_financial_summary",

    "get_cash_transactions",
    "get_sales_transactions",
    "get_purchase_transactions",
    "get_receipt_transactions",
    "get_payment_transactions",
    "get_credit_note_transactions",
    "get_debit_note_transactions",

    # Statements can also be requested for a specific period.
    "get_customer_statement",
    "get_supplier_statement",

    # GST and TDS reports support period-wise queries.
    "get_input_gst",
    "get_output_gst",
    "get_gst_summary",
    "get_tds_summary",
    "get_tds_transactions",

    "get_cash_flow_summary",
    "get_profitability_summary",
    
    # Any ledger can also be queried for a period.
    "get_ledger_report",
    
    "get_sales_by_customer",
    "get_purchases_by_supplier",
    
    "get_top_selling_items",
    "get_low_selling_items",
    "get_stock_movement",
    "get_customer_profitability",
    "get_product_profitability",
    "get_tax_liability",
    "get_tds_receivable",
    "get_tds_payable",
    "get_company_comparison",
    "get_financial_trends",
    
    "get_cost_centre_analysis",
    "get_party_statement",
    "get_bank_transactions",
    "get_ledger_transactions",
    
}


# Comparison uses two separate periods, so it is
# handled separately from normal date-aware tools.
COMPARISON_TOOL = "get_period_comparison"


def _extract_allowed_companies(
    message: str,
    allowed_companies: list[str] | None,
) -> list[str]:
    """
    Extract company names from the user's message using only
    companies assigned to the authenticated user.
    """

    if not message or not allowed_companies:
        return []

    normalized_message = message.casefold()

    # Longer names first so similar company names
    # are matched more reliably.
    sorted_companies = sorted(
        allowed_companies,
        key=len,
        reverse=True,
    )

    matched_companies = []

    for company in sorted_companies:
        if not company:
            continue

        if company.casefold() in normalized_message:
            matched_companies.append(company)

    return matched_companies
async def process_chat_message(
    message: str,
    company_name: str | None = None,
    allowed_companies: list[str] | None = None,
    user_id: str | None = None,
) -> dict:
    """
    Process a chatbot message and return financial data
    from the approved read-only Tally tools.
    """

    request_id = create_request_id()

    log_chat_event(
        request_id=request_id,
        event="request_received",
    )

    cleaned_message = message.strip()

    # Do not process an empty chatbot request.
    if not cleaned_message:
        log_chat_event(
            request_id=request_id,
            event="invalid_request",
            intent="invalid_request",
        )

        return {
            "success": False,
            "source": None,
            "intent": "invalid_request",
            "answer": "Please enter a financial question.",
            "data": None,
        }

    # The chatbot is read-only.
    # Block requests that try to create, update or delete Tally data.
    if is_write_request(cleaned_message):
        log_chat_event(
            request_id=request_id,
            event="write_request_blocked",
            intent="write_operation",
        )

        return {
            "success": False,
            "source": None,
            "intent": "write_operation",
            "answer": READ_ONLY_MESSAGE,
            "data": None,
        }

    try:
        # First try the fast local router.
        # This avoids calling Gemini for simple and common queries.
        local_intent = detect_local_intent(
            cleaned_message
        )

        if isinstance(local_intent, dict):
            # Some local queries also contain values needed by the tool.
            # Example: customer statement with a customer name.
            selection = {
                "tool_name": local_intent.get(
                    "tool_name"
                ),
                "arguments": local_intent.get(
                    "arguments",
                    {},
                ),
                "error": None,
            }

        elif local_intent:
            # Simple local intents only need the tool name.
            selection = {
                "tool_name": local_intent,
                "arguments": {},
                "error": None,
            }

        else:
            # Use Gemini only when the local router
            # cannot confidently understand the request.
            selection = await select_tool(
                cleaned_message
            )

    except Exception:
        log_chat_event(
            request_id=request_id,
            event="model_exception",
            intent="model_error",
        )

        return {
            "success": False,
            "source": None,
            "intent": "model_error",
            "answer": (
                "I am unable to understand the request right now. "
                "Please try again shortly."
            ),
            "data": None,
        }

    model_error = selection.get(
        "error"
    )

    # Handle Gemini timeout separately so the user
    # receives a clear message instead of a server error.
    if model_error == "timeout":
        log_chat_event(
            request_id=request_id,
            event="model_timeout",
            intent="model_timeout",
        )

        return {
            "success": False,
            "source": None,
            "intent": "model_timeout",
            "answer": (
                "The AI service is taking longer than expected. "
                "Please try again."
            ),
            "data": None,
        }

    if model_error == "rate_limit":
        log_chat_event(
            request_id=request_id,
            event="model_rate_limit",
            intent="model_rate_limit",
        )

        return {
            "success": False,
            "source": None,
            "intent": "model_rate_limit",
            "answer": (
                "The AI service is temporarily busy. "
                "Please try again in a moment."
            ),
            "data": None,
        }

    if model_error == "authentication":
        log_chat_event(
            request_id=request_id,
            event="model_authentication_error",
            intent="model_authentication_error",
        )

        return {
            "success": False,
            "source": None,
            "intent": "model_authentication_error",
            "answer": (
                "The chatbot service is temporarily unavailable."
            ),
            "data": None,
        }

    if model_error == "model_not_found":
        log_chat_event(
            request_id=request_id,
            event="model_configuration_error",
            intent="model_configuration_error",
        )

        return {
            "success": False,
            "source": None,
            "intent": "model_configuration_error",
            "answer": (
                "The chatbot service is temporarily unavailable."
            ),
            "data": None,
        }

    if model_error in {
        "model_error",
        "model_unavailable",
    }:
        log_chat_event(
            request_id=request_id,
            event="model_error",
            intent="model_error",
        )

        return {
            "success": False,
            "source": None,
            "intent": "model_error",
            "answer": (
                "The chatbot service is temporarily unavailable. "
                "Please try again shortly."
            ),
            "data": None,
        }

    tool_name = selection.get(
        "tool_name"
    )

    # Make our own copy so we can safely add
    # company and date values below.
    arguments = dict(
        selection.get(
            "arguments",
            {},
        )
        or {}
    )

    if not tool_name:
        log_chat_event(
            request_id=request_id,
            event="unsupported_request",
            intent="unsupported",
        )

        return {
            "success": False,
            "source": None,
            "intent": "unsupported",
            "answer": UNSUPPORTED_MESSAGE,
            "data": None,
        }

    # Add from_date and to_date when the selected
    # financial tool supports period-wise queries.
    if tool_name in DATE_AWARE_TOOLS:
        resolved_range = resolve_date_range(
            cleaned_message
        )

        if resolved_range:
            arguments["from_date"] = (
                resolved_range.from_date.strftime(
                    "%d-%m-%Y"
                )
            )

            arguments["to_date"] = (
                resolved_range.to_date.strftime(
                    "%d-%m-%Y"
                )
            )

    # Comparison queries need two separate periods,
    # so they use four date arguments.
    if tool_name == COMPARISON_TOOL:
        comparison = resolve_comparison_ranges(
            cleaned_message
        )

        if comparison:
            arguments["first_from_date"] = (
                comparison.first_period.from_date.strftime(
                    "%d-%m-%Y"
                )
            )

            arguments["first_to_date"] = (
                comparison.first_period.to_date.strftime(
                    "%d-%m-%Y"
                )
            )

            arguments["second_from_date"] = (
                comparison.second_period.from_date.strftime(
                    "%d-%m-%Y"
                )
            )

            arguments["second_to_date"] = (
                comparison.second_period.to_date.strftime(
                    "%d-%m-%Y"
                )
            )

    # Normal tools use one selected company.
    # Company comparison handles multiple companies separately.
    # For company comparison, verify that every requested
    # company belongs to the authenticated user.
    if tool_name == "get_company_comparison":
        requested_companies = _extract_allowed_companies(
            cleaned_message,
            allowed_companies,
        )

        arguments["company_names"] = requested_companies

        if len(requested_companies) < 2:
            return {
                "success": False,
                "source": "validation",
                "intent": tool_name,
                "answer": (
                    "Please specify at least two companies to compare."
                ),
                "data": None,
            }

        allowed_company_set = {
            name.strip().casefold()
            for name in (allowed_companies or [])
            if name
        }

        unauthorized_companies = [
            name
            for name in requested_companies
            if (
                not isinstance(name, str)
                or name.strip().casefold()
                not in allowed_company_set
            )
        ]

        if unauthorized_companies:
            return {
                "success": False,
                "source": "authorization",
                "intent": tool_name,
                "answer": (
                    "You are not authorized to access "
                    "one or more requested companies."
                ),
                "data": None,
            }


    # Normal tools use one selected company.
    if company_name and tool_name != "get_company_comparison":
        arguments["company_name"] = company_name


    log_chat_event(
        request_id=request_id,
        event="tool_selected",
        intent=tool_name,
    )

    # Execute only a tool registered in our approved
    # read-only financial tool registry.
    tool_result = await execute_tool(
        tool_name=tool_name,
        arguments=arguments,
        user_id = user_id,
    )

    if not tool_result.get("success"):
        log_chat_event(
            request_id=request_id,
            event="tool_failed",
            intent=tool_name,
            source=tool_result.get(
                "source"
            ),
        )

        return {
            "success": False,
            "source": tool_result.get(
                "source"
            ),
            "intent": tool_name,
            "answer": tool_result.get(
                "message",
                "Unable to retrieve the requested data from Tally.",
            ),
            "data": None,
        }

    # Convert the tool result into a user-friendly
    # chatbot response.
    answer = format_tool_response(
        tool_name=tool_name,
        tool_result=tool_result,
    )

    log_chat_event(
        request_id=request_id,
        event="request_completed",
        intent=tool_name,
        source="tally",
    )

    return {
        "success": True,
        "source": "tally",
        "intent": tool_name,
        "answer": answer,
        "data": tool_result.get(
            "data"
        ),
    }