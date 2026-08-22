from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.integrations.batchdialer_client import BatchDialerCDRPage, BatchDialerTransientError
from app.main import app
from app.models.foundation import (
    Appointment,
    ApprovalRequest,
    AttributionTouch,
    BatchDialerSyncCheckpoint,
    CallRecord,
    CallRecording,
    CallTranscript,
    CommunicationRecord,
    ConsentRecord,
    Lead,
    Property,
    ProspectingProviderEvent,
    Task,
)
from app.services.batchdialer_direct import (
    BatchDialerClaimLost,
    _lock_claimed_event,
    archive_batchdialer_cdr,
    classify_disposition,
    poll_batchdialer_direct,
    process_next_batchdialer_direct_event,
)
from app.services.bootstrap import bootstrap_foundation


class FakeBatchDialerClient:
    def __init__(self, _settings: Settings) -> None:
        pass

    def get_contact(self, _contact_id: str) -> dict[str, Any]:
        return {
            "id": 44,
            "firstname": "Test",
            "lastname": "Seller",
            "address": "123 Test Lane",
            "city": "Atlanta",
            "state": "GA",
            "postalcode": "30303",
            "email": "seller@example.com",
            "phonenumber1": "+16785550199",
            "phonenumbers": [{"phonenumber": "+16785550199"}],
        }

    def get_transcript(self, _cdr_id: int | str) -> tuple[dict[str, Any], ...]:
        return (
            {
                "time": 1,
                "role": "Speaker 1",
                "text": "Would you like to discuss selling and meet Tuesday at 2?",
            },
            {
                "time": 2,
                "role": "Speaker 2",
                "text": "Yes, I want to sell and I agree to meet Tuesday at 2.",
            },
        )


class FakeOpenAIResponsesClient:
    def __init__(self, **_kwargs: object) -> None:
        pass

    def create_structured_response(
        self, **_kwargs: object
    ) -> tuple[dict[str, Any], dict[str, int]]:
        seller_evidence = {
            "segment_index": 1,
            "supporting_text": "I want to sell",
        }
        agent_evidence = {
            "segment_index": 0,
            "supporting_text": "Would you like to discuss selling",
        }
        appointment_evidence = {
            "segment_index": 1,
            "supporting_text": "I agree to meet Tuesday at 2",
        }
        return (
            {
                "decision": "accept",
                "live_two_way_conversation": True,
                "explicit_seller_interest": True,
                "appointment_agreed": True,
                "conflict_type": "none",
                "confidence": 97,
                "reason": "The seller explicitly wants to sell and agreed to meet.",
                "conversation_evidence": [agent_evidence, seller_evidence],
                "seller_interest_evidence": [seller_evidence],
                "appointment_evidence": [appointment_evidence],
            },
            {"total_tokens": 100, "input_tokens": 80, "output_tokens": 20},
        )


class ReviewOpenAIResponsesClient(FakeOpenAIResponsesClient):
    def create_structured_response(
        self, **_kwargs: object
    ) -> tuple[dict[str, Any], dict[str, int]]:
        return (
            {
                "decision": "review",
                "live_two_way_conversation": True,
                "explicit_seller_interest": True,
                "appointment_agreed": False,
                "conflict_type": "none",
                "confidence": 92,
                "reason": "The seller did not explicitly agree to an appointment.",
                "conversation_evidence": [
                    {
                        "segment_index": 0,
                        "supporting_text": "Would you like to discuss selling",
                    },
                    {"segment_index": 1, "supporting_text": "I want to sell"}
                ],
                "seller_interest_evidence": [
                    {"segment_index": 1, "supporting_text": "I want to sell"}
                ],
                "appointment_evidence": [],
            },
            {"total_tokens": 90, "input_tokens": 70, "output_tokens": 20},
        )


class InvalidEvidenceOpenAIResponsesClient(FakeOpenAIResponsesClient):
    def create_structured_response(
        self, **_kwargs: object
    ) -> tuple[dict[str, Any], dict[str, int]]:
        result, usage = super().create_structured_response(**_kwargs)
        result["seller_interest_evidence"] = [
            {"segment_index": 1, "supporting_text": "This text was never spoken"}
        ]
        return result, usage


class OneTurnEvidenceOpenAIResponsesClient(FakeOpenAIResponsesClient):
    def create_structured_response(
        self, **_kwargs: object
    ) -> tuple[dict[str, Any], dict[str, int]]:
        result, usage = super().create_structured_response(**_kwargs)
        result["conversation_evidence"] = [
            {"segment_index": 1, "supporting_text": "I want to sell"}
        ]
        return result, usage


class LowConfidenceOpenAIResponsesClient(FakeOpenAIResponsesClient):
    def create_structured_response(
        self, **_kwargs: object
    ) -> tuple[dict[str, Any], dict[str, int]]:
        result, usage = super().create_structured_response(**_kwargs)
        result["decision"] = "review"
        result["confidence"] = 72
        result["reason"] = "The cited seller-interest evidence needs human review."
        return result, usage


