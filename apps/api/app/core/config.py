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
    bootstrap_admin_email: str | None = Field(
        default=None,
        validation_alias="BOOTSTRAP_ADMIN_EMAIL",
    )
    bootstrap_admin_name: str | None = Field(default=None, validation_alias="BOOTSTRAP_ADMIN_NAME")
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
    openai_transcription_model: str = Field(
        default="gpt-4o-transcribe-diarize",
        validation_alias="OPENAI_TRANSCRIPTION_MODEL",
    )
    call_transcription_enabled: bool = Field(
        default=True,
        validation_alias="CALL_TRANSCRIPTION_ENABLED",
    )
    call_transcription_poll_seconds: int = Field(
        default=10,
        ge=2,
        le=300,
        validation_alias="CALL_TRANSCRIPTION_POLL_SECONDS",
    )
    call_transcription_max_attempts: int = Field(
        default=3,
        ge=1,
        le=10,
        validation_alias="CALL_TRANSCRIPTION_MAX_ATTEMPTS",
    )
    call_transcription_max_audio_bytes: int = Field(
        default=25_000_000,
        ge=1_000_000,
        le=25_000_000,
        validation_alias="CALL_TRANSCRIPTION_MAX_AUDIO_BYTES",
    )
    property_data_provider: str = Field(
        default="rentcast",
        validation_alias="PROPERTY_DATA_PROVIDER",
    )
    attom_api_key: str | None = Field(default=None, validation_alias="ATTOM_API_KEY")
    rentcast_api_key: str | None = Field(default=None, validation_alias="RENTCAST_API_KEY")
    rentcast_base_url: str = Field(
        default="https://api.rentcast.io/v1",
        validation_alias="RENTCAST_BASE_URL",
    )
    bridge_api_base_url: str | None = Field(default=None, validation_alias="BRIDGE_API_BASE_URL")
    bridge_api_key: str | None = Field(default=None, validation_alias="BRIDGE_API_KEY")
    twilio_sms_enabled: bool = Field(default=False, validation_alias="TWILIO_SMS_ENABLED")
    twilio_account_sid: str | None = Field(default=None, validation_alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str | None = Field(default=None, validation_alias="TWILIO_AUTH_TOKEN")
    twilio_api_key_sid: str | None = Field(default=None, validation_alias="TWILIO_API_KEY_SID")
    twilio_api_key_secret: str | None = Field(
        default=None,
        validation_alias="TWILIO_API_KEY_SECRET",
    )
    twilio_messaging_service_sid: str | None = Field(
        default=None,
        validation_alias="TWILIO_MESSAGING_SERVICE_SID",
    )
    twilio_sms_from_number: str | None = Field(
        default=None,
        validation_alias="TWILIO_SMS_FROM_NUMBER",
    )
    twilio_webhook_base_url: str | None = Field(
        default=None,
        validation_alias="TWILIO_WEBHOOK_BASE_URL",
    )
    twilio_validate_webhook_signatures: bool = Field(
        default=True,
        validation_alias="TWILIO_VALIDATE_WEBHOOK_SIGNATURES",
    )
    twilio_sms_timezone: str = Field(
        default="America/New_York",
        validation_alias="TWILIO_SMS_TIMEZONE",
    )
    twilio_sms_allowed_start_hour: int = Field(
        default=0,
        ge=0,
        le=23,
        validation_alias="TWILIO_SMS_ALLOWED_START_HOUR",
    )
    twilio_sms_allowed_end_hour: int = Field(
        default=24,
        ge=1,
        le=24,
        validation_alias="TWILIO_SMS_ALLOWED_END_HOUR",
    )
    twilio_voice_enabled: bool = Field(default=False, validation_alias="TWILIO_VOICE_ENABLED")
    twilio_voice_from_number: str | None = Field(
        default=None,
        validation_alias="TWILIO_VOICE_FROM_NUMBER",
    )
    twilio_twiml_app_sid: str | None = Field(
        default=None,
        validation_alias="TWILIO_TWIML_APP_SID",
    )
    twilio_voice_token_ttl_seconds: int = Field(
        default=3600,
        ge=300,
        le=86400,
        validation_alias="TWILIO_VOICE_TOKEN_TTL_SECONDS",
    )
    twilio_voice_ring_timeout_seconds: int = Field(
        default=25,
        ge=10,
        le=60,
        validation_alias="TWILIO_VOICE_RING_TIMEOUT_SECONDS",
    )
    twilio_voice_timezone: str = Field(
        default="America/New_York",
        validation_alias="TWILIO_VOICE_TIMEZONE",
    )
    twilio_voice_allowed_start_hour: int = Field(
        default=9,
        ge=0,
        le=23,
        validation_alias="TWILIO_VOICE_ALLOWED_START_HOUR",
    )
    twilio_voice_allowed_end_hour: int = Field(
        default=20,
        ge=1,
        le=24,
        validation_alias="TWILIO_VOICE_ALLOWED_END_HOUR",
    )
    twilio_voice_recording_enabled: bool = Field(
        default=False,
        validation_alias="TWILIO_VOICE_RECORDING_ENABLED",
    )
    twilio_voice_recording_disclosure: str | None = Field(
        default=None,
        validation_alias="TWILIO_VOICE_RECORDING_DISCLOSURE",
    )
    underwriting_offer_low_percentage: float = Field(
        default=0.65,
        validation_alias="UNDERWRITING_OFFER_LOW_PERCENTAGE",
    )
    underwriting_offer_high_percentage: float = Field(
        default=0.70,
        validation_alias="UNDERWRITING_OFFER_HIGH_PERCENTAGE",
    )
    underwriting_default_assignment_fee_cents: int = Field(
        default=1_500_000,
        ge=0,
        validation_alias="UNDERWRITING_DEFAULT_ASSIGNMENT_FEE_CENTS",
    )
    underwriting_transaction_reserve_cents: int = Field(
        default=250_000,
        ge=0,
        validation_alias="UNDERWRITING_TRANSACTION_RESERVE_CENTS",
    )
    underwriting_purchase_cost_percentage: float = Field(
        default=0.02,
        ge=0,
        le=1,
        validation_alias="UNDERWRITING_PURCHASE_COST_PERCENTAGE",
    )
    underwriting_financing_holding_percentage: float = Field(
        default=0.06,
        ge=0,
        le=1,
        validation_alias="UNDERWRITING_FINANCING_HOLDING_PERCENTAGE",
    )
    underwriting_resale_cost_percentage: float = Field(
        default=0.08,
        ge=0,
        le=1,
        validation_alias="UNDERWRITING_RESALE_COST_PERCENTAGE",
    )
    underwriting_negotiation_reserve_percentage: float = Field(
        default=0.08,
        ge=0,
        le=1,
        validation_alias="UNDERWRITING_NEGOTIATION_RESERVE_PERCENTAGE",
    )
    underwriting_rental_target_cap_rate: float = Field(
        default=0.08,
        gt=0,
        le=1,
        validation_alias="UNDERWRITING_RENTAL_TARGET_CAP_RATE",
    )
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
            origin.strip().rstrip("/")
            for origin in self.clerk_authorized_parties_raw.split(",")
            if origin.strip()
        ]

    @property
    def twilio_sms_configuration_blockers(self) -> tuple[str, ...]:
        blockers: list[str] = []
        if not self.twilio_sms_enabled:
            blockers.append("TWILIO_SMS_ENABLED=true")
        if not self.twilio_account_sid:
            blockers.append("TWILIO_ACCOUNT_SID")
        if not self.twilio_auth_token and not (
            self.twilio_api_key_sid and self.twilio_api_key_secret
        ):
            blockers.append(
                "TWILIO_AUTH_TOKEN or both TWILIO_API_KEY_SID and TWILIO_API_KEY_SECRET"
            )
        if not self.twilio_messaging_service_sid:
            blockers.append("TWILIO_MESSAGING_SERVICE_SID")
        if not self.twilio_sms_from_number:
            blockers.append("TWILIO_SMS_FROM_NUMBER")
        if not self.twilio_webhook_base_url:
            blockers.append("TWILIO_WEBHOOK_BASE_URL")
        return tuple(blockers)

    @property
    def twilio_sms_configured(self) -> bool:
        return not self.twilio_sms_configuration_blockers

    @property
    def twilio_voice_configured(self) -> bool:
        return bool(
            self.twilio_voice_enabled
            and self.twilio_account_sid
            and self.twilio_api_key_sid
            and self.twilio_api_key_secret
            and self.twilio_twiml_app_sid
            and self.twilio_voice_from_number
            and self.twilio_webhook_base_url
            and self.twilio_auth_token
        )

    @property
    def twilio_voice_recording_configured(self) -> bool:
        return bool(
            self.twilio_voice_configured
            and self.twilio_voice_recording_enabled
            and self.twilio_voice_recording_disclosure
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
