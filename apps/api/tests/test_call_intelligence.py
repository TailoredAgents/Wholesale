from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import principal_for_user
from app.core.config import Settings
from app.integrations.openai_client import OpenAIAudioTranscript, validate_strict_json_schema
from app.integrations.twilio_recordings import TwilioRecordingMedia
from app.main import app
from app.models.foundation import (
    ActivityEvent,
    AiOrchestratorEvent,
    AiRunLog,
    ApprovalRequest,
    CallRecord,
    CallRecording,
    CommunicationRecord,
    Contact,
    Conversation,
    Lead,
    Property,
    Task,
)
from app.schemas.leads import LeadCloseOutRequest
from app.schemas.voice import CallTranscriptReview, StructuredCallNotes
from app.services.bootstrap import bootstrap_foundation
from app.services.call_intelligence import (
    enqueue_call_transcript,
    process_call_transcript,
    process_next_call_transcript,
)
from app.services.leads import close_out_lead

OWNER_EMAIL = "owner@example.com"


def test_call_note_schema_is_valid_for_openai_strict_mode() -> None:
    schema = StructuredCallNotes.model_json_schema()

    validate_strict_json_schema(schema)
    assert set(schema["properties"]) == set(schema["required"])


def test_close_out_during_transcription_failure_keeps_ai_work_dismissed(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    result = bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    assert result.admin_user is not None
    owner = result.admin_user
    client = TestClient(app)
    created = client.post(
        "/api/v1/leads",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "contact": {"legal_name": "Concurrent Seller", "contact_type": "seller"},
            "property": {
                "street_address": "41 Concurrent Way",
                "city": "Atlanta",
                "state": "GA",
                "postal_code": "30303",
                "property_type": "single_family",
            },
            "source": "inbound_call",
            "stage_key": "contacted",
        },
    )
    assert created.status_code == 201, created.text
    lead = db_session.get(Lead, UUID(created.json()["id"]))
    assert lead is not None
    conversation = db_session.scalar(select(Conversation).where(Conversation.lead_id == lead.id))
    assert conversation is not None
    communication = CommunicationRecord(
        organization_id=lead.organization_id,
        conversation_id=conversation.id,
        lead_id=lead.id,
        contact_id=lead.contact_id,
        actor_user_id=owner.id,
        direction="outbound",
        channel="call",
        status="completed",
        provider="twilio",
        provider_message_id="CA-close-during-transcription",
        subject=None,
        body="Outbound call",
        occurred_at=datetime.now(UTC),
        external_payload=None,
        communication_metadata=None,
    )
    db_session.add(communication)
    db_session.flush()
    call = CallRecord(
        organization_id=lead.organization_id,
        conversation_id=conversation.id,
        lead_id=lead.id,
        contact_id=lead.contact_id,
        actor_user_id=owner.id,
        communication_record_id=communication.id,
        voice_line_id=None,
        call_intent_id=None,
        provider="twilio",
        provider_call_id="CA-close-during-transcription",
        child_provider_call_id=None,
        direction="outbound",
        status="completed",
        from_number="+14045550100",
        to_number="+14045550101",
        started_at=datetime.now(UTC),
        answered_at=datetime.now(UTC),
        ended_at=datetime.now(UTC),
        duration_seconds=60,
        disposition=None,
        recording_consent_status="disclosed",
        call_metadata=None,
    )
    db_session.add(call)
    db_session.flush()
    recording = CallRecording(
        organization_id=lead.organization_id,
        call_record_id=call.id,
        provider="twilio",
        provider_recording_id="RE-close-during-transcription",
        status="completed",
        media_reference="twilio://recordings/RE-close-during-transcription",
        duration_seconds=60,
        channel_count=2,
        consent_status="disclosed",
        recorded_at=datetime.now(UTC),
        deleted_at=None,
        recording_metadata=None,
    )
    db_session.add(recording)
    db_session.flush()
    transcript = enqueue_call_transcript(
        db_session,
        recording,
        model_name="gpt-4o-transcribe-diarize",
    )
    db_session.commit()

    monkeypatch.setattr(
        "app.services.call_intelligence.download_twilio_recording",
        lambda *_args: TwilioRecordingMedia(b"audio", "audio/mpeg"),
    )

    def close_then_fail(*_args: object, **_kwargs: object) -> OpenAIAudioTranscript:
        closed = close_out_lead(
            db_session,
            principal_for_user(db_session, owner),
            lead.id,
            LeadCloseOutRequest(
                disposition="dead",
                reason="The seller ended discussions while call processing was still running.",
            ),
        )
        assert closed is not None
        raise ValueError("Provider failed after the lead was closed.")

    monkeypatch.setattr(
        "app.services.call_intelligence.OpenAIResponsesClient.create_audio_transcription",
        close_then_fail,
    )
    settings = Settings.model_validate(
        {
            "DATABASE_URL": "sqlite+pysqlite:///:memory:",
            "OPENAI_API_KEY": "test-key",
            "CALL_TRANSCRIPTION_ENABLED": True,
        }
    )

    processed = process_call_transcript(db_session, transcript.id, settings)

    assert processed.status == "failed"
    db_session.expire_all()
    operation_event = db_session.scalar(
        select(AiOrchestratorEvent).where(
            AiOrchestratorEvent.event_key == f"call.notes:{transcript.id}"
        )
    )
    assert operation_event is not None
    assert operation_event.status == "dismissed"
    assert operation_event.last_error is not None
    assert operation_event.last_error.startswith("Lead closed out:")


