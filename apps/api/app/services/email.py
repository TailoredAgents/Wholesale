import base64
import binascii
import hashlib
from datetime import UTC, datetime, timedelta
from email.utils import getaddresses
from html.parser import HTMLParser
from typing import Any
from uuid import UUID

import jwt
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import Settings, get_settings
from app.domain.rbac import PermissionKeys
from app.integrations.communications import (
    OutboundMessageRequest,
    SimulatedCommunicationProvider,
)
from app.integrations.google_gmail import (
    GoogleGmailClient,
    GoogleGmailError,
    get_google_gmail_client,
)
from app.models.foundation import (
    ActivityEvent,
    AuditEvent,
    CommunicationDispatch,
    CommunicationProviderEvent,
    CommunicationRecord,
    Contact,
    ContactMethod,
    Conversation,
    EmailAccount,
    EmailAttachment,
    EmailTemplate,
    Lead,
    User,
)
from app.schemas.email import (
    EmailAccountListResponse,
    EmailAccountRead,
    EmailAccountUpdate,
    EmailAttachmentRead,
    EmailOAuthAuthorizeRead,
    EmailSendRead,
    EmailSendRequest,
    EmailSyncRead,
    EmailTemplateCreate,
    EmailTemplateRead,
    EmailTemplateUpdate,
)
from app.services.inbox import get_scoped_conversation, update_conversation_activity


class EmailConfigurationError(RuntimeError):
    pass


class EmailDispatchConflictError(RuntimeError):
    pass


class EmailAttachmentError(RuntimeError):
    pass


class _HtmlTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text)


def _fernet(settings: Settings) -> Fernet:
    if not settings.email_token_encryption_key:
        raise EmailConfigurationError("Email token encryption is not configured.")
    key = base64.urlsafe_b64encode(
        hashlib.sha256(settings.email_token_encryption_key.encode("utf-8")).digest()
    )
    return Fernet(key)


def encrypt_token(token: str, settings: Settings) -> str:
    return _fernet(settings).encrypt(token.encode("utf-8")).decode("ascii")


def decrypt_token(token: str, settings: Settings) -> str:
    try:
        return _fernet(settings).decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise EmailConfigurationError("Stored email credentials could not be decrypted.") from exc


def create_google_authorization(
    principal: Principal,
    settings: Settings | None = None,
    client: GoogleGmailClient | None = None,
) -> EmailOAuthAuthorizeRead:
    settings = settings or get_settings()
    if settings.email_configuration_blockers:
        raise EmailConfigurationError(
            "Email is not configured: " + ", ".join(settings.email_configuration_blockers)
        )
    assert settings.email_oauth_state_secret is not None
    state = jwt.encode(
        {
            "sub": str(principal.user_id),
            "org": str(principal.organization_id),
            "purpose": "google_email_connect",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=10),
        },
        settings.email_oauth_state_secret,
        algorithm="HS256",
    )
    gmail = client or get_google_gmail_client(settings)
    return EmailOAuthAuthorizeRead(authorization_url=gmail.authorization_url(state))


