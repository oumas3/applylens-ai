from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.routers.documents import UPLOAD_DIRECTORY, documents
from app.services.document_service import DocumentExtractionError, DocumentService

router = APIRouter(
    prefix="/api/v1/opportunities",
    tags=["opportunities"],
)


class OpportunityAnalysisRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(..., min_length=1)
    requirements: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)
    deadline: str | None = None
    funding: str | None = None


class RequirementAnalysis(BaseModel):
    requirement: str
    status: str
    evidence: list[str]
    explanation: str
    action: str | None = None


class OpportunityAnalysisResponse(BaseModel):
    title: str
    eligibility: str
    matched_requirements: list[str]
    missing_requirements: list[str]
    evidence_summary: list[str]
    requirement_results: list[RequirementAnalysis]
    deadline: str | None = None
    funding: str | None = None


def _matching_evidence(requirement: str, evidence_items: list[str]) -> list[str]:
    requirement_text = requirement.lower()
    matches: list[str] = []

    for evidence in evidence_items:
        evidence_text = evidence.lower()

        if requirement_text in evidence_text:
            matches.append(evidence)
            continue

        if "research" in requirement_text and any(
            term in evidence_text for term in ["research", "paper", "papers", "publication", "publications", "thesis", "project"]
        ):
            matches.append(evidence)
            continue

        if "english" in requirement_text and any(
            term in evidence_text for term in ["english", "ielts", "toefl", "proficiency"]
        ):
            matches.append(evidence)
            continue

        if "degree" in requirement_text and any(
            term in evidence_text for term in ["degree", "bachelor", "master", "phd", "education"]
        ):
            matches.append(evidence)

    return matches


def _document_evidence(document_ids: list[str]) -> list[str]:
    extracted_text: list[str] = []

    for document_id in document_ids:
        document = documents.get(document_id)

        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document not found: {document_id}",
            )

        try:
            text = DocumentService.extract_text(
                document.content_type,
                (UPLOAD_DIRECTORY / document.stored_filename).read_bytes(),
            )
        except (OSError, DocumentExtractionError) as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unable to read document: {document.original_filename}",
            ) from error

        if text.strip():
            extracted_text.append(text.strip())

    return extracted_text


@router.post(
    "/analyse",
    response_model=OpportunityAnalysisResponse,
    status_code=status.HTTP_200_OK,
)
def analyse_opportunity(request: OpportunityAnalysisRequest) -> OpportunityAnalysisResponse:
    normalized_requirements = [item.strip() for item in request.requirements if item and item.strip()]
    normalized_evidence = [item.strip() for item in request.evidence if item and item.strip()]
    normalized_evidence.extend(_document_evidence(request.document_ids))

    matched_requirements = []
    missing_requirements = []
    requirement_results: list[RequirementAnalysis] = []

    for requirement in normalized_requirements:
        matching_evidence = _matching_evidence(requirement, normalized_evidence)

        if matching_evidence:
            matched_requirements.append(requirement)
            requirement_results.append(
                RequirementAnalysis(
                    requirement=requirement,
                    status="Eligible",
                    evidence=matching_evidence,
                    explanation="Supporting evidence was found in the provided profile.",
                )
            )
        else:
            missing_requirements.append(requirement)
            requirement_results.append(
                RequirementAnalysis(
                    requirement=requirement,
                    status="Action required",
                    evidence=[],
                    explanation="No supporting evidence was found in the provided profile.",
                    action=f"Provide evidence for: {requirement}",
                )
            )

    eligibility = "Eligible" if not missing_requirements else "Unclear"

    return OpportunityAnalysisResponse(
        title=request.title,
        eligibility=eligibility,
        matched_requirements=matched_requirements,
        missing_requirements=missing_requirements,
        evidence_summary=normalized_evidence,
        requirement_results=requirement_results,
        deadline=request.deadline,
        funding=request.funding,
    )
