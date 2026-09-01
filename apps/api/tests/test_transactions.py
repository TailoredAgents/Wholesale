import base64
import hmac
import re
import zlib
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import principal_for_user
from app.core.config import get_settings
from app.main import app
from app.models.foundation import (
    ActivityEvent,
    ApprovalRequest,
    AuditEvent,
    ContractPackage,
    Deal,
    EsignEnvelope,
    EsignProviderEvent,
    EsignRecipient,
    Lead,
    OfferConcession,
    OfferNegotiationPlan,
    Organization,
    Role,
    RoleAssignment,
    Transaction,
    TransactionChecklistItem,
    TransactionDocument,
    TransactionEvent,
    UnderwritingVersion,
    User,
)
from app.services import esign as esign_service
from app.services.bootstrap import bootstrap_foundation
from app.services.contract_authority_locks import lock_offer_authority_for_mutation
from app.services.offer_concessions import record_field_agreement
from tests.test_dispositions import (
    create_approved_disposition_case,
    put_verified_buy_box,
    setup_case_foundation,
    upload_received_proof,
    verify_proof,
)

OWNER_EMAIL = "owner@example.com"
HEADERS = {"X-Dev-User-Email": OWNER_EMAIL}
CANONICAL_EVIDENCE_CHECKLIST_KEYS = {
    "open_title",
    "seller_documents",
    "due_diligence",
    "closing_confirmed",
}


def pdf_page_streams(content: bytes) -> bytes:
    decoded = []
    for encoded in re.findall(rb"stream\r?\n(.*?)endstream", content, re.DOTALL):
        try:
            compressed = base64.a85decode(
                b"<~" + encoded.strip(),
                adobe=True,
            )
            decoded.append(zlib.decompress(compressed))
        except (ValueError, zlib.error):
            continue
    return b"\n".join(decoded)


def setup_transaction(db: Session, client: TestClient) -> tuple[str, str]:
    bootstrap_foundation(
        db, organization_name="Stonegate Home Buyers", admin_email=OWNER_EMAIL, admin_name="Owner"
    )
    lead = client.post(
        "/api/v1/leads",
        headers=HEADERS,
        json={
            "contact": {"legal_name": "Jane Seller", "contact_type": "seller"},
            "property": {
                "street_address": "123 Peachtree St",
                "city": "Atlanta",
                "state": "GA",
                "postal_code": "30303",
                "property_type": "single_family",
            },
            "source": "referral",
            "stage_key": "offer_ready",
        },
    )
    transaction_response = client.post(
        f"/api/v1/leads/{lead.json()['id']}/transactions",
        headers=HEADERS,
        json={
            "purchase_price_cents": 17000000,
            "earnest_money_cents": 100000,
            "closing_date": "2026-08-14T21:00:00Z",
            "inspection_period_days": 7,
        },
    )
    assert lead.status_code == 201, lead.text
    assert transaction_response.status_code == 201, transaction_response.text
    seed_approved_offer_authority(db, lead.json()["id"])
    return lead.json()["id"], transaction_response.json()["transactions"][0]["id"]


def seed_approved_offer_authority(
    db: Session,
    lead_id: str,
    *,
    opening_offer_cents: int = 17_000_000,
    seller_ceiling_cents: int = 17_000_000,
) -> OfferNegotiationPlan:
    lead = db.get(Lead, UUID(lead_id))
    owner = db.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert lead is not None
    assert owner is not None
    version = UnderwritingVersion(
        organization_id=lead.organization_id,
        lead_id=lead.id,
        property_id=lead.property_id,
        created_by_user_id=owner.id,
        version_number=1,
        valuation_profile="house_v3",
        status="approved",
        arv_low_cents=25_000_000,
        arv_high_cents=27_000_000,
        repair_low_cents=2_000_000,
        repair_high_cents=3_000_000,
        max_offer_cents=seller_ceiling_cents,
        recommended_offer_cents=opening_offer_cents,
        offer_strategy="test_authority",
        notes="Focused transaction authority fixture.",
        source="manual",
        underwriting_metadata={"fixture": True},
    )
    db.add(version)
    db.flush()
    approval = ApprovalRequest(
        organization_id=lead.organization_id,
        requested_by_user_id=owner.id,
        assigned_to_user_id=owner.id,
        decided_by_user_id=owner.id,
        request_type="offer_ceiling",
        entity_type="offer_negotiation_plan",
        entity_id=None,
        status="approved",
        title="Approve focused offer authority",
        summary="Approved authority fixture for contract governance tests.",
        decision_notes="Authority verified for transaction tests.",
        decided_at=datetime.now(UTC),
        approval_metadata={"lead_id": str(lead.id)},
    )
    db.add(approval)
    db.flush()
    plan = OfferNegotiationPlan(
        organization_id=lead.organization_id,
        lead_id=lead.id,
        property_id=lead.property_id,
        underwriting_version_id=version.id,
        market_analysis_id=None,
        approval_request_id=approval.id,
        created_by_user_id=owner.id,
        status="approved",
        seller_asking_price_cents=None,
        arv_low_cents=25_000_000,
        arv_point_cents=26_000_000,
        arv_high_cents=27_000_000,
        total_rehab_cents=2_500_000,
        disposition_cents=25_000_000,
        opening_offer_cents=opening_offer_cents,
        target_contract_cents=opening_offer_cents,
        stretch_contract_cents=seller_ceiling_cents,
        seller_ceiling_cents=seller_ceiling_cents,
        seller_context=None,
        rationale="Focused transaction authority fixture.",
        source_snapshot={"fixture": True},
    )
    db.add(plan)
    db.flush()
    approval.entity_id = plan.id
    db.commit()
    return plan


def add_new_underwriting_version(db: Session, lead_id: str) -> UnderwritingVersion:
    lead = db.get(Lead, UUID(lead_id))
    owner = db.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert lead is not None
    assert owner is not None
    version = UnderwritingVersion(
        organization_id=lead.organization_id,
        lead_id=lead.id,
        property_id=lead.property_id,
        created_by_user_id=owner.id,
        version_number=2,
        valuation_profile="house_v3",
        status="needs_review",
        arv_low_cents=24_000_000,
        arv_high_cents=26_000_000,
        repair_low_cents=3_000_000,
        repair_high_cents=4_000_000,
        max_offer_cents=16_000_000,
        recommended_offer_cents=15_000_000,
        offer_strategy="updated_test_authority",
        notes="Newer source version invalidates the contract snapshot.",
        source="manual",
        underwriting_metadata={"fixture": True, "newer": True},
    )
    db.add(version)
    db.commit()
    return version


def purchase_package_payload(purchase_price_cents: int = 17_000_000) -> dict[str, object]:
    return {
        "document_type": "purchase_agreement",
        "seller_name": "Jane Seller",
        "buyer_entity_name": "Stonegate Acquisitions LLC",
        "purchase_price_cents": purchase_price_cents,
        "earnest_money_cents": 100_000,
        "closing_date": "2026-08-14T21:00:00Z",
        "inspection_period_days": 7,
    }


def approve_purchase_package(client: TestClient, transaction_id: str) -> dict[str, object]:
    package = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages",
        headers=HEADERS,
        json=purchase_package_payload(),
    )
    assert package.status_code == 201, package.text
    pending = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package.json()['id']}/request-approval",
        headers=HEADERS,
    )
    assert pending.status_code == 200, pending.text
    approved = client.patch(
        f"/api/v1/approvals/{pending.json()['approval_request_id']}/decision",
        headers=HEADERS,
        json={"status": "approved", "decision_notes": "Exact authority snapshot verified."},
    )
    assert approved.status_code == 200, approved.text
    return cast(dict[str, object], package.json())


def post_external_execution_import(
    client: TestClient,
    lead_id: str,
    *,
    content: bytes,
    headers: dict[str, str] | None = None,
    params: dict[str, object] | None = None,
    content_type: str = "application/pdf",
) -> httpx.Response:
    form_values = dict(params or external_execution_import_params())
    file_name = str(form_values.pop("file_name"))
    form_data = {
        key: ("true" if value is True else "false" if value is False else str(value))
        for key, value in form_values.items()
        if value is not None
    }
    return cast(
        httpx.Response,
        client.post(
            f"/api/v1/leads/{lead_id}/transactions/import-executed-contract",
            headers=headers or HEADERS,
            data=form_data,
            files={"file": (file_name, content, content_type)},
        ),
    )


def test_owner_can_import_external_executed_contract_without_offer_authority(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    lead_id = create_external_import_lead(db_session, client)
    handoff_calls: list[UUID] = []
    disposition_case_id = uuid4()

    def fake_handoff(_db: Session, transaction: Transaction) -> SimpleNamespace:
        handoff_calls.append(transaction.id)
        return SimpleNamespace(id=disposition_case_id)

    monkeypatch.setattr(
        "app.services.disposition_handoff.ensure_house_disposition_case_for_executed_transaction",
        fake_handoff,
    )
    response = post_external_execution_import(
        client,
        lead_id,
        content=b"%PDF-1.7\nfully executed purchase agreement",
        params=external_execution_import_params(
            file_name='..\\docusign-completed\"\r\nX-Test.pdf'
        ),
    )

    assert response.status_code == 201, response.text
    imported = response.json()
    assert imported["lead_stage"] == "under_contract"
    assert imported["transaction_status"] == "executed"
    assert imported["disposition_case_id"] == str(disposition_case_id)
    assert imported["disposition_handoff_ready"] is True
    assert imported["disposition_handoff_status"] == "ready"
    assert imported["disposition_handoff_blockers"] == []
    transaction_id = UUID(imported["transaction_id"])
    package_id = UUID(imported["contract_package_id"])
    document_id = UUID(imported["document_id"])
    assert handoff_calls == [transaction_id]

    transaction = db_session.get(Transaction, transaction_id)
    package = db_session.get(ContractPackage, package_id)
    document = db_session.get(TransactionDocument, document_id)
    lead = db_session.get(Lead, UUID(lead_id))
    assert transaction is not None
    assert package is not None
    assert document is not None
    assert lead is not None
    deal = db_session.get(Deal, transaction.deal_id)
    assert deal is not None
    assert transaction.contract_type == "purchase_agreement"
    assert transaction.purchase_price_cents == 17_500_000
    assert transaction.contract_executed_at is not None
    assert transaction.contract_executed_at.replace(tzinfo=UTC) == datetime(
        2026, 8, 31, 16, tzinfo=UTC
    )
    assert transaction.transaction_metadata is not None
    assert transaction.transaction_metadata["source"] == "external_execution_import"
    assert lead.stage_key == "under_contract"
    assert deal.stage_key == "under_contract"
    assert package.status == "executed"
    assert package.approval_request_id is None
    assert "purchase_authority" not in package.terms_snapshot
    assert package.terms_snapshot["authority_basis"] == "external_fully_executed_agreement"
    assert document.contract_package_id == package.id
    assert document.document_type == "signed_purchase_agreement"
    assert document.status == "executed"
    assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*\.pdf", document.file_name)
    assert document.sha256 == sha256(b"%PDF-1.7\nfully executed purchase agreement").hexdigest()

    governed_items = {
        item.item_key: item
        for item in db_session.scalars(
            select(TransactionChecklistItem).where(
                TransactionChecklistItem.transaction_id == transaction.id
            )
        ).all()
    }
    assert set(governed_items) == CANONICAL_EVIDENCE_CHECKLIST_KEYS | {
        "contract_approved",
        "contract_executed",
        "earnest_money",
        "assignment",
    }
    assert governed_items["contract_approved"].status == "not_applicable"
    assert "internal package approval did not occur" in (
        governed_items["contract_approved"].evidence_notes or ""
    )
    assert governed_items["contract_executed"].status == "complete"
    for item_key in ("contract_approved", "contract_executed"):
        assert governed_items[item_key].evidence_document_id == document.id

    audit = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "contract.execution.external_import",
            AuditEvent.entity_id == transaction.id,
        )
    )
    activity = db_session.scalar(
        select(ActivityEvent).where(
            ActivityEvent.event_type == "lead.contract_external_execution_imported",
            ActivityEvent.entity_id == lead.id,
        )
    )
    assert audit is not None
    assert audit.new_value is not None
    assert audit.new_value["document_sha256"] == document.sha256
    assert activity is not None

    immutable = client.request(
        "DELETE",
        f"/api/v1/transactions/{transaction.id}/documents/{document.id}",
        headers=HEADERS,
        json={"reason": "Attempted removal after external execution import."},
    )
    assert immutable.status_code == 422
    assert "immutable" in immutable.json()["detail"]


