import base64
import hmac
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.main import app
from app.models.foundation import (
    AuditEvent,
    Buyer,
    BuyerOffer,
    BuyerProofDocument,
    ContractPackage,
    DispositionBuyerOutcome,
    DispositionBuyerSelection,
    DispositionBuyerSelectionSlot,
    DispositionCase,
    DispositionClosingCheckpoint,
    DispositionDeadlineAlert,
    DispositionMatch,
    DispositionOfferRevision,
    EsignEnvelope,
    EsignProviderEvent,
    EsignRecipient,
    Lead,
    Transaction,
    TransactionChecklistItem,
    TransactionDocument,
    User,
)
from app.services.bootstrap import bootstrap_foundation
from app.services.disposition_offer_room import process_next_closing_deadline_escalation
from tests.test_dispositions import (
    HEADERS,
    add_user_with_role,
    create_approved_disposition_case,
    put_verified_buy_box,
    setup_case_foundation,
    upload_received_proof,
    verify_proof,
)
from tests.test_transactions import pdf_page_streams


def _create_active_buyer(client: TestClient, *, name: str, email: str) -> str:
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
    return buyer_id


def _prepare_buyer(client: TestClient, buyer_id: str) -> str:
    put_verified_buy_box(client, buyer_id)
    proof = upload_received_proof(client, buyer_id, amount_cents=40_000_000)
    verify_proof(client, proof["id"], amount_cents=40_000_000)
    return proof["id"]


def _create_offer(
    client: TestClient,
    case_id: str,
    buyer_id: str,
    proof_id: str,
    *,
    amount_cents: int,
    key: str,
    deposit_due_at: datetime | None = None,
) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/offers",
        headers=HEADERS,
        json={
            "buyer_id": buyer_id,
            "amount_cents": amount_cents,
            "earnest_money_cents": 250_000,
            "deposit_due_at": deposit_due_at.isoformat() if deposit_due_at else None,
            "due_diligence_days": 7,
            "contingencies": [],
            "contingencies_confirmed": True,
            "proposed_closing_at": (datetime.now(UTC) + timedelta(days=21)).isoformat(),
            "funding_method": "cash",
            "funding_confidence_basis_points": 9000,
            "proof_document_id": proof_id,
            "change_reason": "Normalized buyer offer for DS7 regression coverage.",
            "idempotency_key": key,
        },
    )
    assert response.status_code == 201, response.text
    return next(item for item in response.json()["offers"] if item["buyer_id"] == buyer_id)


def _selection_payload(
    primary: dict[str, Any],
    backups: list[dict[str, Any]],
    *,
    key: str,
    expected_selection_lock_version: int | None = None,
) -> dict[str, Any]:
    return {
        "primary_offer_id": primary["id"],
        "backup_offer_ids": [item["id"] for item in backups],
        "expected_offer_lock_versions": {
            item["id"]: item["lock_version"] for item in [primary, *backups]
        },
        "expected_selection_lock_version": expected_selection_lock_version,
        "reason": "Approved executable buyer coverage with a distinct ranked backup.",
        "idempotency_key": key,
    }


def _setup_ready_case_with_offers(
    db: Session,
    client: TestClient,
    *,
    offer_count: int,
    deposit_due_at: datetime | None = None,
) -> tuple[str, list[str], list[dict[str, Any]]]:
    _, transaction_id, first_buyer_id = setup_case_foundation(db, client)
    case_id = create_approved_disposition_case(client, transaction_id)
    buyer_ids = [first_buyer_id]
    for index in range(2, offer_count + 1):
        buyer_ids.append(
            _create_active_buyer(
                client,
                name=f"DS7 Backup Buyer {index}",
                email=f"ds7-backup-{index}@example.com",
            )
        )
    proof_ids = [_prepare_buyer(client, buyer_id) for buyer_id in buyer_ids]
    matched = client.post(
        f"/api/v1/dispositions/cases/{case_id}/matches",
        headers=HEADERS,
    )
    assert matched.status_code == 200, matched.text
    assert {
        item["buyer_id"]
        for item in matched.json()["matches"]
        if item["qualification_status"] == "qualified"
    }.issuperset(buyer_ids)
    offers = [
        _create_offer(
            client,
            case_id,
            buyer_id,
            proof_id,
            amount_cents=20_000_000 - index * 100_000,
            key=f"ds7-offer-{index + 1:02d}",
            deposit_due_at=deposit_due_at,
        )
        for index, (buyer_id, proof_id) in enumerate(zip(buyer_ids, proof_ids, strict=True))
    ]
    return case_id, buyer_ids, offers


def _owner(db: Session) -> User:
    owner = db.scalar(select(User).where(User.email == HEADERS["X-Dev-User-Email"]))
    assert owner is not None
    return owner


def _complete_primary_deposit(
    client: TestClient,
    case_id: str,
    workspace: dict[str, Any],
) -> dict[str, Any]:
    selection_id = workspace["current_selection"]["id"]
    primary_offer_id = workspace["current_selection"]["primary"]["offer_id"]
    checkpoint = next(
        item
        for item in workspace["checkpoints"]
        if item["selection_id"] == selection_id
        and item["offer_id"] == primary_offer_id
        and item["checkpoint_type"] == "buyer_deposit"
    )
    response = client.patch(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/checkpoints/{checkpoint['id']}",
        headers=HEADERS,
        json={
            "expected_lock_version": checkpoint["lock_version"],
            "status": "completed",
            "evidence": {"confirmation_note": "Title confirmed buyer funds cleared into escrow."},
            "reason": "Recorded verified title confirmation for buyer deposit.",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _create_assignment_package(
    db: Session,
    client: TestClient,
    case_id: str,
) -> tuple[ContractPackage, Buyer, BuyerOffer]:
    case = db.get(DispositionCase, UUID(case_id))
    assert case is not None
    selection = db.scalar(
        select(DispositionBuyerSelection).where(
            DispositionBuyerSelection.disposition_case_id == case.id,
            DispositionBuyerSelection.status == "active",
        )
    )
    assert selection is not None
    primary_slot = db.scalar(
        select(DispositionBuyerSelectionSlot).where(
            DispositionBuyerSelectionSlot.selection_id == selection.id,
            DispositionBuyerSelectionSlot.role == "primary",
        )
    )
    assert primary_slot is not None
    primary_offer = db.get(BuyerOffer, primary_slot.offer_id)
    buyer = db.get(Buyer, primary_slot.buyer_id)
    assert primary_offer is not None and buyer is not None
    transaction = db.get(Transaction, case.transaction_id)
    assert transaction is not None
    transaction.assignment_fee_cents = primary_offer.amount_cents - transaction.purchase_price_cents
    db.commit()
    response = client.post(
        f"/api/v1/transactions/{case.transaction_id}/contract-packages",
        headers=HEADERS,
        json={
            "document_type": "assignment_contract",
            "seller_name": "Disposition Seller",
            "buyer_entity_name": buyer.name,
            "purchase_price_cents": transaction.purchase_price_cents,
            "earnest_money_cents": primary_offer.earnest_money_cents,
            "closing_date": (
                primary_offer.proposed_closing_at or datetime.now(UTC) + timedelta(days=21)
            ).isoformat(),
            "inspection_period_days": primary_offer.due_diligence_days,
        },
    )
    assert response.status_code == 201, response.text
    package = db.get(ContractPackage, UUID(response.json()["id"]))
    assert package is not None
    binding = package.terms_snapshot.get("disposition_buyer_binding")
    assert binding is not None
    assert binding["case_id"] == str(case.id)
    assert binding["selection_id"] == str(selection.id)
    assert binding["offer_id"] == str(primary_offer.id)
    assert binding["buyer_id"] == str(buyer.id)
    assert binding["offer_lock_version"] == primary_offer.lock_version
    assert binding["buyer_identity_snapshot"] == {
        "name": buyer.name,
        "normalized_name": "".join(
            character for character in buyer.name.casefold() if character.isalnum()
        ),
        "company_name": buyer.company_name,
        "normalized_company_name": "".join(
            character for character in (buyer.company_name or "").casefold() if character.isalnum()
        ),
        "email": buyer.normalized_email or buyer.email,
    }
    assert binding["offer_economics_snapshot"] == {
        "selected_offer_amount_cents": primary_offer.amount_cents,
        "base_purchase_price_cents": transaction.purchase_price_cents,
        "assignment_fee_cents": transaction.assignment_fee_cents,
        "end_buyer_price_cents": primary_offer.amount_cents,
        "earnest_money_cents": primary_offer.earnest_money_cents or 0,
        "deposit_due_at": (
            primary_offer.deposit_due_at.replace(tzinfo=UTC).isoformat()
            if primary_offer.deposit_due_at and primary_offer.deposit_due_at.tzinfo is None
            else primary_offer.deposit_due_at.astimezone(UTC).isoformat()
            if primary_offer.deposit_due_at
            else None
        ),
        "closing_date": primary_offer.proposed_closing_at.date().isoformat(),
        "inspection_period_days": primary_offer.due_diligence_days,
    }
    assert len(binding["offer_economics_hash"]) == 64
    return package, buyer, primary_offer


def _create_executed_assignment_package(
    db: Session,
    client: TestClient,
    case_id: str,
    *,
    with_execution_identity: bool = True,
) -> ContractPackage:
    package, buyer, _ = _approve_assignment_package(db, client, case_id)
    if with_execution_identity:
        document = _upload_executed_assignment_document(client, package)
        executed = client.post(
            f"/api/v1/transactions/{package.transaction_id}/contract-packages/{package.id}"
            "/mark-executed",
            headers=HEADERS,
            json={
                "document_id": document["id"],
                "confirm_fully_executed": True,
                "reason": "Verified the fully executed selected-buyer assignment agreement.",
                "assignee_name": buyer.name,
                "assignee_email": buyer.normalized_email or buyer.email,
            },
        )
        assert executed.status_code == 200, executed.text
        db.expire_all()
        stored = db.get(ContractPackage, package.id)
        assert stored is not None and stored.status == "executed"
        return stored
    package.status = "executed"
    package.executed_at = datetime.now(UTC)
    db.commit()
    return package


def _approve_assignment_package(
    db: Session,
    client: TestClient,
    case_id: str,
) -> tuple[ContractPackage, Buyer, BuyerOffer]:
    package, buyer, offer = _create_assignment_package(db, client, case_id)
    pending = client.post(
        f"/api/v1/transactions/{package.transaction_id}/contract-packages/{package.id}"
        "/request-approval",
        headers=HEADERS,
    )
    assert pending.status_code == 200, pending.text
    approved = client.patch(
        f"/api/v1/approvals/{pending.json()['approval_request_id']}/decision",
        headers=HEADERS,
        json={
            "status": "approved",
            "decision_notes": "Selected-buyer assignment terms and identity verified.",
        },
    )
    assert approved.status_code == 200, approved.text
    db.expire_all()
    stored = db.get(ContractPackage, package.id)
    stored_buyer = db.get(Buyer, buyer.id)
    stored_offer = db.get(BuyerOffer, offer.id)
    assert stored is not None and stored.status == "approved"
    assert stored_buyer is not None and stored_offer is not None
    return stored, stored_buyer, stored_offer


def _upload_executed_assignment_document(
    client: TestClient,
    package: ContractPackage,
) -> dict[str, Any]:
    uploaded = client.post(
        f"/api/v1/transactions/{package.transaction_id}/documents",
        headers={**HEADERS, "Content-Type": "application/pdf"},
        params={
            "file_name": "executed-assignment.pdf",
            "document_type": "assignment_contract",
            "title": "Executed assignment agreement",
            "document_status": "executed",
            "package_id": str(package.id),
        },
        content=b"%PDF controlled executed assignment agreement",
    )
    assert uploaded.status_code == 201, uploaded.text
    return uploaded.json()


def _satisfy_transaction_funding_prerequisites(
    db: Session,
    client: TestClient,
    transaction_id: UUID,
    *,
    include_purchase_execution: bool = True,
) -> None:
    if include_purchase_execution:
        transaction = db.get(Transaction, transaction_id)
        assert transaction is not None
        executed_purchase = next(
            (
                package
                for package in db.scalars(
                    select(ContractPackage).where(
                        ContractPackage.transaction_id == transaction_id,
                        ContractPackage.organization_id == transaction.organization_id,
                    )
                ).all()
                if package.status == "executed"
                and package.terms_snapshot.get("document_type") == "purchase_agreement"
            ),
            None,
        )
        if executed_purchase is None:
            packages = list(
                db.scalars(
                    select(ContractPackage).where(
                        ContractPackage.transaction_id == transaction_id,
                        ContractPackage.organization_id == transaction.organization_id,
                    )
                ).all()
            )
            owner = _owner(db)
            executed_at = datetime.now(UTC)
            db.add(
                ContractPackage(
                    organization_id=transaction.organization_id,
                    transaction_id=transaction.id,
                    lead_id=transaction.lead_id,
                    property_id=transaction.property_id,
                    template_id=None,
                    created_by_user_id=owner.id,
                    approval_request_id=None,
                    version_number=max((item.version_number for item in packages), default=0) + 1,
                    status="executed",
                    seller_name="Disposition Seller",
                    buyer_entity_name="Stonegate Acquisitions LLC",
                    purchase_price_cents=transaction.purchase_price_cents,
                    earnest_money_cents=100_000,
                    closing_date=executed_at + timedelta(days=21),
                    inspection_period_days=7,
                    terms_snapshot={"document_type": "purchase_agreement"},
                    notes="Controlled executed seller purchase authority for funding tests.",
                    approved_at=executed_at,
                    sent_at=executed_at,
                    executed_at=executed_at,
                    voided_at=None,
                )
            )
            transaction.contract_executed_at = executed_at
            db.commit()
        elif transaction.contract_executed_at is None:
            transaction.contract_executed_at = executed_purchase.executed_at or datetime.now(UTC)
            db.commit()
    for item in db.scalars(
        select(TransactionChecklistItem).where(
            TransactionChecklistItem.transaction_id == transaction_id
        )
    ).all():
        item.status = "complete"
        item.completed_at = datetime.now(UTC)
    db.commit()
    existing_funding = db.scalar(
        select(TransactionDocument).where(
            TransactionDocument.transaction_id == transaction_id,
            TransactionDocument.document_type == "funding_confirmation",
        )
    )
    if existing_funding is None:
        uploaded = client.post(
            f"/api/v1/transactions/{transaction_id}/documents",
            headers={**HEADERS, "Content-Type": "application/pdf"},
            params={
                "file_name": "funding-confirmation.pdf",
                "document_type": "funding_confirmation",
                "title": "Funding confirmation",
                "document_status": "evidence",
            },
            content=b"%PDF canonical funding confirmation",
        )
        assert uploaded.status_code == 201, uploaded.text


def test_selection_requires_manager_and_rejects_stale_offer_terms(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, _, offers = _setup_ready_case_with_offers(db_session, client, offer_count=2)
    rep = add_user_with_role(
        db_session,
        email="ds7-rep@example.com",
        display_name="DS7 Rep",
        role_key="disposition_rep",
    )
    rep_headers = {"X-Dev-User-Email": rep.email}
    payload = _selection_payload(offers[0], [offers[1]], key="ds7-select-rbac")

    forbidden = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
        headers=rep_headers,
        json=payload,
    )
    assert forbidden.status_code == 403, forbidden.text

    revised = client.patch(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/offers/{offers[0]['id']}",
        headers=HEADERS,
        json={
            "expected_lock_version": offers[0]["lock_version"],
            "amount_cents": offers[0]["amount_cents"] + 50_000,
            "change_reason": "Buyer improved the price before manager approval.",
            "idempotency_key": "ds7-stale-revision",
        },
    )
    assert revised.status_code == 200, revised.text

    stale = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
        headers=HEADERS,
        json=payload,
    )
    assert stale.status_code == 422, stale.text
    assert "changed" in stale.json()["detail"].lower()

    fresh_offers = {item["id"]: item for item in revised.json()["offers"]}
    selected = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
        headers=HEADERS,
        json=_selection_payload(
            fresh_offers[offers[0]["id"]],
            [fresh_offers[offers[1]["id"]]],
            key="ds7-select-fresh",
        ),
    )
    assert selected.status_code == 201, selected.text
    assert selected.json()["current_selection"]["primary"]["offer_id"] == offers[0]["id"]


