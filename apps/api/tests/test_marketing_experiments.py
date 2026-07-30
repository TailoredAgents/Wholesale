from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import app
from app.models.foundation import (
    Appointment,
    AuditEvent,
    Deal,
    Lead,
    MarketingExperiment,
    MarketingExperimentAssignment,
    RevenueRecord,
    Transaction,
)
from app.services.bootstrap import bootstrap_foundation

OWNER_EMAIL = "owner@example.com"


def seed_owner(db: Session) -> None:
    bootstrap_foundation(
        db,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )


def headers() -> dict[str, str]:
    return {"X-Dev-User-Email": OWNER_EMAIL}


def experiment_payload(key: str = "homepage_cta_2026_01") -> dict[str, object]:
    return {
        "experiment_key": key,
        "name": "Homepage offer CTA wording",
        "hypothesis": (
            "A clearer cash-offer CTA will increase qualified seller inquiries "
            "without reducing downstream contract quality."
        ),
        "surface_key": "homepage_offer_cta",
        "primary_metric": "qualified_lead",
        "variants": [
            {
                "key": "control",
                "label": "Current CTA",
                "weight_basis_points": 5000,
                "cta_label": "Start My Offer",
            },
            {
                "key": "treatment",
                "label": "Test CTA",
                "weight_basis_points": 5000,
                "cta_label": "Get My Cash Offer",
            },
        ],
        "minimum_sessions_per_variant": 20,
        "minimum_runtime_days": 7,
        "decision_rule": (
            "Wait for both thresholds, then prefer qualified-lead rate unless "
            "contract or funded-deal outcomes contradict it."
        ),
    }


def decide(
    client: TestClient,
    experiment_id: str,
    decision: str,
    reason: str = "Owner reviewed the experiment state.",
) -> Response:
    return cast(
        Response,
        client.post(
            f"/api/v1/marketing/experiments/{experiment_id}/decision",
            headers=headers(),
            json={"decision": decision, "reason": reason},
        ),
    )