def test_external_execution_import_reuses_safe_contract_prep_and_voids_draft(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    lead_id, transaction_id = setup_transaction(db_session, client)
    approved_plan = db_session.scalar(
        select(OfferNegotiationPlan).where(
            OfferNegotiationPlan.lead_id == UUID(lead_id),
            OfferNegotiationPlan.status == "approved",
        )
    )
    assert approved_plan is not None
    pending_plan, pending_concession, plan_approval, concession_approval = (
        seed_pending_offer_authority(db_session, lead_id)
    )
    draft = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages",
        headers=HEADERS,
        json=purchase_package_payload(),
    )
    assert draft.status_code == 201, draft.text
    monkeypatch.setattr(
        "app.services.disposition_handoff.ensure_house_disposition_case_for_executed_transaction",
        lambda _db, _transaction: None,
    )

    response = post_external_execution_import(
        client,
        lead_id,
        content=b"%PDF-1.7\nreplacement external execution",
    )

    assert response.status_code == 201, response.text
    assert response.json()["transaction_id"] == transaction_id
    assert response.json()["disposition_handoff_ready"] is False
    assert response.json()["disposition_handoff_status"] == "needs_setup"
    assert response.json()["disposition_handoff_blockers"] == [
        "Disposition setup is incomplete; automatic retry is pending."
    ]
    old_package = db_session.get(ContractPackage, UUID(draft.json()["id"]))
    transaction = db_session.get(Transaction, UUID(transaction_id))
    assert old_package is not None
    assert transaction is not None
    assert old_package.status == "void"
    assert old_package.voided_at is not None
    assert transaction.status == "executed"
    assert transaction.purchase_price_cents == 17_500_000
    db_session.refresh(approved_plan)
    db_session.refresh(pending_plan)
    db_session.refresh(pending_concession)
    db_session.refresh(plan_approval)
    db_session.refresh(concession_approval)
    assert approved_plan.status == "approved"
    assert pending_plan.status == "cancelled"
    assert pending_concession.status == "cancelled"
    assert plan_approval.status == "cancelled"
    assert concession_approval.status == "cancelled"
    assert "fully executed external" in (plan_approval.decision_notes or "")


