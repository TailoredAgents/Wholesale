import json
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import Settings, get_settings
from app.domain.rbac import PermissionKeys
from app.integrations.openai_client import OpenAIClientError, OpenAIResponsesClient
from app.integrations.twilio_recordings import (
    TwilioRecordingError,
    download_twilio_recording,
)
from app.models.foundation import (
    ActivityEvent,
    AiAgentDefinition,
    AiPromptVersion,
    AiRunLog,
    ApprovalRequest,
    AuditEvent,
    CallRecord,
    CallRecording,
    CallTranscript,
    CommunicationRecord,
    Contact,
    Lead,
    Property,
    Task,
)
from app.schemas.voice import (
    CallTranscriptRead,
    CallTranscriptReview,
    StructuredCallNotes,
)

CALL_INTELLIGENCE_AGENT_KEY = "call_intelligence"
CALL_INTELLIGENCE_PROMPT = """You prepare factual real-estate acquisition call notes.
Use only facts explicitly present in the diarized transcript. Never infer a price, timeline,
condition, occupancy, debt, title issue, commitment, or appointment. Use null or an empty list
when the call does not support a field. Keep seller language precise and operational.
Evidence entries must point to the supplied segment index and start time. This is a draft for
human review and must not claim that Stonegate made a binding offer or contractual commitment."""
LEAD_UPDATE_FIELDS = {
    "motivation": "motivation",
    "timeline": "desired_timeline",
    "property_condition": "property_condition",
    "occupancy_status": "occupancy_status",
    "asking_price": "asking_price",
}


class CallIntelligenceError(RuntimeError):
    pass


def enqueue_call_transcript(
    db: Session,
    recording: CallRecording,
    *,
    model_name: str,
) -> CallTranscript:
    existing = db.scalar(
        select(CallTranscript)
        .where(
            CallTranscript.organization_id == recording.organization_id,
            CallTranscript.recording_id == recording.id,
        )
        .order_by(CallTranscript.created_at.desc())
    )
    if existing is not None:
        return existing
    transcript = CallTranscript(
        organization_id=recording.organization_id,
        recording_id=recording.id,
        provider="openai",
        model_name=model_name,
        status="queued",
        language=None,
        transcript_text=None,
        speaker_segments=None,
        confidence_score=None,
        approved_by_user_id=None,
        approved_at=None,
        error_message=None,
        transcript_metadata={"attempts": 0, "human_review_required": True},
    )
    db.add(transcript)
    db.flush()
    return transcript


def process_next_call_transcript(
    db: Session,
    settings: Settings | None = None,
) -> UUID | None:
    settings = settings or get_settings()
    candidates = db.scalars(
        select(CallTranscript)
        .where(
            or_(
                CallTranscript.status.in_(("queued", "failed")),
                (
                    (CallTranscript.status == "processing")
                    & (CallTranscript.updated_at < datetime.now(UTC) - timedelta(minutes=15))
                ),
            )
        )
        .order_by(CallTranscript.created_at.asc())
        .with_for_update(skip_locked=True)
        .limit(20)
    ).all()
    transcript = next(
        (
            item
            for item in candidates
            if int((item.transcript_metadata or {}).get("attempts", 0))
            < settings.call_transcription_max_attempts
        ),
        None,
    )
    if transcript is None:
        recording = db.scalar(
            select(CallRecording)
            .outerjoin(CallTranscript, CallTranscript.recording_id == CallRecording.id)
            .where(
                CallRecording.status == "completed",
                CallRecording.deleted_at.is_(None),
                CallRecording.provider_recording_id.is_not(None),
                CallTranscript.id.is_(None),
            )
            .order_by(CallRecording.created_at.asc())
            .limit(1)
        )
        if recording is None:
            return None
        transcript = enqueue_call_transcript(
            db,
            recording,
            model_name=settings.openai_transcription_model,
        )
    transcript.status = "processing"
    transcript.error_message = None
    db.commit()
    transcript_id = transcript.id
    process_call_transcript(db, transcript_id, settings)
    return transcript_id


