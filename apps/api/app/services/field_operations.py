from datetime import UTC, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.domain.rbac import PermissionKeys
from app.models.foundation import (
    ActivityEvent,
    Appointment,
    AppointmentDispatchRecord,
    AuditEvent,
    CalendarEvent,
    CloserAvailabilityBlock,
    CloserDispatchProfile,
    CloserTerritoryCoverage,
    Contact,
    FieldInspection,
    FieldMeetingBrief,
    FieldNegotiationSession,
    Lead,
    LeadManagementCase,
    Market,
    Notification,
    Property,
    Role,
    RoleAssignment,
    Territory,
    User,
)
from app.schemas.field_operations import (
    AppointmentDispatchCreate,
    AppointmentDispatchRead,
    CloserAvailabilityBlockCreate,
    CloserAvailabilityBlockRead,
    CloserProfileRead,
    CloserProfileUpsert,
    DispatchAppointmentRead,
    DispatchCandidateRead,
    DispatchLeadRead,
    DispatchSlotEvaluation,
    DispatchSlotRequest,
    DispatchTerritoryRead,
    DispatchUserRead,
    FieldCloserScorecardRead,
    FieldOperationsMetrics,
    FieldOperationsOverview,
)

ELIGIBLE_CLOSER_ROLES = {
    "administrator",
    "owner",
    "founder_operator",
    "acquisition_manager",
    "acquisition_rep",
}
ACTIVE_APPOINTMENT_STATUSES = {"scheduled", "rescheduled"}
READY_TO_SCHEDULE_STAGES = {
    "qualified",
    "appointment_set",
    "appointment_scheduling",
    "qualification_complete",
}


def can_manage(principal: Principal) -> bool:
    return PermissionKeys.MANAGE_ACQUISITION_OPERATIONS in principal.permission_keys


def utc_value(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def resolve_timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown timezone: {name}") from exc


def eligible_closer_users(db: Session, organization_id: UUID) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .join(RoleAssignment, RoleAssignment.user_id == User.id)
            .join(Role, Role.id == RoleAssignment.role_id)
            .where(
                User.organization_id == organization_id,
                User.is_active.is_(True),
                Role.key.in_(ELIGIBLE_CLOSER_ROLES),
            )
            .distinct()
            .order_by(User.display_name)
        )
    )


def profile_read(db: Session, profile: CloserDispatchProfile) -> CloserProfileRead:
    user = db.get(User, profile.user_id)
    coverage = list(
        db.scalars(
            select(CloserTerritoryCoverage).where(
                CloserTerritoryCoverage.organization_id == profile.organization_id,
                CloserTerritoryCoverage.dispatch_profile_id == profile.id,
            )
        )
    )
    territory_ids = [item.territory_id for item in coverage]
    territory_names = [
        territory.name
        for territory_id in territory_ids
        if (territory := db.get(Territory, territory_id)) is not None
    ]
    blocks = list(
        db.scalars(
            select(CloserAvailabilityBlock)
            .where(
                CloserAvailabilityBlock.organization_id == profile.organization_id,
                CloserAvailabilityBlock.dispatch_profile_id == profile.id,
                CloserAvailabilityBlock.ends_at >= datetime.now(UTC) - timedelta(days=1),
            )
            .order_by(CloserAvailabilityBlock.starts_at)
        )
    )
    return CloserProfileRead(
        id=profile.id,
        user_id=profile.user_id,
        user_name=user.display_name if user else "Inactive user",
        timezone=profile.timezone,
        working_days=list(profile.working_days),
        workday_start_minute=profile.workday_start_minute,
        workday_end_minute=profile.workday_end_minute,
        daily_capacity=profile.daily_capacity,
        default_appointment_minutes=profile.default_appointment_minutes,
        travel_buffer_minutes=profile.travel_buffer_minutes,
        home_base_postal_code=profile.home_base_postal_code,
        territory_enforcement_enabled=profile.territory_enforcement_enabled,
        is_active=profile.is_active,
        territory_ids=territory_ids,
        territory_names=territory_names,
        blocks=[
            CloserAvailabilityBlockRead(
                id=block.id,
                block_type=block.block_type,
                starts_at=block.starts_at,
                ends_at=block.ends_at,
                reason=block.reason,
            )
            for block in blocks
        ],
    )


