from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.security.auth import get_authorized_company

from app.tally.service import (
    fetch_profit_loss,
    fetch_group_summary,
    fetch_trial_balance,
    fetch_balance_sheet,
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
)

from app.financial.service import (
    build_outstanding_summary,
    build_receivables_from_tally_report,
    build_payables_from_tally_report,
    build_pending_invoices_from_reports,
)

from app.export.exporter import build_excel, build_pdf


router = APIRouter()


# ============================================================
# COLUMNS
# ============================================================

LEDGER_COLUMNS = [
    {"key": "date", "label": "Date"},
    {"key": "particulars", "label": "Particulars"},
    {"key": "voucher_type", "label": "Vch Type"},
    {"key": "voucher_number", "label": "Vch No."},
    {"key": "debit", "label": "Debit"},
    {"key": "credit", "label": "Credit"},
    {"key": "running_balance", "label": "Balance"},
]

# P&L is a two-column (Dr | Cr) report - see get_profit_loss_report /
# export_profit_loss_report below for how "left"/"right" become
# actual columns for both the JSON API and the PDF/Excel export.
PROFIT_LOSS_COLUMNS = [
    {"key": "left_name", "label": "Particulars"},
    {"key": "left_amount", "label": "Amount"},
    {"key": "right_name", "label": "Particulars"},
    {"key": "right_amount", "label": "Amount"},
]

TRIAL_BALANCE_COLUMNS = [
    {"key": "name", "label": "Ledger"},
    {"key": "debit", "label": "Debit"},
    {"key": "credit", "label": "Credit"},
]

BALANCE_SHEET_COLUMNS = [
    {"key": "name", "label": "Particulars"},
    {"key": "amount", "label": "Amount"},
]

BILLS_COLUMNS = [
    {"key": "party", "label": "Party"},
    {"key": "bill_reference", "label": "Bill Ref."},
    {"key": "bill_date", "label": "Bill Date"},
    {"key": "due_date", "label": "Due Date"},
    {"key": "overdue_days", "label": "Overdue Days"},
    {"key": "outstanding_amount", "label": "Outstanding"},
]

STOCK_SUMMARY_COLUMNS = [
    {"key": "stock_item", "label": "Stock Item"},
    {"key": "stock_group", "label": "Stock Group"},
    {"key": "unit", "label": "Unit"},
    {"key": "opening_quantity", "label": "Opening Qty"},
    {"key": "opening_value", "label": "Opening Value"},
    {"key": "closing_quantity", "label": "Closing Qty"},
    {"key": "closing_rate", "label": "Closing Rate"},
    {"key": "closing_value", "label": "Closing Value"},
]

STOCK_GROUP_COLUMNS = [
    {"key": "stock_group", "label": "Stock Group"},
    {"key": "parent", "label": "Parent"},
    {"key": "base_units", "label": "Base Units"},
]

STOCK_CATEGORY_COLUMNS = [
    {"key": "stock_category", "label": "Stock Category"},
    {"key": "parent", "label": "Parent"},
]

GODOWN_COLUMNS = [
    {"key": "godown", "label": "Godown"},
    {"key": "parent", "label": "Parent"},
    {"key": "is_internal", "label": "Internal"},
]

STOCK_MOVEMENT_COLUMNS = [
    {"key": "date", "label": "Date"},
    {"key": "stock_item", "label": "Stock Item"},
    {"key": "voucher_type", "label": "Vch Type"},
    {"key": "voucher_number", "label": "Vch No."},
    {"key": "party", "label": "Party"},
    {"key": "quantity", "label": "Quantity"},
    {"key": "rate", "label": "Rate"},
    {"key": "value", "label": "Value"},
    {"key": "direction", "label": "Movement"},
]

STOCK_VALUATION_COLUMNS = [
    {"key": "stock_item", "label": "Stock Item"},
    {"key": "unit", "label": "Unit"},
    {"key": "closing_quantity", "label": "Closing Qty"},
    {"key": "valuation_rate", "label": "Valuation Rate"},
    {"key": "valuation_value", "label": "Valuation Value"},
]

NEGATIVE_STOCK_COLUMNS = [
    {"key": "stock_item", "label": "Stock Item"},
    {"key": "stock_group", "label": "Stock Group"},
    {"key": "unit", "label": "Unit"},
    {"key": "closing_quantity", "label": "Closing Qty"},
    {"key": "closing_rate", "label": "Closing Rate"},
    {"key": "closing_value", "label": "Closing Value"},
]

PENDING_INVOICES_COLUMNS = [
    {"key": "type", "label": "Type"},
    {"key": "party", "label": "Party"},
    {"key": "bill_reference", "label": "Bill Ref."},
    {"key": "bill_date", "label": "Bill Date"},
    {"key": "due_date", "label": "Due Date"},
    {"key": "overdue_days", "label": "Overdue Days"},
    {"key": "outstanding_amount", "label": "Outstanding"},
]


# ============================================================
# EXPORT HELPERS
# ============================================================

def _period_label(from_date=None, to_date=None, as_on=None) -> str | None:
    """Tally-style period line for a report header, e.g.
    '1-Apr-2024 to 31-Mar-2025' or 'as on 31-Mar-2025'."""
    if as_on:
        return f"as on {as_on.strftime('%d-%b-%Y')}"
    if from_date and to_date:
        return f"{from_date.strftime('%d-%b-%Y')} to {to_date.strftime('%d-%b-%Y')}"
    if to_date:
        return f"as on {to_date.strftime('%d-%b-%Y')}"
    return None


def _as_rows(report) -> list:
    """Some parsers return a flat list; others return
    {"success": ..., "rows": [...], "count": ...}. Normalize to a
    flat list either way so callers never have to care."""
    if isinstance(report, dict):
        return report.get("rows", [])
    return report or []


