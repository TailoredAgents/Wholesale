from datetime import UTC, datetime

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.integrations.openai_client import OpenAIAudioTranscript
from app.integrations.twilio_recordings import TwilioRecordingMedia
from app.main import app
from app.models.foundation import (
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
from app.schemas.voice import CallTranscriptReview, StructuredCallNotes
from app.services.bootstrap import bootstrap_foundation
from app.services.call_intelligence import (
    enqueue_call_transcript,
    process_call_transcript,
)

OWNER_EMAIL = "owner@example.com"


def test_call_transcription_requires_review_and_applies_only_selected_empty_fields(
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

    monkeypatch.setattr(
        "app.services.call_intelligence.download_twilio_recording",
        lambda *_args: TwilioRecordingMedia(b"audio", "audio/mpeg"),
    )
    monkeypatch.setattr(
        "app.services.call_intelligence.OpenAIResponsesClient.create_audio_transcription",
        lambda *_args, **_kwargs: OpenAIAudioTranscript(
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
        ),
    )
    notes_payload = {
        "summary": "Seller discussed timing, price, and roof repairs.",
        "motivation": "Relocating",
        "timeline": "30 days",
        "property_condition": "Roof needs replacement",
        "occupancy_status": "Owner occupied",
        "asking_price": "$180,000",
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
    monkeypatch.setattr(
        "app.services.call_intelligence.OpenAIResponsesClient.create_structured_response",
        lambda *_args, **_kwargs: (
            notes_payload,
            {
                "input_tokens": 2000,
                "output_tokens": 500,
                "total_tokens": 2500,
            },
        ),
    )
    settings = Settings.model_validate(
        {
            "DATABASE_URL": "sqlite+pysqlite:///:memory:",
            "OPENAI_API_KEY": "test-key",
            "CALL_TRANSCRIPTION_ENABLED": True,
        }
    )
    processed = process_call_transcript(db_session, transcript.id, settings)

    assert processed.status == "needs_review"
    assert processed.transcript_text
    assert processed.confidence_score == 88
    assert db_session.scalar(
        select(func.count()).select_from(ApprovalRequest)
    ) == 1
    assert db_session.scalar(select(func.count()).select_from(AiRunLog)) == 1
    ai_run = db_session.scalar(select(AiRunLog))
    assert ai_run is not None
    assert ai_run.input_tokens == 3000
    assert ai_run.output_tokens == 600
    assert ai_run.total_tokens == 3600
    assert ai_run.cost_microusd == 28_500
    assert ai_run.cost_cents == 3
    assert ai_run.run_metadata is not None
    assert ai_run.run_metadata["pricing_status"] == "priced"

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
            "asking_price",
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
    db_session.refresh(lead)
    assert lead.motivation == "Existing verified motivation"
    assert lead.desired_timeline == "30 days"
    assert lead.property_condition == "Roof replacement needed"
    assert lead.asking_price == "$180,000"
    assert db_session.scalar(
        select(func.count())
        .select_from(CommunicationRecord)
        .where(CommunicationRecord.provider == "openai_reviewed")
    ) == 1
    db_session.refresh(transcript)
    review_metrics = (transcript.transcript_metadata or {}).get("review_metrics")
    assert isinstance(review_metrics, dict)
    assert review_metrics["changed_fields"] == ["property_condition"]
    assert review_metrics["field_agreement_percent"] == 92
    quality_response = client.get(
        "/api/v1/ai",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    assert quality_response.status_code == 200
    quality = quality_response.json()["call_intelligence_quality"]
    assert quality["reviewed_calls"] == 1
    assert quality["approved_calls"] == 1
    assert quality["average_field_agreement"] == 92
    assert quality["autonomy_status"] == "human_review_required"
    assert db_session.scalar(
        select(func.count()).select_from(Task).where(Task.task_type == "call_follow_up")
    ) == 1

    repeated = client.patch(
        f"/api/v1/voice/transcripts/{transcript.id}/review",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=payload.model_dump(mode="json"),
    )
    assert repeated.status_code == 200
    assert db_session.scalar(
        select(func.count())
        .select_from(CommunicationRecord)
        .where(CommunicationRecord.provider == "openai_reviewed")
    ) == 1
    assert db_session.scalar(
        select(func.count()).select_from(Task).where(Task.task_type == "call_follow_up")
    ) == 1
