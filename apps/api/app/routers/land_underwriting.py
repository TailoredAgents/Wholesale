from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_permission
from app.core.database import get_db
from app.domain.rbac import PermissionKeys
from app.schemas.land_underwriting import (
    LandOfferPolicyActivate,
    LandOfferPolicyCreate,
    LandOfferPolicyRead,
    LandValuationCreate,
    LandValuationRead,
)
from app.services.land_underwriting import (
    activate_land_offer_policy,
    create_land_offer_policy,
    create_land_valuation,
    latest_land_valuation,
    list_land_offer_policies,
    list_land_valuations,
)

router = APIRouter(tags=["land-underwriting"])
underwriting_dependency = require_permission(PermissionKeys.EDIT_UNDERWRITING)
offer_policy_dependency = require_permission(PermissionKeys.APPROVE_OFFERS)


@router.get("/api/v1/leads/{lead_id}/land-valuations/latest")
def read_latest_land_valuation(
    lead_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(underwriting_dependency)],
) -> LandValuationRead | None:
    try:
        return latest_land_valuation(db, principal, lead_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.get("/api/v1/leads/{lead_id}/land-valuations")
def read_land_valuation_history(
    lead_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(underwriting_dependency)],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> list[LandValuationRead]:
    try:
        analyses = list_land_valuations(
            db,
            principal,
            lead_id,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    if analyses is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return analyses


@router.post(
    "/api/v1/leads/{lead_id}/land-valuations",
    status_code=status.HTTP_201_CREATED,
)
def record_land_valuation(
    lead_id: UUID,
    payload: LandValuationCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(underwriting_dependency)],
) -> LandValuationRead:
    try:
        analysis = create_land_valuation(db, principal, lead_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    if analysis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found.")
    return analysis


@router.get("/api/v1/land-underwriting/offer-policies")
def read_land_offer_policies(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(underwriting_dependency)],
) -> list[LandOfferPolicyRead]:
    return list_land_offer_policies(db, principal)


@router.post(
    "/api/v1/land-underwriting/offer-policies",
    status_code=status.HTTP_201_CREATED,
)
def record_land_offer_policy(
    payload: LandOfferPolicyCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(offer_policy_dependency)],
) -> LandOfferPolicyRead:
    return create_land_offer_policy(db, principal, payload)


@router.post("/api/v1/land-underwriting/offer-policies/{policy_id}/activate")
def activate_saved_land_offer_policy(
    policy_id: UUID,
    payload: LandOfferPolicyActivate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(offer_policy_dependency)],
) -> LandOfferPolicyRead:
    try:
        policy = activate_land_offer_policy(
            db,
            principal,
            policy_id,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    if policy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Land offer policy not found.",
        )
    return policy