def test_manager_can_supersede_backup_coverage_without_erasing_history(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    due_at = datetime.now(UTC) + timedelta(days=2)
    case_id, buyer_ids, offers = _setup_ready_case_with_offers(
        db_session,
        client,
        offer_count=3,
        deposit_due_at=due_at,
    )
    first = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
        headers=HEADERS,
        json=_selection_payload(offers[0], [offers[1]], key="ds7-coverage-v1"),
    )
    assert first.status_code == 201, first.text
    first_body = first.json()
    first_selection = first_body["current_selection"]
    first_checkpoint_ids = {
        item["id"]
        for item in first_body["checkpoints"]
        if item["selection_id"] == first_selection["id"]
    }
    assert first_checkpoint_ids

    fresh_by_id = {item["id"]: item for item in first_body["offers"]}
    stale_coverage = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
        headers=HEADERS,
        json=_selection_payload(
            fresh_by_id[offers[0]["id"]],
            [fresh_by_id[offers[2]["id"]]],
            key="ds7-coverage-stale",
            expected_selection_lock_version=first_selection["lock_version"] + 1,
        ),
    )
    assert stale_coverage.status_code == 422, stale_coverage.text
    assert "coverage changed" in stale_coverage.json()["detail"].lower()

    superseded = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
        headers=HEADERS,
        json=_selection_payload(
            fresh_by_id[offers[0]["id"]],
            [fresh_by_id[offers[2]["id"]]],
            key="ds7-coverage-v2",
            expected_selection_lock_version=first_selection["lock_version"],
        ),
    )
    assert superseded.status_code == 201, superseded.text
    body = superseded.json()
    assert body["current_selection"]["id"] != first_selection["id"]
    assert body["current_selection"]["primary"]["offer_id"] == offers[0]["id"]
    assert [item["offer_id"] for item in body["current_selection"]["backups"]] == [offers[2]["id"]]
    history = {item["id"]: item for item in body["selection_history"]}
    assert history[first_selection["id"]]["status"] == "replaced"
    old_checkpoints = [item for item in body["checkpoints"] if item["id"] in first_checkpoint_ids]
    assert old_checkpoints
    assert all(item["status"] == "cancelled" for item in old_checkpoints)


def test_deposit_completion_requires_a_substantive_confirmation_note(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, _, offers = _setup_ready_case_with_offers(
        db_session,
        client,
        offer_count=2,
        deposit_due_at=datetime.now(UTC) + timedelta(days=1),
    )
    selected = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
        headers=HEADERS,
        json=_selection_payload(offers[0], [offers[1]], key="ds7-deposit-select"),
    )
    assert selected.status_code == 201, selected.text
    checkpoint = next(
        item
        for item in selected.json()["checkpoints"]
        if item["checkpoint_type"] == "buyer_deposit"
        and item["selection_id"] == selected.json()["current_selection"]["id"]
    )

    too_short = client.patch(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/checkpoints/{checkpoint['id']}",
        headers=HEADERS,
        json={
            "expected_lock_version": checkpoint["lock_version"],
            "status": "completed",
            "evidence": {"confirmation_note": "too short"},
            "reason": "Controlled deposit evidence validation.",
        },
    )
    assert too_short.status_code == 422, too_short.text

    completed = client.patch(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/checkpoints/{checkpoint['id']}",
        headers=HEADERS,
        json={
            "expected_lock_version": checkpoint["lock_version"],
            "status": "completed",
            "evidence": {"confirmation_note": "Title confirmed cleared buyer funds in escrow."},
            "reason": "Title confirmation was reviewed and recorded.",
        },
    )
    assert completed.status_code == 200, completed.text
    stored = next(
        item for item in completed.json()["checkpoints"] if item["id"] == checkpoint["id"]
    )
    assert stored["status"] == "completed"
    assert "cleared buyer funds" in stored["evidence"]["confirmation_note"]


def test_deposit_waiver_requires_manager_permission_and_documented_reason(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, _, offers = _setup_ready_case_with_offers(
        db_session,
        client,
        offer_count=2,
        deposit_due_at=datetime.now(UTC) + timedelta(days=1),
    )
    selected = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
        headers=HEADERS,
        json=_selection_payload(offers[0], [offers[1]], key="ds7-waiver-select"),
    )
    assert selected.status_code == 201, selected.text
    checkpoint = next(
        item
        for item in selected.json()["checkpoints"]
        if item["checkpoint_type"] == "buyer_deposit"
        and item["selection_id"] == selected.json()["current_selection"]["id"]
    )
    rep = add_user_with_role(
        db_session,
        email="ds7-waiver-rep@example.com",
        display_name="DS7 Waiver Rep",
        role_key="disposition_rep",
    )
    waiver = {
        "expected_lock_version": checkpoint["lock_version"],
        "status": "waived",
        "evidence": {
            "support_note": "Manager approved no EMD because closing is scheduled immediately."
        },
        "reason": "Documented exception to the normal deposit requirement.",
    }
    forbidden = client.patch(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/checkpoints/{checkpoint['id']}",
        headers={"X-Dev-User-Email": rep.email},
        json=waiver,
    )
    assert forbidden.status_code == 403, forbidden.text

    waived = client.patch(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/checkpoints/{checkpoint['id']}",
        headers=HEADERS,
        json=waiver,
    )
    assert waived.status_code == 200, waived.text
    stored = next(item for item in waived.json()["checkpoints"] if item["id"] == checkpoint["id"])
    assert stored["status"] == "waived"
    assert "Manager approved" in stored["evidence"]["support_note"]


def test_terminal_offer_outcome_cannot_penalize_buyer_twice(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, buyer_ids, offers = _setup_ready_case_with_offers(
        db_session,
        client,
        offer_count=2,
    )
    buyer_id = buyer_ids[0]
    offer_id = offers[0]["id"]
    first = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/outcomes",
        headers=HEADERS,
        json={
            "offer_id": offer_id,
            "outcome_type": "withdrawal",
            "cause_category": "buyer",
            "reason": "Buyer withdrew after confirming they could not fund the purchase.",
            "evidence": {"confirmation_note": "Buyer withdrawal confirmed by phone."},
            "idempotency_key": "ds7-outcome-first",
        },
    )
    assert first.status_code == 201, first.text
    buyer = db_session.get(Buyer, UUID(buyer_id))
    assert buyer is not None
    db_session.refresh(buyer)
    failed_after_first = buyer.failed_deals
    reliability_after_first = buyer.reliability_score_basis_points
    assert failed_after_first == 1

    duplicate = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/outcomes",
        headers=HEADERS,
        json={
            "offer_id": offer_id,
            "outcome_type": "fallout",
            "cause_category": "buyer",
            "reason": "A second terminal penalty must not be accepted for the same offer.",
            "evidence": {"confirmation_note": "Controlled duplicate outcome attempt."},
            "idempotency_key": "ds7-outcome-second",
        },
    )
    assert duplicate.status_code == 422, duplicate.text
    db_session.refresh(buyer)
    assert buyer.failed_deals == failed_after_first
    assert buyer.reliability_score_basis_points == reliability_after_first
    outcomes = list(
        db_session.scalars(
            select(DispositionBuyerOutcome).where(
                DispositionBuyerOutcome.offer_id == UUID(offer_id)
            )
        ).all()
    )
    assert len(outcomes) == 1


