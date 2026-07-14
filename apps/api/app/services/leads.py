from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.models.foundation import (
    ActivityEvent,
    AttributionTouch,
    AuditEvent,
    ConsentRecord,
    Contact,
    ContactMethod,
    ConversionEvent,
    Deal,
    Lead,
    Property,
    User,
)
from app.schemas.leads import (
    ActivityEventRead,
    AttributionTouchRead,
    ConsentRecordRead,
    ContactMethodRead,
    DashboardSummary,
    LeadCreate,
    LeadDetail,
    LeadRead,
    LeadStaffUpdate,
    LeadStageUpdate,
    PipelineStageCount,
    SourcePerformance,
)

PAID_LEAD_SOURCES = ("google_ppc", "meta_ads", "facebook_ads", "instagram_ads", "website")
SELLER_PIPELINE_STAGES = {
    "new",
    "contact_attempt_due",
    "attempting_contact",
    "contacted",
    "qualification_in_progress",
    "qualified",
    "appointment_scheduled",
    "underwriting",
    "offer_pending_approval",
    "offer_ready",
    "offer_presented",
    "negotiating",
    "long_term_follow_up",
    "under_contract",
    "disqualified",
    "dead",
    "reopened",
}


def create_lead(db: Session, principal: Principal, payload: LeadCreate) -> LeadRead:
    contact = Contact(
        organization_id=principal.organization_id,
        legal_name=payload.contact.legal_name,
        preferred_name=payload.contact.preferred_name,
        contact_type=payload.contact.contact_type,
        assigned_user_id=principal.user_id,
    )
    db.add(contact)
    db.flush()

    property_record = Property(
        organization_id=principal.organization_id,
        street_address=payload.property.street_address,
        city=payload.property.city,
        state=payload.property.state.upper(),
        postal_code=payload.property.postal_code,
        county=payload.property.county,
        property_type=payload.property.property_type,
    )
    db.add(property_record)
    db.flush()

    lead = Lead(
        organization_id=principal.organization_id,
        contact_id=contact.id,
        property_id=property_record.id,
        assigned_user_id=principal.user_id,
        source=payload.source,
        stage_key=payload.stage_key,
        lead_temperature=payload.lead_temperature,
    )
    db.add(lead)
    db.flush()

    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            event_type="lead.created",
            summary=f"Lead created for {contact.legal_name}.",
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="lead.create",
            entity_type="lead",
            entity_id=lead.id,
            previous_value=None,
            new_value={"source": lead.source, "stage_key": lead.stage_key},
            reason="Manual local lead creation",
        )
    )
    db.commit()
    db.refresh(lead)
    return lead_to_read(db, lead)


def list_leads(db: Session, principal: Principal, limit: int = 25) -> list[LeadRead]:
    leads = db.scalars(
        select(Lead)
        .where(Lead.organization_id == principal.organization_id)
        .order_by(Lead.created_at.desc())
        .limit(limit)
    ).all()
    return [lead_to_read(db, lead) for lead in leads]


def get_lead_detail(db: Session, principal: Principal, lead_id: UUID) -> LeadDetail | None:
    lead = get_scoped_lead(db, principal, lead_id)
    if lead is None:
        return None
    base = lead_to_read(db, lead)
    contact_methods = db.scalars(
        select(ContactMethod)
        .where(
            ContactMethod.organization_id == principal.organization_id,
            ContactMethod.contact_id == lead.contact_id,
        )
        .order_by(ContactMethod.created_at.asc())
    ).all()
    consent_records = db.scalars(
        select(ConsentRecord)
        .where(
            ConsentRecord.organization_id == principal.organization_id,
            ConsentRecord.contact_id == lead.contact_id,
        )
        .order_by(ConsentRecord.created_at.desc())
    ).all()
    attribution_touches = db.scalars(
        select(AttributionTouch)
        .where(
            AttributionTouch.organization_id == principal.organization_id,
            AttributionTouch.lead_id == lead.id,
        )
        .order_by(AttributionTouch.created_at.desc())
    ).all()
    recent_activity = db.scalars(
        select(ActivityEvent)
        .where(
            ActivityEvent.organization_id == principal.organization_id,
            ActivityEvent.entity_type == "lead",
            ActivityEvent.entity_id == lead.id,
        )
        .order_by(ActivityEvent.created_at.desc(), ActivityEvent.id.desc())
        .limit(20)
    ).all()

    return LeadDetail(
        **base.model_dump(),
        contact_methods=[
            ContactMethodRead(
                method_type=method.method_type,
                value=method.value,
                is_primary=method.is_primary,
            )
            for method in contact_methods
        ],
        consent_records=[
            ConsentRecordRead(
                channel=record.channel,
                status=record.status,
                source=record.source,
                wording_version=record.wording_version,
                captured_ip=record.captured_ip,
                created_at=record.created_at,
            )
            for record in consent_records
        ],
        attribution_touches=[
            AttributionTouchRead(
                touch_type=touch.touch_type,
                source=touch.source,
                medium=touch.medium,
                campaign=touch.campaign,
                term=touch.term,
                content=touch.content,
                gclid=touch.gclid,
                fbclid=touch.fbclid,
                landing_page=touch.landing_page,
                referrer=touch.referrer,
                created_at=touch.created_at,
            )
            for touch in attribution_touches
        ],
        recent_activity=[
            ActivityEventRead(
                event_type=activity.event_type,
                summary=activity.summary,
                created_at=activity.created_at,
            )
            for activity in recent_activity
        ],
    )


