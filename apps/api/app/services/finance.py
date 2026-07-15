from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, delete, func, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.models.foundation import (
    ActivityEvent,
    AuditEvent,
    CompensationCalculation,
    CompensationRule,
    Contact,
    Deal,
    DealDeduction,
    Lead,
    MarketingSpend,
    Property,
    RevenueRecord,
    Transaction,
)
from app.schemas.finance import (
    CompensationCalculationRead,
    CompensationRuleCreate,
    CompensationRuleRead,
    DealDeductionCreate,
    DealDeductionRead,
    FinanceOverview,
    FinanceSummary,
    MarketingSpendCreate,
    MarketingSpendRead,
    RevenueCreate,
    RevenueRead,
)

REVENUE_STATUSES = {"pending", "collected", "void"}
REVENUE_SOURCES = {"assignment_fee", "double_close", "consulting_fee", "other"}
DEDUCTION_CATEGORIES = {"title", "attorney", "transaction", "marketing", "seller_credit", "other"}
COMPENSATION_APPLIES_TO = {"gross_revenue", "net_revenue"}


def get_finance_overview(db: Session, principal: Principal) -> FinanceOverview:
    revenue_records = db.scalars(
        select(RevenueRecord)
        .where(RevenueRecord.organization_id == principal.organization_id)
        .order_by(RevenueRecord.received_at.desc(), RevenueRecord.created_at.desc())
        .limit(100)
    ).all()
    deductions = db.scalars(
        select(DealDeduction)
        .where(DealDeduction.organization_id == principal.organization_id)
        .order_by(DealDeduction.incurred_at.desc(), DealDeduction.created_at.desc())
        .limit(100)
    ).all()
    rules = db.scalars(
        select(CompensationRule)
        .where(CompensationRule.organization_id == principal.organization_id)
        .order_by(CompensationRule.effective_start_at.desc(), CompensationRule.created_at.desc())
        .limit(100)
    ).all()
    calculations = db.scalars(
        select(CompensationCalculation)
        .where(CompensationCalculation.organization_id == principal.organization_id)
        .order_by(CompensationCalculation.created_at.desc())
        .limit(100)
    ).all()
    marketing_spend = db.scalars(
        select(MarketingSpend)
        .where(MarketingSpend.organization_id == principal.organization_id)
        .order_by(MarketingSpend.spend_month_at.desc(), MarketingSpend.created_at.desc())
        .limit(100)
    ).all()
    lead_context = get_lead_context(
        db,
        principal,
        [record.lead_id for record in revenue_records if record.lead_id is not None],
    )
    return FinanceOverview(
        summary=get_finance_summary(db, principal),
        revenue_records=[
            revenue_to_read(record, lead_context.get(record.lead_id)) for record in revenue_records
        ],
        deductions=[deduction_to_read(deduction) for deduction in deductions],
        compensation_rules=[rule_to_read(rule) for rule in rules],
        compensation_calculations=[
            calculation_to_read(calculation) for calculation in calculations
        ],
        marketing_spend=[marketing_spend_to_read(spend) for spend in marketing_spend],
    )


def create_revenue_record(
    db: Session,
    principal: Principal,
    payload: RevenueCreate,
) -> RevenueRead:
    validate_revenue_payload(payload)
    lead, deal, transaction = resolve_finance_context(db, principal, payload.lead_id)
    record = RevenueRecord(
        organization_id=principal.organization_id,
        lead_id=lead.id if lead is not None else None,
        deal_id=deal.id if deal is not None else None,
        transaction_id=transaction.id if transaction is not None else None,
        source=payload.source,
        status=payload.status,
        amount_cents=payload.amount_cents,
        received_at=payload.received_at or datetime.now(UTC),
        notes=payload.notes,
    )
    db.add(record)
    db.flush()
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="finance",
            entity_id=record.id,
            event_type="finance.revenue_recorded",
            summary=f"Revenue recorded: {payload.amount_cents / 100:.0f}.",
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="finance.revenue_create",
            entity_type="revenue_record",
            entity_id=record.id,
            previous_value=None,
            new_value={
                "lead_id": str(record.lead_id) if record.lead_id else None,
                "deal_id": str(record.deal_id) if record.deal_id else None,
                "transaction_id": str(record.transaction_id) if record.transaction_id else None,
                "source": record.source,
                "status": record.status,
                "amount_cents": record.amount_cents,
            },
            reason="Manual revenue entry",
        )
    )
    recalculate_compensation(db, principal)
    db.commit()
    db.refresh(record)
    context = get_lead_context(db, principal, [record.lead_id]).get(record.lead_id)
    return revenue_to_read(record, context)