def complete_google_authorization(
    db: Session,
    *,
    code: str,
    state: str,
    settings: Settings | None = None,
    client: GoogleGmailClient | None = None,
) -> EmailAccount:
    settings = settings or get_settings()
    if settings.email_configuration_blockers:
        raise EmailConfigurationError("Email is not fully configured.")
    assert settings.email_oauth_state_secret is not None
    try:
        claims = jwt.decode(
            state,
            settings.email_oauth_state_secret,
            algorithms=["HS256"],
            options={"require": ["sub", "org", "purpose", "exp"]},
        )
        if claims["purpose"] != "google_email_connect":
            raise ValueError
        user_id = UUID(str(claims["sub"]))
        organization_id = UUID(str(claims["org"]))
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise EmailConfigurationError(
            "The email connection request expired or is invalid."
        ) from exc

    user = db.scalar(
        select(User).where(
            User.id == user_id,
            User.organization_id == organization_id,
            User.is_active.is_(True),
        )
    )
    if user is None:
        raise EmailConfigurationError("The Stonegate user is no longer active.")

    gmail = client or get_google_gmail_client(settings)
    token = gmail.exchange_code(code)
    if not token.refresh_token:
        raise EmailConfigurationError(
            "Google did not return offline access. Remove Stonegate from Google account access "
            "and connect it again."
        )
    profile = gmail.get_profile(token.access_token)
    account = db.scalar(
        select(EmailAccount).where(
            EmailAccount.organization_id == organization_id,
            EmailAccount.provider == "google",
            EmailAccount.email_address == profile.email_address,
        )
    )
    if account is not None and account.user_id != user.id:
        raise EmailConfigurationError(
            "That mailbox is already connected to another Stonegate user."
        )
    if account is None:
        account = EmailAccount(
            organization_id=organization_id,
            user_id=user.id,
            connected_by_user_id=user.id,
            provider="google",
            provider_account_id=profile.email_address,
            email_address=profile.email_address,
            display_name=user.display_name,
            status="active",
            is_shared=False,
            sync_enabled=True,
            encrypted_access_token=None,
            encrypted_refresh_token="",
            access_token_expires_at=None,
            history_cursor=profile.history_id,
            last_synced_at=datetime.now(UTC),
            last_error=None,
            signature_text=None,
            account_metadata={"scopes": "gmail.modify", "connected_via": "oauth"},
        )
        db.add(account)
    account.status = "active"
    account.sync_enabled = True
    account.encrypted_access_token = encrypt_token(token.access_token, settings)
    account.encrypted_refresh_token = encrypt_token(token.refresh_token, settings)
    account.access_token_expires_at = datetime.now(UTC) + timedelta(seconds=token.expires_in)
    account.history_cursor = profile.history_id
    account.last_synced_at = datetime.now(UTC)
    account.last_error = None
    db.flush()
    db.add(
        AuditEvent(
            organization_id=organization_id,
            actor_user_id=user.id,
            actor_type="user",
            action="email.account_connected",
            entity_type="email_account",
            entity_id=account.id,
            previous_value=None,
            new_value={"provider": "google", "email_address": account.email_address},
            reason="Google Workspace mailbox connected through OAuth",
        )
    )
    db.commit()
    db.refresh(account)
    return account


def list_email_accounts(db: Session, principal: Principal) -> EmailAccountListResponse:
    can_manage = PermissionKeys.MANAGE_EMAIL_ACCOUNTS in principal.permission_keys
    filters = [EmailAccount.organization_id == principal.organization_id]
    if not can_manage:
        filters.append(
            or_(EmailAccount.user_id == principal.user_id, EmailAccount.is_shared.is_(True))
        )
    accounts = db.scalars(
        select(EmailAccount)
        .where(*filters)
        .order_by(EmailAccount.status.asc(), EmailAccount.email_address.asc())
    ).all()
    settings = get_settings()
    return EmailAccountListResponse(
        items=[email_account_to_read(account, principal) for account in accounts],
        provider_configured=not settings.email_configuration_blockers,
        configuration_blockers=list(settings.email_configuration_blockers),
    )


def update_email_account(
    db: Session,
    principal: Principal,
    account_id: UUID,
    payload: EmailAccountUpdate,
) -> EmailAccountRead | None:
    account = get_scoped_email_account(db, principal, account_id, allow_shared=True)
    if account is None:
        return None
    can_manage = PermissionKeys.MANAGE_EMAIL_ACCOUNTS in principal.permission_keys
    if account.user_id != principal.user_id and not can_manage:
        raise PermissionError("Only the mailbox owner can update this email account.")
    values = payload.model_dump(exclude_unset=True)
    if ("is_shared" in values or "sync_enabled" in values) and not can_manage:
        raise PermissionError("Only an email administrator can change mailbox sharing or sync.")
    previous = {
        "display_name": account.display_name,
        "is_shared": account.is_shared,
        "sync_enabled": account.sync_enabled,
    }
    for key, value in values.items():
        setattr(account, key, value)
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="email.account_updated",
            entity_type="email_account",
            entity_id=account.id,
            previous_value=previous,
            new_value={
                "display_name": account.display_name,
                "is_shared": account.is_shared,
                "sync_enabled": account.sync_enabled,
            },
            reason="Email account settings updated",
        )
    )
    db.commit()
    return email_account_to_read(account, principal)


def disconnect_email_account(
    db: Session,
    principal: Principal,
    account_id: UUID,
) -> bool:
    account = get_scoped_email_account(db, principal, account_id, allow_shared=True)
    if account is None:
        return False
    if (
        account.user_id != principal.user_id
        and PermissionKeys.MANAGE_EMAIL_ACCOUNTS not in principal.permission_keys
    ):
        raise PermissionError("Only the mailbox owner or an administrator can disconnect it.")
    account.status = "disconnected"
    account.sync_enabled = False
    account.encrypted_access_token = None
    account.encrypted_refresh_token = encrypt_token("disconnected", get_settings())
    account.access_token_expires_at = None
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="email.account_disconnected",
            entity_type="email_account",
            entity_id=account.id,
            previous_value={"status": "active"},
            new_value={"status": "disconnected"},
            reason="Google Workspace mailbox disconnected",
        )
    )
    db.commit()
    return True


