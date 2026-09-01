from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.domain.rbac import PermissionKeys
from app.models.foundation import (
    BuyerOffer,
    CompensationPlanVersion,
    DealReconciliation,
    DispositionBuyerPoolRun,
    DispositionBuyerSelection,
    DispositionCampaign,
    DispositionCase,
    DispositionOperatingMode,
    Lead,
    Permission,
    Role,
    RoleAssignment,
    RolePermission,
    Transaction,
    User,
)
from app.schemas.disposition_readiness import (
    DispositionReadinessActionRead,
    DispositionReadinessCheckRead,
    DispositionReadinessOwnerRead,
    DispositionReadinessRead,
    DispositionReadinessRemediationRead,
)
from app.services import disposition_packages, dispositions
from app.services.disposition_state import ACTIVE_DISPOSITION_CASE_STATUSES

OWNER_PERMISSION_KEYS = frozenset(
    {
        PermissionKeys.VIEW_DEALS,
        PermissionKeys.EDIT_DEALS,
        PermissionKeys.VIEW_BUYERS,
        PermissionKeys.EDIT_BUYERS,
    }
)


def _href(case: DispositionCase, tab: str, anchor: str | None = None) -> str:
    value = (
        f"/os/deals?view=all&display=queue&deal={case.deal_id}"
        f"&tab=disposition&dispositionTab={tab}"
    )
    return f"{value}#{anchor}" if anchor else value


def _check(
    case: DispositionCase,
    *,
    key: str,
    label: str,
    ready: bool,
    detail: str,
    tab: str,
    anchor: str | None = None,
    complete: bool = False,
    applicable: bool = True,
) -> DispositionReadinessCheckRead:
    if not applicable:
        status: Literal["ready", "warning", "blocked", "complete", "not_applicable"] = (
            "not_applicable"
        )
    elif complete:
        status = "complete"
    else:
        status = "ready" if ready else "warning"
    return DispositionReadinessCheckRead(
        key=key,
        label=label,
        status=status,
        blocker_class="warning" if applicable and not ready and not complete else None,
        detail=detail,
        remediation=(
            DispositionReadinessRemediationRead(
                label=f"Open {label.lower()}",
                tab=tab,
                anchor=anchor,
                href=_href(case, tab, anchor),
            )
            if applicable and not ready and not complete
            else None
        ),
    )


def _action(
    case: DispositionCase,
    *,
    key: str,
    label: str,
    tab: str,
    detail: str,
    checks: list[DispositionReadinessCheckRead],
    complete: bool = False,
    applicable: bool = True,
    parallel_group: str | None = "work",
) -> DispositionReadinessActionRead:
    warnings = any(item.status in {"warning", "blocked"} for item in checks)
    state: Literal["available", "ready", "blocked", "complete", "not_applicable"]
    if not applicable:
        state = "not_applicable"
    elif complete:
        state = "complete"
    else:
        state = "available"
    return DispositionReadinessActionRead(
        key=key,
        label=label,
        state=state,
        blocker_class="warning" if warnings else None,
        detail=detail,
        target_tab=tab,
        target_anchor=None,
        href=_href(case, tab),
        best_action_rank=None,
        parallel_group=parallel_group if applicable and not complete else None,
        checks=checks,
    )


