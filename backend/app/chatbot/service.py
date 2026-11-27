import re
from starlette.concurrency import run_in_threadpool
from app.security.permissions import can_execute_tool
from app.chatbot.context import follow_up_selection, FOLLOW_UP
from app.chatbot.exports import save_export, load_export
from app.chatbot.executor import execute_tool
from app.chatbot.formatter import format_tool_response
from app.chatbot.intent_router import detect_local_intent
from app.chatbot.gemini_client import select_tool
from app.chatbot.date_resolver import (
    resolve_date_range,
    InvalidDateRange,
    resolve_comparison_ranges,
    get_current_financial_year_range,
)
from app.chatbot.session_store import (
    get_session_state,
    save_session_state,
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
    "get_day_book",
    "get_monthly_summary",
    "get_stock_item_details",
    "get_trial_balance",
    "get_balance_sheet",
    "get_ledger_balance",
    "get_revenue",
    "get_expenses",
    "get_net_profit",
    "get_profit_loss",
    "get_financial_summary",
    "get_invoice_details",

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
    "get_stock_summary",
    
    "get_sales_by_customer",
    "get_purchases_by_supplier",
    "get_sales_by_item",
    "get_purchases_by_item",
    
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

SESSION_REDISPLAY_TOOLS = {
    "get_profit_loss",
    "get_trial_balance",
    "get_balance_sheet",
}

# Tool-selection cache: the same question needs the same tool, so a repeat
# question skips the model call. Dates are always resolved locally for the
# current day, so selections whose arguments contain dates are not cached.
TOOL_SELECTION_CACHE_TTL = 86400
_SELECTION_DATE_KEYS = {
    "from_date", "to_date", "first_from_date", "first_to_date",
    "second_from_date", "second_to_date", "current_from_date",
    "current_to_date", "previous_from_date", "previous_to_date",
}


def _selection_cache_key(message: str) -> str:
    import hashlib

    normalized = " ".join(message.casefold().split())
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"chat:toolsel:v1:{digest}"


async def _cached_select_tool(message: str) -> dict:
    from app.cache.manager import cache_manager

    key = _selection_cache_key(message)

    try:
        cached, _state, _at = await cache_manager.get_entry(key)
        if isinstance(cached, dict) and "tool_name" in cached:
            return {
                "tool_name": cached.get("tool_name"),
                "arguments": dict(cached.get("arguments") or {}),
                "error": None,
            }
    except Exception:
        pass

    selection = await select_tool(message)

    arguments = selection.get("arguments") or {}
    if (
        selection.get("error") is None
        and not (_SELECTION_DATE_KEYS & set(arguments))
    ):
        try:
            await cache_manager.set_entry(
                key=key,
                data={
                    "tool_name": selection.get("tool_name"),
                    "arguments": arguments,
                },
                fresh_ttl=TOOL_SELECTION_CACHE_TTL,
                retention_ttl=TOOL_SELECTION_CACHE_TTL,
            )
        except Exception:
            pass

    return selection


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
    org_id: str = "default",
    force_refresh: bool = False,
    session_id: str | None = None,
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
            "session_id": session_id,
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
            "session_id": session_id,
        }

    try:
        # First try the fast local router.
        # This avoids calling Gemini for simple and common queries.
        local_intent = detect_local_intent(cleaned_message)
        if local_intent == "unsupported":
            return {"success": False, "source": None, "intent": "unsupported", "answer": UNSUPPORTED_MESSAGE,
                    "data": None, "session_id": session_id}
        session = await get_session_state(user_id, company_name, session_id) if user_id or session_id else None

        follow_match = FOLLOW_UP.match(cleaned_message)
        if (session and session.get("last_tool") == "get_monthly_summary" and follow_match
                and follow_match.group(1).strip(" ?.!").casefold() in {"sales", "revenue", "purchases", "expenses", "profit", "net profit"}):
            local_intent = "follow_up_period"

        if local_intent == "follow_up_export_excel":
            session = session or await get_session_state(user_id, company_name, session_id)
            download = (session or {}).get("last_export")
            if not download:
                return {"success": False, "source": "validation", "intent": "export_excel",
                        "answer": "Ask for a financial or inventory report first, then export it to Excel.", "data": None, "session_id": session_id}
            token = download["url"].split("/")[-1].split(".")[0]
            record = await load_export(user_id, org_id, company_name, token)
            if not record:
                return {"success": False, "source": "validation", "intent": "export_excel",
                        "answer": "The previous report snapshot has expired. Ask for that report again to export it.", "data": None, "session_id": session_id}
            included = (record.get("arguments") or {}).get("company_names", [])
            permitted_companies = {name.casefold() for name in allowed_companies or []}
            if any(name.casefold() not in permitted_companies for name in included):
                return {"success": False, "source": "authorization", "intent": "export_excel",
                        "answer": "Your current company access does not allow this report export.", "data": None, "session_id": session_id}
            permitted = await run_in_threadpool(can_execute_tool, user_id, record["tool_name"])
            if not permitted:
                return {"success": False, "source": "authorization", "intent": "export_excel",
                        "answer": "Your current permissions do not allow this report export.", "data": None, "session_id": session_id}
            return {"success": True, "source": record["result"].get("source", "tally"), "intent": "export_excel",
                    "answer": "Your Excel report is ready. Use the download button below.",
                    "downloads": [download], "data": None, "session_id": session_id}

        if local_intent == "follow_up_period":
            session = session or await get_session_state(user_id, company_name, session_id)
            try:
                selection = follow_up_selection(cleaned_message, session, DATE_AWARE_TOOLS)
            except InvalidDateRange as exc:
                return {"success": False, "source": "validation", "intent": "invalid_date", "answer": str(exc), "data": None, "session_id": session_id}
            if not selection:
                return {"success": False, "source": "validation", "intent": "follow_up",
                        "answer": "Please ask for a report first, or specify the report, entity and period for this follow-up.", "data": None, "session_id": session_id}

        elif local_intent == "follow_up_stock":
            session = session or await get_session_state(user_id, company_name, session_id)
            item = (session or {}).get("last_arguments", {}).get("item_name")
            if not item:
                return {"success": False, "source": "validation", "intent": "follow_up", "answer": "Please name the stock item first.", "data": None, "session_id": session_id}
            selection = {"tool_name": "get_stock_movement" if "movement" in cleaned_message.lower() else "get_stock_item_details",
                         "arguments": {"item_name": item, **((session or {}).get("last_period") or {})}, "error": None}

        elif local_intent == "follow_up_show_all_items":
            session = await get_session_state(user_id, company_name, session_id)
            if session and session.get("last_data") and session.get("last_tool") in ("get_profit_loss", "get_trial_balance", "get_balance_sheet"):
                tool_name = session["last_tool"]
                answer = format_tool_response(tool_name, {"success": True, "source": "tally", "data": session["last_data"]})
                return {
                    "success": True,
                    "source": "tally",
                    "intent": tool_name,
                    "answer": answer,
                    "data": session["last_data"],
                    "downloads": [session["last_export"]] if session.get("last_export") else [],
                    "session_id": session_id,
                }
            elif session and session.get("last_tool"):
                selection = {
                    "tool_name": session["last_tool"],
                    "arguments": session.get("last_arguments", {}),
                    "error": None,
                }
            else:
                return {
                    "success": False,
                    "source": None,
                    "intent": "follow_up",
                    "answer": "There is no previous financial report in this session to display items from. Please ask for a report first.",
                    "data": None,
                    "session_id": session_id,
                }

        elif local_intent == "follow_up_opening_balance":
            session = await get_session_state(user_id, company_name, session_id)
            if not session or not session.get("last_entity"):
                return {
                    "success": False, "source": "validation", "intent": "follow_up",
                    "answer": "Please specify the ledger or bank account whose opening balance you want.",
                    "data": None, "session_id": session_id,
                }
            selection = {
                "tool_name": "get_ledger_balance",
                "arguments": {
                    **(session.get("last_period") or {}),
                    "ledger_name": session["last_entity"], "balance_type": "opening",
                },
                "error": None,
            }

        elif local_intent == "follow_up_entity_transactions":
            session = await get_session_state(user_id, company_name, session_id)
            if session and session.get("last_entity"):
                selection = {
                    "tool_name": "get_stock_movement" if session.get("last_arguments", {}).get("item_name") else "get_ledger_transactions",
                    "arguments": {("item_name" if session.get("last_arguments", {}).get("item_name") else "ledger_name"): session["last_entity"], **(session.get("last_period") or {})},
                    "error": None,
                }
            else:
                return {
                    "success": False,
                    "source": None,
                    "intent": "follow_up",
                    "answer": "Please specify which account or ledger transactions you would like to view.",
                    "data": None,
                    "session_id": session_id,
                }

        elif local_intent == "follow_up_entity_balance":
            session = await get_session_state(user_id, company_name, session_id)
            if session and session.get("last_entity"):
                selection = {
                    "tool_name": "get_ledger_balance",
                    "arguments": {"ledger_name": session["last_entity"], **(session.get("last_period") or {})},
                    "error": None,
                }
            else:
                return {
                    "success": False,
                    "source": None,
                    "intent": "follow_up",
                    "answer": "Please specify which account or ledger balance you would like to view.",
                    "data": None,
                    "session_id": session_id,
                }

        elif isinstance(local_intent, dict):
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
            selection = await _cached_select_tool(
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
        try:
            resolved_range = None if local_intent in ("follow_up_period", "follow_up_stock") else resolve_date_range(cleaned_message)
        except InvalidDateRange as exc:
            return {
                "success": False, "source": "validation", "intent": "invalid_date",
                "answer": str(exc), "data": None, "session_id": session_id,
            }

        if (not resolved_range and local_intent not in ("follow_up_period", "follow_up_stock")
                and re.match(r"^(?:now|also|only|and|what\s+about|how\s+about)\b", cleaned_message, re.IGNORECASE) and session):
            for key, value in (session.get("last_period") or {}).items():
                if value and key not in arguments:
                    arguments[key] = value

        if resolved_range:
            # A single-date Balance Sheet or Trial Balance is an as-of
            # request; starting it on that day would change its balances.
            if (tool_name in {"get_trial_balance", "get_balance_sheet"}
                    and resolved_range.from_date == resolved_range.to_date):
                arguments.pop("from_date", None)
            else:
                arguments["from_date"] = resolved_range.from_date.strftime("%d-%m-%Y")

            arguments["to_date"] = (
                resolved_range.to_date.strftime(
                    "%d-%m-%Y"
                )
            )

    # Comparison queries need two separate periods,
    # so they use four date arguments.
    if tool_name == COMPARISON_TOOL:
        try:
            comparison = resolve_comparison_ranges(cleaned_message)
        except InvalidDateRange as exc:
            return {
                "success": False, "source": "validation", "intent": "invalid_date",
                "answer": str(exc), "data": None, "session_id": session_id,
            }

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

    # Gemini may select the period-trend tool directly. Keep its
    # current/previous argument names aligned with the comparison
    # resolver used by the local intent path.
    if tool_name == "get_period_trend":
        try:
            comparison = resolve_comparison_ranges(cleaned_message)
        except InvalidDateRange as exc:
            return {
                "success": False, "source": "validation", "intent": "invalid_date",
                "answer": str(exc), "data": None, "session_id": session_id,
            }

        if comparison:
            arguments["current_from_date"] = (
                comparison.first_period.from_date.strftime(
                    "%d-%m-%Y"
                )
            )
            arguments["current_to_date"] = (
                comparison.first_period.to_date.strftime(
                    "%d-%m-%Y"
                )
            )
            arguments["previous_from_date"] = (
                comparison.second_period.from_date.strftime(
                    "%d-%m-%Y"
                )
            )
            arguments["previous_to_date"] = (
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
    if tool_name != "get_company_comparison":
        explicit_companies = _extract_allowed_companies(
            cleaned_message,
            allowed_companies,
        )
        if explicit_companies:
            arguments["company_name"] = explicit_companies[0]
        elif company_name:
            arguments["company_name"] = company_name


    log_chat_event(
        request_id=request_id,
        event="tool_selected",
        intent=tool_name,
    )

    # Execute only a tool registered in our approved
    # read-only financial tool registry.
    import inspect
    sig = inspect.signature(execute_tool)
    tool_kwargs = {
        "tool_name": tool_name,
        "arguments": arguments,
        "user_id": user_id,
    }
    if "org_id" in sig.parameters:
        tool_kwargs["org_id"] = org_id
    if "force_refresh" in sig.parameters:
        tool_kwargs["force_refresh"] = force_refresh

    tool_result = await execute_tool(**tool_kwargs)

    if not tool_result.get("success"):
        try:
            await save_session_state(user_id, arguments.get("company_name") or company_name, {
                "last_tool": tool_name, "last_arguments": arguments,
                "last_period": {k: arguments.get(k) for k in ("from_date", "to_date")},
                "last_entity": next((arguments[k] for k in ("ledger_name", "party_name", "item_name") if arguments.get(k)), None),
                "last_export": None,
            }, session_id=session_id)
        except Exception:
            pass
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

    calculation_method = tool_result.get("calculation_method")
    if calculation_method == "application_aggregation":
        answer = (
            "Derived figure: worked out from Tally report data; "
            "Tally does not print this as a single total.\n\n"
            + answer
        )

    log_chat_event(
        request_id=request_id,
        event="request_completed",
        intent=tool_name,
        source=tool_result.get("source", "tally"),
    )

    data = tool_result.get("data") or {}
    effective_company = arguments.get("company_name") or company_name
    period = {key: arguments.get(key) or data.get(key) for key in ("from_date", "to_date")}
    if tool_name in DATE_AWARE_TOOLS:
        arguments.update({key: value for key, value in period.items() if value})
    download = None
    try:
        download = await save_export(user_id, org_id, effective_company, tool_name, arguments, tool_result, answer)
    except Exception:
        pass

    entity = None
    if "party_name" in arguments:
        entity = arguments["party_name"]
    elif "ledger_name" in arguments:
        entity = arguments["ledger_name"]
    elif "customer_name" in arguments:
        entity = arguments["customer_name"]
    elif "supplier_name" in arguments:
        entity = arguments["supplier_name"]
    elif "item_name" in arguments:
        entity = arguments["item_name"]

    try:
        await save_session_state(
            user_id=user_id,
            company=effective_company,
            session_id=session_id,
            state_data={
                "last_tool": tool_name,
                "last_intent": tool_name,
                # Only the three statements are re-displayed from memory
                # ("show all items"); other tools re-run, so storing their
                # full data would only waste Redis and process memory.
                "last_data": (
                    tool_result.get("data")
                    if tool_name in SESSION_REDISPLAY_TOOLS
                    else None
                ),
                "last_arguments": arguments,
                "last_entity": entity,
                "last_export": download,
                "last_period": period,
                "last_answer": answer,
            },
        )
    except Exception:
        pass

    return {
        "success": True,
        "source": tool_result.get("source", "tally"),
        "intent": tool_name,
        "answer": answer,
        "data": tool_result.get(
            "data"
        ),
        "data_origin": tool_result.get("data_origin"),
        "calculation_method": calculation_method,
        "downloads": [download] if download else [],
        "cached_at": tool_result.get("cached_at"),
        "is_stale": tool_result.get("is_stale", False),
        "session_id": session_id,
    }
