from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.security.auth import (
    UserContext,
    get_current_user,
)
from app.tally.client import TallyClient
from app.tally.service import (
    fetch_bill_allocations,
    fetch_bills_receivable,
    fetch_companies,
    fetch_companies_result,
)


from app.cache.config import is_force_refresh

router = APIRouter()

tally_client = TallyClient()


def _is_force_refresh(force_refresh: Any, refresh: Any) -> bool:
    return is_force_refresh(force_refresh=force_refresh, refresh=refresh)


def _resolve_org_id(current_user: UserContext) -> str:
    user_id = getattr(current_user, "user_id", None)

    if not user_id:
        raise HTTPException(
            status_code=500,
            detail="Unable to resolve authenticated user organization.",
        )

    try:
        from app.security.user_store import get_user_organization_id

        organization_id = get_user_organization_id(str(user_id))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Unable to resolve authenticated user organization.",
        )

    if not organization_id:
        raise HTTPException(
            status_code=500,
            detail="Unable to resolve authenticated user organization.",
        )

    return str(organization_id)


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
    force_refresh: bool = Query(default=False),
    refresh: str | int | None = Query(default=None),
):
    """
    Return only the Tally companies that the authenticated user
    is allowed to access.

    Company data is cached per organization. Authorization filtering
    is always applied after retrieving the cached Tally company list.
    """
    try:
        effective_org_id = _resolve_org_id(current_user)

        is_force = _is_force_refresh(
            force_refresh=force_refresh,
            refresh=refresh,
        )

        cache_result = await fetch_companies_result(
            force_refresh=is_force,
            org_id=effective_org_id,
        )

        companies = cache_result.data

        # Apply authorization AFTER retrieving company data.
        # Redis never decides what the user is allowed to access.
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
                if company.get("name", "").casefold() in allowed_lookup
            ]

        return {
            "success": True,
            "source": cache_result.source,
            "companies": allowed_companies,
            "cached_at": cache_result.cached_at,
            "is_stale": cache_result.is_stale,
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Unable to fetch companies from Tally: {exc}",
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

        effective_org_id = _resolve_org_id(current_user)

        data = await fetch_bills_receivable(
            company_name=company_name,
            org_id=effective_org_id,
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