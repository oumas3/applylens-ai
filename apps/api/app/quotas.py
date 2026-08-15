"""Configurable per-account storage limits for the free public beta."""

from typing import Literal

from fastapi import HTTPException, status

from app.config import get_settings


QuotaResource = Literal["document", "opportunity", "review", "task"]


def enforce_account_quota(resource: QuotaResource, resulting_count: int) -> None:
    settings = get_settings()
    limit = int(getattr(settings, f"free_beta_{resource}_limit"))
    if resulting_count > limit:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Free beta {resource} limit reached ({limit}). "
                f"Delete an existing {resource} before adding another."
            ),
        )
