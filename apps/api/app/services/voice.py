from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import exists, select
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
    VoiceForwardingUpdate,
    VoiceLineAssignmentUpdate,
    VoiceLineCreate,
    VoiceLineRead,
    VoiceLineTeamRead,
    VoiceLineUserRead,
    VoiceProviderReadinessRead,
    VoiceReadinessCheckRead,
    VoiceRecordingRead,
    VoiceSessionRead,
)
from app.services.call_intelligence import enqueue_call_transcript
from app.services.communication_compliance import (
    evaluate_voice_eligibility,
    format_e164,
    phone_lookup_values,
)
from app.services.inbox import (
    ensure_buyer_conversation,
    ensure_primary_conversation,
    get_scoped_conversation,
    update_conversation_activity,
)

VOICE_LINE_ROUTES = {"conversation_owner", "assigned_user"}
VOICE_LINE_STATUSES = {"active", "inactive"}
VOICE_LINE_RING_STRATEGIES = {"sequential", "simultaneous"}
VOICE_LINE_DEPARTMENT_PURPOSES = {
    "acquisitions": "seller_conversations",
    "dispositions": "buyer_relations",
    "general": "company_general",
}
VOICE_LINE_MISSED_CALL_ACTIONS = {
    "fallback_then_voicemail",
    "voicemail",
    "task_only",
}
FINAL_CALL_STATUSES = {"completed", "busy", "failed", "no-answer", "canceled"}
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
        format_e164(payload.voice_forwarding_number)
        if payload.voice_forwarding_number
        else None
    )
    if payload.voice_forwarding_number and formatted is None:
        raise ValueError("Cellphone must be a valid E.164 phone number.")
    if payload.voice_forwarding_enabled and formatted is None:
        raise ValueError("Enter a cellphone number before enabling forwarding.")
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
    }
    user.voice_forwarding_number = formatted
    user.voice_forwarding_enabled = payload.voice_forwarding_enabled
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
            },
            reason="Updated staff inbound call destination",
        )
    )
    db.commit()
    return VoiceLineUserRead(
        id=user.id,
        display_name=user.display_name,
        email=user.email,
        voice_forwarding_number=user.voice_forwarding_number,
        voice_forwarding_enabled=user.voice_forwarding_enabled,
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
        VoiceLineTeamRead(id=team.id, name=team.name, team_type=team.team_type)
        for team in teams
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
                    "Recording disclosure and retention are configured."
                    if settings.twilio_voice_recording_configured
                    else "Recording is enabled but its disclosure or retention is incomplete."
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
        coverage_start_hour=payload.coverage_start_hour,
        coverage_end_hour=payload.coverage_end_hour,
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
        coverage_start_hour=payload.coverage_start_hour,
        coverage_end_hour=payload.coverage_end_hour,
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
    missed_call_action = payload.missed_call_action or line.missed_call_action
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


def create_call_intent(
    db: Session,
    principal: Principal,
    conversation_id: UUID,
    payload: VoiceCallIntentCreate,
) -> VoiceCallIntentRead | None:
    conversation = get_scoped_conversation(db, principal, conversation_id)
    if conversation is None:
        return None
    if (
        PermissionKeys.PLACE_CALLS not in principal.permission_keys
        and (
            PermissionKeys.PLACE_ASSIGNED_CALLS not in principal.permission_keys
            or conversation.assigned_user_id != principal.user_id
        )
    ):
        raise PermissionError("Calls can only be placed from an assigned conversation.")
    existing = db.scalar(
        select(VoiceCallIntent).where(
            VoiceCallIntent.organization_id == principal.organization_id,
            VoiceCallIntent.idempotency_key == payload.idempotency_key,
        )
    )
    if existing is not None:
        if existing.conversation_id != conversation.id:
            raise VoiceIntentConflictError(
                "The idempotency key was already used for another call."
            )
        line = db.get(VoiceLine, existing.voice_line_id)
        if line is None:
            raise VoiceConfigurationError("The selected Stonegate voice line no longer exists.")
        return call_intent_to_read(existing, line, get_settings())

    if conversation.conversation_type not in {"lead", "buyer"}:
        raise VoiceConfigurationError(
            "Calling is only available from seller and buyer conversations."
        )
    contact = db.get(Contact, conversation.contact_id)
    lead = db.get(Lead, conversation.lead_id) if conversation.lead_id is not None else None
    if conversation.conversation_type == "lead" and lead is None:
        return None
    if contact is None:
        return None
    eligibility = evaluate_voice_eligibility(db, contact)
    if not eligibility.can_call or eligibility.recipient is None:
        raise VoiceComplianceError(" ".join(eligibility.blockers))
    line = select_voice_line_for_conversation(
        db,
        principal.organization_id,
        principal.user_id,
        conversation=conversation,
    )
    if line is None:
        department = "dispositions" if conversation.conversation_type == "buyer" else "acquisitions"
        raise VoiceConfigurationError(
            f"No authorized active Stonegate {department} line is available."
        )
    now = datetime.now(UTC)
    settings = get_settings()
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
        recording_consent_status=(
            "disclosure_configured"
            if settings.twilio_voice_recording_configured
            else "not_requested"
        ),
        expires_at=now + timedelta(minutes=5),
        consumed_at=None,
        provider_call_id=None,
        intent_metadata={
            "source": "shared_inbox",
            "conversation_type": conversation.conversation_type,
            "department_key": line.department_key,
        },
    )
    db.add(intent)
    db.commit()
    return call_intent_to_read(intent, line, settings)