def test_offer_room_reads_legacy_declined_offer_status(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, _, offers = _setup_ready_case_with_offers(db_session, client, offer_count=2)
    legacy_offer = db_session.scalar(select(Buyer).where(Buyer.id == UUID(offers[0]["buyer_id"])))
    assert legacy_offer is not None
    from app.models.foundation import BuyerOffer

    offer_row = db_session.get(BuyerOffer, UUID(offers[0]["id"]))
    assert offer_row is not None
    offer_row.status = "declined"
    db_session.commit()

    response = client.get(
        f"/api/v1/dispositions/cases/{case_id}/offer-room",
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    statuses = {item["id"]: item["status"] for item in response.json()["offers"]}
    assert statuses[offers[0]["id"]] == "declined"


def test_superseded_selection_and_checkpoint_rows_remain_queryable(
    db_session: Session,
    api_db_override: None,
) -> None:
    """A small database-level guard for the immutable coverage foreign-key chain."""
    client = TestClient(app)
    case_id, _, offers = _setup_ready_case_with_offers(
        db_session,
        client,
        offer_count=3,
        deposit_due_at=datetime.now(UTC) + timedelta(days=1),
    )
    first = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
        headers=HEADERS,
        json=_selection_payload(offers[0], [offers[1]], key="ds7-history-v1"),
    ).json()
    current = first["current_selection"]
    by_id = {item["id"]: item for item in first["offers"]}
    second = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
        headers=HEADERS,
        json=_selection_payload(
            by_id[offers[0]["id"]],
            [by_id[offers[2]["id"]]],
            key="ds7-history-v2",
            expected_selection_lock_version=current["lock_version"],
        ),
    )
    assert second.status_code == 201, second.text
    old_selection = db_session.get(DispositionBuyerSelection, UUID(current["id"]))
    assert old_selection is not None
    db_session.refresh(old_selection)
    assert old_selection.status == "replaced"
    old_checkpoints = list(
        db_session.scalars(
            select(DispositionClosingCheckpoint).where(
                DispositionClosingCheckpoint.selection_id == old_selection.id
            )
        ).all()
    )
    assert old_checkpoints
    assert all(item.status == "cancelled" for item in old_checkpoints)


def test_offer_room_is_house_only_and_tenant_scoped(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, _, _ = _setup_ready_case_with_offers(db_session, client, offer_count=2)
    other = bootstrap_foundation(
        db_session,
        organization_name="Other DS7 Organization",
        admin_email="other-ds7-owner@example.com",
        admin_name="Other DS7 Owner",
    )
    hidden = client.get(
        f"/api/v1/dispositions/cases/{case_id}/offer-room",
        headers={"X-Dev-User-Email": other.admin_user.email},
    )
    assert hidden.status_code == 404, hidden.text

    case = db_session.get(DispositionCase, UUID(case_id))
    assert case is not None
    lead = db_session.get(Lead, case.lead_id)
    assert lead is not None
    lead.asset_class = "land"
    db_session.commit()
    wrong_workflow = client.get(
        f"/api/v1/dispositions/cases/{case_id}/offer-room",
        headers=HEADERS,
    )
    assert wrong_workflow.status_code == 409, wrong_workflow.text
    assert "residential" in wrong_workflow.json()["detail"].lower()


def test_offer_receipt_and_revisions_are_idempotent_and_immutable(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, _, offers = _setup_ready_case_with_offers(db_session, client, offer_count=2)
    offer = offers[0]
    original_amount = offer["amount_cents"]

    replay = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/offers",
        headers=HEADERS,
        json={
            "buyer_id": offer["buyer_id"],
            "amount_cents": original_amount + 9_999_999,
            "funding_method": "private_money",
            "funding_confidence_basis_points": 1,
            "contingencies": ["Payload must not replace the accepted receipt."],
            "contingencies_confirmed": True,
            "change_reason": "Replay with conflicting values must return the original receipt.",
            "idempotency_key": "ds7-offer-01",
        },
    )
    assert replay.status_code == 201, replay.text
    replayed_offer = next(item for item in replay.json()["offers"] if item["id"] == offer["id"])
    assert replayed_offer["amount_cents"] == original_amount
    assert replayed_offer["funding_method"] == "cash"

    revised = client.patch(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/offers/{offer['id']}",
        headers=HEADERS,
        json={
            "expected_lock_version": offer["lock_version"],
            "amount_cents": original_amount + 125_000,
            "change_reason": "Buyer submitted a documented higher offer.",
            "idempotency_key": "ds7-revision-idempotent",
        },
    )
    assert revised.status_code == 200, revised.text
    revised_offer = next(item for item in revised.json()["offers"] if item["id"] == offer["id"])
    replay_revision = client.patch(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/offers/{offer['id']}",
        headers=HEADERS,
        json={
            "expected_lock_version": revised_offer["lock_version"],
            "amount_cents": original_amount + 5_000_000,
            "change_reason": "A conflicting replay cannot rewrite revision history.",
            "idempotency_key": "ds7-revision-idempotent",
        },
    )
    assert replay_revision.status_code == 200, replay_revision.text
    stored_offer = db_session.get(BuyerOffer, UUID(offer["id"]))
    assert stored_offer is not None
    db_session.refresh(stored_offer)
    assert stored_offer.amount_cents == original_amount + 125_000
    revisions = list(
        db_session.scalars(
            select(DispositionOfferRevision)
            .where(DispositionOfferRevision.offer_id == stored_offer.id)
            .order_by(DispositionOfferRevision.revision_number)
        ).all()
    )
    assert [item.revision_number for item in revisions] == [1, 2]
    assert revisions[0].terms_snapshot["amount_cents"] == original_amount
    assert revisions[1].terms_snapshot["amount_cents"] == original_amount + 125_000


def test_selection_requires_a_distinct_backup_and_receipt_keeps_primary_fresh(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, _, offers = _setup_ready_case_with_offers(db_session, client, offer_count=2)
    duplicate_backup = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
        headers=HEADERS,
        json={
            "primary_offer_id": offers[0]["id"],
            "backup_offer_ids": [offers[0]["id"]],
            "expected_offer_lock_versions": {offers[0]["id"]: offers[0]["lock_version"]},
            "reason": "A primary offer cannot also occupy the backup position.",
            "idempotency_key": "ds7-duplicate-backup",
        },
    )
    assert duplicate_backup.status_code == 422, duplicate_backup.text

    selected = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
        headers=HEADERS,
        json=_selection_payload(offers[0], [offers[1]], key="ds7-receipt-selection"),
    )
    assert selected.status_code == 201, selected.text
    primary_before = next(
        item for item in selected.json()["offers"] if item["id"] == offers[0]["id"]
    )
    receipt_replay = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/offers",
        headers=HEADERS,
        json={
            "buyer_id": offers[0]["buyer_id"],
            "amount_cents": offers[0]["amount_cents"],
            "funding_method": "cash",
            "funding_confidence_basis_points": 9000,
            "contingencies": [],
            "contingencies_confirmed": True,
            "change_reason": "Idempotent provider receipt replay.",
            "idempotency_key": "ds7-offer-01",
        },
    )
    assert receipt_replay.status_code == 201, receipt_replay.text
    primary_after = next(
        item for item in receipt_replay.json()["offers"] if item["id"] == offers[0]["id"]
    )
    assert primary_after["status"] == "selected"
    assert primary_after["lock_version"] == primary_before["lock_version"]
    assert (
        receipt_replay.json()["current_selection"]["id"]
        == selected.json()["current_selection"]["id"]
    )


def test_deadline_scan_is_deduplicated_for_one_deadline_version(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, _, offers = _setup_ready_case_with_offers(
        db_session,
        client,
        offer_count=2,
        deposit_due_at=datetime.now(UTC) - timedelta(hours=1),
    )
    selected = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
        headers=HEADERS,
        json=_selection_payload(offers[0], [offers[1]], key="ds7-deadline-selection"),
    )
    assert selected.status_code == 201, selected.text
    first = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/deadlines/scan",
        headers=HEADERS,
    )
    second = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/deadlines/scan",
        headers=HEADERS,
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    deposit_checkpoint = next(
        item
        for item in second.json()["checkpoints"]
        if item["checkpoint_type"] == "buyer_deposit"
        and item["selection_id"] == second.json()["current_selection"]["id"]
    )
    alerts = list(
        db_session.scalars(
            select(DispositionDeadlineAlert).where(
                DispositionDeadlineAlert.checkpoint_id == UUID(deposit_checkpoint["id"]),
                DispositionDeadlineAlert.deadline_version == deposit_checkpoint["deadline_version"],
            )
        ).all()
    )
    assert len(alerts) == 1
    assert any(item["id"] == str(alerts[0].id) for item in second.json()["alerts"])

    resolved_workspace = _complete_primary_deposit(client, case_id, second.json())
    assert all(item["id"] != str(alerts[0].id) for item in resolved_workspace["alerts"])
    db_session.expire_all()
    resolved_alert = db_session.get(DispositionDeadlineAlert, alerts[0].id)
    assert resolved_alert is not None and resolved_alert.resolved_at is not None


def test_primary_outcome_requires_atomic_replacement_and_promotes_backup(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, buyer_ids, offers = _setup_ready_case_with_offers(
        db_session,
        client,
        offer_count=3,
        deposit_due_at=datetime.now(UTC) + timedelta(days=1),
    )
    selected = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
        headers=HEADERS,
        json=_selection_payload(
            offers[0],
            [offers[1], offers[2]],
            key="ds7-atomic-selection",
        ),
    )
    assert selected.status_code == 201, selected.text
    current = selected.json()["current_selection"]
    blocked = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/outcomes",
        headers=HEADERS,
        json={
            "offer_id": offers[0]["id"],
            "selection_id": current["id"],
            "outcome_type": "fallout",
            "cause_category": "buyer",
            "reason": "Active primary outcomes must promote approved coverage atomically.",
            "evidence": {"confirmation_note": "Buyer could not perform."},
            "idempotency_key": "ds7-primary-outcome-blocked",
        },
    )
    assert blocked.status_code == 422, blocked.text
    assert "replace primary" in blocked.json()["detail"].lower()

    replaced = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/selections/{current['id']}"
        "/replace-primary",
        headers=HEADERS,
        json={
            "expected_lock_version": current["lock_version"],
            "replacement_offer_id": offers[1]["id"],
            "outcome_type": "fallout",
            "cause_category": "buyer",
            "reason": "Buyer failed funding review; promote the approved first backup.",
            "evidence": {"confirmation_note": "Manager verified the funding failure."},
            "idempotency_key": "ds7-atomic-replacement",
        },
    )
    assert replaced.status_code == 200, replaced.text
    body = replaced.json()
    assert body["current_selection"]["primary"]["offer_id"] == offers[1]["id"]
    assert [item["offer_id"] for item in body["current_selection"]["backups"]] == [offers[2]["id"]]
    assert body["current_selection"]["id"] != current["id"]
    assert sum(item["status"] == "active" for item in body["selection_history"]) == 1
    original_buyer = db_session.get(Buyer, UUID(buyer_ids[0]))
    assert original_buyer is not None
    db_session.refresh(original_buyer)
    assert original_buyer.failed_deals == 1


def test_manual_completed_close_outcome_is_not_exposed(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, _, offers = _setup_ready_case_with_offers(db_session, client, offer_count=2)
    response = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/outcomes",
        headers=HEADERS,
        json={
            "offer_id": offers[0]["id"],
            "outcome_type": "completed_close",
            "cause_category": "external",
            "reason": "Only canonical transaction funding may record a completed close.",
            "evidence": {"confirmation_note": "Manual close attempt."},
            "idempotency_key": "ds7-manual-completed-close",
        },
    )
    assert response.status_code == 422, response.text


