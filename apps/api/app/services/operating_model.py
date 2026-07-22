from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.models.foundation import (
    AuditEvent,
    CompensationPlanRole,
    CompensationPlanVersion,
    Contact,
    Deal,
    DispositionOperatingMode,
    Lead,
    Market,
    MarketLaunchChecklist,
    MarketLaunchChecklistItem,
    RoleCredit,
    Transaction,
    User,
)
from app.schemas.operating_model import (
    BusinessMarketRead,
    BusinessUserRead,
    CompensationPlanActivation,
    CompensationPlanCreate,
    CompensationPlanRead,
    CompensationPlanRoleRead,
    DispositionOperatingModeRead,
    MarketLaunchChecklistApproval,
    MarketLaunchChecklistCreate,
    MarketLaunchChecklistItemRead,
    MarketLaunchChecklistItemUpdate,
    MarketLaunchChecklistRead,
    OperatingModelOverview,
    RoleCreditCreate,
    RoleCreditDecision,
    RoleCreditRead,
)

PLAN_ROLE_SPECS = (
    ("lead_manager", "lead_manager_basis_points", None),
    ("acquisitions_closer", "acquisitions_closer_basis_points", None),
    ("ceo_management", "ceo_management_basis_points", None),
    ("dispositions", "dispositions_basis_points", None),
    (
        "transaction_coordinator",
        "transaction_coordinator_basis_points",
        "transaction_coordinator_cap_cents",
    ),
)

LAUNCH_ITEM_SPECS = (
    ("service_area", "market", "Approved counties, territory, and acquisition buy box"),
    ("economics", "finance", "Market economics and campaign budget approved"),
    ("contracts", "legal", "State-specific contract and disclosure templates approved"),
    ("legal_review", "legal", "Local legal and compliance review completed"),
    ("contact_rules", "compliance", "Calling, messaging, consent, and recording rules documented"),
    ("closing_partners", "transactions", "Closing attorney, title, and funding partners confirmed"),
    ("buyer_coverage", "dispositions", "Qualified buyer coverage validated"),
    ("staffing", "people", "Role coverage, capacity, and escalation owners assigned"),
    ("communications", "systems", "Company numbers, messaging, email, and routing configured"),
    ("attribution", "marketing", "Campaign attribution and cost tracking validated"),
    ("owner_review", "approval", "Owner launch review completed"),
)


def get_operating_model_overview(db: Session, principal: Principal) -> OperatingModelOverview:
    users = db.scalars(
        select(User)
        .where(User.organization_id == principal.organization_id)
        .order_by(User.is_active.desc(), User.display_name)
    ).all()
    markets = db.scalars(
        select(Market)
        .where(Market.organization_id == principal.organization_id)
        .order_by(Market.is_primary.desc(), Market.name)
    ).all()
    plans = db.scalars(
        select(CompensationPlanVersion)
        .where(CompensationPlanVersion.organization_id == principal.organization_id)
        .order_by(
            (CompensationPlanVersion.status == "active").desc(),
            CompensationPlanVersion.version_number.desc(),
        )
    ).all()
    credits = db.scalars(
        select(RoleCredit)
        .where(RoleCredit.organization_id == principal.organization_id)
        .order_by(RoleCredit.created_at.desc())
        .limit(200)
    ).all()
    checklists = db.scalars(
        select(MarketLaunchChecklist)
        .where(MarketLaunchChecklist.organization_id == principal.organization_id)
        .order_by(MarketLaunchChecklist.created_at.desc())
    ).all()
    return OperatingModelOverview(
        users=[
            BusinessUserRead(
                id=user.id,
                display_name=user.display_name,
                email=user.email,
                is_active=user.is_active,
            )
            for user in users
        ],
        markets=[
            BusinessMarketRead(
                id=market.id,
                name=market.name,
                state_code=market.state_code,
                status=market.status,
            )
            for market in markets
        ],
        compensation_plans=[compensation_plan_read(db, plan) for plan in plans],
        role_credits=[role_credit_read(db, credit) for credit in credits],
        launch_checklists=[launch_checklist_read(db, checklist) for checklist in checklists],
    )


