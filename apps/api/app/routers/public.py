from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
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
from app.services.request_rate_limit import (
    public_intake_rate_limiter,
    trusted_client_address,
)
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
    enforce_public_intake_rate_limit(request, route_key="seller-lead:create")
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
    enforce_public_intake_rate_limit(request, route_key="seller-lead:enrichment")
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
    enforce_public_conversion_event_rate_limit(request)
    event = record_public_conversion_event(
        db,
        payload,
        ip_address=get_ip_address(request),
        user_agent=user_agent,
    )
    return ConversionEventResponse(id=event.id, event_type=event.event_type)


def get_ip_address(request: Request) -> str | None:
    settings = get_settings()
    return trusted_client_address(request, production=settings.app_env == "production")


def enforce_public_intake_rate_limit(request: Request, *, route_key: str) -> None:
    settings = get_settings()
    if not settings.public_intake_rate_limit_enabled:
        return
    enforce_public_rate_limit(
        request,
        route_key=route_key,
        limit=settings.public_intake_rate_limit_requests,
        window_seconds=settings.public_intake_rate_limit_window_seconds,
        detail="Too many offer requests. Please wait before trying again.",
    )


def enforce_public_conversion_event_rate_limit(request: Request) -> None:
    settings = get_settings()
    if not settings.public_intake_rate_limit_enabled:
        return
    enforce_public_rate_limit(
        request,
        route_key="conversion-event:create",
        limit=settings.public_conversion_event_rate_limit_requests,
        window_seconds=settings.public_conversion_event_rate_limit_window_seconds,
        detail="Too many conversion events. Please wait before trying again.",
    )


def enforce_public_rate_limit(
    request: Request,
    *,
    route_key: str,
    limit: int,
    window_seconds: int,
    detail: str,
) -> None:
    client_address = get_ip_address(request) or "unknown"
    retry_after = public_intake_rate_limiter.check(
        f"public:{route_key}:{client_address}",
        limit=limit,
        window_seconds=window_seconds,
    )
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            headers={"Retry-After": str(retry_after)},
        )