def get_overview(db: Session, principal: Principal) -> FieldOperationsOverview:
    users = eligible_closer_users(db, principal.organization_id)
    profiles = list(
        db.scalars(
            select(CloserDispatchProfile)
            .where(CloserDispatchProfile.organization_id == principal.organization_id)
            .order_by(CloserDispatchProfile.created_at)
        )
    )
    if not can_manage(principal):
        users = [user for user in users if user.id == principal.user_id]
        profiles = [profile for profile in profiles if profile.user_id == principal.user_id]
    profile_user_ids = {profile.user_id for profile in profiles}
    territories = list(
        db.scalars(
            select(Territory)
            .where(
                Territory.organization_id == principal.organization_id,
                Territory.status == "active",
            )
            .order_by(Territory.name)
        )
    )
    territory_reads: list[DispatchTerritoryRead] = []
    for territory in territories:
        market = db.get(Market, territory.market_id)
        territory_reads.append(
            DispatchTerritoryRead(
                id=territory.id,
                name=territory.name,
                market_name=market.name if market else "Unknown market",
                county_names=list(territory.county_names),
                postal_codes=list(territory.postal_codes),
            )
        )

    ready_leads = list_ready_leads(db, principal)
    appointments = list_upcoming_appointments(db, principal)
    now = datetime.now(UTC)
    today_count = sum(item.scheduled_start_at.date() == now.date() for item in appointments)
    active_profiles = [profile for profile in profiles if profile.is_active]
    at_capacity = 0
    for profile in active_profiles:
        count = appointment_count_for_local_day(db, profile, now)
        if count >= profile.daily_capacity:
            at_capacity += 1
    return FieldOperationsOverview(
        can_manage=can_manage(principal),
        metrics=FieldOperationsMetrics(
            ready_to_schedule=len(ready_leads),
            appointments_today=today_count,
            unassigned_today=sum(
                item.scheduled_start_at.date() == now.date() and item.closer_name == "Unassigned"
                for item in appointments
            ),
            at_capacity_today=at_capacity,
        ),
        users=[
            DispatchUserRead(
                id=user.id,
                name=user.display_name,
                email=user.email,
                profile_configured=user.id in profile_user_ids,
            )
            for user in users
        ],
        profiles=[profile_read(db, profile) for profile in profiles],
        territories=territory_reads,
        ready_leads=ready_leads,
        upcoming_appointments=appointments,
        scorecards=field_scorecards(db, principal, users),
    )


