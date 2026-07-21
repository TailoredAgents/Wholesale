from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import Settings
from app.domain.rbac import PermissionKeys
from app.models.foundation import (
    ActivityEvent,
    Appointment,
    ApprovalRequest,
    AuditEvent,
    CalendarEvent,
    CallingList,
    CallingListEntry,
    Contact,
    ContactMethod,
    DuplicateCandidate,
    FollowUpEnrollment,
    FollowUpPlan,
    Lead,
    LeadMergeEvent,
    Notification,
    Property,
    Role,
    RoleAssignment,
    SavedView,
    Task,
    Team,
    TeamMembership,
    User,
)
from app.schemas.inbox import ConversationHandoffRequest
from app.schemas.leads import LeadAppointmentUpdate, LeadDetail
from app.schemas.operations import (
    AcquisitionOperationsOverview,
    AppointmentOperationsRead,
    CallingListCreate,
    CallingListEntryRead,
    CallingListEntryUpdate,
    CallingListLeadAdd,
    CallingListRead,
    DuplicateCandidateRead,
    DuplicateResolution,
    FollowUpEnrollmentCreate,
    FollowUpPlanCreate,
    FollowUpPlanRead,
    NotificationRead,
    OperationsUserCreate,
    OperationsUserRead,
    OperationsUserUpdate,
    SavedViewCreate,
    SavedViewRead,
    TeamCreate,
    TeamMemberCreate,
    TeamMemberRead,
    TeamRead,
)
from app.services.inbox import ensure_primary_conversation, handoff_conversation
from app.services.leads import get_lead_detail

OPERATIONAL_ROLE_KEYS = {
    "administrator",
    "acquisition_manager",
    "acquisition_rep",
    "prospecting_caller",
    "disposition_manager",
    "disposition_rep",
    "transaction_coordinator",
}
INTERESTED_DISPOSITIONS = {"interested", "appointment_set"}


def can_manage_operations(principal: Principal) -> bool:
    return PermissionKeys.MANAGE_ACQUISITION_OPERATIONS in principal.permission_keys


def user_role_keys(db: Session, organization_id: UUID, user_id: UUID) -> list[str]:
    return list(
        db.scalars(
            select(Role.key)
            .join(RoleAssignment, RoleAssignment.role_id == Role.id)
            .where(
                RoleAssignment.organization_id == organization_id,
                RoleAssignment.user_id == user_id,
            )
            .order_by(Role.name)
        )
    )


def get_operations_overview(
    db: Session,
    principal: Principal,
) -> AcquisitionOperationsOverview:
    manageable = can_manage_operations(principal)
    users = list_users(db, principal, manageable=manageable)
    teams = list_teams(db, principal, manageable=manageable)
    calling_lists = list_calling_lists(db, principal, manageable=manageable)
    notifications = list_notifications(db, principal)
    saved_views = list_saved_views(db, principal)
    duplicates = list_duplicate_candidates(db, principal) if manageable else []
    plans = list_follow_up_plans(db, principal) if manageable else []
    appointments = list_operational_appointments(db, principal, manageable=manageable)
    return AcquisitionOperationsOverview(
        can_manage=manageable,
        users=users,
        teams=teams,
        calling_lists=calling_lists,
        appointments=appointments,
        saved_views=saved_views,
        notifications=notifications,
        unread_notification_count=sum(item.read_at is None for item in notifications),
        duplicate_candidates=duplicates,
        follow_up_plans=plans,
    )


def list_users(
    db: Session,
    principal: Principal,
    *,
    manageable: bool,
) -> list[OperationsUserRead]:
    statement = select(User).where(User.organization_id == principal.organization_id)
    if not manageable:
        statement = statement.where(User.id == principal.user_id)
    users = db.scalars(statement.order_by(User.is_active.desc(), User.display_name)).all()
    result: list[OperationsUserRead] = []
    for user in users:
        open_leads = int(
            db.scalar(
                select(func.count())
                .select_from(Lead)
                .where(
                    Lead.organization_id == principal.organization_id,
                    Lead.assigned_user_id == user.id,
                    Lead.archived_at.is_(None),
                )
            )
            or 0
        )
        open_tasks = int(
            db.scalar(
                select(func.count())
                .select_from(Task)
                .where(
                    Task.organization_id == principal.organization_id,
                    Task.responsible_user_id == user.id,
                    Task.status.in_(("open", "in_progress")),
                )
            )
            or 0
        )
        result.append(
            OperationsUserRead(
                id=user.id,
                email=user.email,
                display_name=user.display_name,
                is_active=user.is_active,
                role_keys=user_role_keys(db, principal.organization_id, user.id),
                open_leads=open_leads,
                open_tasks=open_tasks,
            )
        )
    return result


