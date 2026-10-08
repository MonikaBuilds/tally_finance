import asyncio
import logging
import os

from datetime import date, datetime
from typing import Any

from app.chatbot.tool_registry import TOOL_FUNCTIONS
from app.security.permissions import can_execute_tool
from app.cache.config import cache_settings
from app.cache.keys import build_cache_key
from app.cache.manager import cache_manager

logger = logging.getLogger(__name__)

CHATBOT_TOOL_TIMEOUT = 20.0

CHATBOT_MAX_CONCURRENT_TOOLS = max(
    1,
    int(
        os.getenv(
            "CHATBOT_MAX_CONCURRENT_TOOLS",
            "8",
        )
    ),
)

CHATBOT_QUEUE_TIMEOUT = 2.0

_tool_semaphore = asyncio.Semaphore(
    CHATBOT_MAX_CONCURRENT_TOOLS
)


DATE_ARGUMENTS = {
    "from_date",
    "to_date",
    "first_from_date",
    "first_to_date",
    "second_from_date",
    "second_to_date",
    "current_from_date",
    "current_to_date",
    "previous_from_date",
    "previous_to_date",
}

# These tools summarize or combine Tally rows in application code. Keep
# this explicit so callers and the UI can distinguish those figures from
# values returned as rows in a Tally report.
APPLICATION_AGGREGATION_TOOLS = {
    "get_receivables",
    "get_payables",
    "get_aged_receivables",
    "get_aged_payables",
    "get_pending_invoices",
    "get_highest_receivable",
    "get_highest_payable",
    "get_overdue_receivables",
    "get_overdue_payables",
    "get_revenue",
    "get_expenses",
    "get_net_profit",
    "get_financial_summary",
    "get_party_outstanding_summary",
    "get_outstanding_summary",
    "get_top_receivables",
    "get_top_payables",
    "get_cash_balance",
    "get_bank_balance",
    "get_bank_transactions",
    "get_ledger_transactions",
    "get_customer_statement",
    "get_supplier_statement",
    "get_cash_transactions",
    "get_sales_by_customer",
    "get_purchases_by_supplier",
    "get_sales_by_item",
    "get_purchases_by_item",
    "get_receipt_transactions",
    "get_payment_transactions",
    "get_credit_note_transactions",
    "get_debit_note_transactions",
    "get_invoice_details",
    "get_invoice_status",
    "get_input_gst",
    "get_output_gst",
    "get_gst_summary",
    "get_stock_summary",
    "get_top_stock_items",
    "get_negative_stock_items",
    "get_tds_summary",
    "get_tds_transactions",
    "get_profitability_summary",
    "get_top_expenses",
    "get_top_customers",
    "get_top_suppliers",
    "get_period_comparison",
    "get_period_trend",
    "get_cash_flow_summary",
    "get_top_selling_items",
    "get_low_selling_items",
    "get_customer_profitability",
    "get_product_profitability",
    "get_tax_liability",
    "get_tds_receivable",
    "get_tds_payable",
    "get_financial_trends",
    "get_company_comparison",
    "get_cost_centre_analysis",
}


def _parse_date(
    value: Any,
    argument_name: str,
) -> date | None:
    if value is None:
        return None

    if isinstance(value, date):
        return value

    if not isinstance(value, str):
        raise ValueError(
            f"{argument_name} must be a date "
            "in DD-MM-YYYY format."
        )

    normalized = value.strip()
    for date_format in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(
                normalized,
                date_format,
            ).date()
        except ValueError:
            continue

    else:
        raise ValueError(
            f"{argument_name} must be a valid date "
            "in DD-MM-YYYY or YYYY-MM-DD format."
        )