def field_scorecards(
    db: Session, principal: Principal, users: list[User]
) -> list[FieldCloserScorecardRead]:
    period_start = datetime.now(UTC) - timedelta(days=30)
    result: list[FieldCloserScorecardRead] = []
    for user in users:
        appointments = list(
            db.scalars(
                select(Appointment).where(
                    Appointment.organization_id == principal.organization_id,
                    Appointment.owner_user_id == user.id,
                    Appointment.scheduled_start_at >= period_start,
                )
            )
        )
        appointment_ids = [item.id for item in appointments]
        if appointment_ids:
            briefs = int(
                db.scalar(
                    select(func.count(func.distinct(FieldMeetingBrief.appointment_id))).where(
                        FieldMeetingBrief.appointment_id.in_(appointment_ids)
                    )
                )
                or 0
            )
            submitted_inspections = int(
                db.scalar(
                    select(func.count(FieldInspection.id)).where(
                        FieldInspection.appointment_id.in_(appointment_ids),
                        FieldInspection.status.in_(("submitted", "reviewed")),
                    )
                )
                or 0
            )
            negotiations = list(
                db.scalars(
                    select(FieldNegotiationSession).where(
                        FieldNegotiationSession.appointment_id.in_(appointment_ids),
                        FieldNegotiationSession.outcome != "pending",
                    )
                )
            )
        else:
            briefs = 0
            submitted_inspections = 0
            negotiations = []
        assigned = len(appointments)
        outcomes = len(negotiations)
        result.append(
            FieldCloserScorecardRead(
                user_id=user.id,
                user_name=user.display_name,
                assigned_appointments=assigned,
                briefs_prepared=briefs,
                inspections_submitted=submitted_inspections,
                outcomes_recorded=outcomes,
                accepted_outcomes=sum(item.outcome == "accepted" for item in negotiations),
                follow_up_outcomes=sum(
                    item.outcome in {"follow_up", "not_decided"} for item in negotiations
                ),
                declined_outcomes=sum(item.outcome == "declined" for item in negotiations),
                preparation_rate_basis_points=round(briefs * 10_000 / assigned) if assigned else 0,
                documentation_rate_basis_points=round(outcomes * 10_000 / assigned)
                if assigned
                else 0,
            )
        )
    return result


def list_ready_leads(db: Session, principal: Principal) -> list[DispatchLeadRead]:
    organization_id = principal.organization_id
    scheduled_lead_ids = select(Appointment.lead_id).where(
        Appointment.organization_id == organization_id,
        Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES),
        Appointment.scheduled_start_at >= datetime.now(UTC) - timedelta(hours=2),
    )
    statement = select(Lead).where(
        Lead.organization_id == organization_id,
        Lead.archived_at.is_(None),
        Lead.stage_key.in_(READY_TO_SCHEDULE_STAGES),
        Lead.id.not_in(scheduled_lead_ids),
    )
    if not can_manage(principal):
        statement = statement.where(Lead.assigned_user_id == principal.user_id)
    leads = list(
        db.scalars(
            statement.order_by(Lead.next_follow_up_at.asc().nulls_last(), Lead.created_at).limit(
                100
            )
        )
    )
    result: list[DispatchLeadRead] = []
    for lead in leads:
        contact = db.get(Contact, lead.contact_id)
        property_record = db.get(Property, lead.property_id)
        owner = db.get(User, lead.assigned_user_id) if lead.assigned_user_id else None
        if property_record is None:
            continue
        result.append(
            DispatchLeadRead(
                id=lead.id,
                seller_name=contact.legal_name if contact else "Unknown seller",
                property_address=(
                    f"{property_record.street_address}, {property_record.city}, "
                    f"{property_record.state} {property_record.postal_code}"
                ),
                county=property_record.county,
                postal_code=property_record.postal_code,
                stage_key=lead.stage_key,
                current_owner_name=owner.display_name if owner else None,
                next_follow_up_at=lead.next_follow_up_at,
                lead_url=f"/os/leads/{lead.id}",
            )
        )
    return result