def _pl_rows_to_two_columns(report: dict) -> list:
    """
    parse_profit_loss() returns {"left": [...], "right": [...]} - two
    independently-lengthed columns. Zip them side by side into one
    row-per-line-pair list so the existing flat-table exporter
    (build_excel/build_pdf) can render it, padding the shorter side
    with blanks.
    """
    left = report.get("left", []) if isinstance(report, dict) else []
    right = report.get("right", []) if isinstance(report, dict) else []

    row_count = max(len(left), len(right))

    rows = []

    for i in range(row_count):
        left_row = left[i] if i < len(left) else None
        right_row = right[i] if i < len(right) else None

        rows.append(
            {
                "left_name": left_row["name"] if left_row else "",
                "left_amount": left_row["amount"] if left_row else "",
                "right_name": right_row["name"] if right_row else "",
                "right_amount": right_row["amount"] if right_row else "",
            }
        )

    return rows


def _download_headers(filename: str) -> dict:
    return {
        "Content-Disposition": f'attachment; filename="{filename}"'
    }


def _export_response(
    file_format: str,
    title: str,
    columns: list,
    rows: list,
    company_name: str | None,
    filename_base: str,
    footer: dict | None = None,
    period: str | None = None,
):
    if file_format not in ("pdf", "xlsx"):
        raise HTTPException(
            status_code=400,
            detail="format must be 'pdf' or 'xlsx'",
        )

    if file_format == "xlsx":
        content = build_excel(
            title=title,
            columns=columns,
            rows=rows,
            company_name=company_name,
            footer=footer,
            period=period,
        )

        return Response(
            content=content,
            media_type=(
                "application/vnd.openxmlformats-officedocument"
                ".spreadsheetml.sheet"
            ),
            headers=_download_headers(
                f"{filename_base}.xlsx"
            ),
        )

    content = build_pdf(
        title=title,
        columns=columns,
        rows=rows,
        company_name=company_name,
        footer=footer,
        period=period,
    )

    return Response(
        content=content,
        media_type="application/pdf",
        headers=_download_headers(
            f"{filename_base}.pdf"
        ),
    )


# ============================================================
# PROFIT & LOSS
# ============================================================

@router.get("/profit-loss")
async def get_profit_loss_report(
    from_date: date | None = None,
    to_date: date | None = None,
    company_name: str | None = Depends(get_authorized_company)
):
    if from_date and to_date and from_date > to_date:
        raise HTTPException(
            status_code=400,
            detail="from_date cannot be later than to_date",
        )

    try:
        report = await fetch_profit_loss(
            from_date=from_date,
            to_date=to_date,
            company_name=company_name,
        )

        return {
            "success": True,
            "source": "tally",
            # Two independent columns - Dr (left) and Cr (right) -
            # not a flat list, since P&L genuinely has two sides.
            "report": {
                "left": report.get("left", []),
                "right": report.get("right", []),
                "total_left": report.get("total_left", 0),
                "total_right": report.get("total_right", 0),
            },
        }

    except HTTPException:
        raise

    except Exception as e:
        print("Profit & Loss error:", repr(e))

        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Profit & Loss from Tally",
        )


@router.get("/profit-loss/export/{file_format}")
async def export_profit_loss_report(
    file_format: str,
    from_date: date | None = None,
    to_date: date | None = None,
    company_name: str | None = Depends(get_authorized_company)
):
    try:
        report = await fetch_profit_loss(
            from_date=from_date,
            to_date=to_date,
            company_name=company_name,
        )

    except Exception as e:
        print("Profit & Loss export error:", repr(e))

        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Profit & Loss from Tally",
        )

    return _export_response(
        file_format=file_format,
        title="Profit & Loss",
        columns=PROFIT_LOSS_COLUMNS,
        rows=_pl_rows_to_two_columns(report),
        company_name=company_name,
        filename_base="profit_and_loss",
        period=_period_label(from_date=from_date, to_date=to_date),
    )


# ============================================================
# GROUP SUMMARY (Profit & Loss / Balance Sheet drill-down)
# ============================================================

@router.get("/group-summary")
async def get_group_summary_report(
    group: str,
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
):
    """
    The screen Tally shows when you double-click a P&L/Balance Sheet
    group line (Direct Expenses, Indirect Expenses, Sales Accounts,
    Purchase Accounts, or any sub-group reached by drilling further,
    e.g. Office Exp). Each row is either another sub-group (drill
    again into /group-summary?group=<row.name>) or a ledger (drill
    into /ledger?ledger_name=<row.name>&view=monthly) - we mark
    which is which by checking the row name against the company's
    ledger list, since Tally's Group Summary XML doesn't flag it
    directly.
    """
    try:
        report = await fetch_group_summary(
            group_name=group,
            from_date=from_date,
            to_date=to_date,
            company_name=company_name,
        )

        try:
            ledgers = await fetch_ledger_list(company_name=company_name)
            ledger_names = {
                (l.get("name") or "").strip().casefold()
                for l in ledgers
                if l.get("name")
            }
        except Exception:
            # If the ledger list call fails, fall back to treating
            # every row as a group rather than breaking the page -
            # the row is still clickable, just drills one level
            # further into Group Summary instead of the ledger.
            ledger_names = set()

        rows = []
        for row in report.get("rows", []):
            is_ledger = (row.get("name") or "").strip().casefold() in ledger_names
            rows.append({**row, "is_ledger": is_ledger, "is_group": not is_ledger})

        return {
            "success": True,
            "source": "tally",
            "group_name": report.get("group_name", group),
            "report": rows,
            "total_debit": report.get("total_debit", 0),
            "total_credit": report.get("total_credit", 0),
        }

    except HTTPException:
        raise

    except Exception as e:
        print("Group Summary error:", repr(e))

        raise HTTPException(
            status_code=502,
            detail=f"Unable to fetch Group Summary for '{group}' from Tally",
        )


# ============================================================
# TRIAL BALANCE
# ============================================================

def _trial_balance_kwargs(
    company_name: str | None,
    from_date: date | None,
    to_date: date | None,
) -> dict:
    """
    Keyword arguments for fetch_trial_balance().

    from_date is only forwarded when the caller actually supplied
    one, so a request without a From Date behaves exactly as it did
    before the From/To filter was added.
    """
    kwargs = {
        "company_name": company_name,
        "to_date": to_date,
    }

    if from_date:
        kwargs["from_date"] = from_date

    return kwargs


