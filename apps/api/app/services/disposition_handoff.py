from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.core.config import Settings
from app.domain.assets import ASSET_CLASSES, normalize_asset_class, property_identity_label
from app.domain.rbac import PermissionKeys
from app.models.foundation import (
    AuditEvent,
    CompensationPlanVersion,
    Deal,
    DispositionCase,
    DispositionOperatingMode,
    DispositionPackageVersion,
    Lead,
    OperatingSeat,
    Permission,
    Property,
    Role,
    RoleAssignment,
    RolePermission,
    StaffLeadAlert,
    Task,
    Team,
    TeamMembership,
    Transaction,
    User,
)
from app.services.communication_compliance import format_e164
from app.services.disposition_state import (
    ACTIVE_DISPOSITION_CASE_STATUSES,
    TERMINAL_DISPOSITION_CASE_STATUSES,
)
from app.services.lead_lifecycle import INACTIVE_LEAD_STAGES

PACKAGE_READY_ALERT_SOURCE_TYPE = "disposition_package_ready"
DISPOSITION_ROLE_KEYS = ("disposition_manager", "disposition_rep")
EXECUTIVE_FALLBACK_ROLE_KEYS = ("owner", "founder_operator", "ceo")
REQUIRED_DISPOSITION_OWNER_PERMISSION_KEYS = frozenset(
    {
        PermissionKeys.VIEW_DEALS,
        PermissionKeys.EDIT_DEALS,
        PermissionKeys.VIEW_BUYERS,
        PermissionKeys.EDIT_BUYERS,
    }
)
HANDOFF_RECOVERY_INTERVAL = timedelta(minutes=5)
HANDOFF_SETUP_TASK_TYPE = "disposition_handoff_setup"
HANDOFF_PENDING_BLOCKER = "Disposition setup is incomplete; automatic retry is pending."
PACKAGE_READY_ALERT_RECOVERY_WINDOW = timedelta(hours=24)
COMPLETED_DISPOSITION_CASE_STATUSES = TERMINAL_DISPOSITION_CASE_STATUSES & {
    "closed",
    "reconciled",
}
INACTIVE_DISPOSITION_DEAL_STAGES = frozenset({"cancelled", "canceled", "closed", "dead", "funded"})


@dataclass(frozen=True)
class DispositionOwnerRoute:
    user: User | None
    source: str
    team_id: UUID | None = None


@dataclass(frozen=True)
class InitialDispositionEconomics:
    asking_price_cents: int
    minimum_acceptable_cents: int
    desired_assignment_fee_cents: int | None
    source: str


def derive_initial_disposition_economics(
    db: Session,
    transaction: Transaction,
) -> InitialDispositionEconomics:
    """Derive a conservative starting point from saved contract facts only."""

    deal = db.get(Deal, transaction.deal_id)
    desired_fee = transaction.assignment_fee_cents
    source = "transaction"
    if desired_fee is None and deal is not None:
        desired_fee = deal.assignment_fee_cents
        source = "deal"
    normalized_fee = max(0, int(desired_fee)) if desired_fee is not None else None
    buyer_price = int(transaction.purchase_price_cents) + int(normalized_fee or 0)
    return InitialDispositionEconomics(
        asking_price_cents=buyer_price,
        minimum_acceptable_cents=buyer_price,
        desired_assignment_fee_cents=normalized_fee,
        source=(
            f"{source}_purchase_and_assignment"
            if normalized_fee is not None
            else "contract_basis"
        ),
    )


