import json
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import principal_for_user
from app.core.config import get_settings
from app.main import app
from app.models.foundation import (
    AuditEvent,
    Buyer,
    BuyerDiscoveryCandidate,
    BuyerDiscoveryRun,
    BuyerOffer,
    BuyerProofDocument,
    CompensationPlanRole,
    CompensationPlanVersion,
    DealDeduction,
    DealReconciliation,
    DispositionBuyerOutcome,
    DispositionBuyerPoolCandidate,
    DispositionBuyerPoolEntry,
    DispositionBuyerPoolRun,
    DispositionCampaign,
    DispositionCampaignRecipient,
    DispositionCase,
    DispositionCopilotRecommendation,
    DispositionCopilotReview,
    DispositionMatch,
    DispositionOperatingMode,
    DispositionPackageVersion,
    LandValuationAnalysis,
    Lead,
    Property,
    PropertyIntelligenceSnapshot,
    RevenueRecord,
    Role,
    RoleAssignment,
    RoleCredit,
    Transaction,
    User,
)
from app.schemas.dispositions import (
    BuyerSelection,
    DispositionCaseCreate,
    DispositionCoordinationOutput,
    DispositionCopilotAnalyzeRequest,
    ReconciliationDecision,
)
from app.services import disposition_copilot, dispositions
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
            "geographies": [{"jurisdiction": "city", "value": "Atlanta", "state": "GA"}],
            "strategies": ["wholesale_assignment"],
            "min_price_cents": 10000000,
            "max_price_cents": 30000000,
            "funding_methods": ["cash"],
            "property_types": ["single_family"],
        }
    else:
        criteria = {
            "asset_class": "land",
            "geographies": [{"jurisdiction": "city", "value": "Atlanta", "state": "GA"}],
            "strategies": ["wholesale_assignment"],
            "min_price_cents": 1000000,
            "max_price_cents": 30000000,
            "funding_methods": ["cash"],
            "min_acres": 1,
            "max_acres": 20,
            "intended_uses": ["residential"],
            "flood_zone_tolerance": "accepted",
            "wetlands_tolerance": "accepted",
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
            "expires_at": (expires_at or datetime.now(UTC) + timedelta(days=90)).isoformat(),
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
            "expires_at": (expires_at or datetime.now(UTC) + timedelta(days=90)).isoformat(),
            "notes": "Amount, institution, and expiration were reviewed by a human.",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "verified"
    assert response.json()["verified_by_user_id"] is not None
    assert response.json()["verified_at"] is not None
    return response.json()


def create_active_buyer(
    client: TestClient,
    *,
    name: str,
    email: str,
) -> str:
    created = client.post(
        "/api/v1/buyers",
        headers=HEADERS,
        json={
            "name": name,
            "email": email,
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
    assert created.status_code == 201, created.text
    buyer_id = created.json()["id"]
    activated = client.patch(
        f"/api/v1/buyers/{buyer_id}",
        headers=HEADERS,
        json={"status": "active"},
    )
    assert activated.status_code == 200, activated.text
    return buyer_id


def record_offer_room_offer(
    client: TestClient,
    case_id: str,
    buyer_id: str,
    *,
    amount_cents: int,
    proof_document_id: str | None,
    idempotency_key: str,
    earnest_money_cents: int = 500000,
) -> dict[str, Any]:
    recorded = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/offers",
        headers=HEADERS,
        json={
            "buyer_id": buyer_id,
            "amount_cents": amount_cents,
            "earnest_money_cents": earnest_money_cents,
            "deposit_due_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            "due_diligence_days": 7,
            "contingencies": [],
            "contingencies_confirmed": True,
            "proposed_closing_at": (datetime.now(UTC) + timedelta(days=21)).isoformat(),
            "funding_method": "cash",
            "funding_confidence_basis_points": 9000,
            "proof_document_id": proof_document_id,
            "change_reason": "Normalized buyer offer for disposition regression coverage.",
            "idempotency_key": idempotency_key,
        },
    )
    assert recorded.status_code == 201, recorded.text
    return next(item for item in recorded.json()["offers"] if item["buyer_id"] == buyer_id)


def select_offer_room_buyers(
    client: TestClient,
    case_id: str,
    primary: dict[str, Any],
    backups: list[dict[str, Any]],
    *,
    idempotency_key: str,
):
    selected_offers = [primary, *backups]
    return client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
        headers=HEADERS,
        json={
            "primary_offer_id": primary["id"],
            "backup_offer_ids": [item["id"] for item in backups],
            "expected_offer_lock_versions": {
                item["id"]: item["lock_version"] for item in selected_offers
            },
            "reason": "Verified funds, executable terms, and ranked backup coverage.",
            "idempotency_key": idempotency_key,
        },
    )


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
            "stage_key": "new",
        },
    )
    lead_id = lead_response.json()["id"]
    lead = db.get(Lead, UUID(lead_id))
    assert lead is not None
    # This fixture establishes pre-existing approved House authority directly. Public lead
    # creation intentionally cannot fabricate a governed offer/contract milestone.
    lead.stage_key = "offer_ready"
    db.commit()
    transaction_response = client.post(
        f"/api/v1/leads/{lead_id}/transactions",
        headers=HEADERS,
        json={"purchase_price_cents": 15000000},
    )
    transaction_id = transaction_response.json()["transactions"][0]["id"]
    transaction = db.get(Transaction, UUID(transaction_id))
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
    approved = approve_disposition_package(client, case_id)
    assert approved.status_code == 200, approved.text
    return case_id


def approve_disposition_package(client: TestClient, case_id: str):
    draft = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/versions",
        headers=HEADERS,
        json={"expected_latest_version": 0},
    )
    assert draft.status_code == 201, draft.text
    return client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/versions/{draft.json()['id']}/approval",
        headers=HEADERS,
        json={
            "expected_version": draft.json()["lock_version"],
            "attestation": True,
            "reason": "Reviewed saved evidence for test approval.",
        },
    )


def add_user_with_role(
    db: Session,
    *,
    email: str,
    display_name: str,
    role_key: str,
) -> User:
    owner = db.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert owner is not None
    role = db.scalar(
        select(Role).where(
            Role.organization_id == owner.organization_id,
            Role.key == role_key,
        )
    )
    assert role is not None
    user = User(
        organization_id=owner.organization_id,
        email=email,
        display_name=display_name,
        external_auth_id=None,
        is_active=True,
        calling_enabled=False,
    )
    db.add(user)
    db.flush()
    db.add(
        RoleAssignment(
            organization_id=owner.organization_id,
            user_id=user.id,
            role_id=role.id,
        )
    )
    db.commit()
    return user


def test_disposition_package_is_recursively_public_safe_and_manager_approved(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    _, transaction_id, _ = setup_case_foundation(db_session, client)
    created = client.post(
        "/api/v1/dispositions/cases",
        headers=HEADERS,
        json={
            "transaction_id": transaction_id,
            "strategy": "assignment",
            "asking_price_cents": 19283746,
            "minimum_acceptable_cents": 18273645,
            "desired_assignment_fee_cents": 4283746,
            "operating_mode_key": "human_led",
        },
    )
    assert created.status_code == 201, created.text
    case_id = created.json()["id"]
    draft = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/versions",
        headers=HEADERS,
        json={"expected_latest_version": 0},
    )
    assert draft.status_code == 201, draft.text
    assert draft.headers["cache-control"] == "private, no-store"
    assert draft.json()["readiness"]["status"] == "warnings"
    assert draft.json()["readiness"]["blocked_count"] == 0

    floor_secret = "PRIVATE-FLOOR-18273645"
    basis_secret = "PRIVATE-BASIS-15000000"
    fee_secret = "PRIVATE-FEE-4283746"
    seller_secret = "PRIVATE-SELLER-MOTIVATION"
    approval_secret = "PRIVATE-APPROVAL-REASON"
    version = db_session.get(DispositionPackageVersion, UUID(draft.json()["id"]))
    case = db_session.get(DispositionCase, UUID(case_id))
    assert version is not None and case is not None
    crafted = dict(version.public_snapshot)
    crafted["seller_identity"] = seller_secret
    crafted["property"] = {
        **crafted["property"],
        "seller_name": seller_secret,
        "mortgage_balance": basis_secret,
    }
    crafted["pricing"] = {
        **crafted["pricing"],
        "minimum_acceptable_cents": floor_secret,
        "purchase_price_cents": basis_secret,
        "desired_assignment_fee_cents": fee_secret,
    }
    crafted["valuation"] = {
        "arv_low_cents": 21000000,
        "recommended_offer_cents": basis_secret,
        "internal_notes": seller_secret,
    }
    crafted["repairs"] = {"total_cents": 1000000, "internal_floor": floor_secret}
    crafted["inspection"] = {"photo_count": 2, "seller_motivation": seller_secret}
    crafted["title"] = {"title_cleared": False, "mortgage_balance": basis_secret}
    crafted["evidence_summary"] = {
        "verified_fact_count": 1,
        "seller_private_fact": fee_secret,
    }
    version.public_snapshot = crafted
    case.package_snapshot = crafted
    db_session.commit()

    rep = add_user_with_role(
        db_session,
        email="package-rep@example.com",
        display_name="Package Rep",
        role_key="disposition_rep",
    )
    viewer = add_user_with_role(
        db_session,
        email="package-viewer@example.com",
        display_name="Package Viewer",
        role_key="read_only_partner",
    )
    viewer_headers = {"X-Dev-User-Email": viewer.email}
    rep_headers = {"X-Dev-User-Email": rep.email}

    viewer_case = client.get(f"/api/v1/dispositions/cases/{case_id}", headers=viewer_headers)
    assert viewer_case.status_code == 200, viewer_case.text
    assert viewer_case.json()["minimum_acceptable_cents"] is None
    assert viewer_case.json()["desired_assignment_fee_cents"] is None
    viewer_versions = client.get(
        f"/api/v1/dispositions/cases/{case_id}/package/versions",
        headers=viewer_headers,
    )
    assert viewer_versions.status_code == 200, viewer_versions.text
    assert viewer_versions.headers["cache-control"] == "private, no-store"
    assert viewer_versions.json()[0]["private_economics_snapshot"] is None
    public_response = viewer_case.text + viewer_versions.text
    for forbidden in (floor_secret, basis_secret, fee_secret, seller_secret):
        assert forbidden not in public_response
    nested_public = viewer_versions.json()[0]["public_snapshot"]
    forbidden_keys = {
        "seller_identity",
        "seller_name",
        "seller_motivation",
        "mortgage_balance",
        "minimum_acceptable_cents",
        "purchase_price_cents",
        "desired_assignment_fee_cents",
        "recommended_offer_cents",
        "internal_notes",
        "internal_floor",
        "seller_private_fact",
    }

    def assert_forbidden_keys_absent(value: object) -> None:
        if isinstance(value, dict):
            assert not forbidden_keys.intersection(value)
            for nested_value in value.values():
                assert_forbidden_keys_absent(nested_value)
        elif isinstance(value, list):
            for nested_value in value:
                assert_forbidden_keys_absent(nested_value)

    assert_forbidden_keys_absent(nested_public)
    assert all(
        secret not in json.dumps(nested_public)
        for secret in (floor_secret, basis_secret, fee_secret, seller_secret)
    )

    rep_workspace = client.get(f"/api/v1/dispositions/cases/{case_id}/package", headers=rep_headers)
    assert rep_workspace.status_code == 200, rep_workspace.text
    assert rep_workspace.json()["can_view_internal_economics"] is True
    assert rep_workspace.json()["can_approve"] is False
    assert rep_workspace.json()["private_economics"]["minimum_acceptable_cents"] == 18273645
    forbidden_approval = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/versions/{version.id}/approval",
        headers=rep_headers,
        json={
            "expected_version": 1,
            "attestation": True,
            "reason": "Representative attempted an unauthorized approval.",
        },
    )
    assert forbidden_approval.status_code == 403
    bodyless_alias = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/approve",
        headers=HEADERS,
    )
    assert bodyless_alias.status_code == 422

    approved = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/versions/{version.id}/approval",
        headers=HEADERS,
        json={
            "expected_version": 1,
            "attestation": True,
            "reason": approval_secret,
        },
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    restricted_history = client.get(
        f"/api/v1/dispositions/cases/{case_id}/package/versions",
        headers=viewer_headers,
    )
    assert restricted_history.json()[0]["approval_reason"] is None
    assert approval_secret not in restricted_history.text
    exact_pdf = client.get(
        f"/api/v1/dispositions/cases/{case_id}/package/versions/{version.id}/package.pdf",
        headers=viewer_headers,
    )
    assert exact_pdf.status_code == 200, exact_pdf.text
    assert exact_pdf.headers["cache-control"] == "private, no-store"
    for forbidden in (floor_secret, basis_secret, fee_secret, seller_secret):
        assert forbidden.encode() not in exact_pdf.content


