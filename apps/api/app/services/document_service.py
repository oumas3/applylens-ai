from __future__ import annotations

from pathlib import Path


class DocumentService:
    @staticmethod
    def extract_text(content_type: str, file_bytes: bytes) -> str:
        if content_type == "text/plain":
            return file_bytes.decode("utf-8")

        if content_type == "application/pdf":
            return ""

        return ""