def test_experiment_assignment_survives_lead_and_downstream_outcomes(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    assert client.get("/api/v1/public/experiments").json() == {"experiments": []}

    created = client.post(
        "/api/v1/marketing/experiments",
        headers=headers(),
        json=experiment_payload(),
    )
    assert created.status_code == 201, created.text
    experiment_id = created.json()["id"]
    assert decide(client, experiment_id, "start").status_code == 200
    public = client.get("/api/v1/public/experiments")
    assert public.status_code == 200
    assert public.headers["cache-control"] == "no-store"
    assert public.json()["experiments"][0]["experiment_key"] == "homepage_cta_2026_01"

    control_event = client.post(
        "/api/v1/public/conversion-events",
        json={
            "event_type": "form_start",
            "session_id": "control-session",
            "experiment_key": "homepage_cta_2026_01",
            "experiment_variant": "control",
            "device_category": "mobile",
        },
    )
    conflicting_event = client.post(
        "/api/v1/public/conversion-events",
        json={
            "event_type": "offer_start",
            "session_id": "control-session",
            "experiment_key": "homepage_cta_2026_01",
            "experiment_variant": "treatment",
            "device_category": "desktop",
        },
    )
    treatment_event = client.post(
        "/api/v1/public/conversion-events",
        json={
            "event_type": "form_start",
            "session_id": "treatment-session",
            "experiment_key": "homepage_cta_2026_01",
            "experiment_variant": "treatment",
            "device_category": "desktop",
        },
    )
    assert control_event.status_code == 201
    assert conflicting_event.status_code == 201
    assert treatment_event.status_code == 201

    intake = client.post(
        "/api/v1/public/seller-leads",
        json={
            "property_address": "100 Test Street",
            "property_city": "Atlanta",
            "property_state": "GA",
            "property_postal_code": "30303",
            "name": "Qualified Seller",
            "phone": "4045551212",
            "preferred_contact_method": "phone",
            "consent_to_contact": True,
            "conversion_session_id": "control-session",
            "experiment_key": "homepage_cta_2026_01",
            "experiment_variant": "treatment",
            "device_category": "mobile",
        },
    )
    assert intake.status_code == 201, intake.text
    lead_id = UUID(intake.json()["lead_id"])
    lead = db_session.get(Lead, lead_id)
    assert lead is not None
    lead.stage_key = "qualified"

    appointment = Appointment(
        organization_id=lead.organization_id,
        lead_id=lead.id,
        contact_id=lead.contact_id,
        property_id=lead.property_id,
        owner_user_id=None,
        appointment_type="seller",
        status="scheduled",
        scheduled_start_at=datetime.now(UTC) + timedelta(days=1),
        scheduled_end_at=None,
        location_type="property",
        location=None,
        notes=None,
        outcome=None,
        external_calendar_id=None,
        appointment_metadata=None,
    )
    deal = Deal(
        organization_id=lead.organization_id,
        lead_id=lead.id,
        property_id=lead.property_id,
        stage_key="under_contract",
        contract_price_cents=15000000,
        assignment_fee_cents=2500000,
    )
    db_session.add_all([appointment, deal])
    db_session.flush()
    transaction = Transaction(
        organization_id=lead.organization_id,
        deal_id=deal.id,
        lead_id=lead.id,
        property_id=lead.property_id,
        contact_id=lead.contact_id,
        owner_user_id=None,
        coordinator_user_id=None,
        status="under_contract",
        contract_type="assignment",
        purchase_price_cents=15000000,
        assignment_fee_cents=2500000,
        earnest_money_cents=10000,
        contract_executed_at=datetime.now(UTC),
    )
    revenue = RevenueRecord(
        organization_id=lead.organization_id,
        lead_id=lead.id,
        deal_id=deal.id,
        transaction_id=None,
        source="assignment_fee",
        status="collected",
        amount_cents=2500000,
        received_at=datetime.now(UTC),
        notes=None,
    )
    db_session.add_all([transaction, revenue])
    experiment = db_session.get(MarketingExperiment, UUID(experiment_id))
    assert experiment is not None
    experiment.accumulated_runtime_seconds = 7 * 86400
    for variant in ("control", "treatment"):
        existing = 1
        for index in range(existing, 20):
            db_session.add(
                MarketingExperimentAssignment(
                    organization_id=lead.organization_id,
                    experiment_id=experiment.id,
                    session_id=f"{variant}-extra-{index}",
                    variant_key=variant,
                    device_category="desktop",
                    lead_id=None,
                    assigned_at=datetime.now(UTC),
                )
            )
    db_session.commit()

    overview = client.get("/api/v1/marketing/experiments", headers=headers())
    assert overview.status_code == 200
    report = overview.json()["experiments"][0]
    assert report["decision_status"] == "ready_for_human_review"
    control = next(row for row in report["performance"] if row["key"] == "control")
    treatment = next(row for row in report["performance"] if row["key"] == "treatment")
    assert control["assigned_sessions"] == 20
    assert control["mobile_sessions"] == 1
    assert control["leads_created"] == 1
    assert control["qualified_leads"] == 1
    assert control["appointments_scheduled"] == 1
    assert control["contracts_signed"] == 1
    assert control["funded_deals"] == 1
    assert control["collected_revenue_cents"] == 2500000
    assert control["primary_rate_basis_points"] == 500
    assert control["source_breakdown"][0] == {
        "source": "direct",
        "medium": "unknown",
        "campaign": "uncategorized",
        "assigned_sessions": 20,
        "leads_created": 1,
        "qualified_leads": 1,
        "contracts_signed": 1,
        "funded_deals": 1,
        "collected_revenue_cents": 2500000,
    }
    assert treatment["assigned_sessions"] == 20
    assert treatment["qualified_leads"] == 0

    assignment = db_session.scalar(
        select(MarketingExperimentAssignment).where(
            MarketingExperimentAssignment.session_id == "control-session"
        )
    )
    assert assignment is not None
    assert assignment.variant_key == "control"
    assert assignment.lead_id == lead_id

    completed = decide(
        client,
        experiment_id,
        "complete",
        "Control retained because it produced the qualified and funded outcome.",
    )
    assert completed.status_code == 200
    assert completed.json()["decision_status"] == "completed"
    assert client.get("/api/v1/public/experiments").json() == {"experiments": []}
    assert (
        db_session.scalar(
            select(func.count(AuditEvent.id)).where(
                AuditEvent.entity_type == "marketing_experiment"
            )
        )
        == 3
    )


def test_experiment_validation_and_surface_collision(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    invalid = experiment_payload("invalid_weights")
    invalid["variants"] = [
        {
            "key": "control",
            "label": "Current CTA",
            "weight_basis_points": 6000,
            "cta_label": "Start My Offer",
        },
        {
            "key": "treatment",
            "label": "Test CTA",
            "weight_basis_points": 6000,
            "cta_label": "Get My Cash Offer",
        },
    ]
    assert (
        client.post(
            "/api/v1/marketing/experiments",
            headers=headers(),
            json=invalid,
        ).status_code
        == 422
    )

    first = client.post(
        "/api/v1/marketing/experiments",
        headers=headers(),
        json=experiment_payload("homepage_cta_first"),
    )
    second = client.post(
        "/api/v1/marketing/experiments",
        headers=headers(),
        json=experiment_payload("homepage_cta_second"),
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert decide(client, first.json()["id"], "start").status_code == 200
    paused = decide(client, first.json()["id"], "pause")
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"
    resumed = decide(client, first.json()["id"], "resume")
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "running"
    collision = decide(client, second.json()["id"], "start")
    assert collision.status_code == 422
    assert "already running" in collision.json()["detail"]
