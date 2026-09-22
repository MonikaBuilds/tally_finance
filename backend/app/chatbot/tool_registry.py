from app.chatbot.tools import get_ledger_transactions_tool, get_low_selling_items_tool, get_overdue_invoices_tool, get_top_selling_items_tool
from app.chatbot.tools import (
    get_cash_flow_summary_tool,
    get_receivables_tool,
    get_period_comparison_tool,
    get_payables_tool,
    get_aged_receivables_tool,
    get_aged_payables_tool,
    get_pending_invoices_tool,
    get_highest_receivable_tool,
    get_highest_payable_tool,
    get_overdue_receivables_tool,
    get_overdue_payables_tool,
    get_revenue_tool,
    get_expenses_tool,
    get_net_profit_tool,
    get_profit_loss_tool,
    get_tds_transactions_tool,
    get_trial_balance_tool,
    get_balance_sheet_tool,
    get_party_outstanding_summary_tool,
    get_outstanding_summary_tool,
    get_top_receivables_tool,
    get_top_payables_tool,
    get_financial_summary_tool,
    get_ledger_report_tool,
    get_cash_balance_tool,
    get_bank_balance_tool,
    get_bank_transactions_tool,
    get_cash_transactions_tool,
    get_sales_transactions_tool,
    get_purchase_transactions_tool,
    get_receipt_transactions_tool,
    get_payment_transactions_tool,
    get_credit_note_transactions_tool,
    get_debit_note_transactions_tool,
    get_invoice_details_tool,
    get_invoice_status_tool,
    get_customer_statement_tool,
    get_supplier_statement_tool,
    get_input_gst_tool,
    get_output_gst_tool,
    get_gst_summary_tool,
    get_stock_items_tool,
    get_stock_summary_tool,
    get_stock_item_details_tool,
    get_top_stock_items_tool,
    get_negative_stock_items_tool,
    
    get_tds_summary_tool,
    get_tds_transactions_tool,
    get_profitability_summary_tool,
    get_top_expenses_tool,
    get_top_customers_tool,
    get_top_suppliers_tool,
    get_period_trend_tool,
    get_cash_flow_summary_tool,
    
    get_sales_by_customer_tool,
    get_purchases_by_supplier_tool,
    get_sales_by_item_tool,
    get_purchases_by_item_tool,
    get_stock_movement_tool,
    
    get_ledger_balance_tool,
    get_ledger_transactions_tool,
    get_low_selling_items_tool,
    get_overdue_invoices_tool,
    get_top_selling_items_tool,
    
    get_customer_profitability_tool,
    get_product_profitability_tool,
    get_tax_liability_tool,
    
    get_tds_receivable_tool,
    get_tds_payable_tool,
    get_financial_trends_tool,
    get_company_comparison_tool,
    get_cost_centre_analysis_tool,
    
    get_party_statement_tool,
    get_invoice_status_tool,
    get_bank_transactions_tool,
)


