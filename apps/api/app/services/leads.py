from collections.abc import Sequence
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import get_settings
from app.domain.rbac import PermissionKeys
from app.integrations.rentcast_client import (
    RentCastClient,
    RentCastClientError,
    RentCastRentEstimate,
    RentCastValueEstimate,
    rent_estimate_from_payload,
    value_estimate_from_payload,
)
from app.models.foundation import (
    ActivityEvent,
    AiRunLog,
    Appointment,
    ApprovalRequest,
    AttributionTouch,
    AuditEvent,
    Buyer,
    BuyerEngagement,
    BuyerOffer,
    CommunicationRecord,
    ConsentRecord,
    Contact,
    ContactMethod,
    ContractPackage,
    Conversation,
    ConversationAssignmentEvent,
    ConversationWatcher,
    ConversionEvent,
    Deal,
    DealDeduction,
    DealPayout,
    DealReconciliation,
    DispositionCampaign,
    DispositionCase,
    DispositionMatch,
    Lead,
    LeadFormSubmission,
    OfferNegotiationPlan,
    OfflineConversionExport,
    Permission,
    Property,
    RepairEstimate,
    RevenueRecord,
    RoleAssignment,
    RolePermission,
    RoleCredit,
    Task,
    Transaction,
    TransactionChecklistItem,
    TransactionCopilotRecommendation,
    TransactionCopilotReview,
    TransactionDocument,
    TransactionDocumentFact,
    TransactionEvent,
    TransactionParty,
    UnderwritingCalibrationCase,
    UnderwritingMarketAnalysis,
    UnderwritingVersion,
    User,
)
from app.schemas.leads import (
    ActivityEventRead,
    AppointmentRead,
    AttributionTouchRead,
    BuyerOfferRead,
    CommunicationRecordRead,
    ConsentRecordRead,
    ContactMethodRead,
    DashboardSummary,
    LeadAiReadySummary,
    LeadAssignableUserRead,
    LeadAppointmentCreate,
    LeadBuyerOfferCreate,
    LeadCommunicationCreate,
    LeadContactMethodUpdate,
    LeadCreate,
    LeadDetail,
    LeadFollowUpTaskCreate,
    LeadIntelligence,
    LeadMarketAnalysisCreate,
    LeadMarketAnalysisRead,
    LeadMarketValueEstimateRead,
    LeadMissingField,
    LeadNextBestAction,
    LeadNoteCreate,
    LeadRead,
    LeadStaffUpdate,
    LeadStageUpdate,
    LeadTaskRead,
    LeadTransactionCreate,
    LeadUnderwritingCreate,
    MarketAnalysisCompRead,
    MarketComparableRead,
    PipelineStageCount,
    PropertyValidationRead,
    RepairEstimateItemInput,
    SourcePerformance,
    TransactionChecklistItemRead,
    TransactionRead,
    UnderwritingCompReviewSummaryRead,
    UnderwritingCompSearchSummaryRead,
    UnderwritingExecutionMetricsRead,
    UnderwritingMethodologyControlRead,
    UnderwritingPreMeetingInputsRead,
    UnderwritingSupportingEvidenceRead,
    UnderwritingVersionAdjustmentSnapshot,
    UnderwritingVersionCompSnapshot,
    UnderwritingVersionRead,
    UnderwritingVersionRepairSnapshot,
)
from app.services.inbox import (
    add_automatic_owner_watchers,
    ensure_primary_conversation,
    sync_conversation_to_lead_stage,
    update_conversation_activity,
)
from app.services.underwriting_adjustments import (
    build_adjustment_shadow,
    build_market_adjusted_conclusion,
)
from app.services.property_validation import (
    canonical_address_key,
    reset_property_validation,
    validate_provider_record,
)
from app.services.repair_catalog import prepare_new_scope_items
from app.services.repair_estimates import get_repair_estimate
from app.services.tasks import (
    create_deal_next_action,
    create_initial_lead_next_action,
    get_primary_next_action,
    supersede_open_primary_tasks,
)
from app.services.underwriting_comp_search import (
    search_adaptive_closed_sales,
    warnings_from_search_summary,
)
from app.services.underwriting_evidence import (
    collect_secondary_market_evidence,
    merge_research_comparable_sales,
    research_comparable_sale_records,
    resolve_rentcast_subject,
    secondary_conflict_warnings,
    unavailable_secondary_evidence,
)
from app.services.underwriting_manual_comps import (
    merge_verified_manual_sales,
    resolve_manual_comparable_records,
)
from app.services.underwriting_methodology import resolve_underwriting_methodology
from app.services.underwriting_supporting_evidence import (
    collect_supporting_market_evidence,
    unavailable_supporting_evidence,
)
from app.services.underwriting_v2 import (
    UnderwritingV2Result,
    analyze_underwriting_v2,
)
from app.services.underwriting_v3 import (
    METHODOLOGY_VERSION,
    promote_market_adjusted_result,
)

logger = structlog.get_logger()

PAID_LEAD_SOURCES = ("google_ppc", "meta_ads", "facebook_ads", "instagram_ads", "website")
COMMUNICATION_DIRECTIONS = {"inbound", "outbound", "internal"}
COMMUNICATION_CHANNELS = {"call", "sms", "email", "voicemail", "note"}
COMMUNICATION_STATUSES = {"logged", "draft", "sent", "received", "failed", "blocked"}
APPOINTMENT_TYPES = {"seller_call", "walkthrough", "offer_review", "follow_up"}
APPOINTMENT_STATUSES = {"scheduled", "completed", "cancelled", "no_show", "rescheduled"}
APPOINTMENT_LOCATION_TYPES = {"phone", "property", "video", "office", "other"}
UNDERWRITING_STATUSES = {"draft", "needs_review", "approved", "rejected"}
TRANSACTION_CONTRACT_TYPES = {"purchase_agreement", "assignment_contract", "novation"}
BUYER_OFFER_STATUSES = {"received", "countered", "accepted", "rejected", "withdrawn"}
BUYER_OFFER_FINANCING_TYPES = {"cash", "hard_money", "private_money", "conventional", "other"}
HIGH_URGENCY_TIMELINES = {"asap", "now", "immediately", "30_days", "30 days", "within 30 days"}
MEDIUM_URGENCY_TIMELINES = {"60_90_days", "60-90 days", "90_days", "90 days"}
QUALIFICATION_FIELDS = [
    (
        "motivation",
        "Motivation",
        "Why is the seller considering a sale now?",
        "high",
    ),
    (
        "desired_timeline",
        "Timeline",
        "When does the seller want to close or decide?",
        "high",
    ),
    (
        "property_condition",
        "Property condition",
        "What repairs, updates, or condition issues should underwriting know?",
        "medium",
    ),
    (
        "occupancy_status",
        "Occupancy",
        "Is the property vacant, owner occupied, or tenant occupied?",
        "medium",
    ),
    (
        "asking_price",
        "Asking price",
        "What price or net number is the seller hoping for?",
        "medium",
    ),
    (
        "mortgage_balance",
        "Mortgage balance",
        "Is there a mortgage, lien, or payoff amount to consider?",
        "medium",
    ),
    (
        "appointment_status",
        "Appointment status",
        "Has an appointment or walkthrough been requested or scheduled?",
        "high",
    ),
]
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
    assigned_user_id = payload.assigned_user_id or principal.user_id
    assigned_user = db.scalar(
        select(User).where(
            User.organization_id == principal.organization_id,
            User.id == assigned_user_id,
            User.is_active.is_(True),
        )
    )
    if assigned_user is None:
        raise ValueError("Select an active Stonegate owner for this lead.")
    can_own_lead = db.scalar(
        select(func.count())
        .select_from(RoleAssignment)
        .join(RolePermission, RolePermission.role_id == RoleAssignment.role_id)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .where(
            RoleAssignment.organization_id == principal.organization_id,
            RoleAssignment.user_id == assigned_user.id,
            Permission.key == PermissionKeys.EDIT_LEADS,
        )
    )
    if not can_own_lead:
        raise ValueError("Select an active acquisitions or management owner for this lead.")

    contact = Contact(
        organization_id=principal.organization_id,
        legal_name=payload.contact.legal_name,
        preferred_name=payload.contact.preferred_name,
        contact_type=payload.contact.contact_type,
        assigned_user_id=assigned_user.id,
    )
    db.add(contact)
    db.flush()
    contact_methods = [
        ("phone", payload.phone, normalize_phone(payload.phone or "")),
        ("email", payload.email, normalize_email(payload.email or "")),
    ]
    has_primary_method = False
    for method_type, value, normalized_value in contact_methods:
        if not value or not normalized_value:
            continue
        db.add(
            ContactMethod(
                organization_id=principal.organization_id,
                contact_id=contact.id,
                method_type=method_type,
                value=value.strip(),
                normalized_value=normalized_value,
                is_primary=not has_primary_method,
            )
        )
        has_primary_method = True

    property_record = Property(
        organization_id=principal.organization_id,
        street_address=payload.property.street_address,
        city=payload.property.city,
        state=payload.property.state.upper(),
        postal_code=payload.property.postal_code,
        county=payload.property.county,
        property_type=payload.property.property_type,
        normalized_address_key=canonical_address_key(
            payload.property.street_address,
            payload.property.city,
            payload.property.state,
            payload.property.postal_code,
        ),
        address_validation_status="unverified",
    )
    db.add(property_record)
    db.flush()

    lead = Lead(
        organization_id=principal.organization_id,
        contact_id=contact.id,
        property_id=property_record.id,
        assigned_user_id=assigned_user.id,
        source=payload.source,
        stage_key=payload.stage_key,
        lead_temperature=payload.lead_temperature,
        motivation=payload.motivation,
        desired_timeline=payload.desired_timeline,
        property_condition=payload.property_condition,
        occupancy_status=payload.occupancy_status,
        asking_price=payload.asking_price,
        mortgage_balance=payload.mortgage_balance,
        appointment_status=payload.appointment_status,
        next_follow_up_at=payload.next_follow_up_at,
    )
    db.add(lead)
    db.flush()
    ensure_primary_conversation(db, lead)
    create_initial_lead_next_action(
        db,
        lead,
        actor_user_id=principal.user_id,
    )

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
    if payload.initial_note:
        db.add(
            ActivityEvent(
                organization_id=principal.organization_id,
                actor_user_id=principal.user_id,
                entity_type="lead",
                entity_id=lead.id,
                event_type="lead.note_added",
                summary=payload.initial_note.strip(),
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
            new_value={
                "source": lead.source,
                "stage_key": lead.stage_key,
                "assigned_user_id": str(assigned_user.id),
                "phone_recorded": bool(payload.phone),
                "email_recorded": bool(payload.email),
            },
            reason="Manual local lead creation",
        )
    )
    db.commit()
    db.refresh(lead)
    return lead_to_read(db, lead)


def list_leads(
    db: Session,
    principal: Principal,
    *,
    archived: bool = False,
    limit: int = 100,
) -> list[LeadRead]:
    archive_filter = Lead.archived_at.is_not(None) if archived else Lead.archived_at.is_(None)
    filters = [
        Lead.organization_id == principal.organization_id,
        archive_filter,
    ]
    if (
        PermissionKeys.VIEW_LEADS not in principal.permission_keys
        and PermissionKeys.EDIT_LEADS not in principal.permission_keys
    ):
        filters.append(Lead.assigned_user_id == principal.user_id)
    leads = db.scalars(
        select(Lead).where(*filters).order_by(Lead.created_at.desc()).limit(limit)
    ).all()
    return [lead_to_read(db, lead) for lead in leads]