def ensure_disposition_case_for_executed_transaction(
    db: Session,
    transaction: Transaction,
) -> DispositionCase | None:
    """Open the shared disposition workspace from signed House or Land facts.

    This system-only entry point deliberately does not accept operator-supplied private
    economics. Both automated and manual recovery paths derive conservative starting values
    from the executed transaction and leave final package economics subject to the existing
    permission-gated draft-and-approval workflow.
    """
    db.flush()
    locked_transaction = db.scalar(
        select(Transaction)
        .where(
            Transaction.id == transaction.id,
            Transaction.organization_id == transaction.organization_id,
        )
        .with_for_update()
    )
    if locked_transaction is None or locked_transaction.status not in {
        "executed",
        "closing",
        "funded",
    }:
        return None

    existing = db.scalar(
        select(DispositionCase).where(
            DispositionCase.organization_id == locked_transaction.organization_id,
            DispositionCase.transaction_id == locked_transaction.id,
        )
    )
    if existing is not None:
        completed_handoff = (
            locked_transaction.status == "funded"
            and existing.status in COMPLETED_DISPOSITION_CASE_STATUSES
        )
        if existing.status in ACTIVE_DISPOSITION_CASE_STATUSES or completed_handoff:
            owner_route, blockers = _hydrate_disposition_case_setup(
                db,
                transaction=locked_transaction,
                disposition_case=existing,
            )
            if blockers:
                _record_case_setup_warnings(
                    db,
                    transaction=locked_transaction,
                    disposition_case=existing,
                    blockers=blockers,
                    owner_route=owner_route,
                )
            _resolve_auto_create_blocked_tasks(
                db,
                transaction=locked_transaction,
                case=existing,
            )
            return existing
        existing_owner = _active_authorized_disposition_user(
            db,
            locked_transaction.organization_id,
            existing.owner_user_id,
        )
        owner_route = (
            DispositionOwnerRoute(user=existing_owner, source="existing_case_owner")
            if existing_owner is not None
            else select_disposition_owner(
                db,
                organization_id=locked_transaction.organization_id,
            )
        )
        _record_auto_create_blocked(
            db,
            transaction=locked_transaction,
            blockers=[
                "The existing Disposition case is "
                f"{existing.status.replace('_', ' ')} while its transaction remains active."
            ],
            owner_route=owner_route,
        )
        return None

    lead = db.get(Lead, locked_transaction.lead_id)
    if (
        lead is None
        or lead.organization_id != locked_transaction.organization_id
        or lead.asset_class not in ASSET_CLASSES
        or lead.archived_at is not None
        or lead.stage_key in INACTIVE_LEAD_STAGES
    ):
        return None
    asset_class = normalize_asset_class(lead.asset_class)

    owner_route = select_disposition_owner(
        db,
        organization_id=locked_transaction.organization_id,
    )
    plan = _select_compensation_plan(db, locked_transaction)
    mode = _select_disposition_mode(db, locked_transaction, plan)
    setup_blockers: list[str] = []
    if owner_route.user is None:
        setup_blockers.append(
            "No active Dispositions specialist, team member, or owner fallback."
        )
    if plan is None:
        setup_blockers.append("No active compensation plan.")
    if plan is not None and mode is None:
        setup_blockers.append("No available human-led disposition operating mode.")
    property_record = db.get(Property, locked_transaction.property_id)
    initial_economics = derive_initial_disposition_economics(db, locked_transaction)

    disposition_case = DispositionCase(
        organization_id=locked_transaction.organization_id,
        transaction_id=locked_transaction.id,
        deal_id=locked_transaction.deal_id,
        lead_id=locked_transaction.lead_id,
        property_id=locked_transaction.property_id,
        owner_user_id=owner_route.user.id if owner_route.user else None,
        compensation_plan_version_id=plan.id if plan else None,
        disposition_operating_mode_id=mode.id if mode else None,
        status="package_prep",
        strategy="assignment",
        asking_price_cents=initial_economics.asking_price_cents,
        minimum_acceptable_cents=initial_economics.minimum_acceptable_cents,
        desired_assignment_fee_cents=initial_economics.desired_assignment_fee_cents,
        package_status="draft",
        package_snapshot={
            "package_reference": "pending",
            "asset_class": asset_class,
            "property": {
                "address": _property_address(property_record),
                "property_type": property_record.property_type if property_record else None,
                "county": property_record.county if property_record else None,
                "parcel_id": property_record.parcel_id if property_record else None,
            },
            "opportunity": {"strategy": "assignment"},
            "pricing": {
                "buyer_asking_price_cents": initial_economics.asking_price_cents
            },
            "due_diligence": [
                "Buyer must independently verify property facts, access, title, and "
                "closing capacity."
            ],
        },
        package_approved_by_user_id=None,
        package_approved_at=None,
        selected_buyer_id=None,
        backup_buyer_id=None,
        selection_approved_by_user_id=None,
        selection_approved_at=None,
        notes=(
            f"Automatically opened from the executed {asset_class.title()} seller "
            "purchase agreement."
        ),
    )
    db.add(disposition_case)
    if plan is not None:
        locked_transaction.compensation_plan_version_id = plan.id
    if mode is not None:
        locked_transaction.disposition_operating_mode_id = mode.id
    db.flush()
    if setup_blockers:
        _record_case_setup_warnings(
            db,
            transaction=locked_transaction,
            disposition_case=disposition_case,
            blockers=setup_blockers,
            owner_route=owner_route,
        )
    _resolve_auto_create_blocked_tasks(
        db,
        transaction=locked_transaction,
        case=disposition_case,
    )
    db.add(
        AuditEvent(
            organization_id=locked_transaction.organization_id,
            actor_user_id=None,
            actor_type="system",
            action="disposition.case_auto_create",
            entity_type="disposition_case",
            entity_id=disposition_case.id,
            previous_value=None,
            new_value={
                "transaction_id": str(locked_transaction.id),
                "lead_id": str(locked_transaction.lead_id),
                "asset_class": asset_class,
                "owner_user_id": str(owner_route.user.id) if owner_route.user else None,
                "owner_routing_source": owner_route.source,
                "owner_team_id": str(owner_route.team_id) if owner_route.team_id else None,
                "compensation_plan_version_id": str(plan.id) if plan else None,
                "disposition_operating_mode_id": str(mode.id) if mode else None,
                "status": "package_prep",
                "setup_warnings": setup_blockers,
                "private_economics_source": "executed_transaction",
                "private_economics_derivation": initial_economics.source,
            },
            reason=(
                f"Executed {asset_class.title()} purchase agreement automatically entered "
                "Dispositions."
            ),
        )
    )
    return disposition_case


