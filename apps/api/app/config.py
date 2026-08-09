from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_env: Literal["development", "test", "production"] = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    web_origin: str = "http://localhost:5173"
    database_url: str | None = None
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    auth_database_path: Path = ROOT_DIR / "apps" / "api" / "storage" / "auth.db"
    retrieval_chunk_max_chars: int = Field(default=1200, gt=0, le=10000)
    retrieval_chunk_overlap_chars: int = Field(default=100, ge=0, le=9999)
    retrieval_embedding_dimension: int = Field(default=32, gt=0, le=2048)
    retrieval_provider: Literal["lexical", "hash", "openai"] = "lexical"
    retrieval_storage: Literal["memory", "pgvector"] = "memory"
    openai_api_key: SecretStr | None = None
    openai_embedding_model: str = "text-embedding-3-small"
    openai_base_url: str = "https://api.openai.com/v1"

    @field_validator("web_origin")
    @classmethod
    def normalize_web_origin(cls, value: str) -> str:
        return value.strip().rstrip("/")

    @model_validator(mode="after")
    def validate_runtime_settings(self) -> "Settings":
        if self.retrieval_chunk_overlap_chars >= self.retrieval_chunk_max_chars:
            raise ValueError(
                "retrieval_chunk_overlap_chars must be smaller than retrieval_chunk_max_chars"
            )
        if self.retrieval_provider == "openai" and (
            self.openai_api_key is None
            or not self.openai_api_key.get_secret_value().strip()
        ):
            raise ValueError("OPENAI_API_KEY is required when retrieval_provider is openai")
        if self.retrieval_storage == "pgvector" and not self.database_url:
            raise ValueError("DATABASE_URL is required when retrieval_storage is pgvector")
        if self.retrieval_storage == "pgvector" and self.retrieval_provider != "openai":
            raise ValueError("retrieval_provider must be openai when retrieval_storage is pgvector")
        if self.app_env == "production":
            if not self.database_url:
                raise ValueError("DATABASE_URL is required when APP_ENV is production")
            database = urlparse(self.database_url)
            if (
                database.scheme not in {"postgres", "postgresql"}
                or not database.hostname
                or not database.path.strip("/")
            ):
                raise ValueError(
                    "DATABASE_URL must be a PostgreSQL URL with a host and database name"
                )
            origin = urlparse(self.web_origin)
            if origin.scheme != "https" or not origin.netloc:
                raise ValueError("WEB_ORIGIN must be an absolute HTTPS URL in production")
            if (
                origin.username
                or origin.password
                or origin.path
                or origin.query
                or origin.fragment
            ):
                raise ValueError(
                    "WEB_ORIGIN must not contain credentials, path, query, or fragment"
                )
        return self

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def web_origins(self) -> list[str]:
        origins = {self.web_origin}

        if self.app_env == "development":
            origins.update(
                {
                    "http://localhost:5173",
                    "http://127.0.0.1:5173",
                }
            )

        return sorted(origins)


@lru_cache
def get_settings() -> Settings:
    return Settings()
