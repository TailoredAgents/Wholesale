import json
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import and_, exists, or_, select
from sqlalchemy.exc import IntegrityError
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
    Conversation,
    Lead,
    Property,
    Prospect,
    ProspectHandoff,
    ProspectingAttempt,
    ProspectingCallQualityReview,
    ProspectingDialLeg,
    ProspectingProviderEvent,
    ProspectingQualificationResponse,
    ProspectingScriptVersion,
    Task,
)
from app.schemas.voice import (
    CallNotes,
    CallTranscriptRead,
    CallTranscriptReview,
    LandStructuredCallNotes,
    StructuredCallNotes,
)
from app.services.ai_costs import AiCostEstimate, cents_from_microusd, estimate_openai_cost
from app.services.ai_operations import (
    enqueue_call_intelligence_ai_work,
    mark_call_intelligence_ai_work,
    mark_call_intelligence_reviewed,
)
from app.services.call_evidence_scope import get_authorized_recording
from app.services.call_recording_evidence import select_preferred_call_recording
from app.services.lead_lifecycle import (
    INACTIVE_LEAD_STAGES,
    lock_organization_lead,
    require_lead_open_for_work,
)

CALL_INTELLIGENCE_AGENT_KEY = "call_intelligence"
CALL_INTELLIGENCE_PROMPT = """You prepare factual real-estate acquisition call notes.
Use only facts explicitly present in the diarized transcript. Never infer a price, timeline,
condition, occupancy, debt, title issue, commitment, or appointment. Put a stated mortgage,
loan balance, or payoff amount in mortgage_balance; use mortgage_or_title for other lien, probate,
ownership, or title context. Use null or an empty list when the call does not support a field.
Keep seller language precise and operational.
Evidence entries must point to the supplied segment index and start time. This is a draft for
internal CRM documentation and must not claim that Stonegate made a binding offer or contractual
commitment."""
CALL_NOTES_OUTPUT_GUARD = """Write all CRM note fields in clear English using Latin-script
words and standard punctuation. Never substitute CJK or other non-Latin characters to shorten
an English phrase or fit a field limit. The timeline,
property_condition, occupancy_status, asking_price, and mortgage_balance fields must each be
a concise, complete thought of no more than about 90 characters. Omit secondary detail rather
than ending mid-sentence, switching languages, or inventing an abbreviation."""
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


class PermanentCallIntelligenceError(CallIntelligenceError):
    """A transcript failure that cannot be repaired by retrying the provider."""


PROSPECTING_TRANSCRIPT_CONTACT_OUTCOMES = {
    "callback_requested",
    "follow_up",
    "interested",
    "appointment_set",
    "not_interested",
    "do_not_call",
}


@dataclass(frozen=True)
class ProspectingTranscriptEligibility:
    state: str
    reason: str
    call: CallRecord | None = None
    attempt: ProspectingAttempt | None = None
    leg: ProspectingDialLeg | None = None
    prospect: Prospect | None = None

    @property
    def eligible(self) -> bool:
        return self.state == "eligible"


def call_notes_model_for_asset(asset_class: object) -> type[StructuredCallNotes]:
    if normalize_asset_class(asset_class) == LAND_ASSET_CLASS:
        return LandStructuredCallNotes
    return StructuredCallNotes


def call_notes_system_prompt(base_prompt: str, asset_class: object) -> str:
    prompts = [base_prompt, CALL_NOTES_OUTPUT_GUARD]
    if normalize_asset_class(asset_class) == LAND_ASSET_CLASS:
        prompts.append(LAND_CALL_INTELLIGENCE_PROMPT)
    return "\n\n".join(prompts)


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
    lead = db.get(Lead, call.lead_id) if call is not None and call.lead_id is not None else None
    if lead is not None:
        return normalize_asset_class(lead.asset_class)
    prospect = (
        db.get(Prospect, call.prospect_id)
        if call is not None and call.prospect_id is not None
        else None
    )
    if prospect is not None:
        return normalize_asset_class(prospect.asset_class)
    return normalize_asset_class(
        (transcript.transcript_metadata or {}).get("asset_class"),
        default=HOUSE_ASSET_CLASS,
    )


