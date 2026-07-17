from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
    ConversationWatcherCreate,
    InboxAssigneeListResponse,
    SmsSendRead,
    SmsSendRequest,
)
from app.services.inbox import (
    add_conversation_watcher,
    get_conversation_detail,
    handoff_conversation,
    list_conversations,
    list_eligible_assignees,
    mark_conversation_read,
    remove_conversation_watcher,
)
from app.services.messaging import (
    SmsComplianceError,
    SmsConfigurationError,
    SmsDispatchConflictError,
    send_conversation_sms,
)

router = APIRouter(prefix="/api/v1/inbox", tags=["inbox"])
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


@router.post("/conversations/{conversation_id}/messages/sms", status_code=201)
def send_inbox_sms(
    conversation_id: UUID,
    payload: SmsSendRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(send_sms_dependency)],
) -> SmsSendRead:
    try:
        result = send_conversation_sms(db, principal, conversation_id, payload)
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