def create_operations_user(
    db: Session,
    principal: Principal,
    payload: OperationsUserCreate,
) -> OperationsUserRead:
    role = validate_operational_role(db, principal.organization_id, payload.role_key)
    normalized_email = payload.email.lower().strip()
    existing = db.scalar(
        select(User).where(
            User.organization_id == principal.organization_id,
            User.email == normalized_email,
        )
    )
    if existing is not None:
        raise ValueError("A workspace user with this email already exists.")
    user = User(
        organization_id=principal.organization_id,
        email=normalized_email,
        display_name=payload.display_name.strip(),
        external_auth_id=None,
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(
        RoleAssignment(
            organization_id=principal.organization_id,
            user_id=user.id,
            role_id=role.id,
        )
    )
    audit(
        db,
        principal,
        action="user.create",
        entity_type="user",
        entity_id=user.id,
        previous=None,
        new={"email": normalized_email, "role_key": role.key, "is_active": True},
        reason="Acquisition operations user created",
    )
    db.commit()
    return operations_user_read(db, user)


def operations_user_read(db: Session, user: User) -> OperationsUserRead:
    open_leads = int(
        db.scalar(
            select(func.count())
            .select_from(Lead)
            .where(
                Lead.organization_id == user.organization_id,
                Lead.assigned_user_id == user.id,
                Lead.archived_at.is_(None),
            )
        )
        or 0
    )
    open_tasks = int(
        db.scalar(
            select(func.count())
            .select_from(Task)
            .where(
                Task.organization_id == user.organization_id,
                Task.responsible_user_id == user.id,
                Task.status.in_(("open", "in_progress")),
            )
        )
        or 0
    )
    return OperationsUserRead(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_active=user.is_active,
        role_keys=user_role_keys(db, user.organization_id, user.id),
        open_leads=open_leads,
        open_tasks=open_tasks,
    )


def update_operations_user(
    db: Session,
    principal: Principal,
    user_id: UUID,
    payload: OperationsUserUpdate,
) -> OperationsUserRead | None:
    user = db.scalar(
        select(User).where(
            User.organization_id == principal.organization_id,
            User.id == user_id,
        )
    )
    if user is None:
        return None
    if user.id == principal.user_id and payload.is_active is False:
        raise ValueError("You cannot deactivate your own account.")
    previous = {
        "display_name": user.display_name,
        "is_active": user.is_active,
        "role_keys": user_role_keys(db, principal.organization_id, user.id),
    }
    if payload.display_name is not None:
        user.display_name = payload.display_name.strip()
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.role_key is not None:
        role = validate_operational_role(db, principal.organization_id, payload.role_key)
        for assignment in db.scalars(
            select(RoleAssignment).where(
                RoleAssignment.organization_id == principal.organization_id,
                RoleAssignment.user_id == user.id,
            )
        ):
            db.delete(assignment)
        db.flush()
        db.add(
            RoleAssignment(
                organization_id=principal.organization_id,
                user_id=user.id,
                role_id=role.id,
            )
        )
    audit(
        db,
        principal,
        action="user.update",
        entity_type="user",
        entity_id=user.id,
        previous=previous,
        new={
            "display_name": user.display_name,
            "is_active": user.is_active,
            "role_key": payload.role_key,
        },
        reason=payload.reason,
    )
    db.commit()
    return operations_user_read(db, user)


def validate_operational_role(db: Session, organization_id: UUID, role_key: str) -> Role:
    if role_key not in OPERATIONAL_ROLE_KEYS:
        raise ValueError("Select an operational Stonegate role.")
    role = db.scalar(
        select(Role).where(Role.organization_id == organization_id, Role.key == role_key)
    )
    if role is None:
        raise ValueError("The selected role is not available in this workspace.")
    return role


def list_teams(
    db: Session,
    principal: Principal,
    *,
    manageable: bool,
) -> list[TeamRead]:
    statement = select(Team).where(Team.organization_id == principal.organization_id)
    if not manageable:
        statement = statement.join(TeamMembership).where(
            TeamMembership.user_id == principal.user_id
        )
    teams = db.scalars(statement.order_by(Team.name)).unique().all()
    users = {
        user.id: user
        for user in db.scalars(
            select(User).where(User.organization_id == principal.organization_id)
        )
    }
    result: list[TeamRead] = []
    for team in teams:
        members = db.scalars(select(TeamMembership).where(TeamMembership.team_id == team.id)).all()
        result.append(
            TeamRead(
                id=team.id,
                name=team.name,
                team_type=team.team_type,
                manager_user_id=team.manager_user_id,
                manager_name=(
                    users[team.manager_user_id].display_name
                    if team.manager_user_id in users
                    else None
                ),
                is_active=team.is_active,
                members=[
                    TeamMemberRead(
                        user_id=membership.user_id,
                        display_name=users[membership.user_id].display_name,
                        email=users[membership.user_id].email,
                        membership_role=membership.membership_role,
                    )
                    for membership in members
                    if membership.user_id in users
                ],
            )
        )
    return result


def create_team(db: Session, principal: Principal, payload: TeamCreate) -> TeamRead:
    manager = None
    if payload.manager_user_id is not None:
        manager = get_active_user(db, principal.organization_id, payload.manager_user_id)
        if manager is None:
            raise ValueError("Team manager must be an active workspace user.")
    team = Team(
        organization_id=principal.organization_id,
        name=payload.name.strip(),
        team_type=payload.team_type,
        manager_user_id=manager.id if manager else None,
        is_active=True,
    )
    db.add(team)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("A team with this name already exists.") from exc
    if manager is not None:
        db.add(
            TeamMembership(
                organization_id=principal.organization_id,
                team_id=team.id,
                user_id=manager.id,
                membership_role="manager",
            )
        )
    audit(db, principal, "team.create", "team", team.id, None, {"name": team.name}, "Team created")
    db.commit()
    return next(item for item in list_teams(db, principal, manageable=True) if item.id == team.id)


def add_team_member(
    db: Session,
    principal: Principal,
    team_id: UUID,
    payload: TeamMemberCreate,
) -> TeamRead | None:
    team = db.scalar(
        select(Team).where(
            Team.organization_id == principal.organization_id,
            Team.id == team_id,
        )
    )
    if team is None:
        return None
    user = get_active_user(db, principal.organization_id, payload.user_id)
    if user is None:
        raise ValueError("Team member must be an active workspace user.")
    membership = db.scalar(
        select(TeamMembership).where(
            TeamMembership.team_id == team.id,
            TeamMembership.user_id == user.id,
        )
    )
    if membership is None:
        membership = TeamMembership(
            organization_id=principal.organization_id,
            team_id=team.id,
            user_id=user.id,
            membership_role=payload.membership_role,
        )
        db.add(membership)
    else:
        membership.membership_role = payload.membership_role
    if payload.membership_role == "manager":
        team.manager_user_id = user.id
    audit(
        db,
        principal,
        "team.member_upsert",
        "team",
        team.id,
        None,
        {"user_id": str(user.id), "membership_role": payload.membership_role},
        "Team membership updated",
    )
    db.commit()
    return next(item for item in list_teams(db, principal, manageable=True) if item.id == team.id)


def list_calling_lists(
    db: Session,
    principal: Principal,
    *,
    manageable: bool,
) -> list[CallingListRead]:
    statement = select(CallingList).where(CallingList.organization_id == principal.organization_id)
    if not manageable:
        statement = statement.join(CallingListEntry).where(
            CallingListEntry.assigned_user_id == principal.user_id
        )
    calling_lists = db.scalars(statement.order_by(CallingList.created_at.desc())).unique().all()
    result: list[CallingListRead] = []
    for calling_list in calling_lists:
        entry_statement = select(CallingListEntry).where(
            CallingListEntry.calling_list_id == calling_list.id
        )
        if not manageable:
            entry_statement = entry_statement.where(
                CallingListEntry.assigned_user_id == principal.user_id
            )
        entries = db.scalars(entry_statement.order_by(CallingListEntry.created_at)).all()
        entry_reads = [calling_list_entry_read(db, entry) for entry in entries]
        result.append(
            CallingListRead(
                id=calling_list.id,
                name=calling_list.name,
                description=calling_list.description,
                status=calling_list.status,
                default_assignee_user_id=calling_list.default_assignee_user_id,
                total_records=len(entry_reads),
                completed_records=sum(item.status == "completed" for item in entry_reads),
                interested_records=sum(
                    item.disposition in INTERESTED_DISPOSITIONS for item in entry_reads
                ),
                entries=entry_reads,
            )
        )
    return result


def calling_list_entry_read(db: Session, entry: CallingListEntry) -> CallingListEntryRead:
    lead = db.get(Lead, entry.lead_id)
    contact = db.get(Contact, lead.contact_id) if lead else None
    property_record = db.get(Property, lead.property_id) if lead else None
    assignee = db.get(User, entry.assigned_user_id) if entry.assigned_user_id else None
    return CallingListEntryRead(
        id=entry.id,
        lead_id=entry.lead_id,
        seller_name=contact.legal_name if contact else "Unknown seller",
        property_address=(
            f"{property_record.street_address}, {property_record.city}, {property_record.state}"
            if property_record
            else "Unknown property"
        ),
        assigned_user_id=entry.assigned_user_id,
        assigned_user_name=assignee.display_name if assignee else None,
        status=entry.status,
        attempt_count=entry.attempt_count,
        disposition=entry.disposition,
        notes=entry.notes,
        last_attempt_at=entry.last_attempt_at,
        completed_at=entry.completed_at,
    )


def create_calling_list(
    db: Session,
    principal: Principal,
    payload: CallingListCreate,
) -> CallingListRead:
    if payload.default_assignee_user_id and not get_active_user(
        db, principal.organization_id, payload.default_assignee_user_id
    ):
        raise ValueError("Default assignee must be an active workspace user.")
    calling_list = CallingList(
        organization_id=principal.organization_id,
        name=payload.name.strip(),
        description=payload.description,
        status="active",
        created_by_user_id=principal.user_id,
        default_assignee_user_id=payload.default_assignee_user_id,
    )
    db.add(calling_list)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("A calling list with this name already exists.") from exc
    audit(
        db,
        principal,
        "calling_list.create",
        "calling_list",
        calling_list.id,
        None,
        {"name": calling_list.name},
        "Calling list created",
    )
    db.commit()
    return next(
        item
        for item in list_calling_lists(db, principal, manageable=True)
        if item.id == calling_list.id
    )


def add_calling_list_leads(
    db: Session,
    principal: Principal,
    calling_list_id: UUID,
    payload: CallingListLeadAdd,
) -> CallingListRead | None:
    calling_list = db.scalar(
        select(CallingList).where(
            CallingList.organization_id == principal.organization_id,
            CallingList.id == calling_list_id,
        )
    )
    if calling_list is None:
        return None
    assignee_id = payload.assigned_user_id or calling_list.default_assignee_user_id
    assignee = get_active_user(db, principal.organization_id, assignee_id) if assignee_id else None
    if assignee_id and assignee is None:
        raise ValueError("Calling-list assignee must be an active workspace user.")
    for lead_id in payload.lead_ids:
        lead = db.scalar(
            select(Lead).where(
                Lead.organization_id == principal.organization_id,
                Lead.id == lead_id,
                Lead.archived_at.is_(None),
            )
        )
        if lead is None:
            raise ValueError(f"Lead {lead_id} is unavailable.")
        existing = db.scalar(
            select(CallingListEntry).where(
                CallingListEntry.calling_list_id == calling_list.id,
                CallingListEntry.lead_id == lead.id,
            )
        )
        if existing is not None:
            continue
        db.add(
            CallingListEntry(
                organization_id=principal.organization_id,
                calling_list_id=calling_list.id,
                lead_id=lead.id,
                assigned_user_id=assignee.id if assignee else None,
                status="new",
                attempt_count=0,
                disposition=None,
                notes=None,
                last_attempt_at=None,
                completed_at=None,
            )
        )
        if assignee is not None:
            assign_lead_for_prospecting(db, principal, lead, assignee)
    audit(
        db,
        principal,
        "calling_list.leads_add",
        "calling_list",
        calling_list.id,
        None,
        {
            "lead_ids": [str(value) for value in payload.lead_ids],
            "assignee_id": str(assignee_id) if assignee_id else None,
        },
        "Leads added to calling list",
    )
    db.commit()
    return next(
        item
        for item in list_calling_lists(db, principal, manageable=True)
        if item.id == calling_list.id
    )


def assign_lead_for_prospecting(
    db: Session,
    principal: Principal,
    lead: Lead,
    assignee: User,
) -> None:
    lead.assigned_user_id = assignee.id
    contact = db.get(Contact, lead.contact_id)
    if contact:
        contact.assigned_user_id = assignee.id
    conversation = ensure_primary_conversation(db, lead)
    conversation.assigned_user_id = assignee.id
    conversation.queue_key = "va_prospecting"
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            event_type="lead.assigned_to_calling_list",
            summary=f"Assigned to {assignee.display_name} for prospecting.",
        )
    )


