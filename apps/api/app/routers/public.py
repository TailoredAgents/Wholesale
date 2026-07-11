from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.public_intake import SellerIntakeCreate, SellerIntakeResponse
from app.services.public_intake import create_public_seller_lead

router = APIRouter(prefix="/api/v1/public", tags=["public"])


@router.post("/seller-leads", status_code=201)
def create_seller_lead_from_public_form(
    payload: SellerIntakeCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user_agent: Annotated[str | None, Header(alias="User-Agent")] = None,
) -> SellerIntakeResponse:
    forwarded_for = request.headers.get("x-forwarded-for")
    ip_address = None
    if forwarded_for:
        ip_address = forwarded_for.split(",")[0].strip()
    elif request.client:
        ip_address = request.client.host
    return create_public_seller_lead(
        db,
        payload,
        ip_address=ip_address,
        user_agent=user_agent,
    )
