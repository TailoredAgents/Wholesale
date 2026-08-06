from calendar import monthrange
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import Select, delete, func, select
from sqlalchemy.orm import InstrumentedAttribute, Session
from sqlalchemy.sql.elements import ColumnElement

from app.core.auth import Principal
from app.models.foundation import (
    AccountingAccount,
    AccountingPeriod,
    AccountingPostingRule,
    AccountingProfile,
    AccountingSourceLink,
    ActivityEvent,
    AuditEvent,
    CompensationCalculation,
    CompensationRule,
    Contact,
    Deal,
    DealDeduction,
    DealPayout,
    DealReconciliation,
    FinancialObligation,
    JournalEntry,
    JournalLine,
    Lead,
    MarketingSpend,
    Property,
    RevenueRecord,
    Transaction,
    TransactionDocument,
    VendorBill,
    VendorBillLine,
)
from app.schemas.finance import (
    AccountingAccountRead,
    AccountingLedgerOverview,
    AccountingLedgerSummary,
    AccountingPeriodCreate,
    AccountingPeriodRead,
    AccountingPeriodStatusUpdate,
    AccountingPostingRuleRead,
    AccountingPostingWorkspaceRead,
    AccountingProfileRead,
    AccountingProfileUpdate,
    AccountingSetupRead,
    AccountingSourceDraftRequest,
    AccountingSourceItemRead,
    CompensationCalculationRead,
    CompensationRuleCreate,
    CompensationRuleRead,
    DealDeductionCreate,
    DealDeductionRead,
    DealPayoutStatusUpdate,
    FinanceOverview,
    FinanceSummary,
    FinancialObligationCreate,
    FinancialObligationRead,
    FinancialObligationStatusUpdate,
    JournalDecision,
    JournalEntryCreate,
    JournalEntryRead,
    JournalLineCreate,
    JournalLineRead,
    JournalReverseCreate,
    MarketingSpendCreate,
    MarketingSpendRead,
    RevenueCreate,
    RevenueRead,
    TaxReadinessRead,
)

REVENUE_STATUSES = {"pending", "collected", "void"}
REVENUE_SOURCES = {"assignment_fee", "double_close", "consulting_fee", "other"}
DEDUCTION_CATEGORIES = {"title", "attorney", "transaction", "marketing", "seller_credit", "other"}
COMPENSATION_APPLIES_TO = {"gross_revenue", "net_revenue"}
ENTITY_TYPES = {
    "undecided",
    "sole_proprietor",
    "single_member_llc",
    "multi_member_llc",
    "corporation",
}
FEDERAL_TAX_CLASSIFICATIONS = {
    "undecided",
    "disregarded_entity",
    "partnership",
    "s_corporation",
    "c_corporation",
}
ACCOUNTING_METHODS = {"undecided", "cash", "accrual"}
OWNER_COMPENSATION_TREATMENTS = {
    "pending",
    "owner_draw",
    "payroll",
    "guaranteed_payment",
}
ACCOUNTING_PERIOD_STATUSES = {"open", "review", "closed", "locked"}
OBLIGATION_TYPES = {
    "vendor_payable",
    "contractor_payable",
    "reimbursement",
    "owner_distribution",
}
OBLIGATION_STATUSES = {"draft", "approved", "payable", "paid", "disputed", "reversed"}
PAYMENT_TRANSITIONS = {
    "draft": {"approved"},
    "approved": {"payable", "disputed"},
    "payable": {"paid", "disputed"},
    "disputed": {"approved", "reversed"},
    "paid": {"reversed"},
    "reversed": set(),
}

# The operating-model acquisition reserve is intentionally absent. It is a
# profitability target, not an accounting expense without an underlying cost.
DEFAULT_WHOLESALE_ACCOUNTS = (
    (
        "1000",
        "operating_cash",
        "Operating Cash",
        "asset",
        "cash",
        "debit",
        "cash",
        False,
        "Primary operating bank balance.",
    ),
    (
        "1010",
        "tax_reserve_cash",
        "Tax Reserve Cash",
        "asset",
        "cash",
        "debit",
        "cash",
        False,
        "Cash reserved by management for expected tax payments.",
    ),
    (
        "1100",
        "settlement_receivable",
        "Settlement Receivable",
        "asset",
        "receivable",
        "debit",
        "receivable",
        True,
        "Funded closing proceeds due to Stonegate but not yet received.",
    ),
    (
        "1200",
        "earnest_money_deposits",
        "Earnest Money Deposits",
        "asset",
        "deposit",
        "debit",
        "deposit",
        True,
        "Stonegate earnest money held by a closing attorney or title company.",
    ),
    (
        "1300",
        "real_estate_inventory",
        "Real Estate Inventory",
        "asset",
        "inventory",
        "debit",
        "inventory",
        True,
        "Property cost held for resale in a double-close transaction.",
    ),
    (
        "1310",
        "capitalized_deal_costs",
        "Capitalized Acquisition and Closing Costs",
        "asset",
        "inventory_cost",
        "debit",
        "inventory",
        True,
        "Deal costs capitalized into property inventory when required.",
    ),
    (
        "1400",
        "prepaid_expenses",
        "Prepaid Expenses",
        "asset",
        "prepaid",
        "debit",
        "prepaid_expense",
        False,
        "Payments that benefit a future accounting period.",
    ),
    (
        "2000",
        "accounts_payable",
        "Accounts Payable",
        "liability",
        "payable",
        "credit",
        "accounts_payable",
        False,
        "Approved vendor obligations not yet paid.",
    ),
    (
        "2100",
        "commission_payable",
        "Commission Payable",
        "liability",
        "payable",
        "credit",
        "compensation",
        True,
        "Approved deal commissions payable after cleared proceeds.",
    ),
    (
        "2200",
        "contractor_payable",
        "Contractor Payable",
        "liability",
        "payable",
        "credit",
        "contract_labor",
        False,
        "Approved contractor obligations not yet paid.",
    ),
    (
        "2300",
        "transactional_funding_payable",
        "Transactional Funding Payable",
        "liability",
        "financing",
        "credit",
        "deal_financing",
        True,
        "Short-term transactional funding owed on a double close.",
    ),
    (
        "2400",
        "credit_cards",
        "Credit Cards",
        "liability",
        "credit_card",
        "credit",
        "credit_card",
        False,
        "Company credit-card balances.",
    ),
    (
        "3000",
        "owner_contributions",
        "Owner Contributions",
        "equity",
        "contribution",
        "credit",
        "equity",
        False,
        "Owner capital contributed to the company.",
    ),
    (
        "3100",
        "owner_distributions",
        "Owner Distributions",
        "equity",
        "distribution",
        "debit",
        "owner_distribution",
        False,
        "Owner withdrawals that are not operating expenses.",
    ),
    (
        "3200",
        "retained_earnings",
        "Retained Earnings",
        "equity",
        "retained_earnings",
        "credit",
        "equity",
        False,
        "Accumulated company earnings.",
    ),
    (
        "4000",
        "assignment_fee_revenue",
        "Assignment Fee Revenue",
        "revenue",
        "assignment",
        "credit",
        "gross_receipts",
        True,
        "Revenue earned from assigning a purchase contract.",
    ),
    (
        "4100",
        "wholesale_property_sale_revenue",
        "Wholesale Property Sale Revenue",
        "revenue",
        "property_sale",
        "credit",
        "gross_receipts",
        True,
        "Gross resale proceeds from a double-close transaction.",
    ),
    (
        "4200",
        "jv_revenue",
        "Joint Venture Revenue",
        "revenue",
        "joint_venture",
        "credit",
        "gross_receipts",
        True,
        "Stonegate revenue from a documented joint-venture transaction.",
    ),
    (
        "4900",
        "other_operating_revenue",
        "Other Operating Revenue",
        "revenue",
        "other",
        "credit",
        "other_income",
        False,
        "Operating revenue outside normal assignment, resale, or JV activity.",
    ),
    (
        "5000",
        "property_acquisition_cost",
        "Property Acquisition Cost",
        "cost_of_revenue",
        "inventory_cost",
        "debit",
        "cost_of_goods_sold",
        True,
        "Acquisition basis released from inventory when a double-close property is sold.",
    ),
    (
        "5100",
        "deal_closing_costs",
        "Deal Closing Costs",
        "cost_of_revenue",
        "closing_cost",
        "debit",
        "cost_of_goods_sold",
        True,
        "Closing costs directly attributable to a completed deal.",
    ),
    (
        "5200",
        "transactional_funding_fees",
        "Transactional Funding Fees",
        "cost_of_revenue",
        "financing_cost",
        "debit",
        "cost_of_goods_sold",
        True,
        "Direct transactional funding charges for a double close.",
    ),
    (
        "5300",
        "jv_partner_payments",
        "Joint Venture Partner Payments",
        "cost_of_revenue",
        "partner_payment",
        "debit",
        "cost_of_goods_sold",
        True,
        "Documented partner share attributable to a joint-venture deal.",
    ),
    (
        "5400",
        "buyer_credits_refunds",
        "Buyer Credits and Refunds",
        "cost_of_revenue",
        "contra_revenue",
        "debit",
        "returns_allowances",
        True,
        "Approved deal-specific buyer credits or revenue refunds.",
    ),
    (
        "5500",
        "deal_commissions",
        "Deal Commissions",
        "cost_of_revenue",
        "commission",
        "debit",
        "compensation",
        True,
        "Approved commissions attributable to funded deal revenue.",
    ),
    (
        "6000",
        "advertising",
        "Advertising",
        "expense",
        "marketing",
        "debit",
        "advertising",
        False,
        "Paid media, direct mail, and other advertising.",
    ),
    (
        "6010",
        "lead_lists_data",
        "Lead Lists and Data",
        "expense",
        "marketing_data",
        "debit",
        "advertising",
        False,
        "Prospect lists, property data, skip tracing, and campaign data.",
    ),
    (
        "6020",
        "prospecting_labor",
        "VA and Prospecting Labor",
        "expense",
        "contract_labor",
        "debit",
        "contract_labor",
        False,
        "Cold-calling and outreach labor not tied to a funded-deal commission.",
    ),
    (
        "6100",
        "software_subscriptions",
        "Software and Subscriptions",
        "expense",
        "software",
        "debit",
        "office_expense",
        False,
        "Business software, hosting, data tools, and subscriptions.",
    ),
    (
        "6200",
        "professional_services",
        "Legal and Accounting",
        "expense",
        "professional_services",
        "debit",
        "legal_professional",
        False,
        "Attorneys, tax professionals, bookkeeping, and accounting services.",
    ),
    (
        "6300",
        "insurance",
        "Insurance",
        "expense",
        "insurance",
        "debit",
        "insurance",
        False,
        "Business insurance premiums.",
    ),
    (
        "6400",
        "office_expense",
        "Office Expense",
        "expense",
        "office",
        "debit",
        "office_expense",
        False,
        "Ordinary office supplies and operating costs.",
    ),
    (
        "6500",
        "communications",
        "Telephone and Communications",
        "expense",
        "communications",
        "debit",
        "utilities",
        False,
        "Business phone, SMS, email, and internet communication costs.",
    ),
    (
        "6600",
        "travel_mileage",
        "Travel and Mileage",
        "expense",
        "travel",
        "debit",
        "travel",
        False,
        "Documented business travel and vehicle mileage.",
    ),
    (
        "6700",
        "bank_merchant_fees",
        "Bank and Merchant Fees",
        "expense",
        "bank_fee",
        "debit",
        "bank_fees",
        False,
        "Banking and payment-processing fees.",
    ),
    (
        "6800",
        "payroll_contract_labor",
        "Payroll and Contract Labor",
        "expense",
        "labor",
        "debit",
        "wages_contract_labor",
        False,
        "Non-deal payroll and contractor labor.",
    ),
    (
        "6900",
        "other_operating_expense",
        "Other Operating Expense",
        "expense",
        "other",
        "debit",
        "other_deduction",
        False,
        "Reviewed operating costs without a more specific account.",
    ),
)