def test_call_transcription_auto_populates_empty_fields_before_review(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    result = bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    assert result.admin_user is not None
    owner = result.admin_user
    organization = result.organization
    contact = Contact(
        organization_id=organization.id,
        legal_name="Taylor Seller",
        preferred_name="Taylor",
        contact_type="seller",
        assigned_user_id=owner.id,
    )
    property_record = Property(
        organization_id=organization.id,
        street_address="100 Main Street",
        city="Atlanta",
        state="GA",
        postal_code="30303",
        county="Fulton",
        property_type="single_family",
        normalized_address_key=None,
    )
    db_session.add_all([contact, property_record])
    db_session.flush()
    lead = Lead(
        organization_id=organization.id,
        contact_id=contact.id,
        property_id=property_record.id,
        assigned_user_id=owner.id,
        source="inbound_call",
        stage_key="contacted",
        lead_temperature=None,
        motivation="Existing verified motivation",
        desired_timeline=None,
        property_condition=None,
        occupancy_status=None,
        asking_price=None,
        mortgage_balance=None,
        appointment_status=None,
        next_follow_up_at=None,
        archived_at=None,
    )
    db_session.add(lead)
    db_session.flush()
    conversation = Conversation(
        organization_id=organization.id,
        lead_id=lead.id,
        contact_id=contact.id,
        assigned_user_id=owner.id,
        status="open",
        queue_key="acquisitions_follow_up",
        priority="normal",
        unread_count=0,
        last_activity_at=datetime.now(UTC),
        last_inbound_at=None,
        last_outbound_at=None,
        closed_at=None,
    )
    db_session.add(conversation)
    db_session.flush()
    communication = CommunicationRecord(
        organization_id=organization.id,
        conversation_id=conversation.id,
        lead_id=lead.id,
        contact_id=contact.id,
        actor_user_id=owner.id,
        direction="outbound",
        channel="call",
        status="completed",
        provider="twilio",
        provider_message_id="CA-call-intelligence",
        subject=None,
        body="Outbound call",
        occurred_at=datetime.now(UTC),
        external_payload=None,
        communication_metadata=None,
    )
    db_session.add(communication)
    db_session.flush()
    call = CallRecord(
        organization_id=organization.id,
        conversation_id=conversation.id,
        lead_id=lead.id,
        contact_id=contact.id,
        actor_user_id=owner.id,
        communication_record_id=communication.id,
        voice_line_id=None,
        call_intent_id=None,
        provider="twilio",
        provider_call_id="CA-call-intelligence",
        child_provider_call_id=None,
        direction="outbound",
        status="completed",
        from_number="+14045550100",
        to_number="+14045550101",
        started_at=datetime.now(UTC),
        answered_at=datetime.now(UTC),
        ended_at=datetime.now(UTC),
        duration_seconds=180,
        disposition=None,
        recording_consent_status="disclosed",
        call_metadata=None,
    )
    db_session.add(call)
    db_session.flush()
    recording = CallRecording(
        organization_id=organization.id,
        call_record_id=call.id,
        provider="twilio",
        provider_recording_id="RE-call-intelligence",
        status="completed",
        media_reference="twilio://recordings/RE-call-intelligence",
        duration_seconds=180,
        channel_count=2,
        consent_status="disclosed",
        recorded_at=datetime.now(UTC),
        deleted_at=None,
        recording_metadata=None,
    )
    db_session.add(recording)
    db_session.flush()
    transcript = enqueue_call_transcript(
        db_session,
        recording,
        model_name="gpt-4o-transcribe-diarize",
    )
    db_session.commit()

    transcript.status = "exhausted"
    transcript.error_message = "Temporary provider failure."
    transcript.transcript_metadata = {
        **(transcript.transcript_metadata or {}),
        "attempts": 3,
        "exhausted_at": datetime.now(UTC).isoformat(),
    }
    db_session.commit()
    retry_client = TestClient(app)
    retry_response = retry_client.post(
        f"/api/v1/voice/transcripts/{transcript.id}/retry",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    assert retry_response.status_code == 202
    assert retry_response.json()["status"] == "queued"
    db_session.refresh(transcript)
    assert transcript.error_message is None
    assert (transcript.transcript_metadata or {})["attempts"] == 0
    assert (transcript.transcript_metadata or {})["manual_retry_count"] == 1

    monkeypatch.setattr(
        "app.services.call_intelligence.download_twilio_recording",
        lambda *_args: TwilioRecordingMedia(b"audio", "audio/mpeg"),
    )
    audio_transcription_calls = 0

    def transcribe_audio(*_args: object, **_kwargs: object) -> OpenAIAudioTranscript:
        nonlocal audio_transcription_calls
        audio_transcription_calls += 1
        return OpenAIAudioTranscript(
            text="Seller wants to move in 30 days and asks $180,000.",
            language="en",
            segments=[
                {
                    "speaker": "Seller",
                    "start": 12.0,
                    "end": 18.0,
                    "text": "I want to move in 30 days and I am asking 180 thousand.",
                }
            ],
            total_tokens=1100,
            input_tokens=1000,
            output_tokens=100,
        )

    monkeypatch.setattr(
        "app.services.call_intelligence.OpenAIResponsesClient.create_audio_transcription",
        transcribe_audio,
    )
    notes_payload = {
        "summary": "Seller discussed timing, price, and roof repairs.",
        "motivation": "Relocating",
        "timeline": "30 days",
        "property_condition": "Roof needs replacement",
        "occupancy_status": "Owner occupied",
        "asking_price": "$180,000",
        "mortgage_balance": "$92,000 payoff",
        "mortgage_or_title": None,
        "repairs": ["Replace roof"],
        "objections": [],
        "commitments": ["Review an in-person offer"],
        "next_action": "Confirm property appointment",
        "follow_up_at": "2026-07-20T14:00:00-04:00",
        "appointment_details": None,
        "confidence": 88,
        "evidence": [
            {
                "field": "timeline",
                "segment_index": 0,
                "start_seconds": 12.0,
                "supporting_text": "Seller stated 30 days.",
            }
        ],
    }
    structured_response_calls = 0

    def create_structured_notes(
        *_args: object,
        **_kwargs: object,
    ) -> tuple[dict[str, object], dict[str, int]]:
        nonlocal structured_response_calls
        structured_response_calls += 1
        if structured_response_calls == 1:
            raise ValueError("Temporary note-generation failure.")
        return (
            notes_payload,
            {
                "input_tokens": 2000,
                "output_tokens": 500,
                "total_tokens": 2500,
            },
        )

    monkeypatch.setattr(
        "app.services.call_intelligence.OpenAIResponsesClient.create_structured_response",
        create_structured_notes,
    )
    settings = Settings.model_validate(
        {
            "DATABASE_URL": "sqlite+pysqlite:///:memory:",
            "OPENAI_API_KEY": "test-key",
            "CALL_TRANSCRIPTION_ENABLED": True,
        }
    )
    first_attempt = process_call_transcript(db_session, transcript.id, settings)
    assert first_attempt.status == "failed"
    assert first_attempt.transcript_text
    assert audio_transcription_calls == 1
    checkpoint = (first_attempt.transcript_metadata or {}).get("transcription_checkpoint")
    assert isinstance(checkpoint, dict)
    assert checkpoint["model"] == "gpt-4o-transcribe-diarize"
    failed_run = db_session.scalar(select(AiRunLog).where(AiRunLog.status == "failed"))
    assert failed_run is not None
    assert failed_run.input_tokens == 1000
    assert failed_run.output_tokens == 100
    assert failed_run.total_tokens == 1100
    assert failed_run.cost_microusd == 3_500

    processed = process_call_transcript(db_session, transcript.id, settings)

    assert processed.status == "needs_review"
    assert processed.transcript_text
    assert processed.confidence_score == 88
    assert audio_transcription_calls == 1
    assert structured_response_calls == 2
    db_session.refresh(lead)
    assert lead.motivation == "Existing verified motivation"
    assert lead.desired_timeline == "30 days"
    assert lead.property_condition == "Roof needs replacement"
    assert lead.occupancy_status == "Owner occupied"
    assert lead.asking_price == "$180,000"
    assert lead.mortgage_balance == "$92,000 payoff"
    auto_population_event = db_session.scalar(
        select(ActivityEvent).where(
            ActivityEvent.event_type == "call_notes.crm_fields_auto_populated"
        )
    )
    assert auto_population_event is not None
    assert "desired_timeline" in auto_population_event.summary
    lead.occupancy_status = "Tenant occupied"
    db_session.commit()
    assert db_session.scalar(select(func.count()).select_from(ApprovalRequest)) == 1
    assert db_session.scalar(select(func.count()).select_from(AiRunLog)) == 2
    run_keys = set(db_session.scalars(select(AiRunLog.idempotency_key)))
    assert len(run_keys) == 2
    assert all(key and ":manual:1:attempt:" in key for key in run_keys)
    ai_run = db_session.scalar(select(AiRunLog).where(AiRunLog.status == "needs_review"))
    assert ai_run is not None
    assert ai_run.input_tokens == 2000
    assert ai_run.output_tokens == 500
    assert ai_run.total_tokens == 2500
    assert ai_run.cost_microusd == 25_000
    assert ai_run.cost_cents == 3
    assert ai_run.run_metadata is not None
    assert ai_run.run_metadata["pricing_status"] == "priced"
    assert ai_run.run_metadata["transcription_reused"] is True
    total_call_cost = db_session.scalar(select(func.sum(AiRunLog.cost_microusd)))
    assert total_call_cost == 28_500
    operation_event = db_session.scalar(
        select(AiOrchestratorEvent).where(
            AiOrchestratorEvent.event_key == f"call.notes:{transcript.id}"
        )
    )
    assert operation_event is not None
    assert operation_event.status == "needs_review"
    assert ai_run.orchestrator_event_id == operation_event.id

    client = TestClient(app)
    approval = db_session.scalar(select(ApprovalRequest))
    assert approval is not None
    approval_list = client.get(
        "/api/v1/approvals",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    assert approval_list.status_code == 200
    assert approval_list.json()["items"][0]["review_url"] == "/os/inbox"
    blind_decision = client.patch(
        f"/api/v1/approvals/{approval.id}/decision",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={"status": "approved", "decision_notes": "Approve without the call."},
    )
    assert blind_decision.status_code == 422

    reviewed_notes = {
        **notes_payload,
        "property_condition": "Roof replacement needed",
    }
    payload = CallTranscriptReview(
        status="approved",
        structured_notes=StructuredCallNotes.model_validate(reviewed_notes),
        decision_notes="Checked against the recording.",
        apply_field_updates=[
            "motivation",
            "timeline",
            "property_condition",
            "occupancy_status",
            "asking_price",
            "mortgage_balance",
        ],
        create_follow_up_task=True,
    )
    review_response = client.patch(
        f"/api/v1/voice/transcripts/{transcript.id}/review",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=payload.model_dump(mode="json"),
    )
    assert review_response.status_code == 200
    assert review_response.json()["status"] == "approved"
    db_session.refresh(operation_event)
    assert operation_event.status == "completed"
    assert (operation_event.payload or {})["review_outcome"] == "approved"
    db_session.refresh(lead)
    assert lead.motivation == "Existing verified motivation"
    assert lead.desired_timeline == "30 days"
    assert lead.property_condition == "Roof replacement needed"
    assert lead.occupancy_status == "Tenant occupied"
    assert lead.asking_price == "$180,000"
    assert lead.mortgage_balance == "$92,000 payoff"
    assert lead.next_follow_up_at is not None
    assert lead.next_follow_up_at.replace(tzinfo=UTC) == datetime(2026, 7, 20, 18, 0, tzinfo=UTC)
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(CommunicationRecord)
            .where(CommunicationRecord.provider == "openai_reviewed")
        )
        == 1
    )
    approved_note = db_session.scalar(
        select(CommunicationRecord).where(CommunicationRecord.provider == "openai_reviewed")
    )
    assert approved_note is not None
    assert approved_note.lead_id == lead.id
    assert approved_note.contact_id == lead.contact_id
    assert approved_note.conversation_id == conversation.id
    assert "Mortgage balance/payoff: $92,000 payoff" in approved_note.body
    lead_detail = client.get(
        f"/api/v1/leads/{lead.id}",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    assert lead_detail.status_code == 200, lead_detail.text
    lead_payload = lead_detail.json()
    assert lead_payload["desired_timeline"] == "30 days"
    assert lead_payload["property_condition"] == "Roof replacement needed"
    assert lead_payload["occupancy_status"] == "Tenant occupied"
    assert lead_payload["asking_price"] == "$180,000"
    assert lead_payload["mortgage_balance"] == "$92,000 payoff"
    assert lead_payload["next_follow_up_at"] == "2026-07-20T18:00:00"
    assert lead_payload["communications"][0]["id"] == str(approved_note.id)
    assert lead_payload["communications"][0]["direction"] == "internal"
    assert lead_payload["communications"][0]["channel"] == "note"
    assert any(task["task_type"] == "call_follow_up" for task in lead_payload["open_tasks"])
    db_session.refresh(transcript)
    review_metrics = (transcript.transcript_metadata or {}).get("review_metrics")
    assert isinstance(review_metrics, dict)
    assert review_metrics["changed_fields"] == ["property_condition"]
    assert review_metrics["field_agreement_percent"] == 93
    quality_response = client.get(
        "/api/v1/ai",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    assert quality_response.status_code == 200
    quality = quality_response.json()["call_intelligence_quality"]
    assert quality["reviewed_calls"] == 1
    assert quality["approved_calls"] == 1
    assert quality["average_field_agreement"] == 93
    assert quality["autonomy_status"] == "human_review_required"
    assert (
        db_session.scalar(
            select(func.count()).select_from(Task).where(Task.task_type == "call_follow_up")
        )
        == 1
    )

    follow_up_task = db_session.scalar(select(Task).where(Task.task_type == "call_follow_up"))
    assert follow_up_task is not None
    assert follow_up_task.due_at is not None
    assert follow_up_task.due_at.replace(tzinfo=UTC) == datetime(2026, 7, 20, 18, 0, tzinfo=UTC)

    repeated = client.patch(
        f"/api/v1/voice/transcripts/{transcript.id}/review",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=payload.model_dump(mode="json"),
    )
    assert repeated.status_code == 200
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(CommunicationRecord)
            .where(CommunicationRecord.provider == "openai_reviewed")
        )
        == 1
    )
    assert (
        db_session.scalar(
            select(func.count()).select_from(Task).where(Task.task_type == "call_follow_up")
        )
        == 1
    )

    transcript.status = "failed"
    transcript.transcript_metadata = {
        **(transcript.transcript_metadata or {}),
        "attempts": 1,
        "next_retry_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
    }
    db_session.commit()
    assert process_next_call_transcript(db_session, settings) is None
    db_session.refresh(transcript)
    assert transcript.status == "failed"

    transcript.transcript_metadata = {
        **(transcript.transcript_metadata or {}),
        "attempts": settings.call_transcription_max_attempts,
        "next_retry_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
    }
    db_session.commit()
    assert process_next_call_transcript(db_session, settings) is None
    db_session.refresh(transcript)
    assert transcript.status == "exhausted"