@router.get("/trial-balance")
async def get_trial_balance_report(
    company_name: str | None = Depends(get_authorized_company),
    to_date: date | None = None,
    from_date: date | None = None,
):
    if from_date and to_date and from_date > to_date:
        raise HTTPException(
            status_code=400,
            detail="from_date cannot be later than to_date",
        )

    try:
        report = await fetch_trial_balance(
            **_trial_balance_kwargs(
                company_name, from_date, to_date
            )
        )

        return {
            "success": True,
            "source": "tally",
            "from_date": from_date.isoformat() if from_date else None,
            "to_date": to_date.isoformat() if to_date else None,
            "report": _as_rows(report),
        }

    except Exception as e:
        print("Trial Balance error:", repr(e))

        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Trial Balance from Tally",
        )


@router.get("/trial-balance/export/{file_format}")
async def export_trial_balance_report(
    file_format: str,
    company_name: str | None = Depends(get_authorized_company),
    to_date: date | None = None,
    from_date: date | None = None,
):
    if from_date and to_date and from_date > to_date:
        raise HTTPException(
            status_code=400,
            detail="from_date cannot be later than to_date",
        )

    try:
        report = await fetch_trial_balance(
            **_trial_balance_kwargs(
                company_name, from_date, to_date
            )
        )

    except Exception as e:
        print("Trial Balance export error:", repr(e))

        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Trial Balance from Tally",
        )

    rows = _as_rows(report)

    total_debit = sum(
        row.get("debit") or 0
        for row in rows
    )

    total_credit = sum(
        row.get("credit") or 0
        for row in rows
    )

    return _export_response(
        file_format=file_format,
        title="Trial Balance",
        columns=TRIAL_BALANCE_COLUMNS,
        rows=rows,
        company_name=company_name,
        filename_base="trial_balance",
        footer={
            "label": f"Total (Credit: {total_credit:,.2f})",
            "key": "debit",
            "value": total_debit,
        },
        period=_period_label(from_date=from_date, to_date=to_date),
    )


# ------------------------------------------------------------
# Trial Balance drill-down: Purchase Bills Pending
#
# Reached from Trial Balance -> Purchase Accounts -> Purchase Bills
# to Come. Tally's "Purchase Bills Pending" screen lists goods that
# have been received (Receipt Notes) but not yet billed, item by
# item. The rows are built from the company's real Receipt Note
# vouchers for the selected period, using the same voucher/stock
# parser the Stock Item Vouchers screen already uses.
# ------------------------------------------------------------

@router.get("/trial-balance/purchase-bills-pending")
async def get_trial_balance_purchase_bills_pending(
    company_name: str | None = Depends(get_authorized_company),
    from_date: date | None = None,
    to_date: date | None = None,
):
    if from_date and to_date and from_date > to_date:
        raise HTTPException(
            status_code=400,
            detail="from_date cannot be later than to_date",
        )

    try:
        report = await fetch_stock_movement(
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
        )

        rows = [
            {
                "date": row.get("date"),
                "tracking_number": row.get("voucher_number"),
                "voucher_type": row.get("voucher_type"),
                "stock_item": row.get("stock_item"),
                "party": row.get("party"),
                "quantity": row.get("quantity", 0),
                "rate": row.get("rate", 0),
                "value": row.get("amount", 0),
            }
            for row in report.get("rows", [])
            if "receipt note" in (row.get("voucher_type") or "").casefold()
        ]

        return {
            "success": True,
            "source": "tally",
            "report": rows,
            "count": len(rows),
            "total_value": sum(row["value"] or 0 for row in rows),
        }

    except HTTPException:
        raise

    except Exception as e:
        print("Trial Balance Purchase Bills Pending error:", repr(e))

        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Purchase Bills Pending from Tally",
        )


# ============================================================
# BALANCE SHEET
# ============================================================

@router.get("/balance-sheet")
async def get_balance_sheet_report(
    company_name: str | None = None,
    to_date: date | None = None,
):
    try:
        report = await fetch_balance_sheet(
            company_name=company_name,
            to_date=to_date,
        )

        return {
            "success": True,
            "source": "tally",
            "report": _as_rows(report),
        }

    except Exception as e:
        print("Balance Sheet error:", repr(e))

        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Balance Sheet from Tally",
        )


@router.get("/balance-sheet/export/{file_format}")
async def export_balance_sheet_report(
    file_format: str,
    company_name: str | None = None,
    to_date: date | None = None,
):
    try:
        report = await fetch_balance_sheet(
            company_name=company_name,
            to_date=to_date,
        )

    except Exception as e:
        print("Balance Sheet export error:", repr(e))

        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Balance Sheet from Tally",
        )

    return _export_response(
        file_format=file_format,
        title="Balance Sheet",
        columns=BALANCE_SHEET_COLUMNS,
        rows=_as_rows(report),
        company_name=company_name,
        filename_base="balance_sheet",
        period=_period_label(to_date=to_date),
    )


# ============================================================
# BILL ALLOCATIONS
# ============================================================

@router.get("/bill-allocations")
async def get_bill_allocations(
    company_name: str | None = None,
):
    try:
        bills = await fetch_bill_allocations(
            company_name=company_name,
        )

        return {
            "success": True,
            "source": "tally",
            "count": len(bills),
            "bills": bills,
        }

    except Exception as e:
        print("Bill allocations error:", repr(e))

        raise HTTPException(
            status_code=502,
            detail="Unable to fetch bill allocations from Tally",
        )


# ============================================================
# RECEIVABLES
# ============================================================

@router.get("/receivables")
async def get_receivables_report(
    company_name: str | None = None,
):
    try:
        tally_bills = await fetch_bills_receivable(
            company_name=company_name,
        )

        allocations = await fetch_bill_allocations(
            company_name=company_name,
        )

        outstanding = build_outstanding_summary(
            allocations
        )

        data = build_receivables_from_tally_report(
            tally_bills,
            outstanding,
        )

        return {
            "success": True,
            "source": "tally",
            "data": data,
        }

    except Exception as e:
        print("Receivables error:", repr(e))

        raise HTTPException(
            status_code=502,
            detail="Unable to fetch receivables from Tally",
        )