DEFAULT_POSTING_RULES = (
    (
        "assignment_revenue_collected",
        "Collected assignment revenue",
        "revenue_record",
        "collected",
        "cash_revenue",
        "operating_cash",
        "assignment_fee_revenue",
        True,
        "Draft cash-basis assignment revenue after funded-deal evidence and reconciliation "
        "are complete.",
    ),
    (
        "double_close_revenue_collected",
        "Collected double-close proceeds",
        "revenue_record",
        "collected",
        "cash_revenue",
        "operating_cash",
        "wholesale_property_sale_revenue",
        True,
        "Draft gross double-close sale proceeds. Property basis and direct costs remain "
        "separate source entries.",
    ),
    (
        "other_revenue_collected",
        "Collected other operating revenue",
        "revenue_record",
        "collected",
        "cash_revenue",
        "operating_cash",
        "other_operating_revenue",
        True,
        "Draft collected consulting or other approved operating revenue without classifying "
        "it as an assignment fee.",
    ),
    (
        "deal_deduction_paid",
        "Paid deal deduction",
        "deal_deduction",
        "paid",
        "paid_expense",
        "other_operating_expense",
        "operating_cash",
        False,
        "Draft a paid deal cost using the approved category-to-account mapping.",
    ),
    (
        "marketing_spend_paid",
        "Paid marketing and operating spend",
        "marketing_spend",
        "paid",
        "paid_expense",
        "advertising",
        "operating_cash",
        False,
        "Draft paid marketing, software, data, or prospecting costs using source-aware "
        "account mapping.",
    ),
    (
        "commission_accrued",
        "Approved commission payable",
        "deal_payout",
        "approved",
        "commission_accrual",
        "deal_commissions",
        "commission_payable",
        True,
        "Draft an approved funded-deal commission as a payable without initiating payment.",
    ),
    (
        "commission_paid",
        "Commission payment",
        "deal_payout",
        "paid",
        "liability_payment",
        "commission_payable",
        "operating_cash",
        True,
        "Draft settlement of a commission payable after a payment reference is recorded.",
    ),
    (
        "obligation_accrued",
        "Approved payable or reimbursement",
        "financial_obligation",
        "approved",
        "obligation_accrual",
        "other_operating_expense",
        "accounts_payable",
        True,
        "Draft an approved vendor, contractor, or reimbursement obligation as a payable.",
    ),
    (
        "obligation_paid",
        "Payable settlement",
        "financial_obligation",
        "paid",
        "liability_payment",
        "accounts_payable",
        "operating_cash",
        True,
        "Draft settlement of an approved payable after payment evidence is recorded.",
    ),
    (
        "owner_distribution_paid",
        "Owner distribution payment",
        "financial_obligation",
        "paid",
        "owner_distribution",
        "owner_distributions",
        "operating_cash",
        True,
        "Draft an owner distribution as equity activity, never as an operating expense.",
    ),
)


def get_accounting_setup(
    db: Session,
    principal: Principal,
) -> AccountingSetupRead:
    profile = ensure_accounting_foundation(db, principal)
    accounts = list(
        db.scalars(
            select(AccountingAccount)
            .where(
                AccountingAccount.organization_id == principal.organization_id,
                AccountingAccount.policy_version == profile.policy_version,
            )
            .order_by(AccountingAccount.code)
        ).all()
    )
    readiness_gaps = accounting_readiness_gaps(profile)
    deduction_records = list(
        db.scalars(
            select(DealDeduction).where(DealDeduction.organization_id == principal.organization_id)
        ).all()
    )
    spend_records = list(
        db.scalars(
            select(MarketingSpend).where(
                MarketingSpend.organization_id == principal.organization_id
            )
        ).all()
    )
    source_records = len(deduction_records) + len(spend_records)
    missing_notes = sum(
        1 for item in deduction_records if not item.notes or not item.notes.strip()
    ) + sum(1 for item in spend_records if not item.notes or not item.notes.strip())
    tax_gaps = list(readiness_gaps)
    if not source_records:
        tax_gaps.append("No expense or deal-deduction records are available for review.")
    elif missing_notes:
        tax_gaps.append(f"{missing_notes} source records do not include a business-purpose note.")
    readiness_score = max(0, 100 - (20 * len(readiness_gaps)))
    tax_score = max(0, 100 - (15 * len(tax_gaps)))
    return AccountingSetupRead(
        profile=accounting_profile_to_read(profile),
        accounts=[accounting_account_to_read(account) for account in accounts],
        readiness_score=readiness_score,
        readiness_gaps=readiness_gaps,
        policy_notes=[
            "Assignment fees are revenue; double-close resale proceeds and property basis "
            "are tracked separately.",
            "Earnest money remains an asset until applied, returned, or forfeited.",
            "Commissions become payable only after funded proceeds and approved reconciliation.",
            "The acquisition reserve is a management target, not a ledger expense without "
            "a real underlying cost.",
        ],
        tax_copilot=TaxReadinessRead(
            capability_key="finance.tax_review",
            mode="draft_only",
            status="enabled",
            readiness_score=tax_score,
            readiness_gaps=tax_gaps,
            review_scope=[
                "Classify recorded costs against the approved chart of accounts.",
                "Identify missing business purpose, receipt, or deal linkage.",
                "Separate current expenses, capitalized deal costs, inventory, and owner activity.",
                "Prepare an evidence-linked review package for the owner and tax professional.",
            ],
            prohibited_actions=[
                "File a tax return or submit a tax election.",
                "Promise that an item is deductible.",
                "Post, delete, or alter accounting entries.",
                "Move money or approve owner compensation.",
            ],
            source_records=source_records,
            records_missing_notes=missing_notes,
        ),
    )


def update_accounting_profile(
    db: Session,
    principal: Principal,
    payload: AccountingProfileUpdate,
) -> AccountingSetupRead:
    validate_accounting_profile(payload)
    profile = ensure_accounting_foundation(db, principal)
    previous = accounting_profile_snapshot(profile)
    profile.legal_entity_name = payload.legal_entity_name.strip()
    profile.entity_type = payload.entity_type
    profile.federal_tax_classification = payload.federal_tax_classification
    profile.accounting_method = payload.accounting_method
    profile.tax_year_end_month = payload.tax_year_end_month
    profile.tax_year_end_day = payload.tax_year_end_day
    profile.books_start_date = payload.books_start_date
    profile.home_state = payload.home_state.upper()
    profile.owner_compensation_treatment = payload.owner_compensation_treatment
    profile.notes = payload.notes
    profile.updated_by_user_id = principal.user_id
    profile.status = "ready" if not accounting_readiness_gaps(profile) else "needs_setup"
    db.flush()
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="finance.accounting_profile_update",
            entity_type="accounting_profile",
            entity_id=profile.id,
            previous_value=previous,
            new_value=accounting_profile_snapshot(profile),
            reason="Accounting policy setup",
        )
    )
    db.commit()
    return get_accounting_setup(db, principal)


def ensure_accounting_foundation(
    db: Session,
    principal: Principal,
) -> AccountingProfile:
    profile = db.scalar(
        select(AccountingProfile).where(
            AccountingProfile.organization_id == principal.organization_id
        )
    )
    created = False
    if profile is None:
        profile = AccountingProfile(
            organization_id=principal.organization_id,
            legal_entity_name="Stonegate Home Buyers",
            entity_type="undecided",
            federal_tax_classification="undecided",
            accounting_method="cash",
            tax_year_end_month=12,
            tax_year_end_day=31,
            books_start_date=None,
            home_state="GA",
            currency="USD",
            owner_compensation_treatment="pending",
            status="needs_setup",
            policy_version=1,
            tax_rule_year=datetime.now(UTC).year,
            notes=None,
            updated_by_user_id=principal.user_id,
        )
        db.add(profile)
        db.flush()
        created = True

    existing_keys = set(
        db.scalars(
            select(AccountingAccount.system_key).where(
                AccountingAccount.organization_id == principal.organization_id,
                AccountingAccount.policy_version == profile.policy_version,
            )
        ).all()
    )
    for (
        code,
        system_key,
        name,
        account_type,
        subtype,
        normal_balance,
        tax_category,
        deal_tracking,
        description,
    ) in DEFAULT_WHOLESALE_ACCOUNTS:
        if system_key in existing_keys:
            continue
        db.add(
            AccountingAccount(
                organization_id=principal.organization_id,
                accounting_profile_id=profile.id,
                policy_version=profile.policy_version,
                code=code,
                system_key=system_key,
                name=name,
                account_type=account_type,
                subtype=subtype,
                normal_balance=normal_balance,
                tax_category=tax_category,
                deal_tracking=deal_tracking,
                is_active=True,
                description=description,
            )
        )
        existing_keys.add(system_key)
        created = True
    if created:
        db.add(
            AuditEvent(
                organization_id=principal.organization_id,
                actor_user_id=principal.user_id,
                actor_type="system",
                action="finance.accounting_foundation_install",
                entity_type="accounting_profile",
                entity_id=profile.id,
                previous_value=None,
                new_value={
                    "policy_version": profile.policy_version,
                    "account_count": len(existing_keys),
                },
                reason="F6 wholesaling accounting foundation",
            )
        )
        db.commit()
        db.refresh(profile)
    return profile