def test_external_investor_packet_is_exact_immutable_and_uses_normal_approval(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    _, transaction_id, _ = setup_case_foundation(db_session, client)
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
    rep = add_user_with_role(
        db_session,
        email="external-packet-rep@example.com",
        display_name="External Packet Rep",
        role_key="disposition_rep",
    )
    rep_headers = {"X-Dev-User-Email": rep.email}
    exact_pdf = b"%PDF-1.7\nExternally prepared investor packet exact bytes\n%%EOF"

    uploaded = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/versions/external",
        headers={**rep_headers, "Content-Type": "application/pdf"},
        params={
            "expected_latest_version": 0,
            "file_name": "Alex Investor Packet.pdf",
            "content_type": "application/pdf",
            "source_note": "Packet prepared outside Stonegate and reviewed in Dispositions.",
        },
        content=exact_pdf,
    )
    assert uploaded.status_code == 201, uploaded.text
    payload = uploaded.json()
    assert payload["status"] == "draft"
    assert payload["artifact_source"] == "external_upload"
    assert payload["pdf_file_name"] == "Alex-Investor-Packet.pdf"
    assert payload["pdf_size"] == len(exact_pdf)
    assert payload["pdf_sha256"] == sha256(exact_pdf).hexdigest()
    assert payload["artifact_metadata"] == {
        "source": "external_upload",
        "original_file_name": "Alex-Investor-Packet.pdf",
        "content_type": "application/pdf",
        "size_bytes": len(exact_pdf),
        "sha256": sha256(exact_pdf).hexdigest(),
        "uploaded_at": payload["artifact_metadata"]["uploaded_at"],
        "uploaded_by_user_id": str(rep.id),
        "malware_scan_status": payload["artifact_metadata"]["malware_scan_status"],
        "source_note": "Packet prepared outside Stonegate and reviewed in Dispositions.",
    }
    version = db_session.get(DispositionPackageVersion, UUID(payload["id"]))
    assert version is not None
    assert bytes(version.pdf_data or b"") == exact_pdf
    assert version.pdf_sha256 == sha256(exact_pdf).hexdigest()
    upload_audit = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_id == version.id,
            AuditEvent.action == "disposition.package_version_external_upload",
        )
    )
    assert upload_audit is not None
    assert (upload_audit.new_value or {})["sha256"] == sha256(exact_pdf).hexdigest()

    read_only = add_user_with_role(
        db_session,
        email="external-packet-viewer@example.com",
        display_name="External Packet Viewer",
        role_key="read_only_partner",
    )
    read_only_headers = {"X-Dev-User-Email": read_only.email}
    unapproved_download = client.get(
        f"/api/v1/dispositions/cases/{case_id}/package/versions/{version.id}/package.pdf",
        headers=read_only_headers,
    )
    assert unapproved_download.status_code == 422, unapproved_download.text
    assert "unapproved external investor packet" in unapproved_download.json()["detail"]

    forbidden_approval = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/versions/{version.id}/approval",
        headers=rep_headers,
        json={
            "expected_version": payload["lock_version"],
            "attestation": True,
            "reason": "Rep should not be able to approve the external packet.",
        },
    )
    assert forbidden_approval.status_code == 403, forbidden_approval.text
    approved = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/versions/{version.id}/approval",
        headers=HEADERS,
        json={
            "expected_version": payload["lock_version"],
            "attestation": True,
            "reason": "Reviewed the exact external PDF and confirmed buyer-safe release content.",
        },
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["artifact_source"] == "external_upload"
    assert approved.json()["pdf_sha256"] == sha256(exact_pdf).hexdigest()
    db_session.refresh(version)
    assert bytes(version.pdf_data or b"") == exact_pdf

    current_download = client.get(
        f"/api/v1/dispositions/cases/{case_id}/package.pdf",
        headers=HEADERS,
    )
    assert current_download.status_code == 200, current_download.text
    assert current_download.content == exact_pdf
    approved_download = client.get(
        f"/api/v1/dispositions/cases/{case_id}/package/versions/{version.id}/package.pdf",
        headers=read_only_headers,
    )
    assert approved_download.status_code == 200, approved_download.text
    assert approved_download.content == exact_pdf
    issued = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/share-links",
        headers=HEADERS,
        json={"expires_in_hours": 72},
    )
    assert issued.status_code == 201, issued.text
    assert issued.json()["artifact_sha256"] == sha256(exact_pdf).hexdigest()
    package_ready_audit = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_id == version.id,
            AuditEvent.action.in_(
                {
                    "disposition.package_ready_sms_queued",
                    "disposition.package_ready_sms_not_queued",
                }
            ),
        )
    )
    assert package_ready_audit is not None


def test_land_case_accepts_exact_external_packet_but_not_generated_house_artifacts(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    lead_id, transaction_id, _ = setup_case_foundation(db_session, client)
    lead = db_session.get(Lead, UUID(lead_id))
    transaction = db_session.get(Transaction, UUID(transaction_id))
    assert lead is not None and transaction is not None
    property_record = db_session.get(Property, transaction.property_id)
    assert property_record is not None
    lead.asset_class = "land"
    property_record.property_type = "vacant_land"
    property_record.street_address = ""
    property_record.city = ""
    property_record.postal_code = ""
    property_record.parcel_id = "LAND-42-TEST"
    property_record.county = "Fulton"
    property_record.state = "GA"
    db_session.commit()

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
    assert created.json()["asset_class"] == "land"
    assert created.json()["property_address"] == "APN LAND-42-TEST, Fulton, GA"
    case_id = created.json()["id"]

    deal_overview = client.get("/api/v1/deals", headers=HEADERS)
    assert deal_overview.status_code == 200, deal_overview.text
    land_deal = next(
        item for item in deal_overview.json()["items"] if item["transaction_id"] == transaction_id
    )
    assert land_deal["asset_class"] == "land"
    assert land_deal["property_address"] == "APN LAND-42-TEST, Fulton, GA"

    workspace = client.get(
        f"/api/v1/dispositions/cases/{case_id}/package",
        headers=HEADERS,
    )
    assert workspace.status_code == 200, workspace.text
    assert workspace.json()["public_preview"]["asset_class"] == "land"
    identity = next(
        item
        for item in workspace.json()["current_readiness"]["checks"]
        if item["key"] == "property_identity"
    )
    assert identity["status"] == "ready"
    assert identity["detail"] == "APN LAND-42-TEST, Fulton, GA"
    generated = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/versions",
        headers=HEADERS,
        json={"expected_latest_version": 0},
    )
    assert generated.status_code == 409, generated.text
    assert "not available for Land leads" in generated.json()["detail"]

    exact_pdf = b"%PDF-1.7\nExact externally prepared Land packet\n%%EOF"
    uploaded = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/versions/external",
        headers={**HEADERS, "Content-Type": "application/pdf"},
        params={
            "expected_latest_version": 0,
            "file_name": "land-investor-packet.pdf",
            "content_type": "application/pdf",
        },
        content=exact_pdf,
    )
    assert uploaded.status_code == 201, uploaded.text
    approved = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/versions/{uploaded.json()['id']}/approval",
        headers=HEADERS,
        json={
            "expected_version": uploaded.json()["lock_version"],
            "attestation": True,
            "reason": "Reviewed the exact externally prepared Land packet.",
        },
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["artifact_source"] == "external_upload"
    downloaded = client.get(
        f"/api/v1/dispositions/cases/{case_id}/package.pdf",
        headers=HEADERS,
    )
    assert downloaded.status_code == 200, downloaded.text
    assert downloaded.content == exact_pdf

    land_pool = client.post(
        f"/api/v1/dispositions/cases/{case_id}/buyer-pool/runs",
        headers=HEADERS,
    )
    assert land_pool.status_code == 200, land_pool.text
    assert land_pool.json()["run"]["asset_class"] == "land"
    assert land_pool.json()["run"]["matcher_version"] == "stonegate_buyer_pool_v2"
    stored_pool_run = db_session.scalar(
        select(DispositionBuyerPoolRun).where(
            DispositionBuyerPoolRun.disposition_case_id == UUID(case_id)
        )
    )
    assert stored_pool_run is not None
    assert stored_pool_run.input_snapshot["land_subject"]["identity"]["parcel_id"] == (
        "LAND-42-TEST"
    )

    legacy_house_matching = client.post(
        f"/api/v1/dispositions/cases/{case_id}/matches",
        headers=HEADERS,
    )
    assert legacy_house_matching.status_code == 409, legacy_house_matching.text
    assert "not available for Land leads" in legacy_house_matching.json()["detail"]


