from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_permission
from app.core.database import get_db
from app.domain.rbac import PermissionKeys
from app.models.foundation import Buyer
from app.schemas.buyers import (
    BuyerCreate,
    BuyerConversationRead,
    BuyerDataProviderRead,
    BuyerDiscoveryCreate,
    BuyerDiscoveryImport,
    BuyerDiscoveryRunRead,
    BuyerListResponse,
    BuyerRead,
)
from app.services import buyer_discovery
from app.services.buyers import create_buyer, list_buyers
from app.services.inbox import ensure_buyer_conversation

router = APIRouter(prefix="/api/v1/buyers", tags=["buyers"])
view_buyers_dependency = require_permission(PermissionKeys.VIEW_BUYERS)
edit_buyers_dependency = require_permission(PermissionKeys.EDIT_BUYERS)


@router.get("")
def read_buyers(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_buyers_dependency)],
) -> BuyerListResponse:
    return BuyerListResponse(items=list_buyers(db, principal))


@router.post("", status_code=201)
def create_buyer_record(
    payload: BuyerCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_buyers_dependency)],
) -> BuyerRead:
    try:
        return create_buyer(db, principal, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


@router.post("/{buyer_id}/conversation")
def open_buyer_conversation(
    buyer_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_buyers_dependency)],
) -> BuyerConversationRead:
    buyer = db.get(Buyer, buyer_id)
    if buyer is None or buyer.organization_id != principal.organization_id:
        raise HTTPException(status_code=404, detail="Buyer not found.")
    conversation = ensure_buyer_conversation(
        db,
        buyer,
        actor_user_id=principal.user_id,
    )
    db.commit()
    return BuyerConversationRead(conversation_id=conversation.id)


@router.get("/provider")
def read_buyer_data_provider(
    principal: Annotated[Principal, Depends(view_buyers_dependency)],
) -> BuyerDataProviderRead:
    del principal
    return buyer_discovery.provider_status()


@router.get("/discovery-runs/latest")
def read_latest_buyer_discovery(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_buyers_dependency)],
) -> BuyerDiscoveryRunRead | None:
    return buyer_discovery.latest_discovery_run(db, principal, case_id)


@router.post("/discovery-runs", status_code=201)
def create_buyer_discovery(
    payload: BuyerDiscoveryCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_buyers_dependency)],
) -> BuyerDiscoveryRunRead:
    try:
        return buyer_discovery.discover_buyers(db, principal, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


@router.post("/discovery-runs/{run_id}/import")
def import_buyer_candidates(
    run_id: UUID,
    payload: BuyerDiscoveryImport,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_buyers_dependency)],
) -> BuyerDiscoveryRunRead:
    try:
        result = buyer_discovery.import_candidates(db, principal, run_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Buyer discovery run not found.")
    return result
