from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_any_permission, require_permission
from app.core.database import get_db
from app.domain.rbac import PermissionKeys
from app.integrations.twilio_messaging import TwilioMessagingError
from app.schemas.inbox import (
    ConversationDetailRead,
    ConversationHandoffRequest,
    ConversationListResponse,
    ConversationRead,
    ConversationResolutionRead,
    ConversationWatcherCreate,
    GeneralConversationClassification,
    GeneralConversationLeadCreate,
    GeneralConversationLeadLink,
    InboxAssigneeListResponse,
    MailboxResponseOverviewRead,
    SmsSendRead,
    SmsSendRequest,
)
from app.services.inbox import (
    add_conversation_watcher,
    classify_general_conversation,
    convert_general_conversation_to_lead,
    get_conversation_detail,
    get_inbox_attachment_content,
    get_mailbox_response_overview,
    handoff_conversation,
    link_general_conversation_to_lead,
    list_conversations,
    list_eligible_assignees,
    mark_conversation_read,
    remove_conversation_watcher,
)
from app.services.lead_lifecycle import LeadLifecycleConflictError
from app.services.messaging import (
    SmsComplianceError,
    SmsConfigurationError,
    SmsDispatchConflictError,
    send_conversation_sms,
)

router = APIRouter(prefix="/api/v1/inbox", tags=["inbox"])
INLINE_ATTACHMENT_CONTENT_TYPES = frozenset(
    {"image/gif", "image/jpeg", "image/png", "image/webp"}
)
view_inbox_dependency = require_any_permission(
    PermissionKeys.VIEW_CONVERSATIONS,
    PermissionKeys.VIEW_ASSIGNED_CONVERSATIONS,
)
handoff_dependency = require_any_permission(
    PermissionKeys.MANAGE_CONVERSATION_ASSIGNMENTS,
    PermissionKeys.HANDOFF_ASSIGNED_CONVERSATIONS,
)
manage_assignments_dependency = require_permission(PermissionKeys.MANAGE_CONVERSATION_ASSIGNMENTS)
send_sms_dependency = require_any_permission(
    PermissionKeys.SEND_SMS,
    PermissionKeys.SEND_ASSIGNED_SMS,
)

edit_leads_dependency = require_permission(PermissionKeys.EDIT_LEADS)


@router.get("/conversations")
def read_conversations(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_inbox_dependency)],
    queue: str | None = Query(default=None),
    assigned_to_me: bool = Query(default=False),
) -> ConversationListResponse:
    try:
        items = list_conversations(
            db,
            principal,
            queue_key=queue,
            assigned_to_me=assigned_to_me,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return ConversationListResponse(items=items)


@router.get("/response-overview")
def read_mailbox_response_overview(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_inbox_dependency)],
) -> MailboxResponseOverviewRead:
    return get_mailbox_response_overview(db, principal)


@router.get("/conversations/{conversation_id}")
def read_conversation(
    conversation_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_inbox_dependency)],
) -> ConversationDetailRead:
    conversation = get_conversation_detail(db, principal, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return conversation


@router.patch("/conversations/{conversation_id}/read")
def mark_inbox_conversation_read(
    conversation_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_inbox_dependency)],
) -> ConversationRead:
    conversation = mark_conversation_read(db, principal, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return conversation


@router.get("/attachments/{attachment_id}/content")
def read_inbox_attachment(
    attachment_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_inbox_dependency)],
) -> Response:
    try:
        result = get_inbox_attachment_content(db, principal, attachment_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found.")
    attachment, content = result
    safe_name = quote(attachment.filename)
    disposition = (
        "inline"
        if attachment.content_type.lower() in INLINE_ATTACHMENT_CONTENT_TYPES
        else "attachment"
    )
    return Response(
        content=content,
        media_type=attachment.content_type,
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f"{disposition}; filename*=UTF-8''{safe_name}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/conversations/{conversation_id}/convert-to-lead", status_code=201)
def convert_inbox_conversation_to_lead(
    conversation_id: UUID,
    payload: GeneralConversationLeadCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_leads_dependency)],
) -> ConversationResolutionRead:
    try:
        result = convert_general_conversation_to_lead(db, principal, conversation_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return result


@router.post("/conversations/{conversation_id}/link-to-lead")
def link_inbox_conversation_to_lead(
    conversation_id: UUID,
    payload: GeneralConversationLeadLink,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_leads_dependency)],
) -> ConversationResolutionRead:
    try:
        result = link_general_conversation_to_lead(db, principal, conversation_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return result


@router.post("/conversations/{conversation_id}/classification")
def classify_inbox_general_conversation(
    conversation_id: UUID,
    payload: GeneralConversationClassification,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(handoff_dependency)],
) -> ConversationResolutionRead:
    try:
        result = classify_general_conversation(db, principal, conversation_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return result


@router.post("/conversations/{conversation_id}/messages/sms", status_code=201)
def send_inbox_sms(
    conversation_id: UUID,
    payload: SmsSendRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(send_sms_dependency)],
) -> SmsSendRead:
    try:
        result = send_conversation_sms(
            db,
            principal,
            conversation_id,
            payload,
            require_permission=False,
        )
    except LeadLifecycleConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except SmsComplianceError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except SmsDispatchConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except SmsConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except TwilioMessagingError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return result


@router.get("/assignees")
def read_eligible_assignees(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(handoff_dependency)],
) -> InboxAssigneeListResponse:
    return InboxAssigneeListResponse(items=list_eligible_assignees(db, principal))


@router.post("/conversations/{conversation_id}/handoff")
def handoff_inbox_conversation(
    conversation_id: UUID,
    payload: ConversationHandoffRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(handoff_dependency)],
) -> ConversationRead:
    try:
        conversation = handoff_conversation(db, principal, conversation_id, payload)
    except LeadLifecycleConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return conversation


@router.post("/conversations/{conversation_id}/watchers")
def create_conversation_watcher(
    conversation_id: UUID,
    payload: ConversationWatcherCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_assignments_dependency)],
) -> ConversationRead:
    try:
        conversation = add_conversation_watcher(
            db,
            principal,
            conversation_id,
            payload,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return conversation


@router.delete("/conversations/{conversation_id}/watchers/{user_id}")
def delete_conversation_watcher(
    conversation_id: UUID,
    user_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_assignments_dependency)],
) -> ConversationRead:
    conversation = remove_conversation_watcher(db, principal, conversation_id, user_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return conversation
