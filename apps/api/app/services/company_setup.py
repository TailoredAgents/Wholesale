from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.models.foundation import (
    AuditEvent,
    BusinessCounterparty,
    Buyer,
    CloserDispatchProfile,
    CompensationPlanVersion,
    LeadQualificationScriptVersion,
    Market,
    MarketLaunchChecklist,
    OperatingSeat,
    ProspectingScriptVersion,
    Role,
    RoleAssignment,
    StaffRoleAcceptance,
    Team,
    Territory,
    User,
)
from app.schemas.operating_model import (
    BusinessCounterpartyCreate,
    BusinessCounterpartyDecision,
    BusinessCounterpartyRead,
    CompanySetupCheckRead,
    CompanySetupInstallRead,
    CompanySetupRead,
    MyRoleSetupRead,
    OperatingSeatRead,
    OperatingSeatUpdate,
    StaffRoleAcceptanceAssign,
    StaffRoleAcceptanceDecision,
    StaffRoleAcceptanceRead,
    StaffRoleAcceptanceSubmit,
)

OWNER_ROLE_KEYS = {"owner", "founder_operator", "ceo"}
MANUAL_BY_ROLE = {
    "owner": "owner",
    "founder_operator": "owner",
    "ceo": "owner",
    "operations_assistant": "operations_assistant",
    "acquisition_manager": "lead_manager",
    "acquisition_rep": "closer",
    "prospecting_caller": "va_caller",
    "disposition_manager": "dispositions",
    "disposition_rep": "dispositions",
    "transaction_coordinator": "transaction_coordinator",
    "finance_accounting": "finance",
    "marketing_manager": "marketing",
}
STANDARD_SEATS = (
    ("owner_management", "Owner / CEO management", "owner", "covered"),
    ("lead_management", "Lead management", "acquisition_manager", "hiring"),
    ("acquisitions_closer", "Acquisitions closer", "acquisition_rep", "covered"),
    ("va_caller_1", "VA caller 1", "prospecting_caller", "hiring"),
    ("va_caller_2", "VA caller 2", "prospecting_caller", "hiring"),
    ("dispositions", "Dispositions", "disposition_manager", "covered"),
    (
        "transaction_coordination",
        "Transaction coordination",
        "transaction_coordinator",
        "planned",
    ),
    ("finance", "Finance and accounting", "finance_accounting", "covered"),
    ("marketing", "Marketing", "marketing_manager", "covered"),
)


def install_company_setup(
    db: Session,
    principal: Principal,
) -> CompanySetupInstallRead:
    existing_keys = set(
        db.scalars(
            select(OperatingSeat.seat_key).where(
                OperatingSeat.organization_id == principal.organization_id
            )
        )
    )
    created = 0
    for seat_key, label, role_key, default_status in STANDARD_SEATS:
        if seat_key in existing_keys:
            continue
        owner_covered = default_status == "covered"
        db.add(
            OperatingSeat(
                organization_id=principal.organization_id,
                seat_key=seat_key,
                label=label,
                role_key=role_key,
                status=default_status,
                primary_user_id=principal.user_id if owner_covered else None,
                backup_user_id=None,
                notes="Initially covered by the owner." if owner_covered else None,
                updated_by_user_id=principal.user_id,
            )
        )
        created += 1
    db.flush()
    _add_audit(
        db,
        principal,
        action="company_setup.installed",
        entity_type="organization",
        entity_id=principal.organization_id,
        new={"created_seat_count": created},
        reason="Installed Stonegate standard operating seats.",
    )
    db.commit()
    return CompanySetupInstallRead(
        created_seat_count=created,
        setup=get_company_setup(db, principal),
    )