def _hydrate_disposition_case_setup(
    db: Session,
    *,
    transaction: Transaction,
    disposition_case: DispositionCase,
) -> tuple[DispositionOwnerRoute, list[str]]:
    """Best-effort setup hydration for an already-open advisory workbench shell."""

    prior_owner_user_id = disposition_case.owner_user_id
    existing_owner = _active_authorized_disposition_user(
        db,
        transaction.organization_id,
        disposition_case.owner_user_id,
    )
    owner_route = (
        DispositionOwnerRoute(user=existing_owner, source="existing_case_owner")
        if existing_owner is not None
        else select_disposition_owner(db, organization_id=transaction.organization_id)
    )
    if existing_owner is None:
        # Do not leave a deactivated or deauthorized owner on an otherwise usable
        # advisory shell. Re-route when possible; otherwise keep it unassigned.
        disposition_case.owner_user_id = (
            owner_route.user.id if owner_route.user is not None else None
        )
        if disposition_case.owner_user_id != prior_owner_user_id:
            db.add(
                AuditEvent(
                    organization_id=transaction.organization_id,
                    actor_user_id=None,
                    actor_type="system",
                    action="disposition.case_owner_rerouted",
                    entity_type="disposition_case",
                    entity_id=disposition_case.id,
                    previous_value={
                        "owner_user_id": (
                            str(prior_owner_user_id) if prior_owner_user_id else None
                        )
                    },
                    new_value={
                        "owner_user_id": (
                            str(disposition_case.owner_user_id)
                            if disposition_case.owner_user_id
                            else None
                        ),
                        "routing_source": owner_route.source,
                    },
                    reason=(
                        "Re-routed an inactive or unauthorized disposition owner."
                        if disposition_case.owner_user_id is not None
                        else "Cleared an inactive or unauthorized disposition owner."
                    ),
                )
            )

    plan = _select_compensation_plan(db, transaction)
    if disposition_case.compensation_plan_version_id is None and plan is not None:
        disposition_case.compensation_plan_version_id = plan.id
    if transaction.compensation_plan_version_id is None and plan is not None:
        transaction.compensation_plan_version_id = plan.id

    mode = _select_disposition_mode(db, transaction, plan)
    if disposition_case.disposition_operating_mode_id is None and mode is not None:
        disposition_case.disposition_operating_mode_id = mode.id
    if transaction.disposition_operating_mode_id is None and mode is not None:
        transaction.disposition_operating_mode_id = mode.id

    blockers: list[str] = []
    if owner_route.user is None:
        blockers.append("No active Dispositions specialist, team member, or owner fallback.")
    if disposition_case.compensation_plan_version_id is None:
        blockers.append("No active compensation plan.")
    if disposition_case.disposition_operating_mode_id is None:
        blockers.append("No available human-led disposition operating mode.")
    return owner_route, blockers


def ensure_house_disposition_case_for_executed_transaction(
    db: Session,
    transaction: Transaction,
) -> DispositionCase | None:
    """Compatibility entry point that preserves the generated House workflow boundary."""

    lead = db.get(Lead, transaction.lead_id)
    if lead is None or lead.asset_class != "house":
        return None
    return ensure_disposition_case_for_executed_transaction(db, transaction)


def disposition_handoff_blockers(
    db: Session,
    transaction: Transaction,
) -> list[str]:
    """Read the durable blockers for an executed transaction waiting on setup."""
    audit = db.scalar(
        select(AuditEvent)
        .where(
            AuditEvent.organization_id == transaction.organization_id,
            AuditEvent.action == "disposition.case_auto_create_blocked",
            AuditEvent.entity_type == "transaction",
            AuditEvent.entity_id == transaction.id,
        )
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(1)
    )
    if audit is not None:
        raw_blockers = (audit.new_value or {}).get("blockers")
        if isinstance(raw_blockers, list):
            blockers = [value.strip() for value in raw_blockers if isinstance(value, str)]
            if blockers:
                return blockers
        if audit.reason and audit.reason.strip():
            return [audit.reason.strip()]
    return [HANDOFF_PENDING_BLOCKER]


def process_next_disposition_handoff_recovery(
    db: Session,
    _settings: Settings,
) -> UUID | None:
    """Retry one executed House or Land transaction after a setup blocker clears."""
    cutoff = datetime.now(UTC) - HANDOFF_RECOVERY_INTERVAL
    latest_blocked_at = (
        select(func.max(AuditEvent.created_at))
        .where(
            AuditEvent.organization_id == Transaction.organization_id,
            AuditEvent.entity_type == "transaction",
            AuditEvent.entity_id == Transaction.id,
            AuditEvent.action == "disposition.case_auto_create_blocked",
        )
        .correlate(Transaction)
        .scalar_subquery()
    )
    latest_setup_warning_at = (
        select(func.max(AuditEvent.created_at))
        .where(
            AuditEvent.organization_id == Transaction.organization_id,
            AuditEvent.entity_type == "disposition_case",
            AuditEvent.entity_id == DispositionCase.id,
            AuditEvent.action == "disposition.case_setup_incomplete",
        )
        .correlate(Transaction, DispositionCase)
        .scalar_subquery()
    )
    active_owner_exists = (
        select(User.id)
        .where(
            User.id == DispositionCase.owner_user_id,
            User.organization_id == Transaction.organization_id,
            User.is_active.is_(True),
        )
        .correlate(Transaction, DispositionCase)
        .exists()
    )
    required_owner_permissions_exist = [
        select(Permission.id)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(RoleAssignment, RoleAssignment.role_id == RolePermission.role_id)
        .join(Role, Role.id == RoleAssignment.role_id)
        .where(
            RoleAssignment.organization_id == Transaction.organization_id,
            RoleAssignment.user_id == DispositionCase.owner_user_id,
            RolePermission.organization_id == Transaction.organization_id,
            Role.organization_id == Transaction.organization_id,
            Permission.key == permission_key,
        )
        .correlate(Transaction, DispositionCase)
        .exists()
        for permission_key in REQUIRED_DISPOSITION_OWNER_PERMISSION_KEYS
    ]
    invalid_owner = or_(
        DispositionCase.owner_user_id.is_(None),
        ~active_owner_exists,
        *(~permission_exists for permission_exists in required_owner_permissions_exist),
    )
    transaction = db.scalar(
        select(Transaction)
        .join(
            Lead,
            (Lead.id == Transaction.lead_id)
            & (Lead.organization_id == Transaction.organization_id),
        )
        .outerjoin(
            DispositionCase,
            (DispositionCase.organization_id == Transaction.organization_id)
            & (DispositionCase.transaction_id == Transaction.id),
        )
        .where(
            or_(
                DispositionCase.id.is_(None),
                and_(
                    DispositionCase.status.in_(tuple(ACTIVE_DISPOSITION_CASE_STATUSES)),
                    or_(
                        invalid_owner,
                        DispositionCase.compensation_plan_version_id.is_(None),
                        DispositionCase.disposition_operating_mode_id.is_(None),
                    ),
                    or_(
                        latest_setup_warning_at.is_(None),
                        latest_setup_warning_at <= cutoff,
                    ),
                ),
                and_(
                    ~DispositionCase.status.in_(tuple(ACTIVE_DISPOSITION_CASE_STATUSES)),
                    ~and_(
                        Transaction.status == "funded",
                        DispositionCase.status.in_(tuple(COMPLETED_DISPOSITION_CASE_STATUSES)),
                    ),
                ),
            ),
            Transaction.status.in_(("executed", "closing", "funded")),
            Transaction.contract_executed_at.is_not(None),
            Lead.asset_class.in_(tuple(sorted(ASSET_CLASSES))),
            Lead.archived_at.is_(None),
            ~Lead.stage_key.in_(tuple(INACTIVE_LEAD_STAGES)),
            or_(latest_blocked_at.is_(None), latest_blocked_at <= cutoff),
        )
        .order_by(Transaction.contract_executed_at, Transaction.id)
        .limit(1)
    )
    if transaction is None:
        return None
    ensure_disposition_case_for_executed_transaction(db, transaction)
    db.commit()
    return transaction.id


