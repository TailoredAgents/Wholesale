from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.domain.rbac import PermissionKeys
from app.models.foundation import (
    ActivityEvent,
    ApprovalRequest,
    AuditEvent,
    Contact,
    Lead,
    OfferNegotiationPlan,
    Role,
    RoleAssignment,
    UnderwritingMarketAnalysis,
    UnderwritingVersion,
    User,
)
from app.schemas.approvals import (
    OfferNegotiationPlanCreate,
    OfferNegotiationPlanListResponse,
    OfferNegotiationPlanRead,
)

APPROVER_ROLE_PRIORITY = {
    "owner": 0,
    "founder_operator": 1,
    "ceo": 2,
    "acquisition_manager": 3,
}


def list_offer_negotiation_plans(
    db: Session,
    principal: Principal,
    lead_id: UUID,
) -> OfferNegotiationPlanListResponse | None:
    lead = scoped_lead(db, principal, lead_id)
    if lead is None:
        return None
    plans = db.scalars(
        select(OfferNegotiationPlan)
        .where(
            OfferNegotiationPlan.organization_id == principal.organization_id,
            OfferNegotiationPlan.lead_id == lead.id,
        )
        .order_by(
            (OfferNegotiationPlan.status == "pending").desc(),
            OfferNegotiationPlan.created_at.desc(),
            OfferNegotiationPlan.id.desc(),
        )
    ).all()
    return OfferNegotiationPlanListResponse(
        items=[offer_plan_to_read(db, plan) for plan in plans],
        can_approve=PermissionKeys.APPROVE_OFFERS in principal.permission_keys,
    )


