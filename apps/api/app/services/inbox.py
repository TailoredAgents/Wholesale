from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session, defer
from sqlalchemy.sql.elements import ColumnElement

from app.core.auth import Principal
from app.core.config import get_settings
from app.domain.assets import (
    asset_class_for_property_type,
    normalize_asset_class,
    property_identity_label,
)
from app.domain.rbac import PermissionKeys
from app.models.foundation import (
    ActivityEvent,
    Appointment,
    AuditEvent,
    Buyer,
    CallRecord,
    CallRecording,
    CallTranscript,
    CommunicationDispatch,
    CommunicationParticipant,
    CommunicationProviderEvent,
    CommunicationRecord,
    Contact,
    ContactMethod,
    Conversation,
    ConversationAssignmentEvent,
    ConversationContextLink,
    ConversationWatcher,
    EmailAttachment,
    EmailSenderAlias,
    EmailSenderGrant,
    Lead,
    LeadManagementCase,
    Notification,
    Property,
    Role,
    RoleAssignment,
    Task,
    Team,
    TeamMembership,
    User,
    VoiceCallIntent,
    VoiceLine,
)
from app.schemas.email import EmailAttachmentRead
from app.schemas.inbox import (
    ConversationAppointmentRead,
    ConversationAssignmentEventRead,
    ConversationContactMethodRead,
    ConversationDetailRead,
    ConversationHandoffRequest,
    ConversationRead,
    ConversationResolutionRead,
    ConversationTaskRead,
    ConversationTimelineItemRead,
    ConversationWatcherCreate,
    ConversationWatcherRead,
    GeneralConversationClassification,
    GeneralConversationLeadCreate,
    GeneralConversationLeadLink,
    InboxAssigneeRead,
    MailboxResponseBucketRead,
    MailboxResponseOverviewRead,
    SmsEligibilityRead,
    VoiceEligibilityRead,
)
from app.services.call_intelligence import transcript_to_read
from app.services.communication_compliance import (
    evaluate_sms_eligibility,
    evaluate_voice_eligibility,
)
from app.services.document_storage import read_content
from app.services.email_identity import general_email_display_name
from app.services.lead_lifecycle import lock_organization_lead, require_lead_open_for_work
from app.services.mailbox_notifications import (
    MAILBOX_NOTIFICATION_TYPES,
    latest_inbound_channel,
    mailbox_response_status,
)

CONVERSATION_QUEUE_KEYS = {
    "unassigned",
    "va_prospecting",
    "qualified",
    "appointment_set",
    "acquisitions_follow_up",
    "dispositions",
    "closed",
}
ELIGIBLE_ACQUISITION_ROLE_KEYS = {
    "owner",
    "founder_operator",
    "ceo",
    "acquisition_manager",
    "acquisition_rep",
    "operations_assistant",
}
ELIGIBLE_ASSIGNMENT_ROLE_KEYS = {
    *ELIGIBLE_ACQUISITION_ROLE_KEYS,
    "disposition_manager",
    "disposition_rep",
    "prospecting_caller",
}
ELIGIBLE_DISPOSITION_ROLE_KEYS = {
    "owner",
    "founder_operator",
    "ceo",
    "disposition_manager",
    "disposition_rep",
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
        conversation_type="lead",
        lead_id=lead.id,
        contact_id=lead.contact_id,
        assigned_user_id=lead.assigned_user_id,
        assigned_team_id=None,
        source_alias_id=None,
        visibility_scope="standard",
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
        ConversationContextLink(
            organization_id=lead.organization_id,
            conversation_id=conversation.id,
            context_type="lead",
            lead_id=lead.id,
            transaction_id=None,
            buyer_id=None,
            disposition_case_id=None,
            created_by_user_id=lead.assigned_user_id,
            is_primary=True,
            link_metadata={"source": "lead_creation"},
        )
    )
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


def ensure_buyer_conversation(
    db: Session,
    buyer: Buyer,
    *,
    actor_user_id: UUID | None = None,
) -> Conversation:
    existing = db.scalar(
        select(Conversation)
        .join(
            ConversationContextLink,
            ConversationContextLink.conversation_id == Conversation.id,
        )
        .where(
            Conversation.organization_id == buyer.organization_id,
            ConversationContextLink.organization_id == buyer.organization_id,
            ConversationContextLink.context_type == "buyer",
            ConversationContextLink.buyer_id == buyer.id,
        )
    )
    if existing is not None:
        return existing

    line = db.scalar(
        select(VoiceLine)
        .where(
            VoiceLine.organization_id == buyer.organization_id,
            VoiceLine.department_key == "dispositions",
            VoiceLine.purpose_key == "buyer_relations",
            VoiceLine.status == "active",
        )
        .order_by(VoiceLine.is_default.desc(), VoiceLine.created_at.asc())
    )
    contact = Contact(
        organization_id=buyer.organization_id,
        legal_name=buyer.name,
        preferred_name=buyer.name.split()[0] if buyer.name.strip() else None,
        contact_type="buyer",
        assigned_user_id=line.assigned_user_id if line is not None else None,
    )
    db.add(contact)
    db.flush()
    if buyer.phone:
        digits = "".join(character for character in buyer.phone if character.isdigit())
        db.add(
            ContactMethod(
                organization_id=buyer.organization_id,
                contact_id=contact.id,
                method_type="phone",
                value=buyer.phone,
                normalized_value=digits,
                is_primary=True,
            )
        )
    if buyer.email:
        db.add(
            ContactMethod(
                organization_id=buyer.organization_id,
                contact_id=contact.id,
                method_type="email",
                value=buyer.email,
                normalized_value=buyer.email.strip().lower(),
                is_primary=not bool(buyer.phone),
            )
        )

    conversation = Conversation(
        organization_id=buyer.organization_id,
        conversation_type="buyer",
        lead_id=None,
        contact_id=contact.id,
        assigned_user_id=line.assigned_user_id if line is not None else None,
        assigned_team_id=line.assigned_team_id if line is not None else None,
        source_alias_id=None,
        visibility_scope="standard",
        status="open",
        queue_key="dispositions",
        priority="normal",
        unread_count=0,
        last_activity_at=buyer.created_at,
        last_inbound_at=None,
        last_outbound_at=None,
        closed_at=None,
        conversation_metadata={
            "source": "buyer_crm",
            "unified_timeline": True,
            "department_key": "dispositions",
        },
    )
    db.add(conversation)
    db.flush()
    db.add(
        ConversationContextLink(
            organization_id=buyer.organization_id,
            conversation_id=conversation.id,
            context_type="buyer",
            lead_id=None,
            transaction_id=None,
            buyer_id=buyer.id,
            disposition_case_id=None,
            created_by_user_id=actor_user_id,
            is_primary=True,
            link_metadata={"source": "buyer_conversation"},
        )
    )
    db.add(
        ConversationAssignmentEvent(
            organization_id=buyer.organization_id,
            conversation_id=conversation.id,
            lead_id=None,
            actor_user_id=actor_user_id,
            previous_assigned_user_id=None,
            assigned_user_id=conversation.assigned_user_id,
            previous_queue_key="unassigned",
            queue_key="dispositions",
            reason="Buyer conversation created for dispositions.",
        )
    )
    db.flush()
    return conversation