def validate_accounting_profile(payload: AccountingProfileUpdate) -> None:
    if payload.entity_type not in ENTITY_TYPES:
        raise ValueError("Unsupported legal entity type.")
    if payload.federal_tax_classification not in FEDERAL_TAX_CLASSIFICATIONS:
        raise ValueError("Unsupported federal tax classification.")
    if payload.accounting_method not in ACCOUNTING_METHODS:
        raise ValueError("Unsupported accounting method.")
    if payload.owner_compensation_treatment not in OWNER_COMPENSATION_TREATMENTS:
        raise ValueError("Unsupported owner compensation treatment.")
    try:
        datetime(
            2024,
            payload.tax_year_end_month,
            payload.tax_year_end_day,
            tzinfo=UTC,
        )
    except ValueError as exc:
        raise ValueError("Tax year end is not a valid calendar date.") from exc


def accounting_readiness_gaps(profile: AccountingProfile) -> list[str]:
    gaps: list[str] = []
    if profile.entity_type == "undecided":
        gaps.append("Confirm the legal entity type.")
    if profile.federal_tax_classification == "undecided":
        gaps.append("Confirm the federal tax classification with the tax professional.")
    if profile.accounting_method == "undecided":
        gaps.append("Confirm the accounting method.")
    if profile.books_start_date is None:
        gaps.append("Set the date Stonegate's internal books begin.")
    if profile.owner_compensation_treatment == "pending":
        gaps.append("Confirm owner compensation treatment for the selected tax classification.")
    return gaps


def accounting_profile_snapshot(profile: AccountingProfile) -> dict[str, object]:
    return {
        "legal_entity_name": profile.legal_entity_name,
        "entity_type": profile.entity_type,
        "federal_tax_classification": profile.federal_tax_classification,
        "accounting_method": profile.accounting_method,
        "tax_year_end_month": profile.tax_year_end_month,
        "tax_year_end_day": profile.tax_year_end_day,
        "books_start_date": (
            profile.books_start_date.isoformat() if profile.books_start_date else None
        ),
        "home_state": profile.home_state,
        "owner_compensation_treatment": profile.owner_compensation_treatment,
        "status": profile.status,
    }


def accounting_profile_to_read(profile: AccountingProfile) -> AccountingProfileRead:
    return AccountingProfileRead(
        id=profile.id,
        legal_entity_name=profile.legal_entity_name,
        entity_type=profile.entity_type,
        federal_tax_classification=profile.federal_tax_classification,
        accounting_method=profile.accounting_method,
        tax_year_end_month=profile.tax_year_end_month,
        tax_year_end_day=profile.tax_year_end_day,
        books_start_date=profile.books_start_date,
        home_state=profile.home_state,
        currency=profile.currency,
        owner_compensation_treatment=profile.owner_compensation_treatment,
        status=profile.status,
        policy_version=profile.policy_version,
        tax_rule_year=profile.tax_rule_year,
        notes=profile.notes,
        updated_at=profile.updated_at,
    )


def accounting_account_to_read(account: AccountingAccount) -> AccountingAccountRead:
    return AccountingAccountRead(
        id=account.id,
        policy_version=account.policy_version,
        code=account.code,
        system_key=account.system_key,
        name=account.name,
        account_type=account.account_type,
        subtype=account.subtype,
        normal_balance=account.normal_balance,
        tax_category=account.tax_category,
        deal_tracking=account.deal_tracking,
        is_active=account.is_active,
        description=account.description,
    )


def get_accounting_ledger(
    db: Session,
    principal: Principal,
) -> AccountingLedgerOverview:
    profile = ensure_accounting_foundation(db, principal)
    ensure_accounting_period(db, principal, date.today(), profile)
    periods = list(
        db.scalars(
            select(AccountingPeriod)
            .where(AccountingPeriod.organization_id == principal.organization_id)
            .order_by(AccountingPeriod.period_start_at.desc())
            .limit(24)
        ).all()
    )
    entries = list(
        db.scalars(
            select(JournalEntry)
            .where(JournalEntry.organization_id == principal.organization_id)
            .order_by(JournalEntry.entry_date.desc(), JournalEntry.created_at.desc())
            .limit(100)
        ).all()
    )
    entry_ids = [entry.id for entry in entries]
    lines = (
        list(
            db.scalars(
                select(JournalLine)
                .where(JournalLine.journal_entry_id.in_(entry_ids))
                .order_by(JournalLine.journal_entry_id, JournalLine.line_number)
            ).all()
        )
        if entry_ids
        else []
    )
    account_ids = {line.accounting_account_id for line in lines}
    accounts = (
        {
            account.id: account
            for account in db.scalars(
                select(AccountingAccount).where(AccountingAccount.id.in_(account_ids))
            ).all()
        }
        if account_ids
        else {}
    )
    lines_by_entry: dict[UUID, list[JournalLine]] = {}
    for line in lines:
        lines_by_entry.setdefault(line.journal_entry_id, []).append(line)
    reversal_by_original = {
        entry.reverses_entry_id: entry.id
        for entry in entries
        if entry.reverses_entry_id is not None
    }
    period_counts: dict[UUID, dict[str, int]] = {
        period.id: {"draft": 0, "approved": 0, "posted": 0} for period in periods
    }
    for period_id, status, count in db.execute(
        select(
            JournalEntry.accounting_period_id,
            JournalEntry.status,
            func.count(JournalEntry.id),
        )
        .where(JournalEntry.organization_id == principal.organization_id)
        .group_by(JournalEntry.accounting_period_id, JournalEntry.status)
    ).all():
        counts = period_counts.get(period_id)
        if counts is not None and status in counts:
            counts[status] = int(count)
    status_summary = {
        status: (int(count), int(amount or 0))
        for status, count, amount in db.execute(
            select(
                JournalEntry.status,
                func.count(JournalEntry.id),
                func.sum(JournalEntry.total_debits_cents),
            )
            .where(JournalEntry.organization_id == principal.organization_id)
            .group_by(JournalEntry.status)
        ).all()
    }
    return AccountingLedgerOverview(
        summary=AccountingLedgerSummary(
            draft_entries=status_summary.get("draft", (0, 0))[0],
            approved_entries=status_summary.get("approved", (0, 0))[0],
            posted_entries=status_summary.get("posted", (0, 0))[0],
            reversed_entries=status_summary.get("reversed", (0, 0))[0],
            posted_amount_cents=(
                status_summary.get("posted", (0, 0))[1] + status_summary.get("reversed", (0, 0))[1]
            ),
            out_of_balance_entries=int(
                db.scalar(
                    select(func.count(JournalEntry.id)).where(
                        JournalEntry.organization_id == principal.organization_id,
                        JournalEntry.total_debits_cents != JournalEntry.total_credits_cents,
                    )
                )
                or 0
            ),
        ),
        periods=[accounting_period_to_read(period, period_counts[period.id]) for period in periods],
        entries=[
            journal_entry_to_read(
                entry,
                lines_by_entry.get(entry.id, []),
                accounts,
                reversal_by_original.get(entry.id),
            )
            for entry in entries
        ],
    )


def create_accounting_period(
    db: Session,
    principal: Principal,
    payload: AccountingPeriodCreate,
) -> AccountingPeriodRead:
    year, month = (int(part) for part in payload.period_key.split("-"))
    profile = ensure_accounting_foundation(db, principal)
    period = ensure_accounting_period(
        db,
        principal,
        date(year, month, 1),
        profile,
    )
    db.commit()
    return accounting_period_to_read(
        period,
        accounting_period_entry_counts(db, principal, period.id),
    )


def create_journal_entry(
    db: Session,
    principal: Principal,
    payload: JournalEntryCreate,
    *,
    commit: bool = True,
) -> JournalEntryRead:
    existing = db.scalar(
        select(JournalEntry).where(
            JournalEntry.organization_id == principal.organization_id,
            JournalEntry.idempotency_key == payload.idempotency_key,
        )
    )
    if existing is not None:
        return load_journal_entry_read(db, principal, existing)

    profile = ensure_accounting_foundation(db, principal)
    period = ensure_accounting_period(db, principal, payload.entry_date, profile)
    if period.status != "open":
        raise ValueError("Journal entries can only be prepared in an open period.")
    if payload.currency.upper() != profile.currency:
        raise ValueError(f"Journal currency must be {profile.currency}.")

    account_ids = {line.accounting_account_id for line in payload.lines}
    accounts = {
        account.id: account
        for account in db.scalars(
            select(AccountingAccount).where(
                AccountingAccount.organization_id == principal.organization_id,
                AccountingAccount.id.in_(account_ids),
                AccountingAccount.policy_version == profile.policy_version,
            )
        ).all()
    }
    if set(accounts) != account_ids:
        raise ValueError("Every journal line must use an active account from the current policy.")
    if any(not account.is_active for account in accounts.values()):
        raise ValueError("Inactive accounting accounts cannot receive new journal lines.")
    validate_journal_links(db, principal, payload)

    total_debits = 0
    total_credits = 0
    for line in payload.lines:
        if (line.debit_cents > 0) == (line.credit_cents > 0):
            raise ValueError(
                "Each journal line must contain either a debit or a credit, but not both."
            )
        total_debits += line.debit_cents
        total_credits += line.credit_cents
    if total_debits <= 0 or total_debits != total_credits:
        raise ValueError("Journal debits and credits must be equal and greater than zero.")

    entry_id = uuid4()
    entry = JournalEntry(
        id=entry_id,
        organization_id=principal.organization_id,
        accounting_period_id=period.id,
        entry_number=f"JE-{payload.entry_date:%Y%m}-{str(entry_id)[:8].upper()}",
        entry_date=payload.entry_date,
        status="draft",
        memo=payload.memo.strip(),
        source_type=payload.source_type.strip(),
        source_id=payload.source_id,
        posting_rule_version=payload.posting_rule_version,
        evidence_references=payload.evidence_references,
        idempotency_key=payload.idempotency_key,
        currency=profile.currency,
        total_debits_cents=total_debits,
        total_credits_cents=total_credits,
        prepared_by_user_id=principal.user_id,
        approved_by_user_id=None,
        posted_by_user_id=None,
        reversed_by_user_id=None,
        reverses_entry_id=None,
        approved_at=None,
        posted_at=None,
        reversed_at=None,
        review_notes=None,
    )
    db.add(entry)
    db.flush()
    for line_number, payload_line in enumerate(payload.lines, start=1):
        db.add(
            JournalLine(
                organization_id=principal.organization_id,
                journal_entry_id=entry.id,
                accounting_account_id=payload_line.accounting_account_id,
                line_number=line_number,
                debit_cents=payload_line.debit_cents,
                credit_cents=payload_line.credit_cents,
                memo=payload_line.memo,
                deal_id=payload_line.deal_id,
                transaction_id=payload_line.transaction_id,
            )
        )
    add_accounting_audit(
        db,
        principal,
        "finance.journal_prepare",
        entry,
        None,
        journal_snapshot(entry),
        "Balanced journal prepared for review",
    )
    if commit:
        db.commit()
        db.refresh(entry)
    else:
        db.flush()
    return load_journal_entry_read(db, principal, entry)


