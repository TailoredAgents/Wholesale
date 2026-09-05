import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog
from sqlalchemy import exists, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import Settings, get_settings
from app.domain.rbac import PermissionKeys
from app.integrations.twilio_recordings import delete_twilio_recording
from app.integrations.twilio_voice import (
    InboundVoiceTarget,
    call_screen_result_twiml,
    call_screen_twiml,
    callback_url,
    create_voice_access_token,
    forwarded_outbound_screen_twiml,
    hangup_twiml,
    inbound_call_twiml,
    inbound_target_endpoint_counts,
    outbound_call_twiml,
    voice_identity,
    voicemail_twiml,
)
from app.integrations.twilio_voice_calls import (
    TwilioVoiceCallError,
    TwilioVoiceCallProvider,
    get_twilio_voice_call_provider,
)
from app.models.foundation import (
    ActivityEvent,
    AuditEvent,
    Buyer,
    CallRecord,
    CallRecording,
    CallTranscript,
    CommunicationProviderEvent,
    CommunicationRecord,
    ConsentRecord,
    Contact,
    ContactMethod,
    Conversation,
    ConversationContextLink,
    Lead,
    Property,
    Role,
    RoleAssignment,
    Task,
    Team,
    TeamMembership,
    User,
    VoiceCallIntent,
    VoiceLine,
)
from app.schemas.voice import (
    VoiceCallIntentCreate,
    VoiceCallIntentRead,
    VoiceCallStatusRead,
    VoiceForwardingUpdate,
    VoiceLineAssignmentUpdate,
    VoiceLineCreate,
    VoiceLineRead,
    VoiceLineTeamRead,
    VoiceLineUserRead,
    VoiceProviderReadinessRead,
    VoiceQuickDialCreate,
    VoiceQuickDialRead,
    VoiceReadinessCheckRead,
    VoiceRecordingRead,
    VoiceSessionRead,
)
from app.services.call_evidence_scope import get_authorized_recording
from app.services.call_intelligence import (
    enqueue_call_transcript,
    enqueue_eligible_prospecting_call_transcript,
)
from app.services.communication_compliance import (
    business_voice_permission_not_required,
    business_voice_requested_phone_number,
    evaluate_voice_eligibility,
    format_e164,
    phone_lookup_values,
)
from app.services.inbox import (
    create_general_conversation,
    ensure_buyer_conversation,
    ensure_primary_conversation,
    get_scoped_conversation,
    reactivate_closed_lead_for_inbound,
    update_conversation_activity,
)
from app.services.lead_lifecycle import (
    INACTIVE_LEAD_STAGES,
    LeadLifecycleConflictError,
    lock_organization_lead,
    require_lead_open_for_work,
)
from app.services.prospecting_callbacks import (
    complete_prospecting_callback_voicemail,
    ensure_prospecting_missed_callback_task,
    process_prospecting_inbound_callback,
    update_prospecting_callback_status,
)
from app.services.prospecting_voice import (
    ProspectingVoiceConfigurationError,
    ProspectingVoiceConflictError,
    lock_prospecting_connect_pilot,
    process_browser_prospecting_outbound_request,
    reconcile_signed_prospecting_disclosure,
    reconcile_signed_prospecting_recording,
    reconcile_signed_prospecting_status,
    validate_prospecting_connect_intent,
)

VOICE_LINE_ROUTES = {"conversation_owner", "assigned_user"}
VOICE_LINE_STATUSES = {"active", "inactive"}
VOICE_LINE_RING_STRATEGIES = {"sequential", "simultaneous"}
VOICE_LINE_DEPARTMENT_PURPOSES = {
    "acquisitions": {"seller_conversations", "prospecting_outbound"},
    "dispositions": {"buyer_relations"},
    "general": {"company_general"},
}
VOICE_LINE_MISSED_CALL_ACTIONS = {
    "fallback_then_voicemail",
    "voicemail",
    "task_only",
}
ALWAYS_ON_COVERAGE_START_HOUR = 0
ALWAYS_ON_COVERAGE_END_HOUR = 24
FINAL_CALL_STATUSES = {"completed", "busy", "failed", "no-answer", "canceled"}
logger = structlog.get_logger()
CALL_STATUS_RANK = {
    "queued": 0,
    "initiated": 1,
    "ringing": 2,
    "in-progress": 3,
    "answered": 3,
    "completed": 4,
    "busy": 4,
    "failed": 4,
    "no-answer": 4,
    "canceled": 4,
}


def recording_consent_status(settings: Settings) -> str:
    if not settings.twilio_voice_recording_configured:
        return "not_requested"
    return (
        "disclosure_configured"
        if settings.twilio_voice_recording_disclosure
        else "one_party_consent"
    )


class VoiceComplianceError(RuntimeError):
    pass


class VoiceConfigurationError(RuntimeError):
    pass


class VoiceIntentConflictError(RuntimeError):
    pass


def list_voice_lines(db: Session, principal: Principal) -> list[VoiceLineRead]:
    lines = db.scalars(
        select(VoiceLine)
        .where(VoiceLine.organization_id == principal.organization_id)
        .order_by(VoiceLine.is_default.desc(), VoiceLine.label.asc())
    ).all()
    return [voice_line_to_read(db, line) for line in lines]


def list_voice_line_users(db: Session, principal: Principal) -> list[VoiceLineUserRead]:
    users = db.scalars(
        select(User)
        .where(
            User.organization_id == principal.organization_id,
            User.is_active.is_(True),
        )
        .order_by(User.display_name.asc(), User.email.asc())
    ).all()
    return [
        VoiceLineUserRead(
            id=user.id,
            display_name=user.display_name,
            email=user.email,
            voice_forwarding_number=user.voice_forwarding_number,
            voice_forwarding_enabled=user.voice_forwarding_enabled,
            lead_alert_sms_enabled=user.lead_alert_sms_enabled,
            inbound_message_alert_sms_enabled=user.inbound_message_alert_sms_enabled,
        )
        for user in users
    ]


def update_user_voice_forwarding(
    db: Session,
    principal: Principal,
    user_id: UUID,
    payload: VoiceForwardingUpdate,
) -> VoiceLineUserRead | None:
    user = db.scalar(
        select(User).where(
            User.id == user_id,
            User.organization_id == principal.organization_id,
            User.is_active.is_(True),
        )
    )
    if user is None:
        return None
    formatted = (
        format_e164(payload.voice_forwarding_number) if payload.voice_forwarding_number else None
    )
    if payload.voice_forwarding_number and formatted is None:
        raise ValueError("Cellphone must be a valid E.164 phone number.")
    if payload.voice_forwarding_enabled and formatted is None:
        raise ValueError("Enter a cellphone number before enabling forwarding.")
    if payload.lead_alert_sms_enabled and formatted is None:
        raise ValueError("Enter a cellphone number before enabling new-lead text alerts.")
    inbound_message_alert_sms_enabled = (
        user.inbound_message_alert_sms_enabled
        if payload.inbound_message_alert_sms_enabled is None
        else payload.inbound_message_alert_sms_enabled
    )
    if inbound_message_alert_sms_enabled and formatted is None:
        raise ValueError("Enter a cellphone number before enabling inbound-message text alerts.")
    company_line = (
        db.scalar(
            select(VoiceLine.id).where(
                VoiceLine.organization_id == principal.organization_id,
                VoiceLine.phone_number == formatted,
            )
        )
        if formatted
        else None
    )
    if company_line is not None:
        raise ValueError("A Stonegate company line cannot be used as a staff cellphone.")
    previous = {
        "voice_forwarding_number": user.voice_forwarding_number,
        "voice_forwarding_enabled": user.voice_forwarding_enabled,
        "lead_alert_sms_enabled": user.lead_alert_sms_enabled,
        "inbound_message_alert_sms_enabled": user.inbound_message_alert_sms_enabled,
    }
    user.voice_forwarding_number = formatted
    user.voice_forwarding_enabled = payload.voice_forwarding_enabled
    user.lead_alert_sms_enabled = payload.lead_alert_sms_enabled
    user.inbound_message_alert_sms_enabled = inbound_message_alert_sms_enabled
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="communication.voice_forwarding_update",
            entity_type="user",
            entity_id=user.id,
            previous_value=previous,
            new_value={
                "voice_forwarding_number": formatted,
                "voice_forwarding_enabled": payload.voice_forwarding_enabled,
                "lead_alert_sms_enabled": payload.lead_alert_sms_enabled,
                "inbound_message_alert_sms_enabled": inbound_message_alert_sms_enabled,
            },
            reason="Updated staff call destination and operational text-alert preferences",
        )
    )
    db.commit()
    return VoiceLineUserRead(
        id=user.id,
        display_name=user.display_name,
        email=user.email,
        voice_forwarding_number=user.voice_forwarding_number,
        voice_forwarding_enabled=user.voice_forwarding_enabled,
        lead_alert_sms_enabled=user.lead_alert_sms_enabled,
        inbound_message_alert_sms_enabled=user.inbound_message_alert_sms_enabled,
    )


def list_voice_line_teams(db: Session, principal: Principal) -> list[VoiceLineTeamRead]:
    teams = db.scalars(
        select(Team)
        .where(
            Team.organization_id == principal.organization_id,
            Team.is_active.is_(True),
        )
        .order_by(Team.name.asc())
    ).all()
    return [
        VoiceLineTeamRead(id=team.id, name=team.name, team_type=team.team_type) for team in teams
    ]


def get_voice_provider_readiness(
    db: Session,
    principal: Principal,
) -> VoiceProviderReadinessRead:
    settings = get_settings()
    line = db.scalar(
        select(VoiceLine)
        .where(
            VoiceLine.organization_id == principal.organization_id,
            VoiceLine.department_key == "acquisitions",
            VoiceLine.purpose_key == "seller_conversations",
            VoiceLine.status == "active",
        )
        .order_by(VoiceLine.is_default.desc(), VoiceLine.created_at.asc())
    )
    environment_blockers = list(settings.twilio_voice_configuration_blockers)
    line_read = voice_line_to_read(db, line) if line is not None else None
    base_url = (settings.twilio_webhook_base_url or "https://api.stonegatehb.com").rstrip("/")
    checks = [
        VoiceReadinessCheckRead(
            key="environment",
            label="Twilio forwarding configuration",
            required=True,
            ready=not environment_blockers,
            detail=(
                "All required Voice variables are present."
                if not environment_blockers
                else f"Missing: {', '.join(environment_blockers)}"
            ),
        ),
        VoiceReadinessCheckRead(
            key="line",
            label="Active acquisitions line",
            required=True,
            ready=line is not None,
            detail=(
                f"{line.label} uses {line.phone_number}."
                if line is not None
                else "Add an active Acquisitions line in Communications settings."
            ),
        ),
        VoiceReadinessCheckRead(
            key="caller_id",
            label="Company caller ID",
            required=True,
            ready=bool(line and format_e164(line.phone_number)),
            detail=(
                f"Outbound seller calls use {line.phone_number}."
                if line is not None
                else "Add the acquisitions company number in Communications settings."
            ),
        ),
        VoiceReadinessCheckRead(
            key="ownership",
            label="Primary and fallback staff",
            required=True,
            ready=bool(line_read and line_read.ownership_complete),
            detail=(
                "Both assigned staff members have cellphone forwarding enabled."
                if line_read and line_read.ownership_complete
                else "Assign primary and fallback staff, then save both cellphone destinations."
            ),
        ),
        VoiceReadinessCheckRead(
            key="team",
            label="Department team",
            required=False,
            ready=bool(line and line.assigned_team_id),
            detail=(
                f"{line_read.assigned_team_name} joins the shared line."
                if line_read and line_read.assigned_team_name
                else "Optional: select the Acquisitions team for future staff coverage."
            ),
        ),
        VoiceReadinessCheckRead(
            key="recording",
            label="Call recording",
            required=False,
            ready=(
                not settings.twilio_voice_recording_enabled
                or settings.twilio_voice_recording_configured
            ),
            detail=(
                "Call recording is intentionally disabled for initial Voice acceptance."
                if not settings.twilio_voice_recording_enabled
                else (
                    "Recording authorization policy and retention are configured."
                    if settings.twilio_voice_recording_configured
                    else (
                        "Recording is enabled but its authorization policy or retention "
                        "is incomplete."
                    )
                )
            ),
        ),
    ]
    return VoiceProviderReadinessRead(
        configured=all(check.ready for check in checks if check.required),
        line_id=line.id if line is not None else None,
        line_phone_number=line.phone_number if line is not None else None,
        inbound_webhook_url=f"{base_url}/api/v1/webhooks/twilio/voice/incoming",
        outbound_twiml_app_url=f"{base_url}/api/v1/webhooks/twilio/voice/outbound",
        status_callback_url=f"{base_url}/api/v1/webhooks/twilio/voice/status",
        recording_callback_url=f"{base_url}/api/v1/webhooks/twilio/voice/recording",
        checks=checks,
    )


