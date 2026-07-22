from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_any_permission, require_permission
from app.core.database import get_db
from app.domain.rbac import PermissionKeys
from app.schemas.transactions import (
    ChecklistItemUpdate,
    ContractPackageCreate,
    ContractPackageRead,
    ContractTemplateRead,
    TransactionClose,
    TransactionDetail,
    TransactionDocumentRead,
    TransactionEventCreate,
    TransactionEventRead,
    TransactionOverview,
    TransactionPartyCreate,
    TransactionPartyRead,
    TransactionUpdate,
)
from app.services.transactions import (
    add_party,
    approve_template,
    close_transaction,
    create_contract_package,
    get_document,
    get_transaction_detail,
    list_templates,
    list_transactions,
    mark_contract_executed,
    mark_contract_sent,
    record_note,
    request_contract_approval,
    update_checklist_item,
    update_transaction,
    upload_document,
    upload_template,
)

router = APIRouter(prefix="/api/v1/transactions", tags=["transactions"])
view_dependency = require_permission(PermissionKeys.VIEW_DEALS)
edit_dependency = require_permission(PermissionKeys.EDIT_DEALS)
contract_dependency = require_permission(PermissionKeys.MODIFY_CONTRACTS)
send_dependency = require_permission(PermissionKeys.SEND_CONTRACTS)
template_dependency = require_any_permission(
    PermissionKeys.MODIFY_CONTRACTS,
    PermissionKeys.MANAGE_OPERATING_MODEL,
)


def not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found.")


@router.get("")
def read_transactions(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_dependency)],
) -> TransactionOverview:
    return list_transactions(db, principal)


@router.get("/templates")
def read_contract_templates(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_dependency)],
) -> list[ContractTemplateRead]:
    return list_templates(db, principal)


@router.post("/templates", status_code=201)
def create_contract_template(
    content: Annotated[bytes, Body(media_type="application/octet-stream")],
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(template_dependency)],
    file_name: str = Query(min_length=1, max_length=255),
    document_type: str = Query(min_length=1, max_length=80),
    state_code: str = Query(min_length=2, max_length=2),
    name: str = Query(min_length=1, max_length=255),
    notes: str | None = Query(default=None, max_length=1000),
    content_type: Annotated[str, Header(alias="Content-Type")] = "application/octet-stream",
) -> ContractTemplateRead:
    try:
        return upload_template(
            db,
            principal,
            content=content,
            file_name=file_name,
            content_type=content_type,
            document_type=document_type,
            state_code=state_code,
            name=name,
            notes=notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/templates/{template_id}/approve")
def approve_contract_template(
    template_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(template_dependency)],
) -> ContractTemplateRead:
    result = approve_template(db, principal, template_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Contract template not found.")
    return result


@router.get("/{transaction_id}")
def read_transaction(
    transaction_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_dependency)],
) -> TransactionDetail:
    result = get_transaction_detail(db, principal, transaction_id)
    if result is None:
        raise not_found()
    return result


@router.patch("/{transaction_id}")
def patch_transaction(
    transaction_id: UUID,
    payload: TransactionUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_dependency)],
) -> TransactionDetail:
    try:
        result = update_transaction(db, principal, transaction_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise not_found()
    return result


@router.post("/{transaction_id}/contract-packages", status_code=201)
def draft_contract_package(
    transaction_id: UUID,
    payload: ContractPackageCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(contract_dependency)],
) -> ContractPackageRead:
    try:
        result = create_contract_package(db, principal, transaction_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise not_found()
    return result


@router.post("/{transaction_id}/contract-packages/{package_id}/request-approval")
def submit_contract_package(
    transaction_id: UUID,
    package_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(contract_dependency)],
) -> ContractPackageRead:
    try:
        result = request_contract_approval(db, principal, transaction_id, package_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise not_found()
    return result


@router.post("/{transaction_id}/contract-packages/{package_id}/mark-sent")
def record_contract_sent(
    transaction_id: UUID,
    package_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(send_dependency)],
) -> ContractPackageRead:
    try:
        result = mark_contract_sent(db, principal, transaction_id, package_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise not_found()
    return result


@router.post("/{transaction_id}/contract-packages/{package_id}/mark-executed")
def record_contract_executed(
    transaction_id: UUID,
    package_id: UUID,
    document_id: Annotated[UUID, Query()],
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(contract_dependency)],
) -> ContractPackageRead:
    try:
        result = mark_contract_executed(db, principal, transaction_id, package_id, document_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise not_found()
    return result


@router.post("/{transaction_id}/documents", status_code=201)
def create_transaction_document(
    transaction_id: UUID,
    content: Annotated[bytes, Body(media_type="application/octet-stream")],
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_dependency)],
    file_name: str = Query(min_length=1, max_length=255),
    document_type: str = Query(min_length=1, max_length=80),
    title: str = Query(min_length=1, max_length=255),
    document_status: str = Query(default="final", min_length=1, max_length=40),
    package_id: Annotated[UUID | None, Query()] = None,
    notes: str | None = Query(default=None, max_length=1000),
    content_type: Annotated[str, Header(alias="Content-Type")] = "application/octet-stream",
) -> TransactionDocumentRead:
    try:
        result = upload_document(
            db,
            principal,
            transaction_id,
            content=content,
            file_name=file_name,
            content_type=content_type,
            document_type=document_type,
            title=title,
            status=document_status,
            package_id=package_id,
            notes=notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise not_found()
    return result


@router.get("/{transaction_id}/documents/{document_id}/content")
def download_transaction_document(
    transaction_id: UUID,
    document_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_dependency)],
) -> Response:
    document = get_document(db, principal, transaction_id, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return Response(
        content=document.file_data,
        media_type=document.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{document.file_name}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.post("/{transaction_id}/parties", status_code=201)
def create_transaction_party(
    transaction_id: UUID,
    payload: TransactionPartyCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_dependency)],
) -> TransactionPartyRead:
    result = add_party(db, principal, transaction_id, payload)
    if result is None:
        raise not_found()
    return result


@router.patch("/{transaction_id}/checklist/{item_id}")
def patch_checklist_item(
    transaction_id: UUID,
    item_id: UUID,
    payload: ChecklistItemUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_dependency)],
) -> TransactionDetail:
    try:
        result = update_checklist_item(db, principal, transaction_id, item_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise not_found()
    return result


@router.post("/{transaction_id}/events", status_code=201)
def create_transaction_event(
    transaction_id: UUID,
    payload: TransactionEventCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_dependency)],
) -> TransactionEventRead:
    result = record_note(db, principal, transaction_id, payload)
    if result is None:
        raise not_found()
    return result


@router.post("/{transaction_id}/close")
def finalize_transaction(
    transaction_id: UUID,
    payload: TransactionClose,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_dependency)],
) -> TransactionDetail:
    try:
        result = close_transaction(db, principal, transaction_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise not_found()
    return result