def update_calling_list_entry(
    db: Session,
    principal: Principal,
    entry_id: UUID,
    payload: CallingListEntryUpdate,
) -> CallingListEntryRead | None:
    entry = db.scalar(
        select(CallingListEntry).where(
            CallingListEntry.organization_id == principal.organization_id,
            CallingListEntry.id == entry_id,
        )
    )
    if entry is None:
        return None
    if not can_manage_operations(principal) and entry.assigned_user_id != principal.user_id:
        raise PermissionError("You can update only calling-list records assigned to you.")
    previous = {
        "status": entry.status,
        "disposition": entry.disposition,
        "attempt_count": entry.attempt_count,
    }
    entry.status = payload.status
    entry.disposition = payload.disposition
    entry.notes = payload.notes
    entry.attempt_count += 1
    entry.last_attempt_at = datetime.now(UTC)
    entry.completed_at = datetime.now(UTC) if payload.status == "completed" else None
    if payload.disposition in INTERESTED_DISPOSITIONS:
        if payload.handoff_user_id is None:
            raise ValueError("Interested records require an acquisitions handoff owner.")
        lead = db.get(Lead, entry.lead_id)
        if lead is None:
            raise ValueError("The calling-list lead is no longer available.")
        conversation = ensure_primary_conversation(db, lead)
        handoff_conversation(
            db,
            principal,
            conversation.id,
            ConversationHandoffRequest(
                assigned_user_id=payload.handoff_user_id,
                queue_key="appointment_set"
                if payload.disposition == "appointment_set"
                else "qualified",
                reason=payload.notes or "Interested seller handed off from calling list.",
            ),
        )
        create_notification(
            db,
            organization_id=principal.organization_id,
            recipient_user_id=payload.handoff_user_id,
            notification_type="lead_handoff",
            title="Seller handoff received",
            body="An interested seller was handed off from the prospecting team.",
            entity_type="lead",
            entity_id=entry.lead_id,
            action_url=f"/os/leads/{entry.lead_id}",
            dedupe_key=f"calling-list-handoff:{entry.id}:{entry.attempt_count}",
        )
    audit(
        db,
        principal,
        "calling_list.entry_update",
        "calling_list_entry",
        entry.id,
        previous,
        {
            "status": entry.status,
            "disposition": entry.disposition,
            "attempt_count": entry.attempt_count,
        },
        "Calling attempt recorded",
    )
    refresh_calling_list_status(db, entry.calling_list_id)
    db.commit()
    return calling_list_entry_read(db, entry)