def approve_journal_entry(
    db: Session,
    principal: Principal,
    entry_id: UUID,
    payload: JournalDecision,
) -> JournalEntryRead | None:
    entry = get_journal_entry(db, principal, entry_id, for_update=True)
    if entry is None:
        return None
    if entry.status != "draft":
        raise ValueError("Only a draft journal can be approved.")
    period = get_accounting_period(
        db,
        principal,
        entry.accounting_period_id,
        for_update=True,
    )
    if period is None or period.status not in {"open", "review"}:
        raise ValueError("The accounting period is not open for journal review.")
    previous = journal_snapshot(entry)
    entry.status = "approved"
    entry.approved_by_user_id = principal.user_id
    entry.approved_at = datetime.now(UTC)
    entry.review_notes = payload.notes
    add_accounting_audit(
        db,
        principal,
        "finance.journal_approve",
        entry,
        previous,
        journal_snapshot(entry),
        payload.notes or "Journal approved",
    )
    db.commit()
    db.refresh(entry)
    return load_journal_entry_read(db, principal, entry)


def post_journal_entry(
    db: Session,
    principal: Principal,
    entry_id: UUID,
    payload: JournalDecision,
) -> JournalEntryRead | None:
    entry = get_journal_entry(db, principal, entry_id, for_update=True)
    if entry is None:
        return None
    if entry.status != "approved":
        raise ValueError("Only an approved journal can be posted.")
    period = get_accounting_period(
        db,
        principal,
        entry.accounting_period_id,
        for_update=True,
    )
    if period is None or period.status != "open":
        raise ValueError("Journals can only be posted in an open accounting period.")
    lines = list(
        db.scalars(select(JournalLine).where(JournalLine.journal_entry_id == entry.id)).all()
    )
    total_debits = sum(line.debit_cents for line in lines)
    total_credits = sum(line.credit_cents for line in lines)
    if (
        len(lines) < 2
        or total_debits <= 0
        or total_debits != total_credits
        or total_debits != entry.total_debits_cents
    ):
        raise ValueError("Journal balance validation failed before posting.")
    previous = journal_snapshot(entry)
    entry.status = "posted"
    entry.posted_by_user_id = principal.user_id
    entry.posted_at = datetime.now(UTC)
    if payload.notes:
        entry.review_notes = payload.notes
    if entry.reverses_entry_id is not None:
        original = get_journal_entry(db, principal, entry.reverses_entry_id)
        if original is None or original.status != "posted":
            raise ValueError("The original journal is not available for reversal.")
        original_previous = journal_snapshot(original)
        original.status = "reversed"
        original.reversed_by_user_id = principal.user_id
        original.reversed_at = entry.posted_at
        add_accounting_audit(
            db,
            principal,
            "finance.journal_reversed",
            original,
            original_previous,
            journal_snapshot(original),
            f"Reversed by {entry.entry_number}",
        )
    add_accounting_audit(
        db,
        principal,
        "finance.journal_post",
        entry,
        previous,
        journal_snapshot(entry),
        payload.notes or "Approved journal posted",
    )
    db.commit()
    db.refresh(entry)
    return load_journal_entry_read(db, principal, entry)


def create_journal_reversal(
    db: Session,
    principal: Principal,
    entry_id: UUID,
    payload: JournalReverseCreate,
) -> JournalEntryRead | None:
    original = get_journal_entry(db, principal, entry_id, for_update=True)
    if original is None:
        return None
    if original.status != "posted":
        raise ValueError("Only a posted journal can be reversed.")
    existing_reversal = db.scalar(
        select(JournalEntry).where(
            JournalEntry.organization_id == principal.organization_id,
            JournalEntry.reverses_entry_id == original.id,
        )
    )
    if existing_reversal is not None:
        return load_journal_entry_read(db, principal, existing_reversal)
    idempotent_entry = db.scalar(
        select(JournalEntry).where(
            JournalEntry.organization_id == principal.organization_id,
            JournalEntry.idempotency_key == payload.idempotency_key,
        )
    )
    if idempotent_entry is not None:
        if idempotent_entry.reverses_entry_id == original.id:
            return load_journal_entry_read(db, principal, idempotent_entry)
        raise ValueError("The reversal idempotency key is already in use.")
    original_lines = list(
        db.scalars(
            select(JournalLine)
            .where(JournalLine.journal_entry_id == original.id)
            .order_by(JournalLine.line_number)
        ).all()
    )
    reversal = create_journal_entry(
        db,
        principal,
        JournalEntryCreate(
            entry_date=payload.reversal_date,
            memo=f"Reversal of {original.entry_number}: {payload.reason}",
            source_type="journal_reversal",
            source_id=str(original.id),
            posting_rule_version=original.posting_rule_version,
            evidence_references=[
                *original.evidence_references,
                f"journal:{original.entry_number}",
            ],
            idempotency_key=payload.idempotency_key,
            currency=original.currency,
            lines=[
                JournalLineCreate(
                    accounting_account_id=line.accounting_account_id,
                    debit_cents=line.credit_cents,
                    credit_cents=line.debit_cents,
                    memo=f"Reverse line {line.line_number}",
                    deal_id=line.deal_id,
                    transaction_id=line.transaction_id,
                )
                for line in original_lines
            ],
        ),
        commit=False,
    )
    reversal_model = get_journal_entry(db, principal, reversal.id)
    if reversal_model is None:
        raise ValueError("Journal reversal could not be created.")
    reversal_model.reverses_entry_id = original.id
    reversal_model.review_notes = payload.reason
    add_accounting_audit(
        db,
        principal,
        "finance.journal_reversal_prepare",
        reversal_model,
        None,
        journal_snapshot(reversal_model),
        payload.reason,
    )
    db.commit()
    db.refresh(reversal_model)
    return load_journal_entry_read(db, principal, reversal_model)


def update_accounting_period_status(
    db: Session,
    principal: Principal,
    period_id: UUID,
    payload: AccountingPeriodStatusUpdate,
) -> AccountingPeriodRead | None:
    period = get_accounting_period(db, principal, period_id, for_update=True)
    if period is None:
        return None
    if payload.status not in ACCOUNTING_PERIOD_STATUSES:
        raise ValueError("Unsupported accounting period status.")
    if payload.status == period.status:
        return accounting_period_to_read(
            period,
            accounting_period_entry_counts(db, principal, period.id),
        )
    allowed = {
        "open": {"review"},
        "review": {"open", "closed"},
        "closed": {"open", "locked"},
        "locked": set(),
    }
    if payload.status not in allowed[period.status]:
        raise ValueError(f"Accounting period cannot move from {period.status} to {payload.status}.")
    if period.status == "closed" and payload.status == "open" and not payload.reason:
        raise ValueError("A reason is required to reopen a closed accounting period.")
    if payload.status == "closed":
        unposted = int(
            db.scalar(
                select(func.count(JournalEntry.id)).where(
                    JournalEntry.organization_id == principal.organization_id,
                    JournalEntry.accounting_period_id == period.id,
                    JournalEntry.status.in_(("draft", "approved")),
                )
            )
            or 0
        )
        if unposted:
            raise ValueError(
                f"Resolve {unposted} unposted journal entries before closing this period."
            )
    now = datetime.now(UTC)
    previous = accounting_period_snapshot(period)
    period.status = payload.status
    if payload.status == "review":
        period.review_started_by_user_id = principal.user_id
        period.review_started_at = now
    elif payload.status == "closed":
        period.closed_by_user_id = principal.user_id
        period.closed_at = now
    elif payload.status == "locked":
        period.locked_by_user_id = principal.user_id
        period.locked_at = now
    elif payload.status == "open" and previous["status"] == "closed":
        period.reopened_by_user_id = principal.user_id
        period.reopened_at = now
        period.reopen_reason = payload.reason
        period.closed_by_user_id = None
        period.closed_at = None
    add_accounting_audit(
        db,
        principal,
        "finance.accounting_period_status",
        period,
        previous,
        accounting_period_snapshot(period),
        payload.reason or f"Accounting period moved to {payload.status}",
    )
    db.commit()
    db.refresh(period)
    return accounting_period_to_read(
        period,
        accounting_period_entry_counts(db, principal, period.id),
    )


def ensure_accounting_period(
    db: Session,
    principal: Principal,
    entry_date: date,
    profile: AccountingProfile | None = None,
) -> AccountingPeriod:
    period_key = entry_date.strftime("%Y-%m")
    period = db.scalar(
        select(AccountingPeriod).where(
            AccountingPeriod.organization_id == principal.organization_id,
            AccountingPeriod.period_key == period_key,
        )
    )
    if period is not None:
        return period
    profile = profile or ensure_accounting_foundation(db, principal)
    start_at = date(entry_date.year, entry_date.month, 1)
    end_at = date(
        entry_date.year,
        entry_date.month,
        monthrange(entry_date.year, entry_date.month)[1],
    )
    period = AccountingPeriod(
        organization_id=principal.organization_id,
        accounting_profile_id=profile.id,
        period_key=period_key,
        period_start_at=start_at,
        period_end_at=end_at,
        status="open",
        review_started_by_user_id=None,
        review_started_at=None,
        closed_by_user_id=None,
        closed_at=None,
        locked_by_user_id=None,
        locked_at=None,
        reopened_by_user_id=None,
        reopened_at=None,
        reopen_reason=None,
    )
    db.add(period)
    db.flush()
    add_accounting_audit(
        db,
        principal,
        "finance.accounting_period_create",
        period,
        None,
        accounting_period_snapshot(period),
        "Monthly accounting period opened",
    )
    db.commit()
    db.refresh(period)
    return period


def get_accounting_period(
    db: Session,
    principal: Principal,
    period_id: UUID,
    *,
    for_update: bool = False,
) -> AccountingPeriod | None:
    statement = select(AccountingPeriod).where(
        AccountingPeriod.id == period_id,
        AccountingPeriod.organization_id == principal.organization_id,
    )
    if for_update:
        statement = statement.with_for_update()
    return db.scalar(statement)


def get_journal_entry(
    db: Session,
    principal: Principal,
    entry_id: UUID,
    *,
    for_update: bool = False,
) -> JournalEntry | None:
    statement = select(JournalEntry).where(
        JournalEntry.id == entry_id,
        JournalEntry.organization_id == principal.organization_id,
    )
    if for_update:
        statement = statement.with_for_update()
    return db.scalar(statement)


