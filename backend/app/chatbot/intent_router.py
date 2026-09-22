import re

from calendar import monthrange
from datetime import date


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
        party_name = customer_match.group(1).strip()

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
        party_name = supplier_match.group(1).strip()
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
            "tool_name": "get_top_customers",
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
        r"(revenue|sales|expenses?|net\s+profit|profit)\s+"
        r"(?:for\s+)?this\s+month\s+"
        r"(?:with|vs|versus)\s+"
        r"last\s+month\b",
        message,
        flags=re.IGNORECASE,
    )

    if comparison_match:
        print("LOCAL COMPARISON MATCHED:", comparison_match.group(0))
        metric_text = (
            comparison_match
            .group(1)
            .lower()
            .strip()
        )

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
            
    # Overdue invoice queries are simple and deterministic.
    # Route them locally instead of sending them to the AI model.
    if re.search(
        r"\b(overdue invoices?|overdue bills?|show overdue invoices?)\b",
        message,
        flags=re.IGNORECASE,
    ):
        return "get_overdue_invoices"
    
    # Stock item details are deterministic when the user
    # provides the product or stock item name.
    stock_details_match = re.search(
        r"\b(?:show\s+)?(?:details?\s+(?:of|for)|"
        r"stock\s+(?:item\s+)?details?\s+(?:of|for))\s+(.+?)\s*$",
        message,
        flags=re.IGNORECASE,
    )

    if stock_details_match:
        stock_item_name = stock_details_match.group(1).strip()

        if stock_item_name:
            return {
                "tool_name": "get_stock_item_details",
                "arguments": {
                    "stock_item_name": stock_item_name,
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
        ledger_name = (
            ledger_transactions_match
            .group(1)
            .strip()
        )

        if ledger_name:
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
        ledger_name = (
            ledger_statement_match
            .group(1)
            .strip()
        )

        if ledger_name:
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
        ledger_name = (
            ledger_balance_match
            .group(1)
            .strip()
        )

        if ledger_name:
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
            r"pending invoice|"
            r"pending invoices"
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

        # Net profit
        (
            r"\b("
            r"net profit|"
            r"net income"
            r")\b",
            "get_net_profit",
        ),

        # Revenue
        (
            r"\b("
            r"revenue|"
            r"sales revenue|"
            r"total sales"
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
    for pattern, tool_name in patterns:
        if re.search(
            pattern,
            text,
        ):
            return tool_name

    # No safe local match was found.
    # Gemini can decide the tool from here.
    return None