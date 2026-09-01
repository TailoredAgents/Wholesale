from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

ReadinessActionState = Literal[
    "available", "ready", "blocked", "complete", "not_applicable"
]
ReadinessCheckStatus = Literal["ready", "warning", "blocked", "complete", "not_applicable"]
ReadinessBlockerClass = Literal["hard_stop", "release_gate", "warning"]


class DispositionReadinessRemediationRead(BaseModel):
    label: str
    tab: str
    anchor: str | None = None
    href: str


class DispositionReadinessCheckRead(BaseModel):
    key: str
    label: str
    status: ReadinessCheckStatus
    blocker_class: ReadinessBlockerClass | None
    detail: str
    is_advisory: Literal[True] = True
    remediation: DispositionReadinessRemediationRead | None = None


class DispositionReadinessActionRead(BaseModel):
    key: str
    label: str
    state: ReadinessActionState
    blocker_class: ReadinessBlockerClass | None
    detail: str
    is_advisory: Literal[True] = True
    target_tab: str
    target_anchor: str | None = None
    href: str
    best_action_rank: int | None = None
    parallel_group: str | None = None
    checks: list[DispositionReadinessCheckRead]


class DispositionReadinessOwnerRead(BaseModel):
    user_id: UUID
    label: str


class DispositionReadinessRead(BaseModel):
    case_id: UUID
    is_advisory: Literal[True] = True
    generated_at: datetime
    source_fingerprint: str
    owner: DispositionReadinessOwnerRead | None
    warning_count: int
    completed_count: int
    total_count: int
    best_action_key: str | None
    parallel_action_keys: list[str]
    actions: list[DispositionReadinessActionRead]
