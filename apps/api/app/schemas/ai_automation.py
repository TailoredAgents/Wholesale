from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AiExternalActionPolicyDecision(BaseModel):
    decision: str = Field(pattern="^(approve_control|return_to_draft)$")
    notes: str = Field(min_length=1, max_length=1000)


class AiExternalActionSimulationCreate(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=255)
    audience_count: int = Field(default=1, ge=1, le=10_000)
    estimated_cost_microusd: int = Field(default=0, ge=0, le=1_000_000_000)
    consent_verified: bool = False
    template_approved: bool = False
    within_contact_hours: bool = False
    frequency_allowed: bool = False
    suppression_checked: bool = False
    human_takeover_ready: bool = False


class AiExternalActionPauseCreate(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class AiExternalActionAttemptRead(BaseModel):
    id: UUID
    policy_id: UUID
    idempotency_key: str
    execution_mode: str
    status: str
    audience_count: int
    estimated_cost_microusd: int
    policy_checks: dict[str, object]
    block_reasons: list[str]
    external_delivery_attempted: bool
    delivered_count: int
    requested_by_user_id: UUID
    created_at: datetime


class AiExternalActionPolicyRead(BaseModel):
    id: UUID
    action_key: str
    name: str
    description: str
    capability_key: str
    channel: str
    provider_key: str
    owner_role_key: str
    status: str
    audience_policy: dict[str, object]
    consent_policy: dict[str, object]
    template_policy: dict[str, object]
    schedule_policy: dict[str, object]
    volume_policy: dict[str, object]
    cost_policy: dict[str, object]
    quality_policy: dict[str, object]
    canary_policy: dict[str, object]
    pause_policy: dict[str, object]
    rollback_policy: dict[str, object]
    prohibited_actions: list[str]
    dry_run_only: bool
    external_delivery_enabled: bool
    approved_by_user_id: UUID | None
    approved_at: datetime | None
    last_pause_reason: str | None
    paused_at: datetime | None
    readiness_status: str
    readiness_blockers: list[str]
    attempts: list[AiExternalActionAttemptRead]
    updated_at: datetime


class AiExternalAutomationMetrics(BaseModel):
    policy_count: int
    control_only_count: int
    paused_count: int
    canary_ready_count: int
    external_delivery_enabled_count: int
    simulation_count: int
    blocked_simulation_count: int
    external_delivery_attempt_count: int
    delivered_message_count: int


class AiExternalAutomationOverview(BaseModel):
    phase_status: str
    external_delivery_globally_enabled: bool
    emergency_stop: bool
    metrics: AiExternalAutomationMetrics
    policies: list[AiExternalActionPolicyRead]


class AiExternalActionPolicyInstallRead(BaseModel):
    created_policy_count: int
    existing_policy_count: int
    overview: AiExternalAutomationOverview