def start_forwarded_call(
    db: Session,
    principal: Principal,
    conversation_id: UUID,
    payload: VoiceCallIntentCreate,
    *,
    provider: TwilioVoiceCallProvider | None = None,
) -> VoiceCallIntentRead | None:
    intent_read = create_call_intent(db, principal, conversation_id, payload)
    if intent_read is None:
        return None
    intent = db.get(VoiceCallIntent, intent_read.id)
    if intent is None:
        return None
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
        conversation_id=intent.conversation_id,
        lead_id=intent.lead_id,
        contact_id=intent.contact_id,
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
    conversation = db.get(Conversation, intent.conversation_id)
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
            summary="Outbound call started through the Stonegate cellphone bridge.",
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
) -> VoiceCallIntentRead | None:
    lead = db.scalar(
        select(Lead).where(
            Lead.id == lead_id,
            Lead.organization_id == principal.organization_id,
            Lead.archived_at.is_(None),
        )
    )
    if lead is None:
        return None
    conversation = ensure_primary_conversation(db, lead)
    return start_forwarded_call(
        db,
        principal,
        conversation.id,
        payload,
        provider=provider,
    )


def process_forwarded_voice_connect(
    db: Session,
    payload: dict[str, str],
    *,
    intent_id: UUID,
) -> str:
    intent = db.get(VoiceCallIntent, intent_id)
    if intent is None or intent.status != "started":
        raise VoiceConfigurationError("Stonegate forwarded call is unavailable.")
    if payload.get("Digits") != "1":
        return hangup_twiml()
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
    if line is None:
        raise VoiceConfigurationError("Stonegate voice line is unavailable.")
    if existing_call is None:
        communication, call = create_call_records(
            db,
            organization_id=intent.organization_id,
            conversation_id=intent.conversation_id,
            lead_id=intent.lead_id,
            contact_id=intent.contact_id,
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
        conversation = db.get(Conversation, intent.conversation_id)
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


def process_inbound_voice_request(db: Session, payload: dict[str, str]) -> str:
    settings = get_settings()
    caller = required_voice_value(payload, "From")
    recipient = required_voice_value(payload, "To")
    call_sid = required_voice_value(payload, "CallSid")
    line = find_voice_line_by_number(db, recipient)
    if line is None or not settings.twilio_voice_configured:
        raise VoiceConfigurationError("Inbound Stonegate Voice is not configured for this number.")
    existing = find_call(db, line.organization_id, provider_call_id=call_sid)
    if existing is not None:
        if not is_within_line_coverage(line):
            if line.missed_call_action in {"voicemail", "fallback_then_voicemail"}:
                return voicemail_twiml(settings, call_id=str(existing.id))
            return hangup_twiml(
                "Stonegate is currently closed. We will return your call shortly."
            )
        target_user_ids = resolve_inbound_users(db, line, existing.conversation_id)
        targets = resolve_inbound_targets(db, target_user_ids)
        if not targets:
            if line.missed_call_action in {"voicemail", "fallback_then_voicemail"}:
                return voicemail_twiml(settings, call_id=str(existing.id))
            ensure_missed_call_task(db, existing)
            db.commit()
            return hangup_twiml("Stonegate is unavailable. We will return your call shortly.")
        update_call_routing_metadata(existing, line, targets)
        db.commit()
        return inbound_call_twiml(
            settings,
            targets=targets,
            call_id=str(existing.id),
            recording_enabled=settings.twilio_voice_recording_configured,
            ring_strategy=line.ring_strategy,
        )
    conversation_type = "buyer" if line.purpose_key == "buyer_relations" else "lead"
    conversation = find_conversation_by_phone(
        db,
        line.organization_id,
        caller,
        conversation_type=conversation_type,
    )
    if conversation is None:
        conversation = (
            create_inbound_call_buyer(db, line, caller)
            if conversation_type == "buyer"
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
        recording_consent_status=(
            "disclosure_configured"
            if settings.twilio_voice_recording_configured
            else "not_requested"
        ),
    )
    communication.body = f"Inbound call from {format_e164(caller) or caller}"
    targets = resolve_inbound_targets(db, target_user_ids)
    update_call_routing_metadata(call, line, targets)
    update_conversation_activity(
        conversation,
        direction="inbound",
        occurred_at=call.started_at or datetime.now(UTC),
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
    if not is_within_line_coverage(line):
        if line.missed_call_action in {"voicemail", "fallback_then_voicemail"}:
            return voicemail_twiml(settings, call_id=str(call.id))
        ensure_missed_call_task(db, call)
        db.commit()
        return hangup_twiml("Stonegate is currently closed. We will return your call shortly.")
    if not targets:
        if line.missed_call_action in {"voicemail", "fallback_then_voicemail"}:
            return voicemail_twiml(settings, call_id=str(call.id))
        ensure_missed_call_task(db, call)
        db.commit()
        return hangup_twiml("Stonegate is unavailable. We will return your call shortly.")
    return inbound_call_twiml(
        settings,
        targets=targets,
        call_id=str(call.id),
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
        db.commit()
    return call_screen_result_twiml(accepted=accepted)


def process_voice_status(
    db: Session,
    payload: dict[str, str],
    *,
    intent_id: UUID | None = None,
    call_id: UUID | None = None,
    answered_user_id: UUID | None = None,
) -> str:
    status = (
        payload.get("DialCallStatus")
        or payload.get("CallStatus")
        or required_voice_value(payload, "CallStatus")
    ).lower()
    call = resolve_callback_call(db, payload, intent_id=intent_id, call_id=call_id)
    if call is None:
        return "unmatched"
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
    return event.processing_status


def process_voice_dial_result(
    db: Session,
    payload: dict[str, str],
    *,
    intent_id: UUID | None = None,
    call_id: UUID | None = None,
) -> str:
    process_voice_status(db, payload, intent_id=intent_id, call_id=call_id)
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
    ensure_missed_call_task(db, call)
    db.commit()


def process_voice_recording(
    db: Session,
    payload: dict[str, str],
    *,
    intent_id: UUID | None = None,
    call_id: UUID | None = None,
) -> str:
    recording_sid = required_voice_value(payload, "RecordingSid")
    recording_status = required_voice_value(payload, "RecordingStatus").lower()
    call = resolve_callback_call(db, payload, intent_id=intent_id, call_id=call_id)
    if call is None:
        return "unmatched"
    if recording_status == "completed" and call.recording_consent_status == "disclosure_configured":
        call.recording_consent_status = "disclosed"
    event_id = f"voice:recording:{recording_sid}:{recording_status}"
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
        if recording_status == "completed":
            recording.recorded_at = completed_at
            recording.retention_expires_at = (
                recording.retention_expires_at or retention_expires_at
            )
    if recording_status == "completed":
        db.flush()
        enqueue_call_transcript(
            db,
            recording,
            model_name=settings.openai_transcription_model,
        )
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
) -> str:
    call = resolve_callback_call(db, payload, intent_id=intent_id, call_id=call_id)
    if call is None:
        return "unmatched"
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
    filters = [
        CallRecording.id == recording_id,
        CallRecording.organization_id == principal.organization_id,
    ]
    if PermissionKeys.VIEW_CONVERSATIONS not in principal.permission_keys:
        filters.append(Conversation.assigned_user_id == principal.user_id)
    recording = db.scalar(
        select(CallRecording)
        .join(CallRecord, CallRecord.id == CallRecording.call_record_id)
        .join(Conversation, Conversation.id == CallRecord.conversation_id)
        .where(*filters)
    )
    return recording


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
        payload.get("CallDuration")
        or payload.get("DialCallDuration")
        or payload.get("Duration")
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
    conversation = db.get(Conversation, call.conversation_id)
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
        if forwarding_number is None:
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
) -> None:
    endpoint_count = sum(int(target.forwarding_number is not None) for target in targets)
    call.call_metadata = {
        **(call.call_metadata or {}),
        "routing_target_user_ids": [target.user_id for target in targets],
        "routing_mobile_user_ids": [
            target.user_id for target in targets if target.forwarding_number is not None
        ],
        "routing_owner_user_id": targets[0].user_id if targets else None,
        "ring_strategy": line.ring_strategy,
        "ring_user_count": len(targets),
        "ring_target_count": endpoint_count,
    }


def voice_line_announcement(line: VoiceLine) -> str:
    if line.purpose_key == "buyer_relations":
        return "Stonegate dispositions call."
    if line.purpose_key == "seller_conversations":
        return "Stonegate acquisitions call."
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


def is_within_line_coverage(
    line: VoiceLine,
    *,
    now: datetime | None = None,
) -> bool:
    local_now = now or datetime.now(ZoneInfo(line.coverage_timezone))
    if local_now.tzinfo is None:
        local_now = local_now.replace(tzinfo=ZoneInfo(line.coverage_timezone))
    else:
        local_now = local_now.astimezone(ZoneInfo(line.coverage_timezone))
    hour = local_now.hour
    if line.coverage_start_hour < line.coverage_end_hour:
        return line.coverage_start_hour <= hour < line.coverage_end_hour
    return hour >= line.coverage_start_hour or hour < line.coverage_end_hour


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
        )
        .order_by(VoiceLine.is_default.desc(), VoiceLine.created_at.asc())
    )


