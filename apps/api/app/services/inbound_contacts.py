from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.foundation import (
    ActivityEvent,
    Buyer,
    ConsentRecord,
    Contact,
    ContactMethod,
    Conversation,
    Lead,
    Property,
    VoiceLine,
)
from app.services.ai_operations import enqueue_lead_created_ai_work
from app.services.communication_compliance import format_e164
from app.services.inbox import ensure_buyer_conversation, ensure_primary_conversation


def create_unknown_inbound_sms_conversation(
    db: Session,
    *,
    line: VoiceLine,
    sender: str,
) -> Conversation:
    if line.purpose_key == "buyer_relations":
        return _create_unknown_buyer_sms_conversation(db, line=line, sender=sender)
    return _create_unknown_seller_sms_conversation(db, line=line, sender=sender)


def _create_unknown_seller_sms_conversation(
    db: Session,
    *,
    line: VoiceLine,
    sender: str,
) -> Conversation:
    normalized = format_e164(sender) or sender
    assigned_user_id = line.assigned_user_id or line.fallback_user_id
    contact = Contact(
        organization_id=line.organization_id,
        legal_name=f"Inbound text {normalized}",
        preferred_name=None,
        contact_type="seller",
        assigned_user_id=assigned_user_id,
    )
    db.add(contact)
    db.flush()
    db.add(
        ContactMethod(
            organization_id=line.organization_id,
            contact_id=contact.id,
            method_type="phone",
            value=normalized,
            normalized_value="".join(character for character in normalized if character.isdigit()),
            is_primary=True,
        )
    )
    property_record = Property(
        organization_id=line.organization_id,
        street_address="Address pending",
        city="Unknown",
        state="GA",
        postal_code="00000",
        county=None,
        property_type=None,
        normalized_address_key=None,
    )
    db.add(property_record)
    db.flush()
    lead = Lead(
        organization_id=line.organization_id,
        contact_id=contact.id,
        property_id=property_record.id,
        assigned_user_id=assigned_user_id,
        source="inbound_sms",
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
    conversation = ensure_primary_conversation(db, lead)
    conversation.assigned_team_id = line.assigned_team_id
    conversation.conversation_metadata = {
        **(conversation.conversation_metadata or {}),
        "source": "inbound_sms",
        "voice_line_id": str(line.id),
        "department_key": line.department_key,
        "unknown_sender_review_required": True,
    }
    _record_inbound_sms_consent(
        db,
        organization_id=line.organization_id,
        contact_id=contact.id,
        party_label="Seller",
        normalized_address=normalized,
    )
    enqueue_lead_created_ai_work(db, lead, source="inbound_sms")
    db.add(
        ActivityEvent(
            organization_id=line.organization_id,
            actor_user_id=None,
            entity_type="lead",
            entity_id=lead.id,
            event_type="lead.created_from_inbound_sms",
            summary="New lead created from an unknown inbound text message.",
        )
    )
    return conversation


def _create_unknown_buyer_sms_conversation(
    db: Session,
    *,
    line: VoiceLine,
    sender: str,
) -> Conversation:
    normalized = format_e164(sender) or sender
    assigned_user_id = line.assigned_user_id or line.fallback_user_id
    buyer = Buyer(
        organization_id=line.organization_id,
        name=f"Inbound buyer text {normalized}",
        company_name=None,
        email=None,
        phone=normalized,
        buyer_type="cash_buyer",
        status="active",
        proof_of_funds_status="unknown",
        max_purchase_price_cents=None,
        reliability_score_basis_points=5000,
        completed_deals=0,
        failed_deals=0,
        proof_of_funds_expires_at=None,
        notes="Created automatically from an unknown inbound dispositions text.",
    )
    db.add(buyer)
    db.flush()
    conversation = ensure_buyer_conversation(
        db,
        buyer,
        actor_user_id=assigned_user_id,
    )
    contact = db.get(Contact, conversation.contact_id)
    if contact is None:
        raise RuntimeError("Unknown inbound buyer SMS did not create a contact.")
    contact.assigned_user_id = assigned_user_id
    conversation.assigned_user_id = assigned_user_id
    conversation.assigned_team_id = line.assigned_team_id
    conversation.conversation_metadata = {
        **(conversation.conversation_metadata or {}),
        "source": "inbound_sms",
        "voice_line_id": str(line.id),
        "department_key": line.department_key,
        "unknown_sender_review_required": True,
    }
    _record_inbound_sms_consent(
        db,
        organization_id=line.organization_id,
        contact_id=contact.id,
        party_label="Buyer",
        normalized_address=normalized,
    )
    db.add(
        ActivityEvent(
            organization_id=line.organization_id,
            actor_user_id=None,
            entity_type="buyer",
            entity_id=buyer.id,
            event_type="buyer.created_from_inbound_sms",
            summary="New buyer created from an unknown inbound dispositions text message.",
        )
    )
    return conversation


def _record_inbound_sms_consent(
    db: Session,
    *,
    organization_id: UUID,
    contact_id: UUID,
    party_label: str,
    normalized_address: str,
) -> None:
    now = datetime.now(UTC)
    db.add(
        ConsentRecord(
            organization_id=organization_id,
            contact_id=contact_id,
            channel="sms",
            status="granted",
            source="inbound_sms",
            wording_version="contact-initiated-sms-v1",
            wording=f"{party_label} initiated an SMS conversation with Stonegate.",
            normalized_address=normalized_address,
            captured_ip=None,
            user_agent=None,
            created_at=now,
            updated_at=now,
        )
    )