def get_lead_detail(db: Session, principal: Principal, lead_id: UUID) -> LeadDetail | None:
    lead = get_scoped_lead(db, principal, lead_id, include_archived=True)
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
    assignable_users = (
        db.scalars(
            select(User)
            .where(
                User.organization_id == principal.organization_id,
                User.is_active.is_(True),
            )
            .order_by(User.display_name.asc(), User.email.asc())
        ).all()
        if PermissionKeys.EDIT_LEADS in principal.permission_keys
        else []
    )
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
    open_tasks = db.scalars(
        select(Task)
        .where(
            Task.organization_id == principal.organization_id,
            Task.lead_id == lead.id,
            Task.status.in_(("open", "in_progress")),
        )
        .order_by(Task.due_at.is_(None), Task.due_at.asc(), Task.created_at.asc())
        .limit(20)
    ).all()
    communications = db.scalars(
        select(CommunicationRecord)
        .where(
            CommunicationRecord.organization_id == principal.organization_id,
            CommunicationRecord.lead_id == lead.id,
        )
        .order_by(CommunicationRecord.occurred_at.desc(), CommunicationRecord.created_at.desc())
        .limit(100)
    ).all()
    appointments = db.scalars(
        select(Appointment)
        .where(
            Appointment.organization_id == principal.organization_id,
            Appointment.lead_id == lead.id,
        )
        .order_by(Appointment.scheduled_start_at.asc(), Appointment.created_at.desc())
        .limit(20)
    ).all()
    restricted_assigned_access = (
        PermissionKeys.VIEW_LEADS not in principal.permission_keys
        and PermissionKeys.EDIT_LEADS not in principal.permission_keys
    )
    underwriting_versions = (
        []
        if restricted_assigned_access
        else db.scalars(
            select(UnderwritingVersion)
            .where(
                UnderwritingVersion.organization_id == principal.organization_id,
                UnderwritingVersion.lead_id == lead.id,
            )
            .order_by(
                UnderwritingVersion.version_number.desc(),
                UnderwritingVersion.created_at.desc(),
            )
            .limit(20)
        ).all()
    )
    underwriting_analyses_by_version = {
        analysis.underwriting_version_id: analysis
        for analysis in (
            db.scalars(
                select(UnderwritingMarketAnalysis).where(
                    UnderwritingMarketAnalysis.organization_id
                    == principal.organization_id,
                    UnderwritingMarketAnalysis.underwriting_version_id.in_(
                        [version.id for version in underwriting_versions]
                    ),
                )
            ).all()
            if underwriting_versions
            else []
        )
        if analysis.underwriting_version_id is not None
    }
    transactions = (
        []
        if restricted_assigned_access
        else db.scalars(
            select(Transaction)
            .where(
                Transaction.organization_id == principal.organization_id,
                Transaction.lead_id == lead.id,
            )
            .order_by(Transaction.created_at.desc())
            .limit(10)
        ).all()
    )
    transaction_ids = [transaction.id for transaction in transactions]
    checklist_items_by_transaction: dict[UUID, list[TransactionChecklistItem]] = {
        transaction_id: [] for transaction_id in transaction_ids
    }
    if transaction_ids:
        checklist_items = db.scalars(
            select(TransactionChecklistItem)
            .where(
                TransactionChecklistItem.organization_id == principal.organization_id,
                TransactionChecklistItem.transaction_id.in_(transaction_ids),
            )
            .order_by(
                TransactionChecklistItem.sort_order.asc(),
                TransactionChecklistItem.created_at.asc(),
            )
        ).all()
        for item in checklist_items:
            checklist_items_by_transaction[item.transaction_id].append(item)
    buyer_offers = (
        []
        if restricted_assigned_access
        else db.scalars(
            select(BuyerOffer)
            .where(
                BuyerOffer.organization_id == principal.organization_id,
                BuyerOffer.lead_id == lead.id,
            )
            .order_by(BuyerOffer.received_at.desc(), BuyerOffer.created_at.desc())
            .limit(20)
        ).all()
    )
    buyer_ids = [offer.buyer_id for offer in buyer_offers]
    buyers_by_id = {
        buyer.id: buyer
        for buyer in db.scalars(
            select(Buyer).where(
                Buyer.organization_id == principal.organization_id,
                Buyer.id.in_(buyer_ids),
            )
        ).all()
    } if buyer_ids else {}

    return LeadDetail(
        **base.model_dump(),
        contact_methods=[
            ContactMethodRead(
                id=method.id,
                method_type=method.method_type,
                value=method.value,
                is_primary=method.is_primary,
            )
            for method in contact_methods
        ],
        assignable_users=[
            LeadAssignableUserRead(
                id=user.id,
                display_name=user.display_name,
                email=user.email,
            )
            for user in assignable_users
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
        open_tasks=[
            LeadTaskRead(
                id=task.id,
                task_type=task.task_type,
                work_kind=task.work_kind,
                title=task.title,
                status=task.status,
                priority=task.priority,
                due_at=task.due_at,
                completed_at=task.completed_at,
            )
            for task in open_tasks
        ],
        communications=[
            CommunicationRecordRead(
                id=communication.id,
                direction=communication.direction,
                channel=communication.channel,
                status=communication.status,
                provider=communication.provider,
                provider_message_id=communication.provider_message_id,
                subject=communication.subject,
                body=communication.body,
                occurred_at=communication.occurred_at,
                created_at=communication.created_at,
            )
            for communication in communications
        ],
        appointments=[
            AppointmentRead(
                id=appointment.id,
                appointment_type=appointment.appointment_type,
                status=appointment.status,
                scheduled_start_at=appointment.scheduled_start_at,
                scheduled_end_at=appointment.scheduled_end_at,
                location_type=appointment.location_type,
                location=appointment.location,
                notes=appointment.notes,
                outcome=appointment.outcome,
                created_at=appointment.created_at,
            )
            for appointment in appointments
        ],
        underwriting_versions=[
            UnderwritingVersionRead(
                id=version.id,
                version_number=version.version_number,
                status=version.status,
                arv_low_cents=version.arv_low_cents,
                arv_high_cents=version.arv_high_cents,
                repair_low_cents=version.repair_low_cents,
                repair_high_cents=version.repair_high_cents,
                max_offer_cents=version.max_offer_cents,
                recommended_offer_cents=version.recommended_offer_cents,
                offer_strategy=version.offer_strategy,
                notes=version.notes,
                source=version.source,
                created_at=version.created_at,
                arv_point_cents=optional_int(
                    (version.underwriting_metadata or {}).get("arv_point_cents")
                ),
                total_rehab_cents=optional_int(
                    (version.underwriting_metadata or {}).get("total_rehab_cents")
                ),
                recommended_disposition_cents=optional_int(
                    (version.underwriting_metadata or {}).get(
                        "recommended_disposition_cents"
                    )
                ),
                seller_contract_ceiling_cents=optional_int(
                    (version.underwriting_metadata or {}).get(
                        "seller_contract_ceiling_cents"
                    )
                ),
                report_stage=string_or_none(
                    (version.underwriting_metadata or {}).get("report_stage")
                ),
                repair_estimate_source=string_or_none(
                    dict_value(
                        (version.underwriting_metadata or {}).get("pre_meeting_inputs")
                    ).get("repair_estimate_source")
                ),
                comp_search_level=string_or_none(
                    dict_value(
                        (version.underwriting_metadata or {}).get(
                            "comp_search_summary"
                        )
                    ).get("final_level")
                ),
                repair_catalog_version=string_or_none(
                    dict_value(
                        (version.underwriting_metadata or {}).get(
                            "pre_meeting_inputs"
                        )
                    ).get("repair_catalog_version")
                ),
                comp_snapshot=underwriting_version_comp_snapshot(
                    underwriting_analyses_by_version.get(version.id)
                ),
                repair_snapshot=underwriting_version_repair_snapshot(
                    version.underwriting_metadata or {}
                ),
                adjustment_snapshot=underwriting_version_adjustment_snapshot(
                    version.underwriting_metadata or {}
                ),
            )
            for version in underwriting_versions
        ],
        transactions=[
            TransactionRead(
                id=transaction.id,
                deal_id=transaction.deal_id,
                status=transaction.status,
                contract_type=transaction.contract_type,
                purchase_price_cents=transaction.purchase_price_cents,
                assignment_fee_cents=transaction.assignment_fee_cents,
                earnest_money_cents=transaction.earnest_money_cents,
                title_company=transaction.title_company,
                closing_date=transaction.closing_date,
                inspection_period_days=transaction.inspection_period_days,
                contract_sent_at=transaction.contract_sent_at,
                contract_executed_at=transaction.contract_executed_at,
                notes=transaction.notes,
                checklist_items=[
                    TransactionChecklistItemRead(
                        id=item.id,
                        title=item.title,
                        status=item.status,
                        due_at=item.due_at,
                        completed_at=item.completed_at,
                        sort_order=item.sort_order,
                    )
                    for item in checklist_items_by_transaction[transaction.id]
                ],
                created_at=transaction.created_at,
            )
            for transaction in transactions
        ],
        buyer_offers=[
            BuyerOfferRead(
                id=offer.id,
                buyer_id=offer.buyer_id,
                buyer_name=buyers_by_id[offer.buyer_id].name
                if offer.buyer_id in buyers_by_id
                else "Unknown buyer",
                amount_cents=offer.amount_cents,
                earnest_money_cents=offer.earnest_money_cents,
                financing_type=offer.financing_type,
                status=offer.status,
                proof_of_funds_received=offer.proof_of_funds_received,
                notes=offer.notes,
                received_at=offer.received_at,
                created_at=offer.created_at,
            )
            for offer in buyer_offers
        ],
        recent_activity=[
            ActivityEventRead(
                event_type=activity.event_type,
                summary=activity.summary,
                created_at=activity.created_at,
            )
            for activity in recent_activity
        ],
        intelligence=build_lead_intelligence(
            lead=lead,
            contact_methods=list(contact_methods),
            open_tasks=list(open_tasks),
        ),
    )


def build_lead_intelligence(
    *,
    lead: Lead,
    contact_methods: list[ContactMethod],
    open_tasks: list[Task],
) -> LeadIntelligence:
    missing_fields = get_missing_fields(lead, contact_methods)
    quality_score = get_quality_score(missing_fields)
    urgency_score = get_urgency_score(lead, open_tasks)
    next_best_action = get_next_best_action(lead, missing_fields, open_tasks, quality_score)
    return LeadIntelligence(
        quality_score=quality_score,
        urgency_score=urgency_score,
        priority_label=get_priority_label(urgency_score),
        missing_fields=missing_fields,
        next_best_action=next_best_action,
        ai_ready_summary=get_ai_ready_summary(
            lead,
            missing_fields,
            next_best_action,
            urgency_score,
        ),
    )


def get_missing_fields(lead: Lead, contact_methods: list[ContactMethod]) -> list[LeadMissingField]:
    missing_fields: list[LeadMissingField] = []
    if not contact_methods:
        missing_fields.append(
            LeadMissingField(
                field_key="contact_method",
                label="Contact method",
                question="What is the best phone number or email for seller follow-up?",
                severity="high",
            )
        )
    for field_key, label, question, severity in QUALIFICATION_FIELDS:
        value = getattr(lead, field_key)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing_fields.append(
                LeadMissingField(
                    field_key=field_key,
                    label=label,
                    question=question,
                    severity=severity,
                )
            )
    return missing_fields


def get_quality_score(missing_fields: list[LeadMissingField]) -> int:
    total_fields = len(QUALIFICATION_FIELDS) + 1
    high_penalty = sum(15 for field in missing_fields if field.severity == "high")
    medium_penalty = sum(10 for field in missing_fields if field.severity == "medium")
    raw_score = 100 - high_penalty - medium_penalty
    if len(missing_fields) == total_fields:
        return 0
    return max(0, min(100, raw_score))


def get_urgency_score(lead: Lead, open_tasks: list[Task]) -> int:
    score = 0
    if lead.lead_temperature == "hot":
        score += 30
    elif lead.lead_temperature == "warm":
        score += 18

    timeline = (lead.desired_timeline or "").strip().lower()
    if timeline in HIGH_URGENCY_TIMELINES or "asap" in timeline or "30" in timeline:
        score += 30
    elif timeline in MEDIUM_URGENCY_TIMELINES or "60" in timeline or "90" in timeline:
        score += 15

    now = datetime.now(UTC)
    for task in open_tasks:
        if task.due_at is None:
            continue
        due_at = task.due_at if task.due_at.tzinfo else task.due_at.replace(tzinfo=UTC)
        if due_at <= now:
            score += 25
            break

    if lead.stage_key in {"new", "contact_attempt_due", "attempting_contact"}:
        score += 12
    if lead.source in PAID_LEAD_SOURCES:
        score += 8
    if lead.next_follow_up_at is None and lead.stage_key not in {"dead", "disqualified"}:
        score += 8
    return max(0, min(100, score))


def get_priority_label(urgency_score: int) -> str:
    if urgency_score >= 80:
        return "critical"
    if urgency_score >= 60:
        return "high"
    if urgency_score >= 35:
        return "medium"
    return "routine"


def get_next_best_action(
    lead: Lead,
    missing_fields: list[LeadMissingField],
    open_tasks: list[Task],
    quality_score: int,
) -> LeadNextBestAction:
    overdue_task = get_first_overdue_task(open_tasks)
    if overdue_task is not None:
        return LeadNextBestAction(
            action_type="complete_overdue_task",
            label="Complete overdue follow-up",
            description=f"Work the overdue task: {overdue_task.title}.",
            priority="urgent",
        )

    high_missing_field = next(
        (field for field in missing_fields if field.severity == "high"),
        None,
    )
    if high_missing_field is not None:
        return LeadNextBestAction(
            action_type="ask_missing_question",
            label=f"Ask about {high_missing_field.label.lower()}",
            description=high_missing_field.question,
            priority="high",
        )

    if lead.appointment_status in {None, "", "not_scheduled", "appointment_requested"}:
        return LeadNextBestAction(
            action_type="schedule_appointment",
            label="Schedule seller appointment",
            description=(
                "Qualification is strong enough to move toward a walkthrough or seller call."
            ),
            priority="high" if quality_score >= 70 else "normal",
        )

    if lead.stage_key in {"qualified", "appointment_scheduled", "underwriting"}:
        return LeadNextBestAction(
            action_type="prepare_underwriting",
            label="Prepare underwriting review",
            description="Move known property facts into offer analysis and identify pricing gaps.",
            priority="normal",
        )

    return LeadNextBestAction(
        action_type="create_follow_up",
        label="Create next follow-up",
        description="Set the next dated task so the lead does not fall through the cracks.",
        priority="normal",
    )


def get_first_overdue_task(open_tasks: list[Task]) -> Task | None:
    now = datetime.now(UTC)
    for task in open_tasks:
        if task.due_at is None:
            continue
        due_at = task.due_at if task.due_at.tzinfo else task.due_at.replace(tzinfo=UTC)
        if due_at <= now:
            return task
    return None


def get_ai_ready_summary(
    lead: Lead,
    missing_fields: list[LeadMissingField],
    next_best_action: LeadNextBestAction,
    urgency_score: int,
) -> LeadAiReadySummary:
    known_facts = [
        f"Stage: {lead.stage_key}.",
        f"Source: {lead.source}.",
    ]
    optional_facts = [
        ("Temperature", lead.lead_temperature),
        ("Motivation", lead.motivation),
        ("Timeline", lead.desired_timeline),
        ("Condition", lead.property_condition),
        ("Occupancy", lead.occupancy_status),
        ("Asking price", lead.asking_price),
        ("Mortgage balance", lead.mortgage_balance),
        ("Appointment", lead.appointment_status),
    ]
    known_facts.extend(
        f"{label}: {value}." for label, value in optional_facts if value is not None and value != ""
    )
    if urgency_score >= 60:
        urgency = "High urgency lead."
    elif urgency_score >= 35:
        urgency = "Moderate urgency lead."
    else:
        urgency = "Routine urgency lead."
    situation = lead.motivation or "Seller motivation has not been captured yet."
    return LeadAiReadySummary(
        situation=situation,
        urgency=urgency,
        known_facts=known_facts,
        missing_questions=[field.question for field in missing_fields],
        recommended_next_action=next_best_action.label,
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
    sync_conversation_to_lead_stage(
        db,
        lead,
        actor_user_id=principal.user_id,
        reason=payload.reason,
    )
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


def add_lead_note(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    payload: LeadNoteCreate,
) -> LeadDetail | None:
    lead = get_scoped_lead(db, principal, lead_id)
    if lead is None:
        return None

    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            event_type="lead.note_added",
            summary=payload.note,
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="lead.note_create",
            entity_type="lead",
            entity_id=lead.id,
            previous_value=None,
            new_value={"note": payload.note},
            reason="Lead note added",
        )
    )
    db.commit()
    return get_lead_detail(db, principal, lead_id)


def create_lead_follow_up_task(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    payload: LeadFollowUpTaskCreate,
) -> LeadDetail | None:
    lead = get_scoped_lead(db, principal, lead_id)
    if lead is None:
        return None

    supersede_open_primary_tasks(db, lead_id=lead.id)
    task = Task(
        organization_id=principal.organization_id,
        lead_id=lead.id,
        deal_id=None,
        responsible_user_id=lead.assigned_user_id or principal.user_id,
        task_type="follow_up",
        work_kind="primary_next_action",
        title=payload.title,
        status="open",
        priority=payload.priority,
        due_at=payload.due_at,
        completed_at=None,
    )
    db.add(task)
    if payload.due_at is not None:
        previous_follow_up = lead.next_follow_up_at
        lead.next_follow_up_at = payload.due_at
    else:
        previous_follow_up = None
    db.flush()
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            event_type="task.follow_up_created",
            summary=f"Follow-up task created: {task.title}.",
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="task.follow_up_create",
            entity_type="task",
            entity_id=task.id,
            previous_value={"next_follow_up_at": previous_follow_up.isoformat()}
            if previous_follow_up
            else None,
            new_value={
                "lead_id": str(lead.id),
                "title": task.title,
                "priority": task.priority,
                "due_at": task.due_at.isoformat() if task.due_at else None,
            },
            reason="Manual lead follow-up task",
        )
    )
    db.commit()
    return get_lead_detail(db, principal, lead_id)


def add_lead_communication(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    payload: LeadCommunicationCreate,
) -> LeadDetail | None:
    if payload.direction not in COMMUNICATION_DIRECTIONS:
        raise ValueError(f"Unsupported communication direction: {payload.direction}")
    if payload.channel not in COMMUNICATION_CHANNELS:
        raise ValueError(f"Unsupported communication channel: {payload.channel}")
    if payload.status not in COMMUNICATION_STATUSES:
        raise ValueError(f"Unsupported communication status: {payload.status}")

    lead = get_scoped_lead(db, principal, lead_id)
    if lead is None:
        return None

    conversation = ensure_primary_conversation(db, lead)
    occurred_at = payload.occurred_at or datetime.now(UTC)
    communication = CommunicationRecord(
        organization_id=principal.organization_id,
        conversation_id=conversation.id,
        lead_id=lead.id,
        contact_id=lead.contact_id,
        actor_user_id=principal.user_id,
        direction=payload.direction,
        channel=payload.channel,
        status=payload.status,
        provider="manual",
        provider_message_id=None,
        subject=payload.subject,
        body=payload.body,
        occurred_at=occurred_at,
        external_payload=None,
        communication_metadata={
            "source": "manual_log",
            "automation_allowed": False,
        },
    )
    db.add(communication)
    update_conversation_activity(
        conversation,
        direction=payload.direction,
        occurred_at=occurred_at,
    )
    db.flush()

    summary = (
        f"{payload.direction.title()} {payload.channel} {payload.status}: "
        f"{payload.body[:160]}"
    )
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            event_type="lead.communication_logged",
            summary=summary,
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="communication.log",
            entity_type="communication_record",
            entity_id=communication.id,
            previous_value=None,
            new_value={
                "lead_id": str(lead.id),
                "direction": communication.direction,
                "channel": communication.channel,
                "status": communication.status,
                "provider": communication.provider,
                "occurred_at": communication.occurred_at.isoformat(),
            },
            reason="Manual communication log",
        )
    )
    db.commit()
    return get_lead_detail(db, principal, lead_id)