def get_company_setup(db: Session, principal: Principal) -> CompanySetupRead:
    organization_id = principal.organization_id
    users = _user_map(db, organization_id)
    markets = _market_map(db, organization_id)
    seats = list(
        db.scalars(
            select(OperatingSeat)
            .where(OperatingSeat.organization_id == organization_id)
            .order_by(OperatingSeat.created_at, OperatingSeat.label)
        )
    )
    counterparties = list(
        db.scalars(
            select(BusinessCounterparty)
            .where(BusinessCounterparty.organization_id == organization_id)
            .order_by(BusinessCounterparty.created_at.desc())
        )
    )
    acceptances = list(
        db.scalars(
            select(StaffRoleAcceptance)
            .where(StaffRoleAcceptance.organization_id == organization_id)
            .order_by(StaffRoleAcceptance.created_at.desc())
        )
    )
    checks = _setup_checks(db, organization_id, seats, counterparties, acceptances)
    return CompanySetupRead(
        seats=[_seat_read(seat, users) for seat in seats],
        counterparties=[
            _counterparty_read(counterparty, users, markets) for counterparty in counterparties
        ],
        role_acceptances=[_acceptance_read(acceptance, users) for acceptance in acceptances],
        checks=checks,
        completed_check_count=sum(check.status == "complete" for check in checks),
        total_check_count=len(checks),
    )


def update_operating_seat(
    db: Session,
    principal: Principal,
    seat_id: UUID,
    payload: OperatingSeatUpdate,
) -> OperatingSeatRead | None:
    seat = db.scalar(
        select(OperatingSeat).where(
            OperatingSeat.organization_id == principal.organization_id,
            OperatingSeat.id == seat_id,
        )
    )
    if seat is None:
        return None
    previous = _seat_value(seat)
    for user_id in (payload.primary_user_id, payload.backup_user_id):
        if user_id is None:
            continue
        user = _active_user(db, principal.organization_id, user_id)
        if user is None:
            raise ValueError("Seat coverage requires an active workspace user.")
        role_keys = _user_role_keys(db, principal.organization_id, user.id)
        if not role_keys.intersection(OWNER_ROLE_KEYS | {seat.role_key}):
            raise ValueError(
                f"{user.display_name} does not have the {seat.role_key} role required "
                "for this seat."
            )
    seat.status = payload.status
    seat.primary_user_id = payload.primary_user_id
    seat.backup_user_id = payload.backup_user_id
    seat.notes = _clean(payload.notes)
    seat.updated_by_user_id = principal.user_id
    _add_audit(
        db,
        principal,
        action="operating_seat.updated",
        entity_type="operating_seat",
        entity_id=seat.id,
        previous=previous,
        new=_seat_value(seat),
        reason="Updated operating seat coverage.",
    )
    db.commit()
    db.refresh(seat)
    return _seat_read(seat, _user_map(db, principal.organization_id))


def create_counterparty(
    db: Session,
    principal: Principal,
    payload: BusinessCounterpartyCreate,
) -> BusinessCounterpartyRead:
    if payload.market_id is not None and not _market_exists(
        db, principal.organization_id, payload.market_id
    ):
        raise ValueError("Market not found.")
    counterparty = BusinessCounterparty(
        organization_id=principal.organization_id,
        market_id=payload.market_id,
        counterparty_type=payload.counterparty_type,
        name=payload.name.strip(),
        company_name=_clean(payload.company_name),
        email=_clean(payload.email),
        phone=_clean(payload.phone),
        status="pending",
        verified_by_user_id=None,
        verified_at=None,
        notes=_clean(payload.notes),
    )
    db.add(counterparty)
    db.flush()
    _add_audit(
        db,
        principal,
        action="business_counterparty.created",
        entity_type="business_counterparty",
        entity_id=counterparty.id,
        new={"type": counterparty.counterparty_type, "status": counterparty.status},
        reason="Added company counterparty for verification.",
    )
    db.commit()
    db.refresh(counterparty)
    return _counterparty_read(
        counterparty,
        _user_map(db, principal.organization_id),
        _market_map(db, principal.organization_id),
    )


