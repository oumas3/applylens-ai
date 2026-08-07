from datetime import date, datetime
import hashlib
from io import BytesIO
import json
import logging
from pathlib import Path
import re
from uuid import uuid4

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from typing import Literal

from app.config import get_settings
from app.routers.auth import get_current_user
from app.routers.documents import documents, file_storage, read_upload_bytes
from app.services.document_service import DocumentExtractionError, DocumentService
from app.services.application_store import PostgresApplicationStore
from app.services.embedding_service import (
    HashEmbeddingProvider,
    OpenAIEmbeddingProvider,
)
from app.services.retrieval_service import (
    EmbeddingRetriever,
    InMemoryRetriever,
    PgVectorRetriever,
    RetrievalResult,
    chunk_text,
)

router = APIRouter(
    prefix="/api/v1/opportunities",
    tags=["opportunities"],
    dependencies=[Depends(get_current_user)],
)
logger = logging.getLogger(__name__)

OPPORTUNITIES_FILE = Path(__file__).resolve().parents[2] / "storage" / "opportunities.json"
runtime_settings = get_settings()
application_store = (
    PostgresApplicationStore(runtime_settings.database_url)
    if runtime_settings.database_url
    else None
)


class OpportunityIngestRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(..., min_length=1)
    source_text: str = Field(..., min_length=1)
    institution: str | None = None
    degree_type: str | None = None
    source_name: str | None = None
    source_url: AnyHttpUrl | None = None
    deadline: str | None = None
    deadline_date: date | None = None
    funding: str | None = None


class RequirementCitation(BaseModel):
    requirement: str
    source_name: str | None = None
    page: int | None = None


class OpportunityRecord(BaseModel):
    id: str
    user_id: str | None = None
    title: str
    source_text: str
    institution: str | None = None
    degree_type: str | None = None
    source_name: str | None = None
    source_url: AnyHttpUrl | None = None
    requirements: list[str] = Field(default_factory=list)
    requirement_citations: list[RequirementCitation] = Field(default_factory=list)
    deadline: str | None = None
    deadline_date: date | None = None
    funding: str | None = None


class OpportunityIngestAnalysisRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    evidence: list[str] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)


class EvidenceSearchRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


def _load_opportunities() -> list[OpportunityRecord]:
    if application_store is not None:
        try:
            return [
                OpportunityRecord.model_validate(item)
                for item in application_store.load_opportunities()
            ]
        except Exception:
            logger.exception("Unable to load opportunities from PostgreSQL")
            return []

    if not OPPORTUNITIES_FILE.exists():
        return []

    try:
        payload = json.loads(OPPORTUNITIES_FILE.read_text(encoding="utf-8"))
        return [OpportunityRecord.model_validate(item) for item in payload]
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return []


def _persist_opportunities(user_id: str | None = None) -> None:
    if application_store is not None:
        application_store.replace_opportunities(
            (
                opportunity.model_dump(mode="python")
                for opportunity in ingested_opportunities
                if user_id is None or opportunity.user_id == user_id
            ),
            user_id=user_id,
        )
        return

    OPPORTUNITIES_FILE.parent.mkdir(parents=True, exist_ok=True)
    OPPORTUNITIES_FILE.write_text(
        json.dumps(
            [opportunity.model_dump(mode="json") for opportunity in ingested_opportunities],
            indent=2,
        ),
        encoding="utf-8",
    )


ingested_opportunities: list[OpportunityRecord] = _load_opportunities()
_retrieval_cache: dict[
    str,
    tuple[
        tuple[str, str | None, int, int, int, str, str],
        InMemoryRetriever | EmbeddingRetriever | PgVectorRetriever,
    ],
] = {}


def _extract_requirements(source_text: str) -> list[str]:
    requirement_markers = (
        "must",
        "required",
        "applicants should",
        "eligibility",
        "minimum",
        "you need",
    )
    requirements: list[str] = []

    for raw_line in source_text.splitlines():
        line = raw_line.strip().lstrip("-•* ")
        normalized_line = line.lower()

        if not line or normalized_line in {"requirements", "eligibility criteria"}:
            continue

        if any(marker in normalized_line for marker in requirement_markers):
            if line not in requirements:
                requirements.append(line)

    return requirements