def select_disposition_owner(
    db: Session,
    *,
    organization_id: UUID,
) -> DispositionOwnerRoute:
    teams = list(
        db.scalars(
            select(Team)
            .where(
                Team.organization_id == organization_id,
                Team.team_type == "dispositions",
                Team.is_active.is_(True),
            )
            .order_by(Team.name, Team.created_at, Team.id)
        ).all()
    )
    for team in teams:
        manager = _active_authorized_disposition_user(
            db,
            organization_id,
            team.manager_user_id,
        )
        if manager is not None:
            return DispositionOwnerRoute(
                user=manager,
                source="dispositions_team_manager",
                team_id=team.id,
            )
        memberships = list(
            db.scalars(
                select(TeamMembership)
                .where(
                    TeamMembership.organization_id == organization_id,
                    TeamMembership.team_id == team.id,
                )
                .order_by(
                    TeamMembership.membership_role,
                    TeamMembership.created_at,
                    TeamMembership.id,
                )
            ).all()
        )
        memberships.sort(
            key=lambda item: (
                0 if item.membership_role == "manager" else 1,
                item.created_at,
                str(item.id),
            )
        )
        for membership in memberships:
            member = _active_authorized_disposition_user(
                db,
                organization_id,
                membership.user_id,
            )
            if member is not None:
                return DispositionOwnerRoute(
                    user=member,
                    source="dispositions_team_member",
                    team_id=team.id,
                )

    for role_key in DISPOSITION_ROLE_KEYS:
        for specialist in _active_users_with_role_key(db, organization_id, role_key):
            authorized = _active_authorized_disposition_user(
                db,
                organization_id,
                specialist.id,
            )
            if authorized is not None:
                return DispositionOwnerRoute(user=authorized, source=f"role:{role_key}")

    seats = list(
        db.scalars(
            select(OperatingSeat)
            .where(
                OperatingSeat.organization_id == organization_id,
                OperatingSeat.seat_key == "dispositions",
                OperatingSeat.status == "covered",
            )
            .order_by(OperatingSeat.created_at, OperatingSeat.id)
        ).all()
    )
    for seat in seats:
        for user_id, source in (
            (seat.primary_user_id, "operating_seat_primary"),
            (seat.backup_user_id, "operating_seat_backup"),
        ):
            user = _active_authorized_disposition_user(db, organization_id, user_id)
            if user is not None:
                return DispositionOwnerRoute(user=user, source=source)

    for role_key in EXECUTIVE_FALLBACK_ROLE_KEYS:
        for executive in _active_users_with_role_key(db, organization_id, role_key):
            authorized = _active_authorized_disposition_user(
                db,
                organization_id,
                executive.id,
            )
            if authorized is not None:
                return DispositionOwnerRoute(
                    user=authorized,
                    source=f"fallback_role:{role_key}",
                )
    return DispositionOwnerRoute(user=None, source="unassigned")


