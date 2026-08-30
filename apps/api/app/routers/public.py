from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.integrations.realestateapi_client import RealEstateAPIClient, RealEstateAPIError
from app.schemas.marketing_experiments import PublicExperimentResponse
from app.schemas.public_intake import (
    ConversionEventCreate,
    ConversionEventResponse,
    PublicAddressSuggestion,
    PublicAddressSuggestionsResponse,
    SellerIntakeEnrichmentCreate,
    SellerIntakeEnrichmentResponse,
    SellerIntakeResponse,
    WebsiteSellerAddressCaptureCreate,
    WebsiteSellerAddressCaptureResponse,
    WebsiteSellerIntakeCreate,
)
from app.schemas.trust_proof import PublicTrustProofResponse
from app.services.conversion_events import record_public_conversion_event
from app.services.disposition_packet_links import SharedPackageUnavailable, read_shared_package
from app.services.marketing_experiments import list_public_experiments
from app.services.public_intake import (
    capture_public_seller_address,
    create_public_seller_lead,
    enrich_public_seller_lead,
)
from app.services.request_rate_limit import (
    public_intake_rate_limiter,
    trusted_client_address,
)
from app.services.trust_proof import get_public_trust_proofs

router = APIRouter(prefix="/api/v1/public", tags=["public"])


@router.get(
    "/investor-packages/{token}",
    name="download_shared_investor_package",
)
def download_shared_investor_package(
    token: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user_agent: Annotated[str | None, Header(alias="User-Agent")] = None,
) -> Response:
    settings = get_settings()
    if settings.public_intake_rate_limit_enabled:
        enforce_public_rate_limit(
            request,
            route_key="investor-package:read",
            limit=settings.public_conversion_event_rate_limit_requests,
            window_seconds=settings.public_conversion_event_rate_limit_window_seconds,
            detail="Too many investor package requests. Please wait before trying again.",
        )
    try:
        content, file_name = read_shared_package(
            db,
            token,
            client_address=get_ip_address(request),
            user_agent=user_agent,
        )
    except SharedPackageUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_410_GONE if exc.gone else status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Cache-Control": "private, no-store, max-age=0",
            "Content-Disposition": f'inline; filename="{file_name}"',
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
            "X-Robots-Tag": "noindex, nofollow, noarchive",
        },
    )


@router.get("/address-suggestions")
def read_public_address_suggestions(
    request: Request,
    response: Response,
    q: Annotated[str, Query(min_length=3, max_length=160)],
    limit: Annotated[int, Query(ge=1, le=6)] = 6,
) -> PublicAddressSuggestionsResponse:
    response.headers["Cache-Control"] = "no-store"
    clean_query = " ".join(q.split())
    if len(clean_query) < 3:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Address search must contain at least 3 characters.",
        )
    enforce_public_address_suggestions_rate_limit(request)
    settings = get_settings()
    if not settings.realestateapi_api_key:
        return PublicAddressSuggestionsResponse(available=False)
    try:
        suggestions = RealEstateAPIClient(settings).autocomplete_addresses(
            clean_query,
            max_results=limit,
            preferred_state="GA",
        )
    except RealEstateAPIError:
        return PublicAddressSuggestionsResponse(available=False)
    return PublicAddressSuggestionsResponse(
        available=True,
        suggestions=[
            PublicAddressSuggestion(
                provider_id=suggestion.provider_id,
                label=suggestion.label,
                street_address=suggestion.street_address,
                city=suggestion.city,
                state=suggestion.state,
                postal_code=suggestion.postal_code,
            )
            for suggestion in suggestions
        ],
    )


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
    payload: WebsiteSellerIntakeCreate,
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


@router.post("/seller-leads/address-capture", status_code=201)
def capture_seller_address_from_public_form(
    payload: WebsiteSellerAddressCaptureCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user_agent: Annotated[str | None, Header(alias="User-Agent")] = None,
) -> WebsiteSellerAddressCaptureResponse:
    enforce_public_intake_rate_limit(request, route_key="seller-lead:address-capture")
    return capture_public_seller_address(
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


def enforce_public_address_suggestions_rate_limit(request: Request) -> None:
    settings = get_settings()
    if not settings.public_intake_rate_limit_enabled:
        return
    enforce_public_rate_limit(
        request,
        route_key="address-suggestion:read",
        limit=settings.public_conversion_event_rate_limit_requests,
        window_seconds=settings.public_conversion_event_rate_limit_window_seconds,
        detail="Too many address searches. Please wait before trying again.",
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
