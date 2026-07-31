from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    web_origin: str = "http://localhost:5173"
    database_url: str | None = None
    retrieval_chunk_max_chars: int = Field(default=1200, gt=0, le=10000)
    retrieval_chunk_overlap_chars: int = Field(default=100, ge=0, le=9999)
    retrieval_embedding_dimension: int = Field(default=32, gt=0, le=2048)
    retrieval_provider: Literal["lexical", "hash", "openai"] = "lexical"
    openai_api_key: SecretStr | None = None
    openai_embedding_model: str = "text-embedding-3-small"
    openai_base_url: str = "https://api.openai.com/v1"

    @model_validator(mode="after")
    def validate_retrieval_settings(self) -> "Settings":
        if self.retrieval_chunk_overlap_chars >= self.retrieval_chunk_max_chars:
            raise ValueError(
                "retrieval_chunk_overlap_chars must be smaller than retrieval_chunk_max_chars"
            )
        if self.retrieval_provider == "openai" and self.openai_api_key is None:
            raise ValueError("OPENAI_API_KEY is required when retrieval_provider is openai")
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
