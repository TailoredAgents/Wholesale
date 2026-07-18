from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import Settings, get_settings
from app.domain.rbac import PermissionKeys
from app.integrations.twilio_voice import (
    create_voice_access_token,
    inbound_call_twiml,
    outbound_call_twiml,
    voice_identity,
)
from app.models.foundation import (
    ActivityEvent,
    AuditEvent,
    CallRecord,
    CallRecording,
    CommunicationProviderEvent,
    CommunicationRecord,
    Contact,
    ContactMethod,
    Conversation,
    Lead,
    Property,
    Role,
    RoleAssignment,
    Task,
    User,
    VoiceCallIntent,
    VoiceLine,
)
from app.schemas.voice import (
    VoiceCallIntentCreate,
    VoiceCallIntentRead,
    VoiceLineAssignmentUpdate,
    VoiceLineCreate,
    VoiceLineRead,
    VoiceSessionRead,
)
from app.services.communication_compliance import (
    evaluate_voice_eligibility,
    format_e164,
    phone_lookup_values,
)
from app.services.inbox import (
    ensure_primary_conversation,
    get_scoped_conversation,
    update_conversation_activity,
)

VOICE_LINE_ROUTES = {"conversation_owner", "assigned_user"}
VOICE_LINE_STATUSES = {"active", "inactive"}
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


