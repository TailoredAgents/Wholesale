from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_any_permission
from app.core.database import get_db
from app.domain.rbac import PermissionKeys
from app.schemas.approvals import ApprovalDecision, ApprovalListResponse, ApprovalRequestRead
from app.services.approvals import decide_approval_request, list_approval_requests

router = APIRouter(prefix="/api/v1/approvals", tags=["approvals"])
view_approvals_dependency = require_any_permission(
    PermissionKeys.VIEW_AUDIT_LOGS,
    PermissionKeys.APPROVE_OFFERS,
)


@router.get("")
def read_approval_requests(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_approvals_dependency)],
) -> ApprovalListResponse:
    return ApprovalListResponse(items=list_approval_requests(db, principal))


@router.patch("/{approval_id}/decision")
def decide_approval(
    approval_id: UUID,
    payload: ApprovalDecision,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_approvals_dependency)],
) -> ApprovalRequestRead:
    try:
        approval = decide_approval_request(db, principal, approval_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    if approval is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval request not found.",
        )
    return approval