class ScriptedBatchDialerClient(FakeBatchDialerClient):
    def __init__(
        self,
        transcript_responses: list[object],
        *,
        contact: dict[str, Any] | None = None,
    ) -> None:
        self.transcript_responses = list(transcript_responses)
        self.contact = contact
        self.transcript_calls = 0

    def get_contact(self, contact_id: str) -> dict[str, Any]:
        if self.contact is not None:
            return self.contact
        return super().get_contact(contact_id)

    def get_transcript(self, _cdr_id: int | str) -> tuple[dict[str, Any], ...]:
        self.transcript_calls += 1
        if not self.transcript_responses:
            raise BatchDialerTransientError("Transcript still unavailable.")
        response = self.transcript_responses.pop(0)
        if isinstance(response, Exception):
            raise response
        assert isinstance(response, tuple)
        return response


def qualifying_transcript() -> tuple[dict[str, Any], ...]:
    return FakeBatchDialerClient(direct_settings()).get_transcript(12345)


def revised_qualifying_transcript() -> tuple[dict[str, Any], ...]:
    return (
        {
            "time": 1,
            "role": "Speaker 1",
            "text": "Would you like to discuss selling this month?",
        },
        {
            "time": 2,
            "role": "Speaker 2",
            "text": "Yes, I want to sell this month.",
        },
    )


def install_qualification_fakes(monkeypatch: Any, provider: object | None = None) -> None:
    monkeypatch.setattr(
        "app.services.batchdialer_direct.BatchDialerClient",
        (lambda _settings: provider) if provider is not None else FakeBatchDialerClient,
    )
    monkeypatch.setattr(
        "app.services.batchdialer_direct.OpenAIResponsesClient",
        FakeOpenAIResponsesClient,
    )


def test_disposition_mapping_is_exact_and_handles_provider_mojibake() -> None:
    assert classify_disposition("Qualified Seller â€“ Follow Up") == "interested"
    assert classify_disposition("Appointment Set") == "appointment_set"
    assert classify_disposition("Not Interested") == "non_lead"
    assert classify_disposition("Qualified Seller Renamed") == "unknown"


def test_archive_is_idempotent_and_revisions_requeue(db_session: Session) -> None:
    organization = bootstrap_foundation(
        db_session,
        admin_email="owner@example.com",
        admin_name="Owner",
        organization_name="Stonegate Home Buyers",
    ).organization
    now = datetime.now(UTC)
    cdr = sample_cdr("Qualified Seller – Follow Up")

    assert archive_batchdialer_cdr(
        db_session, organization_id=organization.id, cdr=cdr, now=now
    ) == "archived"
    db_session.commit()
    assert archive_batchdialer_cdr(
        db_session, organization_id=organization.id, cdr=cdr, now=now
    ) == "unchanged"
    cdr["comments"] = ["A revised provider note"]
    assert archive_batchdialer_cdr(
        db_session, organization_id=organization.id, cdr=cdr, now=now
    ) == "updated"
    assert db_session.scalar(select(func.count()).select_from(ProspectingProviderEvent)) == 1


def test_new_cdr_revision_invalidates_an_inflight_worker_claim(
    db_session: Session,
) -> None:
    organization = bootstrap_foundation(
        db_session,
        admin_email="owner@example.com",
        admin_name="Owner",
        organization_name="Stonegate Home Buyers",
    ).organization
    cdr = sample_cdr("Qualified Seller â€“ Follow Up")
    archive_batchdialer_cdr(
        db_session,
        organization_id=organization.id,
        cdr=cdr,
        now=datetime.now(UTC),
    )
    db_session.commit()
    event = db_session.scalar(select(ProspectingProviderEvent))
    assert event is not None
    old_hash = event.payload_sha256
    event.processing_status = "processing"
    event.retry_count = 5
    event.payload = {**event.payload, "_stonegate_claim": "old-claim"}
    db_session.commit()

    revised = sample_cdr("Qualified Seller â€“ Follow Up")
    revised["comments"] = ["Provider supplied a newer call observation."]
    assert archive_batchdialer_cdr(
        db_session,
        organization_id=organization.id,
        cdr=revised,
        now=datetime.now(UTC),
    ) == "updated"
    db_session.commit()

    with pytest.raises(BatchDialerClaimLost):
        _lock_claimed_event(
            db_session,
            event_id=event.id,
            claim_token="old-claim",
            claimed_payload_sha256=old_hash,
        )
    db_session.rollback()
    db_session.refresh(event)
    assert event.processing_status == "pending"
    assert event.retry_count == 0
    assert "_stonegate_claim" not in event.payload


def test_poll_stops_on_empty_page_even_when_provider_returns_a_cursor(
    db_session: Session,
    monkeypatch: Any,
) -> None:
    organization = bootstrap_foundation(
        db_session,
        admin_email="owner@example.com",
        admin_name="Owner",
        organization_name="Stonegate Home Buyers",
    ).organization

    class EmptyCursorClient:
        def __init__(self) -> None:
            self.cdr_calls: list[tuple[object, int, str | None]] = []
            self.campaign_calls = 0

        def get_campaigns(self) -> tuple[dict[str, Any], ...]:
            self.campaign_calls += 1
            return ()

        def get_cdr_page(
            self,
            *,
            call_date: object,
            page_length: int,
            next_page: str | None,
        ) -> BatchDialerCDRPage:
            self.cdr_calls.append((call_date, page_length, next_page))
            return BatchDialerCDRPage(items=(), next_page="provider-kept-cursor")

    provider = EmptyCursorClient()
    monkeypatch.setattr(
        "app.services.batchdialer_direct.BatchDialerClient",
        lambda _settings: provider,
    )

    checkpoint_id = poll_batchdialer_direct(
        db_session,
        direct_settings(BATCHDIALER_SCAN_DAYS=1),
    )
    checkpoint = db_session.get(BatchDialerSyncCheckpoint, checkpoint_id)

    assert checkpoint is not None
    assert checkpoint.organization_id == organization.id
    assert checkpoint.status == "healthy"
    assert checkpoint.fetched_cdr_count == 0
    assert checkpoint.archived_event_count == 0
    assert checkpoint.sync_metadata["last_run"]["anomalies"] == [
        f"empty_page_cursor:{provider.cdr_calls[0][0].isoformat()}"
    ]
    assert provider.campaign_calls == 1
    assert len(provider.cdr_calls) == 1
    assert provider.cdr_calls[0][1:] == (100, None)


