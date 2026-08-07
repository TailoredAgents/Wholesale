from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.core.auth import principal_for_user
from app.core.config import get_settings
from app.main import app
from app.models.foundation import (
    Lead,
    Property,
    PropertyIntelligenceSnapshot,
    PropertyResearchRun,
    UnderwritingMarketAnalysis,
    User,
)
from app.services.bootstrap import bootstrap_foundation
from app.services.property_intelligence import (
    backfill_next_property_snapshot,
    get_property_image_content,
    property_snapshot_backfill_candidate_statement,
)

OWNER_EMAIL = "owner@example.com"


def test_property_snapshot_backfill_locks_only_the_analysis_table() -> None:
    statement = property_snapshot_backfill_candidate_statement()
    compiled = str(statement.compile(dialect=postgresql.dialect()))

    assert "FOR UPDATE OF underwriting_market_analyses SKIP LOCKED" in compiled


def seed_owner(db_session: Session) -> User:
    result = bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    assert result.admin_user is not None
    return result.admin_user


def lead_payload(name: str) -> dict[str, object]:
    return {
        "contact": {"legal_name": name, "contact_type": "seller"},
        "property": {
            "street_address": "123 Peachtree Street",
            "city": "Atlanta",
            "state": "GA",
            "postal_code": "30303",
            "property_type": "single_family",
        },
        "source": "manual",
        "stage_key": "new",
    }


