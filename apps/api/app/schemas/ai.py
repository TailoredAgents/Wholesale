from datetime import datetime
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
    tool_calls: list[AiToolCallRead]
    created_at: datetime


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
