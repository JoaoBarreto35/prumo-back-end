from functools import lru_cache

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Prumo API"
    app_version: str = "1.0.0"
    environment: str = "development"
    debug: bool = True
    api_prefix: str = "/api/v1"
    frontend_url: str = "http://localhost:5173"

    database_url: str
    jwt_secret: SecretStr
    gemini_api_key: SecretStr

    access_token_minutes: int = 30
    refresh_token_days: int = 30
    gemini_model: str = "gemini-2.5-flash"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("DATABASE_URL não foi configurada.")

        normalized = value.strip()
        if normalized.startswith("postgres://"):
            normalized = normalized.replace("postgres://", "postgresql+psycopg://", 1)
        elif normalized.startswith("postgresql://"):
            normalized = normalized.replace("postgresql://", "postgresql+psycopg://", 1)
        return normalized

    @property
    def jwt_secret_value(self) -> str:
        return self.jwt_secret.get_secret_value()

    @property
    def gemini_api_key_value(self) -> str:
        return self.gemini_api_key.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