def refresh_calling_list_status(db: Session, calling_list_id: UUID) -> None:
    calling_list = db.get(CallingList, calling_list_id)
    if calling_list is None:
        return
    remaining = int(
        db.scalar(
            select(func.count())
            .select_from(CallingListEntry)
            .where(
                CallingListEntry.calling_list_id == calling_list.id,
                CallingListEntry.status != "completed",
            )
        )
        or 0
    )
    calling_list.status = "completed" if remaining == 0 else "active"


def list_saved_views(db: Session, principal: Principal) -> list[SavedViewRead]:
    views = db.scalars(
        select(SavedView)
        .where(
            SavedView.organization_id == principal.organization_id,
            or_(SavedView.owner_user_id == principal.user_id, SavedView.is_shared.is_(True)),
        )
        .order_by(SavedView.resource_type, SavedView.name)
    ).all()
    return [
        SavedViewRead(
            id=view.id,
            name=view.name,
            resource_type=view.resource_type,
            filters=view.filters,
            is_shared=view.is_shared,
            team_id=view.team_id,
        )
        for view in views
    ]


def create_saved_view(
    db: Session,
    principal: Principal,
    payload: SavedViewCreate,
) -> SavedViewRead:
    if payload.is_shared and not can_manage_operations(principal):
        raise PermissionError("Only acquisition managers can create shared views.")
    view = SavedView(
        organization_id=principal.organization_id,
        owner_user_id=principal.user_id,
        team_id=payload.team_id,
        resource_type=payload.resource_type,
        name=payload.name.strip(),
        filters=payload.filters,
        is_shared=payload.is_shared,
    )
    db.add(view)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("A saved view with this name already exists.") from exc
    return SavedViewRead(
        id=view.id,
        name=view.name,
        resource_type=view.resource_type,
        filters=view.filters,
        is_shared=view.is_shared,
        team_id=view.team_id,
    )


def list_notifications(db: Session, principal: Principal) -> list[NotificationRead]:
    notifications = db.scalars(
        select(Notification)
        .where(
            Notification.organization_id == principal.organization_id,
            Notification.recipient_user_id == principal.user_id,
        )
        .order_by(Notification.created_at.desc())
        .limit(30)
    ).all()
    return [notification_read(item) for item in notifications]


def notification_read(item: Notification) -> NotificationRead:
    return NotificationRead(
        id=item.id,
        notification_type=item.notification_type,
        title=item.title,
        body=item.body,
        entity_type=item.entity_type,
        entity_id=item.entity_id,
        action_url=item.action_url,
        read_at=item.read_at,
        created_at=item.created_at,
    )


