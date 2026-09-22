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

@router.get("/trial-balance")
async def get_trial_balance_report(
    company_name: str | None = Depends(get_authorized_company),
    to_date: date | None = None
):
    try:
        report = await fetch_trial_balance(
            company_name=company_name,
            to_date=to_date,
        )

        return {
            "success": True,
            "source": "tally",
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
    to_date: date | None = None
):
    try:
        report = await fetch_trial_balance(
            company_name=company_name,
            to_date=to_date,
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
        period=_period_label(to_date=to_date),
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