def test_external_execution_import_rejects_non_pdf_and_land(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    house_lead_id = create_external_import_lead(db_session, client)
    invalid_pdf = post_external_execution_import(
        client,
        house_lead_id,
        content=b"not a pdf",
    )
    assert invalid_pdf.status_code == 422
    assert "valid PDF header" in invalid_pdf.json()["detail"]

    land_lead_id = create_external_import_lead(db_session, client, asset_class="land")
    land = post_external_execution_import(
        client,
        land_lead_id,
        content=b"%PDF-1.7\nland agreement",
    )
    assert land.status_code == 409
    assert "Land leads" in land.json()["detail"]


def test_external_execution_import_refuses_active_sent_contract_workflow(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    lead_id, transaction_id = setup_transaction(db_session, client)
    transaction = db_session.get(Transaction, UUID(transaction_id))
    assert transaction is not None
    transaction.status = "sent"
    db_session.commit()

    response = post_external_execution_import(
        client,
        lead_id,
        content=b"%PDF-1.7\nconflicting agreement",
    )

    assert response.status_code == 422
    assert "already has an active" in response.json()["detail"]


@pytest.mark.parametrize("empty_field", ["seller_name", "buyer_entity_name"])
def test_external_execution_import_rejects_names_empty_after_trimming(
    db_session: Session,
    api_db_override: None,
    empty_field: str,
) -> None:
    client = TestClient(app)
    lead_id = create_external_import_lead(db_session, client)

    response = post_external_execution_import(
        client,
        lead_id,
        params=external_execution_import_params(**{empty_field: "   "}),
        content=b"%PDF-1.7\nwhitespace name",
    )

    assert response.status_code == 422
    assert (
        db_session.scalar(select(Transaction.id).where(Transaction.lead_id == UUID(lead_id)))
        is None
    )


def test_external_execution_import_does_not_resurrect_dead_deal(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    lead_id = create_external_import_lead(db_session, client)
    lead = db_session.get(Lead, UUID(lead_id))
    assert lead is not None
    dead_deal = Deal(
        organization_id=lead.organization_id,
        lead_id=lead.id,
        property_id=lead.property_id,
        stage_key="dead",
        contract_price_cents=16_000_000,
        assignment_fee_cents=2_000_000,
    )
    db_session.add(dead_deal)
    db_session.commit()
    monkeypatch.setattr(
        "app.services.disposition_handoff.ensure_house_disposition_case_for_executed_transaction",
        lambda _db, _transaction: None,
    )

    response = post_external_execution_import(
        client,
        lead_id,
        content=b"%PDF-1.7\nnew contract after dead deal",
    )

    assert response.status_code == 201, response.text
    imported_transaction = db_session.get(Transaction, UUID(response.json()["transaction_id"]))
    assert imported_transaction is not None
    assert imported_transaction.deal_id != dead_deal.id
    db_session.refresh(dead_deal)
    assert dead_deal.stage_key == "dead"


def test_external_execution_import_requires_contract_authority_permission(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    lead_id = create_external_import_lead(db_session, client)
    unrelated_headers = headers_for_transaction_role(
        db_session,
        role_key="operations_assistant",
        email="catchup-unrelated@example.com",
    )
    acquisition_headers = headers_for_transaction_role(
        db_session,
        role_key="acquisition_rep",
        email="catchup-acquisition@example.com",
    )
    denied = post_external_execution_import(
        client,
        lead_id,
        headers=unrelated_headers,
        content=b"%PDF-1.7\npermission test",
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == (
        "Missing one of permissions: contracts:modify, contracts:record_executed"
    )

    monkeypatch.setattr(
        "app.services.disposition_handoff.ensure_house_disposition_case_for_executed_transaction",
        lambda _db, _transaction: None,
    )
    allowed = post_external_execution_import(
        client,
        lead_id,
        headers=acquisition_headers,
        content=b"%PDF-1.7\npermission test",
    )
    assert allowed.status_code == 201, allowed.text


def test_external_execution_import_keeps_object_storage_after_success(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    lead_id = create_external_import_lead(db_session, client)
    deleted: list[tuple[str, str | None]] = []
    monkeypatch.setattr(
        "app.services.transactions.store_content",
        lambda **_kwargs: SimpleNamespace(
            provider="s3",
            key="org/transactions/executed-agreement.pdf",
            database_bytes=None,
            malware_scan_status="clean",
            retention_until=datetime(2027, 9, 1, tzinfo=UTC),
        ),
    )
    monkeypatch.setattr(
        "app.services.transactions.delete_content",
        lambda *, provider, key: deleted.append((provider, key)),
    )
    monkeypatch.setattr(
        "app.services.disposition_handoff.ensure_house_disposition_case_for_executed_transaction",
        lambda _db, _transaction: None,
    )

    response = post_external_execution_import(
        client,
        lead_id,
        content=b"%PDF-1.7\nobject storage success",
    )

    assert response.status_code == 201, response.text
    assert deleted == []
    document = db_session.get(TransactionDocument, UUID(response.json()["document_id"]))
    assert document is not None
    assert document.storage_provider == "s3"
    assert document.storage_key == "org/transactions/executed-agreement.pdf"


@pytest.mark.parametrize("failure_point", ["handoff", "commit"])
def test_external_execution_import_cleans_object_storage_after_failure(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
    failure_point: str,
) -> None:
    client = TestClient(app)
    lead_id = create_external_import_lead(db_session, client)
    deleted: list[tuple[str, str | None]] = []
    monkeypatch.setattr(
        "app.services.transactions.store_content",
        lambda **_kwargs: SimpleNamespace(
            provider="s3",
            key="org/transactions/failed-executed-agreement.pdf",
            database_bytes=None,
            malware_scan_status="clean",
            retention_until=datetime(2027, 9, 1, tzinfo=UTC),
        ),
    )
    monkeypatch.setattr(
        "app.services.transactions.delete_content",
        lambda *, provider, key: deleted.append((provider, key)),
    )
    if failure_point == "handoff":

        def fail_handoff(_db: Session, _transaction: Transaction) -> None:
            raise RuntimeError("simulated handoff failure")

        monkeypatch.setattr(
            "app.services.disposition_handoff."
            "ensure_house_disposition_case_for_executed_transaction",
            fail_handoff,
        )
    else:
        monkeypatch.setattr(
            "app.services.disposition_handoff."
            "ensure_house_disposition_case_for_executed_transaction",
            lambda _db, _transaction: None,
        )

        def fail_commit() -> None:
            raise RuntimeError("simulated commit failure")

        monkeypatch.setattr(db_session, "commit", fail_commit)

    with pytest.raises(RuntimeError, match=f"simulated {failure_point} failure"):
        post_external_execution_import(
            client,
            lead_id,
            content=b"%PDF-1.7\nobject storage failure",
        )

    assert deleted == [("s3", "org/transactions/failed-executed-agreement.pdf")]
    assert (
        db_session.scalar(select(Transaction.id).where(Transaction.lead_id == UUID(lead_id)))
        is None
    )


def esign_send_payload() -> dict[str, object]:
    return {
        "subject": "Stonegate purchase agreement",
        "message": "Please review and sign the approved agreement.",
        "recipients": [
            {
                "placeholder_name": "Seller",
                "name": "Jane Seller",
                "email": "jane@example.com",
                "signing_order": 1,
            }
        ],
    }


def external_execution_import_params(**overrides: object) -> dict[str, object]:
    params: dict[str, object] = {
        "file_name": "docusign-completed-purchase-agreement.pdf",
        "seller_name": "Jane Seller",
        "buyer_entity_name": "Stonegate Acquisitions LLC",
        "purchase_price_cents": 17_500_000,
        "assignment_fee_cents": 2_500_000,
        "earnest_money_cents": 100_000,
        "title_company": "Peachtree Closing Law",
        "closing_date": "2026-09-30T17:00:00Z",
        "inspection_period_days": 10,
        "earnest_money_due_at": "2026-09-03T17:00:00Z",
        "due_diligence_deadline": "2026-09-10T17:00:00Z",
        "executed_at": "2026-08-31T16:00:00Z",
        "execution_source": "docusign",
        "external_reference": "docu-envelope-123",
        "notes": "Agreement was completed in DocuSign before Stonegate catch-up entry.",
        "confirm_fully_executed": True,
        "attestation_reason": "Compared every signature and the final terms in DocuSign.",
    }
    params.update(overrides)
    return params


def create_external_import_lead(
    db: Session,
    client: TestClient,
    *,
    asset_class: str = "house",
) -> str:
    bootstrap_foundation(
        db,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    property_type = "vacant_land" if asset_class == "land" else "single_family"
    response = client.post(
        "/api/v1/leads",
        headers=HEADERS,
        json={
            "contact": {"legal_name": "Jane Seller", "contact_type": "seller"},
            "property": {
                "street_address": "123 Peachtree St",
                "city": "Atlanta",
                "state": "GA",
                "postal_code": "30303",
                "property_type": property_type,
            },
            "source": "referral",
            "stage_key": "qualified",
            "asset_class": asset_class,
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def headers_for_transaction_role(
    db: Session,
    *,
    role_key: str,
    email: str,
) -> dict[str, str]:
    organization = db.scalar(select(Organization))
    assert organization is not None
    role = db.scalar(
        select(Role).where(
            Role.organization_id == organization.id,
            Role.key == role_key,
        )
    )
    assert role is not None
    user = User(
        organization_id=organization.id,
        email=email,
        display_name=email,
        external_auth_id=None,
        is_active=True,
        calling_enabled=False,
    )
    db.add(user)
    db.flush()
    db.add(
        RoleAssignment(
            organization_id=organization.id,
            user_id=user.id,
            role_id=role.id,
        )
    )
    db.commit()
    return {"X-Dev-User-Email": email}


def seed_pending_offer_authority(
    db: Session,
    lead_id: str,
) -> tuple[OfferNegotiationPlan, OfferConcession, ApprovalRequest, ApprovalRequest]:
    approved_plan = db.scalar(
        select(OfferNegotiationPlan).where(
            OfferNegotiationPlan.lead_id == UUID(lead_id),
            OfferNegotiationPlan.status == "approved",
        )
    )
    owner = db.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert approved_plan is not None
    assert owner is not None
    plan_approval = ApprovalRequest(
        organization_id=approved_plan.organization_id,
        requested_by_user_id=owner.id,
        assigned_to_user_id=owner.id,
        decided_by_user_id=None,
        request_type="offer_ceiling",
        entity_type="offer_negotiation_plan",
        entity_id=None,
        status="pending",
        title="Pending offer plan",
        summary="Pending authority should retire when signed terms are imported.",
        approval_metadata={"lead_id": lead_id},
    )
    db.add(plan_approval)
    db.flush()
    pending_plan = OfferNegotiationPlan(
        organization_id=approved_plan.organization_id,
        lead_id=approved_plan.lead_id,
        property_id=approved_plan.property_id,
        underwriting_version_id=approved_plan.underwriting_version_id,
        market_analysis_id=approved_plan.market_analysis_id,
        approval_request_id=plan_approval.id,
        created_by_user_id=owner.id,
        status="pending",
        seller_asking_price_cents=approved_plan.seller_asking_price_cents,
        arv_low_cents=approved_plan.arv_low_cents,
        arv_point_cents=approved_plan.arv_point_cents,
        arv_high_cents=approved_plan.arv_high_cents,
        total_rehab_cents=approved_plan.total_rehab_cents,
        disposition_cents=approved_plan.disposition_cents,
        opening_offer_cents=approved_plan.opening_offer_cents,
        target_contract_cents=approved_plan.target_contract_cents,
        stretch_contract_cents=approved_plan.stretch_contract_cents,
        seller_ceiling_cents=approved_plan.seller_ceiling_cents,
        seller_context=None,
        rationale="Pending replacement authority fixture.",
        source_snapshot={"fixture": "pending"},
    )
    db.add(pending_plan)
    db.flush()
    plan_approval.entity_id = pending_plan.id
    concession_approval = ApprovalRequest(
        organization_id=approved_plan.organization_id,
        requested_by_user_id=owner.id,
        assigned_to_user_id=owner.id,
        decided_by_user_id=None,
        request_type="offer_concession",
        entity_type="offer_concession",
        entity_id=None,
        status="pending",
        title="Pending concession",
        summary="Pending concession should retire when signed terms are imported.",
        approval_metadata={"lead_id": lead_id},
    )
    db.add(concession_approval)
    db.flush()
    pending_concession = OfferConcession(
        organization_id=approved_plan.organization_id,
        lead_id=approved_plan.lead_id,
        property_id=approved_plan.property_id,
        offer_negotiation_plan_id=pending_plan.id,
        underwriting_version_id=approved_plan.underwriting_version_id,
        appointment_id=None,
        requested_by_user_id=owner.id,
        approval_request_id=concession_approval.id,
        decided_by_user_id=None,
        presented_by_user_id=None,
        sequence_number=1,
        status="pending",
        authority_basis="manager_approval_required",
        previous_offer_cents=17_000_000,
        proposed_offer_cents=17_500_000,
        concession_delta_cents=500_000,
        seller_counter_cents=17_500_000,
        reason="Seller counter requires approval.",
        seller_exchange="Seller requested a revised price.",
        decision_notes=None,
        decided_at=None,
        presented_at=None,
        source_snapshot={"fixture": "pending"},
    )
    db.add(pending_concession)
    db.flush()
    concession_approval.entity_id = pending_concession.id
    db.commit()
    return pending_plan, pending_concession, plan_approval, concession_approval


def test_canonical_checklist_completion_requires_supporting_evidence(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    _, transaction_id = setup_transaction(db_session, client)
    detail = client.get(f"/api/v1/transactions/{transaction_id}", headers=HEADERS)
    assert detail.status_code == 200, detail.text

    completed_with_evidence: set[str] = set()
    for item in detail.json()["checklist"]:
        item_key = item["item_key"]
        endpoint = f"/api/v1/transactions/{transaction_id}/checklist/{item['id']}"
        if item_key in CANONICAL_EVIDENCE_CHECKLIST_KEYS:
            missing = client.patch(endpoint, headers=HEADERS, json={"status": "complete"})
            assert missing.status_code == 422, missing.text
            assert "supporting evidence note" in missing.json()["detail"]
            payload = {
                "status": "complete",
                "evidence_notes": f"  Verified support for {item_key} in the closing file.  ",
            }
            completed_with_evidence.add(item_key)
        else:
            payload = {"status": "complete"}

        completed = client.patch(endpoint, headers=HEADERS, json=payload)
        assert completed.status_code == 200, completed.text
        saved_item = next(
            saved for saved in completed.json()["checklist"] if saved["id"] == item["id"]
        )
        assert saved_item["status"] == "complete"
        if item_key in CANONICAL_EVIDENCE_CHECKLIST_KEYS:
            assert saved_item["evidence_notes"] == (
                f"Verified support for {item_key} in the closing file."
            )

    assert completed_with_evidence == CANONICAL_EVIDENCE_CHECKLIST_KEYS


def setup_governed_assignment_selection(
    db: Session,
    client: TestClient,
    transaction_id: str,
) -> dict[str, str]:
    # Seed the active compensation/operating model required by the governed
    # disposition case. The returned fixture transaction is intentionally unused.
    setup_case_foundation(db, client)
    case_id = create_approved_disposition_case(client, transaction_id)
    buyers: list[dict[str, str]] = []
    for name, email in (
        ("Ready Cash Buyer LLC", "buyer@example.com"),
        ("Backup Cash Buyer LLC", "backup-buyer@example.com"),
    ):
        created = client.post(
            "/api/v1/buyers",
            headers=HEADERS,
            json={
                "name": name,
                "email": email,
                "buyer_type": "cash_buyer",
                "status": "active",
                "max_purchase_price_cents": 40_000_000,
                "criteria": {
                    "markets": "Atlanta, GA",
                    "property_types": "single_family",
                    "max_price_cents": 40_000_000,
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
        put_verified_buy_box(client, buyer_id)
        proof = upload_received_proof(client, buyer_id, amount_cents=40_000_000)
        verify_proof(client, proof["id"], amount_cents=40_000_000)
        buyers.append({"id": buyer_id, "name": name, "email": email, "proof_id": proof["id"]})

    matched = client.post(
        f"/api/v1/dispositions/cases/{case_id}/matches",
        headers=HEADERS,
    )
    assert matched.status_code == 200, matched.text
    offers: list[dict[str, object]] = []
    for index, buyer in enumerate(buyers):
        offered = client.post(
            f"/api/v1/dispositions/cases/{case_id}/offer-room/offers",
            headers=HEADERS,
            json={
                "buyer_id": buyer["id"],
                "amount_cents": 20_000_000 - index * 100_000,
                "earnest_money_cents": 100_000,
                "deposit_due_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
                "due_diligence_days": 7,
                "contingencies": [],
                "contingencies_confirmed": True,
                "proposed_closing_at": (datetime.now(UTC) + timedelta(days=21)).isoformat(),
                "funding_method": "cash",
                "funding_confidence_basis_points": 9000,
                "proof_document_id": buyer["proof_id"],
                "change_reason": "Governed assignment e-sign completion fixture.",
                "idempotency_key": f"f4-governed-offer-{index + 1}",
            },
        )
        assert offered.status_code == 201, offered.text
        offers.append(
            next(item for item in offered.json()["offers"] if item["buyer_id"] == buyer["id"])
        )
    selected = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
        headers=HEADERS,
        json={
            "primary_offer_id": offers[0]["id"],
            "backup_offer_ids": [offers[1]["id"]],
            "expected_offer_lock_versions": {
                str(item["id"]): item["lock_version"] for item in offers
            },
            "reason": "Approved primary and backup coverage for assignment e-sign completion.",
            "idempotency_key": "f4-governed-assignment-selection",
        },
    )
    assert selected.status_code == 201, selected.text
    transaction = db.get(Transaction, UUID(transaction_id))
    assert transaction is not None
    selected_amount = offers[0]["amount_cents"]
    assert isinstance(selected_amount, int)
    transaction.assignment_fee_cents = selected_amount - transaction.purchase_price_cents
    db.commit()
    return buyers[0]


def test_contract_approval_execution_and_funding_gates(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    handoff_calls: list[UUID] = []
    monkeypatch.setattr(
        "app.services.disposition_handoff.ensure_house_disposition_case_for_executed_transaction",
        lambda _db, transaction: handoff_calls.append(transaction.id),
    )
    client = TestClient(app)
    lead_id, transaction_id = setup_transaction(db_session, client)
    overview = client.get("/api/v1/transactions", headers=HEADERS)
    assert overview.status_code == 200
    assert overview.json()["metrics"]["active"] == 1

    package_response = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages",
        headers=HEADERS,
        json={
            "seller_name": "Jane Seller",
            "buyer_entity_name": "Stonegate Acquisitions LLC",
            "purchase_price_cents": 17000000,
            "earnest_money_cents": 100000,
            "closing_date": "2026-08-14T21:00:00Z",
            "inspection_period_days": 7,
        },
    )
    assert package_response.status_code == 201
    package_id = package_response.json()["id"]
    pending = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/request-approval",
        headers=HEADERS,
    )
    approval_id = pending.json()["approval_request_id"]
    approved = client.patch(
        f"/api/v1/approvals/{approval_id}/decision",
        headers=HEADERS,
        json={"status": "approved", "decision_notes": "Terms verified."},
    )
    assert approved.status_code == 200
    assert (
        client.post(
            f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/mark-sent",
            headers=HEADERS,
        ).status_code
        == 200
    )

    missing_document = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/mark-executed",
        headers=HEADERS,
        json={
            "document_id": "00000000-0000-0000-0000-000000000001",
            "confirm_fully_executed": True,
            "reason": "Verified the complete signed agreement against the package.",
        },
    )
    assert missing_document.status_code == 422
    signed = client.post(
        f"/api/v1/transactions/{transaction_id}/documents?file_name=signed.pdf&document_type=signed_purchase_agreement&title=Signed%20purchase%20agreement&document_status=executed&package_id={package_id}",
        headers={**HEADERS, "Content-Type": "application/pdf"},
        content=b"%PDF signed purchase agreement",
    )
    assert signed.status_code == 201
    executed = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/mark-executed",
        headers=HEADERS,
        json={
            "document_id": signed.json()["id"],
            "confirm_fully_executed": True,
            "reason": "Compared the seller and buyer signatures with the approved package.",
        },
    )
    assert executed.status_code == 200
    assert handoff_calls == [UUID(transaction_id)]
    assert (
        client.get(f"/api/v1/leads/{lead_id}", headers=HEADERS).json()["stage_key"]
        == "under_contract"
    )

    blocked = client.post(
        f"/api/v1/transactions/{transaction_id}/close",
        headers=HEADERS,
        json={"outcome": "funded", "notes": "Closing confirmed."},
    )
    assert blocked.status_code == 422
    detail = client.get(f"/api/v1/transactions/{transaction_id}", headers=HEADERS).json()
    for item in detail["checklist"]:
        completion_payload: dict[str, object] = {"status": "complete"}
        if item["item_key"] in CANONICAL_EVIDENCE_CHECKLIST_KEYS:
            completion_payload["evidence_notes"] = (
                f"Verified {item['item_key']} against the transaction closing file."
            )
        response = client.patch(
            f"/api/v1/transactions/{transaction_id}/checklist/{item['id']}",
            headers=HEADERS,
            json=completion_payload,
        )
        assert response.status_code == 200
    funding = client.post(
        f"/api/v1/transactions/{transaction_id}/documents?file_name=funding.pdf&document_type=funding_confirmation&title=Funding%20confirmation&document_status=evidence",
        headers={**HEADERS, "Content-Type": "application/pdf"},
        content=b"%PDF funding confirmation",
    )
    closed = client.post(
        f"/api/v1/transactions/{transaction_id}/close",
        headers=HEADERS,
        json={"outcome": "funded", "notes": "Funds received by closing attorney."},
    )
    assert funding.status_code == 201
    assert closed.status_code == 200
    assert closed.json()["status"] == "funded"


def test_purchase_package_rejects_arbitrary_price_and_requires_approved_above_ceiling_evidence(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    lead_id, transaction_id = setup_transaction(db_session, client)

    mismatched = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages",
        headers=HEADERS,
        json=purchase_package_payload(17_100_000),
    )
    assert mismatched.status_code == 422
    assert "current transaction purchase price" in mismatched.json()["detail"]

    transaction = db_session.get(Transaction, UUID(transaction_id))
    plan = db_session.scalar(
        select(OfferNegotiationPlan).where(OfferNegotiationPlan.lead_id == UUID(lead_id))
    )
    owner = db_session.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert transaction is not None
    assert plan is not None
    assert owner is not None
    transaction.purchase_price_cents = 18_000_000
    db_session.commit()

    outside_authority = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages",
        headers=HEADERS,
        json=purchase_package_payload(18_000_000),
    )
    assert outside_authority.status_code == 422
    assert "manager-approved concession" in outside_authority.json()["detail"]

    concession_approval = ApprovalRequest(
        organization_id=plan.organization_id,
        requested_by_user_id=owner.id,
        assigned_to_user_id=owner.id,
        decided_by_user_id=owner.id,
        request_type="offer_concession",
        entity_type="offer_concession",
        entity_id=None,
        status="approved",
        title="Approve exact seller exception",
        summary="Approve the exact accepted price above the prior seller ceiling.",
        decision_notes="Manager verified the economics and approved this exact exception.",
        decided_at=datetime.now(UTC),
        approval_metadata={"lead_id": lead_id},
    )
    db_session.add(concession_approval)
    db_session.flush()
    concession = OfferConcession(
        organization_id=plan.organization_id,
        lead_id=plan.lead_id,
        property_id=plan.property_id,
        offer_negotiation_plan_id=plan.id,
        underwriting_version_id=plan.underwriting_version_id,
        appointment_id=None,
        requested_by_user_id=owner.id,
        approval_request_id=concession_approval.id,
        decided_by_user_id=owner.id,
        presented_by_user_id=None,
        sequence_number=1,
        status="approved",
        authority_basis="manager_exception",
        previous_offer_cents=17_000_000,
        proposed_offer_cents=18_000_000,
        concession_delta_cents=1_000_000,
        seller_counter_cents=18_000_000,
        reason="Exact exception approved after updated economics review.",
        seller_exchange="Seller requested the exact approved exception amount.",
        decision_notes="Approved for this exact contract amount.",
        decided_at=datetime.now(UTC),
        presented_at=None,
        source_snapshot={"fixture": True},
    )
    db_session.add(concession)
    db_session.flush()
    concession_approval.entity_id = concession.id
    db_session.commit()

    governed = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages",
        headers=HEADERS,
        json=purchase_package_payload(18_000_000),
    )
    assert governed.status_code == 201, governed.text
    authority = governed.json()["authority_snapshot"]
    assert authority["offer_negotiation_plan_id"] == str(plan.id)
    assert authority["underwriting_version_id"] == str(plan.underwriting_version_id)
    assert authority["purchase_price_cents"] == 18_000_000
    assert authority["governing_concession_id"] == str(concession.id)


def test_purchase_authority_staleness_blocks_approval_send_and_execution(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    lead_id, transaction_id = setup_transaction(db_session, client)
    package = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages",
        headers=HEADERS,
        json=purchase_package_payload(),
    )
    assert package.status_code == 201, package.text
    pending = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package.json()['id']}/request-approval",
        headers=HEADERS,
    )
    assert pending.status_code == 200, pending.text
    add_new_underwriting_version(db_session, lead_id)

    stale_approval = client.patch(
        f"/api/v1/approvals/{pending.json()['approval_request_id']}/decision",
        headers=HEADERS,
        json={"status": "approved", "decision_notes": "Attempt stale approval."},
    )
    assert stale_approval.status_code == 422
    assert "stale" in stale_approval.json()["detail"]

    stored_package = db_session.get(ContractPackage, UUID(package.json()["id"]))
    stored_transaction = db_session.get(Transaction, UUID(transaction_id))
    assert stored_package is not None
    assert stored_transaction is not None
    stored_package.status = "approved"
    stored_transaction.status = "contract_prep"
    db_session.commit()
    stale_send = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package.json()['id']}/mark-sent",
        headers=HEADERS,
    )
    assert stale_send.status_code == 422
    assert "stale" in stale_send.json()["detail"]

    stored_package.status = "sent"
    stored_transaction.status = "sent"
    db_session.commit()
    signed = client.post(
        f"/api/v1/transactions/{transaction_id}/documents?file_name=stale-signed.pdf&document_type=signed_purchase_agreement&title=Stale%20signed%20agreement&document_status=executed&package_id={package.json()['id']}",
        headers={**HEADERS, "Content-Type": "application/pdf"},
        content=b"%PDF stale authority signed agreement",
    )
    assert signed.status_code == 201, signed.text
    stale_execution = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package.json()['id']}/mark-executed",
        headers=HEADERS,
        json={
            "document_id": signed.json()["id"],
            "confirm_fully_executed": True,
            "reason": "Verified signatures, but the authority source is now stale.",
        },
    )
    assert stale_execution.status_code == 422
    assert "stale" in stale_execution.json()["detail"]


def test_manual_execution_requires_exact_completed_document_scan_and_audited_attestation(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    _, transaction_id = setup_transaction(db_session, client)
    package = approve_purchase_package(client, transaction_id)
    package_id = str(package["id"])

    wrong_type = client.post(
        f"/api/v1/transactions/{transaction_id}/documents?file_name=assignment.pdf&document_type=assignment_contract&title=Executed%20assignment&document_status=executed&package_id={package_id}",
        headers={**HEADERS, "Content-Type": "application/pdf"},
        content=b"%PDF wrong execution document type",
    )
    assert wrong_type.status_code == 201, wrong_type.text
    wrong_execution = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/mark-executed",
        headers=HEADERS,
        json={
            "document_id": wrong_type.json()["id"],
            "confirm_fully_executed": True,
            "reason": "Reviewed this document, but it is not the purchase agreement.",
        },
    )
    assert wrong_execution.status_code == 422
    assert "signed purchase agreement" in wrong_execution.json()["detail"]

    incomplete = client.post(
        f"/api/v1/transactions/{transaction_id}/documents?file_name=unsigned.pdf&document_type=signed_purchase_agreement&title=Incomplete%20purchase%20agreement&document_status=final&package_id={package_id}",
        headers={**HEADERS, "Content-Type": "application/pdf"},
        content=b"%PDF incomplete purchase agreement",
    )
    assert incomplete.status_code == 201, incomplete.text
    incomplete_execution = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/mark-executed",
        headers=HEADERS,
        json={
            "document_id": incomplete.json()["id"],
            "confirm_fully_executed": True,
            "reason": "Reviewed the file before recording manual execution.",
        },
    )
    assert incomplete_execution.status_code == 422
    assert "explicitly marked executed" in incomplete_execution.json()["detail"]

    document = db_session.get(TransactionDocument, UUID(incomplete.json()["id"]))
    assert document is not None
    document.status = "executed"
    document.malware_scan_status = "scan_error"
    db_session.commit()
    unsafe_execution = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/mark-executed",
        headers=HEADERS,
        json={
            "document_id": incomplete.json()["id"],
            "confirm_fully_executed": True,
            "reason": "Reviewed all signature pages against the approved agreement.",
        },
    )
    assert unsafe_execution.status_code == 422
    assert "malware scan" in unsafe_execution.json()["detail"]

    document.malware_scan_status = "not_configured"
    db_session.commit()
    executed = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/mark-executed",
        headers=HEADERS,
        json={
            "document_id": incomplete.json()["id"],
            "confirm_fully_executed": True,
            "reason": "Compared every seller and buyer signature with the approved package.",
        },
    )
    assert executed.status_code == 200, executed.text
    audit = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "contract.execution.manual_attest",
            AuditEvent.entity_id == UUID(package_id),
        )
    )
    assert audit is not None
    assert audit.actor_user_id is not None
    assert audit.reason == "Compared every seller and buyer signature with the approved package."
    assert audit.new_value is not None
    assert audit.new_value["document_id"] == incomplete.json()["id"]