def process_call_transcript(
    db: Session,
    transcript_id: UUID,
    settings: Settings | None = None,
) -> CallTranscript:
    settings = settings or get_settings()
    transcript = db.get(CallTranscript, transcript_id)
    if transcript is None:
        raise CallIntelligenceError("Call transcript job was not found.")
    metadata = dict(transcript.transcript_metadata or {})
    attempts = int(metadata.get("attempts", 0)) + 1
    metadata["attempts"] = attempts
    metadata["processing_started_at"] = datetime.now(UTC).isoformat()
    transcript.transcript_metadata = metadata
    transcript.status = "processing"
    db.commit()

    started_at = datetime.now(UTC)
    started_monotonic = time.perf_counter()
    run: AiRunLog | None = None
    run_id: UUID | None = None
    try:
        if not settings.call_transcription_enabled:
            raise CallIntelligenceError("Call transcription is disabled.")
        if not settings.ai_enabled or not settings.openai_api_key:
            raise CallIntelligenceError("OpenAI call transcription is not configured.")
        recording = db.get(CallRecording, transcript.recording_id)
        if recording is None or not recording.provider_recording_id:
            raise CallIntelligenceError("The call recording is unavailable.")
        call = db.get(CallRecord, recording.call_record_id)
        if call is None:
            raise CallIntelligenceError("The call record is unavailable.")
        lead = db.get(Lead, call.lead_id)
        if lead is None:
            raise CallIntelligenceError("The call lead is unavailable.")

        agent, prompt = ensure_call_intelligence_agent(
            db,
            organization_id=transcript.organization_id,
            model_name=settings.openai_default_model,
        )
        run = AiRunLog(
            organization_id=transcript.organization_id,
            agent_definition_id=agent.id,
            prompt_version_id=prompt.id,
            lead_id=lead.id,
            status="running",
            model_name=agent.model_name,
            input_summary=f"Recorded call {call.id} queued for transcription and note review.",
            output_summary=None,
            total_tokens=None,
            cost_cents=None,
            latency_ms=None,
            started_at=started_at,
            completed_at=None,
            error_message=None,
        )
        db.add(run)
        db.flush()
        run_id = run.id
        db.commit()

        media = download_twilio_recording(settings, recording.provider_recording_id)
        if len(media.content) > settings.call_transcription_max_audio_bytes:
            raise CallIntelligenceError("Call recording exceeds OpenAI's 25 MB upload limit.")
        client = OpenAIResponsesClient(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout_seconds=settings.openai_request_timeout_seconds,
        )
        audio_result = client.create_audio_transcription(
            model=settings.openai_transcription_model,
            audio=media.content,
            media_type=media.media_type,
        )
        if not audio_result.text:
            raise CallIntelligenceError("OpenAI returned an empty call transcript.")
        transcript.transcript_text = audio_result.text
        transcript.speaker_segments = normalize_segments(audio_result.segments)
        transcript.language = audio_result.language

        notes_payload, note_tokens = client.create_structured_response(
            model=settings.openai_default_model,
            system_prompt=prompt.prompt_text,
            user_prompt=build_call_notes_prompt(db, call, transcript),
            schema_name="stonegate_call_notes",
            json_schema=StructuredCallNotes.model_json_schema(),
            reasoning_effort=settings.openai_reasoning_effort,
        )
        notes = StructuredCallNotes.model_validate(notes_payload)
        confidence = notes.confidence
        transcript.confidence_score = confidence
        transcript.status = "needs_review"
        transcript.error_message = None
        transcript.transcript_metadata = {
            **metadata,
            "processing_completed_at": datetime.now(UTC).isoformat(),
            "structured_notes": notes.model_dump(mode="json"),
            "transcription_model": settings.openai_transcription_model,
            "notes_model": settings.openai_default_model,
            "human_review_required": True,
        }
        approval = ensure_call_notes_approval(db, transcript, call, lead, notes)
        transcript.transcript_metadata["approval_request_id"] = str(approval.id)
        run.status = "needs_review"
        run.output_summary = notes.summary[:4000]
        run.total_tokens = sum(
            value for value in (audio_result.total_tokens, note_tokens) if value is not None
        ) or None
        run.latency_ms = round((time.perf_counter() - started_monotonic) * 1000)
        run.completed_at = datetime.now(UTC)
        transcript.transcript_metadata["ai_run_id"] = str(run.id)
        db.commit()
        db.refresh(transcript)
        return transcript
    except (
        CallIntelligenceError,
        OpenAIClientError,
        TwilioRecordingError,
        ValidationError,
    ) as exc:
        db.rollback()
        transcript = db.get(CallTranscript, transcript_id)
        if transcript is None:
            raise
        transcript.status = "failed"
        transcript.error_message = str(exc)[:2000]
        transcript.transcript_metadata = {
            **(transcript.transcript_metadata or {}),
            "attempts": attempts,
            "last_failed_at": datetime.now(UTC).isoformat(),
        }
        if run_id is not None:
            persisted_run = db.get(AiRunLog, run_id)
            if persisted_run is not None:
                persisted_run.status = "failed"
                persisted_run.error_message = str(exc)[:2000]
                persisted_run.latency_ms = round(
                    (time.perf_counter() - started_monotonic) * 1000
                )
                persisted_run.completed_at = datetime.now(UTC)
        db.commit()
        db.refresh(transcript)
        return transcript