def test_assignment_binding_survives_backup_reapproval_and_funding_is_exact_once(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, buyer_ids, offers = _setup_ready_case_with_offers(
        db_session,
        client,
        offer_count=3,
        deposit_due_at=datetime.now(UTC) + timedelta(days=1),
    )
    selected = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
        headers=HEADERS,
        json=_selection_payload(offers[0], [offers[1]], key="ds7-binding-selection-v1"),
    )
    assert selected.status_code == 201, selected.text
    package = _create_executed_assignment_package(db_session, client, case_id)
    assert (
        package.terms_snapshot["assignment_execution_identity"]["source"]
        == "manual_execution_attestation"
    )

    by_id = {item["id"]: item for item in selected.json()["offers"]}
    reapproved = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
        headers=HEADERS,
        json=_selection_payload(
            by_id[offers[0]["id"]],
            [by_id[offers[2]["id"]]],
            key="ds7-binding-selection-v2",
            expected_selection_lock_version=selected.json()["current_selection"]["lock_version"],
        ),
    )
    assert reapproved.status_code == 201, reapproved.text
    deposited = _complete_primary_deposit(client, case_id, reapproved.json())
    primary_after_receipt = next(
        item for item in deposited["offers"] if item["id"] == offers[0]["id"]
    )
    assert primary_after_receipt["lock_version"] == offers[0]["lock_version"]

    case = db_session.get(DispositionCase, UUID(case_id))
    assert case is not None
    _satisfy_transaction_funding_prerequisites(db_session, client, case.transaction_id)
    first = client.post(
        f"/api/v1/transactions/{case.transaction_id}/close",
        headers=HEADERS,
        json={"outcome": "funded", "notes": "Closing attorney confirmed funds."},
    )
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "funded"
    buyer = db_session.get(Buyer, UUID(buyer_ids[0]))
    assert buyer is not None
    db_session.refresh(buyer)
    completed_deals = buyer.completed_deals
    reliability = buyer.reliability_score_basis_points
    assert completed_deals == 1

    replay = client.post(
        f"/api/v1/transactions/{case.transaction_id}/close",
        headers=HEADERS,
        json={"outcome": "funded", "notes": "Duplicate funding delivery."},
    )
    assert replay.status_code == 200, replay.text
    db_session.refresh(buyer)
    assert buyer.completed_deals == completed_deals
    assert buyer.reliability_score_basis_points == reliability
    completed_outcomes = list(
        db_session.scalars(
            select(DispositionBuyerOutcome).where(
                DispositionBuyerOutcome.disposition_case_id == UUID(case_id),
                DispositionBuyerOutcome.outcome_type == "completed_close",
            )
        ).all()
    )
    assert len(completed_outcomes) == 1


def test_funding_requires_bound_assignment_and_documented_deposit(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, buyer_ids, offers = _setup_ready_case_with_offers(
        db_session,
        client,
        offer_count=2,
        deposit_due_at=datetime.now(UTC) + timedelta(days=1),
    )
    selected = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
        headers=HEADERS,
        json=_selection_payload(offers[0], [offers[1]], key="ds7-funding-gates"),
    )
    assert selected.status_code == 201, selected.text
    case = db_session.get(DispositionCase, UUID(case_id))
    assert case is not None
    selection = db_session.get(
        DispositionBuyerSelection,
        UUID(selected.json()["current_selection"]["id"]),
    )
    selected_buyer = db_session.get(Buyer, UUID(buyer_ids[0]))
    assert selection is not None and selected_buyer is not None
    selection.idempotency_key = "legacy-adoption:ds7-unbound-package"
    owner = _owner(db_session)
    db_session.add(
        ContractPackage(
            organization_id=case.organization_id,
            transaction_id=case.transaction_id,
            lead_id=case.lead_id,
            property_id=case.property_id,
            template_id=None,
            created_by_user_id=owner.id,
            approval_request_id=None,
            version_number=1,
            status="executed",
            seller_name="Disposition Seller",
            # Even an old package named after the selected buyer cannot bypass the frozen
            # buyer/offer/signer binding introduced by the governed Offer Room.
            buyer_entity_name=selected_buyer.name,
            purchase_price_cents=offers[0]["amount_cents"],
            earnest_money_cents=offers[0]["earnest_money_cents"],
            closing_date=datetime.now(UTC) + timedelta(days=21),
            inspection_period_days=offers[0]["due_diligence_days"],
            terms_snapshot={"document_type": "assignment_contract"},
            notes="Legacy-looking unbound package must not satisfy governed funding.",
            approved_at=datetime.now(UTC),
            sent_at=datetime.now(UTC),
            executed_at=datetime.now(UTC),
            voided_at=None,
        )
    )
    db_session.commit()
    _satisfy_transaction_funding_prerequisites(
        db_session,
        client,
        case.transaction_id,
        include_purchase_execution=False,
    )

    missing_purchase = client.post(
        f"/api/v1/transactions/{case.transaction_id}/close",
        headers=HEADERS,
        json={"outcome": "funded", "notes": "Attempt with assignment authority only."},
    )
    assert missing_purchase.status_code == 422, missing_purchase.text
    assert "purchase agreement" in missing_purchase.json()["detail"].lower()
    db_session.rollback()

    _satisfy_transaction_funding_prerequisites(db_session, client, case.transaction_id)

    missing_assignment = client.post(
        f"/api/v1/transactions/{case.transaction_id}/close",
        headers=HEADERS,
        json={"outcome": "funded", "notes": "Attempt without buyer agreement."},
    )
    assert missing_assignment.status_code == 422, missing_assignment.text
    assert "assignment agreement" in missing_assignment.json()["detail"].lower()
    db_session.rollback()

    _create_executed_assignment_package(db_session, client, case_id)
    missing_deposit = client.post(
        f"/api/v1/transactions/{case.transaction_id}/close",
        headers=HEADERS,
        json={"outcome": "funded", "notes": "Attempt without deposit receipt."},
    )
    assert missing_deposit.status_code == 422, missing_deposit.text
    assert "deposit" in missing_deposit.json()["detail"].lower()
    db_session.rollback()


def test_executed_assignment_blocks_primary_offer_terms_change(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, _, offers = _setup_ready_case_with_offers(
        db_session,
        client,
        offer_count=2,
        deposit_due_at=datetime.now(UTC) + timedelta(days=1),
    )
    selected = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
        headers=HEADERS,
        json=_selection_payload(offers[0], [offers[1]], key="ds7-stale-binding-v1"),
    )
    assert selected.status_code == 201, selected.text
    _create_executed_assignment_package(db_session, client, case_id)
    primary = next(item for item in selected.json()["offers"] if item["id"] == offers[0]["id"])
    revised = client.patch(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/offers/{primary['id']}",
        headers=HEADERS,
        json={
            "expected_lock_version": primary["lock_version"],
            "amount_cents": primary["amount_cents"] + 100_000,
            "change_reason": "Primary buyer changed price after signing the assignment.",
            "idempotency_key": "ds7-primary-terms-changed",
        },
    )
    assert revised.status_code == 422, revised.text
    detail = revised.json()["detail"].lower()
    assert "executed buyer assignment" in detail
    assert "resolve" in detail


def test_stale_backup_cannot_be_promoted_and_is_not_an_eligible_replacement(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, _, offers = _setup_ready_case_with_offers(db_session, client, offer_count=2)
    selected = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
        headers=HEADERS,
        json=_selection_payload(offers[0], [offers[1]], key="ds7-stale-backup-selection"),
    )
    assert selected.status_code == 201, selected.text
    current = selected.json()["current_selection"]

    revised = client.patch(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/offers/{offers[1]['id']}",
        headers=HEADERS,
        json={
            "expected_lock_version": offers[1]["lock_version"],
            "amount_cents": offers[1]["amount_cents"] + 75_000,
            "change_reason": "Backup buyer changed price after coverage approval.",
            "idempotency_key": "ds7-stale-backup-revision",
        },
    )
    assert revised.status_code == 200, revised.text
    workspace = revised.json()
    backup = workspace["current_selection"]["backups"][0]
    assert backup["readiness_status"] == "provisional"
    assert any("reapproval" in item.lower() for item in backup["readiness_blockers"])
    option = next(
        item for item in workspace["replacement_options"] if item["offer_id"] == offers[1]["id"]
    )
    assert option["eligible"] is False
    assert any("reapproval" in item.lower() for item in option["blockers"])

    blocked = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/selections/{current['id']}"
        "/replace-primary",
        headers=HEADERS,
        json={
            "expected_lock_version": current["lock_version"],
            "replacement_offer_id": offers[1]["id"],
            "outcome_type": "withdrawal",
            "cause_category": "buyer",
            "reason": "Primary withdrew, but stale backup terms cannot be promoted.",
            "evidence": {"confirmation_note": "Controlled stale backup promotion attempt."},
            "idempotency_key": "ds7-stale-backup-promotion",
        },
    )
    assert blocked.status_code == 422, blocked.text
    after = client.get(
        f"/api/v1/dispositions/cases/{case_id}/offer-room",
        headers=HEADERS,
    )
    assert after.status_code == 200, after.text
    assert after.json()["current_selection"]["id"] == current["id"]
    assert after.json()["current_selection"]["primary"]["offer_id"] == offers[0]["id"]
    assert after.json()["outcomes"] == []


@pytest.mark.parametrize(
    ("invalid_kind", "expected_fragment"),
    [
        ("inactive", "inactive"),
        ("archived", "archived"),
        ("expired_proof", "proof"),
        ("insufficient_proof", "proof"),
        ("unqualified_match", "qualified"),
    ],
)
def test_backup_read_and_promotion_revalidate_live_buyer_eligibility(
    db_session: Session,
    api_db_override: None,
    invalid_kind: str,
    expected_fragment: str,
) -> None:
    client = TestClient(app)
    case_id, buyer_ids, offers = _setup_ready_case_with_offers(
        db_session,
        client,
        offer_count=2,
    )
    selected = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
        headers=HEADERS,
        json=_selection_payload(
            offers[0],
            [offers[1]],
            key=f"ds7-live-backup-{invalid_kind}",
        ),
    )
    assert selected.status_code == 201, selected.text
    current = selected.json()["current_selection"]
    backup_buyer = db_session.get(Buyer, UUID(buyer_ids[1]))
    backup_proof = db_session.get(BuyerProofDocument, UUID(offers[1]["proof_document_id"]))
    backup_match = db_session.scalar(
        select(DispositionMatch).where(
            DispositionMatch.disposition_case_id == UUID(case_id),
            DispositionMatch.buyer_id == UUID(buyer_ids[1]),
        )
    )
    assert backup_buyer is not None and backup_proof is not None and backup_match is not None
    if invalid_kind == "inactive":
        backup_buyer.status = "inactive"
    elif invalid_kind == "archived":
        backup_buyer.archived_at = datetime.now(UTC)
    elif invalid_kind == "expired_proof":
        backup_proof.expires_at = datetime.now(UTC) - timedelta(days=1)
    elif invalid_kind == "insufficient_proof":
        backup_proof.verified_amount_cents = offers[1]["amount_cents"] - 1
    else:
        backup_match.qualification_status = "review_required"
    db_session.commit()

    workspace_response = client.get(
        f"/api/v1/dispositions/cases/{case_id}/offer-room",
        headers=HEADERS,
    )
    assert workspace_response.status_code == 200, workspace_response.text
    workspace = workspace_response.json()
    backup = workspace["current_selection"]["backups"][0]
    assert backup["readiness_status"] == "provisional"
    assert expected_fragment in " ".join(backup["readiness_blockers"]).lower()
    option = next(
        item for item in workspace["replacement_options"] if item["offer_id"] == offers[1]["id"]
    )
    assert option["eligible"] is False
    assert expected_fragment in " ".join(option["blockers"]).lower()

    blocked = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/selections/{current['id']}"
        "/replace-primary",
        headers=HEADERS,
        json={
            "expected_lock_version": current["lock_version"],
            "replacement_offer_id": offers[1]["id"],
            "outcome_type": "fallout",
            "cause_category": "buyer",
            "reason": "Controlled promotion attempt after backup eligibility changed.",
            "evidence": {"confirmation_note": "Live eligibility was intentionally invalidated."},
            "idempotency_key": f"ds7-invalid-backup-promotion-{invalid_kind}",
        },
    )
    assert blocked.status_code == 422, blocked.text
    assert (
        client.get(
            f"/api/v1/dispositions/cases/{case_id}/offer-room",
            headers=HEADERS,
        ).json()["current_selection"]["primary"]["offer_id"]
        == offers[0]["id"]
    )