def test_contract_template_requires_explicit_approval(
    db_session: Session, api_db_override: None
) -> None:
    client = TestClient(app)
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    created = client.post(
        "/api/v1/transactions/templates?file_name=ga-purchase.pdf&document_type=purchase_agreement&state_code=GA&name=Georgia%20Purchase%20Agreement",
        headers={**HEADERS, "Content-Type": "application/pdf"},
        content=b"%PDF attorney reviewed template",
    )
    assert created.status_code == 201
    assert created.json()["status"] == "draft"
    approved = client.post(
        f"/api/v1/transactions/templates/{created.json()['id']}/approve", headers=HEADERS
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"


def test_signwell_connection_registers_and_persists_verified_webhook(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("ESIGN_PROVIDER", "signwell")
    monkeypatch.setenv("ESIGN_API_KEY", "test-signwell-api-key")
    monkeypatch.setenv(
        "ESIGN_WEBHOOK_CALLBACK_URL",
        "https://api.example.com/api/v1/webhooks/esign/signwell",
    )
    monkeypatch.delenv("ESIGN_SIGNWELL_WEBHOOK_ID", raising=False)
    get_settings.cache_clear()
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )

    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        del kwargs
        request = httpx.Request("GET", url)
        if url.endswith("/me"):
            return httpx.Response(
                200,
                request=request,
                json={"id": "account-1", "name": "Stonegate", "email": OWNER_EMAIL},
            )
        if url.endswith("/hooks"):
            return httpx.Response(200, request=request, json=[])
        raise AssertionError(f"Unexpected SignWell GET {url}")

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        assert url.endswith("/hooks")
        assert kwargs["json"] == {
            "callback_url": "https://api.example.com/api/v1/webhooks/esign/signwell"
        }
        return httpx.Response(
            201,
            request=httpx.Request("POST", url),
            json={
                "id": "stonegate-webhook-id",
                "callback_url": "https://api.example.com/api/v1/webhooks/esign/signwell",
            },
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "post", fake_post)
    client = TestClient(app)
    connected = client.post(
        "/api/v1/transactions/integrations/signwell/connect",
        headers=HEADERS,
    )
    assert connected.status_code == 200, connected.text
    assert connected.json()["account_email"] == OWNER_EMAIL
    assert connected.json()["webhook_created"] is True

    status_response = client.get("/api/v1/transactions/integrations/f4", headers=HEADERS)
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["esign_configured"] is True
    assert status_payload["esign_webhook_connected"] is True
    assert status_payload["esign_account_email"] == OWNER_EMAIL

    event_type = "document_sent"
    event_time = 1786698000
    event = {
        "event": {
            "hash": hmac.new(
                b"stonegate-webhook-id",
                f"{event_type}@{event_time}".encode(),
                sha256,
            ).hexdigest(),
            "time": event_time,
            "type": event_type,
        },
        "data": {"object": {"id": str(uuid4()), "status": "sent"}},
    }
    webhook = client.post("/api/v1/webhooks/esign/signwell", json=event)
    assert webhook.status_code == 200, webhook.text
    assert webhook.json() == {"received": True, "matched": False}
    get_settings.cache_clear()


def test_transaction_document_facts_preserve_page_evidence_and_reject_duplicates(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    _, transaction_id = setup_transaction(db_session, client)
    path = (
        f"/api/v1/transactions/{transaction_id}/documents"
        "?file_name=contract.pdf"
        "&document_type=signed_purchase_agreement"
        "&title=Executed%20agreement"
        "&document_status=executed"
    )
    content = b"%PDF unique executed agreement"
    uploaded = client.post(
        path,
        headers={**HEADERS, "Content-Type": "application/pdf"},
        content=content,
    )
    assert uploaded.status_code == 201, uploaded.text
    duplicate = client.post(
        path,
        headers={**HEADERS, "Content-Type": "application/pdf"},
        content=content,
    )
    assert duplicate.status_code == 422
    assert "already stored" in duplicate.json()["detail"]

    fact = client.post(
        (f"/api/v1/transactions/{transaction_id}/documents/{uploaded.json()['id']}/facts"),
        headers=HEADERS,
        json={
            "field_key": "Closing Date",
            "value_text": "August 14, 2026",
            "source_page": 4,
            "source_excerpt": "Closing shall occur on August 14, 2026.",
        },
    )
    assert fact.status_code == 201, fact.text
    assert fact.json()["field_key"] == "closing_date"
    assert fact.json()["status"] == "confirmed"
    assert fact.json()["source_page"] == 4

    detail = client.get(
        f"/api/v1/transactions/{transaction_id}",
        headers=HEADERS,
    )
    stored_document = next(
        item for item in detail.json()["documents"] if item["id"] == uploaded.json()["id"]
    )
    assert stored_document["facts"][0]["value_text"] == "August 14, 2026"
    assert stored_document["facts"][0]["reviewed_by_name"] == "Owner"


def test_signwell_send_persists_a_draft_before_notifying_signers(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("ESIGN_PROVIDER", "signwell")
    monkeypatch.setenv("ESIGN_API_KEY", "test-signwell-api-key")
    monkeypatch.setenv("ESIGN_SIGNWELL_WEBHOOK_ID", "test-signwell-webhook-id")
    monkeypatch.setenv("ESIGN_TEST_MODE", "true")
    get_settings.cache_clear()
    client = TestClient(app)
    _, transaction_id = setup_transaction(db_session, client)
    package = approve_purchase_package(client, transaction_id)
    package_id = UUID(str(package["id"]))
    provider_calls: list[str] = []

    def create_draft(_client: object, payload: dict[str, object]) -> dict[str, object]:
        provider_calls.append("create")
        assert payload["draft"] is True
        db_session.expire_all()
        reserved = db_session.scalar(
            select(EsignEnvelope).where(EsignEnvelope.contract_package_id == package_id)
        )
        stored_package = db_session.get(ContractPackage, package_id)
        assert reserved is not None
        assert reserved.status == "creating_draft"
        assert reserved.provider_document_id.startswith("intent-")
        assert stored_package is not None and stored_package.status == "sending"
        return {
            "id": "signwell-draft-1",
            "status": "draft",
            "recipients": [
                {"id": "seller-1", "email": "jane@example.com"},
                {"id": "stonegate-1", "email": OWNER_EMAIL},
            ],
        }

    def send_draft(_client: object, document_id: str) -> dict[str, object]:
        provider_calls.append("send")
        assert document_id == "signwell-draft-1"
        db_session.expire_all()
        durable = db_session.scalar(
            select(EsignEnvelope).where(EsignEnvelope.contract_package_id == package_id)
        )
        assert durable is not None
        assert durable.provider_document_id == document_id
        assert durable.status == "sending"
        assert durable.provider_payload["source_document_id"]
        return {
            "id": document_id,
            "status": "sent",
            "recipients": [
                {"id": "seller-1", "email": "jane@example.com"},
                {"id": "stonegate-1", "email": OWNER_EMAIL},
            ],
        }

    monkeypatch.setattr("app.services.esign.SignWellClient.create_document", create_draft)
    monkeypatch.setattr("app.services.esign.SignWellClient.send_document", send_draft)

    sent = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/esign",
        headers=HEADERS,
        json=esign_send_payload(),
    )
    duplicate = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/esign",
        headers=HEADERS,
        json=esign_send_payload(),
    )

    assert sent.status_code == 201, sent.text
    assert sent.json()["status"] == "sent"
    assert duplicate.status_code == 422
    assert provider_calls == ["create", "send"]
    db_session.expire_all()
    event = db_session.scalar(
        select(TransactionEvent).where(
            TransactionEvent.transaction_id == UUID(transaction_id),
            TransactionEvent.event_type == "esign.sent",
        )
    )
    assert event is not None
    assert event.details["source_document_id"]
    get_settings.cache_clear()


def test_signwell_ambiguous_draft_creation_blocks_automatic_retry(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("ESIGN_PROVIDER", "signwell")
    monkeypatch.setenv("ESIGN_API_KEY", "test-signwell-api-key")
    monkeypatch.setenv("ESIGN_SIGNWELL_WEBHOOK_ID", "test-signwell-webhook-id")
    monkeypatch.setenv("ESIGN_TEST_MODE", "true")
    get_settings.cache_clear()
    client = TestClient(app)
    _, transaction_id = setup_transaction(db_session, client)
    package = approve_purchase_package(client, transaction_id)
    package_id = UUID(str(package["id"]))
    create_attempts = 0

    def ambiguous_create(_client: object, _payload: dict[str, object]) -> dict[str, object]:
        nonlocal create_attempts
        create_attempts += 1
        raise httpx.ReadTimeout("provider outcome unknown")

    monkeypatch.setattr("app.services.esign.SignWellClient.create_document", ambiguous_create)

    first = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/esign",
        headers=HEADERS,
        json=esign_send_payload(),
    )
    retry = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/esign",
        headers=HEADERS,
        json=esign_send_payload(),
    )

    assert first.status_code == 422
    assert "No automatic retry" in first.json()["detail"]
    assert retry.status_code == 422
    assert "outcome is uncertain" in retry.json()["detail"]
    assert create_attempts == 1
    db_session.expire_all()
    envelope = db_session.scalar(
        select(EsignEnvelope).where(EsignEnvelope.contract_package_id == package_id)
    )
    stored_package = db_session.get(ContractPackage, package_id)
    assert envelope is not None and envelope.status == "draft_creation_uncertain"
    assert stored_package is not None and stored_package.status == "sending"
    get_settings.cache_clear()


