import hashlib
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.domain.rbac import PermissionKeys
from app.models.foundation import (
    ActivityEvent,
    Appointment,
    ApprovalRequest,
    AuditEvent,
    Contact,
    ContactMethod,
    FieldInspection,
    FieldInspectionPhoto,
    FieldMeetingBrief,
    FieldNegotiationSession,
    FieldUnderwritingTransfer,
    Lead,
    LeadQualificationSession,
    OfferNegotiationPlan,
    Property,
    RepairEstimate,
    Task,
    UnderwritingMarketAnalysis,
    UnderwritingVersion,
    User,
)
from app.schemas.field_operations import (
    FieldAppointmentWorkspaceRead,
    FieldCalendarAppointmentRead,
    FieldCalendarRead,
    FieldInspectionPhotoRead,
    FieldInspectionRead,
    FieldInspectionUpdate,
    FieldMeetingBriefRead,
    FieldNegotiationRead,
    FieldNegotiationUpdate,
    FieldObjection,
    FieldRepairItem,
    FieldRoomObservation,
    FieldUnderwritingTransferRead,
)
from app.services.offer_concessions import record_field_agreement, record_field_offer

ALLOWED_PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic"}
MAX_PHOTO_BYTES = 5 * 1024 * 1024
MAX_PHOTOS_PER_INSPECTION = 30


def can_manage(principal: Principal) -> bool:
    return PermissionKeys.MANAGE_ACQUISITION_OPERATIONS in principal.permission_keys


def can_review_underwriting(principal: Principal) -> bool:
    return PermissionKeys.EDIT_UNDERWRITING in principal.permission_keys


def scoped_appointment(
    db: Session, principal: Principal, appointment_id: UUID
) -> Appointment | None:
    appointment = db.scalar(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.organization_id == principal.organization_id,
        )
    )
    if appointment is None:
        return None
    if not can_manage(principal) and appointment.owner_user_id != principal.user_id:
        raise PermissionError("Only the assigned closer or an acquisition manager can access it.")
    return appointment


def calendar_appointments(
    db: Session,
    principal: Principal,
    starts_at: datetime,
    ends_at: datetime,
    owner_user_id: UUID | None,
) -> FieldCalendarRead:
    start = as_utc(starts_at)
    end = as_utc(ends_at)
    if end <= start:
        raise ValueError("Calendar end must be after its start.")
    if end - start > timedelta(days=62):
        raise ValueError("Calendar ranges cannot exceed 62 days.")
    statement = select(Appointment).where(
        Appointment.organization_id == principal.organization_id,
        Appointment.scheduled_start_at < end,
        func.coalesce(Appointment.scheduled_end_at, Appointment.scheduled_start_at) >= start,
    )
    if not can_manage(principal):
        statement = statement.where(Appointment.owner_user_id == principal.user_id)
    elif owner_user_id is not None:
        statement = statement.where(Appointment.owner_user_id == owner_user_id)
    appointments = list(db.scalars(statement.order_by(Appointment.scheduled_start_at)).all())
    return FieldCalendarRead(
        starts_at=start,
        ends_at=end,
        appointments=[calendar_appointment_read(db, item) for item in appointments],
    )


def calendar_appointment_read(
    db: Session, appointment: Appointment
) -> FieldCalendarAppointmentRead:
    contact = db.get(Contact, appointment.contact_id)
    property_record = db.get(Property, appointment.property_id)
    owner = db.get(User, appointment.owner_user_id) if appointment.owner_user_id else None
    inspection = db.scalar(
        select(FieldInspection).where(FieldInspection.appointment_id == appointment.id)
    )
    negotiation = db.scalar(
        select(FieldNegotiationSession).where(
            FieldNegotiationSession.appointment_id == appointment.id
        )
    )
    field_status = "not_started"
    if negotiation and negotiation.outcome != "pending":
        field_status = negotiation.outcome
    elif inspection:
        field_status = inspection.status
    return FieldCalendarAppointmentRead(
        id=appointment.id,
        lead_id=appointment.lead_id,
        seller_name=contact.legal_name if contact else "Unknown seller",
        property_address=(
            f"{property_record.street_address}, {property_record.city}, "
            f"{property_record.state} {property_record.postal_code}"
            if property_record
            else "Unknown property"
        ),
        closer_user_id=appointment.owner_user_id,
        closer_name=owner.display_name if owner else "Unassigned",
        appointment_type=appointment.appointment_type,
        status=appointment.status,
        scheduled_start_at=appointment.scheduled_start_at,
        scheduled_end_at=appointment.scheduled_end_at,
        location_type=appointment.location_type,
        outcome=appointment.outcome,
        field_status=field_status,
        lead_url=f"/os/leads/{appointment.lead_id}",
    )


