from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
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
    lead_manager_handoff_sla_minutes: int = Field(
        default=60,
        ge=5,
        le=480,
        validation_alias="LEAD_MANAGER_HANDOFF_SLA_MINUTES",
    )
    mailbox_first_response_target_minutes: int = Field(
        default=30,
        ge=1,
        le=1440,
        validation_alias="MAILBOX_FIRST_RESPONSE_TARGET_MINUTES",
    )
    mailbox_next_response_target_minutes: int = Field(
        default=120,
        ge=1,
        le=2880,
        validation_alias="MAILBOX_NEXT_RESPONSE_TARGET_MINUTES",
    )
    mailbox_unassigned_escalation_minutes: int = Field(
        default=15,
        ge=1,
        le=1440,
        validation_alias="MAILBOX_UNASSIGNED_ESCALATION_MINUTES",
    )
    mailbox_owner_escalation_minutes: int = Field(
        default=240,
        ge=5,
        le=10080,
        validation_alias="MAILBOX_OWNER_ESCALATION_MINUTES",
    )
    communication_provider_mode: Literal["disabled", "simulate", "live"] = Field(
        default="live",
        validation_alias="COMMUNICATION_PROVIDER_MODE",
    )
    worker_readiness_required: bool = Field(
        default=False,
        validation_alias="WORKER_READINESS_REQUIRED",
    )
    worker_heartbeat_interval_seconds: int = Field(
        default=30,
        ge=5,
        le=300,
        validation_alias="WORKER_HEARTBEAT_INTERVAL_SECONDS",
    )
    worker_stale_after_seconds: int = Field(
        default=120,
        ge=15,
        le=1800,
        validation_alias="WORKER_STALE_AFTER_SECONDS",
    )
    worker_retry_base_seconds: int = Field(
        default=15,
        ge=1,
        le=300,
        validation_alias="WORKER_RETRY_BASE_SECONDS",
    )
    worker_retry_max_seconds: int = Field(
        default=900,
        ge=15,
        le=3600,
        validation_alias="WORKER_RETRY_MAX_SECONDS",
    )
    operations_alert_webhook_url: str | None = Field(
        default=None,
        validation_alias="OPERATIONS_ALERT_WEBHOOK_URL",
    )
    operations_alert_after_failures: int = Field(
        default=3,
        ge=1,
        le=100,
        validation_alias="OPERATIONS_ALERT_AFTER_FAILURES",
    )
    sentry_dsn: str | None = Field(default=None, validation_alias="SENTRY_DSN")
    sentry_environment: str | None = Field(
        default=None,
        validation_alias="SENTRY_ENVIRONMENT",
    )
    sentry_traces_sample_rate: float = Field(
        default=0.05,
        ge=0,
        le=1,
        validation_alias="SENTRY_TRACES_SAMPLE_RATE",
    )
    ai_enabled: bool = Field(default=True, validation_alias="AI_ENABLED")
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    openai_base_url: str = Field(
        default="https://api.openai.com/v1",
        validation_alias="OPENAI_BASE_URL",
    )
    openai_default_model: str = Field(
        default="gpt-5.6-sol",
        validation_alias="OPENAI_DEFAULT_MODEL",
    )
    openai_high_volume_model: str | None = Field(
        default=None,
        validation_alias="OPENAI_HIGH_VOLUME_MODEL",
    )
    openai_escalation_model: str | None = Field(
        default=None,
        validation_alias="OPENAI_ESCALATION_MODEL",
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
        default=75.0,
        validation_alias="OPENAI_REQUEST_TIMEOUT_SECONDS",
    )
    openai_pricing_overrides_raw: str = Field(
        default="",
        validation_alias="OPENAI_PRICING_OVERRIDES_JSON",
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
    call_recording_retention_days: int = Field(
        default=180,
        ge=1,
        le=3650,
        validation_alias="CALL_RECORDING_RETENTION_DAYS",
    )
    email_enabled: bool = Field(default=False, validation_alias="EMAIL_ENABLED")
    email_provider: Literal["disabled", "simulate", "google", "resend"] = Field(
        default="disabled",
        validation_alias="EMAIL_PROVIDER",
    )
    email_sync_enabled: bool = Field(default=False, validation_alias="EMAIL_SYNC_ENABLED")
    email_sync_poll_seconds: int = Field(
        default=30,
        ge=10,
        le=900,
        validation_alias="EMAIL_SYNC_POLL_SECONDS",
    )
    email_max_attachment_bytes: int = Field(
        default=10_000_000,
        ge=1_000_000,
        le=25_000_000,
        validation_alias="EMAIL_MAX_ATTACHMENT_BYTES",
    )
    email_token_encryption_key: str | None = Field(
        default=None,
        validation_alias="EMAIL_TOKEN_ENCRYPTION_KEY",
    )
    email_oauth_state_secret: str | None = Field(
        default=None,
        validation_alias="EMAIL_OAUTH_STATE_SECRET",
    )
    email_web_app_base_url: str = Field(
        default="http://localhost:3000",
        validation_alias="EMAIL_WEB_APP_BASE_URL",
    )
    resend_api_key: str | None = Field(default=None, validation_alias="RESEND_API_KEY")
    resend_webhook_secret: str | None = Field(
        default=None,
        validation_alias="RESEND_WEBHOOK_SECRET",
    )
    resend_sending_domain: str = Field(
        default="stonegatehb.com",
        validation_alias="RESEND_SENDING_DOMAIN",
    )
    resend_receiving_domain: str = Field(
        default="stonegatehb.com",
        validation_alias="RESEND_RECEIVING_DOMAIN",
    )
    resend_default_from_email: str = Field(
        default="offers@stonegatehb.com",
        validation_alias="RESEND_DEFAULT_FROM_EMAIL",
    )
    resend_webhook_base_url: str = Field(
        default="http://localhost:8000",
        validation_alias="RESEND_WEBHOOK_BASE_URL",
    )
    document_storage_provider: Literal["database", "s3"] = Field(
        default="database",
        validation_alias="DOCUMENT_STORAGE_PROVIDER",
    )
    document_storage_endpoint_url: str | None = Field(
        default=None,
        validation_alias="DOCUMENT_STORAGE_ENDPOINT_URL",
    )
    document_storage_bucket: str | None = Field(
        default=None,
        validation_alias="DOCUMENT_STORAGE_BUCKET",
    )
    document_storage_access_key_id: str | None = Field(
        default=None,
        validation_alias="DOCUMENT_STORAGE_ACCESS_KEY_ID",
    )
    document_storage_secret_access_key: str | None = Field(
        default=None,
        validation_alias="DOCUMENT_STORAGE_SECRET_ACCESS_KEY",
    )
    document_storage_region: str = Field(
        default="auto",
        validation_alias="DOCUMENT_STORAGE_REGION",
    )
    document_storage_download_ttl_seconds: int = Field(
        default=300,
        ge=30,
        le=3600,
        validation_alias="DOCUMENT_STORAGE_DOWNLOAD_TTL_SECONDS",
    )
    document_retention_days: int = Field(
        default=2555,
        ge=1,
        le=7300,
        validation_alias="DOCUMENT_RETENTION_DAYS",
    )
    document_malware_scanner: Literal["disabled", "clamav"] = Field(
        default="disabled",
        validation_alias="DOCUMENT_MALWARE_SCANNER",
    )
    document_malware_scan_required: bool = Field(
        default=False,
        validation_alias="DOCUMENT_MALWARE_SCAN_REQUIRED",
    )
    clamav_host: str | None = Field(default=None, validation_alias="CLAMAV_HOST")
    clamav_port: int = Field(default=3310, ge=1, le=65535, validation_alias="CLAMAV_PORT")
    clamav_timeout_seconds: float = Field(
        default=15,
        ge=1,
        le=120,
        validation_alias="CLAMAV_TIMEOUT_SECONDS",
    )
    esign_provider: Literal["disabled", "simulate", "signwell"] = Field(
        default="disabled",
        validation_alias="ESIGN_PROVIDER",
    )
    esign_api_key: str | None = Field(default=None, validation_alias="ESIGN_API_KEY")
    esign_base_url: str = Field(
        default="https://www.signwell.com/api/v1",
        validation_alias="ESIGN_BASE_URL",
    )
    esign_signwell_webhook_id: str | None = Field(
        default=None,
        validation_alias="ESIGN_SIGNWELL_WEBHOOK_ID",
    )
    esign_webhook_callback_url: str = Field(
        default="https://api.stonegatehb.com/api/v1/webhooks/esign/signwell",
        validation_alias="ESIGN_WEBHOOK_CALLBACK_URL",
    )
    esign_test_mode: bool = Field(default=True, validation_alias="ESIGN_TEST_MODE")
    esign_request_timeout_seconds: float = Field(
        default=30,
        ge=5,
        le=120,
        validation_alias="ESIGN_REQUEST_TIMEOUT_SECONDS",
    )
    google_oauth_client_id: str | None = Field(
        default=None,
        validation_alias="GOOGLE_OAUTH_CLIENT_ID",
    )
    google_oauth_client_secret: str | None = Field(
        default=None,
        validation_alias="GOOGLE_OAUTH_CLIENT_SECRET",
    )
    google_oauth_redirect_uri: str = Field(
        default="http://localhost:8000/api/v1/email/oauth/google/callback",
        validation_alias="GOOGLE_OAUTH_REDIRECT_URI",
    )
    property_data_provider: str = Field(
        default="rentcast",
        validation_alias="PROPERTY_DATA_PROVIDER",
    )
    buyer_data_provider: Literal["disabled", "dealmachine"] = Field(
        default="disabled",
        validation_alias="BUYER_DATA_PROVIDER",
    )
    dealmachine_api_key: str | None = Field(
        default=None,
        validation_alias="DEALMACHINE_API_KEY",
    )
    dealmachine_base_url: str = Field(
        default="https://api.v2.dealmachine.com/v1",
        validation_alias="DEALMACHINE_BASE_URL",
    )
    dealmachine_request_timeout_seconds: float = Field(
        default=30,
        ge=5,
        le=120,
        validation_alias="DEALMACHINE_REQUEST_TIMEOUT_SECONDS",
    )
    buyer_discovery_max_results: int = Field(
        default=100,
        ge=10,
        le=250,
        validation_alias="BUYER_DISCOVERY_MAX_RESULTS",
    )
    marketing_conversion_mode: Literal["disabled", "simulate", "live"] = Field(
        default="disabled",
        validation_alias="MARKETING_CONVERSION_MODE",
    )
    marketing_conversion_window_days: int = Field(
        default=90,
        ge=1,
        le=365,
        validation_alias="MARKETING_CONVERSION_WINDOW_DAYS",
    )
    marketing_conversion_max_attempts: int = Field(
        default=5,
        ge=1,
        le=20,
        validation_alias="MARKETING_CONVERSION_MAX_ATTEMPTS",
    )
    marketing_conversion_retry_base_seconds: int = Field(
        default=60,
        ge=5,
        le=3600,
        validation_alias="MARKETING_CONVERSION_RETRY_BASE_SECONDS",
    )
    marketing_website_base_url: str = Field(
        default="https://www.stonegatehb.com",
        validation_alias="MARKETING_WEBSITE_BASE_URL",
    )
    google_data_manager_client_id: str | None = Field(
        default=None,
        validation_alias="GOOGLE_DATA_MANAGER_CLIENT_ID",
    )
    google_data_manager_client_secret: str | None = Field(
        default=None,
        validation_alias="GOOGLE_DATA_MANAGER_CLIENT_SECRET",
    )
    google_data_manager_refresh_token: str | None = Field(
        default=None,
        validation_alias="GOOGLE_DATA_MANAGER_REFRESH_TOKEN",
    )
    google_data_manager_login_account_id: str | None = Field(
        default=None,
        validation_alias="GOOGLE_DATA_MANAGER_LOGIN_ACCOUNT_ID",
    )
    google_data_manager_operating_account_id: str | None = Field(
        default=None,
        validation_alias="GOOGLE_DATA_MANAGER_OPERATING_ACCOUNT_ID",
    )
    google_data_manager_conversion_actions_raw: str = Field(
        default="",
        validation_alias="GOOGLE_DATA_MANAGER_CONVERSION_ACTIONS_JSON",
    )
    meta_conversions_access_token: str | None = Field(
        default=None,
        validation_alias="META_CONVERSIONS_ACCESS_TOKEN",
    )
    meta_pixel_id: str | None = Field(default=None, validation_alias="META_PIXEL_ID")
    meta_conversions_api_version: str = Field(
        default="v25.0",
        validation_alias="META_CONVERSIONS_API_VERSION",
    )
    meta_test_event_code: str | None = Field(
        default=None,
        validation_alias="META_TEST_EVENT_CODE",
    )
    meta_lead_ads_enabled: bool = Field(
        default=False,
        validation_alias="META_LEAD_ADS_ENABLED",
    )
    meta_lead_ads_app_secret: str | None = Field(
        default=None,
        validation_alias="META_LEAD_ADS_APP_SECRET",
    )
    meta_lead_ads_verify_token: str | None = Field(
        default=None,
        validation_alias="META_LEAD_ADS_VERIFY_TOKEN",
    )
    meta_lead_ads_page_id: str | None = Field(
        default=None,
        validation_alias="META_LEAD_ADS_PAGE_ID",
    )
    meta_lead_ads_access_token: str | None = Field(
        default=None,
        validation_alias="META_LEAD_ADS_ACCESS_TOKEN",
    )
    meta_lead_ads_api_version: str = Field(
        default="v25.0",
        validation_alias="META_LEAD_ADS_API_VERSION",
    )
    meta_lead_ads_request_timeout_seconds: float = Field(
        default=30,
        ge=5,
        le=120,
        validation_alias="META_LEAD_ADS_REQUEST_TIMEOUT_SECONDS",
    )
    meta_lead_ads_max_attempts: int = Field(
        default=8,
        ge=1,
        le=25,
        validation_alias="META_LEAD_ADS_MAX_ATTEMPTS",
    )
    meta_lead_ads_retry_base_seconds: int = Field(
        default=30,
        ge=5,
        le=3600,
        validation_alias="META_LEAD_ADS_RETRY_BASE_SECONDS",
    )
    staff_lead_alert_sms_mode: Literal["disabled", "simulate", "live"] = Field(
        default="disabled",
        validation_alias="STAFF_LEAD_ALERT_SMS_MODE",
    )
    staff_lead_alert_max_attempts: int = Field(
        default=5,
        ge=1,
        le=20,
        validation_alias="STAFF_LEAD_ALERT_MAX_ATTEMPTS",
    )
    staff_lead_alert_retry_base_seconds: int = Field(
        default=30,
        ge=5,
        le=3600,
        validation_alias="STAFF_LEAD_ALERT_RETRY_BASE_SECONDS",
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
    underwriting_active_methodology_version: Literal["v2.2", "v3"] = Field(
        default="v3",
        validation_alias="UNDERWRITING_ACTIVE_METHODOLOGY_VERSION",
    )
    underwriting_v3_shadow_enabled: bool = Field(
        default=False,
        validation_alias="UNDERWRITING_V3_SHADOW_ENABLED",
    )
    underwriting_dealmachine_comps_mode: Literal["disabled", "shadow", "candidate"] = Field(
        default="disabled",
        validation_alias="UNDERWRITING_DEALMACHINE_COMPS_MODE",
    )
    underwriting_dealmachine_max_credits_per_analysis: int = Field(
        default=2,
        ge=0,
        le=25,
        validation_alias="UNDERWRITING_DEALMACHINE_MAX_CREDITS_PER_ANALYSIS",
    )
    underwriting_ai_comp_analyst_mode: Literal["disabled", "draft"] = Field(
        default="disabled",
        validation_alias="UNDERWRITING_AI_COMP_ANALYST_MODE",
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

    @model_validator(mode="after")
    def reject_production_simulation(self) -> "Settings":
        if self.app_env.lower() == "production" and self.communication_provider_mode == "simulate":
            raise ValueError("COMMUNICATION_PROVIDER_MODE=simulate is forbidden in production.")
        if self.app_env.lower() == "production" and self.esign_provider == "simulate":
            raise ValueError("ESIGN_PROVIDER=simulate is forbidden in production.")
        if self.app_env.lower() == "production" and self.marketing_conversion_mode == "simulate":
            raise ValueError("MARKETING_CONVERSION_MODE=simulate is forbidden in production.")
        if self.app_env.lower() == "production" and self.staff_lead_alert_sms_mode == "simulate":
            raise ValueError("STAFF_LEAD_ALERT_SMS_MODE=simulate is forbidden in production.")
        if (
            self.app_env.lower() == "production"
            and self.email_enabled
            and self.email_provider == "simulate"
        ):
            raise ValueError("EMAIL_PROVIDER=simulate is forbidden in production.")
        return self

    @property
    def communication_simulation_enabled(self) -> bool:
        return self.communication_provider_mode == "simulate"

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
    def email_configuration_blockers(self) -> tuple[str, ...]:
        blockers: list[str] = []
        if not self.email_enabled:
            blockers.append("EMAIL_ENABLED=true")
        if self.email_provider == "disabled":
            blockers.append("EMAIL_PROVIDER")
        elif self.email_provider == "google":
            if not self.google_oauth_client_id:
                blockers.append("GOOGLE_OAUTH_CLIENT_ID")
            if not self.google_oauth_client_secret:
                blockers.append("GOOGLE_OAUTH_CLIENT_SECRET")
            if not self.email_token_encryption_key:
                blockers.append("EMAIL_TOKEN_ENCRYPTION_KEY")
            if not self.email_oauth_state_secret:
                blockers.append("EMAIL_OAUTH_STATE_SECRET")
        elif self.email_provider == "resend":
            if not self.resend_api_key:
                blockers.append("RESEND_API_KEY")
            if not self.resend_webhook_secret:
                blockers.append("RESEND_WEBHOOK_SECRET")
            if not self.resend_sending_domain.strip():
                blockers.append("RESEND_SENDING_DOMAIN")
            if not self.resend_receiving_domain.strip():
                blockers.append("RESEND_RECEIVING_DOMAIN")
            if not self.resend_default_from_email.strip():
                blockers.append("RESEND_DEFAULT_FROM_EMAIL")
            elif not self.resend_default_from_email.lower().endswith(
                f"@{self.resend_sending_domain.strip().lower()}"
            ):
                blockers.append("RESEND_DEFAULT_FROM_EMAIL domain")
            if not self.resend_webhook_base_url.strip():
                blockers.append("RESEND_WEBHOOK_BASE_URL")
        return tuple(blockers)

    @property
    def document_storage_configuration_blockers(self) -> tuple[str, ...]:
        if self.document_storage_provider == "database":
            return ()
        blockers: list[str] = []
        if not self.document_storage_endpoint_url:
            blockers.append("DOCUMENT_STORAGE_ENDPOINT_URL")
        if not self.document_storage_bucket:
            blockers.append("DOCUMENT_STORAGE_BUCKET")
        if not self.document_storage_access_key_id:
            blockers.append("DOCUMENT_STORAGE_ACCESS_KEY_ID")
        if not self.document_storage_secret_access_key:
            blockers.append("DOCUMENT_STORAGE_SECRET_ACCESS_KEY")
        return tuple(blockers)

    @property
    def esign_configuration_blockers(self) -> tuple[str, ...]:
        if self.esign_provider == "simulate":
            return ()
        blockers: list[str] = []
        if self.esign_provider != "signwell":
            blockers.append("ESIGN_PROVIDER=signwell")
        if not self.esign_api_key:
            blockers.append("ESIGN_API_KEY")
        return tuple(blockers)

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
        return not self.twilio_voice_configuration_blockers

    @property
    def twilio_voice_configuration_blockers(self) -> tuple[str, ...]:
        blockers: list[str] = []
        if not self.twilio_voice_enabled:
            blockers.append("TWILIO_VOICE_ENABLED=true")
        for configured, variable in (
            (self.twilio_account_sid, "TWILIO_ACCOUNT_SID"),
            (self.twilio_auth_token, "TWILIO_AUTH_TOKEN"),
            (self.twilio_webhook_base_url, "TWILIO_WEBHOOK_BASE_URL"),
        ):
            if not configured:
                blockers.append(variable)
        if not self.twilio_validate_webhook_signatures:
            blockers.append("TWILIO_VALIDATE_WEBHOOK_SIGNATURES=true")
        return tuple(blockers)

    @property
    def twilio_browser_voice_configured(self) -> bool:
        return not self.twilio_browser_voice_configuration_blockers

    @property
    def twilio_browser_voice_configuration_blockers(self) -> tuple[str, ...]:
        blockers = list(self.twilio_voice_configuration_blockers)
        for configured, variable in (
            (self.twilio_api_key_sid, "TWILIO_API_KEY_SID"),
            (self.twilio_api_key_secret, "TWILIO_API_KEY_SECRET"),
            (self.twilio_twiml_app_sid, "TWILIO_TWIML_APP_SID"),
        ):
            if not configured:
                blockers.append(variable)
        return tuple(blockers)

    @property
    def twilio_voice_recording_configured(self) -> bool:
        return bool(
            self.twilio_voice_configured
            and self.twilio_voice_recording_enabled
            and self.call_recording_retention_days
        )

    @property
    def google_data_manager_conversion_actions(self) -> dict[str, str]:
        if not self.google_data_manager_conversion_actions_raw.strip():
            return {}
        import json

        try:
            parsed = json.loads(self.google_data_manager_conversion_actions_raw)
        except (TypeError, ValueError):
            return {}
        if not isinstance(parsed, dict):
            return {}
        return {
            str(key): str(value)
            for key, value in parsed.items()
            if isinstance(key, str) and isinstance(value, (str, int)) and str(value).strip()
        }

    @property
    def google_conversion_configuration_blockers(self) -> tuple[str, ...]:
        blockers: list[str] = []
        if not self.google_data_manager_client_id:
            blockers.append("GOOGLE_DATA_MANAGER_CLIENT_ID")
        if not self.google_data_manager_client_secret:
            blockers.append("GOOGLE_DATA_MANAGER_CLIENT_SECRET")
        if not self.google_data_manager_refresh_token:
            blockers.append("GOOGLE_DATA_MANAGER_REFRESH_TOKEN")
        if not self.google_data_manager_operating_account_id:
            blockers.append("GOOGLE_DATA_MANAGER_OPERATING_ACCOUNT_ID")
        required_actions = {
            "qualified_lead",
            "appointment_scheduled",
            "contract_signed",
            "funded_deal",
        }
        if not required_actions.issubset(self.google_data_manager_conversion_actions):
            blockers.append("GOOGLE_DATA_MANAGER_CONVERSION_ACTIONS_JSON")
        return tuple(blockers)

    @property
    def meta_conversion_configuration_blockers(self) -> tuple[str, ...]:
        blockers: list[str] = []
        if not self.meta_conversions_access_token:
            blockers.append("META_CONVERSIONS_ACCESS_TOKEN")
        if not self.meta_pixel_id:
            blockers.append("META_PIXEL_ID")
        return tuple(blockers)

    @property
    def meta_lead_ads_configuration_blockers(self) -> tuple[str, ...]:
        blockers: list[str] = []
        if not self.meta_lead_ads_enabled:
            blockers.append("META_LEAD_ADS_ENABLED=true")
        if not self.meta_lead_ads_app_secret:
            blockers.append("META_LEAD_ADS_APP_SECRET")
        if not self.meta_lead_ads_verify_token:
            blockers.append("META_LEAD_ADS_VERIFY_TOKEN")
        if not self.meta_lead_ads_page_id:
            blockers.append("META_LEAD_ADS_PAGE_ID")
        if not self.meta_lead_ads_access_token:
            blockers.append("META_LEAD_ADS_ACCESS_TOKEN")
        return tuple(blockers)

    @property
    def meta_lead_ads_configured(self) -> bool:
        return not self.meta_lead_ads_configuration_blockers

    @property
    def staff_lead_alert_configuration_blockers(self) -> tuple[str, ...]:
        if self.staff_lead_alert_sms_mode == "disabled":
            return ("STAFF_LEAD_ALERT_SMS_MODE=live",)
        if self.staff_lead_alert_sms_mode == "simulate":
            return ()
        return self.twilio_sms_configuration_blockers


@lru_cache
def get_settings() -> Settings:
    return Settings()