def test_signwell_provider_draft_can_be_verified_and_attached_after_precommit_crash(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("ESIGN_PROVIDER", "signwell")
    monkeypatch.setenv("ESIGN_API_KEY", "test-signwell-api-key")
    monkeypatch.setenv("ESIGN_SIGNWELL_WEBHOOK_ID", "test-signwell-webhook-id")
    monkeypatch.setenv("ESIGN_TEST_MODE", "true")
    get_settings.cache_clear()
    client = TestClient(app, raise_server_exceptions=False)
    _, transaction_id = setup_transaction(db_session, client)
    package = approve_purchase_package(client, transaction_id)
    package_id = UUID(str(package["id"]))
    original_update = esign_service.update_esign_recipient_provider_data

    monkeypatch.setattr(
        "app.services.esign.SignWellClient.create_document",
        lambda _client, _payload: {
            "id": "signwell-orphaned-draft",
            "status": "draft",
            "recipients": [
                {"id": "seller-1", "email": "jane@example.com"},
                {"id": "stonegate-1", "email": OWNER_EMAIL},
            ],
        },
    )

    def crash_before_provider_id_commit(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("simulated crash before provider draft persistence")

    monkeypatch.setattr(
        esign_service,
        "update_esign_recipient_provider_data",
        crash_before_provider_id_commit,
    )
    interrupted = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/esign",
        headers=HEADERS,
        json=esign_send_payload(),
    )

    assert interrupted.status_code == 500
    db_session.rollback()
    db_session.expire_all()
    envelope = db_session.scalar(
        select(EsignEnvelope).where(EsignEnvelope.contract_package_id == package_id)
    )
    assert envelope is not None
    assert envelope.status == "creating_draft"
    assert envelope.provider_document_id.startswith("intent-")

    monkeypatch.setattr(esign_service, "update_esign_recipient_provider_data", original_update)
    monkeypatch.setattr(
        "app.services.esign.SignWellClient.get_document",
        lambda _client, document_id: {
            "id": document_id,
            "status": "draft",
            "test_mode": True,
            "metadata": {
                "stonegate_transaction_id": transaction_id,
                "stonegate_contract_package_id": str(package_id),
            },
            "recipients": [
                {"id": "seller-1", "email": "jane@example.com"},
                {"id": "stonegate-1", "email": OWNER_EMAIL},
            ],
        },
    )
    recovered = client.post(
        f"/api/v1/transactions/{transaction_id}/esign/{envelope.id}/attach-draft",
        headers=HEADERS,
        json={
            "provider_document_id": "signwell-orphaned-draft",
            "confirm_provider_draft_verified": True,
            "reason": "Verified this unsent draft in the SignWell account.",
        },
    )

    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["status"] == "draft"
    assert recovered.json()["provider_document_id"] == "signwell-orphaned-draft"
    db_session.expire_all()
    recovery_event = db_session.scalar(
        select(TransactionEvent).where(
            TransactionEvent.transaction_id == UUID(transaction_id),
            TransactionEvent.event_type == "esign.draft_recovered",
        )
    )
    assert recovery_event is not None
    assert recovery_event.details["operator_attested"] is True
    get_settings.cache_clear()


def test_signwell_draft_recovery_rejects_mismatched_provider_metadata(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("ESIGN_PROVIDER", "signwell")
    monkeypatch.setenv("ESIGN_API_KEY", "test-signwell-api-key")
    monkeypatch.setenv("ESIGN_SIGNWELL_WEBHOOK_ID", "test-signwell-webhook-id")
    monkeypatch.setenv("ESIGN_TEST_MODE", "true")
    get_settings.cache_clear()
    client = TestClient(app)
    _, transaction_id = setup_transaction(db_session, client)
    package = approve_purchase_package(client, transaction_id)
    package_id = UUID(str(package["id"]))
    monkeypatch.setattr(
        "app.services.esign.SignWellClient.create_document",
        lambda _client, _payload: (_ for _ in ()).throw(httpx.ReadTimeout("unknown")),
    )
    failed = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/esign",
        headers=HEADERS,
        json=esign_send_payload(),
    )
    assert failed.status_code == 422
    db_session.expire_all()
    envelope = db_session.scalar(
        select(EsignEnvelope).where(EsignEnvelope.contract_package_id == package_id)
    )
    assert envelope is not None
    monkeypatch.setattr(
        "app.services.esign.SignWellClient.get_document",
        lambda _client, document_id: {
            "id": document_id,
            "status": "draft",
            "test_mode": True,
            "metadata": {
                "stonegate_transaction_id": str(uuid4()),
                "stonegate_contract_package_id": str(package_id),
            },
            "recipients": [
                {"id": "seller-1", "email": "jane@example.com"},
                {"id": "stonegate-1", "email": OWNER_EMAIL},
            ],
        },
    )
    rejected = client.post(
        f"/api/v1/transactions/{transaction_id}/esign/{envelope.id}/attach-draft",
        headers=HEADERS,
        json={
            "provider_document_id": "wrong-signwell-draft",
            "confirm_provider_draft_verified": True,
            "reason": "Attempted recovery with mismatched provider metadata.",
        },
    )

    assert rejected.status_code == 422
    assert "metadata does not match" in rejected.json()["detail"]
    db_session.expire_all()
    stored = db_session.get(EsignEnvelope, envelope.id)
    assert stored is not None and stored.status == "draft_creation_uncertain"
    assert stored.provider_document_id.startswith("intent-")
    get_settings.cache_clear()


def test_signwell_uncertain_empty_intent_can_be_audited_and_released(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("ESIGN_PROVIDER", "signwell")
    monkeypatch.setenv("ESIGN_API_KEY", "test-signwell-api-key")
    monkeypatch.setenv("ESIGN_SIGNWELL_WEBHOOK_ID", "test-signwell-webhook-id")
    monkeypatch.setenv("ESIGN_TEST_MODE", "true")
    get_settings.cache_clear()
    client = TestClient(app)
    lead_id, transaction_id = setup_transaction(db_session, client)
    package = approve_purchase_package(client, transaction_id)
    package_id = UUID(str(package["id"]))
    monkeypatch.setattr(
        "app.services.esign.SignWellClient.create_document",
        lambda _client, _payload: (_ for _ in ()).throw(httpx.ReadTimeout("unknown")),
    )
    failed = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/esign",
        headers=HEADERS,
        json=esign_send_payload(),
    )
    assert failed.status_code == 422
    db_session.expire_all()
    envelope = db_session.scalar(
        select(EsignEnvelope).where(EsignEnvelope.contract_package_id == package_id)
    )
    assert envelope is not None
    envelope.created_at = datetime.now(UTC) - timedelta(minutes=10)
    db_session.commit()

    released = client.post(
        f"/api/v1/transactions/{transaction_id}/esign/{envelope.id}/abandon-draft-intent",
        headers=HEADERS,
        json={
            "confirm_no_provider_document_exists": True,
            "reason": "Verified the Stonegate package in SignWell and found no document.",
        },
    )

    assert released.status_code == 200, released.text
    assert released.json()["status"] == "error"
    db_session.expire_all()
    stored_package = db_session.get(ContractPackage, package_id)
    assert stored_package is not None and stored_package.status == "approved"
    lock_offer_authority_for_mutation(
        db_session,
        stored_package.organization_id,
        UUID(lead_id),
    )
    audit = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_id == envelope.id,
            AuditEvent.action == "esign.intent.abandon",
        )
    )
    assert audit is not None
    get_settings.cache_clear()


