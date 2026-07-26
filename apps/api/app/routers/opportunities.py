from datetime import date

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

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
    deadline_date: date | None = None
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
    deadline_date: date | None = None
    funding: str | None = None
    funding_status: Literal["available", "unavailable", "unclear"] = "unclear"


def _matching_evidence(requirement: str, evidence_items: list[str]) -> list[str]:
    requirement_text = requirement.lower()
    matches: list[str] = []

    for evidence in evidence_items:
        evidence_text = evidence.lower()

        if _is_negative_evidence(evidence_text):
            continue

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


def _is_negative_evidence(evidence_text: str) -> bool:
    negative_phrases = (
        "not eligible",
        "does not have",
        "do not have",
        "doesn't have",
        "without",
        "failed",
        "no degree",
        "no bachelor's",
        "no bachelor",
    )
    return any(phrase in evidence_text for phrase in negative_phrases)


def _negative_evidence(requirement: str, evidence_items: list[str]) -> list[str]:
    requirement_text = requirement.lower()
    return [
        evidence
        for evidence in evidence_items
        if _is_negative_evidence(evidence.lower())
        and (
            requirement_text in evidence.lower()
            or (
                "english" in requirement_text
                and any(term in evidence.lower() for term in ["english", "ielts", "toefl"])
            )
            or (
                "degree" in requirement_text
                and any(term in evidence.lower() for term in ["degree", "bachelor", "master", "phd"])
            )
            or (
                "research" in requirement_text
                and any(term in evidence.lower() for term in ["research", "paper", "publication", "thesis"])
            )
        )
    ]


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


def _funding_status(funding: str | None) -> Literal["available", "unavailable", "unclear"]:
    if not funding or not funding.strip():
        return "unclear"

    funding_text = funding.lower()
    if any(term in funding_text for term in ["no funding", "unfunded", "unavailable"]):
        return "unavailable"
    if any(term in funding_text for term in ["scholarship", "funding", "grant", "stipend", "available"]):
        return "available"
    return "unclear"


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
    failed_requirements = []
    requirement_results: list[RequirementAnalysis] = []

    for requirement in normalized_requirements:
        matching_evidence = _matching_evidence(requirement, normalized_evidence)
        negative_evidence = _negative_evidence(requirement, normalized_evidence)

        if negative_evidence:
            failed_requirements.append(requirement)
            requirement_results.append(
                RequirementAnalysis(
                    requirement=requirement,
                    status="Not eligible",
                    evidence=negative_evidence,
                    explanation="The provided profile contains evidence that this requirement is not met.",
                    action=f"Resolve the eligibility gap for: {requirement}",
                )
            )
        elif matching_evidence:
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

    if failed_requirements:
        eligibility = "Not eligible"
    elif missing_requirements:
        eligibility = "Action required"
    else:
        eligibility = "Eligible"

    return OpportunityAnalysisResponse(
        title=request.title,
        eligibility=eligibility,
        matched_requirements=matched_requirements,
        missing_requirements=missing_requirements,
        evidence_summary=normalized_evidence,
        requirement_results=requirement_results,
        deadline=request.deadline,
        deadline_date=request.deadline_date,
        funding=request.funding,
        funding_status=_funding_status(request.funding),
    )