def create_voice_line(
    db: Session,
    principal: Principal,
    payload: VoiceLineCreate,
) -> VoiceLineRead:
    phone_number = format_e164(payload.phone_number)
    if phone_number is None:
        raise ValueError("Voice line must be a valid E.164 phone number.")
    validate_line_assignment(db, principal.organization_id, payload.assigned_user_id)
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
        provider="twilio",
        provider_phone_number_id=payload.provider_phone_number_id,
        phone_number=phone_number,
        label=payload.label.strip(),
        status="active",
        is_default=payload.is_default,
        inbound_route=payload.inbound_route,
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
    if "assigned_user_id" in payload.model_fields_set:
        validate_line_assignment(db, principal.organization_id, payload.assigned_user_id)
        line.assigned_user_id = payload.assigned_user_id
    if payload.label is not None:
        line.label = payload.label.strip()
    if payload.status is not None:
        if payload.status not in VOICE_LINE_STATUSES:
            raise ValueError("Unsupported voice line status.")
        line.status = payload.status
    if payload.inbound_route is not None:
        if payload.inbound_route not in VOICE_LINE_ROUTES:
            raise ValueError("Unsupported inbound voice route.")
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
    if not settings.twilio_voice_configured:
        blockers.append("Twilio Voice is not configured.")
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

    contact = db.get(Contact, conversation.contact_id)
    lead = db.get(Lead, conversation.lead_id)
    if contact is None or lead is None:
        return None
    eligibility = evaluate_voice_eligibility(db, contact)
    if not eligibility.can_call or eligibility.recipient is None:
        raise VoiceComplianceError(" ".join(eligibility.blockers))
    line = select_voice_line(db, principal.organization_id, principal.user_id)
    if line is None:
        raise VoiceConfigurationError("No active Stonegate voice line is available.")
    now = datetime.now(UTC)
    settings = get_settings()
    intent = VoiceCallIntent(
        organization_id=principal.organization_id,
        conversation_id=conversation.id,
        lead_id=lead.id,
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
        intent_metadata={"source": "shared_inbox"},
    )
    db.add(intent)
    db.commit()
    return call_intent_to_read(intent, line, settings)


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
        db.add(
            ActivityEvent(
                organization_id=intent.organization_id,
                actor_user_id=intent.actor_user_id,
                entity_type="lead",
                entity_id=intent.lead_id,
                event_type="lead.call_started",
                summary="Outbound seller call initiated from the shared inbox.",
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
        target_user_id = resolve_inbound_user(db, line, existing.conversation_id)
        if target_user_id is None:
            raise VoiceConfigurationError("No Stonegate user is available for this call.")
        return inbound_call_twiml(
            settings,
            identity=voice_identity(str(target_user_id)),
            call_id=str(existing.id),
            recording_enabled=settings.twilio_voice_recording_configured,
        )
    conversation = find_conversation_by_phone(db, line.organization_id, caller)
    if conversation is None:
        conversation = create_inbound_call_lead(db, line, caller)
    target_user_id = resolve_inbound_user(db, line, conversation.id)
    communication, call = create_call_records(
        db,
        organization_id=line.organization_id,
        conversation_id=conversation.id,
        lead_id=conversation.lead_id,
        contact_id=conversation.contact_id,
        actor_user_id=target_user_id,
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
    update_conversation_activity(
        conversation,
        direction="inbound",
        occurred_at=call.started_at or datetime.now(UTC),
    )
    db.add(
        ActivityEvent(
            organization_id=line.organization_id,
            actor_user_id=None,
            entity_type="lead",
            entity_id=conversation.lead_id,
            event_type="lead.call_received",
            summary="Inbound seller call received.",
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
    if target_user_id is None:
        raise VoiceConfigurationError("No Stonegate user is available for this call.")
    return inbound_call_twiml(
        settings,
        identity=voice_identity(str(target_user_id)),
        call_id=str(call.id),
        recording_enabled=settings.twilio_voice_recording_configured,
    )


def process_voice_status(
    db: Session,
    payload: dict[str, str],
    *,
    intent_id: UUID | None = None,
    call_id: UUID | None = None,
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
    apply_call_status(db, call, status, payload)
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
            recorded_at=datetime.now(UTC) if recording_status == "completed" else None,
            deleted_at=None,
            recording_metadata={
                "source": payload.get("RecordingSource"),
                "storage": "provider_private",
            },
        )
        db.add(recording)
    else:
        recording.status = recording_status
        recording.duration_seconds = parse_int(payload.get("RecordingDuration"))
        recording.channel_count = parse_int(payload.get("RecordingChannels"))
        if recording_status == "completed":
            recording.recorded_at = datetime.now(UTC)
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
) -> None:
    now = datetime.now(UTC)
    child_sid = payload.get("CallSid")
    if payload.get("ParentCallSid") and child_sid:
        call.child_provider_call_id = child_sid
        call.call_metadata = {
            **(call.call_metadata or {}),
            "child_call_sid": child_sid,
        }
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
    db.add(
        Task(
            organization_id=call.organization_id,
            lead_id=call.lead_id,
            responsible_user_id=call.actor_user_id,
            task_type="missed_call",
            title=f"Return missed call from {call.from_number or 'seller'}",
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
            entity_type="lead",
            entity_id=call.lead_id,
            event_type="lead.missed_call",
            summary="Missed inbound call created an urgent return-call task.",
        )
    )


def create_call_records(
    db: Session,
    *,
    organization_id: UUID,
    conversation_id: UUID,
    lead_id: UUID,
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


def find_conversation_by_phone(
    db: Session,
    organization_id: UUID,
    phone_number: str,
) -> Conversation | None:
    values = phone_lookup_values(phone_number)
    if not values:
        return None
    return db.scalar(
        select(Conversation)
        .join(ContactMethod, ContactMethod.contact_id == Conversation.contact_id)
        .where(
            Conversation.organization_id == organization_id,
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


def resolve_inbound_user(
    db: Session,
    line: VoiceLine,
    conversation_id: UUID,
) -> UUID | None:
    conversation = db.get(Conversation, conversation_id)
    candidate_ids = (
        [line.assigned_user_id, conversation.assigned_user_id if conversation else None]
        if line.inbound_route == "assigned_user"
        else [conversation.assigned_user_id if conversation else None, line.assigned_user_id]
    )
    for candidate_id in candidate_ids:
        if candidate_id is None:
            continue
        user = db.get(User, candidate_id)
        if user is not None and user.is_active and user.organization_id == line.organization_id:
            return user.id
    return db.scalar(
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
    assigned = db.scalar(
        select(VoiceLine)
        .where(
            VoiceLine.organization_id == organization_id,
            VoiceLine.assigned_user_id == user_id,
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


def clear_default_lines(db: Session, organization_id: UUID) -> None:
    for line in db.scalars(
        select(VoiceLine).where(VoiceLine.organization_id == organization_id)
    ):
        line.is_default = False


def voice_line_to_read(db: Session, line: VoiceLine) -> VoiceLineRead:
    assigned_user = db.get(User, line.assigned_user_id) if line.assigned_user_id else None
    return VoiceLineRead(
        id=line.id,
        phone_number=line.phone_number,
        label=line.label,
        status=line.status,
        is_default=line.is_default,
        inbound_route=line.inbound_route,
        assigned_user_id=line.assigned_user_id,
        assigned_user_name=assigned_user.display_name if assigned_user else None,
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