TOOL_FUNCTIONS = {
    "get_receivables": get_receivables_tool,
    "get_period_comparison": get_period_comparison_tool,
    "get_payables": get_payables_tool,
    "get_aged_receivables": get_aged_receivables_tool,
    "get_aged_payables": get_aged_payables_tool,
    "get_pending_invoices": get_pending_invoices_tool,
    "get_highest_receivable": get_highest_receivable_tool,
    "get_highest_payable": get_highest_payable_tool,
    "get_overdue_receivables": get_overdue_receivables_tool,
    "get_overdue_payables": get_overdue_payables_tool,
    "get_revenue": get_revenue_tool,
    "get_expenses": get_expenses_tool,
    "get_net_profit": get_net_profit_tool,
    "get_profit_loss": get_profit_loss_tool,
    "get_trial_balance": get_trial_balance_tool,
    "get_balance_sheet": get_balance_sheet_tool,
    "get_party_outstanding_summary": (
        get_party_outstanding_summary_tool
    ),
    "get_outstanding_summary": (
        get_outstanding_summary_tool
    ),
    "get_top_receivables": get_top_receivables_tool,
    "get_top_payables": get_top_payables_tool,
    "get_financial_summary": get_financial_summary_tool,
    "get_ledger_report": get_ledger_report_tool,
    "get_cash_balance": get_cash_balance_tool,
    "get_bank_balance": get_bank_balance_tool,
    "get_bank_transactions": get_bank_transactions_tool,
    "get_cash_transactions": get_cash_transactions_tool,
    "get_sales_transactions": get_sales_transactions_tool,
    "get_purchase_transactions": get_purchase_transactions_tool,
    "get_receipt_transactions": get_receipt_transactions_tool,
    "get_payment_transactions": get_payment_transactions_tool,
    "get_credit_note_transactions": get_credit_note_transactions_tool,
    "get_debit_note_transactions": get_debit_note_transactions_tool,
    "get_invoice_details": get_invoice_details_tool,
    "get_invoice_status": get_invoice_status_tool,
    "get_customer_statement": get_customer_statement_tool,
    "get_supplier_statement": get_supplier_statement_tool,
    # GST tools are read-only and retrieve tax information from Tally.
    "get_input_gst": get_input_gst_tool,
    "get_output_gst": get_output_gst_tool,
    "get_gst_summary": get_gst_summary_tool,
    "get_stock_items": get_stock_items_tool,
    "get_stock_summary": get_stock_summary_tool,
    "get_stock_item_details": get_stock_item_details_tool,
    "get_top_stock_items": get_top_stock_items_tool,
    "get_negative_stock_items": get_negative_stock_items_tool,
    "get_tds_summary": get_tds_summary_tool,
    "get_tds_transactions": get_tds_transactions_tool,
    "get_profitability_summary": get_profitability_summary_tool,
    "get_top_expenses": get_top_expenses_tool,
    "get_top_customers": get_top_customers_tool,
    "get_top_suppliers": get_top_suppliers_tool,
    "get_period_trend": get_period_trend_tool,
    # Reads cash and bank movements and calculates the overall cash flow.
    "get_cash_flow_summary": get_cash_flow_summary_tool,
    "get_overdue_invoices": get_overdue_invoices_tool,
    
    "get_ledger_balance": get_ledger_balance_tool,
    "get_ledger_transactions": get_ledger_transactions_tool,
    
    "get_sales_by_customer": get_sales_by_customer_tool,
    "get_purchases_by_supplier": get_purchases_by_supplier_tool,
    
    "get_sales_by_item": get_sales_by_item_tool,
    "get_purchases_by_item": get_purchases_by_item_tool,
    
    "get_top_selling_items": get_top_selling_items_tool,
    "get_low_selling_items": get_low_selling_items_tool,
    "get_stock_movement": get_stock_movement_tool,
    
    "get_customer_profitability": get_customer_profitability_tool,
    "get_product_profitability": get_product_profitability_tool,
    "get_tax_liability": get_tax_liability_tool,
    
    "get_tds_receivable": get_tds_receivable_tool,
    "get_tds_payable": get_tds_payable_tool,
    "get_financial_trends": get_financial_trends_tool,
    "get_company_comparison": get_company_comparison_tool,
    "get_cost_centre_analysis": get_cost_centre_analysis_tool,
    "get_party_statement": get_party_statement_tool,
    "get_invoice_status": get_invoice_status_tool,
    "get_bank_transactions": get_bank_transactions_tool
}


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "name": "get_receivables",
        "description": (
            "Get current outstanding receivables from Tally. "
            "Use when the user asks how much customers owe the company."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "company_name": {
                    "type": "string",
                    "description": "Optional Tally company name."
                }
            }
        }
    },
    
    
    # get_financial_summary
    
    {
        "name": "get_financial_summary",
        "description": (
            "Get an overall financial summary from Tally including "
            "revenue, expenses, net profit or loss, receivables, "
            "payables, and pending invoices. Use this when the user "
            "asks for an overall financial summary, financial overview, "
            "business performance summary, or general financial position."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "from_date": {
                    "type": "string",
                    "description": (
                        "Optional start date in DD-MM-YYYY format."
                    )
                },
                "to_date": {
                    "type": "string",
                    "description": (
                        "Optional end date in DD-MM-YYYY format."
                    )
                },
                "company_name": {
                    "type": "string",
                    "description": (
                        "Optional Tally company name."
                    )
                }
            }
        }
    },
    
    # get_payables
    
    {
        "type": "function",
        "name": "get_payables",
        "description": (
            "Get current outstanding payables from Tally. "
            "Use when the user asks how much the company owes suppliers."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "company_name": {
                    "type": "string",
                    "description": "Optional Tally company name."
                }
            }
        }
    },
    
    # get_aged_receivables
    
    {
        "type": "function",
        "name": "get_pending_invoices",
        "description": (
            "Get all currently pending receivable and payable invoices "
            "from Tally."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "company_name": {
                    "type": "string",
                    "description": "Optional Tally company name."
                }
            }
        }
    },
    
    # get_aged_receivables
    
    {
        "type": "function",
        "name": "get_highest_receivable",
        "description": (
            "Find the largest outstanding receivable using actual Tally data."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "company_name": {
                    "type": "string",
                    "description": "Optional Tally company name."
                }
            }
        }
    },
    
    # get_highest_payable
    
    {
        "type": "function",
        "name": "get_highest_payable",
        "description": (
            "Find the largest outstanding payable using actual Tally data."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "company_name": {
                    "type": "string",
                    "description": "Optional Tally company name."
                }
            }
        }
    },
    
    # get_overdue_receivables
    
    {
        "type": "function",
        "name": "get_overdue_receivables",
        "description": (
            "Get outstanding receivables whose due date has passed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "company_name": {
                    "type": "string",
                    "description": "Optional Tally company name."
                }
            }
        }
    },
    
    # get_overdue_payables
    
    {
        "type": "function",
        "name": "get_overdue_payables",
        "description": (
            "Get outstanding payables whose due date has passed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "company_name": {
                    "type": "string",
                    "description": "Optional Tally company name."
                }
            }
        }
    },
    
    # get_revenue
    
    {
        "type": "function",
        "name": "get_revenue",
        "description": (
            "Get revenue from the Tally Profit and Loss report. "
            "Use an optional date range if the user provides one."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "company_name": {
                    "type": "string",
                    "description": "Optional Tally company name."
                },
                "from_date": {
                    "type": "string",
                    "description": (
                        "Optional start date in DD-MM-YYYY format."
                    )
                },
                "to_date": {
                    "type": "string",
                    "description": (
                        "Optional end date in DD-MM-YYYY format."
                    )
                }
            }
        }
    },
    
    # get_expenses
    
    {
        "type": "function",
        "name": "get_expenses",
        "description": (
            "Get total expenses from Tally for an optional date range."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "company_name": {
                    "type": "string",
                    "description": "Optional Tally company name."
                },
                "from_date": {
                    "type": "string",
                    "description": (
                        "Optional start date in DD-MM-YYYY format."
                    )
                },
                "to_date": {
                    "type": "string",
                    "description": (
                        "Optional end date in DD-MM-YYYY format."
                    )
                }
            }
        }
    },
    
    # get_net_profit
    
    
    {
        "type": "function",
        "name": "get_net_profit",
        "description": (
            "Get net profit or net loss from Tally "
            "for an optional date range."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "company_name": {
                    "type": "string",
                    "description": "Optional Tally company name."
                },
                "from_date": {
                    "type": "string",
                    "description": (
                        "Optional start date in DD-MM-YYYY format."
                    )
                },
                "to_date": {
                    "type": "string",
                    "description": (
                        "Optional end date in DD-MM-YYYY format."
                    )
                }
            }
        }
    },
    
    # get_profit_loss
    
    {
        "type": "function",
        "name": "get_profit_loss",
        "description": (
            "Get the Profit and Loss report from Tally."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "company_name": {
                    "type": "string",
                    "description": "Optional Tally company name."
                },
                "from_date": {
                    "type": "string",
                    "description": (
                        "Optional start date in DD-MM-YYYY format."
                    )
                },
                "to_date": {
                    "type": "string",
                    "description": (
                        "Optional end date in DD-MM-YYYY format."
                    )
                }
            }
        }
    },
    
    # get_trial_balance
    
    {
        "type": "function",
        "name": "get_trial_balance",
        "description": (
            "Get the Trial Balance report from Tally."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "company_name": {
                    "type": "string",
                    "description": "Optional Tally company name."
                },
                "to_date": {
                    "type": "string",
                    "description": (
                        "Optional report date in DD-MM-YYYY format."
                    )
                }
            }
        }
    },
    
    # get_balance_sheet
    
    {
        "type": "function",
        "name": "get_balance_sheet",
        "description": (
            "Get the Balance Sheet report from Tally."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "company_name": {
                    "type": "string",
                    "description": "Optional Tally company name."
                },
                "to_date": {
                    "type": "string",
                    "description": (
                        "Optional report date in DD-MM-YYYY format."
                    )
                }
            }
        }
    },
    
    # get_party_outstanding_summary
    
    
    {
        "type": "function",
        "name": "get_party_outstanding_summary",
        "description": (
            "Get outstanding receivable and payable information "
            "for a specific customer, supplier, party, or ledger "
            "from Tally. Use this when the user mentions a party "
            "name and asks what they owe us, what we owe them, "
            "their outstanding balance, or both payable and "
            "receivable information."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "party_name": {
                    "type": "string",
                    "description": (
                        "The customer, supplier, party, or ledger "
                        "name mentioned by the user."
                    )
                },
                "company_name": {
                    "type": "string",
                    "description": (
                        "Optional Tally company name."
                    )
                }
            },
            "required": [
                "party_name"
            ]
        }
    },
    
    # get_outstanding_summary
    
    {
        "type": "function",
        "name": "get_outstanding_summary",
        "description": (
            "Get both total outstanding receivables and total "
            "outstanding payables from Tally. Use when the user "
            "asks for receivables and payables together, overall "
            "outstanding amounts, money to receive and money to pay, "
            "or a combined outstanding summary."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "company_name": {
                    "type": "string",
                    "description": (
                        "Optional Tally company name."
                    )
                }
            }
        }
    },
    
    # get_top_receivables
    
    {
    "type": "function",
    "name": "get_top_receivables",
    "description": (
        "Get the largest outstanding receivable bills "
        "from Tally, ranked by outstanding amount. "
        "Use for questions such as top receivables, "
        "largest receivable bills, or biggest "
        "outstanding receivable amounts."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": (
                    "Number of receivable bills to return. "
                    "Use 5 when the user does not specify "
                    "a number."
                )
            },
            "company_name": {
                "type": "string",
                "description": (
                    "Optional Tally company name."
                )
            }
        }
    }
},
    
    # get_ledger_report
    