def appointment_workspace(
    db: Session, principal: Principal, appointment_id: UUID
) -> FieldAppointmentWorkspaceRead | None:
    from app.services.acquisitions_copilot import (
        get_acquisitions_copilot_overview,
    )

    appointment = scoped_appointment(db, principal, appointment_id)
    if appointment is None:
        return None
    brief = db.scalar(
        select(FieldMeetingBrief)
        .where(
            FieldMeetingBrief.appointment_id == appointment.id,
            FieldMeetingBrief.status == "current",
        )
        .order_by(FieldMeetingBrief.version_number.desc())
    )
    inspection = db.scalar(
        select(FieldInspection).where(FieldInspection.appointment_id == appointment.id)
    )
    negotiation = db.scalar(
        select(FieldNegotiationSession).where(
            FieldNegotiationSession.appointment_id == appointment.id
        )
    )
    transfer = (
        db.scalar(
            select(FieldUnderwritingTransfer).where(
                FieldUnderwritingTransfer.inspection_id == inspection.id
            )
        )
        if inspection
        else None
    )
    return FieldAppointmentWorkspaceRead(
        appointment=calendar_appointment_read(db, appointment),
        brief=brief_read(brief) if brief else None,
        inspection=inspection_read(db, inspection) if inspection else None,
        negotiation=negotiation_read(negotiation) if negotiation else None,
        underwriting_transfer=transfer_read(db, transfer) if transfer else None,
        copilot=get_acquisitions_copilot_overview(db, principal, appointment),
        can_edit=can_manage(principal) or appointment.owner_user_id == principal.user_id,
        can_review_underwriting=can_review_underwriting(principal),
    )


def generate_meeting_brief(
    db: Session, principal: Principal, appointment_id: UUID
) -> FieldMeetingBriefRead | None:
    appointment = scoped_appointment(db, principal, appointment_id)
    if appointment is None:
        return None
    lead = db.get(Lead, appointment.lead_id)
    contact = db.get(Contact, appointment.contact_id)
    property_record = db.get(Property, appointment.property_id)
    if lead is None or contact is None or property_record is None:
        raise ValueError("The appointment requires an active lead, seller, and property.")
    qualification = db.scalar(
        select(LeadQualificationSession)
        .where(LeadQualificationSession.lead_id == lead.id)
        .order_by(LeadQualificationSession.completed_at.desc())
    )
    underwriting = db.scalar(
        select(UnderwritingVersion)
        .where(UnderwritingVersion.lead_id == lead.id)
        .order_by(UnderwritingVersion.version_number.desc())
    )
    analysis = db.scalar(
        select(UnderwritingMarketAnalysis)
        .where(UnderwritingMarketAnalysis.lead_id == lead.id)
        .order_by(UnderwritingMarketAnalysis.created_at.desc())
    )
    approved_plan, approval = approved_offer_plan(db, lead.id)
    contact_methods = list(
        db.scalars(select(ContactMethod).where(ContactMethod.contact_id == contact.id)).all()
    )
    tasks = list(
        db.scalars(
            select(Task).where(
                Task.lead_id == lead.id,
                Task.status.in_(("open", "in_progress")),
            )
        ).all()
    )
    answers = dict(qualification.answers) if qualification else {}
    unresolved = unresolved_questions(lead, answers, approved_plan)
    objections = likely_objections(lead, answers, approved_plan)
    brief_data = {
        "seller": {
            "legal_name": contact.legal_name,
            "preferred_name": contact.preferred_name,
            "contact_methods": [
                {"type": item.method_type, "value": item.value, "primary": item.is_primary}
                for item in contact_methods
            ],
            "motivation": lead.motivation,
            "timeline": lead.desired_timeline,
            "asking_price": lead.asking_price,
            "occupancy": lead.occupancy_status,
            "mortgage_balance": lead.mortgage_balance,
        },
        "property": {
            "address": (
                f"{property_record.street_address}, {property_record.city}, "
                f"{property_record.state} {property_record.postal_code}"
            ),
            "county": property_record.county,
            "property_type": property_record.property_type,
            "reported_condition": lead.property_condition,
            "validation_status": property_record.address_validation_status,
        },
        "appointment": {
            "starts_at": appointment.scheduled_start_at.isoformat(),
            "ends_at": appointment.scheduled_end_at.isoformat()
            if appointment.scheduled_end_at
            else None,
            "location": appointment.location,
            "notes": appointment.notes,
        },
        "qualification": answers,
        "underwriting": underwriting_summary(underwriting, analysis),
        "approved_offer": approved_offer_summary(approved_plan, approval),
        "unresolved_questions": unresolved,
        "likely_objections": objections,
        "open_tasks": [
            {"title": task.title, "priority": task.priority, "due_at": optional_iso(task.due_at)}
            for task in tasks
        ],
        "meeting_plan": [
            "Confirm every decision maker and the seller's desired outcome.",
            "Walk the property before discussing a final number.",
            "Explain the evidence behind the offer without presenting an unapproved ceiling.",
            "Record objections, commitments, and the exact next action before leaving.",
        ],
    }
    current = list(
        db.scalars(
            select(FieldMeetingBrief).where(
                FieldMeetingBrief.appointment_id == appointment.id,
                FieldMeetingBrief.status == "current",
            )
        )
    )
    for item in current:
        item.status = "superseded"
    next_version = (
        int(
            db.scalar(
                select(func.max(FieldMeetingBrief.version_number)).where(
                    FieldMeetingBrief.appointment_id == appointment.id
                )
            )
            or 0
        )
        + 1
    )
    source_snapshot = {
        "lead_id": str(lead.id),
        "lead_updated_at": lead.updated_at.isoformat(),
        "qualification_session_id": str(qualification.id) if qualification else None,
        "underwriting_version_id": str(underwriting.id) if underwriting else None,
        "market_analysis_id": str(analysis.id) if analysis else None,
        "offer_negotiation_plan_id": str(approved_plan.id) if approved_plan else None,
        "approval_request_id": str(approval.id) if approval else None,
    }
    brief = FieldMeetingBrief(
        organization_id=principal.organization_id,
        appointment_id=appointment.id,
        lead_id=lead.id,
        generated_by_user_id=principal.user_id,
        version_number=next_version,
        status="current",
        source_snapshot=source_snapshot,
        brief_data=brief_data,
    )
    db.add(brief)
    db.flush()
    add_audit(
        db,
        principal,
        "field_operations.brief_generate",
        "field_meeting_brief",
        brief.id,
        {"version_number": next_version, "source_snapshot": source_snapshot},
        "Seller meeting brief generated from current evidence",
    )
    db.commit()
    return brief_read(brief)


