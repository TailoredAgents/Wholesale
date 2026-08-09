import base64
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any, Literal
from uuid import UUID, uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import Settings, get_settings
from app.domain.assets import require_house_workflow
from app.models.foundation import (
    AuditEvent,
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
    EsignDraftAbandonRequest,
    EsignDraftRecoveryRequest,
    EsignEmbeddedSignerRead,
    EsignEnvelopeRead,
    EsignRecipientCreate,
    EsignRecipientRead,
    EsignSendRequest,
    F4IntegrationStatusRead,
    SignWellConnectionRead,
)
from app.services.contract_authority import (
    ACCEPTABLE_EXECUTION_SCAN_STATUSES,
    package_document_type,
    validate_purchase_contract_authority,
)
from app.services.contract_documents import GeneratedContract, generate_contract_pdf
from app.services.document_storage import store_content

TERMINAL_ENVELOPE_STATUSES = {"completed", "declined", "expired", "cancelled", "error"}
TERMINAL_TRANSACTION_STATUSES = {"cancelled", "canceled", "closed", "funded"}
TERMINAL_LEAD_STAGES = {"dead", "disqualified", "lost", "closed"}
ENVELOPE_STATUS_ORDER = {
    "draft": -1,
    "created": 0,
    "sent": 1,
    "viewed": 2,
    "in_progress": 3,
}
EVENT_STATUS = {
    "document_draft": "draft",
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


@dataclass(frozen=True)
class SignWellWebhookVerification:
    organization_id: UUID | None
    source: Literal["organization", "global", "internal"]


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

    def send_document(self, document_id: str) -> dict[str, Any]:
        response = httpx.post(
            f"{self.settings.esign_base_url.rstrip('/')}/documents/{document_id}/send",
            headers=self.headers,
            timeout=self.settings.esign_request_timeout_seconds,
        )
        self._raise(response, "SignWell could not send the signature request")
        if not response.content:
            return {}
        payload = response.json()
        return dict(payload) if isinstance(payload, dict) else {}

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
    webhook_connected = (
        simulated or configuration is not None or bool(active.esign_signwell_webhook_id)
    )
    account_connected = (
        simulated or configuration is not None or bool(active.esign_signwell_webhook_id)
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
        (item for item in hooks if str(item.get("callback_url") or "").rstrip("/") == callback_url),
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
        select(Transaction)
        .where(
            Transaction.id == transaction_id,
            Transaction.organization_id == principal.organization_id,
        )
        .with_for_update(of=Transaction)
    )
    if transaction is None:
        return None
    require_house_transaction_workflow(db, transaction)
    package = db.scalar(
        select(ContractPackage)
        .where(
            ContractPackage.id == package_id,
            ContractPackage.transaction_id == transaction_id,
            ContractPackage.organization_id == principal.organization_id,
        )
        .with_for_update(of=ContractPackage)
    )
    if package is None:
        return None
    template = db.get(ContractTemplate, package.template_id) if package.template_id else None
    if template is not None and (template.deleted_at is not None or template.status != "approved"):
        raise ValueError("The selected internal contract template is not approved.")
    existing = db.scalar(
        select(EsignEnvelope).where(
            EsignEnvelope.contract_package_id == package.id,
            EsignEnvelope.status.not_in(TERMINAL_ENVELOPE_STATUSES),
        )
    )
    if existing is not None:
        if package.status == "sending" and existing.status == "draft":
            validate_purchase_contract_authority(
                db,
                transaction,
                package,
                gate="resuming the saved signature draft",
            )
            requested_recipients = normalize_contract_recipients(
                db,
                principal,
                payload.recipients,
                package_document_type(package),
            )
            ensure_saved_draft_matches_request(db, existing, payload, requested_recipients)
            return send_saved_esign_draft(
                db,
                principal,
                transaction,
                package,
                existing,
                active,
            )
        if existing.status in {"sending", "send_uncertain"}:
            raise ValueError(
                "This signature request may already have been sent. Reconcile its provider "
                "status before taking another action."
            )
        if existing.status in {"creating_draft", "draft_creation_uncertain"}:
            raise ValueError(
                "The provider draft outcome is uncertain. Verify the SignWell account before "
                "creating another contract package."
            )
        raise ValueError("This package already has an active signature request.")
    if package.status != "approved":
        raise ValueError("Approve this exact contract package before sending it for signature.")
    validate_purchase_contract_authority(
        db,
        transaction,
        package,
        gate="reserving the signature request",
    )
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
    now = datetime.now(UTC)
    envelope = EsignEnvelope(
        organization_id=principal.organization_id,
        transaction_id=transaction.id,
        contract_package_id=package.id,
        created_by_user_id=principal.user_id,
        completed_document_id=None,
        provider=active.esign_provider,
        provider_document_id=f"intent-{uuid4()}",
        delivery_mode=payload.delivery_mode,
        status="creating_draft",
        subject=payload.subject,
        message=payload.message,
        test_mode=active.esign_test_mode or active.esign_provider == "simulate",
        provider_payload={
            "phase": "creating_draft",
            "source_document_id": str(source_document.id),
        },
        sent_at=None,
        completed_at=None,
        declined_at=None,
        expired_at=None,
        cancelled_at=None,
        last_provider_event_at=None,
    )
    db.add(envelope)
    db.flush()
    for item in recipients:
        db.add(
            EsignRecipient(
                organization_id=principal.organization_id,
                esign_envelope_id=envelope.id,
                provider_recipient_id=None,
                embedded_signing_url=None,
                placeholder_name=item.placeholder_name,
                name=item.name,
                email=str(item.email).lower(),
                signing_order=item.signing_order,
                status="created",
                viewed_at=None,
                signed_at=None,
                declined_at=None,
            )
        )
    package.status = "sending"
    db.add(
        TransactionEvent(
            organization_id=principal.organization_id,
            transaction_id=transaction.id,
            lead_id=transaction.lead_id,
            actor_user_id=principal.user_id,
            event_type="esign.send_reserved",
            summary=f"Reserved contract package v{package.version_number} for e-signature.",
            details={
                "envelope_id": str(envelope.id),
                "source_document_id": str(source_document.id),
                "delivery_mode": payload.delivery_mode,
            },
            occurred_at=now,
        )
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("This package already has an active signature request.") from exc

    if active.esign_provider == "simulate":
        provider_response: dict[str, Any] = {
            "id": f"sim-{uuid4()}",
            "status": "draft",
            "recipients": [
                {
                    "id": str(index),
                    "email": str(item.email),
                }
                for index, item in enumerate(recipients, start=1)
            ],
        }
    else:
        try:
            provider_response = SignWellClient(active).create_document(provider_payload)
        except Exception as exc:
            mark_esign_intent_uncertain(
                db,
                envelope.id,
                status="draft_creation_uncertain",
                expected_status="creating_draft",
                error=exc,
            )
            raise ValueError(
                "SignWell draft creation did not complete cleanly. No automatic retry was "
                "attempted; verify the SignWell account before continuing."
            ) from exc
    provider_document_id = str(provider_response.get("id") or "").strip()
    if not provider_document_id:
        error = ValueError("The e-signature provider did not return a document ID.")
        mark_esign_intent_uncertain(
            db,
            envelope.id,
            status="draft_creation_uncertain",
            expected_status="creating_draft",
            error=error,
            provider_payload=provider_response,
        )
        raise error
    persisted_envelope = db.scalar(
        select(EsignEnvelope)
        .where(EsignEnvelope.id == envelope.id)
        .with_for_update(of=EsignEnvelope)
    )
    if persisted_envelope is None:
        raise ValueError("The durable signature-send reservation is unavailable.")
    if (
        persisted_envelope.status != "creating_draft"
        or not persisted_envelope.provider_document_id.startswith("intent-")
    ):
        db.rollback()
        raise ValueError(
            "The signature intent changed while SignWell created the draft. Verify and attach "
            "the returned provider document before any further action."
        )
    persisted_envelope.provider_document_id = provider_document_id
    persisted_envelope.provider_payload = {
        **provider_response,
        "phase": "draft",
        "source_document_id": str(source_document.id),
    }
    persisted_envelope.status = "draft"
    provider_recipients = {
        str(item.get("email", "")).strip().lower(): item
        for item in provider_response.get("recipients", [])
        if isinstance(item, dict)
    }
    update_esign_recipient_provider_data(
        db,
        persisted_envelope.id,
        provider_recipients,
        status="created",
    )
    db.commit()
    return send_saved_esign_draft(
        db,
        principal,
        transaction,
        package,
        persisted_envelope,
        active,
    )


def ensure_saved_draft_matches_request(
    db: Session,
    envelope: EsignEnvelope,
    payload: EsignSendRequest,
    recipients: list[EsignRecipientCreate],
) -> None:
    saved_recipients = list(
        db.scalars(
            select(EsignRecipient)
            .where(EsignRecipient.esign_envelope_id == envelope.id)
            .order_by(EsignRecipient.signing_order)
        )
    )
    saved = [
        (
            item.placeholder_name,
            item.name,
            item.email.strip().lower(),
            item.signing_order,
        )
        for item in saved_recipients
    ]
    requested = [
        (
            item.placeholder_name,
            item.name,
            str(item.email).strip().lower(),
            item.signing_order,
        )
        for item in sorted(recipients, key=lambda item: item.signing_order)
    ]
    if (
        envelope.subject != payload.subject
        or envelope.message != payload.message
        or envelope.delivery_mode != payload.delivery_mode
        or saved != requested
    ):
        raise ValueError(
            "The saved SignWell draft must be resumed with the exact original subject, "
            "message, delivery mode, and signer list."
        )


def update_esign_recipient_provider_data(
    db: Session,
    envelope_id: UUID,
    provider_recipients: dict[str, dict[str, Any]],
    *,
    status: str,
) -> None:
    for recipient in db.scalars(
        select(EsignRecipient).where(EsignRecipient.esign_envelope_id == envelope_id)
    ).all():
        provider_item = provider_recipients.get(recipient.email.strip().lower(), {})
        if provider_item.get("id"):
            recipient.provider_recipient_id = str(provider_item["id"])
        if provider_item.get("embedded_signing_url"):
            recipient.embedded_signing_url = str(provider_item["embedded_signing_url"])
        if status != "sent" or recipient.status in {"created", "sent"}:
            recipient.status = status


def mark_esign_intent_uncertain(
    db: Session,
    envelope_id: UUID,
    *,
    status: str,
    expected_status: str,
    error: Exception,
    provider_payload: dict[str, Any] | None = None,
) -> bool:
    db.rollback()
    envelope = db.scalar(
        select(EsignEnvelope)
        .where(EsignEnvelope.id == envelope_id)
        .with_for_update(of=EsignEnvelope)
    )
    if envelope is None:
        return False
    if envelope.status != expected_status:
        db.rollback()
        return False
    stored_payload = {**(envelope.provider_payload or {}), **(provider_payload or {})}
    stored_payload.update({"phase": status, "error": str(error)[:500]})
    envelope.provider_payload = stored_payload
    envelope.status = status
    db.commit()
    return True


def finalize_local_esign_send(
    db: Session,
    envelope: EsignEnvelope,
    *,
    occurred_at: datetime,
    actor_user_id: UUID | None,
) -> None:
    """Idempotently advance the local package after provider delivery is evidenced."""
    transaction = db.scalar(
        select(Transaction)
        .where(Transaction.id == envelope.transaction_id)
        .with_for_update(of=Transaction)
    )
    package = db.scalar(
        select(ContractPackage)
        .where(ContractPackage.id == envelope.contract_package_id)
        .with_for_update(of=ContractPackage)
    )
    if transaction is None or package is None:
        raise ValueError("The signature request no longer matches a Stonegate transaction.")
    envelope.sent_at = envelope.sent_at or occurred_at
    # A webhook may have already finalized the same provider delivery before the
    # synchronous API response returns. Once that durable evidence exists, later
    # offer-authority changes must not relabel or reject the completed send.
    if package.status in {"sent", "executed"}:
        return
    validate_purchase_contract_authority(
        db,
        transaction,
        package,
        gate="recording provider delivery",
    )
    if package.status != "sending":
        raise ValueError("The contract package is not reserved for this signature request.")
    package.status = "sent"
    package.sent_at = package.sent_at or occurred_at
    transaction.status = "sent"
    transaction.contract_sent_at = transaction.contract_sent_at or occurred_at
    db.add(
        TransactionEvent(
            organization_id=envelope.organization_id,
            transaction_id=transaction.id,
            lead_id=transaction.lead_id,
            actor_user_id=actor_user_id,
            event_type="esign.sent",
            summary=(
                f"Contract package v{package.version_number} prepared for in-person signing."
                if envelope.delivery_mode == "in_person"
                else f"Contract package v{package.version_number} sent through SignWell."
            ),
            details={
                "envelope_id": str(envelope.id),
                "provider_document_id": envelope.provider_document_id,
                "source_document_id": envelope.provider_payload.get("source_document_id"),
                "test_mode": envelope.test_mode,
                "delivery_mode": envelope.delivery_mode,
            },
            occurred_at=occurred_at,
        )
    )


def send_saved_esign_draft(
    db: Session,
    principal: Principal,
    transaction: Transaction,
    package: ContractPackage,
    envelope: EsignEnvelope,
    settings: Settings,
) -> EsignEnvelopeRead:
    transaction_id = transaction.id
    package_id = package.id
    envelope_id = envelope.id
    # Callers may have read transaction/package first. Release those read locks and
    # standardize all provider-active paths on envelope -> transaction -> package.
    db.rollback()
    locked_envelope = db.scalar(
        select(EsignEnvelope)
        .where(
            EsignEnvelope.id == envelope_id,
            EsignEnvelope.organization_id == principal.organization_id,
        )
        .with_for_update(of=EsignEnvelope)
    )
    locked_transaction = db.scalar(
        select(Transaction)
        .where(
            Transaction.id == transaction_id,
            Transaction.organization_id == principal.organization_id,
        )
        .with_for_update(of=Transaction)
    )
    locked_package = db.scalar(
        select(ContractPackage)
        .where(
            ContractPackage.id == package_id,
            ContractPackage.organization_id == principal.organization_id,
        )
        .with_for_update(of=ContractPackage)
    )
    if locked_transaction is None or locked_package is None or locked_envelope is None:
        raise ValueError("The saved signature draft is no longer available.")
    if locked_package.status != "sending" or locked_envelope.status != "draft":
        raise ValueError("The saved signature draft is not ready to send.")
    validate_purchase_contract_authority(
        db,
        locked_transaction,
        locked_package,
        gate="sending the saved provider draft",
    )
    locked_envelope.status = "sending"
    locked_envelope.provider_payload = {
        **locked_envelope.provider_payload,
        "phase": "sending",
    }
    provider_document_id = locked_envelope.provider_document_id
    delivery_mode = locked_envelope.delivery_mode
    db.commit()

    try:
        if settings.esign_provider == "simulate":
            simulated_recipients = list(
                db.scalars(
                    select(EsignRecipient)
                    .where(EsignRecipient.esign_envelope_id == envelope_id)
                    .order_by(EsignRecipient.signing_order)
                )
            )
            provider_response: dict[str, Any] = {
                "id": provider_document_id,
                "status": "sent",
                "recipients": [
                    {
                        "id": item.provider_recipient_id or str(index),
                        "email": item.email,
                        **(
                            {
                                "embedded_signing_url": (
                                    f"https://www.signwell.com/docs/simulated-{uuid4()}/"
                                )
                            }
                            if delivery_mode == "in_person"
                            else {}
                        ),
                    }
                    for index, item in enumerate(simulated_recipients, start=1)
                ],
            }
        else:
            provider_response = SignWellClient(settings).send_document(provider_document_id)
    except Exception as exc:
        transitioned = mark_esign_intent_uncertain(
            db,
            envelope_id,
            status="send_uncertain",
            expected_status="sending",
            error=exc,
        )
        if not transitioned:
            advanced = db.get(EsignEnvelope, envelope_id)
            if advanced is not None and advanced.status in {
                "draft",
                "sent",
                "viewed",
                "in_progress",
                "completed",
                "declined",
                "expired",
                "cancelled",
            }:
                return envelope_read(db, advanced)
        raise ValueError(
            "The SignWell send outcome is uncertain. Reconcile this exact provider document "
            "before any retry."
        ) from exc

    locked_envelope = db.scalar(
        select(EsignEnvelope)
        .where(EsignEnvelope.id == envelope_id)
        .with_for_update(of=EsignEnvelope)
    )
    locked_transaction = db.scalar(
        select(Transaction).where(Transaction.id == transaction_id).with_for_update(of=Transaction)
    )
    locked_package = db.scalar(
        select(ContractPackage)
        .where(ContractPackage.id == package_id)
        .with_for_update(of=ContractPackage)
    )
    if locked_transaction is None or locked_package is None or locked_envelope is None:
        raise ValueError("The sent signature request could not be reconciled locally.")
    now = datetime.now(UTC)
    if locked_envelope.status not in {"draft", "sending", "send_uncertain"}:
        # A provider webhook won the race. Keep its authoritative state and payload
        # fields while retaining the synchronous response as additional evidence.
        locked_envelope.provider_payload = {
            **provider_response,
            **locked_envelope.provider_payload,
            "id": locked_envelope.provider_document_id,
            "send_response": provider_response,
        }
        locked_envelope.sent_at = locked_envelope.sent_at or now
        provider_recipients = {
            str(item.get("email", "")).strip().lower(): item
            for item in provider_response.get("recipients", [])
            if isinstance(item, dict)
        }
        update_esign_recipient_provider_data(
            db,
            locked_envelope.id,
            provider_recipients,
            status="sent",
        )
        finalize_local_esign_send(
            db,
            locked_envelope,
            occurred_at=now,
            actor_user_id=principal.user_id,
        )
        db.commit()
        return envelope_read(db, locked_envelope)
    try:
        validate_purchase_contract_authority(
            db,
            locked_transaction,
            locked_package,
            gate="recording the provider send",
        )
    except ValueError as exc:
        locked_envelope.status = "send_uncertain"
        locked_envelope.provider_payload = {
            **locked_envelope.provider_payload,
            **provider_response,
            "phase": "authority_conflict_after_send",
            "error": str(exc)[:500],
        }
        db.commit()
        raise ValueError(
            "SignWell may have sent the document, but offer authority changed during delivery. "
            "Escalate and reconcile this envelope immediately."
        ) from exc
    if locked_envelope.status in {"draft", "sending", "send_uncertain"}:
        locked_envelope.status = "sent"
        locked_envelope.provider_payload = {
            **locked_envelope.provider_payload,
            **provider_response,
            "id": locked_envelope.provider_document_id,
            "status": "sent",
            "phase": "sent",
        }
    locked_envelope.sent_at = locked_envelope.sent_at or now
    provider_recipients = {
        str(item.get("email", "")).strip().lower(): item
        for item in locked_envelope.provider_payload.get("recipients", [])
        if isinstance(item, dict)
    }
    update_esign_recipient_provider_data(
        db,
        locked_envelope.id,
        provider_recipients,
        status="sent",
    )
    finalize_local_esign_send(
        db,
        locked_envelope,
        occurred_at=now,
        actor_user_id=principal.user_id,
    )
    db.commit()
    return envelope_read(db, locked_envelope)


def attach_verified_esign_draft(
    db: Session,
    principal: Principal,
    transaction_id: UUID,
    envelope_id: UUID,
    payload: EsignDraftRecoveryRequest,
    settings: Settings | None = None,
) -> EsignEnvelopeRead | None:
    """Recover the only unsafe provider-create crash window without creating a duplicate."""
    active = settings or get_settings()
    blockers = active.esign_configuration_blockers
    if blockers:
        raise ValueError(f"E-signature is missing: {', '.join(blockers)}.")
    if active.esign_provider != "signwell":
        raise ValueError("Provider-draft recovery is available only for SignWell.")
    recovery_reason = payload.reason.strip()
    if len(recovery_reason) < 10:
        raise ValueError("Record a specific recovery reason of at least ten characters.")

    # Scope the local intent before touching the shared provider account. This prevents
    # the recovery action from becoming a cross-tenant provider-document oracle.
    scoped_envelope = db.scalar(
        select(EsignEnvelope).where(
            EsignEnvelope.id == envelope_id,
            EsignEnvelope.organization_id == principal.organization_id,
            EsignEnvelope.transaction_id == transaction_id,
        )
    )
    if scoped_envelope is None:
        return None
    if scoped_envelope.status not in {"creating_draft", "draft_creation_uncertain"}:
        raise ValueError("Only an uncertain SignWell draft-creation intent can be recovered.")
    if not scoped_envelope.provider_document_id.startswith("intent-"):
        raise ValueError("This signature request already has a durable provider document ID.")

    provider_document_id = payload.provider_document_id.strip()
    if provider_document_id.startswith("intent-"):
        raise ValueError("Enter the real SignWell document ID, not Stonegate's intent ID.")
    # Establish the provider-active lock order before the authoritative provider read.
    db.rollback()
    envelope = db.scalar(
        select(EsignEnvelope)
        .where(
            EsignEnvelope.id == envelope_id,
            EsignEnvelope.organization_id == principal.organization_id,
            EsignEnvelope.transaction_id == transaction_id,
        )
        .with_for_update(of=EsignEnvelope)
    )
    if envelope is None:
        return None
    transaction = db.scalar(
        select(Transaction)
        .where(
            Transaction.id == transaction_id,
            Transaction.organization_id == principal.organization_id,
        )
        .with_for_update(of=Transaction)
    )
    package = db.scalar(
        select(ContractPackage)
        .where(
            ContractPackage.id == envelope.contract_package_id,
            ContractPackage.transaction_id == transaction_id,
            ContractPackage.organization_id == principal.organization_id,
        )
        .with_for_update(of=ContractPackage)
    )
    if transaction is None or package is None:
        raise ValueError("The signature recovery intent no longer matches its transaction.")
    validate_local_recovery_intent(envelope, package)
    validate_purchase_contract_authority(
        db,
        transaction,
        package,
        gate="recovering the verified provider draft",
    )
    try:
        provider_document = SignWellClient(active).get_document(provider_document_id)
    except Exception as exc:
        raise ValueError("Stonegate could not verify that SignWell document.") from exc
    validate_recovery_document(
        db,
        envelope,
        transaction,
        package,
        provider_document_id,
        provider_document,
    )

    prior_status = envelope.status
    envelope.provider_document_id = provider_document_id
    envelope.status = "draft"
    envelope.provider_payload = {
        **envelope.provider_payload,
        **provider_document,
        "id": provider_document_id,
        "phase": "draft_recovered",
        "source_document_id": envelope.provider_payload.get("source_document_id"),
        "recovery_reason": recovery_reason,
    }
    provider_recipients = {
        str(item.get("email", "")).strip().lower(): item
        for item in provider_document.get("recipients", [])
        if isinstance(item, dict)
    }
    update_esign_recipient_provider_data(
        db,
        envelope.id,
        provider_recipients,
        status="created",
    )
    db.add(
        TransactionEvent(
            organization_id=envelope.organization_id,
            transaction_id=transaction.id,
            lead_id=transaction.lead_id,
            actor_user_id=principal.user_id,
            event_type="esign.draft_recovered",
            summary=(
                f"Attached verified SignWell draft to contract package "
                f"v{package.version_number}."
            ),
            details={
                "envelope_id": str(envelope.id),
                "provider_document_id": provider_document_id,
                "prior_status": prior_status,
                "operator_attested": payload.confirm_provider_draft_verified,
                "reason": recovery_reason,
            },
            occurred_at=datetime.now(UTC),
        )
    )
    db.add(
        AuditEvent(
            organization_id=envelope.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="esign.draft.attach",
            entity_type="esign_envelope",
            entity_id=envelope.id,
            previous_value={"status": prior_status, "provider_document_id": "intent"},
            new_value={
                "status": "draft",
                "provider_document_id": provider_document_id,
                "operator_attested": payload.confirm_provider_draft_verified,
            },
            reason=recovery_reason,
        )
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("That SignWell document is already attached to another request.") from exc
    return envelope_read(db, envelope)


def validate_local_recovery_intent(
    envelope: EsignEnvelope,
    package: ContractPackage,
) -> None:
    if envelope.status not in {"creating_draft", "draft_creation_uncertain"}:
        raise ValueError("Only an uncertain SignWell draft-creation intent can be recovered.")
    if not envelope.provider_document_id.startswith("intent-"):
        raise ValueError("This signature request already has a durable provider document ID.")
    if package.status != "sending":
        raise ValueError("The contract package is not reserved for signature recovery.")


def abandon_esign_draft_intent(
    db: Session,
    principal: Principal,
    transaction_id: UUID,
    envelope_id: UUID,
    payload: EsignDraftAbandonRequest,
    settings: Settings | None = None,
) -> EsignEnvelopeRead | None:
    """Release a stale create intent after an operator verifies no provider document exists."""
    active = settings or get_settings()
    abandon_reason = payload.reason.strip()
    if len(abandon_reason) < 10:
        raise ValueError("Record a specific abandonment reason of at least ten characters.")
    scoped_envelope = db.scalar(
        select(EsignEnvelope).where(
            EsignEnvelope.id == envelope_id,
            EsignEnvelope.organization_id == principal.organization_id,
            EsignEnvelope.transaction_id == transaction_id,
        )
    )
    if scoped_envelope is None:
        return None
    db.rollback()
    envelope = db.scalar(
        select(EsignEnvelope)
        .where(
            EsignEnvelope.id == envelope_id,
            EsignEnvelope.organization_id == principal.organization_id,
            EsignEnvelope.transaction_id == transaction_id,
        )
        .with_for_update(of=EsignEnvelope)
    )
    if envelope is None:
        return None
    transaction = db.scalar(
        select(Transaction)
        .where(
            Transaction.id == transaction_id,
            Transaction.organization_id == principal.organization_id,
        )
        .with_for_update(of=Transaction)
    )
    package = db.scalar(
        select(ContractPackage)
        .where(
            ContractPackage.id == envelope.contract_package_id,
            ContractPackage.transaction_id == transaction_id,
            ContractPackage.organization_id == principal.organization_id,
        )
        .with_for_update(of=ContractPackage)
    )
    if transaction is None or package is None:
        raise ValueError("The signature recovery intent no longer matches its transaction.")
    validate_local_recovery_intent(envelope, package)
    minimum_age = timedelta(seconds=max(300, int(active.esign_request_timeout_seconds * 3)))
    if datetime.now(UTC) - as_utc(envelope.created_at) < minimum_age:
        raise ValueError(
            "Wait at least five minutes before abandoning a draft intent, then verify in "
            "SignWell that no document was created."
        )

    prior_status = envelope.status
    envelope.status = "error"
    envelope.provider_payload = {
        **envelope.provider_payload,
        "phase": "draft_creation_abandoned",
        "abandon_reason": abandon_reason,
        "operator_confirmed_no_provider_document": (payload.confirm_no_provider_document_exists),
    }
    package.status = "approved"
    db.add(
        TransactionEvent(
            organization_id=envelope.organization_id,
            transaction_id=transaction.id,
            lead_id=transaction.lead_id,
            actor_user_id=principal.user_id,
            event_type="esign.draft_intent_abandoned",
            summary=(
                f"Released stale signature intent for contract package v{package.version_number}."
            ),
            details={
                "envelope_id": str(envelope.id),
                "prior_status": prior_status,
                "operator_confirmed_no_provider_document": (
                    payload.confirm_no_provider_document_exists
                ),
                "reason": abandon_reason,
            },
            occurred_at=datetime.now(UTC),
        )
    )
    db.add(
        AuditEvent(
            organization_id=envelope.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="esign.intent.abandon",
            entity_type="esign_envelope",
            entity_id=envelope.id,
            previous_value={"status": prior_status, "package_status": "sending"},
            new_value={"status": "error", "package_status": "approved"},
            reason=abandon_reason,
        )
    )
    db.commit()
    return envelope_read(db, envelope)


def validate_recovery_document(
    db: Session,
    envelope: EsignEnvelope,
    transaction: Transaction,
    package: ContractPackage,
    provider_document_id: str,
    provider_document: dict[str, Any],
) -> None:
    returned_id = str(provider_document.get("id") or "").strip()
    if returned_id != provider_document_id:
        raise ValueError("SignWell returned a different document than the requested recovery ID.")
    provider_status = str(provider_document.get("status") or "").strip().lower()
    if provider_status not in {"created", "draft"}:
        raise ValueError("Only a verified, unsent SignWell draft can be attached.")
    metadata = provider_document.get("metadata")
    if not isinstance(metadata, dict) or (
        str(metadata.get("stonegate_transaction_id") or "") != str(transaction.id)
        or str(metadata.get("stonegate_contract_package_id") or "") != str(package.id)
    ):
        raise ValueError("The SignWell draft metadata does not match this Stonegate package.")
    if (
        "test_mode" in provider_document
        and bool(provider_document["test_mode"]) != envelope.test_mode
    ):
        raise ValueError("The SignWell draft test mode does not match this signature request.")
    provider_recipients = provider_document.get("recipients")
    if not isinstance(provider_recipients, list):
        raise ValueError("SignWell did not return the draft's recipients for verification.")
    provider_emails = {
        str(item.get("email") or "").strip().lower()
        for item in provider_recipients
        if isinstance(item, dict) and item.get("email")
    }
    saved_emails = {
        item.email.strip().lower()
        for item in db.scalars(
            select(EsignRecipient).where(EsignRecipient.esign_envelope_id == envelope.id)
        )
    }
    if not provider_emails or provider_emails != saved_emails:
        raise ValueError("The SignWell draft recipients do not match the reserved signer list.")


def resume_esign_draft(
    db: Session,
    principal: Principal,
    transaction_id: UUID,
    envelope_id: UUID,
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
    envelope = db.scalar(
        select(EsignEnvelope).where(
            EsignEnvelope.id == envelope_id,
            EsignEnvelope.organization_id == principal.organization_id,
            EsignEnvelope.transaction_id == transaction_id,
        )
    )
    if transaction is None or envelope is None:
        return None
    package = db.scalar(
        select(ContractPackage).where(
            ContractPackage.id == envelope.contract_package_id,
            ContractPackage.organization_id == principal.organization_id,
            ContractPackage.transaction_id == transaction_id,
        )
    )
    if package is None:
        return None
    if envelope.status != "draft":
        raise ValueError("Only a reconciled, unsent provider draft can be resumed.")
    if not envelope.provider_document_id or envelope.provider_document_id.startswith("intent-"):
        raise ValueError("The provider draft does not have a durable SignWell document ID.")
    return send_saved_esign_draft(
        db,
        principal,
        transaction,
        package,
        envelope,
        active,
    )


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
    if transaction is not None:
        require_house_transaction_workflow(db, transaction)
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
        # Persist the provider document ID before any signer notification is attempted.
        "draft": True,
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
) -> SignWellWebhookVerification:
    active = settings or get_settings()
    event_data = payload.get("event")
    if not isinstance(event_data, dict):
        raise ValueError("Invalid SignWell event payload.")
    event_type = str(event_data.get("type") or "").strip()
    event_time = str(event_data.get("time") or "").strip()
    provided = str(event_data.get("hash") or "").strip()
    if not event_type or not event_time or not provided:
        raise ValueError("Invalid SignWell event signature.")

    signed_message = f"{event_type}@{event_time}".encode()

    def matches(webhook_id: str) -> bool:
        return secrets.compare_digest(
            provided,
            hmac.new(webhook_id.encode(), signed_message, sha256).hexdigest(),
        )

    configurations = (
        list(
            db.scalars(
                select(EsignProviderConfiguration).where(
                    EsignProviderConfiguration.provider == "signwell"
                )
            ).all()
        )
        if db is not None
        else []
    )
    matching_organization_ids = {
        configuration.organization_id
        for configuration in configurations
        if configuration.webhook_id and matches(configuration.webhook_id)
    }
    if len(matching_organization_ids) > 1:
        raise ValueError("Ambiguous SignWell event signature.")
    if matching_organization_ids:
        return SignWellWebhookVerification(
            organization_id=next(iter(matching_organization_ids)),
            source="organization",
        )
    if active.esign_signwell_webhook_id and matches(active.esign_signwell_webhook_id):
        return SignWellWebhookVerification(organization_id=None, source="global")
    raise ValueError("Invalid SignWell event signature.")


def resolve_signwell_envelope(
    db: Session,
    provider_document_id: str,
    verification: SignWellWebhookVerification,
) -> EsignEnvelope | None:
    envelope_filter = (
        EsignEnvelope.provider_document_id == provider_document_id,
        EsignEnvelope.provider.in_(("signwell", "simulate")),
    )
    if verification.organization_id is not None:
        envelope = db.scalar(
            select(EsignEnvelope)
            .where(
                *envelope_filter,
                EsignEnvelope.organization_id == verification.organization_id,
            )
            .with_for_update()
        )
        if envelope is not None:
            return envelope
        cross_organization_match = db.scalar(select(EsignEnvelope.id).where(*envelope_filter))
        if cross_organization_match is not None:
            raise ValueError("Invalid SignWell event signature for envelope organization.")
        return None

    if verification.source != "global":
        raise ValueError("Invalid SignWell event signature.")
    envelopes = list(
        db.scalars(select(EsignEnvelope).where(*envelope_filter).with_for_update()).all()
    )
    if not envelopes:
        return None
    envelope_organization_ids = set(
        db.scalars(
            select(EsignEnvelope.organization_id)
            .where(EsignEnvelope.provider.in_(("signwell", "simulate")))
            .distinct()
        ).all()
    )
    if len(envelopes) != 1 or envelope_organization_ids != {envelopes[0].organization_id}:
        raise ValueError("Global SignWell event signature is not valid for multiple organizations.")
    return envelopes[0]


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def ignored_provider_event_status(
    envelope: EsignEnvelope,
    event_type: str,
    occurred_at: datetime,
) -> str | None:
    next_status = EVENT_STATUS.get(event_type)
    if next_status is None:
        if envelope.last_provider_event_at is not None and occurred_at < as_utc(
            envelope.last_provider_event_at
        ):
            return "ignored_stale"
        return None
    if envelope.status in TERMINAL_ENVELOPE_STATUSES and next_status != envelope.status:
        return "ignored_out_of_order"
    current_order = ENVELOPE_STATUS_ORDER.get(envelope.status)
    next_order = ENVELOPE_STATUS_ORDER.get(next_status)
    if current_order is not None and next_order is not None and next_order < current_order:
        if event_type in {"document_viewed", "document_signed"}:
            return None
        return (
            "ignored_stale"
            if envelope.last_provider_event_at is not None
            and occurred_at < as_utc(envelope.last_provider_event_at)
            else "ignored_out_of_order"
        )
    # Reconciliation uses its local observation time. A later-arriving provider event may
    # carry an older provider timestamp while still proving forward state (especially
    # completion). Only discard an older event when it does not advance state.
    if (
        envelope.last_provider_event_at is not None
        and occurred_at < as_utc(envelope.last_provider_event_at)
        and next_status == envelope.status
        and event_type not in {"document_viewed", "document_signed"}
    ):
        return "ignored_stale"
    return None


def process_signwell_event(
    db: Session,
    payload: dict[str, Any],
    settings: Settings | None = None,
    *,
    verification: SignWellWebhookVerification,
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
    envelope = resolve_signwell_envelope(db, provider_document_id, verification)
    if envelope is None:
        return False
    provider_event = db.scalar(
        select(EsignProviderEvent).where(
            EsignProviderEvent.organization_id == envelope.organization_id,
            EsignProviderEvent.provider == envelope.provider,
            EsignProviderEvent.provider_event_id == provider_event_id,
        )
    )
    if provider_event is not None:
        if provider_event.status != "failed":
            return True
        stored_event_data = provider_event.payload.get("event")
        stored_document_data = provider_event.payload.get("data", {}).get("object")
        if not isinstance(stored_event_data, dict) or not isinstance(stored_document_data, dict):
            raise ValueError("Stored SignWell event payload is invalid.")
        event_data = stored_event_data
        document_data = stored_document_data
    occurred_at = datetime.fromtimestamp(
        int(event_data.get("time") or datetime.now(UTC).timestamp()),
        tz=UTC,
    )
    if provider_event is None:
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
    else:
        provider_event.status = "processing"
        provider_event.processed_at = None
        provider_event.processing_error = None
    ignored_status = ignored_provider_event_status(envelope, event_type, occurred_at)
    if ignored_status is not None:
        provider_event.status = ignored_status
        provider_event.processed_at = datetime.now(UTC)
        db.commit()
        return True
    db.flush()
    quarantine_reason: str | None = None
    try:
        with db.begin_nested():
            quarantine_reason = apply_provider_event(
                db,
                envelope,
                event_type,
                event_data,
                document_data,
                active,
            )
    except Exception as exc:
        provider_event.status = "failed"
        provider_event.processed_at = datetime.now(UTC)
        provider_event.processing_error = str(exc)[:2000]
        db.commit()
        raise
    provider_event.status = "quarantined" if quarantine_reason else "processed"
    provider_event.processed_at = datetime.now(UTC)
    provider_event.processing_error = quarantine_reason[:2000] if quarantine_reason else None
    db.commit()
    return True


def apply_provider_event(
    db: Session,
    envelope: EsignEnvelope,
    event_type: str,
    event_data: dict[str, Any],
    document_data: dict[str, Any],
    settings: Settings,
) -> str | None:
    occurred_at = datetime.fromtimestamp(
        int(event_data.get("time") or datetime.now(UTC).timestamp()),
        tz=UTC,
    )
    prior_envelope_status = envelope.status
    provider_delivery_events = {
        "document_sent",
        "document_viewed",
        "document_in_progress",
        "document_signed",
        "document_completed",
        "document_declined",
        "document_expired",
        "document_bounced",
    }
    provider_terminal_failure_events = {
        "document_declined",
        "document_expired",
        "document_canceled",
        "document_error",
    }
    transaction: Transaction | None = None
    package: ContractPackage | None = None
    if event_type in provider_delivery_events | provider_terminal_failure_events:
        transaction, package = lock_provider_event_contract(db, envelope)
    if event_type == "document_completed":
        assert transaction is not None and package is not None
        quarantine_reason = provider_completion_quarantine_reason(db, transaction, package)
        if quarantine_reason is not None:
            db.add(
                TransactionEvent(
                    organization_id=envelope.organization_id,
                    transaction_id=transaction.id,
                    lead_id=transaction.lead_id,
                    actor_user_id=None,
                    event_type="esign.completion_quarantined",
                    summary=(
                        "A delayed provider completion was quarantined because the transaction "
                        "or lead is closed."
                    ),
                    details={
                        "envelope_id": str(envelope.id),
                        "provider_document_id": envelope.provider_document_id,
                        "provider_event_type": event_type,
                        "reason": quarantine_reason,
                        "transaction_status": transaction.status,
                    },
                    occurred_at=occurred_at,
                )
            )
            return quarantine_reason
        validate_purchase_contract_authority(
            db,
            transaction,
            package,
            gate="accepting provider execution",
        )
    if envelope.last_provider_event_at is None or occurred_at > as_utc(
        envelope.last_provider_event_at
    ):
        envelope.last_provider_event_at = occurred_at
    envelope.provider_payload = {**envelope.provider_payload, **document_data}
    if event_type in provider_delivery_events and envelope.status in {
        "creating_draft",
        "draft",
        "sending",
        "send_uncertain",
    }:
        finalize_local_esign_send(
            db,
            envelope,
            occurred_at=occurred_at,
            actor_user_id=None,
        )
    next_status = EVENT_STATUS.get(event_type)
    current_order = ENVELOPE_STATUS_ORDER.get(envelope.status)
    next_order = ENVELOPE_STATUS_ORDER.get(next_status) if next_status is not None else None
    if next_status is not None and not (
        current_order is not None and next_order is not None and next_order < current_order
    ):
        envelope.status = next_status
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
                if recipient.status not in {"signed", "declined"}:
                    recipient.status = "viewed"
                    recipient.viewed_at = recipient.viewed_at or occurred_at
            elif event_type == "document_signed":
                if recipient.status != "declined":
                    recipient.status = "signed"
                    recipient.signed_at = recipient.signed_at or occurred_at
            elif event_type == "document_declined" and recipient.status != "signed":
                recipient.status = "declined"
                recipient.declined_at = recipient.declined_at or occurred_at
    if event_type == "document_completed":
        assert transaction is not None and package is not None
        envelope.completed_at = envelope.completed_at or occurred_at
        for recipient in db.scalars(
            select(EsignRecipient).where(EsignRecipient.esign_envelope_id == envelope.id)
        ).all():
            recipient.status = "signed"
            recipient.signed_at = recipient.signed_at or occurred_at
        complete_envelope(
            db,
            envelope,
            transaction,
            package,
            document_data,
            settings,
        )
    elif event_type == "document_declined":
        envelope.declined_at = envelope.declined_at or occurred_at
    elif event_type == "document_expired":
        envelope.expired_at = envelope.expired_at or occurred_at
    elif event_type == "document_canceled":
        envelope.cancelled_at = envelope.cancelled_at or occurred_at
    if event_type in provider_terminal_failure_events:
        assert transaction is not None and package is not None
        release_failed_esign_reservation(
            db,
            envelope,
            transaction,
            package,
            event_type=event_type,
            occurred_at=occurred_at,
            prior_envelope_status=prior_envelope_status,
        )
    return None


def provider_completion_quarantine_reason(
    db: Session,
    transaction: Transaction,
    package: ContractPackage,
) -> str | None:
    """Refuse delayed execution after Stonegate has made the record terminal."""
    if (
        transaction.status in TERMINAL_TRANSACTION_STATUSES
        or transaction.cancelled_at is not None
        or transaction.closed_at is not None
        or transaction.funded_at is not None
    ):
        return (
            "Provider completion cannot execute a terminal Stonegate transaction "
            f"(status: {transaction.status})."
        )
    lead = db.scalar(
        select(Lead)
        .where(
            Lead.id == transaction.lead_id,
            Lead.organization_id == transaction.organization_id,
        )
        .execution_options(populate_existing=True)
        .with_for_update(of=Lead)
    )
    if lead is None and package_document_type(package) == "purchase_agreement":
        return "Provider completion cannot execute because the transaction lead is unavailable."
    if lead is not None and (
        lead.archived_at is not None or lead.stage_key in TERMINAL_LEAD_STAGES
    ):
        return (
            "Provider completion cannot execute a closed or archived Stonegate lead "
            f"(stage: {lead.stage_key})."
        )
    return None


def lock_provider_event_contract(
    db: Session,
    envelope: EsignEnvelope,
) -> tuple[Transaction, ContractPackage]:
    """Complete the provider-event lock order: envelope -> transaction -> package."""
    transaction = db.scalar(
        select(Transaction)
        .where(Transaction.id == envelope.transaction_id)
        .with_for_update(of=Transaction)
    )
    package = db.scalar(
        select(ContractPackage)
        .where(ContractPackage.id == envelope.contract_package_id)
        .with_for_update(of=ContractPackage)
    )
    if transaction is None or package is None:
        raise ValueError("The provider envelope no longer matches a Stonegate transaction.")
    if (
        transaction.organization_id != envelope.organization_id
        or package.organization_id != envelope.organization_id
        or package.transaction_id != transaction.id
    ):
        raise ValueError("The provider envelope contract binding is invalid.")
    return transaction, package


def release_failed_esign_reservation(
    db: Session,
    envelope: EsignEnvelope,
    transaction: Transaction,
    package: ContractPackage,
    *,
    event_type: str,
    occurred_at: datetime,
    prior_envelope_status: str,
) -> None:
    """Release authority only after SignWell proves the document is no longer signable."""
    if prior_envelope_status in TERMINAL_ENVELOPE_STATUSES:
        return
    if package.status not in {"sending", "sent"}:
        return
    prior_package_status = package.status
    package.status = "approved"
    if transaction.status == "sent":
        transaction.status = "contract_prep"
    db.add(
        TransactionEvent(
            organization_id=envelope.organization_id,
            transaction_id=transaction.id,
            lead_id=transaction.lead_id,
            actor_user_id=None,
            event_type="esign.delivery_closed",
            summary=(
                f"SignWell closed contract package v{package.version_number} without execution."
            ),
            details={
                "envelope_id": str(envelope.id),
                "provider_document_id": envelope.provider_document_id,
                "provider_event_type": event_type,
                "prior_package_status": prior_package_status,
                "package_status": package.status,
            },
            occurred_at=occurred_at,
        )
    )


def complete_envelope(
    db: Session,
    envelope: EsignEnvelope,
    transaction: Transaction,
    package: ContractPackage,
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
    validate_purchase_contract_authority(
        db,
        transaction,
        package,
        gate="recording provider execution",
    )
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
    if stored.malware_scan_status not in ACCEPTABLE_EXECUTION_SCAN_STATUSES:
        raise ValueError("The completed agreement does not have an acceptable malware scan state.")
    document = TransactionDocument(
        id=document_id,
        organization_id=envelope.organization_id,
        transaction_id=transaction.id,
        contract_package_id=package.id,
        uploaded_by_user_id=envelope.created_by_user_id,
        document_type=document_type,
        title=f"SignWell completed {document_label} v{package.version_number}",
        status="executed",
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
                "execution_evidence": "completed_provider_envelope",
                "malware_scan_status": document.malware_scan_status,
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
        "created": "document_draft",
        "draft": "document_draft",
        "completed": "document_completed",
        "declined": "document_declined",
        "expired": "document_expired",
        "canceled": "document_canceled",
        "cancelled": "document_canceled",
        "error": "document_error",
        "failed": "document_error",
        "bounced": "document_bounced",
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
        verification=SignWellWebhookVerification(
            organization_id=envelope.organization_id,
            source="internal",
        ),
    )
    db.refresh(envelope)
    return envelope_read(db, envelope)


def require_house_transaction_workflow(db: Session, transaction: Transaction) -> None:
    lead = db.get(Lead, transaction.lead_id)
    if lead is None:
        raise ValueError("The transaction lead is no longer available.")
    require_house_workflow(lead.asset_class, workflow="Residential contract and e-signature")
