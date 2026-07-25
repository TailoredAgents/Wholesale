import base64
import hmac
import secrets
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import Settings, get_settings
from app.models.foundation import (
    ContractPackage,
    ContractTemplate,
    Deal,
    EsignEnvelope,
    EsignProviderEvent,
    EsignRecipient,
    Lead,
    Property,
    Transaction,
    TransactionDocument,
    TransactionEvent,
)
from app.schemas.transactions import (
    EsignEnvelopeRead,
    EsignRecipientRead,
    EsignSendRequest,
    F4IntegrationStatusRead,
)
from app.services.document_storage import store_content

TERMINAL_ENVELOPE_STATUSES = {"completed", "declined", "expired", "cancelled", "error"}
EVENT_STATUS = {
    "document_created": "created",
    "document_sent": "sent",
    "document_viewed": "viewed",
    "document_in_progress": "in_progress",
    "document_signed": "in_progress",
    "document_completed": "completed",
    "document_expired": "expired",
    "document_canceled": "cancelled",
    "document_declined": "declined",
    "document_bounced": "bounced",
    "document_error": "error",
}


class SignWellClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def create_from_template(self, payload: dict[str, object]) -> dict[str, Any]:
        response = httpx.post(
            f"{self.settings.esign_base_url.rstrip('/')}/document_templates/documents",
            headers={"X-Api-Key": self.settings.esign_api_key or ""},
            json=payload,
            timeout=self.settings.esign_request_timeout_seconds,
        )
        self._raise(response, "SignWell could not create the signature request")
        return dict(response.json())

    def get_document(self, document_id: str) -> dict[str, Any]:
        response = httpx.get(
            f"{self.settings.esign_base_url.rstrip('/')}/documents/{document_id}",
            headers={"X-Api-Key": self.settings.esign_api_key or ""},
            timeout=self.settings.esign_request_timeout_seconds,
        )
        self._raise(response, "SignWell could not reconcile the signature request")
        return dict(response.json())

    def completed_pdf(self, document_id: str) -> bytes:
        response = httpx.get(
            f"{self.settings.esign_base_url.rstrip('/')}/documents/{document_id}/completed_pdf",
            headers={"X-Api-Key": self.settings.esign_api_key or ""},
            params={"audit_page": "true", "file_format": "pdf"},
            timeout=self.settings.esign_request_timeout_seconds,
        )
        self._raise(response, "SignWell completed PDF is not available")
        return response.content

    @staticmethod
    def _raise(response: httpx.Response, prefix: str) -> None:
        if response.is_success:
            return
        detail = response.text[:500]
        raise ValueError(f"{prefix}: HTTP {response.status_code}. {detail}")


def integration_status(settings: Settings | None = None) -> F4IntegrationStatusRead:
    active = settings or get_settings()
    storage_blockers = list(active.document_storage_configuration_blockers)
    esign_blockers = list(active.esign_configuration_blockers)
    return F4IntegrationStatusRead(
        storage_provider=active.document_storage_provider,
        storage_configured=not storage_blockers,
        storage_blockers=storage_blockers,
        malware_scanner=active.document_malware_scanner,
        malware_scan_required=active.document_malware_scan_required,
        esign_provider=active.esign_provider,
        esign_configured=not esign_blockers,
        esign_test_mode=active.esign_test_mode,
        esign_blockers=esign_blockers,
    )