def start_inspection(
    db: Session, principal: Principal, appointment_id: UUID
) -> FieldInspectionRead | None:
    appointment = scoped_appointment(db, principal, appointment_id)
    if appointment is None:
        return None
    inspection = db.scalar(
        select(FieldInspection).where(FieldInspection.appointment_id == appointment.id)
    )
    if inspection is None:
        inspection = FieldInspection(
            organization_id=principal.organization_id,
            appointment_id=appointment.id,
            lead_id=appointment.lead_id,
            property_id=appointment.property_id,
            inspector_user_id=principal.user_id,
            status="draft",
            started_at=datetime.now(UTC),
            submitted_at=None,
            reviewed_at=None,
            reviewed_by_user_id=None,
            overall_condition=None,
            occupancy_observed=None,
            utilities_status=None,
            access_notes=None,
            title_concerns=None,
            safety_concerns=None,
            room_observations=[],
            repair_items=[],
            inspector_notes=None,
        )
        db.add(inspection)
        db.flush()
        add_activity(
            db,
            principal,
            appointment.lead_id,
            "field.inspection_started",
            "Field walkthrough started.",
        )
        db.commit()
    return inspection_read(db, inspection)


def update_inspection(
    db: Session,
    principal: Principal,
    inspection_id: UUID,
    payload: FieldInspectionUpdate,
) -> FieldInspectionRead | None:
    inspection = scoped_inspection(db, principal, inspection_id)
    if inspection is None:
        return None
    if inspection.status != "draft":
        raise ValueError("Submitted field inspections are immutable.")
    for key, value in payload.model_dump(mode="json", exclude_unset=True).items():
        setattr(inspection, key, value)
    add_audit(
        db,
        principal,
        "field_operations.inspection_update",
        "field_inspection",
        inspection.id,
        {
            "room_count": len(inspection.room_observations),
            "repair_count": len(inspection.repair_items),
        },
        "Field inspection draft saved",
    )
    db.commit()
    return inspection_read(db, inspection)


def submit_inspection(
    db: Session, principal: Principal, inspection_id: UUID
) -> FieldInspectionRead | None:
    inspection = scoped_inspection(db, principal, inspection_id)
    if inspection is None:
        return None
    if inspection.status != "draft":
        raise ValueError("Only a draft inspection can be submitted.")
    if not inspection.overall_condition:
        raise ValueError("Select the overall property condition before submitting.")
    if not inspection.room_observations:
        raise ValueError("Record at least one inspected area before submitting.")
    inspection.status = "submitted"
    inspection.submitted_at = datetime.now(UTC)
    add_activity(
        db,
        principal,
        inspection.lead_id,
        "field.inspection_submitted",
        "Field walkthrough submitted for underwriting review.",
    )
    add_audit(
        db,
        principal,
        "field_operations.inspection_submit",
        "field_inspection",
        inspection.id,
        {
            "overall_condition": inspection.overall_condition,
            "room_count": len(inspection.room_observations),
            "repair_count": len(inspection.repair_items),
            "photo_count": photo_count(db, inspection.id),
        },
        "Closer submitted field evidence",
    )
    db.commit()
    return inspection_read(db, inspection)


