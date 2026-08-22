from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.integrations.batchdialer_client import BatchDialerCDRPage
from app.main import app
from app.models.foundation import (
    Appointment,
    AttributionTouch,
    BatchDialerSyncCheckpoint,
    CallRecord,
    CallRecording,
    CallTranscript,
    CommunicationRecord,
    ConsentRecord,
    Lead,
    ProspectingProviderEvent,
    Task,
)
from app.services.batchdialer_direct import (
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
            {"time": 1, "role": "agent", "text": "What makes you want to sell?"},
            {"time": 2, "role": "seller", "text": "I need to move soon."},
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
    monkeypatch.setattr(
        "app.services.batchdialer_direct.BatchDialerClient",
        FakeBatchDialerClient,
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
    monkeypatch.setattr(
        "app.services.batchdialer_direct.BatchDialerClient",
        FakeBatchDialerClient,
    )
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
    monkeypatch.setattr(
        "app.services.batchdialer_direct.BatchDialerClient",
        FakeBatchDialerClient,
    )
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
    }
    values.update(overrides)
    return Settings.model_validate(values)
