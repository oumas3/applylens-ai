from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, UploadFile, status
from pydantic import BaseModel


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


class DocumentMetadata(BaseModel):
    id: str
    filename: str
    content_type: str
    size_bytes: int
    status: Literal["uploaded"]
    uploaded_at: datetime


documents: dict[str, DocumentMetadata] = {}


@router.post(
    "",
    response_model=DocumentMetadata,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(file: UploadFile) -> DocumentMetadata:
    filename = file.filename or "document.pdf"

    if (
        file.content_type != "application/pdf"
        or not filename.lower().endswith(".pdf")
    ):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF documents are accepted.",
        )

    pdf_signature = await file.read(5)

    if pdf_signature != b"%PDF-":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file is not a valid PDF.",
        )

    await file.seek(0)

    document_id = str(uuid4())
    destination = UPLOAD_DIRECTORY / f"{document_id}.pdf"
    size_bytes = 0

    try:
        with destination.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                size_bytes += len(chunk)

                if size_bytes > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="The PDF must not exceed 10 MB.",
                    )

                output.write(chunk)

    except Exception:
        destination.unlink(missing_ok=True)
        raise

    finally:
        await file.close()

    metadata = DocumentMetadata(
        id=document_id,
        filename=filename,
        content_type="application/pdf",
        size_bytes=size_bytes,
        status="uploaded",
        uploaded_at=datetime.now(timezone.utc),
    )

    documents[document_id] = metadata
    return metadata


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