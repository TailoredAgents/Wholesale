import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal, TypedDict

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.models.foundation import (
    AiRunLog,
    Appointment,
    Deal,
    DealReconciliation,
    Lead,
    OperationalFailure,
    Task,
)
from app.schemas.management_copilots import (
    ManagementCapability,
    ManagementMetricCard,
    ManagementRiskAlert,
)
from app.services.accounting_reports import get_accounting_reports
from app.services.banking import get_banking_workspace
from app.services.finance import (
    get_accounting_ledger,
    get_finance_overview,
    get_operational_posting_workspace,
)
from app.services.leads import get_dashboard_summary
from app.services.marketing import get_marketing_overview


class ManagementFacts(TypedDict):
    health_score: int
    health_band: Literal["healthy", "needs_review", "critical"]
    readiness_gaps: list[str]
    risk_alerts: list[ManagementRiskAlert]
    metric_cards: list[ManagementMetricCard]
    context: dict[str, Any]
    fingerprint: str


def build_management_facts(
    db: Session,
    principal: Principal,
    capability_key: ManagementCapability,
    period_days: int,
) -> ManagementFacts:
    if capability_key == "finance.reconcile":
        return _finance_facts(db, principal, period_days)
    if capability_key == "finance.tax_review":
        return _tax_facts(db, principal, period_days)
    if capability_key == "marketing.analyze":
        return _marketing_facts(db, principal, period_days)
    if capability_key == "operations.brief":
        return _operations_facts(db, principal, period_days)
    raise ValueError("Unsupported management capability.")


def _tax_facts(
    db: Session,
    principal: Principal,
    period_days: int,
) -> ManagementFacts:
    from app.services.finance import get_accounting_setup, get_finance_overview

    setup = get_accounting_setup(db, principal)
    overview = get_finance_overview(db, principal, period_days)
    posting = get_operational_posting_workspace(db, principal)
    account_by_key = {item.system_key: item for item in setup.accounts}
    classification_candidates = []
    for item in _posting_candidates(posting):
        debit_key = item["proposed_debit_account_key"]
        account = account_by_key.get(debit_key) if isinstance(debit_key, str) else None
        classification_candidates.append(
            {
                **item,
                "proposed_tax_category": account.tax_category if account else None,
                "classification_status": "human_review_required",
                "professional_decision_required": True,
            }
        )
    source_record_count = len(overview.deductions) + len(overview.marketing_spend)
    missing_note_count = sum(1 for item in overview.deductions if not item.notes) + sum(
        1 for item in overview.marketing_spend if not item.notes
    )
    score = setup.tax_copilot.readiness_score
    risks: list[ManagementRiskAlert] = []
    if setup.readiness_gaps:
        risks.append(
            ManagementRiskAlert(
                severity="warning",
                item="Accounting profile",
                reason="Tax treatment depends on unresolved company-profile decisions.",
                evidence=[f"accounting_profile:{setup.profile.id}"],
            )
        )
    if missing_note_count:
        risks.append(
            ManagementRiskAlert(
                severity="warning",
                item="Business purpose",
                reason=f"{missing_note_count} records lack a business-purpose note.",
                evidence=[
                    *[
                        f"deal_deduction:{item.id}"
                        for item in overview.deductions
                        if not item.notes
                    ],
                    *[
                        f"marketing_spend:{item.id}"
                        for item in overview.marketing_spend
                        if not item.notes
                    ],
                ][:20],
            )
        )
    context = {
        "accounting_profile": setup.profile.model_dump(mode="json"),
        "chart_of_accounts": [
            {
                "code": item.code,
                "name": item.name,
                "account_type": item.account_type,
                "tax_category": item.tax_category,
                "deal_tracking": item.deal_tracking,
            }
            for item in setup.accounts
        ],
        "policy_notes": setup.policy_notes,
        "deductions": [item.model_dump(mode="json") for item in overview.deductions],
        "marketing_spend": [item.model_dump(mode="json") for item in overview.marketing_spend],
        "classification_candidates": classification_candidates[:50],
        "authority": {
            "mode": "draft_only",
            "human_review_required": True,
            "prohibited_actions": setup.tax_copilot.prohibited_actions,
        },
    }
    encoded = json.dumps(context, sort_keys=True, default=str)
    return {
        "health_score": score,
        "health_band": (
            "healthy" if score >= 80 else "needs_review" if score >= 50 else "critical"
        ),
        "readiness_gaps": setup.tax_copilot.readiness_gaps,
        "risk_alerts": risks,
        "metric_cards": [
            ManagementMetricCard(
                label="Source records",
                value=str(source_record_count),
                detail=f"Last {period_days} days",
                tone="info",
            ),
            ManagementMetricCard(
                label="Missing purpose",
                value=str(missing_note_count),
                detail="Needs owner evidence",
                tone="warning" if missing_note_count else "success",
            ),
            ManagementMetricCard(
                label="Account structure",
                value=str(len(setup.accounts)),
                detail=f"Policy version {setup.profile.policy_version}",
                tone="success",
            ),
            ManagementMetricCard(
                label="Classifications",
                value=str(len(classification_candidates)),
                detail="Proposals requiring human review",
                tone="warning" if classification_candidates else "neutral",
            ),
        ],
        "context": context,
        "fingerprint": hashlib.sha256(encoded.encode()).hexdigest(),
    }