def _prepare_arguments(
    arguments: dict[str, Any] | None,
) -> dict[str, Any]:
    if arguments is None:
        return {}

    if not isinstance(arguments, dict):
        raise ValueError(
            "Tool arguments must be an object."
        )

    prepared = dict(arguments)

    for argument_name in DATE_ARGUMENTS:
        if argument_name in prepared:
            prepared[argument_name] = _parse_date(
                prepared[argument_name],
                argument_name,
            )

    from_date = prepared.get(
        "from_date"
    )
    to_date = prepared.get(
        "to_date"
    )

    first_from_date = prepared.get(
        "first_from_date"
    )
    first_to_date = prepared.get(
        "first_to_date"
    )

    if (
        first_from_date is not None
        and first_to_date is not None
        and first_from_date > first_to_date
    ):
        raise ValueError(
            "first_from_date cannot be later "
            "than first_to_date."
        )

    second_from_date = prepared.get(
        "second_from_date"
    )
    second_to_date = prepared.get(
        "second_to_date"
    )

    if (
        second_from_date is not None
        and second_to_date is not None
        and second_from_date > second_to_date
    ):
        raise ValueError(
            "second_from_date cannot be later "
            "than second_to_date."
        )

    current_from_date = prepared.get("current_from_date")
    current_to_date = prepared.get("current_to_date")
    if (
        current_from_date is not None
        and current_to_date is not None
        and current_from_date > current_to_date
    ):
        raise ValueError(
            "current_from_date cannot be later than current_to_date."
        )

    previous_from_date = prepared.get("previous_from_date")
    previous_to_date = prepared.get("previous_to_date")
    if (
        previous_from_date is not None
        and previous_to_date is not None
        and previous_from_date > previous_to_date
    ):
        raise ValueError(
            "previous_from_date cannot be later than previous_to_date."
        )

    if (
        from_date is not None
        and to_date is not None
        and from_date > to_date
    ):
        raise ValueError(
            "from_date cannot be later "
            "than to_date."
        )

    company_name = prepared.get(
        "company_name"
    )

    if company_name is not None:
        if not isinstance(
            company_name,
            str,
        ):
            raise ValueError(
                "company_name must be a string."
            )

        company_name = (
            company_name.strip()
        )

        prepared["company_name"] = (
            company_name
            if company_name
            else None
        )

    return prepared


class _NonCacheableToolResult(Exception):
    def __init__(self, result: dict):
        self.result = result