{
    "type": "function",
    "name": "get_ledger_report",
    "description": (
        "Get a ledger's statement from Tally: its opening "
        "balance, closing balance, and every voucher entry "
        "posted to it, with a running balance. Use this "
        "whenever the user asks about a specific ledger's "
        "balance, transactions, statement, or history."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "ledger_name": {
                "type": "string",
                "description": (
                    "The ledger name mentioned by the user."
                )
            },
            "company_name": {
                "type": "string",
                "description": "Optional Tally company name."
            },
            "from_date": {
                "type": "string",
                "description": (
                    "Optional start date in DD-MM-YYYY format."
                )
            },
            "to_date": {
                "type": "string",
                "description": (
                    "Optional end date in DD-MM-YYYY format."
                )
            }
        },
        "required": [
            "ledger_name"
        ]
    }
},


# get_top_payables

{
    "type": "function",
    "name": "get_top_payables",
    "description": (
        "Get the largest outstanding payable bills "
        "from Tally, ranked by outstanding amount. "
        "Use for questions such as top payables, "
        "largest payable bills, or biggest "
        "outstanding payable amounts."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": (
                    "Number of payable bills to return. "
                    "Use 5 when the user does not specify "
                    "a number."
                )
            },
            "company_name": {
                "type": "string",
                "description": (
                    "Optional Tally company name."
                )
            }
        }
    }
},


