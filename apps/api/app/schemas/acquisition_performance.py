from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

AcquisitionPerformanceDimensionKey = Literal[
    "speed_to_lead",
    "follow_up_discipline",
    "conversation_quality",
    "qualification_quality",
    "crm_hygiene",
    "appointment_execution",
    "mature_outcomes",
]


class AcquisitionPerformanceDimension(BaseModel):
    key: AcquisitionPerformanceDimensionKey
    label: str
    weight_basis_points: int = Field(ge=0, le=10_000)
    score: int | None = Field(default=None, ge=0, le=100)
    status: Literal["unavailable", "building", "ready"]
    sample_size: int = Field(ge=0)
    minimum_sample_size: int = Field(ge=1)
    numerator: float | None = Field(default=None, ge=0)
    denominator: float | None = Field(default=None, ge=0)
    display_value: str
    detail: str


class AcquisitionPerformanceScorecard(BaseModel):
    user_id: UUID
    user_name: str
    overall_score: int | None = Field(default=None, ge=0, le=100)
    coverage_basis_points: int = Field(ge=0, le=10_000)
    reliability_status: Literal["building", "provisional", "reliable"]
    dimensions: list[AcquisitionPerformanceDimension]
    strengths: list[str]
    focus_areas: list[str]
    warnings: list[str]


class AcquisitionPerformanceOverview(BaseModel):
    period_days: Literal[30, 90]
    period_start: datetime
    period_end: datetime
    policy_version: str
    shadow_mode: bool
    weights: dict[AcquisitionPerformanceDimensionKey, int]
    scorecards: list[AcquisitionPerformanceScorecard]
    warnings: list[str]
