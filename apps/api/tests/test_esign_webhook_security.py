import hmac
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.main import app
from app.models.foundation import (
    ContractPackage,
    EsignEnvelope,
    EsignProviderConfiguration,
    EsignProviderEvent,
    EsignRecipient,
    Organization,
    Transaction,
    TransactionDocument,
    User,
)
from app.services.bootstrap import bootstrap_foundation
from tests.test_transactions import (
    HEADERS,
    OWNER_EMAIL,
    approve_purchase_package,
    setup_transaction,
)


@pytest.fixture(autouse=True)
def clear_global_signwell_webhook_id(monkeypatch: MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.delenv("ESIGN_SIGNWELL_WEBHOOK_ID", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def create_workspace(db: Session, suffix: str) -> tuple[Organization, User]:
    result = bootstrap_foundation(
        db,
        organization_name=f"Webhook Workspace {suffix}",
        admin_email=f"owner-{suffix.lower()}@example.com",
        admin_name=f"Owner {suffix}",
    )
    assert result.admin_user is not None
    return result.organization, result.admin_user


def configure_signwell(db: Session, organization: Organization, user: User, secret: str) -> None:
    db.add(
        EsignProviderConfiguration(
            organization_id=organization.id,
            configured_by_user_id=user.id,
            provider="signwell",
            webhook_id=secret,
            callback_url="https://api.example.com/api/v1/webhooks/esign/signwell",
            account_email=user.email,
            account_name=organization.name,
            last_verified_at=datetime.now(UTC),
            provider_details={},
        )
    )
    db.commit()


def create_envelope(
    db: Session,
    organization: Organization,
    user: User,
    *,
    provider_document_id: str,
    status: str = "sent",
    last_provider_event_at: datetime | None = None,
    recipient_status: str = "pending",
    signed_at: datetime | None = None,
    transaction_id: UUID | None = None,
    contract_package_id: UUID | None = None,
) -> tuple[EsignEnvelope, EsignRecipient]:
    if transaction_id is None or contract_package_id is None:
        transaction, package = create_assignment_transaction(db, organization, user)
        transaction_id = transaction.id
        contract_package_id = package.id
    envelope = EsignEnvelope(
        organization_id=organization.id,
        transaction_id=transaction_id,
        contract_package_id=contract_package_id,
        created_by_user_id=user.id,
        completed_document_id=None,
        provider="signwell",
        provider_document_id=provider_document_id,
        delivery_mode="email",
        status=status,
        subject="Purchase agreement",
        message=None,
        test_mode=True,
        provider_payload={"id": provider_document_id, "status": status},
        sent_at=datetime.now(UTC),
        completed_at=None,
        declined_at=None,
        expired_at=None,
        cancelled_at=None,
        last_provider_event_at=last_provider_event_at,
    )
    db.add(envelope)
    db.flush()
    recipient = EsignRecipient(
        organization_id=organization.id,
        esign_envelope_id=envelope.id,
        provider_recipient_id="signer-1",
        embedded_signing_url=None,
        placeholder_name="Seller",
        name="Jane Seller",
        email="jane@example.com",
        signing_order=1,
        status=recipient_status,
        viewed_at=None,
        signed_at=signed_at,
        declined_at=None,
    )
    db.add(recipient)
    db.commit()
    return envelope, recipient


def test_signwell_webhook_rejects_oversized_body_before_json_parsing(
    api_db_override: None,
) -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/webhooks/esign/signwell",
        headers={"Content-Type": "application/json"},
        content=b'{"padding":"' + (b"x" * 1_000_000) + b'"}',
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "SignWell webhook payload is too large."


def create_assignment_transaction(
    db: Session,
    organization: Organization,
    user: User,
) -> tuple[Transaction, ContractPackage]:
    lead_id = uuid4()
    property_id = uuid4()
    transaction = Transaction(
        organization_id=organization.id,
        deal_id=uuid4(),
        lead_id=lead_id,
        property_id=property_id,
        contact_id=uuid4(),
        owner_user_id=user.id,
        coordinator_user_id=None,
        compensation_plan_version_id=None,
        disposition_operating_mode_id=None,
        status="contract_sent",
        contract_type="assignment",
        purchase_price_cents=17_000_000,
        assignment_fee_cents=None,
        earnest_money_cents=100_000,
        title_company=None,
        closing_date=None,
        inspection_period_days=7,
        earnest_money_due_at=None,
        earnest_money_paid_at=None,
        due_diligence_deadline=None,
        title_opened_at=None,
        title_cleared_at=None,
        assignment_deadline=None,
        funded_at=None,
        closed_at=None,
        cancelled_at=None,
        contract_sent_at=datetime.now(UTC),
        contract_executed_at=None,
        notes=None,
        transaction_metadata={"fixture": "esign_failure_atomicity"},
    )
    db.add(transaction)
    db.flush()
    package = ContractPackage(
        organization_id=organization.id,
        transaction_id=transaction.id,
        lead_id=lead_id,
        property_id=property_id,
        template_id=None,
        created_by_user_id=user.id,
        approval_request_id=None,
        version_number=1,
        status="sent",
        seller_name="Jane Seller",
        buyer_entity_name="Stonegate Acquisitions LLC",
        purchase_price_cents=17_000_000,
        earnest_money_cents=100_000,
        closing_date=None,
        inspection_period_days=7,
        terms_snapshot={"document_type": "assignment_contract"},
        notes=None,
        approved_at=datetime.now(UTC),
        sent_at=datetime.now(UTC),
        executed_at=None,
        voided_at=None,
    )
    db.add(package)
    db.commit()
    return transaction, package


def signwell_event(
    secret: str,
    *,
    event_type: str,
    event_time: int,
    provider_document_id: str,
    related_signer: bool = False,
    related_signer_id: str = "signer-1",
    related_signer_email: str = "jane@example.com",
    document_status: str = "in_progress",
) -> dict[str, object]:
    event: dict[str, object] = {
        "hash": hmac.new(
            secret.encode(),
            f"{event_type}@{event_time}".encode(),
            sha256,
        ).hexdigest(),
        "time": event_time,
        "type": event_type,
    }
    if related_signer:
        event["related_signer"] = {
            "id": related_signer_id,
            "email": related_signer_email,
        }
    return {
        "event": event,
        "data": {"object": {"id": provider_document_id, "status": document_status}},
    }


def test_organization_webhook_credential_cannot_mutate_another_workspace(
    db_session: Session,
    api_db_override: None,
) -> None:
    first_org, first_user = create_workspace(db_session, "Alpha")
    second_org, second_user = create_workspace(db_session, "Bravo")
    configure_signwell(db_session, first_org, first_user, "alpha-webhook-secret")
    configure_signwell(db_session, second_org, second_user, "bravo-webhook-secret")
    envelope, recipient = create_envelope(
        db_session,
        second_org,
        second_user,
        provider_document_id="bravo-document",
    )
    event_time = int(datetime(2026, 8, 8, 14, tzinfo=UTC).timestamp())
    client = TestClient(app)

    cross_workspace = client.post(
        "/api/v1/webhooks/esign/signwell",
        json=signwell_event(
            "alpha-webhook-secret",
            event_type="document_viewed",
            event_time=event_time,
            provider_document_id=envelope.provider_document_id,
            related_signer=True,
        ),
    )
    assert cross_workspace.status_code == 401
    db_session.expire_all()
    stored_envelope = db_session.get(EsignEnvelope, envelope.id)
    stored_recipient = db_session.get(EsignRecipient, recipient.id)
    assert stored_envelope is not None
    assert stored_recipient is not None
    assert stored_envelope.status == "sent"
    assert stored_recipient.status == "pending"
    assert list(db_session.scalars(select(EsignProviderEvent)).all()) == []

    correctly_scoped = client.post(
        "/api/v1/webhooks/esign/signwell",
        json=signwell_event(
            "bravo-webhook-secret",
            event_type="document_viewed",
            event_time=event_time,
            provider_document_id=envelope.provider_document_id,
            related_signer=True,
        ),
    )
    assert correctly_scoped.status_code == 200, correctly_scoped.text
    assert correctly_scoped.json() == {"received": True, "matched": True}
    db_session.expire_all()
    stored_envelope = db_session.get(EsignEnvelope, envelope.id)
    stored_recipient = db_session.get(EsignRecipient, recipient.id)
    assert stored_envelope is not None
    assert stored_recipient is not None
    assert stored_envelope.status == "viewed"
    assert stored_recipient.status == "viewed"


def test_stale_and_out_of_order_events_are_audited_without_state_regression(
    db_session: Session,
    api_db_override: None,
) -> None:
    organization, user = create_workspace(db_session, "Order")
    configure_signwell(db_session, organization, user, "order-webhook-secret")
    applied_at = datetime(2026, 8, 8, 15, tzinfo=UTC)
    envelope, recipient = create_envelope(
        db_session,
        organization,
        user,
        provider_document_id="ordered-document",
        status="in_progress",
        last_provider_event_at=applied_at,
        recipient_status="signed",
        signed_at=applied_at,
    )
    client = TestClient(app)

    stale = client.post(
        "/api/v1/webhooks/esign/signwell",
        json=signwell_event(
            "order-webhook-secret",
            event_type="document_viewed",
            event_time=int((applied_at - timedelta(minutes=1)).timestamp()),
            provider_document_id=envelope.provider_document_id,
            related_signer=True,
        ),
    )
    out_of_order = client.post(
        "/api/v1/webhooks/esign/signwell",
        json=signwell_event(
            "order-webhook-secret",
            event_type="document_sent",
            event_time=int((applied_at + timedelta(minutes=1)).timestamp()),
            provider_document_id=envelope.provider_document_id,
        ),
    )
    assert stale.status_code == 200, stale.text
    assert out_of_order.status_code == 200, out_of_order.text

    db_session.expire_all()
    stored_envelope = db_session.get(EsignEnvelope, envelope.id)
    stored_recipient = db_session.get(EsignRecipient, recipient.id)
    assert stored_envelope is not None
    assert stored_recipient is not None
    assert stored_envelope.status == "in_progress"
    assert stored_envelope.provider_payload["status"] == "in_progress"
    assert stored_envelope.last_provider_event_at is not None
    assert int(stored_envelope.last_provider_event_at.replace(tzinfo=UTC).timestamp()) == int(
        applied_at.timestamp()
    )
    assert stored_recipient.status == "signed"
    assert stored_recipient.signed_at is not None
    assert int(stored_recipient.signed_at.replace(tzinfo=UTC).timestamp()) == int(
        applied_at.timestamp()
    )
    events = list(
        db_session.scalars(
            select(EsignProviderEvent).order_by(EsignProviderEvent.occurred_at)
        ).all()
    )
    assert [event.status for event in events] == ["processed", "ignored_out_of_order"]
    assert all(event.processed_at is not None for event in events)
    assert events[0].payload["event"]["type"] == "document_viewed"
    assert events[1].payload["event"]["type"] == "document_sent"


def test_out_of_order_signer_events_preserve_each_recipient_and_envelope_progress(
    db_session: Session,
    api_db_override: None,
) -> None:
    organization, user = create_workspace(db_session, "SignerOrder")
    configure_signwell(db_session, organization, user, "signer-order-secret")
    envelope, first_recipient = create_envelope(
        db_session,
        organization,
        user,
        provider_document_id="signer-order-document",
    )
    second_recipient = EsignRecipient(
        organization_id=organization.id,
        esign_envelope_id=envelope.id,
        provider_recipient_id="signer-2",
        embedded_signing_url=None,
        placeholder_name="Seller 2",
        name="John Seller",
        email="john@example.com",
        signing_order=2,
        status="pending",
        viewed_at=None,
        signed_at=None,
        declined_at=None,
    )
    db_session.add(second_recipient)
    db_session.commit()
    newer_time = datetime(2026, 8, 8, 17, tzinfo=UTC)
    client = TestClient(app)

    first = client.post(
        "/api/v1/webhooks/esign/signwell",
        json=signwell_event(
            "signer-order-secret",
            event_type="document_signed",
            event_time=int(newer_time.timestamp()),
            provider_document_id=envelope.provider_document_id,
            related_signer=True,
        ),
    )
    second = client.post(
        "/api/v1/webhooks/esign/signwell",
        json=signwell_event(
            "signer-order-secret",
            event_type="document_signed",
            event_time=int((newer_time - timedelta(minutes=1)).timestamp()),
            provider_document_id=envelope.provider_document_id,
            related_signer=True,
            related_signer_id="signer-2",
            related_signer_email="john@example.com",
        ),
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    db_session.expire_all()
    stored_envelope = db_session.get(EsignEnvelope, envelope.id)
    stored_first = db_session.get(EsignRecipient, first_recipient.id)
    stored_second = db_session.get(EsignRecipient, second_recipient.id)
    assert stored_envelope is not None and stored_envelope.status == "in_progress"
    assert stored_envelope.last_provider_event_at is not None
    assert int(stored_envelope.last_provider_event_at.replace(tzinfo=UTC).timestamp()) == int(
        newer_time.timestamp()
    )
    assert stored_first is not None and stored_first.status == "signed"
    assert stored_second is not None and stored_second.status == "signed"


def test_global_single_workspace_webhook_path_is_idempotent(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("ESIGN_SIGNWELL_WEBHOOK_ID", "global-webhook-secret")
    get_settings.cache_clear()
    organization, user = create_workspace(db_session, "Global")
    envelope, recipient = create_envelope(
        db_session,
        organization,
        user,
        provider_document_id="global-document",
    )
    payload = signwell_event(
        "global-webhook-secret",
        event_type="document_viewed",
        event_time=int(datetime(2026, 8, 8, 16, tzinfo=UTC).timestamp()),
        provider_document_id=envelope.provider_document_id,
        related_signer=True,
    )
    client = TestClient(app)

    first = client.post("/api/v1/webhooks/esign/signwell", json=payload)
    duplicate = client.post("/api/v1/webhooks/esign/signwell", json=payload)
    assert first.status_code == 200, first.text
    assert duplicate.status_code == 200, duplicate.text
    assert first.json() == duplicate.json() == {"received": True, "matched": True}

    db_session.expire_all()
    stored_envelope = db_session.get(EsignEnvelope, envelope.id)
    stored_recipient = db_session.get(EsignRecipient, recipient.id)
    assert stored_envelope is not None
    assert stored_recipient is not None
    assert stored_envelope.status == "viewed"
    assert stored_recipient.status == "viewed"
    events = list(db_session.scalars(select(EsignProviderEvent)).all())
    assert len(events) == 1
    assert events[0].status == "processed"


def test_failed_completion_is_atomic_and_exact_retry_finishes_execution(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    _, transaction_id = setup_transaction(db_session, client)
    package_payload = approve_purchase_package(client, transaction_id)
    transaction = db_session.get(Transaction, UUID(transaction_id))
    package = db_session.get(ContractPackage, UUID(str(package_payload["id"])))
    user = db_session.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert transaction is not None and package is not None and user is not None
    organization = db_session.get(Organization, transaction.organization_id)
    assert organization is not None
    configure_signwell(db_session, organization, user, "atomic-webhook-secret")
    marked_sent = client.post(
        f"/api/v1/transactions/{transaction.id}/contract-packages/{package.id}/mark-sent",
        headers=HEADERS,
    )
    assert marked_sent.status_code == 200, marked_sent.text
    envelope, recipient = create_envelope(
        db_session,
        organization,
        user,
        provider_document_id="atomic-document",
        status="in_progress",
        recipient_status="viewed",
        transaction_id=transaction.id,
        contract_package_id=package.id,
    )
    completed_pdf = b"%PDF completed assignment with audit evidence"
    download_attempts = 0

    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        nonlocal download_attempts
        del kwargs
        assert url.endswith("/documents/atomic-document/completed_pdf")
        download_attempts += 1
        request = httpx.Request("GET", url)
        if download_attempts == 1:
            return httpx.Response(503, request=request, text="temporarily unavailable")
        return httpx.Response(200, request=request, content=completed_pdf)

    monkeypatch.setattr(httpx, "get", fake_get)
    event_time = int(datetime(2026, 8, 8, 17, tzinfo=UTC).timestamp())
    payload = signwell_event(
        "atomic-webhook-secret",
        event_type="document_completed",
        event_time=event_time,
        provider_document_id=envelope.provider_document_id,
        document_status="completed",
    )
    failed = client.post("/api/v1/webhooks/esign/signwell", json=payload)
    assert failed.status_code == 422, failed.text
    assert "completed PDF is not available" in failed.json()["detail"]

    db_session.expire_all()
    failed_envelope = db_session.get(EsignEnvelope, envelope.id)
    failed_recipient = db_session.get(EsignRecipient, recipient.id)
    failed_package = db_session.get(ContractPackage, package.id)
    failed_transaction = db_session.get(Transaction, transaction.id)
    assert failed_envelope is not None
    assert failed_recipient is not None
    assert failed_package is not None
    assert failed_transaction is not None
    assert failed_envelope.status == "in_progress"
    assert failed_envelope.completed_at is None
    assert failed_envelope.completed_document_id is None
    assert failed_recipient.status == "viewed"
    assert failed_recipient.signed_at is None
    assert failed_package.status == "sent"
    assert failed_package.executed_at is None
    assert failed_transaction.status == "sent"
    assert list(db_session.scalars(select(TransactionDocument)).all()) == []
    provider_events = list(db_session.scalars(select(EsignProviderEvent)).all())
    assert len(provider_events) == 1
    assert provider_events[0].status == "failed"
    assert provider_events[0].processed_at is not None
    assert "completed PDF is not available" in (provider_events[0].processing_error or "")

    retried = client.post("/api/v1/webhooks/esign/signwell", json=payload)
    duplicate = client.post("/api/v1/webhooks/esign/signwell", json=payload)
    assert retried.status_code == 200, retried.text
    assert duplicate.status_code == 200, duplicate.text
    assert retried.json() == duplicate.json() == {"received": True, "matched": True}
    assert download_attempts == 2

    db_session.expire_all()
    completed_envelope = db_session.get(EsignEnvelope, envelope.id)
    completed_recipient = db_session.get(EsignRecipient, recipient.id)
    completed_package = db_session.get(ContractPackage, package.id)
    completed_transaction = db_session.get(Transaction, transaction.id)
    assert completed_envelope is not None
    assert completed_recipient is not None
    assert completed_package is not None
    assert completed_transaction is not None
    assert completed_envelope.status == "completed"
    assert completed_envelope.completed_at is not None
    assert completed_recipient.status == "signed"
    assert completed_recipient.signed_at is not None
    assert completed_package.status == "executed"
    assert completed_transaction.status == "executed"
    documents = list(db_session.scalars(select(TransactionDocument)).all())
    assert len(documents) == 1
    assert documents[0].status == "executed"
    assert documents[0].file_data == completed_pdf
    assert completed_envelope.completed_document_id == documents[0].id
    provider_events = list(db_session.scalars(select(EsignProviderEvent)).all())
    assert len(provider_events) == 1
    assert provider_events[0].status == "processed"
    assert provider_events[0].processing_error is None