def _build_requirement_citations(
    requirements: list[str],
    source_name: str | None,
    page: int | None = None,
) -> list[RequirementCitation]:
    return [
        RequirementCitation(
            requirement=requirement,
            source_name=source_name,
            page=page,
        )
        for requirement in requirements
    ]


_DEADLINE_DATE_PATTERN = re.compile(
    r"\b(?:"
    r"\d{4}-\d{1,2}-\d{1,2}|"
    r"\d{1,2}[/-]\d{1,2}[/-]\d{4}|"
    r"\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|"
    r"May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|"
    r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}|"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
    r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+\d{4}"
    r")\b",
    re.IGNORECASE,
)


def _parse_deadline_date(value: str) -> date | None:
    normalized = re.sub(r"\s+", " ", value.strip().strip(".,;:"))
    for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d %B %Y", "%d %b %Y", "%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y"):
        try:
            return datetime.strptime(normalized, pattern).date()
        except ValueError:
            continue
    return None


def _extract_deadline(source_text: str) -> tuple[str | None, date | None]:
    markers = ("deadline", "due date", "closing date", "applications close", "application closes")
    for raw_line in source_text.splitlines():
        line = raw_line.strip().lstrip("-* ")
        normalized_line = line.lower()
        if not line or not any(marker in normalized_line for marker in markers):
            continue

        date_match = _DEADLINE_DATE_PATTERN.search(line)
        if date_match:
            value = date_match.group(0)
            return value, _parse_deadline_date(value)
        return line, None
    return None, None


def _extract_funding(source_text: str) -> str | None:
    funding_markers = (
        "funding",
        "scholarship",
        "stipend",
        "grant",
        "tuition waiver",
        "self-funded",
        "unfunded",
    )
    for raw_line in source_text.splitlines():
        line = raw_line.strip().lstrip("-* ")
        if line and any(marker in line.lower() for marker in funding_markers):
            return line
    return None


class OpportunityAnalysisRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(..., min_length=1)
    institution: str | None = None
    degree_type: str | None = None
    requirements: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)
    application_url: AnyHttpUrl | None = None
    required_documents: list[str] = Field(default_factory=list)
    deadline: str | None = None
    deadline_date: date | None = None
    funding: str | None = None


class RequirementAnalysis(BaseModel):
    requirement: str
    status: Literal["Eligible", "Not eligible", "Action required"]
    evidence: list[str]
    explanation: str
    action: str | None = None


class OpportunityAnalysisResponse(BaseModel):
    title: str
    institution: str | None = None
    degree_type: str | None = None
    eligibility: str
    matched_requirements: list[str]
    missing_requirements: list[str]
    evidence_summary: list[str]
    requirement_results: list[RequirementAnalysis]
    source_citations: list[RequirementCitation] = Field(default_factory=list)
    deadline: str | None = None
    deadline_date: date | None = None
    funding: str | None = None
    funding_status: Literal["available", "unavailable", "unclear"] = "unclear"
    application_url: AnyHttpUrl | None = None
    required_documents: list[str] = Field(default_factory=list)


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


def _document_evidence(
    document_ids: list[str],
    user_id: str,
) -> list[str]:
    extracted_text: list[str] = []

    for document_id in document_ids:
        document = documents.get(document_id)

        if document is None or document.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document not found: {document_id}",
            )

        try:
            text = DocumentService.extract_text(
                document.content_type,
                file_storage.read(document.stored_filename),
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
    "/ingest",
    response_model=OpportunityRecord,
    status_code=status.HTTP_201_CREATED,
)
def ingest_opportunity(
    request: OpportunityIngestRequest,
    user: dict[str, str | bool] = Depends(get_current_user),
) -> OpportunityRecord:
    extracted_deadline, extracted_deadline_date = _extract_deadline(request.source_text)
    opportunity = OpportunityRecord(
        id=str(uuid4()),
        user_id=str(user["id"]),
        title=request.title,
        source_text=request.source_text,
        institution=request.institution,
        degree_type=request.degree_type,
        source_name=request.source_name,
        source_url=request.source_url,
        requirements=_extract_requirements(request.source_text),
        requirement_citations=_build_requirement_citations(
            _extract_requirements(request.source_text),
            request.source_name,
        ),
        deadline=request.deadline or extracted_deadline,
        deadline_date=request.deadline_date or extracted_deadline_date,
        funding=request.funding or _extract_funding(request.source_text),
    )
    ingested_opportunities.append(opportunity)
    _persist_opportunities(str(user["id"]))
    return opportunity