def list_email_templates(db: Session, principal: Principal) -> list[EmailTemplateRead]:
    templates = db.scalars(
        select(EmailTemplate)
        .where(
            EmailTemplate.organization_id == principal.organization_id,
            EmailTemplate.is_active.is_(True),
            or_(
                EmailTemplate.is_shared.is_(True),
                EmailTemplate.created_by_user_id == principal.user_id,
            ),
        )
        .order_by(EmailTemplate.name.asc())
    ).all()
    return [email_template_to_read(template) for template in templates]


def create_email_template(
    db: Session,
    principal: Principal,
    payload: EmailTemplateCreate,
) -> EmailTemplateRead:
    template = EmailTemplate(
        organization_id=principal.organization_id,
        created_by_user_id=principal.user_id,
        name=payload.name.strip(),
        subject_template=payload.subject_template.strip(),
        body_template=payload.body_template.strip(),
        is_shared=payload.is_shared,
        is_active=True,
    )
    db.add(template)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("An email template with that name already exists.") from exc
    db.refresh(template)
    return email_template_to_read(template)


def update_email_template(
    db: Session,
    principal: Principal,
    template_id: UUID,
    payload: EmailTemplateUpdate,
) -> EmailTemplateRead | None:
    template = db.scalar(
        select(EmailTemplate).where(
            EmailTemplate.id == template_id,
            EmailTemplate.organization_id == principal.organization_id,
        )
    )
    if template is None:
        return None
    if (
        template.created_by_user_id != principal.user_id
        and PermissionKeys.MANAGE_EMAIL_ACCOUNTS not in principal.permission_keys
    ):
        raise PermissionError("Only the template owner or an administrator can update it.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(template, key, value.strip() if isinstance(value, str) else value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("An email template with that name already exists.") from exc
    return email_template_to_read(template)


def send_conversation_email(
    db: Session,
    principal: Principal,
    conversation_id: UUID,
    payload: EmailSendRequest,
    *,
    settings: Settings | None = None,
    client: GoogleGmailClient | None = None,
) -> EmailSendRead | None:
    settings = settings or get_settings()
    simulation_enabled = settings.communication_simulation_enabled
    conversation = get_scoped_conversation(db, principal, conversation_id)
    if conversation is None:
        return None
    if PermissionKeys.SEND_EMAIL not in principal.permission_keys and (
        PermissionKeys.SEND_ASSIGNED_EMAIL not in principal.permission_keys
        or conversation.assigned_user_id != principal.user_id
    ):
        raise PermissionError("Email can only be sent from an assigned conversation.")
    if settings.email_configuration_blockers and not simulation_enabled:
        raise EmailConfigurationError(
            "Email is not configured: " + ", ".join(settings.email_configuration_blockers)
        )

    account = get_scoped_email_account(db, principal, payload.email_account_id, allow_shared=True)
    if account is None or account.status != "active":
        raise EmailConfigurationError("Select an active Stonegate email account.")
    contact = db.get(Contact, conversation.contact_id)
    lead = db.get(Lead, conversation.lead_id)
    if contact is None or lead is None:
        return None
    recipient_method = db.scalar(
        select(ContactMethod)
        .where(
            ContactMethod.organization_id == principal.organization_id,
            ContactMethod.contact_id == contact.id,
            ContactMethod.method_type == "email",
        )
        .order_by(ContactMethod.is_primary.desc(), ContactMethod.created_at.asc())
    )
    if recipient_method is None:
        raise EmailConfigurationError("This seller does not have an email address.")
    recipient = recipient_method.value.strip().lower()
    subject = payload.subject.strip()
    body = payload.body.strip()
    decoded_attachments = decode_outbound_attachments(payload, settings)
    request_hash = hashlib.sha256(
        (
            f"{account.id}|{recipient}|{subject}|{body}|"
            + "|".join(
                f"{filename}:{content_type}:{hashlib.sha256(content).hexdigest()}"
                for filename, content_type, content in decoded_attachments
            )
        ).encode("utf-8")
    ).hexdigest()
    existing_dispatch = db.scalar(
        select(CommunicationDispatch).where(
            CommunicationDispatch.organization_id == principal.organization_id,
            CommunicationDispatch.idempotency_key == payload.idempotency_key,
        )
    )
    if existing_dispatch is not None:
        if (
            existing_dispatch.conversation_id != conversation.id
            or existing_dispatch.request_body_hash != request_hash
        ):
            raise EmailDispatchConflictError(
                "The idempotency key was already used for a different email."
            )
        if existing_dispatch.communication_record_id:
            communication = db.get(CommunicationRecord, existing_dispatch.communication_record_id)
            metadata = communication.communication_metadata if communication else None
            if communication and communication.provider_message_id and metadata:
                return EmailSendRead(
                    communication_id=communication.id,
                    provider_message_id=communication.provider_message_id,
                    provider_thread_id=str(metadata.get("provider_thread_id", "")),
                    status=communication.status,
                    recipient=recipient,
                )
        raise EmailDispatchConflictError(
            f"This email request is already {existing_dispatch.status}; use a new request to retry."
        )

    dispatch = CommunicationDispatch(
        organization_id=principal.organization_id,
        conversation_id=conversation.id,
        lead_id=lead.id,
        contact_id=contact.id,
        actor_user_id=principal.user_id,
        communication_record_id=None,
        idempotency_key=payload.idempotency_key,
        channel="email",
        recipient=recipient,
        request_body_hash=request_hash,
        status="pending",
        provider="simulated" if simulation_enabled else "google",
        provider_message_id=None,
        error_code=None,
        error_message=None,
        completed_at=None,
        dispatch_metadata={"email_account_id": str(account.id)},
    )
    db.add(dispatch)
    db.commit()
    dispatch_id = dispatch.id

    prior_email = db.scalar(
        select(CommunicationRecord)
        .where(
            CommunicationRecord.organization_id == principal.organization_id,
            CommunicationRecord.conversation_id == conversation.id,
            CommunicationRecord.channel == "email",
        )
        .order_by(CommunicationRecord.occurred_at.desc())
    )
    prior_metadata = (prior_email.communication_metadata if prior_email else None) or {}
    message_body = append_signature(body, account.signature_text)
    gmail: GoogleGmailClient | None = None
    access_token: str | None = None
    if simulation_enabled:
        simulated_result = SimulatedCommunicationProvider().send(
            OutboundMessageRequest(
                lead_id=str(lead.id),
                contact_id=str(contact.id),
                channel="email",
                recipient=recipient,
                subject=subject,
                body=message_body,
                idempotency_key=payload.idempotency_key,
                metadata={"attachment_count": str(len(decoded_attachments))},
            )
        )
        provider_message_id = simulated_result.provider_message_id or f"sim-email-{dispatch_id}"
        provider_thread_id = str(
            prior_metadata.get("provider_thread_id") or f"sim-thread-{conversation.id}"
        )
        provider_payload = simulated_result.raw_payload
        rfc_message_id = f"<{provider_message_id}@example.test>"
        provider_name = simulated_result.provider
    else:
        gmail = client or get_google_gmail_client(settings)
        try:
            access_token = get_account_access_token(db, account, settings, gmail)
            result = gmail.send_message(
                access_token,
                sender_name=account.display_name,
                sender_email=account.email_address,
                recipient=recipient,
                subject=subject,
                body=message_body,
                attachments=decoded_attachments,
                thread_id=(
                    str(prior_metadata["provider_thread_id"])
                    if prior_metadata and prior_metadata.get("provider_thread_id")
                    else None
                ),
                in_reply_to=(
                    str(prior_metadata["rfc_message_id"])
                    if prior_metadata and prior_metadata.get("rfc_message_id")
                    else None
                ),
                references=(
                    str(prior_metadata["references"])
                    if prior_metadata and prior_metadata.get("references")
                    else (
                        str(prior_metadata["rfc_message_id"])
                        if prior_metadata and prior_metadata.get("rfc_message_id")
                        else None
                    )
                ),
            )
        except (EmailConfigurationError, GoogleGmailError) as exc:
            mark_email_dispatch_failed(db, dispatch_id, str(exc))
            raise
        provider_message_id = result.message_id
        provider_thread_id = result.thread_id
        provider_payload = result.raw_payload
        rfc_message_id = str(result.raw_payload.get("rfc_message_id", ""))
        provider_name = "google"

    occurred_at = datetime.now(UTC)
    communication = CommunicationRecord(
        organization_id=principal.organization_id,
        conversation_id=conversation.id,
        lead_id=lead.id,
        contact_id=contact.id,
        actor_user_id=principal.user_id,
        direction="outbound",
        channel="email",
        status="sent",
        provider=provider_name,
        provider_message_id=provider_message_id,
        subject=subject,
        body=message_body,
        occurred_at=occurred_at,
        external_payload=provider_payload,
        communication_metadata={
            "source": "shared_inbox",
            "email_account_id": str(account.id),
            "provider_thread_id": provider_thread_id,
            "rfc_message_id": rfc_message_id,
            "references": " ".join(
                part
                for part in [
                    str(prior_metadata.get("references", "")) if prior_metadata else "",
                    rfc_message_id,
                ]
                if part
            ),
            "from": account.email_address,
            "to": recipient,
            "attachment_count": len(decoded_attachments),
        },
    )
    db.add(communication)
    db.flush()
    completed_dispatch = db.get(CommunicationDispatch, dispatch_id)
    if completed_dispatch is None:
        raise RuntimeError("Email dispatch disappeared before completion.")
    completed_dispatch.communication_record_id = communication.id
    completed_dispatch.status = "sent"
    completed_dispatch.provider_message_id = provider_message_id
    completed_dispatch.completed_at = occurred_at
    update_conversation_activity(conversation, direction="outbound", occurred_at=occurred_at)
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            event_type="lead.email_sent",
            summary=f"Email sent to {recipient}.",
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="communication.email_send",
            entity_type="communication_record",
            entity_id=communication.id,
            previous_value=None,
            new_value={
                "provider_message_id": provider_message_id,
                "provider_thread_id": provider_thread_id,
                "recipient": recipient,
                "attachment_count": len(decoded_attachments),
            },
            reason="One-to-one email sent from shared inbox",
        )
    )
    db.commit()
    if gmail is not None and access_token is not None:
        try:
            provider_message = gmail.get_message(access_token, provider_message_id)
            index_message_attachments(db, account, communication, provider_message)
            db.commit()
        except GoogleGmailError:
            account.last_error = "Email sent, but attachment metadata will be indexed during sync."
            db.commit()
    return EmailSendRead(
        communication_id=communication.id,
        provider_message_id=provider_message_id,
        provider_thread_id=provider_thread_id,
        status="sent",
        recipient=recipient,
    )


