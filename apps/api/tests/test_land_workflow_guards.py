from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import app
from app.models.foundation import (
    BuyerOffer,
    ContractPackage,
    Deal,
    Lead,
    OfferNegotiationPlan,
    RepairEstimate,
    Transaction,
    UnderwritingMarketAnalysis,
    UnderwritingVersion,
)
from app.services.bootstrap import bootstrap_foundation

OWNER_EMAIL = "land-guard-owner@example.com"


def create_land_lead(client: TestClient) -> str:
    response = client.post(
        "/api/v1/leads",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "contact": {
                "legal_name": "Land Seller",
                "contact_type": "seller",
            },
            "property": {
                "street_address": "100 Rural Route",
                "city": "Macon",
                "state": "GA",
                "postal_code": "31201",
                "county": "Bibb",
                "property_type": "vacant_land",
                "parcel_id": "LAND-APN-100",
            },
            "asset_class": "land",
            "source": "va_outreach",
            "stage_key": "new",
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def test_land_lead_is_blocked_from_residential_underwriting_entry_points(
    db_session: Session,
    api_db_override: None,
) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Land Guard Owner",
    )
    client = TestClient(app)
    lead_id = create_land_lead(client)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}

    read_paths = (
        f"/api/v1/leads/{lead_id}/repair-estimates",
        f"/api/v1/leads/{lead_id}/repair-catalog",
        f"/api/v1/leads/{lead_id}/underwriting/manual-comps",
        f"/api/v1/leads/{lead_id}/underwriting/offer-plans",
        f"/api/v1/leads/{lead_id}/underwriting/negotiation-ledger",
        f"/api/v1/leads/{lead_id}/underwriting/market-value",
        f"/api/v1/leads/{lead_id}/underwriting/market-analysis",
    )
    for path in read_paths:
        response = client.get(path, headers=headers)
        assert response.status_code == 409, (path, response.text)
        assert "not available for Land leads yet" in response.json()["detail"]

    manual_underwriting = client.post(
        f"/api/v1/leads/{lead_id}/underwriting",
        headers=headers,
        json={
            "status": "needs_review",
            "arv_low_cents": 10_000_000,
            "arv_high_cents": 12_000_000,
            "repair_low_cents": 1_000_000,
            "repair_high_cents": 2_000_000,
            "recommended_offer_cents": 5_000_000,
        },
    )
    assert manual_underwriting.status_code == 409, manual_underwriting.text

    market_analysis = client.post(
        f"/api/v1/leads/{lead_id}/underwriting/market-analysis",
        headers=headers,
        json={},
    )
    assert market_analysis.status_code == 409, market_analysis.text

    valuation_stage = client.patch(
        f"/api/v1/leads/{lead_id}/stage",
        headers=headers,
        json={"stage_key": "underwriting", "reason": "Dedicated Land valuation started."},
    )
    assert valuation_stage.status_code == 200, valuation_stage.text
    restricted_stage = client.patch(
        f"/api/v1/leads/{lead_id}/stage",
        headers=headers,
        json={
            "stage_key": "offer_pending_approval",
            "reason": "Land offer approval is not released.",
        },
    )
    assert restricted_stage.status_code == 409, restricted_stage.text

    write_requests = (
        (
            f"/api/v1/leads/{lead_id}/repair-estimates",
            {
                "source_type": "internal_scope",
                "estimate_date": "2026-08-08T12:00:00Z",
                "scope_items": [
                    {
                        "category": "roof",
                        "estimated_cost_cents": 1_000_000,
                        "details": "Residential roof replacement must not be saved for Land.",
                    }
                ],
            },
        ),
        (
            f"/api/v1/leads/{lead_id}/underwriting/manual-comps",
            {
                "street_address": "300 House Comp Street",
                "city": "Macon",
                "state": "GA",
                "postal_code": "31201",
                "sale_date": "2026-07-01",
                "sale_price_cents": 25_000_000,
                "arms_length_verified": True,
                "arms_length_evidence": "Recorded warranty deed reviewed by staff.",
                "property_type": "single_family",
                "square_footage": 1800,
                "source_type": "county_record",
                "source_reference": "Bibb deed book test reference",
                "verification_notes": "Human verified residential comp retained only for test.",
            },
        ),
        (
            f"/api/v1/leads/{lead_id}/underwriting/offer-plans",
            {
                "underwriting_version_id": str(uuid4()),
                "rationale": "A Land lead must be rejected before the House version is loaded.",
            },
        ),
        (
            f"/api/v1/leads/{lead_id}/underwriting/concessions",
            {
                "offer_negotiation_plan_id": str(uuid4()),
                "previous_offer_cents": 10_000_000,
                "proposed_offer_cents": 11_000_000,
                "reason": "Residential concession must remain blocked for a Land lead.",
                "seller_exchange": "Seller requested a higher House offer.",
            },
        ),
        (
            f"/api/v1/leads/{lead_id}/underwriting/negotiation-events",
            {
                "offer_negotiation_plan_id": str(uuid4()),
                "event_type": "price_discussion",
                "channel": "phone",
                "notes": "Residential price discussion must remain blocked.",
            },
        ),
        (
            f"/api/v1/leads/{lead_id}/transactions",
            {
                "contract_type": "purchase_agreement",
                "purchase_price_cents": 10_000_000,
                "notes": "Residential transaction creation must remain blocked.",
            },
        ),
    )
    for path, payload in write_requests:
        response = client.post(path, headers=headers, json=payload)
        assert response.status_code == 409, (path, response.text)
        assert "not available for Land leads yet" in response.json()["detail"]

    retired_offer_entry = client.post(
        f"/api/v1/leads/{lead_id}/buyer-offers",
        headers=headers,
        json={
            "buyer_id": str(uuid4()),
            "amount_cents": 12_000_000,
            "financing_type": "cash",
            "status": "received",
        },
    )
    assert retired_offer_entry.status_code == 410, retired_offer_entry.text
    assert "Offer Room" in retired_offer_entry.json()["detail"]

    for model in (
        UnderwritingVersion,
        UnderwritingMarketAnalysis,
        RepairEstimate,
        OfferNegotiationPlan,
        Transaction,
        BuyerOffer,
        Deal,
    ):
        assert int(db_session.scalar(select(func.count()).select_from(model)) or 0) == 0


