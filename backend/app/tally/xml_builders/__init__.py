"""
Tally XML request builders organized by domain.
"""

# Common helpers
from .common import (
    format_tally_date,
    build_company_variable,
)

# Company
from .company import (
    build_company_request,
)

# Financial
from .financial import (
    build_profit_loss_request,
    build_group_summary_request,
    build_trial_balance_request,
    build_balance_sheet_request,
    build_voucher_bills_request,
    build_bills_receivable_request,
    build_bills_payable_request,
)

# Ledger / Voucher
from .ledger import (
    build_ledger_list_request,
    build_single_ledger_request,
    build_ledger_report_request,
    build_ledger_voucher_collection_request,
    build_voucher_detail_request,
    build_chatbot_ledger_request,
)

# Inventory
from .inventory import (
    build_stock_summary_request,
    build_stock_item_request,
    build_stock_group_request,
    build_stock_category_request,
    build_godown_request,
    build_stock_movement_request,
    build_inventory_register_request,
    build_stock_item_list_request,
)


__all__ = [
    # Common
    "format_tally_date",
    "build_company_variable",

    # Company
    "build_company_request",

    # Financial
    "build_profit_loss_request",
    "build_group_summary_request",
    "build_trial_balance_request",
    "build_balance_sheet_request",
    "build_voucher_bills_request",
    "build_bills_receivable_request",
    "build_bills_payable_request",

    # Ledger / Voucher
    "build_ledger_list_request",
    "build_single_ledger_request",
    "build_ledger_report_request",
    "build_ledger_voucher_collection_request",
    "build_voucher_detail_request",
    "build_chatbot_ledger_request",

    # Inventory
    "build_stock_summary_request",
    "build_stock_item_request",
    "build_stock_group_request",
    "build_stock_category_request",
    "build_godown_request",
    "build_stock_movement_request",
    "build_inventory_register_request",
    "build_stock_item_list_request",
]