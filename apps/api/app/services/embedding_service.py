from __future__ import annotations

import hashlib
import math
from typing import Protocol

import httpx


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


class OpenAIEmbeddingProvider:
    """OpenAI embeddings adapter selected explicitly for production use."""

    dimension = 1536

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "text-embedding-3-small",
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 30.0,
    ) -> None:
        if not api_key.strip():
            raise ValueError("api_key must not be empty")
        if not model.strip():
            raise ValueError("model must not be empty")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def embed_text(self, text: str) -> list[float]:
        if not text.strip():
            raise ValueError("text must not be empty")
        return self.embed_many([text])[0]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if any(not text.strip() for text in texts):
            raise ValueError("texts must not contain empty values")

        response = httpx.post(
            f"{self.base_url}/embeddings",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={"model": self.model, "input": texts},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        data = sorted(payload.get("data", []), key=lambda item: item["index"])
        vectors = [item["embedding"] for item in data]
        if len(vectors) != len(texts):
            raise ValueError("embedding response count did not match input count")
        if any(len(vector) != self.dimension for vector in vectors):
            raise ValueError("embedding response dimension was unexpected")
        return vectors
