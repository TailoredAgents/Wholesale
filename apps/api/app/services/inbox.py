from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.domain.rbac import PermissionKeys
from app.models.foundation import (
    ActivityEvent,
    Appointment,
    AuditEvent,
    CallRecord,
    CallRecording,
    CallTranscript,
    CommunicationRecord,
    Contact,
    ContactMethod,
    Conversation,
    ConversationAssignmentEvent,
    ConversationWatcher,
    EmailAttachment,
    Lead,
    Property,
    Role,
    RoleAssignment,
    Task,
    User,
)
from app.schemas.email import EmailAttachmentRead
from app.schemas.inbox import (
    ConversationAppointmentRead,
    ConversationAssignmentEventRead,
    ConversationContactMethodRead,
    ConversationDetailRead,
    ConversationHandoffRequest,
    ConversationRead,
    ConversationTaskRead,
    ConversationTimelineItemRead,
    ConversationWatcherCreate,
    ConversationWatcherRead,
    InboxAssigneeRead,
    SmsEligibilityRead,
    VoiceEligibilityRead,
)
from app.services.call_intelligence import transcript_to_read
from app.services.communication_compliance import (
    evaluate_sms_eligibility,
    evaluate_voice_eligibility,
)

CONVERSATION_QUEUE_KEYS = {
    "unassigned",
    "va_prospecting",
    "qualified",
    "appointment_set",
    "acquisitions_follow_up",
    "closed",
}
ELIGIBLE_ACQUISITION_ROLE_KEYS = {
    "owner",
    "founder_operator",
    "ceo",
    "acquisition_manager",
    "acquisition_rep",
}
ELIGIBLE_ASSIGNMENT_ROLE_KEYS = {
    *ELIGIBLE_ACQUISITION_ROLE_KEYS,
    "prospecting_caller",
}
OWNER_WATCHER_ROLE_KEYS = {"owner", "founder_operator", "ceo"}
PRE_QUALIFIED_STAGES = {
    "new",
    "contact_attempt_due",
    "attempting_contact",
    "contacted",
    "qualification_in_progress",
}
PRE_APPOINTMENT_STAGES = {*PRE_QUALIFIED_STAGES, "qualified"}


def ensure_primary_conversation(
    db: Session,
    lead: Lead,
    *,
    queue_key: str | None = None,
) -> Conversation:
    existing = db.scalar(
        select(Conversation).where(
            Conversation.organization_id == lead.organization_id,
            Conversation.lead_id == lead.id,
        )
    )
    if existing is not None:
        return existing

    conversation = Conversation(
        organization_id=lead.organization_id,
        lead_id=lead.id,
        contact_id=lead.contact_id,
        assigned_user_id=lead.assigned_user_id,
        status="open",
        queue_key=queue_key
        or ("acquisitions_follow_up" if lead.assigned_user_id else "unassigned"),
        priority="normal",
        unread_count=0,
        last_activity_at=lead.created_at,
        last_inbound_at=None,
        last_outbound_at=None,
        closed_at=None,
        conversation_metadata={"source": "lead", "unified_timeline": True},
    )
    db.add(conversation)
    db.flush()
    db.add(
        ConversationAssignmentEvent(
            organization_id=lead.organization_id,
            conversation_id=conversation.id,
            lead_id=lead.id,
            actor_user_id=lead.assigned_user_id,
            previous_assigned_user_id=None,
            assigned_user_id=lead.assigned_user_id,
            previous_queue_key="unassigned",
            queue_key=conversation.queue_key,
            reason="Conversation created from lead.",
        )
    )
    return conversation


def update_conversation_activity(
    conversation: Conversation,
    *,
    direction: str,
    occurred_at: datetime,
) -> None:
    conversation.last_activity_at = occurred_at
    if direction == "inbound":
        conversation.last_inbound_at = occurred_at
        conversation.unread_count += 1
    elif direction == "outbound":
        conversation.last_outbound_at = occurred_at


