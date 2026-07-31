import pytest
from pydantic import ValidationError

from app.config import Settings


def test_retrieval_settings_have_stable_development_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.retrieval_chunk_max_chars == 1200
    assert settings.retrieval_chunk_overlap_chars == 100
    assert settings.retrieval_embedding_dimension == 32
    assert settings.retrieval_provider == "lexical"
    assert settings.retrieval_storage == "memory"


def test_retrieval_overlap_must_be_smaller_than_chunk_size() -> None:
    with pytest.raises(ValidationError, match="must be smaller"):
        Settings(
            _env_file=None,
            retrieval_chunk_max_chars=100,
            retrieval_chunk_overlap_chars=100,
        )


def test_retrieval_provider_accepts_hash_mode() -> None:
    settings = Settings(_env_file=None, retrieval_provider="hash")

    assert settings.retrieval_provider == "hash"


def test_retrieval_provider_accepts_openai_with_api_key() -> None:
    settings = Settings(
        _env_file=None,
        retrieval_provider="openai",
        openai_api_key="test-key",
    )

    assert settings.retrieval_provider == "openai"


def test_retrieval_provider_rejects_unknown_mode() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, retrieval_provider="unknown")


def test_openai_retrieval_requires_api_key() -> None:
    with pytest.raises(ValidationError, match="OPENAI_API_KEY is required"):
        Settings(_env_file=None, retrieval_provider="openai")


def test_pgvector_storage_requires_database_url() -> None:
    with pytest.raises(ValidationError, match="DATABASE_URL is required"):
        Settings(
            _env_file=None,
            retrieval_provider="openai",
            openai_api_key="test-key",
            retrieval_storage="pgvector",
        )


def test_pgvector_storage_accepts_database_url() -> None:
    settings = Settings(
        _env_file=None,
        retrieval_provider="openai",
        openai_api_key="test-key",
        retrieval_storage="pgvector",
        database_url="postgresql://localhost/applylens",
    )

    assert settings.retrieval_storage == "pgvector"


def test_pgvector_storage_requires_openai_provider() -> None:
    with pytest.raises(ValidationError, match="retrieval_provider must be openai"):
        Settings(
            _env_file=None,
            retrieval_storage="pgvector",
            database_url="postgresql://localhost/applylens",
        )
