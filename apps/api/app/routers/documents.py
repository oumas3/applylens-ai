from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field

from app.services.document_service import (
    DocumentExtractionError,
    DocumentService,
)
from app.routers.auth import get_current_user

router = APIRouter(
    prefix="/api/v1/documents",
    tags=["documents"],
    dependencies=[Depends(get_current_user)],
)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
UPLOAD_READ_CHUNK_SIZE = 1024 * 1024  # 1 MB

UPLOAD_DIRECTORY = (
    Path(__file__).resolve().parents[2]
    / "storage"
    / "uploads"
)

UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)
DOCUMENTS_FILE = Path(__file__).resolve().parents[2] / "storage" / "documents.json"


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
    original_filename: str = Field(..., min_length=1)
    stored_filename: str
    category: DocumentCategory
    content_type: str
    size_bytes: int
    status: Literal["uploaded"]
    extracted_text_length: int = 0
    uploaded_at: datetime


class DocumentUploadRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    category: DocumentCategory = Field(default="OTHER")


def _load_documents() -> dict[str, DocumentMetadata]:
    if not DOCUMENTS_FILE.exists():
        return {}

    try:
        payload = json.loads(DOCUMENTS_FILE.read_text(encoding="utf-8"))
        loaded = [DocumentMetadata.model_validate(item) for item in payload]
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}

    return {document.id: document for document in loaded}


def _persist_documents() -> None:
    DOCUMENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = DOCUMENTS_FILE.with_suffix(".json.tmp")
    temporary_file.write_text(
        json.dumps(
            [document.model_dump(mode="json") for document in documents.values()],
            indent=2,
        ),
        encoding="utf-8",
    )
    temporary_file.replace(DOCUMENTS_FILE)


documents: dict[str, DocumentMetadata] = _load_documents()


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

    document_id = str(uuid4())
    file_extension = Path(filename).suffix.lower()
    stored_filename = f"{document_id}{file_extension}"
    destination = UPLOAD_DIRECTORY / stored_filename
    size_bytes = 0

    try:
        with destination.open("wb") as output:
            output.write(file_bytes)
            size_bytes = len(file_bytes)

    except Exception:
        destination.unlink(missing_ok=True)
        raise

    finally:
        await file.close()

    try:
        extracted_text = DocumentService.extract_text(
            normalized_content_type,
            file_bytes,
        )
    except DocumentExtractionError as error:
        destination.unlink(missing_ok=True)

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error

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
        uploaded_at=datetime.now(timezone.utc),
    )

    documents[document_id] = metadata
    _persist_documents()
    return metadata


@router.get(
    "",
    response_model=list[DocumentMetadata],
)
def list_documents(user: dict[str, str | bool] = Depends(get_current_user)) -> list[DocumentMetadata]:
    return [document for document in documents.values() if document.user_id == user["id"]]


@router.get(
    "/{document_id}",
    response_model=DocumentMetadata,
)
def get_document(document_id: str, user: dict[str, str | bool] = Depends(get_current_user)) -> DocumentMetadata:
    document = documents.get(document_id)

    if document is None or document.user_id != user["id"]:
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
    document = documents.get(document_id)

    if document is None or document.user_id != user["id"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    extracted_text = DocumentService.extract_text(
        document.content_type,
        (UPLOAD_DIRECTORY / document.stored_filename).read_bytes(),
    )
    return extracted_text


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_document(document_id: str, user: dict[str, str | bool] = Depends(get_current_user)) -> None:
    document = documents.get(document_id)

    if document is None or document.user_id != user["id"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    documents.pop(document_id)
    stored_file = UPLOAD_DIRECTORY / document.stored_filename
    if stored_file.exists():
        stored_file.unlink()
    _persist_documents()
