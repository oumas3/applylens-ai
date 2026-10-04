from __future__ import annotations

from io import BytesIO

from pydantic import BaseModel
from pypdf import PdfReader
from pypdf.errors import FileNotDecryptedError, PdfReadError


class DocumentExtractionError(ValueError):
    """Raised when text cannot be extracted safely from a document."""


class ExtractedPage(BaseModel):
    """Extracted text with its original PDF page number when available."""

    number: int | None = None
    text: str


class DocumentService:
    @staticmethod
    def extract_pages(
        content_type: str,
        file_bytes: bytes,
        *,
        max_pages: int = 100,
        max_chars: int = 500_000,
    ) -> list[ExtractedPage]:
        if max_pages < 1:
            raise ValueError("max_pages must be positive")
        if max_chars < 1:
            raise ValueError("max_chars must be positive")

        if content_type == "text/plain":
            try:
                text = file_bytes.decode("utf-8")
            except UnicodeDecodeError as error:
                raise DocumentExtractionError(
                    "The text file must use UTF-8 encoding."
                ) from error

            if len(text) > max_chars:
                raise DocumentExtractionError(
                    f"Extracted text must not exceed {max_chars:,} characters."
                )
            if not text.strip():
                raise DocumentExtractionError(
                    "No readable text was found in the document."
                )
            return [ExtractedPage(text=text)]

        if content_type == "application/pdf":
            try:
                reader = PdfReader(BytesIO(file_bytes))
                if reader.is_encrypted:
                    raise DocumentExtractionError(
                        "Encrypted PDFs are not supported."
                    )
                if len(reader.pages) > max_pages:
                    page_label = "page" if max_pages == 1 else "pages"
                    raise DocumentExtractionError(
                        f"PDFs must not exceed {max_pages} {page_label}."
                    )

                pages: list[ExtractedPage] = []
                extracted_chars = 0

                for page_number, page in enumerate(reader.pages, start=1):
                    page_text = page.extract_text()

                    if page_text:
                        pages.append(
                            ExtractedPage(number=page_number, text=page_text)
                        )
                        extracted_chars += len(page_text)
                        if extracted_chars > max_chars:
                            raise DocumentExtractionError(
                                "Extracted text must not exceed "
                                f"{max_chars:,} characters."
                            )

                if not any(page.text.strip() for page in pages):
                    raise DocumentExtractionError(
                        "No readable text was found in the PDF. "
                        "Scanned PDFs require OCR, which is not supported."
                    )
                return pages

            except (FileNotDecryptedError, PdfReadError) as error:
                raise DocumentExtractionError(
                    "The PDF could not be read."
                ) from error

        raise DocumentExtractionError("Unsupported document type.")

    @classmethod
    def extract_text(
        cls,
        content_type: str,
        file_bytes: bytes,
        *,
        max_pages: int = 100,
        max_chars: int = 500_000,
    ) -> str:
        pages = cls.extract_pages(
            content_type,
            file_bytes,
            max_pages=max_pages,
            max_chars=max_chars,
        )
        return "\n".join(page.text for page in pages)