async def execute_tool(
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    user_id: str | None = None,
    org_id: str = "default",
    force_refresh: bool = False,
) -> dict:
    # -------------------------------------------------
    # 1. READ-ONLY / REGISTERED TOOL CHECK
    # -------------------------------------------------
    # Only tools registered in TOOL_FUNCTIONS can run.
    # This prevents unsupported or write operations
    # such as update/delete operations from executing.
    if tool_name not in TOOL_FUNCTIONS:
        return {
            "success": False,
            "source": None,
            "message": (
                "The requested operation is not "
                "available to this read-only "
                "assistant."
            ),
            "data": None,
        }

    # -------------------------------------------------
    # 2. RBAC PERMISSION CHECK
    # -------------------------------------------------
    # Authorization happens before argument processing,
    # cache lookup, semaphore acquisition, or any Tally tool execution.
    #
    # Admin:
    #   Can access all mapped tools.
    #
    # Normal user:
    #   Must have the permission mapped to this tool.
    #
    # Missing user / unmapped tool:
    #   Access is denied (fail closed).
    if not can_execute_tool(
        user_id=user_id,
        tool_name=tool_name,
    ):
        return {
            "success": False,
            "source": "authorization",
            "message": (
                "You are not authorized to access "
                "this type of financial data."
            ),
            "data": None,
        }

    try:
        # ---------------------------------------------
        # 3. VALIDATE AND PREPARE ARGUMENTS
        # ---------------------------------------------
        prepared_arguments = (
            _prepare_arguments(
                arguments
            )
        )

        tool_function = (
            TOOL_FUNCTIONS[
                tool_name
            ]
        )

        # ---------------------------------------------
        # 4. PREPARE CACHE KEY
        # ---------------------------------------------
        company_name = prepared_arguments.get("company_name")
        cache_params = {
            k: v for k, v in prepared_arguments.items()
            if k != "company_name"
        }
        cache_key = build_cache_key(
            report_name=f"chat:{tool_name}",
            company_name=company_name,
            org_id=org_id,
            params=cache_params,
        )

        # ---------------------------------------------
        # 5. DEFINE FETCHER WITH CONCURRENCY PROTECTION
        # ---------------------------------------------
        async def _fetch_from_tally():
            try:
                await asyncio.wait_for(
                    _tool_semaphore.acquire(),
                    timeout=CHATBOT_QUEUE_TIMEOUT,
                )
            except asyncio.TimeoutError:
                raise TimeoutError("QUEUE_TIMEOUT")

            try:
                raw_result = await asyncio.wait_for(
                    tool_function(
                        **prepared_arguments
                    ),
                    timeout=CHATBOT_TOOL_TIMEOUT,
                )
            finally:
                _tool_semaphore.release()

            if not isinstance(
                raw_result,
                dict,
            ):
                raise ValueError(
                    "The financial tool returned "
                    "an invalid response."
                )

            # Never cache unsuccessful results in Redis
            if not raw_result.get("success", False):
                raise _NonCacheableToolResult(raw_result)

            raw_result.setdefault("data_origin", "tally")
            raw_result.setdefault(
                "calculation_method",
                "application_aggregation"
                if tool_name in APPLICATION_AGGREGATION_TOOLS
                else "tally_report_rows",
            )

            return raw_result

        # ---------------------------------------------
        # 6. FETCH WITH CACHING & STALE OUTAGE FALLBACK
        # ---------------------------------------------
        try:
            cache_res = await cache_manager.get_or_fetch(
                cache_key=cache_key,
                fetcher=_fetch_from_tally,
                fresh_ttl=cache_settings.get_fresh_ttl(tool_name),
                stale_retention_ttl=cache_settings.REDIS_CACHE_STALE_RETENTION_TTL,
                force_refresh=force_refresh,
                metadata={
                    "tool": tool_name,
                    "company": company_name,
                    "org_id": org_id,
                },
            )

            res_data = cache_res.data
            if isinstance(res_data, dict):
                output = dict(res_data)
                output["source"] = cache_res.source
                output["is_stale"] = cache_res.is_stale
                output["cached_at"] = cache_res.cached_at
                output.setdefault("data_origin", "tally")
                output.setdefault(
                    "calculation_method",
                    "application_aggregation"
                    if tool_name in APPLICATION_AGGREGATION_TOOLS
                    else "tally_report_rows",
                )
                return output

            return {
                "success": True,
                "source": cache_res.source,
                "data": res_data,
                "cached_at": cache_res.cached_at,
                "is_stale": cache_res.is_stale,
            }

        except _NonCacheableToolResult as exc:
            return exc.result

    except TimeoutError as exc:
        if str(exc) == "QUEUE_TIMEOUT":
            return {
                "success": False,
                "source": None,
                "message": (
                    "The chatbot is handling many "
                    "requests right now. Please try "
                    "again shortly."
                ),
                "data": None,
            }
        return {
            "success": False,
            "source": "tally",
            "message": (
                "Tally is taking too long to "
                "respond. Please try again shortly."
            ),
            "data": None,
        }

    except asyncio.TimeoutError:
        return {
            "success": False,
            "source": "tally",
            "message": (
                "Tally is taking too long to "
                "respond. Please try again shortly."
            ),
            "data": None,
        }

    except TypeError:
        return {
            "success": False,
            "source": None,
            "message": (
                "Invalid arguments were supplied "
                "for the requested financial tool."
            ),
            "data": None,
        }

    except ValueError as exc:
        return {
            "success": False,
            "source": None,
            "message": str(exc),
            "data": None,
        }

    except Exception:
        logger.exception(
            "Chatbot tool execution failed: tool=%s",
            tool_name,
        )

        # Return a safe message to the user without
        # exposing internal errors from the backend..
        return {
            "success": False,
            "source": "tally",
            "message": (
                "Unable to retrieve the requested "
                "financial data from Tally right now."
            ),
            "data": None,
        }
