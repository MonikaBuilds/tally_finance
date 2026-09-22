from fastapi import APIRouter, Depends, HTTPException

from app.tally.service import (
    fetch_profit_loss,
    fetch_bill_allocations,
    fetch_bills_receivable,
    fetch_bills_payable,
)

from app.financial.service import (
    build_outstanding_summary,
    build_receivables_from_tally_report,
    build_payables_from_tally_report,
    build_pending_invoices_from_reports,
)

from app.financial.calculations import (
    build_dashboard_financials,
)

from app.security.auth import (
    get_authorized_company,
)


router = APIRouter()


@router.get("/summary")
async def get_dashboard_summary(
    company_name: str | None = Depends(get_authorized_company),
):
    try:
        profit_loss = await fetch_profit_loss(
            company_name=company_name,
        )

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
            allocations,
        )

        receivables = build_receivables_from_tally_report(
            receivable_bills,
            outstanding,
        )

        payables = build_payables_from_tally_report(
            payable_bills,
            outstanding,
        )

        pending = build_pending_invoices_from_reports(
            receivables,
            payables,
        )

        summary = build_dashboard_financials(
            profit_loss=profit_loss,
            receivables=receivables,
            payables=payables,
            pending_invoices=pending,
        )

        return {
            "success": True,
            "source": "tally",
            "data": summary,
        }

    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Unable to build dashboard summary from Tally",
        )