def prospecting_transcript_eligibility(
    db: Session,
    recording: CallRecording,
) -> ProspectingTranscriptEligibility:
    """Validate the entire signed cold-call graph before audio can leave Twilio."""

    call = db.get(CallRecord, recording.call_record_id)
    if call is None or call.organization_id != recording.organization_id:
        return ProspectingTranscriptEligibility("invalid", "Call record is unavailable.")
    if recording.deleted_at is not None or recording.status == "deleted":
        return ProspectingTranscriptEligibility(
            "invalid",
            "The retained call audio has been deleted.",
            call=call,
        )
    if recording.status != "completed":
        if recording.status in {"in-progress", "processing", "queued"}:
            return ProspectingTranscriptEligibility(
                "pending",
                "The recording is still being processed.",
                call=call,
            )
        return ProspectingTranscriptEligibility(
            "invalid",
            "The recording ended without completed media.",
            call=call,
        )
    if not recording.provider_recording_id:
        return ProspectingTranscriptEligibility(
            "invalid",
            "The completed recording is missing its provider identity.",
            call=call,
        )
    if recording.consent_status not in {"disclosed", "one_party_consent"}:
        return ProspectingTranscriptEligibility(
            "invalid",
            "The completed recording lacks an authorized consent record.",
            call=call,
        )
    if call.prospect_id is None:
        return ProspectingTranscriptEligibility("eligible", "Warm CRM call.", call=call)
    if not all((call.prospect_id, call.prospecting_attempt_id, call.prospecting_dial_leg_id)):
        return ProspectingTranscriptEligibility(
            "invalid", "Cold-call correlation identifiers are incomplete.", call=call
        )
    attempt = db.get(ProspectingAttempt, call.prospecting_attempt_id)
    leg = db.get(ProspectingDialLeg, call.prospecting_dial_leg_id)
    prospect = db.get(Prospect, call.prospect_id)
    if attempt is None or leg is None or prospect is None:
        return ProspectingTranscriptEligibility(
            "invalid", "Cold-call graph is incomplete.", call=call
        )
    if not all(
        (
            call.provider_call_id,
            attempt.provider_call_id,
            leg.provider_call_id,
            attempt.provider_recording_id,
            leg.provider_recording_id,
        )
    ):
        return ProspectingTranscriptEligibility(
            "invalid",
            "Cold-call provider correlation is incomplete.",
            call=call,
            attempt=attempt,
            leg=leg,
            prospect=prospect,
        )
    graph_matches = all(
        (
            attempt.organization_id == recording.organization_id,
            leg.organization_id == recording.organization_id,
            prospect.organization_id == recording.organization_id,
            attempt.prospect_id == prospect.id,
            leg.prospect_id == prospect.id,
            leg.attempt_id == attempt.id,
            attempt.call_record_id == call.id,
            leg.call_record_id == call.id,
            attempt.batch_entry_id == leg.batch_entry_id,
            attempt.provider_call_id == call.provider_call_id,
            leg.provider_call_id == call.provider_call_id,
            attempt.provider_recording_id == recording.provider_recording_id,
            leg.provider_recording_id == recording.provider_recording_id,
        )
    )
    if not graph_matches:
        return ProspectingTranscriptEligibility(
            "invalid",
            "Cold-call graph identifiers conflict.",
            call=call,
            attempt=attempt,
            leg=leg,
            prospect=prospect,
        )
    signed_recording_event = db.scalar(
        select(ProspectingProviderEvent.id).where(
            ProspectingProviderEvent.organization_id == recording.organization_id,
            ProspectingProviderEvent.provider == recording.provider,
            ProspectingProviderEvent.attempt_id == attempt.id,
            ProspectingProviderEvent.dial_leg_id == leg.id,
            ProspectingProviderEvent.provider_recording_id == recording.provider_recording_id,
            ProspectingProviderEvent.event_type == "recording.completed",
            ProspectingProviderEvent.signature_verified.is_(True),
        )
    )
    if signed_recording_event is None:
        return ProspectingTranscriptEligibility(
            "invalid",
            "No verified provider recording callback matches the cold-call graph.",
            call=call,
            attempt=attempt,
            leg=leg,
            prospect=prospect,
        )
    if attempt.status != "completed" or leg.completed_at is None:
        return ProspectingTranscriptEligibility(
            "pending",
            "The caller has not completed wrap-up.",
            call=call,
            attempt=attempt,
            leg=leg,
            prospect=prospect,
        )
    if (
        attempt.contact_made is not True
        or attempt.outcome not in PROSPECTING_TRANSCRIPT_CONTACT_OUTCOMES
        or leg.connected_at is None
        or leg.status != "completed"
        or attempt.party_classification == "wrong_party"
        or leg.party_classification == "wrong_party"
    ):
        return ProspectingTranscriptEligibility(
            "ineligible",
            "Only completed, connected seller conversations are transcribed.",
            call=call,
            attempt=attempt,
            leg=leg,
            prospect=prospect,
        )
    return ProspectingTranscriptEligibility(
        "eligible",
        "Completed connected seller conversation.",
        call=call,
        attempt=attempt,
        leg=leg,
        prospect=prospect,
    )


def enqueue_eligible_prospecting_call_transcript(
    db: Session,
    recording: CallRecording,
    *,
    model_name: str,
) -> CallTranscript | None:
    eligibility = prospecting_transcript_eligibility(db, recording)
    if not eligibility.eligible:
        return None
    return enqueue_call_transcript(db, recording, model_name=model_name)


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
        transcript_metadata={"attempts": 0, "human_review_required": False},
    )
    try:
        with db.begin_nested():
            db.add(transcript)
            db.flush()
        return transcript
    except IntegrityError:
        existing = db.scalar(
            select(CallTranscript).where(CallTranscript.recording_id == recording.id)
        )
        if existing is None:
            raise CallIntelligenceError("The call transcript could not be queued safely.") from None
        return existing


