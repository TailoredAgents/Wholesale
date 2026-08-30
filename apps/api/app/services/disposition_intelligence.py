from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from statistics import median
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.domain.rbac import PermissionKeys
from app.models.foundation import (
    Buyer,
    BuyerEngagement,
    BuyerOffer,
    DealReconciliation,
    DispositionBuyerOutcome,
    DispositionBuyerPoolCandidate,
    DispositionBuyerSelection,
    DispositionBuyerSelectionSlot,
    DispositionCampaign,
    DispositionCase,
    DispositionCopilotRecommendation,
    DispositionCopilotReview,
    DispositionOutreachDelivery,
    DispositionPackageVersion,
    DispositionProviderEvidence,
    DispositionReplyLink,
    Lead,
    Property,
    RevenueRecord,
    Transaction,
    User,
)
from app.schemas.disposition_intelligence import (
    DispositionActivityMetrics,
    DispositionAgentMetric,
    DispositionBuyerMetric,
    DispositionCorrectionMetrics,
    DispositionEconomicsMetrics,
    DispositionFilterOption,
    DispositionFilterOptions,
    DispositionIntelligenceAccess,
    DispositionIntelligenceFilters,
    DispositionIntelligenceResponse,
    DispositionIntelligenceScope,
    DispositionLearningMetrics,
    DispositionMetricProvenance,
    DispositionMilestoneMetric,
    DispositionRateMetric,
    DispositionSourceMetric,
    IntelligenceDataQuality,
    MetricState,
)

MINIMUM_COMPARISON_SAMPLE = 10
TERMINAL_TRANSACTION_STATUSES = {"funded", "closed", "complete", "completed"}
COLLECTED_REVENUE_STATUSES = {"collected", "received", "paid"}
EXTERNAL_SOURCE_KEYS = {"investorlift", "provider", "external", "api"}


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _hours(start: datetime | None, end: datetime | None) -> float | None:
    left, right = _aware(start), _aware(end)
    if left is None or right is None or right < left:
        return None
    return round((right - left).total_seconds() / 3600, 2)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - lower
    return round(ordered[lower] * (1 - weight) + ordered[upper] * weight, 2)


def _state(count: int, expected: int | None = None) -> MetricState:
    if count <= 0:
        return "unavailable"
    if expected is not None and count < expected:
        return "partial"
    return "known"


def _rate(key: str, label: str, numerator: int, denominator: int) -> DispositionRateMetric:
    return DispositionRateMetric(
        key=key,
        label=label,
        state="known" if denominator else "unavailable",
        numerator=numerator,
        denominator=denominator,
        rate_percent=(round(numerator / denominator * 100, 1) if denominator else None),
    )


def _source_identity(buyer: Buyer) -> tuple[str, str, str]:
    source_key = (buyer.source_key or "stonegate_network").strip().lower()
    if source_key in EXTERNAL_SOURCE_KEYS:
        category = "provider"
    elif buyer.relationship_owner_user_id:
        category = "agent_owned"
    else:
        category = "stonegate_network"
    key = source_key if category == "provider" else category
    label = buyer.source_detail or source_key.replace("_", " ").title()
    if category == "agent_owned":
        label = "Agent-owned network"
    elif category == "stonegate_network":
        label = "Stonegate network"
    return key, label, category


def _case_anchor(case: DispositionCase, transaction: Transaction | None) -> datetime:
    if transaction is not None:
        return (
            _aware(transaction.contract_executed_at)
            or _aware(transaction.funded_at)
            or _aware(transaction.closed_at)
            or _aware(transaction.created_at)
            or datetime.min.replace(tzinfo=UTC)
        )
    return _aware(case.created_at) or datetime.min.replace(tzinfo=UTC)


def _option_rows(values: Iterable[tuple[str, str]]) -> list[DispositionFilterOption]:
    counts: Counter[tuple[str, str]] = Counter(values)
    return [
        DispositionFilterOption(value=value, label=label, count=count)
        for (value, label), count in sorted(counts.items(), key=lambda item: item[0][1].lower())
    ]