def send_contract_for_signature(
    db: Session,
    principal: Principal,
    transaction_id: UUID,
    package_id: UUID,
    payload: EsignSendRequest,
    settings: Settings | None = None,
) -> EsignEnvelopeRead | None:
    active = settings or get_settings()
    blockers = active.esign_configuration_blockers
    if blockers:
        raise ValueError(f"E-signature is missing: {', '.join(blockers)}.")
    transaction = db.scalar(
        select(Transaction).where(
            Transaction.id == transaction_id,
            Transaction.organization_id == principal.organization_id,
        )
    )
    package = db.scalar(
        select(ContractPackage).where(
            ContractPackage.id == package_id,
            ContractPackage.transaction_id == transaction_id,
            ContractPackage.organization_id == principal.organization_id,
        )
    )
    if transaction is None or package is None:
        return None
    if package.status != "approved":
        raise ValueError("Approve this exact contract package before sending it for signature.")
    template = (
        db.get(ContractTemplate, package.template_id) if package.template_id else None
    )
    if (
        template is None
        or template.deleted_at is not None
        or template.status != "approved"
        or not template.esign_provider_template_id
    ):
        raise ValueError("Connect the approved contract template to a SignWell template first.")
    existing = db.scalar(
        select(EsignEnvelope).where(
            EsignEnvelope.contract_package_id == package.id,
            EsignEnvelope.status.not_in(TERMINAL_ENVELOPE_STATUSES),
        )
    )
    if existing is not None:
        raise ValueError("This package already has an active signature request.")
    recipient_emails = [str(item.email).strip().lower() for item in payload.recipients]
    if len(recipient_emails) != len(set(recipient_emails)):
        raise ValueError("Each signer must use a unique email address.")
    signing_orders = [item.signing_order for item in payload.recipients]
    if len(signing_orders) != len(set(signing_orders)):
        raise ValueError("Each signer must use a unique signing order.")
    property_record = db.get(Property, transaction.property_id)
    provider_payload = build_signwell_payload(
        transaction,
        package,
        template,
        property_record,
        payload,
        active,
    )
    if active.esign_provider == "simulate":
        provider_response: dict[str, Any] = {
            "id": f"sim-{uuid4()}",
            "status": "sent",
            "recipients": [
                {"id": str(index), "email": str(item.email)}
                for index, item in enumerate(payload.recipients, start=1)
            ],
        }
    else:
        provider_response = SignWellClient(active).create_from_template(provider_payload)
    provider_document_id = str(provider_response.get("id") or "").strip()
    if not provider_document_id:
        raise ValueError("The e-signature provider did not return a document ID.")
    now = datetime.now(UTC)
    envelope = EsignEnvelope(
        organization_id=principal.organization_id,
        transaction_id=transaction.id,
        contract_package_id=package.id,
        created_by_user_id=principal.user_id,
        completed_document_id=None,
        provider=active.esign_provider,
        provider_document_id=provider_document_id,
        status="sent",
        subject=payload.subject,
        message=payload.message,
        test_mode=active.esign_test_mode or active.esign_provider == "simulate",
        provider_payload=provider_response,
        sent_at=now,
        completed_at=None,
        declined_at=None,
        expired_at=None,
        cancelled_at=None,
        last_provider_event_at=None,
    )
    db.add(envelope)
    db.flush()
    provider_recipients = {
        str(item.get("email", "")).strip().lower(): item
        for item in provider_response.get("recipients", [])
        if isinstance(item, dict)
    }
    for item in payload.recipients:
        provider_item = provider_recipients.get(str(item.email).strip().lower(), {})
        db.add(
            EsignRecipient(
                organization_id=principal.organization_id,
                esign_envelope_id=envelope.id,
                provider_recipient_id=(
                    str(provider_item.get("id")) if provider_item.get("id") else None
                ),
                placeholder_name=item.placeholder_name,
                name=item.name,
                email=str(item.email).lower(),
                signing_order=item.signing_order,
                status="sent",
                viewed_at=None,
                signed_at=None,
                declined_at=None,
            )
        )
    package.status = "sent"
    package.sent_at = now
    transaction.status = "sent"
    transaction.contract_sent_at = now
    db.add(
        TransactionEvent(
            organization_id=principal.organization_id,
            transaction_id=transaction.id,
            lead_id=transaction.lead_id,
            actor_user_id=principal.user_id,
            event_type="esign.sent",
            summary=f"Contract package v{package.version_number} sent through SignWell.",
            details={
                "envelope_id": str(envelope.id),
                "provider_document_id": provider_document_id,
                "test_mode": envelope.test_mode,
            },
            occurred_at=now,
        )
    )
    db.commit()
    return envelope_read(db, envelope)