def review_call_transcript(
    db: Session,
    principal: Principal,
    transcript_id: UUID,
    payload: CallTranscriptReview,
) -> CallTranscriptRead | None:
    if (
        PermissionKeys.ACCESS_RECORDINGS not in principal.permission_keys
        or PermissionKeys.EDIT_LEADS not in principal.permission_keys
    ):
        raise PermissionError("Call-note review requires recording and lead-edit access.")
    transcript = db.scalar(
        select(CallTranscript).where(
            CallTranscript.id == transcript_id,
            CallTranscript.organization_id == principal.organization_id,
        )
    )
    if transcript is None:
        return None
    if transcript.status not in {"needs_review", "approved", "rejected"}:
        raise ValueError("Call notes are not ready for review.")
    if transcript.status in {"approved", "rejected"}:
        return transcript_to_read(db, transcript)

    recording = db.get(CallRecording, transcript.recording_id)
    call = db.get(CallRecord, recording.call_record_id) if recording else None
    if call is None:
        raise ValueError("Call record is unavailable.")
    lead = db.get(Lead, call.lead_id)
    if lead is None:
        raise ValueError("Lead is unavailable.")
    approval = get_call_notes_approval(db, transcript)
    previous = {
        "status": transcript.status,
        "structured_notes": (transcript.transcript_metadata or {}).get("structured_notes"),
    }
    notes = payload.structured_notes
    transcript.transcript_metadata = {
        **(transcript.transcript_metadata or {}),
        "structured_notes": notes.model_dump(mode="json"),
        "reviewed_at": datetime.now(UTC).isoformat(),
        "review_decision_notes": payload.decision_notes,
    }
    transcript.status = payload.status
    if payload.status == "approved":
        transcript.approved_by_user_id = principal.user_id
        transcript.approved_at = datetime.now(UTC)
        apply_approved_call_notes(
            db,
            principal,
            transcript,
            call,
            lead,
            notes,
            apply_field_updates=payload.apply_field_updates,
            create_follow_up_task=payload.create_follow_up_task,
        )
    if approval is not None:
        approval.status = payload.status
        approval.decision_notes = payload.decision_notes
        approval.decided_at = datetime.now(UTC)
    mark_ai_run_reviewed(db, transcript, payload.status)
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="call_transcript",
            entity_id=transcript.id,
            event_type=f"call_notes.{payload.status}",
            summary=f"AI call notes {payload.status} after human review.",
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="call_notes.review",
            entity_type="call_transcript",
            entity_id=transcript.id,
            previous_value=previous,
            new_value={
                "status": transcript.status,
                "structured_notes": notes.model_dump(mode="json"),
                "applied_fields": payload.apply_field_updates,
            },
            reason=payload.decision_notes or "Human call-note review",
        )
    )
    db.commit()
    db.refresh(transcript)
    return transcript_to_read(db, transcript)