def create_general_conversation(
    db: Session,
    *,
    organization_id: UUID,
    contact_id: UUID,
    assigned_user_id: UUID | None = None,
    assigned_team_id: UUID | None = None,
    source_alias_id: UUID | None = None,
    visibility_scope: str = "standard",
) -> Conversation:
    if visibility_scope not in {"standard", "restricted"}:
        raise ValueError("Unsupported conversation visibility scope.")
    contact = db.scalar(
        select(Contact).where(
            Contact.organization_id == organization_id,
            Contact.id == contact_id,
        )
    )
    if contact is None:
        raise ValueError("Conversation contact is not available in this workspace.")
    if assigned_user_id is not None:
        user = db.scalar(
            select(User).where(
                User.organization_id == organization_id,
                User.id == assigned_user_id,
                User.is_active.is_(True),
            )
        )
        if user is None:
            raise ValueError("Conversation assignee is not an active workspace user.")
    if assigned_team_id is not None:
        team = db.scalar(
            select(Team).where(
                Team.organization_id == organization_id,
                Team.id == assigned_team_id,
                Team.is_active.is_(True),
            )
        )
        if team is None:
            raise ValueError("Conversation team is not active in this workspace.")
    if source_alias_id is not None:
        alias = db.scalar(
            select(EmailSenderAlias).where(
                EmailSenderAlias.organization_id == organization_id,
                EmailSenderAlias.id == source_alias_id,
                EmailSenderAlias.status == "active",
                EmailSenderAlias.inbound_enabled.is_(True),
            )
        )
        if alias is None:
            raise ValueError("Conversation source alias is not active for inbound email.")

    conversation = Conversation(
        organization_id=organization_id,
        conversation_type="general",
        lead_id=None,
        contact_id=contact.id,
        assigned_user_id=assigned_user_id,
        assigned_team_id=assigned_team_id,
        source_alias_id=source_alias_id,
        visibility_scope=visibility_scope,
        status="open",
        queue_key="unassigned",
        priority="normal",
        unread_count=0,
        last_activity_at=datetime.now(UTC),
        last_inbound_at=None,
        last_outbound_at=None,
        closed_at=None,
        conversation_metadata={"source": "general_email", "unified_timeline": True},
    )
    db.add(conversation)
    db.flush()
    db.add(
        ConversationAssignmentEvent(
            organization_id=organization_id,
            conversation_id=conversation.id,
            lead_id=None,
            actor_user_id=assigned_user_id,
            previous_assigned_user_id=None,
            assigned_user_id=assigned_user_id,
            previous_queue_key="unassigned",
            queue_key="unassigned",
            reason="General conversation created.",
        )
    )
    db.flush()
    return conversation


