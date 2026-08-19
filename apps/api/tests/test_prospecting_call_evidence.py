from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.rbac import PermissionKeys
from app.integrations.openai_client import OpenAIAudioTranscript
from app.integrations.twilio_recordings import (
    TwilioRecordingError,
    TwilioRecordingMedia,
)
from app.main import app
from app.models.foundation import (
    ActivityEvent,
    AuditEvent,
    CallRecord,
    CallRecording,
    CallTranscript,
    Campaign,
    CommunicationRecord,
    Contact,
    Conversation,
    ConversationWatcher,
    EmailSenderAlias,
    EmailSenderGrant,
    Lead,
    Permission,
    Property,
    Prospect,
    ProspectCallingBatchEntry,
    ProspectHandoff,
    ProspectingAttempt,
    ProspectingDialLeg,
    ProspectingProviderEvent,
    ProspectingQualificationResponse,
    ProspectingScriptVersion,
    Role,
    RoleAssignment,
    RolePermission,
    Team,
    TeamMembership,
    User,
)
from app.services.bootstrap import bootstrap_foundation
from app.services.call_intelligence import (
    apply_prospecting_transcript_suggestions,
    build_call_notes_prompt,
    call_notes_system_prompt,
    enqueue_eligible_prospecting_call_transcript,
    link_accepted_prospecting_evidence_for_attempt,
    process_call_transcript,
    process_next_call_transcript,
    prospecting_transcript_eligibility,
    validate_call_notes_payload_for_asset,
)
from app.services.prospecting_evidence import prospecting_evidence_status
from tests.test_prospecting_voice import ColdCallGraph, seed_cold_call_graph
from tests.test_twilio_voice import create_call_assets


@dataclass(frozen=True)
class ProspectingEvidenceGraph:
    cold_call: ColdCallGraph
    call: CallRecord
    recording: CallRecording


@dataclass(frozen=True)
class AcceptedHandoffGraph:
    handoff: ProspectHandoff
    lead: Lead
    conversation: Conversation


def seed_eligible_recording(
    db: Session,
    client: TestClient,
    *,
    asset_class: str = "house",
    duration_seconds: int = 95,
) -> ProspectingEvidenceGraph:
    graph = seed_cold_call_graph(db, client)
    now = datetime.now(UTC)
    provider_call_id = f"CA-d7-{uuid4().hex}"
    provider_recording_id = f"RE-d7-{uuid4().hex}"
    graph.prospect.asset_class = asset_class
    campaign = db.get(Campaign, graph.prospect.campaign_id)
    script = db.get(ProspectingScriptVersion, graph.attempt.script_version_id)
    assert campaign is not None
    assert script is not None
    campaign.asset_class = asset_class
    script.asset_class = asset_class
    script.qualification_questions = [
        {
            "key": "motivation",
            "label": "Motivation",
            "prompt": "Why are you considering selling?",
            "answer_type": "text",
            "choices": [],
            "required_for_handoff": True,
        },
        {
            "key": "timeline",
            "label": "Timeline",
            "prompt": "When would you like to sell?",
            "answer_type": "text",
            "choices": [],
            "required_for_handoff": True,
        },
        {
            "key": "property_condition",
            "label": "Condition",
            "prompt": "What condition is the property in?",
            "answer_type": "text",
            "choices": [],
            "required_for_handoff": False,
        },
        {
            "key": "parcel_id",
            "label": "Parcel ID",
            "prompt": "What is the parcel ID?",
            "answer_type": "text",
            "choices": [],
            "required_for_handoff": asset_class == "land",
        },
        {
            "key": "acreage",
            "label": "Acreage",
            "prompt": "How many acres are included?",
            "answer_type": "text",
            "choices": [],
            "required_for_handoff": asset_class == "land",
        },
    ]
    if asset_class == "land":
        graph.prospect.source_payload = {
            **(graph.prospect.source_payload or {}),
            "parcel_id": "APN-D7-100",
            "county": "Fulton",
        }

    call = CallRecord(
        organization_id=graph.organization.id,
        conversation_id=None,
        lead_id=None,
        contact_id=None,
        prospect_id=graph.prospect.id,
        prospecting_attempt_id=graph.attempt.id,
        prospecting_dial_leg_id=graph.leg.id,
        actor_user_id=graph.caller.id,
        communication_record_id=None,
        voice_line_id=graph.line.id,
        call_intent_id=None,
        provider="twilio",
        provider_call_id=provider_call_id,
        child_provider_call_id=None,
        direction="outbound",
        status="completed",
        from_number=graph.line.phone_number,
        to_number=graph.prospect.normalized_phone,
        started_at=now,
        answered_at=now,
        ended_at=now,
        duration_seconds=duration_seconds,
        disposition="interested",
        recording_consent_status="disclosed",
        call_metadata={"context": "prospecting"},
    )
    db.add(call)
    db.flush()

    graph.attempt.call_record_id = call.id
    graph.attempt.provider = "twilio"
    graph.attempt.provider_call_id = provider_call_id
    graph.attempt.provider_recording_id = provider_recording_id
    graph.attempt.status = "completed"
    graph.attempt.outcome = "interested"
    graph.attempt.contact_made = True
    graph.attempt.answer_classification = "human"
    graph.attempt.party_classification = "right_party"
    graph.attempt.interest_classification = "interested"
    graph.attempt.follow_up_permission = "granted"
    graph.attempt.answered_at = now
    graph.attempt.completed_at = now

    graph.leg.call_record_id = call.id
    graph.leg.provider_call_id = provider_call_id
    graph.leg.provider_recording_id = provider_recording_id
    graph.leg.status = "completed"
    graph.leg.answer_classification = "human"
    graph.leg.party_classification = "right_party"
    graph.leg.connected_at = now
    graph.leg.completed_at = now

    recording = CallRecording(
        organization_id=graph.organization.id,
        call_record_id=call.id,
        provider="twilio",
        provider_recording_id=provider_recording_id,
        status="completed",
        media_reference=f"twilio://recordings/{provider_recording_id}",
        duration_seconds=duration_seconds,
        channel_count=2,
        consent_status="disclosed",
        recorded_at=now,
        retention_expires_at=None,
        deleted_at=None,
        deleted_by_user_id=None,
        deletion_reason=None,
        recording_metadata={"context": "prospecting"},
    )
    provider_event = ProspectingProviderEvent(
        organization_id=graph.organization.id,
        provider_campaign_sync_id=None,
        provider_contact_sync_id=None,
        batch_entry_id=graph.entry.id,
        attempt_id=graph.attempt.id,
        dial_session_id=graph.session.id,
        dial_leg_id=graph.leg.id,
        provider="twilio",
        external_event_id=f"voice:recording:{provider_recording_id}:completed",
        event_type="recording.completed",
        processing_status="processed",
        provider_call_id=provider_call_id,
        provider_recording_id=provider_recording_id,
        provider_sequence_number=None,
        occurred_at=now,
        signature_verified=True,
        signature_fingerprint="a" * 64,
        payload_sha256="b" * 64,
        payload={
            "RecordingSid": provider_recording_id,
            "RecordingStatus": "completed",
        },
        retry_count=0,
        error_message=None,
        received_at=now,
        processed_at=now,
    )
    db.add_all([recording, provider_event])
    db.commit()
    return ProspectingEvidenceGraph(
        cold_call=graph,
        call=call,
        recording=recording,
    )