def queue_disposition_package_ready_alert(
    db: Session,
    *,
    disposition_case: DispositionCase,
    package_version: DispositionPackageVersion,
) -> int:
    """Queue one owner-only SMS that reports an exact package review event."""
    if (
        package_version.organization_id != disposition_case.organization_id
        or package_version.disposition_case_id != disposition_case.id
        or package_version.status != "approved"
        or disposition_case.package_status != "approved"
    ):
        return 0
    latest = db.scalar(
        select(DispositionPackageVersion)
        .where(
            DispositionPackageVersion.organization_id == disposition_case.organization_id,
            DispositionPackageVersion.disposition_case_id == disposition_case.id,
        )
        .order_by(
            DispositionPackageVersion.version_number.desc(),
            DispositionPackageVersion.id.desc(),
        )
        .limit(1)
    )
    if latest is None or latest.id != package_version.id:
        return 0
    if db.scalar(
        select(StaffLeadAlert.id).where(
            StaffLeadAlert.organization_id == disposition_case.organization_id,
            StaffLeadAlert.source_type == PACKAGE_READY_ALERT_SOURCE_TYPE,
            StaffLeadAlert.source_event_id == package_version.id,
            StaffLeadAlert.recipient_user_id == disposition_case.owner_user_id,
        )
    ):
        return 0

    active_owner = _active_organization_user(
        db,
        disposition_case.organization_id,
        disposition_case.owner_user_id,
    )
    owner = _active_authorized_disposition_user(
        db,
        disposition_case.organization_id,
        disposition_case.owner_user_id,
    )
    sms_opted_in = bool(owner is not None and owner.lead_alert_sms_enabled)
    owner_phone = format_e164(owner.voice_forwarding_number if owner is not None else None)
    phone = owner_phone if sms_opted_in else None
    address = _property_address(db.get(Property, disposition_case.property_id))
    created = 0
    if owner is not None and phone is not None:
        db.add(
            StaffLeadAlert(
                organization_id=disposition_case.organization_id,
                meta_lead_event_id=None,
                source_type=PACKAGE_READY_ALERT_SOURCE_TYPE,
                source_event_id=package_version.id,
                lead_id=disposition_case.lead_id,
                conversation_id=None,
                recipient_user_id=owner.id,
                recipient_phone=phone,
                message_body=(
                    f"Investor package v{package_version.version_number} for {address} was "
                    "approved; checklist work may remain. Open Stonegate: "
                    "https://www.stonegatehb.com/os/deals?view=all&display=queue&"
                    f"deal={disposition_case.deal_id}&tab=disposition&dispositionTab=package"
                )[:1000],
                status="pending",
                attempt_count=0,
                last_attempt_at=None,
                next_attempt_at=None,
                sent_at=None,
                delivered_at=None,
                provider=None,
                provider_message_id=None,
                provider_response=None,
                last_error=None,
            )
        )
        created = 1

    db.add(
        AuditEvent(
            organization_id=disposition_case.organization_id,
            actor_user_id=None,
            actor_type="system",
            action=(
                "disposition.package_ready_sms_queued"
                if created
                else "disposition.package_ready_sms_not_queued"
            ),
            entity_type="disposition_package_version",
            entity_id=package_version.id,
            previous_value=None,
            new_value={
                "case_id": str(disposition_case.id),
                "deal_id": str(disposition_case.deal_id),
                "package_version": package_version.version_number,
                "source_fingerprint": package_version.source_fingerprint,
                "recipient_user_id": (
                    str(disposition_case.owner_user_id)
                    if disposition_case.owner_user_id is not None
                    else None
                ),
                "owner_active": active_owner is not None,
                "owner_disposition_authorized": owner is not None,
                "owner_sms_opted_in": sms_opted_in,
                "owner_phone_usable": owner_phone is not None,
                "alerts_created": created,
            },
            reason=(
                "Queued an alert for the exact package version approved by a reviewer."
                if created
                else _package_ready_alert_not_queued_reason(
                    active_owner=active_owner,
                    authorized_owner=owner,
                    sms_opted_in=sms_opted_in,
                    phone=owner_phone,
                )
            ),
        )
    )
    db.flush()
    return created