def list_upcoming_appointments(db: Session, principal: Principal) -> list[DispatchAppointmentRead]:
    statement = select(Appointment).where(
        Appointment.organization_id == principal.organization_id,
        Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES),
        Appointment.scheduled_start_at >= datetime.now(UTC) - timedelta(hours=2),
    )
    if not can_manage(principal):
        statement = statement.where(Appointment.owner_user_id == principal.user_id)
    appointments = list(db.scalars(statement.order_by(Appointment.scheduled_start_at).limit(100)))
    result: list[DispatchAppointmentRead] = []
    for appointment in appointments:
        contact = db.get(Contact, appointment.contact_id)
        property_record = db.get(Property, appointment.property_id)
        owner = db.get(User, appointment.owner_user_id) if appointment.owner_user_id else None
        dispatch = db.scalar(
            select(AppointmentDispatchRecord)
            .where(AppointmentDispatchRecord.appointment_id == appointment.id)
            .order_by(AppointmentDispatchRecord.created_at.desc())
        )
        result.append(
            DispatchAppointmentRead(
                id=appointment.id,
                lead_id=appointment.lead_id,
                seller_name=contact.legal_name if contact else "Unknown seller",
                property_address=(
                    f"{property_record.street_address}, {property_record.city}, "
                    f"{property_record.state}"
                    if property_record
                    else "Unknown property"
                ),
                closer_name=owner.display_name if owner else "Unassigned",
                status=appointment.status,
                scheduled_start_at=appointment.scheduled_start_at,
                scheduled_end_at=appointment.scheduled_end_at,
                decision_status=dispatch.decision_status if dispatch else None,
                violations=list(dispatch.violations) if dispatch else [],
                lead_url=f"/os/leads/{appointment.lead_id}",
            )
        )
    return result


def upsert_profile(
    db: Session,
    principal: Principal,
    user_id: UUID,
    payload: CloserProfileUpsert,
) -> CloserProfileRead | None:
    user = db.scalar(
        select(User).where(
            User.id == user_id,
            User.organization_id == principal.organization_id,
            User.is_active.is_(True),
        )
    )
    if user is None:
        return None
    if user.id not in {item.id for item in eligible_closer_users(db, principal.organization_id)}:
        raise ValueError("Only an active acquisitions or management user can be a closer.")
    resolve_timezone(payload.timezone)
    territory_ids = set(payload.territory_ids)
    valid_territory_ids = set(
        db.scalars(
            select(Territory.id).where(
                Territory.organization_id == principal.organization_id,
                Territory.id.in_(territory_ids),
            )
        )
    )
    if territory_ids != valid_territory_ids:
        raise ValueError("One or more territories are not available in this workspace.")

    profile = db.scalar(
        select(CloserDispatchProfile).where(
            CloserDispatchProfile.organization_id == principal.organization_id,
            CloserDispatchProfile.user_id == user_id,
        )
    )
    previous = profile_snapshot(profile) if profile else None
    if profile is None:
        profile = CloserDispatchProfile(organization_id=principal.organization_id, user_id=user_id)
        db.add(profile)
    profile.timezone = payload.timezone
    profile.working_days = payload.working_days
    profile.workday_start_minute = payload.workday_start_minute
    profile.workday_end_minute = payload.workday_end_minute
    profile.daily_capacity = payload.daily_capacity
    profile.default_appointment_minutes = payload.default_appointment_minutes
    profile.travel_buffer_minutes = payload.travel_buffer_minutes
    profile.home_base_postal_code = payload.home_base_postal_code
    profile.territory_enforcement_enabled = payload.territory_enforcement_enabled
    profile.is_active = payload.is_active
    db.flush()
    existing = list(
        db.scalars(
            select(CloserTerritoryCoverage).where(
                CloserTerritoryCoverage.dispatch_profile_id == profile.id
            )
        )
    )
    for coverage in existing:
        db.delete(coverage)
    for territory_id in territory_ids:
        db.add(
            CloserTerritoryCoverage(
                organization_id=principal.organization_id,
                dispatch_profile_id=profile.id,
                territory_id=territory_id,
            )
        )
    audit(
        db,
        principal,
        "field_operations.profile_upsert",
        "closer_dispatch_profile",
        profile.id,
        previous,
        profile_snapshot(profile) | {"territory_ids": [str(item) for item in territory_ids]},
        "Closer dispatch configuration updated",
    )
    db.commit()
    return profile_read(db, profile)


