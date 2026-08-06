from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_any_permission, require_permission
from app.core.config import get_settings
from app.core.database import get_db
from app.domain.rbac import PermissionKeys
from app.integrations.email_delivery import EmailProviderError
from app.integrations.google_gmail import GoogleGmailError
from app.schemas.email import (
    EmailAccountListResponse,
    EmailAccountRead,
    EmailAccountUpdate,
    EmailAdminOptionsRead,
    EmailOAuthAuthorizeRead,
    EmailRecipientOptionListResponse,
    EmailRoutingExceptionListResponse,
    EmailRoutingExceptionRead,
    EmailRoutingResolutionRequest,
    EmailSenderAliasCreate,
    EmailSenderAliasListResponse,
    EmailSenderAliasRead,
    EmailSenderAliasUpdate,
    EmailSenderGrantCreate,
    EmailSendRead,
    EmailSendRequest,
    EmailSyncRead,
    EmailTemplateCreate,
    EmailTemplateListResponse,
    EmailTemplateRead,
    EmailTemplateUpdate,
    GeneralEmailComposeRead,
    GeneralEmailComposeRequest,
)
from app.services.email import (
    EmailAttachmentError,
    EmailConfigurationError,
    EmailDispatchConflictError,
    complete_google_authorization,
    compose_general_email,
    create_email_template,
    create_google_authorization,
    disconnect_email_account,
    get_attachment_content,
    get_scoped_email_account,
    list_email_accounts,
    list_email_templates,
    search_email_recipients,
    send_conversation_email,
    sync_email_account,
    update_email_account,
    update_email_template,
)
from app.services.email_admin import (
    get_email_admin_options,
    list_email_routing_exceptions,
    resolve_email_routing_exception,
)
from app.services.email_aliases import (
    create_email_sender_alias,
    grant_email_sender_access,
    list_email_sender_aliases,
    revoke_email_sender_access,
    update_email_sender_alias,
)

router = APIRouter(prefix="/api/v1/email", tags=["email"])
email_user_dependency = require_any_permission(
    PermissionKeys.SEND_EMAIL,
    PermissionKeys.SEND_ASSIGNED_EMAIL,
)
email_manager_dependency = require_any_permission(PermissionKeys.MANAGE_EMAIL_ACCOUNTS)
global_email_dependency = require_permission(PermissionKeys.SEND_EMAIL)


@router.get("/accounts")
def read_email_accounts(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(email_user_dependency)],
) -> EmailAccountListResponse:
    return list_email_accounts(db, principal)


@router.get("/aliases")
def read_email_sender_aliases(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(email_user_dependency)],
) -> EmailSenderAliasListResponse:
    return list_email_sender_aliases(db, principal)


@router.get("/recipients")
def read_email_recipient_options(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(global_email_dependency)],
    q: str = Query(default="", max_length=255),
) -> EmailRecipientOptionListResponse:
    return EmailRecipientOptionListResponse(items=search_email_recipients(db, principal, q))


@router.post("/aliases", status_code=201)
def post_email_sender_alias(
    payload: EmailSenderAliasCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(email_manager_dependency)],
) -> EmailSenderAliasRead:
    try:
        return create_email_sender_alias(db, principal, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


@router.patch("/aliases/{alias_id}")
def patch_email_sender_alias(
    alias_id: UUID,
    payload: EmailSenderAliasUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(email_manager_dependency)],
) -> EmailSenderAliasRead:
    try:
        alias = update_email_sender_alias(db, principal, alias_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if alias is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email alias not found.")
    return alias


@router.put("/aliases/{alias_id}/grants")
def put_email_sender_grant(
    alias_id: UUID,
    payload: EmailSenderGrantCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(email_manager_dependency)],
) -> EmailSenderAliasRead:
    try:
        alias = grant_email_sender_access(db, principal, alias_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if alias is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email alias not found.")
    return alias


@router.delete("/aliases/{alias_id}/grants/{user_id}")
def delete_email_sender_grant(
    alias_id: UUID,
    user_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(email_manager_dependency)],
) -> EmailSenderAliasRead:
    alias = revoke_email_sender_access(db, principal, alias_id, user_id)
    if alias is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email alias not found.")
    return alias


@router.get("/admin/options")
def read_email_admin_options(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(email_manager_dependency)],
) -> EmailAdminOptionsRead:
    return get_email_admin_options(db, principal)


@router.get("/routing-exceptions")
def read_email_routing_exceptions(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(email_manager_dependency)],
) -> EmailRoutingExceptionListResponse:
    return list_email_routing_exceptions(db, principal)


@router.post("/routing-exceptions/{event_id}/resolve")
def resolve_resend_routing_exception(
    event_id: UUID,
    payload: EmailRoutingResolutionRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(email_manager_dependency)],
) -> EmailRoutingExceptionRead:
    try:
        event = resolve_email_routing_exception(db, principal, event_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email routing exception not found.",
        )
    return event


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
    except (EmailProviderError, GoogleGmailError) as exc:
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
    except (EmailProviderError, GoogleGmailError) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return result


@router.post("/compose", status_code=201)
def compose_new_email(
    payload: GeneralEmailComposeRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(global_email_dependency)],
) -> GeneralEmailComposeRead:
    try:
        return compose_general_email(db, principal, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except EmailAttachmentError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except EmailDispatchConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (EmailConfigurationError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except (EmailProviderError, GoogleGmailError) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


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