def revalidate_disposition_package_ready_alert(
    db: Session,
    alert: StaffLeadAlert,
    *,
    now: datetime | None = None,
) -> bool:
    """Re-authorize a queued package alert immediately before provider delivery.

    A durable alert row records intent, not continuing authority. Ownership, RBAC,
    staff SMS opt-in, and the cellphone can all change while the row waits in the
    worker queue. This check deliberately runs after the alert is claimed and before
    any provider call.
    """
    if alert.source_type != PACKAGE_READY_ALERT_SOURCE_TYPE:
        return True

    checked_at = now or datetime.now(UTC)
    package = db.scalar(
        select(DispositionPackageVersion)
        .where(
            DispositionPackageVersion.id == alert.source_event_id,
            DispositionPackageVersion.organization_id == alert.organization_id,
        )
        .with_for_update()
    )
    disposition_case = None
    if package is not None:
        disposition_case = db.scalar(
            select(DispositionCase)
            .where(
                DispositionCase.id == package.disposition_case_id,
                DispositionCase.organization_id == alert.organization_id,
            )
            .with_for_update()
        )

    reason: str | None = None
    terminal = False
    current_owner_id: UUID | None = None
    active_owner: User | None = None
    authorized_owner: User | None = None
    sms_opted_in = False
    owner_phone: str | None = None

    if package is None or disposition_case is None:
        reason = "The approved disposition package or case is no longer available."
        terminal = True
    else:
        current_owner_id = disposition_case.owner_user_id
        lead = db.scalar(
            select(Lead).where(
                Lead.id == disposition_case.lead_id,
                Lead.organization_id == alert.organization_id,
            )
        )
        deal = db.scalar(
            select(Deal).where(
                Deal.id == disposition_case.deal_id,
                Deal.organization_id == alert.organization_id,
            )
        )
        latest_package_id = db.scalar(
            select(DispositionPackageVersion.id)
            .where(
                DispositionPackageVersion.organization_id == alert.organization_id,
                DispositionPackageVersion.disposition_case_id == disposition_case.id,
            )
            .order_by(
                DispositionPackageVersion.version_number.desc(),
                DispositionPackageVersion.id.desc(),
            )
            .limit(1)
        )
        if (
            package.status != "approved"
            or disposition_case.package_status != "approved"
            or latest_package_id != package.id
            or disposition_case.status not in ACTIVE_DISPOSITION_CASE_STATUSES
            or lead is None
            or lead.asset_class not in ASSET_CLASSES
            or lead.archived_at is not None
            or lead.stage_key in INACTIVE_LEAD_STAGES
            or deal is None
            or deal.stage_key in INACTIVE_DISPOSITION_DEAL_STAGES
        ):
            reason = "The disposition package is no longer attached to an active supported deal."
            terminal = True
        elif alert.recipient_user_id != current_owner_id:
            reason = "The queued recipient is no longer the assigned disposition owner."
            terminal = True
        else:
            active_owner = _active_organization_user(
                db,
                alert.organization_id,
                current_owner_id,
            )
            authorized_owner = _active_authorized_disposition_user(
                db,
                alert.organization_id,
                current_owner_id,
            )
            sms_opted_in = bool(
                authorized_owner is not None and authorized_owner.lead_alert_sms_enabled
            )
            owner_phone = format_e164(
                authorized_owner.voice_forwarding_number if authorized_owner is not None else None
            )
            if active_owner is None:
                reason = "The assigned disposition owner is no longer active."
            elif authorized_owner is None:
                reason = (
                    "The assigned disposition owner no longer has required "
                    "Dispositions permissions."
                )
            elif not sms_opted_in:
                reason = (
                    "The assigned disposition owner is no longer opted in to text-new-leads alerts."
                )
            elif owner_phone is None:
                reason = (
                    "The assigned disposition owner no longer has a usable cellphone "
                    "for staff alerts."
                )

    if reason is None:
        assert owner_phone is not None
        alert.recipient_phone = owner_phone
        alert.last_error = None
        return True

    previous_error = alert.last_error
    alert.status = "canceled" if terminal else "blocked"
    alert.next_attempt_at = None if terminal else checked_at + HANDOFF_RECOVERY_INTERVAL
    alert.last_error = reason[:2000]
    if previous_error != reason:
        db.add(
            AuditEvent(
                organization_id=alert.organization_id,
                actor_user_id=None,
                actor_type="system",
                action="disposition.package_ready_sms_not_queued",
                entity_type="disposition_package_version",
                entity_id=alert.source_event_id,
                previous_value={
                    "queued_recipient_user_id": str(alert.recipient_user_id),
                    "queued_recipient_phone": alert.recipient_phone,
                },
                new_value={
                    "case_id": (str(disposition_case.id) if disposition_case is not None else None),
                    "deal_id": (
                        str(disposition_case.deal_id) if disposition_case is not None else None
                    ),
                    "recipient_user_id": (
                        str(current_owner_id) if current_owner_id is not None else None
                    ),
                    "owner_active": active_owner is not None,
                    "owner_disposition_authorized": authorized_owner is not None,
                    "owner_sms_opted_in": sms_opted_in,
                    "owner_phone_usable": owner_phone is not None,
                    "delivery_revalidation": True,
                    "alert_status": alert.status,
                },
                reason=reason,
            )
        )
    return False