def seed_handoff_context(
    db: Session,
    evidence: ProspectingEvidenceGraph,
    *,
    status: str,
    assigned_user_id: UUID | None = None,
) -> AcceptedHandoffGraph:
    graph = evidence.cold_call
    now = datetime.now(UTC)
    assignee_id = assigned_user_id or graph.owner.id
    contact = Contact(
        organization_id=graph.organization.id,
        legal_name=graph.prospect.legal_name,
        preferred_name=None,
        contact_type="seller",
        assigned_user_id=assignee_id,
    )
    property_record = Property(
        organization_id=graph.organization.id,
        street_address=graph.prospect.street_address or "101 Evidence Way",
        city=graph.prospect.city or "Atlanta",
        state=graph.prospect.state_code or "GA",
        postal_code=graph.prospect.postal_code or "30303",
        county="Fulton",
        property_type="land" if graph.prospect.asset_class == "land" else "single_family",
        parcel_id=(
            str((graph.prospect.source_payload or {}).get("parcel_id"))
            if graph.prospect.asset_class == "land"
            else None
        ),
        normalized_parcel_key=None,
        normalized_address_key=None,
    )
    db.add_all([contact, property_record])
    db.flush()
    lead = Lead(
        organization_id=graph.organization.id,
        contact_id=contact.id,
        property_id=property_record.id,
        assigned_user_id=assignee_id,
        source="cold_call",
        asset_class=graph.prospect.asset_class,
        qualification_context={},
        stage_key="qualified",
        lead_temperature="warm",
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
    conversation = Conversation(
        organization_id=graph.organization.id,
        conversation_type="lead",
        lead_id=lead.id,
        contact_id=contact.id,
        assigned_user_id=assignee_id,
        assigned_team_id=None,
        source_alias_id=None,
        visibility_scope="standard",
        status="open",
        queue_key="qualified",
        priority="normal",
        unread_count=0,
        last_activity_at=now,
        last_inbound_at=None,
        last_outbound_at=None,
        closed_at=None,
        conversation_metadata={"source": "prospect_handoff"},
    )
    handoff = ProspectHandoff(
        organization_id=graph.organization.id,
        prospect_id=graph.prospect.id,
        attempt_id=graph.attempt.id,
        lead_id=lead.id,
        assigned_user_id=assignee_id,
        submitted_by_user_id=graph.caller.id,
        reviewed_by_user_id=graph.owner.id if status == "accepted" else None,
        status=status,
        submitted_at=now,
        reviewed_at=now if status == "accepted" else None,
        decision_code="accepted_interested" if status == "accepted" else None,
        review_reason=None,
    )
    graph.prospect.converted_lead_id = lead.id
    db.add_all([conversation, handoff])
    db.commit()
    return AcceptedHandoffGraph(handoff=handoff, lead=lead, conversation=conversation)


def seed_earlier_wrong_party_recordings(
    db: Session,
    evidence: ProspectingEvidenceGraph,
    *,
    count: int,
) -> None:
    graph = evidence.cold_call
    base_time = datetime.now(UTC) - timedelta(days=2)
    for index in range(count):
        occurred_at = base_time + timedelta(seconds=index)
        provider_call_id = f"CA-d7-wrong-party-{index:04d}"
        provider_recording_id = f"RE-d7-wrong-party-{index:04d}"
        phone = f"+1470555{index:04d}"
        prospect = Prospect(
            organization_id=graph.organization.id,
            campaign_id=graph.prospect.campaign_id,
            assigned_user_id=graph.caller.id,
            source_record_key=f"d7-wrong-party-{index:04d}",
            status="completed",
            legal_name=f"D7 Wrong Party {index:04d}",
            phone=phone,
            normalized_phone=phone,
            street_address=f"{index + 200} Wrong Party Way",
            city="Atlanta",
            state_code="GA",
            postal_code="30303",
            suppression_status="clear",
            phone_validation_status="verified",
            call_eligibility="eligible",
            source_payload={},
        )
        db.add(prospect)
        db.flush()
        entry = ProspectCallingBatchEntry(
            organization_id=graph.organization.id,
            prospect_calling_batch_id=graph.batch.id,
            prospect_id=prospect.id,
            assigned_user_id=graph.caller.id,
            sequence_number=index + 1000,
            status="completed",
            attempt_count=1,
            disposition="interested",
            last_attempt_at=occurred_at,
            completed_at=occurred_at,
        )
        db.add(entry)
        db.flush()
        attempt = ProspectingAttempt(
            organization_id=graph.organization.id,
            batch_entry_id=entry.id,
            prospect_id=prospect.id,
            caller_user_id=graph.caller.id,
            script_version_id=graph.attempt.script_version_id,
            call_record_id=None,
            provider="twilio",
            provider_call_id=provider_call_id,
            provider_recording_id=provider_recording_id,
            cohort_id=graph.session.cohort_id,
            status="completed",
            outcome="interested",
            contact_made=True,
            answer_classification="human",
            party_classification="wrong_party",
            interest_classification="interested",
            follow_up_permission="not_recorded",
            classification_source="provider_plus_manual_outcome",
            measurement_metadata={},
            qualification_answers={},
            started_at=occurred_at,
            answered_at=occurred_at,
            completed_at=occurred_at,
        )
        db.add(attempt)
        db.flush()
        leg = ProspectingDialLeg(
            organization_id=graph.organization.id,
            dial_session_id=graph.session.id,
            prospect_id=prospect.id,
            batch_entry_id=entry.id,
            attempt_id=attempt.id,
            voice_line_id=graph.line.id,
            call_record_id=None,
            line_slot=1,
            recipient=phone,
            provider="twilio",
            provider_call_id=provider_call_id,
            provider_recording_id=provider_recording_id,
            idempotency_key=f"d7-wrong-party-leg-{index:04d}",
            status="completed",
            last_provider_event_sequence=0,
            queued_at=occurred_at,
            answered_at=occurred_at,
            connected_at=occurred_at,
            completed_at=occurred_at,
            answer_classification="human",
            party_classification="wrong_party",
            terminal_result="completed",
            leg_metadata={},
        )
        db.add(leg)
        db.flush()
        call = CallRecord(
            organization_id=graph.organization.id,
            conversation_id=None,
            lead_id=None,
            contact_id=None,
            prospect_id=prospect.id,
            prospecting_attempt_id=attempt.id,
            prospecting_dial_leg_id=leg.id,
            actor_user_id=graph.caller.id,
            communication_record_id=None,
            voice_line_id=graph.line.id,
            call_intent_id=None,
            provider="twilio",
            provider_call_id=provider_call_id,
            child_provider_call_id=None,
            direction="outbound",
            status="completed",
            from_number=graph.line.phone_number,
            to_number=phone,
            started_at=occurred_at,
            answered_at=occurred_at,
            ended_at=occurred_at,
            duration_seconds=15,
            disposition="interested",
            recording_consent_status="disclosed",
            call_metadata={"context": "prospecting"},
        )
        db.add(call)
        db.flush()
        attempt.call_record_id = call.id
        leg.call_record_id = call.id
        recording = CallRecording(
            organization_id=graph.organization.id,
            call_record_id=call.id,
            provider="twilio",
            provider_recording_id=provider_recording_id,
            status="completed",
            media_reference=f"twilio://recordings/{provider_recording_id}",
            duration_seconds=15,
            channel_count=2,
            consent_status="disclosed",
            recorded_at=occurred_at,
            retention_expires_at=None,
            deleted_at=None,
            deleted_by_user_id=None,
            deletion_reason=None,
            recording_metadata={"context": "prospecting"},
            created_at=occurred_at,
            updated_at=occurred_at,
        )
        event = ProspectingProviderEvent(
            organization_id=graph.organization.id,
            provider_campaign_sync_id=None,
            provider_contact_sync_id=None,
            batch_entry_id=entry.id,
            attempt_id=attempt.id,
            dial_session_id=graph.session.id,
            dial_leg_id=leg.id,
            provider="twilio",
            external_event_id=f"voice:recording:{provider_recording_id}:completed",
            event_type="recording.completed",
            processing_status="processed",
            provider_call_id=provider_call_id,
            provider_recording_id=provider_recording_id,
            provider_sequence_number=None,
            occurred_at=occurred_at,
            signature_verified=True,
            signature_fingerprint="c" * 64,
            payload_sha256="d" * 64,
            payload={
                "RecordingSid": provider_recording_id,
                "RecordingStatus": "completed",
            },
            retry_count=0,
            error_message=None,
            received_at=occurred_at,
            processed_at=occurred_at,
        )
        db.add_all([recording, event])
        db.flush()
    evidence.recording.created_at = datetime.now(UTC)
    db.commit()


def house_notes_payload() -> dict[str, object]:
    return {
        "summary": "Seller is relocating and wants to sell within 30 days.",
        "motivation": "Relocating",
        "timeline": "Within 30 days",
        "property_condition": None,
        "occupancy_status": None,
        "asking_price": None,
        "mortgage_balance": None,
        "mortgage_or_title": None,
        "repairs": [],
        "objections": [],
        "commitments": [],
        "next_action": "Acquisitions should follow up.",
        "follow_up_at": None,
        "appointment_details": None,
        "confidence": 93,
        "evidence": [
            {
                "field": "timeline",
                "segment_index": 0,
                "start_seconds": 10.0,
                "supporting_text": "Seller wants to sell within 30 days.",
            }
        ],
    }


def complete_transcript_notes(transcript: CallTranscript) -> None:
    transcript.status = "completed"
    transcript.language = "en"
    transcript.transcript_text = "Seller is relocating and wants to sell within 30 days."
    transcript.speaker_segments = [
        {
            "index": 0,
            "speaker": "Seller",
            "start": 10.0,
            "end": 18.0,
            "text": "I am relocating and want to sell within 30 days.",
        }
    ]
    transcript.confidence_score = 93
    transcript.transcript_metadata = {
        **(transcript.transcript_metadata or {}),
        "quick_read_summary": "Why: Relocating\nTiming: Within 30 days",
        "structured_notes": house_notes_payload(),
    }


def test_cold_recording_waits_for_wrap_up_then_queues_exactly_once(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    evidence = seed_eligible_recording(db_session, client)
    attempt = evidence.cold_call.attempt
    provider_event = db_session.scalar(
        select(ProspectingProviderEvent).where(
            ProspectingProviderEvent.attempt_id == attempt.id,
            ProspectingProviderEvent.event_type == "recording.completed",
        )
    )
    assert provider_event is not None

    evidence.recording.status = "in-progress"
    db_session.commit()
    recording_pending = prospecting_transcript_eligibility(db_session, evidence.recording)
    assert recording_pending.state == "pending"
    assert "still being processed" in recording_pending.reason
    assert (
        enqueue_eligible_prospecting_call_transcript(
            db_session,
            evidence.recording,
            model_name="gpt-4o-transcribe-diarize",
        )
        is None
    )

    evidence.recording.status = "completed"
    provider_event.signature_verified = False
    db_session.commit()
    unverified = prospecting_transcript_eligibility(db_session, evidence.recording)
    assert unverified.state == "invalid"
    assert "verified provider recording callback" in unverified.reason
    assert (
        enqueue_eligible_prospecting_call_transcript(
            db_session,
            evidence.recording,
            model_name="gpt-4o-transcribe-diarize",
        )
        is None
    )

    provider_event.signature_verified = True
    attempt.status = "in_progress"
    attempt.completed_at = None
    db_session.commit()
    pending = prospecting_transcript_eligibility(db_session, evidence.recording)
    assert pending.state == "pending"
    assert (
        enqueue_eligible_prospecting_call_transcript(
            db_session,
            evidence.recording,
            model_name="gpt-4o-transcribe-diarize",
        )
        is None
    )

    attempt.status = "completed"
    attempt.completed_at = datetime.now(UTC)
    db_session.commit()
    eligible = prospecting_transcript_eligibility(db_session, evidence.recording)
    assert eligible.state == "eligible"

    first = enqueue_eligible_prospecting_call_transcript(
        db_session,
        evidence.recording,
        model_name="gpt-4o-transcribe-diarize",
    )
    replay = enqueue_eligible_prospecting_call_transcript(
        db_session,
        evidence.recording,
        model_name="gpt-4o-transcribe-diarize",
    )

    assert first is not None
    assert replay is not None
    assert replay.id == first.id
    assert db_session.scalar(select(func.count(CallTranscript.id))) == 1


@pytest.mark.parametrize(
    ("asset_class", "expected_parcel_id"),
    [("house", None), ("land", "APN-D7-100")],
)
def test_call_notes_prompt_uses_cold_prospect_house_or_land_context(
    db_session: Session,
    api_db_override: None,
    asset_class: str,
    expected_parcel_id: str | None,
) -> None:
    client = TestClient(app)
    evidence = seed_eligible_recording(db_session, client, asset_class=asset_class)
    transcript = enqueue_eligible_prospecting_call_transcript(
        db_session,
        evidence.recording,
        model_name="gpt-4o-transcribe-diarize",
    )
    assert transcript is not None
    transcript.transcript_text = "The seller described the property and timing."
    transcript.speaker_segments = [
        {
            "index": 0,
            "speaker": "Seller",
            "start": 12.0,
            "end": 18.0,
            "text": "I would like to sell within 30 days.",
        }
    ]

    payload = json.loads(
        build_call_notes_prompt(
            db_session,
            evidence.call,
            transcript,
            asset_class=asset_class,
        )
    )

    assert payload["party_type"] == "seller"
    assert payload["seller"] == evidence.cold_call.prospect.legal_name
    assert payload["buyer"] is None
    assert payload["property"]["address"] == evidence.cold_call.prospect.street_address
    assert payload["property"]["postal_code"] == evidence.cold_call.prospect.postal_code
    if asset_class == "land":
        assert payload["asset_class"] == "land"
        assert payload["property"]["parcel_id"] == expected_parcel_id
        assert "vacant land" in call_notes_system_prompt("Base prompt", asset_class)
    else:
        assert "asset_class" not in payload
        assert "vacant land" not in call_notes_system_prompt("Base prompt", asset_class)


@pytest.mark.parametrize(
    ("asset_class", "question_key", "human_value", "suggested_value"),
    [
        ("house", "timeline", "Within 90 days", "Within 30 days"),
        ("land", "acreage", "10 acres", "12 acres"),
    ],
)
def test_transcript_suggestions_flag_house_or_land_conflicts_without_overwriting_humans(
    db_session: Session,
    api_db_override: None,
    asset_class: str,
    question_key: str,
    human_value: str,
    suggested_value: str,
) -> None:
    client = TestClient(app)
    evidence = seed_eligible_recording(db_session, client, asset_class=asset_class)
    transcript = enqueue_eligible_prospecting_call_transcript(
        db_session,
        evidence.recording,
        model_name="gpt-4o-transcribe-diarize",
    )
    assert transcript is not None
    attempt = evidence.cold_call.attempt
    attempt.qualification_answers = {
        question_key: human_value,
        "motivation": "Inherited property",
    }
    response = ProspectingQualificationResponse(
        organization_id=evidence.cold_call.organization.id,
        attempt_id=attempt.id,
        script_version_id=attempt.script_version_id,
        question_key=question_key,
        state="answered",
        answer_value=human_value,
        source="va_entry",
        actor_user_id=evidence.cold_call.caller.id,
        is_required=True,
        captured_at=datetime.now(UTC),
        transcript_evidence=None,
        response_metadata={"revision": 4, "mutation_id": "human-save"},
    )
    db_session.add(response)
    db_session.flush()
    notes_payload: dict[str, object] = {
        "summary": "The seller discussed motivation and qualification facts.",
        "motivation": "Relocating for work",
        "timeline": suggested_value if question_key == "timeline" else None,
        "property_condition": None,
        "occupancy_status": None,
        "asking_price": None,
        "mortgage_balance": None,
        "mortgage_or_title": None,
        "repairs": [],
        "objections": [],
        "commitments": [],
        "next_action": "Caller should verify the conflicting answer.",
        "follow_up_at": None,
        "appointment_details": None,
        "confidence": 91,
        "evidence": [
            {
                "field": "motivation",
                "segment_index": 0,
                "start_seconds": 8.0,
                "supporting_text": "Seller said they are relocating for work.",
            },
            {
                "field": question_key,
                "segment_index": 1,
                "start_seconds": 22.0,
                "supporting_text": f"Seller stated {suggested_value}.",
            },
        ],
    }
    if asset_class == "land":
        notes_payload.update(
            {
                "parcel_id": None,
                "acreage": suggested_value,
                "legal_description": None,
                "access_or_frontage": None,
                "utilities": None,
                "zoning_or_use": None,
                "septic_or_perc": None,
                "taxes_or_hoa": None,
                "terrain_or_environmental_concerns": None,
            }
        )
    notes = validate_call_notes_payload_for_asset(notes_payload, asset_class)

    suggestions = apply_prospecting_transcript_suggestions(
        db_session,
        transcript=transcript,
        attempt=attempt,
        notes=notes,
    )
    db_session.flush()

    conflict = next(item for item in suggestions if item["question_key"] == question_key)
    assert conflict == {
        "question_key": question_key,
        "state": "conflict",
        "current_value": human_value,
        "suggested_value": suggested_value,
        "evidence": [notes_payload["evidence"][1]],
    }
    db_session.refresh(response)
    db_session.refresh(attempt)
    assert response.answer_value == human_value
    assert response.source == "va_entry"
    assert response.state == "conflict"
    assert response.response_metadata["revision"] == 4
    assert response.response_metadata["mutation_id"] == "human-save"
    assert response.response_metadata["ai_suggestion"]["state"] == "conflict"
    assert response.response_metadata["ai_suggestion"]["value"] == suggested_value
    assert response.transcript_evidence == {"items": [notes_payload["evidence"][1]]}
    assert attempt.qualification_answers[question_key] == human_value

    motivation = db_session.scalar(
        select(ProspectingQualificationResponse).where(
            ProspectingQualificationResponse.attempt_id == attempt.id,
            ProspectingQualificationResponse.question_key == "motivation",
        )
    )
    assert motivation is not None
    assert motivation.source == "legacy_completion"
    assert motivation.state == "conflict"
    assert motivation.answer_value == "Inherited property"
    assert motivation.response_metadata["ai_suggestion"]["state"] == "conflict"
    assert motivation.response_metadata["ai_suggestion"]["value"] == "Relocating for work"


@pytest.mark.parametrize(
    ("human_value", "suggested_value", "expected_state"),
    [
        ("Within 30 days", "  within   30 DAYS ", "corroborated"),
        ("Within 90 days", "Within 30 days", "conflict"),
    ],
)
def test_legacy_attempt_answer_is_materialized_before_ai_suggestion_comparison(
    db_session: Session,
    api_db_override: None,
    human_value: str,
    suggested_value: str,
    expected_state: str,
) -> None:
    client = TestClient(app)
    evidence = seed_eligible_recording(db_session, client)
    transcript = enqueue_eligible_prospecting_call_transcript(
        db_session,
        evidence.recording,
        model_name="gpt-4o-transcribe-diarize",
    )
    assert transcript is not None
    attempt = evidence.cold_call.attempt
    attempt.qualification_answers = {"timeline": human_value}
    db_session.commit()
    notes_payload = {
        **house_notes_payload(),
        "timeline": suggested_value,
        "evidence": [
            {
                "field": "timeline",
                "segment_index": 0,
                "start_seconds": 10.0,
                "supporting_text": f"Seller stated {suggested_value.strip()}.",
            }
        ],
    }
    notes = validate_call_notes_payload_for_asset(notes_payload, "house")

    suggestions = apply_prospecting_transcript_suggestions(
        db_session,
        transcript=transcript,
        attempt=attempt,
        notes=notes,
    )
    db_session.flush()

    timeline = next(item for item in suggestions if item["question_key"] == "timeline")
    assert timeline["state"] == expected_state
    assert timeline["current_value"] == human_value
    assert timeline["suggested_value"] == suggested_value
    response = db_session.scalar(
        select(ProspectingQualificationResponse).where(
            ProspectingQualificationResponse.attempt_id == attempt.id,
            ProspectingQualificationResponse.question_key == "timeline",
        )
    )
    assert response is not None
    assert response.answer_value == human_value
    assert response.source == "legacy_completion"
    assert response.state == ("conflict" if expected_state == "conflict" else "answered")
    assert response.response_metadata["ai_suggestion"]["state"] == expected_state
    db_session.refresh(attempt)
    assert attempt.qualification_answers == {"timeline": human_value}


@pytest.mark.parametrize("ready_first", [True, False], ids=["transcript-first", "handoff-first"])
def test_accepted_handoff_links_call_evidence_once_in_either_race_order(
    db_session: Session,
    api_db_override: None,
    ready_first: bool,
) -> None:
    client = TestClient(app)
    evidence = seed_eligible_recording(db_session, client)
    transcript = enqueue_eligible_prospecting_call_transcript(
        db_session,
        evidence.recording,
        model_name="gpt-4o-transcribe-diarize",
    )
    assert transcript is not None
    handoff_graph = seed_handoff_context(
        db_session,
        evidence,
        status="pending" if ready_first else "accepted",
    )

    if ready_first:
        complete_transcript_notes(transcript)
        db_session.commit()
        assert (
            link_accepted_prospecting_evidence_for_attempt(
                db_session,
                evidence.cold_call.attempt.id,
            )
            is None
        )
        handoff_graph.handoff.status = "accepted"
        handoff_graph.handoff.reviewed_by_user_id = evidence.cold_call.owner.id
        handoff_graph.handoff.reviewed_at = datetime.now(UTC)
        handoff_graph.handoff.decision_code = "accepted_interested"
    else:
        assert (
            link_accepted_prospecting_evidence_for_attempt(
                db_session,
                evidence.cold_call.attempt.id,
            )
            is None
        )
        complete_transcript_notes(transcript)
    db_session.flush()

    linked = link_accepted_prospecting_evidence_for_attempt(
        db_session,
        evidence.cold_call.attempt.id,
    )
    replay = link_accepted_prospecting_evidence_for_attempt(
        db_session,
        evidence.cold_call.attempt.id,
    )
    db_session.flush()

    assert linked is not None
    assert replay is not None
    assert replay.id == linked.id
    assert linked.organization_id == evidence.cold_call.organization.id
    assert linked.conversation_id == handoff_graph.conversation.id
    assert linked.lead_id == handoff_graph.lead.id
    assert linked.contact_id == handoff_graph.lead.contact_id
    assert linked.source_call_record_id == evidence.call.id
    assert linked.provider == "openai_prospecting"
    assert linked.provider_message_id == f"prospecting-call-notes:{transcript.id}"
    assert linked.communication_metadata == {
        "source": "prospecting_call_intelligence",
        "attempt_id": str(evidence.cold_call.attempt.id),
        "prospect_id": str(evidence.cold_call.prospect.id),
        "handoff_id": str(handoff_graph.handoff.id),
        "recording_id": str(evidence.recording.id),
        "transcript_id": str(transcript.id),
    }
    assert (
        db_session.scalar(
            select(func.count(CommunicationRecord.id)).where(
                CommunicationRecord.provider == "openai_prospecting"
            )
        )
        == 1
    )
    assert (
        db_session.scalar(
            select(func.count(ActivityEvent.id)).where(
                ActivityEvent.event_type == "prospecting.call_intelligence_linked"
            )
        )
        == 1
    )


def test_call_evidence_is_available_to_assigned_caller_and_manager_but_not_other_scopes(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    evidence = seed_eligible_recording(db_session, client)
    transcript = enqueue_eligible_prospecting_call_transcript(
        db_session,
        evidence.recording,
        model_name="gpt-4o-transcribe-diarize",
    )
    assert transcript is not None
    complete_transcript_notes(transcript)
    other_foundation = bootstrap_foundation(
        db_session,
        organization_name="D7 Other Workspace",
        admin_email="d7-other-owner@example.com",
        admin_name="D7 Other Owner",
    )
    assert other_foundation.admin_user is not None
    db_session.commit()
    monkeypatch.setattr(
        "app.routers.voice.download_twilio_recording",
        lambda *_args: TwilioRecordingMedia(b"ID3-d7-private-audio", "audio/mpeg"),
    )
    caller_headers = {"X-Dev-User-Email": evidence.cold_call.caller.email}
    manager_headers = {"X-Dev-User-Email": evidence.cold_call.owner.email}
    other_caller_headers = {"X-Dev-User-Email": evidence.cold_call.other_caller.email}
    cross_org_headers = {"X-Dev-User-Email": other_foundation.admin_user.email}
    evidence_path = f"/api/v1/prospecting/attempts/{evidence.cold_call.attempt.id}/evidence"
    media_path = f"/api/v1/voice/recordings/{evidence.recording.id}/media"
    audio_download_path = f"/api/v1/voice/recordings/{evidence.recording.id}/download"
    transcript_path = f"/api/v1/voice/transcripts/{transcript.id}"
    transcript_download_path = f"/api/v1/voice/transcripts/{transcript.id}/download"

    for headers in (caller_headers, manager_headers):
        detail = client.get(evidence_path, headers=headers)
        assert detail.status_code == 200, detail.text
        assert detail.headers["cache-control"] == "private, no-store"
        body = detail.json()
        assert body["attempt_id"] == str(evidence.cold_call.attempt.id)
        assert body["call_record_id"] == str(evidence.call.id)
        assert body["dial_leg_id"] == str(evidence.cold_call.leg.id)
        assert body["recording"]["id"] == str(evidence.recording.id)
        assert body["transcript"]["id"] == str(transcript.id)
        assert body["evidence_status"] == "ready"
        assert body["capabilities"]["can_play"] is True
        assert body["capabilities"]["can_download_audio"] is True
        assert body["capabilities"]["can_download_transcript"] is True

        media = client.get(media_path, headers=headers)
        assert media.status_code == 200, media.text
        assert media.content == b"ID3-d7-private-audio"
        assert media.headers["cache-control"] == "private, no-store"
        assert media.headers["content-disposition"].startswith("inline;")

        audio_download = client.get(audio_download_path, headers=headers)
        assert audio_download.status_code == 200, audio_download.text
        assert audio_download.content == b"ID3-d7-private-audio"
        assert audio_download.headers["cache-control"] == "private, no-store"
        assert audio_download.headers["content-disposition"].startswith("attachment;")

        transcript_detail = client.get(transcript_path, headers=headers)
        assert transcript_detail.status_code == 200, transcript_detail.text
        assert transcript_detail.json()["transcript_text"].startswith("Seller is relocating")
        transcript_download = client.get(transcript_download_path, headers=headers)
        assert transcript_download.status_code == 200, transcript_download.text
        assert transcript_download.headers["cache-control"] == "private, no-store"

    for headers in (other_caller_headers, cross_org_headers):
        assert client.get(evidence_path, headers=headers).status_code == 404
        assert client.get(media_path, headers=headers).status_code == 404
        assert client.get(audio_download_path, headers=headers).status_code == 404
        assert client.get(transcript_path, headers=headers).status_code == 404
        assert client.get(transcript_download_path, headers=headers).status_code == 404


def test_call_evidence_requires_recording_access_beyond_work_permission(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    evidence = seed_eligible_recording(db_session, client)
    work_permission = db_session.scalar(
        select(Permission).where(Permission.key == PermissionKeys.WORK_ASSIGNED_CALLING_LISTS)
    )
    assert work_permission is not None
    work_only_user = User(
        organization_id=evidence.cold_call.organization.id,
        email="d7-work-only@example.com",
        display_name="D7 Work Only",
        external_auth_id=None,
        is_active=True,
        calling_enabled=True,
    )
    work_only_role = Role(
        organization_id=evidence.cold_call.organization.id,
        key=f"d7_work_only_{uuid4().hex}",
        name="D7 work-only role",
    )
    db_session.add_all([work_only_user, work_only_role])
    db_session.flush()
    db_session.add_all(
        [
            RoleAssignment(
                organization_id=evidence.cold_call.organization.id,
                user_id=work_only_user.id,
                role_id=work_only_role.id,
            ),
            RolePermission(
                organization_id=evidence.cold_call.organization.id,
                role_id=work_only_role.id,
                permission_id=work_permission.id,
            ),
        ]
    )
    evidence.cold_call.attempt.caller_user_id = work_only_user.id
    db_session.commit()

    response = client.get(
        f"/api/v1/prospecting/attempts/{evidence.cold_call.attempt.id}/evidence",
        headers={"X-Dev-User-Email": work_only_user.email},
    )

    assert response.status_code == 403
    assert PermissionKeys.ACCESS_RECORDINGS in response.json()["detail"]


def test_call_evidence_prefers_retained_recording_and_uses_deleted_transcript_fallback(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    evidence = seed_eligible_recording(db_session, client)
    old_transcript = enqueue_eligible_prospecting_call_transcript(
        db_session,
        evidence.recording,
        model_name="gpt-4o-transcribe-diarize",
    )
    assert old_transcript is not None
    complete_transcript_notes(old_transcript)
    now = datetime.now(UTC)
    evidence.recording.status = "deleted"
    evidence.recording.deleted_at = now - timedelta(days=1)
    evidence.recording.deleted_by_user_id = evidence.cold_call.owner.id
    evidence.recording.deletion_reason = "Superseded provider media"
    evidence.recording.recorded_at = now - timedelta(days=2)
    evidence.recording.created_at = now - timedelta(days=2)

    replacement_provider_id = f"RE-d7-replacement-{uuid4().hex}"
    evidence.cold_call.attempt.provider_recording_id = replacement_provider_id
    evidence.cold_call.leg.provider_recording_id = replacement_provider_id
    provider_event = db_session.scalar(
        select(ProspectingProviderEvent).where(
            ProspectingProviderEvent.attempt_id == evidence.cold_call.attempt.id,
            ProspectingProviderEvent.event_type == "recording.completed",
        )
    )
    assert provider_event is not None
    provider_event.provider_recording_id = replacement_provider_id
    provider_event.external_event_id = f"voice:recording:{replacement_provider_id}:completed"
    replacement = CallRecording(
        organization_id=evidence.cold_call.organization.id,
        call_record_id=evidence.call.id,
        provider="twilio",
        provider_recording_id=replacement_provider_id,
        status="completed",
        media_reference=f"twilio://recordings/{replacement_provider_id}",
        duration_seconds=evidence.recording.duration_seconds,
        channel_count=2,
        consent_status="disclosed",
        recorded_at=now,
        retention_expires_at=None,
        deleted_at=None,
        deleted_by_user_id=None,
        deletion_reason=None,
        recording_metadata={"context": "prospecting", "replacement": True},
        created_at=now,
        updated_at=now,
    )
    db_session.add(replacement)
    db_session.commit()
    replacement_transcript = enqueue_eligible_prospecting_call_transcript(
        db_session,
        replacement,
        model_name="gpt-4o-transcribe-diarize",
    )
    assert replacement_transcript is not None
    complete_transcript_notes(replacement_transcript)
    db_session.commit()

    evidence_path = f"/api/v1/prospecting/attempts/{evidence.cold_call.attempt.id}/evidence"
    headers = {"X-Dev-User-Email": evidence.cold_call.owner.email}
    retained = client.get(evidence_path, headers=headers)
    assert retained.status_code == 200, retained.text
    assert retained.json()["recording"]["id"] == str(replacement.id)
    assert retained.json()["transcript"]["id"] == str(replacement_transcript.id)
    assert retained.json()["capabilities"]["can_play"] is True

    replacement.deleted_at = datetime.now(UTC)
    replacement.deleted_by_user_id = evidence.cold_call.owner.id
    replacement.deletion_reason = "D7 transcript retention fallback"
    db_session.commit()

    deleted_fallback = client.get(evidence_path, headers=headers)
    assert deleted_fallback.status_code == 200, deleted_fallback.text
    fallback_body = deleted_fallback.json()
    assert fallback_body["recording"]["id"] == str(replacement.id)
    assert fallback_body["transcript"]["id"] == str(replacement_transcript.id)
    assert fallback_body["evidence_status"] == "ready"
    assert fallback_body["capabilities"]["can_play"] is False
    assert fallback_body["capabilities"]["can_download_audio"] is False
    assert fallback_body["capabilities"]["can_download_transcript"] is True


@pytest.mark.parametrize(
    ("recording_state", "expected_status"),
    [
        ("retained_completed", "recording_ready"),
        ("in_progress", "processing"),
        ("deleted", "unavailable"),
        ("failed", "unavailable"),
        ("missing_provider_identity", "unavailable"),
        ("missing_consent", "unavailable"),
    ],
)
def test_evidence_status_only_advertises_recoverable_recording_states(
    db_session: Session,
    api_db_override: None,
    recording_state: str,
    expected_status: str,
) -> None:
    client = TestClient(app)
    evidence = seed_eligible_recording(db_session, client)
    if recording_state == "in_progress":
        evidence.recording.status = "in-progress"
    elif recording_state == "deleted":
        evidence.recording.deleted_at = datetime.now(UTC)
    elif recording_state == "failed":
        evidence.recording.status = "failed"
    elif recording_state == "missing_provider_identity":
        evidence.recording.provider_recording_id = None
    elif recording_state == "missing_consent":
        evidence.recording.consent_status = "not_recorded"

    assert prospecting_evidence_status(evidence.recording, None) == expected_status


def test_completed_transcript_remains_ready_after_audio_becomes_unavailable(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    evidence = seed_eligible_recording(db_session, client)
    transcript = enqueue_eligible_prospecting_call_transcript(
        db_session,
        evidence.recording,
        model_name="gpt-4o-transcribe-diarize",
    )
    assert transcript is not None
    complete_transcript_notes(transcript)
    evidence.recording.deleted_at = datetime.now(UTC)

    assert prospecting_evidence_status(evidence.recording, transcript) == "ready"


@pytest.mark.parametrize("audio_failure", ["deleted", "missing_consent"])
def test_audio_routes_deny_unavailable_media_but_preserve_transcript_download(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
    audio_failure: str,
) -> None:
    client = TestClient(app)
    evidence = seed_eligible_recording(db_session, client)
    transcript = enqueue_eligible_prospecting_call_transcript(
        db_session,
        evidence.recording,
        model_name="gpt-4o-transcribe-diarize",
    )
    assert transcript is not None
    complete_transcript_notes(transcript)
    if audio_failure == "deleted":
        evidence.recording.deleted_at = datetime.now(UTC)
        evidence.recording.deleted_by_user_id = evidence.cold_call.owner.id
        evidence.recording.deletion_reason = "D7 audio guard"
    else:
        evidence.recording.consent_status = "not_recorded"
    db_session.commit()
    provider_downloads = 0

    def unexpected_provider_download(*_args: object) -> TwilioRecordingMedia:
        nonlocal provider_downloads
        provider_downloads += 1
        return TwilioRecordingMedia(b"must-not-be-served", "audio/mpeg")

    monkeypatch.setattr(
        "app.routers.voice.download_twilio_recording",
        unexpected_provider_download,
    )
    headers = {"X-Dev-User-Email": evidence.cold_call.owner.email}
    for path in (
        f"/api/v1/voice/recordings/{evidence.recording.id}/media",
        f"/api/v1/voice/recordings/{evidence.recording.id}/download",
    ):
        response = client.get(path, headers=headers)
        assert response.status_code == 409
        assert response.json()["detail"] == "Recording is not ready."
    assert provider_downloads == 0

    transcript_download = client.get(
        f"/api/v1/voice/transcripts/{transcript.id}/download",
        headers=headers,
    )
    assert transcript_download.status_code == 200, transcript_download.text
    assert "Seller: I am relocating and want to sell within 30 days." in (transcript_download.text)


def test_warm_recording_scope_matches_restricted_lead_and_buyer_inbox_visibility(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    cold_evidence = seed_eligible_recording(db_session, client)
    handoff = seed_handoff_context(db_session, cold_evidence, status="accepted")
    restricted_lead = handoff.conversation
    organization_id = restricted_lead.organization_id
    owner = cold_evidence.cold_call.owner

    def add_role(permission_keys: set[str], suffix: str) -> Role:
        permissions = {
            item.key: item
            for item in db_session.scalars(
                select(Permission).where(Permission.key.in_(permission_keys))
            ).all()
        }
        assert permissions.keys() == permission_keys
        role = Role(
            organization_id=organization_id,
            key=f"d7_scope_{suffix}_{uuid4().hex}",
            name=f"D7 {suffix} scope",
        )
        db_session.add(role)
        db_session.flush()
        db_session.add_all(
            [
                RolePermission(
                    organization_id=organization_id,
                    role_id=role.id,
                    permission_id=permissions[key].id,
                )
                for key in sorted(permission_keys)
            ]
        )
        return role

    recording_role = add_role({PermissionKeys.ACCESS_RECORDINGS}, "recording")
    conversation_view_role = add_role(
        {
            PermissionKeys.ACCESS_RECORDINGS,
            PermissionKeys.VIEW_CONVERSATIONS,
        },
        "conversation_view",
    )
    buyer_view_role = add_role(
        {
            PermissionKeys.ACCESS_RECORDINGS,
            PermissionKeys.VIEW_BUYERS,
        },
        "buyer_view",
    )

    def add_user(email_prefix: str, role: Role) -> User:
        user = User(
            organization_id=organization_id,
            email=f"d7-{email_prefix}@example.com",
            display_name=f"D7 {email_prefix}",
            external_auth_id=None,
            is_active=True,
            calling_enabled=False,
        )
        db_session.add(user)
        db_session.flush()
        db_session.add(
            RoleAssignment(
                organization_id=organization_id,
                user_id=user.id,
                role_id=role.id,
            )
        )
        return user

    assigned_user = add_user("assigned-scope", recording_role)
    team_user = add_user("team-scope", recording_role)
    watcher_user = add_user("watcher-scope", recording_role)
    alias_user = add_user("alias-scope", recording_role)
    conversation_viewer = add_user("conversation-viewer", conversation_view_role)
    buyer_viewer = add_user("buyer-viewer", buyer_view_role)

    team = Team(
        organization_id=organization_id,
        name=f"D7 Recording Scope {uuid4().hex}",
        team_type="acquisitions",
        manager_user_id=team_user.id,
        is_active=True,
    )
    db_session.add(team)
    db_session.flush()
    db_session.add(
        TeamMembership(
            organization_id=organization_id,
            team_id=team.id,
            user_id=team_user.id,
            membership_role="member",
        )
    )
    alias = EmailSenderAlias(
        organization_id=organization_id,
        owner_user_id=None,
        assigned_team_id=None,
        created_by_user_id=owner.id,
        provider="resend",
        provider_identity_id=None,
        email_address=f"d7-recordings-{uuid4().hex}@example.com",
        display_name="D7 Recording Scope",
        alias_type="department",
        purpose_key="acquisitions",
        status="active",
        inbound_enabled=True,
        outbound_enabled=True,
        is_default=False,
        signature_text=None,
        routing_metadata={"visibility_scope": "restricted"},
    )
    db_session.add(alias)
    db_session.flush()
    db_session.add_all(
        [
            ConversationWatcher(
                organization_id=organization_id,
                conversation_id=restricted_lead.id,
                user_id=watcher_user.id,
                source="manual",
                notification_level="all",
                is_muted=False,
            ),
            EmailSenderGrant(
                organization_id=organization_id,
                email_sender_alias_id=alias.id,
                user_id=alias_user.id,
                granted_by_user_id=owner.id,
                access_level="use",
                can_send=True,
                receives_notifications=True,
            ),
        ]
    )
    restricted_lead.assigned_user_id = assigned_user.id
    restricted_lead.assigned_team_id = team.id
    restricted_lead.source_alias_id = alias.id
    restricted_lead.visibility_scope = "restricted"
    db_session.commit()

    restricted_recording, restricted_transcript = create_call_assets(
        db_session,
        restricted_lead,
        provider_suffix="d7-restricted-lead",
    )
    buyer_contact = Contact(
        organization_id=organization_id,
        legal_name="D7 Buyer Contact",
        preferred_name=None,
        contact_type="buyer",
        assigned_user_id=assigned_user.id,
    )
    db_session.add(buyer_contact)
    db_session.flush()
    buyer_conversation = Conversation(
        organization_id=organization_id,
        conversation_type="buyer",
        lead_id=None,
        contact_id=buyer_contact.id,
        assigned_user_id=assigned_user.id,
        assigned_team_id=None,
        source_alias_id=None,
        visibility_scope="standard",
        status="open",
        queue_key="buyers",
        priority="normal",
        unread_count=0,
        last_activity_at=datetime.now(UTC),
        last_inbound_at=None,
        last_outbound_at=None,
        closed_at=None,
        conversation_metadata=None,
    )
    db_session.add(buyer_conversation)
    db_session.commit()
    buyer_recording, buyer_transcript = create_call_assets(
        db_session,
        buyer_conversation,
        provider_suffix="d7-buyer",
    )
    monkeypatch.setattr(
        "app.routers.voice.download_twilio_recording",
        lambda *_args: TwilioRecordingMedia(b"ID3-d7-warm-scope", "audio/mpeg"),
    )

    restricted_media_path = f"/api/v1/voice/recordings/{restricted_recording.id}/media"
    restricted_transcript_path = f"/api/v1/voice/transcripts/{restricted_transcript.id}"
    for user in (assigned_user, team_user, watcher_user, alias_user, owner):
        headers = {"X-Dev-User-Email": user.email}
        assert client.get(restricted_media_path, headers=headers).status_code == 200
        assert client.get(restricted_transcript_path, headers=headers).status_code == 200

    conversation_viewer_headers = {"X-Dev-User-Email": conversation_viewer.email}
    assert client.get(restricted_media_path, headers=conversation_viewer_headers).status_code == 404
    assert (
        client.get(
            restricted_transcript_path,
            headers=conversation_viewer_headers,
        ).status_code
        == 404
    )

    buyer_media_path = f"/api/v1/voice/recordings/{buyer_recording.id}/media"
    buyer_transcript_path = f"/api/v1/voice/transcripts/{buyer_transcript.id}"
    assert client.get(buyer_media_path, headers=conversation_viewer_headers).status_code == 404
    assert (
        client.get(
            buyer_transcript_path,
            headers=conversation_viewer_headers,
        ).status_code
        == 404
    )
    for user in (buyer_viewer, owner):
        headers = {"X-Dev-User-Email": user.email}
        assert client.get(buyer_media_path, headers=headers).status_code == 200
        assert client.get(buyer_transcript_path, headers=headers).status_code == 200


def test_accepted_handoff_assignee_can_open_source_call_from_warm_timeline(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    evidence = seed_eligible_recording(db_session, client)
    transcript = enqueue_eligible_prospecting_call_transcript(
        db_session,
        evidence.recording,
        model_name="gpt-4o-transcribe-diarize",
    )
    assert transcript is not None
    complete_transcript_notes(transcript)
    created = client.post(
        "/api/v1/operations/users",
        headers={"X-Dev-User-Email": evidence.cold_call.owner.email},
        json={
            "email": "d7-acquisitions-assignee@example.com",
            "display_name": "D7 Acquisitions Assignee",
            "role_key": "acquisition_rep",
            "calling_enabled": False,
        },
    )
    assert created.status_code == 201, created.text
    assignee_id = UUID(created.json()["id"])
    handoff = seed_handoff_context(
        db_session,
        evidence,
        status="accepted",
        assigned_user_id=assignee_id,
    )
    linked = link_accepted_prospecting_evidence_for_attempt(
        db_session,
        evidence.cold_call.attempt.id,
    )
    assert linked is not None
    assert linked.conversation_id == handoff.conversation.id
    assert linked.source_call_record_id == evidence.call.id
    db_session.commit()
    monkeypatch.setattr(
        "app.routers.voice.download_twilio_recording",
        lambda *_args: TwilioRecordingMedia(b"ID3-accepted-handoff-audio", "audio/mpeg"),
    )
    assignee_headers = {"X-Dev-User-Email": "d7-acquisitions-assignee@example.com"}
    unrelated_headers = {"X-Dev-User-Email": evidence.cold_call.other_caller.email}
    media_path = f"/api/v1/voice/recordings/{evidence.recording.id}/media"
    audio_download_path = f"/api/v1/voice/recordings/{evidence.recording.id}/download"
    transcript_path = f"/api/v1/voice/transcripts/{transcript.id}"

    linked.provider = "manual_link"
    db_session.commit()
    assert client.get(media_path, headers=assignee_headers).status_code == 404
    linked.provider = "openai_prospecting"
    db_session.commit()

    media = client.get(media_path, headers=assignee_headers)
    assert media.status_code == 200, media.text
    assert media.content == b"ID3-accepted-handoff-audio"
    assert client.get(audio_download_path, headers=assignee_headers).status_code == 200
    assert client.get(transcript_path, headers=assignee_headers).status_code == 200
    conversation_detail = client.get(
        f"/api/v1/inbox/conversations/{handoff.conversation.id}",
        headers=assignee_headers,
    )
    assert conversation_detail.status_code == 200, conversation_detail.text
    timeline_item = next(
        item
        for item in conversation_detail.json()["timeline"]
        if item["provider"] == "openai_prospecting"
    )
    assert timeline_item["call_id"] == str(evidence.call.id)
    assert timeline_item["recording_id"] == str(evidence.recording.id)
    assert timeline_item["recording_status"] == "completed"
    assert timeline_item["transcript"]["id"] == str(transcript.id)
    assert (
        client.get(
            f"/api/v1/prospecting/attempts/{evidence.cold_call.attempt.id}/evidence",
            headers=assignee_headers,
        ).status_code
        == 403
    )

    assert client.get(media_path, headers=unrelated_headers).status_code == 404
    assert client.get(audio_download_path, headers=unrelated_headers).status_code == 404
    assert client.get(transcript_path, headers=unrelated_headers).status_code == 404


def test_sixty_minute_recording_below_byte_limit_processes_successfully(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    evidence = seed_eligible_recording(
        db_session,
        client,
        duration_seconds=61 * 60 + 7,
    )
    transcript = enqueue_eligible_prospecting_call_transcript(
        db_session,
        evidence.recording,
        model_name="gpt-4o-transcribe-diarize",
    )
    assert transcript is not None
    audio_size = 1_000_000
    transcription_sizes: list[int] = []
    prompt_payloads: list[dict[str, object]] = []
    monkeypatch.setattr(
        "app.services.call_intelligence.download_twilio_recording",
        lambda *_args: TwilioRecordingMedia(b"a" * audio_size, "audio/mpeg"),
    )

    def transcribe_audio(*_args: object, **kwargs: object) -> OpenAIAudioTranscript:
        audio = kwargs["audio"]
        assert isinstance(audio, bytes)
        transcription_sizes.append(len(audio))
        return OpenAIAudioTranscript(
            text="Seller is relocating and wants to sell within 30 days.",
            language="en",
            segments=[
                {
                    "speaker": "Seller",
                    "start": 10.0,
                    "end": 18.0,
                    "text": "I am relocating and want to sell within 30 days.",
                }
            ],
            total_tokens=900,
            input_tokens=800,
            output_tokens=100,
        )

    def create_notes(*_args: object, **kwargs: object) -> tuple[dict[str, object], dict[str, int]]:
        prompt_payloads.append(json.loads(str(kwargs["user_prompt"])))
        return (
            house_notes_payload(),
            {"input_tokens": 1200, "output_tokens": 300, "total_tokens": 1500},
        )

    monkeypatch.setattr(
        "app.services.call_intelligence.OpenAIResponsesClient.create_audio_transcription",
        transcribe_audio,
    )
    monkeypatch.setattr(
        "app.services.call_intelligence.OpenAIResponsesClient.create_structured_response",
        create_notes,
    )
    settings = Settings.model_validate(
        {
            "DATABASE_URL": "sqlite+pysqlite:///:memory:",
            "OPENAI_API_KEY": "test-key",
            "CALL_TRANSCRIPTION_ENABLED": True,
            "CALL_TRANSCRIPTION_MAX_AUDIO_BYTES": audio_size + 1,
        }
    )

    processed = process_call_transcript(db_session, transcript.id, settings)

    assert processed.status == "completed"
    assert processed.transcript_text is not None
    assert transcription_sizes == [audio_size]
    assert evidence.recording.duration_seconds > 60 * 60
    assert prompt_payloads[0]["party_type"] == "seller"
    assert prompt_payloads[0]["seller"] == evidence.cold_call.prospect.legal_name
    metadata = processed.transcript_metadata or {}
    assert metadata["conversation_context"] == "prospecting_seller"
    assert metadata["asset_class"] == "house"
    assert metadata["prospecting_attempt_id"] == str(evidence.cold_call.attempt.id)
    assert any(item["question_key"] == "timeline" for item in metadata["prospecting_suggestions"])


def test_manual_transcript_retry_is_single_use_across_replays_and_processing(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    evidence = seed_eligible_recording(db_session, client)
    transcript = enqueue_eligible_prospecting_call_transcript(
        db_session,
        evidence.recording,
        model_name="gpt-4o-transcribe-diarize",
    )
    assert transcript is not None
    transcript.status = "failed"
    transcript.error_message = "Temporary provider failure."
    transcript.transcript_metadata = {"attempts": 2, "permanent_failure": False}
    db_session.commit()
    path = f"/api/v1/voice/transcripts/{transcript.id}/retry"
    headers = {"X-Dev-User-Email": evidence.cold_call.owner.email}

    first = client.post(path, headers=headers)
    replay = client.post(path, headers=headers)

    assert first.status_code == 202, first.text
    assert replay.status_code == 409, replay.text
    db_session.refresh(transcript)
    assert transcript.status == "queued"
    assert (transcript.transcript_metadata or {})["manual_retry_count"] == 1
    assert (
        db_session.scalar(
            select(func.count(AuditEvent.id)).where(
                AuditEvent.action == "call_transcript.retry",
                AuditEvent.entity_id == transcript.id,
            )
        )
        == 1
    )

    transcript.status = "processing"
    db_session.commit()
    processing_replay = client.post(path, headers=headers)
    assert processing_replay.status_code == 409, processing_replay.text
    db_session.refresh(transcript)
    assert transcript.status == "processing"
    assert (transcript.transcript_metadata or {})["manual_retry_count"] == 1
    assert (
        db_session.scalar(
            select(func.count(AuditEvent.id)).where(
                AuditEvent.action == "call_transcript.retry",
                AuditEvent.entity_id == transcript.id,
            )
        )
        == 1
    )


def test_manual_transcript_retry_rechecks_status_after_concurrent_claim(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    evidence = seed_eligible_recording(db_session, client)
    transcript = enqueue_eligible_prospecting_call_transcript(
        db_session,
        evidence.recording,
        model_name="gpt-4o-transcribe-diarize",
    )
    assert transcript is not None
    transcript.status = "failed"
    transcript.error_message = "Temporary provider failure."
    transcript.transcript_metadata = {"attempts": 2, "permanent_failure": False}
    db_session.commit()
    eligibility_checks = 0

    def simulate_claim_during_retry(
        db: Session,
        recording: CallRecording,
    ) -> object:
        nonlocal eligibility_checks
        eligibility_checks += 1
        eligibility = prospecting_transcript_eligibility(db, recording)
        claimed = db.get(CallTranscript, transcript.id)
        assert claimed is not None
        claimed.status = "processing"
        db.flush()
        return eligibility

    monkeypatch.setattr(
        "app.services.call_intelligence.prospecting_transcript_eligibility",
        simulate_claim_during_retry,
    )
    response = client.post(
        f"/api/v1/voice/transcripts/{transcript.id}/retry",
        headers={"X-Dev-User-Email": evidence.cold_call.owner.email},
    )

    assert response.status_code == 409, response.text
    assert eligibility_checks == 1
    db_session.refresh(transcript)
    assert transcript.status == "processing"
    assert (transcript.transcript_metadata or {}).get("manual_retry_count") is None
    assert (
        db_session.scalar(
            select(func.count(AuditEvent.id)).where(
                AuditEvent.action == "call_transcript.retry",
                AuditEvent.entity_id == transcript.id,
            )
        )
        == 0
    )


def test_prospecting_transcript_provider_retry_exhaustion_and_manual_recovery(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    evidence = seed_eligible_recording(db_session, client)
    transcript = enqueue_eligible_prospecting_call_transcript(
        db_session,
        evidence.recording,
        model_name="gpt-4o-transcribe-diarize",
    )
    assert transcript is not None
    provider_attempts = 0

    def unavailable_media(*_args: object) -> TwilioRecordingMedia:
        nonlocal provider_attempts
        provider_attempts += 1
        raise TwilioRecordingError("Twilio recording is temporarily unavailable.")

    monkeypatch.setattr(
        "app.services.call_intelligence.download_twilio_recording",
        unavailable_media,
    )
    settings = Settings.model_validate(
        {
            "DATABASE_URL": "sqlite+pysqlite:///:memory:",
            "OPENAI_API_KEY": "test-key",
            "CALL_TRANSCRIPTION_ENABLED": True,
            "CALL_TRANSCRIPTION_MAX_ATTEMPTS": 2,
        }
    )

    assert process_next_call_transcript(db_session, settings) == transcript.id
    db_session.refresh(transcript)
    assert transcript.status == "failed"
    assert transcript.error_message == "Twilio recording is temporarily unavailable."
    assert (transcript.transcript_metadata or {})["attempts"] == 1
    assert (transcript.transcript_metadata or {})["permanent_failure"] is False
    assert process_next_call_transcript(db_session, settings) is None
    assert provider_attempts == 1

    transcript.transcript_metadata = {
        **(transcript.transcript_metadata or {}),
        "next_retry_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
    }
    db_session.commit()
    assert process_next_call_transcript(db_session, settings) == transcript.id
    db_session.refresh(transcript)
    assert transcript.status == "exhausted"
    assert (transcript.transcript_metadata or {})["attempts"] == 2
    assert (transcript.transcript_metadata or {})["exhausted_at"] is not None
    assert provider_attempts == 2

    retried = client.post(
        f"/api/v1/voice/transcripts/{transcript.id}/retry",
        headers={"X-Dev-User-Email": evidence.cold_call.owner.email},
    )
    assert retried.status_code == 202, retried.text
    assert retried.json()["status"] == "queued"
    db_session.refresh(transcript)
    assert (transcript.transcript_metadata or {})["attempts"] == 0
    assert (transcript.transcript_metadata or {})["manual_retry_count"] == 1

    monkeypatch.setattr(
        "app.services.call_intelligence.download_twilio_recording",
        lambda *_args: TwilioRecordingMedia(b"retry-audio", "audio/mpeg"),
    )
    monkeypatch.setattr(
        "app.services.call_intelligence.OpenAIResponsesClient.create_audio_transcription",
        lambda *_args, **_kwargs: OpenAIAudioTranscript(
            text="Seller is relocating and wants to sell within 30 days.",
            language="en",
            segments=[
                {
                    "speaker": "Seller",
                    "start": 10.0,
                    "end": 18.0,
                    "text": "I am relocating and want to sell within 30 days.",
                }
            ],
            total_tokens=90,
            input_tokens=80,
            output_tokens=10,
        ),
    )
    monkeypatch.setattr(
        "app.services.call_intelligence.OpenAIResponsesClient.create_structured_response",
        lambda *_args, **_kwargs: (
            house_notes_payload(),
            {"input_tokens": 120, "output_tokens": 30, "total_tokens": 150},
        ),
    )

    assert process_next_call_transcript(db_session, settings) == transcript.id
    db_session.refresh(transcript)
    assert transcript.status == "completed"
    assert transcript.transcript_text is not None
    assert (transcript.transcript_metadata or {})["manual_retry_count"] == 1


@pytest.mark.parametrize(
    ("failure_kind", "reason_fragment"),
    [
        ("deleted", "audio has been deleted"),
        ("missing_provider_identity", "missing its provider identity"),
        ("missing_consent", "lacks an authorized consent record"),
    ],
)
def test_irrecoverable_completed_cold_recording_exhausts_without_retry_capability(
    db_session: Session,
    api_db_override: None,
    failure_kind: str,
    reason_fragment: str,
) -> None:
    client = TestClient(app)
    evidence = seed_eligible_recording(db_session, client)
    transcript = enqueue_eligible_prospecting_call_transcript(
        db_session,
        evidence.recording,
        model_name="gpt-4o-transcribe-diarize",
    )
    assert transcript is not None

    if failure_kind == "deleted":
        evidence.recording.deleted_at = datetime.now(UTC)
        evidence.recording.deleted_by_user_id = evidence.cold_call.owner.id
        evidence.recording.deletion_reason = "D7 retention test"
    elif failure_kind == "missing_provider_identity":
        evidence.recording.provider_recording_id = None
    else:
        evidence.recording.consent_status = "not_recorded"
    db_session.commit()

    eligibility = prospecting_transcript_eligibility(db_session, evidence.recording)
    assert eligibility.state == "invalid"
    assert reason_fragment in eligibility.reason

    settings = Settings.model_validate(
        {
            "DATABASE_URL": "sqlite+pysqlite:///:memory:",
            "CALL_TRANSCRIPTION_ENABLED": True,
        }
    )
    assert process_next_call_transcript(db_session, settings) is None
    db_session.refresh(transcript)
    assert transcript.status == "exhausted"
    assert transcript.error_message is not None
    assert reason_fragment in transcript.error_message
    metadata = transcript.transcript_metadata or {}
    assert metadata["permanent_failure"] is True
    assert metadata["eligibility_state"] == "invalid"
    assert metadata["next_retry_at"] is None
    assert metadata["exhausted_at"] is not None

    detail = client.get(
        f"/api/v1/prospecting/attempts/{evidence.cold_call.attempt.id}/evidence",
        headers={"X-Dev-User-Email": evidence.cold_call.owner.email},
    )
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["evidence_status"] == "unavailable"
    assert body["capabilities"]["can_play"] is False
    assert body["capabilities"]["can_download_audio"] is False
    assert body["capabilities"]["can_retry"] is False


def test_fallback_discovery_is_not_starved_by_more_than_one_page_of_ineligible_calls(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    eligible = seed_eligible_recording(db_session, client)
    seed_earlier_wrong_party_recordings(db_session, eligible, count=101)
    oldest_recording = db_session.scalar(
        select(CallRecording).order_by(CallRecording.created_at.asc())
    )
    assert oldest_recording is not None
    assert prospecting_transcript_eligibility(db_session, oldest_recording).state == "ineligible"
    assert db_session.scalar(select(func.count(CallRecording.id))) == 102
    assert db_session.scalar(select(func.count(CallTranscript.id))) == 0
    processed_ids: list[object] = []

    def capture_processing(
        _db: Session,
        transcript_id: object,
        _settings: Settings,
    ) -> CallTranscript:
        processed_ids.append(transcript_id)
        transcript = db_session.get(CallTranscript, transcript_id)
        assert transcript is not None
        return transcript

    monkeypatch.setattr(
        "app.services.call_intelligence.process_call_transcript",
        capture_processing,
    )
    settings = Settings.model_validate(
        {
            "DATABASE_URL": "sqlite+pysqlite:///:memory:",
            "OPENAI_API_KEY": "test-key",
            "CALL_TRANSCRIPTION_ENABLED": True,
        }
    )

    selected_id = process_next_call_transcript(db_session, settings)

    assert selected_id is not None
    assert processed_ids == [selected_id]
    selected = db_session.get(CallTranscript, selected_id)
    assert selected is not None
    assert selected.recording_id == eligible.recording.id
    assert db_session.scalar(select(func.count(CallTranscript.id))) == 1