def test_land_appointment_cannot_start_the_residential_field_workflow(
    db_session: Session,
    api_db_override: None,
) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Land Guard Owner",
    )
    client = TestClient(app)
    lead_id = create_land_lead(client)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    appointment_response = client.post(
        f"/api/v1/leads/{lead_id}/appointments",
        headers=headers,
        json={
            "appointment_type": "walkthrough",
            "scheduled_start_at": "2030-08-09T14:00:00Z",
            "scheduled_end_at": "2030-08-09T15:00:00Z",
            "location_type": "property",
            "location": "100 Rural Route, Macon, GA 31201",
        },
    )
    assert appointment_response.status_code == 201, appointment_response.text
    appointment_id = appointment_response.json()["appointments"][0]["id"]

    for suffix in ("brief", "inspection"):
        response = client.post(
            f"/api/v1/field-operations/appointments/{appointment_id}/{suffix}",
            headers=headers,
        )
        assert response.status_code == 409, response.text
        assert "not available for Land leads yet" in response.json()["detail"]


def test_pending_house_execution_cannot_continue_after_lead_becomes_land(
    db_session: Session,
    api_db_override: None,
) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Land Guard Owner",
    )
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    create_response = client.post(
        "/api/v1/leads",
        headers=headers,
        json={
            "contact": {"legal_name": "Reclassified Seller", "contact_type": "seller"},
            "property": {
                "street_address": "200 Main Street",
                "city": "Macon",
                "state": "GA",
                "postal_code": "31201",
                "property_type": "single_family",
            },
            "asset_class": "house",
            "source": "manual",
            "stage_key": "new",
        },
    )
    lead_id = create_response.json()["id"]
    underwriting = client.post(
        f"/api/v1/leads/{lead_id}/underwriting",
        headers=headers,
        json={
            "status": "needs_review",
            "arv_low_cents": 30_000_000,
            "arv_high_cents": 33_000_000,
            "repair_low_cents": 6_000_000,
            "repair_high_cents": 7_500_000,
            "max_offer_cents": 20_000_000,
            "recommended_offer_cents": 18_000_000,
        },
    )
    assert underwriting.status_code == 201, underwriting.text
    version_id = underwriting.json()["underwriting_versions"][0]["id"]
    plan = client.post(
        f"/api/v1/leads/{lead_id}/underwriting/offer-plans",
        headers=headers,
        json={
            "underwriting_version_id": version_id,
            "rationale": "Create a pending plan before the asset classification changes.",
        },
    )
    assert plan.status_code == 201, plan.text
    transaction_response = client.post(
        f"/api/v1/leads/{lead_id}/transactions",
        headers=headers,
        json={
            "contract_type": "purchase_agreement",
            "purchase_price_cents": 18_000_000,
            "notes": "Created before the asset is reclassified for guard testing.",
        },
    )
    assert transaction_response.status_code == 201, transaction_response.text
    transaction_id = transaction_response.json()["transactions"][0]["id"]

    reclassification = client.patch(
        f"/api/v1/leads/{lead_id}",
        headers=headers,
        json={
            "asset_class": "land",
            "reason": "This must be rejected while transaction work is active.",
        },
    )
    assert reclassification.status_code == 422, reclassification.text
    assert "active transaction" in reclassification.json()["detail"]

    lead = db_session.get(Lead, UUID(lead_id))
    assert lead is not None
    lead.asset_class = "land"
    db_session.commit()

    decision = client.patch(
        f"/api/v1/approvals/{plan.json()['approval_request_id']}/decision",
        headers=headers,
        json={"status": "approved", "decision_notes": "This must remain blocked."},
    )
    assert decision.status_code == 409, decision.text
    assert "not available for Land leads yet" in decision.json()["detail"]

    legacy_detail = client.get(f"/api/v1/transactions/{transaction_id}", headers=headers)
    assert legacy_detail.status_code == 200, legacy_detail.text

    transaction_update = client.patch(
        f"/api/v1/transactions/{transaction_id}",
        headers=headers,
        json={"notes": "This residential transaction mutation must remain blocked."},
    )
    assert transaction_update.status_code == 409, transaction_update.text

    contract_package = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages",
        headers=headers,
        json={
            "document_type": "purchase_agreement",
            "seller_name": "Reclassified Seller",
            "buyer_entity_name": "Stonegate Home Buyers",
            "purchase_price_cents": 18_000_000,
        },
    )
    assert contract_package.status_code == 409, contract_package.text
    assert int(db_session.scalar(select(func.count()).select_from(ContractPackage)) or 0) == 0

    cancellation = client.post(
        f"/api/v1/transactions/{transaction_id}/close",
        headers=headers,
        json={"outcome": "cancelled", "notes": "Close the incompatible legacy workflow."},
    )
    assert cancellation.status_code == 200, cancellation.text
    assert cancellation.json()["status"] == "cancelled"
