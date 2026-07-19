from __future__ import annotations

import re


class DocumentService:
    @staticmethod
    def extract_text(content_type: str, file_bytes: bytes) -> str:
        if content_type == "text/plain":
            return file_bytes.decode("utf-8")

        if content_type == "application/pdf":
            payload = file_bytes.decode("latin-1", errors="ignore")
            matches = re.findall(r"\((.*?)\)\s*Tj", payload, re.DOTALL)
            if matches:
                return "".join(matches)
            return ""

        return ""
