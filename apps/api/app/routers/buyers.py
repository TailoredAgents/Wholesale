from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_permission
from app.core.database import get_db
from app.domain.rbac import PermissionKeys
from app.models.foundation import Buyer
from app.schemas.buyers import (
    BuyerArchiveRequest,
    BuyerConversationRead,
    BuyerCreate,
    BuyerDataProviderRead,
    BuyerDiscoveryCreate,
    BuyerDiscoveryEstimateCreate,
    BuyerDiscoveryEstimateRead,
    BuyerDiscoveryImport,
    BuyerDiscoveryRunRead,
    BuyerDuplicatePreflightRead,
    BuyerDuplicatePreflightRequest,
    BuyerListResponse,
    BuyerRead,
    BuyerUpdate,
)
from app.services import buyer_discovery
from app.services.buyers import (
    BuyerOwnerNotFoundError,
    BuyerSourceConflictError,
    DuplicateBuyerError,
    archive_buyer,
    create_buyer,
    get_buyer,
    list_buyers,
    preflight_duplicates,
    restore_buyer,
    update_buyer,
)
from app.services.inbox import ensure_buyer_conversation

router = APIRouter(prefix="/api/v1/buyers", tags=["buyers"])
view_buyers_dependency = require_permission(PermissionKeys.VIEW_BUYERS)
edit_buyers_dependency = require_permission(PermissionKeys.EDIT_BUYERS)


@router.get("")
def read_buyers(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_buyers_dependency)],
    q: Annotated[str | None, Query(max_length=255)] = None,
    buyer_status: Annotated[str | None, Query(alias="status", max_length=80)] = None,
    owner_id: UUID | None = None,
    source_key: Annotated[str | None, Query(max_length=80)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> BuyerListResponse:
    try:
        return list_buyers(
            db,
            principal,
            query=q,
            buyer_status=buyer_status,
            owner_id=owner_id,
            source_key=source_key,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


@router.post("/duplicates/preflight")
def read_buyer_duplicates(
    payload: BuyerDuplicatePreflightRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_buyers_dependency)],
) -> BuyerDuplicatePreflightRead:
    try:
        return preflight_duplicates(db, principal, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


@router.post("", status_code=201)
def create_buyer_record(
    payload: BuyerCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_buyers_dependency)],
) -> BuyerRead:
    try:
        return create_buyer(db, principal, payload)
    except DuplicateBuyerError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "buyer_duplicate_match",
                "message": "A matching buyer already exists. Review it before creating another.",
                "matches": [match.model_dump(mode="json") for match in exc.matches],
            },
        ) from exc
    except BuyerOwnerNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BuyerSourceConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "buyer_source_conflict", "message": str(exc)},
        ) from exc
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


@router.get("/provider/readiness")
def read_buyer_data_provider_readiness(
    principal: Annotated[Principal, Depends(view_buyers_dependency)],
) -> BuyerDataProviderRead:
    del principal
    return buyer_discovery.provider_readiness()


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


@router.post("/discovery-runs/estimate")
def estimate_buyer_discovery(
    payload: BuyerDiscoveryEstimateCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_buyers_dependency)],
) -> BuyerDiscoveryEstimateRead:
    try:
        return buyer_discovery.estimate_buyer_discovery(db, principal, payload)
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


@router.get("/{buyer_id}")
def read_buyer(
    buyer_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(view_buyers_dependency)],
) -> BuyerRead:
    result = get_buyer(db, principal, buyer_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Buyer not found.")
    return result


@router.patch("/{buyer_id}")
def update_buyer_record(
    buyer_id: UUID,
    payload: BuyerUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_buyers_dependency)],
) -> BuyerRead:
    try:
        result = update_buyer(db, principal, buyer_id, payload)
    except DuplicateBuyerError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "buyer_duplicate_match",
                "message": "A matching buyer already exists. Review it before saving separately.",
                "matches": [match.model_dump(mode="json") for match in exc.matches],
            },
        ) from exc
    except BuyerOwnerNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BuyerSourceConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "buyer_source_conflict", "message": str(exc)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Buyer not found.")
    return result


@router.post("/{buyer_id}/archive")
def archive_buyer_record(
    buyer_id: UUID,
    payload: BuyerArchiveRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_buyers_dependency)],
) -> BuyerRead:
    result = archive_buyer(db, principal, buyer_id, payload.reason)
    if result is None:
        raise HTTPException(status_code=404, detail="Buyer not found.")
    return result


@router.post("/{buyer_id}/restore")
def restore_buyer_record(
    buyer_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(edit_buyers_dependency)],
) -> BuyerRead:
    result = restore_buyer(db, principal, buyer_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Buyer not found.")
    return result