def test_unknown_disposition_is_quarantined_without_creating_crm_records(
    db_session: Session,
) -> None:
    organization = bootstrap_foundation(
        db_session,
        admin_email="owner@example.com",
        admin_name="Owner",
        organization_name="Stonegate Home Buyers",
    ).organization
    archive_batchdialer_cdr(
        db_session,
        organization_id=organization.id,
        cdr=sample_cdr("Qualified Seller Renamed"),
        now=datetime.now(UTC),
    )
    db_session.commit()

    event_id = process_next_batchdialer_direct_event(db_session, direct_settings())
    event = db_session.get(ProspectingProviderEvent, event_id)

    assert event is not None
    assert event.processing_status == "quarantined"
    assert event.processed_at is not None
    assert "not mapped" in (event.error_message or "")
    assert "cdr" in event.payload
    assert db_session.scalar(select(func.count()).select_from(Lead)) == 0
    assert db_session.scalar(select(func.count()).select_from(CallRecord)) == 0
    assert db_session.scalar(select(func.count()).select_from(Task)) == 0
    assert db_session.scalar(select(func.count()).select_from(ApprovalRequest)) == 1


def test_known_non_lead_is_durably_ignored_without_calling_enrichment_api(
    db_session: Session,
    monkeypatch: Any,
) -> None:
    organization = bootstrap_foundation(
        db_session,
        admin_email="owner@example.com",
        admin_name="Owner",
        organization_name="Stonegate Home Buyers",
    ).organization
    archive_batchdialer_cdr(
        db_session,
        organization_id=organization.id,
        cdr=sample_cdr("Not Interested"),
        now=datetime.now(UTC),
    )
    db_session.commit()

    def unexpected_client(_settings: Settings) -> object:
        raise AssertionError("Non-lead dispositions must not call BatchDialer enrichment APIs.")

    monkeypatch.setattr(
        "app.services.batchdialer_direct.BatchDialerClient",
        unexpected_client,
    )
    event_id = process_next_batchdialer_direct_event(db_session, direct_settings())
    event = db_session.get(ProspectingProviderEvent, event_id)

    assert event is not None
    assert event.processing_status == "processed"
    assert event.error_message is None
    assert event.payload["_stonegate"] == {
        "outcome": "ignored",
        "raw_disposition": "Not Interested",
    }
    assert db_session.scalar(select(func.count()).select_from(Lead)) == 0
    assert db_session.scalar(select(func.count()).select_from(CallRecord)) == 0
    assert db_session.scalar(select(func.count()).select_from(Task)) == 0


def test_qualified_voicemail_id_routes_to_review_without_crm_side_effects(
    db_session: Session,
    api_db_override: None,
    monkeypatch: Any,
) -> None:
    organization = bootstrap_foundation(
        db_session,
        admin_email="owner@example.com",
        admin_name="Owner",
        organization_name="Stonegate Home Buyers",
    ).organization
    provider = ScriptedBatchDialerClient([qualifying_transcript()])
    install_qualification_fakes(monkeypatch, provider)
    cdr = sample_cdr("Qualified Seller – Follow Up")
    cdr["voicemailid"] = 98765
    archive_batchdialer_cdr(
        db_session,
        organization_id=organization.id,
        cdr=cdr,
        now=datetime.now(UTC),
    )
    db_session.commit()

    event_id = process_next_batchdialer_direct_event(db_session, direct_settings())
    event = db_session.get(ProspectingProviderEvent, event_id)
    approval = db_session.scalar(select(ApprovalRequest))

    assert event is not None and event.processing_status == "quarantined"
    assert event.payload["_stonegate"]["qualification"]["reason_code"] == (
        "provider_voicemail_id"
    )
    assert approval is not None and approval.status == "pending"
    assert approval.approval_metadata["reason_code"] == "provider_voicemail_id"
    assert approval.approval_metadata["can_approve"] is False
    assert provider.transcript_calls == 0
    assert db_session.scalar(select(func.count()).select_from(Lead)) == 0
    assert db_session.scalar(select(func.count()).select_from(CallRecord)) == 0
    assert db_session.scalar(select(func.count()).select_from(CallTranscript)) == 0
    assert db_session.scalar(select(func.count()).select_from(AttributionTouch)) == 0

    response = TestClient(app).patch(
        f"/api/v1/approvals/{approval.id}/decision",
        headers={"X-Dev-User-Email": "owner@example.com"},
        json={"status": "approved", "decision_notes": "Override voicemail."},
    )
    assert response.status_code == 422, response.text
    db_session.refresh(approval)
    assert approval.status == "pending"