def sync_email_account(
    db: Session,
    account: EmailAccount,
    *,
    settings: Settings | None = None,
    client: GoogleGmailClient | None = None,
) -> EmailSyncRead:
    settings = settings or get_settings()
    if settings.email_configuration_blockers or not settings.email_sync_enabled:
        raise EmailConfigurationError("Email synchronization is not enabled.")
    if account.status != "active" or not account.sync_enabled:
        raise EmailConfigurationError("This email account is not active for synchronization.")
    gmail = client or get_google_gmail_client(settings)
    access_token = get_account_access_token(db, account, settings, gmail)
    if not account.history_cursor:
        profile = gmail.get_profile(access_token)
        account.history_cursor = profile.history_id
        account.last_synced_at = datetime.now(UTC)
        db.commit()
        return EmailSyncRead(
            account_id=account.id,
            imported_messages=0,
            history_cursor=account.history_cursor,
            synced_at=account.last_synced_at,
        )

    imported = 0
    page_token: str | None = None
    newest_history_id = account.history_cursor
    try:
        while True:
            history = gmail.list_history(
                access_token,
                start_history_id=account.history_cursor,
                page_token=page_token,
            )
            newest_history_id = str(history.get("historyId", newest_history_id))
            message_ids = {
                str(item["message"]["id"])
                for entry in history.get("history", [])
                if isinstance(entry, dict)
                for item in entry.get("messagesAdded", [])
                if isinstance(item, dict)
                and isinstance(item.get("message"), dict)
                and item["message"].get("id")
            }
            for message_id in message_ids:
                if import_gmail_message(
                    db,
                    account,
                    gmail.get_message(access_token, message_id),
                ):
                    imported += 1
            page_token = str(history["nextPageToken"]) if history.get("nextPageToken") else None
            if not page_token:
                break
        account.history_cursor = newest_history_id
        account.last_synced_at = datetime.now(UTC)
        account.last_error = None
        db.commit()
    except GoogleGmailError as exc:
        db.rollback()
        refreshed_account = db.get(EmailAccount, account.id)
        if refreshed_account is not None and exc.status_code == 404:
            return recover_expired_history_cursor(
                db,
                refreshed_account,
                access_token=access_token,
                gmail=gmail,
            )
        if refreshed_account is not None:
            refreshed_account.last_error = str(exc)
            db.commit()
        raise
    assert account.last_synced_at is not None
    return EmailSyncRead(
        account_id=account.id,
        imported_messages=imported,
        history_cursor=account.history_cursor,
        synced_at=account.last_synced_at,
    )