def create_lead_appointment(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    payload: LeadAppointmentCreate,
) -> LeadDetail | None:
    if payload.appointment_type not in APPOINTMENT_TYPES:
        raise ValueError(f"Unsupported appointment type: {payload.appointment_type}")
    if payload.status not in APPOINTMENT_STATUSES:
        raise ValueError(f"Unsupported appointment status: {payload.status}")
    if payload.location_type not in APPOINTMENT_LOCATION_TYPES:
        raise ValueError(f"Unsupported appointment location type: {payload.location_type}")
    if (
        payload.scheduled_end_at is not None
        and payload.scheduled_end_at <= payload.scheduled_start_at
    ):
        raise ValueError("Appointment end time must be after start time.")

    lead = get_scoped_lead(db, principal, lead_id)
    if lead is None:
        return None

    conversation = ensure_primary_conversation(db, lead)
    previous_values = {
        "appointment_status": lead.appointment_status,
        "next_follow_up_at": lead.next_follow_up_at.isoformat()
        if lead.next_follow_up_at
        else None,
        "stage_key": lead.stage_key,
    }
    appointment = Appointment(
        organization_id=principal.organization_id,
        lead_id=lead.id,
        contact_id=lead.contact_id,
        property_id=lead.property_id,
        owner_user_id=lead.assigned_user_id or principal.user_id,
        appointment_type=payload.appointment_type,
        status=payload.status,
        scheduled_start_at=payload.scheduled_start_at,
        scheduled_end_at=payload.scheduled_end_at,
        location_type=payload.location_type,
        location=payload.location,
        notes=payload.notes,
        outcome=None,
        external_calendar_id=None,
        appointment_metadata={
            "source": "manual_schedule",
            "calendar_synced": False,
        },
    )
    db.add(appointment)
    add_automatic_owner_watchers(db, conversation)

    lead.appointment_status = payload.status
    lead.next_follow_up_at = payload.scheduled_start_at
    if lead.stage_key in {
        "new",
        "contact_attempt_due",
        "attempting_contact",
        "contacted",
        "qualification_in_progress",
        "qualified",
    }:
        lead.stage_key = "appointment_scheduled"

    db.flush()
    from app.services.acquisition_operations import (
        create_notification,
        upsert_internal_calendar_event,
    )

    upsert_internal_calendar_event(db, appointment)
    create_notification(
        db,
        organization_id=principal.organization_id,
        recipient_user_id=appointment.owner_user_id,
        notification_type="appointment_scheduled",
        title="Seller appointment scheduled",
        body=f"{payload.appointment_type.replace('_', ' ').title()} scheduled for the lead.",
        entity_type="appointment",
        entity_id=appointment.id,
        action_url=f"/os/leads/{lead.id}?tab=communications",
        dedupe_key=f"appointment-scheduled:{appointment.id}",
    )
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            event_type="lead.appointment_scheduled",
            summary=(
                f"{payload.appointment_type} appointment scheduled for "
                f"{payload.scheduled_start_at.isoformat()}."
            ),
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="appointment.create",
            entity_type="appointment",
            entity_id=appointment.id,
            previous_value=previous_values,
            new_value={
                "lead_id": str(lead.id),
                "appointment_type": appointment.appointment_type,
                "status": appointment.status,
                "scheduled_start_at": appointment.scheduled_start_at.isoformat(),
                "scheduled_end_at": appointment.scheduled_end_at.isoformat()
                if appointment.scheduled_end_at
                else None,
                "location_type": appointment.location_type,
                "stage_key": lead.stage_key,
            },
            reason="Manual appointment scheduling",
        )
    )
    db.commit()
    return get_lead_detail(db, principal, lead_id)


def create_lead_underwriting_version(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    payload: LeadUnderwritingCreate,
) -> LeadDetail | None:
    if payload.status not in UNDERWRITING_STATUSES:
        raise ValueError(f"Unsupported underwriting status: {payload.status}")
    validate_money_range("ARV", payload.arv_low_cents, payload.arv_high_cents)
    validate_money_range("repair", payload.repair_low_cents, payload.repair_high_cents)
    if (
        payload.recommended_offer_cents is not None
        and payload.max_offer_cents is not None
        and payload.recommended_offer_cents > payload.max_offer_cents
    ):
        raise ValueError("Recommended offer cannot exceed maximum offer.")

    lead = get_scoped_lead(db, principal, lead_id)
    if lead is None:
        return None

    latest_version = db.scalar(
        select(func.max(UnderwritingVersion.version_number)).where(
            UnderwritingVersion.organization_id == principal.organization_id,
            UnderwritingVersion.lead_id == lead.id,
        )
    )
    version_number = int(latest_version or 0) + 1
    previous_stage = lead.stage_key
    version = UnderwritingVersion(
        organization_id=principal.organization_id,
        lead_id=lead.id,
        property_id=lead.property_id,
        created_by_user_id=principal.user_id,
        version_number=version_number,
        status=payload.status,
        arv_low_cents=payload.arv_low_cents,
        arv_high_cents=payload.arv_high_cents,
        repair_low_cents=payload.repair_low_cents,
        repair_high_cents=payload.repair_high_cents,
        max_offer_cents=payload.max_offer_cents,
        recommended_offer_cents=payload.recommended_offer_cents,
        offer_strategy=payload.offer_strategy,
        notes=payload.notes,
        source="manual",
        underwriting_metadata={
            "provider_imported": False,
            "human_review_required": payload.status != "approved",
        },
    )
    db.add(version)

    if lead.stage_key not in {"offer_presented", "negotiating", "under_contract"}:
        lead.stage_key = "offer_ready" if payload.status == "approved" else "underwriting"

    db.flush()
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            event_type="lead.underwriting_created",
            summary=f"Underwriting version {version_number} created with {payload.status} status.",
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="underwriting.create",
            entity_type="underwriting_version",
            entity_id=version.id,
            previous_value={"stage_key": previous_stage},
            new_value={
                "lead_id": str(lead.id),
                "version_number": version.version_number,
                "status": version.status,
                "arv_low_cents": version.arv_low_cents,
                "arv_high_cents": version.arv_high_cents,
                "repair_low_cents": version.repair_low_cents,
                "repair_high_cents": version.repair_high_cents,
                "max_offer_cents": version.max_offer_cents,
                "recommended_offer_cents": version.recommended_offer_cents,
                "stage_key": lead.stage_key,
            },
            reason="Manual underwriting version",
        )
    )
    db.commit()
    return get_lead_detail(db, principal, lead_id)


def preview_lead_market_value(
    db: Session,
    principal: Principal,
    lead_id: UUID,
) -> LeadMarketValueEstimateRead | None:
    settings = get_settings()
    if settings.property_data_provider.lower() != "rentcast":
        raise ValueError("PROPERTY_DATA_PROVIDER must be set to rentcast for this preview.")
    if not settings.rentcast_api_key:
        raise ValueError("RENTCAST_API_KEY is not configured.")

    lead = get_scoped_lead(db, principal, lead_id)
    if lead is None:
        return None
    property_record = db.get(Property, lead.property_id)
    if property_record is None:
        raise ValueError("Lead is missing a property record.")

    address = format_property_address(property_record)
    client = RentCastClient(
        api_key=settings.rentcast_api_key,
        base_url=settings.rentcast_base_url,
        timeout_seconds=settings.openai_request_timeout_seconds,
    )
    try:
        estimate = client.get_value_estimate(
            address=address,
            property_type=property_record.property_type,
        )
    except RentCastClientError as exc:
        raise RuntimeError(str(exc)) from exc

    return LeadMarketValueEstimateRead(
        lead_id=lead.id,
        property_id=property_record.id,
        provider="rentcast",
        requested_address=address,
        estimated_value_cents=dollars_to_cents(estimate.price),
        estimated_value_low_cents=dollars_to_cents(estimate.price_range_low),
        estimated_value_high_cents=dollars_to_cents(estimate.price_range_high),
        subject_property=estimate.subject_property,
        comparables=[rentcast_comp_to_read(comp) for comp in estimate.comparables],
        source_note=(
            "RentCast /avm/value estimate and comparable listings. Use as draft "
            "underwriting support only; human ARV approval is required."
        ),
    )


def validate_lead_property_address(
    db: Session,
    principal: Principal,
    lead_id: UUID,
) -> PropertyValidationRead | None:
    settings = get_settings()
    if settings.property_data_provider.lower() != "rentcast":
        raise ValueError("PROPERTY_DATA_PROVIDER must be set to rentcast for address validation.")
    if not settings.rentcast_api_key:
        raise ValueError("RENTCAST_API_KEY is not configured.")
    lead = get_scoped_lead(db, principal, lead_id)
    if lead is None:
        return None
    property_record = db.get(Property, lead.property_id)
    if property_record is None:
        raise ValueError("Lead is missing a property record.")

    requested_address = format_property_address(property_record)
    client = RentCastClient(
        api_key=settings.rentcast_api_key,
        base_url=settings.rentcast_base_url,
        timeout_seconds=settings.openai_request_timeout_seconds,
    )
    try:
        provider_record = client.get_property_record(address=requested_address)
    except RentCastClientError as exc:
        raise RuntimeError(str(exc)) from exc

    previous = {
        "status": property_record.address_validation_status,
        "validated_address": property_record.validated_formatted_address,
    }
    metadata = validate_provider_record(property_record, provider_record)
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            event_type="property.address_validated",
            summary=(
                "Property address validation returned "
                f"{property_record.address_validation_status.replace('_', ' ')}."
            ),
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="property.address.validate",
            entity_type="property",
            entity_id=property_record.id,
            previous_value=previous,
            new_value={
                "status": property_record.address_validation_status,
                "validated_address": property_record.validated_formatted_address,
                "match_score": metadata.get("match_score"),
                "issues": metadata.get("issues"),
            },
            reason="Provider property-record validation",
        )
    )
    db.commit()
    db.refresh(property_record)
    return property_validation_to_read(property_record)


