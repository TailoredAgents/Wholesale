from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class QualificationQuestion(BaseModel):
    key: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1, max_length=120)
    prompt: str = Field(min_length=1, max_length=500)
    answer_type: Literal["text", "choice", "boolean"] = "text"
    choices: list[str] = Field(default_factory=list, max_length=12)
    required: bool = True

    @model_validator(mode="after")
    def validate_choices(self) -> "QualificationQuestion":
        if self.answer_type == "choice" and not self.choices:
            raise ValueError("Choice questions require at least one choice.")
        if self.answer_type != "choice" and self.choices:
            raise ValueError("Only choice questions may define choices.")
        return self


class QualificationScriptCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    introduction: str = Field(min_length=1, max_length=3000)
    questions: list[QualificationQuestion] = Field(min_length=1, max_length=30)

    @field_validator("questions")
    @classmethod
    def unique_question_keys(
        cls, questions: list[QualificationQuestion]
    ) -> list[QualificationQuestion]:
        keys = [question.key for question in questions]
        if len(keys) != len(set(keys)):
            raise ValueError("Qualification question keys must be unique.")
        return questions


class QualificationScriptRead(BaseModel):
    id: UUID
    version_number: int
    title: str
    status: str
    introduction: str
    questions: list[QualificationQuestion]
    approved_at: datetime | None
    created_at: datetime


class LeadManagerCaseRead(BaseModel):
    id: UUID
    lead_id: UUID
    handoff_id: UUID | None
    seller_name: str
    property_address: str
    source: str
    stage_key: str
    assigned_user_id: UUID
    assigned_user_name: str
    status: str
    acceptance_due_at: datetime
    accepted_at: datetime | None
    escalated_at: datetime | None
    acceptance_minutes: int | None
    is_acceptance_overdue: bool
    qualification_completed_at: datetime | None
    qualification_quality_basis_points: int | None
    next_action_type: str | None
    next_action_due_at: datetime | None
    is_next_action_overdue: bool
    age_hours: int
    lead_url: str


class LeadManagerMetrics(BaseModel):
    awaiting_acceptance: int
    overdue_acceptance: int
    qualification_due: int
    follow_up_due: int
    appointments_today: int
    neglected_leads: int


class LeadManagerScorecard(BaseModel):
    user_id: UUID
    user_name: str
    handoffs_received: int
    handoffs_accepted: int
    accepted_within_sla: int
    average_acceptance_minutes: int | None
    qualifications_completed: int
    appointments_set: int
    appointments_held: int
    appointment_no_shows: int
    contracts_created: int
    follow_up_quality_basis_points: int


class LeadManagerOverview(BaseModel):
    current_user_id: UUID
    current_user_name: str
    can_manage: bool
    metrics: LeadManagerMetrics
    active_script: QualificationScriptRead | None
    scripts: list[QualificationScriptRead]
    awaiting_acceptance: list[LeadManagerCaseRead]
    qualification_queue: list[LeadManagerCaseRead]
    follow_up_queue: list[LeadManagerCaseRead]
    appointments_today: list[LeadManagerCaseRead]
    neglected_queue: list[LeadManagerCaseRead]
    scorecards: list[LeadManagerScorecard]


class LeadManagerAcceptRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)


class QualificationCompleteRequest(BaseModel):
    answers: dict[str, str | bool] = Field(default_factory=dict)
    next_action_type: Literal[
        "call", "sms", "email", "appointment", "nurture", "disqualify"
    ]
    next_action_due_at: datetime | None = None

    @model_validator(mode="after")
    def require_due_time(self) -> "QualificationCompleteRequest":
        if self.next_action_type not in {"disqualify"} and self.next_action_due_at is None:
            raise ValueError("A dated next action is required for every active lead.")
        return self


class QualificationSessionRead(BaseModel):
    id: UUID
    case_id: UUID
    lead_id: UUID
    script_version_id: UUID
    script_version_number: int
    answers: dict[str, str | bool]
    missing_required_keys: list[str]
    quality_score_basis_points: int
    next_action_type: str
    next_action_due_at: datetime | None
    completed_at: datetime