def create_deal_deduction(
    db: Session,
    principal: Principal,
    payload: DealDeductionCreate,
) -> DealDeductionRead:
    if payload.category not in DEDUCTION_CATEGORIES:
        raise ValueError(f"Unsupported deduction category: {payload.category}")
    lead, deal, transaction = resolve_finance_context(db, principal, payload.lead_id)
    deduction = DealDeduction(
        organization_id=principal.organization_id,
        lead_id=lead.id if lead is not None else None,
        deal_id=deal.id if deal is not None else None,
        transaction_id=transaction.id if transaction is not None else None,
        category=payload.category,
        amount_cents=payload.amount_cents,
        incurred_at=payload.incurred_at or datetime.now(UTC),
        notes=payload.notes,
    )
    db.add(deduction)
    db.flush()
    add_finance_audit(
        db,
        principal,
        "finance.deduction_create",
        "deal_deduction",
        deduction.id,
        {
            "lead_id": str(deduction.lead_id) if deduction.lead_id else None,
            "deal_id": str(deduction.deal_id) if deduction.deal_id else None,
            "category": deduction.category,
            "amount_cents": deduction.amount_cents,
        },
    )
    recalculate_compensation(db, principal)
    db.commit()
    db.refresh(deduction)
    return deduction_to_read(deduction)


def create_compensation_rule(
    db: Session,
    principal: Principal,
    payload: CompensationRuleCreate,
) -> CompensationRuleRead:
    validate_compensation_rule_payload(payload)
    rule = CompensationRule(
        organization_id=principal.organization_id,
        name=payload.name,
        role_key=payload.role_key,
        basis_points=payload.basis_points,
        applies_to=payload.applies_to,
        effective_start_at=payload.effective_start_at or datetime.now(UTC),
        effective_end_at=payload.effective_end_at,
        is_active=payload.is_active,
        notes=payload.notes,
    )
    db.add(rule)
    db.flush()
    add_finance_audit(
        db,
        principal,
        "finance.compensation_rule_create",
        "compensation_rule",
        rule.id,
        {
            "name": rule.name,
            "role_key": rule.role_key,
            "basis_points": rule.basis_points,
            "applies_to": rule.applies_to,
            "is_active": rule.is_active,
        },
    )
    recalculate_compensation(db, principal)
    db.commit()
    db.refresh(rule)
    return rule_to_read(rule)


def create_marketing_spend(
    db: Session,
    principal: Principal,
    payload: MarketingSpendCreate,
) -> MarketingSpendRead:
    spend = MarketingSpend(
        organization_id=principal.organization_id,
        source=payload.source,
        campaign=payload.campaign,
        amount_cents=payload.amount_cents,
        spend_month_at=payload.spend_month_at or datetime.now(UTC),
        notes=payload.notes,
    )
    db.add(spend)
    db.flush()
    add_finance_audit(
        db,
        principal,
        "finance.marketing_spend_create",
        "marketing_spend",
        spend.id,
        {
            "source": spend.source,
            "campaign": spend.campaign,
            "amount_cents": spend.amount_cents,
        },
    )
    db.commit()
    db.refresh(spend)
    return marketing_spend_to_read(spend)


def recalculate_compensation(db: Session, principal: Principal) -> None:
    db.execute(
        delete(CompensationCalculation).where(
            CompensationCalculation.organization_id == principal.organization_id
        )
    )
    revenue_records = db.scalars(
        select(RevenueRecord).where(
            RevenueRecord.organization_id == principal.organization_id,
            RevenueRecord.status == "collected",
        )
    ).all()
    rules = db.scalars(
        select(CompensationRule).where(
            CompensationRule.organization_id == principal.organization_id,
            CompensationRule.is_active.is_(True),
        )
    ).all()
    for record in revenue_records:
        for rule in rules:
            if not rule_is_effective(rule, record.received_at):
                continue
            basis_amount = get_compensation_basis(db, principal, record, rule)
            calculated_amount = round(basis_amount * rule.basis_points / 10000)
            db.add(
                CompensationCalculation(
                    organization_id=principal.organization_id,
                    revenue_record_id=record.id,
                    compensation_rule_id=rule.id,
                    role_key=rule.role_key,
                    basis_amount_cents=basis_amount,
                    basis_points=rule.basis_points,
                    calculated_amount_cents=calculated_amount,
                    status="calculated",
                    notes=None,
                )
            )