def transcript_to_read(db: Session, transcript: CallTranscript) -> CallTranscriptRead:
    metadata = transcript.transcript_metadata or {}
    raw_notes = metadata.get("structured_notes")
    try:
        notes = StructuredCallNotes.model_validate(raw_notes) if raw_notes else None
    except ValidationError:
        notes = None
    approval = get_call_notes_approval(db, transcript)
    return CallTranscriptRead(
        id=transcript.id,
        status=transcript.status,
        model_name=transcript.model_name,
        language=transcript.language,
        transcript_text=transcript.transcript_text,
        speaker_segments=transcript.speaker_segments or [],
        confidence_score=transcript.confidence_score,
        structured_notes=notes,
        approval_request_id=approval.id if approval else None,
        approved_by_user_id=transcript.approved_by_user_id,
        approved_at=transcript.approved_at,
        error_message=transcript.error_message,
    )


def ensure_call_intelligence_agent(
    db: Session,
    *,
    organization_id: UUID,
    model_name: str,
) -> tuple[AiAgentDefinition, AiPromptVersion]:
    agent = db.scalar(
        select(AiAgentDefinition).where(
            AiAgentDefinition.organization_id == organization_id,
            AiAgentDefinition.key == CALL_INTELLIGENCE_AGENT_KEY,
        )
    )
    if agent is None:
        agent = AiAgentDefinition(
            organization_id=organization_id,
            key=CALL_INTELLIGENCE_AGENT_KEY,
            name="Call Intelligence",
            description="Transcribes seller calls and drafts evidence-backed acquisition notes.",
            status="active",
            model_name=model_name,
            risk_level="medium",
            requires_human_approval=True,
        )
        db.add(agent)
        db.flush()
    elif agent.model_name != model_name:
        agent.model_name = model_name
    prompt = db.scalar(
        select(AiPromptVersion).where(
            AiPromptVersion.agent_definition_id == agent.id,
            AiPromptVersion.status == "active",
        )
    )
    if prompt is None:
        prompt = AiPromptVersion(
            organization_id=organization_id,
            agent_definition_id=agent.id,
            version_number=1,
            status="active",
            prompt_text=CALL_INTELLIGENCE_PROMPT,
            change_notes="Initial evidence-backed call intelligence prompt.",
            created_by_user_id=None,
        )
        db.add(prompt)
        db.flush()
    return agent, prompt


def ensure_call_notes_approval(
    db: Session,
    transcript: CallTranscript,
    call: CallRecord,
    lead: Lead,
    notes: StructuredCallNotes,
) -> ApprovalRequest:
    existing = get_call_notes_approval(db, transcript)
    if existing is not None:
        return existing
    approval = ApprovalRequest(
        organization_id=transcript.organization_id,
        requested_by_user_id=None,
        assigned_to_user_id=call.actor_user_id or lead.assigned_user_id,
        request_type="call_notes_review",
        entity_type="call_transcript",
        entity_id=transcript.id,
        status="pending",
        title="Review AI call notes",
        summary=notes.summary[:2000],
        decision_notes=None,
        due_at=None,
        decided_at=None,
        approval_metadata={
            "lead_id": str(lead.id),
            "recording_id": str(transcript.recording_id),
            "source": "call_intelligence",
        },
    )
    db.add(approval)
    db.flush()
    return approval


def get_call_notes_approval(
    db: Session,
    transcript: CallTranscript,
) -> ApprovalRequest | None:
    return db.scalar(
        select(ApprovalRequest)
        .where(
            ApprovalRequest.organization_id == transcript.organization_id,
            ApprovalRequest.request_type == "call_notes_review",
            ApprovalRequest.entity_type == "call_transcript",
            ApprovalRequest.entity_id == transcript.id,
        )
        .order_by(ApprovalRequest.created_at.desc())
    )