def create_lead_market_analysis(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    payload: LeadMarketAnalysisCreate | None = None,
) -> LeadMarketAnalysisRead | None:
    analysis_started_at = perf_counter()
    payload = payload or LeadMarketAnalysisCreate()
    settings = get_settings()
    methodology_control = resolve_underwriting_methodology(settings)
    if settings.property_data_provider.lower() != "rentcast":
        raise ValueError("PROPERTY_DATA_PROVIDER must be set to rentcast for market analysis.")
    if not settings.rentcast_api_key:
        raise ValueError("RENTCAST_API_KEY is not configured.")

    lead = get_scoped_lead(db, principal, lead_id)
    if lead is None:
        return None
    property_record = db.get(Property, lead.property_id)
    if property_record is None:
        raise ValueError("Lead is missing a property record.")

    repair_estimate = None
    effective_base_rehab_cents = payload.base_rehab_override_cents
    effective_repair_items = prepare_new_scope_items(
        [item.model_dump(mode="json") for item in payload.repair_items]
    )
    effective_contingency_percentage = payload.contingency_override_percentage
    effective_repair_notes = payload.repair_notes
    if payload.repair_estimate_id is not None:
        if (
            payload.base_rehab_override_cents is not None
            or payload.repair_items
            or payload.contingency_override_percentage is not None
        ):
            raise ValueError(
                "Choose either a saved repair estimate or direct repair inputs, not both."
            )
        repair_estimate = get_repair_estimate(
            db,
            principal,
            lead.id,
            payload.repair_estimate_id,
        )
        if repair_estimate is None:
            raise ValueError("The saved repair estimate was not found for this lead.")
        effective_base_rehab_cents = None
        effective_repair_items = repair_estimate.scope_items
        effective_contingency_percentage = repair_estimate.contingency_percentage
        effective_repair_notes = payload.repair_notes or repair_estimate.notes

    address = format_property_address(property_record)
    if payload.source_analysis_id is not None and payload.refresh_market_data:
        raise ValueError("A comp review cannot refresh market data at the same time.")
    analysis_query = select(UnderwritingMarketAnalysis).where(
        UnderwritingMarketAnalysis.organization_id == principal.organization_id,
        UnderwritingMarketAnalysis.lead_id == lead.id,
    )
    if payload.source_analysis_id is not None:
        cached_analysis = db.scalar(
            analysis_query.where(
                UnderwritingMarketAnalysis.id == payload.source_analysis_id
            )
        )
        if cached_analysis is None:
            raise ValueError("The source market analysis was not found for this lead.")
    else:
        cached_analysis = db.scalar(
            analysis_query.order_by(
                UnderwritingMarketAnalysis.created_at.desc(),
                UnderwritingMarketAnalysis.id.desc(),
            )
        )
    cached_raw = (
        cached_analysis.raw_response
        if cached_analysis is not None
        and cached_analysis.analysis_metadata
        and cached_analysis.analysis_metadata.get("methodology_version")
        in {"v2", "v2.1", "v2.2", METHODOLOGY_VERSION}
        and isinstance(cached_analysis.raw_response, dict)
        else None
    )
    cached_avm = cached_raw.get("avm") if cached_raw else None
    cached_sales = cached_raw.get("recorded_sales") if cached_raw else None
    cached_secondary = cached_raw.get("secondary_evidence") if cached_raw else None
    current_research_available = (
        isinstance(cached_secondary, dict)
        and cached_secondary.get("research_version") == "ai_comp_discovery_v1"
    )
    reuse_market_data = (
        (payload.source_analysis_id is not None or not payload.refresh_market_data)
        and isinstance(cached_avm, dict)
        and isinstance(cached_sales, list)
        and (payload.source_analysis_id is not None or current_research_available)
    )
    if payload.comp_review_decisions and not reuse_market_data:
        raise ValueError("Run a market analysis before reviewing comparable sales.")
    rent_error: str | None = None
    property_record_error: str | None = None
    provider_warnings: list[str] = []
    rent_estimate: RentCastRentEstimate | None = None
    address_evidence: dict[str, Any] = {}
    secondary_evidence = unavailable_secondary_evidence(
        "No fresh market-data research was requested."
    )
    supporting_evidence = unavailable_supporting_evidence(
        "No fresh supporting market evidence was requested."
    )
    avm_error: str | None = None
    comp_search_summary: dict[str, Any] | None = None
    provider_returned_comp_count = 0
    if reuse_market_data:
        assert isinstance(cached_avm, dict)
        estimate = value_estimate_from_payload(cached_avm)
        cached_subject = cached_raw.get("subject_record") if cached_raw else None
        cached_rent = cached_raw.get("rent") if cached_raw else None
        cached_address_evidence = (
            cached_raw.get("address_evidence") if cached_raw else None
        )
        cached_secondary_evidence = (
            cached_raw.get("secondary_evidence") if cached_raw else None
        )
        cached_supporting_evidence = (
            cached_raw.get("supporting_evidence") if cached_raw else None
        )
        cached_avm_error = cached_raw.get("avm_error") if cached_raw else None
        cached_property_record_error = (
            cached_raw.get("property_record_error") if cached_raw else None
        )
        address_evidence = (
            cached_address_evidence
            if isinstance(cached_address_evidence, dict)
            else {}
        )
        secondary_evidence = (
            cached_secondary_evidence
            if isinstance(cached_secondary_evidence, dict)
            else secondary_evidence
        )
        supporting_evidence = (
            cached_supporting_evidence
            if isinstance(cached_supporting_evidence, dict)
            else supporting_evidence
        )
        avm_error = (
            cached_avm_error
            if isinstance(cached_avm_error, str) and cached_avm_error
            else None
        )
        subject_record = cached_subject if isinstance(cached_subject, dict) else {}
        sale_records = (
            [record for record in cached_sales if isinstance(record, dict)]
            if isinstance(cached_sales, list)
            else []
        )
        cached_search_summary = (
            (cached_analysis.analysis_metadata or {}).get("comp_search_summary")
            if cached_analysis is not None
            else None
        )
        comp_search_summary = (
            cached_search_summary
            if isinstance(cached_search_summary, dict)
            else None
        )
        cached_execution_metrics = (
            (cached_analysis.analysis_metadata or {}).get("execution_metrics")
            if cached_analysis is not None
            else None
        )
        provider_returned_comp_count = (
            optional_int(cached_execution_metrics.get("provider_returned_comp_count"))
            if isinstance(cached_execution_metrics, dict)
            else None
        ) or len(sale_records)
        rent_estimate = (
            rent_estimate_from_payload(cached_rent)
            if isinstance(cached_rent, dict)
            else None
        )
        if isinstance(cached_property_record_error, str) and cached_property_record_error:
            property_record_error = cached_property_record_error
            provider_warnings.append(
                "The separate public property record was unavailable; subject facts came "
                "from the RentCast AVM response."
            )
        if avm_error:
            provider_warnings.append(
                "The RentCast AVM was unavailable; value conclusions use screened recorded "
                "sales only."
            )
        if comp_search_summary is not None:
            provider_warnings.extend(
                warnings_from_search_summary(comp_search_summary)
            )
    else:
        client = RentCastClient(
            api_key=settings.rentcast_api_key,
            base_url=settings.rentcast_base_url,
            timeout_seconds=settings.openai_request_timeout_seconds,
        )
        try:
            resolution = resolve_rentcast_subject(
                client,
                property_record,
                requested_address=address,
            )
        except RentCastClientError as exc:
            logger.warning(
                "underwriting_market_data_failed",
                lead_id=str(lead.id),
                provider="rentcast",
                operation=exc.operation,
                provider_status_code=exc.status_code,
                provider_error_code=exc.error_code,
                error_message=str(exc),
            )
            raise RuntimeError(str(exc)) from exc
        estimate = resolution.estimate
        subject_record = resolution.subject_record
        address_evidence = resolution.address_evidence
        property_record_error = resolution.property_record_error
        avm_error = resolution.avm_error
        resolved_address = resolution.resolved_address
        if property_record_error:
            provider_warnings.append(
                "The separate public property record was unavailable; subject facts came "
                "from the RentCast AVM response."
            )
            logger.warning(
                "underwriting_optional_property_record_failed",
                lead_id=str(lead.id),
                provider="rentcast",
                operation="property record",
                error_message=property_record_error,
            )
        if avm_error:
            provider_warnings.append(
                "The RentCast AVM was unavailable; value conclusions use screened recorded "
                "sales only."
            )

        subject_facts = {**estimate.subject_property, **subject_record}
        try:
            search_result = search_adaptive_closed_sales(
                client,
                address=resolved_address,
                subject_facts=subject_facts,
                local_property_type=property_record.property_type,
                condition_overrides=payload.comp_condition_overrides,
            )
        except RentCastClientError as exc:
            logger.warning(
                "underwriting_market_data_failed",
                lead_id=str(lead.id),
                provider="rentcast",
                operation=exc.operation,
                provider_status_code=exc.status_code,
                provider_error_code=exc.error_code,
                error_message=str(exc),
            )
            raise RuntimeError(str(exc)) from exc
        sale_records = search_result.records
        comp_search_summary = search_result.summary
        provider_returned_comp_count = search_result.provider_returned_count
        provider_warnings.extend(search_result.warnings)

        try:
            rent_estimate = client.get_rent_estimate(
                address=resolved_address,
                property_type=property_record.property_type,
            )
        except RentCastClientError as exc:
            logger.warning(
                "underwriting_optional_rent_data_failed",
                lead_id=str(lead.id),
                provider="rentcast",
                operation=exc.operation,
                provider_status_code=exc.status_code,
                provider_error_code=exc.error_code,
                error_message=str(exc),
            )
            rent_error = str(exc)
        secondary_evidence = collect_secondary_market_evidence(
            settings,
            property_record,
            requested_address=resolved_address,
            subject_facts=subject_facts,
        )
        provider_warnings.extend(secondary_conflict_warnings(secondary_evidence))
        supporting_evidence = collect_supporting_market_evidence(
            client,
            address=resolved_address,
            postal_code=property_record.postal_code,
            subject_facts=subject_facts,
            local_property_type=property_record.property_type,
        )

    if subject_record:
        validate_provider_record(property_record, subject_record)
        property_record.address_validation_metadata = {
            **(property_record.address_validation_metadata or {}),
            "resolution": address_evidence,
        }
    provider_sale_records = sale_records
    research_sale_records = research_comparable_sale_records(secondary_evidence)
    sale_records, duplicate_research_sale_count = merge_research_comparable_sales(
        provider_sale_records,
        research_sale_records,
    )
    if research_sale_records:
        provider_warnings.append(
            "AI-discovered public closed sales supplement the provider search. Review each "
            "cited source before approving seller-facing value or offer guidance."
        )
    manual_sale_records, manual_comp_ids = resolve_manual_comparable_records(
        db,
        principal,
        lead,
        payload.manual_comp_ids,
        source_analysis=cached_analysis,
    )
    sale_records, duplicate_manual_comp_ids = merge_verified_manual_sales(
        sale_records,
        manual_sale_records,
    )
    result = analyze_underwriting_v2(
        estimate=estimate,
        subject_record=subject_record,
        sale_records=sale_records,
        rent_estimate=rent_estimate,
        local_property_type=property_record.property_type,
        lead_condition=lead.property_condition,
        current_condition_override=payload.current_condition,
        target_condition=payload.target_condition,
        repair_level_override=payload.repair_level,
        base_rehab_override_cents=effective_base_rehab_cents,
        repair_items=effective_repair_items,
        contingency_override_percentage=effective_contingency_percentage,
        holding_period_months=payload.holding_period_months,
        condition_overrides=payload.comp_condition_overrides,
        comp_review_decisions=[
            decision.model_dump(mode="json")
            for decision in payload.comp_review_decisions
        ],
        provider_warnings=provider_warnings,
        address_validation_status=property_record.address_validation_status,
        address_match_score=(
            optional_int(address_evidence.get("match_score"))
            or optional_int(
                (property_record.address_validation_metadata or {}).get("match_score")
            )
        ),
        secondary_evidence=secondary_evidence,
        settings=settings,
    )
    market_adjustment = (
        build_market_adjusted_conclusion(
            subject=dict_value(result.assumptions.get("canonical_subject_facts")),
            selected_comps=result.selected_comps,
            active_arv_point_cents=result.arv_point_cents,
            active_arv_low_cents=result.arv_low_cents,
            active_arv_high_cents=result.arv_high_cents,
        )
        if methodology_control.active_version == METHODOLOGY_VERSION
        else None
    )
    adjustment_shadow = (
        build_adjustment_shadow(
            subject=dict_value(result.assumptions.get("canonical_subject_facts")),
            selected_comps=result.selected_comps,
            active_arv_point_cents=result.arv_point_cents,
            active_arv_low_cents=result.arv_low_cents,
            active_arv_high_cents=result.arv_high_cents,
        )
        if methodology_control.shadow_enabled
        else None
    )
    if market_adjustment is not None:
        result = promote_market_adjusted_result(
            baseline=result,
            market_adjustment=market_adjustment,
            rent_estimate=rent_estimate,
            local_property_type=property_record.property_type,
            holding_period_months=payload.holding_period_months,
            settings=settings,
        )
    custom_inputs_applied = any(
        (
            payload.current_condition,
            payload.target_condition != "standard_flip",
            payload.base_rehab_override_cents is not None,
            payload.repair_items,
            payload.contingency_override_percentage is not None,
            payload.holding_period_months != 6,
            payload.repair_notes,
            payload.repair_estimate_id,
            payload.comp_condition_overrides,
            payload.comp_review_decisions,
            manual_comp_ids,
        )
    )
    report_stage = payload.input_verification_status
    if report_stage == "preliminary" and custom_inputs_applied:
        report_stage = "pre_meeting_reviewed"
    normalized_repair_items_value = result.assumptions.get("repair_items")
    normalized_repair_items = (
        [item for item in normalized_repair_items_value if isinstance(item, dict)]
        if isinstance(normalized_repair_items_value, list)
        else effective_repair_items
    )
    pre_meeting_inputs = UnderwritingPreMeetingInputsRead(
        verification_status=report_stage,
        report_stage=report_stage,
        current_condition=payload.current_condition,
        target_condition=payload.target_condition,
        repair_level=string_or_none(result.assumptions.get("repair_level")) or "moderate",
        repair_estimate_source=(
            repair_estimate.source_type
            if repair_estimate is not None
            else string_or_none(result.assumptions.get("repair_estimate_source"))
            or "system_estimate"
        ),
        base_rehab_override_cents=effective_base_rehab_cents,
        repair_items=[
            RepairEstimateItemInput.model_validate(item)
            for item in normalized_repair_items
        ],
        contingency_override_percentage=effective_contingency_percentage,
        holding_period_months=payload.holding_period_months,
        repair_notes=effective_repair_notes,
        custom_inputs_applied=custom_inputs_applied,
        repair_estimate_id=repair_estimate.id if repair_estimate else None,
        repair_estimate_contractor_name=(
            repair_estimate.contractor_name if repair_estimate else None
        ),
        repair_estimate_date=repair_estimate.estimate_date if repair_estimate else None,
        repair_estimate_reference=(
            repair_estimate.evidence_reference if repair_estimate else None
        ),
        repair_catalog_version=string_or_none(
            dict_value(result.assumptions.get("repair_scenario")).get("version")
        ),
        repair_scenario=(
            dict_value(result.assumptions.get("repair_scenario")) or None
        ),
    )
    assignment_fee_cents = settings.underwriting_default_assignment_fee_cents
    reviewed_at = datetime.now(UTC)
    comp_review = (
        {
            "source_analysis_id": str(cached_analysis.id),
            "reviewed_by_user_id": str(principal.user_id) if principal.user_id else None,
            "reviewed_at": reviewed_at.isoformat(),
            "included_count": sum(
                decision.included for decision in payload.comp_review_decisions
            ),
            "excluded_count": sum(
                not decision.included for decision in payload.comp_review_decisions
            ),
            "decisions": [
                decision.model_dump(mode="json")
                for decision in payload.comp_review_decisions
            ],
        }
        if payload.comp_review_decisions and cached_analysis is not None
        else None
    )
    candidate_comp_count = len(result.selected_comps) + len(result.rejected_comps)
    comp_review_override_count = count_comp_review_overrides(
        cached_analysis,
        payload.comp_review_decisions,
    )
    execution_metrics = {
        "duration_ms": max(0, round((perf_counter() - analysis_started_at) * 1000)),
        "provider_returned_comp_count": provider_returned_comp_count,
        "ai_research_comp_count": len(research_sale_records),
        "ai_research_duplicate_count": duplicate_research_sale_count,
        "candidate_comp_count": candidate_comp_count,
        "selected_comp_count": len(result.selected_comps),
        "rejected_comp_count": len(result.rejected_comps),
        "comp_yield_percentage": (
            round(len(result.selected_comps) / candidate_comp_count * 100, 1)
            if candidate_comp_count
            else None
        ),
        "market_data_reused": reuse_market_data,
        "comp_review_applied": comp_review is not None,
        "comp_review_decision_count": len(payload.comp_review_decisions),
        "comp_review_override_count": comp_review_override_count,
        "manual_review_required": result.manual_review_required,
    }
    if comp_search_summary is None:
        comp_search_summary = legacy_comp_search_summary(
            sale_records=sale_records,
            selected_count=len(result.selected_comps),
            rejected_count=len(result.rejected_comps),
        )
    comp_search_summary = add_research_evidence_to_search_summary(
        comp_search_summary,
        research_sale_count=len(research_sale_records),
        duplicate_count=duplicate_research_sale_count,
        source_count=len(list_of_dicts(secondary_evidence.get("sources"))),
        selected_comps=result.selected_comps,
        rejected_comps=result.rejected_comps,
    )
    comp_search_summary = add_manual_evidence_to_search_summary(
        comp_search_summary,
        manual_sale_count=len(manual_sale_records),
        duplicate_count=len(duplicate_manual_comp_ids),
        selected_comps=result.selected_comps,
        rejected_comps=result.rejected_comps,
    )
    analysis_metadata = {
        "methodology_version": methodology_control.active_version,
        "methodology_control": methodology_control.as_dict(),
        "execution_metrics": execution_metrics,
        "comp_search_summary": comp_search_summary,
        "report_stage": report_stage,
        "pre_meeting_inputs": pre_meeting_inputs.model_dump(mode="json"),
        "repair_estimate_id": str(repair_estimate.id) if repair_estimate else None,
        "subject_square_feet": first_int(
            {**estimate.subject_property, **subject_record},
            ("squareFootage", "livingArea", "grossLivingArea"),
        ),
        "human_review_required": result.manual_review_required,
        "recorded_sales_are_core_evidence": True,
        "avm_is_benchmark_only": True,
        "condition_evidence_required": True,
        "arv_value_basis": result.assumptions.get("arv_value_basis"),
        "as_is_value_basis": result.assumptions.get("as_is_value_basis"),
        "market_data_reused": reuse_market_data,
        "source_analysis_id": (
            str(cached_analysis.id) if reuse_market_data and cached_analysis else None
        ),
        "address_validation_status": property_record.address_validation_status,
        "address_validation_match_score": (
            (property_record.address_validation_metadata or {}).get("match_score")
        ),
        "address_evidence": address_evidence,
        "secondary_evidence": secondary_evidence,
        "supporting_evidence": supporting_evidence,
        "market_adjustment": market_adjustment,
        "adjustment_shadow": adjustment_shadow,
        "manual_comp_ids": [str(record_id) for record_id in manual_comp_ids],
        "manual_duplicate_comp_ids": duplicate_manual_comp_ids,
        "confidence_tier": result.confidence_tier,
        "confidence_factors": result.confidence_factors,
        "comp_review": comp_review,
        "as_is_value_low_cents": result.as_is_low_cents,
        "as_is_value_cents": result.as_is_value_cents,
        "as_is_value_high_cents": result.as_is_high_cents,
        "arv_point_cents": result.arv_point_cents,
        "conservative_arv_cents": result.conservative_arv_cents,
        "base_rehab_cents": result.base_rehab_cents,
        "rehab_contingency_percentage": result.rehab_contingency_percentage,
        "total_rehab_cents": result.total_rehab_cents,
        "repair_scenario": result.assumptions.get("repair_scenario"),
        "flip_buyer_max_cents": result.flip_buyer_max_cents,
        "rental_buyer_max_cents": result.rental_buyer_max_cents,
        "recommended_disposition_cents": result.recommended_disposition_cents,
        "seller_contract_ceiling_cents": result.seller_contract_ceiling_cents,
        "transaction_reserve_cents": settings.underwriting_transaction_reserve_cents,
        "monthly_rent_cents": result.monthly_rent_cents,
        "legacy_rule_cents": result.legacy_rule_cents,
        "review_reasons": result.review_reasons,
        "data_disagreements": result.data_disagreements,
        "assumptions": result.assumptions,
        "rent_estimate_error": rent_error,
        "property_record_error": property_record_error,
        "avm_error": avm_error,
    }

    latest_version = db.scalar(
        select(func.max(UnderwritingVersion.version_number)).where(
            UnderwritingVersion.organization_id == principal.organization_id,
            UnderwritingVersion.lead_id == lead.id,
        )
    )
    version_number = int(latest_version or 0) + 1
    previous_stage = lead.stage_key
    version = UnderwritingVersion(
        organization_id=principal.organization_id,
        lead_id=lead.id,
        property_id=lead.property_id,
        created_by_user_id=principal.user_id,
        version_number=version_number,
        status="needs_review",
        arv_low_cents=result.arv_low_cents,
        arv_high_cents=result.arv_high_cents,
        repair_low_cents=result.repair_low_cents,
        repair_high_cents=result.repair_high_cents,
        max_offer_cents=result.seller_contract_ceiling_cents,
        recommended_offer_cents=result.recommended_opening_offer_cents,
        offer_strategy="flip_or_rental_buyer_economics",
        notes=build_market_analysis_result_notes(
            result,
            report_stage=report_stage,
            methodology_version=methodology_control.active_version,
        ),
        source="rentcast_property_records",
        underwriting_metadata={
            "provider_imported": True,
            **analysis_metadata,
            "method": (
                "market_supported_adjusted_closed_sales_and_buyer_economics"
                if methodology_control.active_version == METHODOLOGY_VERSION
                else "recorded_sales_and_buyer_economics"
            ),
            "offer_formula": (
                "buyer maximum minus assignment target minus transaction reserve"
            ),
        },
    )
    db.add(version)
    db.flush()

    analysis = UnderwritingMarketAnalysis(
        organization_id=principal.organization_id,
        lead_id=lead.id,
        property_id=lead.property_id,
        underwriting_version_id=version.id,
        created_by_user_id=principal.user_id,
        provider="rentcast",
        requested_address=address,
        estimated_value_cents=dollars_to_cents(estimate.price),
        estimated_value_low_cents=dollars_to_cents(estimate.price_range_low),
        estimated_value_high_cents=dollars_to_cents(estimate.price_range_high),
        arv_low_cents=result.arv_low_cents,
        arv_high_cents=result.arv_high_cents,
        repair_low_cents=result.repair_low_cents,
        repair_high_cents=result.repair_high_cents,
        mao_low_cents=result.recommended_opening_offer_cents,
        mao_high_cents=result.seller_contract_ceiling_cents,
        recommended_offer_cents=result.recommended_opening_offer_cents,
        assignment_fee_cents=assignment_fee_cents,
        offer_low_percentage=round(settings.underwriting_offer_low_percentage * 100),
        offer_high_percentage=round(settings.underwriting_offer_high_percentage * 100),
        confidence_score=result.confidence_score,
        selected_comp_count=len(result.selected_comps),
        rejected_comp_count=len(result.rejected_comps),
        selected_comps=[comp.model_dump(mode="json") for comp in result.selected_comps],
        rejected_comps=[comp.model_dump(mode="json") for comp in result.rejected_comps],
        subject_property=dict_value(result.assumptions.get("canonical_subject_facts")),
        raw_response={
            "avm": estimate.raw_response,
            "subject_record": subject_record,
            "recorded_sales": provider_sale_records,
            "research_recorded_sales": research_sale_records,
            "manual_recorded_sales": manual_sale_records,
            "rent": rent_estimate.raw_response if rent_estimate else None,
            "property_record_error": property_record_error,
            "avm_error": avm_error,
            "address_evidence": address_evidence,
            "secondary_evidence": secondary_evidence,
            "supporting_evidence": supporting_evidence,
        },
        analysis_metadata=analysis_metadata,
    )
    db.add(analysis)
    db.flush()
    version.underwriting_metadata = {
        **(version.underwriting_metadata or {}),
        "market_analysis_id": str(analysis.id),
    }
    if lead.stage_key not in {"offer_presented", "negotiating", "under_contract"}:
        lead.stage_key = "underwriting"

    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            event_type=(
                "lead.comp_review_applied"
                if comp_review
                else "lead.market_analysis_created"
            ),
            summary=(
                (
                    f"Comp review applied with {len(result.selected_comps)} included and "
                    f"{len(result.rejected_comps)} excluded sales"
                    if comp_review
                    else (
                        "Stonegate Valuation created with "
                        f"{len(result.selected_comps)} recorded-sale comps"
                        + (
                            f", including {len(manual_comp_ids)} verified manual sale(s)"
                            if manual_comp_ids
                            else ""
                        )
                    )
                )
                + f" and {result.confidence_score}% confidence."
            ),
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action=(
                "underwriting.comp_review.apply"
                if comp_review
                else "underwriting.market_analysis.create"
            ),
            entity_type="underwriting_market_analysis",
            entity_id=analysis.id,
            previous_value={"stage_key": previous_stage},
            new_value={
                "lead_id": str(lead.id),
                "underwriting_version_id": str(version.id),
                "methodology_version": methodology_control.active_version,
                "arv_low_cents": result.arv_low_cents,
                "arv_high_cents": result.arv_high_cents,
                "seller_contract_ceiling_cents": result.seller_contract_ceiling_cents,
                "recommended_offer_cents": result.recommended_opening_offer_cents,
                "stage_key": lead.stage_key,
                "comp_review": comp_review,
            },
            reason=(
                "Human-reviewed comparable set and bounded weight adjustments"
                if comp_review
                else "Recorded-sale analysis and buyer-economics draft"
            ),
        )
    )
    db.commit()
    db.refresh(analysis)
    return market_analysis_to_read(analysis)