def sync_conversation_to_lead_stage(
    db: Session,
    lead: Lead,
    *,
    actor_user_id: UUID,
    reason: str | None,
) -> None:
    queue_by_stage = {
        "qualified": "qualified",
        "appointment_scheduled": "appointment_set",
        "disqualified": "closed",
        "dead": "closed",
        "reopened": "acquisitions_follow_up",
    }
    queue_key = queue_by_stage.get(lead.stage_key)
    if queue_key is None:
        return

    conversation = ensure_primary_conversation(db, lead)
    if lead.stage_key in {"qualified", "appointment_scheduled"}:
        add_automatic_owner_watchers(db, conversation)
    if conversation.queue_key == queue_key:
        return

    previous_queue_key = conversation.queue_key
    conversation.queue_key = queue_key
    conversation.last_activity_at = datetime.now(UTC)
    if queue_key == "closed":
        conversation.status = "closed"
        conversation.closed_at = datetime.now(UTC)
    else:
        conversation.status = "open"
        conversation.closed_at = None
    db.add(
        ConversationAssignmentEvent(
            organization_id=lead.organization_id,
            conversation_id=conversation.id,
            lead_id=lead.id,
            actor_user_id=actor_user_id,
            previous_assigned_user_id=conversation.assigned_user_id,
            assigned_user_id=conversation.assigned_user_id,
            previous_queue_key=previous_queue_key,
            queue_key=queue_key,
            reason=reason or f"Lead stage changed to {lead.stage_key}.",
            created_at=datetime.now(UTC),
        )
    )


def list_conversations(
    db: Session,
    principal: Principal,
    *,
    queue_key: str | None = None,
    assigned_to_me: bool = False,
    limit: int = 100,
) -> list[ConversationRead]:
    filters = [Conversation.organization_id == principal.organization_id]
    if PermissionKeys.VIEW_CONVERSATIONS not in principal.permission_keys or assigned_to_me:
        filters.append(Conversation.assigned_user_id == principal.user_id)
    if queue_key:
        if queue_key not in CONVERSATION_QUEUE_KEYS:
            raise ValueError(f"Unsupported conversation queue: {queue_key}")
        filters.append(Conversation.queue_key == queue_key)

    conversations = db.scalars(
        select(Conversation)
        .where(*filters)
        .order_by(
            Conversation.last_activity_at.is_(None),
            Conversation.last_activity_at.desc(),
            Conversation.created_at.desc(),
        )
        .limit(limit)
    ).all()
    return [conversation_to_read(db, conversation) for conversation in conversations]


def get_conversation(
    db: Session,
    principal: Principal,
    conversation_id: UUID,
) -> ConversationRead | None:
    conversation = get_scoped_conversation(db, principal, conversation_id)
    return conversation_to_read(db, conversation) if conversation is not None else None


