from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.main import app
from app.models.foundation import (
    CallRecord,
    CommunicationRecord,
    Contact,
    ContactMethod,
    Conversation,
    Lead,
    LeadManagementCase,
    LeadQualificationScriptVersion,
    LeadQualificationSession,
    Property,
    Task,
    Transaction,
    User,
)
from app.services.acquisition_performance import (
    _conversation_score,
    _crm_hygiene_dimensions,
    _mature_transaction_outcome,
    _speed_dimensions,
)
from app.services.bootstrap import bootstrap_foundation
from app.services.call_intelligence import ACQUISITION_SALES_QUALITY_POLICY_VERSION

OWNER_EMAIL = "performance-owner@example.com"
REP_EMAIL = "performance-rep@example.com"


def _bootstrap(db: Session) -> tuple[Any, User]:
    foundation = bootstrap_foundation(
        db,
        organization_name="Acquisition Performance Workspace",
        admin_email=OWNER_EMAIL,
        admin_name="Performance Owner",
    )
    assert foundation.admin_user is not None
    return foundation.organization, foundation.admin_user


def _seed_lead(
    db: Session,
    *,
    organization_id: Any,
    owner: User,
    sequence: int,
    created_at: datetime,
) -> Lead:
    contact = Contact(
        organization_id=organization_id,
        legal_name=f"Seller {sequence}",
        preferred_name=None,
        contact_type="seller",
        assigned_user_id=owner.id,
    )
    property_record = Property(
        organization_id=organization_id,
        street_address=f"{sequence} Performance Way",
        city="Atlanta",
        state="GA",
        postal_code="30303",
        county="Fulton",
        property_type="single_family",
        normalized_address_key=f"{sequence}-performance-way-atlanta-ga-30303",
        address_validation_status="verified",
    )
    db.add_all([contact, property_record])
    db.flush()
    db.add(
        ContactMethod(
            organization_id=organization_id,
            contact_id=contact.id,
            method_type="phone",
            value=f"+1404555{sequence:04d}",
            normalized_value=f"+1404555{sequence:04d}",
            is_primary=True,
        )
    )
    lead = Lead(
        organization_id=organization_id,
        contact_id=contact.id,
        property_id=property_record.id,
        assigned_user_id=owner.id,
        source="website",
        asset_class="house",
        qualification_context={},
        stage_key="qualified",
        motivation="Needs a simpler sale",
        desired_timeline="Within 30 days",
        property_condition="Needs updates",
        occupancy_status=None,
        asking_price=None,
        mortgage_balance=None,
        appointment_status=None,
        next_follow_up_at=created_at + timedelta(days=10),
        created_at=created_at,
        updated_at=created_at,
    )
    db.add(lead)
    db.flush()
    return lead


def test_performance_endpoint_is_manager_only_and_returns_stable_contract(
    db_session: Session,
    api_db_override: None,
) -> None:
    _bootstrap(db_session)
    client = TestClient(app)
    owner_headers = {"X-Dev-User-Email": OWNER_EMAIL}

    response = client.get(
        "/api/v1/lead-manager/performance",
        headers=owner_headers,
        params={"period_days": 30},
    )

    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "private, no-store"
    payload = cast(dict[str, Any], response.json())
    assert payload["period_days"] == 30
    assert payload["policy_version"] == "acquisitions-performance-v1-shadow"
    assert payload["shadow_mode"] is True
    assert payload["weights"] == {
        "speed_to_lead": 2_000,
        "follow_up_discipline": 2_000,
        "conversation_quality": 2_000,
        "qualification_quality": 1_500,
        "crm_hygiene": 1_000,
        "appointment_execution": 500,
        "mature_outcomes": 1_000,
    }
    assert len(payload["scorecards"]) == 1
    scorecard = payload["scorecards"][0]
    assert scorecard["overall_score"] is None
    assert scorecard["coverage_basis_points"] == 0
    assert scorecard["reliability_status"] == "building"
    assert len(scorecard["dimensions"]) == 7
    assert all(item["score"] is None for item in scorecard["dimensions"])
    assert all(item["status"] == "unavailable" for item in scorecard["dimensions"])

    invalid_period = client.get(
        "/api/v1/lead-manager/performance",
        headers=owner_headers,
        params={"period_days": 60},
    )
    assert invalid_period.status_code == 422

    created_rep = client.post(
        "/api/v1/operations/users",
        headers=owner_headers,
        json={
            "email": REP_EMAIL,
            "display_name": "Performance Rep",
            "role_key": "acquisition_rep",
        },
    )
    assert created_rep.status_code == 201, created_rep.text
    forbidden = client.get(
        "/api/v1/lead-manager/performance",
        headers={"X-Dev-User-Email": REP_EMAIL},
    )
    assert forbidden.status_code == 403


