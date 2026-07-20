from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError


class DocumentExtractionError(ValueError):
    """Raised when text cannot be extracted safely from a document."""


class DocumentService:
    @staticmethod
    def extract_text(content_type: str, file_bytes: bytes) -> str:
        if content_type == "text/plain":
            return file_bytes.decode("utf-8")

        if content_type == "application/pdf":
            try:
                reader = PdfReader(BytesIO(file_bytes))
                pages_text: list[str] = []

                for page in reader.pages:
                    page_text = page.extract_text()

                    if page_text:
                        pages_text.append(page_text)

                return "\n".join(pages_text)

            except PdfReadError as error:
                raise DocumentExtractionError(
                    "The PDF could not be read."
                ) from error

        return ""