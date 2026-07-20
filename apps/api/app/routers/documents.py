from datetime import datetime, timezone
from dbm import error
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, UploadFile, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field

from app.services.document_service import (
    DocumentExtractionError,
    DocumentService,
)

router = APIRouter(
    prefix="/api/v1/documents",
    tags=["documents"],
)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

UPLOAD_DIRECTORY = (
    Path(__file__).resolve().parents[2]
    / "storage"
    / "uploads"
)

UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)


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


documents: dict[str, DocumentMetadata] = {}


@router.post(
    "",
    response_model=DocumentMetadata,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    file: UploadFile,
    category: str | None = None,
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

    file_bytes = await file.read()

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

    await file.seek(0)

    document_id = str(uuid4())
    file_extension = Path(filename).suffix.lower()
    stored_filename = f"{document_id}{file_extension}"
    destination = UPLOAD_DIRECTORY / stored_filename
    size_bytes = 0

    try:
        with destination.open("wb") as output:
            output.write(file_bytes)
            size_bytes = len(file_bytes)

            if size_bytes > MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="The file must not exceed 10 MB.",
                )

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
    return metadata


@router.get(
    "",
    response_model=list[DocumentMetadata],
)
def list_documents() -> list[DocumentMetadata]:
    return list(documents.values())


@router.get(
    "/{document_id}",
    response_model=DocumentMetadata,
)
def get_document(document_id: str) -> DocumentMetadata:
    document = documents.get(document_id)

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
def get_document_text(document_id: str) -> str:
    document = documents.get(document_id)

    if document is None:
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
def delete_document(document_id: str) -> None:
    document = documents.pop(document_id, None)

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    stored_file = UPLOAD_DIRECTORY / document.stored_filename
    if stored_file.exists():
        stored_file.unlink()