def _finance_facts(
    db: Session,
    principal: Principal,
    period_days: int,
) -> ManagementFacts:
    overview = get_finance_overview(db, principal, period_days)
    end_on = datetime.now(UTC).date()
    start_on = end_on - timedelta(days=period_days - 1)
    previous_end_on = start_on - timedelta(days=1)
    previous_start_on = previous_end_on - timedelta(days=period_days - 1)
    reports = get_accounting_reports(db, principal, start_on, end_on)
    previous_reports = get_accounting_reports(
        db,
        principal,
        previous_start_on,
        previous_end_on,
    )
    ledger = get_accounting_ledger(db, principal)
    posting = get_operational_posting_workspace(db, principal)
    banking = get_banking_workspace(db, principal)
    posting_candidates = _posting_candidates(posting)
    bank_matches, ambiguous_bank_lines = _bank_match_candidates(banking)
    statement_variances = _statement_variances(
        reports,
        previous_reports,
        start_on,
        end_on,
        previous_start_on,
        previous_end_on,
    )
    start_at = datetime.now(UTC) - timedelta(days=period_days)
    reconciliations = list(
        db.scalars(
            select(DealReconciliation)
            .where(
                DealReconciliation.organization_id == principal.organization_id,
                DealReconciliation.created_at >= start_at,
            )
            .order_by(DealReconciliation.created_at.desc())
        ).all()
    )
    pending_revenue = [item for item in overview.revenue_records if item.status == "pending"]
    unlinked_revenue = [
        item
        for item in overview.revenue_records
        if item.lead_id is None or item.transaction_id is None
    ]
    reconciliation_exceptions = [
        item
        for item in reconciliations
        if item.status != "approved"
        or item.company_margin_basis_points < item.target_margin_basis_points
    ]
    score = 100
    gaps: list[str] = []
    risks: list[ManagementRiskAlert] = []
    if not overview.revenue_records:
        gaps.append("No revenue evidence exists in this reporting period.")
        score -= 20
    if pending_revenue:
        score -= min(25, len(pending_revenue) * 5)
        risks.append(
            ManagementRiskAlert(
                severity="warning",
                item="Pending revenue",
                reason=f"{len(pending_revenue)} revenue records are not collected.",
                evidence=[f"revenue_record:{item.id}" for item in pending_revenue[:10]],
            )
        )
    if unlinked_revenue:
        score -= min(20, len(unlinked_revenue) * 5)
        risks.append(
            ManagementRiskAlert(
                severity="critical",
                item="Unlinked revenue",
                reason=f"{len(unlinked_revenue)} records lack complete deal linkage.",
                evidence=[f"revenue_record:{item.id}" for item in unlinked_revenue[:10]],
            )
        )
    if reconciliation_exceptions:
        score -= min(30, len(reconciliation_exceptions) * 10)
        risks.append(
            ManagementRiskAlert(
                severity="critical",
                item="Reconciliation exceptions",
                reason=(
                    f"{len(reconciliation_exceptions)} closing statements require "
                    "approval or margin review."
                ),
                evidence=[
                    f"deal_reconciliation:{item.id}" for item in reconciliation_exceptions[:10]
                ],
            )
        )
    if overview.summary.company_net_cents < 0:
        score -= 30
        risks.append(
            ManagementRiskAlert(
                severity="critical",
                item="Company net",
                reason="Recorded costs and compensation exceed collected revenue.",
                evidence=[f"finance_summary:{start_on}:{end_on}"],
            )
        )
    if not any(item.is_active for item in overview.compensation_rules):
        gaps.append("No active legacy compensation rule is recorded.")
        score -= 10
    if not reports.trial_balance.balanced or not reports.balance_sheet.balanced:
        score -= 40
        risks.append(
            ManagementRiskAlert(
                severity="critical",
                item="Financial statements",
                reason="The trial balance or balance sheet is out of balance.",
                evidence=[
                    f"trial_balance:{start_on}:{end_on}",
                    f"balance_sheet:{end_on}",
                ],
            )
        )
    if reports.close_readiness.blocking_count:
        score -= min(30, reports.close_readiness.blocking_count * 5)
        risks.append(
            ManagementRiskAlert(
                severity="warning",
                item="Month-end close",
                reason=(
                    f"{reports.close_readiness.blocking_count} accounting close "
                    "requirements remain unresolved."
                ),
                evidence=[
                    f"accounting_period:{reports.close_readiness.period_key}",
                    *[
                        f"close_check:{item.key}"
                        for item in reports.close_readiness.items
                        if item.status == "block"
                    ],
                ],
            )
        )
    if posting.exception_count:
        score -= min(25, posting.exception_count * 5)
        risks.append(
            ManagementRiskAlert(
                severity="warning",
                item="Accounting source exceptions",
                reason=(
                    f"{posting.exception_count} operational accounting sources "
                    "need evidence or classification review."
                ),
                evidence=[
                    item["citation"]
                    for item in posting_candidates
                    if item["readiness"] == "exception"
                ][:10]
                or ["accounting_posting_queue"],
            )
        )
    unmatched_bank_lines = banking.summary["unmatched_transactions"]
    if unmatched_bank_lines:
        score -= min(25, unmatched_bank_lines * 3)
        risks.append(
            ManagementRiskAlert(
                severity="warning",
                item="Bank matching",
                reason=(
                    f"{unmatched_bank_lines} bank lines remain unmatched; "
                    f"{len(bank_matches)} have one exact cash candidate and "
                    f"{ambiguous_bank_lines} are ambiguous."
                ),
                evidence=[
                    *[item["bank_transaction_citation"] for item in bank_matches[:10]],
                    "finance_banking_workspace",
                ],
            )
        )
    if ledger.summary.out_of_balance_entries:
        score -= 40
        risks.append(
            ManagementRiskAlert(
                severity="critical",
                item="Journal control",
                reason=(
                    f"{ledger.summary.out_of_balance_entries} journal entries "
                    "failed the balance control."
                ),
                evidence=["accounting_ledger:journal_balance_control"],
            )
        )

    margin_basis_points = (
        round(
            overview.summary.company_net_cents / overview.summary.collected_revenue_cents * 10_000
        )
        if overview.summary.collected_revenue_cents
        else None
    )
    context = {
        "reporting_period_days": period_days,
        "period_start_at": overview.period_start_at,
        "period_end_at": overview.period_end_at,
        "summary": overview.summary.model_dump(mode="json"),
        "previous_summary": (
            overview.previous_summary.model_dump(mode="json") if overview.previous_summary else None
        ),
        "company_margin_basis_points": margin_basis_points,
        "reconciliation_exceptions": [
            {
                "reconciliation_id": str(item.id),
                "status": item.status,
                "gross_revenue_cents": item.gross_revenue_cents,
                "adjusted_deal_margin_cents": item.adjusted_deal_margin_cents,
                "total_compensation_cents": item.total_compensation_cents,
                "company_profit_cents": item.company_profit_cents,
                "company_margin_basis_points": item.company_margin_basis_points,
                "target_margin_basis_points": item.target_margin_basis_points,
            }
            for item in reconciliation_exceptions
        ],
        "pending_revenue": [
            {
                "revenue_record_id": str(item.id),
                "amount_cents": item.amount_cents,
                "source": item.source,
                "has_lead_link": item.lead_id is not None,
                "has_transaction_link": item.transaction_id is not None,
            }
            for item in pending_revenue
        ],
        "unlinked_revenue_count": len(unlinked_revenue),
        "compensation_calculation_count": len(overview.compensation_calculations),
        "active_compensation_rule_count": sum(
            item.is_active for item in overview.compensation_rules
        ),
        "accounting_review": {
            "report_period": {
                "start_on": start_on.isoformat(),
                "end_on": end_on.isoformat(),
                "accounting_method": reports.accounting_method,
            },
            "statement_summary": {
                "revenue_cents": reports.profit_and_loss.revenue.total_cents,
                "cost_of_revenue_cents": (reports.profit_and_loss.cost_of_revenue.total_cents),
                "operating_expense_cents": (reports.profit_and_loss.operating_expenses.total_cents),
                "net_income_cents": reports.profit_and_loss.net_income_cents,
                "cash_change_cents": reports.cash_flow.net_change_cents,
                "total_assets_cents": reports.balance_sheet.total_assets_cents,
                "trial_balance_balanced": reports.trial_balance.balanced,
                "balance_sheet_balanced": reports.balance_sheet.balanced,
            },
            "prior_period_variances": statement_variances,
            "close_readiness": reports.close_readiness.model_dump(mode="json"),
            "posting_candidates": posting_candidates[:50],
            "bank_match_candidates": bank_matches[:50],
            "ambiguous_bank_line_count": ambiguous_bank_lines,
            "ledger_summary": ledger.summary.model_dump(mode="json"),
            "general_ledger_evidence": [
                {
                    **item.model_dump(mode="json"),
                    "citation": (f"journal_line:{item.journal_entry_id}:{item.account_code}"),
                }
                for item in reports.general_ledger[:100]
            ],
            "authority": {
                "mode": "draft_only",
                "may_prepare_explanations": True,
                "may_propose_classification": True,
                "may_propose_balanced_journal": True,
                "may_propose_bank_match": True,
                "may_prepare_close_checklist": True,
                "may_approve_or_post": False,
                "may_match_bank_transaction": False,
                "may_close_period": False,
                "may_move_money": False,
                "may_finalize_tax_treatment": False,
            },
        },
    }
    return _result(
        score,
        gaps,
        risks,
        [
            _metric(
                "Ledger net income",
                _money(reports.profit_and_loss.net_income_cents),
                f"{start_on} through {end_on}",
                ("success" if reports.profit_and_loss.net_income_cents >= 0 else "danger"),
            ),
            _metric(
                "Close blockers",
                str(reports.close_readiness.blocking_count),
                f"{reports.close_readiness.warning_count} evidence warnings",
                "warning" if reports.close_readiness.blocking_count else "success",
            ),
            _metric(
                "Posting candidates",
                str(sum(item["readiness"] == "ready" for item in posting_candidates)),
                f"{posting.exception_count} exceptions",
                "warning" if posting.exception_count else "info",
            ),
            _metric(
                "Exact bank candidates",
                str(len(bank_matches)),
                f"{unmatched_bank_lines} unmatched lines",
                "warning" if unmatched_bank_lines else "success",
            ),
        ],
        context,
    )