def test_ready_dimensions_make_a_provisional_composite_and_ignore_cancelled_tasks(
    db_session: Session,
    api_db_override: None,
) -> None:
    organization, owner = _bootstrap(db_session)
    now = datetime.now(UTC).replace(microsecond=0)
    script = LeadQualificationScriptVersion(
        organization_id=organization.id,
        asset_class="house",
        version_number=1,
        title="Performance test script",
        status="approved",
        introduction="Test",
        questions=[],
        completion_rules={},
        created_by_user_id=owner.id,
        approved_by_user_id=owner.id,
        approved_at=now - timedelta(days=3),
    )
    db_session.add(script)
    db_session.flush()

    leads: list[Lead] = []
    for sequence in range(1, 6):
        created_at = now - timedelta(days=2, minutes=sequence)
        lead = _seed_lead(
            db_session,
            organization_id=organization.id,
            owner=owner,
            sequence=sequence,
            created_at=created_at,
        )
        leads.append(lead)
        db_session.add(
            CommunicationRecord(
                organization_id=organization.id,
                conversation_id=None,
                lead_id=lead.id,
                contact_id=lead.contact_id,
                source_call_record_id=None,
                actor_user_id=owner.id,
                direction="outbound",
                channel="sms",
                status="delivered",
                provider="test",
                provider_message_id=f"performance-speed-{sequence}",
                subject=None,
                body="Following up",
                occurred_at=created_at + timedelta(minutes=4),
            )
        )
        due_at = created_at + timedelta(hours=1)
        db_session.add(
            Task(
                organization_id=organization.id,
                lead_id=lead.id,
                deal_id=None,
                responsible_user_id=owner.id,
                task_type="seller_follow_up",
                work_kind="primary_next_action",
                title="Follow up with seller",
                status="completed",
                priority="normal",
                due_at=due_at,
                completed_at=due_at - timedelta(minutes=1),
                completed_by_user_id=owner.id,
                outcome="completed",
            )
        )
        if sequence <= 3:
            case = LeadManagementCase(
                organization_id=organization.id,
                lead_id=lead.id,
                handoff_id=None,
                assigned_user_id=owner.id,
                status="active",
                acceptance_due_at=created_at + timedelta(minutes=5),
                accepted_at=created_at + timedelta(minutes=1),
                accepted_by_user_id=owner.id,
                escalated_at=None,
                qualification_script_version_id=script.id,
                qualification_started_at=created_at + timedelta(minutes=5),
                qualification_completed_at=created_at + timedelta(minutes=15),
                qualification_quality_basis_points=8_000,
                next_action_type="follow_up",
                next_action_due_at=created_at + timedelta(days=1),
                last_contact_at=created_at + timedelta(minutes=15),
                closed_at=None,
            )
            db_session.add(case)
            db_session.flush()
            db_session.add(
                LeadQualificationSession(
                    organization_id=organization.id,
                    case_id=case.id,
                    lead_id=lead.id,
                    script_version_id=script.id,
                    completed_by_user_id=owner.id,
                    status="completed",
                    answers={"motivation": "Needs a simpler sale"},
                    missing_required_keys=[],
                    quality_score_basis_points=8_000,
                    next_action_type="follow_up",
                    next_action_due_at=created_at + timedelta(days=1),
                    completed_at=created_at + timedelta(minutes=15),
                )
            )

    db_session.add(
        Task(
            organization_id=organization.id,
            lead_id=leads[0].id,
            deal_id=None,
            responsible_user_id=owner.id,
            task_type="seller_follow_up",
            work_kind="primary_next_action",
            title="Superseded follow-up",
            status="cancelled",
            priority="normal",
            due_at=now - timedelta(hours=2),
            completed_at=now - timedelta(hours=3),
            completed_by_user_id=None,
            outcome="superseded",
        )
    )
    db_session.commit()

    response = TestClient(app).get(
        "/api/v1/lead-manager/performance",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        params={"period_days": 30},
    )

    assert response.status_code == 200, response.text
    payload = cast(dict[str, Any], response.json())
    scorecard = payload["scorecards"][0]
    assert scorecard["coverage_basis_points"] == 6_500
    assert scorecard["reliability_status"] == "provisional"
    assert scorecard["overall_score"] == 95
    dimensions = {item["key"]: item for item in scorecard["dimensions"]}
    assert dimensions["speed_to_lead"]["score"] == 100
    assert dimensions["speed_to_lead"]["status"] == "ready"
    assert dimensions["speed_to_lead"]["sample_size"] == 5
    assert dimensions["speed_to_lead"]["numerator"] == 500.0
    assert dimensions["speed_to_lead"]["denominator"] == 500.0
    assert dimensions["follow_up_discipline"]["sample_size"] == 5
    assert dimensions["follow_up_discipline"]["score"] == 100
    assert dimensions["follow_up_discipline"]["status"] == "ready"
    assert dimensions["qualification_quality"]["score"] == 80
    assert dimensions["qualification_quality"]["status"] == "ready"
    assert dimensions["crm_hygiene"]["score"] == 100
    assert dimensions["crm_hygiene"]["status"] == "ready"
    assert dimensions["conversation_quality"]["score"] is None
    assert dimensions["conversation_quality"]["status"] == "unavailable"