def get_conversation_detail(
    db: Session,
    principal: Principal,
    conversation_id: UUID,
) -> ConversationDetailRead | None:
    conversation = get_scoped_conversation(db, principal, conversation_id)
    if conversation is None:
        return None
    lead = db.get(Lead, conversation.lead_id)
    contact = db.get(Contact, conversation.contact_id)
    if lead is None or contact is None:
        raise RuntimeError("Conversation is missing its lead or contact.")
    property_record = db.get(Property, lead.property_id)
    if property_record is None:
        raise RuntimeError("Conversation lead is missing its property.")

    contact_methods = db.scalars(
        select(ContactMethod)
        .where(
            ContactMethod.organization_id == principal.organization_id,
            ContactMethod.contact_id == contact.id,
        )
        .order_by(ContactMethod.is_primary.desc(), ContactMethod.created_at.asc())
    ).all()
    communications = db.scalars(
        select(CommunicationRecord)
        .where(
            CommunicationRecord.organization_id == principal.organization_id,
            CommunicationRecord.conversation_id == conversation.id,
        )
        .order_by(CommunicationRecord.occurred_at.asc(), CommunicationRecord.created_at.asc())
        .limit(200)
    ).all()
    communication_ids = [item.id for item in communications]
    email_attachments = (
        db.scalars(
            select(EmailAttachment)
            .where(
                EmailAttachment.organization_id == principal.organization_id,
                EmailAttachment.communication_record_id.in_(communication_ids),
            )
            .order_by(EmailAttachment.created_at.asc())
        ).all()
        if communication_ids
        else []
    )
    attachments_by_communication_id: dict[UUID, list[EmailAttachment]] = {}
    for attachment in email_attachments:
        attachments_by_communication_id.setdefault(
            attachment.communication_record_id, []
        ).append(attachment)
    calls = (
        db.scalars(
            select(CallRecord).where(
                CallRecord.organization_id == principal.organization_id,
                CallRecord.communication_record_id.in_(communication_ids),
            )
        ).all()
        if communication_ids
        else []
    )
    call_by_communication_id = {
        call.communication_record_id: call
        for call in calls
        if call.communication_record_id is not None
    }
    call_ids = [call.id for call in calls]
    recordings = (
        db.scalars(
            select(CallRecording)
            .where(
                CallRecording.organization_id == principal.organization_id,
                CallRecording.call_record_id.in_(call_ids),
            )
            .order_by(CallRecording.created_at.desc())
        ).all()
        if call_ids
        else []
    )
    recording_by_call_id: dict[UUID, CallRecording] = {}
    for recording in recordings:
        recording_by_call_id.setdefault(recording.call_record_id, recording)
    recording_ids = [recording.id for recording in recordings]
    transcripts = (
        db.scalars(
            select(CallTranscript)
            .where(
                CallTranscript.organization_id == principal.organization_id,
                CallTranscript.recording_id.in_(recording_ids),
            )
            .order_by(CallTranscript.created_at.desc())
        ).all()
        if recording_ids and PermissionKeys.ACCESS_RECORDINGS in principal.permission_keys
        else []
    )
    transcript_by_recording_id: dict[UUID, CallTranscript] = {}
    for transcript in transcripts:
        transcript_by_recording_id.setdefault(transcript.recording_id, transcript)
    assignment_events = db.scalars(
        select(ConversationAssignmentEvent)
        .where(
            ConversationAssignmentEvent.organization_id == principal.organization_id,
            ConversationAssignmentEvent.conversation_id == conversation.id,
        )
        .order_by(
            ConversationAssignmentEvent.created_at.asc(),
            ConversationAssignmentEvent.id.asc(),
        )
        .limit(100)
    ).all()
    tasks = db.scalars(
        select(Task)
        .where(
            Task.organization_id == principal.organization_id,
            Task.lead_id == lead.id,
            Task.status.in_(("open", "in_progress")),
        )
        .order_by(Task.due_at.is_(None), Task.due_at.asc(), Task.created_at.asc())
        .limit(20)
    ).all()
    appointments = db.scalars(
        select(Appointment)
        .where(
            Appointment.organization_id == principal.organization_id,
            Appointment.lead_id == lead.id,
        )
        .order_by(Appointment.scheduled_start_at.asc(), Appointment.created_at.asc())
        .limit(20)
    ).all()

    actor_ids = {
        actor_id
        for actor_id in [
            *(item.actor_user_id for item in communications),
            *(item.actor_user_id for item in assignment_events),
            *(item.owner_user_id for item in appointments),
        ]
        if actor_id is not None
    }
    actor_names = {
        user.id: user.display_name
        for user in db.scalars(
            select(User).where(
                User.organization_id == principal.organization_id,
                User.id.in_(actor_ids),
            )
        ).all()
    }

    def actor_display_name(actor_user_id: UUID | None) -> str | None:
        return actor_names.get(actor_user_id) if actor_user_id is not None else None

    timeline = []
    for item in communications:
        call = call_by_communication_id.get(item.id)
        timeline_recording = recording_by_call_id.get(call.id) if call is not None else None
        timeline_transcript = (
            transcript_by_recording_id.get(timeline_recording.id)
            if timeline_recording is not None
            else None
        )
        timeline.append(
            ConversationTimelineItemRead(
            id=item.id,
            item_type="communication",
            direction=item.direction,
            channel=item.channel,
            status=item.status,
            provider=item.provider,
            subject=item.subject,
            body=item.body,
            actor_user_id=item.actor_user_id,
            actor_display_name=actor_display_name(item.actor_user_id),
            occurred_at=item.occurred_at,
            call_id=call.id if call else None,
            duration_seconds=call.duration_seconds if call else None,
            recording_id=timeline_recording.id if timeline_recording else None,
            recording_status=timeline_recording.status if timeline_recording else None,
            recording_retention_expires_at=(
                timeline_recording.retention_expires_at if timeline_recording else None
            ),
            recording_deleted_at=(
                timeline_recording.deleted_at if timeline_recording else None
            ),
            transcript=(
                transcript_to_read(db, timeline_transcript)
                if timeline_transcript is not None
                else None
            ),
            attachments=[
                EmailAttachmentRead(
                    id=attachment.id,
                    filename=attachment.filename,
                    content_type=attachment.content_type,
                    size_bytes=attachment.size_bytes,
                )
                for attachment in attachments_by_communication_id.get(item.id, [])
            ],
        )
        )
    timeline.extend(
        ConversationTimelineItemRead(
            id=item.id,
            item_type="assignment",
            direction=None,
            channel="assignment",
            status=item.queue_key,
            provider=None,
            subject="Ownership updated",
            body=item.reason,
            actor_user_id=item.actor_user_id,
            actor_display_name=actor_display_name(item.actor_user_id),
            occurred_at=item.created_at,
        )
        for item in assignment_events
    )
    timeline.extend(
        ConversationTimelineItemRead(
            id=item.id,
            item_type="appointment",
            direction=None,
            channel="appointment",
            status=item.status,
            provider=None,
            subject=f"{item.appointment_type.replace('_', ' ').title()} appointment",
            body=item.notes or item.location or item.location_type.replace("_", " ").title(),
            actor_user_id=item.owner_user_id,
            actor_display_name=actor_display_name(item.owner_user_id),
            occurred_at=item.scheduled_start_at,
        )
        for item in appointments
    )
    timeline.sort(key=lambda item: (item.occurred_at, str(item.id)))
    sms_eligibility = evaluate_sms_eligibility(db, contact)
    voice_eligibility = evaluate_voice_eligibility(db, contact)

    base = conversation_to_read(db, conversation)
    return ConversationDetailRead(
        **base.model_dump(),
        preferred_name=contact.preferred_name,
        contact_methods=[
            ConversationContactMethodRead(
                method_type=method.method_type,
                value=method.value,
                is_primary=method.is_primary,
            )
            for method in contact_methods
        ],
        source=lead.source,
        stage_key=lead.stage_key,
        lead_temperature=lead.lead_temperature,
        motivation=lead.motivation,
        desired_timeline=lead.desired_timeline,
        property_condition=lead.property_condition,
        occupancy_status=lead.occupancy_status,
        appointment_status=lead.appointment_status,
        next_follow_up_at=lead.next_follow_up_at,
        property_type=property_record.property_type,
        property_county=property_record.county,
        timeline=timeline,
        open_tasks=[
            ConversationTaskRead(
                id=task.id,
                title=task.title,
                task_type=task.task_type,
                status=task.status,
                priority=task.priority,
                due_at=task.due_at,
            )
            for task in tasks
        ],
        appointments=[
            ConversationAppointmentRead(
                id=appointment.id,
                appointment_type=appointment.appointment_type,
                status=appointment.status,
                scheduled_start_at=appointment.scheduled_start_at,
                scheduled_end_at=appointment.scheduled_end_at,
                location_type=appointment.location_type,
                location=appointment.location,
                notes=appointment.notes,
            )
            for appointment in appointments
        ],
        sms_eligibility=SmsEligibilityRead(
            can_send=sms_eligibility.can_send,
            recipient=sms_eligibility.recipient,
            consent_status=sms_eligibility.consent_status,
            is_suppressed=sms_eligibility.is_suppressed,
            provider_configured=sms_eligibility.provider_configured,
            within_allowed_hours=sms_eligibility.within_allowed_hours,
            blockers=list(sms_eligibility.blockers),
        ),
        voice_eligibility=VoiceEligibilityRead(
            can_call=voice_eligibility.can_call,
            recipient=voice_eligibility.recipient,
            consent_status=voice_eligibility.consent_status,
            is_suppressed=voice_eligibility.is_suppressed,
            provider_configured=voice_eligibility.provider_configured,
            within_allowed_hours=voice_eligibility.within_allowed_hours,
            blockers=list(voice_eligibility.blockers),
        ),
    )


