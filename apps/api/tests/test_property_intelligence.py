from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.core.auth import principal_for_user
from app.core.config import Settings, get_settings
from app.integrations.realestateapi_client import RealEstateAPIPropertyDetail
from app.main import app
from app.models.foundation import (
    Lead,
    Property,
    PropertyIntelligenceSnapshot,
    PropertyResearchRun,
    UnderwritingMarketAnalysis,
    User,
)
from app.services.ai import build_lead_context
from app.services.bootstrap import bootstrap_foundation
from app.services.property_intelligence import (
    backfill_next_property_snapshot,
    current_property_snapshot,
    enqueue_property_research,
    get_property_image_content,
    process_next_property_research,
    property_research_signature,
    property_snapshot_backfill_candidate_statement,
)

OWNER_EMAIL = "owner@example.com"


def test_property_snapshot_backfill_locks_only_the_analysis_table() -> None:
    statement = property_snapshot_backfill_candidate_statement()
    compiled = str(
        statement.compile(dialect=postgresql.dialect())  # type: ignore[no-untyped-call]
    )

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


def land_workflow_settings(*, enabled: bool) -> Settings:
    return Settings.model_validate(
        {
            "LAND_WORKFLOW_ENABLED": enabled,
            "PROPERTY_INTELLIGENCE_AUTO_RESEARCH_ENABLED": True,
            "REALESTATEAPI_API_KEY": "re_test_secret",
        }
    )


def parcel_only_land_payload(name: str) -> dict[str, object]:
    payload = lead_payload(name)
    payload["asset_class"] = "land"
    property_payload = payload["property"]
    assert isinstance(property_payload, dict)
    property_payload.update(
        {
            "street_address": "",
            "city": "",
            "postal_code": "",
            "county": "Pickens County",
            "property_type": "vacant_land",
            "parcel_id": "0012-03-A.004",
        }
    )
    return payload


def test_research_signatures_preserve_house_address_and_scope_land_parcels() -> None:
    property_record = Property(
        street_address="123 Peachtree Street",
        city="Atlanta",
        state="GA",
        postal_code="30303",
        county="Fulton County",
        parcel_id="0012-03-A.004",
    )

    assert property_research_signature(
        property_record, research_profile="house_v1"
    ) == "123 peachtree st|atlanta|GA|30303"
    assert property_research_signature(
        property_record, research_profile="land_v1"
    ) == "parcel:GA|fulton|001203A004"

    property_record.county = "Cobb"
    assert property_research_signature(
        property_record, research_profile="land_v1"
    ) == "parcel:GA|cobb|001203A004"


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