def test_speed_to_lead_credits_the_recorded_actor_not_the_current_owner(
    db_session: Session,
    api_db_override: None,
) -> None:
    organization, owner = _bootstrap(db_session)
    client = TestClient(app)
    created_rep = client.post(
        "/api/v1/operations/users",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "email": REP_EMAIL,
            "display_name": "Performance Rep",
            "role_key": "acquisition_rep",
        },
    )
    assert created_rep.status_code == 201, created_rep.text
    rep = db_session.scalar(select(User).where(User.email == REP_EMAIL))
    assert rep is not None
    created_at = datetime.now(UTC).replace(microsecond=0) - timedelta(days=1)
    lead = _seed_lead(
        db_session,
        organization_id=organization.id,
        owner=owner,
        sequence=99,
        created_at=created_at,
    )
    lead.assigned_user_id = rep.id
    db_session.add(
        CommunicationRecord(
            organization_id=organization.id,
            conversation_id=None,
            lead_id=lead.id,
            contact_id=lead.contact_id,
            source_call_record_id=None,
            actor_user_id=owner.id,
            direction="outbound",
            channel="phone",
            status="completed",
            provider="test",
            provider_message_id="performance-actual-actor",
            subject=None,
            body="Outbound call",
            occurred_at=created_at + timedelta(minutes=8),
        )
    )
    db_session.commit()

    response = client.get(
        "/api/v1/lead-manager/performance",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )

    assert response.status_code == 200, response.text
    scorecards = {item["user_id"]: item for item in response.json()["scorecards"]}
    owner_speed = next(
        item
        for item in scorecards[str(owner.id)]["dimensions"]
        if item["key"] == "speed_to_lead"
    )
    rep_speed = next(
        item
        for item in scorecards[str(rep.id)]["dimensions"]
        if item["key"] == "speed_to_lead"
    )
    assert owner_speed["sample_size"] == 1
    assert owner_speed["score"] is None
    assert owner_speed["numerator"] == 90.0
    assert owner_speed["denominator"] == 100.0
    assert owner_speed["status"] == "building"
    assert rep_speed["sample_size"] == 0
    assert rep_speed["score"] is None
    assert rep_speed["status"] == "unavailable"


def test_speed_to_lead_ignores_pre_intake_provider_history_and_uses_later_outreach(
    db_session: Session,
    api_db_override: None,
) -> None:
    organization, owner = _bootstrap(db_session)
    created_at = datetime.now(UTC).replace(microsecond=0) - timedelta(days=1)
    lead = _seed_lead(
        db_session,
        organization_id=organization.id,
        owner=owner,
        sequence=100,
        created_at=created_at,
    )
    for provider_message_id, occurred_at in (
        ("performance-pre-intake-provider-call", created_at - timedelta(minutes=5)),
        ("performance-valid-follow-up", created_at + timedelta(minutes=8)),
    ):
        db_session.add(
            CommunicationRecord(
                organization_id=organization.id,
                conversation_id=None,
                lead_id=lead.id,
                contact_id=lead.contact_id,
                source_call_record_id=None,
                actor_user_id=owner.id,
                direction="outbound",
                channel="phone",
                status="completed",
                provider="test",
                provider_message_id=provider_message_id,
                subject=None,
                body="Outbound call",
                occurred_at=occurred_at,
            )
        )
    db_session.commit()

    response = TestClient(app).get(
        "/api/v1/lead-manager/performance",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )

    assert response.status_code == 200, response.text
    speed = next(
        item
        for item in response.json()["scorecards"][0]["dimensions"]
        if item["key"] == "speed_to_lead"
    )
    assert speed["sample_size"] == 1
    assert speed["score"] is None
    assert speed["numerator"] == 90.0
    assert speed["denominator"] == 100.0