@router.get("/receivables/export/{file_format}")
async def export_receivables_report(
    file_format: str,
    company_name: str | None = None,
):
    try:
        tally_bills = await fetch_bills_receivable(
            company_name=company_name,
        )

        allocations = await fetch_bill_allocations(
            company_name=company_name,
        )

        outstanding = build_outstanding_summary(
            allocations
        )

        data = build_receivables_from_tally_report(
            tally_bills,
            outstanding,
        )

    except Exception as e:
        print("Receivables export error:", repr(e))

        raise HTTPException(
            status_code=502,
            detail="Unable to fetch receivables from Tally",
        )

    return _export_response(
        file_format=file_format,
        title="Receivables",
        columns=BILLS_COLUMNS,
        rows=data["bills"],
        company_name=company_name,
        filename_base="receivables",
        footer={
            "label": "Total Receivable",
            "key": "outstanding_amount",
            "value": data["total_receivable"],
        },
    )


# ============================================================
# PAYABLES
# ============================================================

@router.get("/payables")
async def get_payables_report(
    company_name: str | None = None,
):
    try:
        tally_bills = await fetch_bills_payable(
            company_name=company_name,
        )

        allocations = await fetch_bill_allocations(
            company_name=company_name,
        )

        outstanding = build_outstanding_summary(
            allocations
        )

        data = build_payables_from_tally_report(
            tally_bills,
            outstanding,
        )

        return {
            "success": True,
            "source": "tally",
            "data": data,
        }

    except Exception as e:
        print("Payables error:", repr(e))

        raise HTTPException(
            status_code=502,
            detail="Unable to fetch payables from Tally",
        )


@router.get("/payables/export/{file_format}")
async def export_payables_report(
    file_format: str,
    company_name: str | None = None,
):
    try:
        tally_bills = await fetch_bills_payable(
            company_name=company_name,
        )

        allocations = await fetch_bill_allocations(
            company_name=company_name,
        )

        outstanding = build_outstanding_summary(
            allocations
        )

        data = build_payables_from_tally_report(
            tally_bills,
            outstanding,
        )

    except Exception as e:
        print("Payables export error:", repr(e))

        raise HTTPException(
            status_code=502,
            detail="Unable to fetch payables from Tally",
        )

    return _export_response(
        file_format=file_format,
        title="Payables",
        columns=BILLS_COLUMNS,
        rows=data["bills"],
        company_name=company_name,
        filename_base="payables",
        footer={
            "label": "Total Payable",
            "key": "outstanding_amount",
            "value": data["total_payable"],
        },
    )


# ============================================================
# LEDGER LIST
# ============================================================

@router.get("/ledgers")
async def get_ledger_list(
    company_name: str | None = Depends(get_authorized_company)
):
    try:
        ledgers = await fetch_ledger_list(
            company_name=company_name,
        )

        return {
            "success": True,
            "source": "tally",
            "count": len(ledgers),
            "ledgers": ledgers,
        }

    except Exception as e:
        print("Ledger list error:", repr(e))

        raise HTTPException(
            status_code=502,
            detail="Unable to fetch ledger list from Tally",
        )


# ============================================================
# LEDGER REPORT
# ============================================================

@router.get("/ledger")
async def get_ledger_report(
    ledger_name: str,
    company_name: str | None = Depends(get_authorized_company),
    from_date: date | None = None,
    to_date: date | None = None,
):
    if from_date and to_date and from_date > to_date:
        raise HTTPException(
            status_code=400,
            detail="from_date cannot be later than to_date",
        )

    try:
        print("\n")
        print("==========================================")
        print("LEDGER REPORT REQUEST")
        print("==========================================")
        print("Ledger    :", ledger_name)
        print("Company   :", company_name)
        print("From Date :", from_date)
        print("To Date   :", to_date)
        print("==========================================")

        report = await fetch_ledger_report(
            ledger_name=ledger_name,
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
        )

        print("LEDGER REPORT SUCCESS")
        print("Entries:", len(report.get("entries", [])))
        print("==========================================")
        print()

        return {
            "success": True,
            "source": "tally",
            "report": report,
        }

    except HTTPException:
        raise

    except Exception as e:
        import traceback

        print("\n")
        print("========== LEDGER REPORT ERROR ==========")
        print("Ledger       :", ledger_name)
        print("Company      :", company_name)
        print("From Date    :", from_date)
        print("To Date      :", to_date)
        print("Error        :", repr(e))
        print("\nTRACEBACK:")
        traceback.print_exc()
        print("========== END LEDGER REPORT ERROR ==========")
        print()

        raise HTTPException(
            status_code=502,
            detail=(
                f"Unable to fetch ledger "
                f"'{ledger_name}' from Tally: {str(e)}"
            ),
        )


# ============================================================
# LEDGER EXPORT
# ============================================================

@router.get("/ledger/export/{file_format}")
async def export_ledger_report(
    file_format: str,
    ledger_name: str,
    company_name: str | None = Depends(get_authorized_company),
    from_date: date | None = None,
    to_date: date | None = None,
):
    if from_date and to_date and from_date > to_date:
        raise HTTPException(
            status_code=400,
            detail="from_date cannot be later than to_date",
        )

    try:
        report = await fetch_ledger_report(
            ledger_name=ledger_name,
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
        )

    except Exception as e:
        import traceback

        print("\n========== LEDGER EXPORT ERROR ==========")
        print("Ledger :", ledger_name)
        print("Error  :", repr(e))
        traceback.print_exc()
        print("========== END LEDGER EXPORT ERROR ==========\n")

        raise HTTPException(
            status_code=502,
            detail=(
                f"Unable to fetch ledger "
                f"'{ledger_name}' from Tally: {str(e)}"
            ),
        )

    opening_balance = report.get(
        "opening_balance",
        0
    ) or 0

    opening_row = {
        "date": "",
        "particulars": "Opening Balance",
        "voucher_type": "",
        "voucher_number": "",
        "debit": (
            opening_balance
            if opening_balance > 0
            else 0
        ),
        "credit": (
            abs(opening_balance)
            if opening_balance < 0
            else 0
        ),
        "running_balance": opening_balance,
        "diff_in_tax_amount": 0,
        "balance_after_diff_in_tax": opening_balance,
        "status": "",
        "reference_number": "",
        "narration": "",
    }

    rows = [
        opening_row
    ] + report.get("entries", [])

    return _export_response(
        file_format=file_format,
        title=f"Ledger: {ledger_name}",
        columns=LEDGER_COLUMNS,
        rows=rows,
        company_name=company_name,
        filename_base=(
            f"{ledger_name.strip()}"
            .replace(" ", "_")
            .replace("/", "-")
            + "_ledger"
        ),
        footer={
            "label": "Closing Balance",
            "key": "running_balance",
            "value": report.get(
                "closing_balance"
            ),
        },
        period=_period_label(from_date=from_date, to_date=to_date),
    )


