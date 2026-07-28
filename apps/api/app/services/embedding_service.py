from __future__ import annotations

import hashlib
import math
from typing import Protocol


class EmbeddingProvider(Protocol):
    dimension: int

    def embed_text(self, text: str) -> list[float]:
        ...

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        ...


class HashEmbeddingProvider:
    """Deterministic local provider used until a real model is selected."""

    def __init__(self, dimension: int = 32) -> None:
        if dimension < 1:
            raise ValueError("dimension must be positive")
        self.dimension = dimension

    def embed_text(self, text: str) -> list[float]:
        if not text.strip():
            raise ValueError("text must not be empty")

        values: list[float] = []
        for index in range(self.dimension):
            digest = hashlib.sha256(f"{index}:{text}".encode("utf-8")).digest()
            values.append((digest[0] / 255.0) * 2.0 - 1.0)

        magnitude = math.sqrt(sum(value * value for value in values))
        return [value / magnitude for value in values]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(text) for text in texts]