def test_speed_to_lead_ignores_non_contact_and_failed_outbound_records(
    db_session: Session,
) -> None:
    organization, owner = _bootstrap(db_session)
    now = datetime.now(UTC).replace(microsecond=0)
    created_at = now - timedelta(days=1)
    lead = _seed_lead(
        db_session,
        organization_id=organization.id,
        owner=owner,
        sequence=101,
        created_at=created_at,
    )
    conversation = Conversation(
        organization_id=organization.id,
        conversation_type="lead",
        lead_id=lead.id,
        contact_id=lead.contact_id,
        assigned_user_id=owner.id,
        assigned_team_id=None,
        source_alias_id=None,
        visibility_scope="standard",
        status="open",
        queue_key="seller_inbox",
        priority="normal",
        unread_count=0,
        last_activity_at=created_at,
        last_inbound_at=None,
        last_outbound_at=None,
        closed_at=None,
        conversation_metadata={},
    )
    db_session.add(conversation)
    db_session.flush()
    invalid_records = (
        ("call", "completed", "manual", 1),
        ("note", "sent", "test", 2),
        ("sms", "failed", "test", 3),
        ("email", "blocked", "test", 4),
        ("email", "draft", "test", 5),
    )
    for sequence, (channel, record_status, provider, elapsed_minutes) in enumerate(
        invalid_records,
        start=1,
    ):
        db_session.add(
            CommunicationRecord(
                organization_id=organization.id,
                conversation_id=None,
                lead_id=lead.id,
                contact_id=lead.contact_id,
                source_call_record_id=None,
                actor_user_id=owner.id,
                direction="outbound",
                channel=channel,
                status=record_status,
                provider=provider,
                provider_message_id=f"performance-invalid-outbound-{sequence}",
                subject=None,
                body="Not a usable seller-contact attempt",
                occurred_at=created_at + timedelta(minutes=elapsed_minutes),
            )
        )
    db_session.add(
        CallRecord(
            organization_id=organization.id,
            conversation_id=conversation.id,
            lead_id=lead.id,
            contact_id=lead.contact_id,
            actor_user_id=owner.id,
            provider="test",
            provider_call_id="performance-still-queued-call",
            direction="outbound",
            status="queued",
            from_number="+14045550000",
            to_number="+14045550101",
            started_at=created_at + timedelta(minutes=6),
            answered_at=None,
            ended_at=None,
            duration_seconds=None,
            disposition=None,
            recording_consent_status="not_requested",
            call_metadata={},
        )
    )
    db_session.add(
        CommunicationRecord(
            organization_id=organization.id,
            conversation_id=None,
            lead_id=lead.id,
            contact_id=lead.contact_id,
            source_call_record_id=None,
            actor_user_id=owner.id,
            direction="outbound",
            channel="email",
            status="sent",
            provider="test",
            provider_message_id="performance-first-real-outbound",
            subject="Seller follow-up",
            body="Following up about your property",
            occurred_at=created_at + timedelta(minutes=8),
        )
    )
    db_session.commit()

    dimensions, _ = _speed_dimensions(
        db_session,
        organization.id,
        {owner.id},
        now - timedelta(days=30),
        now,
    )

    assert dimensions[owner.id].sample_size == 1
    assert dimensions[owner.id].score is None
    assert dimensions[owner.id].status == "building"
    assert dimensions[owner.id].numerator == 90
    assert dimensions[owner.id].denominator == 100


def test_crm_future_action_credit_requires_the_lead_owner_to_own_the_task(
    db_session: Session,
) -> None:
    organization, owner = _bootstrap(db_session)
    now = datetime.now(UTC).replace(microsecond=0)
    other_rep = User(
        organization_id=organization.id,
        email="other-performance-rep@example.com",
        display_name="Other Performance Rep",
        is_active=True,
    )
    db_session.add(other_rep)
    db_session.flush()
    lead = _seed_lead(
        db_session,
        organization_id=organization.id,
        owner=owner,
        sequence=102,
        created_at=now - timedelta(days=1),
    )
    lead.next_follow_up_at = None
    db_session.add(
        Task(
            organization_id=organization.id,
            lead_id=lead.id,
            deal_id=None,
            responsible_user_id=other_rep.id,
            task_type="seller_follow_up",
            work_kind="primary_next_action",
            title="Another rep owns this follow-up",
            status="open",
            priority="normal",
            due_at=now + timedelta(days=1),
            completed_at=None,
            completed_by_user_id=None,
            outcome=None,
        )
    )
    db_session.commit()

    dimensions = _crm_hygiene_dimensions(
        db_session,
        organization.id,
        {owner.id, other_rep.id},
        now - timedelta(days=30),
        now,
    )

    assert dimensions[owner.id].sample_size == 1
    assert dimensions[owner.id].numerator == 1
    assert dimensions[owner.id].denominator == 2
    assert dimensions[owner.id].score is None
    assert dimensions[owner.id].status == "building"