def test_house_and_land_research_runs_are_profile_isolated_when_land_disabled(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_owner(db_session)
    disabled_settings = land_workflow_settings(enabled=False)
    monkeypatch.setattr(
        "app.services.property_intelligence.get_settings",
        lambda: disabled_settings,
    )
    client = TestClient(app)

    house = client.post(
        "/api/v1/leads",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=lead_payload("House Seller"),
    )
    land_payload = lead_payload("Land Seller")
    land_payload["asset_class"] = "land"
    property_payload = land_payload["property"]
    assert isinstance(property_payload, dict)
    property_payload["property_type"] = "land"
    land = client.post(
        "/api/v1/leads",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=land_payload,
    )

    assert house.status_code == 201, house.text
    assert land.status_code == 201, land.text
    assert house.json()["property_id"] == land.json()["property_id"]
    runs = list(
        db_session.scalars(
            select(PropertyResearchRun).where(
                PropertyResearchRun.property_id == UUID(house.json()["property_id"])
            )
        )
    )
    assert {run.research_profile for run in runs} == {"house_v1", "land_v1"}
    house_run = next(run for run in runs if run.research_profile == "house_v1")
    land_run = next(run for run in runs if run.research_profile == "land_v1")
    assert house_run.status == "queued"
    assert land_run.status == "needs_review"
    assert ":house_v1:" in house_run.idempotency_key
    assert ":land_v1:" in land_run.idempotency_key
    assert land_run.run_metadata is not None
    assert land_run.run_metadata["reason_code"] == "land_workflow_disabled"
    assert land_run.run_metadata["residential_market_analysis_skipped"] is True

    house_detail = client.get(
        f"/api/v1/leads/{house.json()['id']}",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    land_detail = client.get(
        f"/api/v1/leads/{land.json()['id']}",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    assert house_detail.status_code == 200, house_detail.text
    assert land_detail.status_code == 200, land_detail.text
    assert house_detail.json()["property_intelligence"]["research_profile"] == "house_v1"
    assert house_detail.json()["property_intelligence"]["research_status"] == "queued"
    land_intelligence = land_detail.json()["property_intelligence"]
    assert land_intelligence["research_profile"] == "land_v1"
    assert land_intelligence["research_status"] == "needs_review"
    assert "LAND_WORKFLOW_ENABLED" in land_intelligence["last_error"]
    assert land_intelligence["market_context"]["workflow_status"] == "disabled"


def test_land_profile_does_not_reuse_house_snapshot_or_version_sequence(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = seed_owner(db_session)
    disabled_settings = land_workflow_settings(enabled=False)
    monkeypatch.setattr(
        "app.services.property_intelligence.get_settings",
        lambda: disabled_settings,
    )
    client = TestClient(app)
    house = client.post(
        "/api/v1/leads",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=lead_payload("House Snapshot Seller"),
    )
    assert house.status_code == 201, house.text
    house_lead = db_session.get(Lead, UUID(house.json()["id"]))
    assert house_lead is not None
    property_record = db_session.get(Property, house_lead.property_id)
    assert property_record is not None
    captured_at = datetime.now(UTC)
    house_snapshot = PropertyIntelligenceSnapshot(
        organization_id=house_lead.organization_id,
        property_id=house_lead.property_id,
        source_lead_id=house_lead.id,
        source_market_analysis_id=None,
        research_profile="house_v1",
        version_number=7,
        status="ready",
        is_current=True,
        address_signature=property_record.normalized_address_key or "",
        completeness_score=80,
        confidence_score=70,
        facts={"profile_marker": {"value": "house"}},
        valuation={"arv_point_cents": 300_000_00},
        comparables=[],
        market_context={},
        sources=[],
        conflicts=[],
        media={},
        snapshot_metadata={},
        captured_at=captured_at,
        expires_at=captured_at + timedelta(days=30),
    )
    db_session.add(house_snapshot)
    db_session.flush()

    land_payload = lead_payload("Land Snapshot Seller")
    land_payload["asset_class"] = "land"
    land = client.post(
        "/api/v1/leads",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=land_payload,
    )
    assert land.status_code == 201, land.text
    land_lead = db_session.get(Lead, UUID(land.json()["id"]))
    assert land_lead is not None
    assert (
        current_property_snapshot(
            db_session,
            organization_id=house_lead.organization_id,
            property_id=house_lead.property_id,
            research_profile="house_v1",
        )
        is house_snapshot
    )
    assert (
        current_property_snapshot(
            db_session,
            organization_id=land_lead.organization_id,
            property_id=land_lead.property_id,
            research_profile="land_v1",
        )
        is None
    )
    principal = principal_for_user(db_session, owner)
    house_ai_context = build_lead_context(db_session, principal, house_lead.id)
    land_ai_context = build_lead_context(db_session, principal, land_lead.id)
    assert house_ai_context is not None
    assert land_ai_context is not None
    house_ai_intelligence = house_ai_context["property_intelligence"]
    assert isinstance(house_ai_intelligence, dict)
    assert house_ai_intelligence["facts"] == {"profile_marker": {"value": "house"}}
    assert land_ai_context["property_intelligence"] is None

    land_run = enqueue_property_research(
        db_session,
        property_record,
        source_lead_id=land_lead.id,
        trigger_source="profile_isolation_test",
        settings=land_workflow_settings(enabled=True),
    )
    assert land_run is not None
    assert land_run.research_profile == "land_v1"
    assert ":land_v1:" in land_run.idempotency_key
    assert ":v1:automatic" in land_run.idempotency_key


def test_enabled_land_research_saves_facts_without_residential_analysis(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_owner(db_session)
    disabled_settings = land_workflow_settings(enabled=False)
    monkeypatch.setattr(
        "app.services.property_intelligence.get_settings",
        lambda: disabled_settings,
    )
    client = TestClient(app)
    payload = lead_payload("Enabled Land Seller")
    payload["asset_class"] = "land"
    property_payload = payload["property"]
    assert isinstance(property_payload, dict)
    property_payload["property_type"] = "land"
    created = client.post(
        "/api/v1/leads",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=payload,
    )
    assert created.status_code == 201, created.text
    lead = db_session.get(Lead, UUID(created.json()["id"]))
    assert lead is not None
    property_record = db_session.get(Property, lead.property_id)
    assert property_record is not None
    enabled_settings = land_workflow_settings(enabled=True)
    queued = enqueue_property_research(
        db_session,
        property_record,
        source_lead_id=lead.id,
        trigger_source="enabled_land_test",
        settings=enabled_settings,
    )
    assert queued is not None
    assert queued.status == "queued"

    def fake_property_detail(
        _client: object,
        *,
        address: str | None = None,
        apn: str | None = None,
        county: str | None = None,
        state: str | None = None,
        include_comps: bool = True,
    ) -> RealEstateAPIPropertyDetail:
        assert address == "123 Peachtree Street, Atlanta, GA 30303"
        assert apn is None
        assert county is None
        assert state is None
        assert include_comps is False
        return RealEstateAPIPropertyDetail(
            found=True,
            property={
                "id": "land-subject-1",
                "estimatedValue": 500_000,
                "comps": [{"id": "embedded-must-not-be-saved"}],
                "propertyType": "Vacant Land",
                "latitude": 33.75,
                "longitude": -84.39,
                "lastSaleDate": "2024-01-10",
                "lastSalePrice": 220_000,
                "propertyInfo": {
                    "address": {
                        "address": "123 Peachtree Street",
                        "city": "Atlanta",
                        "state": "GA",
                        "zip": "30303",
                    },
                    "waterSource": "Public",
                    "sewer": "Septic",
                },
                "lotInfo": {
                    "apn": "14-0001-LL-001",
                    "lotAcres": 4.2,
                    "zoning": "R-3",
                },
                "taxInfo": {
                    "taxAmount": 2_400,
                    "assessedLandValue": 180_000,
                },
            },
            comparables=[{"id": "must-not-be-used"}],
            status_code=200,
            status_message=None,
            raw_response={},
        )

    def fail_residential_analysis(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Land research must not call residential market analysis.")

    monkeypatch.setattr(
        "app.services.property_intelligence.RealEstateAPIClient.get_property_detail",
        fake_property_detail,
    )
    monkeypatch.setattr(
        "app.services.leads.create_lead_market_analysis",
        fail_residential_analysis,
    )

    processed_id = process_next_property_research(db_session, enabled_settings)

    assert processed_id == queued.id
    snapshot = current_property_snapshot(
        db_session,
        organization_id=lead.organization_id,
        property_id=lead.property_id,
        research_profile="land_v1",
    )
    assert snapshot is not None
    assert snapshot.research_profile == "land_v1"
    assert snapshot.source_market_analysis_id is None
    assert snapshot.valuation == {}
    assert snapshot.comparables == []
    assert snapshot.facts["parcel_id"]["value"] == "14-0001-LL-001"
    assert snapshot.facts["lot_size_acres"]["value"] == 4.2
    assert "realestateapi_estimated_value" not in snapshot.facts
    saved_provider_record = snapshot.market_context["provider_property_records"][
        "realestateapi"
    ]
    assert "estimatedValue" not in saved_provider_record
    assert "comps" not in saved_provider_record
    assert snapshot.snapshot_metadata is not None
    assert snapshot.snapshot_metadata["residential_market_analysis_skipped"] is True
    assert property_record.parcel_id == "14-0001-LL-001"
    assert (
        int(
            db_session.scalar(
                select(func.count())
                .select_from(UnderwritingMarketAnalysis)
                .where(UnderwritingMarketAnalysis.lead_id == lead.id)
            )
            or 0
        )
        == 0
    )
    db_session.refresh(queued)
    assert queued.status == snapshot.status
    assert queued.run_metadata is not None
    assert queued.run_metadata["residential_market_analysis_skipped"] is True


def test_apn_only_land_research_uses_one_parcel_lookup_and_reuses_fresh_snapshot(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_owner(db_session)
    settings = land_workflow_settings(enabled=True)
    monkeypatch.setattr(
        "app.services.property_intelligence.get_settings",
        lambda: settings,
    )
    client = TestClient(app)
    created = client.post(
        "/api/v1/leads",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=parcel_only_land_payload("Parcel Only Seller"),
    )
    assert created.status_code == 201, created.text
    lead = db_session.get(Lead, UUID(created.json()["id"]))
    assert lead is not None
    property_record = db_session.get(Property, lead.property_id)
    assert property_record is not None
    assert property_record.normalized_address_key is None
    assert property_record.normalized_parcel_key == "GA|pickens|001203A004"
    queued = db_session.scalar(
        select(PropertyResearchRun).where(
            PropertyResearchRun.property_id == property_record.id,
            PropertyResearchRun.research_profile == "land_v1",
        )
    )
    assert queued is not None
    assert queued.address_signature == "parcel:GA|pickens|001203A004"

    calls: list[dict[str, object]] = []

    def fake_property_detail(
        _client: object,
        *,
        address: str | None = None,
        apn: str | None = None,
        county: str | None = None,
        state: str | None = None,
        include_comps: bool = True,
    ) -> RealEstateAPIPropertyDetail:
        calls.append(
            {
                "address": address,
                "apn": apn,
                "county": county,
                "state": state,
                "include_comps": include_comps,
            }
        )
        return RealEstateAPIPropertyDetail(
            found=True,
            property={
                "id": "land-parcel-1",
                "propertyType": "Vacant Land",
                "latitude": 34.4817,
                "longitude": -84.371,
                "propertyInfo": {
                    "address": {
                        "address": "Lot 12 Talking Rock Road",
                        "city": "Talking Rock",
                        "county": "Pickens",
                        "state": "GA",
                        "zip": "30175",
                    }
                },
                "lotInfo": {
                    "apn": "001203A004",
                    "lotAcres": 3.25,
                    "zoning": "AG",
                },
            },
            comparables=[],
            status_code=200,
            status_message=None,
            raw_response={},
        )

    monkeypatch.setattr(
        "app.services.property_intelligence.RealEstateAPIClient.get_property_detail",
        fake_property_detail,
    )

    processed_id = process_next_property_research(db_session, settings)

    assert processed_id == queued.id
    assert calls == [
        {
            "address": None,
            "apn": "0012-03-A.004",
            "county": "Pickens County",
            "state": "GA",
            "include_comps": False,
        }
    ]
    snapshot = current_property_snapshot(
        db_session,
        organization_id=lead.organization_id,
        property_id=property_record.id,
        research_profile="land_v1",
    )
    assert snapshot is not None
    assert snapshot.address_signature == "parcel:GA|pickens|001203A004"
    assert snapshot.snapshot_metadata is not None
    assert snapshot.snapshot_metadata["lookup_mode"] == "parcel"
    assert snapshot.facts["parcel_id"]["value"] == "0012-03-A.004"
    db_session.refresh(property_record)
    assert property_record.street_address == "Lot 12 Talking Rock Road"
    assert property_record.city == "Talking Rock"
    assert property_record.postal_code == "30175"
    assert property_record.address_validation_status == "provider_confirmed"

    assert (
        enqueue_property_research(
            db_session,
            property_record,
            source_lead_id=lead.id,
            trigger_source="fresh_parcel_cache_test",
            settings=settings,
        )
        is None
    )
    assert process_next_property_research(db_session, settings) is None
    assert len(calls) == 1


def test_apn_only_land_research_rejects_provider_parcel_mismatch_without_snapshot(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_owner(db_session)
    settings = land_workflow_settings(enabled=True)
    monkeypatch.setattr(
        "app.services.property_intelligence.get_settings",
        lambda: settings,
    )
    client = TestClient(app)
    created = client.post(
        "/api/v1/leads",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=parcel_only_land_payload("Mismatched Parcel Seller"),
    )
    assert created.status_code == 201, created.text
    lead = db_session.get(Lead, UUID(created.json()["id"]))
    assert lead is not None
    property_record = db_session.get(Property, lead.property_id)
    assert property_record is not None

    def fake_mismatched_property_detail(
        _client: object,
        **_kwargs: object,
    ) -> RealEstateAPIPropertyDetail:
        return RealEstateAPIPropertyDetail(
            found=True,
            property={
                "id": "wrong-land-parcel",
                "propertyInfo": {
                    "address": {
                        "address": "999 Wrong Parcel Road",
                        "city": "Talking Rock",
                        "county": "Pickens",
                        "state": "GA",
                        "zip": "30175",
                    }
                },
                "lotInfo": {"apn": "DIFFERENT-APN", "lotAcres": 8.0},
            },
            comparables=[],
            status_code=200,
            status_message=None,
            raw_response={},
        )

    monkeypatch.setattr(
        "app.services.property_intelligence.RealEstateAPIClient.get_property_detail",
        fake_mismatched_property_detail,
    )

    processed_id = process_next_property_research(db_session, settings)

    assert processed_id is not None
    assert (
        current_property_snapshot(
            db_session,
            organization_id=lead.organization_id,
            property_id=property_record.id,
            research_profile="land_v1",
        )
        is None
    )
    run = db_session.get(PropertyResearchRun, processed_id)
    assert run is not None
    assert run.status == "needs_review"
    assert run.last_error is not None and "different Land parcel/APN" in run.last_error
    db_session.refresh(property_record)
    assert property_record.street_address == ""
    assert property_record.address_validation_status == "unverified"


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