def create_voice_line(
    db: Session,
    principal: Principal,
    payload: VoiceLineCreate,
) -> VoiceLineRead:
    phone_number = format_e164(payload.phone_number)
    if phone_number is None:
        raise ValueError("Voice line must be a valid E.164 phone number.")
    validate_line_ownership(
        db,
        principal.organization_id,
        assigned_user_id=payload.assigned_user_id,
        fallback_user_id=payload.fallback_user_id,
        assigned_team_id=payload.assigned_team_id,
        department_key=payload.department_key,
        purpose_key=payload.purpose_key,
        coverage_timezone=payload.coverage_timezone,
        coverage_start_hour=ALWAYS_ON_COVERAGE_START_HOUR,
        coverage_end_hour=ALWAYS_ON_COVERAGE_END_HOUR,
        missed_call_action=payload.missed_call_action,
        ring_strategy=payload.ring_strategy,
    )
    if payload.inbound_route not in VOICE_LINE_ROUTES:
        raise ValueError("Unsupported inbound voice route.")
    existing = db.scalar(
        select(VoiceLine).where(
            VoiceLine.organization_id == principal.organization_id,
            VoiceLine.phone_number == phone_number,
        )
    )
    if existing is not None:
        raise VoiceIntentConflictError("That phone number is already a Stonegate voice line.")
    if payload.is_default:
        clear_default_lines(db, principal.organization_id)
    line = VoiceLine(
        organization_id=principal.organization_id,
        assigned_user_id=payload.assigned_user_id,
        fallback_user_id=payload.fallback_user_id,
        assigned_team_id=payload.assigned_team_id,
        provider="twilio",
        provider_phone_number_id=payload.provider_phone_number_id,
        phone_number=phone_number,
        label=payload.label.strip(),
        department_key=payload.department_key,
        purpose_key=payload.purpose_key,
        status="active",
        is_default=payload.is_default,
        inbound_route=payload.inbound_route,
        ring_strategy=payload.ring_strategy,
        coverage_timezone=payload.coverage_timezone,
        coverage_start_hour=ALWAYS_ON_COVERAGE_START_HOUR,
        coverage_end_hour=ALWAYS_ON_COVERAGE_END_HOUR,
        missed_call_action=payload.missed_call_action,
        line_metadata={"source": "voice_line_api"},
    )
    db.add(line)
    db.flush()
    record_line_audit(db, principal, line, "communication.voice_line_create")
    db.commit()
    return voice_line_to_read(db, line)


def update_voice_line(
    db: Session,
    principal: Principal,
    line_id: UUID,
    payload: VoiceLineAssignmentUpdate,
) -> VoiceLineRead | None:
    line = db.scalar(
        select(VoiceLine).where(
            VoiceLine.id == line_id,
            VoiceLine.organization_id == principal.organization_id,
        )
    )
    if line is None:
        return None
    if payload.status is not None and payload.status not in VOICE_LINE_STATUSES:
        raise ValueError("Unsupported voice line status.")
    if payload.inbound_route is not None and payload.inbound_route not in VOICE_LINE_ROUTES:
        raise ValueError("Unsupported inbound voice route.")
    assigned_user_id = (
        payload.assigned_user_id
        if "assigned_user_id" in payload.model_fields_set
        else line.assigned_user_id
    )
    fallback_user_id = (
        payload.fallback_user_id
        if "fallback_user_id" in payload.model_fields_set
        else line.fallback_user_id
    )
    assigned_team_id = (
        payload.assigned_team_id
        if "assigned_team_id" in payload.model_fields_set
        else line.assigned_team_id
    )
    department_key = payload.department_key or line.department_key
    purpose_key = payload.purpose_key or line.purpose_key
    coverage_timezone = payload.coverage_timezone or line.coverage_timezone
    next_status = payload.status or line.status
    missed_call_action = payload.missed_call_action or line.missed_call_action
    if next_status == "active":
        coverage_start_hour = ALWAYS_ON_COVERAGE_START_HOUR
        coverage_end_hour = ALWAYS_ON_COVERAGE_END_HOUR
    else:
        coverage_start_hour = (
            payload.coverage_start_hour
            if payload.coverage_start_hour is not None
            else line.coverage_start_hour
        )
        coverage_end_hour = (
            payload.coverage_end_hour
            if payload.coverage_end_hour is not None
            else line.coverage_end_hour
        )
    ring_strategy = payload.ring_strategy or line.ring_strategy
    validate_line_ownership(
        db,
        principal.organization_id,
        assigned_user_id=assigned_user_id,
        fallback_user_id=fallback_user_id,
        assigned_team_id=assigned_team_id,
        department_key=department_key,
        purpose_key=purpose_key,
        coverage_timezone=coverage_timezone,
        coverage_start_hour=coverage_start_hour,
        coverage_end_hour=coverage_end_hour,
        missed_call_action=missed_call_action,
        ring_strategy=ring_strategy,
    )
    line.assigned_user_id = assigned_user_id
    line.fallback_user_id = fallback_user_id
    line.assigned_team_id = assigned_team_id
    line.department_key = department_key
    line.purpose_key = purpose_key
    line.coverage_timezone = coverage_timezone
    line.coverage_start_hour = coverage_start_hour
    line.coverage_end_hour = coverage_end_hour
    line.missed_call_action = missed_call_action
    line.ring_strategy = ring_strategy
    if payload.label is not None:
        line.label = payload.label.strip()
    if payload.status is not None:
        line.status = payload.status
    if payload.inbound_route is not None:
        line.inbound_route = payload.inbound_route
    if payload.is_default is not None:
        if payload.is_default:
            clear_default_lines(db, principal.organization_id)
        line.is_default = payload.is_default
    record_line_audit(db, principal, line, "communication.voice_line_update")
    db.commit()
    return voice_line_to_read(db, line)


def create_voice_session(
    db: Session,
    principal: Principal,
) -> VoiceSessionRead:
    settings = get_settings()
    identity = voice_identity(str(principal.user_id))
    line = select_voice_line(db, principal.organization_id, principal.user_id)
    blockers: list[str] = []
    if not settings.twilio_browser_voice_configured:
        blockers.append("Browser calling is disabled. Stonegate calls use staff cellphones.")
    if line is None:
        blockers.append("No active Stonegate voice line is available.")
    if blockers:
        return VoiceSessionRead(
            can_initialize=False,
            identity=identity,
            token=None,
            expires_at=None,
            line=voice_line_to_read(db, line) if line else None,
            recording_enabled=settings.twilio_voice_recording_configured,
            blockers=blockers,
        )
    assert line is not None
    token, expires_at = create_voice_access_token(settings, identity=identity)
    return VoiceSessionRead(
        can_initialize=True,
        identity=identity,
        token=token,
        expires_at=expires_at,
        line=voice_line_to_read(db, line),
        recording_enabled=settings.twilio_voice_recording_configured,
        blockers=[],
    )


def get_call_intent_status(
    db: Session,
    principal: Principal,
    intent_id: UUID,
) -> VoiceCallStatusRead | None:
    intent = db.scalar(
        select(VoiceCallIntent).where(
            VoiceCallIntent.id == intent_id,
            VoiceCallIntent.organization_id == principal.organization_id,
            VoiceCallIntent.actor_user_id == principal.user_id,
        )
    )
    if intent is None or intent.prospecting_dial_leg_id is not None:
        return None
    call = db.scalar(select(CallRecord).where(CallRecord.call_intent_id == intent.id))
    provider_status = call.status if call is not None else intent.status
    return VoiceCallStatusRead(
        intent_id=intent.id,
        call_id=call.id if call is not None else None,
        status=provider_status,
        answered_at=call.answered_at if call is not None else None,
        ended_at=call.ended_at if call is not None else None,
        duration_seconds=call.duration_seconds if call is not None else None,
        terminal=provider_status in FINAL_CALL_STATUSES,
    )


def create_quick_dial_intent(
    db: Session,
    principal: Principal,
    payload: VoiceQuickDialCreate,
) -> VoiceQuickDialRead:
    """Create or reuse a lightweight business thread and authorize one browser call.

    Quick Dial is intentionally unavailable to assigned-only callers. The destination is
    normalized by the server, and the caller may select only a company-owned VoiceLine that
    the current user is assigned to. The client never supplies a caller-ID phone number.
    """

    if PermissionKeys.PLACE_CALLS not in principal.permission_keys:
        raise PermissionError("Quick Dial requires permission to place company calls.")
    destination = format_e164(payload.phone_number)
    if destination is None:
        raise VoiceComplianceError("Enter a valid phone number to use Quick Dial.")
    validate_quick_dial_destination(db, principal, destination)
    request_fingerprint = quick_dial_request_fingerprint(payload, destination)

    existing_intent = db.scalar(
        select(VoiceCallIntent).where(
            VoiceCallIntent.organization_id == principal.organization_id,
            VoiceCallIntent.idempotency_key == payload.idempotency_key,
        )
    )
    if existing_intent is not None:
        return existing_quick_dial_to_read(
            db,
            principal,
            payload,
            destination=destination,
            request_fingerprint=request_fingerprint,
            intent=existing_intent,
        )

    contact, conversation = find_quick_dial_context(
        db,
        principal.organization_id,
        destination,
    )
    reused_contact = contact is not None
    reused_conversation = conversation is not None
    if contact is None:
        display_name = clean_quick_dial_name(payload) or f"Business {destination}"
        contact = Contact(
            organization_id=principal.organization_id,
            legal_name=display_name,
            preferred_name=None,
            contact_type="business_contact",
            assigned_user_id=principal.user_id,
        )
        db.add(contact)
        db.flush()
        db.add(
            ContactMethod(
                organization_id=principal.organization_id,
                contact_id=contact.id,
                method_type="phone",
                value=destination,
                normalized_value="".join(
                    character for character in destination if character.isdigit()
                ),
                is_primary=True,
            )
        )
        db.flush()
    if conversation is None:
        conversation = create_general_conversation(
            db,
            organization_id=principal.organization_id,
            contact_id=contact.id,
            assigned_user_id=principal.user_id,
        )
    elif conversation.conversation_type == "general" and conversation.status == "closed":
        conversation.status = "open"
        conversation.closed_at = None
    conversation.conversation_metadata = {
        **(conversation.conversation_metadata or {}),
        "source": (
            (conversation.conversation_metadata or {}).get("source")
            if reused_conversation
            else "quick_dial"
        ),
        "quick_dial": {
            "company_name": clean_optional_text(payload.company_name),
            "contact_name": clean_optional_text(payload.contact_name),
            "phone_number": destination,
            "purpose": payload.purpose,
            "call_reason": clean_optional_text(payload.call_reason),
            "prepared_by_user_id": str(principal.user_id),
            "request_fingerprint": request_fingerprint,
        },
    }
    try:
        intent_read = create_call_intent(
            db,
            principal,
            conversation.id,
            VoiceCallIntentCreate(
                idempotency_key=payload.idempotency_key,
                voice_line_id=(
                    payload.voice_line_id if conversation.conversation_type == "general" else None
                ),
            ),
            intent_source="quick_dial",
            extra_intent_metadata={
                "quick_dial_purpose": payload.purpose,
                "call_reason": clean_optional_text(payload.call_reason),
                "request_fingerprint": request_fingerprint,
            },
            require_browser_voice=True,
            # Quick Dial is an explicit, human-initiated call. Reusing an existing
            # seller or buyer conversation must not silently add a permission gate
            # that a newly created business conversation does not have. Active phone
            # and all-channel suppressions remain enforced by voice eligibility.
            require_recorded_permission=False,
            requested_recipient=destination,
            commit=False,
        )
    except IntegrityError as exc:
        db.rollback()
        winner = db.scalar(
            select(VoiceCallIntent).where(
                VoiceCallIntent.organization_id == principal.organization_id,
                VoiceCallIntent.idempotency_key == payload.idempotency_key,
            )
        )
        if winner is None:
            raise VoiceIntentConflictError(
                "The Quick Dial request conflicted with another call. Try again."
            ) from exc
        return existing_quick_dial_to_read(
            db,
            principal,
            payload,
            destination=destination,
            request_fingerprint=request_fingerprint,
            intent=winner,
        )
    except (
        LeadLifecycleConflictError,
        PermissionError,
        VoiceComplianceError,
        VoiceConfigurationError,
        VoiceIntentConflictError,
    ):
        db.rollback()
        raise
    if intent_read is None:
        db.rollback()
        raise VoiceConfigurationError("The Quick Dial call intent could not be created.")
    intent = db.get(VoiceCallIntent, intent_read.id)
    if intent is None:
        raise VoiceConfigurationError("The Quick Dial call intent could not be saved.")
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="communication.quick_dial_prepare",
            entity_type="conversation",
            entity_id=conversation.id,
            previous_value=None,
            new_value={
                "contact_id": str(contact.id),
                "conversation_type": conversation.conversation_type,
                "voice_line_id": str(intent.voice_line_id),
                "recipient": destination,
                "purpose": payload.purpose,
                "reused_contact": reused_contact,
                "reused_conversation": reused_conversation,
            },
            reason=clean_optional_text(payload.call_reason) or "Manual company Quick Dial prepared",
        )
    )
    db.commit()
    line = db.get(VoiceLine, intent.voice_line_id)
    if line is None:
        raise VoiceConfigurationError("The selected Stonegate voice line no longer exists.")
    return VoiceQuickDialRead(
        conversation_id=conversation.id,
        contact_id=contact.id,
        conversation_type=conversation.conversation_type,
        contact_name=contact.legal_name,
        reused_contact=reused_contact,
        reused_conversation=reused_conversation,
        intent=call_intent_to_read(intent, line, get_settings()),
    )


