from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.main import app
from app.models.foundation import (
    AuditEvent,
    Buyer,
    BuyerDiscoveryCandidate,
    BuyerDiscoveryRun,
    BuyerProofDocument,
    CompensationPlanRole,
    CompensationPlanVersion,
    DealDeduction,
    DispositionBuyerPoolCandidate,
    DispositionBuyerPoolEntry,
    DispositionBuyerPoolRun,
    DispositionCampaign,
    DispositionCopilotRecommendation,
    DispositionCopilotReview,
    DispositionMatch,
    DispositionOperatingMode,
    Lead,
    RevenueRecord,
    Role,
    RoleAssignment,
    RoleCredit,
    Transaction,
    User,
)
from app.services.bootstrap import bootstrap_foundation

OWNER_EMAIL = "owner@example.com"
HEADERS = {"X-Dev-User-Email": OWNER_EMAIL}


def put_verified_buy_box(
    client: TestClient,
    buyer_id: str,
    *,
    asset_class: str = "house",
) -> dict[str, Any]:
    if asset_class == "house":
        criteria: dict[str, Any] = {
            "asset_class": "house",
            "geographies": [
                {"jurisdiction": "city", "value": "Atlanta", "state": "GA"}
            ],
            "strategies": ["wholesale_assignment"],
            "min_price_cents": 10000000,
            "max_price_cents": 30000000,
            "funding_methods": ["cash"],
            "property_types": ["single_family"],
        }
    else:
        criteria = {
            "asset_class": "land",
            "geographies": [
                {"jurisdiction": "city", "value": "Atlanta", "state": "GA"}
            ],
            "strategies": ["land_hold"],
            "min_price_cents": 1000000,
            "max_price_cents": 30000000,
            "funding_methods": ["cash"],
            "min_acres": 1,
            "max_acres": 20,
            "intended_uses": ["hold"],
        }
    response = client.put(
        f"/api/v1/buyers/{buyer_id}/buy-boxes/{asset_class}",
        headers=HEADERS,
        json={
            "expected_version": 0,
            "source": "buyer_interview",
            "change_reason": f"Confirmed {asset_class} criteria for disposition testing.",
            "verification_status": "verified",
            "criteria": criteria,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def upload_received_proof(
    client: TestClient,
    buyer_id: str,
    *,
    amount_cents: int = 40000000,
    expires_at: datetime | None = None,
) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/dispositions/buyers/{buyer_id}/proof",
        headers={**HEADERS, "Content-Type": "application/pdf"},
        params={
            "file_name": "proof.pdf",
            "content_type": "application/pdf",
            "institution_name": "Example Bank",
            "verified_amount_cents": amount_cents,
            "expires_at": (
                expires_at or datetime.now(UTC) + timedelta(days=90)
            ).isoformat(),
        },
        content=b"%PDF proof of funds awaiting human verification",
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "received"
    assert response.json()["verified_by_user_id"] is None
    assert response.json()["verified_at"] is None
    return response.json()


def verify_proof(
    client: TestClient,
    proof_id: str,
    *,
    amount_cents: int = 40000000,
    expires_at: datetime | None = None,
) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/dispositions/proof-documents/{proof_id}/verification",
        headers=HEADERS,
        json={
            "decision": "verified",
            "verification_source": "manual_document_review",
            "institution_name": "Example Bank",
            "verified_amount_cents": amount_cents,
            "expires_at": (
                expires_at or datetime.now(UTC) + timedelta(days=90)
            ).isoformat(),
            "notes": "Amount, institution, and expiration were reviewed by a human.",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "verified"
    assert response.json()["verified_by_user_id"] is not None
    assert response.json()["verified_at"] is not None
    return response.json()


def setup_case_foundation(db: Session, client: TestClient) -> tuple[str, str, str]:
    bootstrap_foundation(
        db,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    owner = db.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert owner is not None
    lead_response = client.post(
        "/api/v1/leads",
        headers=HEADERS,
        json={
            "contact": {"legal_name": "Disposition Seller", "contact_type": "seller"},
            "property": {
                "street_address": "900 Buyer Lane",
                "city": "Atlanta",
                "state": "GA",
                "postal_code": "30303",
                "property_type": "single_family",
            },
            "source": "referral",
            "stage_key": "offer_ready",
        },
    )
    lead_id = lead_response.json()["id"]
    transaction_response = client.post(
        f"/api/v1/leads/{lead_id}/transactions",
        headers=HEADERS,
        json={"purchase_price_cents": 15000000},
    )
    transaction_id = transaction_response.json()["transactions"][0]["id"]
    transaction = db.get(Transaction, UUID(transaction_id))
    lead = db.get(Lead, UUID(lead_id))
    assert transaction is not None and lead is not None
    transaction.status = "executed"
    lead.stage_key = "under_contract"

    plan = CompensationPlanVersion(
        organization_id=owner.organization_id,
        name="Stonegate Standard",
        version_number=1,
        status="active",
        acquisition_reserve_cents=250000,
        target_company_margin_basis_points=3000,
        effective_start_at=datetime.now(UTC),
        effective_end_at=None,
        created_by_user_id=owner.id,
        approved_by_user_id=owner.id,
        approved_at=datetime.now(UTC),
        notes=None,
    )
    db.add(plan)
    db.flush()
    role_specs = {
        "lead_manager": (1000, None),
        "acquisitions_closer": (1000, None),
        "ceo_management": (1000, None),
        "dispositions": (1500, None),
        "transaction_coordinator": (500, 100000),
    }
    for role_key, (basis_points, cap_cents) in role_specs.items():
        db.add(
            CompensationPlanRole(
                organization_id=owner.organization_id,
                compensation_plan_version_id=plan.id,
                role_key=role_key,
                basis_points=basis_points,
                cap_cents=cap_cents,
                notes=None,
            )
        )
        db.add(
            RoleCredit(
                organization_id=owner.organization_id,
                compensation_plan_version_id=plan.id,
                lead_id=lead.id,
                user_id=owner.id,
                role_key=role_key,
                credit_basis_points=10000,
                status="approved",
                assigned_by_user_id=owner.id,
                approved_by_user_id=owner.id,
                approved_at=datetime.now(UTC),
                notes="Test contribution evidence.",
            )
        )
    db.add(
        DispositionOperatingMode(
            organization_id=owner.organization_id,
            compensation_plan_version_id=plan.id,
            key="human_led",
            name="Human-led",
            status="available",
            human_share_min_basis_points=1500,
            human_share_max_basis_points=1500,
            expected_company_share_min_basis_points=5000,
            expected_company_share_max_basis_points=5000,
            ai_authority_level="human_execution",
            activation_requirements={},
        )
    )
    db.commit()

    buyer_response = client.post(
        "/api/v1/buyers",
        headers=HEADERS,
        json={
            "name": "Reliable Atlanta Buyer",
            "email": "reliable-atlanta@example.com",
            "buyer_type": "cash_buyer",
            "status": "active",
            "max_purchase_price_cents": 30000000,
            "criteria": {
                "markets": "Atlanta, GA",
                "property_types": "single_family",
                "max_price_cents": 30000000,
            },
        },
    )
    assert buyer_response.status_code == 201, buyer_response.text
    buyer_id = buyer_response.json()["id"]
    assert buyer_response.json()["status"] == "needs_review"
    activation = client.patch(
        f"/api/v1/buyers/{buyer_id}",
        headers=HEADERS,
        json={"status": "active"},
    )
    assert activation.status_code == 200, activation.text
    return lead_id, transaction_id, buyer_id


def create_approved_disposition_case(client: TestClient, transaction_id: str) -> str:
    created = client.post(
        "/api/v1/dispositions/cases",
        headers=HEADERS,
        json={
            "transaction_id": transaction_id,
            "strategy": "assignment",
            "asking_price_cents": 19000000,
            "minimum_acceptable_cents": 18000000,
            "operating_mode_key": "human_led",
        },
    )
    assert created.status_code == 201, created.text
    case_id = created.json()["id"]
    approved = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/approve",
        headers=HEADERS,
    )
    assert approved.status_code == 200, approved.text
    return case_id


def test_disposition_buyer_selection_and_reconciliation(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    lead_id, transaction_id, buyer_id = setup_case_foundation(db_session, client)
    created = client.post(
        "/api/v1/dispositions/cases",
        headers=HEADERS,
        json={
            "transaction_id": transaction_id,
            "strategy": "assignment",
            "asking_price_cents": 19000000,
            "minimum_acceptable_cents": 18000000,
            "operating_mode_key": "human_led",
        },
    )
    assert created.status_code == 201, created.text
    case_id = created.json()["id"]
    assert created.json()["compensation_plan_label"] == "Stonegate Standard v1"

    assert (
        client.post(
            f"/api/v1/dispositions/cases/{case_id}/package/approve", headers=HEADERS
        ).status_code
        == 200
    )
    unmatched = client.post(f"/api/v1/dispositions/cases/{case_id}/matches", headers=HEADERS)
    assert unmatched.status_code == 200
    assert unmatched.json()["matches"][0]["qualification_status"] == "review_required"
    assert (
        client.post(
            f"/api/v1/dispositions/cases/{case_id}/campaigns/release", headers=HEADERS
        ).status_code
        == 422
    )

    proof = upload_received_proof(client, buyer_id)
    assert proof["storage_provider"] == "database"
    assert proof["malware_scan_status"] == "not_configured"
    proof_content = client.get(proof["content_url"], headers=HEADERS)
    assert proof_content.status_code == 200
    assert proof_content.content == b"%PDF proof of funds awaiting human verification"
    download_audit = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "buyer.proof_download",
            AuditEvent.entity_id == UUID(proof["id"]),
        )
    )
    assert download_audit is not None

    # Uploading a document does not verify it, and the legacy free-text criteria are
    # deliberately excluded from authoritative House matching.
    matched = client.post(f"/api/v1/dispositions/cases/{case_id}/matches", headers=HEADERS)
    assert matched.status_code == 200, matched.text
    assert matched.json()["matches"][0]["qualification_status"] == "review_required"

    verified_proof = verify_proof(client, proof["id"])
    assert verified_proof["verified_amount_cents"] == 40000000
    legacy_only = client.post(
        f"/api/v1/dispositions/cases/{case_id}/matches", headers=HEADERS
    )
    assert legacy_only.status_code == 200, legacy_only.text
    assert legacy_only.json()["matches"][0]["qualification_status"] == "review_required"
    legacy_match = db_session.scalar(
        select(DispositionMatch).where(
            DispositionMatch.disposition_case_id == UUID(case_id),
            DispositionMatch.buyer_id == UUID(buyer_id),
        )
    )
    assert legacy_match is not None
    assert legacy_match.buy_box_version_id is None
    assert legacy_match.criteria_snapshot["legacy_criteria_excluded"] is True

    # A verified Land buy box remains isolated from a House disposition case.
    put_verified_buy_box(client, buyer_id, asset_class="land")
    land_only = client.post(
        f"/api/v1/dispositions/cases/{case_id}/matches", headers=HEADERS
    )
    assert land_only.status_code == 200, land_only.text
    assert land_only.json()["matches"][0]["qualification_status"] == "review_required"

    house_box = put_verified_buy_box(client, buyer_id, asset_class="house")
    matched = client.post(f"/api/v1/dispositions/cases/{case_id}/matches", headers=HEADERS)
    assert matched.status_code == 200, matched.text
    assert matched.json()["matches"][0]["qualification_status"] == "qualified"
    assert matched.json()["matches"][0]["score_basis_points"] == 8500
    stored_match = db_session.scalar(
        select(DispositionMatch).where(
            DispositionMatch.disposition_case_id == UUID(case_id),
            DispositionMatch.buyer_id == UUID(buyer_id),
        )
    )
    assert stored_match is not None
    assert str(stored_match.buy_box_version_id) == house_box["id"]
    assert stored_match.matcher_version == "house_buy_box_v1"
    assert stored_match.criteria_snapshot["criteria"]["asset_class"] == "house"
    assert (
        client.post(
            f"/api/v1/dispositions/cases/{case_id}/campaigns/release", headers=HEADERS
        ).status_code
        == 200
    )

    offer = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offers",
        headers=HEADERS,
        json={
            "buyer_id": buyer_id,
            "amount_cents": 19000000,
            "earnest_money_cents": 500000,
            "financing_type": "cash",
            "proof_document_id": proof["id"],
        },
    )
    assert offer.status_code == 200, offer.text
    offer_id = offer.json()["offers"][0]["id"]
    selection = client.post(
        f"/api/v1/dispositions/cases/{case_id}/buyer-selection",
        headers=HEADERS,
        json={
            "primary_offer_id": offer_id,
            "reason": "Verified funds, acceptable price, and local closing history.",
        },
    )
    assert selection.status_code == 200, selection.text
    assert selection.json()["selected_buyer_id"] == buyer_id

    transaction = db_session.get(Transaction, UUID(transaction_id))
    assert transaction is not None
    transaction.status = "funded"
    db_session.add(
        RevenueRecord(
            organization_id=transaction.organization_id,
            lead_id=UUID(lead_id),
            deal_id=transaction.deal_id,
            transaction_id=transaction.id,
            source="assignment_fee",
            status="collected",
            amount_cents=4000000,
            received_at=datetime.now(UTC),
            notes=None,
        )
    )
    db_session.add(
        DealDeduction(
            organization_id=transaction.organization_id,
            lead_id=UUID(lead_id),
            deal_id=transaction.deal_id,
            transaction_id=transaction.id,
            category="closing_cost",
            amount_cents=250000,
            incurred_at=datetime.now(UTC),
            notes=None,
        )
    )
    db_session.commit()

    reconciliation = client.post(
        f"/api/v1/dispositions/cases/{case_id}/reconciliation", headers=HEADERS
    )
    assert reconciliation.status_code == 200, reconciliation.text
    statement = reconciliation.json()["reconciliation"]
    assert statement["adjusted_deal_margin_cents"] == 3500000
    assert statement["total_compensation_cents"] == 1675000
    assert statement["company_profit_cents"] == 1825000
    assert statement["company_margin_basis_points"] == 5214
    approval = client.post(
        f"/api/v1/dispositions/cases/{case_id}/reconciliation/decision",
        headers=HEADERS,
        json={"decision": "approved", "notes": "Closing statement verified."},
    )
    assert approval.status_code == 200, approval.text
    assert approval.json()["reconciliation"]["status"] == "approved"
    export = client.get(f"/api/v1/dispositions/cases/{case_id}/accounting.csv", headers=HEADERS)
    assert export.status_code == 200
    assert "company_profit,company,,1825000,approved" in export.text


def test_buyer_selection_requires_current_proof_of_funds(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    _, transaction_id, buyer_id = setup_case_foundation(db_session, client)
    case = client.post(
        "/api/v1/dispositions/cases",
        headers=HEADERS,
        json={
            "transaction_id": transaction_id,
            "asking_price_cents": 19000000,
            "minimum_acceptable_cents": 18000000,
        },
    ).json()
    proof = upload_received_proof(client, buyer_id)
    verify_proof(client, proof["id"])
    offer = client.post(
        f"/api/v1/dispositions/cases/{case['id']}/offers",
        headers=HEADERS,
        json={
            "buyer_id": buyer_id,
            "amount_cents": 19000000,
            "proof_document_id": proof["id"],
        },
    )
    assert offer.status_code == 200, offer.text
    proof_row = db_session.get(BuyerProofDocument, UUID(proof["id"]))
    assert proof_row is not None
    proof_row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.commit()
    response = client.post(
        f"/api/v1/dispositions/cases/{case['id']}/buyer-selection",
        headers=HEADERS,
        json={
            "primary_offer_id": offer.json()["offers"][0]["id"],
            "reason": "Attempt without verified evidence.",
        },
    )
    assert response.status_code == 422
    assert "proof-of-funds" in response.json()["detail"]


def test_proof_upload_requires_explicit_complete_human_verification(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    _, _, buyer_id = setup_case_foundation(db_session, client)
    uploaded = client.post(
        f"/api/v1/dispositions/buyers/{buyer_id}/proof",
        headers={**HEADERS, "Content-Type": "application/pdf"},
        params={
            "file_name": "unreviewed-proof.pdf",
            "content_type": "application/pdf",
        },
        content=b"%PDF unreviewed proof evidence",
    )
    assert uploaded.status_code == 201, uploaded.text
    document = uploaded.json()
    assert document["status"] == "received"
    assert document["verified_amount_cents"] is None
    assert document["expires_at"] is None

    missing_amount = client.post(
        f"/api/v1/dispositions/proof-documents/{document['id']}/verification",
        headers=HEADERS,
        json={
            "decision": "verified",
            "verification_source": "manual_document_review",
            "expires_at": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
            "notes": "Controlled review missing the verified amount.",
        },
    )
    assert missing_amount.status_code == 422
    assert "amount" in missing_amount.json()["detail"].lower()

    expired = client.post(
        f"/api/v1/dispositions/proof-documents/{document['id']}/verification",
        headers=HEADERS,
        json={
            "decision": "verified",
            "verification_source": "manual_document_review",
            "verified_amount_cents": 40000000,
            "expires_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
            "notes": "Controlled review with stale evidence.",
        },
    )
    assert expired.status_code == 422
    assert "future expiration" in expired.json()["detail"].lower()

    for invalid_field in ("verification_source", "notes"):
        review_payload = {
            "decision": "verified",
            "verification_source": "manual_document_review",
            "verified_amount_cents": 40000000,
            "expires_at": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
            "notes": "Controlled complete human review.",
        }
        review_payload[invalid_field] = "  "
        whitespace_only = client.post(
            f"/api/v1/dispositions/proof-documents/{document['id']}/verification",
            headers=HEADERS,
            json=review_payload,
        )
        assert whitespace_only.status_code == 422

    verified = verify_proof(client, document["id"])
    assert verified["verification_source"] == "manual_document_review"


def test_proof_renewal_keeps_current_verified_document_attached_to_match(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    _, transaction_id, buyer_id = setup_case_foundation(db_session, client)
    created = client.post(
        "/api/v1/dispositions/cases",
        headers=HEADERS,
        json={
            "transaction_id": transaction_id,
            "asking_price_cents": 19000000,
            "minimum_acceptable_cents": 18000000,
        },
    )
    assert created.status_code == 201, created.text
    case_id = created.json()["id"]
    approved = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/approve",
        headers=HEADERS,
    )
    assert approved.status_code == 200, approved.text
    put_verified_buy_box(client, buyer_id)

    current = upload_received_proof(client, buyer_id)
    verify_proof(client, current["id"])
    renewal = upload_received_proof(
        client,
        buyer_id,
        expires_at=datetime.now(UTC) + timedelta(days=180),
    )

    matched = client.post(
        f"/api/v1/dispositions/cases/{case_id}/matches",
        headers=HEADERS,
    )
    assert matched.status_code == 200, matched.text
    match = matched.json()["matches"][0]
    assert match["qualification_status"] == "qualified"
    assert match["proof_status"] == "verified"
    assert match["latest_proof_document_id"] == current["id"]
    assert match["latest_proof_document_id"] != renewal["id"]

    offer = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offers",
        headers=HEADERS,
        json={
            "buyer_id": buyer_id,
            "amount_cents": 19000000,
            "financing_type": "cash",
            "proof_document_id": match["latest_proof_document_id"],
        },
    )
    assert offer.status_code == 200, offer.text
    selected = client.post(
        f"/api/v1/dispositions/cases/{case_id}/buyer-selection",
        headers=HEADERS,
        json={
            "primary_offer_id": offer.json()["offers"][0]["id"],
            "reason": "Current verified proof remains attached during renewal review.",
        },
    )
    assert selected.status_code == 200, selected.text


def test_disposition_copilot_prefers_current_proof_over_stale_renewal_evidence(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    _, transaction_id, buyer_id = setup_case_foundation(db_session, client)
    created = client.post(
        "/api/v1/dispositions/cases",
        headers=HEADERS,
        json={
            "transaction_id": transaction_id,
            "asking_price_cents": 19000000,
            "minimum_acceptable_cents": 18000000,
        },
    )
    assert created.status_code == 201, created.text
    case_id = created.json()["id"]
    assert (
        client.post(
            f"/api/v1/dispositions/cases/{case_id}/package/approve",
            headers=HEADERS,
        ).status_code
        == 200
    )
    put_verified_buy_box(client, buyer_id)
    now = datetime.now(UTC)
    current = upload_received_proof(
        client,
        buyer_id,
        expires_at=now + timedelta(days=90),
    )
    verify_proof(
        client,
        current["id"],
        expires_at=now + timedelta(days=90),
    )
    stale = upload_received_proof(
        client,
        buyer_id,
        expires_at=now + timedelta(days=180),
    )
    verify_proof(
        client,
        stale["id"],
        expires_at=now + timedelta(days=180),
    )
    stale_row = db_session.get(BuyerProofDocument, UUID(stale["id"]))
    assert stale_row is not None
    stale_row.expires_at = now - timedelta(days=1)
    stale_row.verified_at = now + timedelta(minutes=1)
    db_session.commit()
    upload_received_proof(
        client,
        buyer_id,
        expires_at=now + timedelta(days=365),
    )

    matched = client.post(
        f"/api/v1/dispositions/cases/{case_id}/matches",
        headers=HEADERS,
    )
    assert matched.status_code == 200, matched.text
    assert matched.json()["matches"][0]["qualification_status"] == "qualified"
    overview = client.get(
        f"/api/v1/dispositions/cases/{case_id}/copilot",
        headers=HEADERS,
    )

    assert overview.status_code == 200, overview.text
    payload = overview.json()
    assert payload["verified_buyer_count"] == 1
    assert all(
        risk["reason"] != "Proof of funds is expired."
        for risk in payload["risk_alerts"]
    )


def test_campaign_release_rechecks_expired_proof_after_match(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    _, transaction_id, buyer_id = setup_case_foundation(db_session, client)
    created = client.post(
        "/api/v1/dispositions/cases",
        headers=HEADERS,
        json={
            "transaction_id": transaction_id,
            "asking_price_cents": 19000000,
            "minimum_acceptable_cents": 18000000,
        },
    )
    assert created.status_code == 201, created.text
    case_id = created.json()["id"]
    approved = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/approve",
        headers=HEADERS,
    )
    assert approved.status_code == 200, approved.text
    put_verified_buy_box(client, buyer_id)
    proof = upload_received_proof(client, buyer_id)
    verify_proof(client, proof["id"])
    matched = client.post(
        f"/api/v1/dispositions/cases/{case_id}/matches",
        headers=HEADERS,
    )
    assert matched.status_code == 200, matched.text
    assert matched.json()["matches"][0]["qualification_status"] == "qualified"

    proof_row = db_session.get(BuyerProofDocument, UUID(proof["id"]))
    assert proof_row is not None
    proof_row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.commit()

    released = client.post(
        f"/api/v1/dispositions/cases/{case_id}/campaigns/release",
        headers=HEADERS,
    )
    assert released.status_code == 422, released.text
    assert "currently active qualified buyers" in released.json()["detail"]
    db_session.expire_all()
    stored_match = db_session.scalar(
        select(DispositionMatch).where(
            DispositionMatch.disposition_case_id == UUID(case_id),
            DispositionMatch.buyer_id == UUID(buyer_id),
        )
    )
    assert stored_match is not None
    assert stored_match.qualification_status == "ineligible"
    assert stored_match.recipient_status == "excluded"


def test_proof_document_is_tenant_scoped_permissioned_and_download_audited(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    _, _, buyer_id = setup_case_foundation(db_session, client)
    proof = upload_received_proof(client, buyer_id)

    owner = db_session.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert owner is not None
    read_only_role = db_session.scalar(
        select(Role).where(
            Role.organization_id == owner.organization_id,
            Role.key == "read_only_partner",
        )
    )
    assert read_only_role is not None
    viewer = User(
        organization_id=owner.organization_id,
        email="proof-viewer@example.com",
        display_name="Proof Viewer Without Permission",
        external_auth_id=None,
        is_active=True,
        calling_enabled=False,
    )
    db_session.add(viewer)
    db_session.flush()
    db_session.add(
        RoleAssignment(
            organization_id=owner.organization_id,
            user_id=viewer.id,
            role_id=read_only_role.id,
        )
    )
    db_session.commit()
    viewer_headers = {"X-Dev-User-Email": viewer.email}
    assert client.get(proof["content_url"], headers=viewer_headers).status_code == 403
    assert (
        client.post(
            f"/api/v1/dispositions/proof-documents/{proof['id']}/verification",
            headers=viewer_headers,
            json={
                "decision": "rejected",
                "verification_source": "manual_document_review",
                "notes": "Viewer must not be able to decide restricted evidence.",
            },
        ).status_code
        == 403
    )

    other = bootstrap_foundation(
        db_session,
        organization_name="Other Buyer Organization",
        admin_email="other-proof-owner@example.com",
        admin_name="Other Owner",
    )
    other_headers = {"X-Dev-User-Email": other.admin_user.email}
    assert client.get(proof["content_url"], headers=other_headers).status_code == 404
    assert (
        client.post(
            f"/api/v1/dispositions/proof-documents/{proof['id']}/verification",
            headers=other_headers,
            json={
                "decision": "rejected",
                "verification_source": "manual_document_review",
                "notes": "Cross-tenant access must not reveal document existence.",
            },
        ).status_code
        == 404
    )

    downloaded = client.get(proof["content_url"], headers=HEADERS)
    assert downloaded.status_code == 200
    audit_event = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "buyer.proof_download",
            AuditEvent.entity_id == UUID(proof["id"]),
            AuditEvent.actor_user_id == owner.id,
        )
    )
    assert audit_event is not None


@pytest.mark.parametrize(
    ("buyer_status", "relationship_status", "archived"),
    [
        ("paused", "active", False),
        ("do_not_contact", "active", False),
        ("active", "do_not_contact", False),
        ("archived", "active", True),
    ],
)
def test_campaign_release_rechecks_buyer_lifecycle_after_matching(
    db_session: Session,
    api_db_override: None,
    buyer_status: str,
    relationship_status: str,
    archived: bool,
) -> None:
    client = TestClient(app)
    _, transaction_id, buyer_id = setup_case_foundation(db_session, client)
    created = client.post(
        "/api/v1/dispositions/cases",
        headers=HEADERS,
        json={
            "transaction_id": transaction_id,
            "asking_price_cents": 19000000,
            "minimum_acceptable_cents": 18000000,
        },
    )
    assert created.status_code == 201, created.text
    case_id = created.json()["id"]
    assert (
        client.post(
            f"/api/v1/dispositions/cases/{case_id}/package/approve",
            headers=HEADERS,
        ).status_code
        == 200
    )
    put_verified_buy_box(client, buyer_id)
    proof = upload_received_proof(client, buyer_id)
    verify_proof(client, proof["id"])
    matched = client.post(
        f"/api/v1/dispositions/cases/{case_id}/matches",
        headers=HEADERS,
    )
    assert matched.status_code == 200, matched.text
    assert matched.json()["matches"][0]["qualification_status"] == "qualified"

    buyer = db_session.get(Buyer, UUID(buyer_id))
    assert buyer is not None
    buyer.status = buyer_status
    buyer.relationship_status = relationship_status
    buyer.archived_at = datetime.now(UTC) if archived else None
    db_session.commit()

    copilot = client.get(
        f"/api/v1/dispositions/cases/{case_id}/copilot",
        headers=HEADERS,
    )
    assert copilot.status_code == 200, copilot.text
    assert copilot.json()["qualified_buyer_count"] == 0
    assert copilot.json()["verified_buyer_count"] == 0
    assert "Generate the deterministic buyer ranking." in copilot.json()["readiness_gaps"]

    release = client.post(
        f"/api/v1/dispositions/cases/{case_id}/campaigns/release",
        headers=HEADERS,
    )
    assert release.status_code == 422, release.text
    assert "currently active qualified buyers" in release.json()["detail"]

    db_session.expire_all()
    match = db_session.scalar(
        select(DispositionMatch).where(
            DispositionMatch.disposition_case_id == UUID(case_id),
            DispositionMatch.buyer_id == UUID(buyer_id),
        )
    )
    assert match is not None
    assert match.qualification_status == "ineligible"
    assert match.recipient_status == "excluded"
    campaign_count = db_session.scalar(
        select(func.count(DispositionCampaign.id)).where(
            DispositionCampaign.disposition_case_id == UUID(case_id)
        )
    )
    assert campaign_count == 0


def test_disposition_copilot_generates_reviewed_draft_without_taking_action(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = TestClient(app)
    lead_id, transaction_id, buyer_id = setup_case_foundation(db_session, client)
    case = client.post(
        "/api/v1/dispositions/cases",
        headers=HEADERS,
        json={
            "transaction_id": transaction_id,
            "asking_price_cents": 19000000,
            "minimum_acceptable_cents": 18000000,
        },
    ).json()
    case_id = case["id"]
    assert (
        client.post(
            f"/api/v1/dispositions/cases/{case_id}/package/approve",
            headers=HEADERS,
        ).status_code
        == 200
    )
    put_verified_buy_box(client, buyer_id)
    proof = upload_received_proof(client, buyer_id)
    verify_proof(client, proof["id"])
    matched = client.post(
        f"/api/v1/dispositions/cases/{case_id}/matches",
        headers=HEADERS,
    )
    assert matched.status_code == 200
    copilot_overview = client.get(
        f"/api/v1/dispositions/cases/{case_id}/copilot",
        headers=HEADERS,
    )
    assert copilot_overview.status_code == 200, copilot_overview.text
    assert copilot_overview.json()["verified_buyer_count"] == 1
    offer = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offers",
        headers=HEADERS,
        json={
            "buyer_id": buyer_id,
            "amount_cents": 19000000,
            "earnest_money_cents": 500000,
            "financing_type": "cash",
            "proof_document_id": proof["id"],
        },
    )
    assert offer.status_code == 200
    offer_id = offer.json()["offers"][0]["id"]

    with monkeypatch.context() as configured_environment:
        configured_environment.setenv("AI_ENABLED", "true")
        configured_environment.setenv("OPENAI_API_KEY", "test-openai-key")
        get_settings.cache_clear()
        assert (
            client.post(
                "/api/v1/ai/orchestrator/portfolio/install",
                headers=HEADERS,
            ).status_code
            == 201
        )
        assert (
            client.post(
                "/api/v1/ai/copilots/install",
                headers=HEADERS,
            ).status_code
            == 201
        )
        assert (
            client.post(
                "/api/v1/ai/copilots/foundation/decision",
                headers=HEADERS,
                json={"decision": "approve", "notes": "Approved for AI8 test."},
            ).status_code
            == 200
        )
        installed = client.post("/api/v1/ai/runtime/install", headers=HEADERS)
        assert installed.status_code == 201
        capability = next(
            item
            for item in installed.json()["runtime"]["capabilities"]
            if item["capability_key"] == "disposition.match"
        )
        assert capability["status"] == "enabled"
        assert capability["requires_human_review"] is True

        class FakeOpenAIResponsesClient:
            def __init__(self, **_: object) -> None:
                pass

            def create_structured_response(
                self, **kwargs: object
            ) -> tuple[dict[str, Any], dict[str, int]]:
                prompt = kwargs["user_prompt"]
                assert isinstance(prompt, str)
                assert "Disposition Seller" not in prompt
                assert "purchase_price_cents" not in prompt
                assert "minimum_acceptable_cents" not in prompt
                assert "15000000" not in prompt
                assert "18000000" not in prompt
                assert '"meets_internal_floor": true' in prompt
                schema = kwargs["json_schema"]
                assert isinstance(schema, dict)
                assert schema["additionalProperties"] is False
                return (
                    {
                        "status_summary": (
                            "One verified local buyer has submitted an acceptable offer."
                        ),
                        "package_gaps": [],
                        "package_highlights": [
                            "Atlanta single-family opportunity",
                            "Human-approved asking price is $190,000",
                        ],
                        "recommended_buyers": [
                            {
                                "buyer_id": buyer_id,
                                "buyer_name": "Reliable Atlanta Buyer",
                                "recommendation": "priority",
                                "rationale": [
                                    "Verified funds cover the asking price.",
                                    "The buyer matches the market and property type.",
                                ],
                                "risks": ["No Stonegate closing history is recorded."],
                                "evidence": [
                                    "Deterministic buyer rank 1",
                                    "Current proof-of-funds record",
                                ],
                            }
                        ],
                        "offer_comparison": [
                            {
                                "offer_id": offer_id,
                                "buyer_name": "Reliable Atlanta Buyer",
                                "strength": "strong",
                                "rationale": [
                                    "Offer meets the approved economics.",
                                    "Earnest money is recorded.",
                                ],
                                "risks": ["Deposit receipt has not been recorded."],
                            }
                        ],
                        "buyer_outreach_subject": ("Atlanta single-family investment opportunity"),
                        "buyer_outreach_body": (
                            "Stonegate has an Atlanta single-family opportunity "
                            "available at $190,000. Reply for the approved package."
                        ),
                        "recommended_internal_actions": [
                            "Confirm the deposit deadline before buyer selection."
                        ],
                        "relationship_update_proposals": [
                            "Confirm the buyer's preferred Atlanta ZIP codes."
                        ],
                        "risk_alerts": ["Maintain a backup buyer before final placement."],
                        "uncertainties": ["Stonegate closing performance is not yet recorded."],
                        "evidence": [
                            "Approved disposition package",
                            "Buyer match and offer records",
                        ],
                        "confidence": 88,
                    },
                    {"input_tokens": 180, "output_tokens": 220, "total_tokens": 400},
                )

        monkeypatch.setattr(
            "app.services.ai_runtime.OpenAIResponsesClient",
            FakeOpenAIResponsesClient,
        )
        analyzed = client.post(
            f"/api/v1/dispositions/cases/{case_id}/copilot/analyze",
            headers=HEADERS,
            json={"idempotency_key": "disposition-copilot:test:1"},
        )
        assert analyzed.status_code == 200, analyzed.text
        result = analyzed.json()
        assert result["run_status"] == "needs_review"
        assert result["recommendation"]["status"] == "draft"
        recommendation_id = result["recommendation"]["id"]

        repeated = client.post(
            f"/api/v1/dispositions/cases/{case_id}/copilot/analyze",
            headers=HEADERS,
            json={"idempotency_key": "disposition-copilot:test:1"},
        )
        assert repeated.json()["recommendation"]["id"] == recommendation_id
        review = client.post(
            f"/api/v1/dispositions/copilot/recommendations/{recommendation_id}/review",
            headers=HEADERS,
            json={
                "decision": "accepted",
                "notes": "Disposition specialist reviewed the evidence.",
                "estimated_time_saved_seconds": 600,
            },
        )
        assert review.status_code == 200, review.text
        assert review.json()["decision"] == "accepted"
        overview = client.get(
            f"/api/v1/dispositions/cases/{case_id}/copilot",
            headers=HEADERS,
        )
        assert overview.status_code == 200
        assert overview.json()["recommendations"][0]["status"] == "accepted"
        assert overview.json()["external_actions_blocked"] is True
        assert overview.json()["metrics"]["reviewed"] == 1

    get_settings.cache_clear()
    db_session.expire_all()
    refreshed_case = client.get(
        f"/api/v1/dispositions/cases/{case_id}",
        headers=HEADERS,
    ).json()
    assert refreshed_case["selected_buyer_id"] is None
    assert (
        db_session.scalar(
            select(func.count(DispositionCampaign.id)).where(
                DispositionCampaign.disposition_case_id == UUID(case_id)
            )
        )
        == 0
    )
    assert db_session.scalar(select(func.count(DispositionCopilotRecommendation.id))) == 1
    assert db_session.scalar(select(func.count(DispositionCopilotReview.id))) == 1


def test_explainable_buyer_pool_preserves_decisions_and_stages_external_candidates(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    _, transaction_id, buyer_id = setup_case_foundation(db_session, client)
    case_id = create_approved_disposition_case(client, transaction_id)
    house_box = put_verified_buy_box(client, buyer_id)
    proof = upload_received_proof(client, buyer_id)
    verify_proof(client, proof["id"])

    owner = db_session.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert owner is not None
    discovery_run = BuyerDiscoveryRun(
        organization_id=owner.organization_id,
        disposition_case_id=UUID(case_id),
        requested_by_user_id=owner.id,
        provider="dealmachine",
        status="completed",
        search_snapshot={"state": "GA", "asset_class": "house"},
        provider_request={"test": True},
        result_count=1,
        imported_count=0,
        credit_summary={"properties": 1, "people": 0},
        completed_at=datetime.now(UTC),
    )
    db_session.add(discovery_run)
    db_session.flush()
    external = BuyerDiscoveryCandidate(
        organization_id=owner.organization_id,
        discovery_run_id=discovery_run.id,
        buyer_id=None,
        provider="dealmachine",
        external_key="external-builder-1",
        name="External Builder",
        company_name="External Builder LLC",
        email="external-builder@example.com",
        phone="404-555-0199",
        market="Atlanta, GA",
        state="GA",
        property_types=["single_family"],
        observed_purchase_count=8,
        no_mortgage_count=6,
        last_purchase_date=date.today() - timedelta(days=30),
        min_purchase_price_cents=10000000,
        max_purchase_price_cents=30000000,
        score_basis_points=7200,
        score_components={"observed_activity": 7200},
        evidence_snapshot={"source": "recorded_purchase_activity"},
        provider_snapshot={"provider_id": "external-builder-1"},
        status="review",
    )
    db_session.add(external)
    db_session.commit()

    refreshed = client.post(
        f"/api/v1/dispositions/cases/{case_id}/buyer-pool/runs",
        headers=HEADERS,
    )
    assert refreshed.status_code == 200, refreshed.text
    pool = refreshed.json()
    assert pool["run"]["version_number"] == 1
    assert pool["run"]["matcher_version"] == "stonegate_buyer_pool_v1"
    assert pool["total"] == 2
    assert {item["source_type"] for item in pool["entries"]} == {"network", "external"}

    internal_entry = next(item for item in pool["entries"] if item["buyer_id"] == buyer_id)
    assert internal_entry["eligibility_status"] == "eligible"
    assert internal_entry["buy_box_version_id"] == house_box["id"]
    assert internal_entry["proof_status"] == "verified"
    assert set(internal_entry["score_components"]) == {
        "market",
        "asset",
        "price",
        "strategy",
        "funding",
        "capacity",
        "proof",
        "activity",
        "reliability",
        "relationship",
    }
    assert internal_entry["score_explanation"]

    external_entry = next(item for item in pool["entries"] if item["source_type"] == "external")
    assert external_entry["eligibility_status"] == "review_required"
    assert "explicitly approved" in external_entry["disqualifying_reasons"][0]
    buyer_count_before = int(db_session.scalar(select(func.count(Buyer.id))) or 0)
    shortlisted_external = client.patch(
        (
            f"/api/v1/dispositions/cases/{case_id}/buyer-pool/candidates/"
            f"{external_entry['candidate_id']}"
        ),
        headers=HEADERS,
        json={
            "expected_version": external_entry["lock_version"],
            "decision_status": "shortlisted",
        },
    )
    assert shortlisted_external.status_code == 200, shortlisted_external.text
    assert int(db_session.scalar(select(func.count(Buyer.id))) or 0) == buyer_count_before
    stale_external_update = client.patch(
        (
            f"/api/v1/dispositions/cases/{case_id}/buyer-pool/candidates/"
            f"{external_entry['candidate_id']}"
        ),
        headers=HEADERS,
        json={
            "expected_version": external_entry["lock_version"],
            "decision_status": "passed",
            "reason": "This stale browser state must not overwrite the shortlist.",
        },
    )
    assert stale_external_update.status_code == 422
    assert "another session" in stale_external_update.json()["detail"]

    shortlisted_internal = client.patch(
        (
            f"/api/v1/dispositions/cases/{case_id}/buyer-pool/candidates/"
            f"{internal_entry['candidate_id']}"
        ),
        headers=HEADERS,
        json={
            "expected_version": internal_entry["lock_version"],
            "decision_status": "shortlisted",
        },
    )
    assert shortlisted_internal.status_code == 200, shortlisted_internal.text

    rerun = client.post(
        f"/api/v1/dispositions/cases/{case_id}/buyer-pool/runs",
        headers=HEADERS,
    )
    assert rerun.status_code == 200, rerun.text
    assert rerun.json()["run"]["version_number"] == 2
    rerun_entries = rerun.json()["entries"]
    persisted_internal = next(item for item in rerun_entries if item["buyer_id"] == buyer_id)
    persisted_external = next(item for item in rerun_entries if item["source_type"] == "external")
    assert persisted_internal["decision_status"] == "shortlisted"
    assert persisted_external["decision_status"] == "shortlisted"
    assert persisted_internal["candidate_id"] == internal_entry["candidate_id"]
    assert persisted_external["candidate_id"] == external_entry["candidate_id"]
    assert int(db_session.scalar(select(func.count(DispositionBuyerPoolRun.id))) or 0) == 2
    assert int(db_session.scalar(select(func.count(DispositionBuyerPoolEntry.id))) or 0) == 4
    assert int(db_session.scalar(select(func.count(DispositionBuyerPoolCandidate.id))) or 0) == 2

    converted = client.post(
        (
            f"/api/v1/dispositions/cases/{case_id}/buyer-pool/candidates/"
            f"{external_entry['candidate_id']}/conversion"
        ),
        headers=HEADERS,
        json={
            "expected_version": persisted_external["lock_version"],
            "decision": "create_new",
            "reason": "Human reviewed the provider identity and approved network onboarding.",
        },
    )
    assert converted.status_code == 200, converted.text
    assert int(db_session.scalar(select(func.count(Buyer.id))) or 0) == buyer_count_before + 1
    approved_entry = next(
        item
        for item in converted.json()["entries"]
        if item["candidate_id"] == external_entry["candidate_id"]
    )
    assert approved_entry["buyer_id"] is not None
    assert approved_entry["source_type"] == "mine"
    approved_buyer = db_session.get(Buyer, UUID(approved_entry["buyer_id"]))
    assert approved_buyer is not None
    assert approved_buyer.status == "needs_review"

    post_conversion_run = client.post(
        f"/api/v1/dispositions/cases/{case_id}/buyer-pool/runs",
        headers=HEADERS,
    )
    assert post_conversion_run.status_code == 200, post_conversion_run.text
    assert post_conversion_run.json()["run"]["version_number"] == 3
    assert post_conversion_run.json()["total"] == 2
    assert all(
        item["source_type"] != "external"
        for item in post_conversion_run.json()["entries"]
    )
    approved_after_rerun = next(
        item
        for item in post_conversion_run.json()["entries"]
        if item["candidate_id"] == external_entry["candidate_id"]
    )
    assert any(
        evidence.get("type") == "provider_purchase_evidence"
        for evidence in approved_after_rerun["supporting_evidence"]
    )
    assert int(db_session.scalar(select(func.count(DispositionBuyerPoolCandidate.id))) or 0) == 2
    history = client.get(
        f"/api/v1/dispositions/cases/{case_id}/buyer-pool/runs",
        headers=HEADERS,
    )
    assert history.status_code == 200
    assert [item["version_number"] for item in history.json()] == [3, 2, 1]

    released = client.post(
        f"/api/v1/dispositions/cases/{case_id}/campaigns/release",
        headers=HEADERS,
    )
    assert released.status_code == 200, released.text
    campaign = db_session.scalar(
        select(DispositionCampaign).where(
            DispositionCampaign.disposition_case_id == UUID(case_id)
        )
    )
    assert campaign is not None
    assert campaign.recipient_count == 1
