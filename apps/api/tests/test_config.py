import pytest
from pydantic import ValidationError

from app.config import Settings


def test_retrieval_settings_have_stable_development_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.retrieval_chunk_max_chars == 1200
    assert settings.retrieval_chunk_overlap_chars == 100
    assert settings.retrieval_embedding_dimension == 32


def test_retrieval_overlap_must_be_smaller_than_chunk_size() -> None:
    with pytest.raises(ValidationError, match="must be smaller"):
        Settings(
            _env_file=None,
            retrieval_chunk_max_chars=100,
            retrieval_chunk_overlap_chars=100,
        )
