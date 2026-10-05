from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field

from app.config import get_settings
from app.concurrency import guarded
from app.rate_limiting import enforce_rate_limit
from app.quotas import enforce_account_quota
from app.services.document_service import (
    DocumentExtractionError,
    DocumentService,
    ExtractedPage,
)
from app.services.application_store import PostgresApplicationStore
from app.services.file_storage import LocalFileStorage
from app.routers.auth import get_current_user

router = APIRouter(
    prefix="/api/v1/documents",
    tags=["documents"],
    dependencies=[Depends(get_current_user)],
)
logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
UPLOAD_READ_CHUNK_SIZE = 1024 * 1024  # 1 MB

UPLOAD_DIRECTORY = (
    Path(__file__).resolve().parents[2]
    / "storage"
    / "uploads"
)

DOCUMENTS_FILE = Path(__file__).resolve().parents[2] / "storage" / "documents.json"
settings = get_settings()
file_storage = (
    LocalFileStorage(UPLOAD_DIRECTORY)
    if settings.document_storage == "local"
    else None
)
application_store = (
    PostgresApplicationStore(settings.database_url)
    if settings.database_url
    else None
)


DocumentCategory = Literal[
    "CV",
    "COVER_LETTER",
    "TRANSCRIPT",
    "MOTIVATION_LETTER",
    "OTHER",
]


class DocumentMetadata(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str
    user_id: str | None = None
    original_filename: str = Field(..., min_length=1, max_length=255)
    stored_filename: str
    category: DocumentCategory
    content_type: str
    size_bytes: int
    status: Literal["uploaded"]
    extracted_text_length: int = 0
    extracted_text: str | None = Field(default=None, exclude=True, repr=False)
    extracted_pages: list[ExtractedPage] = Field(
        default_factory=list,
        exclude=True,
        repr=False,
    )
    uploaded_at: datetime


class DocumentUploadRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    category: DocumentCategory = Field(default="OTHER")


def _load_documents() -> dict[str, DocumentMetadata]:
    if application_store is not None:
        try:
            application_store.load_documents()
            return {}
        except Exception:
            logger.exception("Unable to load document metadata from PostgreSQL")
            raise RuntimeError(
                "PostgreSQL document metadata could not be loaded."
            )

    if not DOCUMENTS_FILE.exists():
        return {}

    try:
        payload = json.loads(DOCUMENTS_FILE.read_text(encoding="utf-8"))
        loaded = [DocumentMetadata.model_validate(item) for item in payload]
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}

    return {document.id: document for document in loaded}