def add_photo(
    db: Session,
    principal: Principal,
    inspection_id: UUID,
    *,
    image_data: bytes,
    content_type: str,
    file_name: str,
    area: str,
    caption: str | None,
    captured_at: datetime | None,
) -> FieldInspectionPhotoRead | None:
    inspection = scoped_inspection(db, principal, inspection_id)
    if inspection is None:
        return None
    if inspection.status != "draft":
        raise ValueError("Photos cannot be added after the inspection is submitted.")
    normalized_type = content_type.split(";", 1)[0].strip().lower()
    if normalized_type not in ALLOWED_PHOTO_TYPES:
        raise ValueError("Upload a JPEG, PNG, WebP, or HEIC image.")
    if not image_data or len(image_data) > MAX_PHOTO_BYTES:
        raise ValueError("Each inspection photo must be between 1 byte and 5 MB.")
    if photo_count(db, inspection.id) >= MAX_PHOTOS_PER_INSPECTION:
        raise ValueError("An inspection can contain at most 30 photos.")
    clean_area = area.strip()
    if not clean_area or len(clean_area) > 120:
        raise ValueError("Photo area is required and must be 120 characters or less.")
    clean_name = (
        file_name.strip().replace('"', "'").replace("\r", "").replace("\n", "")[:255]
        or "inspection-photo"
    )
    photo = FieldInspectionPhoto(
        organization_id=principal.organization_id,
        inspection_id=inspection.id,
        uploaded_by_user_id=principal.user_id,
        area=clean_area,
        caption=clean_optional(caption, 500),
        file_name=clean_name,
        content_type=normalized_type,
        byte_size=len(image_data),
        sha256=hashlib.sha256(image_data).hexdigest(),
        captured_at=as_utc(captured_at) if captured_at else None,
        image_data=image_data,
    )
    db.add(photo)
    db.flush()
    add_audit(
        db,
        principal,
        "field_operations.photo_add",
        "field_inspection_photo",
        photo.id,
        {"inspection_id": str(inspection.id), "area": photo.area, "sha256": photo.sha256},
        "Inspection photo captured",
    )
    db.commit()
    return photo_read(photo)


def get_photo_content(
    db: Session, principal: Principal, photo_id: UUID
) -> tuple[FieldInspectionPhoto, bytes] | None:
    photo = db.scalar(
        select(FieldInspectionPhoto).where(
            FieldInspectionPhoto.id == photo_id,
            FieldInspectionPhoto.organization_id == principal.organization_id,
        )
    )
    if photo is None:
        return None
    scoped_inspection(db, principal, photo.inspection_id)
    return photo, bytes(photo.image_data)


def delete_photo(db: Session, principal: Principal, photo_id: UUID) -> bool:
    photo = db.scalar(
        select(FieldInspectionPhoto).where(
            FieldInspectionPhoto.id == photo_id,
            FieldInspectionPhoto.organization_id == principal.organization_id,
        )
    )
    if photo is None:
        return False
    inspection = scoped_inspection(db, principal, photo.inspection_id)
    if inspection is None:
        return False
    if inspection.status != "draft":
        raise ValueError("Submitted inspection photos cannot be deleted.")
    snapshot = {"inspection_id": str(inspection.id), "area": photo.area, "sha256": photo.sha256}
    db.delete(photo)
    add_audit(
        db,
        principal,
        "field_operations.photo_delete",
        "field_inspection_photo",
        photo.id,
        snapshot,
        "Draft inspection photo removed",
    )
    db.commit()
    return True