def mark_notification_read(
    db: Session,
    principal: Principal,
    notification_id: UUID,
) -> NotificationRead | None:
    item = db.scalar(
        select(Notification).where(
            Notification.organization_id == principal.organization_id,
            Notification.recipient_user_id == principal.user_id,
            Notification.id == notification_id,
        )
    )
    if item is None:
        return None
    item.read_at = datetime.now(UTC)
    db.commit()
    return notification_read(item)


def create_notification(
    db: Session,
    *,
    organization_id: UUID,
    recipient_user_id: UUID | None,
    notification_type: str,
    title: str,
    body: str,
    entity_type: str | None,
    entity_id: UUID | None,
    action_url: str | None,
    dedupe_key: str,
) -> Notification | None:
    if recipient_user_id is None:
        return None
    existing = db.scalar(
        select(Notification).where(
            Notification.organization_id == organization_id,
            Notification.recipient_user_id == recipient_user_id,
            Notification.dedupe_key == dedupe_key,
        )
    )
    if existing is not None:
        return existing
    item = Notification(
        organization_id=organization_id,
        recipient_user_id=recipient_user_id,
        notification_type=notification_type,
        title=title,
        body=body,
        entity_type=entity_type,
        entity_id=entity_id,
        action_url=action_url,
        dedupe_key=dedupe_key,
        read_at=None,
    )
    db.add(item)
    db.flush()
    return item


def scan_duplicate_candidates(db: Session, principal: Principal) -> int:
    leads = db.scalars(
        select(Lead)
        .where(
            Lead.organization_id == principal.organization_id,
            Lead.archived_at.is_(None),
        )
        .order_by(Lead.created_at)
    ).all()
    created = 0
    for index, primary in enumerate(leads):
        for duplicate in leads[index + 1 :]:
            score, reasons = duplicate_score(db, primary, duplicate)
            if score < 40:
                continue
            existing = db.scalar(
                select(DuplicateCandidate).where(
                    DuplicateCandidate.organization_id == principal.organization_id,
                    DuplicateCandidate.primary_lead_id == primary.id,
                    DuplicateCandidate.duplicate_lead_id == duplicate.id,
                )
            )
            if existing is None:
                db.add(
                    DuplicateCandidate(
                        organization_id=principal.organization_id,
                        primary_lead_id=primary.id,
                        duplicate_lead_id=duplicate.id,
                        status="pending",
                        match_score=score,
                        match_reasons=reasons,
                        reviewed_by_user_id=None,
                        reviewed_at=None,
                        resolution_notes=None,
                    )
                )
                created += 1
            elif existing.status == "pending":
                existing.match_score = score
                existing.match_reasons = reasons
    db.commit()
    return created


def duplicate_score(db: Session, first: Lead, second: Lead) -> tuple[int, list[str]]:
    first_methods = contact_method_values(db, first.contact_id)
    second_methods = contact_method_values(db, second.contact_id)
    reasons: list[str] = []
    score = 0
    if first_methods["email"].intersection(second_methods["email"]):
        score += 45
        reasons.append("same email")
    if first_methods["phone"].intersection(second_methods["phone"]):
        score += 40
        reasons.append("same phone")
    first_property = db.get(Property, first.property_id)
    second_property = db.get(Property, second.property_id)
    if (
        first_property
        and second_property
        and first_property.normalized_address_key
        and first_property.normalized_address_key == second_property.normalized_address_key
    ):
        score += 35
        reasons.append("same property")
    return min(score, 100), reasons


def contact_method_values(db: Session, contact_id: UUID) -> dict[str, set[str]]:
    values = {"email": set(), "phone": set()}
    for method in db.scalars(select(ContactMethod).where(ContactMethod.contact_id == contact_id)):
        if method.method_type in values:
            values[method.method_type].add(method.normalized_value.lower())
    return values


def list_duplicate_candidates(
    db: Session,
    principal: Principal,
) -> list[DuplicateCandidateRead]:
    candidates = db.scalars(
        select(DuplicateCandidate)
        .where(
            DuplicateCandidate.organization_id == principal.organization_id,
            DuplicateCandidate.status == "pending",
        )
        .order_by(DuplicateCandidate.match_score.desc(), DuplicateCandidate.created_at)
    ).all()
    return [duplicate_candidate_read(db, candidate) for candidate in candidates]


def duplicate_candidate_read(db: Session, candidate: DuplicateCandidate) -> DuplicateCandidateRead:
    return DuplicateCandidateRead(
        id=candidate.id,
        primary_lead_id=candidate.primary_lead_id,
        duplicate_lead_id=candidate.duplicate_lead_id,
        primary_label=lead_label(db, candidate.primary_lead_id),
        duplicate_label=lead_label(db, candidate.duplicate_lead_id),
        status=candidate.status,
        match_score=candidate.match_score,
        match_reasons=candidate.match_reasons,
        resolution_notes=candidate.resolution_notes,
        created_at=candidate.created_at,
    )


def resolve_duplicate_candidate(
    db: Session,
    principal: Principal,
    candidate_id: UUID,
    payload: DuplicateResolution,
) -> DuplicateCandidateRead | None:
    candidate = db.scalar(
        select(DuplicateCandidate).where(
            DuplicateCandidate.organization_id == principal.organization_id,
            DuplicateCandidate.id == candidate_id,
            DuplicateCandidate.status == "pending",
        )
    )
    if candidate is None:
        return None
    candidate.reviewed_by_user_id = principal.user_id
    candidate.reviewed_at = datetime.now(UTC)
    candidate.resolution_notes = payload.notes
    if payload.action == "not_duplicate":
        candidate.status = "dismissed"
    else:
        merge_duplicate_lead(db, principal, candidate, payload.notes)
        candidate.status = "merged"
    audit(
        db,
        principal,
        "duplicate.resolve",
        "duplicate_candidate",
        candidate.id,
        {"status": "pending"},
        {"status": candidate.status, "action": payload.action},
        payload.notes,
    )
    db.commit()
    return duplicate_candidate_read(db, candidate)