def add_availability_block(
    db: Session,
    principal: Principal,
    profile_id: UUID,
    payload: CloserAvailabilityBlockCreate,
) -> CloserAvailabilityBlockRead | None:
    profile = db.scalar(
        select(CloserDispatchProfile).where(
            CloserDispatchProfile.id == profile_id,
            CloserDispatchProfile.organization_id == principal.organization_id,
        )
    )
    if profile is None:
        return None
    block = CloserAvailabilityBlock(
        organization_id=principal.organization_id,
        dispatch_profile_id=profile.id,
        block_type=payload.block_type,
        starts_at=utc_value(payload.starts_at),
        ends_at=utc_value(payload.ends_at),
        reason=payload.reason,
        created_by_user_id=principal.user_id,
    )
    db.add(block)
    db.flush()
    audit(
        db,
        principal,
        "field_operations.block_create",
        "closer_availability_block",
        block.id,
        None,
        {
            "profile_id": str(profile.id),
            "starts_at": block.starts_at.isoformat(),
            "ends_at": block.ends_at.isoformat(),
            "reason": block.reason,
        },
        "Closer unavailable time added",
    )
    db.commit()
    return CloserAvailabilityBlockRead(
        id=block.id,
        block_type=block.block_type,
        starts_at=block.starts_at,
        ends_at=block.ends_at,
        reason=block.reason,
    )


def delete_availability_block(db: Session, principal: Principal, block_id: UUID) -> bool:
    block = db.scalar(
        select(CloserAvailabilityBlock).where(
            CloserAvailabilityBlock.id == block_id,
            CloserAvailabilityBlock.organization_id == principal.organization_id,
        )
    )
    if block is None:
        return False
    snapshot: dict[str, object] = {
        "profile_id": str(block.dispatch_profile_id),
        "starts_at": block.starts_at.isoformat(),
        "ends_at": block.ends_at.isoformat(),
        "reason": block.reason,
    }
    db.delete(block)
    audit(
        db,
        principal,
        "field_operations.block_delete",
        "closer_availability_block",
        block.id,
        snapshot,
        {"deleted": True},
        "Closer unavailable time removed",
    )
    db.commit()
    return True


def evaluate_slot(
    db: Session, principal: Principal, payload: DispatchSlotRequest
) -> DispatchSlotEvaluation | None:
    lead = db.scalar(
        select(Lead).where(
            Lead.id == payload.lead_id,
            Lead.organization_id == principal.organization_id,
            Lead.archived_at.is_(None),
        )
    )
    if lead is None:
        return None
    if not can_manage(principal) and lead.assigned_user_id != principal.user_id:
        raise PermissionError("Only the assigned closer can schedule this lead.")
    start = utc_value(payload.scheduled_start_at)
    end = (
        utc_value(payload.scheduled_end_at)
        if payload.scheduled_end_at
        else start + timedelta(minutes=90)
    )
    territory = resolve_lead_territory(db, lead)
    profiles = list(
        db.scalars(
            select(CloserDispatchProfile)
            .where(
                CloserDispatchProfile.organization_id == principal.organization_id,
                CloserDispatchProfile.is_active.is_(True),
            )
            .order_by(CloserDispatchProfile.created_at)
        )
    )
    if not can_manage(principal):
        profiles = [profile for profile in profiles if profile.user_id == principal.user_id]
    candidates = [evaluate_candidate(db, profile, territory, start, end) for profile in profiles]
    candidates.sort(
        key=lambda item: (
            not item.eligible,
            not item.territory_match,
            -item.remaining_capacity,
            item.user_name.lower(),
        )
    )
    return DispatchSlotEvaluation(
        lead_id=lead.id,
        scheduled_start_at=start,
        scheduled_end_at=end,
        territory_id=territory.id if territory else None,
        territory_name=territory.name if territory else None,
        candidates=candidates,
    )


