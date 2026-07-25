from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = Field(..., description="PostgreSQL async URL")

    # Qdrant
    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333
    qdrant_collection_name: str = "catalog_items"

    # Gemini 1.5 Flash (Voice Live API + Parser NER + Auditor Explainer) — ADR-001
    gemini_api_key: str = Field(..., description="Gemini API key — never hardcode")

    # JWT
    jwt_secret_key: str = Field(..., description="256-bit random hex — never hardcode")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480

    # Export storage
    export_base_dir: str = "/app/exports"

    # CORS — explicit list, no wildcards (security rule)
    allowed_origins: list[str] = Field(
        default=["http://localhost:3000"],
        description="Comma-separated list of allowed origins. No wildcards.",
    )

    # STT thresholds (calibrate in field)
    stt_confidence_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    anomaly_history_window: int = Field(default=5, ge=3, le=10)

    # Application
    app_env: str = "development"
    log_level: str = "INFO"


def _load_settings() -> Settings:
    settings = Settings()
    # Fail-fast: validate no secrets are empty strings
    if not settings.gemini_api_key or settings.gemini_api_key == "AIza...":
        raise ValueError("GEMINI_API_KEY is not set. Check your .env file.")
    if not settings.jwt_secret_key or len(settings.jwt_secret_key) < 32:
        raise ValueError("JWT_SECRET_KEY must be at least 32 characters.")
    return settings


settings = _load_settings()