def read_case_readiness(
    db: Session,
    principal: Principal,
    case_id: UUID,
) -> DispositionReadinessRead | None:
    case = dispositions.scoped_case(db, principal, case_id)
    if case is None:
        return None
    generated_at = datetime.now(UTC)
    owner = (
        db.scalar(
            select(User).where(
                User.id == case.owner_user_id,
                User.organization_id == principal.organization_id,
                User.is_active.is_(True),
            )
        )
        if case.owner_user_id is not None
        else None
    )
    owner_permission_keys = (
        frozenset(
            db.scalars(
                select(Permission.key)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .join(RoleAssignment, RoleAssignment.role_id == RolePermission.role_id)
                .join(Role, Role.id == RoleAssignment.role_id)
                .where(
                    RoleAssignment.organization_id == principal.organization_id,
                    RoleAssignment.user_id == owner.id,
                    RolePermission.organization_id == principal.organization_id,
                    Role.organization_id == principal.organization_id,
                    Permission.key.in_(OWNER_PERMISSION_KEYS),
                )
            ).all()
        )
        if owner is not None
        else frozenset()
    )
    owner_is_ready = bool(
        owner is not None and OWNER_PERMISSION_KEYS.issubset(owner_permission_keys)
    )
    plan = (
        db.scalar(
            select(CompensationPlanVersion).where(
                CompensationPlanVersion.id == case.compensation_plan_version_id,
                CompensationPlanVersion.organization_id == principal.organization_id,
            )
        )
        if case.compensation_plan_version_id is not None
        else None
    )
    operating_mode = (
        db.scalar(
            select(DispositionOperatingMode).where(
                DispositionOperatingMode.id == case.disposition_operating_mode_id,
                DispositionOperatingMode.organization_id == principal.organization_id,
                DispositionOperatingMode.compensation_plan_version_id == plan.id,
            )
        )
        if case.disposition_operating_mode_id is not None and plan is not None
        else None
    )
    lead = db.scalar(
        select(Lead).where(
            Lead.id == case.lead_id,
            Lead.organization_id == principal.organization_id,
        )
    )
    transaction = db.scalar(
        select(Transaction).where(
            Transaction.id == case.transaction_id,
            Transaction.organization_id == principal.organization_id,
        )
    )
    active = case.status in ACTIVE_DISPOSITION_CASE_STATUSES
    is_house = bool(lead and lead.asset_class == "house")

    setup_checks = [
        _check(
            case,
            key="setup.owner",
            label="Disposition owner",
            ready=owner_is_ready,
            detail=(
                f"Assigned to {owner.display_name}."
                if owner_is_ready and owner is not None
                else "The owner is missing, inactive, or lacks Dispositions access; the "
                "workbench remains usable."
            ),
            tab="package",
        ),
        _check(
            case,
            key="setup.compensation_plan",
            label="Compensation plan",
            ready=plan is not None,
            detail=(
                "A compensation plan is attached."
                if plan is not None
                else "No compensation plan is attached; reconcile it before payout approval."
            ),
            tab="package",
        ),
        _check(
            case,
            key="setup.operating_mode",
            label="Operating mode",
            ready=operating_mode is not None,
            detail=(
                "An operating mode is attached."
                if operating_mode is not None
                else "No operating mode is attached; deal work may continue."
            ),
            tab="package",
        ),
    ]

    package_checks: list[DispositionReadinessCheckRead] = []
    package_workspace = disposition_packages.read_workspace(db, principal, case.id)
    if package_workspace is not None:
        for package_check in package_workspace.current_readiness.checks:
            package_checks.append(
                _check(
                    case,
                    key=f"package.{package_check.key}",
                    label=package_check.label,
                    ready=package_check.status == "ready",
                    detail=package_check.detail,
                    tab="package",
                    anchor=package_check.key,
                )
            )
    latest_artifact = None
    artifact_warning: str | None = None
    try:
        latest_artifact = disposition_packages.require_package_artifact(
            db,
            principal,
            case,
            action="using it from the advisory workbench",
        )
    except ValueError as exc:
        artifact_warning = str(exc)
    package_checks.insert(
        0,
        _check(
            case,
            key="package.artifact",
            label="Package artifact",
            ready=latest_artifact is not None,
            detail=(
                f"Package v{latest_artifact.version_number} ({latest_artifact.status}) is usable."
                if latest_artifact
                else artifact_warning
                or "No PDF artifact exists yet; build or upload one only when a send needs it."
            ),
            tab="package",
            anchor="package-versions",
        ),
    )

    pool_run = db.scalar(
        select(DispositionBuyerPoolRun)
        .where(
            DispositionBuyerPoolRun.organization_id == principal.organization_id,
            DispositionBuyerPoolRun.disposition_case_id == case.id,
            DispositionBuyerPoolRun.status == "completed",
        )
        .order_by(DispositionBuyerPoolRun.version_number.desc())
        .limit(1)
    )
    offer_count = int(
        db.scalar(
            select(func.count(BuyerOffer.id)).where(
                BuyerOffer.organization_id == principal.organization_id,
                BuyerOffer.disposition_case_id == case.id,
            )
        )
        or 0
    )
    campaign_count = int(
        db.scalar(
            select(func.count(DispositionCampaign.id)).where(
                DispositionCampaign.organization_id == principal.organization_id,
                DispositionCampaign.disposition_case_id == case.id,
            )
        )
        or 0
    )
    selection = db.scalar(
        select(DispositionBuyerSelection).where(
            DispositionBuyerSelection.organization_id == principal.organization_id,
            DispositionBuyerSelection.disposition_case_id == case.id,
            DispositionBuyerSelection.status == "active",
        )
    )
    reconciliation = db.scalar(
        select(DealReconciliation).where(
            DealReconciliation.organization_id == principal.organization_id,
            DealReconciliation.disposition_case_id == case.id,
        )
    )

    actions = [
        _action(
            case,
            key="setup_case",
            label="Complete case setup",
            tab="package",
            detail="Setup fields are guidance and never lock an active disposition case.",
            checks=setup_checks,
            complete=all(item.status == "ready" for item in setup_checks),
            applicable=active,
        ),
        _action(
            case,
            key="build_package",
            label="Build or review package",
            tab="package",
            detail="Package facts remain advisory until an exact artifact is needed for delivery.",
            checks=package_checks,
            complete=latest_artifact is not None,
            applicable=active,
        ),
        _action(
            case,
            key="rank_buyers",
            label="Rank buyers",
            tab="buyers",
            detail="Buyer ranking can run in parallel with package preparation.",
            checks=[
                _check(
                    case,
                    key="buyers.ranked_pool",
                    label="Ranked buyer pool",
                    ready=pool_run is not None,
                    detail=(
                        f"Buyer pool v{pool_run.version_number} is available."
                        if pool_run
                        else "No ranked pool exists yet."
                    ),
                    tab="buyers",
                    anchor="buyer-pool",
                )
            ],
            complete=pool_run is not None,
            applicable=active,
        ),
        _action(
            case,
            key="contact_buyers",
            label="Contact buyers",
            tab="execution",
            detail="One-to-one work may start with any available canonical buyer.",
            checks=[
                _check(
                    case,
                    key="buyers.contact_targets",
                    label="Buyer contact targets",
                    ready=pool_run is not None,
                    detail=(
                        "Use any candidate in the ranked pool."
                        if pool_run
                        else "Generate a pool to create concrete call targets."
                    ),
                    tab="execution",
                    anchor="call-queue",
                )
            ],
            applicable=active and is_house,
        ),
        _action(
            case,
            key="prepare_outreach",
            label="Prepare outreach",
            tab="outreach",
            detail="Bulk outreach may bind the latest usable preliminary or approved artifact.",
            checks=[
                _check(
                    case,
                    key="outreach.campaign",
                    label="Outreach campaign",
                    ready=campaign_count > 0,
                    detail=(
                        f"{campaign_count} campaign{'s' if campaign_count != 1 else ''} prepared."
                        if campaign_count
                        else "No outreach campaign has been prepared."
                    ),
                    tab="outreach",
                    anchor="campaigns",
                ),
                _check(
                    case,
                    key="outreach.package_artifact",
                    label="Sendable package artifact",
                    ready=latest_artifact is not None,
                    detail="An exact artifact is required only when the delivery includes it.",
                    tab="package",
                    anchor="package-versions",
                ),
            ],
            complete=campaign_count > 0,
            applicable=active and is_house,
        ),
        _action(
            case,
            key="record_offers",
            label="Record offers",
            tab="offers",
            detail="Offer terms can be recorded whenever a buyer makes an offer.",
            checks=[
                _check(
                    case,
                    key="offers.received",
                    label="Buyer offers",
                    ready=offer_count > 0,
                    detail=f"{offer_count} offer{'s' if offer_count != 1 else ''} recorded.",
                    tab="offers",
                    anchor="offer-room",
                )
            ],
            complete=offer_count > 0,
            applicable=active and is_house,
        ),
        _action(
            case,
            key="select_buyer",
            label="Select a buyer",
            tab="offers",
            detail="Price, POF, match quality, and backup coverage are advisory selection signals.",
            checks=[
                _check(
                    case,
                    key="selection.primary",
                    label="Primary buyer selection",
                    ready=selection is not None,
                    detail=(
                        "A primary buyer is selected."
                        if selection
                        else "No primary buyer has been selected."
                    ),
                    tab="offers",
                    anchor="buyer-selection",
                )
            ],
            complete=selection is not None,
            applicable=active and is_house,
        ),
        _action(
            case,
            key="prepare_assignment",
            label="Prepare assignment",
            tab="offers",
            detail="Assignment documents require a truthful selected buyer and exact terms.",
            checks=[
                _check(
                    case,
                    key="assignment.primary_binding",
                    label="Selected buyer binding",
                    ready=selection is not None,
                    detail="Select the buyer whose identity and economics belong in the document.",
                    tab="offers",
                    anchor="buyer-selection",
                )
            ],
            applicable=active and is_house and case.strategy == "assignment",
        ),
        _action(
            case,
            key="record_funding",
            label="Record funding",
            tab="offers",
            detail="Funding is recorded only from truthful closing evidence.",
            checks=[
                _check(
                    case,
                    key="funding.transaction",
                    label="Funded transaction",
                    ready=bool(transaction and transaction.status == "funded"),
                    detail=(
                        "The transaction is funded."
                        if transaction and transaction.status == "funded"
                        else "Funding has not been recorded."
                    ),
                    tab="offers",
                    anchor="offer-room",
                )
            ],
            complete=bool(transaction and transaction.status == "funded"),
            applicable=is_house and (active or case.status in {"closed", "reconciled"}),
        ),
        _action(
            case,
            key="reconcile",
            label="Reconcile deal",
            tab="reconciliation",
            detail="Compensation setup becomes a release concern at financial reconciliation.",
            checks=[
                _check(
                    case,
                    key="reconciliation.record",
                    label="Deal reconciliation",
                    ready=reconciliation is not None,
                    detail=(
                        f"Reconciliation is {reconciliation.status}."
                        if reconciliation
                        else "No reconciliation has been created."
                    ),
                    tab="reconciliation",
                    anchor="deal-reconciliation",
                )
            ],
            complete=bool(reconciliation and reconciliation.status == "approved"),
            applicable=is_house
            and (
                bool(transaction and transaction.status == "funded")
                or case.status in {"closed", "reconciled"}
            ),
            parallel_group=None,
        ),
    ]

    available = [action for action in actions if action.state == "available"]
    for rank, available_action in enumerate(available, 1):
        available_action.best_action_rank = rank
    if available:
        available[0].state = "ready"
    parallel_action_keys = [
        action.key
        for action in available[1:]
        if action.parallel_group == "work"
    ][:4]
    all_checks = [check for action in actions for check in action.checks]
    warning_count = sum(
        check.status in {"warning", "blocked"} for check in all_checks
    )
    applicable_actions = [
        action for action in actions if action.state != "not_applicable"
    ]
    completed_count = sum(
        action.state == "complete" for action in applicable_actions
    )
    fingerprint_payload: dict[str, Any] = {
        "case_id": str(case.id),
        "case_status": case.status,
        "owner_user_id": str(case.owner_user_id) if case.owner_user_id else None,
        "compensation_plan_version_id": (
            str(case.compensation_plan_version_id)
            if case.compensation_plan_version_id
            else None
        ),
        "disposition_operating_mode_id": (
            str(case.disposition_operating_mode_id)
            if case.disposition_operating_mode_id
            else None
        ),
        "latest_artifact_id": str(latest_artifact.id) if latest_artifact else None,
        "pool_run_id": str(pool_run.id) if pool_run else None,
        "campaign_count": campaign_count,
        "offer_count": offer_count,
        "selection_id": str(selection.id) if selection else None,
        "transaction_status": transaction.status if transaction else None,
        "reconciliation_status": reconciliation.status if reconciliation else None,
        "warnings": [
            (check.key, check.status, check.detail) for check in all_checks
        ],
    }
    source_fingerprint = sha256(
        json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return DispositionReadinessRead(
        case_id=case.id,
        generated_at=generated_at,
        source_fingerprint=source_fingerprint,
        owner=(
            DispositionReadinessOwnerRead(user_id=owner.id, label=owner.display_name)
            if owner
            else None
        ),
        warning_count=warning_count,
        completed_count=completed_count,
        total_count=len(applicable_actions),
        best_action_key=available[0].key if available else None,
        parallel_action_keys=parallel_action_keys,
        actions=actions,
    )
