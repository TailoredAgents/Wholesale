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
    EsignProviderConfiguration,
    EsignProviderEvent,
    EsignRecipient,
    Lead,
    Property,
    Transaction,
    TransactionDocument,
    TransactionEvent,
    User,
)
from app.schemas.transactions import (
    EsignEmbeddedSignerRead,
    EsignEnvelopeRead,
    EsignRecipientCreate,
    EsignRecipientRead,
    EsignSendRequest,
    F4IntegrationStatusRead,
    SignWellConnectionRead,
)
from app.services.contract_documents import GeneratedContract, generate_contract_pdf
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

    def create_document(self, payload: dict[str, object]) -> dict[str, Any]:
        response = httpx.post(
            f"{self.settings.esign_base_url.rstrip('/')}/documents",
            headers=self.headers,
            json=payload,
            timeout=self.settings.esign_request_timeout_seconds,
        )
        self._raise(response, "SignWell could not create the signature request")
        return dict(response.json())

    def get_account(self) -> dict[str, Any]:
        response = httpx.get(
            f"{self.settings.esign_base_url.rstrip('/')}/me",
            headers=self.headers,
            timeout=self.settings.esign_request_timeout_seconds,
        )
        self._raise(response, "SignWell account verification failed")
        return dict(response.json())

    def list_webhooks(self) -> list[dict[str, Any]]:
        response = httpx.get(
            f"{self.settings.esign_base_url.rstrip('/')}/hooks",
            headers=self.headers,
            timeout=self.settings.esign_request_timeout_seconds,
        )
        self._raise(response, "SignWell webhook lookup failed")
        payload = response.json()
        if isinstance(payload, list):
            return [dict(item) for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("hooks", "webhooks", "data"):
                items = payload.get(key)
                if isinstance(items, list):
                    return [dict(item) for item in items if isinstance(item, dict)]
        return []

    def create_webhook(self, callback_url: str) -> dict[str, Any]:
        response = httpx.post(
            f"{self.settings.esign_base_url.rstrip('/')}/hooks",
            headers=self.headers,
            json={"callback_url": callback_url},
            timeout=self.settings.esign_request_timeout_seconds,
        )
        self._raise(response, "SignWell webhook registration failed")
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

    @property
    def headers(self) -> dict[str, str]:
        return {"X-Api-Key": self.settings.esign_api_key or ""}

    @staticmethod
    def _raise(response: httpx.Response, prefix: str) -> None:
        if response.is_success:
            return
        detail = response.text[:500]
        raise ValueError(f"{prefix}: HTTP {response.status_code}. {detail}")


def integration_status(
    db: Session | None = None,
    principal: Principal | None = None,
    settings: Settings | None = None,
) -> F4IntegrationStatusRead:
    active = settings or get_settings()
    storage_blockers = list(active.document_storage_configuration_blockers)
    esign_blockers = list(active.esign_configuration_blockers)
    configuration = (
        db.scalar(
            select(EsignProviderConfiguration).where(
                EsignProviderConfiguration.organization_id == principal.organization_id,
                EsignProviderConfiguration.provider == "signwell",
            )
        )
        if db is not None and principal is not None
        else None
    )
    simulated = active.esign_provider == "simulate"
    webhook_connected = simulated or configuration is not None or bool(
        active.esign_signwell_webhook_id
    )
    account_connected = simulated or configuration is not None or bool(
        active.esign_signwell_webhook_id
    )
    if not webhook_connected and not simulated and not esign_blockers:
        esign_blockers.append("Connect SignWell in Transactions")
    return F4IntegrationStatusRead(
        storage_provider=active.document_storage_provider,
        storage_configured=not storage_blockers,
        storage_blockers=storage_blockers,
        malware_scanner=active.document_malware_scanner,
        malware_scan_required=active.document_malware_scan_required,
        esign_provider=active.esign_provider,
        esign_configured=not esign_blockers and webhook_connected,
        esign_test_mode=active.esign_test_mode,
        esign_blockers=esign_blockers,
        esign_account_connected=account_connected,
        esign_account_email=configuration.account_email if configuration else None,
        esign_webhook_connected=webhook_connected,
        esign_webhook_callback_url=active.esign_webhook_callback_url,
        esign_last_verified_at=configuration.last_verified_at if configuration else None,
        esign_linked_template_count=0,
        esign_ready_template_count=3,
    )


def connect_signwell(
    db: Session,
    principal: Principal,
    settings: Settings | None = None,
) -> SignWellConnectionRead:
    active = settings or get_settings()
    blockers = active.esign_configuration_blockers
    if blockers:
        raise ValueError(f"SignWell is missing: {', '.join(blockers)}.")
    if active.esign_provider != "signwell":
        raise ValueError("Set ESIGN_PROVIDER=signwell before connecting SignWell.")

    client = SignWellClient(active)
    account = client.get_account()
    callback_url = active.esign_webhook_callback_url.rstrip("/")
    hooks = client.list_webhooks()
    hook = next(
        (
            item
            for item in hooks
            if str(item.get("callback_url") or "").rstrip("/") == callback_url
        ),
        None,
    )
    webhook_created = hook is None
    if hook is None:
        hook = client.create_webhook(callback_url)
    webhook_id = str(hook.get("id") or "").strip()
    if not webhook_id:
        raise ValueError("SignWell did not return a webhook ID.")

    account_email = first_string(account, "user.email", "contact.email", "email")
    account_name = first_string(account, "account.name", "workspace.name", "name", "user.name")
    now = datetime.now(UTC)
    configuration = db.scalar(
        select(EsignProviderConfiguration).where(
            EsignProviderConfiguration.organization_id == principal.organization_id,
            EsignProviderConfiguration.provider == "signwell",
        )
    )
    if configuration is None:
        configuration = EsignProviderConfiguration(
            organization_id=principal.organization_id,
            configured_by_user_id=principal.user_id,
            provider="signwell",
            webhook_id=webhook_id,
            callback_url=callback_url,
            account_email=account_email,
            account_name=account_name,
            last_verified_at=now,
            provider_details={},
        )
        db.add(configuration)
    else:
        configuration.configured_by_user_id = principal.user_id
        configuration.webhook_id = webhook_id
        configuration.callback_url = callback_url
        configuration.account_email = account_email
        configuration.account_name = account_name
        configuration.last_verified_at = now
    configuration.provider_details = {
        "account_id": first_string(account, "account.id", "workspace.id", "id"),
        "webhook_created_by_stonegate": webhook_created,
    }
    db.commit()
    return SignWellConnectionRead(
        account_connected=True,
        account_email=account_email,
        account_name=account_name,
        webhook_connected=True,
        webhook_callback_url=callback_url,
        webhook_created=webhook_created,
        last_verified_at=now,
        linked_template_count=0,
        ready_template_count=3,
        template_errors=[],
    )


def first_string(payload: dict[str, Any], *paths: str) -> str | None:
    for path in paths:
        value: Any = payload
        for key in path.split("."):
            value = value.get(key) if isinstance(value, dict) else None
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


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
    if active.esign_provider == "signwell":
        configuration = db.scalar(
            select(EsignProviderConfiguration).where(
                EsignProviderConfiguration.organization_id == principal.organization_id,
                EsignProviderConfiguration.provider == "signwell",
            )
        )
        if configuration is None and not active.esign_signwell_webhook_id:
            raise ValueError("Connect SignWell in Transactions before sending a signature request.")
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
    template = db.get(ContractTemplate, package.template_id) if package.template_id else None
    if template is not None and (
        template.deleted_at is not None or template.status != "approved"
    ):
        raise ValueError("The selected internal contract template is not approved.")
    existing = db.scalar(
        select(EsignEnvelope).where(
            EsignEnvelope.contract_package_id == package.id,
            EsignEnvelope.status.not_in(TERMINAL_ENVELOPE_STATUSES),
        )
    )
    if existing is not None:
        raise ValueError("This package already has an active signature request.")
    document_type = str(
        package.terms_snapshot.get("document_type")
        or (template.document_type if template else "purchase_agreement")
    )
    recipients = normalize_contract_recipients(
        db,
        principal,
        payload.recipients,
        document_type,
    )
    recipient_emails = [str(item.email).strip().lower() for item in recipients]
    if len(recipient_emails) != len(set(recipient_emails)):
        raise ValueError("Each signer must use a unique email address.")
    signing_orders = [item.signing_order for item in recipients]
    if len(signing_orders) != len(set(signing_orders)):
        raise ValueError("Each signer must use a unique signing order.")
    property_record = db.get(Property, transaction.property_id)
    generated = generate_contract_pdf(
        transaction,
        package,
        property_record,
        template,
        recipients,
    )
    source_document = store_generated_contract(
        db,
        principal,
        transaction,
        package,
        generated,
        active,
    )
    provider_payload = build_signwell_document_payload(
        transaction,
        package,
        generated,
        payload,
        recipients,
        active,
    )
    if active.esign_provider == "simulate":
        provider_response: dict[str, Any] = {
            "id": f"sim-{uuid4()}",
            "status": "sent",
            "recipients": [
                {
                    "id": str(index),
                    "email": str(item.email),
                    **(
                        {
                            "embedded_signing_url": (
                                f"https://www.signwell.com/docs/simulated-{uuid4()}/"
                            )
                        }
                        if payload.delivery_mode == "in_person"
                        else {}
                    ),
                }
                for index, item in enumerate(recipients, start=1)
            ],
        }
    else:
        provider_response = SignWellClient(active).create_document(provider_payload)
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
        delivery_mode=payload.delivery_mode,
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
    for item in recipients:
        provider_item = provider_recipients.get(str(item.email).strip().lower(), {})
        db.add(
            EsignRecipient(
                organization_id=principal.organization_id,
                esign_envelope_id=envelope.id,
                provider_recipient_id=(
                    str(provider_item.get("id")) if provider_item.get("id") else None
                ),
                embedded_signing_url=(
                    str(provider_item.get("embedded_signing_url"))
                    if provider_item.get("embedded_signing_url")
                    else None
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
            summary=(
                f"Contract package v{package.version_number} prepared for in-person signing."
                if payload.delivery_mode == "in_person"
                else f"Contract package v{package.version_number} sent through SignWell."
            ),
            details={
                "envelope_id": str(envelope.id),
                "provider_document_id": provider_document_id,
                "source_document_id": str(source_document.id),
                "test_mode": envelope.test_mode,
                "delivery_mode": payload.delivery_mode,
            },
            occurred_at=now,
        )
    )
    db.commit()
    return envelope_read(db, envelope)


def preview_contract_for_signature(
    db: Session,
    principal: Principal,
    transaction_id: UUID,
    package_id: UUID,
) -> GeneratedContract | None:
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
    template = db.get(ContractTemplate, package.template_id) if package.template_id else None
    document_type = str(
        package.terms_snapshot.get("document_type")
        or (template.document_type if template else "purchase_agreement")
    )
    recipients = normalize_contract_recipients(
        db,
        principal,
        [
            EsignRecipientCreate(
                placeholder_name=(
                    "Assignee" if document_type == "assignment_contract" else "Seller"
                ),
                name=(
                    "Prospective Assignee"
                    if document_type == "assignment_contract"
                    else package.seller_name
                ),
                email="contract-preview@stonegatehb.com",
                signing_order=1,
            )
        ],
        document_type,
    )
    return generate_contract_pdf(
        transaction,
        package,
        db.get(Property, transaction.property_id),
        template,
        recipients,
    )


def build_signwell_document_payload(
    transaction: Transaction,
    package: ContractPackage,
    generated: GeneratedContract,
    request: EsignSendRequest,
    recipients: list[EsignRecipientCreate],
    settings: Settings,
) -> dict[str, object]:
    provider_recipients = [
        {
            "id": str(index),
            "name": item.name,
            "email": str(item.email),
        }
        for index, item in enumerate(
            sorted(recipients, key=lambda item: item.signing_order),
            start=1,
        )
    ]
    return {
        "test_mode": settings.esign_test_mode,
        "name": f"{generated.title} - {package.seller_name}",
        "subject": request.subject,
        "message": request.message or "",
        "recipients": provider_recipients,
        "files": [
            {
                "name": generated.file_name,
                "file_base64": base64.b64encode(generated.content).decode(),
            }
        ],
        "text_tags": True,
        "draft": False,
        "apply_signing_order": True,
        "reminders": request.delivery_mode == "email",
        "allow_reassign": False,
        "embedded_signing": request.delivery_mode == "in_person",
        "embedded_signing_notifications": request.delivery_mode == "in_person",
        "metadata": {
            "stonegate_transaction_id": str(transaction.id),
            "stonegate_contract_package_id": str(package.id),
        },
    }


def normalize_contract_recipients(
    db: Session,
    principal: Principal,
    requested: list[EsignRecipientCreate],
    document_type: str,
) -> list[EsignRecipientCreate]:
    recipients = sorted(requested, key=lambda item: item.signing_order)
    stonegate_roles = {"stonegate", "buyer", "assignor"}
    has_stonegate = any(
        item.placeholder_name.strip().lower() in stonegate_roles for item in recipients
    )
    if not has_stonegate:
        user = db.get(User, principal.user_id)
        recipients.append(
            EsignRecipientCreate(
                placeholder_name=(
                    "Assignor" if document_type == "assignment_contract" else "Stonegate"
                ),
                name=user.display_name if user else "Stonegate Home Buyers",
                email=principal.email,
                signing_order=max((item.signing_order for item in recipients), default=0) + 1,
            )
        )
    if len(recipients) > 10:
        raise ValueError("A contract package cannot have more than ten signers.")
    return recipients


def store_generated_contract(
    db: Session,
    principal: Principal,
    transaction: Transaction,
    package: ContractPackage,
    generated: GeneratedContract,
    settings: Settings,
) -> TransactionDocument:
    checksum = sha256(generated.content).hexdigest()
    existing = db.scalar(
        select(TransactionDocument).where(
            TransactionDocument.organization_id == principal.organization_id,
            TransactionDocument.transaction_id == transaction.id,
            TransactionDocument.contract_package_id == package.id,
            TransactionDocument.sha256 == checksum,
            TransactionDocument.deleted_at.is_(None),
        )
    )
    if existing is not None:
        return existing
    document_id = uuid4()
    stored = store_content(
        organization_id=principal.organization_id,
        namespace=f"transactions/{transaction.id}",
        record_id=document_id,
        file_name=generated.file_name,
        content_type="application/pdf",
        content=generated.content,
        settings=settings,
    )
    document = TransactionDocument(
        id=document_id,
        organization_id=principal.organization_id,
        transaction_id=transaction.id,
        contract_package_id=package.id,
        uploaded_by_user_id=principal.user_id,
        document_type=f"{generated.document_type}_for_signature",
        title=f"{generated.title} — approved signing copy",
        status="approved",
        file_name=generated.file_name,
        content_type="application/pdf",
        file_size=len(generated.content),
        sha256=checksum,
        file_data=stored.database_bytes,
        storage_provider=stored.provider,
        storage_key=stored.key,
        malware_scan_status=stored.malware_scan_status,
        retention_until=stored.retention_until,
        deleted_at=None,
        occurred_at=datetime.now(UTC),
        notes="Generated internally by Stonegate from the approved contract package.",
    )
    db.add(document)
    db.flush()
    return document


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
        delivery_mode=envelope.delivery_mode,
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
        embedded_signers=[
            EsignEmbeddedSignerRead(
                recipient_id=item.id,
                placeholder_name=item.placeholder_name,
                name=item.name,
                email=item.email,
                signing_order=item.signing_order,
                signing_url=item.embedded_signing_url,
            )
            for item in recipients
            if item.embedded_signing_url
        ],
        created_at=envelope.created_at,
    )


def verify_signwell_event(
    payload: dict[str, Any],
    db: Session | None = None,
    settings: Settings | None = None,
) -> None:
    active = settings or get_settings()
    event_data = payload.get("event")
    if not isinstance(event_data, dict):
        raise ValueError("Invalid SignWell event payload.")
    event_type = str(event_data.get("type") or "").strip()
    event_time = str(event_data.get("time") or "").strip()
    provided = str(event_data.get("hash") or "").strip()
    webhook_ids = {
        item
        for item in (
            [active.esign_signwell_webhook_id]
            + (
                list(
                    db.scalars(
                        select(EsignProviderConfiguration.webhook_id).where(
                            EsignProviderConfiguration.provider == "signwell"
                        )
                    ).all()
                )
                if db is not None
                else []
            )
        )
        if item
    }
    if not webhook_ids or not event_type or not event_time or not provided:
        raise ValueError("Invalid SignWell event signature.")
    verified = any(
        secrets.compare_digest(
            provided,
            hmac.new(
                webhook_id.encode(),
                f"{event_type}@{event_time}".encode(),
                sha256,
            ).hexdigest(),
        )
        for webhook_id in webhook_ids
    )
    if not verified:
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
    template = db.get(ContractTemplate, package.template_id) if package.template_id else None
    template_type = str(
        package.terms_snapshot.get("document_type")
        or (template.document_type if template else "purchase_agreement")
    )
    document_type, file_stem, document_label = {
        "assignment_contract": (
            "assignment_contract",
            "executed-assignment-agreement",
            "assignment agreement",
        ),
        "addendum": ("executed_addendum", "executed-addendum", "contract addendum"),
        "purchase_agreement": (
            "signed_purchase_agreement",
            "signed-purchase-agreement",
            "purchase agreement",
        ),
    }.get(
        template_type,
        ("executed_contract", "executed-contract", "contract"),
    )
    document_id = uuid4()
    file_name = f"{file_stem}-v{package.version_number}.pdf"
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
        document_type=document_type,
        title=f"SignWell completed {document_label} v{package.version_number}",
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
    if template_type == "purchase_agreement":
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
            summary=f"SignWell completed {document_label} package v{package.version_number}.",
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
