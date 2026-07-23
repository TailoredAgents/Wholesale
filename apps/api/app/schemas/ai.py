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
    model_name: str = Field(default="gpt-5.6-sol", max_length=120)
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


class AiCopilotAgentMappingRead(BaseModel):
    id: UUID
    agent_definition_id: UUID
    agent_key: str
    agent_name: str
    purpose: str
    display_order: int


class AiCapabilityContractRead(BaseModel):
    id: UUID
    copilot_definition_id: UUID
    capability_key: str
    name: str
    version_number: int
    status: str
    owner_role_key: str
    trigger_events: list[str]
    input_requirements: list[str]
    output_requirements: list[str]
    allowed_tool_scopes: list[str]
    evidence_requirements: list[str]
    approval_policy: dict[str, object]
    escalation_policy: dict[str, object]
    prohibited_actions: list[str]
    approved_by_user_id: UUID | None
    approved_at: datetime | None
    created_at: datetime


class AiCopilotRead(BaseModel):
    id: UUID
    key: str
    name: str
    description: str
    human_owner_role_key: str
    human_owner_title: str
    human_authority_summary: str
    status: str
    phase_key: str
    approved_by_user_id: UUID | None
    approved_at: datetime | None
    specialist_mappings: list[AiCopilotAgentMappingRead]
    capability_contracts: list[AiCapabilityContractRead]
    created_at: datetime


class AiDataGovernancePolicyRead(BaseModel):
    id: UUID
    key: str
    name: str
    data_category: str
    field_scope: list[str]
    version_number: int
    status: str
    source_precedence: list[str]
    overwrite_policy: str
    redaction_rule: str
    retention_rule: str
    permitted_role_keys: list[str]
    approved_by_user_id: UUID | None
    approved_at: datetime | None
    created_at: datetime


class AiKnowledgeSourceRead(BaseModel):
    id: UUID
    key: str
    title: str
    category: str
    source_type: str
    content_reference: str
    version_number: int
    status: str
    owner_role_key: str
    audience_role_keys: list[str]
    is_authoritative: bool
    effective_at: datetime | None
    review_due_at: datetime | None
    content_checksum: str | None
    content_snapshot: str | None
    approved_by_user_id: UUID | None
    approved_at: datetime | None
    created_at: datetime


class AiDataQualityRuleRead(BaseModel):
    id: UUID
    key: str
    name: str
    record_type: str
    field_scope: list[str]
    rule_type: str
    severity: str
    is_deterministic: bool
    configuration: dict[str, object]
    resolution_action: str
    version_number: int
    status: str
    approved_by_user_id: UUID | None
    approved_at: datetime | None
    created_at: datetime


class AiCopilotFoundationRead(BaseModel):
    status: str
    copilots: list[AiCopilotRead]
    data_governance_policies: list[AiDataGovernancePolicyRead]
    knowledge_sources: list[AiKnowledgeSourceRead]
    data_quality_rules: list[AiDataQualityRuleRead]


class AiCopilotFoundationInstallRead(BaseModel):
    created_copilot_count: int
    created_mapping_count: int
    created_contract_count: int
    created_policy_count: int
    created_knowledge_source_count: int
    created_data_quality_rule_count: int
    foundation: AiCopilotFoundationRead


class AiCopilotFoundationDecision(BaseModel):
    decision: Literal["approve", "return_to_draft"]
    notes: str = Field(min_length=1, max_length=2000)


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


class AiRuntimeInstallRead(BaseModel):
    created_runtime_policy: bool
    created_capability_policy_count: int
    updated_knowledge_source_count: int
    runtime: "AiRuntimeOverview"


class AiRuntimePolicyUpdate(BaseModel):
    provider_status: Literal["enabled", "disabled"] | None = None
    high_volume_model: str | None = Field(default=None, min_length=1, max_length=120)
    default_model: str | None = Field(default=None, min_length=1, max_length=120)
    escalation_model: str | None = Field(default=None, min_length=1, max_length=120)
    max_context_characters: int | None = Field(default=None, ge=4000, le=200_000)
    max_requests_per_minute: int | None = Field(default=None, ge=1, le=1000)
    max_daily_cost_microusd: int | None = Field(default=None, ge=0, le=10_000_000_000)
    circuit_failure_threshold: int | None = Field(default=None, ge=1, le=20)
    circuit_cooldown_seconds: int | None = Field(default=None, ge=30, le=86_400)