@router.post(
    "/ingest-file",
    response_model=OpportunityRecord,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_opportunity_file(
    file: UploadFile,
    title: str = Form(...),
    institution: str | None = Form(default=None),
    degree_type: str | None = Form(default=None),
    user: dict[str, str | bool] = Depends(get_current_user),
) -> OpportunityRecord:
    normalized_title = title.strip()
    if not normalized_title:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Opportunity title is required.",
        )

    filename = file.filename or "opportunity.txt"
    extension = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    normalized_content_type = (file.content_type or "").split(";", 1)[0].strip().lower()

    supported_types = {
        "application/pdf": "pdf",
        "text/plain": "txt",
    }
    if normalized_content_type not in supported_types or extension not in {"pdf", "txt"}:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF and TXT opportunity files are accepted.",
        )

    file_bytes = await read_upload_bytes(file)
    await file.close()

    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The opportunity file is empty.",
        )

    try:
        source_text = DocumentService.extract_text(
            normalized_content_type,
            file_bytes,
        )
    except (DocumentExtractionError, UnicodeDecodeError) as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The opportunity file could not be read.",
        ) from error

    opportunity = ingest_opportunity(
        OpportunityIngestRequest(
            title=normalized_title,
            source_text=source_text,
            institution=institution,
            degree_type=degree_type,
            source_name=filename,
        ),
        user=user,
    )

    if normalized_content_type == "application/pdf":
        try:
            page_citations: list[RequirementCitation] = []
            reader = PdfReader(BytesIO(file_bytes))
            for page_number, page in enumerate(reader.pages, start=1):
                page_text = page.extract_text() or ""
                page_requirements = _extract_requirements(page_text)
                page_citations.extend(
                    _build_requirement_citations(
                        page_requirements,
                        filename,
                        page_number,
                    )
                )

            if page_citations:
                opportunity.requirement_citations = page_citations
                _persist_opportunities(str(user["id"]))
        except PdfReadError:
            # DocumentService already validated the PDF; keep the general
            # source citation when page-level extraction is unavailable.
            pass

    return opportunity


@router.get(
    "/ingested",
    response_model=list[OpportunityRecord],
    status_code=status.HTTP_200_OK,
)
def list_ingested_opportunities(
    user: dict[str, str | bool] = Depends(get_current_user),
) -> list[OpportunityRecord]:
    return [item for item in ingested_opportunities if item.user_id == user["id"]]


@router.delete(
    "/ingested/{opportunity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_ingested_opportunity(
    opportunity_id: str,
    user: dict[str, str | bool] = Depends(get_current_user),
) -> None:
    for index, opportunity in enumerate(ingested_opportunities):
        if opportunity.id == opportunity_id and opportunity.user_id == user["id"]:
            ingested_opportunities.pop(index)
            _retrieval_cache.pop(opportunity_id, None)
            _persist_opportunities(str(user["id"]))
            return

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Ingested opportunity not found.",
    )