def build_call_notes_prompt(db: Session, call: CallRecord, transcript: CallTranscript) -> str:
    contact = db.get(Contact, call.contact_id)
    lead = db.get(Lead, call.lead_id)
    property_record = db.get(Property, lead.property_id) if lead else None
    segments = transcript.speaker_segments or []
    return json.dumps(
        {
            "seller": contact.preferred_name or contact.legal_name if contact else "Unknown",
            "property": (
                {
                    "address": property_record.street_address,
                    "city": property_record.city,
                    "state": property_record.state,
                }
                if property_record
                else None
            ),
            "call_direction": call.direction,
            "segments": segments,
            "full_transcript": transcript.transcript_text,
        },
        indent=2,
    )


def normalize_segments(segments: list[dict[str, object]]) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for index, segment in enumerate(segments):
        text = segment.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        normalized.append(
            {
                "index": index,
                "speaker": str(segment.get("speaker") or "Speaker"),
                "start": numeric_value(segment.get("start")),
                "end": numeric_value(segment.get("end")),
                "text": text.strip(),
            }
        )
    return normalized


def numeric_value(value: object) -> float:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def apply_approved_call_notes(
    db: Session,
    principal: Principal,
    transcript: CallTranscript,
    call: CallRecord,
    lead: Lead,
    notes: StructuredCallNotes,
    *,
    apply_field_updates: list[str],
    create_follow_up_task: bool,
) -> None:
    metadata = transcript.transcript_metadata or {}
    if metadata.get("applied_at"):
        return
    applied_fields: list[str] = []
    note_values = notes.model_dump()
    for note_field in apply_field_updates:
        lead_field = LEAD_UPDATE_FIELDS.get(note_field)
        if lead_field is None:
            continue
        value = note_values.get(note_field)
        if value and getattr(lead, lead_field) is None:
            setattr(lead, lead_field, value)
            applied_fields.append(lead_field)

    db.add(
        CommunicationRecord(
            organization_id=principal.organization_id,
            conversation_id=call.conversation_id,
            lead_id=call.lead_id,
            contact_id=call.contact_id,
            actor_user_id=principal.user_id,
            direction="internal",
            channel="note",
            status="logged",
            provider="openai_reviewed",
            provider_message_id=f"call-notes:{transcript.id}",
            subject="Approved call summary",
            body=format_approved_notes(notes)[:4000],
            occurred_at=datetime.now(UTC),
            external_payload=None,
            communication_metadata={
                "call_transcript_id": str(transcript.id),
                "human_approved": True,
            },
        )
    )
    if create_follow_up_task and notes.next_action:
        db.add(
            Task(
                organization_id=principal.organization_id,
                lead_id=lead.id,
                responsible_user_id=lead.assigned_user_id or call.actor_user_id,
                task_type="call_follow_up",
                title=notes.next_action[:255],
                status="open",
                priority="normal",
                due_at=parse_follow_up_at(notes.follow_up_at),
                completed_at=None,
            )
        )
    transcript.transcript_metadata = {
        **metadata,
        "applied_at": datetime.now(UTC).isoformat(),
        "applied_fields": applied_fields,
        "approved_note_logged": True,
        "follow_up_task_created": bool(create_follow_up_task and notes.next_action),
    }


def format_approved_notes(notes: StructuredCallNotes) -> str:
    lines = [notes.summary]
    details = (
        ("Motivation", notes.motivation),
        ("Timeline", notes.timeline),
        ("Condition", notes.property_condition),
        ("Occupancy", notes.occupancy_status),
        ("Asking price", notes.asking_price),
        ("Mortgage/title", notes.mortgage_or_title),
        ("Next action", notes.next_action),
        ("Appointment", notes.appointment_details),
    )
    lines.extend(f"{label}: {value}" for label, value in details if value)
    for label, values in (
        ("Repairs", notes.repairs),
        ("Objections", notes.objections),
        ("Commitments", notes.commitments),
    ):
        if values:
            lines.append(f"{label}: {'; '.join(values)}")
    return "\n".join(lines)


def parse_follow_up_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def mark_ai_run_reviewed(db: Session, transcript: CallTranscript, status: str) -> None:
    run_id = (transcript.transcript_metadata or {}).get("ai_run_id")
    if not isinstance(run_id, str):
        return
    try:
        run = db.get(AiRunLog, UUID(run_id))
    except ValueError:
        return
    if run is not None:
        run.status = status