def convert_general_conversation_to_lead(
    db: Session,
    principal: Principal,
    conversation_id: UUID,
    payload: GeneralConversationLeadCreate,
) -> ConversationResolutionRead | None:
    conversation = get_scoped_conversation(db, principal, conversation_id)
    if conversation is None:
        return None
    _require_general_conversation(conversation)

    assigned_user_id = (
        payload.assigned_user_id or conversation.assigned_user_id or principal.user_id
    )
    assigned_user = db.scalar(
        select(User).where(
            User.organization_id == principal.organization_id,
            User.id == assigned_user_id,
            User.is_active.is_(True),
        )
    )
    if assigned_user is None or not get_user_role_keys(db, assigned_user).intersection(
        ELIGIBLE_ACQUISITION_ROLE_KEYS
    ):
        raise ValueError("Select an active acquisitions or management owner for this lead.")

    contact = db.get(Contact, conversation.contact_id)
    if contact is None or contact.organization_id != principal.organization_id:
        raise ValueError("The conversation contact is not available in this workspace.")

    from app.services.ai_operations import enqueue_lead_created_ai_work
    from app.services.property_identity import (
        find_property_by_identity,
        refresh_property_identity_keys,
        require_valid_property_identity,
    )
    from app.services.property_intelligence import enqueue_property_research
    from app.services.tasks import create_initial_lead_next_action

    property_payload = payload.property
    asset_class = asset_class_for_property_type(
        property_payload.property_type,
        explicit_asset_class=payload.asset_class,
    )
    property_record, normalized_property_key, normalized_parcel_key = find_property_by_identity(
        db,
        organization_id=principal.organization_id,
        street_address=property_payload.street_address,
        city=property_payload.city,
        state=property_payload.state,
        postal_code=property_payload.postal_code,
        parcel_id=property_payload.parcel_id,
        county=property_payload.county,
    )
    if property_record is None:
        property_record = Property(
            organization_id=principal.organization_id,
            street_address=property_payload.street_address.strip(),
            city=property_payload.city.strip(),
            state=property_payload.state.strip().upper(),
            postal_code=property_payload.postal_code.strip(),
            county=property_payload.county,
            property_type=property_payload.property_type
            or ("land" if asset_class == "land" else None),
            parcel_id=property_payload.parcel_id,
            normalized_parcel_key=normalized_parcel_key,
            normalized_address_key=normalized_property_key,
            address_validation_status="unverified",
        )
        db.add(property_record)
        db.flush()
    else:
        if property_payload.property_type and not property_record.property_type:
            property_record.property_type = property_payload.property_type
        if property_payload.parcel_id and not property_record.parcel_id:
            property_record.parcel_id = property_payload.parcel_id
        if property_payload.county and not property_record.county:
            property_record.county = property_payload.county
        refresh_property_identity_keys(property_record)
    require_valid_property_identity(property_record, asset_class=asset_class)

    lead = Lead(
        organization_id=principal.organization_id,
        contact_id=contact.id,
        property_id=property_record.id,
        assigned_user_id=assigned_user.id,
        source=payload.source.strip(),
        asset_class=asset_class,
        stage_key="new",
        lead_temperature=None,
        motivation=None,
        desired_timeline=None,
        property_condition=None,
        occupancy_status=None,
        asking_price=None,
        mortgage_balance=None,
        appointment_status=None,
        next_follow_up_at=None,
        archived_at=None,
    )
    db.add(lead)
    db.flush()

    now = datetime.now(UTC)
    previous_queue_key = conversation.queue_key
    previous_assigned_user_id = conversation.assigned_user_id
    conversation.conversation_type = "lead"
    conversation.lead_id = lead.id
    conversation.assigned_user_id = assigned_user.id
    conversation.assigned_team_id = None
    conversation.status = "open"
    conversation.queue_key = "acquisitions_follow_up"
    conversation.closed_at = None
    conversation.last_activity_at = now
    conversation.conversation_metadata = {
        **(conversation.conversation_metadata or {}),
        "source": "inbound_email",
        "resolution": "converted_to_lead",
        "resolved_at": now.isoformat(),
        "resolved_by_user_id": str(principal.user_id),
    }
    contact.contact_type = "seller"
    contact.assigned_user_id = assigned_user.id
    db.add(
        ConversationContextLink(
            organization_id=principal.organization_id,
            conversation_id=conversation.id,
            context_type="lead",
            lead_id=lead.id,
            transaction_id=None,
            buyer_id=None,
            disposition_case_id=None,
            created_by_user_id=principal.user_id,
            is_primary=True,
            link_metadata={"source": "inbox_conversion"},
        )
    )
    db.add(
        ConversationAssignmentEvent(
            organization_id=principal.organization_id,
            conversation_id=conversation.id,
            lead_id=lead.id,
            actor_user_id=principal.user_id,
            previous_assigned_user_id=previous_assigned_user_id,
            assigned_user_id=assigned_user.id,
            previous_queue_key=previous_queue_key,
            queue_key=conversation.queue_key,
            reason="General email converted to a seller lead.",
        )
    )
    for communication in db.scalars(
        select(CommunicationRecord).where(
            CommunicationRecord.organization_id == principal.organization_id,
            CommunicationRecord.conversation_id == conversation.id,
        )
    ).all():
        communication.lead_id = lead.id

    create_initial_lead_next_action(db, lead, actor_user_id=principal.user_id)
    enqueue_lead_created_ai_work(db, lead, source="inbound_email")
    enqueue_property_research(
        db,
        property_record,
        source_lead_id=lead.id,
        trigger_source="inbound_email",
    )
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            event_type="lead.created_from_email",
            summary=f"Inbound email converted to a lead for {contact.legal_name}.",
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="inbox.convert_to_lead",
            entity_type="conversation",
            entity_id=conversation.id,
            previous_value={"conversation_type": "general", "lead_id": None},
            new_value={"conversation_type": "lead", "lead_id": str(lead.id)},
            reason="Promoted inbound company email to seller lead",
        )
    )
    db.commit()
    return ConversationResolutionRead(
        action="converted_to_lead",
        source_conversation_id=conversation.id,
        conversation_id=conversation.id,
        lead_id=lead.id,
        status="open",
        message="Email converted to a seller lead. Property research has been queued.",
    )


