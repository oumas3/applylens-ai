from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.config import get_settings
from app.routers.auth import get_current_user
from app.routers.documents import documents
from app.services.application_store import PostgresApplicationStore


router = APIRouter(
    prefix="/api/v1/profile",
    tags=["profile"],
    dependencies=[Depends(get_current_user)],
)
logger = logging.getLogger(__name__)

PROFILES_FILE = Path(__file__).resolve().parents[2] / "storage" / "profiles.json"
settings = get_settings()
application_store = (
    PostgresApplicationStore(settings.database_url)
    if settings.database_url
    else None
)


class EvidenceLinkedItem(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(default_factory=lambda: str(uuid4()), min_length=1)
    document_ids: list[str] = Field(default_factory=list)

    @field_validator("document_ids")
    @classmethod
    def unique_document_ids(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(item for item in values if item))


class YearRangeItem(EvidenceLinkedItem):
    start_year: int | None = Field(default=None, ge=1900, le=2100)
    end_year: int | None = Field(default=None, ge=1900, le=2100)

    @model_validator(mode="after")
    def validate_year_order(self) -> "YearRangeItem":
        if (
            self.start_year is not None
            and self.end_year is not None
            and self.end_year < self.start_year
        ):
            raise ValueError("end_year must not be earlier than start_year")
        return self


class EducationItem(YearRangeItem):
    institution: str = Field(..., min_length=1, max_length=200)
    degree: str = Field(..., min_length=1, max_length=200)
    field_of_study: str | None = Field(default=None, max_length=200)
    grade: str | None = Field(default=None, max_length=100)


class WorkExperienceItem(YearRangeItem):
    organization: str = Field(..., min_length=1, max_length=200)
    role: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class ResearchExperienceItem(YearRangeItem):
    title: str = Field(..., min_length=1, max_length=250)
    organization: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class LanguageItem(EvidenceLinkedItem):
    name: str = Field(..., min_length=1, max_length=100)
    proficiency: Literal["basic", "intermediate", "professional", "fluent", "native"]


class SkillItem(EvidenceLinkedItem):
    name: str = Field(..., min_length=1, max_length=120)


class PublicationItem(EvidenceLinkedItem):
    title: str = Field(..., min_length=1, max_length=500)
    venue: str | None = Field(default=None, max_length=250)
    year: int | None = Field(default=None, ge=1900, le=2100)
    url: AnyHttpUrl | None = None


class CandidateProfileUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    full_name: str | None = Field(default=None, max_length=200)
    headline: str | None = Field(default=None, max_length=250)
    location: str | None = Field(default=None, max_length=200)
    summary: str | None = Field(default=None, max_length=3000)
    education: list[EducationItem] = Field(default_factory=list, max_length=50)
    work_experience: list[WorkExperienceItem] = Field(default_factory=list, max_length=100)
    research_experience: list[ResearchExperienceItem] = Field(default_factory=list, max_length=100)
    languages: list[LanguageItem] = Field(default_factory=list, max_length=50)
    skills: list[SkillItem] = Field(default_factory=list, max_length=200)
    publications: list[PublicationItem] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def validate_item_ids(self) -> "CandidateProfileUpdate":
        for field_name in (
            "education",
            "work_experience",
            "research_experience",
            "languages",
            "skills",
            "publications",
        ):
            items = getattr(self, field_name)
            ids = [item.id for item in items]
            if len(ids) != len(set(ids)):
                raise ValueError(f"{field_name} item IDs must be unique")
        return self


class CandidateProfile(CandidateProfileUpdate):
    user_id: str
    updated_at: datetime | None = None


def _load_profiles() -> dict[str, CandidateProfile]:
    if application_store is not None:
        try:
            loaded = [
                CandidateProfile.model_validate(item)
                for item in application_store.load_profiles()
            ]
            return {profile.user_id: profile for profile in loaded}
        except Exception:
            logger.exception("Unable to load candidate profiles from PostgreSQL")
            return {}

    if not PROFILES_FILE.exists():
        return {}
    try:
        payload = json.loads(PROFILES_FILE.read_text(encoding="utf-8"))
        loaded = [CandidateProfile.model_validate(item) for item in payload]
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}
    return {profile.user_id: profile for profile in loaded}


def _persist_profiles(user_id: str | None = None) -> None:
    if application_store is not None:
        application_store.replace_profiles(
            (
                profile.model_dump(mode="json")
                for profile in profiles.values()
                if user_id is None or profile.user_id == user_id
            ),
            user_id=user_id,
        )
        return

    PROFILES_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = PROFILES_FILE.with_suffix(".json.tmp")
    temporary_file.write_text(
        json.dumps(
            [profile.model_dump(mode="json") for profile in profiles.values()],
            indent=2,
        ),
        encoding="utf-8",
    )
    temporary_file.replace(PROFILES_FILE)


profiles: dict[str, CandidateProfile] = _load_profiles()


def empty_profile(user_id: str) -> CandidateProfile:
    return CandidateProfile(user_id=user_id)