def save_negotiation(
    db: Session,
    principal: Principal,
    appointment_id: UUID,
    payload: FieldNegotiationUpdate,
) -> FieldNegotiationRead | None:
    appointment = scoped_appointment(db, principal, appointment_id)
    if appointment is None:
        return None
    negotiation = db.scalar(
        select(FieldNegotiationSession).where(
            FieldNegotiationSession.appointment_id == appointment.id
        )
    )
    ceiling = approved_ceiling(db, appointment.lead_id)
    governing_concession = None
    if payload.offer_presented_cents is not None:
        if ceiling is None:
            raise ValueError("An approved offer plan is required before presenting a price.")
        if payload.offer_presented_cents > ceiling:
            raise ValueError("The presented offer cannot exceed the approved seller ceiling.")
        _, governing_concession = record_field_offer(
            db,
            principal,
            appointment.lead_id,
            appointment.id,
            payload.offer_presented_cents,
            seller_counter_cents=payload.seller_counter_cents,
            notes=payload.notes or "Field offer presented to seller.",
        )
    if payload.agreed_price_cents is not None:
        if ceiling is None:
            raise ValueError("An approved offer plan is required before recording an agreement.")
        if payload.agreed_price_cents > ceiling:
            raise ValueError("The agreed price exceeds the approved seller ceiling.")
        effective_presented = payload.offer_presented_cents or (
            negotiation.offer_presented_cents if negotiation else None
        )
        if effective_presented != payload.agreed_price_cents:
            raise ValueError(
                "The agreed price must match the most recently presented governed offer."
            )
        agreement_concession = record_field_agreement(
            db,
            principal,
            appointment.lead_id,
            appointment.id,
            payload.agreed_price_cents,
            payload.notes or "Seller agreement recorded in the field workflow.",
        )
        governing_concession = agreement_concession or governing_concession
    if negotiation is None:
        negotiation = FieldNegotiationSession(
            organization_id=principal.organization_id,
            appointment_id=appointment.id,
            lead_id=appointment.lead_id,
            recorded_by_user_id=principal.user_id,
        )
        db.add(negotiation)
    negotiation.recorded_by_user_id = principal.user_id
    negotiation.governing_concession_id = (
        governing_concession.id if governing_concession else negotiation.governing_concession_id
    )
    negotiation.decision_makers_confirmed = payload.decision_makers_confirmed
    negotiation.decision_makers = payload.decision_makers
    negotiation.seller_asking_price_cents = payload.seller_asking_price_cents
    negotiation.offer_presented_cents = payload.offer_presented_cents
    negotiation.seller_counter_cents = payload.seller_counter_cents
    negotiation.agreed_price_cents = payload.agreed_price_cents
    negotiation.approved_ceiling_cents = ceiling
    negotiation.objections = [item.model_dump(mode="json") for item in payload.objections]
    negotiation.commitments = payload.commitments
    negotiation.outcome = payload.outcome
    negotiation.notes = clean_optional(payload.notes, 2000)
    negotiation.next_follow_up_at = (
        as_utc(payload.next_follow_up_at) if payload.next_follow_up_at else None
    )
    lead = db.get(Lead, appointment.lead_id)
    if payload.outcome != "pending":
        appointment.status = "completed"
        appointment.outcome = negotiation_outcome_summary(payload)
    if lead:
        lead.next_follow_up_at = negotiation.next_follow_up_at
        if payload.outcome == "accepted":
            lead.stage_key = "offer_ready"
        elif payload.outcome in {"follow_up", "not_decided", "declined"}:
            lead.stage_key = "qualified"
    db.flush()
    add_activity(
        db,
        principal,
        appointment.lead_id,
        "field.negotiation_saved",
        f"Seller meeting outcome recorded as {payload.outcome.replace('_', ' ')}.",
    )
    add_audit(
        db,
        principal,
        "field_operations.negotiation_save",
        "field_negotiation_session",
        negotiation.id,
        {
            "outcome": negotiation.outcome,
            "offer_presented_cents": negotiation.offer_presented_cents,
            "seller_counter_cents": negotiation.seller_counter_cents,
            "agreed_price_cents": negotiation.agreed_price_cents,
            "approved_ceiling_cents": ceiling,
        },
        "Closer recorded seller negotiation evidence",
    )
    db.commit()
    return negotiation_read(negotiation)