def mark_conversation_read(
    db: Session,
    principal: Principal,
    conversation_id: UUID,
) -> ConversationRead | None:
    conversation = get_scoped_conversation(db, principal, conversation_id)
    if conversation is None:
        return None
    if conversation.unread_count:
        conversation.unread_count = 0
        db.commit()
        db.refresh(conversation)
    return conversation_to_read(db, conversation)


def list_eligible_assignees(db: Session, principal: Principal) -> list[InboxAssigneeRead]:
    role_keys = (
        ELIGIBLE_ASSIGNMENT_ROLE_KEYS
        if PermissionKeys.MANAGE_CONVERSATION_ASSIGNMENTS in principal.permission_keys
        else ELIGIBLE_ACQUISITION_ROLE_KEYS
    )
    rows = db.execute(
        select(User, Role.key)
        .join(RoleAssignment, RoleAssignment.user_id == User.id)
        .join(Role, Role.id == RoleAssignment.role_id)
        .where(
            User.organization_id == principal.organization_id,
            User.is_active.is_(True),
            Role.key.in_(role_keys),
        )
        .order_by(User.display_name.asc(), User.email.asc())
    ).all()
    users: dict[UUID, InboxAssigneeRead] = {}
    for user, role_key in rows:
        if user.id not in users:
            users[user.id] = InboxAssigneeRead(
                user_id=user.id,
                email=user.email,
                display_name=user.display_name,
                role_keys=[],
            )
        users[user.id].role_keys.append(role_key)
    for item in users.values():
        item.role_keys.sort()
    return list(users.values())


