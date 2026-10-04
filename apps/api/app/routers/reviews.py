import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from app.routers.auth import get_current_user
from app.concurrency import guarded
from app.config import get_settings
from app.services.application_store import PostgresApplicationStore
from app.quotas import enforce_account_quota
from typing import Annotated, Literal

REVIEWS_FILE = Path(__file__).resolve().parents[2] / "storage" / "reviews.json"
settings = get_settings()
application_store = (
    PostgresApplicationStore(settings.database_url)
    if settings.database_url
    else None
)

router = APIRouter(
    prefix="/api/v1/reviews",
    tags=["reviews"],
    dependencies=[Depends(get_current_user)],
)
logger = logging.getLogger(__name__)

ReviewText = Annotated[str, StringConstraints(max_length=2_000)]


class OpportunityReview(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: int
    user_id: str | None = None
    title: str = Field(..., min_length=1, max_length=300)
    eligibility: Literal[
        "Eligible",
        "Not eligible",
        "Insufficient information",
        "Unclear",
        "Action required",
    ]
    matched_requirements: list[ReviewText] = Field(default_factory=list, max_length=100)
    missing_requirements: list[ReviewText] = Field(default_factory=list, max_length=100)
    deadline: str | None = Field(default=None, max_length=500)
    funding: str | None = Field(default=None, max_length=2_000)


class ReviewComparisonRequest(BaseModel):
    review_ids: list[int] = Field(default_factory=list, min_length=2, max_length=100)


class ReviewComparisonResponse(BaseModel):
    reviews: list[OpportunityReview]
    recommended_review_id: int | None = None


def _load_reviews() -> list[OpportunityReview]:
    if application_store is not None:
        try:
            application_store.load_reviews()
            return []
        except Exception:
            logger.exception("Unable to load reviews from PostgreSQL")
            raise RuntimeError("PostgreSQL reviews could not be loaded.")

    if not REVIEWS_FILE.exists():
        return []

    try:
        payload = json.loads(REVIEWS_FILE.read_text(encoding="utf-8"))
        return [OpportunityReview.model_validate(item) for item in payload]
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return []


def _persist_reviews(user_id: str | None = None) -> None:
    if application_store is not None:
        application_store.replace_reviews(
            (
                review.model_dump(mode="python")
                for review in reviews
                if user_id is None or review.user_id == user_id
            ),
            user_id=user_id,
        )
        return

    REVIEWS_FILE.parent.mkdir(parents=True, exist_ok=True)
    REVIEWS_FILE.write_text(
        json.dumps([review.model_dump(mode="json") for review in reviews], indent=2),
        encoding="utf-8",
    )


reviews: list[OpportunityReview] = _load_reviews()


def reviews_for_user(user_id: str) -> list[OpportunityReview]:
    if application_store is not None:
        return [
            OpportunityReview.model_validate(item)
            for item in application_store.load_reviews(user_id)
        ]
    return [review for review in reviews if review.user_id == user_id]


@router.get("", response_model=list[OpportunityReview], status_code=status.HTTP_200_OK)
def list_reviews(user: dict[str, str | bool] = Depends(get_current_user)) -> list[OpportunityReview]:
    return reviews_for_user(str(user["id"]))


@router.post("", response_model=OpportunityReview, status_code=status.HTTP_201_CREATED)
def save_review(
    review: OpportunityReview,
    user: dict[str, str | bool] = Depends(get_current_user),
) -> OpportunityReview:
    review.user_id = str(user["id"])

    if application_store is not None:
        result = application_store.create_review(
            review.model_dump(mode="python"),
            limit=settings.free_beta_review_limit,
        )
        if result == "duplicate":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A review with this id already exists.",
            )
        if result == "quota":
            enforce_account_quota("review", settings.free_beta_review_limit + 1)
        return review

    # `id` is client-supplied (the frontend uses Date.now()). Enforce
    # uniqueness per-user at write time so a collision can't silently
    # overwrite/alias another review in delete/compare lookups, and check
    # the quota atomically with the append so concurrent saves can't both
    # pass a stale count. See Sprint 1 bugfix notes; Sprint 2 should move
    # this id to a server-generated UUID.
    with guarded("review-quota", str(user["id"])):
        if any(item.id == review.id and item.user_id == user["id"] for item in reviews):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A review with this id already exists.",
            )
        owned_review_count = sum(item.user_id == user["id"] for item in reviews)
        enforce_account_quota("review", owned_review_count + 1)
        reviews.append(review)
        _persist_reviews(str(user["id"]))

    return review


@router.delete("/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_review(
    review_id: int,
    user: dict[str, str | bool] = Depends(get_current_user),
) -> None:
    if application_store is not None:
        if application_store.delete_review(str(user["id"]), review_id):
            return
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found.",
        )

    for index, review in enumerate(reviews):
        if review.id == review_id and review.user_id == user["id"]:
            reviews.pop(index)
            _persist_reviews(str(user["id"]))
            return

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Review not found.",
    )


@router.post(
    "/compare",
    response_model=ReviewComparisonResponse,
    status_code=status.HTTP_200_OK,
)
def compare_reviews(
    request: ReviewComparisonRequest,
    user: dict[str, str | bool] = Depends(get_current_user),
) -> ReviewComparisonResponse:
    selected_reviews = [
        review
        for review in reviews_for_user(str(user["id"]))
        if review.id in request.review_ids
    ]
    missing_ids = set(request.review_ids) - {review.id for review in selected_reviews}

    if missing_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reviews not found: {', '.join(str(item) for item in sorted(missing_ids))}",
        )

    eligibility_rank = {
        "Eligible": 0,
        "Insufficient information": 1,
        "Action required": 1,
        "Unclear": 2,
        "Not eligible": 3,
    }
    recommended = min(
        selected_reviews,
        key=lambda review: (
            eligibility_rank.get(review.eligibility, 99),
            len(review.missing_requirements),
        ),
        default=None,
    )

    return ReviewComparisonResponse(
        reviews=selected_reviews,
        recommended_review_id=recommended.id if recommended else None,
    )