def get_finance_summary(db: Session, principal: Principal) -> FinanceSummary:
    collected_revenue = sum_int(
        db,
        select(func.coalesce(func.sum(RevenueRecord.amount_cents), 0)).where(
            RevenueRecord.organization_id == principal.organization_id,
            RevenueRecord.status == "collected",
        ),
    )
    pending_revenue = sum_int(
        db,
        select(func.coalesce(func.sum(RevenueRecord.amount_cents), 0)).where(
            RevenueRecord.organization_id == principal.organization_id,
            RevenueRecord.status == "pending",
        ),
    )
    deductions = sum_int(
        db,
        select(func.coalesce(func.sum(DealDeduction.amount_cents), 0)).where(
            DealDeduction.organization_id == principal.organization_id
        ),
    )
    compensation = sum_int(
        db,
        select(func.coalesce(func.sum(CompensationCalculation.calculated_amount_cents), 0)).where(
            CompensationCalculation.organization_id == principal.organization_id
        ),
    )
    marketing_spend = sum_int(
        db,
        select(func.coalesce(func.sum(MarketingSpend.amount_cents), 0)).where(
            MarketingSpend.organization_id == principal.organization_id
        ),
    )
    net_revenue = collected_revenue - deductions
    return FinanceSummary(
        collected_revenue_cents=collected_revenue,
        pending_revenue_cents=pending_revenue,
        deductions_cents=deductions,
        net_revenue_cents=net_revenue,
        compensation_cents=compensation,
        marketing_spend_cents=marketing_spend,
        company_net_cents=net_revenue - compensation - marketing_spend,
    )


def resolve_finance_context(
    db: Session,
    principal: Principal,
    lead_id: UUID | None,
) -> tuple[Lead | None, Deal | None, Transaction | None]:
    if lead_id is None:
        return None, None, None
    lead = db.scalar(
        select(Lead).where(
            Lead.organization_id == principal.organization_id,
            Lead.id == lead_id,
        )
    )
    if lead is None:
        raise ValueError("Lead not found.")
    deal = db.scalar(
        select(Deal)
        .where(
            Deal.organization_id == principal.organization_id,
            Deal.lead_id == lead.id,
        )
        .order_by(Deal.created_at.desc())
    )
    transaction = db.scalar(
        select(Transaction)
        .where(
            Transaction.organization_id == principal.organization_id,
            Transaction.lead_id == lead.id,
        )
        .order_by(Transaction.created_at.desc())
    )
    return lead, deal, transaction


def get_compensation_basis(
    db: Session,
    principal: Principal,
    record: RevenueRecord,
    rule: CompensationRule,
) -> int:
    if rule.applies_to == "gross_revenue":
        return record.amount_cents
    deductions = get_linked_deductions(db, principal, record)
    return max(record.amount_cents - deductions, 0)


def get_linked_deductions(db: Session, principal: Principal, record: RevenueRecord) -> int:
    query = select(func.coalesce(func.sum(DealDeduction.amount_cents), 0)).where(
        DealDeduction.organization_id == principal.organization_id
    )
    if record.deal_id is not None:
        query = query.where(DealDeduction.deal_id == record.deal_id)
    elif record.transaction_id is not None:
        query = query.where(DealDeduction.transaction_id == record.transaction_id)
    elif record.lead_id is not None:
        query = query.where(DealDeduction.lead_id == record.lead_id)
    else:
        return 0
    return sum_int(db, query)


def rule_is_effective(rule: CompensationRule, received_at: datetime) -> bool:
    effective_start = comparable_datetime(rule.effective_start_at)
    effective_end = (
        comparable_datetime(rule.effective_end_at) if rule.effective_end_at is not None else None
    )
    received = comparable_datetime(received_at)
    return effective_start <= received and (
        effective_end is None or effective_end >= received
    )


def comparable_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.replace(tzinfo=None)


