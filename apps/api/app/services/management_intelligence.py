import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, TypedDict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.models.foundation import (
    AiRunLog,
    Appointment,
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
from app.services.finance import get_finance_overview
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
    if capability_key == "marketing.analyze":
        return _marketing_facts(db, principal, period_days)
    if capability_key == "operations.brief":
        return _operations_facts(db, principal, period_days)
    raise ValueError("Unsupported management capability.")


def _finance_facts(
    db: Session,
    principal: Principal,
    period_days: int,
) -> ManagementFacts:
    overview = get_finance_overview(db, principal, period_days)
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
    pending_revenue = [
        item for item in overview.revenue_records if item.status == "pending"
    ]
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
                evidence=["Finance revenue ledger"],
            )
        )
    if unlinked_revenue:
        score -= min(20, len(unlinked_revenue) * 5)
        risks.append(
            ManagementRiskAlert(
                severity="critical",
                item="Unlinked revenue",
                reason=f"{len(unlinked_revenue)} records lack complete deal linkage.",
                evidence=["Finance revenue ledger linkage"],
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
                evidence=["Disposition reconciliation ledger"],
            )
        )
    if overview.summary.company_net_cents < 0:
        score -= 30
        risks.append(
            ManagementRiskAlert(
                severity="critical",
                item="Company net",
                reason="Recorded costs and compensation exceed collected revenue.",
                evidence=["Finance period summary"],
            )
        )
    if not any(item.is_active for item in overview.compensation_rules):
        gaps.append("No active legacy compensation rule is recorded.")
        score -= 10

    margin_basis_points = (
        round(
            overview.summary.company_net_cents
            / overview.summary.collected_revenue_cents
            * 10_000
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
            overview.previous_summary.model_dump(mode="json")
            if overview.previous_summary
            else None
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
        "compensation_calculation_count": len(
            overview.compensation_calculations
        ),
        "active_compensation_rule_count": sum(
            item.is_active for item in overview.compensation_rules
        ),
    }
    return _result(
        score,
        gaps,
        risks,
        [
            _metric(
                "Collected revenue",
                _money(overview.summary.collected_revenue_cents),
                f"Last {period_days} days",
                "success" if overview.summary.collected_revenue_cents else "neutral",
            ),
            _metric(
                "Company net",
                _money(overview.summary.company_net_cents),
                _basis_points(margin_basis_points),
                "success" if overview.summary.company_net_cents >= 0 else "danger",
            ),
            _metric(
                "Reconciliation exceptions",
                str(len(reconciliation_exceptions)),
                "Human approval required",
                "warning" if reconciliation_exceptions else "success",
            ),
            _metric(
                "Pending revenue",
                str(len(pending_revenue)),
                f"{len(unlinked_revenue)} linkage gaps",
                "warning" if pending_revenue else "success",
            ),
        ],
        context,
    )


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
            overview.previous_summary.model_dump(mode="json")
            if overview.previous_summary
            else None
        ),
        "public_funnel": overview.public_funnel.model_dump(mode="json"),
        "web_vitals": [item.model_dump(mode="json") for item in overview.web_vitals],
        "campaigns": [
            item.model_dump(mode="json") for item in overview.campaigns[:30]
        ],
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
                (
                    f"{overview.summary.leads_created} / "
                    f"{overview.summary.contracted_leads}"
                ),
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
    overdue_tasks = _count(
        db,
        Task,
        Task.organization_id == principal.organization_id,
        Task.status != "completed",
        Task.due_at.is_not(None),
        Task.due_at < now,
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
            select(func.count(OperationalFailure.id)).where(
                OperationalFailure.status == "open"
            )
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
                    "critical"
                    if item in {"Financial close", "Provider operations"}
                    else "warning"
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
            "stage_counts": [
                item.model_dump(mode="json") for item in dashboard.pipeline
            ],
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
    return int(
        db.scalar(select(func.count(model.id)).where(*conditions))
        or 0
    )


def _money(value: int | None) -> str:
    if value is None:
        return "N/A"
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value) / 100:,.0f}"


def _basis_points(value: int | None) -> str:
    return "No margin baseline" if value is None else f"{value / 100:.1f}% margin"


def _roas(value: int | None) -> str:
    return "No ROAS baseline" if value is None else f"{value / 10_000:.2f}x ROAS"