def recover_expired_history_cursor(
    db: Session,
    account: EmailAccount,
    *,
    access_token: str,
    gmail: GoogleGmailClient,
) -> EmailSyncRead:
    imported = 0
    page_token: str | None = None
    while True:
        messages = gmail.list_messages(access_token, page_token=page_token)
        for item in messages.get("messages", []):
            if not isinstance(item, dict) or not item.get("id"):
                continue
            if import_gmail_message(
                db,
                account,
                gmail.get_message(access_token, str(item["id"])),
            ):
                imported += 1
        page_token = str(messages["nextPageToken"]) if messages.get("nextPageToken") else None
        if not page_token:
            break
    profile = gmail.get_profile(access_token)
    account.history_cursor = profile.history_id
    account.last_synced_at = datetime.now(UTC)
    account.last_error = None
    db.commit()
    return EmailSyncRead(
        account_id=account.id,
        imported_messages=imported,
        history_cursor=account.history_cursor,
        synced_at=account.last_synced_at,
    )


def sync_next_email_account(
    db: Session,
    settings: Settings | None = None,
    client: GoogleGmailClient | None = None,
) -> UUID | None:
    settings = settings or get_settings()
    if settings.email_configuration_blockers or not settings.email_sync_enabled:
        return None
    due_before = datetime.now(UTC) - timedelta(seconds=settings.email_sync_poll_seconds)
    account = db.scalar(
        select(EmailAccount)
        .where(
            EmailAccount.status == "active",
            EmailAccount.sync_enabled.is_(True),
            or_(
                EmailAccount.last_synced_at.is_(None),
                EmailAccount.last_synced_at <= due_before,
            ),
        )
        .order_by(EmailAccount.last_synced_at.asc())
    )
    if account is None:
        return None
    sync_email_account(db, account, settings=settings, client=client)
    return account.id