def get_latest_lead_market_analysis(
    db: Session,
    principal: Principal,
    lead_id: UUID,
) -> LeadMarketAnalysisRead | None:
    lead = get_scoped_lead(db, principal, lead_id)
    if lead is None:
        return None

    analysis = db.scalar(
        select(UnderwritingMarketAnalysis)
        .where(
            UnderwritingMarketAnalysis.organization_id == principal.organization_id,
            UnderwritingMarketAnalysis.lead_id == lead.id,
        )
        .order_by(
            UnderwritingMarketAnalysis.created_at.desc(),
            UnderwritingMarketAnalysis.id.desc(),
        )
        .limit(1)
    )
    return market_analysis_to_read(analysis) if analysis is not None else None


def create_lead_transaction(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    payload: LeadTransactionCreate,
) -> LeadDetail | None:
    if payload.contract_type not in TRANSACTION_CONTRACT_TYPES:
        raise ValueError(f"Unsupported contract type: {payload.contract_type}")

    lead = get_scoped_lead(db, principal, lead_id)
    if lead is None:
        return None

    existing_transaction = db.scalar(
        select(Transaction).where(
            Transaction.organization_id == principal.organization_id,
            Transaction.lead_id == lead.id,
            Transaction.status.in_(("contract_prep", "sent", "executed", "closing")),
        )
    )
    if existing_transaction is not None:
        raise ValueError("An active transaction already exists for this lead.")

    deal = db.scalar(
        select(Deal)
        .where(
            Deal.organization_id == principal.organization_id,
            Deal.lead_id == lead.id,
        )
        .order_by(Deal.created_at.desc())
    )
    if deal is None:
        deal = Deal(
            organization_id=principal.organization_id,
            lead_id=lead.id,
            property_id=lead.property_id,
            stage_key="contract_prep",
            contract_price_cents=payload.purchase_price_cents,
            assignment_fee_cents=payload.assignment_fee_cents,
        )
        db.add(deal)
        db.flush()
    else:
        deal.stage_key = "contract_prep"
        deal.contract_price_cents = payload.purchase_price_cents
        deal.assignment_fee_cents = payload.assignment_fee_cents

    previous_stage = lead.stage_key
    transaction = Transaction(
        organization_id=principal.organization_id,
        deal_id=deal.id,
        lead_id=lead.id,
        property_id=lead.property_id,
        contact_id=lead.contact_id,
        owner_user_id=lead.assigned_user_id or principal.user_id,
        status="contract_prep",
        contract_type=payload.contract_type,
        purchase_price_cents=payload.purchase_price_cents,
        assignment_fee_cents=payload.assignment_fee_cents,
        earnest_money_cents=payload.earnest_money_cents,
        title_company=payload.title_company,
        closing_date=payload.closing_date,
        inspection_period_days=payload.inspection_period_days,
        contract_sent_at=None,
        contract_executed_at=None,
        notes=payload.notes,
        transaction_metadata={
            "source": "manual_open",
            "esign_synced": False,
        },
    )
    db.add(transaction)
    db.flush()
    create_deal_next_action(
        db,
        deal=deal,
        lead=lead,
        responsible_user_id=transaction.coordinator_user_id or transaction.owner_user_id,
        title="Prepare and send the purchase agreement",
        due_at=transaction.due_diligence_deadline or transaction.closing_date,
    )
    prior_item: TransactionChecklistItem | None = None
    for index, (item_key, category, title, description) in enumerate(
        default_transaction_checklist_specs(), start=1
    ):
        item = TransactionChecklistItem(
            organization_id=principal.organization_id,
            transaction_id=transaction.id,
            responsible_user_id=transaction.owner_user_id,
            item_key=item_key,
            category=category,
            title=title,
            description=description,
            is_required=True,
            dependency_item_id=prior_item.id if prior_item else None,
            evidence_document_id=None,
            evidence_notes=None,
            escalated_at=None,
            status="open",
            due_at=payload.closing_date if "closing" in title.lower() else None,
            completed_at=None,
            sort_order=index,
        )
        db.add(item)
        db.flush()
        prior_item = item

    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            event_type="lead.transaction_opened",
            summary=(
                f"Transaction opened at {payload.purchase_price_cents / 100:.0f} "
                "purchase price."
            ),
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="transaction.create",
            entity_type="transaction",
            entity_id=transaction.id,
            previous_value={"stage_key": previous_stage},
            new_value={
                "lead_id": str(lead.id),
                "deal_id": str(deal.id),
                "status": transaction.status,
                "contract_type": transaction.contract_type,
                "purchase_price_cents": transaction.purchase_price_cents,
                "assignment_fee_cents": transaction.assignment_fee_cents,
                "earnest_money_cents": transaction.earnest_money_cents,
                "closing_date": transaction.closing_date.isoformat()
                if transaction.closing_date
                else None,
                "stage_key": lead.stage_key,
            },
            reason="Manual transaction opening",
        )
    )
    db.commit()
    return get_lead_detail(db, principal, lead_id)


def create_lead_buyer_offer(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    payload: LeadBuyerOfferCreate,
) -> LeadDetail | None:
    if payload.status not in BUYER_OFFER_STATUSES:
        raise ValueError(f"Unsupported buyer offer status: {payload.status}")
    if payload.financing_type not in BUYER_OFFER_FINANCING_TYPES:
        raise ValueError(f"Unsupported buyer offer financing type: {payload.financing_type}")

    lead = get_scoped_lead(db, principal, lead_id)
    if lead is None:
        return None

    buyer = db.scalar(
        select(Buyer).where(
            Buyer.organization_id == principal.organization_id,
            Buyer.id == payload.buyer_id,
        )
    )
    if buyer is None:
        raise ValueError("Buyer not found.")

    deal = db.scalar(
        select(Deal)
        .where(
            Deal.organization_id == principal.organization_id,
            Deal.lead_id == lead.id,
        )
        .order_by(Deal.created_at.desc())
    )
    offer = BuyerOffer(
        organization_id=principal.organization_id,
        lead_id=lead.id,
        deal_id=deal.id if deal is not None else None,
        buyer_id=buyer.id,
        amount_cents=payload.amount_cents,
        earnest_money_cents=payload.earnest_money_cents,
        financing_type=payload.financing_type,
        status=payload.status,
        proof_of_funds_received=payload.proof_of_funds_received,
        notes=payload.notes,
        received_at=payload.received_at or datetime.now(UTC),
    )
    db.add(offer)
    db.flush()
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            event_type="lead.buyer_offer_received",
            summary=f"Buyer offer received from {buyer.name} for {payload.amount_cents / 100:.0f}.",
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="buyer_offer.create",
            entity_type="buyer_offer",
            entity_id=offer.id,
            previous_value=None,
            new_value={
                "lead_id": str(lead.id),
                "deal_id": str(offer.deal_id) if offer.deal_id else None,
                "buyer_id": str(buyer.id),
                "amount_cents": offer.amount_cents,
                "earnest_money_cents": offer.earnest_money_cents,
                "financing_type": offer.financing_type,
                "status": offer.status,
                "proof_of_funds_received": offer.proof_of_funds_received,
            },
            reason="Manual buyer offer entry",
        )
    )
    db.commit()
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

    if "assigned_user_id" in provided_fields:
        update_lead_assignment(
            db,
            principal,
            lead,
            contact,
            payload.assigned_user_id,
            previous_values,
            new_values,
            reason=payload.reason,
        )

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
    update_nullable_value(
        previous_values,
        new_values,
        lead,
        "motivation",
        payload.motivation,
        provided_fields,
    )
    update_nullable_value(
        previous_values,
        new_values,
        lead,
        "desired_timeline",
        payload.desired_timeline,
        provided_fields,
    )
    update_nullable_value(
        previous_values,
        new_values,
        lead,
        "property_condition",
        payload.property_condition,
        provided_fields,
    )
    update_nullable_value(
        previous_values,
        new_values,
        lead,
        "occupancy_status",
        payload.occupancy_status,
        provided_fields,
    )
    update_nullable_value(
        previous_values,
        new_values,
        lead,
        "asking_price",
        payload.asking_price,
        provided_fields,
    )
    update_nullable_value(
        previous_values,
        new_values,
        lead,
        "mortgage_balance",
        payload.mortgage_balance,
        provided_fields,
    )
    update_nullable_value(
        previous_values,
        new_values,
        lead,
        "appointment_status",
        payload.appointment_status,
        provided_fields,
    )
    update_nullable_raw_value(
        previous_values,
        new_values,
        lead,
        "next_follow_up_at",
        payload.next_follow_up_at,
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

    if payload.contact_methods is not None:
        contact_methods_changed = sync_lead_contact_methods(
            db,
            principal,
            contact,
            payload.contact_methods,
            previous_values,
            new_values,
        )
        phone_changed = contact_methods_changed
        email_changed = False
    else:
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
        property_record.normalized_address_key = canonical_address_key(
            property_record.street_address,
            property_record.city,
            property_record.state,
            property_record.postal_code,
        )
        reset_property_validation(property_record)

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
        Lead.organization_id == principal.organization_id,
        Lead.archived_at.is_(None),
    ))
    new_paid_leads = count_scalar(db, select(func.count(Lead.id)).where(
        Lead.organization_id == principal.organization_id,
        Lead.archived_at.is_(None),
        Lead.stage_key == "new",
        Lead.source.in_(PAID_LEAD_SOURCES),
    ))
    active_contracts = count_scalar(db, select(func.count(Deal.id)).where(
        Deal.organization_id == principal.organization_id,
        Deal.stage_key == "under_contract",
    ))
    collected_revenue_cents = int(
        db.scalar(
            select(func.coalesce(func.sum(RevenueRecord.amount_cents), 0)).where(
                RevenueRecord.organization_id == principal.organization_id,
                RevenueRecord.status == "collected",
            )
        )
        or 0
    )
    pipeline_rows = db.execute(
        select(Lead.stage_key, func.count(Lead.id))
        .where(
            Lead.organization_id == principal.organization_id,
            Lead.archived_at.is_(None),
        )
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
        elif event_type == "form_abandon":
            row["form_abandons"] = int(row["form_abandons"]) + count_value
        elif event_type == "form_submit":
            row["form_submits"] = int(row["form_submits"]) + count_value
        elif event_type == "call_click":
            row["call_clicks"] = int(row["call_clicks"]) + count_value

    lead_rows = db.execute(
        select(Lead.source, func.count(Lead.id))
        .where(
            Lead.organization_id == principal.organization_id,
            Lead.archived_at.is_(None),
        )
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
            form_abandons=int(row["form_abandons"]),
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
            "form_abandons": 0,
            "form_submits": 0,
            "call_clicks": 0,
            "leads_created": 0,
        }
    return source_rows[key]


def count_scalar(db: Session, statement: Any) -> int:
    return int(db.scalar(statement) or 0)


def get_scoped_lead(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    *,
    include_archived: bool = False,
) -> Lead | None:
    filters = [
        Lead.organization_id == principal.organization_id,
        Lead.id == lead_id,
    ]
    if not include_archived:
        filters.append(Lead.archived_at.is_(None))
    if (
        PermissionKeys.VIEW_LEADS not in principal.permission_keys
        and PermissionKeys.EDIT_LEADS not in principal.permission_keys
    ):
        filters.append(Lead.assigned_user_id == principal.user_id)
    return db.scalar(select(Lead).where(*filters))


def archive_lead(db: Session, principal: Principal, lead_id: UUID) -> LeadRead | None:
    lead = get_scoped_lead(db, principal, lead_id, include_archived=True)
    if lead is None:
        return None
    if lead.archived_at is not None:
        return lead_to_read(db, lead)

    archived_at = datetime.now(UTC)
    lead.archived_at = archived_at
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            event_type="lead.archived",
            summary="Lead archived.",
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="lead.archive",
            entity_type="lead",
            entity_id=lead.id,
            previous_value={"archived_at": None},
            new_value={"archived_at": archived_at.isoformat()},
            reason="Archived from the operating system",
        )
    )
    db.commit()
    db.refresh(lead)
    return lead_to_read(db, lead)