def process_next_disposition_package_alert_recovery(
    db: Session,
    _settings: Settings,
) -> UUID | None:
    """Retry one exact package-review alert after an owner fixes SMS delivery setup."""
    now = datetime.now(UTC)
    cutoff = now - HANDOFF_RECOVERY_INTERVAL
    recovery_floor = now - PACKAGE_READY_ALERT_RECOVERY_WINDOW
    newer_package = aliased(DispositionPackageVersion)
    newer_version_exists = (
        select(newer_package.id)
        .where(
            newer_package.organization_id == DispositionPackageVersion.organization_id,
            newer_package.disposition_case_id == DispositionPackageVersion.disposition_case_id,
            newer_package.version_number > DispositionPackageVersion.version_number,
        )
        .correlate(DispositionPackageVersion)
        .exists()
    )
    alert_exists = (
        select(StaffLeadAlert.id)
        .where(
            StaffLeadAlert.organization_id == DispositionPackageVersion.organization_id,
            StaffLeadAlert.source_type == PACKAGE_READY_ALERT_SOURCE_TYPE,
            StaffLeadAlert.source_event_id == DispositionPackageVersion.id,
            StaffLeadAlert.recipient_user_id == DispositionCase.owner_user_id,
        )
        .correlate(DispositionPackageVersion, DispositionCase)
        .exists()
    )
    latest_attempt_action = (
        select(AuditEvent.action)
        .where(
            AuditEvent.organization_id == DispositionPackageVersion.organization_id,
            AuditEvent.entity_type == "disposition_package_version",
            AuditEvent.entity_id == DispositionPackageVersion.id,
            AuditEvent.action.in_(
                (
                    "disposition.package_ready_sms_queued",
                    "disposition.package_ready_sms_not_queued",
                )
            ),
        )
        .correlate(DispositionPackageVersion)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(1)
        .scalar_subquery()
    )
    latest_attempt_at = (
        select(AuditEvent.created_at)
        .where(
            AuditEvent.organization_id == DispositionPackageVersion.organization_id,
            AuditEvent.entity_type == "disposition_package_version",
            AuditEvent.entity_id == DispositionPackageVersion.id,
            AuditEvent.action.in_(
                (
                    "disposition.package_ready_sms_queued",
                    "disposition.package_ready_sms_not_queued",
                )
            ),
        )
        .correlate(DispositionPackageVersion)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(1)
        .scalar_subquery()
    )
    package = db.scalar(
        select(DispositionPackageVersion)
        .join(
            DispositionCase,
            (DispositionCase.id == DispositionPackageVersion.disposition_case_id)
            & (DispositionCase.organization_id == DispositionPackageVersion.organization_id),
        )
        .join(
            Lead,
            (Lead.id == DispositionCase.lead_id)
            & (Lead.organization_id == DispositionCase.organization_id),
        )
        .join(
            Deal,
            (Deal.id == DispositionCase.deal_id)
            & (Deal.organization_id == DispositionCase.organization_id),
        )
        .where(
            DispositionPackageVersion.status == "approved",
            DispositionCase.package_status == "approved",
            DispositionCase.status.in_(tuple(ACTIVE_DISPOSITION_CASE_STATUSES)),
            Lead.asset_class.in_(tuple(sorted(ASSET_CLASSES))),
            Lead.archived_at.is_(None),
            ~Lead.stage_key.in_(tuple(INACTIVE_LEAD_STAGES)),
            ~Deal.stage_key.in_(tuple(INACTIVE_DISPOSITION_DEAL_STAGES)),
            ~newer_version_exists,
            ~alert_exists,
            latest_attempt_action == "disposition.package_ready_sms_not_queued",
            latest_attempt_at >= recovery_floor,
            latest_attempt_at <= cutoff,
        )
        .order_by(
            latest_attempt_at,
            DispositionPackageVersion.id,
        )
        .limit(1)
    )
    if package is None:
        return None
    disposition_case = db.get(DispositionCase, package.disposition_case_id)
    if disposition_case is None:
        return None
    queue_disposition_package_ready_alert(
        db,
        disposition_case=disposition_case,
        package_version=package,
    )
    db.commit()
    return package.id


def _select_compensation_plan(
    db: Session,
    transaction: Transaction,
) -> CompensationPlanVersion | None:
    if transaction.compensation_plan_version_id is not None:
        selected = db.get(CompensationPlanVersion, transaction.compensation_plan_version_id)
        if selected is not None and selected.organization_id == transaction.organization_id:
            return selected
    return db.scalar(
        select(CompensationPlanVersion)
        .where(
            CompensationPlanVersion.organization_id == transaction.organization_id,
            CompensationPlanVersion.status == "active",
        )
        .order_by(
            CompensationPlanVersion.version_number.desc(),
            CompensationPlanVersion.created_at.desc(),
            CompensationPlanVersion.id,
        )
    )


def _select_disposition_mode(
    db: Session,
    transaction: Transaction,
    plan: CompensationPlanVersion | None,
) -> DispositionOperatingMode | None:
    if plan is None:
        return None
    if transaction.disposition_operating_mode_id is not None:
        selected = db.get(DispositionOperatingMode, transaction.disposition_operating_mode_id)
        if (
            selected is not None
            and selected.organization_id == transaction.organization_id
            and selected.compensation_plan_version_id == plan.id
            and selected.status == "available"
            and selected.key == "human_led"
        ):
            return selected
    modes = list(
        db.scalars(
            select(DispositionOperatingMode)
            .where(
                DispositionOperatingMode.organization_id == transaction.organization_id,
                DispositionOperatingMode.compensation_plan_version_id == plan.id,
                DispositionOperatingMode.status == "available",
            )
            .order_by(DispositionOperatingMode.created_at, DispositionOperatingMode.id)
        ).all()
    )
    return next((mode for mode in modes if mode.key == "human_led"), None)


def _active_organization_user(
    db: Session,
    organization_id: UUID,
    user_id: UUID | None,
) -> User | None:
    if user_id is None:
        return None
    return db.scalar(
        select(User).where(
            User.id == user_id,
            User.organization_id == organization_id,
            User.is_active.is_(True),
        )
    )


def _active_authorized_disposition_user(
    db: Session,
    organization_id: UUID,
    user_id: UUID | None,
) -> User | None:
    user = _active_organization_user(db, organization_id, user_id)
    if user is None:
        return None
    permission_keys = frozenset(
        db.scalars(
            select(Permission.key)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(RoleAssignment, RoleAssignment.role_id == RolePermission.role_id)
            .join(Role, Role.id == RoleAssignment.role_id)
            .where(
                RoleAssignment.organization_id == organization_id,
                RoleAssignment.user_id == user.id,
                RolePermission.organization_id == organization_id,
                Role.organization_id == organization_id,
                Permission.key.in_(REQUIRED_DISPOSITION_OWNER_PERMISSION_KEYS),
            )
        ).all()
    )
    if not REQUIRED_DISPOSITION_OWNER_PERMISSION_KEYS.issubset(permission_keys):
        return None
    return user


def active_authorized_disposition_user(
    db: Session,
    organization_id: UUID,
    user_id: UUID | None,
) -> User | None:
    """Resolve a disposition owner only when tenant, active-user, and RBAC checks pass."""

    return _active_authorized_disposition_user(db, organization_id, user_id)