def select_voice_line_for_conversation(
    db: Session,
    organization_id: UUID,
    user_id: UUID,
    *,
    conversation: Conversation,
) -> VoiceLine | None:
    department_key = (
        "dispositions" if conversation.conversation_type == "buyer" else "acquisitions"
    )
    purpose_key = (
        "buyer_relations"
        if conversation.conversation_type == "buyer"
        else "seller_conversations"
    )
    team_ids = select(TeamMembership.team_id).where(
        TeamMembership.organization_id == organization_id,
        TeamMembership.user_id == user_id,
    )
    return db.scalar(
        select(VoiceLine)
        .where(
            VoiceLine.organization_id == organization_id,
            VoiceLine.department_key == department_key,
            VoiceLine.purpose_key == purpose_key,
            VoiceLine.status == "active",
            (
                (VoiceLine.assigned_user_id == user_id)
                | (VoiceLine.fallback_user_id == user_id)
                | (VoiceLine.assigned_team_id.in_(team_ids))
            ),
        )
        .order_by(VoiceLine.is_default.desc(), VoiceLine.created_at.asc())
    )


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
    expected_purpose = VOICE_LINE_DEPARTMENT_PURPOSES.get(department_key)
    if expected_purpose is None:
        raise ValueError("Unsupported phone-line department.")
    if purpose_key != expected_purpose:
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
    for line in db.scalars(
        select(VoiceLine).where(VoiceLine.organization_id == organization_id)
    ):
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
    return VoiceCallIntentRead(
        id=intent.id,
        conversation_id=intent.conversation_id,
        recipient=intent.recipient,
        from_number=line.phone_number,
        status=intent.status,
        expires_at=intent.expires_at,
        recording_enabled=settings.twilio_voice_recording_configured,
    )


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
                "assigned_user_id": (
                    str(line.assigned_user_id) if line.assigned_user_id else None
                ),
                "fallback_user_id": (
                    str(line.fallback_user_id) if line.fallback_user_id else None
                ),
                "assigned_team_id": (
                    str(line.assigned_team_id) if line.assigned_team_id else None
                ),
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