def link_general_conversation_to_lead(
    db: Session,
    principal: Principal,
    conversation_id: UUID,
    payload: GeneralConversationLeadLink,
) -> ConversationResolutionRead | None:
    source = get_scoped_conversation(db, principal, conversation_id)
    if source is None:
        return None
    _require_general_conversation(source)
    lead = db.scalar(
        select(Lead).where(
            Lead.organization_id == principal.organization_id,
            Lead.id == payload.lead_id,
            Lead.archived_at.is_(None),
        )
    )
    if lead is None:
        raise ValueError("Select an active seller lead in this workspace.")
    target = ensure_primary_conversation(db, lead)
    target_contact = db.get(Contact, lead.contact_id)
    source_contact = db.get(Contact, source.contact_id)
    if target_contact is None or source_contact is None:
        raise ValueError("The email or lead contact is unavailable.")

    target_methods = {
        (method.method_type, method.normalized_value)
        for method in db.scalars(
            select(ContactMethod).where(
                ContactMethod.organization_id == principal.organization_id,
                ContactMethod.contact_id == target_contact.id,
            )
        ).all()
    }
    has_target_methods = bool(target_methods)
    for method in db.scalars(
        select(ContactMethod).where(
            ContactMethod.organization_id == principal.organization_id,
            ContactMethod.contact_id == source_contact.id,
        )
    ).all():
        key = (method.method_type, method.normalized_value)
        if key in target_methods:
            continue
        db.add(
            ContactMethod(
                organization_id=principal.organization_id,
                contact_id=target_contact.id,
                method_type=method.method_type,
                value=method.value,
                normalized_value=method.normalized_value,
                is_primary=not has_target_methods,
            )
        )
        has_target_methods = True
        target_methods.add(key)

    communications = db.scalars(
        select(CommunicationRecord).where(
            CommunicationRecord.organization_id == principal.organization_id,
            CommunicationRecord.conversation_id == source.id,
        )
    ).all()
    communication_ids = [communication.id for communication in communications]
    for communication in communications:
        communication.conversation_id = target.id
        communication.lead_id = lead.id
        communication.contact_id = target_contact.id
    db.execute(
        update(CommunicationParticipant)
        .where(
            CommunicationParticipant.organization_id == principal.organization_id,
            CommunicationParticipant.conversation_id == source.id,
        )
        .values(conversation_id=target.id)
    )
    db.execute(
        update(CommunicationParticipant)
        .where(
            CommunicationParticipant.organization_id == principal.organization_id,
            CommunicationParticipant.conversation_id == target.id,
            CommunicationParticipant.contact_id == source_contact.id,
        )
        .values(contact_id=target_contact.id)
    )
    db.execute(
        update(CommunicationProviderEvent)
        .where(
            CommunicationProviderEvent.organization_id == principal.organization_id,
            CommunicationProviderEvent.conversation_id == source.id,
        )
        .values(conversation_id=target.id)
    )
    db.execute(
        update(CommunicationDispatch)
        .where(
            CommunicationDispatch.organization_id == principal.organization_id,
            CommunicationDispatch.conversation_id == source.id,
        )
        .values(conversation_id=target.id, lead_id=lead.id, contact_id=target_contact.id)
    )
    db.execute(
        update(VoiceCallIntent)
        .where(
            VoiceCallIntent.organization_id == principal.organization_id,
            VoiceCallIntent.conversation_id == source.id,
        )
        .values(conversation_id=target.id, lead_id=lead.id, contact_id=target_contact.id)
    )
    db.execute(
        update(CallRecord)
        .where(
            CallRecord.organization_id == principal.organization_id,
            CallRecord.conversation_id == source.id,
        )
        .values(conversation_id=target.id, lead_id=lead.id, contact_id=target_contact.id)
    )

    now = datetime.now(UTC)
    target.source_alias_id = target.source_alias_id or source.source_alias_id
    target.last_activity_at = _latest_datetime(
        target.last_activity_at,
        source.last_activity_at,
        now,
    )
    target.last_inbound_at = _latest_datetime(target.last_inbound_at, source.last_inbound_at)
    target.last_outbound_at = _latest_datetime(target.last_outbound_at, source.last_outbound_at)
    target.unread_count += source.unread_count
    target.status = "open"
    target.closed_at = None
    target.conversation_metadata = {
        **(target.conversation_metadata or {}),
        "linked_general_conversation_id": str(source.id),
        "linked_general_conversation_at": now.isoformat(),
    }
    source.status = "closed"
    source.queue_key = "closed"
    source.closed_at = now
    source.unread_count = 0
    source.conversation_metadata = {
        **(source.conversation_metadata or {}),
        "mail_category": "linked_to_lead",
        "resolution": "linked_to_existing_lead",
        "resolved_at": now.isoformat(),
        "resolved_by_user_id": str(principal.user_id),
        "merged_into_conversation_id": str(target.id),
        "lead_id": str(lead.id),
    }
    db.add(
        ConversationAssignmentEvent(
            organization_id=principal.organization_id,
            conversation_id=target.id,
            lead_id=lead.id,
            actor_user_id=principal.user_id,
            previous_assigned_user_id=target.assigned_user_id,
            assigned_user_id=target.assigned_user_id,
            previous_queue_key=target.queue_key,
            queue_key=target.queue_key,
            reason="General email linked to this existing seller lead.",
        )
    )
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            event_type="lead.email_linked",
            summary=f"Inbound email from {source_contact.legal_name} linked to this lead.",
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="inbox.link_to_lead",
            entity_type="conversation",
            entity_id=source.id,
            previous_value={"lead_id": None, "communication_count": len(communication_ids)},
            new_value={"lead_id": str(lead.id), "conversation_id": str(target.id)},
            reason="Merged general email into existing seller conversation",
        )
    )
    db.commit()
    return ConversationResolutionRead(
        action="linked_to_existing_lead",
        source_conversation_id=source.id,
        conversation_id=target.id,
        lead_id=lead.id,
        status="open",
        message="Email history linked to the existing seller lead.",
    )


def classify_general_conversation(
    db: Session,
    principal: Principal,
    conversation_id: UUID,
    payload: GeneralConversationClassification,
) -> ConversationResolutionRead | None:
    conversation = get_scoped_conversation(db, principal, conversation_id)
    if conversation is None:
        return None
    _require_general_conversation(conversation)
    now = datetime.now(UTC)
    conversation.status = "closed" if payload.close else "open"
    conversation.queue_key = "closed" if payload.close else "unassigned"
    conversation.closed_at = now if payload.close else None
    if payload.close:
        conversation.unread_count = 0
    conversation.conversation_metadata = {
        **(conversation.conversation_metadata or {}),
        "mail_category": payload.category,
        "classified_at": now.isoformat(),
        "classified_by_user_id": str(principal.user_id),
        "classification_reason": payload.reason.strip() if payload.reason else None,
    }
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="inbox.classify_general_email",
            entity_type="conversation",
            entity_id=conversation.id,
            previous_value=None,
            new_value={"category": payload.category, "closed": payload.close},
            reason=payload.reason or "Classified from the Stonegate inbox",
        )
    )
    db.commit()
    return ConversationResolutionRead(
        action="classified",
        source_conversation_id=conversation.id,
        conversation_id=conversation.id,
        lead_id=None,
        status=conversation.status,
        message=(
            f"Email marked as {payload.category.replace('_', ' ')} and archived."
            if payload.close
            else "Email restored to the active inbox."
        ),
    )


def _require_general_conversation(conversation: Conversation) -> None:
    if conversation.conversation_type != "general" or conversation.lead_id is not None:
        raise ValueError("Only general email conversations can use this action.")


def _latest_datetime(*values: datetime | None) -> datetime | None:
    available = [value for value in values if value is not None]
    return (
        max(
            available,
            key=lambda value: (
                value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
            ),
        )
        if available
        else None
    )