def get_attachment_content(
    db: Session,
    principal: Principal,
    attachment_id: UUID,
    *,
    settings: Settings | None = None,
    client: GoogleGmailClient | None = None,
) -> tuple[EmailAttachmentRead, bytes] | None:
    attachment = db.scalar(
        select(EmailAttachment).where(
            EmailAttachment.id == attachment_id,
            EmailAttachment.organization_id == principal.organization_id,
        )
    )
    if attachment is None:
        return None
    communication = db.get(CommunicationRecord, attachment.communication_record_id)
    if communication is None or communication.conversation_id is None:
        return None
    if get_scoped_conversation(db, principal, communication.conversation_id) is None:
        return None
    account = db.get(EmailAccount, attachment.email_account_id)
    if account is None:
        return None
    settings = settings or get_settings()
    gmail = client or get_google_gmail_client(settings)
    access_token = get_account_access_token(db, account, settings, gmail)
    content = gmail.get_attachment(
        access_token,
        message_id=attachment.provider_message_id,
        attachment_id=attachment.provider_attachment_id,
    )
    if len(content) > settings.email_max_attachment_bytes:
        raise EmailAttachmentError("The attachment exceeds Stonegate's download limit.")
    return (
        EmailAttachmentRead(
            id=attachment.id,
            filename=attachment.filename,
            content_type=attachment.content_type,
            size_bytes=attachment.size_bytes,
        ),
        content,
    )


