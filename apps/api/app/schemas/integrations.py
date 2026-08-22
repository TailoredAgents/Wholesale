from datetime import datetime

from pydantic import BaseModel, Field


class IntegrationStatusRead(BaseModel):
    key: str
    name: str
    category: str
    mode: str
    enabled: bool
    configured: bool
    blockers: list[str]
    runtime_status: str | None = None
    last_success_at: datetime | None = None
    details: list[str] = Field(default_factory=list)


class IntegrationStatusListResponse(BaseModel):
    items: list[IntegrationStatusRead]