# ============================================================
# VOUCHER DETAIL (drill-down from a Ledger transaction row)
# ============================================================

@router.get("/voucher")
async def get_voucher_detail(
    voucher_type: str,
    voucher_number: str,
    date: date | None = None,
    ledger_name: str | None = None,
    company_name: str | None = None,
):
    """
    Full accounting voucher (every ledger allocation, narration,
    reference) for one transaction - what you land on when you
    click a row in a Ledger report, matching Tally's own
    "Accounting Voucher Alteration" screen.

    ledger_name is optional context: when supplied, the response
    marks which ledger line is the one the user drilled in from, so
    the frontend can show it as "Account" the way Tally does, with
    the other ledger line(s) as "Particulars".
    """

    try:
        print("\n==========================================")
        print("VOUCHER DETAIL REQUEST")
        print("==========================================")
        print("Voucher Type :", voucher_type)
        print("Voucher No.  :", voucher_number)
        print("Date         :", date)
        print("Ledger       :", ledger_name)
        print("Company      :", company_name)
        print("==========================================")

        vouchers = await fetch_voucher_detail(
            voucher_type=voucher_type,
            voucher_number=voucher_number,
            voucher_date=date,
            company_name=company_name,
        )

        if not vouchers:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Voucher '{voucher_type} {voucher_number}' "
                    f"was not found in Tally."
                ),
            )

        voucher = vouchers[0]

        if ledger_name:
            target = ledger_name.strip().casefold()

            for entry in voucher.get("entries", []):
                entry["is_selected_ledger"] = (
                    (entry.get("ledger_name") or "")
                    .strip()
                    .casefold()
                    == target
                )

        print("VOUCHER DETAIL SUCCESS")
        print("Entries:", len(voucher.get("entries", [])))
        print("==========================================\n")

        return {
            "success": True,
            "source": "tally",
            "voucher": voucher,
        }

    except HTTPException:
        raise

    except Exception as e:
        import traceback

        print("\n========== VOUCHER DETAIL ERROR ==========")
        print("Voucher Type :", voucher_type)
        print("Voucher No.  :", voucher_number)
        print("Error        :", repr(e))
        traceback.print_exc()
        print("========== END VOUCHER DETAIL ERROR ==========\n")

        raise HTTPException(
            status_code=502,
            detail=(
                f"Unable to fetch voucher "
                f"'{voucher_type} {voucher_number}' from Tally: {str(e)}"
            ),
        )


# ============================================================
# PENDING INVOICES
# ============================================================

@router.get("/pending-invoices")
async def get_pending_invoices_report(
    company_name: str | None = None,
):
    try:
        receivable_bills = await fetch_bills_receivable(
            company_name=company_name,
        )

        payable_bills = await fetch_bills_payable(
            company_name=company_name,
        )

        allocations = await fetch_bill_allocations(
            company_name=company_name,
        )

        outstanding = build_outstanding_summary(
            allocations
        )

        receivables_data = (
            build_receivables_from_tally_report(
                receivable_bills,
                outstanding,
            )
        )

        payables_data = (
            build_payables_from_tally_report(
                payable_bills,
                outstanding,
            )
        )

        data = build_pending_invoices_from_reports(
            receivables_data,
            payables_data,
        )

        return {
            "success": True,
            "source": "tally",
            "data": data,
        }

    except Exception as e:
        print("Pending invoices error:", repr(e))

        raise HTTPException(
            status_code=502,
            detail="Unable to fetch pending invoices from Tally",
        )


@router.get("/pending-invoices/export/{file_format}")
async def export_pending_invoices_report(
    file_format: str,
    company_name: str | None = None,
):
    try:
        receivable_bills = await fetch_bills_receivable(
            company_name=company_name,
        )

        payable_bills = await fetch_bills_payable(
            company_name=company_name,
        )

        allocations = await fetch_bill_allocations(
            company_name=company_name,
        )

        outstanding = build_outstanding_summary(
            allocations
        )

        receivables_data = (
            build_receivables_from_tally_report(
                receivable_bills,
                outstanding,
            )
        )

        payables_data = (
            build_payables_from_tally_report(
                payable_bills,
                outstanding,
            )
        )

        data = build_pending_invoices_from_reports(
            receivables_data,
            payables_data,
        )

    except Exception as e:
        print("Pending invoices export error:", repr(e))

        raise HTTPException(
            status_code=502,
            detail="Unable to fetch pending invoices from Tally",
        )

    return _export_response(
        file_format=file_format,
        title="Pending Invoices",
        columns=PENDING_INVOICES_COLUMNS,
        rows=data["invoices"],
        company_name=company_name,
        filename_base="pending_invoices",
    )


# ============================================================
# STOCK & INVENTORY
# ============================================================
#
# These endpoints back the "Stock" section of the app:
#   Stock -> Stock Summary
#   Inventory:
#     1. Stock Item     -> List of Stock Items -> Stock Monthly Summary
#     2. Location        -> Select Location -> Location Summary
#                            -> Location Monthly Summary
#     3. Stock Group     -> Stock Group Summary -> Stock Monthly Summary
#
# All data is fetched live from the Tally server via app.tally.service
# (which in turn uses the same TallyClient/XML pipeline as every other
# report in this file) - nothing here is hardcoded.