def _posting_candidates(posting: Any) -> list[dict[str, Any]]:
    rules = {item.id: item for item in posting.rules}
    result: list[dict[str, Any]] = []
    for item in posting.source_items:
        if item.journal_entry_id is not None:
            continue
        rule = rules.get(item.rule_id)
        citation = f"accounting_source:{item.source_type}:{item.source_id}:{item.posting_purpose}"
        result.append(
            {
                "citation": citation,
                "source_type": item.source_type,
                "source_id": item.source_id,
                "posting_purpose": item.posting_purpose,
                "label": item.label,
                "amount_cents": item.amount_cents,
                "readiness": item.readiness,
                "readiness_detail": item.readiness_detail,
                "proposed_debit_account_key": (rule.debit_account_key if rule else None),
                "proposed_credit_account_key": (rule.credit_account_key if rule else None),
                "posting_rule": (
                    f"accounting_posting_rule:{rule.id}:v{rule.version_number}" if rule else None
                ),
                "evidence_references": item.evidence_references,
                "requires_human_journal_review": True,
            }
        )
    return result


def _bank_match_candidates(
    banking: Any,
) -> tuple[list[dict[str, Any]], int]:
    used_journal_ids = {
        str(item.journal_entry_id)
        for item in banking.transactions
        if item.journal_entry_id is not None
    }
    journals_by_amount: dict[int, list[dict[str, Any]]] = {}
    for journal in banking.posted_journals:
        journal_id = str(journal["id"])
        if journal_id in used_journal_ids:
            continue
        amount = int(journal["cash_delta_cents"])
        journals_by_amount.setdefault(amount, []).append(journal)
    unmatched_by_amount: dict[int, list[Any]] = {}
    for transaction in banking.transactions:
        if transaction.status == "unmatched":
            unmatched_by_amount.setdefault(transaction.amount_cents, []).append(transaction)
    suggestions: list[dict[str, Any]] = []
    ambiguous = 0
    for amount, transactions in unmatched_by_amount.items():
        candidates = journals_by_amount.get(amount, [])
        if len(transactions) != 1 or len(candidates) != 1:
            if candidates:
                ambiguous += len(transactions)
            continue
        transaction = transactions[0]
        journal = candidates[0]
        suggestions.append(
            {
                "bank_transaction_citation": (f"bank_transaction:{transaction.id}"),
                "journal_citation": f"journal_entry:{journal['id']}",
                "occurred_on": transaction.occurred_on.isoformat(),
                "description": transaction.description,
                "amount_cents": transaction.amount_cents,
                "journal_entry_number": journal["entry_number"],
                "journal_memo": journal["memo"],
                "match_basis": "one unused posted journal has the exact cash movement",
                "confidence": "candidate_only",
                "requires_human_match_decision": True,
            }
        )
    return suggestions, ambiguous