def create_compensation_plan(
    db: Session,
    principal: Principal,
    payload: CompensationPlanCreate,
) -> CompensationPlanRead:
    normalized_name = payload.name.strip()
    version_number = (
        int(
            db.scalar(
                select(func.coalesce(func.max(CompensationPlanVersion.version_number), 0)).where(
                    CompensationPlanVersion.organization_id == principal.organization_id,
                    CompensationPlanVersion.name == normalized_name,
                )
            )
            or 0
        )
        + 1
    )
    plan = CompensationPlanVersion(
        organization_id=principal.organization_id,
        name=normalized_name,
        version_number=version_number,
        status="draft",
        acquisition_reserve_cents=payload.acquisition_reserve_cents,
        target_company_margin_basis_points=payload.target_company_margin_basis_points,
        effective_start_at=None,
        effective_end_at=None,
        created_by_user_id=principal.user_id,
        approved_by_user_id=None,
        approved_at=None,
        notes=clean_text(payload.notes),
    )
    db.add(plan)
    db.flush()
    for role_key, basis_attribute, cap_attribute in PLAN_ROLE_SPECS:
        cap_cents = getattr(payload, cap_attribute) if cap_attribute else None
        db.add(
            CompensationPlanRole(
                organization_id=principal.organization_id,
                compensation_plan_version_id=plan.id,
                role_key=role_key,
                basis_points=getattr(payload, basis_attribute),
                cap_cents=cap_cents,
                notes=(
                    "Any amount above the cap returns to the company."
                    if role_key == "transaction_coordinator"
                    else None
                ),
            )
        )
    create_disposition_modes(db, principal.organization_id, plan.id, payload)
    add_audit(
        db,
        principal,
        action="operating_model.compensation_plan_create",
        entity_type="compensation_plan_version",
        entity_id=plan.id,
        previous=None,
        new={
            "name": plan.name,
            "version_number": plan.version_number,
            "status": plan.status,
            "acquisition_reserve_cents": plan.acquisition_reserve_cents,
            "target_company_margin_basis_points": plan.target_company_margin_basis_points,
        },
        reason="Versioned compensation plan created",
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("This compensation plan version already exists.") from exc
    return compensation_plan_read(db, plan)


def create_disposition_modes(
    db: Session,
    organization_id: UUID,
    plan_id: UUID,
    payload: CompensationPlanCreate,
) -> None:
    non_disposition_share = (
        payload.lead_manager_basis_points
        + payload.acquisitions_closer_basis_points
        + payload.ceo_management_basis_points
        + payload.transaction_coordinator_basis_points
    )
    human_company_share = 10000 - non_disposition_share - payload.dispositions_basis_points
    ai_managed_company_share = (
        10000 - non_disposition_share - payload.ai_managed_disposition_basis_points
    )
    ai_oversight_company_min = (
        10000 - non_disposition_share - payload.ai_oversight_disposition_max_basis_points
    )
    ai_oversight_company_max = (
        10000 - non_disposition_share - payload.ai_oversight_disposition_min_basis_points
    )
    common_requirements: dict[str, object] = {
        "requires_owner_activation": True,
        "requires_documented_evaluation": True,
        "human_final_buyer_approval": True,
    }
    specs = (
        (
            "human_led",
            "Human-led",
            payload.dispositions_basis_points,
            payload.dispositions_basis_points,
            human_company_share,
            human_company_share,
            "human_execution",
            "available",
            {"requires_documented_evaluation": False},
        ),
        (
            "ai_operated_human_managed",
            "AI-operated, human-managed",
            payload.ai_managed_disposition_basis_points,
            payload.ai_managed_disposition_basis_points,
            ai_managed_company_share,
            ai_managed_company_share,
            "internal_execution_with_human_management",
            "locked",
            {**common_requirements},
        ),
        (
            "ai_led_human_oversight",
            "AI-led, human exception oversight",
            payload.ai_oversight_disposition_min_basis_points,
            payload.ai_oversight_disposition_max_basis_points,
            ai_oversight_company_min,
            ai_oversight_company_max,
            "controlled_external_execution",
            "locked",
            {**common_requirements},
        ),
    )
    for (
        key,
        name,
        human_min,
        human_max,
        company_min,
        company_max,
        authority,
        status,
        requirements,
    ) in specs:
        db.add(
            DispositionOperatingMode(
                organization_id=organization_id,
                compensation_plan_version_id=plan_id,
                key=key,
                name=name,
                status=status,
                human_share_min_basis_points=human_min,
                human_share_max_basis_points=human_max,
                expected_company_share_min_basis_points=company_min,
                expected_company_share_max_basis_points=company_max,
                ai_authority_level=authority,
                activation_requirements=requirements,
            )
        )


def activate_compensation_plan(
    db: Session,
    principal: Principal,
    plan_id: UUID,
    payload: CompensationPlanActivation,
) -> CompensationPlanRead | None:
    plan = scoped_plan(db, principal.organization_id, plan_id)
    if plan is None:
        return None
    if plan.status != "draft":
        raise ValueError("Only a draft compensation plan can be activated.")
    now = datetime.now(UTC)
    active_plans = db.scalars(
        select(CompensationPlanVersion).where(
            CompensationPlanVersion.organization_id == principal.organization_id,
            CompensationPlanVersion.status == "active",
        )
    ).all()
    retired_plan_ids: list[str] = []
    for active_plan in active_plans:
        active_plan.status = "retired"
        active_plan.effective_end_at = now
        retired_plan_ids.append(str(active_plan.id))
    plan.status = "active"
    plan.effective_start_at = now
    plan.approved_by_user_id = principal.user_id
    plan.approved_at = now
    add_audit(
        db,
        principal,
        action="operating_model.compensation_plan_activate",
        entity_type="compensation_plan_version",
        entity_id=plan.id,
        previous={"status": "draft", "retired_plan_ids": retired_plan_ids},
        new={"status": "active", "effective_start_at": now.isoformat()},
        reason=payload.reason,
    )
    db.commit()
    return compensation_plan_read(db, plan)


def compensation_plan_read(db: Session, plan: CompensationPlanVersion) -> CompensationPlanRead:
    users = user_map(db, plan.organization_id)
    roles = db.scalars(
        select(CompensationPlanRole)
        .where(CompensationPlanRole.compensation_plan_version_id == plan.id)
        .order_by(CompensationPlanRole.created_at)
    ).all()
    modes = db.scalars(
        select(DispositionOperatingMode)
        .where(DispositionOperatingMode.compensation_plan_version_id == plan.id)
        .order_by(DispositionOperatingMode.created_at)
    ).all()
    return CompensationPlanRead(
        id=plan.id,
        name=plan.name,
        version_number=plan.version_number,
        status=plan.status,
        acquisition_reserve_cents=plan.acquisition_reserve_cents,
        target_company_margin_basis_points=plan.target_company_margin_basis_points,
        effective_start_at=plan.effective_start_at,
        effective_end_at=plan.effective_end_at,
        created_by_user_id=plan.created_by_user_id,
        created_by_name=user_name(users, plan.created_by_user_id) or "Unknown user",
        approved_by_user_id=plan.approved_by_user_id,
        approved_by_name=user_name(users, plan.approved_by_user_id),
        approved_at=plan.approved_at,
        notes=plan.notes,
        roles=[
            CompensationPlanRoleRead(
                id=role.id,
                role_key=role.role_key,
                basis_points=role.basis_points,
                cap_cents=role.cap_cents,
                notes=role.notes,
            )
            for role in roles
        ],
        disposition_modes=[disposition_mode_read(mode) for mode in modes],
    )


def disposition_mode_read(mode: DispositionOperatingMode) -> DispositionOperatingModeRead:
    return DispositionOperatingModeRead(
        id=mode.id,
        key=mode.key,
        name=mode.name,
        status=mode.status,
        human_share_min_basis_points=mode.human_share_min_basis_points,
        human_share_max_basis_points=mode.human_share_max_basis_points,
        expected_company_share_min_basis_points=mode.expected_company_share_min_basis_points,
        expected_company_share_max_basis_points=mode.expected_company_share_max_basis_points,
        ai_authority_level=mode.ai_authority_level,
        activation_requirements=mode.activation_requirements,
    )


def create_role_credit(
    db: Session,
    principal: Principal,
    payload: RoleCreditCreate,
) -> RoleCreditRead:
    plan = scoped_plan(db, principal.organization_id, payload.compensation_plan_version_id)
    if plan is None or plan.status != "active":
        raise ValueError("Role credits require the active compensation plan.")
    plan_role = db.scalar(
        select(CompensationPlanRole).where(
            CompensationPlanRole.organization_id == principal.organization_id,
            CompensationPlanRole.compensation_plan_version_id == plan.id,
            CompensationPlanRole.role_key == payload.role_key,
        )
    )
    if plan_role is None:
        raise ValueError("The selected role is not part of this compensation plan.")
    lead = db.scalar(
        select(Lead).where(
            Lead.organization_id == principal.organization_id,
            Lead.id == payload.lead_id,
            Lead.archived_at.is_(None),
        )
    )
    if lead is None:
        raise ValueError("Select an active Stonegate lead.")
    user = active_user(db, principal.organization_id, payload.user_id)
    if user is None:
        raise ValueError("Role credit requires an active workspace user.")
    duplicate = db.scalar(
        select(RoleCredit).where(
            RoleCredit.organization_id == principal.organization_id,
            RoleCredit.lead_id == lead.id,
            RoleCredit.user_id == user.id,
            RoleCredit.role_key == payload.role_key,
            RoleCredit.status.in_(("proposed", "approved", "earned", "payable", "paid")),
        )
    )
    if duplicate is not None:
        raise ValueError("This user already has active credit for the selected role and lead.")
    active_credit = int(
        db.scalar(
            select(func.coalesce(func.sum(RoleCredit.credit_basis_points), 0)).where(
                RoleCredit.organization_id == principal.organization_id,
                RoleCredit.lead_id == lead.id,
                RoleCredit.role_key == payload.role_key,
                RoleCredit.status.in_(("proposed", "approved", "earned", "payable", "paid")),
            )
        )
        or 0
    )
    if active_credit + payload.credit_basis_points > 10000:
        raise ValueError("Active role-credit shares cannot exceed 100% for one lead and role.")
    deal = latest_deal(db, principal.organization_id, lead.id)
    transaction = latest_transaction(db, principal.organization_id, lead.id)
    credit = RoleCredit(
        organization_id=principal.organization_id,
        compensation_plan_version_id=plan.id,
        lead_id=lead.id,
        deal_id=deal.id if deal else None,
        transaction_id=transaction.id if transaction else None,
        user_id=user.id,
        role_key=payload.role_key,
        credit_basis_points=payload.credit_basis_points,
        status="proposed",
        assigned_by_user_id=principal.user_id,
        approved_by_user_id=None,
        approved_at=None,
        notes=clean_text(payload.notes),
    )
    db.add(credit)
    db.flush()
    add_audit(
        db,
        principal,
        action="operating_model.role_credit_create",
        entity_type="role_credit",
        entity_id=credit.id,
        previous=None,
        new={
            "plan_id": str(plan.id),
            "lead_id": str(lead.id),
            "user_id": str(user.id),
            "role_key": credit.role_key,
            "credit_basis_points": credit.credit_basis_points,
            "status": credit.status,
        },
        reason="Role contribution proposed before compensation",
    )
    db.commit()
    return role_credit_read(db, credit)


def decide_role_credit(
    db: Session,
    principal: Principal,
    credit_id: UUID,
    payload: RoleCreditDecision,
) -> RoleCreditRead | None:
    credit = db.scalar(
        select(RoleCredit).where(
            RoleCredit.organization_id == principal.organization_id,
            RoleCredit.id == credit_id,
        )
    )
    if credit is None:
        return None
    if credit.status != "proposed":
        raise ValueError("Only a proposed role credit can be decided.")
    previous: dict[str, object] = {"status": credit.status}
    if payload.decision == "approve":
        approved_credits = int(
            db.scalar(
                select(func.coalesce(func.sum(RoleCredit.credit_basis_points), 0)).where(
                    RoleCredit.organization_id == principal.organization_id,
                    RoleCredit.lead_id == credit.lead_id,
                    RoleCredit.role_key == credit.role_key,
                    RoleCredit.id != credit.id,
                    RoleCredit.status.in_(("approved", "earned", "payable", "paid")),
                )
            )
            or 0
        )
        if approved_credits + credit.credit_basis_points > 10000:
            raise ValueError("Approved role-credit shares cannot exceed 100%.")
        credit.status = "approved"
        credit.approved_by_user_id = principal.user_id
        credit.approved_at = datetime.now(UTC)
    else:
        credit.status = "rejected"
        credit.approved_by_user_id = principal.user_id
        credit.approved_at = datetime.now(UTC)
    credit.notes = append_note(credit.notes, payload.reason)
    add_audit(
        db,
        principal,
        action="operating_model.role_credit_decide",
        entity_type="role_credit",
        entity_id=credit.id,
        previous=previous,
        new={"status": credit.status, "decision": payload.decision},
        reason=payload.reason,
    )
    db.commit()
    return role_credit_read(db, credit)


def role_credit_read(db: Session, credit: RoleCredit) -> RoleCreditRead:
    users = user_map(db, credit.organization_id)
    plan = db.get(CompensationPlanVersion, credit.compensation_plan_version_id)
    lead = db.get(Lead, credit.lead_id)
    contact = db.get(Contact, lead.contact_id) if lead else None
    return RoleCreditRead(
        id=credit.id,
        compensation_plan_version_id=credit.compensation_plan_version_id,
        plan_label=(f"{plan.name} v{plan.version_number}" if plan else "Unknown compensation plan"),
        lead_id=credit.lead_id,
        seller_name=contact.legal_name if contact else "Unknown seller",
        user_id=credit.user_id,
        user_name=user_name(users, credit.user_id) or "Unknown user",
        role_key=credit.role_key,
        credit_basis_points=credit.credit_basis_points,
        status=credit.status,
        assigned_by_user_id=credit.assigned_by_user_id,
        assigned_by_name=user_name(users, credit.assigned_by_user_id) or "Unknown user",
        approved_by_user_id=credit.approved_by_user_id,
        approved_by_name=user_name(users, credit.approved_by_user_id),
        approved_at=credit.approved_at,
        notes=credit.notes,
        created_at=credit.created_at,
    )


def create_market_launch_checklist(
    db: Session,
    principal: Principal,
    market_id: UUID,
    payload: MarketLaunchChecklistCreate,
) -> MarketLaunchChecklistRead | None:
    market = db.scalar(
        select(Market).where(
            Market.organization_id == principal.organization_id,
            Market.id == market_id,
        )
    )
    if market is None:
        return None
    owner = active_user(db, principal.organization_id, payload.owner_user_id)
    if owner is None:
        raise ValueError("Launch checklist owner must be an active workspace user.")
    version_number = (
        int(
            db.scalar(
                select(func.coalesce(func.max(MarketLaunchChecklist.version_number), 0)).where(
                    MarketLaunchChecklist.market_id == market.id
                )
            )
            or 0
        )
        + 1
    )
    checklist = MarketLaunchChecklist(
        organization_id=principal.organization_id,
        market_id=market.id,
        version_number=version_number,
        status="draft",
        owner_user_id=owner.id,
        approved_by_user_id=None,
        approved_at=None,
        notes=clean_text(payload.notes),
    )
    db.add(checklist)
    db.flush()
    for sort_order, (item_key, category, label) in enumerate(LAUNCH_ITEM_SPECS, start=1):
        db.add(
            MarketLaunchChecklistItem(
                organization_id=principal.organization_id,
                market_launch_checklist_id=checklist.id,
                item_key=item_key,
                category=category,
                label=label,
                status="pending",
                responsible_user_id=owner.id,
                evidence_notes=None,
                completed_by_user_id=None,
                completed_at=None,
                sort_order=sort_order,
            )
        )
    add_audit(
        db,
        principal,
        action="operating_model.market_launch_checklist_create",
        entity_type="market_launch_checklist",
        entity_id=checklist.id,
        previous=None,
        new={
            "market_id": str(market.id),
            "version_number": checklist.version_number,
            "owner_user_id": str(owner.id),
            "status": checklist.status,
        },
        reason="Market launch checklist created",
    )
    db.commit()
    return launch_checklist_read(db, checklist)


def update_market_launch_item(
    db: Session,
    principal: Principal,
    item_id: UUID,
    payload: MarketLaunchChecklistItemUpdate,
) -> MarketLaunchChecklistItemRead | None:
    item = db.scalar(
        select(MarketLaunchChecklistItem).where(
            MarketLaunchChecklistItem.organization_id == principal.organization_id,
            MarketLaunchChecklistItem.id == item_id,
        )
    )
    if item is None:
        return None
    checklist = db.get(MarketLaunchChecklist, item.market_launch_checklist_id)
    if checklist is None or checklist.status == "approved":
        raise ValueError("Approved launch checklists are immutable.")
    responsible = None
    if payload.responsible_user_id:
        responsible = active_user(db, principal.organization_id, payload.responsible_user_id)
        if responsible is None:
            raise ValueError("Checklist responsibility requires an active workspace user.")
    previous: dict[str, object] = {
        "status": item.status,
        "responsible_user_id": (
            str(item.responsible_user_id) if item.responsible_user_id else None
        ),
        "evidence_notes": item.evidence_notes,
    }
    item.status = payload.status
    item.responsible_user_id = responsible.id if responsible else item.responsible_user_id
    item.evidence_notes = clean_text(payload.evidence_notes)
    if payload.status == "complete":
        item.completed_by_user_id = principal.user_id
        item.completed_at = datetime.now(UTC)
    else:
        item.completed_by_user_id = None
        item.completed_at = None
    db.flush()
    recalculate_checklist_status(db, checklist)
    add_audit(
        db,
        principal,
        action="operating_model.market_launch_item_update",
        entity_type="market_launch_checklist_item",
        entity_id=item.id,
        previous=previous,
        new={
            "status": item.status,
            "responsible_user_id": (
                str(item.responsible_user_id) if item.responsible_user_id else None
            ),
            "evidence_notes": item.evidence_notes,
        },
        reason="Market launch evidence updated",
    )
    db.commit()
    return launch_item_read(db, item)


def approve_market_launch_checklist(
    db: Session,
    principal: Principal,
    checklist_id: UUID,
    payload: MarketLaunchChecklistApproval,
) -> MarketLaunchChecklistRead | None:
    checklist = db.scalar(
        select(MarketLaunchChecklist).where(
            MarketLaunchChecklist.organization_id == principal.organization_id,
            MarketLaunchChecklist.id == checklist_id,
        )
    )
    if checklist is None:
        return None
    if checklist.status == "approved":
        raise ValueError("This market launch checklist is already approved.")
    incomplete_count = int(
        db.scalar(
            select(func.count())
            .select_from(MarketLaunchChecklistItem)
            .where(
                MarketLaunchChecklistItem.market_launch_checklist_id == checklist.id,
                MarketLaunchChecklistItem.status != "complete",
            )
        )
        or 0
    )
    if incomplete_count:
        raise ValueError("Complete every market launch item before approval.")
    previous: dict[str, object] = {"status": checklist.status}
    checklist.status = "approved"
    checklist.approved_by_user_id = principal.user_id
    checklist.approved_at = datetime.now(UTC)
    checklist.notes = append_note(checklist.notes, payload.reason)
    add_audit(
        db,
        principal,
        action="operating_model.market_launch_checklist_approve",
        entity_type="market_launch_checklist",
        entity_id=checklist.id,
        previous=previous,
        new={"status": checklist.status, "approved_at": checklist.approved_at.isoformat()},
        reason=payload.reason,
    )
    db.commit()
    return launch_checklist_read(db, checklist)


def recalculate_checklist_status(db: Session, checklist: MarketLaunchChecklist) -> None:
    statuses = list(
        db.scalars(
            select(MarketLaunchChecklistItem.status).where(
                MarketLaunchChecklistItem.market_launch_checklist_id == checklist.id
            )
        )
    )
    if statuses and all(status == "complete" for status in statuses):
        checklist.status = "ready"
    elif "blocked" in statuses:
        checklist.status = "blocked"
    elif any(status in {"in_progress", "complete"} for status in statuses):
        checklist.status = "in_progress"
    else:
        checklist.status = "draft"


def launch_checklist_read(
    db: Session,
    checklist: MarketLaunchChecklist,
) -> MarketLaunchChecklistRead:
    users = user_map(db, checklist.organization_id)
    market = db.get(Market, checklist.market_id)
    items = db.scalars(
        select(MarketLaunchChecklistItem)
        .where(MarketLaunchChecklistItem.market_launch_checklist_id == checklist.id)
        .order_by(MarketLaunchChecklistItem.sort_order)
    ).all()
    return MarketLaunchChecklistRead(
        id=checklist.id,
        market_id=checklist.market_id,
        market_name=market.name if market else "Unknown market",
        version_number=checklist.version_number,
        status=checklist.status,
        owner_user_id=checklist.owner_user_id,
        owner_name=user_name(users, checklist.owner_user_id) or "Unknown user",
        approved_by_user_id=checklist.approved_by_user_id,
        approved_by_name=user_name(users, checklist.approved_by_user_id),
        approved_at=checklist.approved_at,
        notes=checklist.notes,
        completed_items=sum(item.status == "complete" for item in items),
        total_items=len(items),
        items=[launch_item_read(db, item, users=users) for item in items],
    )


def launch_item_read(
    db: Session,
    item: MarketLaunchChecklistItem,
    *,
    users: dict[UUID, User] | None = None,
) -> MarketLaunchChecklistItemRead:
    scoped_users = users or user_map(db, item.organization_id)
    return MarketLaunchChecklistItemRead(
        id=item.id,
        item_key=item.item_key,
        category=item.category,
        label=item.label,
        status=item.status,
        responsible_user_id=item.responsible_user_id,
        responsible_user_name=user_name(scoped_users, item.responsible_user_id),
        evidence_notes=item.evidence_notes,
        completed_by_user_id=item.completed_by_user_id,
        completed_by_name=user_name(scoped_users, item.completed_by_user_id),
        completed_at=item.completed_at,
        sort_order=item.sort_order,
    )


def scoped_plan(
    db: Session,
    organization_id: UUID,
    plan_id: UUID,
) -> CompensationPlanVersion | None:
    return db.scalar(
        select(CompensationPlanVersion).where(
            CompensationPlanVersion.organization_id == organization_id,
            CompensationPlanVersion.id == plan_id,
        )
    )


def active_user(db: Session, organization_id: UUID, user_id: UUID) -> User | None:
    return db.scalar(
        select(User).where(
            User.organization_id == organization_id,
            User.id == user_id,
            User.is_active.is_(True),
        )
    )


def user_map(db: Session, organization_id: UUID) -> dict[UUID, User]:
    return {
        user.id: user
        for user in db.scalars(select(User).where(User.organization_id == organization_id))
    }


def user_name(users: dict[UUID, User], user_id: UUID | None) -> str | None:
    user = users.get(user_id) if user_id else None
    return user.display_name if user else None


def latest_deal(db: Session, organization_id: UUID, lead_id: UUID) -> Deal | None:
    return db.scalar(
        select(Deal)
        .where(Deal.organization_id == organization_id, Deal.lead_id == lead_id)
        .order_by(Deal.created_at.desc())
    )


def latest_transaction(db: Session, organization_id: UUID, lead_id: UUID) -> Transaction | None:
    return db.scalar(
        select(Transaction)
        .where(Transaction.organization_id == organization_id, Transaction.lead_id == lead_id)
        .order_by(Transaction.created_at.desc())
    )


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def append_note(existing: str | None, note: str) -> str:
    cleaned = note.strip()
    return f"{existing}\n\n{cleaned}" if existing else cleaned


def add_audit(
    db: Session,
    principal: Principal,
    *,
    action: str,
    entity_type: str,
    entity_id: UUID,
    previous: dict[str, object] | None,
    new: dict[str, object],
    reason: str,
) -> None:
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            previous_value=previous,
            new_value=new,
            reason=reason,
        )
    )