def test_land_package_identity_evidence_requires_provider_provenance(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    lead_id, transaction_id, _ = setup_case_foundation(db_session, client)
    lead = db_session.get(Lead, UUID(lead_id))
    transaction = db_session.get(Transaction, UUID(transaction_id))
    assert lead is not None and transaction is not None
    property_record = db_session.get(Property, transaction.property_id)
    assert property_record is not None
    lead.asset_class = "land"
    property_record.property_type = "vacant_land"
    property_record.street_address = ""
    property_record.city = ""
    property_record.postal_code = ""
    property_record.parcel_id = "LAND-EVIDENCE-42"
    property_record.county = "Fulton"
    property_record.state = "GA"
    db_session.commit()

    created = client.post(
        "/api/v1/dispositions/cases",
        headers=HEADERS,
        json={
            "transaction_id": transaction_id,
            "strategy": "assignment",
            "asking_price_cents": 19_000_000,
            "minimum_acceptable_cents": 18_000_000,
            "operating_mode_key": "human_led",
        },
    )
    assert created.status_code == 201, created.text
    case_id = created.json()["id"]

    workspace = client.get(
        f"/api/v1/dispositions/cases/{case_id}/package",
        headers=HEADERS,
    )
    assert workspace.status_code == 200, workspace.text
    identity_evidence = next(
        item for item in workspace.json()["evidence_manifest"] if item["key"] == "property_identity"
    )
    assert identity_evidence["classification"] == "seller_statement"

    property_record.address_validation_status = "provider_confirmed"
    property_record.address_validation_provider = "realestateapi"
    property_record.address_validated_at = datetime.now(UTC)
    property_record.address_validation_metadata = {
        "lookup_mode": "parcel",
        "requested_parcel_key": "GA|FULTON|LANDEVIDENCE42",
        "returned_parcel_key": "GA|FULTON|LANDEVIDENCE42",
    }
    db_session.commit()
    provider_workspace = client.get(
        f"/api/v1/dispositions/cases/{case_id}/package",
        headers=HEADERS,
    )
    assert provider_workspace.status_code == 200, provider_workspace.text
    provider_identity_evidence = next(
        item
        for item in provider_workspace.json()["evidence_manifest"]
        if item["key"] == "property_identity"
    )
    assert provider_identity_evidence["classification"] == "provider_signal"
    assert provider_identity_evidence["provenance"]["provider"] == "realestateapi"


def test_land_package_valuation_requires_review_and_guidance_clearance(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    lead_id, transaction_id, _ = setup_case_foundation(db_session, client)
    lead = db_session.get(Lead, UUID(lead_id))
    transaction = db_session.get(Transaction, UUID(transaction_id))
    assert lead is not None and transaction is not None
    property_record = db_session.get(Property, transaction.property_id)
    assert property_record is not None
    lead.asset_class = "land"
    property_record.property_type = "vacant_land"
    property_record.parcel_id = "LAND-VALUATION-42"
    property_record.county = "Fulton"
    now = datetime.now(UTC)
    snapshot = PropertyIntelligenceSnapshot(
        organization_id=lead.organization_id,
        property_id=property_record.id,
        source_lead_id=lead.id,
        source_market_analysis_id=None,
        version_number=1,
        research_profile="land_v1",
        status="ready",
        is_current=True,
        address_signature=f"land-v1:{property_record.id}",
        completeness_score=90,
        confidence_score=80,
        facts={},
        valuation={},
        comparables=[],
        market_context={},
        sources=[{"provider": "realestateapi", "operation": "property_detail"}],
        conflicts=[],
        media={},
        snapshot_metadata={"lookup_mode": "parcel"},
        captured_at=now,
        expires_at=now + timedelta(days=30),
    )
    db_session.add(snapshot)
    db_session.flush()
    valuation = LandValuationAnalysis(
        organization_id=lead.organization_id,
        lead_id=lead.id,
        property_id=property_record.id,
        property_snapshot_id=snapshot.id,
        source_analysis_id=None,
        policy_version_id=None,
        created_by_user_id=None,
        version_number=1,
        valuation_profile="land_v1",
        methodology_version="land_v1",
        analysis_fingerprint="b" * 64,
        request_idempotency_key=None,
        status="needs_review",
        guidance_status="withheld",
        valuation_basis="per_acre",
        access_evidence_status="unverified",
        subject_acres_ten_thousandths=100_000,
        subject_lot_count=None,
        supported_value_low_cents=10_000_000,
        supported_value_cents=12_000_000,
        supported_value_high_cents=14_000_000,
        quick_sale_low_cents=None,
        quick_sale_high_cents=None,
        opening_offer_cents=None,
        seller_contract_ceiling_cents=None,
        assignment_fee_cents=0,
        closing_title_reserve_cents=0,
        curative_reserve_cents=0,
        uncertainty_reserve_cents=0,
        confidence_score=70,
        selected_comp_count=3,
        rejected_comp_count=0,
        selected_comps=[],
        rejected_comps=[],
        subject_snapshot={},
        search_snapshot={},
        assumptions={},
        review_reasons=[],
        guidance_blockers=[],
        policy_snapshot={},
        analysis_metadata={},
    )
    db_session.add(valuation)
    db_session.commit()

    created = client.post(
        "/api/v1/dispositions/cases",
        headers=HEADERS,
        json={
            "transaction_id": transaction_id,
            "strategy": "assignment",
            "asking_price_cents": 19_000_000,
            "minimum_acceptable_cents": 18_000_000,
            "operating_mode_key": "human_led",
        },
    )
    assert created.status_code == 201, created.text
    case_id = created.json()["id"]

    scenarios = (
        ("needs_review", "available", [], [], "analysis status is needs_review"),
        ("ready", "withheld", [], [], "offer guidance is withheld"),
        (
            "ready",
            "available",
            ["Extended-tier comparable evidence requires human review."],
            [],
            "human review reasons remain unresolved",
        ),
        (
            "ready",
            "available",
            [],
            ["Legal access has not been human-verified with evidence."],
            "offer-guidance blockers remain unresolved",
        ),
    )
    for status, guidance_status, review_reasons, guidance_blockers, detail in scenarios:
        valuation.status = status
        valuation.guidance_status = guidance_status
        valuation.review_reasons = review_reasons
        valuation.guidance_blockers = guidance_blockers
        db_session.commit()
        workspace = client.get(
            f"/api/v1/dispositions/cases/{case_id}/package",
            headers=HEADERS,
        )
        assert workspace.status_code == 200, workspace.text
        assert workspace.json()["public_preview"]["valuation"]["supported_value_cents"] == (
            12_000_000
        )
        valuation_check = next(
            item
            for item in workspace.json()["current_readiness"]["checks"]
            if item["key"] == "valuation"
        )
        assert valuation_check["status"] == "warning"
        assert detail in valuation_check["detail"]
        valuation_evidence = next(
            item for item in workspace.json()["evidence_manifest"] if item["key"] == "valuation"
        )
        assert valuation_evidence["value"]["review_reasons"] == review_reasons
        assert valuation_evidence["value"]["guidance_blockers"] == guidance_blockers

    valuation.status = "ready"
    valuation.guidance_status = "available"
    valuation.review_reasons = []
    valuation.guidance_blockers = []
    db_session.commit()
    ready_workspace = client.get(
        f"/api/v1/dispositions/cases/{case_id}/package",
        headers=HEADERS,
    )
    assert ready_workspace.status_code == 200, ready_workspace.text
    ready_valuation_check = next(
        item
        for item in ready_workspace.json()["current_readiness"]["checks"]
        if item["key"] == "valuation"
    )
    assert ready_valuation_check["status"] == "ready"


def test_external_investor_packet_rejects_non_pdf_and_oversized_content(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = TestClient(app)
    _, transaction_id, _ = setup_case_foundation(db_session, client)
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
    case_id = created.json()["id"]
    endpoint = f"/api/v1/dispositions/cases/{case_id}/package/versions/external"
    invalid_type = client.post(
        endpoint,
        headers={**HEADERS, "Content-Type": "text/plain"},
        params={
            "expected_latest_version": 0,
            "file_name": "packet.pdf",
            "content_type": "application/pdf",
        },
        content=b"%PDF-1.7\nnot accepted under a false request type",
    )
    assert invalid_type.status_code == 422
    invalid_magic = client.post(
        endpoint,
        headers={**HEADERS, "Content-Type": "application/pdf"},
        params={
            "expected_latest_version": 0,
            "file_name": "packet.pdf",
            "content_type": "application/pdf",
        },
        content=b"this is not a PDF",
    )
    assert invalid_magic.status_code == 422
    assert "valid PDF header" in invalid_magic.json()["detail"]

    monkeypatch.setattr("app.services.disposition_packages.MAX_EXTERNAL_PACKAGE_PDF_SIZE", 12)
    oversized = client.post(
        endpoint,
        headers={**HEADERS, "Content-Type": "application/pdf"},
        params={
            "expected_latest_version": 0,
            "file_name": "packet.pdf",
            "content_type": "application/pdf",
        },
        content=b"%PDF-1.7\n1234",
    )
    assert oversized.status_code == 422
    assert "cannot exceed 15 MB" in oversized.json()["detail"]


def test_external_investor_packet_with_scan_error_cannot_be_approved(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = TestClient(app)
    _, transaction_id, _ = setup_case_foundation(db_session, client)
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
    case_id = created.json()["id"]
    monkeypatch.setattr("app.services.disposition_packages.scan_document", lambda _: "scan_error")
    uploaded = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/versions/external",
        headers={**HEADERS, "Content-Type": "application/pdf"},
        params={
            "expected_latest_version": 0,
            "file_name": "unscanned-packet.pdf",
            "content_type": "application/pdf",
        },
        content=b"%PDF-1.7\nPDF whose scanner was temporarily unavailable\n%%EOF",
    )
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["artifact_metadata"]["malware_scan_status"] == "scan_error"
    blocked_preview = client.get(
        f"/api/v1/dispositions/cases/{case_id}/package/versions/"
        f"{uploaded.json()['id']}/package.pdf",
        headers=HEADERS,
    )
    assert blocked_preview.status_code == 422, blocked_preview.text
    assert "cannot be opened" in blocked_preview.json()["detail"]
    blocked = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/versions/{uploaded.json()['id']}/approval",
        headers=HEADERS,
        json={
            "expected_version": uploaded.json()["lock_version"],
            "attestation": True,
            "reason": "Attempting approval while the malware scan is unresolved.",
        },
    )
    assert blocked.status_code == 422, blocked.text
    assert "malware scan state" in blocked.json()["detail"]


def test_private_economics_permission_guards_writes_and_redacts_reads(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    _, transaction_id, buyer_id = setup_case_foundation(db_session, client)
    transaction = db_session.get(Transaction, UUID(transaction_id))
    assert transaction is not None
    transaction.assignment_fee_cents = 4000000
    db_session.commit()

    assistant = add_user_with_role(
        db_session,
        email="economics-restricted@example.com",
        display_name="Economics Restricted",
        role_key="operations_assistant",
    )
    assistant_headers = {"X-Dev-User-Email": assistant.email}
    assistant_principal = principal_for_user(db_session, assistant)

    restricted_overview = client.get("/api/v1/dispositions", headers=assistant_headers)
    assert restricted_overview.status_code == 200, restricted_overview.text
    restricted_payload = restricted_overview.json()
    assert restricted_payload["can_view_private_economics"] is False
    restricted_eligible = next(
        item for item in restricted_payload["eligible_transactions"] if item["id"] == transaction_id
    )
    assert restricted_eligible["purchase_price_cents"] is None
    assert restricted_eligible["assignment_fee_cents"] is None

    owner_overview = client.get("/api/v1/dispositions", headers=HEADERS)
    assert owner_overview.status_code == 200, owner_overview.text
    assert owner_overview.json()["can_view_private_economics"] is True
    owner_eligible = next(
        item
        for item in owner_overview.json()["eligible_transactions"]
        if item["id"] == transaction_id
    )
    assert owner_eligible["purchase_price_cents"] == 15000000
    assert owner_eligible["assignment_fee_cents"] == 4000000

    create_payload = {
        "transaction_id": transaction_id,
        "strategy": "assignment",
        "asking_price_cents": 19000000,
        "minimum_acceptable_cents": 18000000,
        "desired_assignment_fee_cents": 4000000,
        "operating_mode_key": "human_led",
    }
    unauthorized_create = client.post(
        "/api/v1/dispositions/cases",
        headers=assistant_headers,
        json=create_payload,
    )
    assert unauthorized_create.status_code == 403, unauthorized_create.text
    assert "dispositions:view_private_economics" in unauthorized_create.json()["detail"]
    with pytest.raises(PermissionError, match="dispositions:view_private_economics"):
        dispositions.create_case(
            db_session,
            assistant_principal,
            DispositionCaseCreate.model_validate(create_payload),
        )

    created = client.post(
        "/api/v1/dispositions/cases",
        headers=HEADERS,
        json=create_payload,
    )
    assert created.status_code == 201, created.text
    case_id = created.json()["id"]
    case = db_session.get(DispositionCase, UUID(case_id))
    owner = db_session.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert case is not None and owner is not None
    db_session.add(
        DealReconciliation(
            organization_id=case.organization_id,
            transaction_id=case.transaction_id,
            disposition_case_id=case.id,
            compensation_plan_version_id=case.compensation_plan_version_id,
            disposition_operating_mode_id=case.disposition_operating_mode_id,
            created_by_user_id=owner.id,
            approved_by_user_id=None,
            status="draft",
            gross_revenue_cents=4000000,
            acquisition_reserve_cents=250000,
            deal_deductions_cents=100000,
            adjusted_deal_margin_cents=3650000,
            total_compensation_cents=1000000,
            company_profit_cents=2650000,
            company_margin_basis_points=7260,
            target_margin_basis_points=3000,
            snapshot={"private": "economics"},
            approved_at=None,
            notes="Private reconciliation note.",
        )
    )
    db_session.commit()

    restricted_case = client.get(
        f"/api/v1/dispositions/cases/{case_id}",
        headers=assistant_headers,
    )
    assert restricted_case.status_code == 200, restricted_case.text
    assert restricted_case.json()["minimum_acceptable_cents"] is None
    assert restricted_case.json()["desired_assignment_fee_cents"] is None
    assert restricted_case.json()["reconciliation"] is None
    restricted_case_overview = client.get("/api/v1/dispositions", headers=assistant_headers)
    assert restricted_case_overview.status_code == 200, restricted_case_overview.text
    overview_case = next(
        item for item in restricted_case_overview.json()["cases"] if item["id"] == case_id
    )
    assert overview_case["minimum_acceptable_cents"] is None
    assert overview_case["desired_assignment_fee_cents"] is None
    assert overview_case["reconciliation"] is None

    denied_override = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/versions",
        headers=assistant_headers,
        json={"expected_latest_version": 0, "minimum_acceptable_cents": 17500000},
    )
    assert denied_override.status_code == 403, denied_override.text
    assert "dispositions:view_private_economics" in denied_override.json()["detail"]
    allowed_default = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/versions",
        headers=assistant_headers,
        json={"expected_latest_version": 0},
    )
    assert allowed_default.status_code == 201, allowed_default.text
    assert allowed_default.json()["private_economics_snapshot"] is None

    denied_actions = (
        client.post(
            f"/api/v1/dispositions/cases/{case_id}/buyer-selection",
            headers=assistant_headers,
            json={
                "primary_offer_id": "00000000-0000-0000-0000-000000000001",
                "reason": "Restricted user must not probe the internal floor.",
            },
        ),
        client.post(
            f"/api/v1/dispositions/cases/{case_id}/reconciliation",
            headers=assistant_headers,
        ),
        client.post(
            f"/api/v1/dispositions/cases/{case_id}/reconciliation/decision",
            headers=assistant_headers,
            json={"decision": "approved", "notes": "Restricted decision attempt."},
        ),
        client.get(
            f"/api/v1/dispositions/cases/{case_id}/accounting.csv",
            headers=assistant_headers,
        ),
        client.post(
            f"/api/v1/dispositions/cases/{case_id}/copilot/analyze",
            headers=assistant_headers,
            json={"idempotency_key": "restricted-floor-oracle"},
        ),
    )
    for response in denied_actions:
        assert response.status_code == 403, response.text
        assert "dispositions:view_private_economics" in response.json()["detail"]

    with pytest.raises(PermissionError, match="dispositions:view_private_economics"):
        dispositions.select_buyer(
            db_session,
            assistant_principal,
            UUID(case_id),
            BuyerSelection(
                primary_offer_id=UUID("00000000-0000-0000-0000-000000000001"),
                reason="Restricted service call.",
            ),
        )
    with pytest.raises(PermissionError, match="dispositions:view_private_economics"):
        dispositions.build_reconciliation(db_session, assistant_principal, UUID(case_id))
    with pytest.raises(PermissionError, match="dispositions:view_private_economics"):
        dispositions.decide_reconciliation(
            db_session,
            assistant_principal,
            UUID(case_id),
            ReconciliationDecision(
                decision="approved",
                notes="Restricted service decision.",
            ),
        )
    with pytest.raises(PermissionError, match="dispositions:view_private_economics"):
        dispositions.accounting_csv(db_session, assistant_principal, UUID(case_id))
    with pytest.raises(PermissionError, match="dispositions:view_private_economics"):
        disposition_copilot.analyze_disposition(
            db_session,
            assistant_principal,
            UUID(case_id),
            DispositionCopilotAnalyzeRequest(idempotency_key="restricted-service-call"),
        )

    retired_offer_entry = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offers",
        headers=HEADERS,
        json={
            "buyer_id": buyer_id,
            "amount_cents": 17000000,
            "financing_type": "cash",
        },
    )
    assert retired_offer_entry.status_code == 410, retired_offer_entry.text
    assert "Offer Room" in retired_offer_entry.json()["detail"]
    record_offer_room_offer(
        client,
        case_id,
        buyer_id,
        amount_cents=17000000,
        proof_document_id=None,
        idempotency_key="private-floor-offer-room",
    )
    db_session.add(
        DispositionCopilotRecommendation(
            organization_id=case.organization_id,
            disposition_case_id=case.id,
            transaction_id=case.transaction_id,
            lead_id=case.lead_id,
            generated_for_user_id=owner.id,
            ai_run_log_id=None,
            idempotency_key="private-floor-recommendation",
            status="draft",
            output_payload={
                "status_summary": "Review the buyer offer against the internal floor.",
                "package_gaps": [],
                "package_highlights": [],
                "recommended_buyers": [],
                "offer_comparison": [],
                "buyer_outreach_subject": "Buyer offer review",
                "buyer_outreach_body": "Review the current buyer offer.",
                "recommended_internal_actions": ["Review the internal floor."],
                "relationship_update_proposals": [],
                "risk_alerts": ["The offer is below the internal floor."],
                "uncertainties": [],
                "evidence": [],
                "confidence": 80,
            },
            evidence_snapshot={"private_economics": {"minimum": 18000000}},
            confidence_score=80,
            generated_at=datetime.now(UTC),
            reviewed_at=None,
        )
    )
    db_session.commit()
    owner_copilot = client.get(
        f"/api/v1/dispositions/cases/{case_id}/copilot",
        headers=HEADERS,
    )
    assert owner_copilot.status_code == 200, owner_copilot.text
    assert owner_copilot.json()["recommendations"]
    assert any(
        "internal floor" in risk.lower()
        for recommendation in owner_copilot.json()["recommendations"]
        for risk in recommendation["output_payload"]["risk_alerts"]
    )
    restricted_copilot = client.get(
        f"/api/v1/dispositions/cases/{case_id}/copilot",
        headers=assistant_headers,
    )
    assert restricted_copilot.status_code == 200, restricted_copilot.text
    assert restricted_copilot.json()["recommendations"] == []
    assert all(
        "internal floor" not in risk["reason"].lower()
        for risk in restricted_copilot.json()["risk_alerts"]
    )