def _milestone(key: str, label: str, values: list[float], total: int) -> DispositionMilestoneMetric:
    return DispositionMilestoneMetric(
        key=key,
        label=label,
        state=_state(len(values), total if total else None),
        count=len(values),
        median_hours=round(median(values), 2) if values else None,
        p90_hours=_percentile(values, 0.9),
    )


def read_disposition_intelligence(
    db: Session,
    principal: Principal,
    *,
    deal_id: UUID | None = None,
    buyer_id: UUID | None = None,
    agent_user_id: UUID | None = None,
    source: str | None = None,
    market: str | None = None,
    asset_class: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> DispositionIntelligenceResponse:
    if start_at and end_at and _aware(start_at) > _aware(end_at):
        raise ValueError("start_at must be on or before end_at.")

    org_id = principal.organization_id

    def all_for(model):
        return list(db.scalars(select(model).where(model.organization_id == org_id)).all())

    all_cases = all_for(DispositionCase)
    transactions = {row.id: row for row in all_for(Transaction)}
    leads = {row.id: row for row in all_for(Lead)}
    properties = {row.id: row for row in all_for(Property)}
    buyers_by_id = {row.id: row for row in all_for(Buyer)}
    users = {row.id: row for row in all_for(User)}

    packages = all_for(DispositionPackageVersion)
    deliveries = all_for(DispositionOutreachDelivery)
    replies = all_for(DispositionReplyLink)
    provider_evidence = all_for(DispositionProviderEvidence)
    engagements = all_for(BuyerEngagement)
    offers = all_for(BuyerOffer)
    selections = all_for(DispositionBuyerSelection)
    slots = all_for(DispositionBuyerSelectionSlot)
    outcomes = all_for(DispositionBuyerOutcome)
    reconciliations = all_for(DealReconciliation)
    revenues = all_for(RevenueRecord)
    campaigns = all_for(DispositionCampaign)
    candidates = all_for(DispositionBuyerPoolCandidate)
    recommendations = all_for(DispositionCopilotRecommendation)
    reviews = all_for(DispositionCopilotReview)

    def by_case(rows: Iterable[object]) -> defaultdict[UUID, list[object]]:
        return _group(rows, "disposition_case_id")

    packages_by_case = by_case(packages)
    deliveries_by_case = by_case(deliveries)
    replies_by_case = by_case(replies)
    evidence_by_case = by_case(provider_evidence)
    engagements_by_case = by_case(engagements)
    offers_by_case = by_case(offers)
    selections_by_case = by_case(selections)
    slots_by_case = by_case(slots)
    outcomes_by_case = by_case(outcomes)
    campaigns_by_case = by_case(campaigns)
    review_by_recommendation = {row.recommendation_id: row for row in reviews}

    def involved_buyer_ids(case_id: UUID) -> set[UUID]:
        result = {
            row.buyer_id
            for rows in (
                offers_by_case[case_id],
                engagements_by_case[case_id],
                slots_by_case[case_id],
                outcomes_by_case[case_id],
            )
            for row in rows
            if row.buyer_id is not None
        }
        result.update(row.buyer_id for row in replies_by_case[case_id] if row.buyer_id is not None)
        return result

    def involved_agent_ids(case: DispositionCase) -> set[UUID]:
        result = {case.owner_user_id} if case.owner_user_id else set()
        result.update(
            row.approved_by_user_id for row in packages_by_case[case.id] if row.approved_by_user_id
        )
        result.update(
            row.created_by_user_id for row in campaigns_by_case[case.id] if row.created_by_user_id
        )
        result.update(
            row.actor_user_id for row in engagements_by_case[case.id] if row.actor_user_id
        )
        result.update(
            row.approved_by_user_id
            for row in selections_by_case[case.id]
            if row.approved_by_user_id
        )
        result.update(
            row.recorded_by_user_id for row in outcomes_by_case[case.id] if row.recorded_by_user_id
        )
        return result

    filters = DispositionIntelligenceFilters(
        deal_id=deal_id,
        buyer_id=buyer_id,
        agent_user_id=agent_user_id,
        source=source,
        market=market,
        asset_class=asset_class,
        start_at=start_at,
        end_at=end_at,
    )

    normalized_source = source.strip().lower() if source else None
    normalized_market = market.strip().lower() if market else None
    normalized_asset = asset_class.strip().lower() if asset_class else None
    selected_cases: list[DispositionCase] = []
    for case in all_cases:
        transaction = transactions.get(case.transaction_id)
        lead = leads.get(case.lead_id)
        property_record = properties.get(case.property_id)
        anchor = _case_anchor(case, transaction)
        case_buyer_ids = involved_buyer_ids(case.id)
        source_tokens = {
            token
            for related_buyer_id in case_buyer_ids
            if (related_buyer := buyers_by_id.get(related_buyer_id)) is not None
            for token in (_source_identity(related_buyer)[0], _source_identity(related_buyer)[2])
        }
        market_tokens = {
            value.strip().lower()
            for value in (
                property_record.state if property_record else None,
                property_record.city if property_record else None,
                property_record.county if property_record else None,
            )
            if value
        }
        if deal_id and case.deal_id != deal_id:
            continue
        if buyer_id and buyer_id not in case_buyer_ids:
            continue
        if agent_user_id and agent_user_id not in involved_agent_ids(case):
            continue
        if normalized_source and normalized_source not in source_tokens:
            continue
        if normalized_market and normalized_market not in market_tokens:
            continue
        if normalized_asset and (lead is None or lead.asset_class.lower() != normalized_asset):
            continue
        if start_at and anchor < _aware(start_at):
            continue
        if end_at and anchor > _aware(end_at):
            continue
        selected_cases.append(case)

    case_ids = {case.id for case in selected_cases}
    filtered_packages = [row for row in packages if row.disposition_case_id in case_ids]
    filtered_deliveries = [
        row for row in deliveries if row.disposition_case_id in case_ids and row.sent_at is not None
    ]
    filtered_replies = [
        row
        for row in replies
        if row.disposition_case_id in case_ids and row.routing_status == "matched"
    ]
    filtered_evidence = [
        row
        for row in provider_evidence
        if row.disposition_case_id in case_ids and row.review_status == "reviewed"
    ]
    filtered_engagements = [row for row in engagements if row.disposition_case_id in case_ids]
    filtered_offers = [row for row in offers if row.disposition_case_id in case_ids]
    filtered_selections = [
        row
        for row in selections
        if row.disposition_case_id in case_ids and row.status in {"active", "approved", "replaced"}
    ]
    filtered_slots = [row for row in slots if row.disposition_case_id in case_ids]
    filtered_outcomes = [row for row in outcomes if row.disposition_case_id in case_ids]

    primary_slots = [row for row in filtered_slots if row.role == "primary"]
    selected_offer_ids = {row.offer_id for row in primary_slots}
    deposits = [
        row
        for row in filtered_offers
        if row.id in selected_offer_ids and row.deposit_received_at is not None
    ]
    inquiries = [row for row in filtered_engagements if row.engagement_type == "inquiry"]
    inquiries.extend(row for row in filtered_evidence if row.event_type == "inquiry")
    showings = [
        row
        for row in filtered_engagements
        if row.engagement_type == "showing" and row.status not in {"cancelled", "no_show"}
    ]
    fallouts = [
        row
        for row in filtered_outcomes
        if row.outcome_type in {"buyer_fallout", "withdrawal", "missed_deadline"}
    ]
    retrades = [row for row in filtered_outcomes if row.outcome_type == "retrade"]

    completed_case_ids: set[UUID] = set()
    for case in selected_cases:
        transaction = transactions.get(case.transaction_id)
        has_completed_outcome = any(
            row.outcome_type == "completed_close" for row in outcomes_by_case[case.id]
        )
        is_terminal = bool(
            transaction
            and (
                transaction.funded_at
                or transaction.closed_at
                or transaction.status.lower() in TERMINAL_TRANSACTION_STATUSES
            )
        )
        if has_completed_outcome and is_terminal:
            completed_case_ids.add(case.id)

    approved_reconciliations = {
        row.disposition_case_id: row
        for row in reconciliations
        if row.disposition_case_id in completed_case_ids and row.status == "approved"
    }
    completed_transaction_ids = {
        case.transaction_id for case in selected_cases if case.id in completed_case_ids
    }
    collected_revenue_by_transaction: Counter[UUID] = Counter()
    for row in revenues:
        if (
            row.transaction_id in completed_transaction_ids
            and row.status.lower() in COLLECTED_REVENUE_STATUSES
        ):
            collected_revenue_by_transaction[row.transaction_id] += row.amount_cents

    private_visible = (
        PermissionKeys.VIEW_FINANCIALS in principal.permission_keys
        and PermissionKeys.VIEW_DISPOSITION_PRIVATE_ECONOMICS in principal.permission_keys
    )
    reconciliation_count = len(approved_reconciliations)
    if not completed_case_ids:
        economics_state: MetricState = "unavailable"
    elif reconciliation_count < len(completed_case_ids):
        economics_state = "partial"
    else:
        economics_state = "known"

    contracted_spread = sum(
        (transactions[case.transaction_id].assignment_fee_cents or 0)
        for case in selected_cases
        if case.id in completed_case_ids and case.transaction_id in transactions
    )
    collected_revenue = sum(collected_revenue_by_transaction.values())
    approved_profit = sum(row.company_profit_cents for row in approved_reconciliations.values())
    if not private_visible:
        contracted_spread_value = collected_revenue_value = approved_profit_value = None
        economics_detail = (
            "Private economics are hidden without both financial and disposition-economics access."
        )
    else:
        contracted_spread_value = contracted_spread
        collected_revenue_value = collected_revenue
        approved_profit_value = approved_profit
        economics_detail = (
            "Only funded or closed assignments with immutable completed-close "
            "evidence are counted. "
            "Approved finance reconciliation is tracked separately from contracted spread."
        )

    contract_to_package: list[float] = []
    contract_to_outreach: list[float] = []
    contract_to_inquiry: list[float] = []
    contract_to_offer: list[float] = []
    contract_to_selection: list[float] = []
    contract_to_deposit: list[float] = []
    contract_to_close: list[float] = []
    for case in selected_cases:
        transaction = transactions.get(case.transaction_id)
        start = transaction.contract_executed_at if transaction else None
        package_time = case.package_approved_at
        outreach_times = [row.sent_at for row in deliveries_by_case[case.id] if row.sent_at]
        inquiry_times = [
            row.occurred_at
            for row in engagements_by_case[case.id]
            if row.engagement_type == "inquiry"
        ]
        inquiry_times.extend(
            row.occurred_at
            for row in evidence_by_case[case.id]
            if row.event_type == "inquiry" and row.review_status == "reviewed"
        )
        offer_times = [row.received_at for row in offers_by_case[case.id]]
        selection_times = [
            row.approved_at for row in selections_by_case[case.id] if row.approved_at
        ]
        deposit_times = [
            row.deposit_received_at for row in offers_by_case[case.id] if row.deposit_received_at
        ]
        close_time = (transaction.funded_at or transaction.closed_at) if transaction else None
        for target, collection in (
            (package_time, contract_to_package),
            (min(outreach_times) if outreach_times else None, contract_to_outreach),
            (min(inquiry_times) if inquiry_times else None, contract_to_inquiry),
            (min(offer_times) if offer_times else None, contract_to_offer),
            (min(selection_times) if selection_times else None, contract_to_selection),
            (min(deposit_times) if deposit_times else None, contract_to_deposit),
            (close_time, contract_to_close),
        ):
            value = _hours(start, target)
            if value is not None:
                collection.append(value)

    milestone_total = sum(
        1
        for case in selected_cases
        if (
            transactions.get(case.transaction_id)
            and transactions[case.transaction_id].contract_executed_at
        )
    )
    milestones = [
        _milestone(
            "contract_to_package_approval",
            "Contract to package approval",
            contract_to_package,
            milestone_total,
        ),
        _milestone(
            "contract_to_first_outreach",
            "Contract to first outreach",
            contract_to_outreach,
            milestone_total,
        ),
        _milestone(
            "contract_to_first_inquiry",
            "Contract to first inquiry",
            contract_to_inquiry,
            milestone_total,
        ),
        _milestone(
            "contract_to_first_offer", "Contract to first offer", contract_to_offer, milestone_total
        ),
        _milestone(
            "contract_to_buyer_selection",
            "Contract to buyer selection",
            contract_to_selection,
            milestone_total,
        ),
        _milestone(
            "contract_to_deposit", "Contract to deposit", contract_to_deposit, milestone_total
        ),
        _milestone(
            "contract_to_close",
            "Contract to completed assignment",
            contract_to_close,
            milestone_total,
        ),
    ]

    source_rows: dict[str, dict[str, object]] = {}
    buyer_rows: dict[UUID, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def touch_source(buyer: Buyer, field: str, amount: int = 1) -> None:
        key, label, category = _source_identity(buyer)
        row = source_rows.setdefault(
            key,
            {
                "label": label,
                "category": category,
                "activity_count": 0,
                "offers": 0,
                "selected_buyers": 0,
                "completed_assignments": 0,
                "revenue": 0,
            },
        )
        row[field] = int(row[field]) + amount

    for row in filtered_replies:
        if row.buyer_id in buyers_by_id:
            buyer_rows[row.buyer_id]["replies"] += 1
            touch_source(buyers_by_id[row.buyer_id], "activity_count")
    for row in filtered_engagements:
        if row.engagement_type == "inquiry" and row.buyer_id in buyers_by_id:
            touch_source(buyers_by_id[row.buyer_id], "activity_count")
    for row in showings:
        if row.buyer_id in buyers_by_id:
            buyer_rows[row.buyer_id]["showings"] += 1
            touch_source(buyers_by_id[row.buyer_id], "activity_count")
    for row in filtered_offers:
        if row.buyer_id in buyers_by_id:
            buyer_rows[row.buyer_id]["offers"] += 1
            touch_source(buyers_by_id[row.buyer_id], "offers")
    for row in primary_slots:
        if row.buyer_id in buyers_by_id:
            buyer_rows[row.buyer_id]["selections"] += 1
            touch_source(buyers_by_id[row.buyer_id], "selected_buyers")
    for row in filtered_outcomes:
        if row.buyer_id not in buyers_by_id:
            continue
        if row.outcome_type == "completed_close" and row.disposition_case_id in completed_case_ids:
            buyer_rows[row.buyer_id]["completed"] += 1
            touch_source(buyers_by_id[row.buyer_id], "completed_assignments")
            case = next(
                (item for item in selected_cases if item.id == row.disposition_case_id), None
            )
            if case:
                touch_source(
                    buyers_by_id[row.buyer_id],
                    "revenue",
                    collected_revenue_by_transaction[case.transaction_id],
                )
        elif row in fallouts:
            buyer_rows[row.buyer_id]["fallouts"] += 1
        elif row in retrades:
            buyer_rows[row.buyer_id]["retrades"] += 1

    buyer_metrics = [
        DispositionBuyerMetric(
            buyer_id=buyer.id,
            name=buyer.name,
            state="known",
            replies=buyer_rows[buyer.id]["replies"],
            showings=buyer_rows[buyer.id]["showings"],
            offers=buyer_rows[buyer.id]["offers"],
            selections=buyer_rows[buyer.id]["selections"],
            completed_assignments=buyer_rows[buyer.id]["completed"],
            fallouts=buyer_rows[buyer.id]["fallouts"],
            retrades=buyer_rows[buyer.id]["retrades"],
            reliability_score_basis_points=buyer.reliability_score_basis_points,
            provenance=f"Buyer reliability ledger; source={_source_identity(buyer)[0]}",
        )
        for buyer in buyers_by_id.values()
        if buyer.id
        in {buyer_id for case in selected_cases for buyer_id in involved_buyer_ids(case.id)}
    ]
    buyer_metrics.sort(key=lambda row: (-row.completed_assignments, -row.offers, row.name.lower()))

    agent_rows: dict[UUID, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in filtered_packages:
        if row.approved_by_user_id:
            agent_rows[row.approved_by_user_id]["packages"] += 1
    campaign_by_id = {row.id: row for row in campaigns}
    delivery_by_id = {row.id: row for row in filtered_deliveries}
    for row in filtered_deliveries:
        campaign = campaign_by_id.get(row.disposition_campaign_id)
        if campaign:
            agent_rows[campaign.created_by_user_id]["outreach"] += 1
    for row in filtered_replies:
        delivery = delivery_by_id.get(row.outreach_delivery_id)
        campaign = campaign_by_id.get(delivery.disposition_campaign_id) if delivery else None
        if campaign:
            agent_rows[campaign.created_by_user_id]["replies"] += 1
    for row in filtered_selections:
        agent_rows[row.approved_by_user_id]["selections"] += 1
    for row in filtered_outcomes:
        agent_rows[row.recorded_by_user_id]["outcomes"] += 1
        if row.outcome_type == "completed_close" and row.disposition_case_id in completed_case_ids:
            agent_rows[row.recorded_by_user_id]["completed"] += 1
    agent_metrics = [
        DispositionAgentMetric(
            user_id=user_id,
            name=users[user_id].display_name if user_id in users else "Unknown user",
            state="known" if user_id in users else "partial",
            role="multi_role",
            packages_approved=values["packages"],
            outreach_sent=values["outreach"],
            replies_reviewed=values["replies"],
            selections_approved=values["selections"],
            outcomes_recorded=values["outcomes"],
            completed_assignments=values["completed"],
        )
        for user_id, values in agent_rows.items()
        if user_id is not None
    ]
    agent_metrics.sort(
        key=lambda row: (-row.completed_assignments, -row.outcomes_recorded, row.name.lower())
    )

    reviewed_case_ids = {
        recommendation.disposition_case_id
        for recommendation in recommendations
        if recommendation.disposition_case_id in completed_case_ids
        and (review := review_by_recommendation.get(recommendation.id)) is not None
        and review.decision in {"accepted", "edited"}
    }
    human_led_count = len(completed_case_ids - reviewed_case_ids)
    ai_assisted_count = len(reviewed_case_ids)
    comparison_allowed = min(human_led_count, ai_assisted_count) >= MINIMUM_COMPARISON_SAMPLE
    package_revision_count = sum(
        max(0, len(rows) - 1) for case_id, rows in packages_by_case.items() if case_id in case_ids
    )
    match_override_count = sum(
        1
        for row in candidates
        if row.disposition_case_id in case_ids
        and row.decision_updated_by_user_id is not None
        and row.decision_status not in {"pending", "unreviewed"}
    )
    ai_corrections = sum(
        1
        for recommendation in recommendations
        if recommendation.disposition_case_id in case_ids
        and (review := review_by_recommendation.get(recommendation.id)) is not None
        and review.decision == "edited"
    )
    backup_saves = sum(1 for row in filtered_selections if row.replaced_at is not None)

    source_metrics = [
        DispositionSourceMetric(
            key=key,
            label=str(values["label"]),
            category=str(values["category"]),
            state="partial",
            activity_count=int(values["activity_count"]),
            offers=int(values["offers"]),
            selected_buyers=int(values["selected_buyers"]),
            completed_assignments=int(values["completed_assignments"]),
            collected_revenue_cents=(int(values["revenue"]) if private_visible else None),
        )
        for key, values in source_rows.items()
    ]
    source_metrics.sort(
        key=lambda row: (-row.completed_assignments, -row.offers, row.label.lower())
    )

    activity = DispositionActivityMetrics(
        cases=len(selected_cases),
        packages_approved=sum(
            1 for row in filtered_packages if row.status == "approved" or row.approved_at
        ),
        outreach_sent=len(filtered_deliveries),
        replies=len(filtered_replies),
        inquiries=len(inquiries),
        showings=len(showings),
        offers=len(filtered_offers),
        selected_buyers=len({row.selection_id for row in primary_slots}),
        deposits=len(deposits),
    )
    economics = DispositionEconomicsMetrics(
        state=economics_state,
        completed_assignments=len(completed_case_ids),
        reconciled_completed_assignments=reconciliation_count,
        contracted_assignment_spread_cents=contracted_spread_value,
        collected_revenue_cents=collected_revenue_value,
        approved_company_profit_cents=approved_profit_value,
        campaign_cost_cents=None,
        cost_per_offer_cents=None,
        cost_per_selected_buyer_cents=None,
        cost_per_completed_assignment_cents=None,
        detail=economics_detail,
    )

    quality = [
        IntelligenceDataQuality(
            key="activity",
            label="Disposition activity",
            state=_state(len(selected_cases)),
            detail=(
                "Derived from organization-scoped disposition cases and immutable activity records."
            ),
            record_count=len(selected_cases),
        ),
        IntelligenceDataQuality(
            key="finance",
            label="Reconciled economics",
            state=economics_state,
            detail=(
                f"{reconciliation_count} of {len(completed_case_ids)} completed "
                "assignments have approved reconciliations."
            ),
            record_count=reconciliation_count,
        ),
        IntelligenceDataQuality(
            key="campaign_cost",
            label="Disposition campaign cost",
            state="unavailable",
            detail=(
                "No canonical case-level disposition cost ledger exists; marketing "
                "spend is intentionally not substituted."
            ),
            record_count=0,
        ),
        IntelligenceDataQuality(
            key="market",
            label="Market attribution",
            state="partial" if selected_cases else "unavailable",
            detail=(
                "Market filters use canonical property state, city, or county because "
                "disposition cases do not carry a frozen market ID."
            ),
            record_count=sum(1 for case in selected_cases if properties.get(case.property_id)),
        ),
        IntelligenceDataQuality(
            key="source_attribution",
            label="Winning buyer source",
            state="partial" if source_rows else "unavailable",
            detail=(
                "Source is derived from the current buyer provenance record; older "
                "completed assignments do not yet carry a frozen source snapshot."
            ),
            record_count=len(source_rows),
        ),
        IntelligenceDataQuality(
            key="ai_attribution",
            label="AI assistance attribution",
            state="partial" if recommendations else "unavailable",
            detail=(
                "Reviewed copilot cases are descriptive only; current records do not "
                "prove that AI caused an operational action."
            ),
            record_count=len(reviewed_case_ids),
        ),
    ]
    overall_state: MetricState = (
        "unavailable"
        if not selected_cases
        else ("partial" if any(row.state != "known" for row in quality) else "known")
    )

    deal_options = _option_rows(
        (
            str(case.deal_id),
            f"{properties[case.property_id].street_address}, {properties[case.property_id].city}"
            if case.property_id in properties
            else str(case.deal_id),
        )
        for case in all_cases
    )
    buyer_option_ids = {
        related_id for case in all_cases for related_id in involved_buyer_ids(case.id)
    }
    buyer_options = _option_rows(
        (str(item.id), item.name) for item in buyers_by_id.values() if item.id in buyer_option_ids
    )
    agent_option_ids = {related_id for case in all_cases for related_id in involved_agent_ids(case)}
    agent_options = _option_rows(
        (str(item.id), item.display_name) for item in users.values() if item.id in agent_option_ids
    )
    source_options = _option_rows(
        (_source_identity(item)[0], _source_identity(item)[1])
        for item in buyers_by_id.values()
        if item.id in buyer_option_ids
    )
    market_options = _option_rows(
        (item.state.lower(), item.state.upper())
        for item in properties.values()
        if any(case.property_id == item.id for case in all_cases) and item.state
    )
    asset_options = _option_rows(
        (item.asset_class.lower(), item.asset_class.title())
        for item in leads.values()
        if any(case.lead_id == item.id for case in all_cases)
    )

    return DispositionIntelligenceResponse(
        generated_at=datetime.now(UTC),
        scope=DispositionIntelligenceScope(
            start_at=start_at, end_at=end_at, filters_applied=filters
        ),
        access=DispositionIntelligenceAccess(private_economics_visible=private_visible),
        data_state=overall_state,
        data_quality=quality,
        activity=activity,
        economics=economics,
        milestones=milestones,
        rates=[
            _rate("reply_rate", "Reply rate", activity.replies, activity.outreach_sent),
            _rate("showing_rate", "Showing rate", activity.showings, activity.inquiries),
            _rate("offer_rate", "Offer rate", activity.offers, activity.inquiries),
            _rate("deposit_rate", "Deposit rate", activity.deposits, activity.selected_buyers),
            _rate(
                "closing_rate",
                "Completed assignment rate",
                economics.completed_assignments,
                activity.selected_buyers,
            ),
            _rate("retrade_rate", "Retrade rate", len(retrades), activity.selected_buyers),
            _rate("fallout_rate", "Buyer fallout rate", len(fallouts), activity.selected_buyers),
        ],
        sources=source_metrics,
        buyers=buyer_metrics,
        agents=agent_metrics,
        learning=DispositionLearningMetrics(
            state="known"
            if comparison_allowed
            else ("partial" if completed_case_ids else "unavailable"),
            human_led_count=human_led_count,
            ai_assisted_count=ai_assisted_count,
            minimum_comparison_sample=MINIMUM_COMPARISON_SAMPLE,
            comparison_allowed=comparison_allowed,
            notice=(
                "Descriptive comparison only; the report never claims AI caused an outcome. "
                + (
                    "Both cohorts meet the minimum sample."
                    if comparison_allowed
                    else "At least one cohort is below the minimum sample, so "
                    "comparison is suppressed."
                )
            ),
            corrections=DispositionCorrectionMetrics(
                package_revisions=package_revision_count,
                match_overrides=match_override_count,
                ai_corrections=ai_corrections,
                backup_buyer_saves=backup_saves,
            ),
        ),
        provenance=[
            DispositionMetricProvenance(
                metric_key="completed_assignments",
                state=_state(len(completed_case_ids)),
                canonical_sources=["transactions", "disposition_buyer_outcomes"],
                definition=(
                    "Requires a funded or closed transaction and immutable "
                    "completed_close buyer outcome; selections and nominal offers do "
                    "not count."
                ),
            ),
            DispositionMetricProvenance(
                metric_key="economics",
                state=economics_state,
                canonical_sources=["deal_reconciliations", "revenue_records", "transactions"],
                definition=(
                    "Contracted spread, collected revenue, and approved company profit "
                    "remain separate and are never inferred from activity."
                ),
            ),
            DispositionMetricProvenance(
                metric_key="first_outreach",
                state=_state(len(filtered_deliveries)),
                canonical_sources=["disposition_outreach_deliveries.sent_at"],
                definition="First actual send, not package preparation or campaign release.",
            ),
            DispositionMetricProvenance(
                metric_key="buyer_reliability",
                state=_state(len(buyer_metrics)),
                canonical_sources=["buyers", "disposition_buyer_outcomes"],
                definition=(
                    "Current reliability score is shown beside documented offer, "
                    "retrade, fallout, and completed-close behavior."
                ),
            ),
            DispositionMetricProvenance(
                metric_key="winning_buyer_source",
                state="partial" if source_rows else "unavailable",
                canonical_sources=["buyers", "disposition_buyer_selection_slots"],
                definition=(
                    "Uses the selected buyer and current buyer provenance. It is "
                    "marked partial because historical source attribution is not frozen."
                ),
            ),
            DispositionMetricProvenance(
                metric_key="campaign_cost",
                state="unavailable",
                canonical_sources=[],
                definition=(
                    "Unavailable until a case-level disposition cost ledger exists; "
                    "broad marketing spend is not used as a substitute."
                ),
            ),
        ],
        filter_options=DispositionFilterOptions(
            deals=deal_options,
            buyers=buyer_options,
            agents=agent_options,
            sources=source_options,
            markets=market_options,
            asset_classes=asset_options,
        ),
    )


def _group(rows: Iterable[object], attribute: str) -> defaultdict[UUID, list[object]]:
    grouped: defaultdict[UUID, list[object]] = defaultdict(list)
    for row in rows:
        value = getattr(row, attribute, None)
        if value is not None:
            grouped[value].append(row)
    return grouped
