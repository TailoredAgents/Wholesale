from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.main import app
from app.models.foundation import (
    Appointment,
    AuditEvent,
    BatchDialerAgentIdentity,
    BatchDialerCallFact,
    BatchDialerSyncCheckpoint,
    Contact,
    Deal,
    Lead,
    Property,
    Transaction,
    User,
)
from app.services.batchdialer_direct import archive_batchdialer_cdr
from app.services.bootstrap import bootstrap_foundation

OWNER_EMAIL = "batchdialer-performance-owner@example.com"


def test_va_performance_separates_candidates_verified_and_evidence_failures(
    db_session: Session,
    api_db_override: None,
) -> None:
    foundation = bootstrap_foundation(
        db_session,
        organization_name="BatchDialer Performance Workspace",
        admin_email=OWNER_EMAIL,
        admin_name="Performance Owner",
    )
    observed_at = datetime(2026, 8, 18, 15, 0, tzinfo=UTC)
    for offset, disposition in enumerate(
        ("Qualified Seller - Follow Up", "Not Interested", "No Answer")
    ):
        assert (
            archive_batchdialer_cdr(
                db_session,
                organization_id=foundation.organization.id,
                cdr=_cdr(8000 + offset, disposition, observed_at + timedelta(minutes=offset * 3)),
                now=observed_at + timedelta(minutes=offset * 3 + 1),
            )
            == "archived"
        )
    db_session.commit()
    facts = list(
        db_session.scalars(
            select(BatchDialerCallFact).order_by(BatchDialerCallFact.provider_cdr_id)
        ).all()
    )
    assert len(facts) == 3
    facts[0].final_outcome = "needs_review"
    facts[0].final_qualification_status = "needs_review"
    facts[0].final_processing_status = "quarantined"
    facts[1].final_outcome = "ignored"
    facts[1].final_qualification_status = "not_candidate"
    facts[1].final_processing_status = "processed"
    facts[2].final_outcome = "ignored"
    facts[2].final_qualification_status = "not_candidate"
    facts[2].final_processing_status = "processed"
    facts[2].duration_seconds = None
    facts[2].provider_contact_id = None
    db_session.commit()

    client = TestClient(app)
    response = client.get(
        "/api/v1/prospecting/batchdialer/va-performance",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        params={"date_from": "2026-08-18", "date_to": "2026-08-18"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "private, no-store"
    payload = cast(dict[str, Any], response.json())
    assert payload["summary"]["calls"] == 3
    assert payload["summary"]["unique_contacts"] == 2
    assert payload["summary"]["identified_contact_calls"] == 2
    assert payload["summary"]["identified_contact_coverage_basis_points"] == 6_667
    assert payload["summary"]["human_contacts"] == 2
    assert payload["summary"]["qualified_candidates"] == 1
    assert payload["summary"]["evidence_accepted_candidates"] == 0
    assert payload["summary"]["verified_handoffs"] == 0
    assert payload["summary"]["qualification_false_positives"] == 1
    assert payload["summary"]["not_interested"] == 1
    assert payload["summary"]["no_answers"] == 1
    assert payload["summary"]["recorded_duration_calls"] == 2
    assert payload["summary"]["recorded_duration_coverage_basis_points"] == 6_667
    assert payload["summary"]["recorded_call_seconds"] == 180
    assert payload["summary"]["average_recorded_call_seconds"] == 90
    assert payload["summary"]["inferred_calling_minutes"] is not None
    assert payload["earliest_archived_call_at"] is not None
    assert payload["archive_history_status"] == "selected_range_may_be_incomplete"
    assert payload["provider_scan_window_days"] == 2
    assert len(payload["agents"]) == 1
    assert payload["agents"][0]["provider_agent_name"] == "VA One"
    assert payload["agents"][0]["user_id"] is None
    assert any("timeclock" in warning for warning in payload["coverage_warnings"])
    assert any("lack provider duration" in warning for warning in payload["coverage_warnings"])
    assert any("lack a provider contact ID" in warning for warning in payload["coverage_warnings"])
    assert any("rolling 2-day" in warning for warning in payload["coverage_warnings"])


def test_va_performance_discloses_when_selected_history_predates_archive(
    db_session: Session,
    api_db_override: None,
) -> None:
    foundation = bootstrap_foundation(
        db_session,
        organization_name="BatchDialer Coverage Workspace",
        admin_email=OWNER_EMAIL,
        admin_name="Performance Owner",
    )
    observed_at = datetime(2026, 8, 18, 15, 0, tzinfo=UTC)
    archive_batchdialer_cdr(
        db_session,
        organization_id=foundation.organization.id,
        cdr=_cdr(8050, "Not Interested", observed_at),
        now=observed_at,
    )
    db_session.commit()

    response = TestClient(app).get(
        "/api/v1/prospecting/batchdialer/va-performance",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        params={"date_from": "2026-08-01", "date_to": "2026-08-18"},
    )

    assert response.status_code == 200, response.text
    payload = cast(dict[str, Any], response.json())
    assert payload["archive_history_status"] == "selected_range_may_be_incomplete"
    assert payload["earliest_archived_call_at"].startswith("2026-08-18T15:00:00")
    assert any(
        "Earlier dates may be incomplete rather than zero" in warning
        for warning in payload["coverage_warnings"]
    )


def test_va_performance_accepts_earliest_supported_date_without_overflow(
    db_session: Session,
    api_db_override: None,
) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="BatchDialer Earliest Date Workspace",
        admin_email=OWNER_EMAIL,
        admin_name="Performance Owner",
    )

    response = TestClient(app).get(
        "/api/v1/prospecting/batchdialer/va-performance",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        params={"date_to": "0001-01-01"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["date_from"] == "0001-01-01"
    assert response.json()["date_to"] == "0001-01-01"


def test_va_performance_marks_stale_provider_sync_coverage_incomplete(
    db_session: Session,
    api_db_override: None,
) -> None:
    foundation = bootstrap_foundation(
        db_session,
        organization_name="BatchDialer Stale Sync Workspace",
        admin_email=OWNER_EMAIL,
        admin_name="Performance Owner",
    )
    observed_at = datetime.now(UTC) - timedelta(minutes=10)
    archive_batchdialer_cdr(
        db_session,
        organization_id=foundation.organization.id,
        cdr=_cdr(8059, "Not Interested", observed_at - timedelta(days=1)),
        now=observed_at - timedelta(days=1),
    )
    archive_batchdialer_cdr(
        db_session,
        organization_id=foundation.organization.id,
        cdr=_cdr(8060, "Not Interested", observed_at),
        now=observed_at,
    )
    db_session.add(
        BatchDialerSyncCheckpoint(
            organization_id=foundation.organization.id,
            stream="cdrs",
            status="healthy",
            last_success_at=observed_at,
        )
    )
    db_session.commit()

    response = TestClient(app).get(
        "/api/v1/prospecting/batchdialer/va-performance",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        params={
            "date_from": observed_at.date().isoformat(),
            "date_to": observed_at.date().isoformat(),
        },
    )

    assert response.status_code == 200, response.text
    payload = cast(dict[str, Any], response.json())
    assert payload["provider_sync_status"] == "healthy"
    assert payload["provider_sync_freshness"] == "stale"
    assert payload["provider_sync_last_success_at"] is not None
    assert payload["provider_sync_error_present"] is False
    assert payload["provider_sync_poll_interval_seconds"] == 120
    assert payload["archive_history_status"] == "selected_range_may_be_incomplete"
    assert any(
        "more than two configured poll intervals old" in warning
        for warning in payload["coverage_warnings"]
    )
    assert not any(
        "selected range begins before the earliest call" in warning
        for warning in payload["coverage_warnings"]
    )


def test_va_performance_sanitizes_failed_provider_sync_error(
    db_session: Session,
    api_db_override: None,
) -> None:
    foundation = bootstrap_foundation(
        db_session,
        organization_name="BatchDialer Failed Sync Workspace",
        admin_email=OWNER_EMAIL,
        admin_name="Performance Owner",
    )
    observed_at = datetime.now(UTC) - timedelta(minutes=1)
    archive_batchdialer_cdr(
        db_session,
        organization_id=foundation.organization.id,
        cdr=_cdr(8061, "Not Interested", observed_at),
        now=observed_at,
    )
    private_provider_error = "provider response contained secret diagnostics"
    db_session.add(
        BatchDialerSyncCheckpoint(
            organization_id=foundation.organization.id,
            stream="cdrs",
            status="failed",
            last_success_at=observed_at,
            last_error=private_provider_error,
        )
    )
    db_session.commit()

    response = TestClient(app).get(
        "/api/v1/prospecting/batchdialer/va-performance",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )

    assert response.status_code == 200, response.text
    payload = cast(dict[str, Any], response.json())
    assert payload["provider_sync_status"] == "failed"
    assert payload["provider_sync_freshness"] == "incomplete"
    assert payload["provider_sync_error_present"] is True
    assert private_provider_error not in response.text
    assert "last_error" not in payload
    assert payload["archive_history_status"] == "selected_range_may_be_incomplete"
    assert any("failed/error state" in warning for warning in payload["coverage_warnings"])


def test_va_performance_marks_in_progress_provider_poll_incomplete(
    db_session: Session,
    api_db_override: None,
) -> None:
    foundation = bootstrap_foundation(
        db_session,
        organization_name="BatchDialer Polling Sync Workspace",
        admin_email=OWNER_EMAIL,
        admin_name="Performance Owner",
    )
    observed_at = datetime.now(UTC) - timedelta(seconds=10)
    archive_batchdialer_cdr(
        db_session,
        organization_id=foundation.organization.id,
        cdr=_cdr(8062, "Not Interested", observed_at),
        now=observed_at,
    )
    db_session.add(
        BatchDialerSyncCheckpoint(
            organization_id=foundation.organization.id,
            stream="cdrs",
            status="polling",
            last_success_at=observed_at,
        )
    )
    db_session.commit()

    response = TestClient(app).get(
        "/api/v1/prospecting/batchdialer/va-performance",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        params={
            "date_from": observed_at.date().isoformat(),
            "date_to": observed_at.date().isoformat(),
        },
    )

    assert response.status_code == 200, response.text
    payload = cast(dict[str, Any], response.json())
    assert payload["provider_sync_status"] == "polling"
    assert payload["provider_sync_freshness"] == "incomplete"
    assert payload["archive_history_status"] == "selected_range_may_be_incomplete"
    assert any("incomplete" in warning.casefold() for warning in payload["coverage_warnings"])


def test_agent_mapping_is_explicit_tenant_scoped_and_manager_only(
    db_session: Session,
    api_db_override: None,
) -> None:
    foundation = bootstrap_foundation(
        db_session,
        organization_name="BatchDialer Mapping Workspace",
        admin_email=OWNER_EMAIL,
        admin_name="Performance Owner",
    )
    observed_at = datetime(2026, 8, 18, 15, 0, tzinfo=UTC)
    archive_batchdialer_cdr(
        db_session,
        organization_id=foundation.organization.id,
        cdr=_cdr(9001, "Not Interested", observed_at),
        now=observed_at,
    )
    db_session.commit()
    identity = db_session.scalar(select(BatchDialerAgentIdentity))
    assert identity is not None

    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    before = client.get(
        "/api/v1/prospecting/batchdialer/agent-mappings",
        headers=headers,
    )
    assert before.status_code == 200, before.text
    assert before.headers["Cache-Control"] == "private, no-store"
    assert before.json()["items"][0]["user_id"] is None

    mapped = client.patch(
        f"/api/v1/prospecting/batchdialer/agent-mappings/{identity.id}",
        headers=headers,
        json={"user_id": str(foundation.admin_user.id)},
    )
    assert mapped.status_code == 200, mapped.text
    assert mapped.json()["user_id"] == str(foundation.admin_user.id)
    assert mapped.json()["user_name"] == "Performance Owner"

    caller = client.post(
        "/api/v1/operations/users",
        headers=headers,
        json={
            "email": "batchdialer-caller@example.com",
            "display_name": "Caller",
            "role_key": "prospecting_caller",
        },
    )
    assert caller.status_code == 201, caller.text
    forbidden = client.get(
        "/api/v1/prospecting/batchdialer/agent-mappings",
        headers={"X-Dev-User-Email": "batchdialer-caller@example.com"},
    )
    assert forbidden.status_code == 403


def test_agent_mapping_rejects_a_second_provider_identity_for_the_same_user(
    db_session: Session,
    api_db_override: None,
) -> None:
    foundation = bootstrap_foundation(
        db_session,
        organization_name="BatchDialer Unique Mapping Workspace",
        admin_email=OWNER_EMAIL,
        admin_name="Performance Owner",
    )
    observed_at = datetime(2026, 8, 18, 15, 0, tzinfo=UTC)
    for cdr_id, agent_id, agent_name in (
        (9101, 701, "VA One"),
        (9102, 702, "VA Two"),
    ):
        archive_batchdialer_cdr(
            db_session,
            organization_id=foundation.organization.id,
            cdr=_cdr(
                cdr_id,
                "Not Interested",
                observed_at,
                agent_id=agent_id,
                agent_name=agent_name,
            ),
            now=observed_at,
        )
    db_session.commit()
    identities = list(
        db_session.scalars(
            select(BatchDialerAgentIdentity).order_by(
                BatchDialerAgentIdentity.provider_agent_id
            )
        ).all()
    )
    assert len(identities) == 2

    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    first = client.patch(
        f"/api/v1/prospecting/batchdialer/agent-mappings/{identities[0].id}",
        headers=headers,
        json={"user_id": str(foundation.admin_user.id)},
    )
    assert first.status_code == 200, first.text
    duplicate = client.patch(
        f"/api/v1/prospecting/batchdialer/agent-mappings/{identities[1].id}",
        headers=headers,
        json={"user_id": str(foundation.admin_user.id)},
    )
    assert duplicate.status_code == 422, duplicate.text
    assert "already mapped" in duplicate.json()["detail"]


def test_agent_mapping_audits_set_change_and_clear_but_not_noop(
    db_session: Session,
    api_db_override: None,
) -> None:
    foundation = bootstrap_foundation(
        db_session,
        organization_name="BatchDialer Mapping Audit Workspace",
        admin_email=OWNER_EMAIL,
        admin_name="Performance Owner",
    )
    observed_at = datetime(2026, 8, 18, 15, 0, tzinfo=UTC)
    archive_batchdialer_cdr(
        db_session,
        organization_id=foundation.organization.id,
        cdr=_cdr(9151, "Not Interested", observed_at),
        now=observed_at,
    )
    db_session.commit()
    identity = db_session.scalar(select(BatchDialerAgentIdentity))
    assert identity is not None

    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    caller = client.post(
        "/api/v1/operations/users",
        headers=headers,
        json={
            "email": "batchdialer-mapped-caller@example.com",
            "display_name": "Mapped Caller",
            "role_key": "prospecting_caller",
        },
    )
    assert caller.status_code == 201, caller.text
    caller_id = caller.json()["id"]

    mapping_url = f"/api/v1/prospecting/batchdialer/agent-mappings/{identity.id}"
    set_response = client.patch(
        mapping_url,
        headers=headers,
        json={"user_id": str(foundation.admin_user.id)},
    )
    assert set_response.status_code == 200, set_response.text
    db_session.expire_all()
    mapped_at = db_session.get(BatchDialerAgentIdentity, identity.id).mapped_at

    noop_response = client.patch(
        mapping_url,
        headers=headers,
        json={"user_id": str(foundation.admin_user.id)},
    )
    assert noop_response.status_code == 200, noop_response.text
    db_session.expire_all()
    assert db_session.get(BatchDialerAgentIdentity, identity.id).mapped_at == mapped_at

    change_response = client.patch(
        mapping_url,
        headers=headers,
        json={"user_id": caller_id},
    )
    assert change_response.status_code == 200, change_response.text
    clear_response = client.patch(
        mapping_url,
        headers=headers,
        json={"user_id": None},
    )
    assert clear_response.status_code == 200, clear_response.text
    assert clear_response.json()["user_id"] is None

    audit_events = list(
        db_session.scalars(
            select(AuditEvent).where(
                AuditEvent.organization_id == foundation.organization.id,
                AuditEvent.entity_type == "batchdialer_agent_identity",
                AuditEvent.entity_id == identity.id,
            )
        ).all()
    )
    assert len(audit_events) == 3
    assert all(event.actor_user_id == foundation.admin_user.id for event in audit_events)
    assert all(event.actor_type == "user" for event in audit_events)
    by_action = {event.action: event for event in audit_events}
    set_event = by_action["prospecting.batchdialer_agent_mapping_set"]
    change_event = by_action["prospecting.batchdialer_agent_mapping_changed"]
    clear_event = by_action["prospecting.batchdialer_agent_mapping_cleared"]

    assert set_event.previous_value == {
        "provider_agent_id": identity.provider_agent_id,
        "mapped_user_id": None,
    }
    assert set_event.new_value == {
        "provider_agent_id": identity.provider_agent_id,
        "mapped_user_id": str(foundation.admin_user.id),
    }
    assert change_event.previous_value["mapped_user_id"] == str(foundation.admin_user.id)
    assert change_event.new_value["mapped_user_id"] == caller_id
    assert clear_event.previous_value["mapped_user_id"] == caller_id
    assert clear_event.new_value["mapped_user_id"] is None

    serialized_audit = " ".join(
        str((event.previous_value, event.new_value, event.reason)) for event in audit_events
    ).casefold()
    assert OWNER_EMAIL.casefold() not in serialized_audit
    assert "mapped caller" not in serialized_audit


def test_agent_mapping_cross_tenant_attempt_is_not_found_and_not_audited(
    db_session: Session,
    api_db_override: None,
) -> None:
    first = bootstrap_foundation(
        db_session,
        organization_name="BatchDialer First Mapping Workspace",
        admin_email=OWNER_EMAIL,
        admin_name="Performance Owner",
    )
    observed_at = datetime(2026, 8, 18, 15, 0, tzinfo=UTC)
    archive_batchdialer_cdr(
        db_session,
        organization_id=first.organization.id,
        cdr=_cdr(9152, "Not Interested", observed_at),
        now=observed_at,
    )
    second = bootstrap_foundation(
        db_session,
        organization_name="BatchDialer Second Mapping Workspace",
        admin_email="batchdialer-second-owner@example.com",
        admin_name="Second Owner",
    )
    db_session.commit()
    identity = db_session.scalar(
        select(BatchDialerAgentIdentity).where(
            BatchDialerAgentIdentity.organization_id == first.organization.id
        )
    )
    assert identity is not None

    response = TestClient(app).patch(
        f"/api/v1/prospecting/batchdialer/agent-mappings/{identity.id}",
        headers={"X-Dev-User-Email": second.admin_user.email},
        json={"user_id": str(second.admin_user.id)},
    )

    assert response.status_code == 404, response.text
    audit_count = len(
        list(
            db_session.scalars(
                select(AuditEvent).where(
                    AuditEvent.entity_type == "batchdialer_agent_identity",
                    AuditEvent.entity_id == identity.id,
                )
            ).all()
        )
    )
    assert audit_count == 0


def test_agent_mapping_keeps_current_inactive_user_visible_and_clearable(
    db_session: Session,
    api_db_override: None,
) -> None:
    foundation = bootstrap_foundation(
        db_session,
        organization_name="BatchDialer Inactive Mapping Workspace",
        admin_email=OWNER_EMAIL,
        admin_name="Performance Owner",
    )
    observed_at = datetime(2026, 8, 18, 15, 0, tzinfo=UTC)
    archive_batchdialer_cdr(
        db_session,
        organization_id=foundation.organization.id,
        cdr=_cdr(9153, "Not Interested", observed_at),
        now=observed_at,
    )
    db_session.commit()
    identity = db_session.scalar(select(BatchDialerAgentIdentity))
    assert identity is not None
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    created = client.post(
        "/api/v1/operations/users",
        headers=headers,
        json={
            "email": "inactive-batchdialer-va@example.com",
            "display_name": "Inactive VA",
            "role_key": "prospecting_caller",
        },
    )
    assert created.status_code == 201, created.text
    mapped_user_id = UUID(created.json()["id"])
    mapping_url = f"/api/v1/prospecting/batchdialer/agent-mappings/{identity.id}"
    mapped = client.patch(
        mapping_url,
        headers=headers,
        json={"user_id": str(mapped_user_id)},
    )
    assert mapped.status_code == 200, mapped.text

    mapped_user = db_session.get(User, mapped_user_id)
    assert mapped_user is not None
    mapped_user.is_active = False
    db_session.commit()

    listed = client.get(
        "/api/v1/prospecting/batchdialer/agent-mappings",
        headers=headers,
    )
    assert listed.status_code == 200, listed.text
    payload = listed.json()
    assert payload["items"][0]["user_name"] == "Inactive VA"
    inactive_option = next(
        user for user in payload["users"] if user["id"] == str(mapped_user_id)
    )
    assert inactive_option == {
        "id": str(mapped_user_id),
        "name": "Inactive VA",
        "email": "inactive-batchdialer-va@example.com",
        "is_active": False,
    }

    # Saving an unchanged historical mapping remains a no-op, while clearing it
    # remains available to an active manager.
    noop = client.patch(
        mapping_url,
        headers=headers,
        json={"user_id": str(mapped_user_id)},
    )
    assert noop.status_code == 200, noop.text
    cleared = client.patch(mapping_url, headers=headers, json={"user_id": None})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["user_id"] is None


def test_downstream_outcomes_only_credit_original_handoff_and_later_records(
    db_session: Session,
    api_db_override: None,
) -> None:
    foundation = bootstrap_foundation(
        db_session,
        organization_name="BatchDialer Attribution Workspace",
        admin_email=OWNER_EMAIL,
        admin_name="Performance Owner",
    )
    organization_id = foundation.organization.id
    original_at = datetime(2026, 8, 18, 15, 0, tzinfo=UTC)
    repeat_at = original_at + timedelta(hours=2)
    for cdr_id, agent_id, agent_name, occurred_at in (
        (9201, 701, "VA Original", original_at),
        (9202, 702, "VA Repeat", repeat_at),
    ):
        archive_batchdialer_cdr(
            db_session,
            organization_id=organization_id,
            cdr=_cdr(
                cdr_id,
                "Qualified Seller - Follow Up",
                occurred_at,
                agent_id=agent_id,
                agent_name=agent_name,
            ),
            now=occurred_at,
        )
    contact = Contact(
        organization_id=organization_id,
        legal_name="Attribution Seller",
        preferred_name=None,
        contact_type="seller",
        assigned_user_id=foundation.admin_user.id,
    )
    property_record = Property(
        organization_id=organization_id,
        street_address="100 Attribution Way",
        city="Atlanta",
        state="GA",
        postal_code="30303",
    )
    db_session.add_all([contact, property_record])
    db_session.flush()
    lead = Lead(
        organization_id=organization_id,
        contact_id=contact.id,
        property_id=property_record.id,
        assigned_user_id=foundation.admin_user.id,
        source="BatchDialer",
        asset_class="house",
        qualification_context={},
        stage_key="new",
    )
    db_session.add(lead)
    db_session.flush()
    deal = Deal(
        organization_id=organization_id,
        lead_id=lead.id,
        property_id=property_record.id,
        stage_key="active",
    )
    db_session.add(deal)
    db_session.flush()

    before_appointment = Appointment(
        organization_id=organization_id,
        lead_id=lead.id,
        contact_id=contact.id,
        property_id=property_record.id,
        owner_user_id=foundation.admin_user.id,
        appointment_type="acquisition_consultation",
        status="held",
        scheduled_start_at=original_at,
        location_type="seller_property",
        created_at=original_at - timedelta(hours=1),
    )
    after_appointment = Appointment(
        organization_id=organization_id,
        lead_id=lead.id,
        contact_id=contact.id,
        property_id=property_record.id,
        owner_user_id=foundation.admin_user.id,
        appointment_type="acquisition_consultation",
        status="held",
        scheduled_start_at=original_at + timedelta(days=1),
        location_type="seller_property",
        created_at=original_at + timedelta(minutes=30),
    )
    second_after_appointment = Appointment(
        organization_id=organization_id,
        lead_id=lead.id,
        contact_id=contact.id,
        property_id=property_record.id,
        owner_user_id=foundation.admin_user.id,
        appointment_type="acquisition_consultation",
        status="scheduled",
        scheduled_start_at=original_at + timedelta(days=3),
        location_type="seller_property",
        created_at=original_at + timedelta(hours=1),
    )
    before_transaction = Transaction(
        organization_id=organization_id,
        deal_id=deal.id,
        lead_id=lead.id,
        property_id=property_record.id,
        contact_id=contact.id,
        owner_user_id=foundation.admin_user.id,
        status="closed",
        contract_type="assignment",
        purchase_price_cents=10_000_000,
        contract_executed_at=original_at - timedelta(minutes=30),
        closed_at=original_at - timedelta(minutes=15),
        created_at=original_at - timedelta(hours=1),
    )
    after_transaction = Transaction(
        organization_id=organization_id,
        deal_id=deal.id,
        lead_id=lead.id,
        property_id=property_record.id,
        contact_id=contact.id,
        owner_user_id=foundation.admin_user.id,
        status="closed",
        contract_type="assignment",
        purchase_price_cents=11_000_000,
        contract_executed_at=original_at + timedelta(days=1),
        closed_at=original_at + timedelta(days=2),
        created_at=original_at + timedelta(minutes=45),
    )
    late_imported_pre_handoff_transaction = Transaction(
        organization_id=organization_id,
        deal_id=deal.id,
        lead_id=lead.id,
        property_id=property_record.id,
        contact_id=contact.id,
        owner_user_id=foundation.admin_user.id,
        status="closed",
        contract_type="assignment",
        purchase_price_cents=12_000_000,
        contract_executed_at=original_at - timedelta(minutes=20),
        closed_at=original_at - timedelta(minutes=10),
        created_at=original_at + timedelta(hours=1),
    )
    db_session.add_all(
        [
            before_appointment,
            after_appointment,
            second_after_appointment,
            before_transaction,
            after_transaction,
            late_imported_pre_handoff_transaction,
        ]
    )
    facts = list(
        db_session.scalars(
            select(BatchDialerCallFact).order_by(BatchDialerCallFact.provider_cdr_id)
        ).all()
    )
    assert len(facts) == 2
    for fact in facts:
        fact.lead_id = lead.id
        fact.final_outcome = "interested"
        fact.final_qualification_status = "accepted"
        fact.final_processing_status = "processed"
    facts[0].lead_created_by_event = True
    facts[1].lead_created_by_event = False
    db_session.commit()

    response = TestClient(app).get(
        "/api/v1/prospecting/batchdialer/va-performance",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        params={"date_from": "2026-08-18", "date_to": "2026-08-18"},
    )
    assert response.status_code == 200, response.text
    payload = cast(dict[str, Any], response.json())
    assert payload["summary"]["appointments_entered"] == 2
    assert payload["summary"]["handoffs_with_appointment_entered"] == 1
    assert payload["summary"]["appointments_entered_rate_basis_points"] == 10_000
    assert payload["summary"]["qualified_candidates"] == 2
    assert payload["summary"]["evidence_accepted_candidates"] == 2
    assert payload["summary"]["evidence_acceptance_rate_basis_points"] == 10_000
    assert payload["summary"]["verified_handoffs"] == 1
    assert payload["summary"]["appointments_held"] == 1
    assert payload["summary"]["signed_contracts"] == 1
    assert payload["summary"]["closed_transactions"] == 1
    assert any(
        "not maturity-normalized" in warning
        for warning in payload["coverage_warnings"]
    )
    agents = {row["provider_agent_name"]: row["metrics"] for row in payload["agents"]}
    assert agents["VA Original"]["appointments_entered"] == 2
    assert agents["VA Original"]["handoffs_with_appointment_entered"] == 1
    assert agents["VA Original"]["appointments_entered_rate_basis_points"] == 10_000
    assert agents["VA Original"]["verified_handoffs"] == 1
    assert agents["VA Original"]["signed_contracts"] == 1
    assert agents["VA Repeat"]["appointments_entered"] == 0
    assert agents["VA Repeat"]["handoffs_with_appointment_entered"] == 0
    assert agents["VA Repeat"]["verified_handoffs"] == 0
    assert agents["VA Repeat"]["signed_contracts"] == 0


def test_va_performance_rejects_invalid_or_oversized_ranges(
    db_session: Session,
    api_db_override: None,
) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="BatchDialer Range Workspace",
        admin_email=OWNER_EMAIL,
        admin_name="Performance Owner",
    )
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    for params in (
        {"date_from": "2026-08-20", "date_to": "2026-08-18"},
        {"date_from": "2025-01-01", "date_to": "2026-08-18"},
    ):
        response = client.get(
            "/api/v1/prospecting/batchdialer/va-performance",
            headers=headers,
            params=params,
        )
        assert response.status_code == 422
        assert response.headers["Cache-Control"] == "private, no-store"


def test_va_performance_assigns_midnight_spanning_call_to_its_start_day(
    db_session: Session,
    api_db_override: None,
) -> None:
    foundation = bootstrap_foundation(
        db_session,
        organization_name="BatchDialer Midnight Workspace",
        admin_email=OWNER_EMAIL,
        admin_name="Performance Owner",
    )
    # 03:59 UTC is 11:59 PM Eastern on August 21; the provider event completes
    # after local midnight. Reporting must consistently use the call start.
    started_at = datetime(2026, 8, 22, 3, 59, tzinfo=UTC)
    archive_batchdialer_cdr(
        db_session,
        organization_id=foundation.organization.id,
        cdr=_cdr(9301, "Not Interested", started_at),
        now=started_at + timedelta(minutes=2),
    )
    fact = db_session.scalar(select(BatchDialerCallFact))
    assert fact is not None
    fact.occurred_at = started_at + timedelta(minutes=2)
    fact.duration_seconds = None
    db_session.commit()

    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    start_day = client.get(
        "/api/v1/prospecting/batchdialer/va-performance",
        headers=headers,
        params={"date_from": "2026-08-21", "date_to": "2026-08-21"},
    )
    next_day = client.get(
        "/api/v1/prospecting/batchdialer/va-performance",
        headers=headers,
        params={"date_from": "2026-08-22", "date_to": "2026-08-22"},
    )

    assert start_day.status_code == 200, start_day.text
    assert start_day.json()["summary"]["calls"] == 1
    assert start_day.json()["daily_activity"][0]["date"] == "2026-08-21"
    assert start_day.json()["hourly_activity"][0]["recorded_call_seconds"] is None
    assert next_day.status_code == 200, next_day.text
    assert next_day.json()["summary"]["calls"] == 0


def test_campaign_rename_keeps_one_scorecard_with_latest_name(
    db_session: Session,
    api_db_override: None,
) -> None:
    foundation = bootstrap_foundation(
        db_session,
        organization_name="BatchDialer Campaign Rename Workspace",
        admin_email=OWNER_EMAIL,
        admin_name="Performance Owner",
    )
    observed_at = datetime(2026, 8, 18, 15, tzinfo=UTC)
    first = _cdr(9401, "Not Interested", observed_at)
    second = _cdr(9402, "No Answer", observed_at + timedelta(minutes=5))
    cast(dict[str, object], first["campaign"])["name"] = "Original campaign name"
    cast(dict[str, object], second["campaign"])["name"] = "Renamed campaign"
    for offset, cdr in enumerate((first, second)):
        archive_batchdialer_cdr(
            db_session,
            organization_id=foundation.organization.id,
            cdr=cdr,
            now=observed_at + timedelta(minutes=offset + 10),
        )
    db_session.commit()

    response = TestClient(app).get(
        "/api/v1/prospecting/batchdialer/va-performance",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        params={"date_from": "2026-08-18", "date_to": "2026-08-18"},
    )

    assert response.status_code == 200, response.text
    campaigns = response.json()["campaigns"]
    assert len(campaigns) == 1
    assert campaigns[0]["campaign_name"] == "Renamed campaign"
    assert campaigns[0]["metrics"]["calls"] == 2


def test_va_scorecard_excludes_inbound_calls_from_metrics_and_archive_basis(
    db_session: Session,
    api_db_override: None,
) -> None:
    foundation = bootstrap_foundation(
        db_session,
        organization_name="BatchDialer Outbound Only Workspace",
        admin_email=OWNER_EMAIL,
        admin_name="Performance Owner",
    )
    outbound_at = datetime(2026, 8, 18, 15, 0, tzinfo=UTC)
    inbound = _cdr(9450, "Qualified Seller - Follow Up", outbound_at - timedelta(hours=1))
    inbound["direction"] = "inbound"
    outbound = _cdr(9451, "Not Interested", outbound_at)
    for offset, cdr in enumerate((inbound, outbound)):
        archive_batchdialer_cdr(
            db_session,
            organization_id=foundation.organization.id,
            cdr=cdr,
            now=outbound_at + timedelta(minutes=offset + 1),
        )
    db_session.commit()

    response = TestClient(app).get(
        "/api/v1/prospecting/batchdialer/va-performance",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        params={"date_from": "2026-08-18", "date_to": "2026-08-18"},
    )

    assert response.status_code == 200, response.text
    payload = cast(dict[str, Any], response.json())
    assert payload["summary"]["calls"] == 1
    assert payload["summary"]["unique_contacts"] == 1
    assert payload["summary"]["human_contacts"] == 1
    assert payload["summary"]["qualified_candidates"] == 0
    assert payload["summary"]["evidence_accepted_candidates"] == 0
    assert payload["earliest_archived_call_at"].startswith("2026-08-18T15:00:00")
    assert payload["agents"][0]["metrics"]["calls"] == 1
    assert payload["campaigns"][0]["metrics"]["calls"] == 1


def test_completed_status_without_answer_evidence_is_not_a_human_contact(
    db_session: Session,
    api_db_override: None,
) -> None:
    foundation = bootstrap_foundation(
        db_session,
        organization_name="BatchDialer Human Evidence Workspace",
        admin_email=OWNER_EMAIL,
        admin_name="Performance Owner",
    )
    observed_at = datetime(2026, 8, 18, 15, 0, tzinfo=UTC)
    archive_batchdialer_cdr(
        db_session,
        organization_id=foundation.organization.id,
        cdr=_cdr(9452, "Provider Wrap Up", observed_at),
        now=observed_at + timedelta(minutes=1),
    )
    db_session.commit()

    response = TestClient(app).get(
        "/api/v1/prospecting/batchdialer/va-performance",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        params={"date_from": "2026-08-18", "date_to": "2026-08-18"},
    )

    assert response.status_code == 200, response.text
    payload = cast(dict[str, Any], response.json())
    assert payload["summary"]["calls"] == 1
    assert payload["summary"]["human_contacts"] == 0
    assert payload["summary"]["human_contact_rate_basis_points"] == 0
    assert any(
        "lack explicit human-contact evidence" in warning
        for warning in payload["coverage_warnings"]
    )


def _cdr(
    cdr_id: int,
    disposition: str,
    started_at: datetime,
    *,
    agent_id: int = 701,
    agent_name: str = "VA One",
) -> dict[str, object]:
    first_name, _, last_name = agent_name.partition(" ")
    return {
        "id": cdr_id,
        "direction": "out",
        "callStartTime": started_at.isoformat().replace("+00:00", "Z"),
        "callEndTime": (started_at + timedelta(seconds=90)).isoformat().replace("+00:00", "Z"),
        "customerNumber": f"+1678555{cdr_id:04d}",
        "disposition": disposition,
        "duration": 90,
        "status": "completed",
        "callid": f"provider-call-{cdr_id}",
        "recordingenabled": True,
        "agent": {"id": agent_id, "firstname": first_name, "lastname": last_name},
        "contact": {"id": cdr_id + 1000},
        "campaign": {"id": 88, "name": "Georgia Distressed Homeowners"},
    }