def test_qualified_voicemail_transcript_cannot_create_lead(
    db_session: Session,
    monkeypatch: Any,
) -> None:
    organization = bootstrap_foundation(
        db_session,
        admin_email="owner@example.com",
        admin_name="Owner",
        organization_name="Stonegate Home Buyers",
    ).organization
    provider = ScriptedBatchDialerClient(
        [
            (
                {
                    "time": 1,
                    "role": "Speaker 1",
                    "text": "You have reached Curtis. Please leave a message after the tone.",
                },
            )
        ]
    )
    install_qualification_fakes(monkeypatch, provider)
    archive_batchdialer_cdr(
        db_session,
        organization_id=organization.id,
        cdr=sample_cdr("Qualified Seller – Follow Up"),
        now=datetime.now(UTC),
    )
    db_session.commit()

    event_id = process_next_batchdialer_direct_event(db_session, direct_settings())
    event = db_session.get(ProspectingProviderEvent, event_id)

    assert event is not None and event.processing_status == "quarantined"
    assert event.payload["_stonegate"]["qualification"]["reason_code"] == (
        "transcript_voicemail"
    )
    assert db_session.scalar(select(func.count()).select_from(ApprovalRequest)) == 1
    assert db_session.scalar(select(func.count()).select_from(Lead)) == 0
    assert db_session.scalar(select(func.count()).select_from(CallRecord)) == 0


def test_transcript_not_ready_retries_without_lead_then_imports_once_available(
    db_session: Session,
    monkeypatch: Any,
) -> None:
    organization = bootstrap_foundation(
        db_session,
        admin_email="owner@example.com",
        admin_name="Owner",
        organization_name="Stonegate Home Buyers",
    ).organization
    provider = ScriptedBatchDialerClient(
        [BatchDialerTransientError("not ready"), qualifying_transcript()]
    )
    install_qualification_fakes(monkeypatch, provider)
    archive_batchdialer_cdr(
        db_session,
        organization_id=organization.id,
        cdr=sample_cdr("Qualified Seller – Follow Up"),
        now=datetime.now(UTC),
    )
    db_session.commit()

    event_id = process_next_batchdialer_direct_event(db_session, direct_settings())
    event = db_session.get(ProspectingProviderEvent, event_id)
    assert event is not None and event.processing_status == "retry"
    assert event.payload["_stonegate"]["qualification_status"] == "pending"
    assert db_session.scalar(select(func.count()).select_from(Lead)) == 0
    assert db_session.scalar(select(func.count()).select_from(ApprovalRequest)) == 0

    event.processing_status = "pending"
    db_session.commit()
    process_next_batchdialer_direct_event(db_session, direct_settings())
    db_session.refresh(event)

    assert event.processing_status == "processed"
    assert event.payload["_stonegate"]["qualification_status"] == "accepted"
    assert provider.transcript_calls == 2
    assert db_session.scalar(select(func.count()).select_from(Lead)) == 1
    assert db_session.scalar(select(func.count()).select_from(CallRecord)) == 1


def test_transcript_exhaustion_creates_visible_review_without_lead(
    db_session: Session,
    api_db_override: None,
    monkeypatch: Any,
) -> None:
    organization = bootstrap_foundation(
        db_session,
        admin_email="owner@example.com",
        admin_name="Owner",
        organization_name="Stonegate Home Buyers",
    ).organization
    provider = ScriptedBatchDialerClient(
        [
            BatchDialerTransientError("not ready"),
            BatchDialerTransientError("still not ready"),
        ]
    )
    install_qualification_fakes(monkeypatch, provider)
    monkeypatch.setattr(
        "app.services.batchdialer_direct.MAX_QUALIFICATION_TRANSCRIPT_ATTEMPTS",
        2,
    )
    archive_batchdialer_cdr(
        db_session,
        organization_id=organization.id,
        cdr=sample_cdr("Qualified Seller – Follow Up"),
        now=datetime.now(UTC),
    )
    db_session.commit()

    event_id = process_next_batchdialer_direct_event(db_session, direct_settings())
    event = db_session.get(ProspectingProviderEvent, event_id)
    assert event is not None and event.processing_status == "retry"
    event.processing_status = "pending"
    db_session.commit()
    process_next_batchdialer_direct_event(db_session, direct_settings())
    db_session.refresh(event)

    approval = db_session.scalar(select(ApprovalRequest))
    assert event.processing_status == "quarantined"
    assert event.payload["_stonegate"]["qualification"]["reason_code"] == (
        "transcript_unavailable"
    )
    assert approval is not None and approval.status == "pending"
    assert db_session.scalar(select(func.count()).select_from(Lead)) == 0

    response = TestClient(app).get(
        "/api/v1/tasks/workspace",
        headers={"X-Dev-User-Email": "owner@example.com"},
    )
    assert response.status_code == 200, response.text
    assert any(
        item["task_type"] == "batchdialer_lead_qualification"
        for item in response.json()["items"]
    )
    review_item = next(
        item
        for item in response.json()["items"]
        if item["task_type"] == "batchdialer_lead_qualification"
    )
    assert review_item["can_decide"] is True
    assert review_item["review_url"] is None
    assert review_item["approval_metadata"]["can_approve"] is False
    assert "cannot be approved" in review_item["approval_metadata"]["approval_effect"]


