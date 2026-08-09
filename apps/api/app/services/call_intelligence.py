import json
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import Settings, get_settings
from app.domain.assets import HOUSE_ASSET_CLASS, LAND_ASSET_CLASS, normalize_asset_class
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
    CallNotes,
    CallTranscriptRead,
    CallTranscriptReview,
    LandStructuredCallNotes,
    StructuredCallNotes,
)
from app.services.ai_costs import cents_from_microusd, estimate_openai_cost
from app.services.ai_operations import (
    enqueue_call_intelligence_ai_work,
    mark_call_intelligence_ai_work,
    mark_call_intelligence_reviewed,
)

CALL_INTELLIGENCE_AGENT_KEY = "call_intelligence"
CALL_INTELLIGENCE_PROMPT = """You prepare factual real-estate acquisition call notes.
Use only facts explicitly present in the diarized transcript. Never infer a price, timeline,
condition, occupancy, debt, title issue, commitment, or appointment. Put a stated mortgage,
loan balance, or payoff amount in mortgage_balance; use mortgage_or_title for other lien, probate,
ownership, or title context. Use null or an empty list when the call does not support a field.
Keep seller language precise and operational.
Evidence entries must point to the supplied segment index and start time. This is a draft for
human review and must not claim that Stonegate made a binding offer or contractual commitment."""
LAND_CALL_INTELLIGENCE_PROMPT = """This call concerns vacant land. Capture only explicit
seller statements for parcel/APN, acreage, legal description, access or road frontage,
utilities, zoning or intended use, septic or perc testing, taxes or HOA, and terrain or
environmental concerns. Attribute these as unverified seller statements. Never conclude or
promise buildability, legal access, zoning compliance, utility availability, surveyed acreage
or boundaries, title quality, septic suitability, or environmental clearance. Do not turn a
seller's intended use into a verified permitted use. Every populated land-specific field must
have a matching evidence entry using that field's exact schema name."""
LEAD_UPDATE_FIELDS = {
    "motivation": "motivation",
    "timeline": "desired_timeline",
    "property_condition": "property_condition",
    "occupancy_status": "occupancy_status",
    "asking_price": "asking_price",
    "mortgage_balance": "mortgage_balance",
}
QUALITY_NOTE_FIELDS = (
    "summary",
    "motivation",
    "timeline",
    "property_condition",
    "occupancy_status",
    "asking_price",
    "mortgage_balance",
    "mortgage_or_title",
    "repairs",
    "objections",
    "commitments",
    "next_action",
    "follow_up_at",
    "appointment_details",
)
EVIDENCE_NOTE_FIELDS = QUALITY_NOTE_FIELDS[1:]
LAND_QUALIFICATION_FIELDS = (
    "parcel_id",
    "acreage",
    "legal_description",
    "access_or_frontage",
    "utilities",
    "zoning_or_use",
    "septic_or_perc",
    "taxes_or_hoa",
    "terrain_or_environmental_concerns",
)


class CallIntelligenceError(RuntimeError):
    pass


def call_notes_model_for_asset(asset_class: object) -> type[StructuredCallNotes]:
    if normalize_asset_class(asset_class) == LAND_ASSET_CLASS:
        return LandStructuredCallNotes
    return StructuredCallNotes


def call_notes_system_prompt(base_prompt: str, asset_class: object) -> str:
    if normalize_asset_class(asset_class) != LAND_ASSET_CLASS:
        return base_prompt
    return f"{base_prompt}\n\n{LAND_CALL_INTELLIGENCE_PROMPT}"


def validate_call_notes_for_asset(notes: CallNotes, asset_class: object) -> CallNotes:
    return validate_call_notes_payload_for_asset(
        notes.model_dump(mode="json"),
        asset_class,
    )


