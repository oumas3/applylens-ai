from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.config import get_settings
from app.routers import documents as documents_router
from app.routers import opportunities as opportunities_router
from app.routers import reviews as reviews_router
from app.routers import tasks as tasks_router
from app.routers import profiles as profiles_router
from app.routers.auth import (
    SESSION_COOKIE,
    get_auth_service,
    get_current_user,
)


router = APIRouter(
    prefix="/api/v1/account",
    tags=["account"],
    dependencies=[Depends(get_current_user)],
)


class PrivacyPreferenceRequest(BaseModel):
    external_ai_consent: bool


class PrivacyPreferenceResponse(BaseModel):
    external_ai_consent: bool
    external_ai_configured: bool
    external_ai_provider: str | None


class AccountDeletionRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    current_password: str = Field(..., min_length=1, max_length=128)
    confirmation: Literal["DELETE"]


class AccountExportResponse(BaseModel):
    schema_version: Literal["1.1"] = "1.1"
    exported_at: datetime
    account: dict[str, Any]
    documents: list[dict[str, Any]]
    opportunities: list[dict[str, Any]]
    reviews: list[dict[str, Any]]
    tasks: list[dict[str, Any]]
    profile: dict[str, Any] | None


def _privacy_response(consent: bool) -> PrivacyPreferenceResponse:
    settings = get_settings()
    configured = settings.retrieval_provider == "openai"
    return PrivacyPreferenceResponse(
        external_ai_consent=consent,
        external_ai_configured=configured,
        external_ai_provider="OpenAI" if configured else None,
    )


@router.get("/privacy", response_model=PrivacyPreferenceResponse)
def get_privacy_preference(
    user: dict[str, str | bool] = Depends(get_current_user),
) -> PrivacyPreferenceResponse:
    return _privacy_response(bool(user.get("external_ai_consent", False)))


@router.put("/privacy", response_model=PrivacyPreferenceResponse)
def update_privacy_preference(
    request: PrivacyPreferenceRequest,
    user: dict[str, str | bool] = Depends(get_current_user),
) -> PrivacyPreferenceResponse:
    if not get_auth_service().set_external_ai_consent(
        str(user["id"]),
        request.external_ai_consent,
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found.",
        )
    return _privacy_response(request.external_ai_consent)


@router.get("/export", response_model=AccountExportResponse)
def export_account_data(
    response: Response,
    user: dict[str, str | bool] = Depends(get_current_user),
) -> AccountExportResponse:
    user_id = str(user["id"])
    account = get_auth_service().get_account(user_id)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found.",
        )

    exported_documents: list[dict[str, Any]] = []
    for document in documents_router.documents.values():
        if document.user_id != user_id:
            continue
        try:
            content = documents_router.file_storage.read(document.stored_filename)
        except OSError as error:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="A stored document could not be included in the export.",
            ) from error
        exported_documents.append(
            {
                **document.model_dump(mode="json"),
                "sha256": hashlib.sha256(content).hexdigest(),
                "content_base64": base64.b64encode(content).decode("ascii"),
            }
        )

    response.headers["Content-Disposition"] = (
        'attachment; filename="applylens-account-export.json"'
    )
    response.headers["Cache-Control"] = "no-store"
    return AccountExportResponse(
        exported_at=datetime.now(timezone.utc),
        account=account,
        documents=exported_documents,
        opportunities=[
            item.model_dump(mode="json")
            for item in opportunities_router.ingested_opportunities
            if item.user_id == user_id
        ],
        reviews=[
            item.model_dump(mode="json")
            for item in reviews_router.reviews
            if item.user_id == user_id
        ],
        tasks=[
            item.model_dump(mode="json")
            for item in tasks_router.tasks
            if item.user_id == user_id
        ],
        profile=(
            profiles_router.profiles[user_id].model_dump(mode="json")
            if user_id in profiles_router.profiles
            else None
        ),
    )


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
def delete_account(
    request: AccountDeletionRequest,
    response: Response,
    user: dict[str, str | bool] = Depends(get_current_user),
) -> None:
    user_id = str(user["id"])
    service = get_auth_service()
    if not service.verify_user_password(user_id, request.current_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The current password is incorrect.",
        )

    owned_documents = [
        document
        for document in documents_router.documents.values()
        if document.user_id == user_id
    ]
    owned_opportunity_ids = {
        item.id
        for item in opportunities_router.ingested_opportunities
        if item.user_id == user_id
    }

    if not service.delete_user(user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found.",
        )

    for document in owned_documents:
        documents_router.documents.pop(document.id, None)
        documents_router.file_storage.delete(document.stored_filename)
    opportunities_router.ingested_opportunities[:] = [
        item
        for item in opportunities_router.ingested_opportunities
        if item.user_id != user_id
    ]
    for opportunity_id in owned_opportunity_ids:
        opportunities_router._retrieval_cache.pop(opportunity_id, None)
    reviews_router.reviews[:] = [
        item for item in reviews_router.reviews if item.user_id != user_id
    ]
    tasks_router.tasks[:] = [
        item for item in tasks_router.tasks if item.user_id != user_id
    ]
    profiles_router.profiles.pop(user_id, None)

    if not service.database_url:
        documents_router._persist_documents()
        opportunities_router._persist_opportunities()
        reviews_router._persist_reviews()
        tasks_router._persist_tasks()
        profiles_router._persist_profiles()

    response.delete_cookie(SESSION_COOKIE)