def _statement_variances(
    current: Any,
    previous: Any,
    current_start: date,
    current_end: date,
    previous_start: date,
    previous_end: date,
) -> list[dict[str, Any]]:
    values = (
        (
            "Revenue",
            current.profit_and_loss.revenue.total_cents,
            previous.profit_and_loss.revenue.total_cents,
        ),
        (
            "Cost of revenue",
            current.profit_and_loss.cost_of_revenue.total_cents,
            previous.profit_and_loss.cost_of_revenue.total_cents,
        ),
        (
            "Operating expenses",
            current.profit_and_loss.operating_expenses.total_cents,
            previous.profit_and_loss.operating_expenses.total_cents,
        ),
        (
            "Net income",
            current.profit_and_loss.net_income_cents,
            previous.profit_and_loss.net_income_cents,
        ),
        (
            "Cash change",
            current.cash_flow.net_change_cents,
            previous.cash_flow.net_change_cents,
        ),
    )
    return [
        {
            "metric": label,
            "current_cents": current_amount,
            "previous_cents": previous_amount,
            "change_cents": current_amount - previous_amount,
            "change_basis_points": (
                round((current_amount - previous_amount) / abs(previous_amount) * 10_000)
                if previous_amount
                else None
            ),
            "current_citation": (f"financial_statement:{current_start}:{current_end}:{label}"),
            "previous_citation": (f"financial_statement:{previous_start}:{previous_end}:{label}"),
        }
        for label, current_amount, previous_amount in values
    ]


