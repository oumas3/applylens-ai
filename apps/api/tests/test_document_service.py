from io import BytesIO

import pytest
from pypdf import PdfWriter

from app.services.document_service import DocumentExtractionError, DocumentService


def pdf_with_blank_pages(count: int, *, encrypted: bool = False) -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    for _ in range(count):
        writer.add_blank_page(width=612, height=792)
    if encrypted:
        writer.encrypt("test-password")
    writer.write(output)
    return output.getvalue()


def test_text_extraction_rejects_invalid_utf8() -> None:
    with pytest.raises(DocumentExtractionError, match="UTF-8"):
        DocumentService.extract_text("text/plain", b"\xff\xfe")


def test_text_extraction_rejects_whitespace_only_content() -> None:
    with pytest.raises(DocumentExtractionError, match="No readable text"):
        DocumentService.extract_text("text/plain", b" \n\t")


def test_text_extraction_enforces_character_limit() -> None:
    with pytest.raises(DocumentExtractionError, match="5 characters"):
        DocumentService.extract_text("text/plain", b"abcdef", max_chars=5)


def test_pdf_extraction_rejects_encrypted_files() -> None:
    with pytest.raises(DocumentExtractionError, match="Encrypted PDFs"):
        DocumentService.extract_text(
            "application/pdf",
            pdf_with_blank_pages(1, encrypted=True),
        )


def test_pdf_extraction_enforces_page_limit_before_extracting() -> None:
    with pytest.raises(DocumentExtractionError, match="must not exceed 1 page"):
        DocumentService.extract_text(
            "application/pdf",
            pdf_with_blank_pages(2),
            max_pages=1,
        )


def test_pdf_extraction_explains_that_ocr_is_not_supported() -> None:
    with pytest.raises(DocumentExtractionError, match="OCR"):
        DocumentService.extract_text(
            "application/pdf",
            pdf_with_blank_pages(1),
        )


def test_extraction_rejects_unsupported_content_type() -> None:
    with pytest.raises(DocumentExtractionError, match="Unsupported"):
        DocumentService.extract_text("application/octet-stream", b"content")