@pytest.mark.parametrize(
    "invalid_kind",
    ["inactive", "archived", "expired_proof", "insufficient_proof", "unqualified_match"],
)
def test_funding_revalidates_live_primary_buyer_eligibility(
    db_session: Session,
    api_db_override: None,
    invalid_kind: str,
) -> None:
    client = TestClient(app)
    case_id, buyer_ids, offers = _setup_ready_case_with_offers(
        db_session,
        client,
        offer_count=2,
        deposit_due_at=datetime.now(UTC) + timedelta(days=1),
    )
    selected = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
        headers=HEADERS,
        json=_selection_payload(
            offers[0],
            [offers[1]],
            key=f"ds7-funding-revalidation-{invalid_kind}",
        ),
    )
    assert selected.status_code == 201, selected.text
    _create_executed_assignment_package(db_session, client, case_id)
    _complete_primary_deposit(client, case_id, selected.json())
    case = db_session.get(DispositionCase, UUID(case_id))
    assert case is not None
    _satisfy_transaction_funding_prerequisites(db_session, client, case.transaction_id)

    primary_buyer = db_session.get(Buyer, UUID(buyer_ids[0]))
    primary_proof = db_session.get(BuyerProofDocument, UUID(offers[0]["proof_document_id"]))
    primary_match = db_session.scalar(
        select(DispositionMatch).where(
            DispositionMatch.disposition_case_id == UUID(case_id),
            DispositionMatch.buyer_id == UUID(buyer_ids[0]),
        )
    )
    assert primary_buyer is not None and primary_proof is not None and primary_match is not None
    if invalid_kind == "inactive":
        primary_buyer.status = "inactive"
    elif invalid_kind == "archived":
        primary_buyer.archived_at = datetime.now(UTC)
    elif invalid_kind == "expired_proof":
        primary_proof.expires_at = datetime.now(UTC) - timedelta(days=1)
    elif invalid_kind == "insufficient_proof":
        primary_proof.verified_amount_cents = offers[0]["amount_cents"] - 1
    else:
        primary_match.qualification_status = "review_required"
    db_session.commit()

    blocked = client.post(
        f"/api/v1/transactions/{case.transaction_id}/close",
        headers=HEADERS,
        json={"outcome": "funded", "notes": "Controlled live eligibility failure."},
    )
    assert blocked.status_code == 422, blocked.text
    db_session.rollback()
    transaction = db_session.get(Transaction, case.transaction_id)
    assert transaction is not None and transaction.status == "executed"
    db_session.refresh(primary_buyer)
    assert primary_buyer.completed_deals == 0
    assert (
        db_session.scalar(
            select(DispositionBuyerOutcome).where(
                DispositionBuyerOutcome.disposition_case_id == UUID(case_id),
                DispositionBuyerOutcome.outcome_type == "completed_close",
            )
        )
        is None
    )


def test_assignment_draft_freezes_selected_buyer_identity_and_requires_offer_economics(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, buyer_ids, offers = _setup_ready_case_with_offers(
        db_session,
        client,
        offer_count=2,
    )
    selected = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
        headers=HEADERS,
        json=_selection_payload(offers[0], [offers[1]], key="ds7-assignment-normalization"),
    )
    assert selected.status_code == 201, selected.text
    case = db_session.get(DispositionCase, UUID(case_id))
    buyer = db_session.get(Buyer, UUID(buyer_ids[0]))
    offer = db_session.get(BuyerOffer, UUID(offers[0]["id"]))
    assert case is not None and buyer is not None and offer is not None
    transaction = db_session.get(Transaction, case.transaction_id)
    assert transaction is not None
    transaction.assignment_fee_cents = offer.amount_cents - transaction.purchase_price_cents
    db_session.commit()
    base_payload = {
        "document_type": "assignment_contract",
        "seller_name": "Disposition Seller",
        # This is the assignor legal entity, not the selected end buyer/assignee.
        "buyer_entity_name": "Stonegate Home Buyers, LLC",
        "purchase_price_cents": transaction.purchase_price_cents,
        "earnest_money_cents": offer.earnest_money_cents,
        "closing_date": offer.proposed_closing_at.isoformat(),
        "inspection_period_days": offer.due_diligence_days,
    }

    rejected = client.post(
        f"/api/v1/transactions/{case.transaction_id}/contract-packages",
        headers=HEADERS,
        json={
            **base_payload,
            "purchase_price_cents": transaction.purchase_price_cents + 1,
        },
    )
    assert rejected.status_code == 422, rejected.text

    accepted = client.post(
        f"/api/v1/transactions/{case.transaction_id}/contract-packages",
        headers=HEADERS,
        json={
            **base_payload,
            # Assignment EMD, closing, and diligence terms are canonical selected-offer
            # data; caller-supplied values must never replace them in the package.
            "earnest_money_cents": (offer.earnest_money_cents or 0) + 1,
            "closing_date": (offer.proposed_closing_at + timedelta(days=1)).isoformat(),
            "inspection_period_days": (offer.due_diligence_days or 0) + 1,
        },
    )
    assert accepted.status_code == 201, accepted.text
    package = db_session.get(ContractPackage, UUID(accepted.json()["id"]))
    assert package is not None
    assert package.earnest_money_cents == offer.earnest_money_cents
    assert package.closing_date == offer.proposed_closing_at
    assert package.inspection_period_days == offer.due_diligence_days
    binding = package.terms_snapshot["disposition_buyer_binding"]
    assert binding["buyer_identity_snapshot"]["normalized_name"] == "reliableatlantabuyer"
    assert binding["offer_economics_snapshot"]["end_buyer_price_cents"] == offer.amount_cents
    assert len(binding["offer_economics_hash"]) == 64


def test_assignment_esign_requires_exactly_one_matching_selected_buyer_assignee(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ESIGN_PROVIDER", "simulate")
    monkeypatch.setenv("ESIGN_TEST_MODE", "true")
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        case_id, _, offers = _setup_ready_case_with_offers(
            db_session,
            client,
            offer_count=2,
        )
        selected = client.post(
            f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
            headers=HEADERS,
            json=_selection_payload(offers[0], [offers[1]], key="ds7-esign-assignee-gates"),
        )
        assert selected.status_code == 201, selected.text
        package, buyer, _ = _approve_assignment_package(db_session, client, case_id)
        buyer_email = buyer.normalized_email or buyer.email
        endpoint = (
            f"/api/v1/transactions/{package.transaction_id}/contract-packages/{package.id}/esign"
        )

        invalid_recipients = [
            (
                [
                    {
                        "placeholder_name": "Seller",
                        "name": "Disposition Seller",
                        "email": "seller@example.com",
                        "signing_order": 1,
                    }
                ],
                "exactly one",
            ),
            (
                [
                    {
                        "placeholder_name": "Assignee",
                        "name": buyer.name,
                        "email": buyer_email,
                        "signing_order": 1,
                    },
                    {
                        "placeholder_name": "End Buyer",
                        "name": "Second Buyer",
                        "email": "second-buyer@example.com",
                        "signing_order": 2,
                    },
                ],
                "exactly one",
            ),
            (
                [
                    {
                        "placeholder_name": "Assignee",
                        "name": "Wrong Buyer Entity",
                        "email": buyer_email,
                        "signing_order": 1,
                    }
                ],
                "name or entity",
            ),
            (
                [
                    {
                        "placeholder_name": "Assignee",
                        "name": buyer.name,
                        "email": "wrong-assignee@example.com",
                        "signing_order": 1,
                    }
                ],
                "email",
            ),
        ]
        for recipients, expected_fragment in invalid_recipients:
            rejected = client.post(
                endpoint,
                headers=HEADERS,
                json={
                    "subject": "Stonegate selected-buyer assignment",
                    "recipients": recipients,
                },
            )
            assert rejected.status_code == 422, rejected.text
            assert expected_fragment in rejected.json()["detail"].lower()

        assert (
            db_session.scalar(
                select(EsignEnvelope).where(EsignEnvelope.contract_package_id == package.id)
            )
            is None
        )
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize("identity_kind", ["buyer_name", "company_name"])
def test_assignment_esign_accepts_normalized_selected_buyer_name_or_company(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
    identity_kind: str,
) -> None:
    monkeypatch.setenv("ESIGN_PROVIDER", "simulate")
    monkeypatch.setenv("ESIGN_TEST_MODE", "true")
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        case_id, buyer_ids, offers = _setup_ready_case_with_offers(
            db_session,
            client,
            offer_count=2,
        )
        buyer = db_session.get(Buyer, UUID(buyer_ids[0]))
        assert buyer is not None
        if identity_kind == "company_name":
            buyer.company_name = "Reliable Atlanta Holdings, LLC"
            db_session.commit()
        selected = client.post(
            f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
            headers=HEADERS,
            json=_selection_payload(
                offers[0],
                [offers[1]],
                key=f"ds7-esign-normalized-{identity_kind}",
            ),
        )
        assert selected.status_code == 201, selected.text
        package, buyer, _ = _approve_assignment_package(db_session, client, case_id)
        signer_name = (
            "RELIABLE-ATLANTA BUYER"
            if identity_kind == "buyer_name"
            else "reliable-atlanta holdings llc"
        )
        buyer_email = buyer.normalized_email or buyer.email
        sent = client.post(
            f"/api/v1/transactions/{package.transaction_id}/contract-packages/{package.id}/esign",
            headers=HEADERS,
            json={
                "subject": "Stonegate selected-buyer assignment",
                "recipients": [
                    {
                        "placeholder_name": "Assignee",
                        "name": signer_name,
                        "email": buyer_email,
                        "signing_order": 1,
                    }
                ],
            },
        )
        assert sent.status_code == 201, sent.text
        envelope = db_session.get(EsignEnvelope, UUID(sent.json()["id"]))
        assert envelope is not None
        evidence = envelope.provider_payload["assignment_execution_identity"]
        assert evidence["source"] == "esign_recipient"
        assert evidence["name"] == signer_name
        assert evidence["email"] == buyer_email.lower()
        assert evidence["normalized_name"] == "".join(
            character for character in signer_name.casefold() if character.isalnum()
        )
        assert len(evidence["identity_hash"]) == 64
    finally:
        get_settings.cache_clear()


def test_assignment_esign_server_binds_assignor_to_authenticated_user(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ESIGN_PROVIDER", "simulate")
    monkeypatch.setenv("ESIGN_TEST_MODE", "true")
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        case_id, _, offers = _setup_ready_case_with_offers(
            db_session,
            client,
            offer_count=2,
        )
        selected = client.post(
            f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
            headers=HEADERS,
            json=_selection_payload(offers[0], [offers[1]], key="ds7-server-bound-assignor"),
        )
        assert selected.status_code == 201, selected.text
        package, buyer, _ = _approve_assignment_package(db_session, client, case_id)
        owner = _owner(db_session)
        sent = client.post(
            f"/api/v1/transactions/{package.transaction_id}/contract-packages/{package.id}/esign",
            headers=HEADERS,
            json={
                "subject": "Server-bound Stonegate assignor",
                "recipients": [
                    {
                        "placeholder_name": "Assignee",
                        "name": buyer.name,
                        "email": buyer.normalized_email or buyer.email,
                        "signing_order": 1,
                    },
                    {
                        "placeholder_name": "Assignor",
                        "name": "Caller Supplied Fake Assignor",
                        "email": "fake-assignor@example.com",
                        "signing_order": 2,
                    },
                ],
            },
        )
        assert sent.status_code == 201, sent.text
        envelope_id = UUID(sent.json()["id"])
        recipients = list(
            db_session.scalars(
                select(EsignRecipient)
                .where(EsignRecipient.esign_envelope_id == envelope_id)
                .order_by(EsignRecipient.signing_order)
            ).all()
        )
        assignees = [item for item in recipients if item.placeholder_name == "Assignee"]
        assignors = [item for item in recipients if item.placeholder_name == "Assignor"]
        assert len(assignees) == 1
        assert assignees[0].name == buyer.name
        assert assignees[0].email == (buyer.normalized_email or buyer.email)
        assert len(assignors) == 1
        assert assignors[0].name == owner.display_name
        assert assignors[0].email == owner.email
        assert all(item.email != "fake-assignor@example.com" for item in recipients)
    finally:
        get_settings.cache_clear()


def test_manual_assignment_execution_requires_matching_assignee_and_freezes_evidence(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, _, offers = _setup_ready_case_with_offers(
        db_session,
        client,
        offer_count=2,
    )
    selected = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
        headers=HEADERS,
        json=_selection_payload(offers[0], [offers[1]], key="ds7-manual-assignee-gates"),
    )
    assert selected.status_code == 201, selected.text
    package, buyer, _ = _approve_assignment_package(db_session, client, case_id)
    document = _upload_executed_assignment_document(client, package)
    buyer_email = buyer.normalized_email or buyer.email
    endpoint = (
        f"/api/v1/transactions/{package.transaction_id}/contract-packages/{package.id}"
        "/mark-executed"
    )
    base_payload = {
        "document_id": document["id"],
        "confirm_fully_executed": True,
        "reason": "Verified all signatures on the selected-buyer assignment agreement.",
    }
    invalid_identities = [
        {"assignee_email": buyer_email},
        {"assignee_name": buyer.name},
        {"assignee_name": "Wrong Buyer Entity", "assignee_email": buyer_email},
        {"assignee_name": buyer.name, "assignee_email": "wrong-assignee@example.com"},
    ]
    for invalid_identity in invalid_identities:
        rejected = client.post(
            endpoint,
            headers=HEADERS,
            json={**base_payload, **invalid_identity},
        )
        assert rejected.status_code == 422, rejected.text
        assert "assignee" in rejected.json()["detail"].lower()

    executed = client.post(
        endpoint,
        headers=HEADERS,
        json={
            **base_payload,
            "assignee_name": "RELIABLE-ATLANTA BUYER",
            "assignee_email": buyer_email,
        },
    )
    assert executed.status_code == 200, executed.text
    db_session.expire_all()
    stored_package = db_session.get(ContractPackage, package.id)
    stored_document = db_session.get(TransactionDocument, UUID(document["id"]))
    assert stored_package is not None and stored_document is not None
    evidence = dict(stored_package.terms_snapshot["assignment_execution_identity"])
    assert evidence["source"] == "manual_execution_attestation"
    assert evidence["normalized_name"] == "reliableatlantabuyer"
    assert evidence["email"] == buyer_email.lower()
    assert evidence["document_id"] == str(stored_document.id)
    assert evidence["document_sha256"] == stored_document.sha256
    assert evidence["attested_by_user_id"] == str(_owner(db_session).id)
    assert len(evidence["identity_hash"]) == 64
    audit = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_id == package.id,
            AuditEvent.action == "contract.execution.manual_attest",
        )
    )
    assert audit is not None
    assert audit.new_value["assignment_execution_identity"] == evidence

    buyer = db_session.get(Buyer, buyer.id)
    assert buyer is not None
    buyer.name = "Buyer Identity Changed After Execution"
    db_session.commit()
    db_session.refresh(stored_package)
    assert stored_package.terms_snapshot["assignment_execution_identity"] == evidence


