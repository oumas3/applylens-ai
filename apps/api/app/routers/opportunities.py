from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(
    prefix="/api/v1/opportunities",
    tags=["opportunities"],
)


class OpportunityAnalysisRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(..., min_length=1)
    requirements: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    deadline: str | None = None
    funding: str | None = None


class OpportunityAnalysisResponse(BaseModel):
    title: str
    eligibility: str
    matched_requirements: list[str]
    missing_requirements: list[str]
    evidence_summary: list[str]
    deadline: str | None = None
    funding: str | None = None


def _matches_requirement(requirement: str, evidence_items: list[str]) -> bool:
    requirement_text = requirement.lower()

    for evidence in evidence_items:
        evidence_text = evidence.lower()

        if requirement_text in evidence_text:
            return True

        if "research" in requirement_text and any(
            term in evidence_text for term in ["research", "paper", "papers", "publication", "publications", "thesis", "project"]
        ):
            return True

        if "english" in requirement_text and any(
            term in evidence_text for term in ["english", "ielts", "toefl", "proficiency"]
        ):
            return True

        if "degree" in requirement_text and any(
            term in evidence_text for term in ["degree", "bachelor", "master", "phd", "education"]
        ):
            return True

    return False


@router.post(
    "/analyse",
    response_model=OpportunityAnalysisResponse,
    status_code=status.HTTP_200_OK,
)
def analyse_opportunity(request: OpportunityAnalysisRequest) -> OpportunityAnalysisResponse:
    normalized_requirements = [item.strip() for item in request.requirements if item and item.strip()]
    normalized_evidence = [item.strip() for item in request.evidence if item and item.strip()]

    matched_requirements = []
    missing_requirements = []

    for requirement in normalized_requirements:
        if _matches_requirement(requirement, normalized_evidence):
            matched_requirements.append(requirement)
        else:
            missing_requirements.append(requirement)

    eligibility = "Eligible" if not missing_requirements else "Unclear"

    return OpportunityAnalysisResponse(
        title=request.title,
        eligibility=eligibility,
        matched_requirements=matched_requirements,
        missing_requirements=missing_requirements,
        evidence_summary=normalized_evidence,
        deadline=request.deadline,
        funding=request.funding,
    )