def build_signwell_payload(
    transaction: Transaction,
    package: ContractPackage,
    template: ContractTemplate,
    property_record: Property | None,
    request: EsignSendRequest,
    settings: Settings,
) -> dict[str, object]:
    values = {
        "seller_name": package.seller_name,
        "buyer_entity_name": package.buyer_entity_name,
        "purchase_price": f"{package.purchase_price_cents / 100:.2f}",
        "earnest_money": (
            f"{package.earnest_money_cents / 100:.2f}"
            if package.earnest_money_cents is not None
            else ""
        ),
        "closing_date": package.closing_date.date().isoformat() if package.closing_date else "",
        "inspection_period_days": (
            str(package.inspection_period_days)
            if package.inspection_period_days is not None
            else ""
        ),
        "special_terms": str(package.terms_snapshot.get("special_terms") or ""),
        "property_address": (
            f"{property_record.street_address}, {property_record.city}, "
            f"{property_record.state} {property_record.postal_code}"
            if property_record
            else ""
        ),
    }
    mapping = template.esign_field_mapping or {}
    template_fields = [
        {"api_id": str(api_id), "value": values[key]}
        for key, api_id in mapping.items()
        if key in values and str(api_id).strip()
    ]
    recipients = [
        {
            "id": str(index),
            "placeholder_name": item.placeholder_name,
            "name": item.name,
            "email": str(item.email),
        }
        for index, item in enumerate(
            sorted(request.recipients, key=lambda item: item.signing_order),
            start=1,
        )
    ]
    return {
        "test_mode": settings.esign_test_mode,
        "template_id": template.esign_provider_template_id or "",
        "name": f"Purchase agreement - {package.seller_name}",
        "subject": request.subject,
        "message": request.message or "",
        "recipients": recipients,
        "apply_signing_order": True,
        "reminders": True,
        "metadata": {
            "stonegate_transaction_id": str(transaction.id),
            "stonegate_contract_package_id": str(package.id),
        },
        "template_fields": template_fields,
    }


def list_envelopes(
    db: Session,
    organization_id: UUID,
    transaction_id: UUID,
) -> list[EsignEnvelopeRead]:
    return [
        envelope_read(db, item)
        for item in db.scalars(
            select(EsignEnvelope)
            .where(
                EsignEnvelope.organization_id == organization_id,
                EsignEnvelope.transaction_id == transaction_id,
            )
            .order_by(EsignEnvelope.created_at.desc())
        ).all()
    ]


def envelope_read(db: Session, envelope: EsignEnvelope) -> EsignEnvelopeRead:
    recipients = db.scalars(
        select(EsignRecipient)
        .where(EsignRecipient.esign_envelope_id == envelope.id)
        .order_by(EsignRecipient.signing_order)
    ).all()
    return EsignEnvelopeRead(
        id=envelope.id,
        contract_package_id=envelope.contract_package_id,
        provider=envelope.provider,
        provider_document_id=envelope.provider_document_id,
        status=envelope.status,
        subject=envelope.subject,
        message=envelope.message,
        test_mode=envelope.test_mode,
        completed_document_id=envelope.completed_document_id,
        sent_at=envelope.sent_at,
        completed_at=envelope.completed_at,
        declined_at=envelope.declined_at,
        expired_at=envelope.expired_at,
        cancelled_at=envelope.cancelled_at,
        recipients=[
            EsignRecipientRead(
                id=item.id,
                placeholder_name=item.placeholder_name,
                name=item.name,
                email=item.email,
                signing_order=item.signing_order,
                status=item.status,
                viewed_at=item.viewed_at,
                signed_at=item.signed_at,
                declined_at=item.declined_at,
            )
            for item in recipients
        ],
        created_at=envelope.created_at,
    )


def verify_signwell_event(
    payload: dict[str, Any],
    settings: Settings | None = None,
) -> None:
    active = settings or get_settings()
    event_data = payload.get("event")
    if not isinstance(event_data, dict):
        raise ValueError("Invalid SignWell event payload.")
    webhook_id = active.esign_signwell_webhook_id
    event_type = str(event_data.get("type") or "").strip()
    event_time = str(event_data.get("time") or "").strip()
    provided = str(event_data.get("hash") or "").strip()
    if not webhook_id or not event_type or not event_time or not provided:
        raise ValueError("Invalid SignWell event signature.")
    expected = hmac.new(
        webhook_id.encode(),
        f"{event_type}@{event_time}".encode(),
        sha256,
    ).hexdigest()
    if not secrets.compare_digest(provided, expected):
        raise ValueError("Invalid SignWell event signature.")