def validate_journal_links(
    db: Session,
    principal: Principal,
    payload: JournalEntryCreate,
) -> None:
    deal_ids = {line.deal_id for line in payload.lines if line.deal_id is not None}
    transaction_ids = {
        line.transaction_id for line in payload.lines if line.transaction_id is not None
    }
    if deal_ids:
        found_deals = set(
            db.scalars(
                select(Deal.id).where(
                    Deal.organization_id == principal.organization_id,
                    Deal.id.in_(deal_ids),
                )
            ).all()
        )
        if found_deals != deal_ids:
            raise ValueError("A journal line references an unavailable deal.")
    if transaction_ids:
        found_transactions = set(
            db.scalars(
                select(Transaction.id).where(
                    Transaction.organization_id == principal.organization_id,
                    Transaction.id.in_(transaction_ids),
                )
            ).all()
        )
        if found_transactions != transaction_ids:
            raise ValueError("A journal line references an unavailable transaction.")


def load_journal_entry_read(
    db: Session,
    principal: Principal,
    entry: JournalEntry,
) -> JournalEntryRead:
    lines = list(
        db.scalars(
            select(JournalLine)
            .where(JournalLine.journal_entry_id == entry.id)
            .order_by(JournalLine.line_number)
        ).all()
    )
    account_ids = {line.accounting_account_id for line in lines}
    accounts = {
        account.id: account
        for account in db.scalars(
            select(AccountingAccount).where(
                AccountingAccount.organization_id == principal.organization_id,
                AccountingAccount.id.in_(account_ids),
            )
        ).all()
    }
    reversal_entry_id = db.scalar(
        select(JournalEntry.id).where(
            JournalEntry.organization_id == principal.organization_id,
            JournalEntry.reverses_entry_id == entry.id,
        )
    )
    return journal_entry_to_read(
        entry,
        lines,
        accounts,
        reversal_entry_id,
    )


def journal_entry_to_read(
    entry: JournalEntry,
    lines: list[JournalLine],
    accounts: dict[UUID, AccountingAccount],
    reversal_entry_id: UUID | None,
) -> JournalEntryRead:
    return JournalEntryRead(
        id=entry.id,
        accounting_period_id=entry.accounting_period_id,
        entry_number=entry.entry_number,
        entry_date=entry.entry_date,
        status=entry.status,
        memo=entry.memo,
        source_type=entry.source_type,
        source_id=entry.source_id,
        posting_rule_version=entry.posting_rule_version,
        evidence_references=entry.evidence_references,
        idempotency_key=entry.idempotency_key,
        currency=entry.currency,
        total_debits_cents=entry.total_debits_cents,
        total_credits_cents=entry.total_credits_cents,
        prepared_by_user_id=entry.prepared_by_user_id,
        approved_by_user_id=entry.approved_by_user_id,
        posted_by_user_id=entry.posted_by_user_id,
        reversed_by_user_id=entry.reversed_by_user_id,
        reverses_entry_id=entry.reverses_entry_id,
        reversal_entry_id=reversal_entry_id,
        approved_at=entry.approved_at,
        posted_at=entry.posted_at,
        reversed_at=entry.reversed_at,
        review_notes=entry.review_notes,
        created_at=entry.created_at,
        lines=[
            JournalLineRead(
                id=line.id,
                accounting_account_id=line.accounting_account_id,
                account_code=accounts[line.accounting_account_id].code,
                account_name=accounts[line.accounting_account_id].name,
                line_number=line.line_number,
                debit_cents=line.debit_cents,
                credit_cents=line.credit_cents,
                memo=line.memo,
                deal_id=line.deal_id,
                transaction_id=line.transaction_id,
            )
            for line in lines
        ],
    )


def accounting_period_to_read(
    period: AccountingPeriod,
    counts: dict[str, int],
) -> AccountingPeriodRead:
    return AccountingPeriodRead(
        id=period.id,
        period_key=period.period_key,
        period_start_at=period.period_start_at,
        period_end_at=period.period_end_at,
        status=period.status,
        review_started_at=period.review_started_at,
        closed_at=period.closed_at,
        locked_at=period.locked_at,
        reopened_at=period.reopened_at,
        reopen_reason=period.reopen_reason,
        draft_entries=counts.get("draft", 0),
        approved_entries=counts.get("approved", 0),
        posted_entries=counts.get("posted", 0),
    )


def accounting_period_entry_counts(
    db: Session,
    principal: Principal,
    period_id: UUID,
) -> dict[str, int]:
    counts = {"draft": 0, "approved": 0, "posted": 0}
    for status, count in db.execute(
        select(JournalEntry.status, func.count(JournalEntry.id))
        .where(
            JournalEntry.organization_id == principal.organization_id,
            JournalEntry.accounting_period_id == period_id,
        )
        .group_by(JournalEntry.status)
    ).all():
        if status in counts:
            counts[status] = int(count)
    return counts


def journal_snapshot(entry: JournalEntry) -> dict[str, object]:
    return {
        "entry_number": entry.entry_number,
        "entry_date": entry.entry_date.isoformat(),
        "status": entry.status,
        "source_type": entry.source_type,
        "source_id": entry.source_id,
        "currency": entry.currency,
        "total_debits_cents": entry.total_debits_cents,
        "total_credits_cents": entry.total_credits_cents,
        "reverses_entry_id": (str(entry.reverses_entry_id) if entry.reverses_entry_id else None),
    }


def accounting_period_snapshot(period: AccountingPeriod) -> dict[str, object]:
    return {
        "period_key": period.period_key,
        "status": period.status,
        "period_start_at": period.period_start_at.isoformat(),
        "period_end_at": period.period_end_at.isoformat(),
        "reopen_reason": period.reopen_reason,
    }


def add_accounting_audit(
    db: Session,
    principal: Principal,
    action: str,
    entity: AccountingPeriod | JournalEntry,
    previous_value: dict[str, object] | None,
    new_value: dict[str, object],
    reason: str,
) -> None:
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action=action,
            entity_type=(
                "accounting_period" if isinstance(entity, AccountingPeriod) else "journal_entry"
            ),
            entity_id=entity.id,
            previous_value=previous_value,
            new_value=new_value,
            reason=reason,
        )
    )


def ensure_operational_posting_rules(
    db: Session,
    principal: Principal,
) -> list[AccountingPostingRule]:
    existing = list(
        db.scalars(
            select(AccountingPostingRule).where(
                AccountingPostingRule.organization_id == principal.organization_id
            )
        ).all()
    )
    existing_keys = {(rule.rule_key, rule.version_number) for rule in existing}
    created = False
    for (
        rule_key,
        name,
        source_type,
        trigger_status,
        strategy_key,
        debit_account_key,
        credit_account_key,
        evidence_required,
        description,
    ) in DEFAULT_POSTING_RULES:
        if (rule_key, 1) in existing_keys:
            continue
        rule = AccountingPostingRule(
            organization_id=principal.organization_id,
            rule_key=rule_key,
            version_number=1,
            name=name,
            source_type=source_type,
            trigger_status=trigger_status,
            strategy_key=strategy_key,
            debit_account_key=debit_account_key,
            credit_account_key=credit_account_key,
            evidence_required=evidence_required,
            status="draft",
            description=description,
            created_by_user_id=principal.user_id,
            approved_by_user_id=None,
            approved_at=None,
            effective_at=None,
            superseded_at=None,
        )
        db.add(rule)
        existing.append(rule)
        created = True
    if created:
        db.flush()
        db.add(
            AuditEvent(
                organization_id=principal.organization_id,
                actor_user_id=principal.user_id,
                actor_type="user",
                action="finance.posting_rules_install",
                entity_type="accounting_posting_rule",
                entity_id=None,
                previous_value=None,
                new_value={"rule_count": len(DEFAULT_POSTING_RULES), "status": "draft"},
                reason="F6C operational posting rule foundation",
            )
        )
        db.commit()
    return sorted(existing, key=lambda rule: (rule.rule_key, rule.version_number))


def approve_operational_posting_rule(
    db: Session,
    principal: Principal,
    rule_id: UUID,
) -> AccountingPostingRuleRead | None:
    rule = db.scalar(
        select(AccountingPostingRule)
        .where(
            AccountingPostingRule.organization_id == principal.organization_id,
            AccountingPostingRule.id == rule_id,
        )
        .with_for_update()
    )
    if rule is None:
        return None
    if rule.status == "approved":
        return posting_rule_to_read(rule)
    if rule.status != "draft":
        raise ValueError("Only a draft posting rule can be approved.")
    now = datetime.now(UTC)
    prior_rules = list(
        db.scalars(
            select(AccountingPostingRule).where(
                AccountingPostingRule.organization_id == principal.organization_id,
                AccountingPostingRule.rule_key == rule.rule_key,
                AccountingPostingRule.status == "approved",
                AccountingPostingRule.id != rule.id,
            )
        ).all()
    )
    for prior in prior_rules:
        prior.status = "superseded"
        prior.superseded_at = now
    rule.status = "approved"
    rule.approved_by_user_id = principal.user_id
    rule.approved_at = now
    rule.effective_at = now
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="finance.posting_rule_approve",
            entity_type="accounting_posting_rule",
            entity_id=rule.id,
            previous_value={"status": "draft"},
            new_value={
                "status": "approved",
                "rule_key": rule.rule_key,
                "version_number": rule.version_number,
            },
            reason="Owner-approved operational posting rule",
        )
    )
    db.commit()
    db.refresh(rule)
    return posting_rule_to_read(rule)