def update_lead_stage(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    payload: LeadStageUpdate,
) -> LeadDetail | None:
    if payload.stage_key not in SELLER_PIPELINE_STAGES:
        raise ValueError(f"Unsupported seller pipeline stage: {payload.stage_key}")

    lead = get_scoped_lead(db, principal, lead_id)
    if lead is None:
        return None
    previous_stage = lead.stage_key
    if previous_stage == payload.stage_key:
        return get_lead_detail(db, principal, lead_id)

    lead.stage_key = payload.stage_key
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            event_type="lead.stage_changed",
            summary=f"Lead stage changed from {previous_stage} to {payload.stage_key}.",
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="lead.stage_update",
            entity_type="lead",
            entity_id=lead.id,
            previous_value={"stage_key": previous_stage},
            new_value={"stage_key": payload.stage_key},
            reason=payload.reason,
        )
    )
    db.commit()
    db.refresh(lead)
    return get_lead_detail(db, principal, lead_id)


def update_lead_staff_details(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    payload: LeadStaffUpdate,
) -> LeadDetail | None:
    lead = get_scoped_lead(db, principal, lead_id)
    if lead is None:
        return None

    contact = db.get(Contact, lead.contact_id)
    property_record = db.get(Property, lead.property_id)
    if contact is None or property_record is None:
        raise RuntimeError("lead is missing required contact or property")

    previous_values: dict[str, Any] = {}
    new_values: dict[str, Any] = {}

    provided_fields = payload.model_fields_set

    update_value(previous_values, new_values, contact, "legal_name", payload.seller_name)
    update_nullable_value(
        previous_values,
        new_values,
        contact,
        "preferred_name",
        payload.preferred_name,
        provided_fields,
    )
    update_value(previous_values, new_values, lead, "source", payload.source)
    update_nullable_value(
        previous_values,
        new_values,
        lead,
        "lead_temperature",
        payload.lead_temperature,
        provided_fields,
    )
    update_value(
        previous_values,
        new_values,
        property_record,
        "street_address",
        payload.property_street_address,
    )
    update_value(previous_values, new_values, property_record, "city", payload.property_city)
    if payload.property_state is not None:
        update_value(
            previous_values,
            new_values,
            property_record,
            "state",
            payload.property_state.upper(),
        )
    update_value(
        previous_values,
        new_values,
        property_record,
        "postal_code",
        payload.property_postal_code,
    )
    update_nullable_value(
        previous_values,
        new_values,
        property_record,
        "county",
        payload.property_county,
        provided_fields,
        provided_field_name="property_county",
    )
    update_nullable_value(
        previous_values,
        new_values,
        property_record,
        "property_type",
        payload.property_type,
        provided_fields,
    )

    phone_changed = update_contact_method(
        db,
        principal,
        contact,
        previous_values,
        new_values,
        method_type="phone",
        value=payload.phone,
    )
    email_changed = update_contact_method(
        db,
        principal,
        contact,
        previous_values,
        new_values,
        method_type="email",
        value=payload.email,
    )

    if property_fields_changed(previous_values) or property_fields_changed(new_values):
        property_record.normalized_address_key = normalize_address_key(
            property_record.street_address,
            property_record.city,
            property_record.state,
            property_record.postal_code,
        )

    if previous_values or new_values or phone_changed or email_changed:
        db.add(
            ActivityEvent(
                organization_id=principal.organization_id,
                actor_user_id=principal.user_id,
                entity_type="lead",
                entity_id=lead.id,
                event_type="lead.staff_updated",
                summary=f"Lead details updated for {contact.legal_name}.",
            )
        )
        db.add(
            AuditEvent(
                organization_id=principal.organization_id,
                actor_user_id=principal.user_id,
                actor_type="user",
                action="lead.staff_update",
                entity_type="lead",
                entity_id=lead.id,
                previous_value=previous_values,
                new_value=new_values,
                reason=payload.reason,
            )
        )
        db.commit()
        db.refresh(lead)

    return get_lead_detail(db, principal, lead_id)