@router.post(
    "/ingested/{opportunity_id}/evidence-search",
    response_model=list[RetrievalResult],
    status_code=status.HTTP_200_OK,
)
def search_ingested_opportunity_evidence(
    opportunity_id: str,
    request: EvidenceSearchRequest,
    user: dict[str, str | bool] = Depends(get_current_user),
) -> list[RetrievalResult]:
    opportunity = next(
        (
            item
            for item in ingested_opportunities
            if item.id == opportunity_id and item.user_id == user["id"]
        ),
        None,
    )
    if opportunity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ingested opportunity not found.",
        )

    settings = get_settings()
    source_hash = hashlib.sha256(
        opportunity.source_text.encode("utf-8")
    ).hexdigest()
    cache_key = (
        source_hash,
        opportunity.source_name,
        settings.retrieval_chunk_max_chars,
        settings.retrieval_chunk_overlap_chars,
        settings.retrieval_embedding_dimension,
        settings.retrieval_provider,
        settings.retrieval_storage,
    )
    cached = _retrieval_cache.get(opportunity_id)
    if cached is not None and cached[0] == cache_key:
        retriever = cached[1]
    else:
        chunks = chunk_text(
            opportunity.source_text,
            source_name=opportunity.source_name,
            max_chars=settings.retrieval_chunk_max_chars,
            overlap_chars=settings.retrieval_chunk_overlap_chars,
        )
        if settings.retrieval_provider == "openai":
            provider = OpenAIEmbeddingProvider(
                settings.openai_api_key.get_secret_value(),
                model=settings.openai_embedding_model,
                base_url=settings.openai_base_url,
            )
            if settings.retrieval_storage == "pgvector":
                retriever = PgVectorRetriever(
                    settings.database_url,
                    provider,
                    opportunity_id,
                )
            else:
                retriever = EmbeddingRetriever(provider)
        elif settings.retrieval_provider == "hash":
            retriever = EmbeddingRetriever(
                HashEmbeddingProvider(settings.retrieval_embedding_dimension)
            )
        else:
            retriever = InMemoryRetriever()
        retriever.index(chunks)
        _retrieval_cache[opportunity_id] = (cache_key, retriever)
    return retriever.search(request.query, top_k=request.top_k)


@router.post(
    "/ingested/{opportunity_id}/analyse",
    response_model=OpportunityAnalysisResponse,
    status_code=status.HTTP_200_OK,
)
def analyse_ingested_opportunity(
    opportunity_id: str,
    request: OpportunityIngestAnalysisRequest,
    user: dict[str, str | bool] = Depends(get_current_user),
) -> OpportunityAnalysisResponse:
    opportunity = next(
        (
            item
            for item in ingested_opportunities
            if item.id == opportunity_id and item.user_id == user["id"]
        ),
        None,
    )

    if opportunity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ingested opportunity not found.",
        )

    analysis = analyse_opportunity(
        OpportunityAnalysisRequest(
            title=opportunity.title,
            institution=opportunity.institution,
            degree_type=opportunity.degree_type,
            requirements=opportunity.requirements,
            evidence=request.evidence,
            document_ids=request.document_ids,
            application_url=opportunity.source_url,
            deadline=opportunity.deadline,
            deadline_date=opportunity.deadline_date,
            funding=opportunity.funding,
        ),
        user=user,
    )
    analysis.source_citations = opportunity.requirement_citations
    return analysis


@router.post(
    "/analyse",
    response_model=OpportunityAnalysisResponse,
    status_code=status.HTTP_200_OK,
)
def analyse_opportunity(
    request: OpportunityAnalysisRequest,
    user: dict[str, str | bool] = Depends(get_current_user),
) -> OpportunityAnalysisResponse:
    normalized_requirements = [item.strip() for item in request.requirements if item and item.strip()]
    normalized_evidence = [item.strip() for item in request.evidence if item and item.strip()]
    normalized_evidence.extend(_document_evidence(request.document_ids, str(user["id"])))

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
        institution=request.institution,
        degree_type=request.degree_type,
        eligibility=eligibility,
        matched_requirements=matched_requirements,
        missing_requirements=missing_requirements,
        evidence_summary=normalized_evidence,
        requirement_results=requirement_results,
        source_citations=[],
        deadline=request.deadline,
        deadline_date=request.deadline_date,
        funding=request.funding,
        funding_status=_funding_status(request.funding),
        application_url=request.application_url,
        required_documents=[
            item.strip()
            for item in request.required_documents
            if item and item.strip()
        ],
    )
