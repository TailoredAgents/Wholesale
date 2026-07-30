from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.marketing_experiments import PublicExperimentResponse
from app.schemas.public_intake import (
    ConversionEventCreate,
    ConversionEventResponse,
    SellerIntakeCreate,
    SellerIntakeEnrichmentCreate,
    SellerIntakeEnrichmentResponse,
    SellerIntakeResponse,
)
from app.schemas.trust_proof import PublicTrustProofResponse
from app.services.conversion_events import record_public_conversion_event
from app.services.marketing_experiments import list_public_experiments
from app.services.public_intake import create_public_seller_lead, enrich_public_seller_lead
from app.services.trust_proof import get_public_trust_proofs

router = APIRouter(prefix="/api/v1/public", tags=["public"])


@router.get("/experiments")
def read_public_experiments(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> PublicExperimentResponse:
    response.headers["Cache-Control"] = "no-store"
    return list_public_experiments(db)


@router.get("/trust-proofs")
def read_public_trust_proofs(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> PublicTrustProofResponse:
    response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=300"
    return get_public_trust_proofs(db)


@router.post("/seller-leads", status_code=201)
def create_seller_lead_from_public_form(
    payload: SellerIntakeCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user_agent: Annotated[str | None, Header(alias="User-Agent")] = None,
) -> SellerIntakeResponse:
    return create_public_seller_lead(
        db,
        payload,
        ip_address=get_ip_address(request),
        user_agent=user_agent,
    )


@router.post("/seller-leads/enrichment")
def enrich_seller_lead_from_public_form(
    payload: SellerIntakeEnrichmentCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user_agent: Annotated[str | None, Header(alias="User-Agent")] = None,
) -> SellerIntakeEnrichmentResponse:
    return enrich_public_seller_lead(
        db,
        payload,
        ip_address=get_ip_address(request),
        user_agent=user_agent,
    )


@router.post("/conversion-events", status_code=201)
def create_conversion_event(
    payload: ConversionEventCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user_agent: Annotated[str | None, Header(alias="User-Agent")] = None,
) -> ConversionEventResponse:
    event = record_public_conversion_event(
        db,
        payload,
        ip_address=get_ip_address(request),
        user_agent=user_agent,
    )
    return ConversionEventResponse(id=event.id, event_type=event.event_type)


def get_ip_address(request: Request) -> str | None:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None
