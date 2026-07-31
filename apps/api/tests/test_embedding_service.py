import math

import pytest

from app.services.embedding_service import HashEmbeddingProvider


def test_hash_embedding_has_configured_dimension_and_unit_length() -> None:
    provider = HashEmbeddingProvider(dimension=8)

    vector = provider.embed_text("English proficiency")

    assert len(vector) == 8
    assert math.isclose(math.sqrt(sum(value * value for value in vector)), 1.0)


def test_hash_embedding_is_deterministic() -> None:
    provider = HashEmbeddingProvider(dimension=8)

    assert provider.embed_text("same text") == provider.embed_text("same text")
    assert provider.embed_text("same text") != provider.embed_text("different text")


def test_hash_embedding_supports_batch_input() -> None:
    provider = HashEmbeddingProvider(dimension=4)

    vectors = provider.embed_many(["first", "second"])

    assert len(vectors) == 2
    assert all(len(vector) == 4 for vector in vectors)


def test_hash_embedding_rejects_invalid_input() -> None:
    with pytest.raises(ValueError, match="dimension must be positive"):
        HashEmbeddingProvider(dimension=0)

    with pytest.raises(ValueError, match="text must not be empty"):
        HashEmbeddingProvider().embed_text("   ")