# get_aged_receivables

{
    "type": "function",
    "name": "get_aged_receivables",
    "description": (
        "Get aging information for outstanding receivables "
        "from Tally. Use for questions about receivables "
        "overdue by 30, 60, 90 or more days, old customer "
        "dues, debtor aging, or receivable aging."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "minimum_days": {
                "type": "integer",
                "description": (
                    "Optional minimum number of overdue days. "
                    "For example, use 30 for receivables "
                    "overdue at least 30 days, 60 for at "
                    "least 60 days, and 90 for at least "
                    "90 days. Omit it for a complete "
                    "aging summary."
                )
            },
            "company_name": {
                "type": "string",
                "description": (
                    "Optional Tally company name."
                )
            }
        }
    }
},

# get_aged_payables

{
    "type": "function",
    "name": "get_aged_payables",
    "description": (
        "Get aging information for outstanding payables "
        "from Tally. Use for questions about payables "
        "overdue by 30, 60, 90 or more days, old supplier "
        "dues, creditor aging, or payable aging."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "minimum_days": {
                "type": "integer",
                "description": (
                    "Optional minimum number of overdue days. "
                    "For example, use 30 for payables "
                    "overdue at least 30 days, 60 for at "
                    "least 60 days, and 90 for at least "
                    "90 days. Omit it for a complete "
                    "aging summary."
                )
            },
            "company_name": {
                "type": "string",
                "description": (
                    "Optional Tally company name."
                )
            }
        }
    }
},

# get_period_comparison

{
    "name": "get_period_comparison",
    "description": (
        "Compare revenue, expenses, or net profit between "
        "two financial periods. Use this when the user asks "
        "to compare a financial metric between two periods, "
        "such as this month vs last month, this quarter vs "
        "last quarter, or one month vs another month."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "metric": {
                "type": "string",
                "enum": [
                    "revenue",
                    "expenses",
                    "net_profit"
                ],
                "description": (
                    "Financial metric to compare."
                )
            },
            "first_from_date": {
                "type": "string",
                "description": (
                    "Start date of the first period "
                    "in DD-MM-YYYY format."
                )
            },
            "first_to_date": {
                "type": "string",
                "description": (
                    "End date of the first period "
                    "in DD-MM-YYYY format."
                )
            },
            "second_from_date": {
                "type": "string",
                "description": (
                    "Start date of the comparison period "
                    "in DD-MM-YYYY format."
                )
            },
            "second_to_date": {
                "type": "string",
                "description": (
                    "End date of the comparison period "
                    "in DD-MM-YYYY format."
                )
            },
            "company_name": {
                "type": "string",
                "description": (
                    "Optional Tally company name."
                )
            }
        },
        "required": [
            "metric",
            "first_from_date",
            "first_to_date",
            "second_from_date",
            "second_to_date"
        ]
    }
},


# get_cash_balance

{
    "type": "function",
    "name": "get_cash_balance",
    "description": (
        "Get the current Cash-in-Hand balance from Tally. "
        "Use when the user asks for cash balance, current cash, "
        "cash in hand, available cash, petty cash, or the balance "
        "of a specific cash ledger."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "ledger_name": {
                "type": "string",
                "description": (
                    "Optional specific cash ledger name mentioned "
                    "by the user, such as Cash or Petty Cash."
                )
            },
            "company_name": {
                "type": "string",
                "description": (
                    "Optional Tally company name."
                )
            }
        }
    }
},

# get_bank_balance
{
    "type": "function",
    "name": "get_bank_balance",
    "description": (
        "Get current bank account balances from Tally. "
        "Use when the user asks for bank balance, total bank "
        "balance, available money in banks, all bank balances, "
        "or the balance of a specific bank account."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "ledger_name": {
                "type": "string",
                "description": (
                    "Optional specific bank ledger or account "
                    "name mentioned by the user."
                )
            },
            "company_name": {
                "type": "string",
                "description": (
                    "Optional Tally company name."
                )
            }
        }
    }
},

# get_cash_transactions