def get_dashboard_summary(db: Session, principal: Principal) -> DashboardSummary:
    total_leads = count_scalar(db, select(func.count(Lead.id)).where(
        Lead.organization_id == principal.organization_id
    ))
    new_paid_leads = count_scalar(db, select(func.count(Lead.id)).where(
        Lead.organization_id == principal.organization_id,
        Lead.stage_key == "new",
        Lead.source.in_(PAID_LEAD_SOURCES),
    ))
    active_contracts = count_scalar(db, select(func.count(Deal.id)).where(
        Deal.organization_id == principal.organization_id,
        Deal.stage_key == "under_contract",
    ))
    collected_revenue_cents = int(
        db.scalar(
            select(func.coalesce(func.sum(Deal.assignment_fee_cents), 0)).where(
                Deal.organization_id == principal.organization_id,
                Deal.stage_key == "closed",
            )
        )
        or 0
    )
    pipeline_rows = db.execute(
        select(Lead.stage_key, func.count(Lead.id))
        .where(Lead.organization_id == principal.organization_id)
        .group_by(Lead.stage_key)
        .order_by(Lead.stage_key)
    ).all()

    return DashboardSummary(
        total_leads=total_leads,
        new_paid_leads=new_paid_leads,
        active_contracts=active_contracts,
        offers_pending=0,
        collected_revenue_cents=collected_revenue_cents,
        pipeline=[
            PipelineStageCount(stage_key=str(stage_key), count=int(count))
            for stage_key, count in pipeline_rows
        ],
        source_performance=get_source_performance(db, principal),
    )


def get_source_performance(db: Session, principal: Principal) -> list[SourcePerformance]:
    source_rows: dict[tuple[str, str, str], dict[str, int | str]] = {}
    event_rows = db.execute(
        select(
            ConversionEvent.source,
            ConversionEvent.medium,
            ConversionEvent.campaign,
            ConversionEvent.event_type,
            func.count(ConversionEvent.id),
        )
        .where(ConversionEvent.organization_id == principal.organization_id)
        .group_by(
            ConversionEvent.source,
            ConversionEvent.medium,
            ConversionEvent.campaign,
            ConversionEvent.event_type,
        )
    ).all()

    for source, medium, campaign, event_type, count in event_rows:
        row = ensure_source_performance_row(source_rows, source, medium, campaign)
        count_value = int(count)
        if event_type == "page_view":
            row["page_views"] = int(row["page_views"]) + count_value
        elif event_type == "form_start":
            row["form_starts"] = int(row["form_starts"]) + count_value
        elif event_type == "form_submit":
            row["form_submits"] = int(row["form_submits"]) + count_value
        elif event_type == "call_click":
            row["call_clicks"] = int(row["call_clicks"]) + count_value

    lead_rows = db.execute(
        select(Lead.source, func.count(Lead.id))
        .where(Lead.organization_id == principal.organization_id)
        .group_by(Lead.source)
    ).all()
    for source, count in lead_rows:
        row = ensure_source_performance_row(source_rows, source, None, None)
        row["leads_created"] = int(row["leads_created"]) + int(count)

    return [
        SourcePerformance(
            source=str(row["source"]),
            medium=str(row["medium"]),
            campaign=str(row["campaign"]),
            page_views=int(row["page_views"]),
            form_starts=int(row["form_starts"]),
            form_submits=int(row["form_submits"]),
            call_clicks=int(row["call_clicks"]),
            leads_created=int(row["leads_created"]),
        )
        for row in sorted(
            source_rows.values(),
            key=lambda item: (
                -int(item["leads_created"]),
                -int(item["form_submits"]),
                -int(item["form_starts"]),
                -int(item["page_views"]),
                str(item["source"]),
            ),
        )
    ][:10]


def ensure_source_performance_row(
    source_rows: dict[tuple[str, str, str], dict[str, int | str]],
    source: str | None,
    medium: str | None,
    campaign: str | None,
) -> dict[str, int | str]:
    key = (
        source or "direct",
        medium or "unknown",
        campaign or "uncategorized",
    )
    if key not in source_rows:
        source_rows[key] = {
            "source": key[0],
            "medium": key[1],
            "campaign": key[2],
            "page_views": 0,
            "form_starts": 0,
            "form_submits": 0,
            "call_clicks": 0,
            "leads_created": 0,
        }
    return source_rows[key]


def count_scalar(db: Session, statement: Any) -> int:
    return int(db.scalar(statement) or 0)