def profile_evidence(
    profile: CandidateProfile | None,
    document_evidence: dict[str, tuple[str, str]],
) -> list[str]:
    """Return structured claims whose linked document text supports the claim."""
    if profile is None:
        return []

    def tokens(value: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[a-z0-9]+", value.lower())
            if len(token) >= 3
        }

    def sources(item: EvidenceLinkedItem, claim_terms: str) -> list[str]:
        claim_tokens = tokens(claim_terms)
        return list(
            dict.fromkeys(
                filename
                for document_id in item.document_ids
                if document_id in document_evidence
                for filename, text in [document_evidence[document_id]]
                if claim_tokens & tokens(text)
            )
        )

    def with_sources(claim: str, filenames: list[str]) -> str:
        return f"{claim} [source: {', '.join(filenames)}]"

    evidence: list[str] = []
    for item in profile.education:
        supporting_sources = sources(
            item,
            " ".join(
                value
                for value in (
                    item.degree,
                    item.field_of_study,
                    item.institution,
                )
                if value
            ),
        )
        if supporting_sources:
            field = f" in {item.field_of_study}" if item.field_of_study else ""
            grade = f", grade {item.grade}" if item.grade else ""
            evidence.append(
                with_sources(
                    f"Education: {item.degree}{field} at {item.institution}{grade}.",
                    supporting_sources,
                )
            )
    for item in profile.work_experience:
        supporting_sources = sources(
            item,
            f"{item.role} {item.organization} {item.description or ''}",
        )
        if supporting_sources:
            detail = f" {item.description}" if item.description else ""
            evidence.append(
                with_sources(
                    f"Work experience: {item.role} at {item.organization}.{detail}".strip(),
                    supporting_sources,
                )
            )
    for item in profile.research_experience:
        supporting_sources = sources(
            item,
            f"{item.title} {item.organization or ''} {item.description or ''}",
        )
        if supporting_sources:
            organization = f" at {item.organization}" if item.organization else ""
            detail = f" {item.description}" if item.description else ""
            evidence.append(
                with_sources(
                    f"Research experience: {item.title}{organization}.{detail}".strip(),
                    supporting_sources,
                )
            )
    for item in profile.languages:
        supporting_sources = sources(
            item,
            f"{item.name} {item.proficiency}",
        )
        if supporting_sources:
            evidence.append(
                with_sources(
                    f"Language proficiency: {item.name} ({item.proficiency}).",
                    supporting_sources,
                )
            )
    for item in profile.skills:
        supporting_sources = sources(item, item.name)
        if supporting_sources:
            evidence.append(
                with_sources(f"Skill: {item.name}.", supporting_sources)
            )
    for item in profile.publications:
        supporting_sources = sources(
            item,
            f"{item.title} {item.venue or ''}",
        )
        if supporting_sources:
            venue = f" in {item.venue}" if item.venue else ""
            year = f" ({item.year})" if item.year else ""
            evidence.append(
                with_sources(
                    f"Publication: {item.title}{venue}{year}.",
                    supporting_sources,
                )
            )
    return evidence


def referenced_document_ids(profile: CandidateProfileUpdate) -> set[str]:
    return {
        document_id
        for field_name in (
            "education",
            "work_experience",
            "research_experience",
            "languages",
            "skills",
            "publications",
        )
        for item in getattr(profile, field_name)
        for document_id in item.document_ids
    }


@router.get("", response_model=CandidateProfile)
def get_profile(
    user: dict[str, str | bool] = Depends(get_current_user),
) -> CandidateProfile:
    user_id = str(user["id"])
    return profiles.get(user_id, empty_profile(user_id))


@router.put("", response_model=CandidateProfile)
def save_profile(
    request: CandidateProfileUpdate,
    user: dict[str, str | bool] = Depends(get_current_user),
) -> CandidateProfile:
    user_id = str(user["id"])
    referenced_ids = referenced_document_ids(request)
    invalid_ids = sorted(
        document_id
        for document_id in referenced_ids
        if (
            document_id not in documents
            or documents[document_id].user_id != user_id
        )
    )
    if invalid_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Profile evidence must reference documents owned by this account.",
                "document_ids": invalid_ids,
            },
        )

    profile = CandidateProfile(
        user_id=user_id,
        updated_at=datetime.now(timezone.utc),
        **request.model_dump(mode="python"),
    )
    profiles[user_id] = profile
    _persist_profiles(user_id)
    return profile


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
def delete_profile(
    user: dict[str, str | bool] = Depends(get_current_user),
) -> None:
    user_id = str(user["id"])
    profiles.pop(user_id, None)
    _persist_profiles(user_id)


def remove_document_reference(user_id: str, document_id: str) -> None:
    profile = profiles.get(user_id)
    if profile is None:
        return
    changed = False
    for field_name in (
        "education",
        "work_experience",
        "research_experience",
        "languages",
        "skills",
        "publications",
    ):
        for item in getattr(profile, field_name):
            if document_id in item.document_ids:
                item.document_ids = [
                    value for value in item.document_ids if value != document_id
                ]
                changed = True
    if changed:
        profile.updated_at = datetime.now(timezone.utc)
        _persist_profiles(user_id)
