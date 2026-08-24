from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.main import app
from app.models.foundation import (
    Lead,
    LeadManagementCase,
    LeadQualificationScriptVersion,
    Property,
)
from app.schemas.leads import PropertyIntelligenceRead
from app.services.bootstrap import bootstrap_foundation
from app.services.land_acquisition_profile import (
    LAND_REQUIRED_FACTS,
    build_land_acquisition_profile,
    merge_land_staff_context,
    record_land_reported_answers,
)
from app.services.lead_manager_copilot import _qualification_gaps
from app.services.leads import build_lead_intelligence


def land_lead(*, qualification_context: dict[str, object] | None = None) -> Lead:
    now = datetime.now(UTC)
    return Lead(
        id=uuid4(),
        organization_id=uuid4(),
        contact_id=uuid4(),
        property_id=uuid4(),
        assigned_user_id=None,
        source="seller_call",
        asset_class="land",
        qualification_context=qualification_context or {},
        stage_key="contacted",
        lead_temperature="warm",
        motivation="Estate no longer needs the parcel",
        desired_timeline="Within 60 days",
        property_condition=None,
        occupancy_status=None,
        asking_price="$72,000",
        mortgage_balance=None,
        appointment_status=None,
        next_follow_up_at=None,
        archived_at=None,
        updated_at=now,
    )


def land_property(lead: Lead) -> Property:
    return Property(
        id=lead.property_id,
        organization_id=lead.organization_id,
        street_address="",
        city="",
        state="GA",
        postal_code="",
        county="Gilmer",
        property_type="vacant_land",
        parcel_id="01A-002-003",
        normalized_parcel_key="GA|gilmer|01A002003",
        normalized_address_key=None,
        updated_at=datetime.now(UTC),
    )


def property_intelligence(*, facts: dict[str, object] | None = None) -> PropertyIntelligenceRead:
    return PropertyIntelligenceRead(
        research_status="completed",
        research_profile="land_v1",
        facts=facts or {},
    )


def provider_fact(value: object, source: str = "provider_screen") -> dict[str, object]:
    return {
        "value": value,
        "source": source,
        "observed_at": datetime.now(UTC).isoformat(),
    }


def test_provider_only_evidence_does_not_complete_seller_qualification() -> None:
    lead = land_lead()
    profile = build_land_acquisition_profile(
        lead=lead,
        property_record=land_property(lead),
        property_intelligence=property_intelligence(
            facts={
                "recorded_owner": provider_fact("Pat Parcel"),
                "lot_size_acres": provider_fact(6.4),
                "zoning": provider_fact("AG"),
                "water": provider_fact("Public line near road"),
                "flood_zone": provider_fact("X"),
            }
        ),
    )

    assert profile.facts["ownership_decision_makers"].status == "known"
    assert profile.facts["ownership_decision_makers"].source_type == "provider_sourced"
    assert profile.facts["zoning_use"].source_type == "provider_sourced"
    assert profile.facts["utilities"].source_type == "provider_sourced"
    assert profile.facts["flood_wetlands"].source_type == "provider_sourced"
    assert "ownership_decision_makers" in profile.readiness.unanswered_fields
    assert "acreage" in profile.readiness.unanswered_fields
    assert "zoning_use" in profile.readiness.unanswered_fields
    assert "utilities" in profile.readiness.unanswered_fields
    assert "flood_wetlands" in profile.readiness.unanswered_fields
    assert "zoning_use" not in profile.readiness.unknown_fields
    assert profile.readiness.status == "needs_seller_information"
    assert "offer" not in profile.readiness.status

    intelligence = build_lead_intelligence(
        lead=lead,
        contact_methods=[object()],  # type: ignore[list-item]
        open_tasks=[],
        land_acquisition_profile=profile,
    )
    missing_keys = {item.field_key for item in intelligence.missing_fields}
    assert {
        "ownership_decision_makers",
        "acreage",
        "zoning_use",
        "utilities",
        "flood_wetlands",
    }.issubset(missing_keys)
    assert "property_condition" not in missing_keys
    assert "occupancy_status" not in missing_keys
    assert "mortgage_balance" not in missing_keys
    assert "appointment_status" not in missing_keys


def test_profile_projection_rejects_cross_tenant_property() -> None:
    lead = land_lead()
    property_record = land_property(lead)
    property_record.organization_id = uuid4()

    with pytest.raises(ValueError, match="does not belong"):
        build_land_acquisition_profile(
            lead=lead,
            property_record=property_record,
            property_intelligence=property_intelligence(),
        )


