from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.foundation import Lead

TERMINAL_CLOSE_OUT_STAGES = {"dead", "disqualified"}
INACTIVE_LEAD_STAGES = TERMINAL_CLOSE_OUT_STAGES | {"closed"}


class LeadLifecycleConflictError(ValueError):
    """Raised when active work is attempted on a business-closed seller lead."""


def require_lead_open_for_work(lead: Lead) -> None:
    if lead.archived_at is not None or lead.stage_key in TERMINAL_CLOSE_OUT_STAGES:
        raise LeadLifecycleConflictError(
            "This lead is closed. Reopen it before adding or changing active work."
        )
    if lead.stage_key == "closed":
        raise LeadLifecycleConflictError(
            "This lead belongs to a completed deal. Active seller follow-up cannot be added."
        )


def require_lead_not_closed_out(lead: Lead) -> None:
    """Permit completed-deal operations while rejecting Dead/Disqualified close-outs."""
    if lead.archived_at is not None or lead.stage_key in TERMINAL_CLOSE_OUT_STAGES:
        raise LeadLifecycleConflictError(
            "This lead is closed. Reopen it before changing its deal workflow."
        )


def lock_organization_lead(
    db: Session,
    *,
    organization_id: UUID,
    lead_id: UUID,
) -> Lead | None:
    return db.scalar(
        select(Lead)
        .where(
            Lead.organization_id == organization_id,
            Lead.id == lead_id,
        )
        .execution_options(populate_existing=True)
        .with_for_update()
    )