def test_disposition_package_staleness_is_precise_and_history_is_immutable(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    _, transaction_id, _ = setup_case_foundation(db_session, client)
    case_id = create_approved_disposition_case(client, transaction_id)
    workspace = client.get(f"/api/v1/dispositions/cases/{case_id}/package", headers=HEADERS)
    assert workspace.status_code == 200, workspace.text
    approved = workspace.json()["approved_version"]
    assert approved is not None
    version_id = approved["id"]
    original_fingerprint = workspace.json()["current_source_fingerprint"]
    original_pdf = client.get(
        f"/api/v1/dispositions/cases/{case_id}/package/versions/{version_id}/package.pdf",
        headers=HEADERS,
    )
    assert original_pdf.status_code == 200

    transaction = db_session.get(Transaction, UUID(transaction_id))
    assert transaction is not None
    transaction.notes = "An unrelated internal coordination note changed."
    db_session.commit()
    unchanged = client.get(f"/api/v1/dispositions/cases/{case_id}/package", headers=HEADERS)
    assert unchanged.status_code == 200, unchanged.text
    assert unchanged.json()["current_source_fingerprint"] == original_fingerprint
    assert unchanged.json()["approved_package_is_current"] is True
    assert unchanged.json()["current_readiness"]["status"] != "stale"

    transaction.purchase_price_cents += 1
    db_session.commit()
    stale = client.get(f"/api/v1/dispositions/cases/{case_id}/package", headers=HEADERS)
    assert stale.status_code == 200, stale.text
    assert stale.json()["approved_package_is_current"] is False
    assert stale.json()["current_readiness"]["status"] == "stale"
    assert any(
        check["key"] == "approved_package_freshness"
        for check in stale.json()["current_readiness"]["checks"]
    )
    blocked_match = client.post(f"/api/v1/dispositions/cases/{case_id}/matches", headers=HEADERS)
    assert blocked_match.status_code == 422
    assert "stale" in blocked_match.json()["detail"].lower()
    stale_alias = client.get(f"/api/v1/dispositions/cases/{case_id}/package.pdf", headers=HEADERS)
    assert stale_alias.status_code == 422
    exact_historical = client.get(
        f"/api/v1/dispositions/cases/{case_id}/package/versions/{version_id}/package.pdf",
        headers=HEADERS,
    )
    assert exact_historical.status_code == 200
    assert exact_historical.content == original_pdf.content


def test_disposition_package_version_lock_readiness_and_tenant_scope(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    _, transaction_id, _ = setup_case_foundation(db_session, client)
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
    property_record = db_session.scalar(
        select(Property)
        .join(DispositionCase, DispositionCase.property_id == Property.id)
        .where(DispositionCase.id == UUID(case_id))
    )
    assert property_record is not None
    property_record.street_address = ""
    db_session.commit()
    draft = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/versions",
        headers=HEADERS,
        json={"expected_latest_version": 0},
    )
    assert draft.status_code == 201, draft.text
    assert draft.json()["readiness"]["status"] == "blocked"
    assert draft.json()["readiness"]["blocked_count"] >= 1
    assert "property address" in " ".join(draft.json()["readiness"]["blockers"]).lower()
    stale_create = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/versions",
        headers=HEADERS,
        json={"expected_latest_version": 0},
    )
    assert stale_create.status_code == 422
    stale_approval = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/versions/{draft.json()['id']}/approval",
        headers=HEADERS,
        json={
            "expected_version": 99,
            "attestation": True,
            "reason": "Stale approval state must be rejected.",
        },
    )
    assert stale_approval.status_code == 422

    other = bootstrap_foundation(
        db_session,
        organization_name="Other Disposition Organization",
        admin_email="other-disposition-owner@example.com",
        admin_name="Other Disposition Owner",
    )
    other_headers = {"X-Dev-User-Email": other.admin_user.email}
    assert (
        client.get(
            f"/api/v1/dispositions/cases/{case_id}/package", headers=other_headers
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/dispositions/cases/{case_id}/package/versions", headers=other_headers
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/dispositions/cases/{case_id}/package/versions/{draft.json()['id']}/approval",
            headers=other_headers,
            json={
                "expected_version": 1,
                "attestation": True,
                "reason": "Cross-tenant approval must not reveal package existence.",
            },
        ).status_code
        == 404
    )


def test_assignment_package_floor_cannot_undercut_contract_basis(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    _, transaction_id, _ = setup_case_foundation(db_session, client)
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

    rejected = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/versions",
        headers=HEADERS,
        json={
            "expected_latest_version": 0,
            "minimum_acceptable_cents": 14999999,
        },
    )
    assert rejected.status_code == 422, rejected.text
    assert "contract purchase price" in rejected.json()["detail"].lower()
    case = db_session.get(DispositionCase, UUID(case_id))
    assert case is not None
    db_session.refresh(case)
    assert case.minimum_acceptable_cents == 18000000
    assert (
        db_session.scalar(
            select(func.count(DispositionPackageVersion.id)).where(
                DispositionPackageVersion.disposition_case_id == UUID(case_id)
            )
        )
        == 0
    )

    # Readiness is also fail-closed if legacy or administrative data is already unsafe.
    case.minimum_acceptable_cents = 14999999
    db_session.commit()
    workspace = client.get(f"/api/v1/dispositions/cases/{case_id}/package", headers=HEADERS)
    assert workspace.status_code == 200, workspace.text
    assert workspace.json()["current_readiness"]["status"] == "blocked"
    assert (
        "contract purchase price"
        in " ".join(workspace.json()["current_readiness"]["blockers"]).lower()
    )
    economics = next(
        check
        for check in workspace.json()["current_readiness"]["checks"]
        if check["key"] == "economics"
    )
    assert economics["status"] == "blocked"
    assert economics["remediation"] == {
        "label": "Review package economics",
        "href": (f"/os/deals?deal={case.deal_id}&tab=disposition&dispositionTab=package"),
    }