def merge_duplicate_lead(
    db: Session,
    principal: Principal,
    candidate: DuplicateCandidate,
    notes: str,
) -> None:
    primary = db.get(Lead, candidate.primary_lead_id)
    duplicate = db.get(Lead, candidate.duplicate_lead_id)
    if primary is None or duplicate is None or duplicate.archived_at is not None:
        raise ValueError("Both active leads are required for a merge.")
    copied_fields: list[str] = []
    for field in (
        "motivation",
        "desired_timeline",
        "property_condition",
        "occupancy_status",
        "asking_price",
        "mortgage_balance",
    ):
        if not getattr(primary, field) and getattr(duplicate, field):
            setattr(primary, field, getattr(duplicate, field))
            copied_fields.append(field)
    primary_contact = db.get(Contact, primary.contact_id)
    duplicate_contact = db.get(Contact, duplicate.contact_id)
    copied_methods: list[str] = []
    if primary_contact and duplicate_contact:
        existing_values = {
            (item.method_type, item.normalized_value.lower())
            for item in db.scalars(
                select(ContactMethod).where(ContactMethod.contact_id == primary_contact.id)
            )
        }
        for method in db.scalars(
            select(ContactMethod).where(ContactMethod.contact_id == duplicate_contact.id)
        ):
            key = (method.method_type, method.normalized_value.lower())
            if key not in existing_values:
                db.add(
                    ContactMethod(
                        organization_id=principal.organization_id,
                        contact_id=primary_contact.id,
                        method_type=method.method_type,
                        value=method.value,
                        normalized_value=method.normalized_value,
                        is_primary=False,
                    )
                )
                copied_methods.append(method.method_type)
                existing_values.add(key)
    duplicate.archived_at = datetime.now(UTC)
    duplicate.stage_key = "merged_duplicate"
    db.add(
        LeadMergeEvent(
            organization_id=principal.organization_id,
            primary_lead_id=primary.id,
            duplicate_lead_id=duplicate.id,
            merged_by_user_id=principal.user_id,
            merge_strategy="canonical_archive",
            merge_snapshot={
                "copied_fields": copied_fields,
                "copied_contact_methods": copied_methods,
                "notes": notes,
                "duplicate_source": duplicate.source,
            },
        )
    )
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=primary.id,
            event_type="lead.duplicate_merged",
            summary=f"Duplicate record {duplicate.id} consolidated into this lead.",
        )
    )


def list_follow_up_plans(db: Session, principal: Principal) -> list[FollowUpPlanRead]:
    plans = db.scalars(
        select(FollowUpPlan)
        .where(FollowUpPlan.organization_id == principal.organization_id)
        .order_by(FollowUpPlan.name)
    ).all()
    return [follow_up_plan_read(db, plan) for plan in plans]


def follow_up_plan_read(db: Session, plan: FollowUpPlan) -> FollowUpPlanRead:
    active = int(
        db.scalar(
            select(func.count())
            .select_from(FollowUpEnrollment)
            .where(
                FollowUpEnrollment.follow_up_plan_id == plan.id,
                FollowUpEnrollment.status == "active",
            )
        )
        or 0
    )
    return FollowUpPlanRead(
        id=plan.id,
        name=plan.name,
        description=plan.description,
        status=plan.status,
        steps=plan.steps,
        active_enrollments=active,
    )


def create_follow_up_plan(
    db: Session,
    principal: Principal,
    payload: FollowUpPlanCreate,
) -> FollowUpPlanRead:
    plan = FollowUpPlan(
        organization_id=principal.organization_id,
        name=payload.name.strip(),
        description=payload.description,
        status="active",
        created_by_user_id=principal.user_id,
        steps=[step.model_dump(mode="json") for step in payload.steps],
    )
    db.add(plan)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("A follow-up plan with this name already exists.") from exc
    return follow_up_plan_read(db, plan)


def enroll_follow_up_plan(
    db: Session,
    principal: Principal,
    plan_id: UUID,
    payload: FollowUpEnrollmentCreate,
) -> FollowUpPlanRead | None:
    plan = db.scalar(
        select(FollowUpPlan).where(
            FollowUpPlan.organization_id == principal.organization_id,
            FollowUpPlan.id == plan_id,
            FollowUpPlan.status == "active",
        )
    )
    if plan is None:
        return None
    lead = db.scalar(
        select(Lead).where(
            Lead.organization_id == principal.organization_id,
            Lead.id == payload.lead_id,
            Lead.archived_at.is_(None),
        )
    )
    if lead is None:
        raise ValueError("Select an active seller lead.")
    existing = db.scalar(
        select(FollowUpEnrollment).where(
            FollowUpEnrollment.follow_up_plan_id == plan.id,
            FollowUpEnrollment.lead_id == lead.id,
            FollowUpEnrollment.status == "active",
        )
    )
    if existing is not None:
        raise ValueError("This lead is already active in the selected follow-up plan.")
    now = datetime.now(UTC)
    db.add(
        FollowUpEnrollment(
            organization_id=principal.organization_id,
            follow_up_plan_id=plan.id,
            lead_id=lead.id,
            enrolled_by_user_id=principal.user_id,
            status="active",
            started_at=now,
            completed_at=None,
            current_step=0,
        )
    )
    for index, step in enumerate(plan.steps):
        due_at = now + timedelta(days=int(step["delay_days"]))
        action_type = str(step["action_type"])
        title = str(step["title"])
        if action_type in {"task", "call"}:
            db.add(
                Task(
                    organization_id=principal.organization_id,
                    lead_id=lead.id,
                    responsible_user_id=lead.assigned_user_id,
                    task_type=f"follow_up_{action_type}",
                    title=title,
                    status="open",
                    priority="normal",
                    due_at=due_at,
                    completed_at=None,
                )
            )
        else:
            db.add(
                ApprovalRequest(
                    organization_id=principal.organization_id,
                    requested_by_user_id=principal.user_id,
                    assigned_to_user_id=lead.assigned_user_id,
                    request_type=f"follow_up_{action_type}",
                    entity_type="lead",
                    entity_id=lead.id,
                    status="pending",
                    title=title,
                    summary=str(step.get("body") or title),
                    decision_notes=None,
                    due_at=due_at,
                    decided_at=None,
                    approval_metadata={"plan_id": str(plan.id), "step_index": index},
                )
            )
    lead.next_follow_up_at = min(
        now + timedelta(days=int(step["delay_days"])) for step in plan.steps
    )
    create_notification(
        db,
        organization_id=principal.organization_id,
        recipient_user_id=lead.assigned_user_id,
        notification_type="follow_up_plan",
        title="Follow-up plan assigned",
        body=f"{plan.name} was assigned to {lead_label(db, lead.id)}.",
        entity_type="lead",
        entity_id=lead.id,
        action_url=f"/os/leads/{lead.id}",
        dedupe_key=f"follow-up-enrollment:{plan.id}:{lead.id}:{now.isoformat()}",
    )
    audit(
        db,
        principal,
        "follow_up.enroll",
        "lead",
        lead.id,
        None,
        {"plan_id": str(plan.id)},
        "Follow-up plan enrolled",
    )
    db.commit()
    return follow_up_plan_read(db, plan)