def test_lead_creation_reuses_property_and_one_active_research_job(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)

    first = client.post(
        "/api/v1/leads",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=lead_payload("First Seller"),
    )
    second = client.post(
        "/api/v1/leads",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=lead_payload("Second Seller"),
    )

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["property_id"] == second.json()["property_id"]
    assert int(db_session.scalar(select(func.count()).select_from(Property)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(PropertyResearchRun)) or 0) == 1
    detail = client.get(
        f"/api/v1/leads/{first.json()['id']}",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    assert detail.status_code == 200
    assert detail.json()["property_intelligence"]["research_status"] == "queued"
    assert detail.json()["property_intelligence"]["facts"]["property_type"]["value"] == (
        "single_family"
    )


def test_saved_snapshot_populates_property_profile_without_provider_call(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = seed_owner(db_session)
    client = TestClient(app)
    created = client.post(
        "/api/v1/leads",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=lead_payload("Snapshot Seller"),
    )
    assert created.status_code == 201, created.text
    lead = db_session.get(Lead, UUID(created.json()["id"]))
    assert lead is not None
    property_record = db_session.get(Property, lead.property_id)
    assert property_record is not None
    analysis = UnderwritingMarketAnalysis(
        organization_id=lead.organization_id,
        lead_id=lead.id,
        property_id=lead.property_id,
        underwriting_version_id=None,
        created_by_user_id=owner.id,
        provider="rentcast",
        requested_address="123 Peachtree Street, Atlanta, GA 30303",
        estimated_value_cents=250_000_00,
        estimated_value_low_cents=235_000_00,
        estimated_value_high_cents=265_000_00,
        arv_low_cents=280_000_00,
        arv_high_cents=310_000_00,
        repair_low_cents=None,
        repair_high_cents=None,
        mao_low_cents=None,
        mao_high_cents=None,
        recommended_offer_cents=None,
        assignment_fee_cents=15_000_00,
        offer_low_percentage=65,
        offer_high_percentage=70,
        confidence_score=72,
        selected_comp_count=1,
        rejected_comp_count=0,
        selected_comps=[
            {
                "provider_id": "comp-1",
                "formatted_address": "125 Peachtree Street, Atlanta, GA 30303",
                "price_cents": 295_000_00,
                "sale_date": "2026-06-01",
                "distance_miles": 0.2,
            }
        ],
        rejected_comps=[],
        subject_property={
            "propertyType": "Single Family",
            "bedrooms": 3,
            "bathrooms": 2,
            "squareFootage": 1800,
            "lotSize": 7500,
            "yearBuilt": 1985,
            "latitude": 33.75,
            "longitude": -84.39,
        },
        raw_response={
            "realestateapi": {
                "property": {
                    "id": "prop-subject",
                    "estimatedEquity": 175_000,
                    "equityPercent": 61,
                    "propertyInfo": {
                        "address": {
                            "address": "123 Peachtree Street",
                            "city": "Atlanta",
                            "state": "GA",
                            "zip": "30303",
                        }
                    },
                    "taxInfo": {"taxAmount": 3_250},
                    "lotInfo": {"apn": "14-0001-LL-001"},
                    "media": {
                        "primaryListingImageUrl": (
                            "https://imagecdn.realty.dev/mls_photos/prop-subject/1.jpg"
                        ),
                        "photosCount": "12",
                    },
                }
            }
        },
        analysis_metadata={
            "methodology_version": "v3",
            "arv_point_cents": 295_000_00,
            "confidence_tier": "supported",
            "report_stage": "preliminary",
            "assumptions": {
                "subject_fact_provenance": {
                    "squareFootage": "rentcast_property_record",
                }
            },
            "supporting_evidence": {},
            "secondary_evidence": {},
            "comp_intelligence": {},
            "data_disagreements": [],
        },
    )
    db_session.add(analysis)
    db_session.flush()
    backfilled_property_id = backfill_next_property_snapshot(db_session, get_settings())
    assert backfilled_property_id == property_record.id
    snapshot = db_session.scalar(
        select(PropertyIntelligenceSnapshot).where(
            PropertyIntelligenceSnapshot.property_id == property_record.id,
            PropertyIntelligenceSnapshot.is_current.is_(True),
        )
    )
    assert snapshot is not None

    detail = client.get(
        f"/api/v1/leads/{lead.id}",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )

    assert detail.status_code == 200, detail.text
    intelligence = detail.json()["property_intelligence"]
    assert intelligence["snapshot_id"] == str(snapshot.id)
    assert intelligence["facts"]["square_footage"]["value"] == 1800
    assert intelligence["facts"]["square_footage"]["source"] == ("rentcast_property_record")
    assert intelligence["valuation"]["arv_point_cents"] == 295_000_00
    assert len(intelligence["comparables"]) == 1
    assert intelligence["facts"]["estimated_equity_amount"]["value"] == 175_000
    assert intelligence["facts"]["estimated_equity_amount"]["unit"] == "dollars"
    assert intelligence["facts"]["parcel_id"]["value"] == "14-0001-LL-001"
    assert intelligence["image_source"] == "realestateapi_listing"
    assert intelligence["image_views"] == ["listing"]
    assert (
        intelligence["market_context"]["provider_property_records"]["realestateapi"][
            "estimatedEquity"
        ]
        == 175_000
    )
    assert (
        int(db_session.scalar(select(func.count()).select_from(PropertyIntelligenceSnapshot)) or 0)
        == 1
    )
    research_run = db_session.scalar(
        select(PropertyResearchRun).where(PropertyResearchRun.property_id == property_record.id)
    )
    assert research_run is not None
    assert research_run.status == snapshot.status
    assert research_run.run_metadata is not None
    assert research_run.run_metadata["existing_analysis_backfilled"] is True
    principal = principal_for_user(db_session, owner)
    assert principal.organization_id == lead.organization_id
    monkeypatch.setattr(
        "app.services.property_intelligence.get_realestateapi_image",
        lambda image_url, timeout_seconds: (image_url.encode(), "image/jpeg"),
    )
    image = get_property_image_content(
        db_session,
        principal,
        lead.id,
        get_settings(),
        view="listing",
    )
    assert image is not None
    assert image.source == "realestateapi_listing"
    assert image.content.startswith(b"https://imagecdn.realty.dev/mls_photos/")
    captured_at = datetime.fromisoformat(intelligence["captured_at"])
    assert captured_at.tzinfo is not None
    assert captured_at <= datetime.now(UTC)