def create_offer_negotiation_plan(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    payload: OfferNegotiationPlanCreate,
) -> OfferNegotiationPlanRead | None:
    lead = scoped_lead(db, principal, lead_id)
    if lead is None:
        return None
    version = db.scalar(
        select(UnderwritingVersion).where(
            UnderwritingVersion.id == payload.underwriting_version_id,
            UnderwritingVersion.organization_id == principal.organization_id,
            UnderwritingVersion.lead_id == lead.id,
        )
    )
    if version is None:
        raise ValueError("The underwriting version was not found for this lead.")
    ceiling = version.max_offer_cents
    if ceiling is None or ceiling <= 0:
        raise ValueError("The selected underwriting version does not have a seller ceiling.")

    opening, target, stretch = negotiation_ladder(version, ceiling, payload)
    if not 0 <= opening <= target <= stretch <= ceiling:
        raise ValueError(
            "Negotiation amounts must follow opening <= target <= stretch <= seller ceiling."
        )

    now = datetime.now(UTC)
    superseded_count = supersede_pending_offer_plans(db, lead, principal, now)
    metadata = version.underwriting_metadata or {}
    analysis = db.scalar(
        select(UnderwritingMarketAnalysis).where(
            UnderwritingMarketAnalysis.organization_id == principal.organization_id,
            UnderwritingMarketAnalysis.underwriting_version_id == version.id,
        )
    )
    snapshot = {
        "underwriting_version_id": str(version.id),
        "underwriting_version_number": version.version_number,
        "underwriting_version_created_at": version.created_at.isoformat(),
        "market_analysis_id": str(analysis.id) if analysis else None,
        "methodology_version": metadata.get("methodology_version"),
        "report_stage": metadata.get("report_stage"),
        "repair_estimate_id": metadata.get("repair_estimate_id"),
        "source": version.source,
        "status_at_request": version.status,
        "arv_low_cents": version.arv_low_cents,
        "arv_point_cents": optional_int(metadata.get("arv_point_cents")),
        "arv_high_cents": version.arv_high_cents,
        "total_rehab_cents": optional_int(metadata.get("total_rehab_cents"))
        or version.repair_high_cents,
        "disposition_cents": optional_int(metadata.get("recommended_disposition_cents")),
        "seller_ceiling_cents": ceiling,
        "recommended_opening_offer_cents": version.recommended_offer_cents,
    }
    plan = OfferNegotiationPlan(
        organization_id=principal.organization_id,
        lead_id=lead.id,
        property_id=lead.property_id,
        underwriting_version_id=version.id,
        market_analysis_id=analysis.id if analysis else None,
        created_by_user_id=principal.user_id,
        status="pending",
        seller_asking_price_cents=payload.seller_asking_price_cents,
        arv_low_cents=version.arv_low_cents,
        arv_point_cents=optional_int(metadata.get("arv_point_cents")),
        arv_high_cents=version.arv_high_cents,
        total_rehab_cents=(
            optional_int(metadata.get("total_rehab_cents")) or version.repair_high_cents
        ),
        disposition_cents=optional_int(metadata.get("recommended_disposition_cents")),
        opening_offer_cents=opening,
        target_contract_cents=target,
        stretch_contract_cents=stretch,
        seller_ceiling_cents=ceiling,
        seller_context=clean_optional(payload.seller_context),
        rationale=payload.rationale.strip(),
        source_snapshot=snapshot,
    )
    db.add(plan)
    db.flush()

    contact = db.get(Contact, lead.contact_id)
    seller_name = contact.preferred_name or contact.legal_name if contact else "Seller"
    approval = ApprovalRequest(
        organization_id=principal.organization_id,
        requested_by_user_id=principal.user_id,
        assigned_to_user_id=find_offer_approver_id(db, principal),
        decided_by_user_id=None,
        request_type="offer_ceiling",
        entity_type="offer_negotiation_plan",
        entity_id=plan.id,
        status="pending",
        title=f"Approve offer ceiling for {seller_name}",
        summary=(
            f"Version {version.version_number}: opening ${opening / 100:,.0f}, "
            f"target ${target / 100:,.0f}, stretch ${stretch / 100:,.0f}, "
            f"ceiling ${ceiling / 100:,.0f}."
        ),
        decision_notes=None,
        due_at=None,
        decided_at=None,
        approval_metadata={
            "lead_id": str(lead.id),
            "property_id": str(lead.property_id),
            "underwriting_version_id": str(version.id),
            "underwriting_version_number": version.version_number,
            "market_analysis_id": str(analysis.id) if analysis else None,
            "offer_negotiation_plan_id": str(plan.id),
            "opening_offer_cents": opening,
            "target_contract_cents": target,
            "stretch_contract_cents": stretch,
            "seller_ceiling_cents": ceiling,
        },
    )
    db.add(approval)
    db.flush()
    plan.approval_request_id = approval.id
    lead.stage_key = "offer_pending_approval"
    version.status = "pending_approval"

    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            event_type="underwriting.offer_approval_requested",
            summary=(
                f"Offer ceiling approval requested from version {version.version_number} at "
                f"${ceiling / 100:,.0f}."
            ),
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="underwriting.offer_approval.request",
            entity_type="offer_negotiation_plan",
            entity_id=plan.id,
            previous_value={"superseded_pending_plans": superseded_count},
            new_value={
                "approval_request_id": str(approval.id),
                **snapshot,
                "opening_offer_cents": opening,
                "target_contract_cents": target,
                "stretch_contract_cents": stretch,
                "seller_context": plan.seller_context,
                "rationale": plan.rationale,
            },
            reason="Seller negotiation plan submitted for human approval",
        )
    )
    db.commit()
    db.refresh(plan)
    return offer_plan_to_read(db, plan)