def handoff_conversation(
    db: Session,
    principal: Principal,
    conversation_id: UUID,
    payload: ConversationHandoffRequest,
) -> ConversationRead | None:
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.organization_id == principal.organization_id,
            Conversation.id == conversation_id,
        )
    )
    if conversation is None:
        return None

    can_manage_all = PermissionKeys.MANAGE_CONVERSATION_ASSIGNMENTS in principal.permission_keys
    if not can_manage_all and (
        PermissionKeys.HANDOFF_ASSIGNED_CONVERSATIONS not in principal.permission_keys
        or conversation.assigned_user_id != principal.user_id
    ):
        raise PermissionError("Conversation is not assigned to the current user.")

    allowed_queue_keys = {
        "qualified",
        "appointment_set",
        "acquisitions_follow_up",
    }
    if can_manage_all:
        allowed_queue_keys.add("va_prospecting")
    if payload.queue_key not in allowed_queue_keys:
        raise ValueError(f"Unsupported handoff queue: {payload.queue_key}")

    target = db.scalar(
        select(User).where(
            User.organization_id == principal.organization_id,
            User.id == payload.assigned_user_id,
            User.is_active.is_(True),
        )
    )
    if target is None:
        raise ValueError("Assignment target must be an active workspace user.")
    target_role_keys = get_user_role_keys(db, target)
    if not target_role_keys.intersection(ELIGIBLE_ASSIGNMENT_ROLE_KEYS):
        raise ValueError("Assignment target must have an operational acquisitions role.")
    if (
        payload.queue_key == "va_prospecting"
        and "prospecting_caller" not in target_role_keys
    ):
        raise ValueError("VA prospecting conversations must be assigned to a prospecting caller.")
    if (
        payload.queue_key != "va_prospecting"
        and not target_role_keys.intersection(ELIGIBLE_ACQUISITION_ROLE_KEYS)
    ):
        raise ValueError("Handoff target must be an active acquisition user.")

    lead = db.scalar(
        select(Lead).where(
            Lead.organization_id == principal.organization_id,
            Lead.id == conversation.lead_id,
        )
    )
    if lead is None:
        return None
    contact = db.get(Contact, lead.contact_id)

    previous_assigned_user_id = conversation.assigned_user_id
    previous_queue_key = conversation.queue_key
    previous_stage_key = lead.stage_key
    conversation.assigned_user_id = target.id
    conversation.queue_key = payload.queue_key
    conversation.status = "open"
    conversation.closed_at = None
    conversation.last_activity_at = datetime.now(UTC)
    lead.assigned_user_id = target.id
    if contact is not None:
        contact.assigned_user_id = target.id
    if payload.queue_key == "va_prospecting" and lead.stage_key in {
        "new",
        "contact_attempt_due",
        "attempting_contact",
        "contacted",
    }:
        lead.stage_key = "qualification_in_progress"
    elif payload.queue_key == "qualified" and lead.stage_key in PRE_QUALIFIED_STAGES:
        lead.stage_key = "qualified"
    elif payload.queue_key == "appointment_set" and lead.stage_key in PRE_APPOINTMENT_STAGES:
        lead.stage_key = "appointment_scheduled"

    for task in db.scalars(
        select(Task).where(
            Task.organization_id == principal.organization_id,
            Task.lead_id == lead.id,
            Task.status.in_(("open", "in_progress")),
        )
    ):
        task.responsible_user_id = target.id
    for appointment in db.scalars(
        select(Appointment).where(
            Appointment.organization_id == principal.organization_id,
            Appointment.lead_id == lead.id,
            Appointment.status.in_(("scheduled", "rescheduled")),
        )
    ):
        appointment.owner_user_id = target.id

    assignment_event = ConversationAssignmentEvent(
        organization_id=principal.organization_id,
        conversation_id=conversation.id,
        lead_id=lead.id,
        actor_user_id=principal.user_id,
        previous_assigned_user_id=previous_assigned_user_id,
        assigned_user_id=target.id,
        previous_queue_key=previous_queue_key,
        queue_key=payload.queue_key,
        reason=payload.reason,
        created_at=datetime.now(UTC),
    )
    db.add(assignment_event)
    if target_role_keys.intersection(ELIGIBLE_ACQUISITION_ROLE_KEYS):
        ensure_watcher(
            db,
            conversation,
            target,
            source="assignment",
            notification_level="all",
        )
    if payload.queue_key != "va_prospecting":
        add_automatic_owner_watchers(db, conversation)
    action = (
        "conversation.assign"
        if payload.queue_key == "va_prospecting"
        else "conversation.handoff"
    )
    activity_verb = "assigned" if payload.queue_key == "va_prospecting" else "handed off"
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            event_type=(
                "lead.assigned_to_prospecting"
                if payload.queue_key == "va_prospecting"
                else "lead.handed_off"
            ),
            summary=(
                f"Conversation {activity_verb} to {target.display_name} "
                f"in {payload.queue_key}."
            ),
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action=action,
            entity_type="conversation",
            entity_id=conversation.id,
            previous_value={
                "assigned_user_id": str(previous_assigned_user_id)
                if previous_assigned_user_id
                else None,
                "queue_key": previous_queue_key,
                "lead_stage_key": previous_stage_key,
            },
            new_value={
                "assigned_user_id": str(target.id),
                "queue_key": payload.queue_key,
                "lead_stage_key": lead.stage_key,
            },
            reason=payload.reason,
        )
    )
    db.commit()
    db.refresh(conversation)
    return conversation_to_read(db, conversation)