def validate_call_notes_payload_for_asset(payload: object, asset_class: object) -> CallNotes:
    notes_model = call_notes_model_for_asset(asset_class)
    if notes_model is LandStructuredCallNotes and isinstance(payload, dict):
        payload = {**payload}
        for field in LAND_QUALIFICATION_FIELDS:
            payload.setdefault(field, None)
    return notes_model.model_validate(payload)


def resolve_transcript_asset_class(db: Session, transcript: CallTranscript) -> str:
    recording = db.get(CallRecording, transcript.recording_id)
    call = db.get(CallRecord, recording.call_record_id) if recording is not None else None
    lead = (
        db.get(Lead, call.lead_id)
        if call is not None and call.lead_id is not None
        else None
    )
    if lead is not None:
        return normalize_asset_class(lead.asset_class)
    return normalize_asset_class(
        (transcript.transcript_metadata or {}).get("asset_class"),
        default=HOUSE_ASSET_CLASS,
    )


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
    operation_event_id: UUID | None = None
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
        lead = db.get(Lead, call.lead_id) if call.lead_id is not None else None
        asset_class = normalize_asset_class(
            lead.asset_class if lead is not None else HOUSE_ASSET_CLASS
        )
        notes_model = call_notes_model_for_asset(asset_class)
        if lead is not None:
            operation_event = enqueue_call_intelligence_ai_work(
                db,
                transcript_id=transcript.id,
                lead=lead,
                actor_user_id=call.actor_user_id,
                conversation_id=call.conversation_id,
            )
            operation_event_id = operation_event.id

        agent, prompt = ensure_call_intelligence_agent(
            db,
            organization_id=transcript.organization_id,
            model_name=settings.openai_default_model,
        )
        run = AiRunLog(
            organization_id=transcript.organization_id,
            agent_definition_id=agent.id,
            prompt_version_id=prompt.id,
            lead_id=lead.id if lead is not None else None,
            orchestrator_event_id=operation_event_id,
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
            execution_mode="production",
            capability_key="call.summarize",
            idempotency_key=f"call-notes:{transcript.id}",
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

        notes_payload, note_usage = client.create_structured_response(
            model=settings.openai_default_model,
            system_prompt=call_notes_system_prompt(prompt.prompt_text, asset_class),
            user_prompt=build_call_notes_prompt(
                db,
                call,
                transcript,
                asset_class=asset_class,
            ),
            schema_name=(
                "stonegate_land_call_notes"
                if asset_class == LAND_ASSET_CLASS
                else "stonegate_call_notes"
            ),
            json_schema=notes_model.model_json_schema(),
            reasoning_effort=settings.openai_reasoning_effort,
        )
        notes = notes_model.model_validate(notes_payload)
        confidence = notes.confidence
        if isinstance(note_usage, int):
            note_usage = {
                "input_tokens": None,
                "output_tokens": None,
                "total_tokens": note_usage,
            }
        audio_cost = estimate_openai_cost(
            settings,
            model=settings.openai_transcription_model,
            input_tokens=audio_result.input_tokens,
            output_tokens=audio_result.output_tokens,
        )
        notes_cost = estimate_openai_cost(
            settings,
            model=settings.openai_default_model,
            input_tokens=note_usage["input_tokens"],
            output_tokens=note_usage["output_tokens"],
        )
        component_costs = [audio_cost.cost_microusd, notes_cost.cost_microusd]
        total_cost_microusd = (
            sum(cost for cost in component_costs if cost is not None)
            if all(cost is not None for cost in component_costs)
            else None
        )
        input_tokens = sum_optional_counts(
            audio_result.input_tokens,
            note_usage["input_tokens"],
        )
        output_tokens = sum_optional_counts(
            audio_result.output_tokens,
            note_usage["output_tokens"],
        )
        property_record = db.get(Property, lead.property_id) if lead is not None else None
        auto_populated_values = (
            auto_populate_call_note_fields(
                lead,
                notes,
                db=db,
                property_record=property_record,
            )
            if lead is not None
            else {}
        )
        processing_completed_at = datetime.now(UTC)
        transcript.confidence_score = confidence
        transcript.status = "needs_review" if lead is not None else "completed"
        transcript.error_message = None
        transcript.transcript_metadata = {
            **metadata,
            "processing_completed_at": processing_completed_at.isoformat(),
            "structured_notes": notes.model_dump(mode="json"),
            "transcription_model": settings.openai_transcription_model,
            "notes_model": settings.openai_default_model,
            "human_review_required": lead is not None,
            "conversation_context": "seller" if lead is not None else "buyer",
            "asset_class": asset_class,
            "evidence_coverage_percent": evidence_coverage_percent(notes),
            "crm_auto_populated_at": (
                processing_completed_at.isoformat() if auto_populated_values else None
            ),
            "crm_auto_populated_values": auto_populated_values,
        }
        approval: ApprovalRequest | None = None
        if lead is not None:
            if auto_populated_values:
                auto_populated_fields = ", ".join(auto_populated_values)
                db.add(
                    ActivityEvent(
                        organization_id=lead.organization_id,
                        actor_user_id=None,
                        entity_type="lead",
                        entity_id=lead.id,
                        event_type="call_notes.crm_fields_auto_populated",
                        summary=f"AI call notes filled empty CRM fields: {auto_populated_fields}.",
                    )
                )
                db.add(
                    AuditEvent(
                        organization_id=lead.organization_id,
                        actor_user_id=None,
                        actor_type="ai",
                        action="call_notes.crm_fields_auto_populate",
                        entity_type="lead",
                        entity_id=lead.id,
                        previous_value=dict.fromkeys(auto_populated_values),
                        new_value=auto_populated_values,
                        reason="Transcript-grounded call qualification populated empty CRM fields.",
                    )
                )
            approval = ensure_call_notes_approval(db, transcript, call, lead, notes)
            transcript.transcript_metadata = {
                **(transcript.transcript_metadata or {}),
                "approval_request_id": str(approval.id),
            }
            run.status = "needs_review"
        else:
            run.status = "completed"
        run.output_summary = notes.summary[:4000]
        run.input_tokens = input_tokens
        run.output_tokens = output_tokens
        run.total_tokens = (
            sum(
                value
                for value in (audio_result.total_tokens, note_usage["total_tokens"])
                if value is not None
            )
            or None
        )
        run.cost_microusd = total_cost_microusd
        run.cost_cents = cents_from_microusd(total_cost_microusd)
        run.run_metadata = {
            "pricing_components": [
                audio_cost.to_metadata(),
                notes_cost.to_metadata(),
            ],
            "pricing_status": ("priced" if total_cost_microusd is not None else "incomplete"),
        }
        run.latency_ms = round((time.perf_counter() - started_monotonic) * 1000)
        run.completed_at = datetime.now(UTC)
        transcript.transcript_metadata = {
            **(transcript.transcript_metadata or {}),
            "ai_run_id": str(run.id),
        }
        if operation_event_id is not None:
            mark_call_intelligence_ai_work(
                db,
                event_id=operation_event_id,
                status="needs_review" if lead is not None else "completed",
                run_id=run.id,
                summary=notes.summary,
                approval_request_id=approval.id if approval is not None else None,
            )
        db.commit()
        db.refresh(transcript)
        return transcript
    except (
        CallIntelligenceError,
        OpenAIClientError,
        TwilioRecordingError,
        ValidationError,
        ValueError,
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
                persisted_run.latency_ms = round((time.perf_counter() - started_monotonic) * 1000)
                persisted_run.completed_at = datetime.now(UTC)
        if operation_event_id is not None:
            mark_call_intelligence_ai_work(
                db,
                event_id=operation_event_id,
                status="failed",
                run_id=run_id,
                error_message=str(exc),
            )
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
    if recording is None or recording.deleted_at is not None or recording.status != "completed":
        raise ValueError("Call audio is unavailable for the required human review.")
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
    notes = validate_call_notes_for_asset(payload.structured_notes, lead.asset_class)
    review_metrics = calculate_review_metrics(
        previous.get("structured_notes"),
        notes,
    )
    transcript.transcript_metadata = {
        **(transcript.transcript_metadata or {}),
        "structured_notes": notes.model_dump(mode="json"),
        "reviewed_at": datetime.now(UTC).isoformat(),
        "review_decision_notes": payload.decision_notes,
        "review_metrics": review_metrics,
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
    reviewed_run_id = mark_ai_run_reviewed(db, transcript, payload.status)
    mark_call_intelligence_reviewed(
        db,
        run_id=reviewed_run_id,
        decision=payload.status,
        reviewer_user_id=principal.user_id,
    )
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
        notes = (
            validate_call_notes_payload_for_asset(
                raw_notes,
                resolve_transcript_asset_class(db, transcript),
            )
            if raw_notes
            else None
        )
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
    notes: CallNotes,
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


def build_call_notes_prompt(
    db: Session,
    call: CallRecord,
    transcript: CallTranscript,
    *,
    asset_class: str | None = None,
) -> str:
    contact = db.get(Contact, call.contact_id)
    lead = db.get(Lead, call.lead_id)
    property_record = db.get(Property, lead.property_id) if lead else None
    segments = transcript.speaker_segments or []
    contact_name = contact.preferred_name or contact.legal_name if contact else "Unknown"
    resolved_asset_class = normalize_asset_class(
        asset_class if asset_class is not None else (lead.asset_class if lead else None)
    )
    property_payload: dict[str, object] | None = (
        {
            "address": property_record.street_address,
            "city": property_record.city,
            "state": property_record.state,
        }
        if property_record
        else None
    )
    if property_payload is not None and resolved_asset_class == LAND_ASSET_CLASS:
        property_payload = {
            **property_payload,
            "parcel_id": property_record.parcel_id if property_record else None,
        }
    payload: dict[str, object] = {
        "party_type": "seller" if lead is not None else "buyer",
        "seller": contact_name if lead is not None else None,
        "buyer": contact_name if lead is None else None,
        "property": property_payload,
        "call_direction": call.direction,
        "segments": segments,
        "full_transcript": transcript.transcript_text,
    }
    if resolved_asset_class == LAND_ASSET_CLASS:
        payload["asset_class"] = LAND_ASSET_CLASS
    return json.dumps(
        payload,
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
    notes: CallNotes,
    *,
    apply_field_updates: list[str],
    create_follow_up_task: bool,
) -> None:
    metadata = transcript.transcript_metadata or {}
    if metadata.get("applied_at"):
        return
    applied_fields: list[str] = []
    note_values = notes.model_dump()
    raw_auto_populated_values = metadata.get("crm_auto_populated_values")
    auto_populated_values = (
        raw_auto_populated_values if isinstance(raw_auto_populated_values, dict) else {}
    )
    for note_field in apply_field_updates:
        lead_field = LEAD_UPDATE_FIELDS.get(note_field)
        if lead_field is None:
            continue
        value = note_values.get(note_field)
        current_value = getattr(lead, lead_field)
        can_correct_auto_value = (
            lead_field in auto_populated_values
            and current_value == auto_populated_values[lead_field]
        )
        if (can_correct_auto_value and current_value != value) or (
            value and crm_field_is_empty(current_value)
        ):
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
        follow_up_at = parse_follow_up_at(notes.follow_up_at)
        db.add(
            Task(
                organization_id=principal.organization_id,
                lead_id=lead.id,
                responsible_user_id=lead.assigned_user_id or call.actor_user_id,
                task_type="call_follow_up",
                title=notes.next_action[:255],
                status="open",
                priority="normal",
                due_at=follow_up_at,
                completed_at=None,
            )
        )
        if follow_up_at is not None and lead.next_follow_up_at is None:
            lead.next_follow_up_at = follow_up_at
    transcript.transcript_metadata = {
        **metadata,
        "applied_at": datetime.now(UTC).isoformat(),
        "applied_fields": applied_fields,
        "approved_note_logged": True,
        "follow_up_task_created": bool(create_follow_up_task and notes.next_action),
    }


def auto_populate_call_note_fields(
    lead: Lead,
    notes: CallNotes,
    *,
    db: Session | None = None,
    property_record: Property | None = None,
) -> dict[str, object]:
    populated_values: dict[str, object] = {}
    note_values = notes.model_dump()
    for note_field, lead_field in LEAD_UPDATE_FIELDS.items():
        value = note_values.get(note_field)
        if not value or not crm_field_is_empty(getattr(lead, lead_field)):
            continue
        setattr(lead, lead_field, value)
        populated_values[lead_field] = value
    if (
        not isinstance(notes, LandStructuredCallNotes)
        or normalize_asset_class(lead.asset_class) != LAND_ASSET_CLASS
    ):
        return populated_values

    qualification_context = dict(lead.qualification_context or {})
    context_changed = False
    for field in LAND_QUALIFICATION_FIELDS:
        value = note_values.get(field)
        if (
            crm_field_is_empty(value)
            or not crm_field_is_empty(qualification_context.get(field))
            or not evidence_supports_land_field(notes, field)
            or (
                field == "parcel_id"
                and isinstance(value, str)
                and not evidence_explicitly_contains_value(notes, field, value)
            )
        ):
            continue
        qualification_context[field] = value
        populated_values[f"qualification_context.{field}"] = value
        context_changed = True
    if context_changed:
        lead.qualification_context = qualification_context

    if (
        property_record is not None
        and crm_field_is_empty(property_record.parcel_id)
        and notes.parcel_id
        and evidence_explicitly_contains_value(notes, "parcel_id", notes.parcel_id)
    ):
        property_record.parcel_id = notes.parcel_id.strip()
        populated_values["property.parcel_id"] = property_record.parcel_id
        from app.services.property_identity import refresh_property_identity_keys
        from app.services.property_intelligence import (
            enqueue_property_research,
            invalidate_property_intelligence,
        )

        refresh_property_identity_keys(property_record)
        if db is not None and property_record.normalized_parcel_key:
            invalidate_property_intelligence(db, property_record)
            enqueue_property_research(
                db,
                property_record,
                source_lead_id=lead.id,
                trigger_source="call_intelligence_parcel_autofill",
            )
    return populated_values


def crm_field_is_empty(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, list | tuple | dict | set):
        return not value
    return False


def evidence_supports_land_field(notes: LandStructuredCallNotes, field: str) -> bool:
    return any(
        evidence.field == field and evidence.supporting_text.strip()
        for evidence in notes.evidence
    )


def evidence_explicitly_contains_value(
    notes: LandStructuredCallNotes,
    field: str,
    value: str,
) -> bool:
    normalized_value = normalize_identifier_evidence(value)
    if len(normalized_value) < 3:
        return False
    return any(
        evidence.field == field
        and normalized_value in normalize_identifier_evidence(evidence.supporting_text)
        for evidence in notes.evidence
    )


def normalize_identifier_evidence(value: str) -> str:
    return "".join(character.lower() for character in value if character.isalnum())


def format_approved_notes(notes: CallNotes) -> str:
    lines = [notes.summary]
    details = (
        ("Motivation", notes.motivation),
        ("Timeline", notes.timeline),
        ("Condition", notes.property_condition),
        ("Occupancy", notes.occupancy_status),
        ("Asking price", notes.asking_price),
        ("Mortgage balance/payoff", notes.mortgage_balance),
        ("Mortgage/title", notes.mortgage_or_title),
        ("Next action", notes.next_action),
        ("Appointment", notes.appointment_details),
    )
    lines.extend(f"{label}: {value}" for label, value in details if value)
    if isinstance(notes, LandStructuredCallNotes):
        land_details = (
            ("Parcel/APN (seller stated)", notes.parcel_id),
            ("Acreage (seller stated)", notes.acreage),
            ("Legal description (seller stated)", notes.legal_description),
            ("Access/frontage (seller stated)", notes.access_or_frontage),
            ("Utilities (seller stated)", notes.utilities),
            ("Zoning/intended use (unverified)", notes.zoning_or_use),
            ("Septic/perc (seller stated)", notes.septic_or_perc),
            ("Taxes/HOA (seller stated)", notes.taxes_or_hoa),
            (
                "Terrain/environmental concerns (seller stated)",
                notes.terrain_or_environmental_concerns,
            ),
        )
        lines.extend(f"{label}: {value}" for label, value in land_details if value)
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
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def mark_ai_run_reviewed(
    db: Session,
    transcript: CallTranscript,
    status: str,
) -> UUID | None:
    run_id = (transcript.transcript_metadata or {}).get("ai_run_id")
    if not isinstance(run_id, str):
        return None
    try:
        parsed_run_id = UUID(run_id)
    except ValueError:
        return None
    run = db.get(AiRunLog, parsed_run_id)
    if run is not None:
        run.status = status
        run.run_metadata = {
            **(run.run_metadata or {}),
            "human_review_status": status,
            "review_metrics": (transcript.transcript_metadata or {}).get("review_metrics"),
        }
    return parsed_run_id


def calculate_review_metrics(
    raw_draft: object,
    reviewed_notes: CallNotes,
) -> dict[str, object]:
    draft = raw_draft if isinstance(raw_draft, dict) else {}
    reviewed = reviewed_notes.model_dump(mode="json")
    quality_fields = quality_note_fields(reviewed_notes)
    changed_fields = [
        field
        for field in quality_fields
        if normalize_quality_value(draft.get(field)) != normalize_quality_value(reviewed.get(field))
    ]
    evaluated_count = len(quality_fields)
    agreement = round(100 * (evaluated_count - len(changed_fields)) / evaluated_count)
    return {
        "evaluated_field_count": evaluated_count,
        "changed_field_count": len(changed_fields),
        "changed_fields": changed_fields,
        "field_agreement_percent": agreement,
        "evidence_coverage_percent": evidence_coverage_percent(reviewed_notes),
    }


def evidence_coverage_percent(notes: CallNotes) -> int | None:
    payload = notes.model_dump(mode="json")
    evidence_fields = evidence_note_fields(notes)
    populated_fields = {
        field
        for field in evidence_fields
        if normalize_quality_value(payload.get(field)) not in (None, (), "")
    }
    if not populated_fields:
        return None
    evidenced_fields = {
        evidence.field for evidence in notes.evidence if evidence.supporting_text.strip()
    }
    return round(100 * len(populated_fields & evidenced_fields) / len(populated_fields))


def quality_note_fields(notes: CallNotes) -> tuple[str, ...]:
    if isinstance(notes, LandStructuredCallNotes):
        return QUALITY_NOTE_FIELDS + LAND_QUALIFICATION_FIELDS
    return QUALITY_NOTE_FIELDS


def evidence_note_fields(notes: CallNotes) -> tuple[str, ...]:
    if isinstance(notes, LandStructuredCallNotes):
        return EVIDENCE_NOTE_FIELDS + LAND_QUALIFICATION_FIELDS
    return EVIDENCE_NOTE_FIELDS


def normalize_quality_value(value: object) -> object:
    if isinstance(value, str):
        return " ".join(value.lower().split())
    if isinstance(value, list):
        return tuple(
            sorted(
                str(normalize_quality_value(item))
                for item in value
                if normalize_quality_value(item) not in (None, "")
            )
        )
    return value


def sum_optional_counts(*values: int | None) -> int | None:
    present = [value for value in values if value is not None]
    return sum(present) if present else None