def test_signwell_saved_draft_survives_crash_reconcile_and_resume(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("ESIGN_PROVIDER", "signwell")
    monkeypatch.setenv("ESIGN_API_KEY", "test-signwell-api-key")
    monkeypatch.setenv("ESIGN_SIGNWELL_WEBHOOK_ID", "test-signwell-webhook-id")
    monkeypatch.setenv("ESIGN_TEST_MODE", "true")
    get_settings.cache_clear()
    client = TestClient(app, raise_server_exceptions=False)
    _, transaction_id = setup_transaction(db_session, client)
    package = approve_purchase_package(client, transaction_id)
    package_id = UUID(str(package["id"]))
    provider_calls: list[str] = []
    original_send_saved_draft = esign_service.send_saved_esign_draft

    def create_draft(_client: object, payload: dict[str, object]) -> dict[str, object]:
        provider_calls.append("create")
        assert payload["draft"] is True
        return {
            "id": "signwell-draft-crash-window",
            "status": "draft",
            "recipients": [
                {"id": "seller-1", "email": "jane@example.com"},
                {"id": "stonegate-1", "email": OWNER_EMAIL},
            ],
        }

    def crash_after_draft(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("simulated process crash after durable draft commit")

    monkeypatch.setattr("app.services.esign.SignWellClient.create_document", create_draft)
    monkeypatch.setattr(esign_service, "send_saved_esign_draft", crash_after_draft)

    interrupted = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/esign",
        headers=HEADERS,
        json=esign_send_payload(),
    )
    assert interrupted.status_code == 500
    db_session.expire_all()
    envelope = db_session.scalar(
        select(EsignEnvelope).where(EsignEnvelope.contract_package_id == package_id)
    )
    assert envelope is not None
    assert envelope.status == "draft"
    assert envelope.provider_document_id == "signwell-draft-crash-window"

    def get_draft(_client: object, document_id: str) -> dict[str, object]:
        assert document_id == "signwell-draft-crash-window"
        return {"id": document_id, "status": "draft"}

    def send_draft(_client: object, document_id: str) -> dict[str, object]:
        provider_calls.append("send")
        return {"id": document_id, "status": "sent"}

    monkeypatch.setattr(esign_service, "send_saved_esign_draft", original_send_saved_draft)
    monkeypatch.setattr("app.services.esign.SignWellClient.get_document", get_draft)
    monkeypatch.setattr("app.services.esign.SignWellClient.send_document", send_draft)

    reconciled = client.post(
        f"/api/v1/transactions/{transaction_id}/esign/{envelope.id}/reconcile",
        headers=HEADERS,
    )
    resumed = client.post(
        f"/api/v1/transactions/{transaction_id}/esign/{envelope.id}/resume-draft",
        headers=HEADERS,
    )

    assert reconciled.status_code == 200, reconciled.text
    assert reconciled.json()["status"] == "draft"
    db_session.expire_all()
    reconciled_envelope = db_session.get(EsignEnvelope, envelope.id)
    assert reconciled_envelope is not None
    assert reconciled_envelope.provider_payload["source_document_id"]
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["status"] == "sent"
    assert provider_calls == ["create", "send"]
    get_settings.cache_clear()


def test_signwell_reconcile_finishes_local_send_after_response_crash(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("ESIGN_PROVIDER", "signwell")
    monkeypatch.setenv("ESIGN_API_KEY", "test-signwell-api-key")
    monkeypatch.setenv("ESIGN_SIGNWELL_WEBHOOK_ID", "test-signwell-webhook-id")
    monkeypatch.setenv("ESIGN_TEST_MODE", "true")
    get_settings.cache_clear()
    client = TestClient(app, raise_server_exceptions=False)
    _, transaction_id = setup_transaction(db_session, client)
    package = approve_purchase_package(client, transaction_id)
    package_id = UUID(str(package["id"]))

    monkeypatch.setattr(
        "app.services.esign.SignWellClient.create_document",
        lambda _client, _payload: {
            "id": "signwell-accepted-before-crash",
            "status": "draft",
        },
    )
    monkeypatch.setattr(
        "app.services.esign.SignWellClient.send_document",
        lambda _client, document_id: {"id": document_id, "status": "sent"},
    )
    original_finalize = esign_service.finalize_local_esign_send
    finalize_calls = 0

    def crash_first_finalize(*args: object, **kwargs: object) -> None:
        nonlocal finalize_calls
        finalize_calls += 1
        if finalize_calls == 1:
            raise RuntimeError("simulated crash before local provider-send commit")
        original_finalize(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(esign_service, "finalize_local_esign_send", crash_first_finalize)
    interrupted = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/esign",
        headers=HEADERS,
        json=esign_send_payload(),
    )
    assert interrupted.status_code == 500
    db_session.rollback()
    db_session.expire_all()
    envelope = db_session.scalar(
        select(EsignEnvelope).where(EsignEnvelope.contract_package_id == package_id)
    )
    assert envelope is not None and envelope.status == "sending"
    assert db_session.get(ContractPackage, package_id).status == "sending"  # type: ignore[union-attr]

    monkeypatch.setattr(esign_service, "finalize_local_esign_send", original_finalize)
    monkeypatch.setattr(
        "app.services.esign.SignWellClient.get_document",
        lambda _client, document_id: {"id": document_id, "status": "sent"},
    )
    reconciled = client.post(
        f"/api/v1/transactions/{transaction_id}/esign/{envelope.id}/reconcile",
        headers=HEADERS,
    )

    assert reconciled.status_code == 200, reconciled.text
    assert reconciled.json()["status"] == "sent"
    db_session.expire_all()
    assert db_session.get(ContractPackage, package_id).status == "sent"  # type: ignore[union-attr]
    assert db_session.get(Transaction, UUID(transaction_id)).status == "sent"  # type: ignore[union-attr]
    assert (
        len(
            list(
                db_session.scalars(
                    select(TransactionEvent).where(
                        TransactionEvent.transaction_id == UUID(transaction_id),
                        TransactionEvent.event_type == "esign.sent",
                    )
                )
            )
        )
        == 1
    )
    get_settings.cache_clear()


def test_signwell_fast_terminal_webhook_and_timeout_cannot_regress_completion(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("ESIGN_PROVIDER", "signwell")
    monkeypatch.setenv("ESIGN_API_KEY", "test-signwell-api-key")
    monkeypatch.setenv("ESIGN_SIGNWELL_WEBHOOK_ID", "test-signwell-webhook-id")
    monkeypatch.setenv("ESIGN_TEST_MODE", "true")
    get_settings.cache_clear()
    client = TestClient(app)
    _, transaction_id = setup_transaction(db_session, client)
    package = approve_purchase_package(client, transaction_id)
    package_id = UUID(str(package["id"]))
    monkeypatch.setattr(
        "app.services.esign.SignWellClient.create_document",
        lambda _client, _payload: {
            "id": "signwell-fast-completion",
            "status": "draft",
            "recipients": [
                {"id": "seller-1", "email": "jane@example.com"},
                {"id": "stonegate-1", "email": OWNER_EMAIL},
            ],
        },
    )

    def complete_before_send_returns(_client: object, document_id: str) -> dict[str, object]:
        db_session.expire_all()
        envelope = db_session.scalar(
            select(EsignEnvelope).where(EsignEnvelope.provider_document_id == document_id)
        )
        stored_package = db_session.get(ContractPackage, package_id)
        transaction = db_session.get(Transaction, UUID(transaction_id))
        assert envelope is not None and stored_package is not None and transaction is not None
        esign_service.finalize_local_esign_send(
            db_session,
            envelope,
            occurred_at=datetime.now(UTC),
            actor_user_id=None,
        )
        envelope.status = "completed"
        envelope.provider_payload = {
            **envelope.provider_payload,
            "phase": "completed",
            "status": "completed",
        }
        stored_package.status = "executed"
        transaction.status = "executed"
        for recipient in db_session.scalars(
            select(EsignRecipient).where(EsignRecipient.esign_envelope_id == envelope.id)
        ).all():
            recipient.status = "signed"
        db_session.commit()
        raise httpx.ReadTimeout("client timed out after the completion webhook won the race")

    monkeypatch.setattr(
        "app.services.esign.SignWellClient.send_document",
        complete_before_send_returns,
    )
    sent = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/esign",
        headers=HEADERS,
        json=esign_send_payload(),
    )

    assert sent.status_code == 201, sent.text
    assert sent.json()["status"] == "completed"
    assert all(item["status"] == "signed" for item in sent.json()["recipients"])
    db_session.expire_all()
    assert db_session.get(ContractPackage, package_id).status == "executed"  # type: ignore[union-attr]
    assert db_session.get(Transaction, UUID(transaction_id)).status == "executed"  # type: ignore[union-attr]
    stored_envelope = db_session.scalar(
        select(EsignEnvelope).where(EsignEnvelope.contract_package_id == package_id)
    )
    assert stored_envelope is not None
    assert stored_envelope.provider_payload["phase"] == "completed"
    assert (
        len(
            list(
                db_session.scalars(
                    select(TransactionEvent).where(
                        TransactionEvent.transaction_id == UUID(transaction_id),
                        TransactionEvent.event_type == "esign.sent",
                    )
                )
            )
        )
        == 1
    )
    get_settings.cache_clear()


def test_signwell_fast_terminal_webhook_and_success_response_preserve_later_authority(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("ESIGN_PROVIDER", "signwell")
    monkeypatch.setenv("ESIGN_API_KEY", "test-signwell-api-key")
    monkeypatch.setenv("ESIGN_SIGNWELL_WEBHOOK_ID", "test-signwell-webhook-id")
    monkeypatch.setenv("ESIGN_TEST_MODE", "true")
    get_settings.cache_clear()
    client = TestClient(app)
    lead_id, transaction_id = setup_transaction(db_session, client)
    package = approve_purchase_package(client, transaction_id)
    package_id = UUID(str(package["id"]))
    monkeypatch.setattr(
        "app.services.esign.SignWellClient.create_document",
        lambda _client, _payload: {
            "id": "signwell-fast-success",
            "status": "draft",
            "recipients": [
                {"id": "seller-1", "email": "jane@example.com"},
                {"id": "stonegate-1", "email": OWNER_EMAIL},
            ],
        },
    )

    def complete_and_change_authority_before_response(
        _client: object,
        document_id: str,
    ) -> dict[str, object]:
        db_session.expire_all()
        envelope = db_session.scalar(
            select(EsignEnvelope).where(EsignEnvelope.provider_document_id == document_id)
        )
        stored_package = db_session.get(ContractPackage, package_id)
        transaction = db_session.get(Transaction, UUID(transaction_id))
        assert envelope is not None and stored_package is not None and transaction is not None
        esign_service.finalize_local_esign_send(
            db_session,
            envelope,
            occurred_at=datetime.now(UTC),
            actor_user_id=None,
        )
        envelope.status = "completed"
        envelope.provider_payload = {
            **envelope.provider_payload,
            "phase": "completed",
            "status": "completed",
        }
        stored_package.status = "executed"
        transaction.status = "executed"
        for recipient in db_session.scalars(
            select(EsignRecipient).where(EsignRecipient.esign_envelope_id == envelope.id)
        ).all():
            recipient.status = "signed"
        db_session.commit()
        add_new_underwriting_version(db_session, lead_id)
        return {
            "id": document_id,
            "status": "sent",
            "recipients": [
                {"id": "seller-1", "email": "jane@example.com"},
                {"id": "stonegate-1", "email": OWNER_EMAIL},
            ],
        }

    monkeypatch.setattr(
        "app.services.esign.SignWellClient.send_document",
        complete_and_change_authority_before_response,
    )
    sent = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/esign",
        headers=HEADERS,
        json=esign_send_payload(),
    )

    assert sent.status_code == 201, sent.text
    assert sent.json()["status"] == "completed"
    assert all(item["status"] == "signed" for item in sent.json()["recipients"])
    db_session.expire_all()
    stored_envelope = db_session.scalar(
        select(EsignEnvelope).where(EsignEnvelope.contract_package_id == package_id)
    )
    assert stored_envelope is not None
    assert stored_envelope.status == "completed"
    assert stored_envelope.provider_payload["phase"] == "completed"
    assert stored_envelope.provider_payload["send_response"]["status"] == "sent"
    assert db_session.get(ContractPackage, package_id).status == "executed"  # type: ignore[union-attr]
    assert db_session.get(Transaction, UUID(transaction_id)).status == "executed"  # type: ignore[union-attr]
    get_settings.cache_clear()


def test_signwell_terminal_failure_releases_once_without_resetting_a_later_delivery(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("ESIGN_PROVIDER", "signwell")
    monkeypatch.setenv("ESIGN_API_KEY", "test-signwell-api-key")
    monkeypatch.setenv("ESIGN_SIGNWELL_WEBHOOK_ID", "test-signwell-webhook-id")
    monkeypatch.setenv("ESIGN_TEST_MODE", "true")
    get_settings.cache_clear()
    client = TestClient(app)
    _, transaction_id = setup_transaction(db_session, client)
    package = approve_purchase_package(client, transaction_id)
    package_id = UUID(str(package["id"]))
    monkeypatch.setattr(
        "app.services.esign.SignWellClient.create_document",
        lambda _client, _payload: {
            "id": "signwell-terminal-release",
            "status": "draft",
            "recipients": [
                {"id": "seller-1", "email": "jane@example.com"},
                {"id": "stonegate-1", "email": OWNER_EMAIL},
            ],
        },
    )
    monkeypatch.setattr(
        "app.services.esign.SignWellClient.send_document",
        lambda _client, document_id: {"id": document_id, "status": "sent"},
    )
    sent = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/esign",
        headers=HEADERS,
        json=esign_send_payload(),
    )
    assert sent.status_code == 201, sent.text
    first_time = int(datetime.now(UTC).timestamp())
    verification = esign_service.SignWellWebhookVerification(
        organization_id=UUID(str(db_session.get(ContractPackage, package_id).organization_id)),  # type: ignore[union-attr]
        source="internal",
    )
    first_event = {
        "event": {
            "hash": "declined-first",
            "time": first_time,
            "type": "document_declined",
        },
        "data": {"object": {"id": "signwell-terminal-release", "status": "declined"}},
    }
    assert esign_service.process_signwell_event(
        db_session,
        first_event,
        get_settings(),
        verification=verification,
    )
    db_session.expire_all()
    assert db_session.get(ContractPackage, package_id).status == "approved"  # type: ignore[union-attr]

    resent = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/mark-sent",
        headers=HEADERS,
    )
    assert resent.status_code == 200, resent.text
    repeated_event = {
        "event": {
            "hash": "declined-reconciled-later",
            "time": first_time + 30,
            "type": "document_declined",
        },
        "data": {"object": {"id": "signwell-terminal-release", "status": "declined"}},
    }
    assert esign_service.process_signwell_event(
        db_session,
        repeated_event,
        get_settings(),
        verification=verification,
    )
    db_session.expire_all()
    assert db_session.get(ContractPackage, package_id).status == "sent"  # type: ignore[union-attr]
    closed_events = list(
        db_session.scalars(
            select(TransactionEvent).where(
                TransactionEvent.transaction_id == UUID(transaction_id),
                TransactionEvent.event_type == "esign.delivery_closed",
            )
        )
    )
    assert len(closed_events) == 1
    get_settings.cache_clear()


def test_signwell_document_error_releases_an_uncertain_send_reservation(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("ESIGN_PROVIDER", "signwell")
    monkeypatch.setenv("ESIGN_API_KEY", "test-signwell-api-key")
    monkeypatch.setenv("ESIGN_SIGNWELL_WEBHOOK_ID", "test-signwell-webhook-id")
    monkeypatch.setenv("ESIGN_TEST_MODE", "true")
    get_settings.cache_clear()
    client = TestClient(app)
    _, transaction_id = setup_transaction(db_session, client)
    package = approve_purchase_package(client, transaction_id)
    package_id = UUID(str(package["id"]))
    monkeypatch.setattr(
        "app.services.esign.SignWellClient.create_document",
        lambda _client, _payload: {
            "id": "signwell-provider-error",
            "status": "draft",
        },
    )
    monkeypatch.setattr(
        "app.services.esign.SignWellClient.send_document",
        lambda _client, _document_id: (_ for _ in ()).throw(httpx.ReadTimeout("uncertain send")),
    )
    failed = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/esign",
        headers=HEADERS,
        json=esign_send_payload(),
    )
    assert failed.status_code == 422
    db_session.expire_all()
    envelope = db_session.scalar(
        select(EsignEnvelope).where(EsignEnvelope.contract_package_id == package_id)
    )
    stored_package = db_session.get(ContractPackage, package_id)
    assert envelope is not None and envelope.status == "send_uncertain"
    assert stored_package is not None and stored_package.status == "sending"
    monkeypatch.setattr(
        "app.services.esign.SignWellClient.get_document",
        lambda _client, document_id: {"id": document_id, "status": "error"},
    )
    reconciled = client.post(
        f"/api/v1/transactions/{transaction_id}/esign/{envelope.id}/reconcile",
        headers=HEADERS,
    )
    assert reconciled.status_code == 200, reconciled.text
    assert reconciled.json()["status"] == "error"
    db_session.expire_all()
    assert db_session.get(EsignEnvelope, envelope.id).status == "error"  # type: ignore[union-attr]
    assert db_session.get(ContractPackage, package_id).status == "approved"  # type: ignore[union-attr]
    get_settings.cache_clear()


def test_signwell_delayed_completion_advances_after_newer_reconcile_timestamp(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("ESIGN_PROVIDER", "signwell")
    monkeypatch.setenv("ESIGN_API_KEY", "test-signwell-api-key")
    monkeypatch.setenv("ESIGN_SIGNWELL_WEBHOOK_ID", "test-signwell-webhook-id")
    monkeypatch.setenv("ESIGN_TEST_MODE", "true")
    get_settings.cache_clear()
    client = TestClient(app)
    _, transaction_id = setup_transaction(db_session, client)
    package = approve_purchase_package(client, transaction_id)
    package_id = UUID(str(package["id"]))
    monkeypatch.setattr(
        "app.services.esign.SignWellClient.create_document",
        lambda _client, _payload: {
            "id": "signwell-delayed-completion",
            "status": "draft",
        },
    )
    monkeypatch.setattr(
        "app.services.esign.SignWellClient.send_document",
        lambda _client, document_id: {"id": document_id, "status": "sent"},
    )
    sent = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/esign",
        headers=HEADERS,
        json=esign_send_payload(),
    )
    assert sent.status_code == 201, sent.text
    envelope_id = UUID(str(sent.json()["id"]))
    monkeypatch.setattr(
        "app.services.esign.SignWellClient.get_document",
        lambda _client, document_id: {"id": document_id, "status": "sent"},
    )
    reconciled = client.post(
        f"/api/v1/transactions/{transaction_id}/esign/{envelope_id}/reconcile",
        headers=HEADERS,
    )
    assert reconciled.status_code == 200, reconciled.text
    db_session.expire_all()
    envelope = db_session.get(EsignEnvelope, envelope_id)
    assert envelope is not None and envelope.last_provider_event_at is not None
    delayed_time = int((datetime.now(UTC) - timedelta(minutes=2)).timestamp())
    monkeypatch.setattr(
        "app.services.esign.SignWellClient.completed_pdf",
        lambda _client, _document_id: b"%PDF delayed completed agreement",
    )
    completed = esign_service.process_signwell_event(
        db_session,
        {
            "event": {
                "hash": "delayed-completion",
                "time": delayed_time,
                "type": "document_completed",
            },
            "data": {"object": {"id": "signwell-delayed-completion", "status": "completed"}},
        },
        get_settings(),
        verification=esign_service.SignWellWebhookVerification(
            organization_id=envelope.organization_id,
            source="internal",
        ),
    )

    assert completed is True
    db_session.expire_all()
    assert db_session.get(EsignEnvelope, envelope_id).status == "completed"  # type: ignore[union-attr]
    assert db_session.get(ContractPackage, package_id).status == "executed"  # type: ignore[union-attr]
    assert db_session.get(Transaction, UUID(transaction_id)).status == "executed"  # type: ignore[union-attr]
    get_settings.cache_clear()


def test_transaction_cancellation_rejects_a_live_signature_request(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("ESIGN_PROVIDER", "simulate")
    monkeypatch.setenv("ESIGN_SIGNWELL_WEBHOOK_ID", "test-signwell-webhook-id")
    monkeypatch.setenv("ESIGN_TEST_MODE", "true")
    get_settings.cache_clear()
    client = TestClient(app)
    _, transaction_id = setup_transaction(db_session, client)
    package = approve_purchase_package(client, transaction_id)
    package_id = UUID(str(package["id"]))
    sent = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/esign",
        headers=HEADERS,
        json=esign_send_payload(),
    )
    assert sent.status_code == 201, sent.text

    cancelled = client.post(
        f"/api/v1/transactions/{transaction_id}/close",
        headers=HEADERS,
        json={"outcome": "cancelled", "notes": "Seller withdrew from the transaction."},
    )

    assert cancelled.status_code == 422
    assert "Cancel the active SignWell request" in cancelled.json()["detail"]
    db_session.expire_all()
    assert db_session.get(Transaction, UUID(transaction_id)).status == "sent"  # type: ignore[union-attr]
    assert db_session.get(ContractPackage, package_id).status == "sent"  # type: ignore[union-attr]
    assert db_session.get(EsignEnvelope, UUID(str(sent.json()["id"]))).status == "sent"  # type: ignore[union-attr]
    get_settings.cache_clear()


@pytest.mark.parametrize("terminal_state", ["cancelled_transaction", "closed_lead"])
def test_delayed_provider_completion_is_quarantined_after_terminal_state(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
    terminal_state: str,
) -> None:
    monkeypatch.setenv("ESIGN_PROVIDER", "simulate")
    monkeypatch.setenv("ESIGN_SIGNWELL_WEBHOOK_ID", "test-signwell-webhook-id")
    monkeypatch.setenv("ESIGN_TEST_MODE", "true")
    get_settings.cache_clear()
    client = TestClient(app)
    lead_id, transaction_id = setup_transaction(db_session, client)
    package = approve_purchase_package(client, transaction_id)
    package_id = UUID(str(package["id"]))
    sent = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/esign",
        headers=HEADERS,
        json=esign_send_payload(),
    )
    assert sent.status_code == 201, sent.text
    envelope_id = UUID(str(sent.json()["id"]))
    transaction = db_session.get(Transaction, UUID(transaction_id))
    lead = db_session.get(Lead, UUID(lead_id))
    envelope = db_session.get(EsignEnvelope, envelope_id)
    assert transaction is not None and lead is not None and envelope is not None
    terminal_at = datetime.now(UTC)
    if terminal_state == "cancelled_transaction":
        transaction.status = "cancelled"
        transaction.cancelled_at = terminal_at
        lead.stage_key = "follow_up"
    else:
        lead.stage_key = "dead"
        lead.archived_at = terminal_at
        lead.closed_out_at = terminal_at
        lead.close_out_disposition = "dead"
        lead.close_out_reason = "Seller confirmed they do not want to proceed."
    db_session.commit()
    completed_pdf = b"%PDF delayed terminal agreement"
    processed = esign_service.process_signwell_event(
        db_session,
        {
            "event": {
                "hash": f"terminal-completion-{terminal_state}",
                "time": int((terminal_at + timedelta(seconds=1)).timestamp()),
                "type": "document_completed",
            },
            "data": {
                "object": {
                    "id": envelope.provider_document_id,
                    "status": "completed",
                    "completed_pdf_base64": base64.b64encode(completed_pdf).decode(),
                }
            },
        },
        get_settings(),
        verification=esign_service.SignWellWebhookVerification(
            organization_id=envelope.organization_id,
            source="internal",
        ),
    )

    assert processed is True
    db_session.expire_all()
    stored_envelope = db_session.get(EsignEnvelope, envelope_id)
    stored_package = db_session.get(ContractPackage, package_id)
    stored_transaction = db_session.get(Transaction, UUID(transaction_id))
    stored_lead = db_session.get(Lead, UUID(lead_id))
    assert stored_envelope is not None and stored_envelope.status == "completed"
    assert stored_envelope.completed_at is not None
    assert stored_envelope.completed_document_id is not None
    quarantine_payload = stored_envelope.provider_payload["completion_quarantine"]
    assert quarantine_payload["document_id"] == str(stored_envelope.completed_document_id)
    assert "cannot execute" in quarantine_payload["reason"]
    assert stored_package is not None and stored_package.status == "sent"
    assert stored_transaction is not None
    assert stored_transaction.status == (
        "cancelled" if terminal_state == "cancelled_transaction" else "sent"
    )
    assert stored_lead is not None
    assert stored_lead.stage_key == (
        "follow_up" if terminal_state == "cancelled_transaction" else "dead"
    )
    provider_event = db_session.scalar(
        select(EsignProviderEvent).where(
            EsignProviderEvent.esign_envelope_id == envelope_id,
            EsignProviderEvent.event_type == "document_completed",
        )
    )
    assert provider_event is not None and provider_event.status == "quarantined"
    assert provider_event.processing_error is not None
    assert "cannot execute" in provider_event.processing_error
    quarantine_event = db_session.scalar(
        select(TransactionEvent).where(
            TransactionEvent.transaction_id == UUID(transaction_id),
            TransactionEvent.event_type == "esign.completion_quarantined",
        )
    )
    assert quarantine_event is not None
    quarantined_document = db_session.get(
        TransactionDocument,
        stored_envelope.completed_document_id,
    )
    assert quarantined_document is not None
    assert quarantined_document.contract_package_id == package_id
    assert quarantined_document.document_type == "quarantined_purchase_agreement"
    assert quarantined_document.status == "quarantined"
    assert quarantined_document.sha256 == sha256(completed_pdf).hexdigest()
    assert quarantine_event.details["document_id"] == str(quarantined_document.id)
    assert (
        db_session.scalar(
            select(TransactionDocument.id).where(
                TransactionDocument.contract_package_id == package_id,
                TransactionDocument.document_type == "signed_purchase_agreement",
            )
        )
        is None
    )
    recipient = db_session.scalar(
        select(EsignRecipient).where(EsignRecipient.esign_envelope_id == envelope_id)
    )
    assert recipient is not None and recipient.status == "signed"
    assert recipient.signed_at is not None
    get_settings.cache_clear()