def process_next_call_transcript(
    db: Session,
    settings: Settings | None = None,
) -> UUID | None:
    settings = settings or get_settings()
    now = datetime.now(UTC)
    candidates = db.scalars(
        select(CallTranscript)
        .where(
            or_(
                CallTranscript.status.in_(("queued", "failed")),
                (
                    (CallTranscript.status == "processing")
                    & (CallTranscript.updated_at < now - timedelta(minutes=15))
                ),
            )
        )
        .order_by(CallTranscript.created_at.asc())
        .with_for_update(skip_locked=True)
        .limit(100)
    ).all()
    transcript: CallTranscript | None = None
    exhausted_legacy_jobs = False
    for item in candidates:
        item_recording = db.get(CallRecording, item.recording_id)
        if item_recording is None:
            item.status = "exhausted"
            item.error_message = "The call recording is unavailable."
            item.transcript_metadata = {
                **(item.transcript_metadata or {}),
                "permanent_failure": True,
                "exhausted_at": now.isoformat(),
                "next_retry_at": None,
            }
            exhausted_legacy_jobs = True
            continue
        provider_transcript_ready = bool(
            item.provider == "batchdialer"
            and item_recording.provider == "batchdialer"
            and (item.transcript_text or "").strip()
        )
        if not provider_transcript_ready:
            eligibility = prospecting_transcript_eligibility(db, item_recording)
            if eligibility.state == "pending":
                continue
            if eligibility.state in {"invalid", "ineligible"}:
                item.status = "exhausted"
                item.error_message = eligibility.reason
                item.transcript_metadata = {
                    **(item.transcript_metadata or {}),
                    "permanent_failure": True,
                    "eligibility_state": eligibility.state,
                    "exhausted_at": now.isoformat(),
                    "next_retry_at": None,
                }
                exhausted_legacy_jobs = True
                continue
        metadata = item.transcript_metadata or {}
        attempts = int(metadata.get("attempts", 0))
        if attempts >= settings.call_transcription_max_attempts:
            item.status = "exhausted"
            item.transcript_metadata = {
                **metadata,
                "exhausted_at": metadata.get("exhausted_at") or now.isoformat(),
                "next_retry_at": None,
            }
            exhausted_legacy_jobs = True
            continue
        if item.status == "failed" and not call_transcript_retry_due(item, now=now):
            continue
        transcript = item
        break
    if exhausted_legacy_jobs:
        db.flush()
        if transcript is None:
            db.commit()
    if transcript is None:
        recordings = db.scalars(
            select(CallRecording)
            .join(CallRecord, CallRecord.id == CallRecording.call_record_id)
            .outerjoin(
                ProspectingAttempt,
                ProspectingAttempt.id == CallRecord.prospecting_attempt_id,
            )
            .outerjoin(
                ProspectingDialLeg,
                ProspectingDialLeg.id == CallRecord.prospecting_dial_leg_id,
            )
            .outerjoin(Prospect, Prospect.id == CallRecord.prospect_id)
            .outerjoin(CallTranscript, CallTranscript.recording_id == CallRecording.id)
            .where(
                CallRecording.status == "completed",
                CallRecording.deleted_at.is_(None),
                CallRecording.provider_recording_id.is_not(None),
                CallRecording.provider_recording_id != "",
                CallRecording.consent_status.in_({"disclosed", "one_party_consent"}),
                CallRecord.organization_id == CallRecording.organization_id,
                CallTranscript.id.is_(None),
                or_(
                    CallRecord.prospect_id.is_(None),
                    and_(
                        CallRecord.prospect_id.is_not(None),
                        Prospect.organization_id == CallRecording.organization_id,
                        ProspectingAttempt.organization_id == CallRecording.organization_id,
                        ProspectingDialLeg.organization_id == CallRecording.organization_id,
                        ProspectingAttempt.status == "completed",
                        ProspectingAttempt.completed_at.is_not(None),
                        ProspectingAttempt.contact_made.is_(True),
                        ProspectingAttempt.party_classification != "wrong_party",
                        ProspectingAttempt.outcome.in_(PROSPECTING_TRANSCRIPT_CONTACT_OUTCOMES),
                        ProspectingDialLeg.status == "completed",
                        ProspectingDialLeg.party_classification != "wrong_party",
                        ProspectingDialLeg.connected_at.is_not(None),
                        ProspectingDialLeg.completed_at.is_not(None),
                        ProspectingDialLeg.attempt_id == ProspectingAttempt.id,
                        ProspectingDialLeg.prospect_id == CallRecord.prospect_id,
                        ProspectingAttempt.prospect_id == CallRecord.prospect_id,
                        ProspectingDialLeg.batch_entry_id == ProspectingAttempt.batch_entry_id,
                        ProspectingDialLeg.call_record_id == CallRecord.id,
                        ProspectingAttempt.call_record_id == CallRecord.id,
                        CallRecord.provider_call_id.is_not(None),
                        CallRecord.provider_call_id != "",
                        ProspectingDialLeg.provider_call_id == CallRecord.provider_call_id,
                        ProspectingAttempt.provider_call_id == CallRecord.provider_call_id,
                        ProspectingDialLeg.provider_recording_id
                        == CallRecording.provider_recording_id,
                        ProspectingAttempt.provider_recording_id
                        == CallRecording.provider_recording_id,
                        exists().where(
                            ProspectingProviderEvent.organization_id
                            == CallRecording.organization_id,
                            ProspectingProviderEvent.provider == CallRecording.provider,
                            ProspectingProviderEvent.attempt_id == ProspectingAttempt.id,
                            ProspectingProviderEvent.dial_leg_id == ProspectingDialLeg.id,
                            ProspectingProviderEvent.provider_recording_id
                            == CallRecording.provider_recording_id,
                            ProspectingProviderEvent.event_type == "recording.completed",
                            ProspectingProviderEvent.signature_verified.is_(True),
                        ),
                    ),
                ),
            )
            .order_by(CallRecording.created_at.asc())
            .limit(100)
        ).all()
        for recording in recordings:
            eligibility = prospecting_transcript_eligibility(db, recording)
            if not eligibility.eligible:
                continue
            transcript = enqueue_call_transcript(
                db,
                recording,
                model_name=settings.openai_transcription_model,
            )
            break
        if transcript is None:
            return None
    transcript.status = "processing"
    transcript.error_message = None
    db.commit()
    transcript_id = transcript.id
    process_call_transcript(db, transcript_id, settings)
    return transcript_id