def validate_revenue_payload(payload: RevenueCreate) -> None:
    if payload.source not in REVENUE_SOURCES:
        raise ValueError(f"Unsupported revenue source: {payload.source}")
    if payload.status not in REVENUE_STATUSES:
        raise ValueError(f"Unsupported revenue status: {payload.status}")


def validate_compensation_rule_payload(payload: CompensationRuleCreate) -> None:
    if payload.applies_to not in COMPENSATION_APPLIES_TO:
        raise ValueError(f"Unsupported compensation basis: {payload.applies_to}")
    if (
        payload.effective_start_at is not None
        and payload.effective_end_at is not None
        and payload.effective_start_at > payload.effective_end_at
    ):
        raise ValueError("Compensation rule start date cannot be after end date.")


def add_finance_audit(
    db: Session,
    principal: Principal,
    action: str,
    entity_type: str,
    entity_id: UUID,
    new_value: dict[str, object],
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
            new_value=new_value,
            reason="Manual finance entry",
        )
    )


def get_lead_context(
    db: Session,
    principal: Principal,
    lead_ids: list[UUID | None],
) -> dict[UUID | None, tuple[str | None, str | None]]:
    ids = [lead_id for lead_id in lead_ids if lead_id is not None]
    if not ids:
        return {}
    rows = db.execute(
        select(
            Lead.id,
            Contact.legal_name,
            Property.street_address,
            Property.city,
            Property.state,
            Property.postal_code,
        )
        .join(Contact, Contact.id == Lead.contact_id)
        .join(Property, Property.id == Lead.property_id)
        .where(
            Lead.organization_id == principal.organization_id,
            Lead.id.in_(ids),
        )
    ).all()
    return {
        lead_id: (
            seller_name,
            f"{street_address}, {city}, {state} {postal_code}",
        )
        for lead_id, seller_name, street_address, city, state, postal_code in rows
    }


def revenue_to_read(
    record: RevenueRecord,
    context: tuple[str | None, str | None] | None,
) -> RevenueRead:
    seller_name, property_address = context or (None, None)
    return RevenueRead(
        id=record.id,
        lead_id=record.lead_id,
        deal_id=record.deal_id,
        transaction_id=record.transaction_id,
        seller_name=seller_name,
        property_address=property_address,
        source=record.source,
        status=record.status,
        amount_cents=record.amount_cents,
        received_at=record.received_at,
        notes=record.notes,
        created_at=record.created_at,
    )


def deduction_to_read(deduction: DealDeduction) -> DealDeductionRead:
    return DealDeductionRead(
        id=deduction.id,
        lead_id=deduction.lead_id,
        deal_id=deduction.deal_id,
        transaction_id=deduction.transaction_id,
        category=deduction.category,
        amount_cents=deduction.amount_cents,
        incurred_at=deduction.incurred_at,
        notes=deduction.notes,
        created_at=deduction.created_at,
    )


def rule_to_read(rule: CompensationRule) -> CompensationRuleRead:
    return CompensationRuleRead(
        id=rule.id,
        name=rule.name,
        role_key=rule.role_key,
        basis_points=rule.basis_points,
        applies_to=rule.applies_to,
        effective_start_at=rule.effective_start_at,
        effective_end_at=rule.effective_end_at,
        is_active=rule.is_active,
        notes=rule.notes,
        created_at=rule.created_at,
    )


def calculation_to_read(calculation: CompensationCalculation) -> CompensationCalculationRead:
    return CompensationCalculationRead(
        id=calculation.id,
        revenue_record_id=calculation.revenue_record_id,
        compensation_rule_id=calculation.compensation_rule_id,
        role_key=calculation.role_key,
        basis_amount_cents=calculation.basis_amount_cents,
        basis_points=calculation.basis_points,
        calculated_amount_cents=calculation.calculated_amount_cents,
        status=calculation.status,
        notes=calculation.notes,
        created_at=calculation.created_at,
    )


def marketing_spend_to_read(spend: MarketingSpend) -> MarketingSpendRead:
    return MarketingSpendRead(
        id=spend.id,
        source=spend.source,
        campaign=spend.campaign,
        amount_cents=spend.amount_cents,
        spend_month_at=spend.spend_month_at,
        notes=spend.notes,
        created_at=spend.created_at,
    )


def sum_int(db: Session, query: Select[tuple[int]]) -> int:
    return int(db.scalar(query) or 0)