def evaluate_candidate(
    db: Session,
    profile: CloserDispatchProfile,
    territory: Territory | None,
    start: datetime,
    end: datetime,
) -> DispatchCandidateRead:
    user = db.get(User, profile.user_id)
    violations: list[str] = []
    timezone = resolve_timezone(profile.timezone)
    local_start = start.astimezone(timezone)
    local_end = end.astimezone(timezone)
    start_minute = local_start.hour * 60 + local_start.minute
    end_minute = local_end.hour * 60 + local_end.minute
    if local_start.weekday() not in profile.working_days:
        violations.append("outside_working_days")
    if (
        local_start.date() != local_end.date()
        or start_minute < profile.workday_start_minute
        or end_minute > profile.workday_end_minute
    ):
        violations.append("outside_working_hours")

    coverage_ids = set(
        db.scalars(
            select(CloserTerritoryCoverage.territory_id).where(
                CloserTerritoryCoverage.dispatch_profile_id == profile.id
            )
        )
    )
    territory_match = territory is not None and territory.id in coverage_ids
    if profile.territory_enforcement_enabled and not territory_match:
        violations.append("outside_territory")

    booked_count = appointment_count_for_local_day(db, profile, start)
    if booked_count >= profile.daily_capacity:
        violations.append("daily_capacity_reached")

    blocked = db.scalar(
        select(CloserAvailabilityBlock.id).where(
            CloserAvailabilityBlock.dispatch_profile_id == profile.id,
            CloserAvailabilityBlock.starts_at < end,
            CloserAvailabilityBlock.ends_at > start,
        )
    )
    if blocked is not None:
        violations.append("availability_block")

    buffer = timedelta(minutes=profile.travel_buffer_minutes)
    assumed_duration = timedelta(minutes=90)
    conflict = db.scalar(
        select(Appointment.id).where(
            Appointment.organization_id == profile.organization_id,
            Appointment.owner_user_id == profile.user_id,
            Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES),
            Appointment.scheduled_start_at < end + buffer,
            or_(
                and_(
                    Appointment.scheduled_end_at.is_not(None),
                    Appointment.scheduled_end_at > start - buffer,
                ),
                and_(
                    Appointment.scheduled_end_at.is_(None),
                    Appointment.scheduled_start_at > start - buffer - assumed_duration,
                ),
            ),
        )
    )
    if conflict is not None:
        violations.append("appointment_or_travel_conflict")
    return DispatchCandidateRead(
        profile_id=profile.id,
        user_id=profile.user_id,
        user_name=user.display_name if user else "Inactive user",
        eligible=not violations,
        territory_match=territory_match,
        territory_name=territory.name if territory else None,
        daily_booked_count=booked_count,
        daily_capacity=profile.daily_capacity,
        remaining_capacity=max(profile.daily_capacity - booked_count, 0),
        travel_buffer_minutes=profile.travel_buffer_minutes,
        violations=violations,
    )


def appointment_count_for_local_day(
    db: Session, profile: CloserDispatchProfile, reference: datetime
) -> int:
    timezone = resolve_timezone(profile.timezone)
    local_day = utc_value(reference).astimezone(timezone).date()
    local_start = datetime.combine(local_day, time.min, tzinfo=timezone).astimezone(UTC)
    local_end = (
        datetime.combine(local_day, time.min, tzinfo=timezone) + timedelta(days=1)
    ).astimezone(UTC)
    return int(
        db.scalar(
            select(func.count(Appointment.id)).where(
                Appointment.organization_id == profile.organization_id,
                Appointment.owner_user_id == profile.user_id,
                Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES),
                Appointment.scheduled_start_at >= local_start,
                Appointment.scheduled_start_at < local_end,
            )
        )
        or 0
    )


def resolve_lead_territory(db: Session, lead: Lead) -> Territory | None:
    property_record = db.get(Property, lead.property_id)
    if property_record is None:
        return None
    territories = list(
        db.scalars(
            select(Territory)
            .where(
                Territory.organization_id == lead.organization_id,
                Territory.status == "active",
            )
            .order_by(Territory.name)
        )
    )
    normalized_postal = property_record.postal_code.strip().lower()
    for territory in territories:
        if normalized_postal in {str(item).strip().lower() for item in territory.postal_codes}:
            return territory
    normalized_county = (property_record.county or "").strip().lower().removesuffix(" county")
    if normalized_county:
        for territory in territories:
            counties = {
                str(item).strip().lower().removesuffix(" county") for item in territory.county_names
            }
            if normalized_county in counties:
                return territory
    return None


