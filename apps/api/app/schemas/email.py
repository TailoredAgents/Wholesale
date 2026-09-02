from datetime import datetime
from email.utils import parseaddr
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class EmailAccountRead(BaseModel):
    id: UUID
    user_id: UUID
    provider: str
    email_address: str
    display_name: str
    status: str
    is_shared: bool
    sync_enabled: bool
    last_synced_at: datetime | None
    last_error: str | None
    signature_text: str | None
    is_owned_by_current_user: bool


class EmailAccountListResponse(BaseModel):
    items: list[EmailAccountRead]
    provider_configured: bool
    configuration_blockers: list[str]


class EmailOAuthAuthorizeRead(BaseModel):
    authorization_url: str


class EmailAccountUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    signature_text: str | None = Field(default=None, max_length=4000)
    is_shared: bool | None = None
    sync_enabled: bool | None = None


class EmailSenderGrantCreate(BaseModel):
    user_id: UUID
    access_level: Literal["sender", "watcher"] = "sender"
    can_send: bool = True
    receives_notifications: bool = True


class EmailSenderGrantRead(BaseModel):
    id: UUID
    user_id: UUID
    user_name: str
    access_level: str
    can_send: bool
    receives_notifications: bool


class EmailSenderAliasCreate(BaseModel):
    email_address: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=255)
    alias_type: Literal["named", "department", "contractor"]
    purpose_key: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9_]+$")
    status: Literal["active", "reserved", "disabled"] = "active"
    owner_user_id: UUID | None = None
    assigned_team_id: UUID | None = None
    provider: Literal["resend", "simulated"] = "resend"
    inbound_enabled: bool = True
    outbound_enabled: bool = True
    is_default: bool = False
    signature_text: str | None = Field(default=None, max_length=4000)
    routing_metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("email_address")
    @classmethod
    def normalize_email_address(cls, value: str) -> str:
        normalized = value.strip().lower()
        local, separator, domain = normalized.rpartition("@")
        if (
            not separator
            or not local
            or not domain
            or "." not in domain
            or any(character.isspace() for character in normalized)
        ):
            raise ValueError("Enter a valid company email address.")
        return normalized


class EmailSenderAliasUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    purpose_key: str | None = Field(
        default=None,
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9_]+$",
    )
    status: Literal["active", "reserved", "disabled"] | None = None
    owner_user_id: UUID | None = None
    assigned_team_id: UUID | None = None
    inbound_enabled: bool | None = None
    outbound_enabled: bool | None = None
    is_default: bool | None = None
    signature_text: str | None = Field(default=None, max_length=4000)
    routing_metadata: dict[str, object] | None = None


class EmailSenderAliasRead(BaseModel):
    id: UUID
    provider: str
    email_address: str
    display_name: str
    alias_type: str
    purpose_key: str
    status: str
    owner_user_id: UUID | None
    owner_user_name: str | None
    assigned_team_id: UUID | None
    assigned_team_name: str | None
    inbound_enabled: bool
    outbound_enabled: bool
    is_default: bool
    signature_text: str | None
    routing_metadata: dict[str, object]
    can_send: bool
    can_manage: bool
    grants: list[EmailSenderGrantRead]


class EmailSenderAliasListResponse(BaseModel):
    items: list[EmailSenderAliasRead]
    provider: str
    provider_configured: bool
    configuration_blockers: list[str]


class EmailAdminUserRead(BaseModel):
    id: UUID
    email: str
    display_name: str
    role_keys: list[str]


class EmailAdminTeamRead(BaseModel):
    id: UUID
    name: str
    team_type: str


class EmailAdminOptionsRead(BaseModel):
    users: list[EmailAdminUserRead]
    teams: list[EmailAdminTeamRead]


class EmailRoutingExceptionRead(BaseModel):
    id: UUID
    processing_status: str
    provider_message_id: str
    sender: str
    recipients: list[str]
    subject: str | None
    received_at: datetime
    reason: str
    candidate_conversation_ids: list[UUID]


class EmailRoutingExceptionListResponse(BaseModel):
    items: list[EmailRoutingExceptionRead]


class EmailRoutingResolutionRequest(BaseModel):
    conversation_id: UUID


