from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.deals import DealQueueItemRead

DispositionDeskScope = Literal["mine", "team"]
DispositionDeskCategory = Literal[
    "today",
    "active_deals",
    "buyer_follow_ups",
    "replies",
    "offers",
    "deadlines",
]


class DispositionDeskActionRead(BaseModel):
    label: str
    href: str


class DispositionDeskItemRead(BaseModel):
    key: str
    category: DispositionDeskCategory
    title: str
    context: str
    owner_user_id: UUID | None
    owner_name: str
    due_at: datetime | None
    reason: str
    blocker: str | None
    severity: Literal["info", "warning", "danger"]
    deal_id: UUID | None = None
    buyer_id: UUID | None = None
    conversation_id: UUID | None = None
    task_id: UUID | None = None
    offer_id: UUID | None = None
    disposition_case_id: UUID | None = None
    primary_action: DispositionDeskActionRead
    secondary_action: DispositionDeskActionRead | None = None


class DispositionDeskBuyerHealthRead(BaseModel):
    total: int
    active: int
    needs_review: int
    unassigned: int
    missing_proof: int
    expiring_proof: int
    missing_criteria: int


class DispositionDeskMetricsRead(BaseModel):
    today: int
    active_deals: int
    buyer_follow_ups: int
    replies: int
    offers: int
    deadlines: int
    weak_coverage: int


class DispositionDeskSectionStatusRead(BaseModel):
    total: int
    returned: int
    has_more: bool
    offset: int


class DispositionDeskSectionsRead(BaseModel):
    today: DispositionDeskSectionStatusRead
    active_deals: DispositionDeskSectionStatusRead
    buyer_follow_ups: DispositionDeskSectionStatusRead
    replies: DispositionDeskSectionStatusRead
    offers: DispositionDeskSectionStatusRead
    deadlines: DispositionDeskSectionStatusRead
    coverage_warnings: DispositionDeskSectionStatusRead
    deal_records: DispositionDeskSectionStatusRead


class DispositionDeskSourceHealthRead(BaseModel):
    generated_at: datetime
    canonical_data_status: Literal["current"] = "current"
    external_provider_status: Literal[
        "not_configured",
        "configured_unverified",
        "available",
        "unavailable",
    ]
    message: str


class DispositionDeskRead(BaseModel):
    requested_scope: DispositionDeskScope
    effective_scope: DispositionDeskScope
    scope_label: str
    scope_member_count: int
    can_view_team: bool
    scope_notice: str | None = None
    can_edit_buyers: bool
    metrics: DispositionDeskMetricsRead
    sections: DispositionDeskSectionsRead
    buyer_network: DispositionDeskBuyerHealthRead
    today: list[DispositionDeskItemRead] = Field(default_factory=list)
    active_deals: list[DispositionDeskItemRead] = Field(default_factory=list)
    buyer_follow_ups: list[DispositionDeskItemRead] = Field(default_factory=list)
    replies: list[DispositionDeskItemRead] = Field(default_factory=list)
    offers: list[DispositionDeskItemRead] = Field(default_factory=list)
    deadlines: list[DispositionDeskItemRead] = Field(default_factory=list)
    coverage_warnings: list[DispositionDeskItemRead] = Field(default_factory=list)
    deal_records: list[DealQueueItemRead] = Field(default_factory=list)
    source_health: DispositionDeskSourceHealthRead