def list_operational_appointments(
    db: Session,
    principal: Principal,
    *,
    manageable: bool,
) -> list[AppointmentOperationsRead]:
    since = datetime.now(UTC) - timedelta(days=7)
    statement = select(Appointment).where(
        Appointment.organization_id == principal.organization_id,
        Appointment.scheduled_start_at >= since,
    )
    if not manageable:
        statement = statement.where(Appointment.owner_user_id == principal.user_id)
    appointments = db.scalars(statement.order_by(Appointment.scheduled_start_at).limit(100)).all()
    result: list[AppointmentOperationsRead] = []
    for appointment in appointments:
        contact = db.get(Contact, appointment.contact_id)
        property_record = db.get(Property, appointment.property_id)
        owner = db.get(User, appointment.owner_user_id) if appointment.owner_user_id else None
        calendar_event = db.scalar(
            select(CalendarEvent).where(
                CalendarEvent.appointment_id == appointment.id,
                CalendarEvent.provider == "internal",
            )
        )
        result.append(
            AppointmentOperationsRead(
                id=appointment.id,
                lead_id=appointment.lead_id,
                seller_name=contact.legal_name if contact else "Unknown seller",
                property_address=(
                    f"{property_record.street_address}, {property_record.city}, "
                    f"{property_record.state}"
                    if property_record
                    else "Unknown property"
                ),
                owner_user_id=appointment.owner_user_id,
                owner_name=owner.display_name if owner else None,
                appointment_type=appointment.appointment_type,
                status=appointment.status,
                scheduled_start_at=appointment.scheduled_start_at,
                scheduled_end_at=appointment.scheduled_end_at,
                outcome=appointment.outcome,
                calendar_status=calendar_event.status if calendar_event else "not_recorded",
            )
        )
    return result


def update_appointment(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    appointment_id: UUID,
    payload: LeadAppointmentUpdate,
) -> LeadDetail | None:
    lead = db.scalar(
        select(Lead).where(
            Lead.organization_id == principal.organization_id,
            Lead.id == lead_id,
        )
    )
    appointment = db.scalar(
        select(Appointment).where(
            Appointment.organization_id == principal.organization_id,
            Appointment.id == appointment_id,
            Appointment.lead_id == lead_id,
        )
    )
    if lead is None or appointment is None:
        return None
    if not can_manage_operations(principal) and appointment.owner_user_id != principal.user_id:
        raise PermissionError("Only the appointment owner or acquisition manager can update it.")
    if payload.status == "completed" and not payload.outcome:
        raise ValueError("Completed appointments require an outcome.")
    new_start = payload.scheduled_start_at or appointment.scheduled_start_at
    new_end = (
        payload.scheduled_end_at
        if payload.scheduled_end_at is not None
        else appointment.scheduled_end_at
    )
    if new_end is not None and new_end <= new_start:
        raise ValueError("Appointment end time must be after start time.")
    previous = {
        "status": appointment.status,
        "scheduled_start_at": appointment.scheduled_start_at.isoformat(),
        "outcome": appointment.outcome,
    }
    appointment.status = payload.status
    appointment.scheduled_start_at = new_start
    appointment.scheduled_end_at = new_end
    appointment.outcome = payload.outcome
    if payload.notes is not None:
        appointment.notes = payload.notes
    lead.appointment_status = payload.status
    if payload.status in {"scheduled", "rescheduled"}:
        lead.stage_key = "appointment_scheduled"
        lead.next_follow_up_at = new_start
    elif payload.status == "completed":
        lead.stage_key = "underwriting"
        lead.next_follow_up_at = payload.next_follow_up_at
    elif payload.status in {"cancelled", "no_show"}:
        lead.stage_key = "qualification_in_progress" if payload.status == "no_show" else "qualified"
        lead.next_follow_up_at = payload.next_follow_up_at or datetime.now(UTC) + timedelta(days=1)
        db.add(
            Task(
                organization_id=principal.organization_id,
                lead_id=lead.id,
                responsible_user_id=appointment.owner_user_id,
                task_type="appointment_recovery",
                title=f"Follow up after {payload.status.replace('_', ' ')} appointment",
                status="open",
                priority="high",
                due_at=lead.next_follow_up_at,
                completed_at=None,
            )
        )
    upsert_internal_calendar_event(db, appointment)
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            event_type=f"appointment.{payload.status}",
            summary=f"Appointment marked {payload.status.replace('_', ' ')}.",
        )
    )
    create_notification(
        db,
        organization_id=principal.organization_id,
        recipient_user_id=appointment.owner_user_id,
        notification_type="appointment_update",
        title="Appointment updated",
        body=f"{lead_label(db, lead.id)} was marked {payload.status.replace('_', ' ')}.",
        entity_type="appointment",
        entity_id=appointment.id,
        action_url=f"/os/leads/{lead.id}?tab=communications",
        dedupe_key=f"appointment-update:{appointment.id}:{payload.status}:{datetime.now(UTC).isoformat()}",
    )
    audit(
        db,
        principal,
        "appointment.update",
        "appointment",
        appointment.id,
        previous,
        {
            "status": appointment.status,
            "scheduled_start_at": appointment.scheduled_start_at.isoformat(),
            "outcome": appointment.outcome,
        },
        payload.reason,
    )
    db.commit()
    return get_lead_detail(db, principal, lead.id)