def _stock_summary_row(row: dict) -> dict:
    """
    Normalize a parse_stock_summary()/parse_stock_group_items() row
    (name, parent, base_units, opening_quantity, opening_value,
    closing_quantity, closing_value, rate) into the field names the
    Stock Summary / Stock Item / Stock Group Items tables use.
    """
    return {
        "stock_item": row.get("name"),
        "stock_group": row.get("parent"),
        "unit": row.get("base_units"),
        "opening_quantity": row.get("opening_quantity", 0),
        "opening_value": row.get("opening_value", 0),
        "closing_quantity": row.get("closing_quantity", 0),
        "closing_rate": row.get("rate", 0),
        "closing_value": row.get("closing_value", 0),
    }


def _stock_group_row(row: dict) -> dict:
    return {
        "stock_group": row.get("name"),
        "parent": row.get("parent"),
        "base_units": row.get("base_units"),
    }


def _stock_category_row(row: dict) -> dict:
    return {
        "stock_category": row.get("name"),
        "parent": row.get("parent"),
    }


def _godown_row(row: dict) -> dict:
    return {
        "godown": row.get("name"),
        "parent": row.get("parent"),
        "is_internal": row.get("is_internal"),
    }


def _stock_movement_row(row: dict) -> dict:
    quantity = row.get("quantity", 0) or 0
    return {
        **row,
        "value": row.get("amount", 0),
        "direction": "Inward" if quantity >= 0 else "Outward",
    }


def _stock_valuation_row(row: dict) -> dict:
    return {
        "stock_item": row.get("name"),
        "unit": row.get("base_units"),
        "closing_quantity": row.get("quantity", 0),
        "valuation_rate": row.get("rate", 0),
        "valuation_value": row.get("value", 0),
    }


@router.get("/stock-summary")
async def get_stock_summary_report(
    company_name: str | None = Depends(get_authorized_company),
    to_date: date | None = None,
):
    try:
        report = await fetch_stock_summary(
            company_name=company_name,
            to_date=to_date,
        )

        rows = [_stock_summary_row(r) for r in report.get("rows", [])]

        return {
            "success": True,
            "source": "tally",
            "report": rows,
            "count": len(rows),
        }

    except Exception as e:
        print("Stock Summary error:", repr(e))
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Stock Summary from Tally",
        )


@router.get("/stock-summary/export/{file_format}")
async def export_stock_summary_report(
    file_format: str,
    company_name: str | None = Depends(get_authorized_company),
    to_date: date | None = None,
):
    try:
        report = await fetch_stock_summary(
            company_name=company_name,
            to_date=to_date,
        )
        rows = [_stock_summary_row(r) for r in report.get("rows", [])]
    except Exception as e:
        print("Stock Summary export error:", repr(e))
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Stock Summary from Tally",
        )

    total_value = sum(row.get("closing_value") or 0 for row in rows)

    return _export_response(
        file_format=file_format,
        title="Stock Summary",
        columns=STOCK_SUMMARY_COLUMNS,
        rows=rows,
        company_name=company_name,
        filename_base="stock_summary",
        footer={
            "label": "Total Closing Value",
            "key": "closing_value",
            "value": total_value,
        },
        period=_period_label(to_date=to_date),
    )


# ------------------------------------------------------------------
# Stock Item (single item detail - used to seed "opening balance"
# for the Stock Item Monthly Summary screen)
# ------------------------------------------------------------------

@router.get("/stock-item")
async def get_stock_item_report(
    stock_item_name: str,
    company_name: str | None = Depends(get_authorized_company),
    from_date: date | None = None,
    to_date: date | None = None,
):
    try:
        report = await fetch_stock_item(
            company_name=company_name,
            stock_item_name=stock_item_name,
            from_date=from_date,
            to_date=to_date,
        )

        rows = [_stock_summary_row(r) for r in report.get("rows", [])]

        return {
            "success": True,
            "source": "tally",
            "report": rows,
            "item": rows[0] if rows else None,
        }

    except Exception as e:
        print("Stock Item error:", repr(e))
        raise HTTPException(
            status_code=502,
            detail=f"Unable to fetch stock item '{stock_item_name}' from Tally",
        )


# ------------------------------------------------------------------
# Stock Group Summary (list) + Stock Group Items (drill-down)
# ------------------------------------------------------------------

@router.get("/stock-groups")
async def get_stock_groups_report(
    company_name: str | None = Depends(get_authorized_company),
):
    try:
        report = await fetch_stock_groups(company_name=company_name)
        rows = [_stock_group_row(r) for r in report.get("rows", [])]

        return {
            "success": True,
            "source": "tally",
            "report": rows,
            "count": len(rows),
        }

    except Exception as e:
        print("Stock Groups error:", repr(e))
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Stock Group Summary from Tally",
        )


@router.get("/stock-groups/export/{file_format}")
async def export_stock_groups_report(
    file_format: str,
    company_name: str | None = Depends(get_authorized_company),
):
    try:
        report = await fetch_stock_groups(company_name=company_name)
        rows = [_stock_group_row(r) for r in report.get("rows", [])]
    except Exception as e:
        print("Stock Groups export error:", repr(e))
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Stock Group Summary from Tally",
        )

    return _export_response(
        file_format=file_format,
        title="Stock Group Summary",
        columns=STOCK_GROUP_COLUMNS,
        rows=rows,
        company_name=company_name,
        filename_base="stock_group_summary",
    )


@router.get("/stock-group-items")
async def get_stock_group_items_report(
    group: str,
    company_name: str | None = Depends(get_authorized_company),
    to_date: date | None = None,
):
    """
    Stock items that belong to a single Stock Group - what Tally
    shows when you drill into a group from Stock Group Summary.
    """
    try:
        report = await fetch_stock_group_items(
            group_name=group,
            company_name=company_name,
            to_date=to_date,
        )

        rows = [_stock_summary_row(r) for r in report.get("rows", [])]

        return {
            "success": True,
            "source": "tally",
            "group_name": group,
            "report": rows,
            "count": len(rows),
        }

    except Exception as e:
        print("Stock Group Items error:", repr(e))
        raise HTTPException(
            status_code=502,
            detail=f"Unable to fetch items for stock group '{group}' from Tally",
        )


