from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_any_permission
from app.core.config import get_settings
from app.core.database import get_db
from app.domain.rbac import PermissionKeys
from app.integrations.google_gmail import GoogleGmailError
from app.schemas.email import (
    EmailAccountListResponse,
    EmailAccountRead,
    EmailAccountUpdate,
    EmailOAuthAuthorizeRead,
    EmailSendRead,
    EmailSendRequest,
    EmailSyncRead,
    EmailTemplateCreate,
    EmailTemplateListResponse,
    EmailTemplateRead,
    EmailTemplateUpdate,
)
from app.services.email import (
    EmailAttachmentError,
    EmailConfigurationError,
    EmailDispatchConflictError,
    complete_google_authorization,
    create_email_template,
    create_google_authorization,
    disconnect_email_account,
    get_attachment_content,
    get_scoped_email_account,
    list_email_accounts,
    list_email_templates,
    send_conversation_email,
    sync_email_account,
    update_email_account,
    update_email_template,
)

router = APIRouter(prefix="/api/v1/email", tags=["email"])
email_user_dependency = require_any_permission(
    PermissionKeys.SEND_EMAIL,
    PermissionKeys.SEND_ASSIGNED_EMAIL,
)


@router.get("/accounts")
def read_email_accounts(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(email_user_dependency)],
) -> EmailAccountListResponse:
    return list_email_accounts(db, principal)


@router.post("/oauth/google/authorize")
def authorize_google_email(
    principal: Annotated[Principal, Depends(email_user_dependency)],
) -> EmailOAuthAuthorizeRead:
    try:
        return create_google_authorization(principal)
    except EmailConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.get("/oauth/google/callback", include_in_schema=False)
def google_email_callback(
    db: Annotated[Session, Depends(get_db)],
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    settings = get_settings()
    destination = f"{settings.email_web_app_base_url.rstrip('/')}/os/inbox"
    if error or not code or not state:
        return RedirectResponse(f"{destination}?email=connection_cancelled", status_code=303)
    try:
        complete_google_authorization(db, code=code, state=state)
    except (EmailConfigurationError, GoogleGmailError):
        return RedirectResponse(f"{destination}?email=connection_failed", status_code=303)
    return RedirectResponse(f"{destination}?email=connected", status_code=303)


@router.patch("/accounts/{account_id}")
def patch_email_account(
    account_id: UUID,
    payload: EmailAccountUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(email_user_dependency)],
) -> EmailAccountRead:
    try:
        account = update_email_account(db, principal, account_id, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email account not found.",
        )
    return account


@router.delete("/accounts/{account_id}", status_code=204)
def delete_email_account(
    account_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(email_user_dependency)],
) -> Response:
    try:
        disconnected = disconnect_email_account(db, principal, account_id)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if not disconnected:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email account not found.",
        )
    return Response(status_code=204)


@router.post("/accounts/{account_id}/sync")
def synchronize_email_account(
    account_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(email_user_dependency)],
) -> EmailSyncRead:
    account = get_scoped_email_account(db, principal, account_id, allow_shared=True)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email account not found.",
        )
    try:
        return sync_email_account(db, account)
    except EmailConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except GoogleGmailError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/templates")
def read_email_templates(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(email_user_dependency)],
) -> EmailTemplateListResponse:
    return EmailTemplateListResponse(items=list_email_templates(db, principal))


@router.post("/templates", status_code=201)
def post_email_template(
    payload: EmailTemplateCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(email_user_dependency)],
) -> EmailTemplateRead:
    try:
        return create_email_template(db, principal, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.patch("/templates/{template_id}")
def patch_email_template(
    template_id: UUID,
    payload: EmailTemplateUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(email_user_dependency)],
) -> EmailTemplateRead:
    try:
        template = update_email_template(db, principal, template_id, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found.")
    return template


@router.delete("/templates/{template_id}", status_code=204)
def delete_email_template(
    template_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(email_user_dependency)],
) -> Response:
    try:
        template = update_email_template(
            db,
            principal,
            template_id,
            EmailTemplateUpdate(is_active=False),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found.")
    return Response(status_code=204)


@router.post("/conversations/{conversation_id}/messages", status_code=201)
def send_email_message(
    conversation_id: UUID,
    payload: EmailSendRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(email_user_dependency)],
) -> EmailSendRead:
    try:
        result = send_conversation_email(db, principal, conversation_id, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except EmailAttachmentError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except EmailDispatchConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except EmailConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except GoogleGmailError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return result


@router.get("/attachments/{attachment_id}")
def download_email_attachment(
    attachment_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(email_user_dependency)],
) -> Response:
    try:
        result = get_attachment_content(db, principal, attachment_id)
    except EmailAttachmentError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except (EmailConfigurationError, GoogleGmailError) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found.")
    attachment, content = result
    safe_name = quote(attachment.filename)
    return Response(
        content=content,
        media_type=attachment.content_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{safe_name}"},
    )
