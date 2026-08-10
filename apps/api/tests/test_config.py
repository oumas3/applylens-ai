import pytest
from pydantic import ValidationError

from app.config import Settings


SMTP_SETTINGS = {
    "email_delivery": "smtp",
    "smtp_host": "smtp.example.com",
    "smtp_username": "applylens",
    "smtp_password": "test-password",
    "smtp_from_email": "support@example.com",
}


def test_retrieval_settings_have_stable_development_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.retrieval_chunk_max_chars == 1200
    assert settings.retrieval_chunk_overlap_chars == 100
    assert settings.retrieval_embedding_dimension == 32
    assert settings.retrieval_provider == "lexical"
    assert settings.retrieval_storage == "memory"
    assert settings.log_level == "INFO"


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


def test_openai_retrieval_rejects_blank_api_key() -> None:
    with pytest.raises(ValidationError, match="OPENAI_API_KEY is required"):
        Settings(
            _env_file=None,
            retrieval_provider="openai",
            openai_api_key="   ",
        )


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


def test_production_requires_database_url() -> None:
    with pytest.raises(ValidationError, match="DATABASE_URL is required"):
        Settings(
            _env_file=None,
            app_env="production",
            web_origin="https://app.applylens.example",
        )


def test_production_requires_https_web_origin() -> None:
    with pytest.raises(ValidationError, match="absolute HTTPS URL"):
        Settings(
            _env_file=None,
            app_env="production",
            web_origin="http://localhost:5173",
            database_url="postgresql://postgres/applylens",
        )


def test_production_rejects_invalid_database_url() -> None:
    with pytest.raises(ValidationError, match="must be a PostgreSQL URL"):
        Settings(
            _env_file=None,
            app_env="production",
            web_origin="https://app.applylens.example",
            database_url="sqlite:///applylens.db",
        )


def test_production_accepts_persistent_https_configuration() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        web_origin="https://app.applylens.example",
        database_url="postgresql://postgres/applylens",
        log_level="WARNING",
        **SMTP_SETTINGS,
    )

    assert settings.app_env == "production"
    assert settings.web_origins == ["https://app.applylens.example"]
    assert settings.log_level == "WARNING"


def test_web_origin_is_normalized_for_exact_cors_matching() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        web_origin=" https://app.applylens.example/ ",
        database_url="postgresql://postgres/applylens",
        **SMTP_SETTINGS,
    )

    assert settings.web_origin == "https://app.applylens.example"
    assert settings.web_origins == ["https://app.applylens.example"]


def test_production_rejects_web_origin_with_path() -> None:
    with pytest.raises(ValidationError, match="must not contain"):
        Settings(
            _env_file=None,
            app_env="production",
            web_origin="https://app.applylens.example/path",
            database_url="postgresql://postgres/applylens",
        )


def test_production_requires_smtp_delivery() -> None:
    with pytest.raises(ValidationError, match="EMAIL_DELIVERY must be smtp"):
        Settings(
            _env_file=None,
            app_env="production",
            web_origin="https://app.applylens.example",
            database_url="postgresql://postgres/applylens",
        )


def test_smtp_delivery_requires_complete_credentials() -> None:
    with pytest.raises(ValidationError, match="SMTP_HOST is required"):
        Settings(_env_file=None, email_delivery="smtp")


def test_production_requires_encrypted_smtp_transport() -> None:
    with pytest.raises(ValidationError, match="SMTP_STARTTLS must be true"):
        Settings(
            _env_file=None,
            app_env="production",
            web_origin="https://app.applylens.example",
            database_url="postgresql://postgres/applylens",
            smtp_starttls=False,
            **SMTP_SETTINGS,
        )