def _marketing_facts(
    db: Session,
    principal: Principal,
    period_days: int,
) -> ManagementFacts:
    overview = get_marketing_overview(db, principal, period_days)
    exceptions = [
        item
        for item in overview.campaigns
        if (
            item.marketing_spend_cents > 0
            and (
                item.leads_created == 0
                or item.contracted_leads == 0
                or (
                    item.return_on_ad_spend_basis_points is not None
                    and item.return_on_ad_spend_basis_points < 10_000
                )
            )
        )
    ]
    score = 100
    gaps: list[str] = []
    risks: list[ManagementRiskAlert] = []
    if not overview.campaigns:
        gaps.append("No attributed campaign records exist in this reporting period.")
        score -= 30
    if overview.summary.total_spend_cents and overview.summary.leads_created < 5:
        gaps.append("Paid-source sample size is too small for a dependable budget conclusion.")
        score -= 15
    if exceptions:
        score -= min(30, len(exceptions) * 10)
        risks.append(
            ManagementRiskAlert(
                severity="warning",
                item="Source economics",
                reason=f"{len(exceptions)} campaigns have spend without a dependable return.",
                evidence=["Marketing attribution and spend ledger"],
            )
        )
    if overview.public_funnel.form_starts and not overview.public_funnel.form_submits:
        score -= 25
        risks.append(
            ManagementRiskAlert(
                severity="critical",
                item="Seller funnel",
                reason="The public form has starts but no successful submissions.",
                evidence=["Public conversion event ledger"],
            )
        )
    if overview.summary.pending_offline_exports:
        score -= min(15, overview.summary.pending_offline_exports * 3)
        risks.append(
            ManagementRiskAlert(
                severity="warning",
                item="Offline conversions",
                reason=(
                    f"{overview.summary.pending_offline_exports} conversion records "
                    "await approved provider delivery."
                ),
                evidence=["Offline conversion export ledger"],
            )
        )
    if not overview.web_vitals:
        gaps.append("No current Core Web Vitals sample is available.")
        score -= 5

    context = {
        "reporting_period_days": period_days,
        "period_start_at": overview.period_start_at,
        "period_end_at": overview.period_end_at,
        "summary": overview.summary.model_dump(mode="json"),
        "previous_summary": (
            overview.previous_summary.model_dump(mode="json") if overview.previous_summary else None
        ),
        "public_funnel": overview.public_funnel.model_dump(mode="json"),
        "web_vitals": [item.model_dump(mode="json") for item in overview.web_vitals],
        "campaigns": [item.model_dump(mode="json") for item in overview.campaigns[:30]],
        "exception_campaigns": [
            {
                "source": item.source,
                "medium": item.medium,
                "campaign": item.campaign,
            }
            for item in exceptions
        ],
    }
    return _result(
        score,
        gaps,
        risks,
        [
            _metric(
                "Attributed spend",
                _money(overview.summary.total_spend_cents),
                f"{len(overview.campaigns)} source rows",
                "info",
            ),
            _metric(
                "Qualified revenue",
                _money(overview.summary.collected_revenue_cents),
                _roas(overview.summary.return_on_ad_spend_basis_points),
                "success"
                if (overview.summary.return_on_ad_spend_basis_points or 0) >= 10_000
                else "warning",
            ),
            _metric(
                "Leads / contracts",
                (f"{overview.summary.leads_created} / {overview.summary.contracted_leads}"),
                f"CPL {_money(overview.summary.cost_per_lead_cents)}",
                "info",
            ),
            _metric(
                "Pending exports",
                str(overview.summary.pending_offline_exports),
                "Provider delivery remains human-approved",
                "warning" if overview.summary.pending_offline_exports else "success",
            ),
        ],
        context,
    )