class AiCapabilityRuntimeUpdate(BaseModel):
    status: Literal["enabled", "disabled"]
    model_route: Literal["high_volume", "default", "escalation"] | None = None


class AiRuntimeShutdownCreate(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class AiRuntimeExecuteCreate(BaseModel):
    agent_definition_id: UUID
    capability_key: str = Field(min_length=1, max_length=160)
    idempotency_key: str = Field(min_length=1, max_length=255)
    input_payload: dict[str, object] = Field(default_factory=dict)
    lead_id: UUID | None = None
    appointment_id: UUID | None = None
    transaction_id: UUID | None = None
    prospect_id: UUID | None = None
    prospecting_entry_id: UUID | None = None
    prospecting_attempt_id: UUID | None = None


class AiRuntimePolicyRead(BaseModel):
    id: UUID
    provider_status: str
    emergency_stop: bool
    emergency_stop_reason: str | None
    high_volume_model: str
    default_model: str
    escalation_model: str
    max_context_characters: int
    max_requests_per_minute: int
    max_daily_cost_microusd: int
    circuit_failure_threshold: int
    circuit_cooldown_seconds: int
    consecutive_failure_count: int
    circuit_open_until: datetime | None
    trace_redaction_enabled: bool
    external_actions_enabled: bool
    updated_at: datetime


class AiCapabilityRuntimeRead(BaseModel):
    id: UUID
    agent_definition_id: UUID
    agent_name: str
    capability_key: str
    status: str
    model_route: str
    output_schema: dict[str, object]
    allowed_tool_keys: list[str]
    allowed_knowledge_keys: list[str]
    max_output_tokens: int
    max_cost_microusd_per_run: int
    requires_human_review: bool
    updated_at: datetime


class AiEvaluationComparisonCreate(BaseModel):
    baseline_evaluation_run_id: UUID
    challenger_evaluation_run_id: UUID


class AiEvaluationComparisonRead(BaseModel):
    id: UUID
    dataset_id: UUID
    baseline_evaluation_run_id: UUID
    challenger_evaluation_run_id: UUID
    status: str
    regression_blocked: bool
    quality_delta_basis_points: int
    latency_delta_ms: int | None
    cost_delta_microusd: int | None
    summary: dict[str, object]
    created_at: datetime


class AiRuntimeMetrics(BaseModel):
    enabled_capability_count: int
    blocked_run_count: int
    failed_run_count: int
    redacted_trace_count: int
    knowledge_use_count: int
    regression_block_count: int


class AiRuntimeOverview(BaseModel):
    status: str
    policy: AiRuntimePolicyRead | None
    capabilities: list[AiCapabilityRuntimeRead]
    comparisons: list[AiEvaluationComparisonRead]
    metrics: AiRuntimeMetrics


class AiEvaluationCaseCreate(BaseModel):
    case_key: str = Field(min_length=1, max_length=160)
    name: str = Field(min_length=1, max_length=255)
    input_payload: dict[str, object]
    expected_output: dict[str, object] = Field(default_factory=dict)
    candidate_output: dict[str, object] | None = None
    deterministic_checks: dict[str, object] = Field(default_factory=dict)
    risk_tags: list[str] = Field(default_factory=list)
    is_critical: bool = False
    case_type: Literal["operating", "policy", "failure", "adversarial"] = "operating"
    scenario_family: str = Field(default="manual", min_length=1, max_length=120)
    source_type: Literal["synthetic", "corrected_production"] = "synthetic"
    source_reference: str | None = Field(default=None, max_length=255)
    redaction_status: Literal["verified", "needs_review"] = "verified"
    expected_uncertainty: list[str] = Field(default_factory=list, max_length=30)
    required_evidence: list[str] = Field(default_factory=list, max_length=30)
    prohibited_behaviors: list[str] = Field(default_factory=list, max_length=30)
    reviewer_notes: str = Field(default="", max_length=2000)


class AiEvaluationDatasetCreate(BaseModel):
    agent_definition_id: UUID
    capability_key: str = Field(min_length=1, max_length=160)
    dataset_key: str = Field(default="manual", min_length=1, max_length=160)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    minimum_case_count: int = Field(default=3, ge=1, le=500)
    minimum_pass_rate_basis_points: int = Field(default=9000, ge=0, le=10000)
    minimum_factual_accuracy_basis_points: int = Field(default=9000, ge=0, le=10000)
    minimum_evidence_coverage_basis_points: int = Field(default=9000, ge=0, le=10000)
    maximum_critical_failures: int = Field(default=0, ge=0, le=500)
    maximum_average_latency_ms: int | None = Field(default=None, ge=0)
    maximum_average_cost_microusd: int | None = Field(default=None, ge=0)
    owner_role_key: str = Field(default="owner", min_length=1, max_length=120)
    case_schema_version: int = Field(default=1, ge=1, le=100)
    reviewer_instructions: str = Field(default="", max_length=8000)
    disagreement_policy: str = Field(default="", max_length=4000)
    redaction_policy: dict[str, object] = Field(default_factory=dict)
    required_review_scopes: list[Literal["executive", "role_owner"]] = Field(
        default_factory=list,
        max_length=2,
    )
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
    case_type: str
    scenario_family: str
    source_type: str
    source_reference: str | None
    redaction_status: str
    expected_uncertainty: list[str]
    required_evidence: list[str]
    prohibited_behaviors: list[str]
    reviewer_notes: str


class AiEvaluationDatasetReviewRead(BaseModel):
    id: UUID
    review_scope: str
    reviewer_role_key: str
    status: str
    notes: str
    reviewed_by_user_id: UUID
    reviewed_at: datetime


class AiEvaluationDatasetRead(BaseModel):
    id: UUID
    agent_definition_id: UUID
    capability_key: str
    dataset_key: str
    name: str
    version_number: int
    status: str
    description: str | None
    minimum_case_count: int
    minimum_pass_rate_basis_points: int
    minimum_factual_accuracy_basis_points: int
    minimum_evidence_coverage_basis_points: int
    maximum_critical_failures: int
    maximum_average_latency_ms: int | None
    maximum_average_cost_microusd: int | None
    owner_role_key: str
    case_schema_version: int
    reviewer_instructions: str
    disagreement_policy: str
    redaction_policy: dict[str, object]
    required_review_scopes: list[str]
    reviews: list[AiEvaluationDatasetReviewRead]
    approved_by_user_id: UUID | None
    approved_at: datetime | None
    cases: list[AiEvaluationCaseRead]
    created_at: datetime


class AiEvaluationDecision(BaseModel):
    decision: Literal["approve", "retire"]


class AiEvaluationReviewCreate(BaseModel):
    review_scope: Literal["executive", "role_owner"]
    decision: Literal["approve", "request_changes"]
    notes: str = Field(min_length=1, max_length=2000)


class AiCorrectedEvaluationCaseCreate(BaseModel):
    case: AiEvaluationCaseCreate
    source_reference: str = Field(min_length=1, max_length=255)
    correction_notes: str = Field(min_length=1, max_length=2000)


class AiGoldenLibraryInstallRead(BaseModel):
    created_dataset_count: int
    existing_dataset_count: int
    datasets: list[AiEvaluationDatasetRead]


class AiEvaluationRunCreate(BaseModel):
    dataset_id: UUID
    prompt_version_id: UUID


class AiEvaluationResultRead(BaseModel):
    id: UUID
    evaluation_case_id: UUID
    status: str
    score_basis_points: int
    factual_accuracy_basis_points: int
    evidence_coverage_basis_points: int
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
    factual_accuracy_basis_points: int
    evidence_coverage_basis_points: int
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
    copilot_count: int
    active_copilot_count: int
    governed_run_count: int
    unreviewed_trace_count: int
    approved_dataset_count: int
    passing_evaluation_count: int
    pending_promotion_count: int
    active_promotion_count: int
    budget_blocked_run_count: int


class AiOrchestratorOverview(BaseModel):
    metrics: AiOrchestratorMetrics
    foundation: AiCopilotFoundationRead
    events: list[AiOrchestratorEventRead]
    datasets: list[AiEvaluationDatasetRead]
    evaluation_runs: list[AiEvaluationRunRead]
    promotions: list[AiPromotionRead]
    runtime: AiRuntimeOverview


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
