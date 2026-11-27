import re

from app.chatbot.context import is_follow_up

from calendar import monthrange
from datetime import date


_debug_logger = __import__("logging").getLogger(__name__)


def _debug_print(*parts, **_ignored) -> None:
    """Former print() diagnostics: DEBUG level only, never stdout."""
    if _debug_logger.isEnabledFor(10):
        _debug_logger.debug(" ".join(str(part) for part in parts))


# Queries containing these words usually need more context
# or a specialized tool, so Gemini can handle them.
#
# Important:
# Specific local routes such as "top 5 customers" and
# "compare revenue this month with last month" are checked
# BEFORE this list.
COMPLEX_QUERY_KEYWORDS = {
    "compare",
    "comparison",
    "versus",
    "vs",
    "overdue",
    "aging",
    "aged",
    "highest",
    "top",
    "ledger",
    "party",
}

# Words and time period expressions that must never be mistaken for ledger names.
INVALID_LEDGER_NAMES = {
    "this financial year",
    "last financial year",
    "current financial year",
    "previous financial year",
    "this fy",
    "last fy",
    "current fy",
    "previous fy",
    "this year",
    "last year",
    "current year",
    "previous year",
    "this month",
    "last month",
    "current month",
    "previous month",
    "today",
    "yesterday",
    "statement",
    "profit and loss",
    "profit and loss statement",
    "p&l",
    "balance sheet",
    "trial balance",
    "day book",
    "daybook",
    "dairy",
    "diary",
}


def _clean_ledger_name(name: str) -> str:
    if not name:
        return ""
    # Strip a trailing date range before resolving the ledger name.
    months = ("january|february|march|april|may|june|july|august|"
              "september|october|november|december")
    date_start = (
        r"(?:\d{1,2}[-/]\d{1,2}[-/]\d{4}|\d{4}-\d{2}-\d{2}|"
        r"\d{1,2}(?:st|nd|rd|th)?\s+(?:" + months + r")\b|"
        r"(?:" + months + r")\b|(?:this|last|current|previous)\s+"
        r"(?:month|quarter|year|financial\s+year|fy)\b|today\b|yesterday\b|"
        r"(?:fy|financial\s+year)\s*\d)"
    )
    name = re.split(
        r"\s+(?:from|between|on|as\s+on|as\s+of|for|in)\s+(?="
        + date_start + r")|\s+(?=(?:today|yesterday|(?:this|last|current|previous)"
        r"\s+(?:month|quarter|year|financial\s+year|fy))\b)",
        name, maxsplit=1, flags=re.IGNORECASE,
    )[0]
    # Strip instructions like 'with date, voucher type...', 'with details...', 'ledger'
    name = re.sub(
        r"\s+with\s+(?:date|voucher|amount|details|entries).*$",
        "",
        name,
        flags=re.IGNORECASE,
    )
    name = re.sub(
        r"\s+ledger$",
        "",
        name,
        flags=re.IGNORECASE,
    )
    name = name.strip()
    if name.endswith("?"):
        name = name[:-1].strip()
    if name.endswith(".") and not name.lower().endswith(("ltd.", "pvt.", "inc.", "corp.", "co.")):
        name = name[:-1].strip()
    return name


# "dairy"/"diary" alone is how many users ask for the Day Book, but the same
# word appears in party and item names ("Amul Dairy", "dairy products").
# Treat it as the Day Book only when it is the thing being asked for.
_BARE_DIARY_RE = re.compile(
    r"^(?:(?:please\s+)?(?:show|give|open|get|display|view)\s+)?"
    r"(?:me\s+)?(?:the\s+|my\s+|our\s+)?"
    r"(?:(?:today'?s|yesterday'?s|daily)\s+)?"
    r"(?:dairy|diary)"
    r"(?:\s+(?:for|of|on|from)\s+[\w\s\-/,']+)?"
    r"(?:\s+please)?[.?!]?$"
)


def _is_bare_diary_request(text: str) -> bool:
    return bool(_BARE_DIARY_RE.match(text.strip()))