def _persist_documents(user_id: str | None = None) -> None:
    records = [
        {
            **document.model_dump(mode="python"),
            "extracted_text": document.extracted_text,
            "extracted_pages": [
                page.model_dump(mode="python")
                for page in document.extracted_pages
            ],
        }
        for document in documents.values()
        if user_id is None or document.user_id == user_id
    ]
    if application_store is not None:
        application_store.replace_documents(
            records,
            user_id=user_id,
        )
        return

    DOCUMENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = DOCUMENTS_FILE.with_suffix(".json.tmp")
    temporary_file.write_text(
        json.dumps(
            records,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    temporary_file.replace(DOCUMENTS_FILE)


documents: dict[str, DocumentMetadata] = _load_documents()


def documents_for_user(user_id: str) -> list[DocumentMetadata]:
    if application_store is not None:
        return [
            DocumentMetadata.model_validate(item)
            for item in application_store.load_documents(user_id)
        ]
    return [document for document in documents.values() if document.user_id == user_id]


def document_for_user(user_id: str, document_id: str) -> DocumentMetadata | None:
    if application_store is not None:
        return next(
            (
                document
                for document in documents_for_user(user_id)
                if document.id == document_id
            ),
            None,
        )
    document = documents.get(document_id)
    return document if document is not None and document.user_id == user_id else None


def document_record(document: DocumentMetadata) -> dict:
    return {
        **document.model_dump(mode="python"),
        "extracted_text": document.extracted_text,
        "extracted_pages": [
            page.model_dump(mode="python")
            for page in document.extracted_pages
        ],
    }


def read_document_text(document: DocumentMetadata) -> str:
    """Return stored extracted text without exposing its persistence mode."""
    if document.extracted_text is not None:
        return document.extracted_text
    return "\n".join(page.text for page in read_document_pages(document))


def read_document_pages(document: DocumentMetadata) -> list[ExtractedPage]:
    """Return page-aware text, including a legacy fallback without page data."""
    if document.extracted_pages:
        return document.extracted_pages
    if document.extracted_text is not None:
        return [ExtractedPage(text=document.extracted_text)]
    if file_storage is None:
        raise RuntimeError("Local document storage is disabled.")
    return DocumentService.extract_pages(
        document.content_type,
        file_storage.read(document.stored_filename),
        max_pages=settings.document_max_pages,
        max_chars=settings.document_max_extracted_chars,
    )


async def read_upload_bytes(file: UploadFile, *, max_size: int = MAX_FILE_SIZE) -> bytes:
    """Read an upload in bounded chunks and reject oversized payloads early."""
    chunks: list[bytes] = []
    size = 0

    while chunk := await file.read(UPLOAD_READ_CHUNK_SIZE):
        size += len(chunk)
        if size > max_size:
            await file.close()
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="The file must not exceed 10 MB.",
            )
        chunks.append(chunk)

    return b"".join(chunks)


@router.post(
    "",
    response_model=DocumentMetadata,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    file: UploadFile,
    category: str | None = None,
    user: dict[str, str | bool] = Depends(get_current_user),
) -> DocumentMetadata:
    enforce_rate_limit("document_upload", str(user["id"]))
    # Optimistic, non-authoritative pre-check: fail fast for the common
    # over-quota case before doing any file I/O or text extraction. The
    # authoritative check happens again, atomically with the insert, right
    # before we commit -- see the `guarded()` block below. Without that
    # second check, two concurrent uploads could both pass this early count
    # and both get written, exceeding the account's quota.
    owned_document_count = len(documents_for_user(str(user["id"])))
    enforce_account_quota("document", owned_document_count + 1)
    filename = file.filename or "document.pdf"
    category_value = category or "OTHER"

    if not filename or filename in {".", ".."}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename.",
        )

    safe_name = Path(filename).name
    if safe_name != filename or "/" in filename or "\\" in filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename.",
        )

    if category_value not in {
        "CV",
        "COVER_LETTER",
        "TRANSCRIPT",
        "MOTIVATION_LETTER",
        "OTHER",
    }:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid document category.",
        )

    supported_content_types = {"application/pdf", "text/plain"}
    supported_extensions = {".pdf", ".txt"}

    normalized_content_type = file.content_type.split(";", 1)[0].strip().lower()

    if normalized_content_type not in supported_content_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF and TXT documents are accepted.",
        )

    if not filename.lower().endswith(tuple(supported_extensions)):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF and TXT documents are accepted.",
        )

    file_bytes = await read_upload_bytes(file)

    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file is empty.",
        )

    if normalized_content_type == "application/pdf":
        if file_bytes[:5] != b"%PDF-":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The uploaded file is not a valid PDF.",
            )

    try:
        extracted_pages = DocumentService.extract_pages(
            normalized_content_type,
            file_bytes,
            max_pages=settings.document_max_pages,
            max_chars=settings.document_max_extracted_chars,
        )
        extracted_text = "\n".join(page.text for page in extracted_pages)
    except DocumentExtractionError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error
    finally:
        await file.close()

    document_id = str(uuid4())
    file_extension = Path(filename).suffix.lower()
    stored_filename = f"{document_id}{file_extension}"
    size_bytes = len(file_bytes)
    extracted_text_record: str | None = extracted_text
    extracted_pages_record = extracted_pages

    if settings.document_storage == "local":
        assert file_storage is not None
        stored_file = file_storage.save(stored_filename, file_bytes)
        size_bytes = stored_file.size_bytes
        extracted_text_record = None
        extracted_pages_record = []

    metadata = DocumentMetadata(
        id=document_id,
        user_id=str(user["id"]),
        original_filename=filename,
        stored_filename=stored_filename,
        category=category_value,
        content_type=normalized_content_type,
        size_bytes=size_bytes,
        status="uploaded",
        extracted_text_length=len(extracted_text),
        extracted_text=extracted_text_record,
        extracted_pages=extracted_pages_record,
        uploaded_at=datetime.now(timezone.utc),
    )

    if application_store is not None:
        created = application_store.create_document(
            document_record(metadata),
            limit=settings.free_beta_document_limit,
        )
        if not created:
            if settings.document_storage == "local":
                assert file_storage is not None
                file_storage.delete(stored_filename)
            enforce_account_quota(
                "document",
                settings.free_beta_document_limit + 1,
            )
        return metadata

    with guarded("document-quota", str(user["id"])):
        owned_document_count = sum(
            document.user_id == user["id"] for document in documents.values()
        )
        try:
            enforce_account_quota("document", owned_document_count + 1)
        except HTTPException:
            if settings.document_storage == "local":
                assert file_storage is not None
                file_storage.delete(stored_filename)
            raise
        documents[document_id] = metadata
        try:
            _persist_documents(str(user["id"]))
        except Exception:
            documents.pop(document_id, None)
            if settings.document_storage == "local":
                assert file_storage is not None
                file_storage.delete(stored_filename)
            raise

    return metadata


@router.get(
    "",
    response_model=list[DocumentMetadata],
)
def list_documents(user: dict[str, str | bool] = Depends(get_current_user)) -> list[DocumentMetadata]:
    return documents_for_user(str(user["id"]))


@router.get(
    "/{document_id}",
    response_model=DocumentMetadata,
)
def get_document(document_id: str, user: dict[str, str | bool] = Depends(get_current_user)) -> DocumentMetadata:
    document = document_for_user(str(user["id"]), document_id)

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    return document


@router.get(
    "/{document_id}/text",
    response_class=PlainTextResponse,
)
def get_document_text(document_id: str, user: dict[str, str | bool] = Depends(get_current_user)) -> str:
    document = document_for_user(str(user["id"]), document_id)

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    return read_document_text(document)


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_document(document_id: str, user: dict[str, str | bool] = Depends(get_current_user)) -> None:
    user_id = str(user["id"])
    document = document_for_user(user_id, document_id)

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    if application_store is not None:
        if not application_store.delete_document(user_id, document_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found.",
            )
    else:
        documents.pop(document_id)
    if document.extracted_text is None:
        assert file_storage is not None
        file_storage.delete(document.stored_filename)
    if application_store is None:
        _persist_documents(user_id)
    from app.routers.profiles import remove_document_reference

    remove_document_reference(user_id, document_id)