def decide_counterparty(
    db: Session,
    principal: Principal,
    counterparty_id: UUID,
    payload: BusinessCounterpartyDecision,
) -> BusinessCounterpartyRead | None:
    counterparty = db.scalar(
        select(BusinessCounterparty).where(
            BusinessCounterparty.organization_id == principal.organization_id,
            BusinessCounterparty.id == counterparty_id,
        )
    )
    if counterparty is None:
        return None
    previous_status = counterparty.status
    if payload.decision == "verify":
        counterparty.status = "verified"
        counterparty.verified_by_user_id = principal.user_id
        counterparty.verified_at = datetime.now(UTC)
    else:
        counterparty.status = "inactive"
        counterparty.verified_by_user_id = None
        counterparty.verified_at = None
    counterparty.notes = _append_note(counterparty.notes, payload.reason)
    _add_audit(
        db,
        principal,
        action=f"business_counterparty.{payload.decision}",
        entity_type="business_counterparty",
        entity_id=counterparty.id,
        previous={"status": previous_status},
        new={"status": counterparty.status},
        reason=payload.reason,
    )
    db.commit()
    db.refresh(counterparty)
    return _counterparty_read(
        counterparty,
        _user_map(db, principal.organization_id),
        _market_map(db, principal.organization_id),
    )


def assign_role_acceptance(
    db: Session,
    principal: Principal,
    payload: StaffRoleAcceptanceAssign,
) -> StaffRoleAcceptanceRead:
    user = _active_user(db, principal.organization_id, payload.user_id)
    if user is None:
        raise ValueError("Role acceptance requires an active workspace user.")
    role_keys = _user_role_keys(db, principal.organization_id, user.id)
    if payload.role_key not in role_keys:
        raise ValueError("The selected user does not have the assigned role.")
    expected_manual = MANUAL_BY_ROLE.get(payload.role_key)
    if expected_manual is None or payload.manual_key != expected_manual:
        raise ValueError("The selected manual does not match the assigned role.")
    acceptance = StaffRoleAcceptance(
        organization_id=principal.organization_id,
        user_id=user.id,
        role_key=payload.role_key,
        manual_key=payload.manual_key.strip(),
        manual_version=payload.manual_version.strip(),
        status="assigned",
        assigned_by_user_id=principal.user_id,
        workspace_test_evidence=None,
        employee_notes=None,
        accepted_at=None,
        approved_by_user_id=None,
        manager_notes=None,
        approved_at=None,
    )
    db.add(acceptance)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("This manual version is already assigned to that user.") from exc
    _add_audit(
        db,
        principal,
        action="staff_role_acceptance.assigned",
        entity_type="staff_role_acceptance",
        entity_id=acceptance.id,
        new={
            "user_id": str(user.id),
            "role_key": acceptance.role_key,
            "manual_key": acceptance.manual_key,
            "manual_version": acceptance.manual_version,
        },
        reason="Assigned role manual and workspace acceptance.",
    )
    db.commit()
    db.refresh(acceptance)
    return _acceptance_read(acceptance, _user_map(db, principal.organization_id))


def get_my_role_setup(db: Session, principal: Principal) -> MyRoleSetupRead:
    user = db.get(User, principal.user_id)
    if user is None or user.organization_id != principal.organization_id:
        raise ValueError("Workspace user not found.")
    acceptances = list(
        db.scalars(
            select(StaffRoleAcceptance)
            .where(
                StaffRoleAcceptance.organization_id == principal.organization_id,
                StaffRoleAcceptance.user_id == principal.user_id,
            )
            .order_by(StaffRoleAcceptance.created_at.desc())
        )
    )
    users = _user_map(db, principal.organization_id)
    return MyRoleSetupRead(
        user_id=user.id,
        user_name=user.display_name,
        role_keys=sorted(_user_role_keys(db, principal.organization_id, user.id)),
        acceptances=[_acceptance_read(item, users) for item in acceptances],
    )


