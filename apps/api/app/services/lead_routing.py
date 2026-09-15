from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.foundation import (
    ActivityEvent,
    Appointment,
    AuditEvent,
    Contact,
    Conversation,
    ConversationAssignmentEvent,
    ConversationWatcher,
    Lead,
    Role,
    RoleAssignment,
    Task,
    Team,
    TeamMembership,
    User,
)

INITIAL_OWNER_STAGES = frozenset(
    {
        "new",
        "contact_attempt_due",
        "attempting_contact",
        "contacted",
        "qualification_in_progress",
        "long_term_follow_up",
        "reopened",
    }
)
QUALIFIED_OWNER_STAGES = frozenset(
    {
        "qualified",
        "appointment_scheduling",
        "appointment_scheduled",
        "underwriting",
        "offer_pending_approval",
        "offer_ready",
        "offer_presented",
        "negotiating",
        "under_contract",
    }
)


@dataclass(frozen=True)
class AcquisitionRouting:
    team_id: UUID
    team_name: str
    initial_owner_id: UUID
    initial_owner_name: str
    qualified_owner_id: UUID
    qualified_owner_name: str


@dataclass(frozen=True)
class AcquisitionRebalanceResult:
    initial_owner_name: str
    qualified_owner_name: str
    reassigned_to_initial: int
    reassigned_to_qualified: int

    @property
    def reassigned_total(self) -> int:
        return self.reassigned_to_initial + self.reassigned_to_qualified


def resolve_acquisition_routing(
    db: Session,
    organization_id: UUID,
    *,
    team_id: UUID | None = None,
) -> AcquisitionRouting | None:
    statement = select(Team).where(
        Team.organization_id == organization_id,
        Team.team_type == "acquisitions",
        Team.is_active.is_(True),
    )
    if team_id is not None:
        statement = statement.where(Team.id == team_id)
    team = db.scalar(
        statement.order_by(
            case((func.lower(Team.name) == "acquisitions", 0), else_=1),
            Team.created_at,
            Team.id,
        )
    )
    if team is None:
        return None

    member_rows = db.execute(
        select(TeamMembership, User)
        .join(User, User.id == TeamMembership.user_id)
        .where(
            TeamMembership.organization_id == organization_id,
            TeamMembership.team_id == team.id,
            User.organization_id == organization_id,
            User.is_active.is_(True),
        )
        .order_by(TeamMembership.created_at, TeamMembership.id)
    ).all()
    if not member_rows:
        return None

    role_keys: dict[UUID, set[str]] = {}
    for user_id, role_key in db.execute(
        select(RoleAssignment.user_id, Role.key)
        .join(Role, Role.id == RoleAssignment.role_id)
        .where(
            RoleAssignment.organization_id == organization_id,
            RoleAssignment.user_id.in_([user.id for _, user in member_rows]),
        )
    ):
        role_keys.setdefault(user_id, set()).add(role_key)

    manager = next(
        (user for _, user in member_rows if user.id == team.manager_user_id),
        None,
    )
    if manager is None:
        manager = next(
            (
                user
                for membership, user in member_rows
                if membership.membership_role == "manager"
                and "acquisition_manager" in role_keys.get(user.id, set())
            ),
            None,
        )
    if manager is None:
        manager = next(
            (user for membership, user in member_rows if membership.membership_role == "manager"),
            None,
        )

    initial_owner = next(
        (
            user
            for _, user in member_rows
            if "acquisition_rep" in role_keys.get(user.id, set())
        ),
        None,
    )
    if initial_owner is None:
        initial_owner = next(
            (user for membership, user in member_rows if membership.membership_role == "member"),
            None,
        )

    qualified_owner = manager or initial_owner
    initial_owner = initial_owner or manager
    if initial_owner is None or qualified_owner is None:
        return None
    return AcquisitionRouting(
        team_id=team.id,
        team_name=team.name,
        initial_owner_id=initial_owner.id,
        initial_owner_name=initial_owner.display_name,
        qualified_owner_id=qualified_owner.id,
        qualified_owner_name=qualified_owner.display_name,
    )


def routed_owner_id(routing: AcquisitionRouting, stage_key: str) -> UUID | None:
    if stage_key in INITIAL_OWNER_STAGES:
        return routing.initial_owner_id
    if stage_key in QUALIFIED_OWNER_STAGES:
        return routing.qualified_owner_id
    return None


