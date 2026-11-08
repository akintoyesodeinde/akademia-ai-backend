from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Akademia AI"
    app_env: Literal["development", "test", "staging", "production"] = "development"
    debug: bool = False
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"

    # Database connection settings for distinct runtime roles
    database_url: str = (
        "postgresql+asyncpg://akademia_app:akademia_app_dev_pw@127.0.0.1:5436/akademia_ai?ssl=disable"
    )
    migration_database_url: str = (
        "postgresql+asyncpg://akademia_migrator:akademia_migrator_dev_pw@127.0.0.1:5436/akademia_ai?ssl=disable"
    )
    worker_database_url: str = (
        "postgresql+asyncpg://akademia_worker:akademia_worker_dev_pw@127.0.0.1:5436/akademia_ai?ssl=disable"
    )
    superuser_database_url: str = (
        "postgresql+asyncpg://postgres:postgres_dev_pw@127.0.0.1:5436/akademia_ai?ssl=disable"
    )

    # Redis
    redis_url: str = "redis://localhost:6386/0"

    # Authentication & Session Security
    jwt_secret_key: str = Field(
        default="akademia-local-dev-secret-key-at-least-32-chars",
        min_length=32,
    )
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14
    session_cookie_name: str = "akademia_refresh_token"
    csrf_cookie_name: str = "akademia_csrf_token"
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"

    # CORS
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://localhost:5175",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:5175",
        ]
    )

    # Object Storage
    storage_backend: Literal["local"] = "local"
    local_storage_path: str = "./storage_data"
    max_upload_size_bytes: int = 25 * 1024 * 1024  # 25 MiB

    # AI Provider Configuration (Provider-Neutral)
    ai_provider: Literal["deterministic", "openai_compatible"] = "deterministic"
    ai_api_key: str = ""
    ai_base_url: str = "https://api.openai.com/v1"
    ai_chat_model: str = "akademia-grounded-v1"
    ai_embedding_model: str = "akademia-embed-v1"
    ai_embedding_dimension: int = 64
    ai_max_input_tokens: int = 6000
    ai_max_output_tokens: int = 1500
    ai_request_timeout_seconds: int = 30
    ai_max_retries: int = 2
    ai_input_cost_per_1k_tokens_usd: float = 0.0005
    ai_output_cost_per_1k_tokens_usd: float = 0.0015
    ai_embedding_cost_per_1k_tokens_usd: float = 0.0001

    # Email
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_from_email: str = "noreply@akademia.ai"

    # Rate Limiting
    rate_limit_default_per_minute: int = 300
    rate_limit_auth_per_minute: int = 40
    rate_limit_ai_per_minute: int = 60

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_secret_key(cls, v: str, info) -> str:
        if len(v.strip()) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters long")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