def add_conversation_watcher(
    db: Session,
    principal: Principal,
    conversation_id: UUID,
    payload: ConversationWatcherCreate,
) -> ConversationRead | None:
    conversation = get_scoped_conversation(db, principal, conversation_id, require_all=True)
    if conversation is None:
        return None
    user = db.scalar(
        select(User).where(
            User.organization_id == principal.organization_id,
            User.id == payload.user_id,
            User.is_active.is_(True),
        )
    )
    if user is None:
        raise ValueError("Watcher must be an active workspace user.")
    watcher = ensure_watcher(
        db,
        conversation,
        user,
        source="manual",
        notification_level=payload.notification_level,
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="conversation.watcher_add",
            entity_type="conversation_watcher",
            entity_id=watcher.id,
            previous_value=None,
            new_value={
                "conversation_id": str(conversation.id),
                "user_id": str(user.id),
                "notification_level": watcher.notification_level,
            },
            reason="Manual conversation watcher",
        )
    )
    db.commit()
    return conversation_to_read(db, conversation)


def remove_conversation_watcher(
    db: Session,
    principal: Principal,
    conversation_id: UUID,
    user_id: UUID,
) -> ConversationRead | None:
    conversation = get_scoped_conversation(db, principal, conversation_id, require_all=True)
    if conversation is None:
        return None
    watcher = db.scalar(
        select(ConversationWatcher).where(
            ConversationWatcher.organization_id == principal.organization_id,
            ConversationWatcher.conversation_id == conversation.id,
            ConversationWatcher.user_id == user_id,
        )
    )
    if watcher is not None:
        watcher_id = watcher.id
        db.delete(watcher)
        db.add(
            AuditEvent(
                organization_id=principal.organization_id,
                actor_user_id=principal.user_id,
                actor_type="user",
                action="conversation.watcher_remove",
                entity_type="conversation_watcher",
                entity_id=watcher_id,
                previous_value={"conversation_id": str(conversation.id), "user_id": str(user_id)},
                new_value=None,
                reason="Manual conversation watcher removal",
            )
        )
        db.commit()
    return conversation_to_read(db, conversation)