def get_operational_posting_workspace(
    db: Session,
    principal: Principal,
) -> AccountingPostingWorkspaceRead:
    ensure_accounting_foundation(db, principal)
    rules = ensure_operational_posting_rules(db, principal)
    rule_by_key = {rule.rule_key: rule for rule in rules if rule.status in {"draft", "approved"}}
    links = list(
        db.scalars(
            select(AccountingSourceLink).where(
                AccountingSourceLink.organization_id == principal.organization_id
            )
        ).all()
    )
    link_by_source = {
        (link.source_type, link.source_id, link.posting_purpose): link for link in links
    }
    journal_ids = {link.journal_entry_id for link in links}
    journals = {
        entry.id: entry
        for entry in db.scalars(
            select(JournalEntry).where(
                JournalEntry.organization_id == principal.organization_id,
                JournalEntry.id.in_(journal_ids),
            )
        ).all()
    }
    transaction_ids: set[UUID] = set()
    revenue_records = list(
        db.scalars(
            select(RevenueRecord).where(
                RevenueRecord.organization_id == principal.organization_id,
                RevenueRecord.status == "collected",
            )
        ).all()
    )
    deductions = list(
        db.scalars(
            select(DealDeduction).where(DealDeduction.organization_id == principal.organization_id)
        ).all()
    )
    for record in revenue_records:
        if record.transaction_id is not None:
            transaction_ids.add(record.transaction_id)
    for deduction in deductions:
        if deduction.transaction_id is not None:
            transaction_ids.add(deduction.transaction_id)
    payouts = list(
        db.scalars(
            select(DealPayout).where(
                DealPayout.organization_id == principal.organization_id,
                DealPayout.status.in_({"approved", "payable", "paid"}),
            )
        ).all()
    )
    reconciliation_ids = {payout.deal_reconciliation_id for payout in payouts}
    reconciliations = list(
        db.scalars(
            select(DealReconciliation).where(
                DealReconciliation.organization_id == principal.organization_id,
                DealReconciliation.id.in_(reconciliation_ids),
            )
        ).all()
    )
    reconciliation_by_id = {item.id: item for item in reconciliations}
    for reconciliation in reconciliations:
        transaction_ids.add(reconciliation.transaction_id)
    transaction_by_id = {
        transaction.id: transaction
        for transaction in db.scalars(
            select(Transaction).where(
                Transaction.organization_id == principal.organization_id,
                Transaction.id.in_(transaction_ids),
            )
        ).all()
    }
    approved_reconciliation_by_transaction = {
        reconciliation.transaction_id: reconciliation
        for reconciliation in db.scalars(
            select(DealReconciliation).where(
                DealReconciliation.organization_id == principal.organization_id,
                DealReconciliation.transaction_id.in_(transaction_ids),
                DealReconciliation.status == "approved",
            )
        ).all()
    }
    documents_by_transaction: dict[UUID, list[TransactionDocument]] = {}
    for document in db.scalars(
        select(TransactionDocument).where(
            TransactionDocument.organization_id == principal.organization_id,
            TransactionDocument.transaction_id.in_(transaction_ids),
            TransactionDocument.deleted_at.is_(None),
        )
    ).all():
        documents_by_transaction.setdefault(document.transaction_id, []).append(document)

    source_items: list[AccountingSourceItemRead] = []
    stale_links = False

    def add_item(
        *,
        source_type: str,
        source_id: UUID,
        purpose: str,
        label: str,
        amount_cents: int,
        occurred_at: datetime,
        source_status: str,
        rule_key: str,
        evidence_references: list[str],
        evidence_gaps: list[str],
        lead_id: UUID | None = None,
        deal_id: UUID | None = None,
        transaction_id: UUID | None = None,
    ) -> None:
        nonlocal stale_links
        rule = rule_by_key.get(rule_key)
        fingerprint = source_fingerprint(
            source_type,
            str(source_id),
            purpose,
            amount_cents,
            source_status,
            evidence_references,
        )
        link = link_by_source.get((source_type, str(source_id), purpose))
        journal = journals.get(link.journal_entry_id) if link is not None else None
        if link is not None and link.source_fingerprint != fingerprint:
            if link.status != "stale":
                link.status = "stale"
                link.exception_detail = "The source record changed after the journal was drafted."
                stale_links = True
            readiness = "exception"
            detail = link.exception_detail or "The linked draft requires review."
        elif link is not None:
            readiness = "linked"
            detail = f"Linked journal is {journal.status if journal else 'unavailable'}."
        elif rule is None or rule.status != "approved":
            readiness = "rule_review"
            detail = "Approve the versioned posting rule before preparing a draft."
        elif evidence_gaps:
            readiness = "needs_evidence"
            detail = " ".join(evidence_gaps)
        else:
            readiness = "ready"
            detail = "Source and evidence are ready for a balanced draft."
        source_items.append(
            AccountingSourceItemRead(
                source_type=source_type,
                source_id=str(source_id),
                posting_purpose=purpose,
                label=label,
                amount_cents=amount_cents,
                occurred_at=occurred_at,
                status=source_status,
                readiness=readiness,
                readiness_detail=detail,
                rule_id=rule.id if rule else None,
                rule_key=rule_key,
                journal_entry_id=journal.id if journal else None,
                journal_status=journal.status if journal else None,
                evidence_references=evidence_references,
                lead_id=lead_id,
                deal_id=deal_id,
                transaction_id=transaction_id,
            )
        )

    for record in revenue_records:
        rule_key = {
            "assignment_fee": "assignment_revenue_collected",
            "double_close": "double_close_revenue_collected",
            "consulting_fee": "other_revenue_collected",
            "other": "other_revenue_collected",
        }[record.source]
        evidence, gaps = funded_deal_evidence(
            record.transaction_id,
            transaction_by_id,
            approved_reconciliation_by_transaction,
            documents_by_transaction,
        )
        add_item(
            source_type="revenue_record",
            source_id=record.id,
            purpose="collected",
            label=f"{record.source.replace('_', ' ').title()} collected",
            amount_cents=record.amount_cents,
            occurred_at=record.received_at,
            source_status=record.status,
            rule_key=rule_key,
            evidence_references=evidence,
            evidence_gaps=gaps,
            lead_id=record.lead_id,
            deal_id=record.deal_id,
            transaction_id=record.transaction_id,
        )
    for deduction in deductions:
        evidence, gaps = (
            funded_deal_evidence(
                deduction.transaction_id,
                transaction_by_id,
                approved_reconciliation_by_transaction,
                documents_by_transaction,
            )
            if deduction.transaction_id is not None
            else ([], [])
        )
        add_item(
            source_type="deal_deduction",
            source_id=deduction.id,
            purpose="paid",
            label=f"{deduction.category.replace('_', ' ').title()} deal cost",
            amount_cents=deduction.amount_cents,
            occurred_at=deduction.incurred_at,
            source_status="paid",
            rule_key="deal_deduction_paid",
            evidence_references=evidence,
            evidence_gaps=gaps,
            lead_id=deduction.lead_id,
            deal_id=deduction.deal_id,
            transaction_id=deduction.transaction_id,
        )
    for spend in db.scalars(
        select(MarketingSpend).where(MarketingSpend.organization_id == principal.organization_id)
    ).all():
        add_item(
            source_type="marketing_spend",
            source_id=spend.id,
            purpose="paid",
            label=f"{spend.source.replace('_', ' ').title()} spend",
            amount_cents=spend.amount_cents,
            occurred_at=spend.spend_month_at,
            source_status="paid",
            rule_key="marketing_spend_paid",
            evidence_references=[],
            evidence_gaps=[],
        )
    for payout in payouts:
        payout_reconciliation = reconciliation_by_id.get(payout.deal_reconciliation_id)
        transaction_id = payout_reconciliation.transaction_id if payout_reconciliation else None
        evidence, gaps = funded_deal_evidence(
            transaction_id,
            transaction_by_id,
            approved_reconciliation_by_transaction,
            documents_by_transaction,
        )
        evidence = [*evidence, *payout.evidence_references]
        add_item(
            source_type="deal_payout",
            source_id=payout.id,
            purpose="accrued",
            label=f"{payout.role_key.replace('_', ' ').title()} commission payable",
            amount_cents=payout.amount_cents,
            occurred_at=payout.approved_at or payout.created_at,
            source_status=payout.status,
            rule_key="commission_accrued",
            evidence_references=evidence,
            evidence_gaps=gaps,
            transaction_id=transaction_id,
        )
        if payout.status == "paid":
            payment_gaps = list(gaps)
            if not payout.payment_reference:
                payment_gaps.append("Add a payment reference before drafting settlement.")
            add_item(
                source_type="deal_payout",
                source_id=payout.id,
                purpose="paid",
                label=f"{payout.role_key.replace('_', ' ').title()} commission paid",
                amount_cents=payout.amount_cents,
                occurred_at=payout.paid_at or payout.updated_at,
                source_status=payout.status,
                rule_key="commission_paid",
                evidence_references=[
                    *evidence,
                    *([f"payment:{payout.payment_reference}"] if payout.payment_reference else []),
                ],
                evidence_gaps=payment_gaps,
                transaction_id=transaction_id,
            )
    obligations = list(
        db.scalars(
            select(FinancialObligation)
            .where(FinancialObligation.organization_id == principal.organization_id)
            .order_by(FinancialObligation.created_at.desc())
        ).all()
    )
    for obligation in obligations:
        evidence_gaps = (
            []
            if obligation.evidence_references
            else ["Attach an invoice, receipt, or approval reference."]
        )
        if obligation.obligation_type != "owner_distribution" and obligation.status in {
            "approved",
            "payable",
            "paid",
        }:
            add_item(
                source_type="financial_obligation",
                source_id=obligation.id,
                purpose="accrued",
                label=f"{obligation.counterparty_name} payable",
                amount_cents=obligation.amount_cents,
                occurred_at=obligation.approved_at or obligation.created_at,
                source_status=obligation.status,
                rule_key="obligation_accrued",
                evidence_references=obligation.evidence_references,
                evidence_gaps=evidence_gaps,
            )
        if obligation.status == "paid":
            payment_gaps = list(evidence_gaps)
            if not obligation.payment_reference:
                payment_gaps.append("Add a payment reference before drafting settlement.")
            add_item(
                source_type="financial_obligation",
                source_id=obligation.id,
                purpose=(
                    "distribution" if obligation.obligation_type == "owner_distribution" else "paid"
                ),
                label=(
                    f"{obligation.counterparty_name} owner distribution"
                    if obligation.obligation_type == "owner_distribution"
                    else f"{obligation.counterparty_name} paid"
                ),
                amount_cents=obligation.amount_cents,
                occurred_at=obligation.paid_at or obligation.updated_at,
                source_status=obligation.status,
                rule_key=(
                    "owner_distribution_paid"
                    if obligation.obligation_type == "owner_distribution"
                    else "obligation_paid"
                ),
                evidence_references=[
                    *obligation.evidence_references,
                    *(
                        [f"payment:{obligation.payment_reference}"]
                        if obligation.payment_reference
                        else []
                    ),
                ],
                evidence_gaps=payment_gaps,
            )
    if stale_links:
        db.commit()
    source_items.sort(key=lambda item: item.occurred_at, reverse=True)
    return AccountingPostingWorkspaceRead(
        rules=[posting_rule_to_read(rule) for rule in rules],
        source_items=source_items,
        obligations=[financial_obligation_to_read(item) for item in obligations],
        draft_rule_count=sum(rule.status == "draft" for rule in rules),
        ready_item_count=sum(item.readiness == "ready" for item in source_items),
        exception_count=sum(
            item.readiness in {"needs_evidence", "exception"} for item in source_items
        ),
    )