def dispatch_appointment(
    db: Session,
    principal: Principal,
    payload: AppointmentDispatchCreate,
) -> AppointmentDispatchRead | None:
    if not can_manage(principal) and payload.closer_user_id != principal.user_id:
        raise PermissionError("Only a manager can dispatch an appointment to another closer.")
    profile = db.scalar(
        select(CloserDispatchProfile).where(
            CloserDispatchProfile.organization_id == principal.organization_id,
            CloserDispatchProfile.user_id == payload.closer_user_id,
            CloserDispatchProfile.is_active.is_(True),
        )
    )
    if profile is None:
        raise ValueError("The selected closer does not have an active dispatch profile.")
    requested_end = payload.scheduled_end_at or (
        utc_value(payload.scheduled_start_at)
        + timedelta(minutes=profile.default_appointment_minutes)
    )
    evaluation = evaluate_slot(
        db,
        principal,
        DispatchSlotRequest(
            lead_id=payload.lead_id,
            scheduled_start_at=payload.scheduled_start_at,
            scheduled_end_at=requested_end,
        ),
    )
    if evaluation is None:
        return None
    candidate = next(
        (item for item in evaluation.candidates if item.user_id == payload.closer_user_id),
        None,
    )
    if candidate is None:
        raise ValueError("The selected closer is not available for dispatch.")
    if candidate.violations:
        if not payload.override_conflicts:
            raise ValueError(
                "This closer is not available: " + ", ".join(candidate.violations) + "."
            )
        if not can_manage(principal):
            raise PermissionError("Only an acquisition manager can override dispatch conflicts.")

    lead = db.get(Lead, payload.lead_id)
    if lead is None or lead.organization_id != principal.organization_id:
        return None
    contact = db.get(Contact, lead.contact_id)
    property_record = db.get(Property, lead.property_id)
    if contact is None or property_record is None:
        raise ValueError("The lead requires a seller and property before scheduling.")
    existing = db.scalar(
        select(Appointment.id).where(
            Appointment.organization_id == principal.organization_id,
            Appointment.lead_id == lead.id,
            Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES),
            Appointment.scheduled_start_at >= datetime.now(UTC) - timedelta(hours=2),
        )
    )
    if existing is not None:
        raise ValueError("This lead already has an active appointment.")

    appointment = Appointment(
        organization_id=principal.organization_id,
        lead_id=lead.id,
        contact_id=contact.id,
        property_id=property_record.id,
        owner_user_id=payload.closer_user_id,
        appointment_type=payload.appointment_type,
        status="scheduled",
        scheduled_start_at=evaluation.scheduled_start_at,
        scheduled_end_at=evaluation.scheduled_end_at,
        location_type=payload.location_type,
        location=payload.location
        or (
            f"{property_record.street_address}, {property_record.city}, "
            f"{property_record.state} {property_record.postal_code}"
        ),
        notes=payload.notes,
        outcome=None,
        external_calendar_id=None,
        appointment_metadata={"scheduled_from": "field_operations"},
    )
    db.add(appointment)
    db.flush()
    territory = resolve_lead_territory(db, lead)
    dispatch = AppointmentDispatchRecord(
        organization_id=principal.organization_id,
        appointment_id=appointment.id,
        lead_id=lead.id,
        closer_user_id=payload.closer_user_id,
        territory_id=territory.id if territory else None,
        decided_by_user_id=principal.user_id,
        decision_status="override" if candidate.violations else "scheduled",
        scheduled_start_at=evaluation.scheduled_start_at,
        scheduled_end_at=evaluation.scheduled_end_at,
        daily_booked_count=candidate.daily_booked_count,
        travel_buffer_minutes=candidate.travel_buffer_minutes,
        territory_match=candidate.territory_match,
        violations=candidate.violations,
        candidate_snapshot=[item.model_dump(mode="json") for item in evaluation.candidates],
        decision_reason=payload.override_reason,
    )
    db.add(dispatch)
    lead.assigned_user_id = payload.closer_user_id
    lead.appointment_status = "scheduled"
    lead.stage_key = "appointment_scheduled"
    lead.next_follow_up_at = evaluation.scheduled_start_at
    case = db.scalar(select(LeadManagementCase).where(LeadManagementCase.lead_id == lead.id))
    if case:
        case.next_action_type = "appointment"
        case.next_action_due_at = evaluation.scheduled_start_at
    db.add(
        CalendarEvent(
            organization_id=principal.organization_id,
            appointment_id=appointment.id,
            owner_user_id=payload.closer_user_id,
            provider="internal",
            external_event_id=None,
            status="scheduled",
            event_payload={
                "appointment_type": appointment.appointment_type,
                "status": appointment.status,
                "start": appointment.scheduled_start_at.isoformat(),
                "end": evaluation.scheduled_end_at.isoformat(),
                "location": appointment.location,
                "notes": appointment.notes,
            },
            last_error=None,
            synced_at=None,
        )
    )
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            event_type="appointment.dispatched",
            summary=(
                "Appointment dispatched with a manager override."
                if candidate.violations
                else "Appointment dispatched to an available closer."
            ),
        )
    )
    closer = db.get(User, payload.closer_user_id)
    db.add(
        Notification(
            organization_id=principal.organization_id,
            recipient_user_id=payload.closer_user_id,
            notification_type="appointment_dispatched",
            title="New seller appointment",
            body=(
                f"{contact.legal_name} is scheduled for "
                f"{evaluation.scheduled_start_at.isoformat()}."
            ),
            entity_type="appointment",
            entity_id=appointment.id,
            action_url=f"/os/leads/{lead.id}",
            dedupe_key=f"appointment-dispatch:{appointment.id}",
            read_at=None,
        )
    )
    audit(
        db,
        principal,
        "field_operations.appointment_dispatch",
        "appointment",
        appointment.id,
        None,
        {
            "lead_id": str(lead.id),
            "closer_user_id": str(payload.closer_user_id),
            "start": evaluation.scheduled_start_at.isoformat(),
            "end": evaluation.scheduled_end_at.isoformat(),
            "decision_status": dispatch.decision_status,
            "violations": candidate.violations,
        },
        payload.override_reason or "Appointment dispatched",
    )
    db.commit()
    return AppointmentDispatchRead(
        appointment_id=appointment.id,
        dispatch_record_id=dispatch.id,
        lead_id=lead.id,
        closer_user_id=payload.closer_user_id,
        closer_name=closer.display_name if closer else "Unknown closer",
        decision_status=dispatch.decision_status,
        scheduled_start_at=appointment.scheduled_start_at,
        scheduled_end_at=evaluation.scheduled_end_at,
        violations=list(dispatch.violations),
    )


def profile_snapshot(profile: CloserDispatchProfile) -> dict[str, object]:
    return {
        "user_id": str(profile.user_id),
        "timezone": profile.timezone,
        "working_days": list(profile.working_days),
        "workday_start_minute": profile.workday_start_minute,
        "workday_end_minute": profile.workday_end_minute,
        "daily_capacity": profile.daily_capacity,
        "default_appointment_minutes": profile.default_appointment_minutes,
        "travel_buffer_minutes": profile.travel_buffer_minutes,
        "home_base_postal_code": profile.home_base_postal_code,
        "territory_enforcement_enabled": profile.territory_enforcement_enabled,
        "is_active": profile.is_active,
    }


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
