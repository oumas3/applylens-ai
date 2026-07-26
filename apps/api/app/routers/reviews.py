import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

REVIEWS_FILE = Path(__file__).resolve().parents[2] / "storage" / "reviews.json"

router = APIRouter(
    prefix="/api/v1/reviews",
    tags=["reviews"],
)


class OpportunityReview(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: int
    title: str
    eligibility: str
    matched_requirements: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    deadline: str | None = None
    funding: str | None = None


class ReviewComparisonRequest(BaseModel):
    review_ids: list[int] = Field(default_factory=list)


class ReviewComparisonResponse(BaseModel):
    reviews: list[OpportunityReview]
    recommended_review_id: int | None = None


def _load_reviews() -> list[OpportunityReview]:
    if not REVIEWS_FILE.exists():
        return []

    try:
        payload = json.loads(REVIEWS_FILE.read_text(encoding="utf-8"))
        return [OpportunityReview.model_validate(item) for item in payload]
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return []


def _persist_reviews() -> None:
    REVIEWS_FILE.parent.mkdir(parents=True, exist_ok=True)
    REVIEWS_FILE.write_text(
        json.dumps([review.model_dump(mode="json") for review in reviews], indent=2),
        encoding="utf-8",
    )


reviews: list[OpportunityReview] = _load_reviews()


@router.get("", response_model=list[OpportunityReview], status_code=status.HTTP_200_OK)
def list_reviews() -> list[OpportunityReview]:
    return reviews


@router.post("", response_model=OpportunityReview, status_code=status.HTTP_201_CREATED)
def save_review(review: OpportunityReview) -> OpportunityReview:
    reviews.append(review)
    _persist_reviews()
    return review


@router.post(
    "/compare",
    response_model=ReviewComparisonResponse,
    status_code=status.HTTP_200_OK,
)
def compare_reviews(request: ReviewComparisonRequest) -> ReviewComparisonResponse:
    selected_reviews = [review for review in reviews if review.id in request.review_ids]
    missing_ids = set(request.review_ids) - {review.id for review in selected_reviews}

    if missing_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reviews not found: {', '.join(str(item) for item in sorted(missing_ids))}",
        )

    eligibility_rank = {
        "Eligible": 0,
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
