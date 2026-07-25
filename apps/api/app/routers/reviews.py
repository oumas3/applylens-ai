from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict

router = APIRouter(
    prefix="/api/v1/reviews",
    tags=["reviews"],
)


class OpportunityReview(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: int
    title: str
    eligibility: str
    matched_requirements: list[str] = []
    missing_requirements: list[str] = []
    deadline: str | None = None
    funding: str | None = None


reviews: list[OpportunityReview] = []


@router.get("", response_model=list[OpportunityReview], status_code=status.HTTP_200_OK)
def list_reviews() -> list[OpportunityReview]:
    return reviews


@router.post("", response_model=OpportunityReview, status_code=status.HTTP_201_CREATED)
def save_review(review: OpportunityReview) -> OpportunityReview:
    reviews.append(review)
    return review
