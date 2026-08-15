"""Request-level helpers for persistent abuse controls."""

from typing import Literal

from fastapi import HTTPException, Request, status

from app.config import get_settings
from app.services.rate_limit_service import RateLimitService


RateLimitAction = Literal[
    "registration",
    "password_reset",
    "document_upload",
    "opportunity_ingest",
    "opportunity_analysis",
]


def client_identity(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def enforce_rate_limit(action: RateLimitAction, identity: str) -> None:
    settings = get_settings()
    configured_limit = int(getattr(settings, f"{action}_rate_limit"))
    service = RateLimitService(
        settings.auth_database_path,
        settings.database_url,
    )
    retry_after = service.consume(
        service.limit_key(action, identity),
        limit=configured_limit,
        window_seconds=settings.rate_limit_window_seconds,
    )
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )
