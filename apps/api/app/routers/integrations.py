from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.auth import Principal, require_permission
from app.core.config import get_settings
from app.domain.rbac import PermissionKeys
from app.schemas.integrations import IntegrationStatusListResponse, IntegrationStatusRead

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])
integration_manager_dependency = require_permission(PermissionKeys.MANAGE_API_CREDENTIALS)


def _status(
    *,
    key: str,
    name: str,
    category: str,
    mode: str,
    enabled: bool,
    blockers: list[str],
) -> IntegrationStatusRead:
    return IntegrationStatusRead(
        key=key,
        name=name,
        category=category,
        mode=mode,
        enabled=enabled,
        configured=enabled and not blockers,
        blockers=blockers,
    )


@router.get("/status")
def read_integration_status(
    _: Annotated[Principal, Depends(integration_manager_dependency)],
) -> IntegrationStatusListResponse:
    settings = get_settings()

    openai_blockers = []
    if not settings.ai_enabled:
        openai_blockers.append("AI_ENABLED=true")
    if not settings.openai_api_key:
        openai_blockers.append("OPENAI_API_KEY")

    property_blockers = []
    if settings.property_data_provider == "rentcast" and not settings.rentcast_api_key:
        property_blockers.append("RENTCAST_API_KEY")
    elif settings.property_data_provider == "attom" and not settings.attom_api_key:
        property_blockers.append("ATTOM_API_KEY")

    voice_blockers = []
    if not settings.twilio_voice_enabled:
        voice_blockers.append("TWILIO_VOICE_ENABLED=true")
    for configured, variable in (
        (settings.twilio_account_sid, "TWILIO_ACCOUNT_SID"),
        (settings.twilio_auth_token, "TWILIO_AUTH_TOKEN"),
        (settings.twilio_api_key_sid, "TWILIO_API_KEY_SID"),
        (settings.twilio_api_key_secret, "TWILIO_API_KEY_SECRET"),
        (settings.twilio_twiml_app_sid, "TWILIO_TWIML_APP_SID"),
        (settings.twilio_voice_from_number, "TWILIO_VOICE_FROM_NUMBER"),
        (settings.twilio_webhook_base_url, "TWILIO_WEBHOOK_BASE_URL"),
    ):
        if not configured:
            voice_blockers.append(variable)

    buyer_blockers = []
    if settings.buyer_data_provider != "dealmachine":
        buyer_blockers.append("BUYER_DATA_PROVIDER=dealmachine")
    if not settings.dealmachine_api_key:
        buyer_blockers.append("DEALMACHINE_API_KEY")

    storage_blockers = list(settings.document_storage_configuration_blockers)
    monitoring_blockers = [] if settings.sentry_dsn else ["SENTRY_DSN"]

    return IntegrationStatusListResponse(
        items=[
            _status(
                key="openai",
                name="OpenAI",
                category="AI",
                mode=settings.openai_default_model,
                enabled=settings.ai_enabled,
                blockers=openai_blockers,
            ),
            _status(
                key="property-data",
                name="Property data",
                category="Underwriting",
                mode=settings.property_data_provider,
                enabled=settings.property_data_provider != "disabled",
                blockers=property_blockers,
            ),
            _status(
                key="resend",
                name="Resend",
                category="Communications",
                mode=settings.email_provider,
                enabled=settings.email_enabled,
                blockers=list(settings.email_configuration_blockers),
            ),
            _status(
                key="twilio-sms",
                name="Twilio SMS",
                category="Communications",
                mode=settings.communication_provider_mode,
                enabled=settings.twilio_sms_enabled,
                blockers=list(settings.twilio_sms_configuration_blockers),
            ),
            _status(
                key="twilio-voice",
                name="Twilio Voice",
                category="Communications",
                mode=settings.communication_provider_mode,
                enabled=settings.twilio_voice_enabled,
                blockers=voice_blockers,
            ),
            _status(
                key="signwell",
                name="SignWell",
                category="Contracts",
                mode=settings.esign_provider,
                enabled=settings.esign_provider == "signwell",
                blockers=list(settings.esign_configuration_blockers),
            ),
            _status(
                key="dealmachine",
                name="DealMachine",
                category="Buyer data",
                mode=settings.buyer_data_provider,
                enabled=settings.buyer_data_provider == "dealmachine",
                blockers=buyer_blockers,
            ),
            _status(
                key="document-storage",
                name="Document storage",
                category="Infrastructure",
                mode=settings.document_storage_provider,
                enabled=True,
                blockers=storage_blockers,
            ),
            _status(
                key="sentry",
                name="Sentry",
                category="Monitoring",
                mode=settings.sentry_environment or settings.app_env,
                enabled=bool(settings.sentry_dsn),
                blockers=monitoring_blockers,
            ),
        ]
    )
