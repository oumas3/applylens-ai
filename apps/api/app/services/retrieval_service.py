from __future__ import annotations

import hashlib
import math
import re

from pydantic import BaseModel, ConfigDict, Field

from app.services.embedding_service import EmbeddingProvider


class TextChunk(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    chunk_id: str
    text: str = Field(..., min_length=1)
    source_name: str | None = None
    page: int | None = None
    index: int = Field(..., ge=0)


class RetrievalResult(BaseModel):
    chunk: TextChunk
    score: float = Field(..., ge=0, le=1)


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


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


class InMemoryRetriever:
    """Deterministic retrieval implementation used before semantic embeddings."""

    def __init__(self) -> None:
        self._chunks: dict[str, TextChunk] = {}

    def index(self, chunks: list[TextChunk]) -> None:
        for chunk in chunks:
            self._chunks[chunk.chunk_id] = chunk

    def search(self, query: str, *, top_k: int = 5) -> list[RetrievalResult]:
        if top_k < 1:
            raise ValueError("top_k must be positive")

        query_tokens = _tokens(query)
        if not query_tokens:
            return []

        results: list[RetrievalResult] = []
        for chunk in self._chunks.values():
            chunk_tokens = _tokens(chunk.text)
            score = len(query_tokens & chunk_tokens) / len(query_tokens)
            if score > 0:
                results.append(RetrievalResult(chunk=chunk, score=score))

        results.sort(key=lambda result: (-result.score, result.chunk.index))
        return results[:top_k]


class EmbeddingRetriever:
    """In-memory cosine retrieval using any compatible embedding provider."""

    def __init__(self, provider: EmbeddingProvider) -> None:
        self.provider = provider
        self._vectors: dict[str, tuple[TextChunk, list[float]]] = {}

    def index(self, chunks: list[TextChunk]) -> None:
        vectors = self.provider.embed_many([chunk.text for chunk in chunks])
        for chunk, vector in zip(chunks, vectors):
            self._vectors[chunk.chunk_id] = (chunk, vector)

    def search(self, query: str, *, top_k: int = 5) -> list[RetrievalResult]:
        if top_k < 1:
            raise ValueError("top_k must be positive")
        if not query.strip():
            return []

        query_vector = self.provider.embed_text(query)
        query_magnitude = math.sqrt(
            sum(value * value for value in query_vector)
        )
        if query_magnitude == 0:
            return []

        results: list[RetrievalResult] = []
        for chunk, vector in self._vectors.values():
            vector_magnitude = math.sqrt(sum(value * value for value in vector))
            if vector_magnitude == 0:
                continue
            score = sum(
                left * right for left, right in zip(query_vector, vector)
            ) / (query_magnitude * vector_magnitude)
            score = min(1.0, max(0.0, score))
            if score > 0:
                results.append(RetrievalResult(chunk=chunk, score=score))

        results.sort(key=lambda result: (-result.score, result.chunk.index))
        return results[:top_k]