def submit_role_acceptance(
    db: Session,
    principal: Principal,
    acceptance_id: UUID,
    payload: StaffRoleAcceptanceSubmit,
) -> StaffRoleAcceptanceRead | None:
    acceptance = db.scalar(
        select(StaffRoleAcceptance).where(
            StaffRoleAcceptance.organization_id == principal.organization_id,
            StaffRoleAcceptance.id == acceptance_id,
            StaffRoleAcceptance.user_id == principal.user_id,
        )
    )
    if acceptance is None:
        return None
    if acceptance.status == "approved":
        raise ValueError("An approved role acceptance cannot be resubmitted.")
    previous_status = acceptance.status
    acceptance.status = "submitted"
    acceptance.workspace_test_evidence = payload.workspace_test_evidence.strip()
    acceptance.employee_notes = _clean(payload.employee_notes)
    acceptance.accepted_at = datetime.now(UTC)
    acceptance.approved_by_user_id = None
    acceptance.approved_at = None
    _add_audit(
        db,
        principal,
        action="staff_role_acceptance.submitted",
        entity_type="staff_role_acceptance",
        entity_id=acceptance.id,
        previous={"status": previous_status},
        new={"status": acceptance.status},
        reason="Employee completed the role workspace test.",
    )
    db.commit()
    db.refresh(acceptance)
    return _acceptance_read(acceptance, _user_map(db, principal.organization_id))


def decide_role_acceptance(
    db: Session,
    principal: Principal,
    acceptance_id: UUID,
    payload: StaffRoleAcceptanceDecision,
) -> StaffRoleAcceptanceRead | None:
    acceptance = db.scalar(
        select(StaffRoleAcceptance).where(
            StaffRoleAcceptance.organization_id == principal.organization_id,
            StaffRoleAcceptance.id == acceptance_id,
        )
    )
    if acceptance is None:
        return None
    if payload.decision == "approve" and acceptance.status != "submitted":
        raise ValueError("Only a submitted role acceptance can be approved.")
    previous_status = acceptance.status
    status_by_decision = {
        "approve": "approved",
        "needs_changes": "needs_changes",
        "revoke": "revoked",
    }
    acceptance.status = status_by_decision[payload.decision]
    acceptance.manager_notes = payload.manager_notes.strip()
    acceptance.approved_by_user_id = principal.user_id
    acceptance.approved_at = datetime.now(UTC) if payload.decision == "approve" else None
    _add_audit(
        db,
        principal,
        action=f"staff_role_acceptance.{payload.decision}",
        entity_type="staff_role_acceptance",
        entity_id=acceptance.id,
        previous={"status": previous_status},
        new={"status": acceptance.status},
        reason=payload.manager_notes,
    )
    db.commit()
    db.refresh(acceptance)
    return _acceptance_read(acceptance, _user_map(db, principal.organization_id))