{
    "type": "function",
    "name": "get_cash_transactions",
    "description": (
        "Get cash transactions from Cash-in-Hand ledgers in Tally. "
        "Use when the user asks for cash transactions, cash entries, "
        "or cash movement."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "ledger_name": {
                "type": "string",
                "description": (
                    "Optional specific cash ledger name."
                )
            },
            "from_date": {
                "type": "string",
                "description": (
                    "Optional start date in DD-MM-YYYY format."
                )
            },
            "to_date": {
                "type": "string",
                "description": (
                    "Optional end date in DD-MM-YYYY format."
                )
            },
            "company_name": {
                "type": "string",
                "description": (
                    "Optional Tally company name."
                )
            }
        }
    }
},


# get_sales_transactions
{
    "type": "function",
    "name": "get_sales_transactions",
    "description": (
        "Get sales transactions from Sales Accounts ledgers in Tally. "
        "Use when the user asks for sales transactions, sales entries, "
        "sales activity, or transactions from a specific sales ledger."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "ledger_name": {
                "type": "string",
                "description": (
                    "Optional specific sales ledger name."
                )
            },
            "from_date": {
                "type": "string",
                "description": (
                    "Optional start date in DD-MM-YYYY format."
                )
            },
            "to_date": {
                "type": "string",
                "description": (
                    "Optional end date in DD-MM-YYYY format."
                )
            },
            "company_name": {
                "type": "string",
                "description": (
                    "Optional Tally company name."
                )
            }
        }
    }
},

# get_purchase_transactions

{
    "type": "function",
    "name": "get_purchase_transactions",
    "description": (
        "Get purchase transactions from Purchase Accounts ledgers in Tally. "
        "Use when the user asks for purchase transactions, purchase entries, "
        "purchase activity, or transactions from a specific purchase ledger."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "ledger_name": {
                "type": "string",
                "description": (
                    "Optional specific purchase ledger name."
                )
            },
            "from_date": {
                "type": "string",
                "description": (
                    "Optional start date in DD-MM-YYYY format."
                )
            },
            "to_date": {
                "type": "string",
                "description": (
                    "Optional end date in DD-MM-YYYY format."
                )
            },
            "company_name": {
                "type": "string",
                "description": (
                    "Optional Tally company name."
                )
            }
        }
    }
},

# get_receipt_transactions

{
    "type": "function",
    "name": "get_receipt_transactions",
    "description": (
        "Get receipt transactions from Tally. "
        "Use when the user asks about receipts, money received, "
        "customer receipts, or receipt voucher entries."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "from_date": {
                "type": "string",
                "description": (
                    "Optional start date in DD-MM-YYYY format."
                )
            },
            "to_date": {
                "type": "string",
                "description": (
                    "Optional end date in DD-MM-YYYY format."
                )
            },
            "company_name": {
                "type": "string",
                "description": (
                    "Optional Tally company name."
                )
            }
        }
    }
},

# get_payment_transactions

{
    "type": "function",
    "name": "get_payment_transactions",
    "description": (
        "Get payment transactions from Tally. "
        "Use when the user asks about payments made, outgoing payments, "
        "supplier payments, or payment voucher entries."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "from_date": {
                "type": "string",
                "description": "Optional start date in DD-MM-YYYY format."
            },
            "to_date": {
                "type": "string",
                "description": "Optional end date in DD-MM-YYYY format."
            },
            "company_name": {
                "type": "string",
                "description": "Optional Tally company name."
            }
        }
    }
},

# get_credit_note_transactions

{
    "type": "function",
    "name": "get_credit_note_transactions",
    "description": (
        "Get Credit Note transactions from Tally. "
        "Use when the user asks about credit notes, sales returns, "
        "customer adjustments, or Credit Note voucher entries."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "from_date": {
                "type": "string",
                "description": "Optional start date in DD-MM-YYYY format."
            },
            "to_date": {
                "type": "string",
                "description": "Optional end date in DD-MM-YYYY format."
            },
            "company_name": {
                "type": "string",
                "description": "Optional Tally company name."
            }
        }
    }
},

# get_debit_note_transactions
{
    "type": "function",
    "name": "get_debit_note_transactions",
    "description": (
        "Get Debit Note transactions from Tally. "
        "Use when the user asks about debit notes, purchase returns, "
        "supplier adjustments, or Debit Note voucher entries."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "from_date": {
                "type": "string",
                "description": "Optional start date in DD-MM-YYYY format."
            },
            "to_date": {
                "type": "string",
                "description": "Optional end date in DD-MM-YYYY format."
            },
            "company_name": {
                "type": "string",
                "description": "Optional Tally company name."
            }
        }
    }
},


# get_invoice_details

{
    "type": "function",
    "name": "get_invoice_details",
    "description": (
        "Get details of a specific invoice from Tally. "
        "Use when the user asks for invoice amount, party, date, "
        "due date, outstanding amount, or complete invoice details."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "invoice_number": {
                "type": "string",
                "description": "Invoice or bill reference number."
            },
            "company_name": {
                "type": "string",
                "description": "Optional Tally company name."
            }
        },
        "required": ["invoice_number"]
    }
},

