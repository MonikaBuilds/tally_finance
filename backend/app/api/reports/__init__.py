"""
Reports API package modularized into domain routers:
- financial: Profit & Loss, Balance Sheet, Trial Balance, Group Summary
- ledgers: Ledger report, voucher detail, ledger lists
- outstandings: Receivables, Payables, Bill allocations, Pending Invoices
- inventory: Stock Summary, Godowns, Groups, Categories, Movement, Registers
"""

from fastapi import APIRouter

# Re-export all common helpers, constants, and column definitions
from app.api.reports.common import (
    _resolve_org_id,
    _cached_report,
    _period_label,
    _as_rows,
    _pl_rows_to_two_columns,
    _download_headers,
    _check_format,
    _safe_name,
    _spec_response,
    _export_response,
    _fmt_period,
    _check_period,
    LEDGER_COLUMNS,
    PROFIT_LOSS_COLUMNS,
    TRIAL_BALANCE_COLUMNS,
    BALANCE_SHEET_COLUMNS,
    BILLS_COLUMNS,
    STOCK_SUMMARY_COLUMNS,
    STOCK_GROUP_COLUMNS,
    STOCK_CATEGORY_COLUMNS,
    GODOWN_COLUMNS,
    STOCK_MOVEMENT_COLUMNS,
    STOCK_VALUATION_COLUMNS,
    NEGATIVE_STOCK_COLUMNS,
    PENDING_INVOICES_COLUMNS,
    INVENTORY_REGISTER_COLUMNS,
)

# Re-export Tally service fetchers for backward compatibility
from app.tally.service import (
    fetch_profit_loss,
    fetch_group_summary,
    fetch_trial_balance,
    fetch_balance_sheet,
    fetch_balance_sheet_report,
    fetch_bill_allocations,
    fetch_bills_receivable,
    fetch_bills_payable,
    fetch_ledger_list,
    fetch_ledger_report,
    fetch_voucher_detail,
    fetch_stock_summary,
    fetch_stock_item,
    fetch_stock_groups,
    fetch_stock_categories,
    fetch_godowns,
    fetch_stock_movement,
    fetch_stock_valuation,
    fetch_negative_stock,
    fetch_inventory_register,
    fetch_stock_group_items,
    fetch_inventory_voucher_detail,
    fetch_stock_group_summary,
    fetch_stock_category_summary,
    fetch_godown_summary,
    fetch_stock_item_monthly,
    fetch_stock_item_vouchers,
    fetch_sales_bills_pending,
    fetch_register_months,
    fetch_register_voucher_list,
    fetch_godown_item_monthly,
)

# Import sub-routers
from app.api.reports.financial import router as financial_router
from app.api.reports.ledgers import router as ledgers_router
from app.api.reports.outstandings import router as outstandings_router
from app.api.reports.inventory import router as inventory_router

# Unified reports router for main application inclusion
router = APIRouter()
router.include_router(financial_router)
router.include_router(ledgers_router)
router.include_router(outstandings_router)
router.include_router(inventory_router)

__all__ = [
    "router",
    "financial_router",
    "ledgers_router",
    "outstandings_router",
    "inventory_router",
    "_resolve_org_id",
    "_cached_report",
    "_period_label",
    "_as_rows",
    "_pl_rows_to_two_columns",
    "_download_headers",
    "_check_format",
    "_safe_name",
    "_spec_response",
    "_export_response",
    "_fmt_period",
    "_check_period",
    "LEDGER_COLUMNS",
    "PROFIT_LOSS_COLUMNS",
    "TRIAL_BALANCE_COLUMNS",
    "BALANCE_SHEET_COLUMNS",
    "BILLS_COLUMNS",
    "STOCK_SUMMARY_COLUMNS",
    "STOCK_GROUP_COLUMNS",
    "STOCK_CATEGORY_COLUMNS",
    "GODOWN_COLUMNS",
    "STOCK_MOVEMENT_COLUMNS",
    "STOCK_VALUATION_COLUMNS",
    "NEGATIVE_STOCK_COLUMNS",
    "PENDING_INVOICES_COLUMNS",
    "INVENTORY_REGISTER_COLUMNS",
    "fetch_profit_loss",
    "fetch_group_summary",
    "fetch_trial_balance",
    "fetch_balance_sheet",
    "fetch_balance_sheet_report",
    "fetch_bill_allocations",
    "fetch_bills_receivable",
    "fetch_bills_payable",
    "fetch_ledger_list",
    "fetch_ledger_report",
    "fetch_voucher_detail",
    "fetch_stock_summary",
    "fetch_stock_item",
    "fetch_stock_groups",
    "fetch_stock_categories",
    "fetch_godowns",
    "fetch_stock_movement",
    "fetch_stock_valuation",
    "fetch_negative_stock",
    "fetch_inventory_register",
    "fetch_stock_group_items",
    "fetch_inventory_voucher_detail",
    "fetch_stock_group_summary",
    "fetch_stock_category_summary",
    "fetch_godown_summary",
    "fetch_stock_item_monthly",
    "fetch_stock_item_vouchers",
    "fetch_sales_bills_pending",
    "fetch_register_months",
    "fetch_register_voucher_list",
    "fetch_godown_item_monthly",
]
