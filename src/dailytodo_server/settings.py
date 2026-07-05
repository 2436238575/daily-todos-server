"""Runtime configuration for DailyTodo Server."""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DAILYTODO_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://dailytodo:change-me@127.0.0.1:5432/dailytodo"
    api_root: str = ""
    bind_host: str = "127.0.0.1"
    bind_port: int = 8080
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    secret_key: str = Field(default="dev-insecure-secret-change-me", min_length=16)
    auth_rate_limit_requests: int = 20
    auth_rate_limit_window_seconds: int = 60

    @field_validator("api_root")
    @classmethod
    def normalize_api_root(cls, value: str) -> str:
        value = (value or "").strip()
        if not value or value == "/":
            return ""
        if not value.startswith("/"):
            value = f"/{value}"
        return value.rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()