def transfer_to_underwriting(
    db: Session, principal: Principal, inspection_id: UUID
) -> FieldUnderwritingTransferRead | None:
    if not can_review_underwriting(principal):
        raise PermissionError("Underwriting edit access is required to review field evidence.")
    inspection = scoped_inspection(db, principal, inspection_id)
    if inspection is None:
        return None
    if inspection.status not in {"submitted", "reviewed"}:
        raise ValueError("Submit the inspection before transferring it to underwriting.")
    existing = db.scalar(
        select(FieldUnderwritingTransfer).where(
            FieldUnderwritingTransfer.inspection_id == inspection.id
        )
    )
    if existing:
        return transfer_read(db, existing)
    source = db.scalar(
        select(UnderwritingVersion)
        .where(UnderwritingVersion.lead_id == inspection.lead_id)
        .order_by(UnderwritingVersion.version_number.desc())
    )
    next_version = (
        int(
            db.scalar(
                select(func.max(UnderwritingVersion.version_number)).where(
                    UnderwritingVersion.lead_id == inspection.lead_id
                )
            )
            or 0
        )
        + 1
    )
    repair_items = list(inspection.repair_items)
    subtotal = sum(int(item["estimated_cost_cents"]) for item in repair_items)
    contingency_percentage = 15
    contingency = round(subtotal * contingency_percentage / 100)
    repair_estimate: RepairEstimate | None = None
    if repair_items:
        repair_estimate = RepairEstimate(
            organization_id=principal.organization_id,
            lead_id=inspection.lead_id,
            property_id=inspection.property_id,
            created_by_user_id=principal.user_id,
            source_type="walkthrough_scope",
            contractor_name=None,
            estimate_date=inspection.submitted_at or datetime.now(UTC),
            scope_items=repair_items,
            subtotal_cents=subtotal,
            contingency_percentage=contingency_percentage,
            contingency_cents=contingency,
            total_cents=subtotal + contingency,
            evidence_reference=f"field-inspection:{inspection.id}",
            notes=inspection.inspector_notes,
        )
        db.add(repair_estimate)
        db.flush()
    metadata = dict(source.underwriting_metadata or {}) if source else {}
    metadata.update(
        {
            "field_inspection_id": str(inspection.id),
            "source_underwriting_version_id": str(source.id) if source else None,
            "repair_estimate_id": str(repair_estimate.id) if repair_estimate else None,
            "input_verification_status": "walkthrough_verified",
            "report_stage": "walkthrough_verified",
            "overall_condition": inspection.overall_condition,
            "room_observations": inspection.room_observations,
            "field_photo_count": photo_count(db, inspection.id),
            "requires_offer_recalculation": True,
        }
    )
    version = UnderwritingVersion(
        organization_id=principal.organization_id,
        lead_id=inspection.lead_id,
        property_id=inspection.property_id,
        created_by_user_id=principal.user_id,
        version_number=next_version,
        status="draft",
        arv_low_cents=source.arv_low_cents if source else None,
        arv_high_cents=source.arv_high_cents if source else None,
        repair_low_cents=subtotal
        if repair_items
        else (source.repair_low_cents if source else None),
        repair_high_cents=(subtotal + contingency)
        if repair_items
        else (source.repair_high_cents if source else None),
        max_offer_cents=None,
        recommended_offer_cents=None,
        offer_strategy=None,
        notes=(
            "Field evidence transferred. Recalculate and approve before discussing a revised offer."
        ),
        source="field_inspection",
        underwriting_metadata=metadata,
    )
    db.add(version)
    db.flush()
    snapshot = {
        "inspection_id": str(inspection.id),
        "source_underwriting_version_id": str(source.id) if source else None,
        "created_underwriting_version_id": str(version.id),
        "repair_estimate_id": str(repair_estimate.id) if repair_estimate else None,
        "repair_subtotal_cents": subtotal,
        "repair_total_cents": subtotal + contingency,
        "room_observations": inspection.room_observations,
        "photo_ids": [
            str(item)
            for item in db.scalars(
                select(FieldInspectionPhoto.id).where(
                    FieldInspectionPhoto.inspection_id == inspection.id
                )
            )
        ],
    }
    transfer = FieldUnderwritingTransfer(
        organization_id=principal.organization_id,
        inspection_id=inspection.id,
        lead_id=inspection.lead_id,
        reviewed_by_user_id=principal.user_id,
        source_underwriting_version_id=source.id if source else None,
        repair_estimate_id=repair_estimate.id if repair_estimate else None,
        created_underwriting_version_id=version.id,
        transfer_snapshot=snapshot,
    )
    db.add(transfer)
    inspection.status = "reviewed"
    inspection.reviewed_at = datetime.now(UTC)
    inspection.reviewed_by_user_id = principal.user_id
    lead = db.get(Lead, inspection.lead_id)
    if lead:
        lead.stage_key = "underwriting"
    db.flush()
    add_activity(
        db,
        principal,
        inspection.lead_id,
        "field.transferred_to_underwriting",
        f"Field evidence created underwriting version {next_version} for review.",
    )
    add_audit(
        db,
        principal,
        "field_operations.underwriting_transfer",
        "field_underwriting_transfer",
        transfer.id,
        snapshot,
        "Human-reviewed field evidence transferred without overwriting prior underwriting",
    )
    db.commit()
    return transfer_read(db, transfer)


def scoped_inspection(
    db: Session, principal: Principal, inspection_id: UUID
) -> FieldInspection | None:
    inspection = db.scalar(
        select(FieldInspection).where(
            FieldInspection.id == inspection_id,
            FieldInspection.organization_id == principal.organization_id,
        )
    )
    if inspection is None:
        return None
    scoped_appointment(db, principal, inspection.appointment_id)
    return inspection


