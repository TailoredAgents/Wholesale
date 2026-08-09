from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import Principal, principal_for_user
from app.core.config import get_settings
from app.domain.assets import LAND_RESEARCH_PROFILE
from app.integrations.realestateapi_client import RealEstateAPIPropertySearch
from app.main import app
from app.models.foundation import (
    ActivityEvent,
    AuditEvent,
    LandOfferPolicyVersion,
    LandValuationAnalysis,
    Lead,
    Property,
    PropertyIntelligenceSnapshot,
    User,
)
from app.services.ai import build_lead_context
from app.services.bootstrap import bootstrap_foundation
from app.services.land_underwriting import list_land_offer_policies
from app.services.property_intelligence import property_research_signature

OWNER_EMAIL = "land-underwriting-owner@example.com"
OTHER_OWNER_EMAIL = "other-land-owner@example.com"


class FakeRealEstateAPIClient:
    calls = 0

    def __init__(self, _settings: object) -> None:
        pass

    def search_land_sales(self, **_kwargs: object) -> RealEstateAPIPropertySearch:
        type(self).calls += 1
        sale_date = (datetime.now(UTC) - timedelta(days=180)).date().isoformat()
        properties = [
            land_sale(
                provider_id="land-comp-1",
                apn="COMP-1",
                sale_date=sale_date,
                sale_price=80_000,
                lot_square_feet=348_480,
                latitude=33.7505,
                longitude=-84.3890,
            ),
            land_sale(
                provider_id="land-comp-2",
                apn="COMP-2",
                sale_date=sale_date,
                sale_price=100_000,
                lot_square_feet=435_600,
                latitude=33.7510,
                longitude=-84.3885,
            ),
            land_sale(
                provider_id="land-comp-3",
                apn="COMP-3",
                sale_date=sale_date,
                sale_price=120_000,
                lot_square_feet=522_720,
                latitude=33.7515,
                longitude=-84.3880,
            ),
        ]
        return RealEstateAPIPropertySearch(
            properties=properties,
            result_count=3,
            response_count=3,
            status_code=200,
            status_message="Success",
            raw_response={"data": properties},
        )


def land_sale(
    *,
    provider_id: str,
    apn: str,
    sale_date: str,
    sale_price: int,
    lot_square_feet: int,
    latitude: float,
    longitude: float,
) -> dict[str, object]:
    return {
        "id": provider_id,
        "apn": apn,
        "county": "Fulton",
        "state": "GA",
        "propertyType": "LAND",
        "propertyUse": "Residential Vacant Land",
        "latestArmsLengthSaleAmount": sale_price,
        "latestArmsLengthSaleDate": sale_date,
        "lotSquareFeet": lot_square_feet,
        "latitude": latitude,
        "longitude": longitude,
        "formattedAddress": f"{provider_id}, Atlanta, GA",
    }


def create_land_lead(client: TestClient, *, email: str = OWNER_EMAIL) -> UUID:
    response = client.post(
        "/api/v1/leads",
        headers={"X-Dev-User-Email": email},
        json={
            "contact": {
                "legal_name": "Parcel Seller",
                "contact_type": "seller",
            },
            "property": {
                "street_address": "100 Land Test Road",
                "city": "Atlanta",
                "state": "GA",
                "postal_code": "30303",
                "county": "Fulton",
                "property_type": "vacant_land",
                "parcel_id": "SUBJECT-APN-10",
            },
            "asset_class": "land",
            "source": "va_outreach",
            "stage_key": "new",
        },
    )
    assert response.status_code == 201, response.text
    return UUID(response.json()["id"])