def update_conversation_activity(
    conversation: Conversation,
    *,
    direction: str,
    occurred_at: datetime,
    db: Session | None = None,
    reactivate_closed_lead: bool = True,
) -> None:
    if direction == "inbound" and reactivate_closed_lead and db is not None:
        reactivate_closed_lead_for_inbound(db, conversation, occurred_at=occurred_at)
        lead = (
            db.get(Lead, conversation.lead_id)
            if conversation.conversation_type == "lead" and conversation.lead_id is not None
            else None
        )
        if (
            lead is not None
            and lead.archived_at is not None
            and lead.stage_key in {"dead", "disqualified"}
            and lead.closed_out_at is not None
            and _as_utc_datetime(occurred_at) <= _as_utc_datetime(lead.closed_out_at)
        ):
            return
    conversation.last_activity_at = _latest_datetime(
        conversation.last_activity_at,
        occurred_at,
    )
    if direction == "inbound":
        conversation.last_inbound_at = _latest_datetime(
            conversation.last_inbound_at,
            occurred_at,
        )
        if reactivate_closed_lead or conversation.status != "closed":
            conversation.unread_count += 1
    elif direction == "outbound":
        conversation.last_outbound_at = _latest_datetime(
            conversation.last_outbound_at,
            occurred_at,
        )