def detect_local_intent(
    message: str,
) -> str | dict | None:
    """
    Detect common financial queries locally.

    Simple queries return only the tool name.

    Queries that need extra values, such as a party name,
    ranking limit, or comparison dates, return the tool
    name together with the required arguments.

    If the query is complex or unclear, return None so
    Gemini can decide which tool should be used.
    """

    text = message.lower().strip()

    if not text:
        return None

    if re.match(r"^(?:what(?:'s|\s+is)|how\s+is|tell\s+me|show(?:\s+me)?)\s+(?:the\s+)?weather\b", text):
        return "unsupported"

    if re.search(r"\b(?:export|download|save)\b.*\b(?:excel|xlsx|spreadsheet)\b", text):
        return "follow_up_export_excel"

    monthly = bool(re.search(r"\b(?:monthly|month[- ]?wise|month[- ]by[- ]month)\b|\bby\s+month\b", text))
    if monthly:
        metric = ("net_profit" if re.search(r"\b(?:profit|loss)\b", text)
                  else "expenses" if re.search(r"\b(?:expenses?|spending|costs?)\b", text)
                  else "purchases" if re.search(r"\bpurchases?\b", text)
                  else "revenue" if re.search(r"\b(?:sales?|revenue|turnover)\b", text) else None)
        if metric:
            return {"tool_name": "get_monthly_summary", "arguments": {"metric": metric}}

    if is_follow_up(message):
        return "follow_up_period"

    if re.search(r"^(?:show|what\s+is|what\s+are)\s+(?:me\s+)?its\s+(?:stock\s+)?(?:quantity|movement|movements)\b", text):
        return "follow_up_stock"

    if re.search(r"\breceipts?\s+and\s+payments?\b|\bpayments?\s+and\s+receipts?\b", text):
        return {"tool_name": "get_day_book", "arguments": {
            "voucher_types": ["Receipt", "Payment"],
        }}

    if re.search(r"^who\s+owes?\s+(?:us|me)\b", text):
        return "get_receivables"

    if re.search(r"\bwhom?\s+(?:do\s+)?(?:i|we)\s+(?:need\s+to\s+)?pay\b", text):
        return "get_payables"

    owed_party = re.search(r"\bwhat\s+(?:do\s+)?(?:we|i)\s+owe\s+(.+?)\s*$", message, re.IGNORECASE)
    if owed_party:
        return {"tool_name": "get_party_outstanding_summary", "arguments": {
            "party_name": _clean_ledger_name(owed_party.group(1)),
        }}

    if (re.search(r"\breceivables?\b", text) and re.search(r"\bpayables?\b", text)
            and not re.search(r"\b(?:compare|comparison|versus|vs)\b", text)):
        return "get_outstanding_summary"

    if re.search(r"\b(?:ageing|aging|aged)\b", text):
        if re.search(r"\b(?:receivables?|debtors?|customers?)\b", text):
            return "get_aged_receivables"
        if re.search(r"\b(?:payables?|creditors?|suppliers?)\b", text):
            return "get_aged_payables"

    if re.search(r"\boverdue\b", text):
        if re.search(r"\b(?:receivables?|debtors?|customers?)\b", text):
            return "get_overdue_receivables"
        if re.search(r"\b(?:payables?|creditors?|suppliers?)\b", text):
            return "get_overdue_payables"

    if re.search(r"\b(?:show|list|get|display)\s+(?:me\s+)?(?:all\s+)?bank\s+(?:transactions?|entries|statement)\b", text):
        return "get_bank_transactions"

    if re.search(r"\b(?:show|list|get|display)\s+(?:me\s+)?all\s+(?:transactions?|vouchers?|entries)\s+(?:from|between|on|for)\s+(?:\d|fy\b|this\b|last\b|today\b|yesterday\b)", text):
        return "get_day_book"

    for noun, tool in (("receipts?", "get_receipt_transactions"),
                       ("payments?", "get_payment_transactions"),
                       ("sales", "get_sales_transactions"),
                       ("purchases?", "get_purchase_transactions")):
        if re.search(
            r"^(?:show|list|get|display)\s+(?:me\s+)?(?:my\s+|all\s+)?"
            + noun + r"(?:\s+(?:for|from|in)\s+(?:\d|fy\b|this\b|last\b|current\b|previous\b|today\b|yesterday\b|"
            r"january\b|february\b|march\b|april\b|may\b|june\b|july\b|august\b|september\b|october\b|november\b|december\b).*)?[.?]?$",
            text,
        ):
            return tool

    # These common requests need no model selection.
    if re.fullmatch(
        r"(?:(?:please\s+)?(?:show|list|get|display)\s+(?:me\s+)?)?"
        r"(?:(?:all|the|my|our)\s+)*ledgers?(?:\s+list)?[.?!]?", text,
    ):
        return "get_ledger_list"

    if re.search(r"\bdifference\s+in\s+opening\s+balances?\b", text):
        return {"tool_name": "get_balance_sheet",
                "arguments": {"opening_difference_only": True}}

    if re.fullmatch(
        r"(?:(?:please\s+)?(?:show|get|display|what\s+is)\s+)?"
        r"(?:me\s+)?(?:(?:its|the|my|our)\s+)?opening\s+balance[.?!]?", text,
    ):
        return "follow_up_opening_balance"

    if re.search(r"\b(?:invoices?|bills?)\s+(?:are\s+)?pending\b", text):
        return "get_pending_invoices"

    opening_match = re.search(
        r"\bopening\s+balance\s+(?:of|for)\s+(.+?)\s*$", message, re.IGNORECASE,
    )
    if opening_match:
        ledger_name = _clean_ledger_name(opening_match.group(1))
        if ledger_name and ledger_name.lower() not in INVALID_LEDGER_NAMES:
            return {"tool_name": "get_ledger_balance", "arguments": {
                "ledger_name": ledger_name, "balance_type": "opening",
            }}

    # --------------------------------------------------
    # CORE FINANCIAL REPORTS (P&L, Balance Sheet, Trial Balance)
    # --------------------------------------------------
    # Core financial statements must be matched before generic
    # ledger or transaction regexes so queries like
    # "Show me the Profit and Loss statement for this financial year"
    # are never intercepted as ledger lookups.
    #
    # A comparison ("compare P&L this month vs last month") is not a request
    # for one statement, so it continues to the comparison routing below.
    is_comparison = bool(
        re.search(
            r"\b(compare|comparison|versus|vs\.?)\b",
            message,
            flags=re.IGNORECASE,
        )
    )

    if is_comparison and re.search(r"\bprofit\s*(?:and|&)\s*loss\b|\bp&l\b", text):
        return {"tool_name": "get_period_comparison", "arguments": {"metric": "net_profit"}}

    if not is_comparison and re.search(
        r"\b(profit\s+and\s+loss|profit\s*&\s*loss|\bp&l\b|p\s+and\s+l)\b",
        message,
        flags=re.IGNORECASE,
    ):
        return "get_profit_loss"

    if not is_comparison and re.search(
        r"\bbalance\s+sheet\b",
        message,
        flags=re.IGNORECASE,
    ):
        return "get_balance_sheet"

    if not is_comparison and re.search(
        r"\btrial\s+balance\b",
        message,
        flags=re.IGNORECASE,
    ):
        return "get_trial_balance"

    # Day Book / Daybook / Day book dairy / Day book diary
    if re.search(
        r"\b(day\s*book|daybook|day\s*book\s*dairy|day\s*book\s*diary|daily\s*dairy|daily\s*diary)\b",
        message,
        flags=re.IGNORECASE,
    ) or _is_bare_diary_request(text):
        return "get_day_book"

    # --------------------------------------------------
    # CONVERSATIONAL FOLLOW-UP QUERIES
    # --------------------------------------------------
    if re.search(
        r"^(?:show|list|display)\s+(?:me\s+)?(?:all\s+)?(?:\d+\s+)?items(?:\s+(?:from|in|of)\s+(?:the\s+)?report)?(?:\s+please)?[.?]?$",
        text,
    ):
        return "follow_up_show_all_items"

    if re.search(
        r"^(?:show|what\s+are|what\s+is|get)\s+(?:its|the)\s+transactions(?:\s+please)?[.?]?$",
        text,
    ):
        return "follow_up_entity_transactions"

    if re.search(
        r"^(?:what\s+is|show)\s+(?:its|the)\s+(?:closing\s+)?balance(?:\s+please)?[.?]?$",
        text,
    ):
        return "follow_up_entity_balance"

    if re.search(
        r"\b(inventory\s+valuation|stock\s+valuation)\b",
        message,
        flags=re.IGNORECASE,
    ):
        return {
            "tool_name": "get_stock_summary",
            "arguments": {
                "valuation_only": True,
            },
        }

    if re.search(
        r"\b(closing\s+stock|closing\s+inventory|stock\s+summary|inventory\s+summary|"
        r"stock\s+value|inventory\s+value)\b",
        message,
        flags=re.IGNORECASE,
    ):
        return "get_stock_summary"

    # --------------------------------------------------
    # CUSTOMER STATEMENT
    # --------------------------------------------------

    # Customer statements need the customer name.
    # Extract it locally so this common query does not
    # depend on Gemini just to identify the party.
    customer_match = re.search(
        r"\bcustomer\s+statement\s+(?:for|of)\s+(.+?)\s*$",
        message,
        flags=re.IGNORECASE,
    )

    if customer_match:
        party_name = _clean_ledger_name(customer_match.group(1))

        # Remove normal punctuation from the end
        # of the user's question.
        party_name = party_name.rstrip(" ?")

        if party_name:
            return {
                "tool_name": "get_customer_statement",
                "arguments": {
                    "party_name": party_name,
                },
            }

    # --------------------------------------------------
    # SUPPLIER STATEMENT
    # --------------------------------------------------

    # Supplier statements work in the same way.
    supplier_match = re.search(
        r"\bsupplier\s+statement\s+(?:for|of)\s+(.+?)\s*$",
        message,
        flags=re.IGNORECASE,
    )

    if supplier_match:
        party_name = _clean_ledger_name(supplier_match.group(1))
        party_name = party_name.rstrip(" ?")

        if party_name:
            return {
                "tool_name": "get_supplier_statement",
                "arguments": {
                    "party_name": party_name,
                },
            }

    # --------------------------------------------------
    # TOP EXPENSES
    # --------------------------------------------------

    # Handle ranking locally because the requested limit
    # can be safely extracted without calling Gemini.
    top_expenses_match = re.search(
        r"\btop\s+(\d+)\s+expenses?\b",
        message,
        flags=re.IGNORECASE,
    )

    if top_expenses_match:
        limit = int(
            top_expenses_match.group(1)
        )

        # Keep one chatbot response reasonably small.
        limit = max(
            1,
            min(limit, 50),
        )

        return {
            "tool_name": "get_top_expenses",
            "arguments": {
                "limit": limit,
            },
        }

    # --------------------------------------------------
    # TOP CUSTOMERS
    # --------------------------------------------------

    top_customers_match = re.search(
        r"\btop\s+(\d+)\s+customers?\b",
        message,
        flags=re.IGNORECASE,
    )

    if top_customers_match:
        limit = int(
            top_customers_match.group(1)
        )

        limit = max(
            1,
            min(limit, 50),
        )

        return {
            "tool_name": ("get_top_receivables" if re.search(r"\b(?:owes?|outstanding|receivables?)\b", text) else "get_top_customers"),
            "arguments": {
                "limit": limit,
            },
        }

    # --------------------------------------------------
    # TOP SUPPLIERS
    # --------------------------------------------------

    top_suppliers_match = re.search(
        r"\btop\s+(\d+)\s+suppliers?\b",
        message,
        flags=re.IGNORECASE,
    )

    if top_suppliers_match:
        limit = int(
            top_suppliers_match.group(1)
        )

        limit = max(
            1,
            min(limit, 50),
        )

        return {
            "tool_name": "get_top_suppliers",
            "arguments": {
                "limit": limit,
            },
        }

    # --------------------------------------------------
    # TOP STOCK ITEMS
    # --------------------------------------------------

    top_stock_match = re.search(
        r"\btop\s+(\d+)\s+(?:stock\s+items?|products?)\b",
        message,
        flags=re.IGNORECASE,
    )

    if top_stock_match:
        limit = int(
            top_stock_match.group(1)
        )

        limit = max(
            1,
            min(limit, 50),
        )

        return {
            "tool_name": "get_top_stock_items",
            "arguments": {
                "limit": limit,
            },
        }

    # --------------------------------------------------
    # MONTH-TO-MONTH COMPARISON
    # --------------------------------------------------

    # Handle clear financial comparisons locally.
    #
    # Example:
    # "Compare revenue this month with last month"
    #
    # We only route locally when the user clearly tells
    # us which metric should be compared.
    comparison_match = re.search(
        r"\bcompare\s+"
        r"(?:(revenue|sales|expenses?|net\s+profit|profit)\s+(?:for\s+)?)?"
        r"this\s+month(?:'s|s')?\s+"
        r"(?:(revenue|sales|expenses?|net\s+profit|profit)\s+)?"
        r"(?:with|vs|versus)\s+"
        r"last\s+month\b",
        message,
        flags=re.IGNORECASE,
    )

    if comparison_match:
        _debug_print("LOCAL COMPARISON MATCHED:", comparison_match.group(0))
        metric_text = (
            comparison_match
            .group(1)
            or comparison_match
            .group(2)
            or "revenue"
        )
        metric_text = metric_text.lower().strip()

        # Convert normal user wording to the metric names
        # accepted by get_period_comparison_tool().
        if metric_text == "sales":
            metric = "revenue"

        elif metric_text in {
            "expense",
            "expenses",
        }:
            metric = "expenses"

        elif metric_text in {
            "profit",
            "net profit",
        }:
            metric = "net_profit"

        else:
            metric = "revenue"

        today = date.today()

        # Current period starts on the first day
        # of this month.
        first_from_date = date(
            today.year,
            today.month,
            1,
        )

        # Do not include future dates.
        # "This month" means month start up to today.
        first_to_date = today

        # Work out the previous month.
        # January needs special handling because the
        # previous month belongs to the previous year.
        if today.month == 1:
            previous_year = (
                today.year - 1
            )
            previous_month = 12

        else:
            previous_year = today.year
            previous_month = (
                today.month - 1
            )

        second_from_date = date(
            previous_year,
            previous_month,
            1,
        )

        # Last month is already complete, so use
        # its actual final calendar day.
        second_to_date = date(
            previous_year,
            previous_month,
            monthrange(
                previous_year,
                previous_month,
            )[1],
        )

        return {
            "tool_name": "get_period_comparison",
            "arguments": {
                "metric": metric,
                "first_from_date": first_from_date,
                "first_to_date": first_to_date,
                "second_from_date": second_from_date,
                "second_to_date": second_to_date,
            },
        }

    # INVOICE DETAILS

    # Invoice detail queries need the invoice or bill reference.
    # Extract it locally so we do not need Gemini for a simple lookup.
    invoice_details_match = re.search(
        r"\b(?:show\s+)?invoice\s+details?\s+(?:for|of)\s+(.+?)\s*$",
        message,
        flags=re.IGNORECASE,
    )

    if invoice_details_match:
        invoice_number = (
            invoice_details_match
            .group(1)
            .strip()
            .rstrip(" ?")
        )

        if invoice_number:
            return {
                "tool_name": "get_invoice_details",
                "arguments": {
                    "invoice_number": invoice_number,
                },
            }
            
    # --------------------------------------------------
    # INVOICE STATUS
    # --------------------------------------------------

    # Invoice status only needs the invoice or bill reference.
    # Extract it locally so a simple status check does not
    # depend on Gemini.
    invoice_status_match = re.search(
        r"\b(?:show\s+)?invoice\s+status\s+(?:for|of)\s+(.+?)\s*$",
        message,
        flags=re.IGNORECASE,
    )

    if invoice_status_match:
        invoice_number = (
            invoice_status_match
            .group(1)
            .strip()
            .rstrip(" ?")
        )

        if invoice_number:
            return {
                "tool_name": "get_invoice_status",
                "arguments": {
                    "invoice_number": invoice_number,
                },
            }

    invoice_party_match = re.search(
        r"\b(?:find|search|list|show)?\s*(?:all\s+)?"
        r"(?:sales\s+)?invoices?\s+(?:for|of)\s+(.+?)\s*$",
        message,
        flags=re.IGNORECASE,
    )
    if invoice_party_match:
        party_name = invoice_party_match.group(1).strip().rstrip(" ?")
        if party_name:
            return {
                "tool_name": "get_invoice_details",
                "arguments": {"party_name": party_name},
            }

    invoice_amount_match = re.search(
        r"\b(?:invoices?|bills?)\s+(?:with\s+)?(?:amount|value|of|for)\s+"
        r"(?:₹|rs\.?\s*)?([\d,]+(?:\.\d{1,2})?)\b",
        message,
        flags=re.IGNORECASE,
    )
    if invoice_amount_match:
        amount_text = invoice_amount_match.group(1).replace(",", "")
        return {
            "tool_name": "get_invoice_details",
            "arguments": {"amount": float(amount_text)},
        }

    if re.search(
        r"\b(paid\s+invoices?|partially\s+paid\s+invoices?|"
        r"unpaid\s+invoices?|invoice\s+search)\b",
        message,
        flags=re.IGNORECASE,
    ):
        requested_status = None
        if re.search(r"\bpartially\s+paid\b", message, re.IGNORECASE):
            requested_status = "partially paid"
        elif re.search(r"\bpaid\b", message, re.IGNORECASE):
            requested_status = "paid"
        elif re.search(r"\bunpaid\b", message, re.IGNORECASE):
            requested_status = "unpaid"
        return {
            "tool_name": "get_invoice_details",
            "arguments": {"status": requested_status},
        }
            
    # Overdue invoice queries are simple and deterministic.
    # Route them locally instead of sending them to the AI model.
    if re.search(
        r"\b(overdue invoices?|overdue bills?|show overdue invoices?)\b",
        message,
        flags=re.IGNORECASE,
    ):
        return "get_overdue_invoices"
    
    # Voucher families must win over generic ledger and item-detail wording.
    voucher_family = re.search(
        r"\b(journal|contra)\s+(?:entries|vouchers?|transactions?)\b",
        message, re.IGNORECASE,
    )
    if voucher_family:
        return {"tool_name": "get_day_book", "arguments": {
            "voucher_type": voucher_family.group(1).title(),
        }}

    for family, tool in (("sales?", "get_sales_transactions"),
                         ("purchases?", "get_purchase_transactions")):
        if re.search(
            r"\b(?:" + family + r")\s+(?:entries|vouchers?|transactions?)\b|"
            r"\b(?:list|show)\s+(?:all|every)\s+(?:" + family + r")(?!\s+by)\b",
            message, re.IGNORECASE,
        ):
            return tool

    # Stock item details are deterministic when the user
    # explicitly provides the product or stock item name.
    stock_details_match = re.search(
        r"\b(?:show\s+)?(?:stock\s+(?:item\s+)?details?\s+(?:of|for)|"
        r"item\s+details?\s+(?:of|for)|"
        r"product\s+details?\s+(?:of|for))\s+(.+?)\s*$",
        message,
        flags=re.IGNORECASE,
    )

    if stock_details_match:
        item_name = _clean_ledger_name(stock_details_match.group(1))

        if item_name and item_name.lower() not in INVALID_LEDGER_NAMES:
            return {
                "tool_name": "get_stock_item_details",
                "arguments": {
                    "item_name": item_name,
                },
            }

    # General ledger / account / bank details query.
    # Example:
    # "Show me the complete details of HDFC Bank"
    # "Show details of Office Rent"
    ledger_details_match = re.search(
        r"\b(?:show\s+(?:me\s+)?)?(?:complete\s+)?(?:details?\s+(?:of|for)|"
        r"(?:ledger|account|bank)\s+details?\s+(?:of|for))\s+(.+?)\??\s*$",
        message,
        flags=re.IGNORECASE,
    )

    if ledger_details_match:
        target_name = _clean_ledger_name(ledger_details_match.group(1))
        if target_name and target_name.lower() not in INVALID_LEDGER_NAMES:
            return {
                "tool_name": "get_ledger_report",
                "arguments": {
                    "ledger_name": target_name,
                },
            }

    # Explicit voucher / transaction listing
    # Example:
    # "List the 10 vouchers in the Eagle Paradise Pvt. Ltd. ledger"
    # "Show the voucher-wise entries of Eagle Paradise Pvt. Ltd. with date, voucher type, voucher number and amount"
    # "Show all transactions of Eagle Paradise Pvt. Ltd."
    voucher_entries_match = re.search(
        r"\b(?:show|list|get|display)\s+(?:the\s+)?(?:\d+\s+)?(?:all\s+)?(?:voucher-wise\s+entries|vouchers?|entries|transactions?|statement)\s+"
        r"(?:in|of|for)\s+(?:the\s+)?(.+?)\s*$",
        message,
        flags=re.IGNORECASE,
    )

    if voucher_entries_match:
        ledger_name = _clean_ledger_name(voucher_entries_match.group(1))
        if ledger_name and ledger_name.lower() not in INVALID_LEDGER_NAMES:
            return {
                "tool_name": "get_ledger_transactions",
                "arguments": {
                    "ledger_name": ledger_name,
                },
            }

    # Generic ledger transaction queries.
    # Example:
    # "Show transactions of Office Rent Exp"
    # "Show HDFC Bank ledger transactions last month"
    ledger_transactions_match = re.search(
        r"\b(?:show\s+)?"
        r"(?:transactions?|entries|statement)\s+"
        r"(?:of|for)\s+"
        r"(.+?)"
        r"(?:\s+(?:today|this\s+month|last\s+month|"
        r"this\s+financial\s+year|last\s+financial\s+year))?"
        r"\s*$",
        message,
        flags=re.IGNORECASE,
    )

    if ledger_transactions_match:
        ledger_name = _clean_ledger_name(ledger_transactions_match.group(1))

        if ledger_name and ledger_name.lower() not in INVALID_LEDGER_NAMES:
            return {
                "tool_name": "get_ledger_transactions",
                "arguments": {
                    "ledger_name": ledger_name,
                },
            }

    # Also understand wording where the user says
    # "ledger statement" after the ledger name.
    ledger_statement_match = re.search(
        r"\b(?:show\s+)?"
        r"(.+?)\s+"
        r"(?:ledger\s+statement|ledger\s+transactions?)"
        r"(?:\s+(?:"
        r"today|"
        r"this\s+month|"
        r"last\s+month|"
        r"this\s+financial\s+year|"
        r"last\s+financial\s+year|"
        r"from\s+.+?\s+to\s+.+?"
        r"))?"
        r"\s*$",
        message,
        flags=re.IGNORECASE,
    )

    if ledger_statement_match:
        ledger_name = _clean_ledger_name(ledger_statement_match.group(1))

        if ledger_name and ledger_name.lower() not in INVALID_LEDGER_NAMES:
            return {
                "tool_name": "get_ledger_transactions",
                "arguments": {
                    "ledger_name": ledger_name,
                },
            }

    # Generic balance queries for any ledger.
    # Example:
    # "What is the balance of HDFC Bank?"
    # "Show balance of Office Rent Exp"
    ledger_balance_match = re.search(
        r"\b(?:what\s+is\s+the\s+|show\s+|current\s+)?"
        r"(?:current\s+)?balance\s+"
        r"(?:of|for)\s+"
        r"(.+?)\??\s*$",
        message,
        flags=re.IGNORECASE,
    )

    if ledger_balance_match:
        ledger_name = _clean_ledger_name(ledger_balance_match.group(1))

        if ledger_name and ledger_name.lower() not in INVALID_LEDGER_NAMES:
            return {
                "tool_name": "get_ledger_balance",
                "arguments": {
                    "ledger_name": ledger_name,
                },
            }
            
    # Customer-wise sales
    if re.search(
        r"\b("
        r"sales\s+by\s+customer|"
        r"customer[-\s]?wise\s+sales|"
        r"customer\s+sales"
        r")\b",
        message,
        flags=re.IGNORECASE,
    ):
        return "get_sales_by_customer"


    # Supplier-wise purchases
    if re.search(
        r"\b("
        r"purchases?\s+by\s+supplier|"
        r"supplier[-\s]?wise\s+purchases?|"
        r"supplier\s+purchases?"
        r")\b",
        message,
        flags=re.IGNORECASE,
    ):
        return "get_purchases_by_supplier"
    
    # Item-wise sales
    if re.search(
        r"\b("
        r"sales\s+by\s+item|"
        r"item[-\s]?wise\s+sales|"
        r"product[-\s]?wise\s+sales|"
        r"sales\s+by\s+product"
        r")\b",
        message,
        flags=re.IGNORECASE,
    ):
        return "get_sales_by_item"


    # Item-wise purchases
    if re.search(
        r"\b("
        r"purchases?\s+by\s+item|"
        r"item[-\s]?wise\s+purchases?|"
        r"product[-\s]?wise\s+purchases?|"
        r"purchases?\s+by\s+product"
        r")\b",
        message,
        flags=re.IGNORECASE,
    ):
        return "get_purchases_by_item"
    
    # Top-selling products/items
    top_selling_match = re.search(
        r"\b(?:top|highest|best)[-\s]?"
        r"(?:selling\s+)?"
        r"(?:items?|products?)"
        r"(?:\s+(\d+))?\b",
        message,
        flags=re.IGNORECASE,
    )

    if top_selling_match:
        limit = int(
            top_selling_match.group(1)
            or 5
        )

        return {
            "tool_name": "get_top_selling_items",
            "arguments": {
                "limit": limit,
            },
        }


    # Low-selling products/items
    low_selling_match = re.search(
        r"\b(?:low|lowest|least|slow)[-\s]?"
        r"(?:selling\s+)?"
        r"(?:items?|products?)"
        r"(?:\s+(\d+))?\b",
        message,
        flags=re.IGNORECASE,
    )

    if low_selling_match:
        limit = int(
            low_selling_match.group(1)
            or 5
        )

        return {
            "tool_name": "get_low_selling_items",
            "arguments": {
                "limit": limit,
            },
        }
        
    movement_match = re.search(r"\b(?:stock|inventory|item)\s+movement\s+(?:of|for)\s+(.+)$", message, re.IGNORECASE)
    if movement_match:
        item_name = _clean_ledger_name(movement_match.group(1))
        if item_name and item_name.lower() not in INVALID_LEDGER_NAMES:
            return {"tool_name": "get_stock_movement", "arguments": {"item_name": item_name}}

    # Stock movement
    if re.search(
        r"\b("
        r"stock\s+movement|"
        r"inventory\s+movement|"
        r"item\s+movement"
        r")\b",
        message,
        flags=re.IGNORECASE,
    ):
        return "get_stock_movement"
    
    if re.search(
        r"\b("
        r"customer\s+profitability|"
        r"profitability\s+by\s+customer|"
        r"customer\s+performance|"
        r"customer\s+sales\s+contribution"
        r")\b",
        message,
        flags=re.IGNORECASE,
    ):
        return "get_customer_profitability"
    
    if re.search(
        r"\b("
        r"product\s+profitability|"
        r"profitability\s+by\s+product|"
        r"item\s+profitability|"
        r"profitability\s+by\s+item|"
        r"product\s+performance|"
        r"item\s+performance|"
        r"product\s+sales\s+contribution"
        r")\b",
        message,
        flags=re.IGNORECASE,
    ):
        return "get_product_profitability"
    
    if re.search(
        r"\b("
        r"tax\s+liability|"
        r"tax\s+overview|"
        r"gst\s+and\s+tds|"
        r"gst\s+tds\s+summary|"
        r"combined\s+tax|"
        r"total\s+tax\s+liability"
        r")\b",
        message,
        flags=re.IGNORECASE,
    ):
        return "get_tax_liability"
    
    if re.search(
        r"\b("
        r"tds\s+receivable|"
        r"tds\s+recoverable|"
        r"tds\s+to\s+receive|"
        r"tds\s+receivable\s+balance"
        r")\b",
        message,
        flags=re.IGNORECASE,
    ):
        return "get_tds_receivable"

    if re.search(
        r"\b("
        r"tds\s+payable|"
        r"tds\s+payable\s+balance"
        r")\b",
        message,
        flags=re.IGNORECASE,
    ):
        return "get_tds_payable"

    if re.search(
        r"\b("
        r"financial\s+trend|"
        r"financial\s+trends|"
        r"monthly\s+financial\s+trend|"
        r"monthly\s+financial\s+trends|"
        r"revenue\s+trend|"
        r"expense\s+trend|"
        r"profit\s+trend|"
        r"monthly\s+performance"
        r")\b",
        message,
        flags=re.IGNORECASE,
    ):
        return "get_financial_trends"
    
    # --------------------------------------------------
    # COMPANY COMPARISON
    # --------------------------------------------------

    # Route company-to-company financial comparisons
    # to the existing comparison tool.
    #
    # Examples:
    # "Compare ABC Pvt Ltd and XYZ Pvt Ltd"
    # "Compare revenue of ABC Pvt Ltd and XYZ Pvt Ltd"
    # "Compare profit between ABC Pvt Ltd and XYZ Pvt Ltd"

    if re.search(
        r"\b("
        r"company\s+comparison|"
        r"compare\s+companies|"
        r"compare\s+company|"
        r"branch\s+comparison|"
        r"compare\s+branches|"
        r"compare\s+(?:revenue|sales|expenses?|profit|net\s+profit)\s+"
        r"(?:of|between)\s+.+\s+(?:and|vs|versus)\s+.+"
        r")\b",
        message,
        flags=re.IGNORECASE,
    ):
        return "get_company_comparison"
    
    if re.search(
        r"\b("
        r"cost\s+centre|"
        r"cost\s+center|"
        r"cost\s+centre\s+analysis|"
        r"cost\s+center\s+analysis|"
        r"cost\s+centre\s+allocation|"
        r"cost\s+center\s+allocation|"
        r"department\s+wise\s+allocation|"
        r"department-wise\s+allocation"
        r")\b",
        message,
        flags=re.IGNORECASE,
    ):
        return "get_cost_centre_analysis"
    
    if re.search(
        r"\b("
        r"customer\s+statement|"
        r"supplier\s+statement|"
        r"party\s+statement|"
        r"account\s+statement|"
        r"ledger\s+statement|"
        r"customer\s+ledger|"
        r"supplier\s+ledger"
        r")\b",
        message,
        flags=re.IGNORECASE,
    ):
        return "get_party_statement"
    
    if re.search(
        r"\b("
        r"invoice\s+status|"
        r"bill\s+status|"
        r"invoice\s+outstanding|"
        r"bill\s+outstanding|"
        r"invoice\s+pending|"
        r"bill\s+pending|"
        r"invoice\s+overdue|"
        r"bill\s+overdue"
        r")\b",
        message,
        flags=re.IGNORECASE,
    ):
        return "get_invoice_status"
    
    # --------------------------------------------------
    # COMPLEX QUERY FALLBACK
    # --------------------------------------------------

    # If none of the safe local routes above matched,
    # queries containing these words can go to Gemini.
    for keyword in COMPLEX_QUERY_KEYWORDS:
        # Overdue invoices need the outstanding invoice data.
        # Route this directly so a simple query does not need the AI model.
        if re.search(
            r"\b(overdue invoices?|overdue bills?|show overdue invoices?)\b",
            message,
            flags=re.IGNORECASE,
        ):
            return "get_overdue_invoices"

    # --------------------------------------------------
    # SIMPLE LOCAL INTENTS
    # --------------------------------------------------

    # Keep specific patterns before broad patterns.
    # This prevents a general word from selecting
    # the wrong financial tool.
    patterns = [

        # Financial summary
        (
            r"\b("
            r"financial summary|"
            r"finance summary|"
            r"overall financial summary|"
            r"complete financial summary"
            r")\b",
            "get_financial_summary",
        ),

        # Pending invoices
        (
            r"\b("
            r"pending invoices?|"
            r"pending bills?"
            r")\b",
            "get_pending_invoices",
        ),

        # Trial Balance
        (
            r"\btrial balance\b",
            "get_trial_balance",
        ),

        # Balance Sheet
        (
            r"\bbalance sheet\b",
            "get_balance_sheet",
        ),

        # Profit and Loss
        (
            r"\b("
            r"profit and loss|"
            r"profit & loss|"
            r"p&l"
            r")\b",
            "get_profit_loss",
        ),

        # Bank transactions
        (
            r"\b("
            r"bank transactions?|"
            r"bank statement|"
            r"bank entries"
            r")\b",
            "get_bank_transactions",
        ),

        # Cash transactions
        (
            r"\b("
            r"cash transactions?|"
            r"cash entries|"
            r"cash movement"
            r")\b",
            "get_cash_transactions",
        ),

        # Sales transactions
        #
        # Plain "sales" is intentionally not included.
        # A user asking for sales may mean total revenue.
        (
            r"\b("
            r"sales transactions?|"
            r"sales entries|"
            r"sales activity"
            r")\b",
            "get_sales_transactions",
        ),

        # Purchase transactions
        (
            r"\b("
            r"purchase transactions?|"
            r"purchase entries|"
            r"purchase activity"
            r")\b",
            "get_purchase_transactions",
        ),

        # Receipt transactions
        (
            r"\b("
            r"receipt transactions?|"
            r"receipt entries|"
            r"receipt vouchers?|"
            r"customer receipts?|"
            r"money received"
            r")\b",
            "get_receipt_transactions",
        ),

        # Payment transactions
        (
            r"\b("
            r"payment transactions?|"
            r"payment entries|"
            r"payment vouchers?|"
            r"supplier payments?|"
            r"payments made|"
            r"money paid|"
            r"outgoing payments?"
            r")\b",
            "get_payment_transactions",
        ),

        # Credit Note transactions
        (
            r"\b("
            r"credit note transactions?|"
            r"credit notes?|"
            r"credit note entries|"
            r"sales returns?|"
            r"customer adjustments?"
            r")\b",
            "get_credit_note_transactions",
        ),

        # Debit Note transactions
        (
            r"\b("
            r"debit note transactions?|"
            r"debit notes?|"
            r"debit note entries|"
            r"purchase returns?|"
            r"supplier adjustments?"
            r")\b",
            "get_debit_note_transactions",
        ),

        # Input GST
        (
            r"\b("
            r"input gst|"
            r"input cgst|"
            r"input sgst|"
            r"input igst|"
            r"input tax|"
            r"input tax credit|"
            r"itc|"
            r"gst paid on purchases"
            r")\b",
            "get_input_gst",
        ),

        # Output GST
        (
            r"\b("
            r"output gst|"
            r"output cgst|"
            r"output sgst|"
            r"output igst|"
            r"output tax|"
            r"gst collected on sales"
            r")\b",
            "get_output_gst",
        ),

        # TDS summary
        (
            r"\b("
            r"tds summary|"
            r"tds balance|"
            r"tds details|"
            r"tax deducted at source"
            r")\b",
            "get_tds_summary",
        ),

        # TDS transactions
        (
            r"\b("
            r"tds transactions?|"
            r"tds entries|"
            r"tds deductions"
            r")\b",
            "get_tds_transactions",
        ),

        # GST summary
        (
            r"\b("
            r"gst summary|"
            r"gst position|"
            r"net gst|"
            r"gst payable|"
            r"gst liability"
            r")\b",
            "get_gst_summary",
        ),

        # Cash flow
        (
            r"\b("
            r"cash flow|"
            r"cash flow summary|"
            r"cash inflow|"
            r"cash outflow|"
            r"net cash flow"
            r")\b",
            "get_cash_flow_summary",
        ),

        # Stock summary
        (
            r"\b("
            r"stock summary|"
            r"inventory summary|"
            r"current inventory|"
            r"current stock|"
            r"stock value"
            r")\b",
            "get_stock_summary",
        ),

        # Profitability
        (
            r"\b("
            r"profitability|"
            r"profitability summary|"
            r"profit margin|"
            r"business profitability|"
            r"how profitable"
            r")\b",
            "get_profitability_summary",
        ),

        # Stock item list
        (
            r"\b("
            r"show(?: me)? stock items?|"
            r"list(?: all)? stock items?|"
            r"show(?: me)? inventory items?|"
            r"list(?: all)? inventory items?|"
            r"show(?: me)? products?|"
            r"list(?: all)? products?|"
            r"available stock items?"
            r")\b",
            "get_stock_items",
        ),

        # Negative stock
        (
            r"\b("
            r"negative stock|"
            r"negative inventory|"
            r"stock below zero|"
            r"items below zero"
            r")\b",
            "get_negative_stock_items",
        ),

        # Cash balance
        (
            r"\b("
            r"cash balance|"
            r"cash in hand"
            r")\b",
            "get_cash_balance",
        ),

        # Bank balance
        (
            r"\bbank balance\b",
            "get_bank_balance",
        ),

        # Net profit / earnings
        (
            r"\b("
            r"net profit|"
            r"net income|"
            r"how much did (?:i|we) (?:earn|make)|"
            r"how much (?:i|we) earned|"
            r"total earnings|"
            r"my earnings|"
            r"our earnings"
            r")\b",
            "get_net_profit",
        ),

        # Revenue
        (
            r"\b("
            r"revenue|"
            r"sales revenue|"
            r"total sales|"
            r"my revenue|"
            r"our revenue"
            r")\b",
            "get_revenue",
        ),

        # Expenses
        (
            r"\b("
            r"expense|"
            r"expenses|"
            r"total expenses"
            r")\b",
            "get_expenses",
        ),

        # Receivables
        (
            r"\b("
            r"receivable|"
            r"receivables|"
            r"customer outstanding"
            r")\b",
            "get_receivables",
        ),

        # Payables
        # Payables
        (
            r"\b("
            r"payable|"
            r"payables|"
            r"supplier outstanding|"
            r"need to pay|"
            r"amount to pay|"
            r"how much.*pay|"
            r"owe suppliers|"
            r"owe supplier|"
            r"we owe"
            r")\b",
            "get_payables",
        ),
    ]

    # Return the first strong local match.
    statement_tools = {
        "get_profit_loss",
        "get_balance_sheet",
        "get_trial_balance",
    }

    for pattern, tool_name in patterns:
        if is_comparison and tool_name in statement_tools:
            # "Compare P&L ..." is a comparison, not one statement.
            continue

        if re.search(
            pattern,
            text,
        ):
            return tool_name

    # No safe local match was found.
    # Gemini can decide the tool from here.
    return None
