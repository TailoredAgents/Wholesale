from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


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
    email_account_id: UUID
    subject: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1, max_length=4000)
    idempotency_key: str = Field(min_length=8, max_length=120)
    attachments: list[OutboundEmailAttachment] = Field(default_factory=list, max_length=5)


class EmailSendRead(BaseModel):
    communication_id: UUID
    provider_message_id: str
    provider_thread_id: str
    status: str
    recipient: str


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
