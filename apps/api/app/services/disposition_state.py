from __future__ import annotations

from app.models.foundation import DispositionCase

ACTIVE_DISPOSITION_CASE_STATUSES = frozenset(
    {
        "package_prep",
        "buyer_matching",
        "marketed",
        "offers_received",
        "buyer_selected",
    }
)
TERMINAL_DISPOSITION_CASE_STATUSES = frozenset(
    {"cancelled", "canceled", "closed", "reconciled"}
)

_MILESTONE_ORDER = {
    "package_prep": 0,
    "buyer_matching": 1,
    "marketed": 2,
    "offers_received": 3,
    "buyer_selected": 4,
    "closed": 5,
    "reconciled": 6,
}


def is_active_disposition_case(case: DispositionCase) -> bool:
    return case.status in ACTIVE_DISPOSITION_CASE_STATUSES


def advance_disposition_milestone(case: DispositionCase, milestone: str) -> None:
    """Advance a display milestone without making it an authorization source."""

    if case.status in TERMINAL_DISPOSITION_CASE_STATUSES:
        return
    current_rank = _MILESTONE_ORDER.get(case.status, -1)
    requested_rank = _MILESTONE_ORDER.get(milestone)
    if requested_rank is not None and requested_rank > current_rank:
        case.status = milestone
