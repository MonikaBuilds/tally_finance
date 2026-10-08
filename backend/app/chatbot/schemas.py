from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(
        min_length=1,
        max_length=1000
    )

    company_name: str | None = Field(
        default=None,
        max_length=200
    )

    force_refresh: bool = Field(
        default=False
    )


class ChatResponse(BaseModel):
    success: bool
    answer: str
    intent: str | None = None
    source: str | None = None
    data: dict[str, Any] | None = None
    cached_at: str | None = None
    is_stale: bool = False