class EmailDeadLetterRead(BaseModel):
    id: UUID
    event_type: str
    provider_message_id: str
    sender: str
    recipients: list[str]
    subject: str | None
    received_at: datetime
    processed_at: datetime | None
    attempt_count: int
    error_message: str | None
    processing_status: str


class EmailDeadLetterListResponse(BaseModel):
    items: list[EmailDeadLetterRead]


class EmailDeadLetterRequeueRequest(BaseModel):
    reason: str = Field(min_length=10, max_length=500)


class EmailRecipientOptionRead(BaseModel):
    contact_id: UUID
    display_name: str
    email_address: str
    contact_type: str


class EmailRecipientOptionListResponse(BaseModel):
    items: list[EmailRecipientOptionRead]


class EmailTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    subject_template: str = Field(min_length=1, max_length=255)
    body_template: str = Field(min_length=1, max_length=4000)
    is_shared: bool = True


class EmailTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    subject_template: str | None = Field(default=None, min_length=1, max_length=255)
    body_template: str | None = Field(default=None, min_length=1, max_length=4000)
    is_shared: bool | None = None
    is_active: bool | None = None


class EmailTemplateRead(BaseModel):
    id: UUID
    created_by_user_id: UUID
    name: str
    subject_template: str
    body_template: str
    is_shared: bool
    is_active: bool


class EmailTemplateListResponse(BaseModel):
    items: list[EmailTemplateRead]


class OutboundEmailAttachment(BaseModel):
    filename: str = Field(min_length=1, max_length=500)
    content_type: str = Field(min_length=1, max_length=255)
    content_base64: str = Field(min_length=1)

    @field_validator("content_base64")
    @classmethod
    def reject_data_url_prefix(cls, value: str) -> str:
        if value.startswith("data:"):
            raise ValueError("Attachment content must be raw base64 without a data URL prefix.")
        return value


class EmailSendRequest(BaseModel):
    email_sender_alias_id: UUID | None = None
    email_account_id: UUID | None = None
    to: list[str] = Field(default_factory=list, max_length=20)
    subject: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1, max_length=4000)
    html_body: str | None = Field(default=None, max_length=100_000)
    cc: list[str] = Field(default_factory=list, max_length=20)
    bcc: list[str] = Field(default_factory=list, max_length=20)
    idempotency_key: str = Field(min_length=8, max_length=120)
    attachments: list[OutboundEmailAttachment] = Field(default_factory=list, max_length=5)

    @field_validator("to", "cc", "bcc")
    @classmethod
    def normalize_recipients(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            if "\r" in value or "\n" in value:
                raise ValueError("Email recipients cannot contain line breaks.")
            _name, address = parseaddr(value.strip())
            local, separator, domain = address.rpartition("@")
            if not separator or not local or "." not in domain:
                raise ValueError("Enter valid email recipients.")
            candidate = address.lower()
            if candidate not in normalized:
                normalized.append(candidate)
        return normalized

    @model_validator(mode="after")
    def require_one_sender(self) -> "EmailSendRequest":
        if bool(self.email_sender_alias_id) == bool(self.email_account_id):
            raise ValueError("Select exactly one Stonegate email alias or legacy email account.")
        if set(self.cc) & set(self.bcc):
            raise ValueError("An email address cannot be both CC and BCC.")
        return self


class GeneralEmailComposeRequest(EmailSendRequest):
    contact_name: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def require_primary_recipient(self) -> "GeneralEmailComposeRequest":
        if not self.to:
            raise ValueError("Enter at least one To recipient.")
        return self


class EmailSendRead(BaseModel):
    communication_id: UUID
    provider_message_id: str
    provider_thread_id: str
    status: str
    recipient: str


class GeneralEmailComposeRead(BaseModel):
    conversation_id: UUID
    message: EmailSendRead


class EmailSyncRead(BaseModel):
    account_id: UUID
    imported_messages: int
    history_cursor: str | None
    synced_at: datetime


class EmailAttachmentRead(BaseModel):
    id: UUID
    filename: str
    content_type: str
    size_bytes: int
    content_url: str | None = None
    malware_scan_status: str | None = None
