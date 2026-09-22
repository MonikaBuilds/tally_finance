from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)

from app.chatbot.concurrency_limiter import (
    user_concurrency_limiter,
)
from app.chatbot.rate_limiter import chat_rate_limiter
from app.chatbot.schemas import (
    ChatRequest,
    ChatResponse,
)
from app.chatbot.service import process_chat_message
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

        # Process the user's financial question only after
        # authentication, rate limiting and company authorization pass.
        result = await process_chat_message(
            message=request.message,
            company_name=company_name,
            allowed_companies=current_user.allowed_companies,
            user_id=current_user.user_id,
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
        )

    except HTTPException:
        # Preserve expected API errors such as
        # 401, 403 and 429 responses.
        raise

    except Exception:
        # Do not expose internal Tally, Gemini or server errors
        # directly to the frontend.
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