@pytest.mark.parametrize(
    "authority_gate",
    ["approval_after_replacement", "esign_after_offer_change", "manual_after_offer_change"],
)
def test_stale_assignment_authority_blocks_approval_send_and_manual_execution(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
    authority_gate: str,
) -> None:
    monkeypatch.setenv("ESIGN_PROVIDER", "simulate")
    monkeypatch.setenv("ESIGN_TEST_MODE", "true")
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        case_id, _, offers = _setup_ready_case_with_offers(
            db_session,
            client,
            offer_count=2,
        )
        selected = client.post(
            f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
            headers=HEADERS,
            json=_selection_payload(
                offers[0],
                [offers[1]],
                key=f"ds7-stale-authority-{authority_gate}",
            ),
        )
        assert selected.status_code == 201, selected.text
        current = selected.json()["current_selection"]

        if authority_gate == "approval_after_replacement":
            package, _, _ = _create_assignment_package(db_session, client, case_id)
            pending = client.post(
                f"/api/v1/transactions/{package.transaction_id}/contract-packages/{package.id}"
                "/request-approval",
                headers=HEADERS,
            )
            assert pending.status_code == 200, pending.text
            replaced = client.post(
                f"/api/v1/dispositions/cases/{case_id}/offer-room/selections/{current['id']}"
                "/replace-primary",
                headers=HEADERS,
                json={
                    "expected_lock_version": current["lock_version"],
                    "replacement_offer_id": offers[1]["id"],
                    "outcome_type": "fallout",
                    "cause_category": "buyer",
                    "reason": "Primary buyer withdrew before the assignment was approved.",
                    "evidence": {"confirmation_note": "Manager confirmed buyer withdrawal."},
                    "idempotency_key": "ds7-stale-approval-replacement",
                },
            )
            assert replaced.status_code == 200, replaced.text
            blocked = client.patch(
                f"/api/v1/approvals/{pending.json()['approval_request_id']}/decision",
                headers=HEADERS,
                json={
                    "status": "approved",
                    "decision_notes": "This stale package must not be approved.",
                },
            )
        else:
            package, buyer, offer = _approve_assignment_package(db_session, client, case_id)
            # Public Offer Room mutations are blocked once an approved buyer contract exists.
            # These direct writes simulate a stale-authority race or corrupt administrative
            # update so each downstream legal gate still has independent fail-closed coverage.
            offer.amount_cents += 25_000
            offer.lock_version += 1
            db_session.commit()
            if authority_gate == "esign_after_offer_change":
                blocked = client.post(
                    f"/api/v1/transactions/{package.transaction_id}/contract-packages/"
                    f"{package.id}/esign",
                    headers=HEADERS,
                    json={
                        "subject": "Stale assignment must not send",
                        "recipients": [
                            {
                                "placeholder_name": "Assignee",
                                "name": buyer.name,
                                "email": buyer.normalized_email or buyer.email,
                                "signing_order": 1,
                            }
                        ],
                    },
                )
            else:
                document = _upload_executed_assignment_document(client, package)
                blocked = client.post(
                    f"/api/v1/transactions/{package.transaction_id}/contract-packages/"
                    f"{package.id}/mark-executed",
                    headers=HEADERS,
                    json={
                        "document_id": document["id"],
                        "confirm_fully_executed": True,
                        "reason": "Attempt to record a stale selected-buyer assignment.",
                        "assignee_name": buyer.name,
                        "assignee_email": buyer.normalized_email or buyer.email,
                    },
                )

        assert blocked.status_code == 422, blocked.text
        detail = blocked.json()["detail"].lower()
        assert "stale" in detail or "changed" in detail
        db_session.expire_all()
        stored_package = db_session.get(ContractPackage, package.id)
        assert stored_package is not None
        assert stored_package.status not in {"sent", "executed"}
    finally:
        get_settings.cache_clear()


