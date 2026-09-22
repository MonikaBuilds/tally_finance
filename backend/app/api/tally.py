from fastapi import APIRouter, Depends, HTTPException
from datetime import date

from app.security.auth import (
    UserContext,
    get_current_user,
)
from app.tally.client import TallyClient
from app.tally.service import (
    fetch_bill_allocations,
    fetch_bills_receivable,
    fetch_companies,
)


router = APIRouter()

tally_client = TallyClient()


@router.get("/status")
async def tally_status(
    current_user: UserContext = Depends(get_current_user),
):
    """
    Check whether Tally is reachable.

    Authentication is required because Tally connection
    information should not be exposed to unauthenticated users.
    """
    result = await tally_client.check_connection()

    if result["connected"]:
        return {
            "connected": True,
            "message": "Tally is reachable",
            "status_code": result.get("status_code"),
        }

    return {
        "connected": False,
        "message": "Unable to connect to Tally",
    }


@router.get("/companies")
async def get_companies(
    current_user: UserContext = Depends(get_current_user),
):
    """
    Return only the Tally companies that the logged-in
    user is allowed to access.
    """
    try:
        companies = await fetch_companies()

        # Wildcard access is intended only for explicitly configured
        # development or admin-style users.
        if "*" in current_user.allowed_companies:
            allowed_companies = companies

        else:
            allowed_lookup = {
                company.casefold()
                for company in current_user.allowed_companies
            }

            allowed_companies = [
                company
                for company in companies
                if (
                    company.get("name", "").casefold()
                    in allowed_lookup
                )
            ]

        return {
            "success": True,
            "companies": allowed_companies,
        }

    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch companies from Tally",
        )


@router.get("/debug/receivables")
async def debug_receivables(
    company_name: str | None = None,
    current_user: UserContext = Depends(get_current_user),
):
    """
    Temporary endpoint used during development to check
    how long the Bills Receivable report takes in Tally.

    This bypasses the chatbot tool timeout so we can confirm
    whether the delay is coming directly from Tally.
    """
    try:
        # Do not allow a user to query a company that is
        # outside their permitted company list.
        if company_name:
            if "*" not in current_user.allowed_companies:
                allowed_lookup = {
                    company.casefold()
                    for company in current_user.allowed_companies
                }

                if company_name.casefold() not in allowed_lookup:
                    raise HTTPException(
                        status_code=403,
                        detail=(
                            "You are not authorized to access "
                            "this company."
                        ),
                    )

        data = await fetch_bills_receivable(
            company_name=company_name,
        )

        return {
            "success": True,
            "data": data,
        }

    except HTTPException:
        raise

    except Exception as exc:
        # Keep the actual error in the backend terminal
        # while we diagnose the Tally response-time issue.
        print(
            "RECEIVABLE DEBUG ERROR:",
            type(exc).__name__,
            str(exc),
        )

        raise HTTPException(
            status_code=502,
            detail="Unable to fetch receivables from Tally",
        )
        
@router.get("/debug/bill-allocations")
async def debug_bill_allocations(
    company_name: str | None = None,
    current_user: UserContext = Depends(get_current_user),
):
    """
    Temporary endpoint used to check whether Tally's
    bill allocation data can be loaded quickly.
    """
    try:
        # Keep company access protected even for debug endpoints.
        if company_name:
            if "*" not in current_user.allowed_companies:
                allowed_lookup = {
                    company.casefold()
                    for company in current_user.allowed_companies
                }

                if company_name.casefold() not in allowed_lookup:
                    raise HTTPException(
                        status_code=403,
                        detail="You are not authorized to access this company.",
                    )

        data = await fetch_bill_allocations(
            company_name=company_name,
        )

        return {
            "success": True,
            "count": len(data),
            "data": data,
        }

    except HTTPException:
        raise

    except Exception as exc:
        print(
            "BILL ALLOCATION DEBUG ERROR:",
            type(exc).__name__,
            str(exc),
        )

        raise HTTPException(
            status_code=502,
            detail="Unable to fetch bill allocations from Tally",
        )