def test_cancel_replay_does_not_reopen_a_subsequently_closed_lead(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    lead_id, transaction_id = setup_transaction(db_session, client)
    first = client.post(
        f"/api/v1/transactions/{transaction_id}/close",
        headers=HEADERS,
        json={"outcome": "cancelled", "notes": "Seller ended the transaction."},
    )
    assert first.status_code == 200, first.text
    lead = db_session.get(Lead, UUID(lead_id))
    assert lead is not None
    closed_at = datetime.now(UTC)
    lead.stage_key = "dead"
    lead.archived_at = closed_at
    lead.closed_out_at = closed_at
    lead.close_out_disposition = "dead"
    lead.close_out_reason = "Seller confirmed they no longer want to sell."
    db_session.commit()

    replay = client.post(
        f"/api/v1/transactions/{transaction_id}/close",
        headers=HEADERS,
        json={"outcome": "cancelled", "notes": "Duplicate cancellation delivery."},
    )

    assert replay.status_code == 200, replay.text
    assert replay.json()["status"] == "cancelled"
    db_session.expire_all()
    stored_lead = db_session.get(Lead, UUID(lead_id))
    stored_transaction = db_session.get(Transaction, UUID(transaction_id))
    assert stored_lead is not None and stored_lead.stage_key == "dead"
    assert stored_lead.archived_at is not None
    assert stored_lead.archived_at.replace(tzinfo=UTC) == closed_at
    assert stored_transaction is not None
    assert stored_transaction.notes == "Seller ended the transaction."
    cancellation_events = list(
        db_session.scalars(
            select(TransactionEvent).where(
                TransactionEvent.transaction_id == UUID(transaction_id),
                TransactionEvent.event_type == "transaction.cancelled",
            )
        ).all()
    )
    assert len(cancellation_events) == 1


def test_manual_execution_cannot_resurrect_a_cancelled_transaction_or_closed_lead(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    lead_id, transaction_id = setup_transaction(db_session, client)
    package = approve_purchase_package(client, transaction_id)
    package_id = UUID(str(package["id"]))
    document = client.post(
        (
            f"/api/v1/transactions/{transaction_id}/documents"
            "?file_name=manual-signed.pdf"
            "&document_type=signed_purchase_agreement"
            "&title=Manually%20signed%20purchase%20agreement"
            "&document_status=executed"
            f"&package_id={package_id}"
        ),
        headers={**HEADERS, "Content-Type": "application/pdf"},
        content=b"%PDF manually signed purchase agreement",
    )
    assert document.status_code == 201, document.text
    cancelled = client.post(
        f"/api/v1/transactions/{transaction_id}/close",
        headers=HEADERS,
        json={"outcome": "cancelled", "notes": "Seller ended the transaction."},
    )
    assert cancelled.status_code == 200, cancelled.text
    db_session.expire_all()
    assert db_session.get(ContractPackage, package_id).status == "void"  # type: ignore[union-attr]
    lead = db_session.get(Lead, UUID(lead_id))
    assert lead is not None
    lead.stage_key = "disqualified"
    lead.archived_at = datetime.now(UTC)
    lead.closed_out_at = lead.archived_at
    lead.close_out_disposition = "disqualified"
    lead.close_out_reason = "Title issue makes this seller lead ineligible."
    db_session.commit()

    executed = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/mark-executed",
        headers=HEADERS,
        json={
            "document_id": document.json()["id"],
            "confirm_fully_executed": True,
            "reason": "Compared every signature against the approved package.",
        },
    )

    assert executed.status_code == 422
    assert "terminal transaction" in executed.json()["detail"]
    db_session.expire_all()
    assert db_session.get(Transaction, UUID(transaction_id)).status == "cancelled"  # type: ignore[union-attr]
    assert db_session.get(ContractPackage, package_id).status == "void"  # type: ignore[union-attr]
    assert db_session.get(Lead, UUID(lead_id)).stage_key == "disqualified"  # type: ignore[union-attr]
    assert (
        db_session.scalar(
            select(AuditEvent.id).where(
                AuditEvent.entity_id == package_id,
                AuditEvent.action == "contract.execution.manual_attest",
            )
        )
        is None
    )


def test_contract_reservation_freezes_new_seller_agreement_authority(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    lead_id, transaction_id = setup_transaction(db_session, client)
    package = approve_purchase_package(client, transaction_id)
    package_id = UUID(str(package["id"]))
    stored_package = db_session.get(ContractPackage, package_id)
    owner = db_session.scalar(select(User).where(User.email == OWNER_EMAIL))
    plan = db_session.scalar(
        select(OfferNegotiationPlan).where(OfferNegotiationPlan.lead_id == UUID(lead_id))
    )
    assert stored_package is not None and owner is not None and plan is not None
    stored_package.status = "sending"
    db_session.commit()

    response = client.post(
        f"/api/v1/leads/{lead_id}/underwriting/negotiation-events",
        headers=HEADERS,
        json={
            "offer_negotiation_plan_id": str(plan.id),
            "event_type": "agreement",
            "channel": "phone",
            "amount_cents": 17_000_000,
            "notes": "Seller attempted to change authority during contract delivery.",
        },
    )
    with pytest.raises(ValueError, match="Offer authority is temporarily frozen"):
        record_field_agreement(
            db_session,
            principal_for_user(db_session, owner),
            UUID(lead_id),
            uuid4(),
            17_000_000,
            "Seller attempted to change authority during field delivery.",
        )
    db_session.rollback()

    concession_request = client.post(
        f"/api/v1/leads/{lead_id}/underwriting/concessions",
        headers=HEADERS,
        json={
            "offer_negotiation_plan_id": str(plan.id),
            "previous_offer_cents": 17_000_000,
            "proposed_offer_cents": 17_500_000,
            "seller_counter_cents": 17_500_000,
            "reason": "Seller requested a new price during contract delivery.",
            "seller_exchange": "Seller would sign only at the new amount.",
        },
    )

    pending_approval = ApprovalRequest(
        organization_id=plan.organization_id,
        requested_by_user_id=owner.id,
        assigned_to_user_id=owner.id,
        decided_by_user_id=None,
        request_type="offer_concession",
        entity_type="offer_concession",
        entity_id=None,
        status="pending",
        title="Approve blocked in-flight concession",
        summary="Concurrency fixture for contract authority.",
        decision_notes=None,
        decided_at=None,
        approval_metadata={"lead_id": lead_id},
    )
    db_session.add(pending_approval)
    db_session.flush()
    pending_concession = OfferConcession(
        organization_id=plan.organization_id,
        lead_id=plan.lead_id,
        property_id=plan.property_id,
        offer_negotiation_plan_id=plan.id,
        underwriting_version_id=plan.underwriting_version_id,
        appointment_id=None,
        requested_by_user_id=owner.id,
        approval_request_id=pending_approval.id,
        decided_by_user_id=None,
        presented_by_user_id=None,
        sequence_number=1,
        status="pending",
        authority_basis="manager_exception",
        previous_offer_cents=16_500_000,
        proposed_offer_cents=17_000_000,
        concession_delta_cents=500_000,
        seller_counter_cents=17_000_000,
        reason="Pending exact-price exception during delivery.",
        seller_exchange="Seller requested the pending exact amount.",
        decision_notes=None,
        decided_at=None,
        presented_at=None,
        source_snapshot={"fixture": True},
    )
    db_session.add(pending_concession)
    db_session.flush()
    pending_approval.entity_id = pending_concession.id
    db_session.commit()
    concession_decision = client.patch(
        f"/api/v1/approvals/{pending_approval.id}/decision",
        headers=HEADERS,
        json={
            "status": "approved",
            "decision_notes": "Attempted approval while contract was in flight.",
        },
    )

    assert response.status_code == 422
    assert "Offer authority is temporarily frozen" in response.json()["detail"]
    assert concession_request.status_code == 422
    assert "Offer authority is temporarily frozen" in concession_request.json()["detail"]
    assert concession_decision.status_code == 422
    assert "Offer authority is temporarily frozen" in concession_decision.json()["detail"]


def test_manual_sent_contract_freezes_authority_until_audited_withdrawal(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    lead_id, transaction_id = setup_transaction(db_session, client)
    package = approve_purchase_package(client, transaction_id)
    package_id = UUID(str(package["id"]))
    sent = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/mark-sent",
        headers=HEADERS,
    )
    assert sent.status_code == 200, sent.text
    db_session.expire_all()
    stored_package = db_session.get(ContractPackage, package_id)
    assert stored_package is not None
    with pytest.raises(ValueError, match="Offer authority is temporarily frozen"):
        lock_offer_authority_for_mutation(
            db_session,
            stored_package.organization_id,
            UUID(lead_id),
        )
    db_session.rollback()

    blank_reason = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/withdraw",
        headers=HEADERS,
        json={
            "confirm_withdrawn_from_all_recipients": True,
            "reason": "            ",
        },
    )
    assert blank_reason.status_code == 422
    assert "specific withdrawal reason" in blank_reason.json()["detail"]
    withdrawn = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/withdraw",
        headers=HEADERS,
        json={
            "confirm_withdrawn_from_all_recipients": True,
            "reason": "Seller confirmed the paper agreement was destroyed and withdrawn.",
        },
    )

    assert withdrawn.status_code == 200, withdrawn.text
    assert withdrawn.json()["status"] == "void"
    db_session.expire_all()
    stored_package = db_session.get(ContractPackage, package_id)
    assert stored_package is not None
    lock_offer_authority_for_mutation(
        db_session,
        stored_package.organization_id,
        UUID(lead_id),
    )
    audit = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_id == package_id,
            AuditEvent.action == "contract.package.withdraw",
        )
    )
    assert audit is not None