def _operations_facts(
    db: Session,
    principal: Principal,
    period_days: int,
) -> ManagementFacts:
    now = datetime.now(UTC)
    start_at = now - timedelta(days=period_days)
    dashboard = get_dashboard_summary(db, principal)
    finance = get_finance_overview(db, principal, period_days)
    marketing = get_marketing_overview(db, principal, period_days)
    overdue_tasks = int(
        db.scalar(
            select(func.count(Task.id)).where(
                Task.organization_id == principal.organization_id,
                Task.status.in_(("open", "in_progress")),
                Task.due_at.is_not(None),
                Task.due_at < now,
                and_(
                    or_(
                        Task.lead_id.is_(None),
                        Task.lead_id.in_(
                            select(Lead.id).where(
                                Lead.organization_id == principal.organization_id,
                                Lead.archived_at.is_(None),
                                Lead.stage_key.not_in(("dead", "disqualified")),
                            )
                        ),
                    ),
                    or_(
                        Task.deal_id.is_(None),
                        Task.deal_id.in_(
                            select(Deal.id).where(
                                Deal.organization_id == principal.organization_id,
                                Deal.stage_key.not_in(
                                    ("cancelled", "canceled", "closed", "dead", "funded")
                                ),
                            )
                        ),
                    ),
                ),
            )
        )
        or 0
    )
    unassigned_leads = _count(
        db,
        Lead,
        Lead.organization_id == principal.organization_id,
        Lead.archived_at.is_(None),
        Lead.assigned_user_id.is_(None),
    )
    upcoming_appointments = _count(
        db,
        Appointment,
        Appointment.organization_id == principal.organization_id,
        Appointment.status.in_(["scheduled", "confirmed"]),
        Appointment.scheduled_start_at >= now,
        Appointment.scheduled_start_at <= now + timedelta(days=7),
    )
    reconciliation_exceptions = _count(
        db,
        DealReconciliation,
        DealReconciliation.organization_id == principal.organization_id,
        (
            (DealReconciliation.status != "approved")
            | (
                DealReconciliation.company_margin_basis_points
                < DealReconciliation.target_margin_basis_points
            )
        ),
    )
    failed_ai_runs = _count(
        db,
        AiRunLog,
        AiRunLog.organization_id == principal.organization_id,
        AiRunLog.started_at >= start_at,
        AiRunLog.status.in_(["failed", "blocked"]),
    )
    open_provider_failures = int(
        db.scalar(
            select(func.count(OperationalFailure.id)).where(OperationalFailure.status == "open")
        )
        or 0
    )

    score = 100
    gaps: list[str] = []
    risks: list[ManagementRiskAlert] = []
    for count, deduction, item, reason, evidence in (
        (
            overdue_tasks,
            4,
            "Overdue work",
            f"{overdue_tasks} tasks are past due.",
            "Task ledger",
        ),
        (
            unassigned_leads,
            5,
            "Lead ownership",
            f"{unassigned_leads} active leads have no owner.",
            "Lead assignment ledger",
        ),
        (
            reconciliation_exceptions,
            10,
            "Financial close",
            f"{reconciliation_exceptions} reconciliations require intervention.",
            "Disposition reconciliation ledger",
        ),
        (
            open_provider_failures,
            8,
            "Provider operations",
            f"{open_provider_failures} provider failures remain open.",
            "Operational failure ledger",
        ),
        (
            failed_ai_runs,
            3,
            "AI operations",
            f"{failed_ai_runs} AI runs were blocked or failed.",
            "Governed AI run ledger",
        ),
    ):
        if not count:
            continue
        score -= min(25, count * deduction)
        risks.append(
            ManagementRiskAlert(
                severity=(
                    "critical" if item in {"Financial close", "Provider operations"} else "warning"
                ),
                item=item,
                reason=reason,
                evidence=[evidence],
            )
        )
    if dashboard.total_leads == 0:
        gaps.append("No active lead baseline is available.")
        score -= 10
    if finance.summary.collected_revenue_cents == 0:
        gaps.append("No collected revenue exists in the reporting period.")
        score -= 10
    if marketing.summary.total_spend_cents and marketing.summary.leads_created < 5:
        gaps.append("Marketing sample size is too small for scaling decisions.")
        score -= 10

    context = {
        "reporting_period_days": period_days,
        "generated_at": now,
        "pipeline": {
            "total_active_leads": dashboard.total_leads,
            "new_paid_leads": dashboard.new_paid_leads,
            "active_contracts": dashboard.active_contracts,
            "offers_pending": dashboard.offers_pending,
            "stage_counts": [item.model_dump(mode="json") for item in dashboard.pipeline],
            "unassigned_leads": unassigned_leads,
            "upcoming_appointments_7_days": upcoming_appointments,
            "overdue_tasks": overdue_tasks,
        },
        "finance": {
            **finance.summary.model_dump(mode="json"),
            "reconciliation_exception_count": reconciliation_exceptions,
        },
        "marketing": marketing.summary.model_dump(mode="json"),
        "operations": {
            "open_provider_failure_count": open_provider_failures,
            "failed_or_blocked_ai_run_count": failed_ai_runs,
        },
        "source_timestamps": {
            "dashboard": now,
            "finance_period_end": finance.period_end_at,
            "marketing_period_end": marketing.period_end_at,
        },
    }
    return _result(
        score,
        gaps,
        risks,
        [
            _metric(
                "Active pipeline",
                str(dashboard.total_leads),
                f"{dashboard.active_contracts} contracts",
                "info",
            ),
            _metric(
                "Overdue / unassigned",
                f"{overdue_tasks} / {unassigned_leads}",
                "Execution pressure",
                "warning" if overdue_tasks or unassigned_leads else "success",
            ),
            _metric(
                "Company net",
                _money(finance.summary.company_net_cents),
                f"Last {period_days} days",
                "success" if finance.summary.company_net_cents >= 0 else "danger",
            ),
            _metric(
                "Provider / AI exceptions",
                f"{open_provider_failures} / {failed_ai_runs}",
                "Open operational signals",
                "warning" if open_provider_failures or failed_ai_runs else "success",
            ),
        ],
        context,
    )