def restore_lead(db: Session, principal: Principal, lead_id: UUID) -> LeadRead | None:
    lead = get_scoped_lead(db, principal, lead_id, include_archived=True)
    if lead is None:
        return None
    if lead.archived_at is None:
        return lead_to_read(db, lead)

    previous_archived_at = lead.archived_at
    lead.archived_at = None
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            event_type="lead.restored",
            summary="Lead restored from archive.",
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="lead.restore",
            entity_type="lead",
            entity_id=lead.id,
            previous_value={"archived_at": previous_archived_at.isoformat()},
            new_value={"archived_at": None},
            reason="Restored from the operating system archive",
        )
    )
    db.commit()
    db.refresh(lead)
    return lead_to_read(db, lead)


def permanently_delete_lead(db: Session, principal: Principal, lead_id: UUID) -> bool:
    lead = get_scoped_lead(db, principal, lead_id, include_archived=True)
    if lead is None:
        return False
    if lead.archived_at is None:
        raise ValueError("Archive the lead before permanently deleting it.")

    contact_id = lead.contact_id
    property_id = lead.property_id
    deal_ids = list(db.scalars(select(Deal.id).where(Deal.lead_id == lead.id)))
    transaction_ids = list(db.scalars(select(Transaction.id).where(Transaction.lead_id == lead.id)))
    offer_plan_ids = list(
        db.scalars(
            select(OfferNegotiationPlan.id).where(OfferNegotiationPlan.lead_id == lead.id)
        )
    )

    finance_filter = [RevenueRecord.lead_id == lead.id]
    deduction_filter = [DealDeduction.lead_id == lead.id]
    if deal_ids:
        finance_filter.append(RevenueRecord.deal_id.in_(deal_ids))
        deduction_filter.append(DealDeduction.deal_id.in_(deal_ids))
    if transaction_ids:
        finance_filter.append(RevenueRecord.transaction_id.in_(transaction_ids))
        deduction_filter.append(DealDeduction.transaction_id.in_(transaction_ids))

    db.execute(
        update(RevenueRecord)
        .where(or_(*finance_filter))
        .values(lead_id=None, deal_id=None, transaction_id=None)
    )
    db.execute(
        update(DealDeduction)
        .where(or_(*deduction_filter))
        .values(lead_id=None, deal_id=None, transaction_id=None)
    )
    for model in (Task, ConversionEvent, OfflineConversionExport, AiRunLog):
        db.execute(update(model).where(model.lead_id == lead.id).values(lead_id=None))

    if transaction_ids:
        disposition_case_ids = list(
            db.scalars(
                select(DispositionCase.id).where(
                    DispositionCase.transaction_id.in_(transaction_ids)
                )
            )
        )
        if disposition_case_ids:
            reconciliation_ids = list(
                db.scalars(
                    select(DealReconciliation.id).where(
                        DealReconciliation.disposition_case_id.in_(disposition_case_ids)
                    )
                )
            )
            if reconciliation_ids:
                db.execute(
                    delete(DealPayout).where(
                        DealPayout.deal_reconciliation_id.in_(reconciliation_ids)
                    )
                )
                db.execute(
                    delete(DealReconciliation).where(
                        DealReconciliation.id.in_(reconciliation_ids)
                    )
                )
            for disposition_model in (
                BuyerEngagement,
                DispositionCampaign,
                DispositionMatch,
            ):
                db.execute(
                    delete(disposition_model).where(
                        disposition_model.disposition_case_id.in_(disposition_case_ids)
                    )
                )
            db.execute(
                delete(DispositionCase).where(
                    DispositionCase.id.in_(disposition_case_ids)
                )
            )
        package_ids = list(
            db.scalars(
                select(ContractPackage.id).where(
                    ContractPackage.transaction_id.in_(transaction_ids)
                )
            )
        )
        recommendation_ids = list(
            db.scalars(
                select(TransactionCopilotRecommendation.id).where(
                    TransactionCopilotRecommendation.transaction_id.in_(
                        transaction_ids
                    )
                )
            )
        )
        if recommendation_ids:
            db.execute(
                delete(TransactionCopilotReview).where(
                    TransactionCopilotReview.recommendation_id.in_(
                        recommendation_ids
                    )
                )
            )
            db.execute(
                delete(TransactionCopilotRecommendation).where(
                    TransactionCopilotRecommendation.id.in_(
                        recommendation_ids
                    )
                )
            )
        db.execute(
            update(TransactionChecklistItem)
            .where(TransactionChecklistItem.transaction_id.in_(transaction_ids))
            .values(evidence_document_id=None, dependency_item_id=None)
        )
        db.execute(
            delete(TransactionChecklistItem).where(
                TransactionChecklistItem.transaction_id.in_(transaction_ids)
            )
        )
        db.execute(
            delete(TransactionDocumentFact).where(
                TransactionDocumentFact.transaction_id.in_(transaction_ids)
            )
        )
        db.execute(
            delete(TransactionDocument).where(
                TransactionDocument.transaction_id.in_(transaction_ids)
            )
        )
        db.execute(
            delete(TransactionParty).where(
                TransactionParty.transaction_id.in_(transaction_ids)
            )
        )
        db.execute(
            delete(TransactionEvent).where(
                TransactionEvent.transaction_id.in_(transaction_ids)
            )
        )
        if package_ids:
            db.execute(
                update(ContractPackage)
                .where(ContractPackage.id.in_(package_ids))
                .values(approval_request_id=None)
            )
            db.execute(
                delete(ApprovalRequest).where(
                    ApprovalRequest.organization_id == principal.organization_id,
                    ApprovalRequest.entity_type == "contract_package",
                    ApprovalRequest.entity_id.in_(package_ids),
                )
            )
            db.execute(delete(ContractPackage).where(ContractPackage.id.in_(package_ids)))
    if offer_plan_ids:
        db.execute(
            delete(OfferNegotiationPlan).where(OfferNegotiationPlan.id.in_(offer_plan_ids))
        )
        db.execute(
            delete(ApprovalRequest).where(
                ApprovalRequest.organization_id == principal.organization_id,
                ApprovalRequest.entity_type == "offer_negotiation_plan",
                ApprovalRequest.entity_id.in_(offer_plan_ids),
            )
        )
    db.execute(delete(BuyerOffer).where(BuyerOffer.lead_id == lead.id))
    db.execute(delete(RoleCredit).where(RoleCredit.lead_id == lead.id))
    for deletion_model in (
        UnderwritingCalibrationCase,
        UnderwritingMarketAnalysis,
        RepairEstimate,
        Transaction,
        Deal,
        UnderwritingVersion,
        Appointment,
        CommunicationRecord,
        AttributionTouch,
        LeadFormSubmission,
    ):
        db.execute(delete(deletion_model).where(deletion_model.lead_id == lead.id))
    conversation_ids = list(
        db.scalars(select(Conversation.id).where(Conversation.lead_id == lead.id))
    )
    if conversation_ids:
        db.execute(
            delete(ConversationAssignmentEvent).where(
                ConversationAssignmentEvent.conversation_id.in_(conversation_ids)
            )
        )
        db.execute(
            delete(ConversationWatcher).where(
                ConversationWatcher.conversation_id.in_(conversation_ids)
            )
        )
        db.execute(delete(Conversation).where(Conversation.id.in_(conversation_ids)))
    db.execute(
        delete(ApprovalRequest).where(
            ApprovalRequest.organization_id == principal.organization_id,
            ApprovalRequest.entity_type == "lead",
            ApprovalRequest.entity_id == lead.id,
        )
    )
    db.execute(
        delete(ActivityEvent).where(
            ActivityEvent.organization_id == principal.organization_id,
            ActivityEvent.entity_type == "lead",
            ActivityEvent.entity_id == lead.id,
        )
    )
    db.delete(lead)
    db.flush()

    if db.scalar(select(func.count(Lead.id)).where(Lead.contact_id == contact_id)) == 0:
        db.execute(delete(ConsentRecord).where(ConsentRecord.contact_id == contact_id))
        db.execute(delete(ContactMethod).where(ContactMethod.contact_id == contact_id))
        contact = db.get(Contact, contact_id)
        if contact is not None:
            db.delete(contact)
    if db.scalar(select(func.count(Lead.id)).where(Lead.property_id == property_id)) == 0:
        property_record = db.get(Property, property_id)
        if property_record is not None:
            db.delete(property_record)

    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="lead.delete_permanently",
            entity_type="lead",
            entity_id=lead_id,
            previous_value={"archived_at": lead.archived_at.isoformat()},
            new_value=None,
            reason="Permanently deleted from the operating system archive",
        )
    )
    db.commit()
    return True


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


def update_nullable_raw_value(
    previous_values: dict[str, Any],
    new_values: dict[str, Any],
    target: Any,
    field_name: str,
    value: Any,
    provided_fields: set[str],
) -> None:
    if field_name not in provided_fields:
        return
    current_value = getattr(target, field_name)
    if current_value == value:
        return
    previous_values[field_name] = serialize_audit_value(current_value)
    new_values[field_name] = serialize_audit_value(value)
    setattr(target, field_name, value)