# get_invoice_status

{
    "type": "function",
    "name": "get_invoice_status",
    "description": (
        "Check whether a specific invoice is paid, partially paid, "
        "or unpaid using the invoice outstanding amount."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "invoice_number": {
                "type": "string",
                "description": "Invoice or bill reference number."
            },
            "company_name": {
                "type": "string",
                "description": "Optional Tally company name."
            }
        },
        "required": ["invoice_number"]
    }
},

# get_customer_statement

{
    "type": "function",
    "name": "get_customer_statement",
    "description": (
        "Get a customer ledger statement from Tally. "
        "Use when the user asks for customer statement, "
        "customer transactions, or customer ledger activity."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "party_name": {
                "type": "string",
                "description": "Customer or debtor name."
            },
            "from_date": {
                "type": "string",
                "description": "Optional start date in DD-MM-YYYY format."
            },
            "to_date": {
                "type": "string",
                "description": "Optional end date in DD-MM-YYYY format."
            },
            "company_name": {
                "type": "string",
                "description": "Optional Tally company name."
            }
        },
        "required": ["party_name"]
    }
},

# get_supplier_statement

{
    "type": "function",
    "name": "get_supplier_statement",
    "description": (
        "Get a supplier ledger statement from Tally. "
        "Use when the user asks for supplier statement, "
        "supplier transactions, or supplier ledger activity."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "party_name": {
                "type": "string",
                "description": "Supplier or creditor name."
            },
            "from_date": {
                "type": "string",
                "description": "Optional start date in DD-MM-YYYY format."
            },
            "to_date": {
                "type": "string",
                "description": "Optional end date in DD-MM-YYYY format."
            },
            "company_name": {
                "type": "string",
                "description": "Optional Tally company name."
            }
        },
        "required": ["party_name"]
    }
},


#   get_input_gst

{
    "type": "function",
    "name": "get_input_gst",
    "description": (
        "Get Input GST details from Tally. "
        "Use when the user asks about Input CGST, Input SGST, "
        "Input IGST, input tax, or GST paid on purchases."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "from_date": {
                "type": "string",
                "description": "Optional start date in DD-MM-YYYY format."
            },
            "to_date": {
                "type": "string",
                "description": "Optional end date in DD-MM-YYYY format."
            },
            "company_name": {
                "type": "string",
                "description": "Optional Tally company name."
            }
        }
    }
},

# get_output_gst

{
    "type": "function",
    "name": "get_output_gst",
    "description": (
        "Get Output GST details from Tally. "
        "Use when the user asks about Output CGST, Output SGST, "
        "Output IGST, output tax, or GST collected on sales."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "from_date": {
                "type": "string",
                "description": "Optional start date in DD-MM-YYYY format."
            },
            "to_date": {
                "type": "string",
                "description": "Optional end date in DD-MM-YYYY format."
            },
            "company_name": {
                "type": "string",
                "description": "Optional Tally company name."
            }
        }
    }
},

# get_gst_summary

{
    "type": "function",
    "name": "get_gst_summary",
    "description": (
        "Get a combined GST summary from Tally showing "
        "Input GST, Output GST, and Net GST."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "from_date": {
                "type": "string",
                "description": "Optional start date in DD-MM-YYYY format."
            },
            "to_date": {
                "type": "string",
                "description": "Optional end date in DD-MM-YYYY format."
            },
            "company_name": {
                "type": "string",
                "description": "Optional Tally company name."
            }
        }
    }
},

# get_stock_items


{
    "type": "function",
    "name": "get_stock_items",
    "description": (
        "Get the list of stock items available in Tally. "
        "Use when the user asks to show inventory, stock items, "
        "products in stock, or available items."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "company_name": {
                "type": "string",
                "description": "Optional Tally company name."
            }
        }
    }
},

# get_stock_summary

{
    "type": "function",
    "name": "get_stock_summary",
    "description": (
        "Get a summary of inventory from Tally including "
        "total stock items and stock value."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "company_name": {
                "type": "string",
                "description": "Optional Tally company name."
            }
        }
    }
},

#   get_stock_item_details

{
    "type": "function",
    "name": "get_stock_item_details",
    "description": (
        "Get inventory details for one specific stock item. "
        "Use when the user asks about the quantity, rate, "
        "value, or details of a particular product."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "item_name": {
                "type": "string",
                "description": (
                    "Name of the stock item requested by the user."
                )
            },
            "company_name": {
                "type": "string",
                "description": "Optional Tally company name."
            }
        },
        "required": [
            "item_name"
        ]
    }
},

# get_top_stock_items

{
    "type": "function",
    "name": "get_top_stock_items",
    "description": (
        "Get stock items with the highest closing stock value. "
        "Use when the user asks for top inventory items, "
        "highest-value stock, or most valuable products."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": (
                    "Number of stock items to return. "
                    "Defaults to 5."
                )
            },
            "company_name": {
                "type": "string",
                "description": "Optional Tally company name."
            }
        }
    }
},

