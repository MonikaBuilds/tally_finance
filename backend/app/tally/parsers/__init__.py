"""
Tally parser package.

The original Tally parser was a single large parser.py file.
The parsing logic is now organized by responsibility:

    common.py     -> shared XML and conversion helpers
    company.py    -> company parsing
    financial.py  -> financial reports
    ledger.py     -> ledger and voucher reports
    inventory.py  -> stock and inventory reports

Other parts of the application can import parser functions from
this package without needing to know which internal module contains
each function.
"""


# ============================================================
# COMPANY
# ============================================================

from app.tally.parsers.company import (
    parse_companies,
)


# ============================================================
# FINANCIAL REPORTS
# ============================================================

from app.tally.parsers.financial import (
    parse_profit_loss,
    parse_trial_balance,
    parse_group_summary,
    parse_balance_sheet,
    parse_bill_allocations,
    parse_outstanding_report,
)


# ============================================================
# LEDGER / VOUCHERS
# ============================================================

from app.tally.parsers.ledger import (
    parse_ledger_list,
    parse_ledger_voucher_details,
    parse_voucher_detail,
    merge_ledger_rows,
    build_continuous_monthly_summary,
    parse_ledger_report,
)


# ============================================================
# INVENTORY
# ============================================================

from app.tally.parsers.inventory import (
    parse_stock_item_list,
    parse_stock_summary,
    parse_stock_groups,
    parse_stock_categories,
    parse_godowns,
    parse_stock_movement,
    parse_inventory_register,
    parse_inventory_register_summary,
    parse_stock_valuation,
    parse_negative_stock,
)


# ============================================================
# PUBLIC PARSER API
# ============================================================

# __all__ clearly defines which parser functions are intended
# to be used by the rest of the application.
#
# Internal helpers such as _text, _first_text and
# _parse_signed_tally_amount are intentionally not exposed here.

__all__ = [
    # Company
    "parse_companies",

    # Financial
    "parse_profit_loss",
    "parse_trial_balance",
    "parse_group_summary",
    "parse_balance_sheet",
    "parse_bill_allocations",
    "parse_outstanding_report",

    # Ledger / Voucher
    "parse_ledger_list",
    "parse_ledger_voucher_details",
    "parse_voucher_detail",
    "merge_ledger_rows",
    "build_continuous_monthly_summary",
    "parse_ledger_report",

    # Inventory
    "parse_stock_item_list",
    "parse_stock_summary",
    "parse_stock_groups",
    "parse_stock_categories",
    "parse_godowns",
    "parse_stock_movement",
    "parse_inventory_register",
    "parse_inventory_register_summary",
    "parse_stock_valuation",
    "parse_negative_stock",
]