def test_reported_profile_can_be_ready_for_remote_valuation_review_without_appointment() -> None:
    lead = land_lead()
    reported = {
        "ownership_decision_makers": "Seller and spouse are both on title",
        "acreage": "6.4 acres per tax bill",
        "zoning_use": "Seller reports agricultural zoning; intended recreational use",
        "access_frontage": "County-road frontage; legal access still needs verification",
        "utilities": "Power at road; seller is unsure about water",
        "survey_boundaries": "Old survey available; corners not recently marked",
        "septic_perc": "Not applicable",
        "taxes_hoa": "Current taxes; seller reports no HOA",
        "restrictions": "Not applicable",
        "flood_wetlands": "Seller reports no known wetlands; provider review still required",
        "terrain_environmental": "Mostly level; no known dumping",
        "title_probate_heirship": "Seller reports no probate or co-owner issue",
    }
    lead.qualification_context = record_land_reported_answers(
        lead.qualification_context,
        reported,
        source_name="lead_manager_qualification",
        observed_at=datetime.now(UTC),
    )
    profile = build_land_acquisition_profile(
        lead=lead,
        property_record=land_property(lead),
        property_intelligence=property_intelligence(
            facts={"water": provider_fact("Public line near road")}
        ),
    )

    assert profile.readiness.required_fields == list(LAND_REQUIRED_FACTS)
    assert profile.readiness.unanswered_fields == []
    assert profile.readiness.unknown_fields == []
    assert profile.readiness.conflict_fields == []
    assert profile.readiness.completion_score == 100
    assert profile.readiness.status == "ready_for_valuation_review"
    assert profile.readiness.remote_review_ready is True
    assert profile.facts["septic_perc"].status == "known"
    assert profile.facts["septic_perc"].value == "Not applicable"

    intelligence = build_lead_intelligence(
        lead=lead,
        contact_methods=[object()],  # type: ignore[list-item]
        open_tasks=[],
        land_acquisition_profile=profile,
    )
    assert intelligence.quality_score == 100
    assert intelligence.missing_fields == []
    assert intelligence.next_best_action.action_type == "review_land_diligence"
    assert "remotely" in intelligence.next_best_action.description
    assert "offer" not in intelligence.next_best_action.description.lower()


def test_unknown_remains_open_and_staff_merge_preserves_unrelated_context() -> None:
    now = datetime.now(UTC)
    existing = record_land_reported_answers(
        {"batchdialer": {"campaign_id": "42"}},
        {"access_or_frontage": "Road frontage reported"},
        source_name="call_intelligence_transcript",
        observed_at=now,
    )
    merged = merge_land_staff_context(
        existing,
        {
            "utilities": "Unknown",
            "restrictions": "Not applicable",
            "batchdialer": {"campaign_id": "42"},
        },
        observed_at=now,
    )
    lead = land_lead(qualification_context=merged)
    profile = build_land_acquisition_profile(
        lead=lead,
        property_record=land_property(lead),
        property_intelligence=property_intelligence(),
    )

    assert merged["batchdialer"] == {"campaign_id": "42"}
    stored = merged["land_acquisition_v1"]
    assert stored["facts"]["access_frontage"]["value"] == "Road frontage reported"
    assert stored["facts"]["utilities"]["source_type"] == "seller_reported"
    assert profile.facts["utilities"].status == "unknown"
    assert "utilities" in profile.readiness.unknown_fields
    assert "utilities" not in profile.readiness.unanswered_fields
    assert profile.facts["restrictions"].status == "known"
    assert "restrictions" in profile.readiness.completed_fields


def test_conflicting_provider_screen_is_visible_and_blocks_readiness() -> None:
    lead = land_lead()
    lead.qualification_context = record_land_reported_answers(
        lead.qualification_context,
        {"acreage": "6.4 acres", "zoning_use": "Agricultural"},
        source_name="prospecting_qualification",
        observed_at=datetime.now(UTC),
    )
    profile = build_land_acquisition_profile(
        lead=lead,
        property_record=land_property(lead),
        property_intelligence=property_intelligence(
            facts={
                "lot_size_acres": provider_fact(8.1),
                "zoning": provider_fact("Residential"),
            }
        ),
    )

    assert profile.facts["acreage"].status == "conflict"
    assert profile.facts["zoning_use"].status == "conflict"
    assert profile.readiness.status == "needs_seller_information"
    assert "acreage" in profile.readiness.conflict_fields
    assert "zoning_use" in profile.readiness.conflict_fields
    assert any("conflicting evidence" in item for item in profile.readiness.open_questions)


