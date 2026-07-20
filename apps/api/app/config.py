from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    web_origin: str = "http://localhost:5173"
    database_url: str | None = None

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