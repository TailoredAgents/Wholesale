from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import app
from app.models.foundation import (
    AuditEvent,
    Lead,
    UnderwritingCalibrationCase,
    UnderwritingMarketAnalysis,
    User,
)
from app.services.bootstrap import bootstrap_foundation
from app.services.underwriting_calibration import provider_adequacy

OWNER_EMAIL = "owner@example.com"


def seed_analysis(db: Session, client: TestClient) -> UnderwritingMarketAnalysis:
    result = bootstrap_foundation(
        db,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    response = client.post(
        "/api/v1/leads",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "contact": {
                "legal_name": "Jane Seller",
                "preferred_name": "Jane",
                "contact_type": "seller",
            },
            "property": {
                "street_address": "123 Peachtree St",
                "city": "Atlanta",
                "state": "GA",
                "postal_code": "30303",
                "county": "Fulton",
                "property_type": "single_family",
            },
            "source": "website",
            "stage_key": "underwriting",
        },
    )
    assert response.status_code == 201
    lead = db.get(Lead, UUID(response.json()["id"]))
    owner = db.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert lead is not None
    assert owner is not None

    analysis = UnderwritingMarketAnalysis(
        organization_id=result.organization.id,
        lead_id=lead.id,
        property_id=lead.property_id,
        created_by_user_id=owner.id,
        provider="rentcast",
        requested_address="123 Peachtree St, Atlanta, GA 30303",
        estimated_value_cents=25_000_000,
        estimated_value_low_cents=24_000_000,
        estimated_value_high_cents=26_000_000,
        arv_low_cents=28_000_000,
        arv_high_cents=31_000_000,
        repair_low_cents=4_500_000,
        repair_high_cents=5_500_000,
        mao_low_cents=14_000_000,
        mao_high_cents=16_000_000,
        recommended_offer_cents=14_500_000,
        assignment_fee_cents=1_500_000,
        offer_low_percentage=65,
        offer_high_percentage=70,
        confidence_score=78,
        selected_comp_count=3,
        rejected_comp_count=1,
        selected_comps=[],
        rejected_comps=[],
        subject_property={},
        raw_response={},
        analysis_metadata={
            "arv_point_cents": 30_000_000,
            "total_rehab_cents": 5_000_000,
            "seller_contract_ceiling_cents": 16_000_000,
            "recommended_disposition_cents": 17_750_000,
        },
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis


def test_calibration_records_snapshot_and_reports_error_metrics(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    analysis = seed_analysis(db_session, client)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}

    response = client.put(
        f"/api/v1/underwriting/calibration-cases/{analysis.id}",
        headers=headers,
        json={
            "benchmark_type": "expert_review",
            "evidence_date": datetime(2026, 7, 21, tzinfo=UTC).isoformat(),
            "benchmark_arv_cents": 28_500_000,
            "actual_rehab_cents": 5_500_000,
            "actual_seller_contract_cents": 15_000_000,
            "actual_disposition_cents": 17_500_000,
            "evidence_reference": "Broker price opinion dated 2026-07-21",
            "notes": "Reviewed after the walkthrough.",
        },
    )

    assert response.status_code == 200
    recorded = response.json()
    assert recorded["predicted_arv_point_cents"] == 30_000_000
    assert recorded["arv_error_cents"] == 1_500_000
    assert recorded["arv_error_percentage"] == 5.3
    assert recorded["arv_absolute_error_percentage"] == 5.3
    assert recorded["arv_range_hit"] is True

    case_response = client.get(
        f"/api/v1/underwriting/calibration-cases/{analysis.id}",
        headers=headers,
    )
    assert case_response.status_code == 200
    assert case_response.json()["benchmark_arv_cents"] == 28_500_000

    overview_response = client.get(
        "/api/v1/underwriting/calibration",
        headers=headers,
    )
    assert overview_response.status_code == 200
    overview = overview_response.json()
    assert overview["overall"] == {
        "market_key": "All markets",
        "providers": ["rentcast"],
        "methodology_versions": [],
        "sample_count": 1,
        "median_error_percentage": 5.3,
        "median_absolute_error_percentage": 5.3,
        "range_coverage_percentage": 100.0,
        "overestimate_count": 1,
        "underestimate_count": 0,
        "balanced_count": 0,
        "repair_sample_count": 1,
        "repair_median_absolute_error_percentage": 9.1,
        "seller_contract_sample_count": 1,
        "seller_contract_median_absolute_variance_percentage": 6.7,
        "disposition_sample_count": 1,
        "disposition_median_absolute_error_percentage": 1.4,
        "comp_review_case_count": 0,
        "comp_review_decision_count": 0,
        "comp_review_override_count": 0,
        "comp_review_override_percentage": None,
        "provider_adequacy": "insufficient_evidence",
        "failure_patterns": ["ARV estimates show a material overvaluation bias."],
        "readiness": "insufficient_sample",
    }
    assert overview["markets"][0]["market_key"] == "GA | Fulton"
    assert overview["provider_scorecards"][0]["providers"] == ["rentcast"]
    assert overview["uncalibrated_analysis_count"] == 0
    assert overview["minimum_sample_for_formula_review"] == 50
    assert overview["automatic_formula_changes_enabled"] is False
    assert overview["decisions"] == []


def test_provider_adequacy_uses_minimum_sample_and_pilot_thresholds() -> None:
    assert (
        provider_adequacy(sample_count=9, arv_mape=3, range_coverage=100)
        == "insufficient_evidence"
    )
    assert (
        provider_adequacy(sample_count=10, arv_mape=10, range_coverage=80)
        == "adequate"
    )
    assert (
        provider_adequacy(sample_count=10, arv_mape=13, range_coverage=80)
        == "monitor"
    )
    assert (
        provider_adequacy(sample_count=10, arv_mape=16, range_coverage=80)
        == "provider_review_required"
    )


def test_formula_and_provider_changes_require_evidence_and_human_decision(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    analysis = seed_analysis(db_session, client)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    benchmark_response = client.put(
        f"/api/v1/underwriting/calibration-cases/{analysis.id}",
        headers=headers,
        json={
            "benchmark_type": "expert_review",
            "evidence_date": "2026-07-21T12:00:00Z",
            "benchmark_arv_cents": 28_500_000,
        },
    )
    assert benchmark_response.status_code == 200

    draft_response = client.post(
        "/api/v1/underwriting/calibration-decisions",
        headers=headers,
        json={
            "scope_key": "GA | Fulton",
            "decision_type": "methodology_change",
            "title": "Test a narrower ARV range",
            "rationale": "The first verified case needs documented follow-up before changes.",
            "proposed_methodology_version": "v2.2-candidate",
            "proposed_changes": {
                "summary": "Evaluate a tighter range after the sample threshold."
            },
        },
    )
    assert draft_response.status_code == 201
    draft = draft_response.json()
    assert draft["status"] == "draft"
    assert draft["sample_count"] == 1
    assert draft["minimum_sample_required"] == 50
    assert draft["approval_blocked"] is True
    assert draft["evidence_snapshot"]["median_absolute_error_percentage"] == 5.3

    blocked_response = client.patch(
        f"/api/v1/underwriting/calibration-decisions/{draft['id']}",
        headers=headers,
        json={
            "status": "approved",
            "decision_notes": "Approve the proposed formula.",
        },
    )
    assert blocked_response.status_code == 422
    assert "needs 50 verified cases" in blocked_response.json()["detail"]

    rejected_response = client.patch(
        f"/api/v1/underwriting/calibration-decisions/{draft['id']}",
        headers=headers,
        json={
            "status": "rejected",
            "decision_notes": "Keep collecting evidence before changing the formula.",
        },
    )
    assert rejected_response.status_code == 200
    assert rejected_response.json()["status"] == "rejected"

    overview = client.get(
        "/api/v1/underwriting/calibration",
        headers=headers,
    ).json()
    assert overview["decisions"][0]["status"] == "rejected"


def test_calibration_update_preserves_one_case_and_writes_audit_event(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    analysis = seed_analysis(db_session, client)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    payload = {
        "benchmark_type": "completed_resale",
        "evidence_date": "2026-07-21T12:00:00Z",
        "benchmark_arv_cents": 29_000_000,
    }

    first_response = client.put(
        f"/api/v1/underwriting/calibration-cases/{analysis.id}",
        headers=headers,
        json=payload,
    )
    assert first_response.status_code == 200
    payload["benchmark_arv_cents"] = 30_500_000
    second_response = client.put(
        f"/api/v1/underwriting/calibration-cases/{analysis.id}",
        headers=headers,
        json=payload,
    )

    assert second_response.status_code == 200
    assert second_response.json()["id"] == first_response.json()["id"]
    assert second_response.json()["benchmark_arv_cents"] == 30_500_000
    assert int(
        db_session.scalar(select(func.count()).select_from(UnderwritingCalibrationCase)) or 0
    ) == 1
    assert int(
        db_session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "underwriting.calibration.create")
        )
        or 0
    ) == 1

    archive_response = client.delete(
        f"/api/v1/leads/{analysis.lead_id}",
        headers=headers,
    )
    assert archive_response.status_code == 200
    delete_response = client.delete(
        f"/api/v1/leads/{analysis.lead_id}/permanent?confirmation=DELETE",
        headers=headers,
    )
    assert delete_response.status_code == 204
    assert int(
        db_session.scalar(select(func.count()).select_from(UnderwritingCalibrationCase)) or 0
    ) == 0
    assert int(
        db_session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "underwriting.calibration.update")
        )
        or 0
    ) == 1
