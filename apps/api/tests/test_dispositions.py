import json
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
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
    BuyerProofDocument,
    CompensationPlanRole,
    CompensationPlanVersion,
    DealDeduction,
    DealReconciliation,
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
    Lead,
    Property,
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