def apply_acquisition_stage_routing(
    db: Session,
    lead: Lead,
    *,
    actor_user_id: UUID | None,
    reason: str,
    force: bool = False,
    team_id: UUID | None = None,
) -> bool:
    routing = resolve_acquisition_routing(db, lead.organization_id, team_id=team_id)
    if routing is None:
        return False
    desired_owner_id = routed_owner_id(routing, lead.stage_key)
    if desired_owner_id is None:
        return False

    current_owner = db.get(User, lead.assigned_user_id) if lead.assigned_user_id else None
    if not force and current_owner is not None and current_owner.is_active:
        is_expected_handoff = (
            desired_owner_id == routing.qualified_owner_id
            and lead.assigned_user_id == routing.initial_owner_id
        )
        if lead.assigned_user_id != desired_owner_id and not is_expected_handoff:
            return False

    owner_changed = lead.assigned_user_id != desired_owner_id
    previous_owner_id = lead.assigned_user_id
    lead.assigned_user_id = desired_owner_id
    contact = db.get(Contact, lead.contact_id)
    if contact is not None:
        contact.assigned_user_id = desired_owner_id

    conversation = db.scalar(
        select(Conversation).where(
            Conversation.organization_id == lead.organization_id,
            Conversation.lead_id == lead.id,
        )
    )
    if conversation is not None:
        previous_conversation_owner = conversation.assigned_user_id
        conversation.assigned_user_id = desired_owner_id
        conversation.assigned_team_id = routing.team_id
        if owner_changed or previous_conversation_owner != desired_owner_id:
            db.add(
                ConversationAssignmentEvent(
                    organization_id=lead.organization_id,
                    conversation_id=conversation.id,
                    lead_id=lead.id,
                    actor_user_id=actor_user_id,
                    previous_assigned_user_id=previous_conversation_owner,
                    assigned_user_id=desired_owner_id,
                    previous_queue_key=conversation.queue_key,
                    queue_key=conversation.queue_key,
                    reason=reason,
                    created_at=datetime.now(UTC),
                )
            )
        watcher = db.scalar(
            select(ConversationWatcher).where(
                ConversationWatcher.organization_id == lead.organization_id,
                ConversationWatcher.conversation_id == conversation.id,
                ConversationWatcher.user_id == desired_owner_id,
            )
        )
        if watcher is None:
            db.add(
                ConversationWatcher(
                    organization_id=lead.organization_id,
                    conversation_id=conversation.id,
                    user_id=desired_owner_id,
                    source="acquisitions_routing",
                    notification_level="all",
                    is_muted=False,
                )
            )

    for task in db.scalars(
        select(Task).where(
            Task.organization_id == lead.organization_id,
            Task.lead_id == lead.id,
            Task.status.in_(("open", "in_progress")),
        )
    ):
        task.responsible_user_id = desired_owner_id
    for appointment in db.scalars(
        select(Appointment).where(
            Appointment.organization_id == lead.organization_id,
            Appointment.lead_id == lead.id,
            Appointment.status.in_(("scheduled", "rescheduled")),
        )
    ):
        appointment.owner_user_id = desired_owner_id

    if owner_changed:
        desired_owner_name = (
            routing.initial_owner_name
            if desired_owner_id == routing.initial_owner_id
            else routing.qualified_owner_name
        )
        db.add(
            ActivityEvent(
                organization_id=lead.organization_id,
                actor_user_id=actor_user_id,
                entity_type="lead",
                entity_id=lead.id,
                event_type="lead.owner_routed",
                summary=f"Lead ownership routed to {desired_owner_name}.",
            )
        )
        db.add(
            AuditEvent(
                organization_id=lead.organization_id,
                actor_user_id=actor_user_id,
                actor_type="user" if actor_user_id else "system",
                action="lead.owner_route",
                entity_type="lead",
                entity_id=lead.id,
                previous_value={
                    "assigned_user_id": str(previous_owner_id) if previous_owner_id else None,
                },
                new_value={
                    "assigned_user_id": str(desired_owner_id),
                    "assigned_team_id": str(routing.team_id),
                    "stage_key": lead.stage_key,
                },
                reason=reason,
            )
        )
    return owner_changed


def rebalance_inactive_acquisition_leads(
    db: Session,
    organization_id: UUID,
    *,
    actor_user_id: UUID,
    team_id: UUID,
) -> AcquisitionRebalanceResult:
    routing = resolve_acquisition_routing(db, organization_id, team_id=team_id)
    if routing is None:
        raise ValueError(
            "Set one active Acquisitions rep and one active team manager before applying routing."
        )
    active_user_ids = set(
        db.scalars(
            select(User.id).where(
                User.organization_id == organization_id,
                User.is_active.is_(True),
            )
        )
    )
    initial_count = 0
    qualified_count = 0
    leads = db.scalars(
        select(Lead).where(
            Lead.organization_id == organization_id,
            Lead.archived_at.is_(None),
            Lead.stage_key.not_in(("dead", "disqualified", "closed")),
        )
    ).all()
    for lead in leads:
        if lead.assigned_user_id in active_user_ids:
            continue
        desired_owner_id = routed_owner_id(routing, lead.stage_key)
        if desired_owner_id is None:
            continue
        changed = apply_acquisition_stage_routing(
            db,
            lead,
            actor_user_id=actor_user_id,
            reason="Inactive or unassigned seller lead routed from People & Access.",
            force=True,
            team_id=team_id,
        )
        if not changed:
            continue
        if desired_owner_id == routing.initial_owner_id:
            initial_count += 1
        else:
            qualified_count += 1
    db.commit()
    return AcquisitionRebalanceResult(
        initial_owner_name=routing.initial_owner_name,
        qualified_owner_name=routing.qualified_owner_name,
        reassigned_to_initial=initial_count,
        reassigned_to_qualified=qualified_count,
    )