def import_gmail_message(
    db: Session,
    account: EmailAccount,
    message: dict[str, Any],
) -> bool:
    message_id = str(message.get("id", ""))
    if not message_id:
        return False
    existing = db.scalar(
        select(CommunicationRecord).where(
            CommunicationRecord.organization_id == account.organization_id,
            CommunicationRecord.provider == "google",
            CommunicationRecord.provider_message_id == message_id,
        )
    )
    if existing is not None:
        index_message_attachments(db, account, existing, message)
        return False

    headers = message_headers(message)
    from_addresses = normalized_addresses(headers.get("from", ""))
    to_addresses = normalized_addresses(", ".join([headers.get("to", ""), headers.get("cc", "")]))
    account_address = account.email_address.lower()
    direction = "outbound" if account_address in from_addresses else "inbound"
    external_addresses = (
        [address for address in to_addresses if address != account_address]
        if direction == "outbound"
        else [address for address in from_addresses if address != account_address]
    )
    if not external_addresses:
        return False
    contact_method = db.scalar(
        select(ContactMethod).where(
            ContactMethod.organization_id == account.organization_id,
            ContactMethod.method_type == "email",
            ContactMethod.normalized_value.in_(external_addresses),
        )
    )
    if contact_method is None:
        return False
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.organization_id == account.organization_id,
            Conversation.contact_id == contact_method.contact_id,
        )
    )
    if conversation is None:
        return False
    lead = db.get(Lead, conversation.lead_id)
    if lead is None:
        return False

    occurred_at = gmail_occurred_at(message)
    body = message_body(message)[:4000] or "(Email contained no readable message body.)"
    communication = CommunicationRecord(
        organization_id=account.organization_id,
        conversation_id=conversation.id,
        lead_id=lead.id,
        contact_id=contact_method.contact_id,
        actor_user_id=account.user_id if direction == "outbound" else None,
        direction=direction,
        channel="email",
        status="sent" if direction == "outbound" else "received",
        provider="google",
        provider_message_id=message_id,
        subject=headers.get("subject", "")[:255] or None,
        body=body,
        occurred_at=occurred_at,
        external_payload={
            "id": message_id,
            "threadId": str(message.get("threadId", "")),
            "labelIds": list(message.get("labelIds", [])),
        },
        communication_metadata={
            "source": "gmail_sync",
            "email_account_id": str(account.id),
            "provider_thread_id": str(message.get("threadId", "")),
            "rfc_message_id": headers.get("message-id", ""),
            "references": headers.get("references", ""),
            "in_reply_to": headers.get("in-reply-to", ""),
            "from": headers.get("from", ""),
            "to": headers.get("to", ""),
        },
    )
    db.add(communication)
    db.flush()
    index_message_attachments(db, account, communication, message)
    update_conversation_activity(conversation, direction=direction, occurred_at=occurred_at)
    db.add(
        CommunicationProviderEvent(
            organization_id=account.organization_id,
            conversation_id=conversation.id,
            provider="google",
            event_type="gmail.message_added",
            external_event_id=f"{account.id}:{message_id}",
            processing_status="processed",
            payload={
                "message_id": message_id,
                "thread_id": str(message.get("threadId", "")),
                "direction": direction,
            },
            received_at=datetime.now(UTC),
            processed_at=datetime.now(UTC),
            error_message=None,
        )
    )
    if direction == "inbound":
        db.add(
            ActivityEvent(
                organization_id=account.organization_id,
                actor_user_id=None,
                entity_type="lead",
                entity_id=lead.id,
                event_type="lead.email_received",
                summary=f"Email received from {external_addresses[0]}.",
            )
        )
    return True


def index_message_attachments(
    db: Session,
    account: EmailAccount,
    communication: CommunicationRecord,
    message: dict[str, Any],
) -> None:
    for part in walk_message_parts(message.get("payload", {})):
        filename = str(part.get("filename", "")).strip()
        body = part.get("body", {})
        attachment_id = str(body.get("attachmentId", "")) if isinstance(body, dict) else ""
        if not filename or not attachment_id:
            continue
        exists = db.scalar(
            select(EmailAttachment).where(
                EmailAttachment.communication_record_id == communication.id,
                EmailAttachment.provider_attachment_id == attachment_id,
            )
        )
        if exists is not None:
            continue
        headers = {
            str(item.get("name", "")).lower(): str(item.get("value", ""))
            for item in part.get("headers", [])
            if isinstance(item, dict)
        }
        disposition_header = headers.get("content-disposition", "attachment").lower()
        db.add(
            EmailAttachment(
                organization_id=account.organization_id,
                communication_record_id=communication.id,
                email_account_id=account.id,
                provider_message_id=str(message.get("id", "")),
                provider_attachment_id=attachment_id,
                filename=filename[:500],
                content_type=str(part.get("mimeType", "application/octet-stream"))[:255],
                size_bytes=int(body.get("size", 0)),
                content_id=headers.get("content-id", "")[:500] or None,
                disposition="inline" if "inline" in disposition_header else "attachment",
                attachment_metadata=None,
            )
        )


def get_account_access_token(
    db: Session,
    account: EmailAccount,
    settings: Settings,
    client: GoogleGmailClient,
) -> str:
    now = datetime.now(UTC)
    expires_at = account.access_token_expires_at
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if (
        account.encrypted_access_token
        and expires_at is not None
        and expires_at > now + timedelta(seconds=60)
    ):
        return decrypt_token(account.encrypted_access_token, settings)
    refresh_token = decrypt_token(account.encrypted_refresh_token, settings)
    token = client.refresh_access_token(refresh_token)
    account.encrypted_access_token = encrypt_token(token.access_token, settings)
    account.access_token_expires_at = now + timedelta(seconds=token.expires_in)
    account.status = "active"
    account.last_error = None
    db.commit()
    return token.access_token


