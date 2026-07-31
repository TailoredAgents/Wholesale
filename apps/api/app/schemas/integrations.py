from pydantic import BaseModel


class IntegrationStatusRead(BaseModel):
    key: str
    name: str
    category: str
    mode: str
    enabled: bool
    configured: bool
    blockers: list[str]


class IntegrationStatusListResponse(BaseModel):
    items: list[IntegrationStatusRead]