def create_call_intent(
    db: Session,
    principal: Principal,
    conversation_id: UUID,
    payload: VoiceCallIntentCreate,
    *,
    intent_source: str = "shared_inbox",
    extra_intent_metadata: dict[str, object] | None = None,
    require_browser_voice: bool = False,
    require_recorded_permission: bool = True,
    requested_recipient: str | None = None,
    commit: bool = True,
) -> VoiceCallIntentRead | None:
    conversation = get_scoped_conversation(db, principal, conversation_id)
    if conversation is None:
        return None
    if PermissionKeys.PLACE_CALLS not in principal.permission_keys and (
        PermissionKeys.PLACE_ASSIGNED_CALLS not in principal.permission_keys
        or conversation.assigned_user_id != principal.user_id
    ):
        raise PermissionError("Calls can only be placed from an assigned conversation.")
    if conversation.conversation_type not in {"lead", "buyer", "general"}:
        raise VoiceConfigurationError(
            "Calling is only available from seller, buyer, and company conversations."
        )
    if (
        conversation.conversation_type == "general"
        and PermissionKeys.PLACE_CALLS not in principal.permission_keys
    ):
        raise PermissionError("Company calls require permission to place calls.")
    settings = get_settings()
    if require_browser_voice and not settings.twilio_browser_voice_configured:
        raise VoiceConfigurationError(
            "Browser calling needs: "
            + ", ".join(settings.twilio_browser_voice_configuration_blockers)
            + "."
        )
    active_lead: Lead | None = None
    if conversation.conversation_type == "lead" and conversation.lead_id is not None:
        active_lead = lock_organization_lead(
            db,
            organization_id=principal.organization_id,
            lead_id=conversation.lead_id,
        )
        if active_lead is None:
            return None
        require_lead_open_for_work(active_lead)
    existing = db.scalar(
        select(VoiceCallIntent).where(
            VoiceCallIntent.organization_id == principal.organization_id,
            VoiceCallIntent.idempotency_key == payload.idempotency_key,
        )
    )
    if existing is not None:
        validate_call_intent_replay(
            existing,
            principal,
            conversation=conversation,
            payload=payload,
            intent_source=intent_source,
        )
        line = db.get(VoiceLine, existing.voice_line_id)
        if line is None:
            raise VoiceConfigurationError("The selected Stonegate voice line no longer exists.")
        return call_intent_to_read(existing, line, get_settings())

    contact = db.get(Contact, conversation.contact_id)
    lead = active_lead
    if conversation.conversation_type == "lead" and lead is None:
        return None
    if contact is None:
        return None
    recorded_permission_required = (
        require_recorded_permission
        and not business_voice_permission_not_required(conversation, contact)
    )
    eligibility = evaluate_voice_eligibility(
        db,
        contact,
        require_permission=recorded_permission_required,
        requested_phone_number=(
            requested_recipient
            or business_voice_requested_phone_number(conversation, contact)
        ),
    )
    if not eligibility.can_call or eligibility.recipient is None:
        raise VoiceComplianceError(" ".join(eligibility.blockers))
    line = select_voice_line_for_conversation(
        db,
        principal.organization_id,
        principal.user_id,
        conversation=conversation,
        requested_line_id=payload.voice_line_id,
    )
    if line is None:
        department = (
            "dispositions"
            if conversation.conversation_type == "buyer"
            else "company"
            if conversation.conversation_type == "general"
            else "acquisitions"
        )
        raise VoiceConfigurationError(
            f"No authorized active Stonegate {department} line is available."
        )
    now = datetime.now(UTC)
    intent = VoiceCallIntent(
        organization_id=principal.organization_id,
        conversation_id=conversation.id,
        lead_id=lead.id if lead is not None else None,
        contact_id=contact.id,
        actor_user_id=principal.user_id,
        voice_line_id=line.id,
        idempotency_key=payload.idempotency_key,
        recipient=eligibility.recipient,
        status="pending",
        recording_consent_status=recording_consent_status(settings),
        expires_at=now + timedelta(minutes=5),
        consumed_at=None,
        provider_call_id=None,
        intent_metadata={
            "source": intent_source,
            "conversation_type": conversation.conversation_type,
            "department_key": line.department_key,
            "recorded_permission_required": recorded_permission_required,
            **(extra_intent_metadata or {}),
        },
    )
    db.add(intent)
    try:
        if commit:
            db.commit()
        else:
            db.flush()
    except IntegrityError as exc:
        if not commit:
            raise
        db.rollback()
        winner = db.scalar(
            select(VoiceCallIntent).where(
                VoiceCallIntent.organization_id == principal.organization_id,
                VoiceCallIntent.idempotency_key == payload.idempotency_key,
            )
        )
        if winner is None:
            raise VoiceIntentConflictError(
                "The call request conflicted with another request. Try again."
            ) from exc
        validate_call_intent_replay(
            winner,
            principal,
            conversation=conversation,
            payload=payload,
            intent_source=intent_source,
        )
        winner_line = db.get(VoiceLine, winner.voice_line_id)
        if winner_line is None:
            raise VoiceConfigurationError(
                "The selected Stonegate voice line no longer exists."
            ) from exc
        return call_intent_to_read(winner, winner_line, settings)
    return call_intent_to_read(intent, line, settings)


def start_forwarded_call(
    db: Session,
    principal: Principal,
    conversation_id: UUID,
    payload: VoiceCallIntentCreate,
    *,
    provider: TwilioVoiceCallProvider | None = None,
    require_recorded_permission: bool = True,
) -> VoiceCallIntentRead | None:
    intent_read = create_call_intent(
        db,
        principal,
        conversation_id,
        payload,
        intent_source="forwarded_cellphone",
        require_recorded_permission=require_recorded_permission,
    )
    if intent_read is None:
        return None
    intent = db.get(VoiceCallIntent, intent_read.id)
    if intent is None:
        return None
    conversation_id, contact_id = require_warm_call_intent_context(intent)
    if intent.lead_id is not None:
        lead = lock_organization_lead(
            db,
            organization_id=intent.organization_id,
            lead_id=intent.lead_id,
        )
        if lead is None:
            return None
        require_lead_open_for_work(lead)
    line = db.get(VoiceLine, intent.voice_line_id)
    user = db.get(User, principal.user_id)
    if line is None or line.status != "active":
        raise VoiceConfigurationError("The Stonegate company line is unavailable.")
    forwarding_number = format_e164(user.voice_forwarding_number or "") if user else None
    if user is None or not user.voice_forwarding_enabled or forwarding_number is None:
        raise VoiceConfigurationError(
            "Add and enable your cellphone under Settings > Communications before calling."
        )
    if intent.status == "started" and intent.provider_call_id:
        return call_intent_to_read(intent, line, get_settings())

    settings = get_settings()
    if not settings.twilio_voice_configured:
        raise VoiceConfigurationError("Twilio cellphone calling is not configured.")
    try:
        result = (provider or get_twilio_voice_call_provider()).start(
            to=forwarding_number,
            from_number=line.phone_number,
            twiml=forwarded_outbound_screen_twiml(settings, intent_id=str(intent.id)),
            status_callback=callback_url(
                settings,
                "/api/v1/webhooks/twilio/voice/status",
                intent_id=str(intent.id),
            ),
        )
    except TwilioVoiceCallError:
        intent.status = "failed"
        db.commit()
        raise
    communication, call = create_call_records(
        db,
        organization_id=intent.organization_id,
        conversation_id=conversation_id,
        lead_id=intent.lead_id,
        contact_id=contact_id,
        actor_user_id=intent.actor_user_id,
        voice_line_id=line.id,
        call_intent_id=intent.id,
        provider_call_id=result.sid,
        direction="outbound",
        status=result.status,
        from_number=line.phone_number,
        to_number=intent.recipient,
        recording_consent_status=intent.recording_consent_status,
    )
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise VoiceConfigurationError("Call conversation is unavailable.")
    entity_type, entity_id = conversation_activity_entity(db, conversation)
    db.add(
        ActivityEvent(
            organization_id=intent.organization_id,
            actor_user_id=intent.actor_user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            event_type=f"{entity_type}.call_started",
            summary=(
                "Outbound company call started through the Stonegate cellphone bridge."
                if entity_type == "conversation"
                else "Outbound call started through the Stonegate cellphone bridge."
            ),
        )
    )
    db.add(
        AuditEvent(
            organization_id=intent.organization_id,
            actor_user_id=intent.actor_user_id,
            actor_type="user",
            action="communication.voice_call_start",
            entity_type="call_record",
            entity_id=call.id,
            previous_value=None,
            new_value={
                "conversation_id": str(intent.conversation_id),
                "communication_record_id": str(communication.id),
                "from": line.phone_number,
                "to": intent.recipient,
            },
            reason="Call initiated through the Stonegate cellphone bridge",
        )
    )
    record_provider_event(
        db,
        organization_id=intent.organization_id,
        conversation_id=intent.conversation_id,
        event_type="voice.outbound.forwarded",
        external_event_id=f"voice:outbound:{result.sid}",
        payload={"CallSid": result.sid, "CallStatus": result.status},
    )
    intent.status = "started"
    intent.consumed_at = datetime.now(UTC)
    intent.provider_call_id = result.sid
    db.commit()
    return call_intent_to_read(intent, line, settings)


def start_forwarded_lead_call(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    payload: VoiceCallIntentCreate,
    *,
    provider: TwilioVoiceCallProvider | None = None,
    require_recorded_permission: bool = True,
) -> VoiceCallIntentRead | None:
    lead = lock_organization_lead(
        db,
        organization_id=principal.organization_id,
        lead_id=lead_id,
    )
    if lead is None:
        return None
    require_lead_open_for_work(lead)
    if PermissionKeys.PLACE_CALLS not in principal.permission_keys and (
        PermissionKeys.PLACE_ASSIGNED_CALLS not in principal.permission_keys
        or lead.assigned_user_id != principal.user_id
    ):
        raise PermissionError("Calls can only be placed from an assigned lead.")
    conversation = ensure_primary_conversation(db, lead)
    return start_forwarded_call(
        db,
        principal,
        conversation.id,
        payload,
        provider=provider,
        require_recorded_permission=require_recorded_permission,
    )


def create_lead_call_intent(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    payload: VoiceCallIntentCreate,
) -> VoiceCallIntentRead | None:
    """Authorize one browser call from a lead without making the client find its thread."""

    lead = lock_organization_lead(
        db,
        organization_id=principal.organization_id,
        lead_id=lead_id,
    )
    if lead is None:
        return None
    require_lead_open_for_work(lead)
    conversation = ensure_primary_conversation(db, lead)
    return create_call_intent(
        db,
        principal,
        conversation.id,
        payload,
        intent_source="lead_detail",
        require_browser_voice=True,
        require_recorded_permission=False,
    )