def upsert_internal_calendar_event(db: Session, appointment: Appointment) -> CalendarEvent:
    event = db.scalar(
        select(CalendarEvent).where(
            CalendarEvent.organization_id == appointment.organization_id,
            CalendarEvent.appointment_id == appointment.id,
            CalendarEvent.provider == "internal",
        )
    )
    payload = {
        "appointment_type": appointment.appointment_type,
        "status": appointment.status,
        "start": appointment.scheduled_start_at.isoformat(),
        "end": appointment.scheduled_end_at.isoformat() if appointment.scheduled_end_at else None,
        "location": appointment.location,
        "notes": appointment.notes,
    }
    if event is None:
        event = CalendarEvent(
            organization_id=appointment.organization_id,
            appointment_id=appointment.id,
            owner_user_id=appointment.owner_user_id,
            provider="internal",
            external_event_id=None,
            status=appointment.status,
            event_payload=payload,
            last_error=None,
            synced_at=None,
        )
        db.add(event)
    else:
        event.owner_user_id = appointment.owner_user_id
        event.status = appointment.status
        event.event_payload = payload
    return event


def process_next_acquisition_reminder(db: Session, _settings: Settings) -> UUID | None:
    now = datetime.now(UTC)
    appointments = db.scalars(
        select(Appointment)
        .where(
            Appointment.status.in_(("scheduled", "rescheduled")),
            Appointment.scheduled_start_at >= now,
            Appointment.scheduled_start_at <= now + timedelta(hours=24),
            Appointment.owner_user_id.is_not(None),
        )
        .order_by(Appointment.scheduled_start_at)
        .limit(100)
    ).all()
    for appointment in appointments:
        if appointment.owner_user_id is None:
            continue
        dedupe_key = f"appointment-24h:{appointment.id}"
        if notification_exists(
            db,
            appointment.organization_id,
            appointment.owner_user_id,
            dedupe_key,
        ):
            continue
        item = create_notification(
            db,
            organization_id=appointment.organization_id,
            recipient_user_id=appointment.owner_user_id,
            notification_type="appointment_reminder",
            title="Appointment within 24 hours",
            body=f"Prepare for the {appointment.appointment_type.replace('_', ' ')} appointment.",
            entity_type="appointment",
            entity_id=appointment.id,
            action_url=f"/os/leads/{appointment.lead_id}?tab=communications",
            dedupe_key=dedupe_key,
        )
        if item is not None:
            db.commit()
            return item.id
    overdue_tasks = db.scalars(
        select(Task)
        .where(
            Task.status.in_(("open", "in_progress")),
            Task.due_at < now,
            Task.responsible_user_id.is_not(None),
        )
        .order_by(Task.due_at)
        .limit(100)
    ).all()
    for overdue_task in overdue_tasks:
        if overdue_task.responsible_user_id is None:
            continue
        dedupe_key = f"overdue-task:{overdue_task.id}"
        if notification_exists(
            db,
            overdue_task.organization_id,
            overdue_task.responsible_user_id,
            dedupe_key,
        ):
            continue
        item = create_notification(
            db,
            organization_id=overdue_task.organization_id,
            recipient_user_id=overdue_task.responsible_user_id,
            notification_type="overdue_task",
            title="Follow-up task overdue",
            body=overdue_task.title,
            entity_type="task",
            entity_id=overdue_task.id,
            action_url=(
                f"/os/leads/{overdue_task.lead_id}" if overdue_task.lead_id else "/os/tasks"
            ),
            dedupe_key=dedupe_key,
        )
        if item is not None:
            db.commit()
            return item.id
    db.commit()
    return None


def get_active_user(db: Session, organization_id: UUID, user_id: UUID | None) -> User | None:
    if user_id is None:
        return None
    return db.scalar(
        select(User).where(
            User.organization_id == organization_id,
            User.id == user_id,
            User.is_active.is_(True),
        )
    )


def notification_exists(
    db: Session,
    organization_id: UUID,
    recipient_user_id: UUID,
    dedupe_key: str,
) -> bool:
    return (
        db.scalar(
            select(Notification.id).where(
                Notification.organization_id == organization_id,
                Notification.recipient_user_id == recipient_user_id,
                Notification.dedupe_key == dedupe_key,
            )
        )
        is not None
    )


def lead_label(db: Session, lead_id: UUID) -> str:
    lead = db.get(Lead, lead_id)
    if lead is None:
        return "Unknown lead"
    contact = db.get(Contact, lead.contact_id)
    property_record = db.get(Property, lead.property_id)
    seller = contact.legal_name if contact else "Unknown seller"
    address = property_record.street_address if property_record else "unknown property"
    return f"{seller} at {address}"


def audit(
    db: Session,
    principal: Principal,
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