def _setup_checks(
    db: Session,
    organization_id: UUID,
    seats: list[OperatingSeat],
    counterparties: list[BusinessCounterparty],
    acceptances: list[StaffRoleAcceptance],
) -> list[CompanySetupCheckRead]:
    covered_seats = [seat for seat in seats if seat.status == "covered"]
    uncovered_seats = [seat for seat in seats if seat.status in {"planned", "hiring"}]
    active_plan = _count(
        db,
        CompensationPlanVersion,
        CompensationPlanVersion.organization_id == organization_id,
        CompensationPlanVersion.status == "active",
    )
    active_georgia_market = _count(
        db,
        Market,
        Market.organization_id == organization_id,
        Market.state_code == "GA",
        Market.status == "active",
    )
    approved_launch = _count(
        db,
        MarketLaunchChecklist,
        MarketLaunchChecklist.organization_id == organization_id,
        MarketLaunchChecklist.status == "approved",
    )
    active_closer = _count(
        db,
        CloserDispatchProfile,
        CloserDispatchProfile.organization_id == organization_id,
        CloserDispatchProfile.is_active.is_(True),
    )
    active_team = _count(
        db,
        Team,
        Team.organization_id == organization_id,
        Team.is_active.is_(True),
    )
    routed_territory = _count(
        db,
        Territory,
        Territory.organization_id == organization_id,
        Territory.status == "active",
        Territory.assigned_team_id.is_not(None),
    )
    scripts_ready = (
        _count(
            db,
            ProspectingScriptVersion,
            ProspectingScriptVersion.organization_id == organization_id,
            ProspectingScriptVersion.status == "approved",
        )
        > 0
        and _count(
            db,
            LeadQualificationScriptVersion,
            LeadQualificationScriptVersion.organization_id == organization_id,
            LeadQualificationScriptVersion.status == "approved",
        )
        > 0
    )
    verified_closing = any(
        item.status == "verified"
        and item.counterparty_type in {"closing_attorney", "title_company"}
        for item in counterparties
    )
    approved_user_ids = {item.user_id for item in acceptances if item.status == "approved"}
    covered_non_owner_ids = {
        seat.primary_user_id
        for seat in covered_seats
        if seat.primary_user_id is not None
        and not _user_role_keys(
            db,
            organization_id,
            seat.primary_user_id,
        ).intersection(OWNER_ROLE_KEYS)
    }
    role_acceptance_ready = covered_non_owner_ids.issubset(approved_user_ids)
    buyers_ready = _count(
        db,
        Buyer,
        Buyer.organization_id == organization_id,
        Buyer.status == "active",
        Buyer.proof_of_funds_status.in_({"received", "verified"}),
    )
    checks = [
        _check(
            "operating_seats",
            "Operating seats",
            bool(seats),
            f"{len(covered_seats)} covered; {len(uncovered_seats)} planned or hiring.",
        ),
        _check(
            "compensation",
            "Compensation plan",
            active_plan > 0,
            "An active commission plan is in force."
            if active_plan
            else "Activate the approved commission plan.",
        ),
        _check(
            "georgia_market",
            "Georgia market",
            active_georgia_market > 0,
            "Georgia is active." if active_georgia_market else "Activate the Georgia market.",
        ),
        _check(
            "market_launch",
            "Market launch approval",
            approved_launch > 0,
            "A market launch checklist is approved."
            if approved_launch
            else "Complete and approve the market launch checklist.",
        ),
        _check(
            "team_routing",
            "Team and territory routing",
            active_team > 0 and routed_territory > 0,
            "An active team owns at least one active territory."
            if active_team and routed_territory
            else "Assign an active Georgia territory to an operating team.",
        ),
        _check(
            "role_acceptance",
            "Staff role acceptance",
            role_acceptance_ready,
            "All non-owner seat holders are approved."
            if role_acceptance_ready
            else "Assign manuals and approve workspace tests as staff are hired.",
        ),
        _check(
            "closing_partner",
            "Closing partner",
            verified_closing,
            "A closing attorney or title company is verified."
            if verified_closing
            else "Add and verify a Georgia closing partner.",
        ),
        _check(
            "scripts",
            "Operating scripts",
            scripts_ready,
            "Prospecting and qualification scripts are approved."
            if scripts_ready
            else "Approve the current prospecting and qualification scripts.",
        ),
        _check(
            "field_capacity",
            "Closer capacity",
            active_closer > 0,
            "Field closer hours and capacity are configured."
            if active_closer
            else "Configure at least one active closer schedule.",
        ),
        _check(
            "buyer_coverage",
            "Buyer coverage",
            buyers_ready > 0,
            f"{buyers_ready} active buyers have proof of funds."
            if buyers_ready
            else "Add active cash buyers and receive proof of funds.",
        ),
    ]
    if not seats:
        checks[0].status = "not_started"
        checks[0].detail = "Install Stonegate's standard operating seats."
    return checks


def _check(
    key: str,
    label: str,
    complete: bool,
    detail: str,
) -> CompanySetupCheckRead:
    return CompanySetupCheckRead(
        key=key,
        label=label,
        status="complete" if complete else "attention",
        detail=detail,
    )


def _seat_read(seat: OperatingSeat, users: dict[UUID, User]) -> OperatingSeatRead:
    return OperatingSeatRead(
        id=seat.id,
        seat_key=seat.seat_key,
        label=seat.label,
        role_key=seat.role_key,
        status=seat.status,
        primary_user_id=seat.primary_user_id,
        primary_user_name=_user_name(users, seat.primary_user_id),
        backup_user_id=seat.backup_user_id,
        backup_user_name=_user_name(users, seat.backup_user_id),
        notes=seat.notes,
    )