def test_invalid_ai_evidence_citation_routes_to_review(
    db_session: Session,
    monkeypatch: Any,
) -> None:
    organization = bootstrap_foundation(
        db_session,
        admin_email="owner@example.com",
        admin_name="Owner",
        organization_name="Stonegate Home Buyers",
    ).organization
    monkeypatch.setattr(
        "app.services.batchdialer_direct.BatchDialerClient",
        FakeBatchDialerClient,
    )
    monkeypatch.setattr(
        "app.services.batchdialer_direct.OpenAIResponsesClient",
        InvalidEvidenceOpenAIResponsesClient,
    )
    archive_batchdialer_cdr(
        db_session,
        organization_id=organization.id,
        cdr=sample_cdr("Qualified Seller – Follow Up"),
        now=datetime.now(UTC),
    )
    db_session.commit()

    event_id = process_next_batchdialer_direct_event(db_session, direct_settings())
    event = db_session.get(ProspectingProviderEvent, event_id)

    assert event is not None and event.processing_status == "quarantined"
    assert event.payload["_stonegate"]["qualification"]["reason_code"] == (
        "invalid_classifier_evidence"
    )
    assert db_session.scalar(select(func.count()).select_from(Lead)) == 0


def test_ai_must_cite_two_distinct_conversation_turns(
    db_session: Session,
    monkeypatch: Any,
) -> None:
    organization = bootstrap_foundation(
        db_session,
        admin_email="owner@example.com",
        admin_name="Owner",
        organization_name="Stonegate Home Buyers",
    ).organization
    monkeypatch.setattr(
        "app.services.batchdialer_direct.BatchDialerClient",
        FakeBatchDialerClient,
    )
    monkeypatch.setattr(
        "app.services.batchdialer_direct.OpenAIResponsesClient",
        OneTurnEvidenceOpenAIResponsesClient,
    )
    archive_batchdialer_cdr(
        db_session,
        organization_id=organization.id,
        cdr=sample_cdr("Qualified Seller â€“ Follow Up"),
        now=datetime.now(UTC),
    )
    db_session.commit()

    event_id = process_next_batchdialer_direct_event(db_session, direct_settings())
    event = db_session.get(ProspectingProviderEvent, event_id)

    assert event is not None and event.processing_status == "quarantined"
    assert event.payload["_stonegate"]["qualification"]["reason_code"] == (
        "two_way_conversation_not_supported"
    )
    assert db_session.scalar(select(func.count()).select_from(Lead)) == 0


def test_two_cited_turns_from_one_speaker_do_not_prove_a_live_conversation(
    db_session: Session,
    monkeypatch: Any,
) -> None:
    organization = bootstrap_foundation(
        db_session,
        admin_email="owner@example.com",
        admin_name="Owner",
        organization_name="Stonegate Home Buyers",
    ).organization
    provider = ScriptedBatchDialerClient(
        [
            (
                {
                    "time": 1,
                    "role": "Speaker 1",
                    "text": "Would you like to discuss selling?",
                },
                {
                    "time": 2,
                    "role": "Speaker 1",
                    "text": "I want to sell and I agree to meet Tuesday at 2.",
                },
            )
        ]
    )
    install_qualification_fakes(monkeypatch, provider)
    archive_batchdialer_cdr(
        db_session,
        organization_id=organization.id,
        cdr=sample_cdr("Qualified Seller - Follow Up"),
        now=datetime.now(UTC),
    )
    db_session.commit()

    event_id = process_next_batchdialer_direct_event(db_session, direct_settings())
    event = db_session.get(ProspectingProviderEvent, event_id)

    assert event is not None and event.processing_status == "quarantined"
    assert event.payload["_stonegate"]["qualification"]["reason_code"] == (
        "two_way_conversation_not_supported"
    )
    assert db_session.scalar(select(func.count()).select_from(Lead)) == 0


def test_approved_unknown_disposition_still_has_to_pass_transcript_gate(
    db_session: Session,
    api_db_override: None,
    monkeypatch: Any,
) -> None:
    organization = bootstrap_foundation(
        db_session,
        admin_email="owner@example.com",
        admin_name="Owner",
        organization_name="Stonegate Home Buyers",
    ).organization
    install_qualification_fakes(monkeypatch)
    archive_batchdialer_cdr(
        db_session,
        organization_id=organization.id,
        cdr=sample_cdr("Qualified Seller Renamed"),
        now=datetime.now(UTC),
    )
    db_session.commit()

    event_id = process_next_batchdialer_direct_event(db_session, direct_settings())
    event = db_session.get(ProspectingProviderEvent, event_id)
    approval = db_session.scalar(select(ApprovalRequest))
    assert event is not None and event.processing_status == "quarantined"
    assert approval is not None
    assert approval.approval_metadata["can_approve"] is True

    response = TestClient(app).patch(
        f"/api/v1/approvals/{approval.id}/decision",
        headers={"X-Dev-User-Email": "owner@example.com"},
        json={"status": "approved"},
    )
    assert response.status_code == 422, response.text

    response = TestClient(app).patch(
        f"/api/v1/approvals/{approval.id}/decision",
        headers={"X-Dev-User-Email": "owner@example.com"},
        json={"status": "approved", "decision_notes": "Treat as a seller candidate."},
    )
    assert response.status_code == 200, response.text
    process_next_batchdialer_direct_event(db_session, direct_settings())
    db_session.refresh(event)

    assert event.processing_status == "processed"
    assert event.payload["_stonegate"]["qualification"]["classifier"] != "human_review"
    assert db_session.scalar(select(func.count()).select_from(Lead)) == 1