def process_signwell_event(
    db: Session,
    payload: dict[str, Any],
    settings: Settings | None = None,
) -> bool:
    active = settings or get_settings()
    event_data = payload.get("event")
    document_data = payload.get("data", {}).get("object")
    if not isinstance(event_data, dict) or not isinstance(document_data, dict):
        raise ValueError("Invalid SignWell event payload.")
    event_hash = str(event_data.get("hash") or "").strip()
    event_type = str(event_data.get("type") or "").strip()
    provider_document_id = str(document_data.get("id") or "").strip()
    if not event_hash or not event_type or not provider_document_id:
        raise ValueError("SignWell event identifiers are required.")
    related = event_data.get("related_signer")
    related_key = ""
    if isinstance(related, dict):
        related_key = str(related.get("id") or related.get("email") or "")
    provider_event_id = sha256(
        (
            f"{event_hash}:{provider_document_id}:{event_type}:"
            f"{event_data.get('time')}:{related_key}"
        ).encode()
    ).hexdigest()
    envelope = db.scalar(
        select(EsignEnvelope).where(
            EsignEnvelope.provider_document_id == provider_document_id,
            EsignEnvelope.provider.in_(("signwell", "simulate")),
        )
    )
    if envelope is None:
        return False
    duplicate = db.scalar(
        select(EsignProviderEvent.id).where(
            EsignProviderEvent.organization_id == envelope.organization_id,
            EsignProviderEvent.provider == envelope.provider,
            EsignProviderEvent.provider_event_id == provider_event_id,
        )
    )
    if duplicate is not None:
        return True
    occurred_at = datetime.fromtimestamp(
        int(event_data.get("time") or datetime.now(UTC).timestamp()),
        tz=UTC,
    )
    provider_event = EsignProviderEvent(
        organization_id=envelope.organization_id,
        esign_envelope_id=envelope.id,
        provider=envelope.provider,
        provider_event_id=provider_event_id,
        event_type=event_type,
        status="processing",
        payload=payload,
        occurred_at=occurred_at,
        received_at=datetime.now(UTC),
        processed_at=None,
        processing_error=None,
    )
    db.add(provider_event)
    try:
        apply_provider_event(db, envelope, event_type, event_data, document_data, active)
        provider_event.status = "processed"
        provider_event.processed_at = datetime.now(UTC)
        db.commit()
    except Exception as exc:
        provider_event.status = "failed"
        provider_event.processing_error = str(exc)[:2000]
        db.commit()
        raise
    return True


def apply_provider_event(
    db: Session,
    envelope: EsignEnvelope,
    event_type: str,
    event_data: dict[str, Any],
    document_data: dict[str, Any],
    settings: Settings,
) -> None:
    occurred_at = datetime.fromtimestamp(
        int(event_data.get("time") or datetime.now(UTC).timestamp()),
        tz=UTC,
    )
    envelope.last_provider_event_at = occurred_at
    envelope.provider_payload = document_data
    envelope.status = EVENT_STATUS.get(event_type, envelope.status)
    related = event_data.get("related_signer")
    if isinstance(related, dict):
        email = str(related.get("email") or "").strip().lower()
        recipient = db.scalar(
            select(EsignRecipient).where(
                EsignRecipient.esign_envelope_id == envelope.id,
                EsignRecipient.email == email,
            )
        )
        if recipient is not None:
            if event_type == "document_viewed":
                recipient.status = "viewed"
                recipient.viewed_at = occurred_at
            elif event_type == "document_signed":
                recipient.status = "signed"
                recipient.signed_at = occurred_at
            elif event_type == "document_declined":
                recipient.status = "declined"
                recipient.declined_at = occurred_at
    if event_type == "document_completed":
        envelope.completed_at = occurred_at
        for recipient in db.scalars(
            select(EsignRecipient).where(EsignRecipient.esign_envelope_id == envelope.id)
        ).all():
            recipient.status = "signed"
            recipient.signed_at = recipient.signed_at or occurred_at
        complete_envelope(db, envelope, document_data, settings)
    elif event_type == "document_declined":
        envelope.declined_at = occurred_at
    elif event_type == "document_expired":
        envelope.expired_at = occurred_at
    elif event_type == "document_canceled":
        envelope.cancelled_at = occurred_at