def process_forwarded_voice_connect(
    db: Session,
    payload: dict[str, str],
    *,
    intent_id: UUID,
) -> str:
    expected_pilot_id = lock_prospecting_connect_pilot(db, intent_id)
    # Serialize the press-1 bridge boundary so a provider retry cannot receive
    # two seller-dial TwiML responses before the first child callback arrives.
    intent = db.scalar(
        select(VoiceCallIntent)
        .where(VoiceCallIntent.id == intent_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if intent is None or intent.status != "started":
        raise VoiceConfigurationError("Stonegate forwarded call is unavailable.")
    if payload.get("Digits") != "1":
        return hangup_twiml()
    if intent.prospect_id is not None:
        try:
            validate_prospecting_connect_intent(
                db,
                intent,
                payload,
                expected_pilot_id=expected_pilot_id,
            )
        except (ProspectingVoiceConfigurationError, ProspectingVoiceConflictError) as exc:
            raise VoiceConfigurationError(str(exc)) from exc
        db.commit()
    if intent.lead_id is not None:
        lead = lock_organization_lead(
            db,
            organization_id=intent.organization_id,
            lead_id=intent.lead_id,
        )
        if lead is None:
            raise VoiceConfigurationError("The call's seller lead is unavailable.")
        require_lead_open_for_work(lead)
        intent = db.scalar(
            select(VoiceCallIntent)
            .where(
                VoiceCallIntent.id == intent_id,
                VoiceCallIntent.organization_id == lead.organization_id,
            )
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        if intent is None or intent.status != "started":
            raise VoiceConfigurationError("Stonegate forwarded call is unavailable.")
    if intent.prospect_id is None:
        _, contact_id = require_warm_call_intent_context(intent)
        contact = db.get(Contact, contact_id)
        if contact is None or contact.organization_id != intent.organization_id:
            raise VoiceConfigurationError("Call contact is unavailable.")
        recorded_permission_required = bool(
            (intent.intent_metadata or {}).get("recorded_permission_required", True)
        )
        eligibility = evaluate_voice_eligibility(
            db,
            contact,
            require_permission=recorded_permission_required,
            requested_phone_number=intent.recipient,
        )
        if (
            not eligibility.can_call
            or eligibility.recipient is None
            or eligibility.recipient != intent.recipient
        ):
            detail = " ".join(eligibility.blockers) or "The contact phone number changed."
            raise VoiceConfigurationError(f"Call authorization is no longer valid. {detail}")
    line = db.get(VoiceLine, intent.voice_line_id)
    if line is None or line.status != "active":
        raise VoiceConfigurationError("Stonegate voice line is unavailable.")
    return outbound_call_twiml(
        get_settings(),
        recipient=intent.recipient,
        from_number=line.phone_number,
        intent_id=str(intent.id),
        recording_enabled=get_settings().twilio_voice_recording_configured,
    )


def process_outbound_voice_request(
    db: Session,
    payload: dict[str, str],
    *,
    intent_id: UUID,
) -> str:
    settings = get_settings()
    intent = db.get(VoiceCallIntent, intent_id)
    if intent is None:
        raise ValueError("Unknown Stonegate call intent.")
    if intent.prospect_id is not None:
        try:
            return process_browser_prospecting_outbound_request(
                db,
                intent,
                payload,
                settings=settings,
            )
        except ProspectingVoiceConflictError as exc:
            raise VoiceConfigurationError(str(exc)) from exc
        except ProspectingVoiceConfigurationError as exc:
            raise VoiceConfigurationError(str(exc)) from exc
    conversation_id, contact_id = require_warm_call_intent_context(intent)
    if intent.lead_id is not None:
        lead = lock_organization_lead(
            db,
            organization_id=intent.organization_id,
            lead_id=intent.lead_id,
        )
        if lead is None:
            raise VoiceConfigurationError("The call's seller lead is unavailable.")
        require_lead_open_for_work(lead)
    if as_utc(intent.expires_at) < datetime.now(UTC):
        intent.status = "expired"
        db.commit()
        raise ValueError("Stonegate call intent expired.")
    expected_identity = voice_identity(str(intent.actor_user_id))
    caller_identity = payload.get("From", "").removeprefix("client:")
    if caller_identity != expected_identity:
        raise PermissionError("Voice SDK identity does not match the call intent.")
    call_sid = required_voice_value(payload, "CallSid")
    if intent.status != "pending" and (
        intent.status != "started" or intent.provider_call_id != call_sid
    ):
        raise ValueError("Stonegate call intent has already been used.")
    existing_call = find_call(db, intent.organization_id, provider_call_id=call_sid)
    line = db.get(VoiceLine, intent.voice_line_id)
    if line is None or line.organization_id != intent.organization_id:
        raise VoiceConfigurationError("Stonegate voice line is unavailable.")
    if existing_call is None:
        if line.status != "active":
            raise VoiceConfigurationError("Stonegate voice line is no longer active.")
        conversation = db.get(Conversation, conversation_id)
        contact = db.get(Contact, contact_id)
        if (
            conversation is None
            or conversation.organization_id != intent.organization_id
            or contact is None
            or contact.organization_id != intent.organization_id
        ):
            raise VoiceConfigurationError("Call conversation is unavailable.")
        recorded_permission_required = bool(
            (intent.intent_metadata or {}).get("recorded_permission_required", True)
        )
        eligibility = evaluate_voice_eligibility(
            db,
            contact,
            require_permission=recorded_permission_required,
            requested_phone_number=intent.recipient,
        )
        if (
            not eligibility.can_call
            or eligibility.recipient is None
            or eligibility.recipient != intent.recipient
        ):
            detail = " ".join(eligibility.blockers) or "The contact phone number changed."
            raise VoiceConfigurationError(f"Call authorization is no longer valid. {detail}")
    if existing_call is None:
        communication, call = create_call_records(
            db,
            organization_id=intent.organization_id,
            conversation_id=conversation_id,
            lead_id=intent.lead_id,
            contact_id=contact_id,
            actor_user_id=intent.actor_user_id,
            voice_line_id=line.id,
            call_intent_id=intent.id,
            provider_call_id=call_sid,
            direction="outbound",
            status="initiated",
            from_number=line.phone_number,
            to_number=intent.recipient,
            recording_consent_status=intent.recording_consent_status,
        )
        conversation = db.get(Conversation, conversation_id)
        if conversation is None:
            raise VoiceConfigurationError("Call conversation is unavailable.")
        entity_type, entity_id = conversation_activity_entity(db, conversation)
        db.add(
            ActivityEvent(
                organization_id=intent.organization_id,
                actor_user_id=intent.actor_user_id,
                entity_type=entity_type,
                entity_id=entity_id,
                event_type=f"{entity_type}.call_started",
                summary=(
                    "Outbound buyer call initiated from the shared inbox."
                    if entity_type == "buyer"
                    else "Outbound company call initiated from Quick Dial."
                    if entity_type == "conversation"
                    else "Outbound seller call initiated from the shared inbox."
                ),
            )
        )
        db.add(
            AuditEvent(
                organization_id=intent.organization_id,
                actor_user_id=intent.actor_user_id,
                actor_type="user",
                action="communication.voice_call_start",
                entity_type="call_record",
                entity_id=call.id,
                previous_value=None,
                new_value={
                    "conversation_id": str(intent.conversation_id),
                    "communication_record_id": str(communication.id),
                    "from": line.phone_number,
                    "to": intent.recipient,
                },
                reason="Browser call authorized by one-time call intent",
            )
        )
        record_provider_event(
            db,
            organization_id=intent.organization_id,
            conversation_id=intent.conversation_id,
            event_type="voice.outbound",
            external_event_id=f"voice:outbound:{call_sid}",
            payload=payload,
        )
    intent.status = "started"
    intent.consumed_at = datetime.now(UTC)
    intent.provider_call_id = call_sid
    db.commit()
    return outbound_call_twiml(
        settings,
        recipient=intent.recipient,
        from_number=line.phone_number,
        intent_id=str(intent.id),
        recording_enabled=settings.twilio_voice_recording_configured,
    )


def inbound_browser_call_context(
    db: Session,
    conversation: Conversation | None,
    caller: str,
) -> tuple[str, str, str]:
    contact = db.get(Contact, conversation.contact_id) if conversation is not None else None
    caller_number = format_e164(caller) or caller
    caller_name = (
        (contact.preferred_name or contact.legal_name).strip()
        if contact is not None
        else caller_number
    )
    return (
        caller_name or caller_number,
        caller_number,
        (
            f"/os/inbox?conversation={conversation.id}&channel=call"
            if conversation is not None
            else "/os/inbox"
        ),
    )


def process_inbound_voice_request(db: Session, payload: dict[str, str]) -> str:
    settings = get_settings()
    caller = required_voice_value(payload, "From")
    recipient = required_voice_value(payload, "To")
    call_sid = required_voice_value(payload, "CallSid")
    line = find_voice_line_by_number(db, recipient)
    if line is None or not settings.twilio_voice_configured:
        raise VoiceConfigurationError("Inbound Stonegate Voice is not configured for this number.")
    if line.purpose_key == "prospecting_outbound":
        return process_prospecting_inbound_callback(
            db,
            line,
            caller=caller,
            provider_call_id=call_sid,
            settings=settings,
        )
    existing = find_call(db, line.organization_id, provider_call_id=call_sid)
    if existing is not None:
        if existing.conversation_id is None:
            raise VoiceConfigurationError("Inbound call context is unavailable.")
        target_user_ids = resolve_inbound_users(db, line, existing.conversation_id)
        targets = resolve_inbound_targets(
            db,
            target_user_ids,
            include_browser=settings.twilio_browser_voice_configured,
        )
        if not targets:
            if line.missed_call_action in {"voicemail", "fallback_then_voicemail"}:
                return voicemail_twiml(settings, call_id=str(existing.id))
            ensure_missed_call_task(db, existing)
            db.commit()
            return hangup_twiml("Stonegate is unavailable. We will return your call shortly.")
        update_call_routing_metadata(
            existing,
            line,
            targets,
            browser_enabled=settings.twilio_browser_voice_configured,
        )
        db.commit()
        caller_name, caller_number, context_href = inbound_browser_call_context(
            db,
            db.get(Conversation, existing.conversation_id),
            caller,
        )
        return inbound_call_twiml(
            settings,
            targets=targets,
            call_id=str(existing.id),
            caller_name=caller_name,
            caller_number=caller_number,
            context_href=context_href,
            line_label=line.label,
            line_number=line.phone_number,
            recording_enabled=settings.twilio_voice_recording_configured,
            ring_strategy=line.ring_strategy,
        )
    conversation_type = (
        "buyer"
        if line.purpose_key == "buyer_relations"
        else "general"
        if line.purpose_key == "company_general"
        else "lead"
    )
    conversation = find_conversation_by_phone(
        db,
        line.organization_id,
        caller,
        conversation_type=conversation_type,
    )
    if conversation is None and conversation_type == "general":
        # A known seller or buyer may call the general company line. Preserve the existing
        # CRM history instead of creating a duplicate business contact solely from the line used.
        for known_type in ("lead", "buyer"):
            conversation = find_conversation_by_phone(
                db,
                line.organization_id,
                caller,
                conversation_type=known_type,
            )
            if conversation is not None:
                break
    if conversation is None and conversation_type != "general":
        # A company contacted through Quick Dial may return the call on an acquisitions or
        # dispositions line. Reuse its business thread before creating a fake seller or buyer.
        conversation = find_conversation_by_phone(
            db,
            line.organization_id,
            caller,
            conversation_type="general",
        )
    if conversation is None:
        conversation = (
            create_inbound_call_buyer(db, line, caller)
            if conversation_type == "buyer"
            else create_inbound_call_general(db, line, caller)
            if conversation_type == "general"
            else create_inbound_call_lead(db, line, caller)
        )
    target_user_ids = resolve_inbound_users(db, line, conversation.id)
    communication, call = create_call_records(
        db,
        organization_id=line.organization_id,
        conversation_id=conversation.id,
        lead_id=conversation.lead_id,
        contact_id=conversation.contact_id,
        actor_user_id=None,
        voice_line_id=line.id,
        call_intent_id=None,
        provider_call_id=call_sid,
        direction="inbound",
        status="ringing",
        from_number=format_e164(caller) or caller,
        to_number=line.phone_number,
        recording_consent_status=recording_consent_status(settings),
    )
    communication.body = f"Inbound call from {format_e164(caller) or caller}"
    targets = resolve_inbound_targets(
        db,
        target_user_ids,
        include_browser=settings.twilio_browser_voice_configured,
    )
    update_call_routing_metadata(
        call,
        line,
        targets,
        browser_enabled=settings.twilio_browser_voice_configured,
    )
    update_conversation_activity(
        conversation,
        direction="inbound",
        occurred_at=call.started_at or datetime.now(UTC),
        db=db,
    )
    entity_type, entity_id = conversation_activity_entity(db, conversation)
    db.add(
        ActivityEvent(
            organization_id=line.organization_id,
            actor_user_id=None,
            entity_type=entity_type,
            entity_id=entity_id,
            event_type=f"{entity_type}.call_received",
            summary=(
                "Inbound buyer call received."
                if entity_type == "buyer"
                else "Inbound company call received."
                if entity_type == "conversation"
                else "Inbound seller call received."
            ),
        )
    )
    record_provider_event(
        db,
        organization_id=line.organization_id,
        conversation_id=conversation.id,
        event_type="voice.inbound",
        external_event_id=f"voice:inbound:{call_sid}",
        payload=payload,
    )
    db.commit()
    if not targets:
        if line.missed_call_action in {"voicemail", "fallback_then_voicemail"}:
            return voicemail_twiml(settings, call_id=str(call.id))
        ensure_missed_call_task(db, call)
        db.commit()
        return hangup_twiml("Stonegate is unavailable. We will return your call shortly.")
    browser_count, mobile_count = inbound_target_endpoint_counts(
        targets,
        browser_enabled=settings.twilio_browser_voice_configured,
    )
    logger.info(
        "voice_inbound_routing_prepared",
        call_id=str(call.id),
        line_id=str(line.id),
        ring_strategy=line.ring_strategy,
        browser_targets=browser_count,
        mobile_targets=mobile_count,
        total_targets=browser_count + mobile_count,
    )
    caller_name, caller_number, context_href = inbound_browser_call_context(
        db,
        conversation,
        caller,
    )
    return inbound_call_twiml(
        settings,
        targets=targets,
        call_id=str(call.id),
        caller_name=caller_name,
        caller_number=caller_number,
        context_href=context_href,
        line_label=line.label,
        line_number=line.phone_number,
        recording_enabled=settings.twilio_voice_recording_configured,
        ring_strategy=line.ring_strategy,
    )


def process_voice_screen_request(
    db: Session,
    *,
    call_id: UUID,
    answered_user_id: UUID,
    mobile: bool,
) -> str:
    call, line, user = validate_screening_target(db, call_id, answered_user_id)
    return call_screen_twiml(
        get_settings(),
        call_id=str(call.id),
        answered_user_id=str(user.id),
        announcement=voice_line_announcement(line),
        require_acceptance=mobile,
    )


def process_voice_screen_result(
    db: Session,
    payload: dict[str, str],
    *,
    call_id: UUID,
    answered_user_id: UUID,
) -> str:
    call, _line, user = validate_screening_target(db, call_id, answered_user_id)
    accepted = payload.get("Digits") == "1"
    if accepted and call.actor_user_id is None:
        call.actor_user_id = user.id
        communication = (
            db.get(CommunicationRecord, call.communication_record_id)
            if call.communication_record_id
            else None
        )
        if communication is not None:
            communication.actor_user_id = user.id
        call.call_metadata = {
            **(call.call_metadata or {}),
            "mobile_screen_accepted_by_user_id": str(user.id),
            "mobile_screen_accepted_at": datetime.now(UTC).isoformat(),
        }
        update_prospecting_callback_status(db, call, "answered")
        db.commit()
    logger.info(
        "voice_mobile_screen_completed",
        call_id=str(call.id),
        answered_user_id=str(user.id),
        accepted=accepted,
        response_received=bool(payload.get("Digits")),
    )
    return call_screen_result_twiml(accepted=accepted)


def process_voice_status(
    db: Session,
    payload: dict[str, str],
    *,
    intent_id: UUID | None = None,
    call_id: UUID | None = None,
    answered_user_id: UUID | None = None,
    signature_verified: bool = False,
    signature: str | None = None,
    callback_kind: Literal["status", "dial_result"] = "status",
) -> str:
    status = (
        payload.get("DialCallStatus")
        or payload.get("CallStatus")
        or required_voice_value(payload, "CallStatus")
    ).lower()
    call = resolve_callback_call(db, payload, intent_id=intent_id, call_id=call_id)
    if call is None:
        return "unmatched"
    if call.prospecting_dial_leg_id is not None:
        return reconcile_signed_prospecting_status(
            db,
            call,
            payload,
            status=status,
            signature_verified=signature_verified,
            signature=signature,
            callback_kind=callback_kind,
        )
    event_sid = payload.get("CallSid") or payload.get("DialCallSid") or call.provider_call_id
    event_id = f"voice:status:{event_sid}:{status}"
    existing_event = get_voice_provider_event(db, call.organization_id, event_id)
    if existing_event is not None:
        return existing_event.processing_status
    apply_call_status(
        db,
        call,
        status,
        payload,
        answered_user_id=answered_user_id,
    )
    if call.prospecting_inbound_callback_id is not None:
        child_callback = bool(payload.get("ParentCallSid"))
        aggregate_terminal = callback_kind == "dial_result" or (
            not child_callback and status in FINAL_CALL_STATUSES
        )
        callback_status = status if status in {"in-progress", "answered"} else call.status
        update_prospecting_callback_status(
            db,
            call,
            callback_status,
            aggregate_terminal=aggregate_terminal,
        )
    event = record_provider_event(
        db,
        organization_id=call.organization_id,
        conversation_id=call.conversation_id,
        event_type="voice.status",
        external_event_id=event_id,
        payload=payload,
    )
    event.processing_status = "processed"
    event.processed_at = datetime.now(UTC)
    db.commit()
    logger.info(
        "voice_status_processed",
        call_id=str(call.id),
        intent_id=str(intent_id) if intent_id is not None else None,
        callback_kind=callback_kind,
        provider_status=status,
        direction=call.direction,
        child_leg=bool(payload.get("ParentCallSid")),
        answered_user_id=(str(answered_user_id) if answered_user_id is not None else None),
    )
    return event.processing_status


def process_voice_dial_result(
    db: Session,
    payload: dict[str, str],
    *,
    intent_id: UUID | None = None,
    call_id: UUID | None = None,
    signature_verified: bool = False,
    signature: str | None = None,
) -> str:
    process_voice_status(
        db,
        payload,
        intent_id=intent_id,
        call_id=call_id,
        signature_verified=signature_verified,
        signature=signature,
        callback_kind="dial_result",
    )
    call = resolve_callback_call(db, payload, intent_id=intent_id, call_id=call_id)
    if call is None or call.direction != "inbound":
        return hangup_twiml()
    status = (payload.get("DialCallStatus") or payload.get("CallStatus") or "").lower()
    if status not in {"busy", "failed", "no-answer", "canceled"}:
        return hangup_twiml()
    line = db.get(VoiceLine, call.voice_line_id) if call.voice_line_id else None
    if line is None or line.missed_call_action == "task_only":
        return hangup_twiml()
    return voicemail_twiml(get_settings(), call_id=str(call.id))


def process_voice_voicemail_complete(
    db: Session,
    payload: dict[str, str],
    *,
    call_id: UUID,
) -> None:
    call = db.get(CallRecord, call_id)
    if call is None:
        return
    now = datetime.now(UTC)
    call.status = "completed"
    call.ended_at = now
    call.duration_seconds = parse_int(payload.get("RecordingDuration")) or call.duration_seconds
    call.call_metadata = {
        **(call.call_metadata or {}),
        "voicemail": True,
        "voicemail_recording_sid": payload.get("RecordingSid"),
    }
    communication = (
        db.get(CommunicationRecord, call.communication_record_id)
        if call.communication_record_id
        else None
    )
    if communication is not None:
        communication.status = "completed"
        communication.body = f"Voicemail from {call.from_number or 'caller'}"
        communication.external_payload = {
            **(communication.external_payload or {}),
            "voicemail": True,
            "recording_sid": payload.get("RecordingSid"),
        }
    if call.prospecting_inbound_callback_id is not None:
        complete_prospecting_callback_voicemail(db, call)
    else:
        ensure_missed_call_task(db, call)
    db.commit()


def process_voice_recording(
    db: Session,
    payload: dict[str, str],
    *,
    intent_id: UUID | None = None,
    call_id: UUID | None = None,
    signature_verified: bool = False,
    signature: str | None = None,
) -> str:
    recording_sid = required_voice_value(payload, "RecordingSid")
    recording_status = required_voice_value(payload, "RecordingStatus").lower()
    call = resolve_callback_call(db, payload, intent_id=intent_id, call_id=call_id)
    if call is None:
        return "unmatched"
    is_prospecting_call = call.prospecting_dial_leg_id is not None
    is_prospecting_callback = call.prospecting_inbound_callback_id is not None
    if recording_status == "completed" and call.recording_consent_status == "disclosure_configured":
        call.recording_consent_status = "disclosed"
    event_id = f"voice:recording:{recording_sid}:{recording_status}"
    if not is_prospecting_call:
        existing_event = get_voice_provider_event(db, call.organization_id, event_id)
        if existing_event is not None:
            return existing_event.processing_status
    recording = db.scalar(
        select(CallRecording).where(
            CallRecording.organization_id == call.organization_id,
            CallRecording.provider == "twilio",
            CallRecording.provider_recording_id == recording_sid,
        )
    )
    if recording is not None and recording.call_record_id != call.id:
        raise ProspectingVoiceConflictError(
            "Provider recording ID is already attached to another call."
        )
    settings = get_settings()
    completed_at = datetime.now(UTC) if recording_status == "completed" else None
    retention_expires_at = (
        completed_at + timedelta(days=settings.call_recording_retention_days)
        if completed_at is not None
        else None
    )
    if recording is None:
        recording = CallRecording(
            organization_id=call.organization_id,
            call_record_id=call.id,
            provider="twilio",
            provider_recording_id=recording_sid,
            status=recording_status,
            media_reference=f"twilio://recordings/{recording_sid}",
            duration_seconds=parse_int(payload.get("RecordingDuration")),
            channel_count=parse_int(payload.get("RecordingChannels")),
            consent_status=call.recording_consent_status,
            recorded_at=completed_at,
            retention_expires_at=retention_expires_at,
            deleted_at=None,
            deleted_by_user_id=None,
            deletion_reason=None,
            recording_metadata={
                "source": payload.get("RecordingSource"),
                "storage": "provider_private",
                "retention_days": settings.call_recording_retention_days,
            },
        )
        db.add(recording)
    else:
        recording.status = recording_status
        recording.duration_seconds = parse_int(payload.get("RecordingDuration"))
        recording.channel_count = parse_int(payload.get("RecordingChannels"))
        recording.consent_status = call.recording_consent_status
        if recording_status == "completed":
            recording.recorded_at = completed_at
            recording.retention_expires_at = recording.retention_expires_at or retention_expires_at
    if recording_status == "completed" and not is_prospecting_call and not is_prospecting_callback:
        db.flush()
        enqueue_call_transcript(
            db,
            recording,
            model_name=settings.openai_transcription_model,
        )
    if is_prospecting_call:
        processing_status = reconcile_signed_prospecting_recording(
            db,
            call,
            payload,
            signature_verified=signature_verified,
            signature=signature,
        )
        db.flush()
        enqueue_eligible_prospecting_call_transcript(
            db,
            recording,
            model_name=settings.openai_transcription_model,
        )
        db.commit()
        return processing_status
    event = record_provider_event(
        db,
        organization_id=call.organization_id,
        conversation_id=call.conversation_id,
        event_type="voice.recording",
        external_event_id=event_id,
        payload=payload,
    )
    event.processing_status = "processed"
    event.processed_at = datetime.now(UTC)
    db.commit()
    return event.processing_status


def process_voice_recording_disclosure(
    db: Session,
    payload: dict[str, str],
    *,
    intent_id: UUID | None = None,
    call_id: UUID | None = None,
    signature_verified: bool = False,
    signature: str | None = None,
) -> str:
    call = resolve_callback_call(db, payload, intent_id=intent_id, call_id=call_id)
    if call is None:
        return "unmatched"
    if call.prospecting_dial_leg_id is not None:
        call.recording_consent_status = "disclosed"
        processing_status = reconcile_signed_prospecting_disclosure(
            db,
            call,
            payload,
            signature_verified=signature_verified,
            signature=signature,
        )
        db.commit()
        return processing_status
    event_id = f"voice:recording-disclosure:{call.id}"
    existing_event = get_voice_provider_event(db, call.organization_id, event_id)
    if existing_event is not None:
        return existing_event.processing_status
    call.recording_consent_status = "disclosed"
    event = record_provider_event(
        db,
        organization_id=call.organization_id,
        conversation_id=call.conversation_id,
        event_type="voice.recording_disclosure",
        external_event_id=event_id,
        payload=payload,
    )
    event.processing_status = "processed"
    event.processed_at = datetime.now(UTC)
    db.commit()
    return event.processing_status


def get_scoped_recording(
    db: Session,
    principal: Principal,
    recording_id: UUID,
) -> CallRecording | None:
    return get_authorized_recording(db, principal, recording_id)


def get_scoped_transcript(
    db: Session,
    principal: Principal,
    transcript_id: UUID,
) -> CallTranscript | None:
    transcript = db.scalar(
        select(CallTranscript).where(
            CallTranscript.id == transcript_id,
            CallTranscript.organization_id == principal.organization_id,
        )
    )
    if transcript is None:
        return None
    if get_scoped_recording(db, principal, transcript.recording_id) is None:
        return None
    return transcript


def delete_recording(
    db: Session,
    principal: Principal,
    recording_id: UUID,
    *,
    reason: str,
    settings: Settings | None = None,
) -> VoiceRecordingRead | None:
    recording = get_scoped_recording(db, principal, recording_id)
    if recording is None:
        return None
    if recording.deleted_at is not None or recording.status == "deleted":
        return recording_to_read(recording)
    pending_transcript = db.scalar(
        select(CallTranscript.id).where(
            CallTranscript.recording_id == recording.id,
            CallTranscript.status.in_(("queued", "processing")),
        )
    )
    if pending_transcript is not None:
        raise VoiceIntentConflictError(
            "Recording cannot be deleted while transcription is still processing."
        )
    delete_recording_from_provider(
        db,
        recording,
        settings=settings or get_settings(),
        reason=reason,
        actor_user_id=principal.user_id,
        actor_type="user",
    )
    db.commit()
    db.refresh(recording)
    return recording_to_read(recording)


def purge_next_expired_recording(
    db: Session,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> UUID | None:
    cutoff = now or datetime.now(UTC)
    legacy_recording = db.scalar(
        select(CallRecording)
        .where(
            CallRecording.status == "completed",
            CallRecording.deleted_at.is_(None),
            CallRecording.recorded_at.is_not(None),
            CallRecording.retention_expires_at.is_(None),
        )
        .order_by(CallRecording.recorded_at.asc(), CallRecording.id.asc())
        .limit(1)
    )
    if legacy_recording is not None and legacy_recording.recorded_at is not None:
        legacy_recording.retention_expires_at = as_utc(legacy_recording.recorded_at) + timedelta(
            days=settings.call_recording_retention_days
        )
        db.commit()
    pending_transcript = exists(
        select(CallTranscript.id).where(
            CallTranscript.recording_id == CallRecording.id,
            CallTranscript.status.in_(("queued", "processing")),
        )
    )
    recording = db.scalar(
        select(CallRecording)
        .where(
            CallRecording.status == "completed",
            CallRecording.deleted_at.is_(None),
            CallRecording.retention_expires_at.is_not(None),
            CallRecording.retention_expires_at <= cutoff,
            ~pending_transcript,
        )
        .order_by(CallRecording.retention_expires_at.asc(), CallRecording.id.asc())
        .limit(1)
    )
    if recording is None:
        return None
    recording_id = recording.id
    delete_recording_from_provider(
        db,
        recording,
        settings=settings,
        reason="Stonegate recording retention period expired.",
        actor_user_id=None,
        actor_type="system",
    )
    db.commit()
    return recording_id


def delete_recording_from_provider(
    db: Session,
    recording: CallRecording,
    *,
    settings: Settings,
    reason: str,
    actor_user_id: UUID | None,
    actor_type: str,
) -> None:
    previous_value = {
        "status": recording.status,
        "retention_expires_at": (
            recording.retention_expires_at.isoformat()
            if recording.retention_expires_at is not None
            else None
        ),
        "provider_recording_id": recording.provider_recording_id,
    }
    if recording.provider == "twilio" and recording.provider_recording_id:
        delete_twilio_recording(settings, recording.provider_recording_id)
    deleted_at = datetime.now(UTC)
    recording.status = "deleted"
    recording.media_reference = None
    recording.deleted_at = deleted_at
    recording.deleted_by_user_id = actor_user_id
    recording.deletion_reason = reason.strip()
    recording.recording_metadata = {
        **(recording.recording_metadata or {}),
        "provider_media_deleted": True,
        "provider_media_deleted_at": deleted_at.isoformat(),
    }
    db.add(
        AuditEvent(
            organization_id=recording.organization_id,
            actor_user_id=actor_user_id,
            actor_type=actor_type,
            action="communication.recording_delete",
            entity_type="call_recording",
            entity_id=recording.id,
            previous_value=previous_value,
            new_value={
                "status": "deleted",
                "deleted_at": deleted_at.isoformat(),
                "audio_retained": False,
            },
            reason=recording.deletion_reason,
        )
    )


def recording_to_read(recording: CallRecording) -> VoiceRecordingRead:
    return VoiceRecordingRead(
        id=recording.id,
        call_record_id=recording.call_record_id,
        status=recording.status,
        duration_seconds=recording.duration_seconds,
        channel_count=recording.channel_count,
        consent_status=recording.consent_status,
        recorded_at=recording.recorded_at,
        retention_expires_at=recording.retention_expires_at,
        deleted_at=recording.deleted_at,
        deletion_reason=recording.deletion_reason,
    )


def resolve_callback_call(
    db: Session,
    payload: dict[str, str],
    *,
    intent_id: UUID | None,
    call_id: UUID | None,
) -> CallRecord | None:
    if call_id is not None:
        call = db.get(CallRecord, call_id)
        if call is not None:
            return call
    if intent_id is not None:
        call = db.scalar(select(CallRecord).where(CallRecord.call_intent_id == intent_id))
        if call is not None:
            return call
    provider_ids = [
        value
        for value in (
            payload.get("ParentCallSid"),
            payload.get("CallSid"),
            payload.get("DialCallSid"),
        )
        if value
    ]
    if not provider_ids:
        return None
    return db.scalar(
        select(CallRecord).where(
            (CallRecord.provider_call_id.in_(provider_ids))
            | (CallRecord.child_provider_call_id.in_(provider_ids))
        )
    )


def apply_call_status(
    db: Session,
    call: CallRecord,
    status: str,
    payload: dict[str, str],
    *,
    answered_user_id: UUID | None = None,
) -> None:
    now = datetime.now(UTC)
    child_sid = payload.get("CallSid")
    if payload.get("ParentCallSid") and child_sid:
        if status in {"in-progress", "answered"} or call.child_provider_call_id is None:
            call.child_provider_call_id = child_sid
        child_statuses = dict((call.call_metadata or {}).get("child_statuses") or {})
        child_statuses[child_sid] = status
        call.call_metadata = {
            **(call.call_metadata or {}),
            "child_call_sid": call.child_provider_call_id,
            "child_statuses": child_statuses,
        }
    if status in {"in-progress", "answered"} and answered_user_id is not None:
        routed_ids = set((call.call_metadata or {}).get("routing_target_user_ids") or [])
        user = db.get(User, answered_user_id)
        if (
            user is not None
            and user.is_active
            and user.organization_id == call.organization_id
            and (not routed_ids or str(user.id) in routed_ids)
        ):
            call.actor_user_id = user.id
    is_child_terminal = bool(payload.get("ParentCallSid")) and status in FINAL_CALL_STATUSES
    target_count = int((call.call_metadata or {}).get("ring_target_count") or 1)
    if is_child_terminal and call.prospecting_inbound_callback_id is not None:
        # A child leg cannot close the aggregate callback. Twilio may still be
        # ringing another target; the final DialResult/root callback is authoritative.
        return
    if is_child_terminal and target_count > 1:
        return
    current_rank = CALL_STATUS_RANK.get(call.status, -1)
    incoming_rank = CALL_STATUS_RANK.get(status, current_rank)
    if current_rank >= 4 and incoming_rank < current_rank:
        return
    call.status = status
    if status in {"in-progress", "answered"} and call.answered_at is None:
        call.answered_at = now
    duration = parse_int(
        payload.get("CallDuration") or payload.get("DialCallDuration") or payload.get("Duration")
    )
    if duration is not None:
        call.duration_seconds = duration
    if status in FINAL_CALL_STATUSES:
        call.ended_at = now
    communication = (
        db.get(CommunicationRecord, call.communication_record_id)
        if call.communication_record_id
        else None
    )
    if communication is not None:
        if call.actor_user_id is not None:
            communication.actor_user_id = call.actor_user_id
        communication.status = status
        communication.external_payload = {
            **(communication.external_payload or {}),
            "call_status": status,
            "duration_seconds": call.duration_seconds,
        }
    if call.direction == "inbound" and status in {"busy", "failed", "no-answer", "canceled"}:
        ensure_missed_call_task(db, call)


def ensure_missed_call_task(db: Session, call: CallRecord) -> None:
    if call.prospecting_inbound_callback_id is not None:
        ensure_prospecting_missed_callback_task(db, call)
        return
    conversation = db.get(Conversation, call.conversation_id)
    if conversation is not None:
        reactivated_lead = reactivate_closed_lead_for_inbound(
            db,
            conversation,
            occurred_at=call.started_at or datetime.now(UTC),
        )
        if reactivated_lead is not None:
            return
    if call.lead_id is not None:
        lead = lock_organization_lead(
            db,
            organization_id=call.organization_id,
            lead_id=call.lead_id,
        )
        if lead is None or lead.archived_at is not None or lead.stage_key in INACTIVE_LEAD_STAGES:
            return
        inbound_reactivation_task = db.scalar(
            select(Task.id).where(
                Task.organization_id == call.organization_id,
                Task.lead_id == call.lead_id,
                Task.task_type == "inbound_reactivation",
                Task.status.in_(("open", "in_progress")),
            )
        )
        if inbound_reactivation_task is not None:
            return
    existing = db.scalar(
        select(Task).where(
            Task.organization_id == call.organization_id,
            Task.lead_id == call.lead_id,
            Task.task_type == "missed_call",
            Task.status.in_(("open", "in_progress")),
            Task.title.contains(call.from_number or ""),
        )
    )
    if existing is not None:
        return
    responsible_user_id = call.actor_user_id
    if responsible_user_id is None:
        raw_owner_id = (call.call_metadata or {}).get("routing_owner_user_id")
        try:
            responsible_user_id = UUID(str(raw_owner_id)) if raw_owner_id else None
        except ValueError:
            responsible_user_id = None
    entity_type, entity_id = (
        conversation_activity_entity(db, conversation)
        if conversation is not None
        else ("conversation", call.conversation_id)
    )
    party_label = "buyer" if entity_type == "buyer" else "seller"
    db.add(
        Task(
            organization_id=call.organization_id,
            lead_id=call.lead_id,
            responsible_user_id=responsible_user_id,
            task_type="missed_call",
            title=f"Return missed call from {call.from_number or party_label}",
            status="open",
            priority="high",
            due_at=datetime.now(UTC) + timedelta(minutes=5),
            completed_at=None,
        )
    )
    db.add(
        ActivityEvent(
            organization_id=call.organization_id,
            actor_user_id=None,
            entity_type=entity_type,
            entity_id=entity_id,
            event_type=f"{entity_type}.missed_call",
            summary="Missed inbound call created an urgent return-call task.",
        )
    )


def create_call_records(
    db: Session,
    *,
    organization_id: UUID,
    conversation_id: UUID,
    lead_id: UUID | None,
    contact_id: UUID,
    actor_user_id: UUID | None,
    voice_line_id: UUID,
    call_intent_id: UUID | None,
    provider_call_id: str,
    direction: str,
    status: str,
    from_number: str,
    to_number: str,
    recording_consent_status: str,
) -> tuple[CommunicationRecord, CallRecord]:
    occurred_at = datetime.now(UTC)
    communication = CommunicationRecord(
        organization_id=organization_id,
        conversation_id=conversation_id,
        lead_id=lead_id,
        contact_id=contact_id,
        actor_user_id=actor_user_id,
        direction=direction,
        channel="call",
        status=status,
        provider="twilio",
        provider_message_id=provider_call_id,
        subject=None,
        body=(
            f"Outbound call to {to_number}"
            if direction == "outbound"
            else f"Inbound call from {from_number}"
        ),
        occurred_at=occurred_at,
        external_payload={"call_sid": provider_call_id},
        communication_metadata={"source": "twilio_voice"},
    )
    db.add(communication)
    db.flush()
    call = CallRecord(
        organization_id=organization_id,
        conversation_id=conversation_id,
        lead_id=lead_id,
        contact_id=contact_id,
        actor_user_id=actor_user_id,
        communication_record_id=communication.id,
        voice_line_id=voice_line_id,
        call_intent_id=call_intent_id,
        provider="twilio",
        provider_call_id=provider_call_id,
        child_provider_call_id=None,
        direction=direction,
        status=status,
        from_number=from_number,
        to_number=to_number,
        started_at=occurred_at,
        answered_at=None,
        ended_at=None,
        duration_seconds=None,
        disposition=None,
        recording_consent_status=recording_consent_status,
        call_metadata={"source": "twilio_voice"},
    )
    db.add(call)
    db.flush()
    conversation = db.get(Conversation, conversation_id)
    if conversation is not None and direction == "outbound":
        update_conversation_activity(
            conversation,
            direction="outbound",
            occurred_at=occurred_at,
            db=db,
        )
    return communication, call


def create_inbound_call_lead(
    db: Session,
    line: VoiceLine,
    caller: str,
) -> Conversation:
    normalized = format_e164(caller) or caller
    contact = Contact(
        organization_id=line.organization_id,
        legal_name=f"Inbound caller {normalized}",
        preferred_name=None,
        contact_type="seller",
        assigned_user_id=line.assigned_user_id,
    )
    db.add(contact)
    db.flush()
    db.add(
        ContactMethod(
            organization_id=line.organization_id,
            contact_id=contact.id,
            method_type="phone",
            value=normalized,
            normalized_value="".join(character for character in normalized if character.isdigit()),
            is_primary=True,
        )
    )
    property_record = Property(
        organization_id=line.organization_id,
        street_address="Address pending",
        city="Unknown",
        state="GA",
        postal_code="00000",
        county=None,
        property_type=None,
        normalized_address_key=None,
    )
    db.add(property_record)
    db.flush()
    lead = Lead(
        organization_id=line.organization_id,
        contact_id=contact.id,
        property_id=property_record.id,
        assigned_user_id=line.assigned_user_id,
        source="inbound_call",
        stage_key="new",
        lead_temperature=None,
        motivation=None,
        desired_timeline=None,
        property_condition=None,
        occupancy_status=None,
        asking_price=None,
        mortgage_balance=None,
        appointment_status=None,
        next_follow_up_at=None,
        archived_at=None,
    )
    db.add(lead)
    db.flush()
    from app.services.ai_operations import enqueue_lead_created_ai_work

    enqueue_lead_created_ai_work(db, lead, source="inbound_call")
    from app.services.property_intelligence import enqueue_property_research

    enqueue_property_research(
        db,
        property_record,
        source_lead_id=lead.id,
        trigger_source="inbound_call",
    )
    conversation = ensure_primary_conversation(db, lead)
    db.add(
        ActivityEvent(
            organization_id=line.organization_id,
            actor_user_id=None,
            entity_type="lead",
            entity_id=lead.id,
            event_type="lead.created_from_inbound_call",
            summary="New lead created from an unknown inbound caller.",
        )
    )
    return conversation


def create_inbound_call_buyer(
    db: Session,
    line: VoiceLine,
    caller: str,
) -> Conversation:
    normalized = format_e164(caller) or caller
    buyer = Buyer(
        organization_id=line.organization_id,
        name=f"Inbound buyer {normalized}",
        company_name=None,
        email=None,
        phone=normalized,
        buyer_type="cash_buyer",
        status="active",
        proof_of_funds_status="unknown",
        max_purchase_price_cents=None,
        reliability_score_basis_points=5000,
        completed_deals=0,
        failed_deals=0,
        proof_of_funds_expires_at=None,
        notes="Created automatically from an inbound dispositions call.",
    )
    db.add(buyer)
    db.flush()
    conversation = ensure_buyer_conversation(
        db,
        buyer,
        actor_user_id=line.assigned_user_id,
    )
    db.add(
        ConsentRecord(
            organization_id=line.organization_id,
            contact_id=conversation.contact_id,
            channel="phone",
            status="granted",
            source="inbound_call",
            wording_version="caller-initiated-v1",
            wording="Buyer initiated a call to the Stonegate dispositions line.",
            captured_ip=None,
            user_agent=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    db.add(
        ActivityEvent(
            organization_id=line.organization_id,
            actor_user_id=None,
            entity_type="buyer",
            entity_id=buyer.id,
            event_type="buyer.created_from_inbound_call",
            summary="New buyer created from an unknown dispositions caller.",
        )
    )
    return conversation


def create_inbound_call_general(
    db: Session,
    line: VoiceLine,
    caller: str,
) -> Conversation:
    normalized = format_e164(caller) or caller
    contact = Contact(
        organization_id=line.organization_id,
        legal_name=f"Business caller {normalized}",
        preferred_name=None,
        contact_type="business_contact",
        assigned_user_id=line.assigned_user_id,
    )
    db.add(contact)
    db.flush()
    db.add(
        ContactMethod(
            organization_id=line.organization_id,
            contact_id=contact.id,
            method_type="phone",
            value=normalized,
            normalized_value="".join(character for character in normalized if character.isdigit()),
            is_primary=True,
        )
    )
    conversation = create_general_conversation(
        db,
        organization_id=line.organization_id,
        contact_id=contact.id,
        assigned_user_id=line.assigned_user_id,
    )
    conversation.conversation_metadata = {
        **(conversation.conversation_metadata or {}),
        "source": "inbound_company_call",
        "unified_timeline": True,
    }
    db.add(
        ConsentRecord(
            organization_id=line.organization_id,
            contact_id=contact.id,
            channel="phone",
            status="granted",
            source="inbound_call",
            wording_version="caller-initiated-v1",
            wording="Caller initiated a call to the Stonegate company line.",
            normalized_address=normalized,
            captured_ip=None,
            user_agent=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    db.add(
        ActivityEvent(
            organization_id=line.organization_id,
            actor_user_id=None,
            entity_type="conversation",
            entity_id=conversation.id,
            event_type="conversation.created_from_inbound_call",
            summary="New company conversation created from an unknown inbound caller.",
        )
    )
    return conversation


def find_conversation_by_phone(
    db: Session,
    organization_id: UUID,
    phone_number: str,
    *,
    conversation_type: str,
) -> Conversation | None:
    values = phone_lookup_values(phone_number)
    if not values:
        return None
    return db.scalar(
        select(Conversation)
        .join(ContactMethod, ContactMethod.contact_id == Conversation.contact_id)
        .where(
            Conversation.organization_id == organization_id,
            Conversation.conversation_type == conversation_type,
            ContactMethod.organization_id == organization_id,
            ContactMethod.method_type == "phone",
            ContactMethod.normalized_value.in_(values),
        )
        .order_by(
            Conversation.status == "closed",
            Conversation.last_activity_at.desc(),
            Conversation.created_at.desc(),
        )
    )


def clean_optional_text(value: str | None) -> str | None:
    normalized = " ".join((value or "").split()).strip()
    return normalized or None


def clean_quick_dial_name(payload: VoiceQuickDialCreate) -> str | None:
    return clean_optional_text(payload.company_name) or clean_optional_text(payload.contact_name)


def quick_dial_request_fingerprint(
    payload: VoiceQuickDialCreate,
    destination: str,
) -> str:
    canonical = {
        "phone_number": destination,
        "contact_name": clean_optional_text(payload.contact_name),
        "company_name": clean_optional_text(payload.company_name),
        "purpose": payload.purpose,
        "call_reason": clean_optional_text(payload.call_reason),
        "voice_line_id": str(payload.voice_line_id) if payload.voice_line_id else None,
    }
    serialized = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def existing_quick_dial_to_read(
    db: Session,
    principal: Principal,
    payload: VoiceQuickDialCreate,
    *,
    destination: str,
    request_fingerprint: str,
    intent: VoiceCallIntent,
) -> VoiceQuickDialRead:
    metadata = intent.intent_metadata or {}
    if (
        intent.organization_id != principal.organization_id
        or intent.actor_user_id != principal.user_id
        or intent.recipient != destination
        or metadata.get("source") != "quick_dial"
        or metadata.get("request_fingerprint") != request_fingerprint
        or (payload.voice_line_id is not None and intent.voice_line_id != payload.voice_line_id)
    ):
        raise VoiceIntentConflictError("The idempotency key was already used for another call.")
    conversation_id, contact_id = require_warm_call_intent_context(intent)
    conversation = db.get(Conversation, conversation_id)
    contact = db.get(Contact, contact_id)
    line = db.get(VoiceLine, intent.voice_line_id)
    if (
        conversation is None
        or conversation.organization_id != principal.organization_id
        or contact is None
        or contact.organization_id != principal.organization_id
        or line is None
        or line.organization_id != principal.organization_id
        or line.status != "active"
    ):
        raise VoiceConfigurationError("The saved Quick Dial call is no longer available.")
    return VoiceQuickDialRead(
        conversation_id=conversation.id,
        contact_id=contact.id,
        conversation_type=conversation.conversation_type,
        contact_name=contact.legal_name,
        reused_contact=True,
        reused_conversation=True,
        intent=call_intent_to_read(intent, line, get_settings()),
    )


def validate_call_intent_replay(
    intent: VoiceCallIntent,
    principal: Principal,
    *,
    conversation: Conversation,
    payload: VoiceCallIntentCreate,
    intent_source: str,
) -> None:
    metadata = intent.intent_metadata or {}
    if (
        intent.organization_id != principal.organization_id
        or intent.actor_user_id != principal.user_id
        or intent.conversation_id != conversation.id
        or metadata.get("source") != intent_source
    ):
        raise VoiceIntentConflictError("The idempotency key was already used for another call.")
    if payload.voice_line_id is not None and intent.voice_line_id != payload.voice_line_id:
        raise VoiceIntentConflictError(
            "The idempotency key was already used with another Stonegate line."
        )


def validate_quick_dial_destination(
    db: Session,
    principal: Principal,
    destination: str,
) -> None:
    company_numbers = db.scalars(
        select(VoiceLine.phone_number).where(
            VoiceLine.organization_id == principal.organization_id,
        )
    ).all()
    if destination in {format_e164(number) for number in company_numbers}:
        raise VoiceComplianceError("Quick Dial cannot call a Stonegate company line.")
    forwarding_numbers = db.scalars(
        select(User.voice_forwarding_number).where(
            User.organization_id == principal.organization_id,
            User.is_active.is_(True),
            User.voice_forwarding_number.is_not(None),
        )
    ).all()
    if destination in {format_e164(number) for number in forwarding_numbers}:
        raise VoiceComplianceError("Quick Dial cannot call a Stonegate staff forwarding number.")


def find_quick_dial_context(
    db: Session,
    organization_id: UUID,
    destination: str,
) -> tuple[Contact | None, Conversation | None]:
    lookup_values = phone_lookup_values(destination)
    conversation = db.scalar(
        select(Conversation)
        .join(ContactMethod, ContactMethod.contact_id == Conversation.contact_id)
        .where(
            Conversation.organization_id == organization_id,
            Conversation.conversation_type.in_(("general", "buyer", "lead")),
            ContactMethod.organization_id == organization_id,
            ContactMethod.method_type == "phone",
            ContactMethod.normalized_value.in_(lookup_values),
        )
        .order_by(
            (Conversation.status == "closed").asc(),
            (Conversation.conversation_type == "general").desc(),
            Conversation.last_activity_at.desc(),
            Conversation.created_at.desc(),
        )
    )
    if conversation is not None:
        return db.get(Contact, conversation.contact_id), conversation
    contact = db.scalar(
        select(Contact)
        .join(ContactMethod, ContactMethod.contact_id == Contact.id)
        .where(
            Contact.organization_id == organization_id,
            ContactMethod.organization_id == organization_id,
            ContactMethod.method_type == "phone",
            ContactMethod.normalized_value.in_(lookup_values),
        )
        .order_by(
            (Contact.contact_type == "business_contact").desc(),
            Contact.created_at.desc(),
        )
    )
    return contact, None


def resolve_inbound_users(
    db: Session,
    line: VoiceLine,
    conversation_id: UUID,
) -> list[UUID]:
    conversation = db.get(Conversation, conversation_id)
    candidate_ids: list[UUID | None] = (
        [line.assigned_user_id, conversation.assigned_user_id if conversation else None]
        if line.inbound_route == "assigned_user"
        else [conversation.assigned_user_id if conversation else None, line.assigned_user_id]
    )
    if line.assigned_team_id is not None:
        candidate_ids.extend(
            db.scalars(
                select(TeamMembership.user_id)
                .join(User, User.id == TeamMembership.user_id)
                .where(
                    TeamMembership.organization_id == line.organization_id,
                    TeamMembership.team_id == line.assigned_team_id,
                    User.is_active.is_(True),
                )
                .order_by(
                    (TeamMembership.membership_role == "manager").desc(),
                    TeamMembership.created_at.asc(),
                )
            ).all()
        )
    candidate_ids.append(line.fallback_user_id)
    result: list[UUID] = []
    for candidate_id in candidate_ids:
        if candidate_id is None or candidate_id in result:
            continue
        user = db.get(User, candidate_id)
        if user is not None and user.is_active and user.organization_id == line.organization_id:
            result.append(user.id)
    if result:
        return result[:10]
    owner_id = db.scalar(
        select(User.id)
        .join(RoleAssignment, RoleAssignment.user_id == User.id)
        .join(Role, Role.id == RoleAssignment.role_id)
        .where(
            User.organization_id == line.organization_id,
            User.is_active.is_(True),
            Role.key.in_(("owner", "founder_operator", "ceo")),
        )
        .order_by(User.created_at.asc())
    )
    return [owner_id] if owner_id is not None else []


def resolve_inbound_targets(
    db: Session,
    user_ids: list[UUID],
    *,
    include_browser: bool,
) -> list[InboundVoiceTarget]:
    targets: list[InboundVoiceTarget] = []
    for user_id in user_ids:
        if len(targets) >= 10:
            break
        user = db.get(User, user_id)
        if user is None or not user.is_active:
            continue
        forwarding_number = (
            format_e164(user.voice_forwarding_number or "")
            if user.voice_forwarding_enabled
            else None
        )
        if forwarding_number is None and not include_browser:
            continue
        targets.append(
            InboundVoiceTarget(
                identity=voice_identity(str(user.id)),
                user_id=str(user.id),
                forwarding_number=forwarding_number,
            )
        )
    return targets


def update_call_routing_metadata(
    call: CallRecord,
    line: VoiceLine,
    targets: list[InboundVoiceTarget],
    *,
    browser_enabled: bool,
) -> None:
    browser_count, mobile_count = inbound_target_endpoint_counts(
        targets,
        browser_enabled=browser_enabled,
    )
    endpoint_count = browser_count + mobile_count
    call.call_metadata = {
        **(call.call_metadata or {}),
        "routing_target_user_ids": [target.user_id for target in targets],
        "routing_mobile_user_ids": [
            target.user_id for target in targets if target.forwarding_number is not None
        ],
        "routing_browser_user_ids": [target.user_id for target in targets[:browser_count]],
        "routing_owner_user_id": targets[0].user_id if targets else None,
        "ring_strategy": line.ring_strategy,
        "ring_user_count": len(targets),
        "ring_target_count": endpoint_count,
        "ring_browser_target_count": browser_count,
        "ring_mobile_target_count": mobile_count,
    }


def voice_line_announcement(line: VoiceLine) -> str:
    if line.purpose_key == "buyer_relations":
        return "Stonegate dispositions call."
    if line.purpose_key == "seller_conversations":
        return "Stonegate acquisitions call."
    if line.purpose_key == "prospecting_outbound":
        return "Stonegate prospecting call."
    return "Stonegate company call."


def validate_screening_target(
    db: Session,
    call_id: UUID,
    user_id: UUID,
) -> tuple[CallRecord, VoiceLine, User]:
    call = db.get(CallRecord, call_id)
    if call is None or call.direction != "inbound" or call.voice_line_id is None:
        raise VoiceConfigurationError("Inbound call screening target was not found.")
    routed_ids = set((call.call_metadata or {}).get("routing_target_user_ids") or [])
    user = db.get(User, user_id)
    if (
        user is None
        or not user.is_active
        or user.organization_id != call.organization_id
        or str(user.id) not in routed_ids
    ):
        raise VoiceConfigurationError("Inbound call screening target is unavailable.")
    line = db.get(VoiceLine, call.voice_line_id)
    if line is None or line.status != "active":
        raise VoiceConfigurationError("Stonegate voice line is unavailable.")
    return call, line, user


def find_voice_line_by_number(db: Session, phone_number: str) -> VoiceLine | None:
    formatted = format_e164(phone_number)
    if formatted is None:
        return None
    return db.scalar(
        select(VoiceLine).where(
            VoiceLine.phone_number == formatted,
            VoiceLine.status == "active",
        )
    )


def select_voice_line(
    db: Session,
    organization_id: UUID,
    user_id: UUID,
) -> VoiceLine | None:
    team_ids = select(TeamMembership.team_id).where(
        TeamMembership.organization_id == organization_id,
        TeamMembership.user_id == user_id,
    )
    assigned = db.scalar(
        select(VoiceLine)
        .where(
            VoiceLine.organization_id == organization_id,
            (
                (VoiceLine.assigned_user_id == user_id)
                | (VoiceLine.fallback_user_id == user_id)
                | (VoiceLine.assigned_team_id.in_(team_ids))
            ),
            VoiceLine.status == "active",
            VoiceLine.purpose_key != "prospecting_outbound",
        )
        .order_by(VoiceLine.is_default.desc(), VoiceLine.created_at.asc())
    )
    if assigned is not None:
        return assigned
    return db.scalar(
        select(VoiceLine)
        .where(
            VoiceLine.organization_id == organization_id,
            VoiceLine.status == "active",
            VoiceLine.purpose_key != "prospecting_outbound",
        )
        .order_by(VoiceLine.is_default.desc(), VoiceLine.created_at.asc())
    )


def select_voice_line_for_conversation(
    db: Session,
    organization_id: UUID,
    user_id: UUID,
    *,
    conversation: Conversation,
    requested_line_id: UUID | None = None,
) -> VoiceLine | None:
    if conversation.conversation_type == "buyer":
        permitted_pairs = {("dispositions", "buyer_relations")}
    elif conversation.conversation_type == "lead":
        permitted_pairs = {("acquisitions", "seller_conversations")}
    elif conversation.conversation_type == "general":
        # Prefer a dedicated company line, but allow any authorized non-prospecting company
        # number so Quick Dial does not require buying another Twilio number.
        permitted_pairs = {
            ("general", "company_general"),
            ("acquisitions", "seller_conversations"),
            ("dispositions", "buyer_relations"),
        }
    else:
        return None
    team_ids = select(TeamMembership.team_id).where(
        TeamMembership.organization_id == organization_id,
        TeamMembership.user_id == user_id,
    )
    permitted = tuple(
        (VoiceLine.department_key == department_key) & (VoiceLine.purpose_key == purpose_key)
        for department_key, purpose_key in permitted_pairs
    )
    query = select(VoiceLine).where(
        VoiceLine.organization_id == organization_id,
        VoiceLine.status == "active",
        VoiceLine.purpose_key != "prospecting_outbound",
        *([VoiceLine.id == requested_line_id] if requested_line_id is not None else []),
        or_(*permitted),
        (
            (VoiceLine.assigned_user_id == user_id)
            | (VoiceLine.fallback_user_id == user_id)
            | (VoiceLine.assigned_team_id.in_(team_ids))
        ),
    )
    if conversation.conversation_type == "general":
        query = query.order_by(
            (VoiceLine.purpose_key == "company_general").desc(),
            VoiceLine.is_default.desc(),
            VoiceLine.created_at.asc(),
        )
    else:
        query = query.order_by(VoiceLine.is_default.desc(), VoiceLine.created_at.asc())
    return db.scalar(query)


def conversation_activity_entity(
    db: Session,
    conversation: Conversation,
) -> tuple[str, UUID]:
    if conversation.lead_id is not None:
        return "lead", conversation.lead_id
    buyer_id = db.scalar(
        select(ConversationContextLink.buyer_id).where(
            ConversationContextLink.organization_id == conversation.organization_id,
            ConversationContextLink.conversation_id == conversation.id,
            ConversationContextLink.context_type == "buyer",
        )
    )
    return ("buyer", buyer_id) if buyer_id is not None else ("conversation", conversation.id)


def find_call(
    db: Session,
    organization_id: UUID,
    *,
    provider_call_id: str,
) -> CallRecord | None:
    return db.scalar(
        select(CallRecord).where(
            CallRecord.organization_id == organization_id,
            CallRecord.provider == "twilio",
            (
                (CallRecord.provider_call_id == provider_call_id)
                | (CallRecord.child_provider_call_id == provider_call_id)
            ),
        )
    )


def record_provider_event(
    db: Session,
    *,
    organization_id: UUID,
    conversation_id: UUID | None,
    event_type: str,
    external_event_id: str,
    payload: dict[str, str],
) -> CommunicationProviderEvent:
    event = CommunicationProviderEvent(
        organization_id=organization_id,
        conversation_id=conversation_id,
        provider="twilio",
        event_type=event_type,
        external_event_id=external_event_id,
        processing_status="received",
        payload=payload,
        received_at=datetime.now(UTC),
        processed_at=None,
        error_message=None,
    )
    db.add(event)
    return event


def get_voice_provider_event(
    db: Session,
    organization_id: UUID,
    external_event_id: str,
) -> CommunicationProviderEvent | None:
    return db.scalar(
        select(CommunicationProviderEvent).where(
            CommunicationProviderEvent.organization_id == organization_id,
            CommunicationProviderEvent.provider == "twilio",
            CommunicationProviderEvent.external_event_id == external_event_id,
        )
    )


def validate_line_assignment(
    db: Session,
    organization_id: UUID,
    user_id: UUID | None,
) -> None:
    if user_id is None:
        return
    user = db.scalar(
        select(User).where(
            User.id == user_id,
            User.organization_id == organization_id,
            User.is_active.is_(True),
        )
    )
    if user is None:
        raise ValueError("Voice line assignee must be an active Stonegate user.")


def validate_line_team(
    db: Session,
    organization_id: UUID,
    team_id: UUID | None,
) -> None:
    if team_id is None:
        return
    team = db.scalar(
        select(Team).where(
            Team.id == team_id,
            Team.organization_id == organization_id,
            Team.is_active.is_(True),
        )
    )
    if team is None:
        raise ValueError("Voice line team must be an active Stonegate team.")


def validate_line_ownership(
    db: Session,
    organization_id: UUID,
    *,
    assigned_user_id: UUID | None,
    fallback_user_id: UUID | None,
    assigned_team_id: UUID | None,
    department_key: str,
    purpose_key: str,
    coverage_timezone: str,
    coverage_start_hour: int,
    coverage_end_hour: int,
    missed_call_action: str,
    ring_strategy: str,
) -> None:
    validate_line_assignment(db, organization_id, assigned_user_id)
    validate_line_assignment(db, organization_id, fallback_user_id)
    validate_line_team(db, organization_id, assigned_team_id)
    if assigned_user_id is not None and assigned_user_id == fallback_user_id:
        raise ValueError("Primary and fallback owners must be different people.")
    expected_purposes = VOICE_LINE_DEPARTMENT_PURPOSES.get(department_key)
    if expected_purposes is None:
        raise ValueError("Unsupported phone-line department.")
    if purpose_key not in expected_purposes:
        raise ValueError("Phone-line purpose must match its department.")
    if missed_call_action not in VOICE_LINE_MISSED_CALL_ACTIONS:
        raise ValueError("Unsupported missed-call action.")
    if ring_strategy not in VOICE_LINE_RING_STRATEGIES:
        raise ValueError("Unsupported voice-line ring strategy.")
    if coverage_start_hour == coverage_end_hour:
        raise ValueError("Coverage start and end hours must be different.")
    try:
        ZoneInfo(coverage_timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Select a valid phone-line coverage timezone.") from exc


def clear_default_lines(db: Session, organization_id: UUID) -> None:
    for line in db.scalars(select(VoiceLine).where(VoiceLine.organization_id == organization_id)):
        line.is_default = False


def voice_line_to_read(db: Session, line: VoiceLine) -> VoiceLineRead:
    assigned_user = db.get(User, line.assigned_user_id) if line.assigned_user_id else None
    fallback_user = db.get(User, line.fallback_user_id) if line.fallback_user_id else None
    assigned_team = db.get(Team, line.assigned_team_id) if line.assigned_team_id else None
    return VoiceLineRead(
        id=line.id,
        phone_number=line.phone_number,
        label=line.label,
        status=line.status,
        is_default=line.is_default,
        inbound_route=line.inbound_route,
        department_key=line.department_key,
        purpose_key=line.purpose_key,
        assigned_user_id=line.assigned_user_id,
        assigned_user_name=assigned_user.display_name if assigned_user else None,
        fallback_user_id=line.fallback_user_id,
        fallback_user_name=fallback_user.display_name if fallback_user else None,
        assigned_team_id=line.assigned_team_id,
        assigned_team_name=assigned_team.name if assigned_team else None,
        ring_strategy=line.ring_strategy,
        coverage_timezone=line.coverage_timezone,
        coverage_start_hour=line.coverage_start_hour,
        coverage_end_hour=line.coverage_end_hour,
        missed_call_action=line.missed_call_action,
        ownership_complete=bool(
            assigned_user
            and assigned_user.is_active
            and assigned_user.voice_forwarding_enabled
            and format_e164(assigned_user.voice_forwarding_number or "")
            and fallback_user
            and fallback_user.is_active
            and fallback_user.voice_forwarding_enabled
            and format_e164(fallback_user.voice_forwarding_number or "")
        ),
    )


def call_intent_to_read(
    intent: VoiceCallIntent,
    line: VoiceLine,
    settings: Settings,
) -> VoiceCallIntentRead:
    conversation_id, _ = require_warm_call_intent_context(intent)
    return VoiceCallIntentRead(
        id=intent.id,
        conversation_id=conversation_id,
        recipient=intent.recipient,
        from_number=line.phone_number,
        status=intent.status,
        expires_at=intent.expires_at,
        recording_enabled=settings.twilio_voice_recording_configured,
    )


def require_warm_call_intent_context(intent: VoiceCallIntent) -> tuple[UUID, UUID]:
    if intent.conversation_id is None or intent.contact_id is None:
        raise VoiceConfigurationError("Warm CRM call context is unavailable.")
    return intent.conversation_id, intent.contact_id


def record_line_audit(
    db: Session,
    principal: Principal,
    line: VoiceLine,
    action: str,
) -> None:
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action=action,
            entity_type="voice_line",
            entity_id=line.id,
            previous_value=None,
            new_value={
                "phone_number": line.phone_number,
                "assigned_user_id": (str(line.assigned_user_id) if line.assigned_user_id else None),
                "fallback_user_id": (str(line.fallback_user_id) if line.fallback_user_id else None),
                "assigned_team_id": (str(line.assigned_team_id) if line.assigned_team_id else None),
                "department_key": line.department_key,
                "purpose_key": line.purpose_key,
                "coverage_timezone": line.coverage_timezone,
                "coverage_start_hour": line.coverage_start_hour,
                "coverage_end_hour": line.coverage_end_hour,
                "missed_call_action": line.missed_call_action,
                "ring_strategy": line.ring_strategy,
                "status": line.status,
                "is_default": line.is_default,
            },
            reason="Voice line configuration updated",
        )
    )


def required_voice_value(payload: dict[str, str], key: str) -> str:
    value = payload.get(key, "").strip()
    if not value:
        raise ValueError(f"Twilio Voice webhook is missing {key}.")
    return value


def parse_int(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