def process_next_pending_call_note_approval(
    db: Session,
    _settings: Settings,
) -> UUID | None:
    """Automatically post one legacy call-note draft that still awaits approval."""

    candidate_id = db.scalar(
        select(CallTranscript.id)
        .where(CallTranscript.status == "needs_review")
        .order_by(CallTranscript.created_at.asc())
        .limit(1)
    )
    if candidate_id is None:
        return None
    candidate = db.get(CallTranscript, candidate_id)
    if candidate is None:
        return None
    recording = db.get(CallRecording, candidate.recording_id)
    call = db.get(CallRecord, recording.call_record_id) if recording is not None else None
    if call is None or call.lead_id is None:
        candidate.status = "completed"
        cancel_legacy_call_note_approval(db, candidate)
        db.commit()
        return candidate.id
    lead = lock_organization_lead(
        db,
        organization_id=candidate.organization_id,
        lead_id=call.lead_id,
    )
    transcript = db.scalar(
        select(CallTranscript)
        .where(
            CallTranscript.id == candidate_id,
            CallTranscript.status == "needs_review",
        )
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    if transcript is None:
        return None
    if lead is None or lead.archived_at is not None or lead.stage_key in INACTIVE_LEAD_STAGES:
        transcript.status = "completed"
        transcript.transcript_metadata = {
            **(transcript.transcript_metadata or {}),
            "human_review_required": False,
            "note_posting_mode": "skipped_inactive_lead",
        }
        cancel_legacy_call_note_approval(db, transcript)
        db.commit()
        return transcript.id
    raw_notes = (transcript.transcript_metadata or {}).get("structured_notes")
    notes = validate_call_notes_payload_for_asset(raw_notes, lead.asset_class)
    auto_approve_call_notes(db, transcript, call, lead, notes)
    complete_auto_call_note_run(db, transcript, notes.summary)
    db.commit()
    return transcript.id


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
    manual_retry_count = int(metadata.get("manual_retry_count", 0))
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
        if recording.organization_id != transcript.organization_id:
            raise PermanentCallIntelligenceError(
                "Transcript and recording organization context conflict."
            )
        call = db.get(CallRecord, recording.call_record_id)
        if call is None:
            raise CallIntelligenceError("The call record is unavailable.")
        if call.organization_id != transcript.organization_id:
            raise PermanentCallIntelligenceError(
                "Transcript and call organization context conflict."
            )
        eligibility = prospecting_transcript_eligibility(db, recording)
        if call.prospect_id is not None and not eligibility.eligible:
            raise PermanentCallIntelligenceError(eligibility.reason)
        lead = db.get(Lead, call.lead_id) if call.lead_id is not None else None
        prospect = eligibility.prospect if call.prospect_id is not None else None
        prospecting_attempt = eligibility.attempt if prospect is not None else None
        asset_class = normalize_asset_class(
            lead.asset_class
            if lead is not None
            else (prospect.asset_class if prospect is not None else HOUSE_ASSET_CLASS)
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
            attempt_number=attempts,
            idempotency_key=(
                f"call-notes:{transcript.id}:manual:{manual_retry_count}:attempt:{attempts}"
            ),
        )
        db.add(run)
        db.flush()
        run_id = run.id
        db.commit()

        client = OpenAIResponsesClient(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout_seconds=settings.openai_request_timeout_seconds,
        )
        audio_input_tokens: int | None = None
        audio_output_tokens: int | None = None
        audio_total_tokens: int | None = None
        audio_cost: AiCostEstimate | None = None
        transcription_performed = not bool((transcript.transcript_text or "").strip())
        if transcription_performed:
            if call.prospect_id is not None:
                eligibility = prospecting_transcript_eligibility(db, recording)
                if not eligibility.eligible:
                    raise PermanentCallIntelligenceError(eligibility.reason)
            media = download_twilio_recording(settings, recording.provider_recording_id)
            if len(media.content) > settings.call_transcription_max_audio_bytes:
                raise PermanentCallIntelligenceError(
                    "Call recording exceeds OpenAI's 25 MB upload limit."
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
            audio_input_tokens = audio_result.input_tokens
            audio_output_tokens = audio_result.output_tokens
            audio_total_tokens = audio_result.total_tokens
            audio_cost = estimate_openai_cost(
                settings,
                model=settings.openai_transcription_model,
                input_tokens=audio_input_tokens,
                output_tokens=audio_output_tokens,
            )
            checkpointed_at = datetime.now(UTC)
            transcript.transcript_metadata = {
                **metadata,
                "transcription_checkpoint": {
                    "checkpointed_at": checkpointed_at.isoformat(),
                    "model": settings.openai_transcription_model,
                    "input_tokens": audio_input_tokens,
                    "output_tokens": audio_output_tokens,
                    "total_tokens": audio_total_tokens,
                },
            }
            run.input_tokens = audio_input_tokens
            run.output_tokens = audio_output_tokens
            run.total_tokens = audio_total_tokens
            run.cost_microusd = audio_cost.cost_microusd
            run.cost_cents = cents_from_microusd(audio_cost.cost_microusd)
            run.run_metadata = {
                "pricing_components": [audio_cost.to_metadata()],
                "pricing_status": audio_cost.pricing_status,
                "transcription_checkpointed": True,
            }
            # Keep the paid transcription even when later note generation fails. A retry
            # can then resume from the saved text without downloading or transcribing again.
            db.commit()
            metadata = dict(transcript.transcript_metadata or {})

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
        reject_unexpected_cjk_call_notes(notes)
        confidence = notes.confidence
        if isinstance(note_usage, int):
            note_usage = {
                "input_tokens": None,
                "output_tokens": None,
                "total_tokens": note_usage,
            }
        notes_cost = estimate_openai_cost(
            settings,
            model=settings.openai_default_model,
            input_tokens=note_usage["input_tokens"],
            output_tokens=note_usage["output_tokens"],
        )
        pricing_components = [notes_cost.to_metadata()]
        component_costs = [notes_cost.cost_microusd]
        if audio_cost is not None:
            pricing_components.insert(0, audio_cost.to_metadata())
            component_costs.insert(0, audio_cost.cost_microusd)
        total_cost_microusd = (
            sum(cost for cost in component_costs if cost is not None)
            if all(cost is not None for cost in component_costs)
            else None
        )
        input_tokens = sum_optional_counts(
            audio_input_tokens,
            note_usage["input_tokens"],
        )
        output_tokens = sum_optional_counts(
            audio_output_tokens,
            note_usage["output_tokens"],
        )
        if lead is not None:
            lead = lock_organization_lead(
                db,
                organization_id=transcript.organization_id,
                lead_id=lead.id,
            )
        lead_is_active = bool(
            lead is not None
            and lead.archived_at is None
            and lead.stage_key not in INACTIVE_LEAD_STAGES
        )
        property_record = (
            db.get(Property, lead.property_id) if lead is not None and lead_is_active else None
        )
        auto_populated_values = (
            auto_populate_call_note_fields(
                lead,
                notes,
                db=db,
                property_record=property_record,
            )
            if lead is not None and lead_is_active
            else {}
        )
        prospecting_suggestions = (
            apply_prospecting_transcript_suggestions(
                db,
                transcript=transcript,
                attempt=prospecting_attempt,
                notes=notes,
            )
            if prospecting_attempt is not None
            else []
        )
        processing_completed_at = datetime.now(UTC)
        transcript.confidence_score = confidence
        transcript.status = "processing" if lead_is_active else "completed"
        transcript.error_message = None
        transcript.transcript_metadata = {
            **metadata,
            "processing_completed_at": processing_completed_at.isoformat(),
            "structured_notes": notes.model_dump(mode="json"),
            "quick_read_summary": build_quick_read_summary(notes),
            "transcription_model": settings.openai_transcription_model,
            "notes_model": settings.openai_default_model,
            "human_review_required": False,
            "note_posting_mode": "automatic",
            "conversation_context": (
                "seller"
                if lead is not None
                else ("prospecting_seller" if prospect is not None else "buyer")
            ),
            "asset_class": asset_class,
            "evidence_coverage_percent": evidence_coverage_percent(notes),
            "crm_auto_populated_at": (
                processing_completed_at.isoformat() if auto_populated_values else None
            ),
            "crm_auto_populated_values": auto_populated_values,
            "closed_lead_historical_evidence": bool(lead is not None and not lead_is_active),
            "prospecting_attempt_id": (
                str(prospecting_attempt.id) if prospecting_attempt is not None else None
            ),
            "prospecting_suggestions": prospecting_suggestions,
            "ai_run_id": str(run.id),
        }
        if lead is not None and lead_is_active:
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
            auto_approve_call_notes(db, transcript, call, lead, notes)
            db.flush()
        if prospecting_attempt is not None:
            mark_prospecting_call_quality_transcript_ready(
                db,
                attempt=prospecting_attempt,
                transcript=transcript,
            )
        run.status = "completed"
        run.output_summary = notes.summary[:4000]
        run.input_tokens = input_tokens
        run.output_tokens = output_tokens
        run.total_tokens = (
            sum(
                value
                for value in (audio_total_tokens, note_usage["total_tokens"])
                if value is not None
            )
            or None
        )
        run.cost_microusd = total_cost_microusd
        run.cost_cents = cents_from_microusd(total_cost_microusd)
        run.run_metadata = {
            "pricing_components": pricing_components,
            "pricing_status": ("priced" if total_cost_microusd is not None else "incomplete"),
            "transcription_checkpointed": transcription_performed,
            "transcription_reused": not transcription_performed,
        }
        run.latency_ms = round((time.perf_counter() - started_monotonic) * 1000)
        run.completed_at = datetime.now(UTC)
        if operation_event_id is not None:
            mark_call_intelligence_ai_work(
                db,
                event_id=operation_event_id,
                status="completed",
                run_id=run.id,
                summary=notes.summary,
            )
        if prospecting_attempt is not None:
            db.flush()
            link_accepted_prospecting_evidence_for_attempt(
                db,
                prospecting_attempt.id,
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
        failed_at = datetime.now(UTC)
        permanent_failure = isinstance(exc, PermanentCallIntelligenceError)
        exhausted = permanent_failure or attempts >= settings.call_transcription_max_attempts
        retry_delay_seconds = min(30 * (2 ** min(attempts - 1, 5)), 900)
        transcript.transcript_metadata = {
            **(transcript.transcript_metadata or {}),
            "attempts": attempts,
            "last_failed_at": failed_at.isoformat(),
            "next_retry_at": (
                None
                if exhausted
                else (failed_at + timedelta(seconds=retry_delay_seconds)).isoformat()
            ),
            "exhausted_at": failed_at.isoformat() if exhausted else None,
            "permanent_failure": permanent_failure,
        }
        if exhausted:
            transcript.status = "exhausted"
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


def call_transcript_retry_due(
    transcript: CallTranscript,
    *,
    now: datetime | None = None,
) -> bool:
    """Return whether a failed transcript's retry delay has elapsed."""

    raw_retry_at = (transcript.transcript_metadata or {}).get("next_retry_at")
    if not raw_retry_at:
        return True
    try:
        retry_at = datetime.fromisoformat(str(raw_retry_at).replace("Z", "+00:00"))
    except ValueError:
        return True
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=UTC)
    return retry_at <= (now or datetime.now(UTC))


PROSPECTING_QUESTION_NOTE_ALIASES = {
    "condition": "property_condition",
    "property_condition": "property_condition",
    "occupancy": "occupancy_status",
    "occupancy_status": "occupancy_status",
    "asking_price": "asking_price",
    "price": "asking_price",
    "mortgage": "mortgage_balance",
    "mortgage_balance": "mortgage_balance",
    "title": "mortgage_or_title",
    "mortgage_or_title": "mortgage_or_title",
    "timeline": "timeline",
    "motivation": "motivation",
    **{field: field for field in LAND_QUALIFICATION_FIELDS},
}


def apply_prospecting_transcript_suggestions(
    db: Session,
    *,
    transcript: CallTranscript,
    attempt: ProspectingAttempt,
    notes: CallNotes,
) -> list[dict[str, object]]:
    """Save transcript-grounded suggestions without replacing caller-entered facts."""

    script = db.get(ProspectingScriptVersion, attempt.script_version_id)
    if (
        script is None
        or script.organization_id != attempt.organization_id
        or transcript.organization_id != attempt.organization_id
    ):
        raise PermanentCallIntelligenceError(
            "The transcript does not match the attempt's pinned caller script."
        )
    questions = {
        str(item.get("key") or "").strip(): item
        for item in (script.qualification_questions or [])
        if isinstance(item, dict) and str(item.get("key") or "").strip()
    }
    responses = {
        item.question_key: item
        for item in db.scalars(
            select(ProspectingQualificationResponse)
            .where(ProspectingQualificationResponse.attempt_id == attempt.id)
            .with_for_update()
        ).all()
    }
    notes_payload = notes.model_dump(mode="json")
    evidence_by_field: dict[str, list[dict[str, object]]] = {}
    for item in notes.evidence:
        evidence_by_field.setdefault(item.field, []).append(item.model_dump(mode="json"))
    suggestions: list[dict[str, object]] = []
    now = datetime.now(UTC)
    legacy_answers = dict(attempt.qualification_answers or {})
    for question_key, question in questions.items():
        note_field = PROSPECTING_QUESTION_NOTE_ALIASES.get(question_key.lower())
        if note_field is None or note_field not in notes_payload:
            continue
        suggested_value = notes_payload.get(note_field)
        evidence = evidence_by_field.get(note_field, [])
        if suggested_value in (None, "", []) or not evidence:
            continue
        response = responses.get(question_key)
        suggestion_state = "suggested"
        legacy_value = legacy_answers.get(question_key)
        current_value: object | None = (
            response.answer_value
            if response is not None and response.answer_value not in (None, "", [])
            else legacy_value
        )
        if response is None:
            legacy_value_present = legacy_value not in (None, "", [])
            response = ProspectingQualificationResponse(
                organization_id=attempt.organization_id,
                attempt_id=attempt.id,
                script_version_id=script.id,
                question_key=question_key,
                state="answered" if legacy_value_present else "needs_follow_up",
                answer_value=legacy_value if legacy_value_present else None,
                source="legacy_completion" if legacy_value_present else "ai_transcript",
                actor_user_id=attempt.caller_user_id if legacy_value_present else None,
                is_required=bool(question.get("required_for_handoff")),
                captured_at=(attempt.completed_at or now) if legacy_value_present else now,
                transcript_evidence={"items": evidence},
                response_metadata={
                    "revision": 1 if legacy_value_present else 0,
                    "materialized_from_attempt_answers": legacy_value_present,
                },
            )
            db.add(response)
            responses[question_key] = response
        human_value_present = current_value not in (None, "", [])
        if human_value_present:
            current_normalized = normalized_suggestion_value(current_value)
            suggested_normalized = normalized_suggestion_value(suggested_value)
            if current_normalized == suggested_normalized:
                suggestion_state = "corroborated"
            else:
                suggestion_state = "conflict"
                response.state = "conflict"
        if response is not None:
            response.transcript_evidence = {"items": evidence}
        response.response_metadata = {
            **dict(response.response_metadata or {}),
            "ai_suggestion": {
                "state": suggestion_state,
                "value": suggested_value,
                "note_field": note_field,
                "transcript_id": str(transcript.id),
                "recorded_at": now.isoformat(),
            },
        }
        suggestions.append(
            {
                "question_key": question_key,
                "state": suggestion_state,
                "current_value": current_value,
                "suggested_value": suggested_value,
                "evidence": evidence,
            }
        )
    return suggestions


def normalized_suggestion_value(value: object) -> str:
    if isinstance(value, str):
        return " ".join(value.lower().split())
    return json.dumps(value, sort_keys=True, default=str).lower()


def mark_prospecting_call_quality_transcript_ready(
    db: Session,
    *,
    attempt: ProspectingAttempt,
    transcript: CallTranscript,
) -> None:
    review = db.scalar(
        select(ProspectingCallQualityReview)
        .where(
            ProspectingCallQualityReview.organization_id == attempt.organization_id,
            ProspectingCallQualityReview.attempt_id == attempt.id,
        )
        .with_for_update()
    )
    if review is None:
        return
    review.call_record_id = attempt.call_record_id
    review.transcript_id = transcript.id
    if review.status == "awaiting_transcript":
        review.status = "ready_for_analysis"


def link_accepted_prospecting_evidence_for_attempt(
    db: Session,
    attempt_id: UUID,
) -> CommunicationRecord | None:
    """Link one completed cold-call transcript into the accepted seller timeline."""

    handoff = db.scalar(
        select(ProspectHandoff).where(ProspectHandoff.attempt_id == attempt_id).with_for_update()
    )
    if handoff is None or handoff.status != "accepted":
        return None
    attempt = db.get(ProspectingAttempt, attempt_id)
    if attempt is None or attempt.organization_id != handoff.organization_id:
        return None
    call = db.get(CallRecord, attempt.call_record_id) if attempt.call_record_id else None
    if call is None or call.organization_id != handoff.organization_id:
        return None
    recording = select_preferred_call_recording(
        db,
        organization_id=handoff.organization_id,
        call_record_id=call.id,
    )
    if recording is None:
        return None
    transcript = db.scalar(
        select(CallTranscript).where(
            CallTranscript.organization_id == handoff.organization_id,
            CallTranscript.recording_id == recording.id,
            CallTranscript.status.in_(("completed", "approved")),
        )
    )
    if transcript is None:
        return None
    raw_notes = (transcript.transcript_metadata or {}).get("structured_notes")
    if not raw_notes:
        return None
    lead = db.get(Lead, handoff.lead_id)
    if lead is None or lead.organization_id != handoff.organization_id:
        return None
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.organization_id == handoff.organization_id,
            Conversation.lead_id == lead.id,
        )
    )
    if conversation is None or conversation.contact_id != lead.contact_id:
        return None
    provider_message_id = f"prospecting-call-notes:{transcript.id}"
    existing = db.scalar(
        select(CommunicationRecord).where(
            CommunicationRecord.organization_id == handoff.organization_id,
            CommunicationRecord.provider == "openai_prospecting",
            CommunicationRecord.provider_message_id == provider_message_id,
        )
    )
    if existing is not None:
        return existing
    notes = validate_call_notes_payload_for_asset(raw_notes, lead.asset_class)
    now = datetime.now(UTC)
    communication = CommunicationRecord(
        organization_id=handoff.organization_id,
        conversation_id=conversation.id,
        lead_id=lead.id,
        contact_id=lead.contact_id,
        source_call_record_id=call.id,
        actor_user_id=attempt.caller_user_id,
        direction="internal",
        channel="note",
        status="logged",
        provider="openai_prospecting",
        provider_message_id=provider_message_id,
        subject="Prospecting call summary",
        body=format_approved_notes(notes, max_length=4000),
        occurred_at=(
            call.ended_at or call.answered_at or call.started_at or transcript.updated_at or now
        ),
        external_payload=None,
        communication_metadata={
            "source": "prospecting_call_intelligence",
            "attempt_id": str(attempt.id),
            "prospect_id": str(attempt.prospect_id),
            "handoff_id": str(handoff.id),
            "recording_id": str(recording.id),
            "transcript_id": str(transcript.id),
        },
    )
    db.add(communication)
    db.flush()
    conversation.last_activity_at = now
    db.add(
        ActivityEvent(
            organization_id=handoff.organization_id,
            actor_user_id=attempt.caller_user_id,
            entity_type="lead",
            entity_id=lead.id,
            event_type="prospecting.call_intelligence_linked",
            summary="Prospecting call notes and evidence were linked to the seller record.",
        )
    )
    return communication