def add_automatic_owner_watchers(db: Session, conversation: Conversation) -> None:
    owners = db.scalars(
        select(User)
        .join(RoleAssignment, RoleAssignment.user_id == User.id)
        .join(Role, Role.id == RoleAssignment.role_id)
        .where(
            User.organization_id == conversation.organization_id,
            User.is_active.is_(True),
            Role.key.in_(OWNER_WATCHER_ROLE_KEYS),
        )
        .distinct()
    ).all()
    for owner in owners:
        ensure_watcher(
            db,
            conversation,
            owner,
            source="automatic_owner",
            notification_level="important",
        )


def ensure_watcher(
    db: Session,
    conversation: Conversation,
    user: User,
    *,
    source: str,
    notification_level: str,
) -> ConversationWatcher:
    watcher = db.scalar(
        select(ConversationWatcher).where(
            ConversationWatcher.conversation_id == conversation.id,
            ConversationWatcher.user_id == user.id,
        )
    )
    if watcher is None:
        watcher = ConversationWatcher(
            organization_id=conversation.organization_id,
            conversation_id=conversation.id,
            user_id=user.id,
            source=source,
            notification_level=notification_level,
            is_muted=False,
        )
        db.add(watcher)
        db.flush()
    return watcher


def get_scoped_conversation(
    db: Session,
    principal: Principal,
    conversation_id: UUID,
    *,
    require_all: bool = False,
) -> Conversation | None:
    filters = [
        Conversation.organization_id == principal.organization_id,
        Conversation.id == conversation_id,
    ]
    if (require_all or PermissionKeys.VIEW_CONVERSATIONS not in principal.permission_keys) and (
        PermissionKeys.MANAGE_CONVERSATION_ASSIGNMENTS not in principal.permission_keys
    ):
        filters.append(Conversation.assigned_user_id == principal.user_id)
    return db.scalar(select(Conversation).where(*filters))