# get_negative_stock_items
{
    "type": "function",
    "name": "get_negative_stock_items",
    "description": (
        "Get stock items whose current closing quantity is negative. "
        "Use when the user asks about negative inventory, "
        "stock shortages, or items below zero."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "company_name": {
                "type": "string",
                "description": "Optional Tally company name."
            }
        }
    }
},

# get_tds_summary

{
    "name": "get_tds_summary",
    "description": (
        "Get a summary of TDS ledgers and balances from Tally. "
        "Use this when the user asks about TDS balance, TDS summary, "
        "tax deducted at source, or TDS details."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "company_name": {
                "type": "string",
                "description": "Company name in Tally."
            },
            "from_date": {
                "type": "string",
                "description": "Start date for the requested period."
            },
            "to_date": {
                "type": "string",
                "description": "End date for the requested period."
            },
        },
    },
},

# get_tds_transactions

{
    "name": "get_tds_transactions",
    "description": (
        "Get transactions recorded in TDS ledgers from Tally. "
        "Use this when the user asks to see TDS transactions, "
        "TDS entries, or TDS deductions."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "company_name": {
                "type": "string",
                "description": "Company name in Tally."
            },
            "from_date": {
                "type": "string",
                "description": "Start date for the requested period."
            },
            "to_date": {
                "type": "string",
                "description": "End date for the requested period."
            },
        },
    },
},

# get_cash_flow_summary

{
    "name": "get_cash_flow_summary",
    "description": (
        "Get cash inflow, cash outflow and net cash flow "
        "from Cash and Bank ledgers in Tally."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "company_name": {
                "type": "string",
            },
            "from_date": {
                "type": "string",
            },
            "to_date": {
                "type": "string",
            },
        },
    },
},

# get_profitability_summary

{
    "name": "get_profitability_summary",
    "description": (
        "Get revenue, expenses, net profit and profit margin "
        "for the selected period."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "company_name": {
                "type": "string",
            },
            "from_date": {
                "type": "string",
            },
            "to_date": {
                "type": "string",
            },
        },
    },
},


# get_top_expenses

{
    "name": "get_top_expenses",
    "description": (
        "Get the highest expense ledgers for the selected period. "
        "Use this when the user asks for top expenses, highest expenses, "
        "or major expense categories."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "company_name": {
                "type": "string",
            },
            "from_date": {
                "type": "string",
            },
            "to_date": {
                "type": "string",
            },
            "limit": {
                "type": "integer",
                "description": "Number of expense ledgers to return."
            },
        },
    },
},

# get_top_customers

{
    "name": "get_top_customers",
    "description": (
        "Get customers with the highest outstanding receivable. "
        "Use this when the user asks for top customers, highest receivables, "
        "or customers who owe the most money."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "company_name": {
                "type": "string",
            },
            "limit": {
                "type": "integer",
                "description": "Number of customers to return."
            },
        },
    },
},

# get_top_suppliers

{
    "name": "get_top_suppliers",
    "description": (
        "Get suppliers with the highest outstanding payable. "
        "Use this when the user asks for top suppliers, highest payables, "
        "or suppliers to whom the most money is owed."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "company_name": {
                "type": "string",
            },
            "limit": {
                "type": "integer",
                "description": "Number of suppliers to return."
            },
        },
    },
},


# get_period_trend

{
    "name": "get_period_trend",
    "description": (
        "Compare revenue, expenses and net profit between two periods. "
        "Use this for month-to-month or period-to-period financial comparison."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "company_name": {
                "type": "string",
            },
            "current_from_date": {
                "type": "string",
            },
            "current_to_date": {
                "type": "string",
            },
            "previous_from_date": {
                "type": "string",
            },
            "previous_to_date": {
                "type": "string",
            },
        },
    },
},

# get_customer_profitability

{
    "type": "function",
    "name": "get_customer_profitability",
    "description": (
        "Get customer-wise sales contribution and customer performance "
        "for a selected period. This does not estimate gross profit or "
        "profit margin when customer-specific cost data is unavailable."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "from_date": {
                "type": "string",
                "description": (
                    "Optional start date in DD-MM-YYYY format."
                )
            },
            "to_date": {
                "type": "string",
                "description": (
                    "Optional end date in DD-MM-YYYY format."
                )
            },
            "company_name": {
                "type": "string",
                "description": (
                    "Optional Tally company name."
                )
            }
        }
    }
},

# get_product_profitability

{
    "type": "function",
    "name": "get_product_profitability",
    "description": (
        "Get product-wise sales contribution and product performance "
        "for a selected period. Gross profit and margin are not "
        "estimated unless reliable product-level cost data is available."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "from_date": {
                "type": "string",
                "description": "Optional start date in DD-MM-YYYY format."
            },
            "to_date": {
                "type": "string",
                "description": "Optional end date in DD-MM-YYYY format."
            },
            "company_name": {
                "type": "string",
                "description": "Optional Tally company name."
            }
        }
    }
},

