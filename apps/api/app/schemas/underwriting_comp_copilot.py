from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

CompCopilotActionType = Literal[
    "open_comp_review",
    "review_comp",
    "inspect_condition",
    "verify_micro_market",
    "refresh_evidence",
]


class CompCopilotAskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=800)

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 2:
            raise ValueError("Ask a complete valuation question.")
        return normalized


class CompCopilotCitationRead(BaseModel):
    evidence_id: str
    label: str
    kind: Literal["analysis", "subject", "comparable", "source"]
    comp_key: str | None = None
    source_url: str | None = None


class CompCopilotSuggestedActionRead(BaseModel):
    action_type: CompCopilotActionType
    label: str
    rationale: str
    comp_key: str | None = None


class CompCopilotMessageRead(BaseModel):
    id: UUID
    role: Literal["user", "assistant"]
    content: str
    author_user_id: UUID | None = None
    author_name: str | None = None
    citations: list[CompCopilotCitationRead] = Field(default_factory=list)
    suggested_actions: list[CompCopilotSuggestedActionRead] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] | None = None
    limitations: list[str] = Field(default_factory=list)
    used_ai: bool = False
    model: str | None = None
    created_at: datetime


class CompCopilotThreadRead(BaseModel):
    thread_id: UUID | None = None
    analysis_id: UUID
    analysis_created_at: datetime
    messages: list[CompCopilotMessageRead] = Field(default_factory=list)
    suggested_questions: list[str] = Field(default_factory=list)
    ai_available: bool
    valuation_authority: Literal["deterministic_v3_only"] = "deterministic_v3_only"


class CompCopilotAnswerRead(BaseModel):
    thread: CompCopilotThreadRead
    answer: CompCopilotMessageRead


class CompCopilotDraftCitation(BaseModel):
    evidence_id: str = Field(min_length=1, max_length=240)


class CompCopilotDraftAction(BaseModel):
    action_type: CompCopilotActionType
    label: str = Field(min_length=1, max_length=160)
    rationale: str = Field(min_length=1, max_length=500)
    comp_key: str | None = Field(default=None, max_length=500)


class CompCopilotDraft(BaseModel):
    answer: str = Field(min_length=1, max_length=4000)
    citations: list[CompCopilotDraftCitation] = Field(min_length=1, max_length=12)
    suggested_actions: list[CompCopilotDraftAction] = Field(max_length=8)
    confidence: Literal["high", "medium", "low"]
    limitations: list[str] = Field(max_length=8)
    human_review_required: Literal[True]
    valuation_authority: Literal["deterministic_v3_only"]