def test_f4_simulated_esign_completion_stores_provider_pdf_and_executes_package(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    handoff_calls: list[UUID] = []
    monkeypatch.setattr(
        "app.services.disposition_handoff.ensure_house_disposition_case_for_executed_transaction",
        lambda _db, transaction: handoff_calls.append(transaction.id),
    )
    monkeypatch.setenv("ESIGN_PROVIDER", "simulate")
    monkeypatch.setenv("ESIGN_SIGNWELL_WEBHOOK_ID", "test-signwell-webhook-id")
    monkeypatch.setenv("ESIGN_TEST_MODE", "true")
    get_settings.cache_clear()
    client = TestClient(app)
    lead_id, transaction_id = setup_transaction(db_session, client)

    package = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages",
        headers=HEADERS,
        json={
            "document_type": "purchase_agreement",
            "seller_name": "Jane Seller",
            "buyer_entity_name": "Stonegate Acquisitions LLC",
            "purchase_price_cents": 17000000,
            "earnest_money_cents": 100000,
            "closing_date": "2026-08-14T21:00:00Z",
            "inspection_period_days": 7,
        },
    )
    package_id = package.json()["id"]
    preview = client.get(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/preview",
        headers=HEADERS,
    )
    assert preview.status_code == 200, preview.text
    assert preview.headers["content-type"] == "application/pdf"
    assert b"{{signature:1:y::::180:35}}" in pdf_page_streams(preview.content)
    pending = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/request-approval",
        headers=HEADERS,
    )
    client.patch(
        f"/api/v1/approvals/{pending.json()['approval_request_id']}/decision",
        headers=HEADERS,
        json={"status": "approved", "decision_notes": "Terms verified."},
    )
    sent = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{package_id}/esign",
        headers=HEADERS,
        json={
            "subject": "Stonegate purchase agreement",
            "message": "Please review and sign the approved agreement.",
            "recipients": [
                {
                    "placeholder_name": "Seller",
                    "name": "Jane Seller",
                    "email": "jane@example.com",
                    "signing_order": 1,
                }
            ],
        },
    )
    assert sent.status_code == 201, sent.text
    envelope = sent.json()
    assert envelope["status"] == "sent"
    assert envelope["delivery_mode"] == "email"
    assert envelope["embedded_signers"] == []
    assert envelope["test_mode"] is True
    generated_detail = client.get(
        f"/api/v1/transactions/{transaction_id}",
        headers=HEADERS,
    ).json()
    signing_copy = next(
        item
        for item in generated_detail["documents"]
        if item["document_type"] == "purchase_agreement_for_signature"
    )
    signing_pdf = client.get(signing_copy["download_url"], headers=HEADERS)
    assert signing_pdf.content.startswith(b"%PDF")
    signing_text = pdf_page_streams(signing_pdf.content)
    assert b"{{signature:1:y::::180:35}}" in signing_text
    assert b"{{signature:2:y::::180:35}}" in signing_text
    assert b"{{autofill_date_signed:1:y::::90:30}}" in signing_text
    wrong_transaction = client.post(
        f"/api/v1/transactions/{uuid4()}/esign/{envelope['id']}/reconcile",
        headers=HEADERS,
    )
    assert wrong_transaction.status_code == 404
    signed_event_type = "document_signed"
    signed_event_time = 1786697999
    signed_event = {
        "event": {
            "hash": hmac.new(
                b"test-signwell-webhook-id",
                f"{signed_event_type}@{signed_event_time}".encode(),
                sha256,
            ).hexdigest(),
            "time": signed_event_time,
            "type": signed_event_type,
            "related_signer": {"id": "seller-1", "email": "jane@example.com"},
        },
        "data": {
            "object": {
                "id": envelope["provider_document_id"],
                "status": "in_progress",
            }
        },
    }
    signed_but_incomplete = client.post(
        "/api/v1/webhooks/esign/signwell",
        json=signed_event,
    )
    assert signed_but_incomplete.status_code == 200, signed_but_incomplete.text
    incomplete_detail = client.get(
        f"/api/v1/transactions/{transaction_id}",
        headers=HEADERS,
    ).json()
    assert incomplete_detail["contract_packages"][0]["status"] == "sent"
    assert not any(
        item["document_type"] == "signed_purchase_agreement"
        for item in incomplete_detail["documents"]
    )
    completed_pdf = b"%PDF SignWell completed agreement with audit page"
    event_type = "document_completed"
    event_time = 1786698000
    event = {
        "event": {
            "hash": hmac.new(
                b"test-signwell-webhook-id",
                f"{event_type}@{event_time}".encode(),
                sha256,
            ).hexdigest(),
            "time": event_time,
            "type": event_type,
        },
        "data": {
            "object": {
                "id": envelope["provider_document_id"],
                "status": "completed",
                "completed_pdf_base64": base64.b64encode(completed_pdf).decode(),
            }
        },
    }
    completed = client.post(
        "/api/v1/webhooks/esign/signwell",
        json=event,
    )
    duplicate = client.post(
        "/api/v1/webhooks/esign/signwell",
        json=event,
    )
    assert completed.status_code == 200, completed.text
    assert duplicate.status_code == 200
    assert handoff_calls == [UUID(transaction_id)]
    detail = client.get(
        f"/api/v1/transactions/{transaction_id}",
        headers=HEADERS,
    ).json()
    assert detail["contract_packages"][0]["status"] == "executed"
    assert detail["esign_envelopes"][0]["status"] == "completed"
    signed_document = next(
        item for item in detail["documents"] if item["document_type"] == "signed_purchase_agreement"
    )
    assert signed_document["storage_provider"] == "database"
    assert signed_document["malware_scan_status"] == "not_configured"
    download = client.get(
        signed_document["download_url"],
        headers=HEADERS,
    )
    assert download.content == completed_pdf
    assert client.get(f"/api/v1/leads/{lead_id}", headers=HEADERS).json()["stage_key"] == (
        "under_contract"
    )

    selected_assignee = setup_governed_assignment_selection(
        db_session,
        client,
        transaction_id,
    )
    assignment_package = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages",
        headers=HEADERS,
        json={
            "document_type": "assignment_contract",
            "seller_name": "Jane Seller",
            "buyer_entity_name": "Stonegate Acquisitions LLC",
            "purchase_price_cents": 17000000,
            "earnest_money_cents": 100000,
            "closing_date": "2026-08-14T21:00:00Z",
            "inspection_period_days": 7,
        },
    )
    assignment_package_id = assignment_package.json()["id"]
    assignment_pending = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{assignment_package_id}/request-approval",
        headers=HEADERS,
    )
    client.patch(
        f"/api/v1/approvals/{assignment_pending.json()['approval_request_id']}/decision",
        headers=HEADERS,
        json={"status": "approved", "decision_notes": "Assignment terms verified."},
    )
    assignment_sent = client.post(
        f"/api/v1/transactions/{transaction_id}/contract-packages/{assignment_package_id}/esign",
        headers=HEADERS,
        json={
            "subject": "Stonegate assignment agreement",
            "recipients": [
                {
                    "placeholder_name": "Assignee",
                    "name": selected_assignee["name"],
                    "email": selected_assignee["email"],
                    "signing_order": 1,
                }
            ],
        },
    )
    assert assignment_sent.status_code == 201, assignment_sent.text
    assignment_event_time = event_time + 1
    assignment_event = {
        "event": {
            "hash": hmac.new(
                b"test-signwell-webhook-id",
                f"{event_type}@{assignment_event_time}".encode(),
                sha256,
            ).hexdigest(),
            "time": assignment_event_time,
            "type": event_type,
        },
        "data": {
            "object": {
                "id": assignment_sent.json()["provider_document_id"],
                "status": "completed",
                "completed_pdf_base64": base64.b64encode(
                    b"%PDF SignWell completed assignment agreement"
                ).decode(),
            }
        },
    }
    assert client.post("/api/v1/webhooks/esign/signwell", json=assignment_event).status_code == 200
    assignment_detail = client.get(
        f"/api/v1/transactions/{transaction_id}",
        headers=HEADERS,
    ).json()
    stored_assignment = next(
        item
        for item in assignment_detail["documents"]
        if item["contract_package_id"] == assignment_package_id
        and item["document_type"] == "assignment_contract"
    )
    assert stored_assignment["document_type"] == "assignment_contract"
    assert "assignment agreement" in stored_assignment["title"].lower()
    get_settings.cache_clear()