def _counterparty_read(
    counterparty: BusinessCounterparty,
    users: dict[UUID, User],
    markets: dict[UUID, Market],
) -> BusinessCounterpartyRead:
    market = markets.get(counterparty.market_id) if counterparty.market_id else None
    return BusinessCounterpartyRead(
        id=counterparty.id,
        market_id=counterparty.market_id,
        market_name=market.name if market else None,
        counterparty_type=counterparty.counterparty_type,
        name=counterparty.name,
        company_name=counterparty.company_name,
        email=counterparty.email,
        phone=counterparty.phone,
        status=counterparty.status,
        verified_by_user_id=counterparty.verified_by_user_id,
        verified_by_name=_user_name(users, counterparty.verified_by_user_id),
        verified_at=counterparty.verified_at,
        notes=counterparty.notes,
    )


def _acceptance_read(
    acceptance: StaffRoleAcceptance,
    users: dict[UUID, User],
) -> StaffRoleAcceptanceRead:
    return StaffRoleAcceptanceRead(
        id=acceptance.id,
        user_id=acceptance.user_id,
        user_name=_user_name(users, acceptance.user_id) or "Unknown user",
        role_key=acceptance.role_key,
        manual_key=acceptance.manual_key,
        manual_version=acceptance.manual_version,
        status=acceptance.status,
        assigned_by_user_id=acceptance.assigned_by_user_id,
        assigned_by_name=_user_name(users, acceptance.assigned_by_user_id) or "Unknown user",
        workspace_test_evidence=acceptance.workspace_test_evidence,
        employee_notes=acceptance.employee_notes,
        accepted_at=acceptance.accepted_at,
        approved_by_user_id=acceptance.approved_by_user_id,
        approved_by_name=_user_name(users, acceptance.approved_by_user_id),
        manager_notes=acceptance.manager_notes,
        approved_at=acceptance.approved_at,
    )


def _seat_value(seat: OperatingSeat) -> dict[str, object]:
    return {
        "status": seat.status,
        "primary_user_id": str(seat.primary_user_id) if seat.primary_user_id else None,
        "backup_user_id": str(seat.backup_user_id) if seat.backup_user_id else None,
        "notes": seat.notes,
    }


def _user_map(db: Session, organization_id: UUID) -> dict[UUID, User]:
    return {
        user.id: user
        for user in db.scalars(select(User).where(User.organization_id == organization_id))
    }


def _market_map(db: Session, organization_id: UUID) -> dict[UUID, Market]:
    return {
        market.id: market
        for market in db.scalars(select(Market).where(Market.organization_id == organization_id))
    }


def _user_name(users: dict[UUID, User], user_id: UUID | None) -> str | None:
    user = users.get(user_id) if user_id else None
    return user.display_name if user else None


def _active_user(
    db: Session,
    organization_id: UUID,
    user_id: UUID,
) -> User | None:
    return db.scalar(
        select(User).where(
            User.organization_id == organization_id,
            User.id == user_id,
            User.is_active.is_(True),
        )
    )


def _user_role_keys(
    db: Session,
    organization_id: UUID,
    user_id: UUID,
) -> set[str]:
    return set(
        db.scalars(
            select(Role.key)
            .join(RoleAssignment, RoleAssignment.role_id == Role.id)
            .where(
                RoleAssignment.organization_id == organization_id,
                RoleAssignment.user_id == user_id,
            )
        )
    )


def _market_exists(db: Session, organization_id: UUID, market_id: UUID) -> bool:
    return (
        db.scalar(
            select(Market.id).where(
                Market.organization_id == organization_id,
                Market.id == market_id,
            )
        )
        is not None
    )


def _count(db: Session, model: type[Any], *conditions: Any) -> int:
    return int(db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _append_note(existing: str | None, note: str) -> str:
    cleaned = note.strip()
    return f"{existing}\n\n{cleaned}" if existing else cleaned


def _add_audit(
    db: Session,
    principal: Principal,
    *,
    action: str,
    entity_type: str,
    entity_id: UUID,
    new: dict[str, object],
    reason: str,
    previous: dict[str, object] | None = None,
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
