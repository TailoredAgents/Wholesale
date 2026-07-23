from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

ManagementCapability = Literal[
    "finance.reconcile",
    "marketing.analyze",
    "operations.brief",
]


class ManagementFact(BaseModel):
    label: str
    value: str
    evidence: list[str]


class ManagementException(BaseModel):
    severity: Literal["info", "warning", "critical"]
    category: str
    title: str
    detail: str
    evidence: list[str]


class ManagementAnalysisItem(BaseModel):
    category: str
    subject: str
    signal: Literal["positive", "neutral", "warning", "critical"]
    analysis: str
    evidence: list[str]


class ManagementDraftAction(BaseModel):
    action: str
    reason: str
    owner: str
    workspace: Literal[
        "dashboard",
        "finance",
        "marketing",
        "operations",
        "dispositions",
        "transactions",
        "ai",
    ]
    evidence: list[str]
    requires_human_decision: Literal[True]


class ManagementDecisionRequest(BaseModel):
    decision: str
    why_now: str
    options: list[str]
    evidence: list[str]


class ManagementCopilotOutput(BaseModel):
    brief: str
    confirmed_facts: list[ManagementFact]
    exceptions: list[ManagementException]
    analysis: list[ManagementAnalysisItem]
    draft_actions: list[ManagementDraftAction]
    decision_requests: list[ManagementDecisionRequest]
    uncertainties: list[str]
    evidence: list[str]
    confidence: int = Field(ge=0, le=100)


class ManagementCopilotAnalyzeRequest(BaseModel):
    period_days: int = Field(default=30, ge=7, le=365)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=255)


class ManagementCopilotRecommendationRead(BaseModel):
    id: UUID
    capability_key: ManagementCapability
    reporting_period_days: int
    ai_run_log_id: UUID | None
    status: str
    output_payload: ManagementCopilotOutput
    confidence_score: int | None
    generated_at: datetime
    reviewed_at: datetime | None


class ManagementCopilotAnalyzeRead(BaseModel):
    run_id: UUID
    run_status: str
    message: str
    recommendation: ManagementCopilotRecommendationRead | None


class ManagementCopilotReviewRequest(BaseModel):
    decision: Literal["accepted", "edited", "rejected"]
    final_output: dict[str, object] | None = None
    notes: str | None = Field(default=None, max_length=2000)
    estimated_time_saved_seconds: int = Field(default=0, ge=0, le=86_400)

    def model_post_init(self, __context: object) -> None:
        if self.decision == "edited" and self.final_output is None:
            raise ValueError("Edited guidance requires the corrected output.")
        if self.decision != "edited" and self.final_output is not None:
            raise ValueError("Corrected output is only accepted with an edited decision.")


class ManagementCopilotReviewRead(BaseModel):
    id: UUID
    recommendation_id: UUID
    decision: str
    final_output: ManagementCopilotOutput | None
    notes: str | None
    estimated_time_saved_seconds: int
    reviewed_at: datetime


class ManagementRiskAlert(BaseModel):
    severity: Literal["info", "warning", "critical"]
    item: str
    reason: str
    evidence: list[str]


class ManagementMetricCard(BaseModel):
    label: str
    value: str
    detail: str
    tone: Literal["neutral", "info", "success", "warning", "danger"]


class ManagementCopilotMetrics(BaseModel):
    generated: int
    reviewed: int
    accepted_or_corrected_rate_basis_points: int
    correction_rate_basis_points: int
    estimated_time_saved_minutes: int


class ManagementCopilotOverview(BaseModel):
    capability_key: ManagementCapability
    copilot_name: str
    pilot_mode: Literal["draft_only"]
    runtime_status: str
    capability_status: str
    external_actions_blocked: bool
    reporting_period_days: int
    health_score: int = Field(ge=0, le=100)
    health_band: Literal["healthy", "needs_review", "critical"]
    readiness_gaps: list[str]
    risk_alerts: list[ManagementRiskAlert]
    metric_cards: list[ManagementMetricCard]
    recommendations: list[ManagementCopilotRecommendationRead]
    metrics: ManagementCopilotMetrics