def negotiation_ladder(
    version: UnderwritingVersion,
    ceiling: int,
    payload: OfferNegotiationPlanCreate,
) -> tuple[int, int, int]:
    opening = payload.opening_offer_cents
    if opening is None:
        opening = version.recommended_offer_cents or round_to_500(ceiling * 9 // 10)
    opening = min(opening, ceiling)
    spread = ceiling - opening
    target = payload.target_contract_cents
    if target is None:
        target = round_to_500(opening + round(spread * 0.4))
    stretch = payload.stretch_contract_cents
    if stretch is None:
        stretch = round_to_500(opening + round(spread * 0.75))
    return opening, target, stretch


def round_to_500(cents: int) -> int:
    increment = 50_000
    return ((cents + increment // 2) // increment) * increment


def supersede_pending_offer_plans(
    db: Session,
    lead: Lead,
    principal: Principal,
    decided_at: datetime,
) -> int:
    plans = db.scalars(
        select(OfferNegotiationPlan).where(
            OfferNegotiationPlan.organization_id == principal.organization_id,
            OfferNegotiationPlan.lead_id == lead.id,
            OfferNegotiationPlan.status == "pending",
        )
    ).all()
    for plan in plans:
        plan.status = "cancelled"
        if plan.approval_request_id:
            approval = db.get(ApprovalRequest, plan.approval_request_id)
            if approval and approval.status == "pending":
                approval.status = "cancelled"
                approval.decided_by_user_id = principal.user_id
                approval.decision_notes = "Superseded by a newer offer approval request."
                approval.decided_at = decided_at
    return len(plans)


def find_offer_approver_id(db: Session, principal: Principal) -> UUID:
    role_rank = case(
        *(
            (Role.key == role_key, priority)
            for role_key, priority in APPROVER_ROLE_PRIORITY.items()
        ),
        else_=99,
    )
    approver = db.scalar(
        select(User.id)
        .join(RoleAssignment, RoleAssignment.user_id == User.id)
        .join(Role, Role.id == RoleAssignment.role_id)
        .where(
            User.organization_id == principal.organization_id,
            User.is_active.is_(True),
            Role.key.in_(APPROVER_ROLE_PRIORITY),
        )
        .order_by(role_rank, User.created_at)
        .limit(1)
    )
    return approver or principal.user_id


def offer_plan_to_read(db: Session, plan: OfferNegotiationPlan) -> OfferNegotiationPlanRead:
    version = db.get(UnderwritingVersion, plan.underwriting_version_id)
    approval = (
        db.get(ApprovalRequest, plan.approval_request_id)
        if plan.approval_request_id
        else None
    )
    return OfferNegotiationPlanRead(
        id=plan.id,
        lead_id=plan.lead_id,
        property_id=plan.property_id,
        underwriting_version_id=plan.underwriting_version_id,
        underwriting_version_number=version.version_number if version else 0,
        market_analysis_id=plan.market_analysis_id,
        approval_request_id=plan.approval_request_id,
        status=plan.status,
        seller_asking_price_cents=plan.seller_asking_price_cents,
        arv_low_cents=plan.arv_low_cents,
        arv_point_cents=plan.arv_point_cents,
        arv_high_cents=plan.arv_high_cents,
        total_rehab_cents=plan.total_rehab_cents,
        disposition_cents=plan.disposition_cents,
        opening_offer_cents=plan.opening_offer_cents,
        target_contract_cents=plan.target_contract_cents,
        stretch_contract_cents=plan.stretch_contract_cents,
        seller_ceiling_cents=plan.seller_ceiling_cents,
        seller_context=plan.seller_context,
        rationale=plan.rationale,
        source_snapshot=plan.source_snapshot,
        approval_status=approval.status if approval else None,
        decision_notes=approval.decision_notes if approval else None,
        decided_by_user_id=approval.decided_by_user_id if approval else None,
        decided_at=approval.decided_at if approval else None,
        created_at=plan.created_at,
    )


def scoped_lead(db: Session, principal: Principal, lead_id: UUID) -> Lead | None:
    return db.scalar(
        select(Lead).where(
            Lead.id == lead_id,
            Lead.organization_id == principal.organization_id,
        )
    )


def optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return round(value)
    return None


def clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None