def complete_envelope(
    db: Session,
    envelope: EsignEnvelope,
    document_data: dict[str, Any],
    settings: Settings,
) -> None:
    if envelope.completed_document_id is not None:
        return
    if envelope.provider == "simulate":
        encoded = str(document_data.get("completed_pdf_base64") or "")
        content = base64.b64decode(encoded) if encoded else b"%PDF simulated signed agreement"
    else:
        content = SignWellClient(settings).completed_pdf(envelope.provider_document_id)
    transaction = db.get(Transaction, envelope.transaction_id)
    package = db.get(ContractPackage, envelope.contract_package_id)
    if transaction is None or package is None:
        raise ValueError("The completed envelope no longer matches a Stonegate transaction.")
    document_id = uuid4()
    file_name = f"signed-purchase-agreement-v{package.version_number}.pdf"
    stored = store_content(
        organization_id=envelope.organization_id,
        namespace=f"transactions/{transaction.id}",
        record_id=document_id,
        file_name=file_name,
        content_type="application/pdf",
        content=content,
        settings=settings,
    )
    document = TransactionDocument(
        id=document_id,
        organization_id=envelope.organization_id,
        transaction_id=transaction.id,
        contract_package_id=package.id,
        uploaded_by_user_id=envelope.created_by_user_id,
        document_type="signed_purchase_agreement",
        title=f"SignWell completed purchase agreement v{package.version_number}",
        status="final",
        file_name=file_name,
        content_type="application/pdf",
        file_size=len(content),
        sha256=sha256(content).hexdigest(),
        file_data=stored.database_bytes,
        storage_provider=stored.provider,
        storage_key=stored.key,
        malware_scan_status=stored.malware_scan_status,
        retention_until=stored.retention_until,
        deleted_at=None,
        occurred_at=envelope.completed_at or datetime.now(UTC),
        notes=f"Retrieved from {envelope.provider} document {envelope.provider_document_id}.",
    )
    db.add(document)
    db.flush()
    envelope.completed_document_id = document.id
    package.status = "executed"
    package.executed_at = envelope.completed_at or datetime.now(UTC)
    transaction.status = "executed"
    transaction.contract_executed_at = package.executed_at
    lead = db.get(Lead, transaction.lead_id)
    deal = db.get(Deal, transaction.deal_id)
    if lead:
        lead.stage_key = "under_contract"
    if deal:
        deal.stage_key = "under_contract"
    db.add(
        TransactionEvent(
            organization_id=envelope.organization_id,
            transaction_id=transaction.id,
            lead_id=transaction.lead_id,
            actor_user_id=None,
            event_type="esign.completed",
            summary=f"SignWell completed contract package v{package.version_number}.",
            details={
                "envelope_id": str(envelope.id),
                "provider_document_id": envelope.provider_document_id,
                "document_id": str(document.id),
            },
            occurred_at=envelope.completed_at or datetime.now(UTC),
        )
    )


def reconcile_envelope(
    db: Session,
    principal: Principal,
    transaction_id: UUID,
    envelope_id: UUID,
    settings: Settings | None = None,
) -> EsignEnvelopeRead | None:
    active = settings or get_settings()
    envelope = db.scalar(
        select(EsignEnvelope).where(
            EsignEnvelope.id == envelope_id,
            EsignEnvelope.organization_id == principal.organization_id,
            EsignEnvelope.transaction_id == transaction_id,
        )
    )
    if envelope is None:
        return None
    if envelope.provider == "simulate":
        return envelope_read(db, envelope)
    document = SignWellClient(active).get_document(envelope.provider_document_id)
    status = str(document.get("status") or "").lower()
    event_type = {
        "completed": "document_completed",
        "declined": "document_declined",
        "expired": "document_expired",
        "canceled": "document_canceled",
        "cancelled": "document_canceled",
        "pending": "document_in_progress",
        "sent": "document_sent",
    }.get(status, "document_in_progress")
    process_signwell_event(
        db,
        {
            "event": {
                "hash": f"reconcile:{envelope.provider_document_id}:{status}",
                "time": int(datetime.now(UTC).timestamp()),
                "type": event_type,
            },
            "data": {"object": document},
        },
        active,
    )
    db.refresh(envelope)
    return envelope_read(db, envelope)