def prepare_operational_source_journal(
    db: Session,
    principal: Principal,
    payload: AccountingSourceDraftRequest,
) -> JournalEntryRead:
    workspace = get_operational_posting_workspace(db, principal)
    item = next(
        (
            candidate
            for candidate in workspace.source_items
            if candidate.source_type == payload.source_type
            and candidate.source_id == payload.source_id
            and candidate.posting_purpose == payload.posting_purpose
        ),
        None,
    )
    if item is None:
        raise ValueError("Operational accounting source was not found.")
    if item.journal_entry_id is not None and item.readiness == "linked":
        existing = get_journal_entry(db, principal, item.journal_entry_id)
        if existing is None:
            raise ValueError("The linked journal is unavailable.")
        return load_journal_entry_read(db, principal, existing)
    if item.readiness != "ready" or item.rule_id is None:
        raise ValueError(item.readiness_detail)
    rule = db.scalar(
        select(AccountingPostingRule).where(
            AccountingPostingRule.organization_id == principal.organization_id,
            AccountingPostingRule.id == item.rule_id,
            AccountingPostingRule.status == "approved",
        )
    )
    if rule is None:
        raise ValueError("The approved posting rule is unavailable.")
    profile = ensure_accounting_foundation(db, principal)
    debit_key, credit_key = posting_account_keys(db, principal, item, rule)
    vendor_bill_lines = operational_vendor_bill_lines(db, principal, item)
    required_account_keys = {
        debit_key,
        credit_key,
        *(line.expense_account_key for line in vendor_bill_lines),
    }
    accounts = {
        account.system_key: account
        for account in db.scalars(
            select(AccountingAccount).where(
                AccountingAccount.organization_id == principal.organization_id,
                AccountingAccount.policy_version == profile.policy_version,
                AccountingAccount.system_key.in_(required_account_keys),
                AccountingAccount.is_active.is_(True),
            )
        ).all()
    }
    if set(accounts) != required_account_keys:
        raise ValueError("The posting rule references an unavailable accounting account.")
    journal_lines = operational_journal_lines(
        item,
        accounts,
        debit_key,
        credit_key,
        vendor_bill_lines,
    )
    fingerprint = source_fingerprint(
        item.source_type,
        item.source_id,
        item.posting_purpose,
        item.amount_cents,
        item.status,
        item.evidence_references,
    )
    entry = create_journal_entry(
        db,
        principal,
        JournalEntryCreate(
            entry_date=item.occurred_at.date(),
            memo=item.label,
            source_type=item.source_type,
            source_id=item.source_id,
            posting_rule_version=rule.version_number,
            evidence_references=item.evidence_references,
            idempotency_key=(
                f"operational:{item.source_type}:{item.source_id}:"
                f"{item.posting_purpose}:v{rule.version_number}"
            ),
            currency=profile.currency,
            lines=journal_lines,
        ),
        commit=False,
    )
    db.add(
        AccountingSourceLink(
            organization_id=principal.organization_id,
            posting_rule_id=rule.id,
            journal_entry_id=entry.id,
            source_type=item.source_type,
            source_id=item.source_id,
            posting_purpose=item.posting_purpose,
            source_fingerprint=fingerprint,
            status="drafted",
            exception_detail=None,
            generated_by_user_id=principal.user_id,
            generated_at=datetime.now(UTC),
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="finance.operational_journal_prepare",
            entity_type=item.source_type,
            entity_id=UUID(item.source_id),
            previous_value=None,
            new_value={
                "journal_entry_id": str(entry.id),
                "posting_purpose": item.posting_purpose,
                "posting_rule": rule.rule_key,
                "posting_rule_version": rule.version_number,
            },
            reason="Balanced operational journal prepared for human review",
        )
    )
    db.commit()
    journal = get_journal_entry(db, principal, entry.id)
    if journal is None:
        raise ValueError("The prepared journal could not be loaded.")
    return load_journal_entry_read(db, principal, journal)


def create_financial_obligation(
    db: Session,
    principal: Principal,
    payload: FinancialObligationCreate,
) -> FinancialObligationRead:
    if payload.obligation_type not in OBLIGATION_TYPES:
        raise ValueError("Unsupported financial obligation type.")
    if payload.status not in {"draft", "approved"}:
        raise ValueError("New obligations must begin as draft or approved.")
    if payload.obligation_type != "owner_distribution" and not payload.expense_account_key:
        raise ValueError("Select an expense account for this obligation.")
    now = datetime.now(UTC)
    obligation = FinancialObligation(
        organization_id=principal.organization_id,
        obligation_type=payload.obligation_type,
        direction="outbound",
        counterparty_name=payload.counterparty_name.strip(),
        user_id=payload.user_id,
        expense_account_key=payload.expense_account_key,
        amount_cents=payload.amount_cents,
        status=payload.status,
        source_type=payload.source_type,
        source_id=payload.source_id,
        due_at=payload.due_at,
        approved_by_user_id=principal.user_id if payload.status == "approved" else None,
        approved_at=now if payload.status == "approved" else None,
        paid_at=None,
        payment_reference=payload.payment_reference,
        evidence_references=payload.evidence_references,
        notes=payload.notes,
    )
    db.add(obligation)
    db.flush()
    add_finance_audit(
        db,
        principal,
        "finance.obligation_create",
        "financial_obligation",
        obligation.id,
        financial_obligation_snapshot(obligation),
    )
    db.commit()
    db.refresh(obligation)
    return financial_obligation_to_read(obligation)


def update_financial_obligation_status(
    db: Session,
    principal: Principal,
    obligation_id: UUID,
    payload: FinancialObligationStatusUpdate,
) -> FinancialObligationRead | None:
    obligation = db.scalar(
        select(FinancialObligation)
        .where(
            FinancialObligation.organization_id == principal.organization_id,
            FinancialObligation.id == obligation_id,
        )
        .with_for_update()
    )
    if obligation is None:
        return None
    if payload.status == obligation.status:
        return financial_obligation_to_read(obligation)
    if payload.status not in PAYMENT_TRANSITIONS.get(obligation.status, set()):
        raise ValueError(
            f"Financial obligation cannot move from {obligation.status} to {payload.status}."
        )
    evidence = list(
        dict.fromkeys(
            [
                *obligation.evidence_references,
                *(payload.evidence_references or []),
            ]
        )
    )
    reference = payload.payment_reference or obligation.payment_reference
    if payload.status == "paid" and (not reference or not evidence):
        raise ValueError("Paid obligations require a payment reference and evidence.")
    previous = financial_obligation_snapshot(obligation)
    now = datetime.now(UTC)
    obligation.status = payload.status
    obligation.payment_reference = reference
    obligation.evidence_references = evidence
    if payload.notes is not None:
        obligation.notes = payload.notes
    if payload.status == "approved":
        obligation.approved_by_user_id = principal.user_id
        obligation.approved_at = now
    if payload.status == "paid":
        obligation.paid_at = now
    if obligation.source_type == "vendor_bill" and obligation.source_id:
        bill = db.scalar(
            select(VendorBill).where(
                VendorBill.organization_id == principal.organization_id,
                VendorBill.id == UUID(obligation.source_id),
            )
        )
        if bill is not None:
            bill.status = payload.status
            bill.payment_reference = reference
            if payload.status == "paid":
                bill.paid_at = now
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="finance.obligation_status",
            entity_type="financial_obligation",
            entity_id=obligation.id,
            previous_value=previous,
            new_value=financial_obligation_snapshot(obligation),
            reason=payload.notes or "Financial obligation payment state updated",
        )
    )
    db.commit()
    db.refresh(obligation)
    return financial_obligation_to_read(obligation)


def update_deal_payout_status(
    db: Session,
    principal: Principal,
    payout_id: UUID,
    payload: DealPayoutStatusUpdate,
) -> AccountingPostingWorkspaceRead | None:
    payout = db.scalar(
        select(DealPayout)
        .where(
            DealPayout.organization_id == principal.organization_id,
            DealPayout.id == payout_id,
        )
        .with_for_update()
    )
    if payout is None:
        return None
    if payload.status != payout.status:
        allowed = {
            "approved": {"payable"},
            "payable": {"paid", "disputed"},
            "disputed": {"payable"},
        }
        if payload.status not in allowed.get(payout.status, set()):
            raise ValueError(
                f"Commission payout cannot move from {payout.status} to {payload.status}."
            )
    evidence = list(
        dict.fromkeys(
            [
                *payout.evidence_references,
                *(payload.evidence_references or []),
            ]
        )
    )
    reference = payload.payment_reference or payout.payment_reference
    if payload.status == "paid" and (not reference or not evidence):
        raise ValueError("Paid commissions require a payment reference and evidence.")
    previous = {
        "status": payout.status,
        "payment_reference": payout.payment_reference,
    }
    payout.status = payload.status
    payout.due_at = payload.due_at or payout.due_at
    payout.payment_reference = reference
    payout.evidence_references = evidence
    if payload.status == "paid":
        payout.paid_at = datetime.now(UTC)
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="finance.commission_payment_status",
            entity_type="deal_payout",
            entity_id=payout.id,
            previous_value=previous,
            new_value={
                "status": payout.status,
                "payment_reference": payout.payment_reference,
                "due_at": payout.due_at.isoformat() if payout.due_at else None,
            },
            reason="Commission payment state updated",
        )
    )
    db.commit()
    return get_operational_posting_workspace(db, principal)


def posting_account_keys(
    db: Session,
    principal: Principal,
    item: AccountingSourceItemRead,
    rule: AccountingPostingRule,
) -> tuple[str, str]:
    debit_key = rule.debit_account_key
    credit_key = rule.credit_account_key
    if item.source_type == "deal_deduction":
        deduction = db.scalar(
            select(DealDeduction).where(
                DealDeduction.organization_id == principal.organization_id,
                DealDeduction.id == UUID(item.source_id),
            )
        )
        if deduction is None:
            raise ValueError("Deal deduction source is unavailable.")
        debit_key = {
            "title": "deal_closing_costs",
            "attorney": "deal_closing_costs",
            "transaction": "deal_closing_costs",
            "marketing": "advertising",
            "seller_credit": "buyer_credits_refunds",
            "other": "other_operating_expense",
        }[deduction.category]
    elif item.source_type == "marketing_spend":
        spend = db.scalar(
            select(MarketingSpend).where(
                MarketingSpend.organization_id == principal.organization_id,
                MarketingSpend.id == UUID(item.source_id),
            )
        )
        if spend is None:
            raise ValueError("Marketing spend source is unavailable.")
        source = spend.source.lower()
        if any(term in source for term in ("list", "data", "skip")):
            debit_key = "lead_lists_data"
        elif any(term in source for term in ("software", "hosting", "subscription")):
            debit_key = "software_subscriptions"
        elif any(term in source for term in ("caller", "va", "contractor", "labor")):
            debit_key = "prospecting_labor"
        else:
            debit_key = "advertising"
    elif item.source_type == "financial_obligation" and item.posting_purpose == "accrued":
        obligation = db.scalar(
            select(FinancialObligation).where(
                FinancialObligation.organization_id == principal.organization_id,
                FinancialObligation.id == UUID(item.source_id),
            )
        )
        if obligation is None or not obligation.expense_account_key:
            raise ValueError("Financial obligation account mapping is unavailable.")
        debit_key = obligation.expense_account_key
        credit_key = (
            "contractor_payable"
            if obligation.obligation_type == "contractor_payable"
            else "accounts_payable"
        )
    elif item.source_type == "financial_obligation" and item.posting_purpose == "paid":
        obligation = db.scalar(
            select(FinancialObligation).where(
                FinancialObligation.organization_id == principal.organization_id,
                FinancialObligation.id == UUID(item.source_id),
            )
        )
        if obligation is None:
            raise ValueError("Financial obligation source is unavailable.")
        debit_key = (
            "contractor_payable"
            if obligation.obligation_type == "contractor_payable"
            else "accounts_payable"
        )
    return debit_key, credit_key