def _result(
    score: int,
    gaps: list[str],
    risks: list[ManagementRiskAlert],
    metrics: list[ManagementMetricCard],
    context: dict[str, Any],
) -> ManagementFacts:
    score = max(0, min(100, score))
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    fingerprint = hashlib.sha256(
        json.dumps(context, sort_keys=True, default=str).encode()
    ).hexdigest()
    return {
        "health_score": score,
        "health_band": (
            "healthy" if score >= 80 else "needs_review" if score >= 50 else "critical"
        ),
        "readiness_gaps": gaps,
        "risk_alerts": sorted(risks, key=lambda item: severity_order[item.severity]),
        "metric_cards": metrics,
        "context": context,
        "fingerprint": fingerprint,
    }


def _metric(
    label: str,
    value: str,
    detail: str,
    tone: Literal["neutral", "info", "success", "warning", "danger"],
) -> ManagementMetricCard:
    return ManagementMetricCard(label=label, value=value, detail=detail, tone=tone)


def _count(
    db: Session,
    model: type[Any],
    *conditions: Any,
) -> int:
    return int(db.scalar(select(func.count(model.id)).where(*conditions)) or 0)


def _money(value: int | None) -> str:
    if value is None:
        return "N/A"
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value) / 100:,.0f}"


def _basis_points(value: int | None) -> str:
    return "No margin baseline" if value is None else f"{value / 100:.1f}% margin"


def _roas(value: int | None) -> str:
    return "No ROAS baseline" if value is None else f"{value / 10_000:.2f}x ROAS"