def seed_current_land_snapshot(db: Session, lead_id: UUID) -> PropertyIntelligenceSnapshot:
    lead = db.get(Lead, lead_id)
    assert lead is not None
    property_record = db.get(Property, lead.property_id)
    assert property_record is not None
    now = datetime.now(UTC)
    snapshot = PropertyIntelligenceSnapshot(
        organization_id=lead.organization_id,
        property_id=property_record.id,
        source_lead_id=lead.id,
        source_market_analysis_id=None,
        version_number=1,
        research_profile=LAND_RESEARCH_PROFILE,
        status="ready",
        is_current=True,
        address_signature=property_research_signature(
            property_record,
            research_profile=LAND_RESEARCH_PROFILE,
        ),
        completeness_score=95,
        confidence_score=90,
        facts={
            "parcel_id": {"value": "SUBJECT-APN-10"},
            "county": {"value": "Fulton"},
            "state": {"value": "GA"},
            "lot_size_acres": {"value": 10},
            "land_use": {"value": "Residential Vacant Land"},
            "latitude": {"value": 33.75},
            "longitude": {"value": -84.39},
        },
        valuation={},
        comparables=[],
        market_context={},
        sources=[{"provider": "realestateapi", "operation": "property_detail"}],
        conflicts=[],
        media={},
        snapshot_metadata={"lookup_mode": "apn"},
        captured_at=now,
        expires_at=now + timedelta(days=30),
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


def create_and_activate_policy(client: TestClient, headers: dict[str, str]) -> dict[str, object]:
    created = client.post(
        "/api/v1/land-underwriting/offer-policies",
        headers=headers,
        json={"title": "Owner-approved Land offer policy"},
    )
    assert created.status_code == 201, created.text
    policy = created.json()
    assert policy["status"] == "draft"
    activated = client.post(
        f"/api/v1/land-underwriting/offer-policies/{policy['id']}/activate",
        headers=headers,
        json={"reason": "Approved for controlled Land underwriting launch."},
    )
    assert activated.status_code == 200, activated.text
    return cast(dict[str, object], activated.json())


def test_land_valuation_endpoints_save_history_and_reuse_evidence_without_paid_call(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Land Underwriting Owner",
    )
    settings = get_settings()
    monkeypatch.setattr(settings, "land_workflow_enabled", True)
    monkeypatch.setattr(settings, "realestateapi_api_key", "test-realestateapi-key")
    monkeypatch.setattr(
        "app.services.land_underwriting.RealEstateAPIClient",
        FakeRealEstateAPIClient,
    )
    FakeRealEstateAPIClient.calls = 0
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    lead_id = create_land_lead(client)
    seed_current_land_snapshot(db_session, lead_id)

    empty_history = client.get(
        f"/api/v1/leads/{lead_id}/land-valuations",
        headers=headers,
    )
    assert empty_history.status_code == 200
    assert empty_history.json() == []
    empty_latest = client.get(
        f"/api/v1/leads/{lead_id}/land-valuations/latest",
        headers=headers,
    )
    assert empty_latest.status_code == 200
    assert empty_latest.json() is None

    active_policy = create_and_activate_policy(client, headers)
    assert active_policy["status"] == "active"
    listed_policies = client.get(
        "/api/v1/land-underwriting/offer-policies",
        headers=headers,
    )
    assert listed_policies.status_code == 200
    assert [item["id"] for item in listed_policies.json()] == [active_policy["id"]]

    first = client.post(
        f"/api/v1/leads/{lead_id}/land-valuations",
        headers=headers,
        json={
            "refresh_comps": True,
            "idempotency_key": "land-search-initial-001",
            "search_tier": "preferred",
            "valuation_basis": "per_acre",
            "access_evidence_status": "verified",
            "access_evidence_reference": "Recorded ingress/egress easement reviewed by owner.",
            "subject_use_override": "residential",
            "subject_use_evidence_reference": "County zoning map reviewed by owner.",
            "review_note": "Initial controlled Land comp search.",
        },
    )
    assert first.status_code == 201, first.text
    first_analysis = first.json()
    assert first_analysis["version_number"] == 1
    assert first_analysis["status"] == "ready"
    assert first_analysis["guidance_status"] == "available"
    assert first_analysis["is_current"] is True
    assert len(first_analysis["selected_comps"]) == 3
    assert first_analysis["search_snapshot"]["provider_call_made"] is True
    assert first_analysis["search_snapshot"]["provider_credits_estimated"] == 3
    assert first_analysis["opening_offer_cents"] is not None
    assert first_analysis["seller_contract_ceiling_cents"] is not None
    assert first_analysis["subject_snapshot"]["land_use"] == "residential"
    assert first_analysis["subject_snapshot"]["land_use_source"] == "human_override"
    assert FakeRealEstateAPIClient.calls == 1

    retried = client.post(
        f"/api/v1/leads/{lead_id}/land-valuations",
        headers=headers,
        json={
            "refresh_comps": True,
            "idempotency_key": "land-search-initial-001",
            "search_tier": "preferred",
            "valuation_basis": "per_acre",
            "access_evidence_status": "verified",
            "access_evidence_reference": (
                "Recorded ingress/egress easement reviewed by owner."
            ),
            "subject_use_override": "residential",
            "subject_use_evidence_reference": "County zoning map reviewed by owner.",
            "review_note": "Initial controlled Land comp search.",
        },
    )
    assert retried.status_code == 201, retried.text
    assert retried.json()["id"] == first_analysis["id"]
    assert FakeRealEstateAPIClient.calls == 1

    detail = client.get(
        f"/api/v1/leads/{lead_id}",
        headers=headers,
    )
    assert detail.status_code == 200, detail.text
    property_intelligence = detail.json()["property_intelligence"]
    assert property_intelligence["valuation"]["land_value_point_cents"] == (
        first_analysis["supported_value_cents"]
    )
    assert len(property_intelligence["comparables"]) == 3
    assert property_intelligence["market_context"]["land_valuation"]["analysis_id"] == (
        first_analysis["id"]
    )
    source_snapshot = db_session.get(
        PropertyIntelligenceSnapshot,
        UUID(first_analysis["property_snapshot_id"]),
    )
    assert source_snapshot is not None
    assert source_snapshot.valuation == {}
    assert source_snapshot.comparables == []
    owner = db_session.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert owner is not None
    ai_context = build_lead_context(
        db_session,
        principal_for_user(db_session, owner),
        lead_id,
    )
    assert ai_context is not None
    ai_intelligence = ai_context["property_intelligence"]
    assert isinstance(ai_intelligence, dict)
    assert ai_intelligence["valuation"]["land_value_point_cents"] == (
        first_analysis["supported_value_cents"]
    )
    assert ai_intelligence["market_context"]["land_valuation"]["analysis_id"] == (
        first_analysis["id"]
    )

    reviewed = client.post(
        f"/api/v1/leads/{lead_id}/land-valuations",
        headers=headers,
        json={
            "source_analysis_id": first_analysis["id"],
            "access_evidence_status": "verified",
            "access_evidence_reference": "Recorded ingress/egress easement reviewed by owner.",
            "review_note": "Replayed saved evidence without another provider search.",
        },
    )
    assert reviewed.status_code == 201, reviewed.text
    reviewed_analysis = reviewed.json()
    assert reviewed_analysis["version_number"] == 2
    assert reviewed_analysis["source_analysis_id"] == first_analysis["id"]
    assert reviewed_analysis["search_snapshot"]["provider_call_made"] is False
    assert reviewed_analysis["search_snapshot"]["reused_saved_evidence"] is True
    assert FakeRealEstateAPIClient.calls == 1

    incompatible_replay = client.post(
        f"/api/v1/leads/{lead_id}/land-valuations",
        headers=headers,
        json={
            "source_analysis_id": first_analysis["id"],
            "subject_acres_override": "5.0000",
            "subject_acres_evidence_reference": "New survey received after initial analysis.",
            "access_evidence_status": "verified",
            "access_evidence_reference": "Recorded ingress/egress easement reviewed by owner.",
        },
    )
    assert incompatible_replay.status_code == 422
    assert "fresh Land comparable search" in incompatible_replay.json()["detail"]
    assert FakeRealEstateAPIClient.calls == 1

    reject_all = client.post(
        f"/api/v1/leads/{lead_id}/land-valuations",
        headers=headers,
        json={
            "source_analysis_id": first_analysis["id"],
            "selected_comp_keys": [],
            "access_evidence_status": "verified",
            "access_evidence_reference": "Recorded ingress/egress easement reviewed by owner.",
            "review_note": "Reviewer rejected every saved provider candidate.",
        },
    )
    assert reject_all.status_code == 201, reject_all.text
    rejected_analysis = reject_all.json()
    assert rejected_analysis["version_number"] == 3
    assert rejected_analysis["selected_comps"] == []
    assert len(rejected_analysis["rejected_comps"]) == 3
    assert rejected_analysis["status"] == "insufficient_evidence"
    assert rejected_analysis["guidance_status"] == "withheld"
    assert FakeRealEstateAPIClient.calls == 1

    restored_key = rejected_analysis["rejected_comps"][0]["key"]
    restored = client.post(
        f"/api/v1/leads/{lead_id}/land-valuations",
        headers=headers,
        json={
            "source_analysis_id": rejected_analysis["id"],
            "selected_comp_keys": [restored_key],
            "access_evidence_status": "verified",
            "access_evidence_reference": (
                "Recorded ingress/egress easement reviewed by owner."
            ),
            "review_note": "Restored a previously rejected saved sale without a search.",
        },
    )
    assert restored.status_code == 201, restored.text
    restored_analysis = restored.json()
    assert restored_analysis["version_number"] == 4
    assert [item["key"] for item in restored_analysis["selected_comps"]] == [
        restored_key
    ]
    assert restored_analysis["search_snapshot"]["provider_call_made"] is False
    assert FakeRealEstateAPIClient.calls == 1

    history = client.get(
        f"/api/v1/leads/{lead_id}/land-valuations?limit=10",
        headers=headers,
    )
    assert history.status_code == 200
    assert [item["id"] for item in history.json()] == [
        restored_analysis["id"],
        rejected_analysis["id"],
        reviewed_analysis["id"],
        first_analysis["id"],
    ]
    latest = client.get(
        f"/api/v1/leads/{lead_id}/land-valuations/latest",
        headers=headers,
    )
    assert latest.status_code == 200
    assert latest.json()["id"] == restored_analysis["id"]

    assert (
        db_session.scalar(
            select(func.count(LandValuationAnalysis.id)).where(
                LandValuationAnalysis.lead_id == lead_id
            )
        )
        == 4
    )
    assert (
        db_session.scalar(
            select(func.count(ActivityEvent.id)).where(
                ActivityEvent.entity_id == lead_id,
                ActivityEvent.event_type == "land.valuation_created",
            )
        )
        == 4
    )
    assert (
        db_session.scalar(
            select(func.count(AuditEvent.id)).where(
                AuditEvent.action == "land_valuation.create"
            )
        )
        == 4
    )


def test_land_underwriting_is_tenant_scoped_and_rejects_house_leads(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Land Owner",
    )
    bootstrap_foundation(
        db_session,
        organization_name="Other Home Buyers",
        admin_email=OTHER_OWNER_EMAIL,
        admin_name="Other Owner",
    )
    settings = get_settings()
    monkeypatch.setattr(settings, "land_workflow_enabled", True)
    client = TestClient(app)
    owner_headers = {"X-Dev-User-Email": OWNER_EMAIL}
    other_headers = {"X-Dev-User-Email": OTHER_OWNER_EMAIL}
    land_lead_id = create_land_lead(client)
    seed_current_land_snapshot(db_session, land_lead_id)
    policy = create_and_activate_policy(client, owner_headers)

    cross_tenant_history = client.get(
        f"/api/v1/leads/{land_lead_id}/land-valuations",
        headers=other_headers,
    )
    assert cross_tenant_history.status_code == 404
    cross_tenant_activation = client.post(
        f"/api/v1/land-underwriting/offer-policies/{policy['id']}/activate",
        headers=other_headers,
        json={"reason": "This tenant must not activate another tenant policy."},
    )
    assert cross_tenant_activation.status_code == 404
    other_policies = client.get(
        "/api/v1/land-underwriting/offer-policies",
        headers=other_headers,
    )
    assert other_policies.status_code == 200
    assert other_policies.json() == []

    house = client.post(
        "/api/v1/leads",
        headers=owner_headers,
        json={
            "contact": {"legal_name": "House Seller", "contact_type": "seller"},
            "property": {
                "street_address": "10 House Lane",
                "city": "Atlanta",
                "state": "GA",
                "postal_code": "30303",
                "county": "Fulton",
                "property_type": "single_family",
            },
            "asset_class": "house",
            "source": "website",
            "stage_key": "new",
        },
    )
    assert house.status_code == 201, house.text
    response = client.get(
        f"/api/v1/leads/{house.json()['id']}/land-valuations",
        headers=owner_headers,
    )
    assert response.status_code == 422
    assert "only for Land leads" in response.json()["detail"]


def test_paid_search_is_retry_idempotent_and_scoped_to_each_lead(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Land Underwriting Owner",
    )
    settings = get_settings()
    monkeypatch.setattr(settings, "land_workflow_enabled", True)
    monkeypatch.setattr(settings, "realestateapi_api_key", "test-realestateapi-key")
    monkeypatch.setattr(
        "app.services.land_underwriting.RealEstateAPIClient",
        FakeRealEstateAPIClient,
    )
    FakeRealEstateAPIClient.calls = 0
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    first_lead_id = create_land_lead(client)
    second_lead_id = create_land_lead(client)
    first_lead = db_session.get(Lead, first_lead_id)
    second_lead = db_session.get(Lead, second_lead_id)
    assert first_lead is not None and second_lead is not None
    assert first_lead.property_id == second_lead.property_id
    seed_current_land_snapshot(db_session, first_lead_id)
    create_and_activate_policy(client, headers)

    missing_key = client.post(
        f"/api/v1/leads/{first_lead_id}/land-valuations",
        headers=headers,
        json={"refresh_comps": True},
    )
    assert missing_key.status_code == 422, missing_key.text
    assert "idempotency key is required" in missing_key.json()["detail"]
    assert FakeRealEstateAPIClient.calls == 0

    def request(lead_id: UUID, key: str) -> Any:
        return client.post(
            f"/api/v1/leads/{lead_id}/land-valuations",
            headers=headers,
            json={
                "refresh_comps": True,
                "idempotency_key": key,
                "search_tier": "preferred",
                "valuation_basis": "per_acre",
                "access_evidence_status": "verified",
                "access_evidence_reference": "Recorded access reviewed.",
                "subject_use_override": "residential",
                "subject_use_evidence_reference": "County zoning map reviewed.",
            },
        )

    first = request(first_lead_id, "same-parcel-first-lead")
    retry = request(first_lead_id, "same-parcel-first-lead")
    conflicting_retry = client.post(
        f"/api/v1/leads/{first_lead_id}/land-valuations",
        headers=headers,
        json={
            "refresh_comps": True,
            "idempotency_key": "same-parcel-first-lead",
            "search_tier": "expanded",
            "valuation_basis": "per_acre",
            "access_evidence_status": "verified",
            "access_evidence_reference": "Recorded access reviewed.",
            "subject_use_override": "residential",
            "subject_use_evidence_reference": "County zoning map reviewed.",
        },
    )
    second = request(second_lead_id, "same-parcel-second-lead")

    assert first.status_code == 201, first.text
    assert retry.status_code == 201, retry.text
    assert conflicting_retry.status_code == 422, conflicting_retry.text
    assert "already used for different inputs" in conflicting_retry.json()["detail"]
    assert second.status_code == 201, second.text
    assert retry.json()["id"] == first.json()["id"]
    assert second.json()["id"] != first.json()["id"]
    assert first.json()["lead_id"] == str(first_lead_id)
    assert second.json()["lead_id"] == str(second_lead_id)
    assert FakeRealEstateAPIClient.calls == 2


def test_saved_land_guidance_fails_closed_when_snapshot_policy_or_identity_changes(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Land Underwriting Owner",
    )
    settings = get_settings()
    monkeypatch.setattr(settings, "land_workflow_enabled", True)
    monkeypatch.setattr(settings, "realestateapi_api_key", "test-realestateapi-key")
    monkeypatch.setattr(
        "app.services.land_underwriting.RealEstateAPIClient",
        FakeRealEstateAPIClient,
    )
    FakeRealEstateAPIClient.calls = 0
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    lead_id = create_land_lead(client)
    snapshot = seed_current_land_snapshot(db_session, lead_id)
    create_and_activate_policy(client, headers)
    created = client.post(
        f"/api/v1/leads/{lead_id}/land-valuations",
        headers=headers,
        json={
            "refresh_comps": True,
            "idempotency_key": "stale-guidance-initial",
            "access_evidence_status": "verified",
            "access_evidence_reference": "Recorded access reviewed.",
            "subject_use_override": "residential",
            "subject_use_evidence_reference": "County zoning map reviewed.",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["guidance_status"] == "available"
    assert created.json()["is_current"] is True

    snapshot.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.commit()
    expired = client.get(
        f"/api/v1/leads/{lead_id}/land-valuations/latest",
        headers=headers,
    )
    assert expired.status_code == 200, expired.text
    assert expired.json()["is_current"] is False
    assert expired.json()["guidance_status"] == "withheld"
    assert expired.json()["opening_offer_cents"] is None
    assert expired.json()["seller_contract_ceiling_cents"] is None
    assert any("expired" in item.lower() for item in expired.json()["guidance_blockers"])

    detail = client.get(f"/api/v1/leads/{lead_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    land_context = detail.json()["property_intelligence"]["market_context"][
        "land_valuation"
    ]
    assert land_context["is_current"] is False
    assert land_context["guidance_status"] == "withheld"
    assert detail.json()["property_intelligence"]["valuation"]["opening_offer_cents"] is None
    owner = db_session.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert owner is not None
    ai_context = build_lead_context(
        db_session,
        principal_for_user(db_session, owner),
        lead_id,
    )
    assert ai_context is not None
    ai_property_intelligence = ai_context["property_intelligence"]
    assert isinstance(ai_property_intelligence, dict)
    ai_land_context = ai_property_intelligence["market_context"]["land_valuation"]
    assert ai_land_context["is_current"] is False
    assert ai_property_intelligence["valuation"]["opening_offer_cents"] is None

    snapshot.expires_at = datetime.now(UTC) + timedelta(days=30)
    db_session.commit()
    create_and_activate_policy(client, headers)
    policy_changed = client.get(
        f"/api/v1/leads/{lead_id}/land-valuations/latest",
        headers=headers,
    )
    assert policy_changed.status_code == 200, policy_changed.text
    assert policy_changed.json()["is_current"] is False
    assert any(
        "offer policy changed" in item.lower()
        for item in policy_changed.json()["guidance_blockers"]
    )

    lead = db_session.get(Lead, lead_id)
    assert lead is not None
    property_record = db_session.get(Property, lead.property_id)
    assert property_record is not None
    property_record.parcel_id = "DIFFERENT-SUBJECT-APN"
    db_session.commit()
    identity_changed = client.get(
        f"/api/v1/leads/{lead_id}/land-valuations/latest",
        headers=headers,
    )
    assert identity_changed.status_code == 200, identity_changed.text
    assert identity_changed.json()["is_current"] is False
    assert any(
        "property identity changed" in item.lower()
        for item in identity_changed.json()["guidance_blockers"]
    )


def test_land_valuation_feature_gate_and_service_permission_are_fail_closed(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Land Owner",
    )
    settings = get_settings()
    monkeypatch.setattr(settings, "land_workflow_enabled", False)
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    lead_id = create_land_lead(client)
    seed_current_land_snapshot(db_session, lead_id)

    response = client.post(
        f"/api/v1/leads/{lead_id}/land-valuations",
        headers=headers,
        json={"refresh_comps": True},
    )
    assert response.status_code == 409
    assert "disabled" in response.json()["detail"].lower()

    unprivileged = Principal(
        user_id=uuid4(),
        organization_id=result.organization.id,
        email="unprivileged@example.com",
        permission_keys=frozenset(),
    )
    with pytest.raises(PermissionError, match="permission"):
        list_land_offer_policies(db_session, unprivileged)
    assert db_session.scalar(select(func.count(LandOfferPolicyVersion.id))) == 0