def test_only_latest_package_version_can_be_current_or_approved(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    _, transaction_id, _ = setup_case_foundation(db_session, client)
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

    first = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/versions",
        headers=HEADERS,
        json={"expected_latest_version": 0},
    )
    assert first.status_code == 201, first.text
    second = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/versions",
        headers=HEADERS,
        json={"expected_latest_version": 1},
    )
    assert second.status_code == 201, second.text
    versions = client.get(
        f"/api/v1/dispositions/cases/{case_id}/package/versions",
        headers=HEADERS,
    )
    assert versions.status_code == 200, versions.text
    assert [(item["version_number"], item["status"]) for item in versions.json()] == [
        (2, "draft"),
        (1, "superseded"),
    ]
    assert versions.json()[0]["is_current"] is True
    assert versions.json()[1]["is_current"] is False

    old_approval = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/versions/{first.json()['id']}/approval",
        headers=HEADERS,
        json={
            "expected_version": 2,
            "attestation": True,
            "reason": "An older package must never become the release package.",
        },
    )
    assert old_approval.status_code == 422, old_approval.text
    assert "latest package version" in old_approval.json()["detail"].lower()

    approved_second = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/versions/{second.json()['id']}/approval",
        headers=HEADERS,
        json={
            "expected_version": 1,
            "attestation": True,
            "reason": "The latest evidence-backed version was reviewed.",
        },
    )
    assert approved_second.status_code == 200, approved_second.text
    current = client.get(f"/api/v1/dispositions/cases/{case_id}/package", headers=HEADERS)
    assert current.status_code == 200, current.text
    assert current.json()["approved_package_is_current"] is True

    # Rebuilding intentionally invalidates the prior approval, even when the source
    # fingerprint is identical, because the newer draft is now the operative version.
    third = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/versions",
        headers=HEADERS,
        json={"expected_latest_version": 2},
    )
    assert third.status_code == 201, third.text
    rebuilt = client.get(f"/api/v1/dispositions/cases/{case_id}/package", headers=HEADERS)
    assert rebuilt.status_code == 200, rebuilt.text
    assert rebuilt.json()["latest_version"]["id"] == third.json()["id"]
    assert rebuilt.json()["latest_version"]["is_current"] is True
    assert rebuilt.json()["approved_version"]["id"] == second.json()["id"]
    assert rebuilt.json()["approved_version"]["is_current"] is False
    assert rebuilt.json()["approved_package_is_current"] is False
    assert rebuilt.json()["current_readiness"]["status"] == "stale"
    freshness = next(
        check
        for check in rebuilt.json()["current_readiness"]["checks"]
        if check["key"] == "approved_package_freshness"
    )
    case = db_session.get(DispositionCase, UUID(case_id))
    assert case is not None
    assert freshness["remediation"] == {
        "label": "Build a current package",
        "href": (f"/os/deals?deal={case.deal_id}&tab=disposition&dispositionTab=package"),
    }
    assert (
        client.get(f"/api/v1/dispositions/cases/{case_id}/package.pdf", headers=HEADERS)
        .json()["detail"]
        .startswith("An approved immutable disposition package is required")
    )

    approved_third = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/versions/{third.json()['id']}/approval",
        headers=HEADERS,
        json={
            "expected_version": 1,
            "attestation": True,
            "reason": "The rebuilt latest version was reviewed.",
        },
    )
    assert approved_third.status_code == 200, approved_third.text
    versions = client.get(
        f"/api/v1/dispositions/cases/{case_id}/package/versions",
        headers=HEADERS,
    ).json()
    assert [(item["version_number"], item["status"]) for item in versions] == [
        (3, "approved"),
        (2, "superseded"),
        (1, "superseded"),
    ]

    fourth = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/versions",
        headers=HEADERS,
        json={"expected_latest_version": 3},
    )
    assert fourth.status_code == 201, fourth.text
    outdated = db_session.get(DispositionPackageVersion, UUID(fourth.json()["id"]))
    assert outdated is not None
    outdated.renderer_version = "retired_renderer"
    db_session.commit()
    outdated_approval = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/versions/{fourth.json()['id']}/approval",
        headers=HEADERS,
        json={
            "expected_version": 1,
            "attestation": True,
            "reason": "An outdated renderer must fail closed.",
        },
    )
    assert outdated_approval.status_code == 422, outdated_approval.text
    assert "policy or renderer changed" in outdated_approval.json()["detail"].lower()
    outdated_workspace = client.get(
        f"/api/v1/dispositions/cases/{case_id}/package",
        headers=HEADERS,
    )
    assert outdated_workspace.status_code == 200, outdated_workspace.text
    assert outdated_workspace.json()["latest_version"]["is_current"] is False
    assert outdated_workspace.json()["approved_package_is_current"] is False


def test_legacy_marketed_case_can_rebuild_and_reenter_buyer_matching(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    _, transaction_id, _ = setup_case_foundation(db_session, client)
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
    case = db_session.get(DispositionCase, UUID(case_id))
    assert case is not None
    case.status = "marketed"
    case.package_status = "approved"
    db_session.commit()

    draft = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/versions",
        headers=HEADERS,
        json={"expected_latest_version": 0},
    )
    assert draft.status_code == 201, draft.text
    db_session.refresh(case)
    assert case.status == "buyer_matching"
    assert case.package_status == "draft"

    # Approval independently repairs the legacy marketed state as well, which
    # covers cases imported or administratively restored between both actions.
    case.status = "marketed"
    db_session.commit()
    approved = client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/versions/{draft.json()['id']}/approval",
        headers=HEADERS,
        json={
            "expected_version": draft.json()["lock_version"],
            "attestation": True,
            "reason": "Legacy marketed case was reviewed under the current package policy.",
        },
    )
    assert approved.status_code == 200, approved.text
    db_session.refresh(case)
    assert case.status == "buyer_matching"
    assert case.package_status == "approved"

    matching = client.post(
        f"/api/v1/dispositions/cases/{case_id}/matches",
        headers=HEADERS,
    )
    assert matching.status_code == 200, matching.text
    assert matching.json()["status"] == "buyer_matching"


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

    assert approve_disposition_package(client, case_id).status_code == 200
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
    legacy_only = client.post(f"/api/v1/dispositions/cases/{case_id}/matches", headers=HEADERS)
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
    land_only = client.post(f"/api/v1/dispositions/cases/{case_id}/matches", headers=HEADERS)
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
    release = client.post(
        f"/api/v1/dispositions/cases/{case_id}/campaigns/release", headers=HEADERS
    )
    assert release.status_code == 200, release.text
    assert release.json()["status"] == "buyer_matching"
    stored_case = db_session.get(DispositionCase, UUID(case_id))
    assert stored_case is not None
    assert stored_case.status == "buyer_matching"
    prepared_campaign = db_session.scalar(
        select(DispositionCampaign).where(DispositionCampaign.disposition_case_id == UUID(case_id))
    )
    assert prepared_campaign is not None
    assert prepared_campaign.status == "prepared_not_sent"
    assert prepared_campaign.released_at is None
    assert prepared_campaign.package_version_id is not None
    prepared_recipient = db_session.scalar(
        select(DispositionCampaignRecipient).where(
            DispositionCampaignRecipient.disposition_campaign_id == prepared_campaign.id
        )
    )
    assert prepared_recipient is not None
    assert prepared_recipient.status == "prepared_not_sent"
    assert prepared_recipient.package_version_id == prepared_campaign.package_version_id
    prepared_version = db_session.get(
        DispositionPackageVersion, prepared_campaign.package_version_id
    )
    assert prepared_version is not None
    assert prepared_recipient.artifact_sha256 == prepared_version.pdf_sha256
    assert prepared_recipient.captured_destination == {"email": "reliable-atlanta@example.com"}
    assert set(prepared_recipient.captured_identity) == {"buyer_name", "company_name"}
    prepared_record_text = json.dumps(
        {
            "identity": prepared_recipient.captured_identity,
            "destination": prepared_recipient.captured_destination,
        }
    )
    for private_value in ("Disposition Seller", "15000000", "18000000", "4000000"):
        assert private_value not in prepared_record_text

    campaign_id = prepared_campaign.id
    recipient_id = prepared_recipient.id
    repeated_release = client.post(
        f"/api/v1/dispositions/cases/{case_id}/campaigns/release",
        headers=HEADERS,
    )
    assert repeated_release.status_code == 200, repeated_release.text
    assert (
        db_session.scalar(
            select(func.count(DispositionCampaign.id)).where(
                DispositionCampaign.disposition_case_id == UUID(case_id)
            )
        )
        == 1
    )
    assert (
        db_session.scalar(
            select(func.count(DispositionCampaignRecipient.id)).where(
                DispositionCampaignRecipient.disposition_case_id == UUID(case_id)
            )
        )
        == 1
    )
    assert db_session.get(DispositionCampaign, campaign_id) is not None
    assert db_session.get(DispositionCampaignRecipient, recipient_id) is not None

    backup_buyer_id = create_active_buyer(
        client,
        name="Reconciliation Backup Buyer",
        email="reconciliation-backup@example.com",
    )
    put_verified_buy_box(client, backup_buyer_id)
    backup_proof = upload_received_proof(client, backup_buyer_id)
    verify_proof(client, backup_proof["id"])
    refreshed_matches = client.post(
        f"/api/v1/dispositions/cases/{case_id}/matches",
        headers=HEADERS,
    )
    assert refreshed_matches.status_code == 200, refreshed_matches.text
    assert {
        item["buyer_id"]
        for item in refreshed_matches.json()["matches"]
        if item["qualification_status"] == "qualified"
    }.issuperset({buyer_id, backup_buyer_id})
    primary_offer = record_offer_room_offer(
        client,
        case_id,
        buyer_id,
        amount_cents=19000000,
        proof_document_id=proof["id"],
        idempotency_key="reconciliation-primary-offer",
    )
    backup_offer = record_offer_room_offer(
        client,
        case_id,
        backup_buyer_id,
        amount_cents=18500000,
        proof_document_id=backup_proof["id"],
        idempotency_key="reconciliation-backup-offer",
    )
    selection = select_offer_room_buyers(
        client,
        case_id,
        primary_offer,
        [backup_offer],
        idempotency_key="reconciliation-selection",
    )
    assert selection.status_code == 201, selection.text
    assert selection.json()["current_selection"]["primary"]["buyer_id"] == buyer_id

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
    case_id = create_approved_disposition_case(client, transaction_id)
    put_verified_buy_box(client, buyer_id)
    proof = upload_received_proof(client, buyer_id)
    verify_proof(client, proof["id"])
    backup_buyer_id = create_active_buyer(
        client,
        name="Current Proof Backup Buyer",
        email="current-proof-backup@example.com",
    )
    put_verified_buy_box(client, backup_buyer_id)
    backup_proof = upload_received_proof(client, backup_buyer_id)
    verify_proof(client, backup_proof["id"])
    matched = client.post(
        f"/api/v1/dispositions/cases/{case_id}/matches",
        headers=HEADERS,
    )
    assert matched.status_code == 200, matched.text
    primary_offer = record_offer_room_offer(
        client,
        case_id,
        buyer_id,
        amount_cents=19000000,
        proof_document_id=proof["id"],
        idempotency_key="current-proof-primary-offer",
    )
    backup_offer = record_offer_room_offer(
        client,
        case_id,
        backup_buyer_id,
        amount_cents=18500000,
        proof_document_id=backup_proof["id"],
        idempotency_key="current-proof-backup-offer",
    )
    proof_row = db_session.get(BuyerProofDocument, UUID(proof["id"]))
    assert proof_row is not None
    proof_row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.commit()
    response = select_offer_room_buyers(
        client,
        case_id,
        primary_offer,
        [backup_offer],
        idempotency_key="current-proof-selection",
    )
    assert response.status_code == 422
    assert "current verified proof" in response.json()["detail"].lower()


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
    approved = approve_disposition_package(client, case_id)
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

    backup_buyer_id = create_active_buyer(
        client,
        name="Proof Renewal Backup Buyer",
        email="proof-renewal-backup@example.com",
    )
    put_verified_buy_box(client, backup_buyer_id)
    backup_proof = upload_received_proof(client, backup_buyer_id)
    verify_proof(client, backup_proof["id"])
    rematched = client.post(
        f"/api/v1/dispositions/cases/{case_id}/matches",
        headers=HEADERS,
    )
    assert rematched.status_code == 200, rematched.text
    primary_offer = record_offer_room_offer(
        client,
        case_id,
        buyer_id,
        amount_cents=19000000,
        proof_document_id=match["latest_proof_document_id"],
        idempotency_key="proof-renewal-primary-offer",
    )
    backup_offer = record_offer_room_offer(
        client,
        case_id,
        backup_buyer_id,
        amount_cents=18500000,
        proof_document_id=backup_proof["id"],
        idempotency_key="proof-renewal-backup-offer",
    )
    selected = select_offer_room_buyers(
        client,
        case_id,
        primary_offer,
        [backup_offer],
        idempotency_key="proof-renewal-selection",
    )
    assert selected.status_code == 201, selected.text


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
    assert approve_disposition_package(client, case_id).status_code == 200
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
    assert all(risk["reason"] != "Proof of funds is expired." for risk in payload["risk_alerts"])


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
    approved = approve_disposition_package(client, case_id)
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
    assert approve_disposition_package(client, case_id).status_code == 200
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