def inspection_read(db: Session, inspection: FieldInspection) -> FieldInspectionRead:
    inspector = db.get(User, inspection.inspector_user_id)
    photos = list(
        db.scalars(
            select(FieldInspectionPhoto)
            .where(FieldInspectionPhoto.inspection_id == inspection.id)
            .order_by(FieldInspectionPhoto.created_at)
        )
    )
    return FieldInspectionRead(
        id=inspection.id,
        appointment_id=inspection.appointment_id,
        lead_id=inspection.lead_id,
        property_id=inspection.property_id,
        inspector_user_id=inspection.inspector_user_id,
        inspector_name=inspector.display_name if inspector else "Unknown inspector",
        status=inspection.status,
        started_at=inspection.started_at,
        submitted_at=inspection.submitted_at,
        reviewed_at=inspection.reviewed_at,
        overall_condition=inspection.overall_condition,
        occupancy_observed=inspection.occupancy_observed,
        utilities_status=inspection.utilities_status,
        access_notes=inspection.access_notes,
        title_concerns=inspection.title_concerns,
        safety_concerns=inspection.safety_concerns,
        room_observations=[
            FieldRoomObservation.model_validate(item) for item in inspection.room_observations
        ],
        repair_items=[FieldRepairItem.model_validate(item) for item in inspection.repair_items],
        inspector_notes=inspection.inspector_notes,
        photos=[photo_read(photo) for photo in photos],
        repair_total_cents=sum(
            int(item["estimated_cost_cents"]) for item in inspection.repair_items
        ),
    )


def photo_read(photo: FieldInspectionPhoto) -> FieldInspectionPhotoRead:
    return FieldInspectionPhotoRead(
        id=photo.id,
        area=photo.area,
        caption=photo.caption,
        file_name=photo.file_name,
        content_type=photo.content_type,
        byte_size=photo.byte_size,
        sha256=photo.sha256,
        captured_at=photo.captured_at,
        content_url=f"/api/v1/field-operations/photos/{photo.id}/content",
        created_at=photo.created_at,
    )


def brief_read(brief: FieldMeetingBrief) -> FieldMeetingBriefRead:
    return FieldMeetingBriefRead(
        id=brief.id,
        appointment_id=brief.appointment_id,
        version_number=brief.version_number,
        status=brief.status,
        source_snapshot=brief.source_snapshot,
        brief_data=brief.brief_data,
        created_at=brief.created_at,
    )


def negotiation_read(negotiation: FieldNegotiationSession) -> FieldNegotiationRead:
    return FieldNegotiationRead(
        id=negotiation.id,
        appointment_id=negotiation.appointment_id,
        lead_id=negotiation.lead_id,
        recorded_by_user_id=negotiation.recorded_by_user_id,
        governing_concession_id=negotiation.governing_concession_id,
        decision_makers_confirmed=negotiation.decision_makers_confirmed,
        decision_makers=negotiation.decision_makers,
        seller_asking_price_cents=negotiation.seller_asking_price_cents,
        offer_presented_cents=negotiation.offer_presented_cents,
        seller_counter_cents=negotiation.seller_counter_cents,
        agreed_price_cents=negotiation.agreed_price_cents,
        approved_ceiling_cents=negotiation.approved_ceiling_cents,
        objections=[FieldObjection.model_validate(item) for item in negotiation.objections],
        commitments=negotiation.commitments,
        outcome=negotiation.outcome,
        notes=negotiation.notes,
        next_follow_up_at=negotiation.next_follow_up_at,
        updated_at=negotiation.updated_at,
    )


def transfer_read(
    db: Session, transfer: FieldUnderwritingTransfer
) -> FieldUnderwritingTransferRead:
    version = db.get(UnderwritingVersion, transfer.created_underwriting_version_id)
    return FieldUnderwritingTransferRead(
        id=transfer.id,
        inspection_id=transfer.inspection_id,
        source_underwriting_version_id=transfer.source_underwriting_version_id,
        repair_estimate_id=transfer.repair_estimate_id,
        created_underwriting_version_id=transfer.created_underwriting_version_id,
        created_underwriting_version_number=version.version_number if version else 0,
        created_at=transfer.created_at,
    )


def approved_offer_plan(
    db: Session, lead_id: UUID
) -> tuple[OfferNegotiationPlan | None, ApprovalRequest | None]:
    plans = list(
        db.scalars(
            select(OfferNegotiationPlan)
            .where(OfferNegotiationPlan.lead_id == lead_id)
            .order_by(OfferNegotiationPlan.created_at.desc())
        )
    )
    for plan in plans:
        approval = (
            db.get(ApprovalRequest, plan.approval_request_id) if plan.approval_request_id else None
        )
        if approval and approval.status == "approved":
            return plan, approval
    return None, None


def approved_ceiling(db: Session, lead_id: UUID) -> int | None:
    plan, _ = approved_offer_plan(db, lead_id)
    return plan.seller_ceiling_cents if plan else None