@router.get("/stock-group-items/export/{file_format}")
async def export_stock_group_items_report(
    file_format: str,
    group: str,
    company_name: str | None = Depends(get_authorized_company),
    to_date: date | None = None,
):
    try:
        report = await fetch_stock_group_items(
            group_name=group,
            company_name=company_name,
            to_date=to_date,
        )
        rows = [_stock_summary_row(r) for r in report.get("rows", [])]
    except Exception as e:
        print("Stock Group Items export error:", repr(e))
        raise HTTPException(
            status_code=502,
            detail=f"Unable to fetch items for stock group '{group}' from Tally",
        )

    return _export_response(
        file_format=file_format,
        title=f"Stock Group: {group}",
        columns=STOCK_SUMMARY_COLUMNS,
        rows=rows,
        company_name=company_name,
        filename_base=f"stock_group_{group.strip().replace(' ', '_')}",
        period=_period_label(to_date=to_date),
    )


# ------------------------------------------------------------------
# Stock Categories
# ------------------------------------------------------------------

@router.get("/stock-categories")
async def get_stock_categories_report(
    company_name: str | None = Depends(get_authorized_company),
):
    try:
        report = await fetch_stock_categories(company_name=company_name)
        rows = [_stock_category_row(r) for r in report.get("rows", [])]

        return {
            "success": True,
            "source": "tally",
            "report": rows,
            "count": len(rows),
        }

    except Exception as e:
        print("Stock Categories error:", repr(e))
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Stock Category Summary from Tally",
        )


@router.get("/stock-categories/export/{file_format}")
async def export_stock_categories_report(
    file_format: str,
    company_name: str | None = Depends(get_authorized_company),
):
    try:
        report = await fetch_stock_categories(company_name=company_name)
        rows = [_stock_category_row(r) for r in report.get("rows", [])]
    except Exception as e:
        print("Stock Categories export error:", repr(e))
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Stock Category Summary from Tally",
        )

    return _export_response(
        file_format=file_format,
        title="Stock Category Summary",
        columns=STOCK_CATEGORY_COLUMNS,
        rows=rows,
        company_name=company_name,
        filename_base="stock_category_summary",
    )


# ------------------------------------------------------------------
# Locations (Godowns)
# ------------------------------------------------------------------

@router.get("/godowns")
async def get_godowns_report(
    company_name: str | None = Depends(get_authorized_company),
):
    try:
        report = await fetch_godowns(company_name=company_name)
        rows = [_godown_row(r) for r in report.get("rows", [])]

        return {
            "success": True,
            "source": "tally",
            "report": rows,
            "count": len(rows),
        }

    except Exception as e:
        print("Locations error:", repr(e))
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Locations from Tally",
        )


@router.get("/godowns/export/{file_format}")
async def export_godowns_report(
    file_format: str,
    company_name: str | None = Depends(get_authorized_company),
):
    try:
        report = await fetch_godowns(company_name=company_name)
        rows = [_godown_row(r) for r in report.get("rows", [])]
    except Exception as e:
        print("Locations export error:", repr(e))
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Locations from Tally",
        )

    return _export_response(
        file_format=file_format,
        title="Locations",
        columns=GODOWN_COLUMNS,
        rows=rows,
        company_name=company_name,
        filename_base="locations",
    )


# ------------------------------------------------------------------
# Stock Movement - powers Stock Item Monthly Summary (stock_item_name),
# Stock Item Vouchers (stock_item_name + from/to = one month) and
# Location Summary / Location Monthly Summary (godown_name).
# ------------------------------------------------------------------

@router.get("/stock-movement")
async def get_stock_movement_report(
    company_name: str | None = Depends(get_authorized_company),
    from_date: date | None = None,
    to_date: date | None = None,
    stock_item_name: str | None = None,
    godown_name: str | None = None,
):
    if from_date and to_date and from_date > to_date:
        raise HTTPException(
            status_code=400,
            detail="from_date cannot be later than to_date",
        )

    try:
        report = await fetch_stock_movement(
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
            stock_item_name=stock_item_name,
            godown_name=godown_name,
        )

        rows = [_stock_movement_row(r) for r in report.get("rows", [])]

        return {
            "success": True,
            "source": "tally",
            "report": rows,
            "count": len(rows),
        }

    except HTTPException:
        raise

    except Exception as e:
        print("Stock Movement error:", repr(e))
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Stock Movement from Tally",
        )


@router.get("/stock-movement/export/{file_format}")
async def export_stock_movement_report(
    file_format: str,
    company_name: str | None = Depends(get_authorized_company),
    from_date: date | None = None,
    to_date: date | None = None,
    stock_item_name: str | None = None,
    godown_name: str | None = None,
):
    try:
        report = await fetch_stock_movement(
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
            stock_item_name=stock_item_name,
            godown_name=godown_name,
        )
        rows = [_stock_movement_row(r) for r in report.get("rows", [])]
    except Exception as e:
        print("Stock Movement export error:", repr(e))
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Stock Movement from Tally",
        )

    title = "Stock Movement"
    if stock_item_name:
        title = f"Stock Movement: {stock_item_name}"
    elif godown_name:
        title = f"Stock Movement: {godown_name}"

    return _export_response(
        file_format=file_format,
        title=title,
        columns=STOCK_MOVEMENT_COLUMNS,
        rows=rows,
        company_name=company_name,
        filename_base="stock_movement",
        period=_period_label(from_date=from_date, to_date=to_date),
    )


# ------------------------------------------------------------------
# Stock Valuation / Negative Stock (additional reports already
# wired into the Inventory Books screen)
# ------------------------------------------------------------------