def serialize_audit_value(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def validate_money_range(label: str, low_cents: int | None, high_cents: int | None) -> None:
    if low_cents is not None and high_cents is not None and low_cents > high_cents:
        raise ValueError(f"{label} low value cannot be greater than high value.")


def default_transaction_checklist_specs() -> tuple[tuple[str, str, str, str], ...]:
    return (
        (
            "contract_approved",
            "contract",
            "Manager approves contract package",
            "Verify seller, entity, price, deadlines, and special terms.",
        ),
        (
            "contract_executed",
            "contract",
            "Record executed purchase agreement",
            "Upload the signed agreement and record execution.",
        ),
        (
            "earnest_money",
            "funds",
            "Confirm earnest money deposited",
            "Record due and paid dates and attach receipt evidence.",
        ),
        (
            "open_title",
            "title",
            "Open file with closing attorney",
            "Add the closing attorney and confirm file intake.",
        ),
        (
            "seller_documents",
            "title",
            "Collect disclosures and payoff details",
            "Track seller documents, liens, mortgage payoff, and title requests.",
        ),
        (
            "due_diligence",
            "deadlines",
            "Complete due diligence",
            "Resolve inspection issues before the contractual deadline.",
        ),
        (
            "assignment",
            "disposition",
            "Confirm buyer or assignment plan",
            "Attach buyer approval, proof of funds, and assignment documents when applicable.",
        ),
        (
            "closing_confirmed",
            "closing",
            "Confirm closing package and date",
            "Confirm parties, settlement statement, signing, and funding instructions.",
        ),
    )


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


def sync_lead_contact_methods(
    db: Session,
    principal: Principal,
    contact: Contact,
    methods: list[LeadContactMethodUpdate],
    previous_values: dict[str, Any],
    new_values: dict[str, Any],
) -> bool:
    existing_methods = db.scalars(
        select(ContactMethod)
        .where(
            ContactMethod.organization_id == principal.organization_id,
            ContactMethod.contact_id == contact.id,
            ContactMethod.method_type.in_(("phone", "email")),
        )
        .order_by(ContactMethod.method_type.asc(), ContactMethod.is_primary.desc())
    ).all()
    existing_by_id = {method.id: method for method in existing_methods}
    normalized: list[dict[str, Any]] = []
    seen_ids: set[UUID] = set()
    seen_values: set[tuple[str, str]] = set()
    for item in methods:
        cleaned_value = item.value.strip()
        normalized_value = (
            normalize_email(cleaned_value)
            if item.method_type == "email"
            else normalize_phone(cleaned_value)
        )
        if item.method_type == "email" and (
            "@" not in normalized_value or normalized_value.startswith("@")
        ):
            raise ValueError(f"Enter a valid email address: {cleaned_value}")
        if item.method_type == "phone" and len(normalized_value) < 10:
            raise ValueError(f"Enter a valid phone number: {cleaned_value}")
        key = (item.method_type, normalized_value)
        if key in seen_values:
            raise ValueError(f"Remove the duplicate {item.method_type}: {cleaned_value}")
        seen_values.add(key)
        if item.id is not None:
            if item.id in seen_ids:
                raise ValueError("A contact method cannot be submitted more than once.")
            existing = existing_by_id.get(item.id)
            if existing is None:
                raise ValueError("A contact method does not belong to this lead.")
            seen_ids.add(item.id)
        normalized.append(
            {
                "id": item.id,
                "method_type": item.method_type,
                "value": cleaned_value,
                "normalized_value": normalized_value,
                "is_primary": item.is_primary,
            }
        )
    if not normalized:
        raise ValueError("Keep at least one phone number or email address on the lead.")
    for method_type in ("phone", "email"):
        group = [item for item in normalized if item["method_type"] == method_type]
        if not group:
            continue
        # Older intake paths may have left multiple primary rows. Retain the
        # first selected method so an unrelated lead edit repairs the record.
        primary = next((item for item in group if item["is_primary"]), group[0])
        for item in group:
            item["is_primary"] = item is primary

    before = sorted(
        (contact_method_audit_value(method) for method in existing_methods),
        key=contact_method_audit_sort_key,
    )
    submitted_ids = {item["id"] for item in normalized if item["id"] is not None}
    for method in existing_methods:
        if method.id not in submitted_ids:
            db.delete(method)
    for item in normalized:
        method = existing_by_id.get(item["id"]) if item["id"] is not None else None
        if method is None:
            method = ContactMethod(
                organization_id=principal.organization_id,
                contact_id=contact.id,
                method_type=item["method_type"],
                value=item["value"],
                normalized_value=item["normalized_value"],
                is_primary=item["is_primary"],
            )
            db.add(method)
        else:
            method.method_type = item["method_type"]
            method.value = item["value"]
            method.normalized_value = item["normalized_value"]
            method.is_primary = item["is_primary"]
    after = sorted(
        (
            {
                "method_type": item["method_type"],
                "value": item["value"],
                "is_primary": item["is_primary"],
            }
            for item in normalized
        ),
        key=contact_method_audit_sort_key,
    )
    if before == after:
        return False
    previous_values["contact_methods"] = before
    new_values["contact_methods"] = after
    return True


def contact_method_audit_value(method: ContactMethod) -> dict[str, Any]:
    return {
        "method_type": method.method_type,
        "value": method.value,
        "is_primary": method.is_primary,
    }


def contact_method_audit_sort_key(item: dict[str, Any]) -> tuple[str, bool, str]:
    return (
        str(item["method_type"]),
        not bool(item["is_primary"]),
        str(item["value"]).lower(),
    )


def update_lead_assignment(
    db: Session,
    principal: Principal,
    lead: Lead,
    contact: Contact,
    assigned_user_id: UUID | None,
    previous_values: dict[str, Any],
    new_values: dict[str, Any],
    *,
    reason: str | None,
) -> bool:
    if lead.assigned_user_id == assigned_user_id:
        return False
    assignee = None
    if assigned_user_id is not None:
        assignee = db.scalar(
            select(User).where(
                User.id == assigned_user_id,
                User.organization_id == principal.organization_id,
                User.is_active.is_(True),
            )
        )
        if assignee is None:
            raise ValueError("Lead owner must be an active Stonegate user.")
    previous_assigned_user_id = lead.assigned_user_id
    lead.assigned_user_id = assignee.id if assignee else None
    contact.assigned_user_id = lead.assigned_user_id
    previous_values["assigned_user_id"] = (
        str(previous_assigned_user_id) if previous_assigned_user_id else None
    )
    new_values["assigned_user_id"] = str(lead.assigned_user_id) if lead.assigned_user_id else None

    conversation = db.scalar(
        select(Conversation).where(
            Conversation.organization_id == principal.organization_id,
            Conversation.lead_id == lead.id,
        )
    )
    if conversation is not None:
        previous_conversation_owner = conversation.assigned_user_id
        conversation.assigned_user_id = lead.assigned_user_id
        db.add(
            ConversationAssignmentEvent(
                organization_id=principal.organization_id,
                conversation_id=conversation.id,
                lead_id=lead.id,
                actor_user_id=principal.user_id,
                previous_assigned_user_id=previous_conversation_owner,
                assigned_user_id=lead.assigned_user_id,
                previous_queue_key=conversation.queue_key,
                queue_key=conversation.queue_key,
                reason=reason or "Lead owner updated from the lead record.",
                created_at=datetime.now(UTC),
            )
        )
        if assignee is not None:
            watcher = db.scalar(
                select(ConversationWatcher).where(
                    ConversationWatcher.organization_id == principal.organization_id,
                    ConversationWatcher.conversation_id == conversation.id,
                    ConversationWatcher.user_id == assignee.id,
                )
            )
            if watcher is None:
                db.add(
                    ConversationWatcher(
                        organization_id=principal.organization_id,
                        conversation_id=conversation.id,
                        user_id=assignee.id,
                        source="lead_edit",
                        notification_level="all",
                        is_muted=False,
                    )
                )
    for task in db.scalars(
        select(Task).where(
            Task.organization_id == principal.organization_id,
            Task.lead_id == lead.id,
            Task.status.in_(("open", "in_progress")),
        )
    ):
        task.responsible_user_id = lead.assigned_user_id
    for appointment in db.scalars(
        select(Appointment).where(
            Appointment.organization_id == principal.organization_id,
            Appointment.lead_id == lead.id,
            Appointment.status.in_(("scheduled", "rescheduled")),
        )
    ):
        appointment.owner_user_id = lead.assigned_user_id
    return True


def normalize_blank(value: str) -> str | None:
    cleaned_value = value.strip()
    return cleaned_value or None


def normalize_email(value: str) -> str:
    return value.strip().lower()


def normalize_phone(value: str) -> str:
    return "".join(character for character in value if character.isdigit())


def format_property_address(property_record: Property) -> str:
    return (
        f"{property_record.street_address}, {property_record.city}, "
        f"{property_record.state} {property_record.postal_code}"
    )


def dollars_to_cents(value: int | None) -> int | None:
    return value * 100 if value is not None else None


def rentcast_comp_to_read(comp: dict[str, Any]) -> MarketComparableRead:
    return MarketComparableRead(
        provider_id=string_or_none(comp.get("id")),
        formatted_address=string_or_none(comp.get("formattedAddress")),
        status=string_or_none(comp.get("status")),
        listing_type=string_or_none(comp.get("listingType")),
        property_type=string_or_none(comp.get("propertyType")),
        price_cents=dollars_to_cents(optional_int(comp.get("price"))),
        bedrooms=optional_float(comp.get("bedrooms")),
        bathrooms=optional_float(comp.get("bathrooms")),
        square_footage=optional_int(comp.get("squareFootage")),
        year_built=optional_int(comp.get("yearBuilt")),
        distance_miles=optional_float(comp.get("distance")),
        days_old=optional_int(comp.get("daysOld")),
        correlation=optional_float(comp.get("correlation")),
        listed_date=string_or_none(comp.get("listedDate")),
        removed_date=string_or_none(comp.get("removedDate")),
        last_seen_date=string_or_none(comp.get("lastSeenDate")),
    )


def analyze_rentcast_comps(
    comps: list[dict[str, Any]],
) -> tuple[list[MarketAnalysisCompRead], list[MarketAnalysisCompRead]]:
    scored_comps = [score_rentcast_comp(comp) for comp in comps]
    eligible = [
        comp
        for comp in scored_comps
        if comp.price_cents is not None
        and comp.selection_reason != "Active listing; context only."
    ]
    selected = sorted(
        [comp for comp in eligible if comp.score >= 55],
        key=lambda comp: comp.score,
        reverse=True,
    )[:5]
    if len(selected) < 3:
        selected_ids = {comp.provider_id for comp in selected}
        backfill = [
            comp
            for comp in sorted(eligible, key=lambda comp: comp.score, reverse=True)
            if comp.provider_id not in selected_ids
        ]
        selected = [*selected, *backfill[: 3 - len(selected)]]

    selected_ids = {comp.provider_id for comp in selected}
    selected_addresses = {comp.formatted_address for comp in selected}
    rejected = [
        comp
        for comp in scored_comps
        if comp.provider_id not in selected_ids or comp.formatted_address not in selected_addresses
    ]
    selected = [
        comp.model_copy(update={"selection_status": "selected"})
        for comp in selected
    ]
    rejected = [
        comp.model_copy(update={"selection_status": "rejected"})
        for comp in rejected
    ]
    return selected, rejected


def score_rentcast_comp(comp: dict[str, Any]) -> MarketAnalysisCompRead:
    comparable = rentcast_comp_to_read(comp)
    score = 50
    reasons: list[str] = []
    status = (comparable.status or "").strip().lower()
    if comparable.price_cents is None:
        return MarketAnalysisCompRead(
            **comparable.model_dump(),
            selection_status="rejected",
            selection_reason="Missing sale/list price.",
            score=0,
        )
    if status == "active":
        return MarketAnalysisCompRead(
            **comparable.model_dump(),
            selection_status="rejected",
            selection_reason="Active listing; context only.",
            score=25,
        )

    if comparable.correlation is not None:
        correlation = (
            comparable.correlation
            if comparable.correlation <= 1
            else comparable.correlation / 100
        )
        score += round(max(0, min(correlation, 1)) * 25)
        reasons.append("provider similarity score")
    if comparable.distance_miles is not None:
        if comparable.distance_miles <= 1:
            score += 15
            reasons.append("within 1 mile")
        elif comparable.distance_miles <= 3:
            score += 8
            reasons.append("within 3 miles")
        else:
            score -= 10
            reasons.append("farther than 3 miles")
    if comparable.days_old is not None:
        if comparable.days_old <= 90:
            score += 12
            reasons.append("sold/listed within 90 days")
        elif comparable.days_old <= 180:
            score += 6
            reasons.append("sold/listed within 180 days")
        elif comparable.days_old > 365:
            score -= 12
            reasons.append("older than 12 months")
    if comparable.property_type:
        score += 5

    bounded_score = max(0, min(score, 100))
    reason = ", ".join(reasons) if reasons else "usable comp with limited similarity metadata"
    return MarketAnalysisCompRead(
        **comparable.model_dump(),
        selection_status="candidate",
        selection_reason=reason,
        score=bounded_score,
    )


def calculate_arv_range(
    *,
    estimate: RentCastValueEstimate,
    selected_comps: list[MarketAnalysisCompRead],
    subject_square_feet: int | None,
) -> tuple[int | None, int | None]:
    comp_prices = [comp.price_cents for comp in selected_comps if comp.price_cents is not None]
    if len(comp_prices) >= 3:
        ppsf_values = [
            comp.price_cents / comp.square_footage
            for comp in selected_comps
            if comp.price_cents is not None
            and comp.square_footage is not None
            and comp.square_footage > 0
        ]
        if subject_square_feet and len(ppsf_values) >= 3:
            low = round(percentile(ppsf_values, 0.25) * subject_square_feet)
            high = round(percentile(ppsf_values, 0.75) * subject_square_feet)
            return normalize_money_range(low, high)
        return normalize_money_range(
            round(percentile(comp_prices, 0.25)),
            round(percentile(comp_prices, 0.75)),
        )

    estimate_low = dollars_to_cents(estimate.price_range_low)
    estimate_high = dollars_to_cents(estimate.price_range_high)
    if estimate_low is not None and estimate_high is not None:
        return normalize_money_range(estimate_low, estimate_high)
    estimate_cents = dollars_to_cents(estimate.price)
    if estimate_cents is not None:
        return normalize_money_range(round(estimate_cents * 0.92), round(estimate_cents * 1.08))
    return None, None


def estimate_repair_range(condition: str | None, square_feet: int | None) -> tuple[int, int]:
    normalized = (condition or "").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in {"new", "turnkey", "excellent", "good", "cosmetic"}:
        low_per_sqft, high_per_sqft = 15, 25
        fallback = (15_000_00, 30_000_00)
    elif normalized in {"major_repairs", "heavy_repairs", "full_gut", "fire_damage"}:
        low_per_sqft, high_per_sqft = 60, 90
        fallback = (70_000_00, 120_000_00)
    elif normalized in {"tear_down", "structural", "foundation"}:
        low_per_sqft, high_per_sqft = 100, 140
        fallback = (120_000_00, 200_000_00)
    else:
        low_per_sqft, high_per_sqft = 30, 50
        fallback = (35_000_00, 60_000_00)

    if square_feet and square_feet > 0:
        return round(square_feet * low_per_sqft * 100), round(square_feet * high_per_sqft * 100)
    return fallback


def calculate_mao(
    *,
    arv_cents: int | None,
    percentage: float,
    repair_cents: int,
    assignment_fee_cents: int,
) -> int | None:
    if arv_cents is None:
        return None
    return max(0, round((arv_cents * percentage) - repair_cents - assignment_fee_cents))


def calculate_confidence_score(
    *,
    selected_comps: list[MarketAnalysisCompRead],
    arv_low_cents: int | None,
    arv_high_cents: int | None,
) -> int:
    if arv_low_cents is None or arv_high_cents is None:
        return 20
    base = 35 + min(len(selected_comps), 5) * 8
    average_comp_score = (
        sum(comp.score for comp in selected_comps) / len(selected_comps)
        if selected_comps
        else 0
    )
    spread_penalty = 0
    if arv_high_cents > 0:
        spread = (arv_high_cents - arv_low_cents) / arv_high_cents
        if spread > 0.25:
            spread_penalty = 15
        elif spread > 0.15:
            spread_penalty = 7
    return max(20, min(95, round(base + (average_comp_score * 0.25) - spread_penalty)))


def build_market_analysis_notes(
    *,
    selected_count: int,
    rejected_count: int,
    confidence_score: int,
    offer_low_percentage: float,
    offer_high_percentage: float,
    assignment_fee_cents: int,
) -> str:
    return (
        "RentCast comp pull created a draft underwriting version. "
        f"Selected {selected_count} comps and rejected {rejected_count}. "
        f"Confidence: {confidence_score}%. "
        f"Offer screen: {round(offer_low_percentage * 100)}-"
        f"{round(offer_high_percentage * 100)}% of ARV minus repairs and "
        f"{format_cents_for_note(assignment_fee_cents)} assignment fee. "
        "Review comps, repairs, and seller context before approving."
    )


def build_market_analysis_result_notes(
    result: UnderwritingV2Result,
    *,
    report_stage: str,
    methodology_version: str,
) -> str:
    review_status = (
        "Manual review required."
        if result.manual_review_required
        else "Evidence threshold met; human approval still required."
    )
    method_summary = (
        "Stonegate Valuation used screened closed sales, locally supported property "
        "adjustments, and explicit buyer economics. "
        if methodology_version == "v3"
        else (
            "The V2.2 rollback method used recorded sales, price-per-square-foot "
            "screening, subject-size value indicators, and explicit buyer economics. "
        )
    )
    return method_summary + (
        f"Selected {len(result.selected_comps)} recorded comps. "
        f"Confidence: {result.confidence_score}%. "
        f"Seller ceiling: {format_cents_for_note(result.seller_contract_ceiling_cents)}. "
        f"Opening recommendation: "
        f"{format_cents_for_note(result.recommended_opening_offer_cents)}. "
        f"Report stage: {report_stage.replace('_', ' ')}. "
        f"{review_status}"
    )


def market_analysis_to_read(analysis: UnderwritingMarketAnalysis) -> LeadMarketAnalysisRead:
    metadata = analysis.analysis_metadata or {}
    return LeadMarketAnalysisRead(
        id=analysis.id,
        lead_id=analysis.lead_id,
        property_id=analysis.property_id,
        underwriting_version_id=analysis.underwriting_version_id,
        provider=analysis.provider,
        requested_address=analysis.requested_address,
        subject_property=analysis.subject_property,
        estimated_value_cents=analysis.estimated_value_cents,
        estimated_value_low_cents=analysis.estimated_value_low_cents,
        estimated_value_high_cents=analysis.estimated_value_high_cents,
        arv_low_cents=analysis.arv_low_cents,
        arv_high_cents=analysis.arv_high_cents,
        repair_low_cents=analysis.repair_low_cents,
        repair_high_cents=analysis.repair_high_cents,
        mao_low_cents=analysis.mao_low_cents,
        mao_high_cents=analysis.mao_high_cents,
        recommended_offer_cents=analysis.recommended_offer_cents,
        assignment_fee_cents=analysis.assignment_fee_cents,
        offer_low_percentage=analysis.offer_low_percentage,
        offer_high_percentage=analysis.offer_high_percentage,
        confidence_score=analysis.confidence_score,
        selected_comps=[
            MarketAnalysisCompRead.model_validate(comp) for comp in analysis.selected_comps
        ],
        rejected_comps=[
            MarketAnalysisCompRead.model_validate(comp) for comp in analysis.rejected_comps
        ],
        source_note=(
            (
                "Stonegate Valuation uses screened closed sales and applies only locally "
                "supported property adjustments. Unsupported differences remain visible for "
                "review, and all offer terms require human approval."
            )
            if metadata.get("methodology_version") == METHODOLOGY_VERSION
            else (
                "Saved RentCast sales-comparison analysis. Draft numbers are screening guidance "
                "only and require human ARV/offer approval."
            )
        ),
        created_at=analysis.created_at,
        methodology_version=string_or_none(metadata.get("methodology_version")) or "v1",
        as_is_value_low_cents=optional_int(metadata.get("as_is_value_low_cents")),
        as_is_value_cents=optional_int(metadata.get("as_is_value_cents")),
        as_is_value_high_cents=optional_int(metadata.get("as_is_value_high_cents")),
        arv_point_cents=optional_int(metadata.get("arv_point_cents")),
        conservative_arv_cents=optional_int(metadata.get("conservative_arv_cents")),
        base_rehab_cents=optional_int(metadata.get("base_rehab_cents")),
        rehab_contingency_percentage=optional_int(
            metadata.get("rehab_contingency_percentage")
        ),
        total_rehab_cents=optional_int(metadata.get("total_rehab_cents")),
        repair_scenario=(
            dict_value(metadata.get("repair_scenario"))
            if isinstance(metadata.get("repair_scenario"), dict)
            else None
        ),
        flip_buyer_max_cents=optional_int(metadata.get("flip_buyer_max_cents")),
        rental_buyer_max_cents=optional_int(metadata.get("rental_buyer_max_cents")),
        recommended_disposition_cents=optional_int(
            metadata.get("recommended_disposition_cents")
        ),
        seller_contract_ceiling_cents=optional_int(
            metadata.get("seller_contract_ceiling_cents")
        ),
        transaction_reserve_cents=optional_int(metadata.get("transaction_reserve_cents")),
        monthly_rent_cents=optional_int(metadata.get("monthly_rent_cents")),
        manual_review_required=bool(metadata.get("human_review_required", True)),
        confidence_tier=string_or_none(metadata.get("confidence_tier")) or "insufficient",
        confidence_factors=list_of_dicts(metadata.get("confidence_factors")),
        address_evidence=dict_value(metadata.get("address_evidence")),
        secondary_evidence=dict_value(metadata.get("secondary_evidence")),
        review_reasons=string_list(metadata.get("review_reasons")),
        data_disagreements=string_list(metadata.get("data_disagreements")),
        assumptions=dict_value(metadata.get("assumptions")),
        report_stage=string_or_none(metadata.get("report_stage")) or "preliminary",
        pre_meeting_inputs=(
            UnderwritingPreMeetingInputsRead.model_validate(
                metadata.get("pre_meeting_inputs")
            )
            if isinstance(metadata.get("pre_meeting_inputs"), dict)
            else None
        ),
        comp_review=(
            UnderwritingCompReviewSummaryRead.model_validate(metadata.get("comp_review"))
            if isinstance(metadata.get("comp_review"), dict)
            else None
        ),
        subject_square_feet=optional_int(metadata.get("subject_square_feet")),
        methodology_control=(
            UnderwritingMethodologyControlRead.model_validate(
                metadata.get("methodology_control")
            )
            if isinstance(metadata.get("methodology_control"), dict)
            else None
        ),
        execution_metrics=(
            UnderwritingExecutionMetricsRead.model_validate(
                metadata.get("execution_metrics")
            )
            if isinstance(metadata.get("execution_metrics"), dict)
            else None
        ),
        comp_search_summary=(
            UnderwritingCompSearchSummaryRead.model_validate(
                metadata.get("comp_search_summary")
            )
            if isinstance(metadata.get("comp_search_summary"), dict)
            else None
        ),
        supporting_evidence=(
            UnderwritingSupportingEvidenceRead.model_validate(
                metadata.get("supporting_evidence")
            )
            if isinstance(metadata.get("supporting_evidence"), dict)
            else None
        ),
        market_adjustment=(
            dict_value(metadata.get("market_adjustment"))
            if isinstance(metadata.get("market_adjustment"), dict)
            else None
        ),
        adjustment_shadow=(
            dict_value(metadata.get("adjustment_shadow"))
            if isinstance(metadata.get("adjustment_shadow"), dict)
            else None
        ),
        manual_comp_ids=uuid_list(metadata.get("manual_comp_ids")),
    )


def count_comp_review_overrides(
    source: UnderwritingMarketAnalysis | None,
    decisions: Sequence[Any],
) -> int:
    if source is None or not decisions:
        return 0
    source_included = {
        string_or_none(comp.get("provider_id"))
        or string_or_none(comp.get("formatted_address"))
        for comp in source.selected_comps
        if isinstance(comp, dict)
    }
    source_included.discard(None)
    return sum(
        decision.included != (decision.comp_key in source_included)
        for decision in decisions
    )


def add_manual_evidence_to_search_summary(
    summary: dict[str, Any],
    *,
    manual_sale_count: int,
    duplicate_count: int,
    selected_comps: Sequence[MarketAnalysisCompRead],
    rejected_comps: Sequence[MarketAnalysisCompRead],
) -> dict[str, Any]:
    updated = dict(summary)
    accepted_count = max(0, manual_sale_count - duplicate_count)
    updated["manual_verified_sale_count"] = accepted_count
    updated["manual_duplicate_count"] = duplicate_count
    if not manual_sale_count:
        return updated

    manual_comps = [
        comp
        for comp in (*selected_comps, *rejected_comps)
        if comp.verification_status == "manual_verified"
    ]
    usable_manual_count = sum(comp.score > 0 for comp in manual_comps)
    usable_closed_sale_count = sum(
        comp.score > 0 for comp in (*selected_comps, *rejected_comps)
    )
    minimum = optional_int(updated.get("minimum_closed_sales")) or 3
    was_sufficient = bool(updated.get("sufficient_closed_sales"))
    is_sufficient = usable_closed_sale_count >= minimum
    updated["sufficient_closed_sales"] = is_sufficient
    updated["total_unique_sales"] = (
        (optional_int(updated.get("total_unique_sales")) or 0) + accepted_count
    )
    if accepted_count and not was_sufficient:
        updated["final_level"] = "manual"
    attempts = list_of_dicts(updated.get("attempts"))
    attempts.append(
        {
            "level": "manual",
            "radius_miles": None,
            "days_old": None,
            "bedroom_tolerance": None,
            "bathroom_tolerance": None,
            "square_footage_tolerance_percentage": None,
            "year_built_tolerance_years": None,
            "returned_count": manual_sale_count,
            "unique_added_count": accepted_count,
            "duplicate_count": duplicate_count,
            "cumulative_unique_count": optional_int(updated.get("total_unique_sales")) or 0,
            "selected_count": usable_manual_count,
            "rejected_count": max(0, accepted_count - usable_manual_count),
            "same_subdivision_count": sum(
                comp.subdivision_match is True for comp in manual_comps if comp.score > 0
            ),
            "expansion_reason": (
                "Verified operator-entered sales supplemented provider closed-sale evidence."
            ),
            "provider_error": None,
        }
    )
    updated["attempts"] = attempts
    if is_sufficient:
        updated["evidence_shortage_reason"] = None
        updated["next_action"] = (
            "Review source references and condition evidence, then approve or revise the "
            "recommended closed-sale set."
        )
    else:
        updated["evidence_shortage_reason"] = (
            f"Only {usable_closed_sale_count} usable closed sale(s) remain after provider and "
            f"manual evidence screening; {minimum} are preferred."
        )
        updated["next_action"] = (
            "Add another source-verified closed sale or document the evidence shortage before "
            "approving the offer."
        )
    return updated


def add_research_evidence_to_search_summary(
    summary: dict[str, Any],
    *,
    research_sale_count: int,
    duplicate_count: int,
    source_count: int,
    selected_comps: Sequence[MarketAnalysisCompRead],
    rejected_comps: Sequence[MarketAnalysisCompRead],
) -> dict[str, Any]:
    updated = dict(summary)
    if not research_sale_count and not source_count:
        return updated
    accepted_count = max(0, research_sale_count - duplicate_count)
    research_comps = [
        comp
        for comp in (*selected_comps, *rejected_comps)
        if comp.evidence_source == "ai_web_research"
    ]
    selected_research = [
        comp for comp in research_comps if comp.selection_status != "rejected"
    ]
    updated["ai_research_sale_count"] = accepted_count
    updated["ai_research_duplicate_count"] = duplicate_count
    updated["ai_research_selected_count"] = len(selected_research)
    updated["ai_research_source_count"] = source_count
    updated["total_unique_sales"] = (
        (optional_int(updated.get("total_unique_sales")) or 0) + accepted_count
    )
    usable_closed_sale_count = len(
        [
            comp
            for comp in (*selected_comps, *rejected_comps)
            if comp.selection_status != "rejected"
        ]
    )
    minimum = optional_int(updated.get("minimum_closed_sales")) or 3
    updated["sufficient_closed_sales"] = usable_closed_sale_count >= minimum
    if selected_research:
        updated["next_action"] = (
            "Review the recommended sales and cited AI research, then approve or revise the "
            "comparable set."
        )
    if usable_closed_sale_count < minimum:
        updated["evidence_shortage_reason"] = (
            f"Stonegate found {usable_closed_sale_count} usable closed sale(s) after provider "
            "and cited public research; three are preferred for final confidence."
        )
        updated["next_action"] = (
            "Use the working range for preparation, then verify another sale before presenting "
            "a final value or approving an offer."
        )
    return updated


def legacy_comp_search_summary(
    *,
    sale_records: Sequence[dict[str, Any]],
    selected_count: int,
    rejected_count: int,
) -> dict[str, Any]:
    sufficient = selected_count >= 3
    return {
        "strategy_version": "fixed_v2.2_legacy",
        "final_level": "preferred" if sufficient else "manual",
        "sufficient_closed_sales": sufficient,
        "minimum_closed_sales": 3,
        "total_provider_results": len(sale_records),
        "total_unique_sales": len(sale_records),
        "duplicate_count": 0,
        "subject_subdivision": None,
        "same_subdivision_count": 0,
        "market_area_warning": None,
        "evidence_shortage_reason": (
            None
            if sufficient
            else (
                f"The saved fixed search contains {selected_count} usable closed sale(s); "
                "refresh market data to run the adaptive search."
            )
        ),
        "next_action": (
            "Verify comp condition and approve or revise the recommended closed-sale set."
            if sufficient
            else "Refresh market data to run adaptive closed-sale discovery."
        ),
        "attempts": [
            {
                "level": "preferred",
                "radius_miles": 1,
                "days_old": 365,
                "returned_count": len(sale_records),
                "unique_added_count": len(sale_records),
                "duplicate_count": 0,
                "cumulative_unique_count": len(sale_records),
                "selected_count": selected_count,
                "rejected_count": rejected_count,
                "same_subdivision_count": 0,
                "expansion_reason": None,
                "provider_error": None,
            }
        ],
    }


def underwriting_version_comp_snapshot(
    analysis: UnderwritingMarketAnalysis | None,
) -> list[UnderwritingVersionCompSnapshot]:
    if analysis is None:
        return []
    snapshot: list[UnderwritingVersionCompSnapshot] = []
    for index, comp in enumerate(list_of_dicts(analysis.selected_comps)):
        address = string_or_none(comp.get("formatted_address")) or "Unknown address"
        key = (
            string_or_none(comp.get("provider_id"))
            or string_or_none(comp.get("source_reference"))
            or address.lower()
            or f"comp-{index + 1}"
        )
        snapshot.append(
            UnderwritingVersionCompSnapshot(
                key=key,
                address=address,
                grade=string_or_none(comp.get("comp_grade")),
                search_level=string_or_none(comp.get("search_level")),
                condition=string_or_none(comp.get("condition_classification")),
                adjusted_value_cents=optional_int(comp.get("adjusted_value_cents")),
            )
        )
    return snapshot


def underwriting_version_repair_snapshot(
    metadata: dict[str, Any],
) -> list[UnderwritingVersionRepairSnapshot]:
    inputs = dict_value(metadata.get("pre_meeting_inputs"))
    repair_items = list_of_dicts(inputs.get("repair_items"))
    snapshot: list[UnderwritingVersionRepairSnapshot] = []
    for item in repair_items:
        category = string_or_none(item.get("category"))
        if category is None:
            continue
        snapshot.append(
            UnderwritingVersionRepairSnapshot(
                category=category,
                scope_status=(
                    string_or_none(item.get("scope_status")) or "priced_item"
                ),
                expected_cents=first_int(
                    item,
                    (
                        "estimated_cost_cents",
                        "system_expected_cents",
                        "total_cost_cents",
                    ),
                ),
                confirmation_status=string_or_none(item.get("confirmation_status")),
            )
        )
    return snapshot


def underwriting_version_adjustment_snapshot(
    metadata: dict[str, Any],
) -> UnderwritingVersionAdjustmentSnapshot | None:
    shadow = dict_value(metadata.get("market_adjustment")) or dict_value(
        metadata.get("adjustment_shadow")
    )
    if not shadow:
        return None
    rate_evidence = list_of_dicts(shadow.get("rate_evidence"))
    conclusion = dict_value(shadow.get("conclusion"))
    comparison = dict_value(shadow.get("comparison"))
    return UnderwritingVersionAdjustmentSnapshot(
        status=string_or_none(shadow.get("status")) or "unknown",
        shadow_arv_point_cents=optional_int(conclusion.get("arv_point_cents")),
        point_delta_cents=optional_int(comparison.get("point_delta_cents")),
        supported_count=sum(
            item.get("status") == "supported" for item in rate_evidence
        ),
        withheld_count=sum(
            item.get("status") != "supported" for item in rate_evidence
        ),
    )


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def uuid_list(value: Any) -> list[UUID]:
    if not isinstance(value, list):
        return []
    identifiers: list[UUID] = []
    for item in value:
        try:
            identifiers.append(UUID(str(item)))
        except (TypeError, ValueError):
            continue
    return identifiers


def list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def percentile(values: Sequence[float | int], target: float) -> float:
    sorted_values = sorted(float(value) for value in values)
    if not sorted_values:
        return 0
    index = (len(sorted_values) - 1) * target
    lower = int(index)
    upper = min(lower + 1, len(sorted_values) - 1)
    if lower == upper:
        return sorted_values[lower]
    weight = index - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def normalize_money_range(low: int | None, high: int | None) -> tuple[int | None, int | None]:
    if low is None or high is None:
        return low, high
    return (low, high) if low <= high else (high, low)


def first_int(values: dict[str, Any], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        value = optional_int(values.get(key))
        if value is not None:
            return value
    return None


def format_cents_for_note(value: int | None) -> str:
    if value is None:
        return "not supported"
    return f"${value / 100:,.0f}"


def string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def optional_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def optional_int(value: Any) -> int | None:
    float_value = optional_float(value)
    return int(round(float_value)) if float_value is not None else None


def property_fields_changed(values: dict[str, Any]) -> bool:
    property_keys = {"street_address", "city", "state", "postal_code"}
    return any(key in values for key in property_keys)


def property_validation_to_read(property_record: Property) -> PropertyValidationRead:
    metadata = property_record.address_validation_metadata or {}
    return PropertyValidationRead(
        status=property_record.address_validation_status,
        provider=property_record.address_validation_provider,
        provider_property_id=property_record.provider_property_id,
        requested_address=format_property_address(property_record),
        validated_address=property_record.validated_formatted_address,
        match_score=optional_int(metadata.get("match_score")),
        issues=string_list(metadata.get("issues")),
        facts=dict_value(metadata.get("facts")),
        validated_at=property_record.address_validated_at,
    )


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
        property_address=format_property_address(property_record),
        property_street_address=property_record.street_address,
        property_city=property_record.city,
        property_state=property_record.state,
        property_postal_code=property_record.postal_code,
        property_county=property_record.county,
        property_type=property_record.property_type,
        property_validation=property_validation_to_read(property_record),
        assigned_user_id=lead.assigned_user_id,
        assigned_user_email=assigned_user.email if assigned_user else None,
        motivation=lead.motivation,
        desired_timeline=lead.desired_timeline,
        property_condition=lead.property_condition,
        occupancy_status=lead.occupancy_status,
        asking_price=lead.asking_price,
        mortgage_balance=lead.mortgage_balance,
        appointment_status=lead.appointment_status,
        next_follow_up_at=lead.next_follow_up_at,
        primary_next_action=get_primary_next_action(
            db,
            organization_id=lead.organization_id,
            lead_id=lead.id,
        ),
        archived_at=lead.archived_at,
        created_at=lead.created_at,
    )
