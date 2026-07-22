from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class AiToolPermissionCreate(BaseModel):
    tool_key: str = Field(min_length=1, max_length=160)
    tool_name: str = Field(min_length=1, max_length=255)
    permission_level: str = Field(default="read", max_length=80)
    is_enabled: bool = True
    requires_approval: bool = True


class AiAgentCreate(BaseModel):
    key: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=1000)
    status: str = Field(default="draft", max_length=80)
    model_name: str = Field(default="gpt-5.6-terra", max_length=120)
    risk_level: str = Field(default="medium", max_length=80)
    requires_human_approval: bool = True
    max_cost_microusd_per_run: int = Field(default=100000, ge=0, le=100_000_000)
    max_daily_cost_microusd: int = Field(default=1_000_000, ge=0, le=1_000_000_000)
    max_attempts: int = Field(default=2, ge=1, le=5)
    tool_permissions: list[AiToolPermissionCreate] = Field(default_factory=list)


class AiPromptVersionCreate(BaseModel):
    status: str = Field(default="draft", max_length=80)
    prompt_text: str = Field(min_length=1, max_length=8000)
    change_notes: str | None = Field(default=None, max_length=2000)


class AiRunToolCallCreate(BaseModel):
    tool_key: str = Field(min_length=1, max_length=160)
    status: str = Field(default="proposed", max_length=80)
    requires_approval: bool = True
    input_payload: dict[str, object] | None = None
    output_payload: dict[str, object] | None = None
    error_message: str | None = Field(default=None, max_length=2000)


class AiRunCreate(BaseModel):
    agent_definition_id: UUID
    prompt_version_id: UUID | None = None
    lead_id: UUID | None = None
    status: str = Field(default="completed", max_length=80)
    model_name: str | None = Field(default=None, max_length=120)
    input_summary: str = Field(min_length=1, max_length=4000)
    output_summary: str | None = Field(default=None, max_length=4000)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cost_cents: int | None = Field(default=None, ge=0)
    cost_microusd: int | None = Field(default=None, ge=0)
    latency_ms: int | None = Field(default=None, ge=0)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = Field(default=None, max_length=2000)
    run_metadata: dict[str, object] | None = None
    tool_calls: list[AiRunToolCallCreate] = Field(default_factory=list)


class LeadIntakeSummaryRunCreate(BaseModel):
    lead_id: UUID


class AiToolPermissionRead(BaseModel):
    id: UUID
    tool_key: str
    tool_name: str
    permission_level: str
    is_enabled: bool
    requires_approval: bool
    created_at: datetime


class AiAgentRead(BaseModel):
    id: UUID
    key: str
    name: str
    description: str
    status: str
    model_name: str
    risk_level: str
    requires_human_approval: bool
    autonomy_level: str
    max_cost_microusd_per_run: int
    max_daily_cost_microusd: int
    max_attempts: int
    rollback_owner_user_id: UUID | None
    tool_permissions: list[AiToolPermissionRead]
    created_at: datetime


class AiPromptVersionRead(BaseModel):
    id: UUID
    agent_definition_id: UUID
    version_number: int
    status: str
    prompt_text: str
    change_notes: str | None
    created_at: datetime


class AiToolCallRead(BaseModel):
    id: UUID
    ai_run_log_id: UUID
    approval_request_id: UUID | None
    tool_key: str
    status: str
    requires_approval: bool
    input_payload: dict[str, object] | None
    output_payload: dict[str, object] | None
    error_message: str | None
    created_at: datetime


class AiRunRead(BaseModel):
    id: UUID
    agent_definition_id: UUID
    prompt_version_id: UUID | None
    lead_id: UUID | None
    status: str
    model_name: str
    input_summary: str
    output_summary: str | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    cost_cents: int | None
    cost_microusd: int | None
    latency_ms: int | None
    started_at: datetime
    completed_at: datetime | None
    error_message: str | None
    run_metadata: dict[str, object] | None
    orchestrator_event_id: UUID | None
    parent_run_id: UUID | None
    execution_mode: str
    capability_key: str
    attempt_number: int
    idempotency_key: str | None
    budget_limit_microusd: int | None
    budget_status: str
    trace_status: str
    trace_reviewed_by_user_id: UUID | None
    trace_reviewed_at: datetime | None
    trace_review_notes: str | None
    rollback_status: str
    tool_calls: list[AiToolCallRead]
    created_at: datetime


class AiPortfolioInstallRead(BaseModel):
    created_agent_count: int
    existing_agent_count: int
    total_agent_count: int


class AiOrchestratorEventCreate(BaseModel):
    event_key: str = Field(min_length=1, max_length=255)
    event_type: str = Field(min_length=1, max_length=120)
    entity_type: str | None = Field(default=None, max_length=120)
    entity_id: UUID | None = None
    payload: dict[str, object] = Field(default_factory=dict)
    occurred_at: datetime | None = None


class AiOrchestratorEventRead(BaseModel):
    id: UUID
    event_key: str
    event_type: str
    entity_type: str | None
    entity_id: UUID | None
    status: str
    payload: dict[str, object]
    occurred_at: datetime
    processed_at: datetime | None
    last_error: str | None
    created_at: datetime


class AiDryRunCreate(BaseModel):
    agent_definition_id: UUID
    capability_key: str = Field(min_length=1, max_length=160)
    input_summary: str = Field(min_length=1, max_length=4000)
    idempotency_key: str = Field(min_length=1, max_length=255)
    lead_id: UUID | None = None
    orchestrator_event_id: UUID | None = None
    budget_limit_microusd: int | None = Field(default=None, ge=0)
    proposed_tools: list[str] = Field(default_factory=list, max_length=30)