def reactivate_closed_lead_for_inbound(
    db: Session,
    conversation: Conversation,
    *,
    occurred_at: datetime,
) -> Lead | None:
    if conversation.conversation_type != "lead" or conversation.lead_id is None:
        return None
    lead = db.scalar(
        select(Lead)
        .where(
            Lead.organization_id == conversation.organization_id,
            Lead.id == conversation.lead_id,
        )
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    if lead is None:
        return None
    is_business_closed = (
        lead.archived_at is not None
        and lead.stage_key in {"dead", "disqualified"}
        and lead.close_out_disposition in {"dead", "disqualified"}
        and lead.closed_out_at is not None
    )
    if not is_business_closed:
        if conversation.status == "closed":
            previous_queue_key = conversation.queue_key
            conversation.status = "open"
            conversation.queue_key = "acquisitions_follow_up"
            conversation.closed_at = None
            db.add(
                ConversationAssignmentEvent(
                    organization_id=conversation.organization_id,
                    conversation_id=conversation.id,
                    lead_id=lead.id,
                    actor_user_id=None,
                    previous_assigned_user_id=conversation.assigned_user_id,
                    assigned_user_id=conversation.assigned_user_id,
                    previous_queue_key=previous_queue_key,
                    queue_key=conversation.queue_key,
                    reason="Inbound seller contact reopened the conversation.",
                    created_at=datetime.now(UTC),
                )
            )
        return None
    if lead.closed_out_at is not None and _as_utc_datetime(occurred_at) <= _as_utc_datetime(
        lead.closed_out_at
    ):
        return None

    now = datetime.now(UTC)
    due_at = max(_as_utc_datetime(occurred_at), now) + timedelta(minutes=5)
    previous = {
        "stage_key": lead.stage_key,
        "archived_at": lead.archived_at.isoformat() if lead.archived_at else None,
        "next_follow_up_at": (
            lead.next_follow_up_at.isoformat() if lead.next_follow_up_at else None
        ),
    }
    stale_primary_tasks = list(
        db.scalars(
            select(Task).where(
                Task.organization_id == lead.organization_id,
                Task.lead_id == lead.id,
                Task.work_kind == "primary_next_action",
                Task.status.in_(("open", "in_progress")),
            )
        ).all()
    )
    for task in stale_primary_tasks:
        task.status = "cancelled"
        task.completed_at = now
        task.outcome = "superseded_by_inbound_reactivation"
    if stale_primary_tasks:
        db.flush()

    lead.archived_at = None
    lead.stage_key = "reopened"
    lead.next_follow_up_at = due_at
    management_case = db.scalar(
        select(LeadManagementCase).where(
            LeadManagementCase.organization_id == lead.organization_id,
            LeadManagementCase.lead_id == lead.id,
        )
    )
    if management_case is not None:
        management_case.status = "active"
        management_case.closed_at = None
        management_case.accepted_at = management_case.accepted_at or now
        management_case.accepted_by_user_id = (
            management_case.accepted_by_user_id or management_case.assigned_user_id
        )
        management_case.qualification_started_at = management_case.qualification_started_at or now
        management_case.next_action_type = "respond_to_inbound"
        management_case.next_action_due_at = due_at

    sync_conversation_to_lead_stage(
        db,
        lead,
        actor_user_id=None,
        reason="Inbound seller contact automatically reopened the lead.",
    )
    task = Task(
        organization_id=lead.organization_id,
        lead_id=lead.id,
        deal_id=None,
        responsible_user_id=(
            lead.assigned_user_id
            or (management_case.assigned_user_id if management_case is not None else None)
            or conversation.assigned_user_id
        ),
        task_type="inbound_reactivation",
        work_kind="primary_next_action",
        title="Respond to seller who contacted Stonegate",
        status="open",
        priority="urgent",
        due_at=due_at,
        completed_at=None,
    )
    db.add(task)
    db.flush()
    db.add(
        ActivityEvent(
            organization_id=lead.organization_id,
            actor_user_id=None,
            entity_type="lead",
            entity_id=lead.id,
            event_type="lead.auto_reopened_from_inbound",
            summary="Inbound seller contact automatically reopened the lead for urgent follow-up.",
        )
    )
    db.add(
        AuditEvent(
            organization_id=lead.organization_id,
            actor_user_id=None,
            actor_type="system",
            action="lead.auto_reopen_inbound",
            entity_type="lead",
            entity_id=lead.id,
            previous_value=previous,
            new_value={
                "stage_key": "reopened",
                "archived_at": None,
                "next_follow_up_at": due_at.isoformat(),
                "primary_next_action_task_id": str(task.id),
            },
            reason="Seller initiated a new inbound communication.",
        )
    )
    return lead


def _as_utc_datetime(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def sync_conversation_to_lead_stage(
    db: Session,
    lead: Lead,
    *,
    actor_user_id: UUID | None,
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
    desired_status = "closed" if queue_key == "closed" else "open"
    state_already_synced = (
        conversation.queue_key == queue_key
        and conversation.status == desired_status
        and ((conversation.closed_at is not None) == (desired_status == "closed"))
    )
    if state_already_synced:
        return

    previous_queue_key = conversation.queue_key
    conversation.queue_key = queue_key
    conversation.last_activity_at = datetime.now(UTC)
    if desired_status == "closed":
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
    if not principal_has_owner_mailbox_access(db, principal):
        filters.append(conversation_access_filter(db, principal))
    if assigned_to_me:
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


def get_mailbox_response_overview(
    db: Session,
    principal: Principal,
) -> MailboxResponseOverviewRead:
    conversations = list_conversations(db, principal, limit=1000)
    alias_labels = {
        alias.id: f"{alias.display_name} · {alias.email_address}"
        for alias in db.scalars(
            select(EmailSenderAlias).where(
                EmailSenderAlias.organization_id == principal.organization_id
            )
        ).all()
    }
    team_labels = {
        team.id: team.name
        for team in db.scalars(
            select(Team).where(Team.organization_id == principal.organization_id)
        ).all()
    }
    user_labels = {
        user.id: user.display_name
        for user in db.scalars(
            select(User).where(User.organization_id == principal.organization_id)
        ).all()
    }
    return MailboxResponseOverviewRead(
        conversation_count=len(conversations),
        needs_reply_count=sum(item.response_state != "none" for item in conversations),
        overdue_count=sum(item.response_state == "overdue" for item in conversations),
        oldest_wait_minutes=_oldest_wait_minutes(conversations),
        by_alias=_response_buckets(
            conversations,
            key_name="source_alias_id",
            labels=alias_labels,
            empty_label="No email alias",
        ),
        by_team=_response_buckets(
            conversations,
            key_name="assigned_team_id",
            labels=team_labels,
            empty_label="No assigned team",
        ),
        by_assignee=_response_buckets(
            conversations,
            key_name="assigned_user_id",
            labels=user_labels,
            empty_label="Unassigned",
        ),
    )


def _response_buckets(
    conversations: list[ConversationRead],
    *,
    key_name: str,
    labels: dict[UUID, str],
    empty_label: str,
) -> list[MailboxResponseBucketRead]:
    grouped: dict[UUID | None, list[ConversationRead]] = {}
    for conversation in conversations:
        scope_id = getattr(conversation, key_name)
        grouped.setdefault(scope_id, []).append(conversation)
    buckets = [
        MailboxResponseBucketRead(
            scope_id=scope_id,
            scope_label=labels.get(scope_id, empty_label) if scope_id is not None else empty_label,
            conversation_count=len(items),
            needs_reply_count=sum(item.response_state != "none" for item in items),
            overdue_count=sum(item.response_state == "overdue" for item in items),
            oldest_wait_minutes=_oldest_wait_minutes(items),
        )
        for scope_id, items in grouped.items()
    ]
    return sorted(
        buckets,
        key=lambda item: (
            -item.overdue_count,
            -item.needs_reply_count,
            item.scope_label.lower(),
        ),
    )


def _oldest_wait_minutes(conversations: list[ConversationRead]) -> int | None:
    ages = [
        item.response_age_minutes for item in conversations if item.response_age_minutes is not None
    ]
    return max(ages) if ages else None


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
    contact = db.get(Contact, conversation.contact_id)
    if contact is None:
        raise RuntimeError("Conversation is missing its contact.")
    lead = db.get(Lead, conversation.lead_id) if conversation.lead_id is not None else None
    if conversation.conversation_type == "lead" and lead is None:
        raise RuntimeError("Lead conversation is missing its lead.")
    property_record = db.get(Property, lead.property_id) if lead is not None else None
    if lead is not None and property_record is None:
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
            .options(defer(EmailAttachment.content_data))
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
        attachments_by_communication_id.setdefault(attachment.communication_record_id, []).append(
            attachment
        )
    dispatches = (
        db.scalars(
            select(CommunicationDispatch).where(
                CommunicationDispatch.organization_id == principal.organization_id,
                CommunicationDispatch.communication_record_id.in_(communication_ids),
            )
        ).all()
        if communication_ids
        else []
    )
    dispatch_by_communication_id = {
        dispatch.communication_record_id: dispatch
        for dispatch in dispatches
        if dispatch.communication_record_id is not None
    }
    source_call_ids = [
        item.source_call_record_id
        for item in communications
        if item.source_call_record_id is not None
    ]
    calls = (
        db.scalars(
            select(CallRecord).where(
                CallRecord.organization_id == principal.organization_id,
                or_(
                    CallRecord.communication_record_id.in_(communication_ids),
                    CallRecord.id.in_(source_call_ids),
                ),
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
    calls_by_id = {call.id: call for call in calls}
    call_ids = list(calls_by_id)
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
    tasks = (
        db.scalars(
            select(Task)
            .where(
                Task.organization_id == principal.organization_id,
                Task.lead_id == lead.id,
                Task.status.in_(("open", "in_progress")),
            )
            .order_by(Task.due_at.is_(None), Task.due_at.asc(), Task.created_at.asc())
            .limit(20)
        ).all()
        if lead is not None
        else []
    )
    appointments = (
        db.scalars(
            select(Appointment)
            .where(
                Appointment.organization_id == principal.organization_id,
                Appointment.lead_id == lead.id,
            )
            .order_by(Appointment.scheduled_start_at.asc(), Appointment.created_at.asc())
            .limit(20)
        ).all()
        if lead is not None
        else []
    )

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
        call = call_by_communication_id.get(item.id) or (
            calls_by_id.get(item.source_call_record_id)
            if item.source_call_record_id is not None
            else None
        )
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
                status_detail=(
                    dispatch_by_communication_id[item.id].error_message
                    if item.id in dispatch_by_communication_id
                    else None
                ),
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
                        content_url=(
                            f"/api/v1/inbox/attachments/{attachment.id}/content"
                            if attachment.storage_provider
                            else f"/api/v1/email/attachments/{attachment.id}"
                        ),
                    )
                    for attachment in attachments_by_communication_id.get(item.id, [])
                    if not (
                        attachment.disposition.strip().lower() == "inline"
                        and bool((attachment.content_id or "").strip())
                    )
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
        source=lead.source if lead is not None else None,
        stage_key=lead.stage_key if lead is not None else None,
        lead_temperature=lead.lead_temperature if lead is not None else None,
        motivation=lead.motivation if lead is not None else None,
        desired_timeline=lead.desired_timeline if lead is not None else None,
        property_condition=lead.property_condition if lead is not None else None,
        occupancy_status=lead.occupancy_status if lead is not None else None,
        appointment_status=lead.appointment_status if lead is not None else None,
        next_follow_up_at=lead.next_follow_up_at if lead is not None else None,
        property_type=property_record.property_type if property_record is not None else None,
        asset_class=normalize_asset_class(lead.asset_class) if lead is not None else None,
        property_parcel_id=property_record.parcel_id if property_record is not None else None,
        property_county=property_record.county if property_record is not None else None,
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


def get_inbox_attachment_content(
    db: Session,
    principal: Principal,
    attachment_id: UUID,
) -> tuple[EmailAttachment, bytes] | None:
    attachment = db.scalar(
        select(EmailAttachment).where(
            EmailAttachment.id == attachment_id,
            EmailAttachment.organization_id == principal.organization_id,
        )
    )
    if attachment is None or not attachment.storage_provider:
        return None
    communication = db.get(CommunicationRecord, attachment.communication_record_id)
    if communication is None or communication.conversation_id is None:
        return None
    if get_scoped_conversation(db, principal, communication.conversation_id) is None:
        return None
    content = read_content(
        provider=attachment.storage_provider,
        key=attachment.storage_key,
        database_bytes=attachment.content_data,
    )
    return attachment, content


def mark_conversation_read(
    db: Session,
    principal: Principal,
    conversation_id: UUID,
) -> ConversationRead | None:
    conversation = get_scoped_conversation(db, principal, conversation_id)
    if conversation is None:
        return None
    notifications = db.scalars(
        select(Notification).where(
            Notification.organization_id == principal.organization_id,
            Notification.recipient_user_id == principal.user_id,
            Notification.entity_type == "conversation",
            Notification.entity_id == conversation.id,
            Notification.notification_type.in_(MAILBOX_NOTIFICATION_TYPES),
            Notification.read_at.is_(None),
        )
    ).all()
    had_unread = conversation.unread_count > 0
    if had_unread:
        conversation.unread_count = 0
    for notification in notifications:
        notification.read_at = datetime.now(UTC)
    if had_unread or notifications:
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
    conversation_identity = db.execute(
        select(Conversation.conversation_type, Conversation.lead_id).where(
            Conversation.organization_id == principal.organization_id,
            Conversation.id == conversation_id,
        )
    ).one_or_none()
    if conversation_identity is None:
        return None
    if conversation_identity.lead_id is not None:
        lead = lock_organization_lead(
            db,
            organization_id=principal.organization_id,
            lead_id=conversation_identity.lead_id,
        )
        if lead is None:
            return None
        require_lead_open_for_work(lead)
    conversation = db.scalar(
        select(Conversation)
        .where(
            Conversation.organization_id == principal.organization_id,
            Conversation.id == conversation_id,
        )
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    if conversation is None:
        return None
    if conversation.lead_id is None and conversation.conversation_type != "buyer":
        raise ValueError(
            "General conversation assignment is introduced in the mailbox routing phase."
        )

    can_manage_all = PermissionKeys.MANAGE_CONVERSATION_ASSIGNMENTS in principal.permission_keys
    if not can_manage_all and (
        PermissionKeys.HANDOFF_ASSIGNED_CONVERSATIONS not in principal.permission_keys
        or conversation.assigned_user_id != principal.user_id
    ):
        raise PermissionError("Conversation is not assigned to the current user.")

    allowed_queue_keys = (
        {"dispositions"}
        if conversation.conversation_type == "buyer"
        else {"qualified", "appointment_set", "acquisitions_follow_up"}
    )
    if can_manage_all and conversation.conversation_type == "lead":
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
        raise ValueError("Assignment target must have an operational communications role.")
    if conversation.conversation_type == "buyer":
        if not target_role_keys.intersection(ELIGIBLE_DISPOSITION_ROLE_KEYS):
            raise ValueError("Buyer conversations require an active dispositions user.")
        buyer_id = db.scalar(
            select(ConversationContextLink.buyer_id).where(
                ConversationContextLink.organization_id == principal.organization_id,
                ConversationContextLink.conversation_id == conversation.id,
                ConversationContextLink.context_type == "buyer",
            )
        )
        if buyer_id is None:
            raise ValueError("Buyer conversation is missing its buyer record.")
        previous_assigned_user_id = conversation.assigned_user_id
        previous_queue_key = conversation.queue_key
        conversation.assigned_user_id = target.id
        conversation.queue_key = "dispositions"
        conversation.status = "open"
        conversation.closed_at = None
        conversation.last_activity_at = datetime.now(UTC)
        contact = db.get(Contact, conversation.contact_id)
        if contact is not None:
            contact.assigned_user_id = target.id
        db.add(
            ConversationAssignmentEvent(
                organization_id=principal.organization_id,
                conversation_id=conversation.id,
                lead_id=None,
                actor_user_id=principal.user_id,
                previous_assigned_user_id=previous_assigned_user_id,
                assigned_user_id=target.id,
                previous_queue_key=previous_queue_key,
                queue_key="dispositions",
                reason=payload.reason,
                created_at=datetime.now(UTC),
            )
        )
        ensure_watcher(
            db,
            conversation,
            target,
            source="assignment",
            notification_level="all",
        )
        add_automatic_owner_watchers(db, conversation)
        db.add(
            ActivityEvent(
                organization_id=principal.organization_id,
                actor_user_id=principal.user_id,
                entity_type="buyer",
                entity_id=buyer_id,
                event_type="buyer.conversation_assigned",
                summary=f"Buyer conversation assigned to {target.display_name}.",
            )
        )
        db.add(
            AuditEvent(
                organization_id=principal.organization_id,
                actor_user_id=principal.user_id,
                actor_type="user",
                action="conversation.assign",
                entity_type="conversation",
                entity_id=conversation.id,
                previous_value={
                    "assigned_user_id": (
                        str(previous_assigned_user_id) if previous_assigned_user_id else None
                    ),
                    "queue_key": previous_queue_key,
                },
                new_value={
                    "assigned_user_id": str(target.id),
                    "queue_key": "dispositions",
                },
                reason=payload.reason,
            )
        )
        db.commit()
        db.refresh(conversation)
        return conversation_to_read(db, conversation)
    if payload.queue_key == "va_prospecting" and "prospecting_caller" not in target_role_keys:
        raise ValueError("VA prospecting conversations must be assigned to a prospecting caller.")
    if payload.queue_key != "va_prospecting" and not target_role_keys.intersection(
        ELIGIBLE_ACQUISITION_ROLE_KEYS
    ):
        raise ValueError("Handoff target must be an active acquisition user.")

    lead = db.get(Lead, conversation.lead_id)
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
        "conversation.assign" if payload.queue_key == "va_prospecting" else "conversation.handoff"
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
                f"Conversation {activity_verb} to {target.display_name} in {payload.queue_key}."
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
    if not principal_has_owner_mailbox_access(db, principal):
        filters.append(conversation_access_filter(db, principal))
    return db.scalar(select(Conversation).where(*filters))


def principal_has_owner_mailbox_access(
    db: Session,
    principal: Principal,
) -> bool:
    role_key = db.scalar(
        select(Role.key)
        .join(RoleAssignment, RoleAssignment.role_id == Role.id)
        .where(
            RoleAssignment.organization_id == principal.organization_id,
            RoleAssignment.user_id == principal.user_id,
            Role.key.in_(OWNER_WATCHER_ROLE_KEYS),
        )
    )
    return role_key is not None


def conversation_access_filter(
    db: Session,
    principal: Principal,
) -> ColumnElement[bool]:
    team_ids = select(TeamMembership.team_id).where(
        TeamMembership.organization_id == principal.organization_id,
        TeamMembership.user_id == principal.user_id,
    )
    watched_conversation_ids = select(ConversationWatcher.conversation_id).where(
        ConversationWatcher.organization_id == principal.organization_id,
        ConversationWatcher.user_id == principal.user_id,
    )
    granted_alias_ids = select(EmailSenderGrant.email_sender_alias_id).where(
        EmailSenderGrant.organization_id == principal.organization_id,
        EmailSenderGrant.user_id == principal.user_id,
    )
    owned_alias_ids = select(EmailSenderAlias.id).where(
        EmailSenderAlias.organization_id == principal.organization_id,
        EmailSenderAlias.owner_user_id == principal.user_id,
        EmailSenderAlias.status == "active",
    )
    access = [
        Conversation.assigned_user_id == principal.user_id,
        Conversation.assigned_team_id.in_(team_ids),
        Conversation.id.in_(watched_conversation_ids),
        Conversation.source_alias_id.in_(granted_alias_ids),
        Conversation.source_alias_id.in_(owned_alias_ids),
    ]
    if PermissionKeys.VIEW_CONVERSATIONS in principal.permission_keys:
        access.append(
            and_(
                Conversation.conversation_type == "lead",
                Conversation.visibility_scope == "standard",
            )
        )
    if PermissionKeys.VIEW_BUYERS in principal.permission_keys:
        access.append(
            and_(
                Conversation.conversation_type == "buyer",
                Conversation.visibility_scope == "standard",
            )
        )
    return or_(*access)


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
    contact = db.get(Contact, conversation.contact_id)
    assigned_user = (
        db.get(User, conversation.assigned_user_id) if conversation.assigned_user_id else None
    )
    if contact is None:
        raise RuntimeError("Conversation is missing its contact.")
    lead = db.get(Lead, conversation.lead_id) if conversation.lead_id is not None else None
    if conversation.conversation_type == "lead" and lead is None:
        raise RuntimeError("Lead conversation is missing its lead.")
    property_record = db.get(Property, lead.property_id) if lead is not None else None
    if lead is not None and property_record is None:
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
    response = mailbox_response_status(
        conversation,
        get_settings(),
        latest_inbound_channel=latest_inbound_channel(db, conversation),
    )
    buyer_id = db.scalar(
        select(ConversationContextLink.buyer_id).where(
            ConversationContextLink.organization_id == conversation.organization_id,
            ConversationContextLink.conversation_id == conversation.id,
            ConversationContextLink.context_type == "buyer",
        )
    )
    metadata = conversation.conversation_metadata or {}
    contact_display_name = contact.legal_name
    if conversation.conversation_type == "general":
        contact_email = db.scalar(
            select(ContactMethod.normalized_value)
            .where(
                ContactMethod.organization_id == conversation.organization_id,
                ContactMethod.contact_id == contact.id,
                ContactMethod.method_type == "email",
            )
            .order_by(ContactMethod.is_primary.desc(), ContactMethod.created_at.asc())
            .limit(1)
        )
        contact_display_name = general_email_display_name(contact.legal_name, contact_email)
    return ConversationRead(
        id=conversation.id,
        conversation_type=conversation.conversation_type,
        lead_id=conversation.lead_id,
        buyer_id=buyer_id,
        contact_id=conversation.contact_id,
        seller_name=contact_display_name,
        property_address=(
            property_identity_label(
                street_address=property_record.street_address,
                city=property_record.city,
                state=property_record.state,
                postal_code=property_record.postal_code,
                parcel_id=property_record.parcel_id,
                county=property_record.county,
            )
            if property_record is not None
            else (
                "Buyer relationship"
                if conversation.conversation_type == "buyer"
                else str(metadata.get("initial_subject") or "General correspondence")
            )
        ),
        assigned_user_id=conversation.assigned_user_id,
        assigned_user_email=assigned_user.email if assigned_user else None,
        assigned_user_display_name=assigned_user.display_name if assigned_user else None,
        assigned_team_id=conversation.assigned_team_id,
        source_alias_id=conversation.source_alias_id,
        visibility_scope=conversation.visibility_scope,
        status=conversation.status,
        queue_key=conversation.queue_key,
        priority=conversation.priority,
        mail_category=(str(metadata["mail_category"]) if metadata.get("mail_category") else None),
        merged_into_conversation_id=(
            UUID(str(metadata["merged_into_conversation_id"]))
            if metadata.get("merged_into_conversation_id")
            else None
        ),
        unread_count=conversation.unread_count,
        last_activity_at=conversation.last_activity_at,
        last_inbound_at=conversation.last_inbound_at,
        last_outbound_at=conversation.last_outbound_at,
        response_state=response.state,
        response_kind=response.kind,
        response_age_minutes=response.age_minutes,
        response_target_minutes=response.target_minutes,
        response_due_at=response.due_at,
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