def test_provider_data_exception_cannot_be_approved_into_a_lead(
    db_session: Session,
    api_db_override: None,
    monkeypatch: Any,
) -> None:
    organization = bootstrap_foundation(
        db_session,
        admin_email="owner@example.com",
        admin_name="Owner",
        organization_name="Stonegate Home Buyers",
    ).organization
    provider = ScriptedBatchDialerClient(
        [],
        contact={
            "id": 44,
            "firstname": "Missing",
            "lastname": "Phone",
            "address": "123 Test Lane",
            "city": "Atlanta",
            "state": "GA",
            "postalcode": "30303",
            "phonenumbers": [],
        },
    )
    install_qualification_fakes(monkeypatch, provider)
    cdr = sample_cdr("Qualified Seller â€“ Follow Up")
    cdr["customerNumber"] = "invalid"
    archive_batchdialer_cdr(
        db_session,
        organization_id=organization.id,
        cdr=cdr,
        now=datetime.now(UTC),
    )
    db_session.commit()

    event_id = process_next_batchdialer_direct_event(db_session, direct_settings())
    event = db_session.get(ProspectingProviderEvent, event_id)
    approval = db_session.scalar(select(ApprovalRequest))
    assert event is not None and event.processing_status == "quarantined"
    assert approval is not None
    assert approval.approval_metadata["reason_code"] == "provider_evidence_invalid"
    assert approval.approval_metadata["can_approve"] is False
    assert "cannot be approved" in approval.approval_metadata["approval_effect"]

    response = TestClient(app).patch(
        f"/api/v1/approvals/{approval.id}/decision",
        headers={"X-Dev-User-Email": "owner@example.com"},
        json={"status": "approved"},
    )
    assert response.status_code == 422, response.text
    db_session.refresh(approval)
    assert approval.status == "pending"
    assert db_session.scalar(select(func.count()).select_from(Lead)) == 0


def test_appointment_set_without_explicit_agreement_routes_to_review(
    db_session: Session,
    monkeypatch: Any,
) -> None:
    organization = bootstrap_foundation(
        db_session,
        admin_email="owner@example.com",
        admin_name="Owner",
        organization_name="Stonegate Home Buyers",
    ).organization
    monkeypatch.setattr(
        "app.services.batchdialer_direct.BatchDialerClient",
        FakeBatchDialerClient,
    )
    monkeypatch.setattr(
        "app.services.batchdialer_direct.OpenAIResponsesClient",
        ReviewOpenAIResponsesClient,
    )
    archive_batchdialer_cdr(
        db_session,
        organization_id=organization.id,
        cdr=sample_cdr("Appointment Set"),
        now=datetime.now(UTC),
    )
    db_session.commit()

    event_id = process_next_batchdialer_direct_event(db_session, direct_settings())
    event = db_session.get(ProspectingProviderEvent, event_id)

    assert event is not None and event.processing_status == "quarantined"
    assert event.payload["_stonegate"]["qualification"]["reason_code"] == (
        "appointment_not_supported"
    )
    assert db_session.scalar(select(func.count()).select_from(ApprovalRequest)) == 1
    assert db_session.scalar(select(func.count()).select_from(Lead)) == 0
    assert db_session.scalar(select(func.count()).select_from(Task)) == 0


def test_out_of_market_zero_duration_call_can_qualify(
    db_session: Session,
    monkeypatch: Any,
) -> None:
    organization = bootstrap_foundation(
        db_session,
        admin_email="owner@example.com",
        admin_name="Owner",
        organization_name="Stonegate Home Buyers",
    ).organization
    provider = ScriptedBatchDialerClient(
        [qualifying_transcript()],
        contact={
            "id": 44,
            "firstname": "Alabama",
            "lastname": "Seller",
            "address": "1215 W 49th St",
            "city": "Anniston",
            "state": "AL",
            "postalcode": "36206",
            "email": "seller@example.com",
            "phonenumber1": "+12565550199",
            "phonenumbers": [{"phonenumber": "+12565550199"}],
        },
    )
    install_qualification_fakes(monkeypatch, provider)
    cdr = sample_cdr("Qualified Seller â€“ Follow Up")
    cdr["duration"] = 0
    cdr["customerNumber"] = "+12565550199"
    archive_batchdialer_cdr(
        db_session,
        organization_id=organization.id,
        cdr=cdr,
        now=datetime.now(UTC),
    )
    db_session.commit()

    event_id = process_next_batchdialer_direct_event(db_session, direct_settings())
    event = db_session.get(ProspectingProviderEvent, event_id)
    property_record = db_session.scalar(select(Property))

    assert event is not None and event.processing_status == "processed"
    assert event.payload["_stonegate"]["qualification_status"] == "accepted"
    assert property_record is not None and property_record.state == "AL"
    assert db_session.scalar(select(CallRecord.duration_seconds)) == 0
    assert db_session.scalar(select(func.count()).select_from(Lead)) == 1