def retry_call_transcript(
    db: Session,
    principal: Principal,
    transcript_id: UUID,
) -> CallTranscriptRead | None:
    """Queue a failed transcript again after an authorized human requests it."""

    transcript = db.scalar(
        select(CallTranscript)
        .where(
            CallTranscript.id == transcript_id,
            CallTranscript.organization_id == principal.organization_id,
        )
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    if transcript is None:
        return None
    recording = get_authorized_recording(db, principal, transcript.recording_id)
    if recording is None:
        return None
    if transcript.status not in {"failed", "exhausted"}:
        raise ValueError("Only a failed call transcript can be retried.")
    if bool((transcript.transcript_metadata or {}).get("permanent_failure")):
        raise ValueError("This call transcript has a permanent failure and cannot be retried.")
    eligibility = prospecting_transcript_eligibility(db, recording)
    if not eligibility.eligible:
        raise ValueError(f"This call transcript cannot be retried: {eligibility.reason}")
    if transcript.status not in {"failed", "exhausted"}:
        raise ValueError("Only a failed call transcript can be retried.")
    if bool((transcript.transcript_metadata or {}).get("permanent_failure")):
        raise ValueError("This call transcript has a permanent failure and cannot be retried.")
    previous_status = transcript.status
    previous_metadata = dict(transcript.transcript_metadata or {})
    previous_attempts = int(previous_metadata.get("attempts", 0))
    transcript.status = "queued"
    transcript.error_message = None
    transcript.transcript_metadata = {
        **previous_metadata,
        "attempts": 0,
        "next_retry_at": None,
        "exhausted_at": None,
        "manual_retry_count": int(previous_metadata.get("manual_retry_count", 0)) + 1,
        "manual_retry_requested_at": datetime.now(UTC).isoformat(),
        "previous_attempts": previous_attempts,
    }
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="human",
            action="call_transcript.retry",
            entity_type="call_transcript",
            entity_id=transcript.id,
            previous_value={"status": previous_status, "attempts": previous_attempts},
            new_value={"status": "queued", "attempts": 0},
            reason="Authorized user manually retried failed call intelligence.",
        )
    )
    db.commit()
    db.refresh(transcript)
    return transcript_to_read(db, transcript)


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
    lead = (
        lock_organization_lead(
            db,
            organization_id=principal.organization_id,
            lead_id=call.lead_id,
        )
        if call.lead_id is not None
        else None
    )
    if lead is None:
        raise ValueError("Lead is unavailable.")
    require_lead_open_for_work(lead)
    transcript = db.scalar(
        select(CallTranscript)
        .where(
            CallTranscript.id == transcript_id,
            CallTranscript.organization_id == principal.organization_id,
        )
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    if transcript is None:
        return None
    if transcript.status not in {"needs_review", "approved", "rejected"}:
        raise ValueError("Call notes are not ready for review.")
    if transcript.status in {"approved", "rejected"}:
        return transcript_to_read(db, transcript)
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
        apply_call_notes(
            db,
            transcript,
            call,
            lead,
            notes,
            actor_user_id=principal.user_id,
            human_approved=True,
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
        quick_read_summary=(build_quick_read_summary(notes) if notes is not None else None),
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
            description="Transcribes seller calls and posts evidence-backed internal CRM notes.",
            status="active",
            model_name=model_name,
            risk_level="medium",
            requires_human_approval=False,
        )
        db.add(agent)
        db.flush()
    elif agent.model_name != model_name:
        agent.model_name = model_name
    if agent.requires_human_approval:
        agent.requires_human_approval = False
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
    contact = db.get(Contact, call.contact_id) if call.contact_id is not None else None
    lead = db.get(Lead, call.lead_id) if call.lead_id is not None else None
    prospect = db.get(Prospect, call.prospect_id) if call.prospect_id is not None else None
    property_record = db.get(Property, lead.property_id) if lead else None
    segments = transcript.speaker_segments or []
    contact_name = (
        (contact.preferred_name or contact.legal_name)
        if contact
        else (prospect.legal_name if prospect is not None else "Unknown")
    )
    resolved_asset_class = normalize_asset_class(
        asset_class
        if asset_class is not None
        else (lead.asset_class if lead else (prospect.asset_class if prospect else None))
    )
    property_payload: dict[str, object] | None = (
        {
            "address": property_record.street_address,
            "city": property_record.city,
            "state": property_record.state,
        }
        if property_record
        else (
            {
                "address": prospect.street_address,
                "city": prospect.city,
                "state": prospect.state_code,
                "postal_code": prospect.postal_code,
            }
            if prospect is not None
            else None
        )
    )
    if property_payload is not None and resolved_asset_class == LAND_ASSET_CLASS:
        prospect_source = prospect.source_payload or {} if prospect is not None else {}
        property_payload = {
            **property_payload,
            "parcel_id": (
                property_record.parcel_id
                if property_record
                else (
                    prospect_source.get("parcel_id")
                    or prospect_source.get("apn")
                    or prospect_source.get("parcel_number")
                )
            ),
        }
    payload: dict[str, object] = {
        "party_type": "seller" if lead is not None or prospect is not None else "buyer",
        "seller": contact_name if lead is not None or prospect is not None else None,
        "buyer": contact_name if lead is None and prospect is None else None,
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


def render_call_transcript_text(transcript: CallTranscript) -> str:
    lines: list[str] = []
    for segment in transcript.speaker_segments or []:
        text = segment.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        speaker = str(segment.get("speaker") or "Speaker").strip() or "Speaker"
        start = numeric_value(segment.get("start"))
        lines.append(f"[{format_transcript_timestamp(start)}] {speaker}: {text.strip()}")
    if lines:
        return "\n\n".join(lines)
    return (transcript.transcript_text or "").strip()


def format_transcript_timestamp(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds_remaining = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds_remaining:02d}"
    return f"{minutes:02d}:{seconds_remaining:02d}"


def numeric_value(value: object) -> float:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def auto_approve_call_notes(
    db: Session,
    transcript: CallTranscript,
    call: CallRecord,
    lead: Lead,
    notes: CallNotes,
) -> None:
    now = datetime.now(UTC)
    previous_status = transcript.status
    transcript.status = "approved"
    transcript.approved_by_user_id = None
    transcript.approved_at = now
    transcript.transcript_metadata = {
        **(transcript.transcript_metadata or {}),
        "human_review_required": False,
        "note_posting_mode": "automatic",
        "auto_approved_at": now.isoformat(),
        "review_decision_notes": None,
    }
    apply_call_notes(
        db,
        transcript,
        call,
        lead,
        notes,
        actor_user_id=call.actor_user_id,
        human_approved=False,
        apply_field_updates=[],
        create_follow_up_task=False,
    )
    cancel_legacy_call_note_approval(db, transcript)
    db.add(
        ActivityEvent(
            organization_id=lead.organization_id,
            actor_user_id=None,
            entity_type="lead",
            entity_id=lead.id,
            event_type="call_notes.auto_posted",
            summary="AI call summary was automatically added to the seller record.",
        )
    )
    db.add(
        AuditEvent(
            organization_id=lead.organization_id,
            actor_user_id=None,
            actor_type="ai",
            action="call_notes.auto_post",
            entity_type="call_transcript",
            entity_id=transcript.id,
            previous_value={"status": previous_status},
            new_value={
                "status": "approved",
                "note_posting_mode": "automatic",
                "crm_fields_auto_populated": list(
                    (transcript.transcript_metadata or {}).get("crm_auto_populated_values") or {}
                ),
            },
            reason="Transcript-grounded internal call notes are configured for automatic posting.",
        )
    )


def cancel_legacy_call_note_approval(db: Session, transcript: CallTranscript) -> None:
    approval = get_call_notes_approval(db, transcript)
    if approval is None or approval.status != "pending":
        return
    approval.status = "cancelled"
    approval.decision_notes = "Call summaries now post automatically without an approval step."
    approval.decided_at = datetime.now(UTC)


def complete_auto_call_note_run(
    db: Session,
    transcript: CallTranscript,
    summary: str,
) -> None:
    raw_run_id = (transcript.transcript_metadata or {}).get("ai_run_id")
    if not isinstance(raw_run_id, str):
        return
    try:
        run_id = UUID(raw_run_id)
    except ValueError:
        return
    run = db.get(AiRunLog, run_id)
    if run is None:
        return
    run.status = "completed"
    run.run_metadata = {
        **(run.run_metadata or {}),
        "note_posting_mode": "automatic",
        "human_review_required": False,
    }
    if run.orchestrator_event_id is not None:
        mark_call_intelligence_ai_work(
            db,
            event_id=run.orchestrator_event_id,
            status="completed",
            run_id=run.id,
            summary=summary,
        )


def apply_call_notes(
    db: Session,
    transcript: CallTranscript,
    call: CallRecord,
    lead: Lead,
    notes: CallNotes,
    *,
    actor_user_id: UUID | None,
    human_approved: bool,
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
            organization_id=transcript.organization_id,
            conversation_id=call.conversation_id,
            lead_id=call.lead_id,
            contact_id=call.contact_id,
            actor_user_id=actor_user_id,
            direction="internal",
            channel="note",
            status="logged",
            provider="openai_reviewed",
            provider_message_id=f"call-notes:{transcript.id}",
            subject="Call summary" if not human_approved else "Approved call summary",
            body=format_approved_notes(notes, max_length=4000),
            occurred_at=datetime.now(UTC),
            external_payload=None,
            communication_metadata={
                "call_transcript_id": str(transcript.id),
                "human_approved": human_approved,
                "automatically_posted": not human_approved,
            },
        )
    )
    if create_follow_up_task and notes.next_action:
        follow_up_at = parse_follow_up_at(notes.follow_up_at)
        db.add(
            Task(
                organization_id=transcript.organization_id,
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
        evidence.field == field and evidence.supporting_text.strip() for evidence in notes.evidence
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


def format_approved_notes(notes: CallNotes, *, max_length: int | None = None) -> str:
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
    quick_read = build_quick_read_summary(notes)
    if quick_read:
        lines.extend(("", "Quick read:", quick_read))
    formatted = "\n".join(lines)
    if max_length is None or len(formatted) <= max_length or not quick_read:
        return formatted
    quick_read_footer = f"\n\nQuick read:\n{quick_read}"
    detail_limit = max_length - len(quick_read_footer)
    if detail_limit <= 3:
        return quick_read_footer[-max_length:]
    detail_text = "\n".join(lines[:-3])
    shortened_details = detail_text[: detail_limit - 3].rsplit(" ", 1)[0].rstrip()
    return f"{shortened_details or detail_text[: detail_limit - 3]}...{quick_read_footer}"


_CJK_CHARACTER_PATTERN = re.compile(
    "[\u3040-\u30ff\u31f0-\u31ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uf900-\ufaff]"
)


def reject_unexpected_cjk_call_notes(notes: CallNotes) -> None:
    """Prevent a malformed English model response from reaching CRM storage."""

    # Evidence can legitimately quote a seller's name or words in another script. Guard the
    # generated CRM prose, while preserving exact transcript evidence for multilingual calls.
    for value in iter_note_strings(notes.model_dump(mode="json", exclude={"evidence"})):
        if _CJK_CHARACTER_PATTERN.search(value):
            raise CallIntelligenceError(
                "Generated call notes contained unexpected non-English characters. "
                "The response was rejected and will be retried."
            )


def iter_note_strings(value: object) -> Iterator[str]:
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, dict):
        for item in value.values():
            yield from iter_note_strings(item)
        return
    if isinstance(value, list | tuple):
        for item in value:
            yield from iter_note_strings(item)


def build_quick_read_summary(notes: CallNotes) -> str:
    """Build a stable, compact scan view without another AI request."""

    parts: list[str] = []
    motivation = quick_read_value(notes.motivation, max_length=170)
    if motivation:
        parts.append(f"Why: {motivation}")

    asking_price = quick_read_value(notes.asking_price, max_length=90)
    mortgage_balance = quick_read_value(notes.mortgage_balance, max_length=90)
    numbers = []
    if asking_price:
        numbers.append(f"asking {asking_price}")
    if mortgage_balance:
        numbers.append(f"payoff {mortgage_balance}")
    if numbers:
        parts.append(f"Numbers: {'; '.join(numbers)}")

    timeline = quick_read_value(notes.timeline, max_length=130)
    if timeline:
        parts.append(f"Timing: {timeline}")

    next_action = quick_read_value(notes.next_action, max_length=190)
    if next_action:
        parts.append(f"Next: {next_action}")

    if not parts:
        summary = quick_read_value(notes.summary, max_length=360)
        return summary or ""
    return "\n".join(parts)


def quick_read_value(value: str | None, *, max_length: int) -> str | None:
    if not value or _CJK_CHARACTER_PATTERN.search(value):
        return None
    normalized = " ".join(value.split())
    if len(normalized) <= max_length:
        return normalized
    shortened = normalized[: max_length - 3].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return f"{shortened or normalized[: max_length - 3]}..."


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