@pytest.mark.parametrize(
    "authority_field",
    [
        "can_send_outreach",
        "can_select_buyer",
        "can_bind_stonegate",
        "can_update_buyer",
    ],
)
def test_disposition_copilot_output_rejects_model_authority(
    authority_field: str,
) -> None:
    output: dict[str, Any] = {
        "status_summary": "Draft guidance only.",
        "package_gaps": [],
        "package_highlights": [],
        "recommended_buyers": [],
        "offer_comparison": [],
        "buyer_outreach_subject": "",
        "buyer_outreach_body": "",
        "recommended_internal_actions": [],
        "relationship_update_proposals": [],
        "risk_alerts": [],
        "uncertainties": [],
        "evidence": ["case_snapshot:test"],
        "drafts": [],
        "reply_classifications": [],
        "next_actions": [],
        "buyer_update_proposals": [],
        "can_send_outreach": False,
        "can_select_buyer": False,
        "can_bind_stonegate": False,
        "can_update_buyer": False,
        "confidence": 50,
    }
    output[authority_field] = True

    with pytest.raises(ValidationError):
        DispositionCoordinationOutput.model_validate(output)


def test_disposition_copilot_rejects_unsupported_and_wrong_buyer_citations(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    _, transaction_id, first_buyer_id = setup_case_foundation(db_session, client)
    case_id = create_approved_disposition_case(client, transaction_id)
    second_buyer_id = create_active_buyer(
        client,
        name="Second Atlanta Buyer",
        email="second-atlanta@example.com",
    )
    for buyer_id in (first_buyer_id, second_buyer_id):
        put_verified_buy_box(client, buyer_id)
        proof = upload_received_proof(client, buyer_id)
        verify_proof(client, proof["id"])
    matched = client.post(
        f"/api/v1/dispositions/cases/{case_id}/matches",
        headers=HEADERS,
    )
    assert matched.status_code == 200, matched.text

    owner = db_session.scalar(select(User).where(User.email == OWNER_EMAIL))
    case = db_session.get(DispositionCase, UUID(case_id))
    assert owner is not None and case is not None
    principal = principal_for_user(db_session, owner)
    facts = disposition_copilot._disposition_facts(db_session, principal, case)
    case_citation = next(
        item.citation_id for item in facts["citations"] if item.source_type == "case_snapshot"
    )
    second_buyer_citation = next(
        item.citation_id
        for item in facts["citations"]
        if item.source_type == "buyer_match"
        and item.citation_id in facts["buyer_citation_ids"][UUID(second_buyer_id)]
    )
    base_output: dict[str, Any] = {
        "status_summary": "Compare saved buyer evidence.",
        "package_gaps": [],
        "package_highlights": [],
        "recommended_buyers": [],
        "offer_comparison": [],
        "buyer_outreach_subject": "",
        "buyer_outreach_body": "",
        "recommended_internal_actions": [],
        "relationship_update_proposals": [],
        "risk_alerts": [],
        "uncertainties": [],
        "evidence": [case_citation],
        "drafts": [],
        "reply_classifications": [],
        "next_actions": [],
        "buyer_update_proposals": [],
        "can_send_outreach": False,
        "can_select_buyer": False,
        "can_bind_stonegate": False,
        "can_update_buyer": False,
        "confidence": 50,
    }

    unsupported = DispositionCoordinationOutput.model_validate(
        {**base_output, "evidence": ["case_snapshot:fabricated"]}
    )
    with pytest.raises(ValueError, match="outside this disposition case"):
        disposition_copilot._validate_output(case, facts, unsupported)

    first_buyer = db_session.get(Buyer, UUID(first_buyer_id))
    assert first_buyer is not None
    wrong_entity = DispositionCoordinationOutput.model_validate(
        {
            **base_output,
            "recommended_buyers": [
                {
                    "buyer_id": first_buyer_id,
                    "buyer_name": first_buyer.name,
                    "recommendation": "priority",
                    "rationale": ["Review this buyer."],
                    "risks": [],
                    "evidence": ["Saved match evidence."],
                    "citation_ids": [second_buyer_citation],
                }
            ],
        }
    )
    with pytest.raises(ValueError, match="exact buyer"):
        disposition_copilot._validate_output(case, facts, wrong_entity)

    assert case.selected_buyer_id is None
    assert (
        db_session.scalar(
            select(func.count(DispositionCampaign.id)).where(
                DispositionCampaign.disposition_case_id == case.id
            )
        )
        == 0
    )


def test_disposition_copilot_time_boundaries_make_saved_evidence_stale(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = TestClient(app)
    _, transaction_id, buyer_id = setup_case_foundation(db_session, client)
    case_id = create_approved_disposition_case(client, transaction_id)
    base_time = datetime.now(UTC).replace(microsecond=0)
    boundary_time = base_time + timedelta(days=3)
    put_verified_buy_box(client, buyer_id)
    proof = upload_received_proof(client, buyer_id, expires_at=boundary_time)
    verify_proof(client, proof["id"], expires_at=boundary_time)
    matched = client.post(
        f"/api/v1/dispositions/cases/{case_id}/matches",
        headers=HEADERS,
    )
    assert matched.status_code == 200, matched.text
    offer = record_offer_room_offer(
        client,
        case_id,
        buyer_id,
        amount_cents=19000000,
        proof_document_id=proof["id"],
        idempotency_key="copilot-time-boundary-offer",
    )
    saved_offer = db_session.get(BuyerOffer, UUID(offer["id"]))
    owner = db_session.scalar(select(User).where(User.email == OWNER_EMAIL))
    case = db_session.get(DispositionCase, UUID(case_id))
    assert saved_offer is not None and owner is not None and case is not None
    saved_offer.deposit_due_at = boundary_time
    db_session.commit()

    class FrozenDateTime(datetime):
        current = base_time

        @classmethod
        def now(cls, tz: object | None = None) -> datetime:
            value = cls.current
            if tz is None:
                return value.replace(tzinfo=None)
            return value.astimezone(tz)  # type: ignore[arg-type]

    monkeypatch.setattr(disposition_copilot, "datetime", FrozenDateTime)
    principal = principal_for_user(db_session, owner)
    initial_facts = disposition_copilot._disposition_facts(db_session, principal, case)
    initial_citation_facts = {item.source_type: item.fact for item in initial_facts["citations"]}
    assert '"freshness_status":"current_verified"' in initial_citation_facts["buyer_proof"]
    assert '"deposit_status":"pending"' in initial_citation_facts["buyer_offer"]
    case_citation = next(
        item.citation_id
        for item in initial_facts["citations"]
        if item.source_type == "case_snapshot"
    )
    output = DispositionCoordinationOutput.model_validate(
        {
            "status_summary": "Review current proof and deposit timing.",
            "package_gaps": [],
            "package_highlights": [],
            "recommended_buyers": [],
            "offer_comparison": [],
            "buyer_outreach_subject": "",
            "buyer_outreach_body": "",
            "recommended_internal_actions": [],
            "relationship_update_proposals": [],
            "risk_alerts": [],
            "uncertainties": [],
            "evidence": [case_citation],
            "drafts": [],
            "reply_classifications": [],
            "next_actions": [],
            "buyer_update_proposals": [],
            "can_send_outreach": False,
            "can_select_buyer": False,
            "can_bind_stonegate": False,
            "can_update_buyer": False,
            "confidence": 60,
        }
    )
    recommendation = DispositionCopilotRecommendation(
        organization_id=owner.organization_id,
        disposition_case_id=case.id,
        transaction_id=case.transaction_id,
        lead_id=case.lead_id,
        generated_for_user_id=owner.id,
        ai_run_log_id=None,
        idempotency_key="copilot-time-boundary-draft",
        status="draft",
        output_payload=output.model_dump(mode="json"),
        evidence_snapshot={
            "schema_version": "ds9-v1",
            "evidence_fingerprint": initial_facts["evidence_fingerprint"],
            "citations": [item.model_dump(mode="json") for item in initial_facts["citations"]],
        },
        confidence_score=60,
        generated_at=base_time,
        reviewed_at=None,
    )
    db_session.add(recommendation)
    db_session.commit()
    recommendation_id = str(recommendation.id)
    saved_proof = db_session.get(BuyerProofDocument, UUID(proof["id"]))
    assert saved_proof is not None
    proof_updated_at = saved_proof.updated_at
    offer_updated_at = saved_offer.updated_at

    FrozenDateTime.current = base_time + timedelta(days=4)
    current_facts = disposition_copilot._disposition_facts(db_session, principal, case)
    current_citation_facts = {item.source_type: item.fact for item in current_facts["citations"]}
    assert '"freshness_status":"expired"' in current_citation_facts["buyer_proof"]
    assert '"deposit_status":"overdue"' in current_citation_facts["buyer_offer"]
    assert current_facts["evidence_fingerprint"] != initial_facts["evidence_fingerprint"]
    assert db_session.get(BuyerProofDocument, UUID(proof["id"])).updated_at == proof_updated_at
    assert db_session.get(BuyerOffer, UUID(offer["id"])).updated_at == offer_updated_at

    overview = client.get(
        f"/api/v1/dispositions/cases/{case_id}/copilot",
        headers=HEADERS,
    )
    assert overview.status_code == 200, overview.text
    saved_draft = next(
        item for item in overview.json()["recommendations"] if item["id"] == recommendation_id
    )
    assert saved_draft["evidence_status"] == "stale"
    assert saved_draft["permitted_review_decisions"] == ["rejected", "ignored"]
    for decision, extra in (
        ("accepted", {}),
        ("edited", {"final_output": output.model_dump(mode="json")}),
    ):
        blocked = client.post(
            f"/api/v1/dispositions/copilot/recommendations/{recommendation_id}/review",
            headers=HEADERS,
            json={"decision": decision, **extra},
        )
        assert blocked.status_code == 422
        assert "evidence changed" in blocked.json()["detail"]


def test_disposition_copilot_contact_availability_changes_evidence_without_pii(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    _, transaction_id, buyer_id = setup_case_foundation(db_session, client)
    case_id = create_approved_disposition_case(client, transaction_id)
    put_verified_buy_box(client, buyer_id)
    matched = client.post(
        f"/api/v1/dispositions/cases/{case_id}/matches",
        headers=HEADERS,
    )
    assert matched.status_code == 200, matched.text
    owner = db_session.scalar(select(User).where(User.email == OWNER_EMAIL))
    case = db_session.get(DispositionCase, UUID(case_id))
    buyer = db_session.get(Buyer, UUID(buyer_id))
    assert owner is not None and case is not None and buyer is not None
    principal = principal_for_user(db_session, owner)

    initial = disposition_copilot._disposition_facts(db_session, principal, case)
    contact_citation = next(
        item for item in initial["citations"] if item.source_type == "buyer_contact_status"
    )
    assert contact_citation.source_id == buyer_id
    assert '"has_email":true' in contact_citation.fact
    assert buyer.email is not None
    assert buyer.email not in contact_citation.fact

    buyer.email = None
    db_session.commit()
    changed = disposition_copilot._disposition_facts(db_session, principal, case)
    changed_contact = next(
        item for item in changed["citations"] if item.source_type == "buyer_contact_status"
    )
    assert '"has_email":false' in changed_contact.fact
    assert changed["evidence_fingerprint"] != initial["evidence_fingerprint"]


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
    assert approve_disposition_package(client, case_id).status_code == 200
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
    assert "Confirm the property address." not in copilot_overview.json()["readiness_gaps"]
    assert "Confirm the property type." not in copilot_overview.json()["readiness_gaps"]
    offer = record_offer_room_offer(
        client,
        case_id,
        buyer_id,
        amount_cents=19000000,
        proof_document_id=proof["id"],
        idempotency_key="copilot-primary-offer",
    )
    offer_id = offer["id"]

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
                assert "meets_internal_floor" not in prompt
                request_context = json.loads(prompt)["request"]
                evidence_catalog = request_context["evidence_catalog"]
                citation_by_type = {
                    item["source_type"]: item["citation_id"] for item in evidence_catalog
                }
                contact_citation = next(
                    item
                    for item in evidence_catalog
                    if item["source_type"] == "buyer_contact_status"
                )
                assert "buyer_email" not in contact_citation["fact"]
                assert "buyer_phone" not in contact_citation["fact"]
                assert '"contact_available":true' in contact_citation["fact"]
                case_citation = citation_by_type["case_snapshot"]
                package_citation = citation_by_type["package_version"]
                match_citation = citation_by_type["buyer_match"]
                proof_citation = citation_by_type["buyer_proof"]
                offer_citation = citation_by_type["buyer_offer"]
                schema = kwargs["json_schema"]
                assert isinstance(schema, dict)
                assert schema["additionalProperties"] is False
                assert schema["properties"]["can_send_outreach"]["const"] is False
                assert schema["properties"]["can_select_buyer"]["const"] is False
                assert schema["properties"]["can_bind_stonegate"]["const"] is False
                assert schema["properties"]["can_update_buyer"]["const"] is False
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
                                "citation_ids": [
                                    package_citation,
                                    match_citation,
                                    proof_citation,
                                ],
                            }
                        ],
                        "offer_comparison": [
                            {
                                "offer_id": offer_id,
                                "buyer_id": buyer_id,
                                "buyer_name": "Reliable Atlanta Buyer",
                                "strength": "strong",
                                "execution_risk": "low",
                                "rationale": [
                                    "Offer meets the approved economics.",
                                    "Earnest money is recorded.",
                                ],
                                "risks": ["Deposit receipt has not been recorded."],
                                "citation_ids": [offer_citation, proof_citation],
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
                            case_citation,
                            package_citation,
                            match_citation,
                            offer_citation,
                        ],
                        "drafts": [
                            {
                                "draft_type": "package_summary",
                                "buyer_id": None,
                                "title": "Approved Atlanta package",
                                "body": "A current approved package is ready for human review.",
                                "citation_ids": [package_citation],
                                "requires_human_approval": True,
                            },
                            {
                                "draft_type": "recipient_segment",
                                "buyer_id": buyer_id,
                                "title": "Verified Atlanta buyers",
                                "body": "Review the current ranked buyer for possible outreach.",
                                "citation_ids": [
                                    package_citation,
                                    match_citation,
                                    proof_citation,
                                ],
                                "requires_human_approval": True,
                            },
                            {
                                "draft_type": "email",
                                "buyer_id": buyer_id,
                                "title": "Atlanta opportunity",
                                "body": "Review this approved-package email draft before use.",
                                "citation_ids": [package_citation, match_citation],
                                "requires_human_approval": True,
                            },
                            {
                                "draft_type": "sms",
                                "buyer_id": buyer_id,
                                "title": "Atlanta opportunity",
                                "body": "Review this approved-package SMS draft before use.",
                                "citation_ids": [package_citation, match_citation],
                                "requires_human_approval": True,
                            },
                            {
                                "draft_type": "call_brief",
                                "buyer_id": buyer_id,
                                "title": "Buyer call brief",
                                "body": "Confirm funding, interest, timing, and deposit readiness.",
                                "citation_ids": [
                                    package_citation,
                                    match_citation,
                                    proof_citation,
                                ],
                                "requires_human_approval": True,
                            },
                            {
                                "draft_type": "follow_up",
                                "buyer_id": buyer_id,
                                "title": "Buyer follow-up",
                                "body": "Review a follow-up about the current approved package.",
                                "citation_ids": [package_citation, match_citation],
                                "requires_human_approval": True,
                            },
                        ],
                        "reply_classifications": [],
                        "next_actions": [
                            {
                                "action_type": "proof_request",
                                "buyer_id": buyer_id,
                                "offer_id": offer_id,
                                "action": "Confirm current funds and the deposit deadline.",
                                "rationale": "Selection remains a human decision.",
                                "confidence": 84,
                                "priority": "high",
                                "citation_ids": [offer_citation, proof_citation],
                                "requires_human_approval": True,
                            }
                        ],
                        "buyer_update_proposals": [
                            {
                                "buyer_id": buyer_id,
                                "field_name": "reliability_note",
                                "proposed_value": "Track deposit performance after the deal.",
                                "rationale": "No completed Stonegate closing is recorded.",
                                "confidence": 72,
                                "citation_ids": [match_citation, offer_citation],
                                "requires_human_approval": True,
                            }
                        ],
                        "can_send_outreach": False,
                        "can_select_buyer": False,
                        "can_bind_stonegate": False,
                        "can_update_buyer": False,
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
        recommendation = result["recommendation"]
        recommendation_id = recommendation["id"]
        assert recommendation["evidence_status"] == "current"
        assert recommendation["evidence_citations"]
        assert recommendation["ai_trace"]["model_name"]
        assert recommendation["ai_trace"]["prompt_version_id"]
        assert recommendation["authority"] == {
            "can_send_outreach": False,
            "can_select_buyer": False,
            "can_bind_stonegate": False,
            "can_update_buyer": False,
        }
        assert {item["draft_type"] for item in recommendation["output_payload"]["drafts"]} == {
            "package_summary",
            "recipient_segment",
            "email",
            "sms",
            "call_brief",
            "follow_up",
        }
        assert recommendation["output_payload"]["next_actions"][0]["confidence"] == 84

        repeated = client.post(
            f"/api/v1/dispositions/cases/{case_id}/copilot/analyze",
            headers=HEADERS,
            json={"idempotency_key": "disposition-copilot:test:1"},
        )
        assert repeated.json()["recommendation"]["id"] == recommendation_id
        stale_candidate = client.post(
            f"/api/v1/dispositions/cases/{case_id}/copilot/analyze",
            headers=HEADERS,
            json={"idempotency_key": "disposition-copilot:test:stale"},
        )
        assert stale_candidate.status_code == 200, stale_candidate.text
        stale_recommendation_id = stale_candidate.json()["recommendation"]["id"]
        ignored_candidate = client.post(
            f"/api/v1/dispositions/cases/{case_id}/copilot/analyze",
            headers=HEADERS,
            json={"idempotency_key": "disposition-copilot:test:ignored"},
        )
        assert ignored_candidate.status_code == 200, ignored_candidate.text
        ignored_recommendation_id = ignored_candidate.json()["recommendation"]["id"]
        stale_ignored_candidate = client.post(
            f"/api/v1/dispositions/cases/{case_id}/copilot/analyze",
            headers=HEADERS,
            json={"idempotency_key": "disposition-copilot:test:stale-ignored"},
        )
        assert stale_ignored_candidate.status_code == 200, stale_ignored_candidate.text
        stale_ignored_recommendation_id = stale_ignored_candidate.json()["recommendation"]["id"]

        normal_evaluation = {
            "scenario_group": "normal",
            "critical_authority_violation": False,
            "unsupported_or_hallucinated_citation": False,
            "package_fact_correctness": "correct",
            "buyer_match_relevance": "relevant",
            "reply_classification_accuracy": "not_applicable",
            "next_action_usefulness": "useful",
            "notes": "Normal-case evaluator evidence.",
        }
        review = client.post(
            f"/api/v1/dispositions/copilot/recommendations/{recommendation_id}/review",
            headers=HEADERS,
            json={
                "decision": "accepted",
                "notes": "Disposition specialist reviewed the evidence.",
                "estimated_time_saved_seconds": 600,
                "quality_evaluation": normal_evaluation,
            },
        )
        assert review.status_code == 200, review.text
        assert review.json()["decision"] == "accepted"
        assert review.json()["quality_evaluation"]["scenario_group"] == "normal"
        duplicate_review = client.post(
            f"/api/v1/dispositions/copilot/recommendations/{recommendation_id}/review",
            headers=HEADERS,
            json={"decision": "accepted"},
        )
        assert duplicate_review.status_code == 409
        assert "already been reviewed" in duplicate_review.json()["detail"]

        ignored = client.post(
            (f"/api/v1/dispositions/copilot/recommendations/{ignored_recommendation_id}/review"),
            headers=HEADERS,
            json={
                "decision": "ignored",
                "notes": "Duplicate-like draft excluded from the measured pilot.",
                "quality_evaluation": {
                    **normal_evaluation,
                    "scenario_group": "adversarial",
                },
            },
        )
        assert ignored.status_code == 200, ignored.text

        overview = client.get(
            f"/api/v1/dispositions/cases/{case_id}/copilot",
            headers=HEADERS,
        )
        assert overview.status_code == 200
        recommendation_statuses = {
            item["id"]: item["status"] for item in overview.json()["recommendations"]
        }
        assert recommendation_statuses[recommendation_id] == "accepted"
        assert recommendation_statuses[ignored_recommendation_id] == "ignored"
        assert overview.json()["external_actions_blocked"] is True
        pilot = overview.json()["metrics"]["pilot_evaluation"]
        assert overview.json()["metrics"]["reviewed"] == 2
        assert pilot["pilot_ready"] is False
        assert pilot["minimum_domain_sample_size"] == 10
        assert pilot["evaluated_recommendations"] == 1
        assert pilot["observed_scenario_groups"] == ["normal"]
        assert "adversarial" in pilot["missing_scenario_groups"]
        assert any("50" in blocker for blocker in pilot["blockers"])
        assert any("10 disposition cases" in blocker for blocker in pilot["blockers"])
        assert any("package facts" in blocker for blocker in pilot["blockers"])

        record_offer_room_offer(
            client,
            case_id,
            buyer_id,
            amount_cents=19100000,
            proof_document_id=proof["id"],
            idempotency_key="copilot-evidence-revision",
        )
        stale_overview = client.get(
            f"/api/v1/dispositions/cases/{case_id}/copilot",
            headers=HEADERS,
        )
        assert stale_overview.status_code == 200, stale_overview.text
        stale_read = next(
            item
            for item in stale_overview.json()["recommendations"]
            if item["id"] == stale_recommendation_id
        )
        assert stale_read["evidence_status"] == "stale"
        assert stale_read["permitted_review_decisions"] == ["rejected", "ignored"]
        stale_ignored_read = next(
            item
            for item in stale_overview.json()["recommendations"]
            if item["id"] == stale_ignored_recommendation_id
        )
        assert stale_ignored_read["evidence_status"] == "stale"
        assert stale_ignored_read["permitted_review_decisions"] == ["rejected", "ignored"]
        stale_accept = client.post(
            (f"/api/v1/dispositions/copilot/recommendations/{stale_recommendation_id}/review"),
            headers=HEADERS,
            json={"decision": "accepted"},
        )
        assert stale_accept.status_code == 422
        assert "evidence changed" in stale_accept.json()["detail"]
        stale_edit = client.post(
            (f"/api/v1/dispositions/copilot/recommendations/{stale_recommendation_id}/review"),
            headers=HEADERS,
            json={
                "decision": "edited",
                "final_output": stale_candidate.json()["recommendation"]["output_payload"],
            },
        )
        assert stale_edit.status_code == 422
        assert "evidence changed" in stale_edit.json()["detail"]
        stale_reject = client.post(
            (f"/api/v1/dispositions/copilot/recommendations/{stale_recommendation_id}/review"),
            headers=HEADERS,
            json={
                "decision": "rejected",
                "notes": "Evidence changed; generate a current draft.",
                "quality_evaluation": {
                    **normal_evaluation,
                    "scenario_group": "stale",
                },
            },
        )
        assert stale_reject.status_code == 200, stale_reject.text
        assert stale_reject.json()["decision"] == "rejected"
        stale_ignore = client.post(
            (
                "/api/v1/dispositions/copilot/recommendations/"
                f"{stale_ignored_recommendation_id}/review"
            ),
            headers=HEADERS,
            json={"decision": "ignored", "notes": "Superseded by current evidence."},
        )
        assert stale_ignore.status_code == 200, stale_ignore.text
        assert stale_ignore.json()["decision"] == "ignored"
        final_overview = client.get(
            f"/api/v1/dispositions/cases/{case_id}/copilot",
            headers=HEADERS,
        )
        final_pilot = final_overview.json()["metrics"]["pilot_evaluation"]
        assert final_pilot["evaluated_recommendations"] == 2
        assert final_pilot["observed_scenario_groups"] == ["normal", "stale"]
        assert "adversarial" in final_pilot["missing_scenario_groups"]

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
    assert db_session.scalar(select(func.count(DispositionCopilotRecommendation.id))) == 4
    assert db_session.scalar(select(func.count(DispositionCopilotReview.id))) == 4


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
    assert pool["run"]["matcher_version"] == "stonegate_buyer_pool_v2"
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
    assert all(item["source_type"] != "external" for item in post_conversion_run.json()["entries"])
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
        select(DispositionCampaign).where(DispositionCampaign.disposition_case_id == UUID(case_id))
    )
    assert campaign is not None
    assert campaign.recipient_count == 1


def _complete_case_for_disposition_intelligence(
    db: Session,
    client: TestClient,
) -> tuple[str, str, str]:
    lead_id, transaction_id, buyer_id = setup_case_foundation(db, client)
    case_id = create_approved_disposition_case(client, transaction_id)
    offer = record_offer_room_offer(
        client,
        case_id,
        buyer_id,
        amount_cents=19000000,
        proof_document_id=None,
        idempotency_key="ds10-canonical-offer",
    )
    owner = db.scalar(select(User).where(User.email == OWNER_EMAIL))
    case = db.get(DispositionCase, UUID(case_id))
    transaction = db.get(Transaction, UUID(transaction_id))
    assert owner is not None and case is not None and transaction is not None
    now = datetime.now(UTC).replace(microsecond=0)
    transaction.status = "funded"
    transaction.contract_executed_at = now - timedelta(days=10)
    transaction.funded_at = now
    transaction.closed_at = now
    transaction.assignment_fee_cents = 4000000
    db.add(
        DispositionBuyerOutcome(
            organization_id=case.organization_id,
            disposition_case_id=case.id,
            selection_id=None,
            offer_id=UUID(offer["id"]),
            buyer_id=UUID(buyer_id),
            recorded_by_user_id=owner.id,
            outcome_type="completed_close",
            cause_category="completed",
            reason="Canonical funded assignment completed for DS10 verification.",
            details="Synthetic management-intelligence fixture.",
            evidence_snapshot={"fixture": "ds10_completed_assignment"},
            occurred_at=now,
            history_applied_at=now,
            completed_delta=1,
            failed_delta=0,
            reliability_delta_basis_points=100,
            idempotency_key="ds10-completed-close",
        )
    )
    db.add(
        DealReconciliation(
            organization_id=case.organization_id,
            transaction_id=case.transaction_id,
            disposition_case_id=case.id,
            compensation_plan_version_id=case.compensation_plan_version_id,
            disposition_operating_mode_id=case.disposition_operating_mode_id,
            created_by_user_id=owner.id,
            approved_by_user_id=owner.id,
            status="approved",
            gross_revenue_cents=4000000,
            acquisition_reserve_cents=250000,
            deal_deductions_cents=250000,
            adjusted_deal_margin_cents=3500000,
            total_compensation_cents=500000,
            company_profit_cents=3000000,
            company_margin_basis_points=7500,
            target_margin_basis_points=3000,
            snapshot={"fixture": "ds10_approved_reconciliation"},
            approved_at=now,
            notes="Approved synthetic reconciliation for DS10 verification.",
        )
    )
    db.add(
        RevenueRecord(
            organization_id=case.organization_id,
            lead_id=UUID(lead_id),
            deal_id=case.deal_id,
            transaction_id=case.transaction_id,
            source="assignment_fee",
            status="collected",
            amount_cents=4000000,
            received_at=now,
            notes="Collected synthetic assignment revenue for DS10 verification.",
        )
    )
    db.commit()
    return case_id, str(case.deal_id), buyer_id


def test_disposition_intelligence_empty_report_and_invalid_window(
    db_session: Session,
    api_db_override: None,
) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    client = TestClient(app)

    response = client.get("/api/v1/dispositions/intelligence", headers=HEADERS)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["data_state"] == "unavailable"
    assert payload["access"]["private_economics_visible"] is True
    assert payload["activity"] == {
        "cases": 0,
        "packages_approved": 0,
        "outreach_sent": 0,
        "replies": 0,
        "inquiries": 0,
        "showings": 0,
        "offers": 0,
        "selected_buyers": 0,
        "deposits": 0,
    }
    assert payload["economics"]["state"] == "unavailable"
    assert payload["economics"]["completed_assignments"] == 0
    assert payload["economics"]["campaign_cost_cents"] is None
    assert all(payload["filter_options"][key] == [] for key in payload["filter_options"])
    assert all(item["denominator"] == 0 for item in payload["rates"])

    invalid = client.get(
        "/api/v1/dispositions/intelligence",
        headers=HEADERS,
        params={
            "start_at": "2026-08-30T00:00:00Z",
            "end_at": "2026-08-01T00:00:00Z",
        },
    )
    assert invalid.status_code == 422, invalid.text
    assert "start_at must be on or before end_at" in invalid.json()["detail"]


def test_disposition_intelligence_populated_canonical_assignment_and_filters(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    _, deal_id, buyer_id = _complete_case_for_disposition_intelligence(db_session, client)

    response = client.get(
        "/api/v1/dispositions/intelligence",
        headers=HEADERS,
        params={"deal_id": deal_id, "buyer_id": buyer_id, "asset_class": "house"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["data_state"] == "partial"
    assert payload["activity"]["cases"] == 1
    assert payload["activity"]["packages_approved"] == 1
    assert payload["activity"]["offers"] == 1
    assert payload["economics"]["state"] == "known"
    assert payload["economics"]["completed_assignments"] == 1
    assert payload["economics"]["reconciled_completed_assignments"] == 1
    assert payload["economics"]["contracted_assignment_spread_cents"] == 4000000
    assert payload["economics"]["collected_revenue_cents"] == 4000000
    assert payload["economics"]["approved_company_profit_cents"] == 3000000
    assert payload["economics"]["campaign_cost_cents"] is None
    assert payload["scope"]["filters_applied"]["deal_id"] == deal_id
    assert payload["scope"]["filters_applied"]["buyer_id"] == buyer_id
    assert payload["scope"]["filters_applied"]["asset_class"] == "house"
    assert payload["buyers"][0]["buyer_id"] == buyer_id
    assert payload["buyers"][0]["completed_assignments"] == 1
    assert any(item["completed_assignments"] == 1 for item in payload["sources"])
    completed_provenance = next(
        item for item in payload["provenance"] if item["metric_key"] == "completed_assignments"
    )
    assert completed_provenance["state"] == "known"
    campaign_quality = next(
        item for item in payload["data_quality"] if item["key"] == "campaign_cost"
    )
    assert campaign_quality["state"] == "unavailable"
    assert any(option["value"] == deal_id for option in payload["filter_options"]["deals"])
    assert any(option["value"] == buyer_id for option in payload["filter_options"]["buyers"])


def test_disposition_intelligence_excludes_land_case_activity_and_filter_options(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, deal_id, buyer_id = _complete_case_for_disposition_intelligence(
        db_session,
        client,
    )
    case = db_session.get(DispositionCase, UUID(case_id))
    assert case is not None
    lead = db_session.get(Lead, case.lead_id)
    assert lead is not None
    lead.asset_class = "land"
    db_session.commit()

    response = client.get("/api/v1/dispositions/intelligence", headers=HEADERS)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["data_state"] == "unavailable"
    assert all(value == 0 for value in payload["activity"].values())
    assert payload["economics"]["completed_assignments"] == 0
    assert all(options == [] for options in payload["filter_options"].values())
    assert deal_id not in response.text
    assert buyer_id not in response.text


def test_disposition_intelligence_requires_deal_access_and_redacts_economics(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    _complete_case_for_disposition_intelligence(db_session, client)
    disposition_rep = add_user_with_role(
        db_session,
        email="ds10-disposition-rep@example.com",
        display_name="DS10 Disposition Rep",
        role_key="disposition_rep",
    )
    marketing_user = add_user_with_role(
        db_session,
        email="ds10-marketing@example.com",
        display_name="DS10 Marketing",
        role_key="marketing_manager",
    )

    restricted = client.get(
        "/api/v1/dispositions/intelligence",
        headers={"X-Dev-User-Email": disposition_rep.email},
    )
    assert restricted.status_code == 200, restricted.text
    payload = restricted.json()
    assert payload["access"]["private_economics_visible"] is False
    assert payload["economics"]["completed_assignments"] == 1
    for key in (
        "contracted_assignment_spread_cents",
        "collected_revenue_cents",
        "approved_company_profit_cents",
        "campaign_cost_cents",
        "cost_per_offer_cents",
        "cost_per_selected_buyer_cents",
        "cost_per_completed_assignment_cents",
    ):
        assert payload["economics"][key] is None
    assert all(item["collected_revenue_cents"] is None for item in payload["sources"])

    forbidden = client.get(
        "/api/v1/dispositions/intelligence",
        headers={"X-Dev-User-Email": marketing_user.email},
    )
    assert forbidden.status_code == 403, forbidden.text
    assert "deals:view" in forbidden.json()["detail"]


def test_disposition_intelligence_is_organization_scoped(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    _, deal_id, buyer_id = _complete_case_for_disposition_intelligence(db_session, client)
    other = bootstrap_foundation(
        db_session,
        organization_name="Other DS10 Organization",
        admin_email="other-ds10-owner@example.com",
        admin_name="Other DS10 Owner",
    )
    assert other.admin_user is not None

    response = client.get(
        "/api/v1/dispositions/intelligence",
        headers={"X-Dev-User-Email": other.admin_user.email},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["data_state"] == "unavailable"
    assert payload["activity"]["cases"] == 0
    assert payload["economics"]["completed_assignments"] == 0
    assert payload["buyers"] == []
    assert payload["sources"] == []
    assert payload["filter_options"]["deals"] == []
    assert payload["filter_options"]["buyers"] == []
    assert deal_id not in response.text
    assert buyer_id not in response.text