def test_explicit_unknown_completes_interview_but_routes_to_remote_diligence() -> None:
    lead = land_lead()
    reported = {
        key: "Seller reported value"
        for key in LAND_REQUIRED_FACTS
        if key not in {"motivation", "timeline", "asking_price", "parcel_id"}
    }
    reported["utilities"] = "Unknown"
    lead.qualification_context = record_land_reported_answers(
        lead.qualification_context,
        reported,
        source_name="lead_manager_qualification",
        observed_at=datetime.now(UTC),
    )
    profile = build_land_acquisition_profile(
        lead=lead,
        property_record=land_property(lead),
        property_intelligence=property_intelligence(
            facts={"water": provider_fact("Public line near road")}
        ),
    )

    assert profile.readiness.unanswered_fields == []
    assert profile.readiness.completion_score == 100
    assert "utilities" in profile.readiness.completed_fields
    assert profile.readiness.unknown_fields == ["utilities"]
    assert profile.readiness.status == "needs_due_diligence_review"
    assert profile.readiness.remote_review_ready is True
    assert any(
        "Research or verify utilities" in item
        for item in profile.readiness.open_questions
    )
    intelligence = build_lead_intelligence(
        lead=lead,
        contact_methods=[object()],  # type: ignore[list-item]
        open_tasks=[],
        land_acquisition_profile=profile,
    )
    assert intelligence.missing_fields == []


def test_land_staff_patch_materializes_profile_without_replacing_existing_context(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "property_intelligence_auto_research_enabled", False)
    bootstrap_foundation(
        db_session,
        organization_name="Land Profile Org",
        admin_email="land-profile-owner@example.com",
        admin_name="Land Profile Owner",
    )
    client = TestClient(app)
    headers = {"X-Dev-User-Email": "land-profile-owner@example.com"}
    created = client.post(
        "/api/v1/leads",
        headers=headers,
        json={
            "contact": {"legal_name": "Parcel Seller", "contact_type": "seller"},
            "property": {
                "street_address": "",
                "city": "",
                "state": "GA",
                "postal_code": "",
                "county": "Gilmer",
                "property_type": "vacant_land",
                "parcel_id": "01A-002-003",
            },
            "source": "seller_call",
            "asset_class": "land",
            "motivation": "No longer plans to build",
            "desired_timeline": "Within 90 days",
            "asking_price": "$72,000",
            "qualification_context": {
                "batchdialer": {"campaign_id": "land-42"},
            },
        },
    )
    assert created.status_code == 201, created.text

    patched = client.patch(
        f"/api/v1/leads/{created.json()['id']}",
        headers=headers,
        json={
            "qualification_context": {
                "access_frontage": "Seller reports county-road frontage",
                "utilities": "Power at road; water unknown",
                "restrictions": "Not applicable",
            }
        },
    )
    assert patched.status_code == 200, patched.text
    detail = patched.json()
    assert detail["qualification_context"]["batchdialer"] == {
        "campaign_id": "land-42"
    }
    stored_facts = detail["qualification_context"]["land_acquisition_v1"]["facts"]
    assert stored_facts["access_frontage"]["source_type"] == "seller_reported"
    assert stored_facts["access_frontage"]["source_name"] == "staff_qualification_edit"
    assert "parcel_id" not in stored_facts
    profile = detail["land_acquisition_profile"]
    assert profile["version"] == "land_acquisition_v1"
    assert profile["facts"]["parcel_id"]["value"] == "01A-002-003"
    assert profile["facts"]["access_frontage"]["source_type"] == "seller_reported"
    assert "property_condition" not in {
        item["field_key"] for item in detail["intelligence"]["missing_fields"]
    }


def test_land_copilot_gaps_read_alias_context_and_canonical_property_identity() -> None:
    lead = land_lead(
        qualification_context={
            "access_or_frontage": "Seller reports county-road frontage",
            "utilities": "Unknown",
        }
    )
    property_record = land_property(lead)
    case = LeadManagementCase(
        id=uuid4(),
        organization_id=lead.organization_id,
        lead_id=lead.id,
        assigned_user_id=uuid4(),
    )
    script = LeadQualificationScriptVersion(
        id=uuid4(),
        organization_id=lead.organization_id,
        asset_class="land",
        version_number=1,
        title="Land qualification",
        status="approved",
        introduction="Ask only governed Land questions.",
        questions=[
            {
                "key": "parcel_id",
                "label": "Parcel / APN",
                "prompt": "What is the parcel number?",
            },
            {
                "key": "access_frontage",
                "label": "Access and frontage",
                "prompt": "What access is reported?",
            },
            {
                "key": "utilities",
                "label": "Utilities",
                "prompt": "Which utilities are reported?",
            },
            {
                "key": "survey_boundaries",
                "label": "Survey and boundaries",
                "prompt": "Is there a survey?",
            },
        ],
    )
    db = Mock(spec=Session)
    db.scalar.side_effect = [script, None]
    db.get.return_value = property_record

    gaps, questions = _qualification_gaps(db, case, lead)

    assert gaps == ["Survey and boundaries"]
    assert questions == ["Is there a survey?"]