def test_conversation_score_requires_high_confidence_complete_evidence() -> None:
    score_fields = (
        "active_listening_score",
        "discovery_score",
        "objection_handling_score",
        "next_step_clarity_score",
        "professionalism_score",
        "compliance_score",
    )
    evidence: list[dict[str, object]] = [
        {
            "field": field_name,
            "segment_index": 0,
            "start_seconds": 12.0,
            "supporting_text": "I want to move in 30 days.",
        }
        for field_name in score_fields
    ]
    quality = {
        "evaluable": True,
        "evaluation_reason": "The transcript contains a two-way seller conversation.",
        "speaker_attribution_confidence": 85,
        "active_listening_score": 80,
        "discovery_score": 70,
        "objection_handling_score": 60,
        "next_step_clarity_score": 90,
        "professionalism_score": 100,
        "compliance_score": 100,
        "strengths": ["Confirmed the seller's stated timing."],
        "coaching_points": ["Ask one more condition follow-up."],
        "evidence": evidence,
        "confidence": 90,
    }
    metadata = {
        "acquisition_sales_quality": quality,
        "acquisition_sales_quality_status": "scored",
        "acquisition_sales_quality_policy_version": (
            ACQUISITION_SALES_QUALITY_POLICY_VERSION
        ),
        "acquisition_sales_quality_evidence_validated": True,
    }

    assert _conversation_score(metadata) == pytest.approx(79.5)
    assert _conversation_score(
        {
            **metadata,
            "acquisition_sales_quality": {
                **quality,
                "speaker_attribution_confidence": 59,
            },
        }
    ) is None
    incomplete = dict(quality)
    incomplete.pop("compliance_score")
    assert _conversation_score({**metadata, "acquisition_sales_quality": incomplete}) is None
    assert (
        _conversation_score(
            {
                **metadata,
                "acquisition_sales_quality": {**quality, "evaluable": False},
            }
        )
        is None
    )
    assert (
        _conversation_score(
            {
                **metadata,
                "acquisition_sales_quality": {
                    **quality,
                    "evidence": evidence[:-1],
                },
            }
        )
        is None
    )
    assert _conversation_score(
        {**metadata, "acquisition_sales_quality_evidence_validated": False}
    ) is None
    assert _conversation_score(
        {**metadata, "acquisition_sales_quality_status": "not_evaluable"}
    ) is None
    assert _conversation_score(
        {**metadata, "acquisition_sales_quality_policy_version": "stale-policy"}
    ) is None


def test_mature_outcomes_exclude_pending_and_use_the_latest_mature_event() -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    period_start = now - timedelta(days=30)
    pending = Transaction(
        status="pending",
        contract_executed_at=None,
        funded_at=None,
        closed_at=None,
        cancelled_at=None,
        updated_at=now - timedelta(days=1),
    )
    executed = Transaction(
        status="executed",
        contract_executed_at=now - timedelta(days=5),
        funded_at=None,
        closed_at=None,
        cancelled_at=None,
        updated_at=now - timedelta(days=5),
    )
    cancelled_after_execution = Transaction(
        status="cancelled",
        contract_executed_at=now - timedelta(days=5),
        funded_at=None,
        closed_at=None,
        cancelled_at=now - timedelta(days=2),
        updated_at=now - timedelta(days=2),
    )
    closed_status_fallback = Transaction(
        status="closed",
        contract_executed_at=None,
        funded_at=None,
        closed_at=None,
        cancelled_at=None,
        updated_at=now - timedelta(days=1),
    )

    assert _mature_transaction_outcome(pending, period_start, now) is None
    assert _mature_transaction_outcome(executed, period_start, now) is True
    assert _mature_transaction_outcome(cancelled_after_execution, period_start, now) is False
    assert _mature_transaction_outcome(closed_status_fallback, period_start, now) is True