def test_human_approval_is_evidence_bound_and_creates_one_lead(
    db_session: Session,
    api_db_override: None,
    monkeypatch: Any,
) -> None:
    organization = bootstrap_foundation(
        db_session,
        admin_email="owner@example.com",
        admin_name="Owner",
        organization_name="Stonegate Home Buyers",
    ).organization
    provider = ScriptedBatchDialerClient(
        [
            qualifying_transcript(),
            revised_qualifying_transcript(),
            revised_qualifying_transcript(),
        ]
    )
    install_qualification_fakes(monkeypatch, provider)
    monkeypatch.setattr(
        "app.services.batchdialer_direct.OpenAIResponsesClient",
        LowConfidenceOpenAIResponsesClient,
    )
    cdr = sample_cdr("Qualified Seller â€“ Follow Up")
    archive_batchdialer_cdr(
        db_session,
        organization_id=organization.id,
        cdr=cdr,
        now=datetime.now(UTC),
    )
    db_session.commit()

    event_id = process_next_batchdialer_direct_event(db_session, direct_settings())
    event = db_session.get(ProspectingProviderEvent, event_id)
    approval = db_session.scalar(select(ApprovalRequest))
    assert event is not None and event.processing_status == "quarantined"
    assert approval is not None and approval.status == "pending"
    assert approval.approval_metadata["reason_code"] == "qualification_low_confidence"
    assert approval.approval_metadata["can_approve"] is True

    response = TestClient(app).patch(
        f"/api/v1/approvals/{approval.id}/decision",
        headers={"X-Dev-User-Email": "owner@example.com"},
        json={"status": "approved", "decision_notes": "Confirmed by staff."},
    )
    assert response.status_code == 200, response.text
    db_session.refresh(event)
    assert event.processing_status == "pending"

    process_next_batchdialer_direct_event(db_session, direct_settings())
    db_session.refresh(event)

    assert event.processing_status == "quarantined"
    assert db_session.scalar(select(func.count()).select_from(Lead)) == 0
    replacement = db_session.scalar(
        select(ApprovalRequest).where(ApprovalRequest.status == "pending")
    )
    assert replacement is not None and replacement.id != approval.id
    assert replacement.approval_metadata["reason_code"] == (
        "evidence_changed_after_review"
    )

    replacement_response = TestClient(app).patch(
        f"/api/v1/approvals/{replacement.id}/decision",
        headers={"X-Dev-User-Email": "owner@example.com"},
        json={"status": "approved", "decision_notes": "Reviewed current transcript."},
    )
    assert replacement_response.status_code == 200, replacement_response.text
    process_next_batchdialer_direct_event(db_session, direct_settings())
    db_session.refresh(event)

    assert event.processing_status == "processed"
    assert event.payload["_stonegate"]["qualification"]["classifier"] == "human_review"
    assert db_session.scalar(select(func.count()).select_from(Lead)) == 1
    assert db_session.scalar(select(func.count()).select_from(CallRecord)) == 1


def test_qualified_follow_up_creates_lead_call_and_transcript_without_appointment_task(
    db_session: Session,
    monkeypatch: Any,
) -> None:
    organization = bootstrap_foundation(
        db_session,
        admin_email="owner@example.com",
        admin_name="Owner",
        organization_name="Stonegate Home Buyers",
    ).organization
    install_qualification_fakes(monkeypatch)
    archive_batchdialer_cdr(
        db_session,
        organization_id=organization.id,
        cdr=sample_cdr("Qualified Seller â€“ Follow Up"),
        now=datetime.now(UTC),
    )
    db_session.commit()

    event_id = process_next_batchdialer_direct_event(db_session, direct_settings())
    event = db_session.get(ProspectingProviderEvent, event_id)

    assert event is not None and event.processing_status == "processed"
    assert event.payload["_stonegate"]["outcome"] == "interested"
    assert event.payload["_stonegate"]["created_lead"] is True
    assert db_session.scalar(select(func.count()).select_from(Lead)) == 1
    assert db_session.scalar(select(func.count()).select_from(CallRecord)) == 1
    assert db_session.scalar(select(func.count()).select_from(CommunicationRecord)) == 1
    assert db_session.scalar(select(func.count()).select_from(CallRecording)) == 1
    assert db_session.scalar(select(func.count()).select_from(CallTranscript)) == 1
    assert db_session.scalar(select(func.count()).select_from(AttributionTouch)) == 1
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(Task)
            .where(Task.task_type == "batchdialer_manual_appointment")
        )
        == 0
    )
    assert db_session.scalar(select(func.count()).select_from(ConsentRecord)) == 0