def _active_users_with_role_key(
    db: Session,
    organization_id: UUID,
    role_key: str,
) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .join(RoleAssignment, RoleAssignment.user_id == User.id)
            .join(Role, Role.id == RoleAssignment.role_id)
            .where(
                User.organization_id == organization_id,
                User.is_active.is_(True),
                RoleAssignment.organization_id == organization_id,
                Role.organization_id == organization_id,
                Role.key == role_key,
            )
            .order_by(User.created_at, User.id)
        ).all()
    )


def _package_ready_alert_not_queued_reason(
    *,
    active_owner: User | None,
    authorized_owner: User | None,
    sms_opted_in: bool,
    phone: str | None,
) -> str:
    if active_owner is None:
        return "The assigned disposition owner is not an active organization user."
    if authorized_owner is None:
        return "The assigned disposition owner lacks required Dispositions permissions."
    if not sms_opted_in:
        return "The assigned disposition owner has not opted in to staff lead-alert SMS."
    if phone is None:
        return "The assigned disposition owner has no usable cellphone for staff alerts."
    return "The approved package alert was not queued."


def _record_auto_create_blocked(
    db: Session,
    *,
    transaction: Transaction,
    blockers: list[str],
    owner_route: DispositionOwnerRoute,
) -> None:
    existing_task = db.scalar(
        select(Task).where(
            Task.organization_id == transaction.organization_id,
            Task.deal_id == transaction.deal_id,
            Task.task_type == HANDOFF_SETUP_TASK_TYPE,
            Task.status.in_(("open", "in_progress")),
        )
    )
    if existing_task is None:
        db.add(
            Task(
                organization_id=transaction.organization_id,
                lead_id=transaction.lead_id,
                deal_id=transaction.deal_id,
                responsible_user_id=(
                    owner_route.user.id
                    if owner_route.user is not None
                    else transaction.coordinator_user_id or transaction.owner_user_id
                ),
                task_type=HANDOFF_SETUP_TASK_TYPE,
                work_kind="supporting",
                title="Complete Dispositions setup for the executed contract",
                status="open",
                priority="urgent",
                due_at=datetime.now(UTC),
                completed_at=None,
                completed_by_user_id=None,
                outcome=None,
                completion_notes=None,
                successor_task_id=None,
            )
        )
    recent = db.scalar(
        select(AuditEvent.id).where(
            AuditEvent.organization_id == transaction.organization_id,
            AuditEvent.action == "disposition.case_auto_create_blocked",
            AuditEvent.entity_type == "transaction",
            AuditEvent.entity_id == transaction.id,
            AuditEvent.created_at >= datetime.now(UTC) - HANDOFF_RECOVERY_INTERVAL,
        )
    )
    if recent is not None:
        return
    db.add(
        AuditEvent(
            organization_id=transaction.organization_id,
            actor_user_id=None,
            actor_type="system",
            action="disposition.case_auto_create_blocked",
            entity_type="transaction",
            entity_id=transaction.id,
            previous_value=None,
            new_value={
                "transaction_id": str(transaction.id),
                "blockers": blockers,
                "owner_routing_source": owner_route.source,
                "owner_user_id": (
                    str(owner_route.user.id) if owner_route.user is not None else None
                ),
            },
            reason="; ".join(blockers),
        )
    )


def _record_case_setup_warnings(
    db: Session,
    *,
    transaction: Transaction,
    disposition_case: DispositionCase,
    blockers: list[str],
    owner_route: DispositionOwnerRoute,
) -> None:
    recent = db.scalar(
        select(AuditEvent.id).where(
            AuditEvent.organization_id == transaction.organization_id,
            AuditEvent.action == "disposition.case_setup_incomplete",
            AuditEvent.entity_type == "disposition_case",
            AuditEvent.entity_id == disposition_case.id,
            AuditEvent.created_at >= datetime.now(UTC) - HANDOFF_RECOVERY_INTERVAL,
        )
    )
    if recent is not None:
        return
    db.add(
        AuditEvent(
            organization_id=transaction.organization_id,
            actor_user_id=None,
            actor_type="system",
            action="disposition.case_setup_incomplete",
            entity_type="disposition_case",
            entity_id=disposition_case.id,
            previous_value=None,
            new_value={
                "transaction_id": str(transaction.id),
                "warnings": blockers,
                "is_advisory": True,
                "owner_routing_source": owner_route.source,
                "owner_user_id": (
                    str(owner_route.user.id) if owner_route.user is not None else None
                ),
            },
            reason="; ".join(blockers),
        )
    )


def _resolve_auto_create_blocked_tasks(
    db: Session,
    *,
    transaction: Transaction,
    case: DispositionCase,
) -> None:
    completed_at = datetime.now(UTC)
    for task in db.scalars(
        select(Task).where(
            Task.organization_id == transaction.organization_id,
            Task.deal_id == transaction.deal_id,
            Task.task_type == HANDOFF_SETUP_TASK_TYPE,
            Task.status.in_(("open", "in_progress")),
        )
    ).all():
        task.status = "completed"
        task.completed_at = completed_at
        task.outcome = "disposition_case_opened"
        task.completion_notes = f"Automatically resolved when Disposition case {case.id} opened."


def _property_address(property_record: Property | None) -> str:
    if property_record is None:
        return "Address unavailable"
    return (
        property_identity_label(
            street_address=property_record.street_address,
            city=property_record.city,
            state=property_record.state,
            postal_code=property_record.postal_code,
            parcel_id=property_record.parcel_id,
            county=property_record.county,
        )
        or "Address unavailable"
    )