def test_stale_assignment_authority_rejects_provider_completion_atomically(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ESIGN_PROVIDER", "simulate")
    monkeypatch.setenv("ESIGN_TEST_MODE", "true")
    monkeypatch.setenv("ESIGN_SIGNWELL_WEBHOOK_ID", "ds7-stale-provider-secret")
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        case_id, _, offers = _setup_ready_case_with_offers(
            db_session,
            client,
            offer_count=2,
        )
        selected = client.post(
            f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
            headers=HEADERS,
            json=_selection_payload(offers[0], [offers[1]], key="ds7-stale-provider"),
        )
        assert selected.status_code == 201, selected.text
        case = db_session.get(DispositionCase, UUID(case_id))
        assert case is not None
        seller_transaction = db_session.get(Transaction, case.transaction_id)
        assert seller_transaction is not None and seller_transaction.status == "executed"
        seller_contract_sent_at = datetime(2026, 8, 1, 14)
        seller_contract_executed_at = datetime(2026, 8, 2, 15)
        seller_transaction.contract_sent_at = seller_contract_sent_at
        seller_transaction.contract_executed_at = seller_contract_executed_at
        db_session.commit()
        package, buyer, offer = _approve_assignment_package(db_session, client, case_id)
        db_session.expire_all()
        after_approval = db_session.get(Transaction, case.transaction_id)
        assert after_approval is not None and after_approval.status == "executed"
        assert after_approval.contract_sent_at == seller_contract_sent_at
        assert after_approval.contract_executed_at == seller_contract_executed_at
        sent = client.post(
            f"/api/v1/transactions/{package.transaction_id}/contract-packages/{package.id}/esign",
            headers=HEADERS,
            json={
                "subject": "Selected-buyer assignment",
                "recipients": [
                    {
                        "placeholder_name": "Assignee",
                        "name": buyer.name,
                        "email": buyer.normalized_email or buyer.email,
                        "signing_order": 1,
                    }
                ],
            },
        )
        assert sent.status_code == 201, sent.text
        db_session.expire_all()
        after_send = db_session.get(Transaction, case.transaction_id)
        assert after_send is not None and after_send.status == "executed"
        assert after_send.contract_sent_at == seller_contract_sent_at
        assert after_send.contract_executed_at == seller_contract_executed_at

        # Simulate a stale-authority race or corrupt administrative write after provider send.
        # Public offer/selection routes correctly block this mutation once an obligation is live.
        offer.amount_cents += 50_000
        offer.lock_version += 1
        db_session.commit()

        event_type = "document_completed"
        event_time = int(datetime.now(UTC).timestamp())
        event = {
            "event": {
                "hash": hmac.new(
                    b"ds7-stale-provider-secret",
                    f"{event_type}@{event_time}".encode(),
                    sha256,
                ).hexdigest(),
                "time": event_time,
                "type": event_type,
            },
            "data": {
                "object": {
                    "id": sent.json()["provider_document_id"],
                    "status": "completed",
                    "completed_pdf_base64": base64.b64encode(
                        b"%PDF stale selected-buyer assignment"
                    ).decode(),
                }
            },
        }
        quarantined = client.post("/api/v1/webhooks/esign/signwell", json=event)
        assert quarantined.status_code == 200, quarantined.text
        assert quarantined.json() == {"received": True, "matched": True}
        db_session.expire_all()
        envelope = db_session.get(EsignEnvelope, UUID(sent.json()["id"]))
        stored_package = db_session.get(ContractPackage, package.id)
        transaction = db_session.get(Transaction, package.transaction_id)
        assert envelope is not None and envelope.status == "completed"
        assert envelope.completed_at is not None
        assert envelope.completed_document_id is not None
        completion_quarantine = envelope.provider_payload["completion_quarantine"]
        assert "changed" in completion_quarantine["reason"].lower()
        assert completion_quarantine["document_id"] == str(envelope.completed_document_id)
        assert stored_package is not None and stored_package.status == "sent"
        assert transaction is not None and transaction.status == "executed"
        assert transaction.contract_sent_at == seller_contract_sent_at
        assert transaction.contract_executed_at == seller_contract_executed_at
        quarantined_document = db_session.get(
            TransactionDocument,
            envelope.completed_document_id,
        )
        assert quarantined_document is not None
        assert quarantined_document.document_type == "quarantined_assignment_contract"
        assert quarantined_document.status == "quarantined"
        assert quarantined_document.contract_package_id == package.id
        provider_event = db_session.scalar(
            select(EsignProviderEvent).where(
                EsignProviderEvent.esign_envelope_id == envelope.id,
                EsignProviderEvent.event_type == "document_completed",
            )
        )
        assert provider_event is not None and provider_event.status == "quarantined"
        assert "changed" in (provider_event.processing_error or "").lower()
        assignee = db_session.scalar(
            select(EsignRecipient).where(
                EsignRecipient.esign_envelope_id == envelope.id,
                EsignRecipient.placeholder_name == "Assignee",
            )
        )
        assert assignee is not None and assignee.status == "signed"
        assert (
            db_session.scalar(
                select(TransactionDocument).where(
                    TransactionDocument.contract_package_id == package.id,
                    TransactionDocument.document_type == "assignment_contract",
                    TransactionDocument.status == "executed",
                )
            )
            is None
        )
    finally:
        get_settings.cache_clear()


def test_live_assignment_obligation_blocks_buyer_changes_until_withdrawn(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ESIGN_PROVIDER", "simulate")
    monkeypatch.setenv("ESIGN_TEST_MODE", "true")
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        case_id, _, offers = _setup_ready_case_with_offers(
            db_session,
            client,
            offer_count=2,
        )
        selected = client.post(
            f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
            headers=HEADERS,
            json=_selection_payload(offers[0], [offers[1]], key="ds7-live-obligation"),
        )
        assert selected.status_code == 201, selected.text
        workspace = selected.json()
        current = workspace["current_selection"]
        primary_offer = next(item for item in workspace["offers"] if item["id"] == offers[0]["id"])
        backup_offer = next(item for item in workspace["offers"] if item["id"] == offers[1]["id"])
        package, buyer, _ = _approve_assignment_package(db_session, client, case_id)
        sent = client.post(
            f"/api/v1/transactions/{package.transaction_id}/contract-packages/{package.id}/esign",
            headers=HEADERS,
            json={
                "subject": "Live selected-buyer assignment",
                "recipients": [
                    {
                        "placeholder_name": "Assignee",
                        "name": buyer.name,
                        "email": buyer.normalized_email or buyer.email,
                        "signing_order": 1,
                    }
                ],
            },
        )
        assert sent.status_code == 201, sent.text

        revised = client.patch(
            f"/api/v1/dispositions/cases/{case_id}/offer-room/offers/{primary_offer['id']}",
            headers=HEADERS,
            json={
                "expected_lock_version": primary_offer["lock_version"],
                "amount_cents": primary_offer["amount_cents"] + 25_000,
                "change_reason": "Must not revise terms under a live signature request.",
                "idempotency_key": "ds7-live-obligation-revision",
            },
        )
        replaced = client.post(
            f"/api/v1/dispositions/cases/{case_id}/offer-room/selections/{current['id']}"
            "/replace-primary",
            headers=HEADERS,
            json={
                "expected_lock_version": current["lock_version"],
                "replacement_offer_id": backup_offer["id"],
                "outcome_type": "fallout",
                "cause_category": "buyer",
                "reason": "Must not switch buyers under a live signature request.",
                "evidence": {"confirmation_note": "Controlled obligation guard test."},
                "idempotency_key": "ds7-live-obligation-replacement",
            },
        )
        reselected = client.post(
            f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
            headers=HEADERS,
            json=_selection_payload(
                backup_offer,
                [primary_offer],
                key="ds7-live-obligation-reselection",
                expected_selection_lock_version=current["lock_version"],
            ),
        )
        for blocked in (revised, replaced, reselected):
            assert blocked.status_code == 422, blocked.text
            assert "assignment" in blocked.json()["detail"].lower()

        envelope = db_session.get(EsignEnvelope, UUID(sent.json()["id"]))
        assert envelope is not None
        envelope.status = "cancelled"
        db_session.commit()
        withdrawn = client.post(
            f"/api/v1/transactions/{package.transaction_id}/contract-packages/{package.id}"
            "/withdraw",
            headers=HEADERS,
            json={
                "confirm_withdrawn_from_all_recipients": True,
                "reason": "Provider request was cancelled and every recipient was notified.",
            },
        )
        assert withdrawn.status_code == 200, withdrawn.text
        assert withdrawn.json()["status"] == "void"
        replacement_after_withdrawal = client.post(
            f"/api/v1/dispositions/cases/{case_id}/offer-room/selections/{current['id']}"
            "/replace-primary",
            headers=HEADERS,
            json={
                "expected_lock_version": current["lock_version"],
                "replacement_offer_id": backup_offer["id"],
                "outcome_type": "fallout",
                "cause_category": "buyer",
                "reason": "The original assignment was withdrawn before changing buyers.",
                "evidence": {"confirmation_note": "Withdrawal audit is recorded."},
                "idempotency_key": "ds7-replacement-after-withdrawal",
            },
        )
        assert replacement_after_withdrawal.status_code == 200, replacement_after_withdrawal.text
        assert (
            replacement_after_withdrawal.json()["current_selection"]["primary"]["offer_id"]
            == backup_offer["id"]
        )
    finally:
        get_settings.cache_clear()


def test_approved_assignment_can_be_voided_before_replacing_primary_buyer(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, _, offers = _setup_ready_case_with_offers(
        db_session,
        client,
        offer_count=2,
    )
    selected = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
        headers=HEADERS,
        json=_selection_payload(offers[0], [offers[1]], key="ds7-approved-withdrawal"),
    )
    assert selected.status_code == 201, selected.text
    current = selected.json()["current_selection"]
    package, _, _ = _approve_assignment_package(db_session, client, case_id)
    replacement_url = (
        f"/api/v1/dispositions/cases/{case_id}/offer-room/selections/{current['id']}"
        "/replace-primary"
    )
    replacement_payload = {
        "expected_lock_version": current["lock_version"],
        "replacement_offer_id": offers[1]["id"],
        "outcome_type": "fallout",
        "cause_category": "buyer",
        "reason": "Original buyer withdrew before the approved contract was delivered.",
        "evidence": {"confirmation_note": "Manager confirmed the buyer withdrawal."},
        "idempotency_key": "ds7-approved-replacement-after-withdrawal",
    }
    blocked = client.post(
        replacement_url,
        headers=HEADERS,
        json=replacement_payload,
    )
    assert blocked.status_code == 422, blocked.text
    assert "assignment" in blocked.json()["detail"].lower()

    withdrawn = client.post(
        f"/api/v1/transactions/{package.transaction_id}/contract-packages/{package.id}/withdraw",
        headers=HEADERS,
        json={
            "confirm_withdrawn_from_all_recipients": True,
            "reason": "Approved agreement was voided before it was delivered to any recipient.",
        },
    )
    assert withdrawn.status_code == 200, withdrawn.text
    assert withdrawn.json()["status"] == "void"
    db_session.expire_all()
    stored_package = db_session.get(ContractPackage, package.id)
    assert stored_package is not None
    assert stored_package.status == "void"
    assert stored_package.voided_at is not None
    withdrawal_audit = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_id == package.id,
            AuditEvent.action == "contract.package.withdraw",
        )
    )
    assert withdrawal_audit is not None
    assert withdrawal_audit.previous_value == {"status": "approved"}

    replaced = client.post(
        replacement_url,
        headers=HEADERS,
        json=replacement_payload,
    )
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["current_selection"]["primary"]["offer_id"] == offers[1]["id"]


def test_assignment_preview_renders_selected_offer_deposit_amount_and_deadline(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    deposit_due_at = datetime(2026, 9, 15, 18, 30, tzinfo=UTC)
    case_id, _, offers = _setup_ready_case_with_offers(
        db_session,
        client,
        offer_count=2,
        deposit_due_at=deposit_due_at,
    )
    selected = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
        headers=HEADERS,
        json=_selection_payload(offers[0], [offers[1]], key="ds7-assignment-rendering"),
    )
    assert selected.status_code == 201, selected.text
    package, _, _ = _create_assignment_package(db_session, client, case_id)
    preview = client.get(
        f"/api/v1/transactions/{package.transaction_id}/contract-packages/{package.id}/preview",
        headers=HEADERS,
    )
    assert preview.status_code == 200, preview.text
    rendered = pdf_page_streams(preview.content)
    assert b"$2,500.00" in rendered
    assert b"September 15, 2026 at 6:30 PM UTC" in rendered


@pytest.mark.parametrize(
    "evidence_tamper",
    ["missing", "wrong_signer", "identity_hash", "document_sha256"],
)
def test_funding_rejects_missing_or_tampered_manual_assignment_execution_evidence(
    db_session: Session,
    api_db_override: None,
    evidence_tamper: str,
) -> None:
    client = TestClient(app)
    case_id, _, offers = _setup_ready_case_with_offers(
        db_session,
        client,
        offer_count=2,
        deposit_due_at=datetime.now(UTC) + timedelta(days=1),
    )
    selected = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
        headers=HEADERS,
        json=_selection_payload(
            offers[0],
            [offers[1]],
            key=f"ds7-manual-funding-{evidence_tamper}",
        ),
    )
    assert selected.status_code == 201, selected.text
    package = _create_executed_assignment_package(
        db_session,
        client,
        case_id,
        with_execution_identity=evidence_tamper != "missing",
    )
    if evidence_tamper != "missing":
        snapshot = dict(package.terms_snapshot)
        evidence = dict(snapshot["assignment_execution_identity"])
        if evidence_tamper == "wrong_signer":
            evidence["name"] = "Wrong Executed Assignee"
            evidence["normalized_name"] = "wrongexecutedassignee"
        elif evidence_tamper == "identity_hash":
            evidence["identity_hash"] = "0" * 64
        else:
            evidence["document_sha256"] = "0" * 64
        snapshot["assignment_execution_identity"] = evidence
        package.terms_snapshot = snapshot
        db_session.commit()
    _complete_primary_deposit(client, case_id, selected.json())
    case = db_session.get(DispositionCase, UUID(case_id))
    assert case is not None
    _satisfy_transaction_funding_prerequisites(db_session, client, case.transaction_id)

    blocked = client.post(
        f"/api/v1/transactions/{case.transaction_id}/close",
        headers=HEADERS,
        json={"outcome": "funded", "notes": "Controlled signer-evidence rejection."},
    )
    assert blocked.status_code == 422, blocked.text
    assert "assignment agreement" in blocked.json()["detail"].lower()
    db_session.rollback()
    transaction = db_session.get(Transaction, case.transaction_id)
    assert transaction is not None and transaction.status != "funded"