# get_tax_liability
{
    "type": "function",
    "name": "get_tax_liability",
    "description": (
        "Get a combined tax overview including GST input, GST output, "
        "net GST payable and TDS amount for a selected period."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "from_date": {
                "type": "string",
                "description": "Optional start date in DD-MM-YYYY format."
            },
            "to_date": {
                "type": "string",
                "description": "Optional end date in DD-MM-YYYY format."
            },
            "company_name": {
                "type": "string",
                "description": "Optional Tally company name."
            }
        }
    }
},

# get_tds_receivable

{
    "type": "function",
    "name": "get_tds_receivable",
    "description": (
        "Get TDS receivable balances for a selected period. "
        "This represents TDS ledgers with debit closing balances."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "from_date": {
                "type": "string",
                "description": "Optional start date in DD-MM-YYYY format."
            },
            "to_date": {
                "type": "string",
                "description": "Optional end date in DD-MM-YYYY format."
            },
            "company_name": {
                "type": "string",
                "description": "Optional Tally company name."
            }
        }
    }
},

# get_tds_payable

{
    "type": "function",
    "name": "get_tds_payable",
    "description": (
        "Get TDS payable balances for a selected period. "
        "This represents TDS ledgers with credit closing balances."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "from_date": {
                "type": "string",
                "description": "Optional start date in DD-MM-YYYY format."
            },
            "to_date": {
                "type": "string",
                "description": "Optional end date in DD-MM-YYYY format."
            },
            "company_name": {
                "type": "string",
                "description": "Optional Tally company name."
            }
        }
    }
},

# get_financial_trends
{
    "type": "function",
    "name": "get_financial_trends",
    "description": (
        "Get month-wise financial trends including revenue, "
        "total expenses, and net profit for a selected period."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "from_date": {
                "type": "string",
                "description": "Start date in DD-MM-YYYY format."
            },
            "to_date": {
                "type": "string",
                "description": "End date in DD-MM-YYYY format."
            },
            "company_name": {
                "type": "string",
                "description": "Optional Tally company name."
            }
        }
    }
},

# get_company_comparison
{
    "name": "get_company_comparison",
    "description": (
        "Compare financial performance across multiple Tally companies "
        "for a selected date range."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "company_names": {
                "type": "array",
                "items": {
                    "type": "string",
                },
                "description": (
                    "List of Tally company names to compare."
                ),
            },
            "from_date": {
                "type": "string",
                "description": (
                    "Start date in DD-MM-YYYY format."
                ),
            },
            "to_date": {
                "type": "string",
                "description": (
                    "End date in DD-MM-YYYY format."
                ),
            },
        },
        "required": [
            "company_names",
        ],
    },
},

# get_cost_centre_analysis

{
    "name": "get_cost_centre_analysis",
    "description": (
        "Get cost centre-wise financial allocations from Tally. "
        "Use when the user asks about cost centres, cost centre "
        "performance, cost centre allocations, department-wise "
        "allocations, or branch-wise allocations recorded through "
        "Tally cost centres."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "from_date": {
                "type": "string",
                "description": (
                    "Optional start date in DD-MM-YYYY format."
                ),
            },
            "to_date": {
                "type": "string",
                "description": (
                    "Optional end date in DD-MM-YYYY format."
                ),
            },
            "company_name": {
                "type": "string",
                "description": (
                    "Optional Tally company name."
                ),
            },
        },
    },
},

# get_party_statement
{
    "name": "get_party_statement",
    "description": (
        "Get the chronological statement of a customer or supplier "
        "from Tally, including opening balance, closing balance, "
        "and ledger transactions. Use when the user asks for a "
        "customer statement, supplier statement, party statement, "
        "account statement, ledger statement, or transaction history "
        "of a specific customer or supplier."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "party_name": {
                "type": "string",
                "description": (
                    "Customer or supplier ledger name mentioned "
                    "by the user."
                ),
            },
            "from_date": {
                "type": "string",
                "description": (
                    "Optional start date in DD-MM-YYYY format."
                ),
            },
            "to_date": {
                "type": "string",
                "description": (
                    "Optional end date in DD-MM-YYYY format."
                ),
            },
            "company_name": {
                "type": "string",
                "description": (
                    "Optional Tally company name."
                ),
            },
        },
        "required": [
            "party_name",
        ],
    },
},

# get_bank_transactions

{
    "name": "get_bank_transactions",
    "description": (
        "Get transaction history for a specific cash or bank ledger "
        "from Tally. Use when the user asks for bank transactions, "
        "cash transactions, account transactions, deposits, withdrawals, "
        "or transaction history for a specific bank or cash ledger."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "ledger_name": {
                "type": "string",
                "description": (
                    "Name of the cash or bank ledger mentioned "
                    "by the user."
                ),
            },
            "from_date": {
                "type": "string",
                "description": (
                    "Optional start date in DD-MM-YYYY format."
                ),
            },
            "to_date": {
                "type": "string",
                "description": (
                    "Optional end date in DD-MM-YYYY format."
                ),
            },
            "company_name": {
                "type": "string",
                "description": (
                    "Optional Tally company name."
                ),
            },
        },
        "required": [
            "ledger_name",
        ],
    },
},

]