def operational_vendor_bill_lines(
    db: Session,
    principal: Principal,
    item: AccountingSourceItemRead,
) -> list[VendorBillLine]:
    if item.source_type != "financial_obligation" or item.posting_purpose != "accrued":
        return []
    obligation = db.scalar(
        select(FinancialObligation).where(
            FinancialObligation.organization_id == principal.organization_id,
            FinancialObligation.id == UUID(item.source_id),
        )
    )
    if obligation is None or obligation.source_type != "vendor_bill" or not obligation.source_id:
        return []
    bill = db.scalar(
        select(VendorBill).where(
            VendorBill.organization_id == principal.organization_id,
            VendorBill.id == UUID(obligation.source_id),
            VendorBill.financial_obligation_id == obligation.id,
        )
    )
    if bill is None:
        raise ValueError("The linked vendor bill is unavailable.")
    lines = list(
        db.scalars(
            select(VendorBillLine)
            .where(
                VendorBillLine.organization_id == principal.organization_id,
                VendorBillLine.vendor_bill_id == bill.id,
            )
            .order_by(VendorBillLine.line_number)
        ).all()
    )
    if not lines or sum(line.amount_cents for line in lines) != item.amount_cents:
        raise ValueError("The vendor bill lines do not match the approved obligation.")
    return lines


def operational_journal_lines(
    item: AccountingSourceItemRead,
    accounts: dict[str, AccountingAccount],
    debit_key: str,
    credit_key: str,
    vendor_bill_lines: list[VendorBillLine],
) -> list[JournalLineCreate]:
    if vendor_bill_lines:
        return [
            *[
                JournalLineCreate(
                    accounting_account_id=accounts[line.expense_account_key].id,
                    debit_cents=line.amount_cents,
                    credit_cents=0,
                    memo=line.description,
                    deal_id=line.deal_id,
                    transaction_id=line.transaction_id,
                )
                for line in vendor_bill_lines
            ],
            JournalLineCreate(
                accounting_account_id=accounts[credit_key].id,
                debit_cents=0,
                credit_cents=item.amount_cents,
                memo=item.label,
                deal_id=item.deal_id,
                transaction_id=item.transaction_id,
            ),
        ]
    return [
        JournalLineCreate(
            accounting_account_id=accounts[debit_key].id,
            debit_cents=item.amount_cents,
            credit_cents=0,
            memo=item.label,
            deal_id=item.deal_id,
            transaction_id=item.transaction_id,
        ),
        JournalLineCreate(
            accounting_account_id=accounts[credit_key].id,
            debit_cents=0,
            credit_cents=item.amount_cents,
            memo=item.label,
            deal_id=item.deal_id,
            transaction_id=item.transaction_id,
        ),
    ]


def funded_deal_evidence(
    transaction_id: UUID | None,
    transaction_by_id: dict[UUID, Transaction],
    reconciliation_by_transaction: dict[UUID, DealReconciliation],
    documents_by_transaction: dict[UUID, list[TransactionDocument]],
) -> tuple[list[str], list[str]]:
    if transaction_id is None:
        return [], ["Link this source to a funded transaction."]
    transaction = transaction_by_id.get(transaction_id)
    documents = documents_by_transaction.get(transaction_id, [])
    document_types = {document.document_type for document in documents}
    evidence = [
        f"transaction_document:{document.id}"
        for document in documents
        if document.document_type in {"closing_statement", "funding_confirmation"}
    ]
    gaps: list[str] = []
    if transaction is None or transaction.status != "funded":
        gaps.append("Mark the transaction funded.")
    if transaction_id not in reconciliation_by_transaction:
        gaps.append("Approve the funded-deal reconciliation.")
    if "closing_statement" not in document_types:
        gaps.append("Upload the closing statement.")
    if "funding_confirmation" not in document_types:
        gaps.append("Upload funding confirmation.")
    return evidence, gaps


def source_fingerprint(
    source_type: str,
    source_id: str,
    posting_purpose: str,
    amount_cents: int,
    status: str,
    evidence_references: list[str],
) -> str:
    value = "|".join(
        [
            source_type,
            source_id,
            posting_purpose,
            str(amount_cents),
            status,
            *sorted(evidence_references),
        ]
    )
    return sha256(value.encode("utf-8")).hexdigest()


def posting_rule_to_read(rule: AccountingPostingRule) -> AccountingPostingRuleRead:
    return AccountingPostingRuleRead(
        id=rule.id,
        rule_key=rule.rule_key,
        version_number=rule.version_number,
        name=rule.name,
        source_type=rule.source_type,
        trigger_status=rule.trigger_status,
        strategy_key=rule.strategy_key,
        debit_account_key=rule.debit_account_key,
        credit_account_key=rule.credit_account_key,
        evidence_required=rule.evidence_required,
        status=rule.status,
        description=rule.description,
        approved_by_user_id=rule.approved_by_user_id,
        approved_at=rule.approved_at,
        effective_at=rule.effective_at,
    )


def financial_obligation_to_read(
    obligation: FinancialObligation,
) -> FinancialObligationRead:
    return FinancialObligationRead(
        id=obligation.id,
        obligation_type=obligation.obligation_type,
        direction=obligation.direction,
        counterparty_name=obligation.counterparty_name,
        user_id=obligation.user_id,
        expense_account_key=obligation.expense_account_key,
        amount_cents=obligation.amount_cents,
        status=obligation.status,
        source_type=obligation.source_type,
        source_id=obligation.source_id,
        due_at=obligation.due_at,
        approved_by_user_id=obligation.approved_by_user_id,
        approved_at=obligation.approved_at,
        paid_at=obligation.paid_at,
        payment_reference=obligation.payment_reference,
        evidence_references=obligation.evidence_references,
        notes=obligation.notes,
        created_at=obligation.created_at,
    )


def financial_obligation_snapshot(
    obligation: FinancialObligation,
) -> dict[str, object]:
    return {
        "obligation_type": obligation.obligation_type,
        "counterparty_name": obligation.counterparty_name,
        "amount_cents": obligation.amount_cents,
        "status": obligation.status,
        "expense_account_key": obligation.expense_account_key,
        "payment_reference": obligation.payment_reference,
    }


def get_finance_overview(
    db: Session,
    principal: Principal,
    period_days: int | None = None,
) -> FinanceOverview:
    period_end_at = datetime.now(UTC)
    period_start_at = (
        period_end_at - timedelta(days=period_days) if period_days is not None else None
    )
    revenue_records = db.scalars(
        select(RevenueRecord)
        .where(
            RevenueRecord.organization_id == principal.organization_id,
            *period_conditions(RevenueRecord.received_at, period_start_at, period_end_at),
        )
        .order_by(RevenueRecord.received_at.desc(), RevenueRecord.created_at.desc())
        .limit(100)
    ).all()
    deductions = db.scalars(
        select(DealDeduction)
        .where(
            DealDeduction.organization_id == principal.organization_id,
            *period_conditions(DealDeduction.incurred_at, period_start_at, period_end_at),
        )
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
        .join(RevenueRecord, RevenueRecord.id == CompensationCalculation.revenue_record_id)
        .where(
            CompensationCalculation.organization_id == principal.organization_id,
            *period_conditions(RevenueRecord.received_at, period_start_at, period_end_at),
        )
        .order_by(CompensationCalculation.created_at.desc())
        .limit(100)
    ).all()
    marketing_spend = db.scalars(
        select(MarketingSpend)
        .where(
            MarketingSpend.organization_id == principal.organization_id,
            *period_conditions(MarketingSpend.spend_month_at, period_start_at, period_end_at),
        )
        .order_by(MarketingSpend.spend_month_at.desc(), MarketingSpend.created_at.desc())
        .limit(100)
    ).all()
    lead_context = get_lead_context(
        db,
        principal,
        [record.lead_id for record in revenue_records if record.lead_id is not None],
    )
    previous_summary = None
    if period_start_at is not None and period_days is not None:
        previous_summary = get_finance_summary(
            db,
            principal,
            start_at=period_start_at - timedelta(days=period_days),
            end_at=period_start_at,
        )
    return FinanceOverview(
        period_days=period_days,
        period_start_at=period_start_at,
        period_end_at=period_end_at,
        previous_summary=previous_summary,
        summary=get_finance_summary(
            db,
            principal,
            start_at=period_start_at,
            end_at=period_end_at,
        ),
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


def get_finance_summary(
    db: Session,
    principal: Principal,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> FinanceSummary:
    collected_revenue = sum_int(
        db,
        select(func.coalesce(func.sum(RevenueRecord.amount_cents), 0)).where(
            RevenueRecord.organization_id == principal.organization_id,
            RevenueRecord.status == "collected",
            *period_conditions(RevenueRecord.received_at, start_at, end_at),
        ),
    )
    pending_revenue = sum_int(
        db,
        select(func.coalesce(func.sum(RevenueRecord.amount_cents), 0)).where(
            RevenueRecord.organization_id == principal.organization_id,
            RevenueRecord.status == "pending",
            *period_conditions(RevenueRecord.received_at, start_at, end_at),
        ),
    )
    deductions = sum_int(
        db,
        select(func.coalesce(func.sum(DealDeduction.amount_cents), 0)).where(
            DealDeduction.organization_id == principal.organization_id,
            *period_conditions(DealDeduction.incurred_at, start_at, end_at),
        ),
    )
    compensation = sum_int(
        db,
        select(func.coalesce(func.sum(CompensationCalculation.calculated_amount_cents), 0))
        .join(RevenueRecord, RevenueRecord.id == CompensationCalculation.revenue_record_id)
        .where(
            CompensationCalculation.organization_id == principal.organization_id,
            *period_conditions(RevenueRecord.received_at, start_at, end_at),
        ),
    )
    marketing_spend = sum_int(
        db,
        select(func.coalesce(func.sum(MarketingSpend.amount_cents), 0)).where(
            MarketingSpend.organization_id == principal.organization_id,
            *period_conditions(MarketingSpend.spend_month_at, start_at, end_at),
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


def period_conditions(
    column: InstrumentedAttribute[datetime],
    start_at: datetime | None,
    end_at: datetime | None,
) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if start_at is not None:
        conditions.append(column >= start_at)
    if end_at is not None:
        conditions.append(column < end_at)
    return conditions


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
            Lead.archived_at.is_(None),
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
    return effective_start <= received and (effective_end is None or effective_end >= received)


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
