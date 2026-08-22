from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_permission
from app.core.config import get_settings
from app.core.database import get_db
from app.domain.rbac import PermissionKeys
from app.models.foundation import BatchDialerCampaign, BatchDialerSyncCheckpoint
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
    runtime_status: str | None = None,
    last_success_at: datetime | None = None,
    details: list[str] | None = None,
) -> IntegrationStatusRead:
    return IntegrationStatusRead(
        key=key,
        name=name,
        category=category,
        mode=mode,
        enabled=enabled,
        configured=enabled and not blockers,
        blockers=blockers,
        runtime_status=runtime_status,
        last_success_at=last_success_at,
        details=details or [],
    )


@router.get("/status")
def read_integration_status(
    principal: Annotated[Principal, Depends(integration_manager_dependency)],
    db: Annotated[Session, Depends(get_db)],
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

    voice_blockers = list(settings.twilio_voice_configuration_blockers)
    call_intelligence_blockers = list(settings.call_intelligence_configuration_blockers)
    batchdialer_blockers = list(settings.batchdialer_configuration_blockers)
    batchdialer_checkpoint = db.scalar(
        select(BatchDialerSyncCheckpoint).where(
            BatchDialerSyncCheckpoint.organization_id == principal.organization_id,
            BatchDialerSyncCheckpoint.stream == "cdrs",
        )
    )
    batchdialer_campaign_count = len(
        db.scalars(
            select(BatchDialerCampaign.id).where(
                BatchDialerCampaign.organization_id == principal.organization_id,
                BatchDialerCampaign.is_active.is_(True),
            )
        ).all()
    )
    batchdialer_runtime_status = (
        batchdialer_checkpoint.status
        if batchdialer_checkpoint is not None
        else ("not_started" if not batchdialer_blockers else "not_configured")
    )
    batchdialer_details = [f"{batchdialer_campaign_count} active campaign(s) discovered"]
    if batchdialer_checkpoint is not None:
        batchdialer_details.append(
            f"{batchdialer_checkpoint.archived_event_count} new CDR event(s) archived"
        )
        batchdialer_details.append(
            f"{batchdialer_checkpoint.quarantined_event_count} unknown result(s) quarantined"
        )

    buyer_blockers = []
    if settings.buyer_data_provider != "dealmachine":
        buyer_blockers.append("BUYER_DATA_PROVIDER=dealmachine")
    if not settings.dealmachine_api_key:
        buyer_blockers.append("DEALMACHINE_API_KEY")

    dealmachine_comp_blockers = []
    if settings.underwriting_dealmachine_comps_mode == "disabled":
        dealmachine_comp_blockers.append("UNDERWRITING_DEALMACHINE_COMPS_MODE=shadow or candidate")
    if not settings.dealmachine_api_key:
        dealmachine_comp_blockers.append("DEALMACHINE_API_KEY")

    realestateapi_blockers = []
    if settings.underwriting_realestateapi_comps_mode == "disabled":
        realestateapi_blockers.append("UNDERWRITING_REALESTATEAPI_COMPS_MODE=shadow or candidate")
    if not settings.realestateapi_api_key:
        realestateapi_blockers.append("REALESTATEAPI_API_KEY")

    land_workflow_blockers = []
    if not settings.land_workflow_enabled:
        land_workflow_blockers.append("LAND_WORKFLOW_ENABLED=true")
    if not settings.realestateapi_api_key:
        land_workflow_blockers.append("REALESTATEAPI_API_KEY")

    comp_analyst_blockers = []
    if settings.underwriting_ai_comp_analyst_mode == "disabled":
        comp_analyst_blockers.append("UNDERWRITING_AI_COMP_ANALYST_MODE=draft")
    if not settings.ai_enabled:
        comp_analyst_blockers.append("AI_ENABLED=true")
    if not settings.openai_api_key:
        comp_analyst_blockers.append("OPENAI_API_KEY")

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
                key="call-intelligence",
                name="Call recording and AI notes",
                category="Communications",
                mode=settings.openai_transcription_model,
                enabled=(
                    settings.twilio_voice_enabled
                    and settings.twilio_voice_recording_enabled
                    and settings.call_transcription_enabled
                ),
                blockers=call_intelligence_blockers,
            ),
            _status(
                key="batchdialer",
                name="BatchDialer direct sync",
                category="Prospecting",
                mode="direct_api",
                enabled=True,
                blockers=batchdialer_blockers,
                runtime_status=batchdialer_runtime_status,
                last_success_at=(
                    batchdialer_checkpoint.last_success_at
                    if batchdialer_checkpoint is not None
                    else None
                ),
                details=batchdialer_details,
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
                key="dealmachine-underwriting",
                name="DealMachine comps",
                category="Underwriting",
                mode=settings.underwriting_dealmachine_comps_mode,
                enabled=settings.underwriting_dealmachine_comps_mode != "disabled",
                blockers=dealmachine_comp_blockers,
            ),
            _status(
                key="realestateapi-underwriting",
                name="RealEstateAPI property intelligence",
                category="Underwriting",
                mode=settings.underwriting_realestateapi_comps_mode,
                enabled=settings.underwriting_realestateapi_comps_mode != "disabled",
                blockers=realestateapi_blockers,
            ),
            _status(
                key="land-property-research",
                name="Land property research",
                category="Property intelligence",
                mode="enabled" if settings.land_workflow_enabled else "disabled",
                enabled=settings.land_workflow_enabled,
                blockers=land_workflow_blockers,
            ),
            _status(
                key="ai-comp-analyst",
                name="AI Comp Analyst",
                category="Underwriting",
                mode=settings.underwriting_ai_comp_analyst_mode,
                enabled=settings.underwriting_ai_comp_analyst_mode != "disabled",
                blockers=comp_analyst_blockers,
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