def get_user_role_keys(db: Session, user: User) -> set[str]:
    return set(
        db.scalars(
            select(Role.key)
            .join(RoleAssignment, RoleAssignment.role_id == Role.id)
            .where(
                RoleAssignment.organization_id == user.organization_id,
                RoleAssignment.user_id == user.id,
            )
        )
    )


def conversation_to_read(db: Session, conversation: Conversation) -> ConversationRead:
    lead = db.get(Lead, conversation.lead_id)
    contact = db.get(Contact, conversation.contact_id)
    assigned_user = (
        db.get(User, conversation.assigned_user_id) if conversation.assigned_user_id else None
    )
    if lead is None or contact is None:
        raise RuntimeError("Conversation is missing its lead or contact.")
    property_record = db.get(Property, lead.property_id)
    if property_record is None:
        raise RuntimeError("Conversation lead is missing its property.")

    watcher_rows = db.execute(
        select(ConversationWatcher, User)
        .join(User, User.id == ConversationWatcher.user_id)
        .where(
            ConversationWatcher.organization_id == conversation.organization_id,
            ConversationWatcher.conversation_id == conversation.id,
        )
        .order_by(User.display_name.asc(), User.email.asc())
    ).all()
    assignment_events = db.scalars(
        select(ConversationAssignmentEvent)
        .where(
            ConversationAssignmentEvent.organization_id == conversation.organization_id,
            ConversationAssignmentEvent.conversation_id == conversation.id,
        )
        .order_by(
            ConversationAssignmentEvent.created_at.desc(),
            ConversationAssignmentEvent.id.desc(),
        )
        .limit(20)
    ).all()
    return ConversationRead(
        id=conversation.id,
        lead_id=conversation.lead_id,
        contact_id=conversation.contact_id,
        seller_name=contact.legal_name,
        property_address=(
            f"{property_record.street_address}, {property_record.city}, "
            f"{property_record.state} {property_record.postal_code}"
        ),
        assigned_user_id=conversation.assigned_user_id,
        assigned_user_email=assigned_user.email if assigned_user else None,
        assigned_user_display_name=assigned_user.display_name if assigned_user else None,
        status=conversation.status,
        queue_key=conversation.queue_key,
        priority=conversation.priority,
        unread_count=conversation.unread_count,
        last_activity_at=conversation.last_activity_at,
        last_inbound_at=conversation.last_inbound_at,
        last_outbound_at=conversation.last_outbound_at,
        closed_at=conversation.closed_at,
        watchers=[
            ConversationWatcherRead(
                user_id=user.id,
                email=user.email,
                display_name=user.display_name,
                source=watcher.source,
                notification_level=watcher.notification_level,
                is_muted=watcher.is_muted,
            )
            for watcher, user in watcher_rows
        ],
        assignment_history=[
            ConversationAssignmentEventRead(
                id=event.id,
                actor_user_id=event.actor_user_id,
                previous_assigned_user_id=event.previous_assigned_user_id,
                assigned_user_id=event.assigned_user_id,
                previous_queue_key=event.previous_queue_key,
                queue_key=event.queue_key,
                reason=event.reason,
                created_at=event.created_at,
            )
            for event in assignment_events
        ],
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )
