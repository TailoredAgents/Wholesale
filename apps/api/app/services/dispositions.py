import csv
from datetime import UTC, datetime
from hashlib import sha256
from io import BytesIO, StringIO
from uuid import UUID

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.models.foundation import (
    AuditEvent,
    Buyer,
    BuyerCriteria,
    BuyerEngagement,
    BuyerOffer,
    BuyerProofDocument,
    CompensationPlanRole,
    CompensationPlanVersion,
    Contact,
    DealDeduction,
    DealPayout,
    DealReconciliation,
    DispositionCampaign,
    DispositionCase,
    DispositionMatch,
    DispositionOperatingMode,
    Lead,
    Property,
    RevenueRecord,
    RoleCredit,
    Transaction,
    User,
)
from app.schemas.dispositions import (
    BuyerSelection,
    DispositionCaseCreate,
    DispositionCaseRead,
    DispositionMetrics,
    DispositionOverview,
    EligibleTransactionRead,
    EngagementCreate,
    EngagementRead,
    MatchRead,
    OfferCreate,
    OfferRead,
    PayoutRead,
    ProofDocumentRead,
    ReconciliationDecision,
    ReconciliationRead,
)

MAX_FILE_BYTES = 15 * 1024 * 1024


def scoped_case(db: Session, principal: Principal, case_id: UUID) -> DispositionCase | None:
    return db.scalar(
        select(DispositionCase).where(
            DispositionCase.id == case_id,
            DispositionCase.organization_id == principal.organization_id,
        )
    )


def audit(
    db: Session,
    principal: Principal,
    action: str,
    entity_type: str,
    entity_id: UUID,
    new: dict,
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
            new_value=new,
            reason=reason,
        )
    )


def overview(db: Session, principal: Principal) -> DispositionOverview:
    cases = db.scalars(
        select(DispositionCase)
        .where(DispositionCase.organization_id == principal.organization_id)
        .order_by(DispositionCase.created_at.desc())
    ).all()
    used = {item.transaction_id for item in cases}
    transactions = db.scalars(
        select(Transaction)
        .where(
            Transaction.organization_id == principal.organization_id,
            Transaction.status.in_(("executed", "closing", "funded")),
        )
        .order_by(Transaction.created_at.desc())
    ).all()
    eligible = []
    for transaction in transactions:
        if transaction.id in used:
            continue
        contact = db.get(Contact, transaction.contact_id)
        property_record = db.get(Property, transaction.property_id)
        eligible.append(
            EligibleTransactionRead(
                id=transaction.id,
                seller_name=contact.legal_name if contact else "Unknown seller",
                property_address=address(property_record),
                purchase_price_cents=transaction.purchase_price_cents,
                assignment_fee_cents=transaction.assignment_fee_cents,
            )
        )
    reads = [case_read(db, item) for item in cases]
    return DispositionOverview(
        metrics=DispositionMetrics(
            active_cases=sum(item.status not in {"closed", "cancelled"} for item in cases),
            packages_pending=sum(item.package_status != "approved" for item in cases),
            buyer_selected=sum(item.selected_buyer_id is not None for item in cases),
            reconciliation_pending=sum(
                item.reconciliation is not None and item.reconciliation.status == "draft"
                for item in reads
            ),
            below_margin_target=sum(
                item.reconciliation is not None
                and item.reconciliation.company_margin_basis_points
                < item.reconciliation.target_margin_basis_points
                for item in reads
            ),
        ),
        eligible_transactions=eligible,
        cases=reads,
    )


def create_case(
    db: Session, principal: Principal, payload: DispositionCaseCreate
) -> DispositionCaseRead:
    transaction = db.scalar(
        select(Transaction).where(
            Transaction.id == payload.transaction_id,
            Transaction.organization_id == principal.organization_id,
        )
    )
    if transaction is None or transaction.status not in {"executed", "closing", "funded"}:
        raise ValueError("An executed transaction is required.")
    if payload.minimum_acceptable_cents > payload.asking_price_cents:
        raise ValueError("Minimum acceptable price cannot exceed asking price.")
    if db.scalar(
        select(DispositionCase.id).where(DispositionCase.transaction_id == transaction.id)
    ):
        raise ValueError("A disposition case already exists for this transaction.")
    plan = db.scalar(
        select(CompensationPlanVersion).where(
            CompensationPlanVersion.organization_id == principal.organization_id,
            CompensationPlanVersion.status == "active",
        )
    )
    if plan is None:
        raise ValueError("Activate a compensation plan in Business Setup first.")
    mode = db.scalar(
        select(DispositionOperatingMode).where(
            DispositionOperatingMode.compensation_plan_version_id == plan.id,
            DispositionOperatingMode.key == payload.operating_mode_key,
            DispositionOperatingMode.status == "available",
        )
    )
    if mode is None:
        raise ValueError("Select an active disposition operating mode.")
    lead = db.get(Lead, transaction.lead_id)
    contact = db.get(Contact, transaction.contact_id)
    property_record = db.get(Property, transaction.property_id)
    case = DispositionCase(
        organization_id=principal.organization_id,
        transaction_id=transaction.id,
        deal_id=transaction.deal_id,
        lead_id=transaction.lead_id,
        property_id=transaction.property_id,
        owner_user_id=principal.user_id,
        compensation_plan_version_id=plan.id,
        disposition_operating_mode_id=mode.id,
        status="package_prep",
        strategy=payload.strategy,
        asking_price_cents=payload.asking_price_cents,
        minimum_acceptable_cents=payload.minimum_acceptable_cents,
        package_status="draft",
        package_snapshot={
            "seller_name": contact.legal_name if contact else "Unknown",
            "property_address": address(property_record),
            "property_type": property_record.property_type if property_record else None,
            "purchase_price_cents": transaction.purchase_price_cents,
            "asking_price_cents": payload.asking_price_cents,
            "minimum_acceptable_cents": payload.minimum_acceptable_cents,
            "strategy": payload.strategy,
            "lead_source": lead.source if lead else None,
        },
        package_approved_by_user_id=None,
        package_approved_at=None,
        selected_buyer_id=None,
        backup_buyer_id=None,
        selection_approved_by_user_id=None,
        selection_approved_at=None,
        notes=payload.notes,
    )
    db.add(case)
    transaction.compensation_plan_version_id = plan.id
    transaction.disposition_operating_mode_id = mode.id
    db.flush()
    audit(
        db,
        principal,
        "disposition.case_create",
        "disposition_case",
        case.id,
        {"transaction_id": str(transaction.id), "plan_id": str(plan.id), "mode_id": str(mode.id)},
        "Disposition case opened",
    )
    db.commit()
    return case_read(db, case)


def approve_package(db: Session, principal: Principal, case_id: UUID) -> DispositionCaseRead | None:
    case = scoped_case(db, principal, case_id)
    if case is None:
        return None
    case.package_status = "approved"
    case.package_approved_by_user_id = principal.user_id
    case.package_approved_at = datetime.now(UTC)
    case.status = "buyer_matching"
    audit(
        db,
        principal,
        "disposition.package_approve",
        "disposition_case",
        case.id,
        {"package_status": "approved"},
        "Human review of deal package",
    )
    db.commit()
    return case_read(db, case)


def generate_matches(
    db: Session, principal: Principal, case_id: UUID
) -> DispositionCaseRead | None:
    case = scoped_case(db, principal, case_id)
    if case is None:
        return None
    if case.package_status != "approved":
        raise ValueError("Approve the deal package before matching buyers.")
    property_record = db.get(Property, case.property_id)
    db.execute(delete(DispositionMatch).where(DispositionMatch.disposition_case_id == case.id))
    scored: list[tuple[Buyer, int, dict[str, int], str]] = []
    now = datetime.now(UTC)
    buyers = db.scalars(
        select(Buyer).where(
            Buyer.organization_id == principal.organization_id, Buyer.status == "active"
        )
    ).all()
    for buyer in buyers:
        criteria = db.scalar(
            select(BuyerCriteria)
            .where(BuyerCriteria.buyer_id == buyer.id)
            .order_by(BuyerCriteria.created_at.desc())
        )
        buyer_maximums = [
            value
            for value in (
                buyer.max_purchase_price_cents,
                criteria.max_price_cents if criteria else None,
            )
            if value is not None
        ]
        price_ok = (
            not buyer_maximums or min(buyer_maximums) >= case.minimum_acceptable_cents
        ) and (
            criteria is None
            or criteria.min_price_cents is None
            or criteria.min_price_cents <= case.asking_price_cents
        )
        market_terms = csv_terms(criteria.markets if criteria else None)
        property_markets = {
            value.strip().lower()
            for value in (
                property_record.city if property_record else None,
                property_record.state if property_record else None,
                property_record.county if property_record else None,
            )
            if value and value.strip()
        }
        market_ok = not market_terms or bool(market_terms & property_markets)
        property_types = csv_terms(criteria.property_types if criteria else None)
        subject_type = (
            (property_record.property_type or "").strip().lower() if property_record else ""
        )
        type_ok = not property_types or subject_type in property_types
        proof = db.scalar(
            select(BuyerProofDocument)
            .where(
                BuyerProofDocument.buyer_id == buyer.id,
                BuyerProofDocument.organization_id == principal.organization_id,
                BuyerProofDocument.status == "verified",
            )
            .order_by(BuyerProofDocument.created_at.desc())
            .limit(1)
        )
        pof_ok = proof is not None and (proof.expires_at is None or aware(proof.expires_at) >= now)
        if pof_ok and proof and proof.verified_amount_cents is not None:
            pof_ok = proof.verified_amount_cents >= case.minimum_acceptable_cents
        components = {
            "proof": 3000 if pof_ok else 0,
            "price": 2500 if price_ok else 0,
            "market": 2000 if market_ok else 0,
            "reliability": round(buyer.reliability_score_basis_points * 0.15),
            "property_type": 1000 if type_ok else 0,
        }
        score = sum(components.values())
        qualified = price_ok and market_ok and type_ok and pof_ok
        scored.append((buyer, score, components, "qualified" if qualified else "review_required"))
    scored.sort(key=lambda value: value[1], reverse=True)
    for rank, (buyer, score, components, qualification) in enumerate(scored, 1):
        db.add(
            DispositionMatch(
                organization_id=principal.organization_id,
                disposition_case_id=case.id,
                buyer_id=buyer.id,
                score_basis_points=score,
                score_components=components,
                qualification_status=qualification,
                recipient_status="proposed" if qualification == "qualified" else "excluded",
                rank=rank,
            )
        )
    db.commit()
    return case_read(db, case)


def release_campaign(
    db: Session, principal: Principal, case_id: UUID
) -> DispositionCaseRead | None:
    case = scoped_case(db, principal, case_id)
    if case is None:
        return None
    matches = db.scalars(
        select(DispositionMatch).where(
            DispositionMatch.disposition_case_id == case.id,
            DispositionMatch.qualification_status == "qualified",
        )
    ).all()
    if not matches:
        raise ValueError("No qualified buyers are available for an approved campaign.")
    for match in matches:
        match.recipient_status = "approved"
    campaign = DispositionCampaign(
        organization_id=principal.organization_id,
        disposition_case_id=case.id,
        created_by_user_id=principal.user_id,
        status="simulated_released",
        name=f"{case.package_snapshot.get('property_address', 'Deal')} buyer release",
        channel="simulation",
        recipient_count=len(matches),
        released_at=datetime.now(UTC),
    )
    db.add(campaign)
    case.status = "marketed"
    db.commit()
    return case_read(db, case)


def upload_proof(
    db: Session,
    principal: Principal,
    buyer_id: UUID,
    *,
    content: bytes,
    file_name: str,
    content_type: str,
    institution_name: str | None,
    verified_amount_cents: int | None,
    expires_at: datetime | None,
) -> ProofDocumentRead:
    buyer = db.scalar(
        select(Buyer).where(
            Buyer.id == buyer_id, Buyer.organization_id == principal.organization_id
        )
    )
    if buyer is None:
        raise ValueError("Buyer not found.")
    if not content or len(content) > MAX_FILE_BYTES:
        raise ValueError("Proof document must be between 1 byte and 15 MB.")
    document = BuyerProofDocument(
        organization_id=principal.organization_id,
        buyer_id=buyer.id,
        uploaded_by_user_id=principal.user_id,
        status="verified",
        institution_name=institution_name,
        verified_amount_cents=verified_amount_cents,
        expires_at=expires_at,
        file_name=file_name,
        content_type=content_type,
        file_size=len(content),
        sha256=sha256(content).hexdigest(),
        file_data=content,
        notes=None,
    )
    db.add(document)
    buyer.proof_of_funds_status = "received"
    buyer.proof_of_funds_expires_at = expires_at
    db.commit()
    db.refresh(document)
    return proof_read(document)


def create_offer(
    db: Session, principal: Principal, case_id: UUID, payload: OfferCreate
) -> DispositionCaseRead | None:
    case = scoped_case(db, principal, case_id)
    if case is None:
        return None
    buyer = db.scalar(
        select(Buyer).where(
            Buyer.id == payload.buyer_id, Buyer.organization_id == principal.organization_id
        )
    )
    if buyer is None:
        raise ValueError("Buyer not found.")
    proof = (
        db.get(BuyerProofDocument, payload.proof_document_id) if payload.proof_document_id else None
    )
    offer = BuyerOffer(
        organization_id=principal.organization_id,
        lead_id=case.lead_id,
        deal_id=case.deal_id,
        buyer_id=buyer.id,
        disposition_case_id=case.id,
        proof_document_id=proof.id if proof and proof.buyer_id == buyer.id else None,
        amount_cents=payload.amount_cents,
        earnest_money_cents=payload.earnest_money_cents,
        financing_type=payload.financing_type,
        status="received",
        proof_of_funds_received=proof is not None,
        notes=payload.notes,
        received_at=datetime.now(UTC),
        deposit_due_at=payload.deposit_due_at,
        deposit_received_at=None,
        selected_at=None,
    )
    db.add(offer)
    case.status = "offers_received"
    db.commit()
    return case_read(db, case)


def add_engagement(
    db: Session, principal: Principal, case_id: UUID, payload: EngagementCreate
) -> DispositionCaseRead | None:
    case = scoped_case(db, principal, case_id)
    if case is None:
        return None
    buyer = db.scalar(
        select(Buyer).where(
            Buyer.id == payload.buyer_id,
            Buyer.organization_id == principal.organization_id,
        )
    )
    if buyer is None:
        raise ValueError("Buyer not found.")
    db.add(
        BuyerEngagement(
            organization_id=principal.organization_id,
            disposition_case_id=case.id,
            buyer_id=payload.buyer_id,
            actor_user_id=principal.user_id,
            engagement_type=payload.engagement_type,
            status=payload.status,
            scheduled_at=payload.scheduled_at,
            occurred_at=datetime.now(UTC),
            notes=payload.notes,
        )
    )
    db.commit()
    return case_read(db, case)


def select_buyer(
    db: Session, principal: Principal, case_id: UUID, payload: BuyerSelection
) -> DispositionCaseRead | None:
    case = scoped_case(db, principal, case_id)
    if case is None:
        return None
    primary = db.scalar(
        select(BuyerOffer).where(
            BuyerOffer.id == payload.primary_offer_id, BuyerOffer.disposition_case_id == case.id
        )
    )
    backup = (
        db.scalar(
            select(BuyerOffer).where(
                BuyerOffer.id == payload.backup_offer_id, BuyerOffer.disposition_case_id == case.id
            )
        )
        if payload.backup_offer_id
        else None
    )
    if primary is None or primary.amount_cents < case.minimum_acceptable_cents:
        raise ValueError("Primary offer must meet the approved minimum price.")
    if backup and backup.id == primary.id:
        raise ValueError("Primary and backup offers must be different.")
    proof = (
        db.get(BuyerProofDocument, primary.proof_document_id) if primary.proof_document_id else None
    )
    if (
        proof is None
        or proof.status != "verified"
        or (proof.expires_at and aware(proof.expires_at) < datetime.now(UTC))
    ):
        raise ValueError("A current verified proof-of-funds document is required.")
    now = datetime.now(UTC)
    primary.status = "selected"
    primary.selected_at = now
    if backup:
        backup.status = "backup"
    for other in db.scalars(
        select(BuyerOffer).where(
            BuyerOffer.disposition_case_id == case.id,
            BuyerOffer.id.notin_(
                [value for value in (primary.id, backup.id if backup else None) if value]
            ),
        )
    ).all():
        other.status = "declined"
    case.selected_buyer_id = primary.buyer_id
    case.backup_buyer_id = backup.buyer_id if backup else None
    case.selection_approved_by_user_id = principal.user_id
    case.selection_approved_at = now
    case.status = "buyer_selected"
    audit(
        db,
        principal,
        "disposition.buyer_select",
        "disposition_case",
        case.id,
        {
            "primary_buyer_id": str(primary.buyer_id),
            "backup_buyer_id": str(backup.buyer_id) if backup else None,
        },
        payload.reason,
    )
    db.commit()
    return case_read(db, case)