def get_scoped_email_account(
    db: Session,
    principal: Principal,
    account_id: UUID,
    *,
    allow_shared: bool,
) -> EmailAccount | None:
    filters = [
        EmailAccount.id == account_id,
        EmailAccount.organization_id == principal.organization_id,
    ]
    if PermissionKeys.MANAGE_EMAIL_ACCOUNTS not in principal.permission_keys:
        if allow_shared:
            filters.append(
                or_(
                    EmailAccount.user_id == principal.user_id,
                    EmailAccount.is_shared.is_(True),
                )
            )
        else:
            filters.append(EmailAccount.user_id == principal.user_id)
    return db.scalar(select(EmailAccount).where(*filters))


def decode_outbound_attachments(
    payload: EmailSendRequest,
    settings: Settings,
) -> list[tuple[str, str, bytes]]:
    result: list[tuple[str, str, bytes]] = []
    total_size = 0
    for attachment in payload.attachments:
        try:
            content = base64.b64decode(attachment.content_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise EmailAttachmentError(f"{attachment.filename} is not a valid attachment.") from exc
        total_size += len(content)
        if total_size > settings.email_max_attachment_bytes:
            raise EmailAttachmentError(
                "Email attachments exceed Stonegate's configured size limit."
            )
        result.append((attachment.filename, attachment.content_type, content))
    return result


def append_signature(body: str, signature: str | None) -> str:
    signature = signature.strip() if signature else ""
    return f"{body}\n\n--\n{signature}" if signature else body


def mark_email_dispatch_failed(db: Session, dispatch_id: UUID, message: str) -> None:
    dispatch = db.get(CommunicationDispatch, dispatch_id)
    if dispatch is None:
        return
    dispatch.status = "failed"
    dispatch.error_code = "provider_error"
    dispatch.error_message = message[:2000]
    dispatch.completed_at = datetime.now(UTC)
    db.commit()


def email_account_to_read(
    account: EmailAccount,
    principal: Principal,
) -> EmailAccountRead:
    return EmailAccountRead(
        id=account.id,
        user_id=account.user_id,
        provider=account.provider,
        email_address=account.email_address,
        display_name=account.display_name,
        status=account.status,
        is_shared=account.is_shared,
        sync_enabled=account.sync_enabled,
        last_synced_at=account.last_synced_at,
        last_error=account.last_error,
        signature_text=account.signature_text,
        is_owned_by_current_user=account.user_id == principal.user_id,
    )


def email_template_to_read(template: EmailTemplate) -> EmailTemplateRead:
    return EmailTemplateRead(
        id=template.id,
        created_by_user_id=template.created_by_user_id,
        name=template.name,
        subject_template=template.subject_template,
        body_template=template.body_template,
        is_shared=template.is_shared,
        is_active=template.is_active,
    )


def message_headers(message: dict[str, Any]) -> dict[str, str]:
    payload = message.get("payload", {})
    headers = payload.get("headers", []) if isinstance(payload, dict) else []
    return {
        str(item.get("name", "")).lower(): str(item.get("value", ""))
        for item in headers
        if isinstance(item, dict)
    }


def normalized_addresses(value: str) -> list[str]:
    return [address.strip().lower() for _, address in getaddresses([value]) if address.strip()]


def walk_message_parts(part: Any) -> list[dict[str, Any]]:
    if not isinstance(part, dict):
        return []
    result = [part]
    for child in part.get("parts", []):
        result.extend(walk_message_parts(child))
    return result


def message_body(message: dict[str, Any]) -> str:
    payload = message.get("payload", {})
    plain = decode_part_data(
        next(
            (part for part in walk_message_parts(payload) if part.get("mimeType") == "text/plain"),
            None,
        )
    )
    if plain:
        return plain.strip()
    html = decode_part_data(
        next(
            (part for part in walk_message_parts(payload) if part.get("mimeType") == "text/html"),
            None,
        )
    )
    if not html:
        return ""
    extractor = _HtmlTextExtractor()
    extractor.feed(html)
    return "\n".join(extractor.parts)


def decode_part_data(part: dict[str, Any] | None) -> str:
    if not part or not isinstance(part.get("body"), dict):
        return ""
    encoded = str(part["body"].get("data", ""))
    if not encoded:
        return ""
    try:
        return base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode(
            "utf-8", errors="replace"
        )
    except ValueError:
        return ""


def gmail_occurred_at(message: dict[str, Any]) -> datetime:
    try:
        return datetime.fromtimestamp(int(str(message["internalDate"])) / 1000, tz=UTC)
    except (KeyError, TypeError, ValueError):
        return datetime.now(UTC)