def get_scoped_lead(db: Session, principal: Principal, lead_id: UUID) -> Lead | None:
    return db.scalar(
        select(Lead).where(
            Lead.organization_id == principal.organization_id,
            Lead.id == lead_id,
        )
    )


def update_value(
    previous_values: dict[str, Any],
    new_values: dict[str, Any],
    target: Any,
    field_name: str,
    value: str | None,
) -> None:
    if value is None:
        return
    cleaned_value = value.strip()
    if not cleaned_value:
        return
    current_value = getattr(target, field_name)
    if current_value == cleaned_value:
        return
    previous_values[field_name] = current_value
    new_values[field_name] = cleaned_value
    setattr(target, field_name, cleaned_value)


def update_nullable_value(
    previous_values: dict[str, Any],
    new_values: dict[str, Any],
    target: Any,
    field_name: str,
    value: str | None,
    provided_fields: set[str],
    *,
    provided_field_name: str | None = None,
) -> None:
    if (provided_field_name or field_name) not in provided_fields:
        return
    cleaned_value = normalize_blank(value) if value is not None else None
    current_value = getattr(target, field_name)
    if current_value == cleaned_value:
        return
    previous_values[field_name] = current_value
    new_values[field_name] = cleaned_value
    setattr(target, field_name, cleaned_value)


def update_contact_method(
    db: Session,
    principal: Principal,
    contact: Contact,
    previous_values: dict[str, Any],
    new_values: dict[str, Any],
    *,
    method_type: str,
    value: str | None,
) -> bool:
    if value is None:
        return False

    cleaned_value = value.strip()
    if not cleaned_value:
        return False

    normalized_value = (
        normalize_email(cleaned_value)
        if method_type == "email"
        else normalize_phone(cleaned_value)
    )
    if not normalized_value:
        return False

    existing = db.scalar(
        select(ContactMethod)
        .where(
            ContactMethod.organization_id == principal.organization_id,
            ContactMethod.contact_id == contact.id,
            ContactMethod.method_type == method_type,
        )
        .order_by(ContactMethod.is_primary.desc(), ContactMethod.created_at.asc())
    )
    audit_key = f"{method_type}_contact_method"
    if existing is not None:
        if existing.value == cleaned_value and existing.normalized_value == normalized_value:
            return False
        previous_values[audit_key] = existing.value
        new_values[audit_key] = cleaned_value
        existing.value = cleaned_value
        existing.normalized_value = normalized_value
        existing.is_primary = True
        return True

    db.add(
        ContactMethod(
            organization_id=principal.organization_id,
            contact_id=contact.id,
            method_type=method_type,
            value=cleaned_value,
            normalized_value=normalized_value,
            is_primary=True,
        )
    )
    previous_values[audit_key] = None
    new_values[audit_key] = cleaned_value
    return True


def normalize_blank(value: str) -> str | None:
    cleaned_value = value.strip()
    return cleaned_value or None


def normalize_email(value: str) -> str:
    return value.strip().lower()


def normalize_phone(value: str) -> str:
    return "".join(character for character in value if character.isdigit())


def normalize_address_key(
    street_address: str,
    city: str,
    state: str,
    postal_code: str,
) -> str:
    raw = "|".join([street_address, city, state, postal_code])
    normalized = "".join(character.lower() if character.isalnum() else " " for character in raw)
    return " ".join(normalized.split())


def property_fields_changed(values: dict[str, Any]) -> bool:
    property_keys = {"street_address", "city", "state", "postal_code"}
    return any(key in values for key in property_keys)


def lead_to_read(db: Session, lead: Lead) -> LeadRead:
    contact = db.get(Contact, lead.contact_id)
    property_record = db.get(Property, lead.property_id)
    assigned_user = db.get(User, lead.assigned_user_id) if lead.assigned_user_id else None
    if contact is None or property_record is None:
        raise RuntimeError("lead is missing required contact or property")

    return LeadRead(
        id=lead.id,
        contact_id=lead.contact_id,
        property_id=lead.property_id,
        source=lead.source,
        stage_key=lead.stage_key,
        lead_temperature=lead.lead_temperature,
        seller_name=contact.legal_name,
        preferred_name=contact.preferred_name,
        property_address=(
            f"{property_record.street_address}, {property_record.city}, "
            f"{property_record.state} {property_record.postal_code}"
        ),
        property_street_address=property_record.street_address,
        property_city=property_record.city,
        property_state=property_record.state,
        property_postal_code=property_record.postal_code,
        property_county=property_record.county,
        property_type=property_record.property_type,
        assigned_user_email=assigned_user.email if assigned_user else None,
        created_at=lead.created_at,
    )