def build_reconciliation(
    db: Session, principal: Principal, case_id: UUID
) -> DispositionCaseRead | None:
    case = scoped_case(db, principal, case_id)
    if case is None:
        return None
    transaction = db.get(Transaction, case.transaction_id)
    if transaction is None or transaction.status != "funded" or case.selected_buyer_id is None:
        raise ValueError("Funded transaction and approved buyer selection are required.")
    gross = int(
        db.scalar(
            select(func.coalesce(func.sum(RevenueRecord.amount_cents), 0)).where(
                RevenueRecord.transaction_id == transaction.id, RevenueRecord.status == "collected"
            )
        )
        or 0
    )
    if gross <= 0:
        raise ValueError("Record collected deal revenue before reconciliation.")
    deductions = int(
        db.scalar(
            select(func.coalesce(func.sum(DealDeduction.amount_cents), 0)).where(
                DealDeduction.transaction_id == transaction.id
            )
        )
        or 0
    )
    plan = db.get(CompensationPlanVersion, case.compensation_plan_version_id)
    if plan is None:
        raise ValueError("Frozen compensation plan is unavailable.")
    margin = max(gross - plan.acquisition_reserve_cents - deductions, 0)
    reconciliation = db.scalar(
        select(DealReconciliation).where(DealReconciliation.transaction_id == transaction.id)
    )
    if reconciliation and reconciliation.status == "approved":
        raise ValueError("Approved reconciliation cannot be recalculated.")
    if reconciliation is None:
        reconciliation = DealReconciliation(
            organization_id=principal.organization_id,
            transaction_id=transaction.id,
            disposition_case_id=case.id,
            compensation_plan_version_id=plan.id,
            disposition_operating_mode_id=case.disposition_operating_mode_id,
            created_by_user_id=principal.user_id,
            approved_by_user_id=None,
            status="draft",
            gross_revenue_cents=0,
            acquisition_reserve_cents=0,
            deal_deductions_cents=0,
            adjusted_deal_margin_cents=0,
            total_compensation_cents=0,
            company_profit_cents=0,
            company_margin_basis_points=0,
            target_margin_basis_points=plan.target_company_margin_basis_points,
            snapshot={},
            approved_at=None,
            notes=None,
        )
        db.add(reconciliation)
        db.flush()
    db.execute(delete(DealPayout).where(DealPayout.deal_reconciliation_id == reconciliation.id))
    roles = db.scalars(
        select(CompensationPlanRole).where(
            CompensationPlanRole.compensation_plan_version_id == plan.id
        )
    ).all()
    payouts_total = 0
    for role in roles:
        role_amount = round(margin * role.basis_points / 10000)
        if role.cap_cents is not None:
            role_amount = min(role_amount, role.cap_cents)
        credits = db.scalars(
            select(RoleCredit).where(
                RoleCredit.lead_id == case.lead_id,
                RoleCredit.role_key == role.role_key,
                RoleCredit.status.in_(("approved", "earned", "payable")),
            )
        ).all()
        if credits:
            allocated_basis_points = 0
            for credit in credits:
                amount = round(role_amount * credit.credit_basis_points / 10000)
                allocated_basis_points += credit.credit_basis_points
                payouts_total += amount
                db.add(
                    DealPayout(
                        organization_id=principal.organization_id,
                        deal_reconciliation_id=reconciliation.id,
                        role_credit_id=credit.id,
                        user_id=credit.user_id,
                        role_key=role.role_key,
                        credit_basis_points=credit.credit_basis_points,
                        amount_cents=amount,
                        status="calculated",
                        approved_at=None,
                        paid_at=None,
                    )
                )
            unassigned_basis_points = max(10000 - allocated_basis_points, 0)
            if unassigned_basis_points:
                amount = round(role_amount * unassigned_basis_points / 10000)
                payouts_total += amount
                db.add(
                    DealPayout(
                        organization_id=principal.organization_id,
                        deal_reconciliation_id=reconciliation.id,
                        role_credit_id=None,
                        user_id=None,
                        role_key=role.role_key,
                        credit_basis_points=unassigned_basis_points,
                        amount_cents=amount,
                        status="unassigned",
                        approved_at=None,
                        paid_at=None,
                    )
                )
        else:
            payouts_total += role_amount
            db.add(
                DealPayout(
                    organization_id=principal.organization_id,
                    deal_reconciliation_id=reconciliation.id,
                    role_credit_id=None,
                    user_id=None,
                    role_key=role.role_key,
                    credit_basis_points=10000,
                    amount_cents=role_amount,
                    status="unassigned",
                    approved_at=None,
                    paid_at=None,
                )
            )
    company = margin - payouts_total
    reconciliation.status = "draft"
    reconciliation.gross_revenue_cents = gross
    reconciliation.acquisition_reserve_cents = plan.acquisition_reserve_cents
    reconciliation.deal_deductions_cents = deductions
    reconciliation.adjusted_deal_margin_cents = margin
    reconciliation.total_compensation_cents = payouts_total
    reconciliation.company_profit_cents = company
    reconciliation.company_margin_basis_points = round(company * 10000 / margin) if margin else 0
    reconciliation.snapshot = {
        "plan_name": plan.name,
        "plan_version": plan.version_number,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    db.commit()
    return case_read(db, case)


def decide_reconciliation(
    db: Session, principal: Principal, case_id: UUID, payload: ReconciliationDecision
) -> DispositionCaseRead | None:
    case = scoped_case(db, principal, case_id)
    if case is None:
        return None
    reconciliation = db.scalar(
        select(DealReconciliation).where(DealReconciliation.disposition_case_id == case.id)
    )
    if reconciliation is None or reconciliation.status != "draft":
        raise ValueError("A draft reconciliation is required.")
    if (
        payload.decision == "approved"
        and reconciliation.company_margin_basis_points < reconciliation.target_margin_basis_points
        and not payload.approve_below_target
    ):
        raise ValueError(
            "Company margin is below target. Record an explicit owner override to approve."
        )
    unassigned_payout = db.scalar(
        select(DealPayout.id).where(
            DealPayout.deal_reconciliation_id == reconciliation.id,
            DealPayout.user_id.is_(None),
            DealPayout.amount_cents > 0,
        )
    )
    if payload.decision == "approved" and unassigned_payout is not None:
        raise ValueError("Approve role credits for every commission role before reconciliation.")
    now = datetime.now(UTC)
    reconciliation.status = payload.decision
    reconciliation.notes = payload.notes
    reconciliation.approved_by_user_id = principal.user_id
    reconciliation.approved_at = now
    for payout in db.scalars(
        select(DealPayout).where(DealPayout.deal_reconciliation_id == reconciliation.id)
    ).all():
        payout.status = (
            "approved" if payload.decision == "approved" and payout.user_id else payout.status
        )
        payout.approved_at = now if payout.status == "approved" else None
    if payload.decision == "approved":
        case.status = "reconciled"
    audit(
        db,
        principal,
        "finance.reconciliation_decide",
        "deal_reconciliation",
        reconciliation.id,
        {
            "status": reconciliation.status,
            "company_margin_basis_points": reconciliation.company_margin_basis_points,
        },
        payload.notes,
    )
    db.commit()
    return case_read(db, case)


def package_pdf(db: Session, principal: Principal, case_id: UUID) -> tuple[bytes, str] | None:
    case = scoped_case(db, principal, case_id)
    if case is None or case.package_status != "approved":
        return None
    stream = BytesIO()
    pdf = canvas.Canvas(stream, pagesize=letter)
    pdf.setTitle("Stonegate Deal Package")
    green = (0.15, 0.37, 0.26)
    ink = (0.09, 0.11, 0.12)
    muted = (0.40, 0.44, 0.45)
    pdf.setFillColorRGB(*green)
    pdf.rect(0, 680, letter[0], 112, fill=1, stroke=0)
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(48, 752, "STONEGATE HOME BUYERS")
    pdf.setFont("Helvetica-Bold", 23)
    pdf.drawString(48, 716, "Investor Deal Package")
    pdf.setFont("Helvetica", 9)
    pdf.drawString(48, 696, f"Approved {case.package_approved_at:%B %d, %Y}")

    pdf.setFillColorRGB(*ink)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(48, 640, str(case.package_snapshot.get("property_address")))
    pdf.setFillColorRGB(*muted)
    pdf.setFont("Helvetica", 10)
    pdf.drawString(48, 620, "Confidential opportunity summary for qualified buyers")

    pdf.setStrokeColorRGB(0.87, 0.84, 0.79)
    pdf.line(48, 590, 564, 590)
    rows = (
        ("PROPERTY TYPE", case.package_snapshot.get("property_type") or "Not provided"),
        ("TRANSACTION", case.strategy.replace("_", " ").title()),
        ("INVESTOR ASKING PRICE", f"${case.asking_price_cents / 100:,.0f}"),
        ("APPROVED RELEASE", "Human reviewed and approved"),
    )
    y = 555
    for label, value in rows:
        pdf.setFillColorRGB(*muted)
        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawString(48, y, label)
        pdf.setFillColorRGB(*ink)
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(238, y - 1, str(value))
        pdf.setStrokeColorRGB(0.93, 0.91, 0.87)
        pdf.line(48, y - 18, 564, y - 18)
        y -= 54

    pdf.setFillColorRGB(0.96, 0.97, 0.95)
    pdf.roundRect(48, 240, 516, 74, 4, fill=1, stroke=0)
    pdf.setFillColorRGB(*green)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(64, 288, "BUYER DUE DILIGENCE")
    pdf.setFillColorRGB(*ink)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(
        64, 268, "Confirm property facts, access, title, financing, and closing capacity"
    )
    pdf.drawString(64, 253, "before relying on this summary or submitting final purchase terms.")

    pdf.setFillColorRGB(*muted)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(48, 72, "CONFIDENTIAL - FOR QUALIFIED REAL ESTATE INVESTORS")
    pdf.drawRightString(564, 72, f"Case {str(case.id)[:8].upper()}")
    pdf.setFont("Helvetica-Oblique", 7)
    pdf.drawString(
        48,
        52,
        "Stonegate makes no representation that this summary replaces independent due diligence.",
    )
    pdf.save()
    return stream.getvalue(), f"stonegate-deal-package-{case.id}.pdf"


def accounting_csv(db: Session, principal: Principal, case_id: UUID) -> str | None:
    case = scoped_case(db, principal, case_id)
    if case is None:
        return None
    reconciliation = db.scalar(
        select(DealReconciliation).where(
            DealReconciliation.disposition_case_id == case.id,
            DealReconciliation.status == "approved",
        )
    )
    if reconciliation is None:
        return None
    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(("type", "role", "user", "amount_cents", "status"))
    writer.writerow(
        ("company_profit", "company", "", reconciliation.company_profit_cents, "approved")
    )
    users = {
        item.id: item.display_name
        for item in db.scalars(
            select(User).where(User.organization_id == principal.organization_id)
        ).all()
    }
    for payout in db.scalars(
        select(DealPayout).where(DealPayout.deal_reconciliation_id == reconciliation.id)
    ).all():
        user_name = users.get(payout.user_id, "")
        writer.writerow(("payout", payout.role_key, user_name, payout.amount_cents, payout.status))
    return output.getvalue()


def case_read(db: Session, case: DispositionCase) -> DispositionCaseRead:
    contact = db.scalar(
        select(Contact).join(Lead, Lead.contact_id == Contact.id).where(Lead.id == case.lead_id)
    )
    property_record = db.get(Property, case.property_id)
    plan = db.get(CompensationPlanVersion, case.compensation_plan_version_id)
    mode = db.get(DispositionOperatingMode, case.disposition_operating_mode_id)
    buyers = {
        item.id: item
        for item in db.scalars(
            select(Buyer).where(Buyer.organization_id == case.organization_id)
        ).all()
    }
    latest_proof_by_buyer: dict[UUID, BuyerProofDocument] = {}
    for proof in db.scalars(
        select(BuyerProofDocument)
        .where(BuyerProofDocument.organization_id == case.organization_id)
        .order_by(BuyerProofDocument.created_at.desc())
    ).all():
        latest_proof_by_buyer.setdefault(proof.buyer_id, proof)
    matches = db.scalars(
        select(DispositionMatch)
        .where(DispositionMatch.disposition_case_id == case.id)
        .order_by(DispositionMatch.rank)
    ).all()
    offers = db.scalars(
        select(BuyerOffer)
        .where(BuyerOffer.disposition_case_id == case.id)
        .order_by(BuyerOffer.received_at.desc())
    ).all()
    engagements = db.scalars(
        select(BuyerEngagement)
        .where(BuyerEngagement.disposition_case_id == case.id)
        .order_by(BuyerEngagement.occurred_at.desc())
    ).all()
    reconciliation = db.scalar(
        select(DealReconciliation).where(DealReconciliation.disposition_case_id == case.id)
    )
    return DispositionCaseRead(
        id=case.id,
        transaction_id=case.transaction_id,
        lead_id=case.lead_id,
        seller_name=contact.legal_name if contact else "Unknown seller",
        property_address=address(property_record),
        property_type=property_record.property_type if property_record else None,
        status=case.status,
        strategy=case.strategy,
        asking_price_cents=case.asking_price_cents,
        minimum_acceptable_cents=case.minimum_acceptable_cents,
        package_status=case.package_status,
        package_snapshot=case.package_snapshot,
        compensation_plan_label=f"{plan.name} v{plan.version_number}" if plan else "Unavailable",
        operating_mode_label=mode.name if mode else "Unavailable",
        selected_buyer_id=case.selected_buyer_id,
        backup_buyer_id=case.backup_buyer_id,
        matches=[
            MatchRead(
                id=item.id,
                buyer_id=item.buyer_id,
                buyer_name=buyers[item.buyer_id].name,
                score_basis_points=item.score_basis_points,
                score_components=item.score_components,
                qualification_status=item.qualification_status,
                recipient_status=item.recipient_status,
                rank=item.rank,
                proof_status=buyers[item.buyer_id].proof_of_funds_status,
                proof_expires_at=buyers[item.buyer_id].proof_of_funds_expires_at,
                latest_proof_document_id=(
                    latest_proof_by_buyer[item.buyer_id].id
                    if item.buyer_id in latest_proof_by_buyer
                    else None
                ),
            )
            for item in matches
        ],
        offers=[offer_read(item, buyers[item.buyer_id]) for item in offers],
        engagements=[
            EngagementRead(
                id=item.id,
                buyer_id=item.buyer_id,
                buyer_name=buyers[item.buyer_id].name,
                engagement_type=item.engagement_type,
                status=item.status,
                scheduled_at=item.scheduled_at,
                occurred_at=item.occurred_at,
                notes=item.notes,
            )
            for item in engagements
        ],
        reconciliation=reconciliation_read(db, reconciliation) if reconciliation else None,
        created_at=case.created_at,
    )


def reconciliation_read(db: Session, item: DealReconciliation) -> ReconciliationRead:
    users = {
        user.id: user.display_name
        for user in db.scalars(
            select(User).where(User.organization_id == item.organization_id)
        ).all()
    }
    payouts = db.scalars(
        select(DealPayout).where(DealPayout.deal_reconciliation_id == item.id)
    ).all()
    return ReconciliationRead(
        id=item.id,
        status=item.status,
        gross_revenue_cents=item.gross_revenue_cents,
        acquisition_reserve_cents=item.acquisition_reserve_cents,
        deal_deductions_cents=item.deal_deductions_cents,
        adjusted_deal_margin_cents=item.adjusted_deal_margin_cents,
        total_compensation_cents=item.total_compensation_cents,
        company_profit_cents=item.company_profit_cents,
        company_margin_basis_points=item.company_margin_basis_points,
        target_margin_basis_points=item.target_margin_basis_points,
        notes=item.notes,
        payouts=[
            PayoutRead(
                id=value.id,
                role_key=value.role_key,
                user_id=value.user_id,
                user_name=users.get(value.user_id) if value.user_id else None,
                credit_basis_points=value.credit_basis_points,
                amount_cents=value.amount_cents,
                status=value.status,
            )
            for value in payouts
        ],
        created_at=item.created_at,
    )


def offer_read(item: BuyerOffer, buyer: Buyer) -> OfferRead:
    return OfferRead(
        id=item.id,
        buyer_id=item.buyer_id,
        buyer_name=buyer.name,
        amount_cents=item.amount_cents,
        earnest_money_cents=item.earnest_money_cents,
        financing_type=item.financing_type,
        status=item.status,
        proof_document_id=item.proof_document_id,
        deposit_due_at=item.deposit_due_at,
        deposit_received_at=item.deposit_received_at,
        selected_at=item.selected_at,
        notes=item.notes,
        received_at=item.received_at,
    )


def proof_read(item: BuyerProofDocument) -> ProofDocumentRead:
    return ProofDocumentRead(
        id=item.id,
        buyer_id=item.buyer_id,
        status=item.status,
        institution_name=item.institution_name,
        verified_amount_cents=item.verified_amount_cents,
        expires_at=item.expires_at,
        file_name=item.file_name,
        created_at=item.created_at,
    )


def address(item: Property | None) -> str:
    return (
        f"{item.street_address}, {item.city}, {item.state} {item.postal_code}"
        if item
        else "Unknown property"
    )


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def csv_terms(value: str | None) -> set[str]:
    if not value:
        return set()
    return {item.strip().lower() for item in value.split(",") if item.strip()}