def test_appointment_handoff_creates_one_lead_call_transcript_and_manual_task(
    db_session: Session,
    monkeypatch: Any,
) -> None:
    organization = bootstrap_foundation(
        db_session,
        admin_email="owner@example.com",
        admin_name="Owner",
        organization_name="Stonegate Home Buyers",
    ).organization
    install_qualification_fakes(monkeypatch)
    now = datetime.now(UTC)
    archive_batchdialer_cdr(
        db_session,
        organization_id=organization.id,
        cdr=sample_cdr("Appointment Set"),
        now=now,
    )
    db_session.commit()
    event = db_session.scalar(select(ProspectingProviderEvent))
    assert event is not None

    process_next_batchdialer_direct_event(db_session, direct_settings())
    db_session.refresh(event)

    assert event.processing_status == "processed"
    assert event.payload["_stonegate"]["outcome"] == "appointment_set"
    assert db_session.scalar(select(func.count()).select_from(Lead)) == 1
    assert db_session.scalar(select(func.count()).select_from(CallRecord)) == 1
    assert db_session.scalar(select(func.count()).select_from(CommunicationRecord)) == 1
    assert db_session.scalar(select(func.count()).select_from(CallRecording)) == 1
    assert db_session.scalar(select(func.count()).select_from(CallTranscript)) == 1
    assert db_session.scalar(select(func.count()).select_from(Appointment)) == 0
    task = db_session.scalar(
        select(Task).where(Task.task_type == "batchdialer_manual_appointment")
    )
    assert task is not None and task.priority == "urgent" and task.status == "open"
    assert db_session.scalar(select(func.count()).select_from(ConsentRecord)) == 0

    revised = sample_cdr("Appointment Set")
    revised["comments"] = ["The agreed appointment still needs manual calendar entry."]
    assert archive_batchdialer_cdr(
        db_session,
        organization_id=organization.id,
        cdr=revised,
        now=datetime.now(UTC),
    ) == "updated"
    db_session.commit()
    process_next_batchdialer_direct_event(db_session, direct_settings())
    db_session.refresh(event)

    assert event.processing_status == "processed"
    assert event.payload["_stonegate"]["created_lead"] is False
    assert db_session.scalar(select(func.count()).select_from(Lead)) == 1
    assert db_session.scalar(select(func.count()).select_from(CallRecord)) == 1
    assert db_session.scalar(select(func.count()).select_from(CommunicationRecord)) == 1
    assert db_session.scalar(select(func.count()).select_from(CallRecording)) == 1
    assert db_session.scalar(select(func.count()).select_from(CallTranscript)) == 1
    assert db_session.scalar(select(func.count()).select_from(AttributionTouch)) == 1
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(Task)
            .where(Task.task_type == "batchdialer_manual_appointment")
        )
        == 1
    )


def test_active_manual_appointment_clears_batchdialer_task_but_cancelled_one_does_not(
    db_session: Session,
    api_db_override: None,
    monkeypatch: Any,
) -> None:
    organization = bootstrap_foundation(
        db_session,
        admin_email="owner@example.com",
        admin_name="Owner",
        organization_name="Stonegate Home Buyers",
    ).organization
    install_qualification_fakes(monkeypatch)
    archive_batchdialer_cdr(
        db_session,
        organization_id=organization.id,
        cdr=sample_cdr("Appointment Set"),
        now=datetime.now(UTC),
    )
    db_session.commit()
    process_next_batchdialer_direct_event(db_session, direct_settings())
    lead = db_session.scalar(select(Lead))
    task = db_session.scalar(
        select(Task).where(Task.task_type == "batchdialer_manual_appointment")
    )
    assert lead is not None and task is not None
    assert lead.qualification_context["batchdialer_appointment_pending_entry"] is True

    client = TestClient(app)
    cancelled_response = client.post(
        f"/api/v1/leads/{lead.id}/appointments",
        headers={"X-Dev-User-Email": "owner@example.com"},
        json={
            "appointment_type": "seller_call",
            "status": "cancelled",
            "scheduled_start_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            "location_type": "phone",
        },
    )
    assert cancelled_response.status_code == 201, cancelled_response.text
    db_session.refresh(task)
    db_session.refresh(lead)
    assert task.status == "open"
    assert lead.qualification_context["batchdialer_appointment_pending_entry"] is True

    scheduled_response = client.post(
        f"/api/v1/leads/{lead.id}/appointments",
        headers={"X-Dev-User-Email": "owner@example.com"},
        json={
            "appointment_type": "seller_call",
            "status": "scheduled",
            "scheduled_start_at": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
            "location_type": "phone",
        },
    )
    assert scheduled_response.status_code == 201, scheduled_response.text
    db_session.refresh(task)
    db_session.refresh(lead)
    assert task.status == "completed"
    assert task.outcome == "appointment_entered"
    assert "batchdialer_appointment_pending_entry" not in lead.qualification_context


def sample_cdr(disposition: str) -> dict[str, Any]:
    return {
        "id": 12345,
        "direction": "out",
        "callStartTime": "2026-08-18T17:00:00Z",
        "callEndTime": "2026-08-18T17:03:00Z",
        "did": "+16785550100",
        "customerNumber": "+16785550199",
        "disposition": disposition,
        "duration": 180,
        "status": "completed",
        "callid": "provider-call-12345",
        "comments": ["Seller asked for a follow-up."],
        "agent": {"id": 7, "firstname": "VA", "lastname": "Agent"},
        "contact": {
            "id": 44,
            "firstname": "Test",
            "lastname": "Seller",
            "state": "GA",
            "email": "seller@example.com",
        },
        "campaign": {"id": 88, "name": "Georgia Distressed Homeowners"},
    }


def direct_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "BATCHDIALER_API_KEY": "test-key-that-is-long-enough",
        "BATCHDIALER_HTTP_MAX_ATTEMPTS": 1,
        "AI_ENABLED": True,
        "OPENAI_API_KEY": "test-openai-key",
    }
    values.update(overrides)
    return Settings.model_validate(values)
