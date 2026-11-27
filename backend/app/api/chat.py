import logging
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)

logger = logging.getLogger(__name__)

from app.chatbot.concurrency_limiter import (
    user_concurrency_limiter,
)
from app.chatbot.rate_limiter import chat_rate_limiter
from app.chatbot.schemas import (
    ChatRequest,
    ChatResponse,
)
from app.chatbot.service import process_chat_message
from app.chatbot.exports import load_export, export_excel
from app.security.permissions import can_execute_tool
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from uuid import UUID
from app.security.user_store import get_user_organization_id
from app.security.auth import (
    UserContext,
    authorize_company,
    get_current_user,
)


router = APIRouter()


@router.post(
    "/chat",
    response_model=ChatResponse,
)
async def chat(
    request: ChatRequest,
    current_user: UserContext = Depends(get_current_user),
):
    """
    Handle an authenticated chatbot request.

    The request is protected by:
    - per-user request rate limiting
    - per-user concurrent request limiting
    - company-level authorization
    """

    slot_acquired = False

    try:
        # Limit the total number of chatbot requests a user can make
        # within the configured time window.
        allowed = await chat_rate_limiter.allow(
            current_user.user_id
        )

        if not allowed:
            raise HTTPException(
                status_code=429,
                detail=(
                    "Too many chatbot requests. "
                    "Please wait a moment and try again."
                ),
            )

        # Prevent one user from running too many chatbot requests
        # at the same time and occupying shared Tally/Gemini capacity.
        slot_acquired = await user_concurrency_limiter.acquire(
            current_user.user_id
        )

        if not slot_acquired:
            raise HTTPException(
                status_code=429,
                detail=(
                    "You already have multiple chatbot requests running. "
                    "Please wait for one to finish."
                ),
            )

        # Make sure the logged-in user is allowed to access
        # the requested Tally company.
        company_name = authorize_company(
            user=current_user,
            requested_company=request.company_name,
        )

        # Resolve the organization from the validated token (or DB fallback).
        resolved_org = str(current_user.organization_id or get_user_organization_id(current_user.user_id) or "default") or "default"
        org_id = str(resolved_org)

        # Process the user's financial question only after
        # authentication, rate limiting and company authorization pass.
        result = await process_chat_message(
            message=request.message,
            company_name=company_name,
            allowed_companies=current_user.allowed_companies,
            user_id=current_user.user_id,
            org_id=org_id,
            force_refresh=getattr(request, "force_refresh", False),
            session_id=request.session_id,
        )

        return ChatResponse(
            success=result.get(
                "success",
                False,
            ),
            answer=result.get(
                "answer",
                "Unable to process the request.",
            ),
            intent=result.get("intent"),
            source=result.get("source"),
            data=result.get("data"),
            cached_at=result.get("cached_at"),
            is_stale=result.get("is_stale", False),
            session_id=result.get("session_id") or request.session_id,
            downloads=result.get("downloads") or [],
        )
    except HTTPException:
        # Preserve expected API errors such as
        # 401, 403 and 429 responses.
        raise

    except Exception as exc:
        # Do not expose internal Tally, Gemini or server errors
        # directly to the frontend, but record full trace for diagnostics.
        logger.exception("Unexpected error processing chat request: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to process the chatbot request."
            ),
        )

    finally:
        # Release the concurrency slot only when it was actually acquired.
        # This also runs when Tally, Gemini or another operation fails.
        if slot_acquired:
            await user_concurrency_limiter.release(
                current_user.user_id
            )

@router.get("/chat/exports/{token}.xlsx")
async def download_chat_excel(token: UUID, company_name: str, current_user: UserContext = Depends(get_current_user)):
    company = authorize_company(user=current_user, requested_company=company_name)
    org = str(current_user.organization_id or get_user_organization_id(current_user.user_id) or "default")
    record = await load_export(current_user.user_id, org, company, str(token))
    if record is None:
        raise HTTPException(status_code=410, detail="This Excel snapshot has expired or is unavailable in this account/company. Ask for the report again.")
    for included_company in (record.get("arguments") or {}).get("company_names", []):
        authorize_company(user=current_user, requested_company=included_company)
    permitted = await run_in_threadpool(can_execute_tool, current_user.user_id, record["tool_name"])
    if not permitted:
        raise HTTPException(status_code=403, detail="Your current permissions do not allow this report export.")
    content = await run_in_threadpool(export_excel, record)
    filename = "chat_" + record["tool_name"].removeprefix("get_") + ".xlsx"
    return Response(content=content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"})
