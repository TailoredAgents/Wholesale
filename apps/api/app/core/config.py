from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="local", validation_alias="APP_ENV")
    log_level: str = Field(default="info", validation_alias="LOG_LEVEL")
    database_url: str = Field(
        default="postgresql+psycopg:///real_estate_wholesale",
        validation_alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")
    api_cors_origins_raw: str = Field(
        default="http://localhost:3000", validation_alias="API_CORS_ORIGINS"
    )
    default_organization_name: str = Field(
        default="Stonegate Home Buyers",
        validation_alias="DEFAULT_ORGANIZATION_NAME",
    )
    speed_to_lead_due_minutes: int = Field(
        default=5,
        validation_alias="SPEED_TO_LEAD_DUE_MINUTES",
    )
    ai_enabled: bool = Field(default=True, validation_alias="AI_ENABLED")
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    openai_base_url: str = Field(
        default="https://api.openai.com/v1",
        validation_alias="OPENAI_BASE_URL",
    )
    openai_default_model: str = Field(
        default="gpt-5.6-terra",
        validation_alias="OPENAI_DEFAULT_MODEL",
    )
    openai_reasoning_effort: str = Field(
        default="medium",
        validation_alias="OPENAI_REASONING_EFFORT",
    )
    openai_web_search_enabled: bool = Field(
        default=False,
        validation_alias="OPENAI_WEB_SEARCH_ENABLED",
    )
    openai_request_timeout_seconds: float = Field(
        default=30.0,
        validation_alias="OPENAI_REQUEST_TIMEOUT_SECONDS",
    )
    property_data_provider: str = Field(default="attom", validation_alias="PROPERTY_DATA_PROVIDER")
    attom_api_key: str | None = Field(default=None, validation_alias="ATTOM_API_KEY")
    rentcast_api_key: str | None = Field(default=None, validation_alias="RENTCAST_API_KEY")
    bridge_api_base_url: str | None = Field(default=None, validation_alias="BRIDGE_API_BASE_URL")
    bridge_api_key: str | None = Field(default=None, validation_alias="BRIDGE_API_KEY")
    clerk_issuer: str | None = Field(default=None, validation_alias="CLERK_ISSUER")
    clerk_jwks_url: str | None = Field(default=None, validation_alias="CLERK_JWKS_URL")
    clerk_audience: str | None = Field(default=None, validation_alias="CLERK_AUDIENCE")
    clerk_authorized_parties_raw: str = Field(
        default="http://localhost:3000",
        validation_alias="CLERK_AUTHORIZED_PARTIES",
    )
    clerk_secret_key: str | None = Field(default=None, validation_alias="CLERK_SECRET_KEY")

    @field_validator("database_url")
    @classmethod
    def normalize_postgres_driver(cls, value: str) -> str:
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    @property
    def api_cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.api_cors_origins_raw.split(",") if origin.strip()]

    @property
    def clerk_authorized_parties(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.clerk_authorized_parties_raw.split(",")
            if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