@pytest.mark.parametrize(
    ("recipient_state", "funding_status"),
    [("matching_signed", 200), ("wrong_assignee", 422), ("unsigned", 422)],
)
def test_funding_revalidates_completed_esign_assignment_recipient(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
    recipient_state: str,
    funding_status: int,
) -> None:
    monkeypatch.setenv("ESIGN_PROVIDER", "simulate")
    monkeypatch.setenv("ESIGN_TEST_MODE", "true")
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        case_id, _, offers = _setup_ready_case_with_offers(
            db_session,
            client,
            offer_count=2,
            deposit_due_at=datetime.now(UTC) + timedelta(days=1),
        )
        selected = client.post(
            f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
            headers=HEADERS,
            json=_selection_payload(
                offers[0],
                [offers[1]],
                key=f"ds7-esign-funding-{recipient_state}",
            ),
        )
        assert selected.status_code == 201, selected.text
        package, buyer, _ = _approve_assignment_package(db_session, client, case_id)
        buyer_email = buyer.normalized_email or buyer.email
        sent = client.post(
            f"/api/v1/transactions/{package.transaction_id}/contract-packages/{package.id}/esign",
            headers=HEADERS,
            json={
                "subject": "Stonegate completed assignment",
                "recipients": [
                    {
                        "placeholder_name": "Assignee",
                        "name": buyer.name,
                        "email": buyer_email,
                        "signing_order": 1,
                    }
                ],
            },
        )
        assert sent.status_code == 201, sent.text
        executed_document = _upload_executed_assignment_document(client, package)
        envelope = db_session.get(EsignEnvelope, UUID(sent.json()["id"]))
        assert envelope is not None
        assignee = db_session.scalar(
            select(EsignRecipient).where(
                EsignRecipient.esign_envelope_id == envelope.id,
                EsignRecipient.placeholder_name == "Assignee",
            )
        )
        transaction = db_session.get(Transaction, package.transaction_id)
        assert assignee is not None and transaction is not None
        envelope.status = "completed"
        envelope.completed_at = datetime.now(UTC)
        envelope.completed_document_id = UUID(executed_document["id"])
        package.status = "executed"
        package.executed_at = envelope.completed_at
        transaction.status = "executed"
        if recipient_state == "matching_signed":
            assignee.status = "signed"
            assignee.signed_at = envelope.completed_at
        elif recipient_state == "wrong_assignee":
            assignee.status = "signed"
            assignee.signed_at = envelope.completed_at
            assignee.name = "Wrong Completed Assignee"
        else:
            assignee.status = "sent"
            assignee.signed_at = None
        db_session.commit()
        _complete_primary_deposit(client, case_id, selected.json())
        case = db_session.get(DispositionCase, UUID(case_id))
        assert case is not None
        _satisfy_transaction_funding_prerequisites(db_session, client, case.transaction_id)

        funding = client.post(
            f"/api/v1/transactions/{case.transaction_id}/close",
            headers=HEADERS,
            json={"outcome": "funded", "notes": "Completed e-sign recipient verified."},
        )
        assert funding.status_code == funding_status, funding.text
        if funding_status == 200:
            assert funding.json()["status"] == "funded"
        else:
            assert "assignment agreement" in funding.json()["detail"].lower()
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize(
    "tamper_kind",
    [
        "live_buyer_identity",
        "identity_snapshot",
        "economics_snapshot",
        "economics_hash",
        "package_economics",
    ],
)
def test_funding_rejects_tampered_assignment_identity_or_economics(
    db_session: Session,
    api_db_override: None,
    tamper_kind: str,
) -> None:
    client = TestClient(app)
    case_id, _, offers = _setup_ready_case_with_offers(
        db_session,
        client,
        offer_count=2,
        deposit_due_at=datetime.now(UTC) + timedelta(days=1),
    )
    selected = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
        headers=HEADERS,
        json=_selection_payload(
            offers[0],
            [offers[1]],
            key=f"ds7-binding-tamper-{tamper_kind}",
        ),
    )
    assert selected.status_code == 201, selected.text
    package = _create_executed_assignment_package(db_session, client, case_id)
    _complete_primary_deposit(client, case_id, selected.json())
    case = db_session.get(DispositionCase, UUID(case_id))
    assert case is not None
    _satisfy_transaction_funding_prerequisites(db_session, client, case.transaction_id)

    if tamper_kind == "live_buyer_identity":
        binding = package.terms_snapshot["disposition_buyer_binding"]
        selected_buyer = db_session.get(Buyer, UUID(binding["buyer_id"]))
        assert selected_buyer is not None
        selected_buyer.name = "Changed End Buyer Identity"
    elif tamper_kind == "package_economics":
        package.purchase_price_cents += 1
    else:
        snapshot = dict(package.terms_snapshot)
        binding = dict(snapshot["disposition_buyer_binding"])
        if tamper_kind == "identity_snapshot":
            identity = dict(binding["buyer_identity_snapshot"])
            identity["normalized_name"] = "tamperedbuyer"
            binding["buyer_identity_snapshot"] = identity
        elif tamper_kind == "economics_snapshot":
            economics = dict(binding["offer_economics_snapshot"])
            economics["base_purchase_price_cents"] += 1
            binding["offer_economics_snapshot"] = economics
        else:
            binding["offer_economics_hash"] = "0" * 64
        snapshot["disposition_buyer_binding"] = binding
        package.terms_snapshot = snapshot
    db_session.commit()

    blocked = client.post(
        f"/api/v1/transactions/{case.transaction_id}/close",
        headers=HEADERS,
        json={"outcome": "funded", "notes": "Controlled assignment binding tamper."},
    )
    assert blocked.status_code == 422, blocked.text
    assert "assignment agreement" in blocked.json()["detail"].lower()
    db_session.rollback()
    transaction = db_session.get(Transaction, case.transaction_id)
    assert transaction is not None and transaction.status == "executed"


def test_checkpoint_responsible_user_must_be_active_and_in_the_same_organization(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, _, offers = _setup_ready_case_with_offers(db_session, client, offer_count=2)
    selected = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
        headers=HEADERS,
        json=_selection_payload(offers[0], [offers[1]], key="ds7-checkpoint-user-selection"),
    )
    assert selected.status_code == 201, selected.text
    current = selected.json()["current_selection"]
    inactive = add_user_with_role(
        db_session,
        email="ds7-inactive-checkpoint@example.com",
        display_name="Inactive Checkpoint User",
        role_key="disposition_rep",
    )
    inactive.is_active = False
    other = bootstrap_foundation(
        db_session,
        organization_name="DS7 Checkpoint Other Organization",
        admin_email="ds7-checkpoint-other@example.com",
        admin_name="Other Checkpoint Owner",
    )
    db_session.commit()
    base_payload = {
        "selection_id": current["id"],
        "offer_id": offers[0]["id"],
        "checkpoint_type": "buyer_response",
        "label": "Confirm buyer access window",
        "due_at": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
        "notes": "Controlled responsible-user validation.",
        "evidence": {},
    }
    for user_id, key in (
        (str(inactive.id), "ds7-checkpoint-inactive-user"),
        (str(other.admin_user.id), "ds7-checkpoint-other-org-user"),
    ):
        rejected = client.post(
            f"/api/v1/dispositions/cases/{case_id}/offer-room/checkpoints",
            headers=HEADERS,
            json={
                **base_payload,
                "responsible_user_id": user_id,
                "idempotency_key": key,
            },
        )
        assert rejected.status_code == 422, rejected.text
        assert "responsible user" in rejected.json()["detail"].lower()

    active = add_user_with_role(
        db_session,
        email="ds7-active-checkpoint@example.com",
        display_name="Active Checkpoint User",
        role_key="disposition_rep",
    )
    created = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/checkpoints",
        headers=HEADERS,
        json={
            **base_payload,
            "responsible_user_id": str(active.id),
            "idempotency_key": "ds7-checkpoint-active-user",
        },
    )
    assert created.status_code == 201, created.text
    checkpoint = next(
        item
        for item in created.json()["checkpoints"]
        if item["label"] == "Confirm buyer access window"
    )
    assert checkpoint["responsible_user_id"] == str(active.id)


def test_superseded_and_terminal_checkpoints_are_immutable(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, _, offers = _setup_ready_case_with_offers(db_session, client, offer_count=3)
    first = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
        headers=HEADERS,
        json=_selection_payload(offers[0], [offers[1]], key="ds7-checkpoint-history-v1"),
    )
    assert first.status_code == 201, first.text
    first_selection = first.json()["current_selection"]
    manual = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/checkpoints",
        headers=HEADERS,
        json={
            "selection_id": first_selection["id"],
            "offer_id": offers[0]["id"],
            "checkpoint_type": "buyer_response",
            "label": "Confirm buyer access window",
            "due_at": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
            "notes": "Controlled immutable checkpoint.",
            "evidence": {},
            "idempotency_key": "ds7-immutable-old-checkpoint",
        },
    )
    assert manual.status_code == 201, manual.text
    old_checkpoint = next(
        item
        for item in manual.json()["checkpoints"]
        if item["label"] == "Confirm buyer access window"
    )
    by_id = {item["id"]: item for item in manual.json()["offers"]}
    superseded = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
        headers=HEADERS,
        json=_selection_payload(
            by_id[offers[0]["id"]],
            [by_id[offers[2]["id"]]],
            key="ds7-checkpoint-history-v2",
            expected_selection_lock_version=first_selection["lock_version"],
        ),
    )
    assert superseded.status_code == 201, superseded.text
    cancelled = next(
        item for item in superseded.json()["checkpoints"] if item["id"] == old_checkpoint["id"]
    )
    assert cancelled["status"] == "cancelled"
    stale_update = client.patch(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/checkpoints/{cancelled['id']}",
        headers=HEADERS,
        json={
            "expected_lock_version": cancelled["lock_version"],
            "status": "in_progress",
            "reason": "A superseded checkpoint must remain immutable.",
        },
    )
    assert stale_update.status_code == 422, stale_update.text

    current = superseded.json()["current_selection"]
    current_manual = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/checkpoints",
        headers=HEADERS,
        json={
            "selection_id": current["id"],
            "offer_id": offers[0]["id"],
            "checkpoint_type": "buyer_response",
            "label": "Confirm final buyer access window",
            "due_at": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
            "notes": "Controlled terminal checkpoint.",
            "evidence": {},
            "idempotency_key": "ds7-immutable-terminal-checkpoint",
        },
    )
    assert current_manual.status_code == 201, current_manual.text
    pending = next(
        item
        for item in current_manual.json()["checkpoints"]
        if item["label"] == "Confirm final buyer access window"
    )
    completed = client.patch(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/checkpoints/{pending['id']}",
        headers=HEADERS,
        json={
            "expected_lock_version": pending["lock_version"],
            "status": "completed",
            "evidence": {"confirmation_note": "Buyer access was confirmed and completed."},
            "reason": "Buyer access confirmed.",
        },
    )
    assert completed.status_code == 200, completed.text
    terminal = next(item for item in completed.json()["checkpoints"] if item["id"] == pending["id"])
    assert terminal["status"] == "completed"
    terminal_update = client.patch(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/checkpoints/{terminal['id']}",
        headers=HEADERS,
        json={
            "expected_lock_version": terminal["lock_version"],
            "status": "in_progress",
            "due_at": (datetime.now(UTC) + timedelta(days=5)).isoformat(),
            "reason": "A completed checkpoint must remain immutable.",
        },
    )
    assert terminal_update.status_code == 422, terminal_update.text


def test_deadline_worker_aborts_when_canonical_source_lock_is_contended(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = TestClient(app)
    case_id, _, offers = _setup_ready_case_with_offers(
        db_session,
        client,
        offer_count=2,
        deposit_due_at=datetime.now(UTC) - timedelta(hours=1),
    )
    selected = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/selections",
        headers=HEADERS,
        json=_selection_payload(offers[0], [offers[1]], key="ds7-worker-lock-contention"),
    )
    assert selected.status_code == 201, selected.text
    deposit = next(
        item
        for item in selected.json()["checkpoints"]
        if item["checkpoint_type"] == "buyer_deposit"
        and item["selection_id"] == selected.json()["current_selection"]["id"]
    )
    original_scalar = db_session.scalar
    scalar_calls = 0

    def contended_source_lock(statement: Any, *args: Any, **kwargs: Any) -> Any:
        nonlocal scalar_calls
        scalar_calls += 1
        if scalar_calls == 2:
            return None
        return original_scalar(statement, *args, **kwargs)

    monkeypatch.setattr(db_session, "scalar", contended_source_lock)
    result = process_next_closing_deadline_escalation(db_session, get_settings())
    assert result is None
    assert scalar_calls == 2
    checkpoint = db_session.get(DispositionClosingCheckpoint, UUID(deposit["id"]))
    assert checkpoint is not None and checkpoint.status == "pending"
    alerts = list(
        db_session.scalars(
            select(DispositionDeadlineAlert).where(
                DispositionDeadlineAlert.checkpoint_id == checkpoint.id
            )
        ).all()
    )
    assert alerts == []