@router.get("/stock-valuation")
async def get_stock_valuation_report(
    company_name: str | None = Depends(get_authorized_company),
    to_date: date | None = None,
):
    try:
        report = await fetch_stock_valuation(
            company_name=company_name,
            to_date=to_date,
        )
        rows = [_stock_valuation_row(r) for r in report.get("rows", [])]

        return {
            "success": True,
            "source": "tally",
            "report": rows,
            "count": len(rows),
        }

    except Exception as e:
        print("Stock Valuation error:", repr(e))
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Stock Valuation from Tally",
        )


@router.get("/stock-valuation/export/{file_format}")
async def export_stock_valuation_report(
    file_format: str,
    company_name: str | None = Depends(get_authorized_company),
    to_date: date | None = None,
):
    try:
        report = await fetch_stock_valuation(
            company_name=company_name,
            to_date=to_date,
        )
        rows = [_stock_valuation_row(r) for r in report.get("rows", [])]
    except Exception as e:
        print("Stock Valuation export error:", repr(e))
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Stock Valuation from Tally",
        )

    total_value = sum(row.get("valuation_value") or 0 for row in rows)

    return _export_response(
        file_format=file_format,
        title="Stock Valuation",
        columns=STOCK_VALUATION_COLUMNS,
        rows=rows,
        company_name=company_name,
        filename_base="stock_valuation",
        footer={
            "label": "Total Valuation",
            "key": "valuation_value",
            "value": total_value,
        },
        period=_period_label(to_date=to_date),
    )


@router.get("/negative-stock")
async def get_negative_stock_report(
    company_name: str | None = Depends(get_authorized_company),
    to_date: date | None = None,
):
    try:
        report = await fetch_negative_stock(
            company_name=company_name,
            to_date=to_date,
        )
        rows = [_stock_summary_row(r) for r in report.get("rows", [])]

        return {
            "success": True,
            "source": "tally",
            "report": rows,
            "count": len(rows),
        }

    except Exception as e:
        print("Negative Stock error:", repr(e))
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Negative Stock from Tally",
        )


@router.get("/negative-stock/export/{file_format}")
async def export_negative_stock_report(
    file_format: str,
    company_name: str | None = Depends(get_authorized_company),
    to_date: date | None = None,
):
    try:
        report = await fetch_negative_stock(
            company_name=company_name,
            to_date=to_date,
        )
        rows = [_stock_summary_row(r) for r in report.get("rows", [])]
    except Exception as e:
        print("Negative Stock export error:", repr(e))
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch Negative Stock from Tally",
        )

    return _export_response(
        file_format=file_format,
        title="Negative Stock",
        columns=NEGATIVE_STOCK_COLUMNS,
        rows=rows,
        company_name=company_name,
        filename_base="negative_stock",
        period=_period_label(to_date=to_date),
    )


# ============================================================
# INVENTORY BOOKS REGISTERS
# ============================================================

INVENTORY_REGISTER_COLUMNS = [
    {"key": "month", "label": "Particulars"},
    {"key": "total_vouchers", "label": "Total Vouchers"},
]

INVENTORY_REGISTERS = {
    "sales-orders": {"title": "Sales Orders Book", "voucher_type": "Sales Order", "filename": "sales_orders_book"},
    "purchase-orders": {"title": "Purchase Orders Book", "voucher_type": "Purchase Order", "filename": "purchase_orders_book"},
    "delivery-note": {"title": "Delivery Note Register", "voucher_type": "Delivery Note", "filename": "delivery_note_register"},
    "receipt-note": {"title": "Receipt Note Register", "voucher_type": "Receipt Note", "filename": "receipt_note_register"},
    "rejections-in": {"title": "Rejections In Register", "voucher_type": "Rejections In", "filename": "rejections_in_register"},
    "rejections-out": {"title": "Rejections Out Register", "voucher_type": "Rejections Out", "filename": "rejections_out_register"},
    "stock-journal": {"title": "Stock Transfer Journal Register", "voucher_type": "Stock Journal", "filename": "stock_transfer_journal_register"},
    "physical-stock": {"title": "Physical Stock Register", "voucher_type": "Physical Stock", "filename": "physical_stock_register"},
    "material-out": {"title": "Material Out Register", "voucher_type": "Material Out", "filename": "material_out_register"},
    "material-in": {"title": "Material In Register", "voucher_type": "Material In", "filename": "material_in_register"},
}


@router.get("/inventory-register/{register_key}")
async def get_inventory_register(
    register_key: str,
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
):
    register = INVENTORY_REGISTERS.get(register_key)
    if not register:
        raise HTTPException(status_code=404, detail="Unknown Inventory Books register")
    if from_date and to_date and from_date > to_date:
        raise HTTPException(status_code=400, detail="from_date cannot be later than to_date")

    try:
        report = await fetch_inventory_register(
            voucher_type=register["voucher_type"],
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
        )
        return {
            "success": True,
            "source": "tally",
            "report_name": register["title"],
            "count": len(report["report"]),
            "report": report["report"],
            "grand_total": report["grand_total"],
            "grand_total_cancelled": report["grand_total_cancelled"],
        }
    except Exception as e:
        print(f'{register["title"]} error:', repr(e))
        raise HTTPException(status_code=502, detail=f'Unable to fetch {register["title"]} from Tally')


@router.get("/inventory-register/{register_key}/export/{file_format}")
async def export_inventory_register(
    register_key: str,
    file_format: str,
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
):
    register = INVENTORY_REGISTERS.get(register_key)
    if not register:
        raise HTTPException(status_code=404, detail="Unknown Inventory Books register")
    if from_date and to_date and from_date > to_date:
        raise HTTPException(status_code=400, detail="from_date cannot be later than to_date")

    try:
        result = await fetch_inventory_register(
            voucher_type=register["voucher_type"],
            company_name=company_name,
            from_date=from_date,
            to_date=to_date,
        )
    except Exception as e:
        print(f'{register["title"]} export error:', repr(e))
        raise HTTPException(status_code=502, detail=f'Unable to fetch {register["title"]} from Tally')

    return _export_response(
        file_format=file_format,
        title=register["title"],
        columns=INVENTORY_REGISTER_COLUMNS,
        rows=result["report"],
        company_name=company_name,
        filename_base=register["filename"],
        period=_period_label(from_date=from_date, to_date=to_date),
    )