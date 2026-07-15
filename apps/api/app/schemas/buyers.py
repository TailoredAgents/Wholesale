from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class BuyerCriteriaCreate(BaseModel):
    markets: str | None = Field(default=None, max_length=500)
    property_types: str | None = Field(default=None, max_length=500)
    min_price_cents: int | None = Field(default=None, ge=0)
    max_price_cents: int | None = Field(default=None, ge=0)
    rehab_levels: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=1000)


class BuyerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    company_name: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=80)
    buyer_type: str = Field(default="cash_buyer", max_length=80)
    status: str = Field(default="active", max_length=80)
    proof_of_funds_status: str = Field(default="unknown", max_length=80)
    max_purchase_price_cents: int | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=2000)
    criteria: BuyerCriteriaCreate | None = None


class BuyerCriteriaRead(BaseModel):
    markets: str | None
    property_types: str | None
    min_price_cents: int | None
    max_price_cents: int | None
    rehab_levels: str | None
    notes: str | None


class BuyerRead(BaseModel):
    id: UUID
    name: str
    company_name: str | None
    email: str | None
    phone: str | None
    buyer_type: str
    status: str
    proof_of_funds_status: str
    max_purchase_price_cents: int | None
    notes: str | None
    criteria: BuyerCriteriaRead | None
    created_at: datetime


class BuyerListResponse(BaseModel):
    items: list[BuyerRead]
