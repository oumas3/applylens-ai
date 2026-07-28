from __future__ import annotations

import hashlib
import re

from pydantic import BaseModel, ConfigDict, Field


class TextChunk(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    chunk_id: str
    text: str = Field(..., min_length=1)
    source_name: str | None = None
    page: int | None = None
    index: int = Field(..., ge=0)


def _chunk_id(
    text: str,
    source_name: str | None,
    page: int | None,
    index: int,
) -> str:
    identity = f"{source_name or 'unknown'}:{page or 0}:{index}:{text}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]


def _split_long_paragraph(paragraph: str, max_chars: int) -> list[str]:
    words = paragraph.split()
    pieces: list[str] = []
    current = ""

    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > max_chars:
            pieces.append(current)
            current = word
        else:
            current = candidate

    if current:
        pieces.append(current)

    return pieces


def _apply_overlap(pieces: list[str], overlap_chars: int) -> list[str]:
    if overlap_chars == 0:
        return pieces

    overlapped = [pieces[0]]
    for previous, current in zip(pieces, pieces[1:]):
        suffix = previous[-overlap_chars:].strip()
        overlapped.append(f"{suffix} {current}".strip())
    return overlapped


def chunk_text(
    text: str,
    *,
    source_name: str | None = None,
    page: int | None = None,
    max_chars: int = 1200,
    overlap_chars: int = 0,
) -> list[TextChunk]:
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    if overlap_chars < 0:
        raise ValueError("overlap_chars cannot be negative")
    if overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be smaller than max_chars")

    if not text.strip():
        return []

    content_limit = max_chars - overlap_chars - (1 if overlap_chars else 0)
    if content_limit < 1:
        raise ValueError("max_chars is too small for the requested overlap")

    paragraphs = [
        re.sub(r"\s+", " ", paragraph).strip()
        for paragraph in re.split(r"\n\s*\n", text)
    ]
    paragraphs = [paragraph for paragraph in paragraphs if paragraph]

    pieces: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > content_limit:
            if current:
                pieces.append(current)
                current = ""
            pieces.extend(_split_long_paragraph(paragraph, content_limit))
            continue

        candidate = f"{current}\n\n{paragraph}".strip()
        if current and len(candidate) > content_limit:
            pieces.append(current)
            current = paragraph
        else:
            current = candidate

    if current:
        pieces.append(current)

    pieces = _apply_overlap(pieces, overlap_chars)

    return [
        TextChunk(
            chunk_id=_chunk_id(piece, source_name, page, index),
            text=piece,
            source_name=source_name,
            page=page,
            index=index,
        )
        for index, piece in enumerate(pieces)
    ]