class AiTraceReview(BaseModel):
    status: Literal["reviewed", "flagged"]
    notes: str = Field(min_length=1, max_length=2000)


class AiEvaluationCaseCreate(BaseModel):
    case_key: str = Field(min_length=1, max_length=160)
    name: str = Field(min_length=1, max_length=255)
    input_payload: dict[str, object]
    expected_output: dict[str, object] = Field(default_factory=dict)
    candidate_output: dict[str, object] | None = None
    deterministic_checks: dict[str, object] = Field(default_factory=dict)
    risk_tags: list[str] = Field(default_factory=list)
    is_critical: bool = False


class AiEvaluationDatasetCreate(BaseModel):
    agent_definition_id: UUID
    capability_key: str = Field(min_length=1, max_length=160)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    minimum_case_count: int = Field(default=3, ge=1, le=500)
    minimum_pass_rate_basis_points: int = Field(default=9000, ge=0, le=10000)
    maximum_critical_failures: int = Field(default=0, ge=0, le=500)
    maximum_average_latency_ms: int | None = Field(default=None, ge=0)
    maximum_average_cost_microusd: int | None = Field(default=None, ge=0)
    cases: list[AiEvaluationCaseCreate] = Field(min_length=1, max_length=500)


class AiEvaluationCaseRead(BaseModel):
    id: UUID
    case_key: str
    name: str
    input_payload: dict[str, object]
    expected_output: dict[str, object]
    candidate_output: dict[str, object] | None
    deterministic_checks: dict[str, object]
    risk_tags: list[str]
    is_critical: bool


class AiEvaluationDatasetRead(BaseModel):
    id: UUID
    agent_definition_id: UUID
    capability_key: str
    name: str
    version_number: int
    status: str
    description: str | None
    minimum_case_count: int
    minimum_pass_rate_basis_points: int
    maximum_critical_failures: int
    maximum_average_latency_ms: int | None
    maximum_average_cost_microusd: int | None
    approved_by_user_id: UUID | None
    approved_at: datetime | None
    cases: list[AiEvaluationCaseRead]
    created_at: datetime


class AiEvaluationDecision(BaseModel):
    decision: Literal["approve", "retire"]


class AiEvaluationRunCreate(BaseModel):
    dataset_id: UUID
    prompt_version_id: UUID


class AiEvaluationResultRead(BaseModel):
    id: UUID
    evaluation_case_id: UUID
    status: str
    score_basis_points: int
    critical_failure: bool
    actual_output: dict[str, object] | None
    check_results: dict[str, object]
    latency_ms: int | None
    cost_microusd: int | None
    error_message: str | None


class AiEvaluationRunRead(BaseModel):
    id: UUID
    dataset_id: UUID
    prompt_version_id: UUID
    status: str
    execution_mode: str
    model_name: str
    case_count: int
    passed_case_count: int
    pass_rate_basis_points: int
    critical_failure_count: int
    average_latency_ms: int | None
    average_cost_microusd: int | None
    total_cost_microusd: int
    thresholds_passed: bool
    summary: dict[str, object]
    started_at: datetime
    completed_at: datetime | None
    results: list[AiEvaluationResultRead]
    created_at: datetime


class AiPromotionCreate(BaseModel):
    evaluation_run_id: UUID
    to_level: Literal["draft", "recommend", "execute_internal"]
    reason: str = Field(min_length=1, max_length=2000)


class AiPromotionRead(BaseModel):
    id: UUID
    agent_definition_id: UUID
    capability_key: str
    evaluation_run_id: UUID
    approval_request_id: UUID | None
    from_level: str
    to_level: str
    status: str
    reason: str
    decision_notes: str | None
    effective_at: datetime | None
    rolled_back_at: datetime | None
    rollback_reason: str | None
    created_at: datetime


class AiRollbackCreate(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class AiOrchestratorMetrics(BaseModel):
    portfolio_agent_count: int
    governed_run_count: int
    unreviewed_trace_count: int
    approved_dataset_count: int
    passing_evaluation_count: int
    pending_promotion_count: int
    active_promotion_count: int
    budget_blocked_run_count: int


class AiOrchestratorOverview(BaseModel):
    metrics: AiOrchestratorMetrics
    events: list[AiOrchestratorEventRead]
    datasets: list[AiEvaluationDatasetRead]
    evaluation_runs: list[AiEvaluationRunRead]
    promotions: list[AiPromotionRead]


class AiControlSummary(BaseModel):
    agent_count: int
    active_agent_count: int
    prompt_version_count: int
    run_count: int
    pending_approval_count: int
    total_cost_cents: int
    total_cost_microusd: int
    unpriced_run_count: int
    average_latency_ms: int | None


class CallIntelligenceQuality(BaseModel):
    total_calls: int
    reviewed_calls: int
    approved_calls: int
    rejected_calls: int
    pending_review_calls: int
    failed_calls: int
    average_confidence: int | None
    average_field_agreement: int | None
    average_evidence_coverage: int | None
    high_correction_calls: int
    minimum_review_sample: int
    autonomy_status: str
    autonomy_blockers: list[str]


class AiControlOverview(BaseModel):
    summary: AiControlSummary
    call_intelligence_quality: CallIntelligenceQuality
    agents: list[AiAgentRead]
    prompt_versions: list[AiPromptVersionRead]
    runs: list[AiRunRead]
    orchestrator: AiOrchestratorOverview