def underwriting_summary(
    version: UnderwritingVersion | None, analysis: UnderwritingMarketAnalysis | None
) -> dict[str, object] | None:
    if version is None and analysis is None:
        return None
    arv_low_cents = (
        version.arv_low_cents if version else analysis.arv_low_cents if analysis else None
    )
    arv_high_cents = (
        version.arv_high_cents if version else analysis.arv_high_cents if analysis else None
    )
    repair_low_cents = (
        version.repair_low_cents if version else analysis.repair_low_cents if analysis else None
    )
    repair_high_cents = (
        version.repair_high_cents if version else analysis.repair_high_cents if analysis else None
    )
    recommended_offer_cents = (
        version.recommended_offer_cents
        if version
        else analysis.recommended_offer_cents
        if analysis
        else None
    )
    return {
        "version_id": str(version.id) if version else None,
        "version_number": version.version_number if version else None,
        "status": version.status if version else None,
        "arv_low_cents": arv_low_cents,
        "arv_high_cents": arv_high_cents,
        "repair_low_cents": repair_low_cents,
        "repair_high_cents": repair_high_cents,
        "recommended_offer_cents": recommended_offer_cents,
        "confidence_score": analysis.confidence_score if analysis else None,
        "selected_comp_count": analysis.selected_comp_count if analysis else None,
    }


def approved_offer_summary(
    plan: OfferNegotiationPlan | None, approval: ApprovalRequest | None
) -> dict[str, object] | None:
    if plan is None or approval is None:
        return None
    return {
        "plan_id": str(plan.id),
        "approval_id": str(approval.id),
        "approval_status": approval.status,
        "opening_offer_cents": plan.opening_offer_cents,
        "target_contract_cents": plan.target_contract_cents,
        "stretch_contract_cents": plan.stretch_contract_cents,
        "seller_ceiling_cents": plan.seller_ceiling_cents,
        "decision_notes": approval.decision_notes,
    }


def unresolved_questions(
    lead: Lead, answers: dict[str, object], approved_plan: OfferNegotiationPlan | None
) -> list[str]:
    questions: list[str] = []
    checks = (
        (
            answers.get("decision_makers") or answers.get("ownership"),
            "Confirm every owner and decision maker.",
        ),
        (lead.motivation, "Clarify the seller's primary reason for selling."),
        (lead.desired_timeline, "Confirm the seller's preferred closing date."),
        (lead.occupancy_status, "Confirm occupancy and possession expectations."),
        (lead.property_condition, "Verify property condition during the walkthrough."),
        (approved_plan, "Obtain offer-plan approval before discussing a final number."),
    )
    for value, question in checks:
        if not value:
            questions.append(question)
    return questions


def likely_objections(
    lead: Lead, answers: dict[str, object], approved_plan: OfferNegotiationPlan | None
) -> list[dict[str, str]]:
    objections: list[dict[str, str]] = []
    if lead.asking_price:
        objections.append({"category": "price", "reason": "Seller has stated a price expectation."})
    if lead.occupancy_status and "tenant" in lead.occupancy_status.lower():
        objections.append(
            {"category": "timing", "reason": "Tenant occupancy may affect access and possession."}
        )
    if not answers.get("decision_makers"):
        objections.append(
            {"category": "family", "reason": "Decision-maker authority is not confirmed."}
        )
    if lead.mortgage_balance:
        objections.append(
            {"category": "title", "reason": "Mortgage or lien payoff may affect net proceeds."}
        )
    if approved_plan is None:
        objections.append(
            {"category": "price", "reason": "No approved negotiation ceiling is available."}
        )
    return objections


def negotiation_outcome_summary(payload: FieldNegotiationUpdate) -> str:
    if payload.outcome == "accepted":
        return f"Seller accepted at ${(payload.agreed_price_cents or 0) / 100:,.0f}."
    return f"Seller meeting outcome: {payload.outcome.replace('_', ' ')}."


def photo_count(db: Session, inspection_id: UUID) -> int:
    return int(
        db.scalar(
            select(func.count(FieldInspectionPhoto.id)).where(
                FieldInspectionPhoto.inspection_id == inspection_id
            )
        )
        or 0
    )


def add_activity(
    db: Session, principal: Principal, lead_id: UUID, event_type: str, summary: str
) -> None:
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead_id,
            event_type=event_type,
            summary=summary,
        )
    )


def add_audit(
    db: Session,
    principal: Principal,
    action: str,
    entity_type: str,
    entity_id: UUID,
    new_value: Mapping[str, object],
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
            previous_value=None,
            new_value=dict(new_value),
            reason=reason,
        )
    )


def clean_optional(value: str | None, maximum: int) -> str | None:
    cleaned = (value or "").strip()
    return cleaned[:maximum] or None


def optional_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
