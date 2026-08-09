from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class StaffLeadAlertRecoveryRequest(BaseModel):
    reason: str = Field(min_length=10, max_length=500)

    @field_validator("reason")
    @classmethod
    def require_meaningful_reason(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 10:
            raise ValueError("Recovery reason must contain at least 10 non-space characters.")
        return normalized


class StaffLeadAlertRecoveryRead(BaseModel):
    event_id: UUID
    lead_id: UUID
    created: int
    requeued: int
    skipped_active_or_delivered: int
    skipped_ineligible: int
    delivery_configured: bool
    configuration_blockers: list[str]
