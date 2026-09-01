import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import Settings, get_settings
from app.domain.assets import require_house_workflow
from app.integrations.dealmachine_client import DealMachineClient, DealMachineError
from app.models.foundation import (
    ActivityEvent,
    AuditEvent,
    Buyer,
    BuyerCriteria,
    BuyerDiscoveryCandidate,
    BuyerDiscoveryRun,
    DispositionCase,
    Lead,
    Organization,
    Property,
    PropertyIntelligenceSnapshot,
)
from app.schemas.buyers import (
    BuyerDataProviderRead,
    BuyerDiscoveryCandidateRead,
    BuyerDiscoveryCreate,
    BuyerDiscoveryEstimateCreate,
    BuyerDiscoveryEstimateRead,
    BuyerDiscoveryImport,
    BuyerDiscoveryRunRead,
    BuyerDiscoverySearchTier,
    BuyerDiscoverySummaryRead,
    BuyerDiscoveryTierStatusRead,
)
from app.services import disposition_packages
from app.services.buyers import (
    normalize_company,
    normalize_email,
    normalize_phone,
    normalize_source_key,
    normalize_text,
)
from app.services.inbox import ensure_buyer_conversation


@dataclass(frozen=True)
class DiscoveryTierPolicy:
    target_candidates: int
    estimated_credit_cap: int
    price_floor_ratio: float
    price_ceiling_ratio: float
    radius_miles: float | None


@dataclass(frozen=True)
class DiscoveryContext:
    case: DispositionCase
    property_record: Property
    search_tier: BuyerDiscoverySearchTier
    policy: DiscoveryTierPolicy
    package_version_id: UUID | None
    package_source_fingerprint: str
    package_status: str | None
    package_is_current: bool
    requested_candidates: int
    provider_request: dict[str, Any]
    scope_description: str
    request_fingerprint: str = ""


TIER_ORDER: tuple[BuyerDiscoverySearchTier, ...] = (
    "best_fit",
    "expanded",
    "regional",
)
TIER_POLICIES: dict[BuyerDiscoverySearchTier, DiscoveryTierPolicy] = {
    "best_fit": DiscoveryTierPolicy(
        target_candidates=10,
        estimated_credit_cap=30,
        price_floor_ratio=0.65,
        price_ceiling_ratio=1.35,
        radius_miles=None,
    ),
    "expanded": DiscoveryTierPolicy(
        target_candidates=20,
        estimated_credit_cap=60,
        price_floor_ratio=0.45,
        price_ceiling_ratio=1.75,
        radius_miles=15,
    ),
    "regional": DiscoveryTierPolicy(
        target_candidates=40,
        estimated_credit_cap=120,
        price_floor_ratio=0.25,
        price_ceiling_ratio=2.5,
        radius_miles=50,
    ),
}
CASE_CREDIT_CAP = 250
MONTHLY_CREDIT_CAP = 2_000
CREDIT_COST_USD = Decimal("0.0075")
REUSE_WINDOW = timedelta(days=7)

ENTITY_TERMS = {
    "llc",
    "inc",
    "corp",
    "corporation",
    "company",
    "properties",
    "property",
    "investments",
    "holdings",
    "homes",
    "capital",
    "group",
    "partners",
    "lp",
}
PROPERTY_TYPE_MAP = {
    "single_family": "Single Family",
    "single family": "Single Family",
    "house": "Single Family",
    "townhouse": "Townhouse",
    "condo": "Condominium",
    "condominium": "Condominium",
    "multi_family": "Multi Family",
    "multifamily": "Multi Family",
    "duplex": "Multi Family",
    "triplex": "Multi Family",
    "quadplex": "Multi Family",
    "mobile_home": "Mobile Home",
    "mobile home": "Mobile Home",
    "land": "Vacant Land",
    "vacant_land": "Vacant Land",
}


def provider_status(settings: Settings | None = None) -> BuyerDataProviderRead:
    settings = settings or get_settings()
    configured = bool(
        settings.buyer_data_provider == "dealmachine" and settings.dealmachine_api_key
    )
    if settings.buyer_data_provider == "disabled":
        message = "Buyer-data search is disabled until DealMachine is configured."
    elif not settings.dealmachine_api_key:
        message = "Add DEALMACHINE_API_KEY to enable live buyer discovery."
    else:
        message = "DealMachine is configured for selective buyer discovery."
    return BuyerDataProviderRead(
        provider=settings.buyer_data_provider,
        configured=configured,
        live_search_enabled=configured,
        message=message,
    )


def provider_readiness(
    settings: Settings | None = None,
    *,
    client: DealMachineClient | None = None,
) -> BuyerDataProviderRead:
    settings = settings or get_settings()
    status = provider_status(settings)
    if not status.configured:
        return status
    try:
        usage = (client or DealMachineClient(settings)).get_usage()
    except DealMachineError as exc:
        return status.model_copy(
            update={
                "connected": False,
                "live_search_enabled": False,
                "message": str(exc),
            }
        )
    plan = _dictionary(usage.get("plan"))
    billing_cycle = _dictionary(usage.get("billing_cycle"))
    credits = _dictionary(usage.get("credits"))
    remaining = _integer(credits.get("total_available"))
    paid = plan.get("is_paid") if isinstance(plan.get("is_paid"), bool) else None
    enabled = bool(paid is True and remaining is not None and remaining > 0)
    if enabled:
        message = "DealMachine is connected and ready for cost-previewed buyer discovery."
    elif paid is False:
        message = "DealMachine is connected, but the account does not have a paid API plan."
    elif paid is not True:
        message = (
            "DealMachine is connected, but the API did not confirm a paid plan."
        )
    else:
        message = "DealMachine is connected, but the account has no available data credits."
    return status.model_copy(
        update={
            "connected": True,
            "live_search_enabled": enabled,
            "message": message,
            "plan_name": _string(plan.get("name")) or None,
            "is_paid": paid,
            "billing_cycle_end": _parse_datetime(billing_cycle.get("end")),
            "credits_remaining": remaining,
            "credits_used": _integer(credits.get("used")),
            "credits_total": _integer(credits.get("total_cap")),
        }
    )


def estimate_buyer_discovery(
    db: Session,
    principal: Principal,
    payload: BuyerDiscoveryEstimateCreate,
    *,
    settings: Settings | None = None,
    client: DealMachineClient | None = None,
) -> BuyerDiscoveryEstimateRead:
    settings = settings or get_settings()
    status = provider_status(settings)
    if not status.configured:
        raise ValueError(status.message)
    provider_client = client or DealMachineClient(settings)
    try:
        context = _prepared_discovery_context(
            db,
            principal,
            payload,
            settings,
            property_filters=provider_client.list_property_filters(),
        )
        _require_unlocked_tier(db, principal, context.case.id, context.search_tier)
        case_credits, monthly_credits = _budget_usage(
            db,
            principal,
            case_id=context.case.id,
        )
        reusable = _reusable_run(db, principal, context)
        if reusable is not None:
            return _reused_estimate_read(
                context,
                reusable,
                case_credits=case_credits,
                monthly_credits=monthly_credits,
            )
        pending = _pending_credit_reconciliation_run(db, principal, context.case.id)
        if pending is not None:
            raise ValueError(_pending_reconciliation_message(pending))
        usage = provider_client.get_usage()
        estimate = provider_client.estimate_property_search(context.provider_request)
    except DealMachineError as exc:
        raise ValueError(str(exc)) from exc
    return _estimate_read(
        context,
        estimate,
        usage,
        case_credits=case_credits,
        monthly_credits=monthly_credits,
    )


def latest_discovery_run(
    db: Session,
    principal: Principal,
    case_id: UUID,
) -> BuyerDiscoveryRunRead | None:
    run = db.scalar(
        select(BuyerDiscoveryRun)
        .where(
            BuyerDiscoveryRun.organization_id == principal.organization_id,
            BuyerDiscoveryRun.disposition_case_id == case_id,
        )
        .order_by(BuyerDiscoveryRun.created_at.desc())
        .limit(1)
    )
    return run_to_read(db, principal, run) if run else None


def discovery_summary(
    db: Session,
    principal: Principal,
    case_id: UUID,
) -> BuyerDiscoverySummaryRead:
    case = db.scalar(
        select(DispositionCase).where(
            DispositionCase.id == case_id,
            DispositionCase.organization_id == principal.organization_id,
        )
    )
    if case is None:
        raise ValueError("Disposition case not found.")
    require_house_discovery_workflow(db, case)
    runs = list(
        db.scalars(
            select(BuyerDiscoveryRun)
            .where(
                BuyerDiscoveryRun.organization_id == principal.organization_id,
                BuyerDiscoveryRun.disposition_case_id == case.id,
                BuyerDiscoveryRun.provider == "dealmachine",
            )
            .order_by(BuyerDiscoveryRun.created_at.desc())
        ).all()
    )
    latest_by_tier: dict[BuyerDiscoverySearchTier, BuyerDiscoveryRun] = {}
    completed: list[BuyerDiscoverySearchTier] = []
    for run in runs:
        # Historical rows predate governed tiers. Inferred display labels remain
        # useful on an individual legacy run, but cannot unlock paid widening.
        if run.search_tier not in TIER_POLICIES:
            continue
        tier = cast(BuyerDiscoverySearchTier, run.search_tier)
        latest_by_tier.setdefault(tier, run)
        if run.status == "completed" and tier not in completed:
            completed.append(tier)
    completed_set = set(completed)
    completed_tiers = [tier for tier in TIER_ORDER if tier in completed_set]
    unlocked_tiers = _unlocked_tiers(completed_set)
    next_tier = next(
        (tier for tier in unlocked_tiers if tier not in completed_set),
        None,
    )
    case_credits, monthly_credits = _budget_usage(
        db,
        principal,
        case_id=case.id,
    )
    return BuyerDiscoverySummaryRead(
        disposition_case_id=case.id,
        provider="dealmachine",
        completed_tiers=completed_tiers,
        unlocked_tiers=unlocked_tiers,
        next_tier=next_tier,
        cumulative_case_credits=case_credits,
        cumulative_case_credit_cap=CASE_CREDIT_CAP,
        monthly_credits=monthly_credits,
        monthly_credit_cap=MONTHLY_CREDIT_CAP,
        approximate_cost_per_credit_usd=float(CREDIT_COST_USD),
        tier_statuses=[
            BuyerDiscoveryTierStatusRead(
                search_tier=tier,
                target_candidates=TIER_POLICIES[tier].target_candidates,
                estimated_credit_cap=TIER_POLICIES[tier].estimated_credit_cap,
                maximum_estimated_cost_usd=_credit_cost(
                    TIER_POLICIES[tier].estimated_credit_cap
                ),
                completed=tier in completed_set,
                unlocked=tier in unlocked_tiers,
                latest_run=(
                    run_to_read(db, principal, latest_by_tier[tier])
                    if tier in latest_by_tier
                    else None
                ),
            )
            for tier in TIER_ORDER
        ],
    )


def discover_buyers(
    db: Session,
    principal: Principal,
    payload: BuyerDiscoveryCreate,
    *,
    settings: Settings | None = None,
    client: DealMachineClient | None = None,
) -> BuyerDiscoveryRunRead:
    settings = settings or get_settings()
    status = provider_status(settings)
    if not status.configured:
        raise ValueError(status.message)
    provider_client = client or DealMachineClient(settings)
    try:
        property_filters = provider_client.list_property_filters()
    except DealMachineError as exc:
        raise ValueError(str(exc)) from exc

    # The organization lock protects the shared monthly budget and the case lock is
    # the creation-time idempotency fence. Both remain held until the running spend
    # reservation is committed immediately before the paid provider request.
    db.scalar(
        select(Organization)
        .where(Organization.id == principal.organization_id)
        .with_for_update()
    )
    locked_case = db.scalar(
        select(DispositionCase)
        .where(
            DispositionCase.id == payload.disposition_case_id,
            DispositionCase.organization_id == principal.organization_id,
        )
        .with_for_update()
    )
    if locked_case is None:
        raise ValueError("Disposition case not found.")
    context = _prepared_discovery_context(
        db,
        principal,
        payload,
        settings,
        property_filters=property_filters,
        locked_case=locked_case,
    )
    _require_unlocked_tier(db, principal, context.case.id, context.search_tier)
    if payload.confirmed_request_fingerprint != context.request_fingerprint:
        raise ValueError(
            "The buyer-search request changed after its preview. Preview the search again "
            "before running it."
        )
    reusable = _reusable_run(db, principal, context)
    if reusable is not None:
        result = run_to_read(db, principal, reusable)
        return result.model_copy(
            update={
                "reused": True,
                "reused_run_id": reusable.id,
            }
        )
    pending = _pending_credit_reconciliation_run(db, principal, context.case.id)
    if pending is not None:
        raise ValueError(_pending_reconciliation_message(pending))
    case_credits, monthly_credits = _budget_usage(
        db,
        principal,
        case_id=context.case.id,
    )
    try:
        usage = provider_client.get_usage()
        estimate = provider_client.estimate_property_search(context.provider_request)
    except DealMachineError as exc:
        raise ValueError(str(exc)) from exc
    estimate_read = _estimate_read(
        context,
        estimate,
        usage,
        case_credits=case_credits,
        monthly_credits=monthly_credits,
    )
    if not estimate_read.enough_credits:
        raise ValueError(estimate_read.message)
    if payload.confirmed_estimated_credits != estimate_read.estimated_credits:
        raise ValueError(
            "DealMachine's estimated credit use changed. Preview the search again "
            "before running it."
        )
    run = BuyerDiscoveryRun(
        organization_id=principal.organization_id,
        disposition_case_id=context.case.id,
        requested_by_user_id=principal.user_id,
        provider="dealmachine",
        status="running",
        search_tier=context.search_tier,
        request_fingerprint=context.request_fingerprint,
        target_candidate_count=context.policy.target_candidates,
        estimated_credit_cap=context.policy.estimated_credit_cap,
        estimated_credits=estimate_read.estimated_credits,
        actual_credits=None,
        search_snapshot={
            "property_address": _address(context.property_record),
            "postal_code": context.property_record.postal_code.strip()[:5],
            "property_type": context.property_record.property_type,
            "asking_price_cents": context.case.asking_price_cents,
            "max_candidates": payload.max_candidates,
            "search_tier": context.search_tier,
            "target_candidates": context.policy.target_candidates,
            "scope": context.scope_description,
            "package_version_id": (
                str(context.package_version_id) if context.package_version_id else None
            ),
            "package_source_fingerprint": context.package_source_fingerprint,
            "package_status": context.package_status,
            "package_is_current": context.package_is_current,
            "package_is_preliminary": bool(
                context.package_version_id is not None
                and (
                    context.package_status != "approved"
                    or not context.package_is_current
                )
            ),
        },
        provider_request=context.provider_request,
        result_count=0,
        imported_count=0,
        credit_summary={
            "estimated": _estimate_credit_snapshot(estimate),
            "estimated_cost_usd": _credit_cost(estimate_read.estimated_credits),
            "authorized_credit_cap": context.policy.estimated_credit_cap,
            "authorized_cost_cap_usd": _credit_cost(
                context.policy.estimated_credit_cap
            ),
        },
        error_message=None,
        completed_at=None,
    )
    db.add(run)
    db.flush()
    # Persist the spend reservation before crossing the paid-provider boundary. If
    # the worker or API process exits after DealMachine accepts the request, a retry
    # will see this exact running fingerprint and will not spend the credits again.
    db.commit()
    db.refresh(run)
    try:
        response = provider_client.search_properties(context.provider_request)
    except DealMachineError as exc:
        _fail_discovery_run(
            db,
            principal,
            run,
            error_message=str(exc),
            action="buyer.discovery_provider_failed",
            actual_credit_summary=None,
        )
        db.commit()
        raise ValueError(str(exc)) from exc

    actual_summary = _actual_credit_summary(response)
    if actual_summary is None:
        message = (
            "DealMachine did not return complete actual credit telemetry. "
            "No buyer candidates were admitted because the spend cannot be reconciled."
        )
        _fail_discovery_run(
            db,
            principal,
            run,
            error_message=message,
            action="buyer.discovery_credit_telemetry_failed",
            actual_credit_summary=_credit_summary(response),
        )
        db.commit()
        raise ValueError(message)

    actual_credits = actual_summary["used"]
    run.actual_credits = actual_credits
    post_case_credits = case_credits + actual_credits
    post_monthly_credits = monthly_credits + actual_credits
    boundary_error = _actual_credit_boundary_error(
        context,
        actual_credits=actual_credits,
        case_credits=post_case_credits,
        monthly_credits=post_monthly_credits,
    )
    if boundary_error:
        _fail_discovery_run(
            db,
            principal,
            run,
            error_message=boundary_error,
            action="buyer.discovery_credit_boundary_failed",
            actual_credit_summary=actual_summary,
        )
        db.commit()
        raise ValueError(boundary_error)

    try:
        grouped_candidates = _candidate_groups(
            response.get("data", []),
            case=context.case,
            property_record=context.property_record,
            max_candidates=len(response.get("data", [])),
            scope_description=context.scope_description,
        )
        candidates = _net_new_candidates(
            db,
            principal,
            context.case.id,
            grouped_candidates,
            limit=context.policy.target_candidates,
        )
    except (TypeError, ValueError) as exc:
        message = "DealMachine buyer evidence could not be normalized safely."
        _fail_discovery_run(
            db,
            principal,
            run,
            error_message=message,
            action="buyer.discovery_response_failed",
            actual_credit_summary=actual_summary,
        )
        db.commit()
        raise ValueError(message) from exc

    for item in candidates:
        evidence_snapshot = {
            **item["evidence_snapshot"],
            "source_attribution": {
                "provider": "dealmachine",
                "discovery_run_id": str(run.id),
                "search_tier": context.search_tier,
                "request_fingerprint": context.request_fingerprint,
                "estimated_credits": estimate_read.estimated_credits,
                "authorized_credit_cap": context.policy.estimated_credit_cap,
                "actual_credits": actual_credits,
                "estimated_cost_usd": _credit_cost(estimate_read.estimated_credits),
                "authorized_cost_cap_usd": _credit_cost(
                    context.policy.estimated_credit_cap
                ),
                "actual_cost_usd": _credit_cost(actual_credits),
            },
        }
        db.add(
            BuyerDiscoveryCandidate(
                organization_id=principal.organization_id,
                discovery_run_id=run.id,
                buyer_id=None,
                provider="dealmachine",
                external_key=item["external_key"],
                name=item["name"],
                company_name=item["company_name"],
                email=item["email"],
                phone=item["phone"],
                market=item["market"],
                state=context.property_record.state.upper(),
                property_types=item["property_types"],
                observed_purchase_count=item["observed_purchase_count"],
                no_mortgage_count=item["no_mortgage_count"],
                last_purchase_date=item["last_purchase_date"],
                min_purchase_price_cents=item["min_purchase_price_cents"],
                max_purchase_price_cents=item["max_purchase_price_cents"],
                score_basis_points=item["score_basis_points"],
                score_components=item["score_components"],
                evidence_snapshot=evidence_snapshot,
                provider_snapshot=item["provider_snapshot"],
                status="review",
                imported_at=None,
            )
        )
    run.status = "completed"
    run.result_count = len(candidates)
    run.credit_summary = {
        **actual_summary,
        "estimated": _estimate_credit_snapshot(estimate),
        "estimated_cost_usd": _credit_cost(estimate_read.estimated_credits),
        "authorized_credit_cap": context.policy.estimated_credit_cap,
        "authorized_cost_cap_usd": _credit_cost(context.policy.estimated_credit_cap),
        "actual_cost_usd": _credit_cost(actual_credits),
        "provider_balance_before": _usage_credit_snapshot(usage),
    }
    run.completed_at = datetime.now(UTC)
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="buyer.discovery_completed",
            entity_type="buyer_discovery_run",
            entity_id=run.id,
            previous_value=None,
            new_value={
                "provider": "dealmachine",
                "disposition_case_id": str(context.case.id),
                "search_tier": context.search_tier,
                "target_candidates": context.policy.target_candidates,
                "candidate_count": len(candidates),
                "estimated_credits": estimate_read.estimated_credits,
                "authorized_credit_cap": context.policy.estimated_credit_cap,
                "actual_credits": actual_credits,
                "estimated_cost_usd": _credit_cost(estimate_read.estimated_credits),
                "authorized_cost_cap_usd": _credit_cost(
                    context.policy.estimated_credit_cap
                ),
                "actual_cost_usd": _credit_cost(actual_credits),
                "cumulative_case_credits": post_case_credits,
                "monthly_credits": post_monthly_credits,
                "buyers_imported": 0,
                "external_messages_sent": 0,
            },
            reason="User initiated deal-specific buyer discovery",
        )
    )
    db.commit()
    db.refresh(run)
    return run_to_read(db, principal, run)


def import_candidates(
    db: Session,
    principal: Principal,
    run_id: UUID,
    payload: BuyerDiscoveryImport,
) -> BuyerDiscoveryRunRead | None:
    run = db.scalar(
        select(BuyerDiscoveryRun).where(
            BuyerDiscoveryRun.id == run_id,
            BuyerDiscoveryRun.organization_id == principal.organization_id,
        )
    )
    if run is None:
        return None
    case = db.get(DispositionCase, run.disposition_case_id)
    if case is None:
        raise ValueError("The source disposition case is unavailable.")
    require_house_discovery_workflow(db, case)
    candidates = list(
        db.scalars(
            select(BuyerDiscoveryCandidate).where(
                BuyerDiscoveryCandidate.organization_id == principal.organization_id,
                BuyerDiscoveryCandidate.discovery_run_id == run.id,
                BuyerDiscoveryCandidate.id.in_(payload.candidate_ids),
            )
        ).all()
    )
    if len(candidates) != len(set(payload.candidate_ids)):
        raise ValueError("One or more buyer candidates are unavailable.")
    property_record = db.get(Property, case.property_id) if case else None
    if property_record is None:
        raise ValueError("The source disposition case is unavailable.")

    existing_buyers = list(
        db.scalars(select(Buyer).where(Buyer.organization_id == principal.organization_id)).all()
    )
    existing_buyers_by_id = {item.id: item for item in existing_buyers}
    by_name: dict[str, list[Buyer]] = {}
    by_email: dict[str, list[Buyer]] = {}
    by_phone: dict[str, list[Buyer]] = {}
    by_source_external: dict[tuple[str, str], list[Buyer]] = {}
    for item in existing_buyers:
        for display_name in {item.name, item.company_name}:
            if not display_name:
                continue
            normalized_name = _normalized_name(display_name)
            if normalized_name:
                by_name.setdefault(normalized_name, []).append(item)
        if item.normalized_email:
            by_email.setdefault(item.normalized_email, []).append(item)
        if item.normalized_phone:
            by_phone.setdefault(item.normalized_phone, []).append(item)
        if item.source_external_key:
            by_source_external.setdefault((item.source_key, item.source_external_key), []).append(
                item
            )
    imported = 0
    duplicates = 0
    duplicate_reviews = 0
    quarantined = 0
    now = datetime.now(UTC)
    for candidate in candidates:
        if candidate.buyer_id is not None:
            candidate.status = "duplicate"
            duplicates += 1
            continue
        source_key = normalize_source_key(candidate.provider)
        display_email = normalize_text(candidate.email)
        display_phone = normalize_text(candidate.phone)
        normalized_email = normalize_email(display_email)
        normalized_phone = normalize_phone(display_phone)
        canonical_email = display_email if normalized_email is not None else None
        canonical_phone = display_phone if normalized_phone is not None else None
        previous_buyer_ids = {
            buyer_id
            for buyer_id in db.scalars(
                select(BuyerDiscoveryCandidate.buyer_id)
                .where(
                    BuyerDiscoveryCandidate.organization_id == principal.organization_id,
                    BuyerDiscoveryCandidate.provider == candidate.provider,
                    BuyerDiscoveryCandidate.external_key == candidate.external_key,
                    BuyerDiscoveryCandidate.buyer_id.is_not(None),
                    BuyerDiscoveryCandidate.id != candidate.id,
                )
                .order_by(BuyerDiscoveryCandidate.imported_at.desc())
            ).all()
            if buyer_id is not None
        }
        strong_matches: dict[UUID, Buyer] = {
            buyer_id: existing_buyers_by_id[buyer_id]
            for buyer_id in previous_buyer_ids
            if buyer_id in existing_buyers_by_id
        }
        for possible in by_source_external.get((source_key, candidate.external_key), []):
            strong_matches[possible.id] = possible
        if normalized_email:
            for possible in by_email.get(normalized_email, []):
                strong_matches[possible.id] = possible
        if normalized_phone:
            for possible in by_phone.get(normalized_phone, []):
                strong_matches[possible.id] = possible

        if len(strong_matches) > 1:
            candidate.status = "needs_duplicate_review"
            candidate.evidence_snapshot = {
                **(candidate.evidence_snapshot or {}),
                "duplicate_review": {
                    "reason": "ambiguous_strong_identity",
                    "possible_buyer_ids": [
                        str(buyer_id) for buyer_id in sorted(strong_matches, key=str)
                    ],
                },
            }
            duplicate_reviews += 1
            continue
        buyer = next(iter(strong_matches.values()), None)
        if buyer is not None:
            candidate.buyer_id = buyer.id
            candidate.status = "duplicate"
            candidate.imported_at = now
            duplicates += 1
            continue

        candidate_name_keys = {
            _normalized_name(display_name)
            for display_name in {candidate.name, candidate.company_name}
            if display_name
        }
        name_only_matches = {
            possible.id: possible
            for name_key in candidate_name_keys
            for possible in by_name.get(name_key, [])
        }
        if name_only_matches:
            candidate.status = "needs_duplicate_review"
            candidate.evidence_snapshot = {
                **(candidate.evidence_snapshot or {}),
                "duplicate_review": {
                    "reason": "name_or_company_match_only",
                    "possible_buyer_ids": [
                        str(buyer_id) for buyer_id in sorted(name_only_matches, key=str)
                    ],
                },
            }
            duplicate_reviews += 1
            continue

        if normalized_email is None and normalized_phone is None:
            candidate.status = "needs_contact_review"
            quarantined += 1
            continue

        observed_max = candidate.max_purchase_price_cents
        buyer = Buyer(
            organization_id=principal.organization_id,
            name=candidate.name,
            company_name=candidate.company_name,
            email=canonical_email,
            phone=canonical_phone,
            normalized_email=normalized_email,
            normalized_phone=normalized_phone,
            normalized_company_name=normalize_company(candidate.company_name),
            buyer_type="cash_buyer",
            status="needs_review",
            source_key=source_key,
            source_detail="Buyer discovery candidate",
            source_external_key=candidate.external_key,
            created_by_user_id=principal.user_id,
            relationship_owner_user_id=principal.user_id,
            proof_of_funds_status="unknown",
            max_purchase_price_cents=(
                round(observed_max * 1.25) if observed_max is not None else None
            ),
            reliability_score_basis_points=5000,
            completed_deals=0,
            failed_deals=0,
            proof_of_funds_expires_at=None,
            notes=(
                "Imported from DealMachine purchase evidence. Contact details, buying "
                "criteria, closing capacity, and proof of funds require Stonegate verification."
            ),
        )
        db.add(buyer)
        db.flush()
        observed_min = candidate.min_purchase_price_cents
        db.add(
            BuyerCriteria(
                organization_id=principal.organization_id,
                buyer_id=buyer.id,
                version_number=1,
                is_current=True,
                markets=candidate.market,
                property_types=(
                    property_record.property_type or ", ".join(candidate.property_types) or None
                ),
                min_price_cents=(round(observed_min * 0.75) if observed_min is not None else None),
                max_price_cents=(round(observed_max * 1.25) if observed_max is not None else None),
                rehab_levels=None,
                notes=(
                    "Initial buy box inferred from provider evidence. Confirm directly "
                    "with the buyer before campaign approval."
                ),
            )
        )
        ensure_buyer_conversation(db, buyer, actor_user_id=principal.user_id)
        candidate.buyer_id = buyer.id
        candidate.status = "imported"
        candidate.imported_at = now
        for name_key in candidate_name_keys:
            by_name.setdefault(name_key, []).append(buyer)
        existing_buyers_by_id[buyer.id] = buyer
        if buyer.normalized_email:
            by_email.setdefault(buyer.normalized_email, []).append(buyer)
        if buyer.normalized_phone:
            by_phone.setdefault(buyer.normalized_phone, []).append(buyer)
        if buyer.source_external_key:
            by_source_external.setdefault((buyer.source_key, buyer.source_external_key), []).append(
                buyer
            )
        imported += 1
        db.add(
            ActivityEvent(
                organization_id=principal.organization_id,
                actor_user_id=principal.user_id,
                entity_type="buyer",
                entity_id=buyer.id,
                event_type="buyer.imported",
                summary=f"Buyer imported from DealMachine: {buyer.name}.",
            )
        )
        db.add(
            AuditEvent(
                organization_id=principal.organization_id,
                actor_user_id=principal.user_id,
                actor_type="user",
                action="buyer.import",
                entity_type="buyer",
                entity_id=buyer.id,
                previous_value=None,
                new_value={
                    "provider": candidate.provider,
                    "discovery_candidate_id": str(candidate.id),
                    "proof_of_funds_status": "unknown",
                    "criteria_verified": False,
                    "external_messages_sent": 0,
                },
                reason="User approved buyer candidate import",
            )
        )
    run.imported_count = int(run.imported_count or 0) + imported
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="buyer.discovery_import_reviewed",
            entity_type="buyer_discovery_run",
            entity_id=run.id,
            previous_value=None,
            new_value={
                "selected_count": len(candidates),
                "imported_count": imported,
                "duplicate_count": duplicates,
                "duplicate_review_count": duplicate_reviews,
                "quarantined_count": quarantined,
                "external_messages_sent": 0,
            },
            reason="Human-selected DealMachine candidate import",
        )
    )
    db.commit()
    db.refresh(run)
    return run_to_read(db, principal, run)


def run_to_read(
    db: Session,
    principal: Principal,
    run: BuyerDiscoveryRun,
) -> BuyerDiscoveryRunRead:
    candidates = list(
        db.scalars(
            select(BuyerDiscoveryCandidate)
            .where(
                BuyerDiscoveryCandidate.organization_id == principal.organization_id,
                BuyerDiscoveryCandidate.discovery_run_id == run.id,
            )
            .order_by(
                BuyerDiscoveryCandidate.score_basis_points.desc(),
                BuyerDiscoveryCandidate.name,
            )
        ).all()
    )
    tier = _run_search_tier(run)
    policy = TIER_POLICIES[tier]
    case_credits, monthly_credits = _budget_usage(
        db,
        principal,
        case_id=run.disposition_case_id,
    )
    actual_credits = _actual_run_credits(run)
    estimated_credits = int(run.estimated_credits or 0)
    return BuyerDiscoveryRunRead(
        id=run.id,
        disposition_case_id=run.disposition_case_id,
        provider=run.provider,
        status=run.status,
        search_snapshot=run.search_snapshot,
        result_count=run.result_count,
        imported_count=run.imported_count,
        credit_summary=run.credit_summary,
        error_message=run.error_message,
        completed_at=run.completed_at,
        candidates=[
            BuyerDiscoveryCandidateRead(
                id=item.id,
                buyer_id=item.buyer_id,
                provider=item.provider,
                name=item.name,
                company_name=item.company_name,
                email=item.email,
                phone=item.phone,
                market=item.market,
                state=item.state,
                property_types=item.property_types,
                observed_purchase_count=item.observed_purchase_count,
                no_mortgage_count=item.no_mortgage_count,
                last_purchase_date=item.last_purchase_date,
                min_purchase_price_cents=item.min_purchase_price_cents,
                max_purchase_price_cents=item.max_purchase_price_cents,
                score_basis_points=item.score_basis_points,
                score_components=item.score_components,
                evidence_snapshot=item.evidence_snapshot,
                status=item.status,
            )
            for item in candidates
        ],
        created_at=run.created_at,
        search_tier=tier,
        target_candidates=int(run.target_candidate_count or policy.target_candidates),
        estimated_credit_cap=int(run.estimated_credit_cap or policy.estimated_credit_cap),
        estimated_credits=estimated_credits,
        actual_credits=actual_credits,
        estimated_cost_usd=_credit_cost(estimated_credits),
        actual_cost_usd=(
            _credit_cost(actual_credits) if actual_credits is not None else None
        ),
        cumulative_case_credits=case_credits,
        cumulative_case_credit_cap=CASE_CREDIT_CAP,
        monthly_credits=monthly_credits,
        monthly_credit_cap=MONTHLY_CREDIT_CAP,
        reused=False,
        reused_run_id=None,
    )


def _prepared_discovery_context(
    db: Session,
    principal: Principal,
    payload: BuyerDiscoveryEstimateCreate,
    settings: Settings,
    *,
    property_filters: list[object],
    locked_case: DispositionCase | None = None,
) -> DiscoveryContext:
    context = _discovery_context(
        db,
        principal,
        payload,
        settings,
        locked_case=locked_case,
    )
    _add_property_type_filter(
        context.provider_request,
        property_record=context.property_record,
        filters=property_filters,
    )
    fingerprint = _canonical_hash(
        {
            "provider": "dealmachine",
            "disposition_case_id": str(context.case.id),
            "search_tier": context.search_tier,
            "provider_request": context.provider_request,
        }
    )
    return replace(context, request_fingerprint=fingerprint)


def _discovery_context(
    db: Session,
    principal: Principal,
    payload: BuyerDiscoveryEstimateCreate,
    settings: Settings,
    *,
    locked_case: DispositionCase | None = None,
) -> DiscoveryContext:
    case = locked_case or db.scalar(
        select(DispositionCase).where(
            DispositionCase.id == payload.disposition_case_id,
            DispositionCase.organization_id == principal.organization_id,
        )
    )
    if case is None:
        raise ValueError("Disposition case not found.")
    require_house_discovery_workflow(db, case)
    property_record = db.scalar(
        select(Property).where(
            Property.id == case.property_id,
            Property.organization_id == principal.organization_id,
        )
    )
    if property_record is None:
        raise ValueError("The disposition case has no property record.")
    try:
        package = disposition_packages.require_package_artifact(
            db,
            principal,
            case,
            action="recording optional buyer-discovery package provenance",
        )
    except ValueError:
        package = None
    package_is_current = bool(
        package is not None
        and disposition_packages.package_version_currentness(
            db, principal, case, package
        )
    )
    postal_code = (property_record.postal_code or "").strip()[:5]
    if not re.fullmatch(r"\d{5}", postal_code):
        raise ValueError("A five-digit property ZIP code is required for buyer discovery.")
    tier = _payload_search_tier(payload)
    policy = TIER_POLICIES[tier]
    provider_request, scope_description = _provider_request(
        db,
        case,
        property_record,
        tier,
        policy,
        settings,
    )
    facts_fingerprint = _canonical_hash(
        {
            "disposition_case_id": str(case.id),
            "property_id": str(property_record.id),
            "property_updated_at": property_record.updated_at,
            "asking_price_cents": case.asking_price_cents,
            "minimum_acceptable_cents": case.minimum_acceptable_cents,
            "package_version_id": str(package.id) if package else None,
            "package_source_fingerprint": package.source_fingerprint if package else None,
        }
    )
    return DiscoveryContext(
        case=case,
        property_record=property_record,
        search_tier=tier,
        policy=policy,
        package_version_id=package.id if package else None,
        package_source_fingerprint=(
            package.source_fingerprint if package else facts_fingerprint
        ),
        package_status=package.status if package else None,
        package_is_current=package_is_current,
        requested_candidates=payload.max_candidates,
        provider_request=provider_request,
        scope_description=scope_description,
    )


def require_house_discovery_workflow(db: Session, case: DispositionCase) -> None:
    lead = db.get(Lead, case.lead_id)
    if lead is None:
        raise ValueError("The disposition lead is no longer available.")
    require_house_workflow(lead.asset_class, workflow="Residential cash-buyer discovery")


def _estimate_read(
    context: DiscoveryContext,
    estimate: dict[str, Any],
    usage: dict[str, Any],
    *,
    case_credits: int,
    monthly_credits: int,
) -> BuyerDiscoveryEstimateRead:
    estimated = _dictionary(estimate.get("estimated_credits"))
    breakdown = _dictionary(estimated.get("breakdown"))
    pagination = _dictionary(estimate.get("pagination"))
    totals = _dictionary(estimate.get("totals"))
    credits = _dictionary(usage.get("credits"))
    plan = _dictionary(usage.get("plan"))
    estimated_credit_value = _integer(estimated.get("this_page"))
    credits_remaining_value = _integer(credits.get("total_available"))
    estimated_credits = max(estimated_credit_value or 0, 0)
    credits_remaining = max(credits_remaining_value or 0, 0)
    paid = plan.get("is_paid")
    blockers: list[str] = []
    if paid is not True:
        blockers.append(
            "DealMachine did not confirm that the connected account has a paid API plan."
        )
    if estimated_credit_value is None or estimated_credit_value < 0:
        blockers.append(
            "DealMachine did not return a valid estimated credit cost for this search."
        )
    if credits_remaining_value is None or credits_remaining_value < 0:
        blockers.append(
            "DealMachine did not return a valid available-credit balance for this account."
        )
    if (
        estimated_credit_value is not None
        and estimated_credit_value >= 0
        and estimated_credits > context.policy.estimated_credit_cap
    ):
        blockers.append(
            f"The estimate exceeds the {context.policy.estimated_credit_cap}-credit "
            f"{context.search_tier.replace('_', ' ')} tier limit."
        )
    if case_credits + context.policy.estimated_credit_cap > CASE_CREDIT_CAP:
        blockers.append(
            f"The tier's {context.policy.estimated_credit_cap}-credit authorization would "
            f"exceed the {CASE_CREDIT_CAP}-credit lifetime limit for this deal."
        )
    if monthly_credits + context.policy.estimated_credit_cap > MONTHLY_CREDIT_CAP:
        blockers.append(
            f"The tier's {context.policy.estimated_credit_cap}-credit authorization would "
            f"exceed the {MONTHLY_CREDIT_CAP}-credit monthly disposition limit."
        )
    if (
        estimated_credit_value is not None
        and estimated_credit_value >= 0
        and credits_remaining_value is not None
        and credits_remaining_value >= 0
        and credits_remaining < context.policy.estimated_credit_cap
    ):
        blockers.append(
            f"Only {credits_remaining} DealMachine credits are available for an "
            f"authorized maximum of {context.policy.estimated_credit_cap} credits."
        )
    enough_credits = not blockers
    message = (
        " ".join(blockers)
        if blockers
        else (
            f"DealMachine previews {estimated_credits} credits "
            f"(${_credit_cost(estimated_credits):.4f}) for the "
            f"{context.search_tier.replace('_', ' ')} search. The binding authorization "
            f"is capped at {context.policy.estimated_credit_cap} credits "
            f"(${_credit_cost(context.policy.estimated_credit_cap):.4f}) because live "
            "owner enrichment can cost more than the preview."
        )
    )
    return BuyerDiscoveryEstimateRead(
        disposition_case_id=context.case.id,
        requested_candidates=context.requested_candidates,
        provider_result_limit=_integer(context.provider_request.get("per_page")) or 0,
        total_matching_properties=(
            _integer(pagination.get("total_results")) or _integer(totals.get("properties")) or 0
        ),
        estimated_credits=estimated_credits,
        estimated_property_credits=_integer(breakdown.get("properties")) or 0,
        estimated_people_credits=_integer(breakdown.get("people")) or 0,
        credits_remaining=credits_remaining,
        enough_credits=enough_credits,
        message=message,
        request_fingerprint=context.request_fingerprint,
        search_tier=context.search_tier,
        target_candidates=context.policy.target_candidates,
        estimated_credit_cap=context.policy.estimated_credit_cap,
        estimated_cost_usd=_credit_cost(estimated_credits),
        cumulative_case_credits=case_credits,
        cumulative_case_credit_cap=CASE_CREDIT_CAP,
        monthly_credits=monthly_credits,
        monthly_credit_cap=MONTHLY_CREDIT_CAP,
        reused=False,
        reused_run_id=None,
    )


def _provider_request(
    db: Session,
    case: DispositionCase,
    property_record: Property,
    tier: BuyerDiscoverySearchTier,
    policy: DiscoveryTierPolicy,
    settings: Settings,
) -> tuple[dict[str, Any], str]:
    target_dollars = max(round(case.asking_price_cents / 100), 1)
    filters: list[dict[str, Any]] = [
        {"filter_id": "is_recently_sold", "value": True},
        {
            "filter_id": "last_sale_price",
            "operator": "range",
            "value": {
                "min": max(round(target_dollars * 0.5), 1),
                "max": round(target_dollars * policy.price_ceiling_ratio),
            },
        },
    ]
    filters[1]["value"] = {
        "min": max(round(target_dollars * policy.price_floor_ratio), 1),
        "max": round(target_dollars * policy.price_ceiling_ratio),
    }
    latitude, longitude = _subject_coordinates(db, property_record)
    postal_code = property_record.postal_code.strip()[:5]
    locations: list[dict[str, object]]
    if tier == "best_fit":
        locations = [{"type": "zip_code", "code": postal_code}]
        scope_description = f"Subject ZIP {postal_code} with the closest price band"
    elif policy.radius_miles is not None and latitude is not None and longitude is not None:
        locations = [
            {
                "type": "radius",
                "latitude": latitude,
                "longitude": longitude,
                "radius_miles": policy.radius_miles,
            }
        ]
        scope_description = (
            f"{policy.radius_miles:g}-mile radius around the saved subject coordinates"
        )
    elif tier == "expanded":
        # No new geocoder or paid property lookup is triggered merely to run discovery.
        # A wider price band in the exact ZIP is the bounded fallback.
        locations = [{"type": "zip_code", "code": postal_code}]
        scope_description = (
            f"Subject ZIP {postal_code} with a wider price band; saved coordinates unavailable"
        )
    else:
        locations = [{"type": "state", "code": property_record.state.strip().upper()}]
        scope_description = "Statewide price-and-property-type fallback; coordinates unavailable"
    return {
        "locations": locations,
        "anchor": "properties",
        "contact_audience": "owners",
        "filters": filters,
        "fields": [
            "owner_1_full_name",
            "owner_2_full_name",
            "last_sale_date",
            "last_sale_price",
            "num_mortgages",
            "property_type",
        ],
        "page": 1,
        "per_page": min(
            settings.buyer_discovery_max_results,
            policy.target_candidates,
        ),
        "sort": [{"field_id": "last_sale_date", "direction": "desc"}],
    }, scope_description


def _payload_search_tier(
    payload: BuyerDiscoveryEstimateCreate,
) -> BuyerDiscoverySearchTier:
    if payload.search_tier is not None:
        return payload.search_tier
    # Existing clients predate named tiers and submit only the legacy candidate count.
    # Keep those calls valid, but route them through the least expensive governed tier
    # instead of letting an omitted field bypass sequential widening.
    return "best_fit"


def _run_search_tier(run: BuyerDiscoveryRun) -> BuyerDiscoverySearchTier:
    if run.search_tier in TIER_POLICIES:
        return run.search_tier
    snapshot = run.search_snapshot if isinstance(run.search_snapshot, dict) else {}
    snapshot_tier = snapshot.get("search_tier")
    if snapshot_tier in TIER_POLICIES:
        return cast(BuyerDiscoverySearchTier, snapshot_tier)
    legacy_max = _integer(snapshot.get("max_candidates")) or 25
    if legacy_max <= 10:
        return "best_fit"
    if legacy_max <= 25:
        return "expanded"
    return "regional"


def _completed_tiers(
    db: Session,
    principal: Principal,
    case_id: UUID,
) -> set[BuyerDiscoverySearchTier]:
    runs = list(
        db.scalars(
            select(BuyerDiscoveryRun).where(
                BuyerDiscoveryRun.organization_id == principal.organization_id,
                BuyerDiscoveryRun.disposition_case_id == case_id,
                BuyerDiscoveryRun.provider == "dealmachine",
                BuyerDiscoveryRun.status == "completed",
            )
        ).all()
    )
    return {
        cast(BuyerDiscoverySearchTier, run.search_tier)
        for run in runs
        if run.search_tier in TIER_POLICIES
    }


def _unlocked_tiers(
    completed: set[BuyerDiscoverySearchTier],
) -> list[BuyerDiscoverySearchTier]:
    unlocked: list[BuyerDiscoverySearchTier] = ["best_fit"]
    if "best_fit" in completed:
        unlocked.append("expanded")
    if {"best_fit", "expanded"}.issubset(completed):
        unlocked.append("regional")
    return unlocked


def _require_unlocked_tier(
    db: Session,
    principal: Principal,
    case_id: UUID,
    tier: BuyerDiscoverySearchTier,
) -> None:
    completed = _completed_tiers(db, principal, case_id)
    if tier in _unlocked_tiers(completed):
        return
    prerequisites = TIER_ORDER[: TIER_ORDER.index(tier)]
    missing = [item for item in prerequisites if item not in completed]
    missing_label = " and ".join(item.replace("_", " ") for item in missing)
    raise ValueError(
        f"Complete the {missing_label} DealMachine tier before "
        f"starting the {tier.replace('_', ' ')} tier."
    )


def _reusable_run(
    db: Session,
    principal: Principal,
    context: DiscoveryContext,
) -> BuyerDiscoveryRun | None:
    runs = list(
        db.scalars(
            select(BuyerDiscoveryRun)
            .where(
                BuyerDiscoveryRun.organization_id == principal.organization_id,
                BuyerDiscoveryRun.disposition_case_id == context.case.id,
                BuyerDiscoveryRun.provider == "dealmachine",
                BuyerDiscoveryRun.request_fingerprint == context.request_fingerprint,
                BuyerDiscoveryRun.search_tier == context.search_tier,
                BuyerDiscoveryRun.status == "completed",
                BuyerDiscoveryRun.created_at >= datetime.now(UTC) - REUSE_WINDOW,
            )
            .order_by(BuyerDiscoveryRun.created_at.desc())
        ).all()
    )
    return runs[0] if runs else None


def _pending_credit_reconciliation_run(
    db: Session,
    principal: Principal,
    case_id: UUID,
) -> BuyerDiscoveryRun | None:
    runs = list(
        db.scalars(
            select(BuyerDiscoveryRun)
            .where(
                BuyerDiscoveryRun.organization_id == principal.organization_id,
                BuyerDiscoveryRun.disposition_case_id == case_id,
                BuyerDiscoveryRun.provider == "dealmachine",
                BuyerDiscoveryRun.status.in_(["running", "failed"]),
            )
            .order_by(BuyerDiscoveryRun.created_at.desc())
        ).all()
    )
    for run in runs:
        if run.status == "running" or _actual_run_credits(run) is None:
            return run
    return None


def _pending_reconciliation_message(run: BuyerDiscoveryRun) -> str:
    return (
        f"A prior DealMachine request ({run.id}) is pending credit reconciliation. "
        "Stonegate will not run another paid buyer search for this deal until that "
        "attempt is reconciled."
    )


def _reused_estimate_read(
    context: DiscoveryContext,
    run: BuyerDiscoveryRun,
    *,
    case_credits: int,
    monthly_credits: int,
) -> BuyerDiscoveryEstimateRead:
    credit_summary = run.credit_summary if isinstance(run.credit_summary, dict) else {}
    balance = _dictionary(credit_summary.get("provider_balance_before"))
    return BuyerDiscoveryEstimateRead(
        disposition_case_id=context.case.id,
        requested_candidates=context.requested_candidates,
        provider_result_limit=_integer(context.provider_request.get("per_page")) or 0,
        total_matching_properties=run.result_count,
        estimated_credits=0,
        estimated_property_credits=0,
        estimated_people_credits=0,
        credits_remaining=_integer(balance.get("total_available")) or 0,
        enough_credits=True,
        message=(
            "Stonegate will reuse the current saved DealMachine result for this exact "
            "deal, package, and tier. No new credits will be spent."
        ),
        request_fingerprint=context.request_fingerprint,
        search_tier=context.search_tier,
        target_candidates=context.policy.target_candidates,
        estimated_credit_cap=context.policy.estimated_credit_cap,
        estimated_cost_usd=0,
        cumulative_case_credits=case_credits,
        cumulative_case_credit_cap=CASE_CREDIT_CAP,
        monthly_credits=monthly_credits,
        monthly_credit_cap=MONTHLY_CREDIT_CAP,
        reused=True,
        reused_run_id=run.id,
    )


def _budget_usage(
    db: Session,
    principal: Principal,
    *,
    case_id: UUID,
) -> tuple[int, int]:
    month_start = datetime.now(UTC).replace(
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    case_runs = list(
        db.scalars(
            select(BuyerDiscoveryRun).where(
                BuyerDiscoveryRun.organization_id == principal.organization_id,
                BuyerDiscoveryRun.disposition_case_id == case_id,
                BuyerDiscoveryRun.provider == "dealmachine",
            )
        ).all()
    )
    monthly_runs = list(
        db.scalars(
            select(BuyerDiscoveryRun).where(
                BuyerDiscoveryRun.organization_id == principal.organization_id,
                BuyerDiscoveryRun.provider == "dealmachine",
                BuyerDiscoveryRun.created_at >= month_start,
            )
        ).all()
    )
    return (
        sum(_run_credit_usage(run) for run in case_runs),
        sum(_run_credit_usage(run) for run in monthly_runs),
    )


def _run_credit_usage(run: BuyerDiscoveryRun) -> int:
    actual = _actual_run_credits(run)
    if actual is not None:
        return actual
    # Running attempts and failed attempts without complete provider telemetry reserve
    # the full authorized tier ceiling until reconciled.
    if run.status in {"running", "failed"}:
        return int(run.estimated_credit_cap or run.estimated_credits or 0)
    return 0


def _actual_run_credits(run: BuyerDiscoveryRun) -> int | None:
    if run.actual_credits is not None:
        return max(int(run.actual_credits), 0)
    summary = run.credit_summary if isinstance(run.credit_summary, dict) else {}
    used = _integer(summary.get("used"))
    return max(used, 0) if used is not None else None


def _actual_credit_summary(response: dict[str, Any]) -> dict[str, int] | None:
    summary = _credit_summary(response)
    if summary is None:
        return None
    used = _integer(summary.get("used"))
    properties = _integer(summary.get("properties"))
    people = _integer(summary.get("people"))
    deduplicated = _integer(summary.get("deduplicated"))
    if used is None or properties is None or people is None:
        return None
    if min(used, properties, people) < 0:
        return None
    return {
        "used": used,
        "properties": properties,
        "people": people,
        "deduplicated": max(deduplicated or 0, 0),
    }


def _actual_credit_boundary_error(
    context: DiscoveryContext,
    *,
    actual_credits: int,
    case_credits: int,
    monthly_credits: int,
) -> str | None:
    if actual_credits > context.policy.estimated_credit_cap:
        return (
            f"DealMachine reported {actual_credits} actual credits, exceeding the "
            f"{context.policy.estimated_credit_cap}-credit tier boundary."
        )
    if case_credits > CASE_CREDIT_CAP:
        return f"The DealMachine response exceeded the {CASE_CREDIT_CAP}-credit deal boundary."
    if monthly_credits > MONTHLY_CREDIT_CAP:
        return (
            f"The DealMachine response exceeded the {MONTHLY_CREDIT_CAP}-credit monthly boundary."
        )
    return None


def _fail_discovery_run(
    db: Session,
    principal: Principal,
    run: BuyerDiscoveryRun,
    *,
    error_message: str,
    action: str,
    actual_credit_summary: dict[str, Any] | None,
) -> None:
    previous_summary = run.credit_summary if isinstance(run.credit_summary, dict) else {}
    run.status = "failed"
    run.error_message = error_message
    run.completed_at = datetime.now(UTC)
    if actual_credit_summary is not None:
        run.credit_summary = {
            **previous_summary,
            **actual_credit_summary,
            "actual_cost_usd": (
                _credit_cost(run.actual_credits) if run.actual_credits is not None else None
            ),
        }
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action=action,
            entity_type="buyer_discovery_run",
            entity_id=run.id,
            previous_value=None,
            new_value={
                "provider": "dealmachine",
                "search_tier": run.search_tier,
                "request_fingerprint": run.request_fingerprint,
                "estimated_credits": run.estimated_credits,
                "actual_credits": run.actual_credits,
                "error": error_message,
                "buyers_imported": 0,
                "external_messages_sent": 0,
            },
            reason="Governed DealMachine buyer discovery was stopped",
        )
    )


def _estimate_credit_snapshot(estimate: dict[str, Any]) -> dict[str, Any]:
    estimated = _dictionary(estimate.get("estimated_credits"))
    return {
        "this_page": _integer(estimated.get("this_page")) or 0,
        "total_all_pages": _integer(estimated.get("total_all_pages")) or 0,
        "breakdown": _dictionary(estimated.get("breakdown")),
    }


def _usage_credit_snapshot(usage: dict[str, Any]) -> dict[str, Any]:
    credits = _dictionary(usage.get("credits"))
    return {
        "total_available": _integer(credits.get("total_available")),
        "used": _integer(credits.get("used")),
        "total_cap": _integer(credits.get("total_cap")),
    }


def _credit_cost(credits: int) -> float:
    return float(
        (Decimal(max(credits, 0)) * CREDIT_COST_USD).quantize(
            Decimal("0.0001"),
            rounding=ROUND_HALF_UP,
        )
    )


def _subject_coordinates(
    db: Session,
    property_record: Property,
) -> tuple[float | None, float | None]:
    metadata = (
        property_record.address_validation_metadata
        if isinstance(property_record.address_validation_metadata, dict)
        else {}
    )
    facts = _dictionary(metadata.get("facts"))
    latitude = _number(facts.get("latitude"))
    longitude = _number(facts.get("longitude"))
    if latitude is not None and longitude is not None:
        return _valid_coordinates(latitude, longitude)
    snapshot = db.scalar(
        select(PropertyIntelligenceSnapshot)
        .where(
            PropertyIntelligenceSnapshot.organization_id == property_record.organization_id,
            PropertyIntelligenceSnapshot.property_id == property_record.id,
            PropertyIntelligenceSnapshot.is_current.is_(True),
        )
        .order_by(
            PropertyIntelligenceSnapshot.version_number.desc(),
            PropertyIntelligenceSnapshot.created_at.desc(),
        )
    )
    snapshot_facts = snapshot.facts if snapshot and isinstance(snapshot.facts, dict) else {}
    return _valid_coordinates(
        _number(_fact_payload_value(snapshot_facts.get("latitude"))),
        _number(_fact_payload_value(snapshot_facts.get("longitude"))),
    )


def _fact_payload_value(value: object) -> object:
    if isinstance(value, dict):
        return value.get("value")
    return value


def _valid_coordinates(
    latitude: float | None,
    longitude: float | None,
) -> tuple[float | None, float | None]:
    if (
        latitude is None
        or longitude is None
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
    ):
        return None, None
    return round(latitude, 6), round(longitude, 6)


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _add_property_type_filter(
    request: dict[str, Any],
    *,
    property_record: Property,
    filters: list[object],
) -> None:
    target_label = PROPERTY_TYPE_MAP.get((property_record.property_type or "").strip().lower())
    if not target_label:
        return
    target_key = _normalized_option_label(target_label)
    for item in filters:
        if not isinstance(item, dict) or item.get("filter_id") != "property_type":
            continue
        options = item.get("options")
        if not isinstance(options, list):
            return
        for option in options:
            if not isinstance(option, dict):
                continue
            if _normalized_option_label(_string(option.get("label"))) != target_key:
                continue
            option_id = option.get("option_id")
            if not isinstance(option_id, (str, int)) or isinstance(option_id, bool):
                return
            request_filters = request.get("filters")
            if isinstance(request_filters, list):
                request_filters.append(
                    {
                        "filter_id": "property_type",
                        "operator": "contains_any",
                        "value": [option_id],
                    }
                )
            return


def _normalized_option_label(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _candidate_groups(
    records: list[object],
    *,
    case: DispositionCase,
    property_record: Property,
    max_candidates: int,
    scope_description: str = "Subject ZIP",
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    display_names: dict[str, str] = {}
    for raw in records:
        if not isinstance(raw, dict):
            continue
        owner_names = {
            name
            for name in (
                _string(raw.get("owner_1_full_name") or raw.get("owner_name")),
                _string(raw.get("owner_2_full_name")),
            )
            if name
        }
        for name in owner_names:
            key = _normalized_name(name)
            if not key:
                continue
            grouped[key].append(raw)
            display_names.setdefault(key, name)

    result: list[dict[str, Any]] = []
    target = case.asking_price_cents
    subject_type = PROPERTY_TYPE_MAP.get(
        (property_record.property_type or "").strip().lower(),
        property_record.property_type or "Unknown",
    )
    today = datetime.now(UTC).date()
    for key, evidence in grouped.items():
        name = display_names[key]
        email, phone = _contact_details(name, evidence)
        purchases = [
            (_parse_date(item.get("last_sale_date")), _money_cents(item.get("last_sale_price")))
            for item in evidence
        ]
        dates = [value for value, _ in purchases if value is not None]
        prices = [value for _, value in purchases if value is not None]
        property_types = sorted(
            {
                property_type
                for item in evidence
                for property_type in _strings(item.get("property_type"))
            }
        )
        no_mortgage = sum(_integer(item.get("num_mortgages")) == 0 for item in evidence)
        last_date = max(dates) if dates else None
        days_since = (today - last_date).days if last_date else None
        recency = (
            3000
            if days_since is not None and days_since <= 90
            else 2400
            if days_since is not None and days_since <= 180
            else 1800
            if days_since is not None and days_since <= 365
            else 600
            if last_date
            else 0
        )
        closest_price = min(prices, key=lambda price: abs(price - target)) if prices else None
        price_ratio = (
            abs(closest_price - target) / max(target, 1) if closest_price is not None else 1.0
        )
        price_fit = max(0, round(2500 * (1 - min(price_ratio, 1))))
        type_fit = (
            1500
            if any(item.lower() == subject_type.lower() for item in property_types)
            else 750
            if not property_types
            else 0
        )
        activity = min(1500, len(evidence) * 500)
        mortgage_signal = round(1000 * no_mortgage / len(evidence))
        entity = _is_entity(name)
        entity_signal = 500 if entity else 200
        components = {
            "purchase_recency": recency,
            "price_fit": price_fit,
            "property_type_fit": type_fit,
            "observed_activity": activity,
            "no_mortgage_signal": mortgage_signal,
            "entity_signal": entity_signal,
        }
        result.append(
            {
                "external_key": "owner:" + hashlib.sha256(key.encode()).hexdigest()[:40],
                "name": name,
                "company_name": name if entity else None,
                "email": email,
                "phone": phone,
                "market": (
                    f"{property_record.city}, {property_record.state} {property_record.postal_code}"
                ),
                "property_types": property_types or [subject_type],
                "observed_purchase_count": len(evidence),
                "no_mortgage_count": no_mortgage,
                "last_purchase_date": last_date,
                "min_purchase_price_cents": min(prices) if prices else None,
                "max_purchase_price_cents": max(prices) if prices else None,
                "score_basis_points": min(sum(components.values()), 10000),
                "score_components": components,
                "evidence_snapshot": {
                    "basis": (
                        f"Recent recorded purchases sampled by DealMachine using: "
                        f"{scope_description}. "
                        "No-mortgage records are a lead signal, not proof of a cash purchase."
                    ),
                    "observed_property_ids": [
                        _string(item.get("dm_property_id") or item.get("id"))
                        for item in evidence
                        if _string(item.get("dm_property_id") or item.get("id"))
                    ],
                    "observed_addresses": [
                        _record_address(item) for item in evidence if _record_address(item)
                    ],
                },
                "provider_snapshot": {"properties": evidence},
            }
        )
    result.sort(
        key=lambda item: (
            item["score_basis_points"],
            item["last_purchase_date"] or date.min,
            item["observed_purchase_count"],
        ),
        reverse=True,
    )
    return result[:max_candidates]


def _net_new_candidates(
    db: Session,
    principal: Principal,
    case_id: UUID,
    candidates: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    prior_external_keys = set(
        db.scalars(
            select(BuyerDiscoveryCandidate.external_key)
            .join(
                BuyerDiscoveryRun,
                BuyerDiscoveryRun.id == BuyerDiscoveryCandidate.discovery_run_id,
            )
            .where(
                BuyerDiscoveryCandidate.organization_id == principal.organization_id,
                BuyerDiscoveryCandidate.provider == "dealmachine",
                BuyerDiscoveryRun.disposition_case_id == case_id,
            )
        ).all()
    )
    buyers = list(
        db.scalars(
            select(Buyer).where(Buyer.organization_id == principal.organization_id)
        ).all()
    )
    known_provider_keys = {
        buyer.source_external_key
        for buyer in buyers
        if buyer.source_key == "dealmachine" and buyer.source_external_key
    }
    known_emails = {buyer.normalized_email for buyer in buyers if buyer.normalized_email}
    known_phones = {buyer.normalized_phone for buyer in buyers if buyer.normalized_phone}
    known_names = {
        normalized
        for buyer in buyers
        for raw_name in (buyer.name, buyer.company_name)
        if raw_name and (normalized := _normalized_name(raw_name))
    }
    accepted: list[dict[str, Any]] = []
    for candidate in candidates:
        external_key = _string(candidate.get("external_key"))
        if external_key in prior_external_keys or external_key in known_provider_keys:
            continue
        normalized_email = normalize_email(_string(candidate.get("email")))
        normalized_phone = normalize_phone(_string(candidate.get("phone")))
        candidate_names = {
            normalized
            for raw_name in (candidate.get("name"), candidate.get("company_name"))
            if isinstance(raw_name, str) and (normalized := _normalized_name(raw_name))
        }
        if normalized_email and normalized_email in known_emails:
            continue
        if normalized_phone and normalized_phone in known_phones:
            continue
        if candidate_names & known_names:
            continue
        accepted.append(candidate)
        if len(accepted) >= limit:
            break
    return accepted


def _credit_summary(response: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("credits", "credit_summary", "usage"):
        value = response.get(key)
        if isinstance(value, dict):
            return value
    meta = response.get("meta")
    if isinstance(meta, dict):
        for key in ("credits", "credit_summary", "usage"):
            value = meta.get(key)
            if isinstance(value, dict):
                return value
    return None


def _contact_details(
    owner_name: str,
    records: list[dict[str, Any]],
) -> tuple[str | None, str | None]:
    owner_key = _normalized_name(owner_name)
    contacts: list[dict[str, Any]] = []
    for record in records:
        raw_contacts = record.get("contacts")
        if isinstance(raw_contacts, list):
            contacts.extend(item for item in raw_contacts if isinstance(item, dict))
    matching = [
        item
        for item in contacts
        if _normalized_name(_string(item.get("full_name") or item.get("person_full_name")))
        == owner_key
    ]
    ordered = matching + [item for item in contacts if item not in matching]
    for contact in ordered:
        emails = contact.get("emails")
        phones = contact.get("phones")
        email = _first_contact_value(emails, ("email", "address", "value"))
        phone = _first_contact_value(
            phones,
            ("number", "phone", "value"),
            skip_do_not_call=True,
        )
        if email or phone:
            return email, phone
    return None, None


def _first_contact_value(
    value: object,
    fields: tuple[str, ...],
    *,
    skip_do_not_call: bool = False,
) -> str | None:
    if not isinstance(value, list):
        return None
    for item in value:
        if isinstance(item, str) and item.strip():
            return item.strip()
        if isinstance(item, dict):
            if skip_do_not_call and item.get("do_not_call") is True:
                continue
            for field in fields:
                result = _string(item.get(field))
                if result:
                    return result
    return None


def _normalized_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _is_entity(value: str) -> bool:
    return bool(set(_normalized_name(value).split()) & ENTITY_TERMS)


def _parse_date(value: object) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _money_cents(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return round(float(value) * 100)
    if isinstance(value, str):
        try:
            return round(float(value.replace(",", "").replace("$", "")) * 100)
        except ValueError:
            return None
    return None


def _integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return None
    return None


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _dictionary(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _string(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return []


def _record_address(record: dict[str, Any]) -> str:
    return ", ".join(
        value
        for value in (
            _string(record.get("address")),
            _string(record.get("city")),
            _string(record.get("state")),
            _string(record.get("zip") or record.get("code")),
        )
        if value
    )


def _address(property_record: Property) -> str:
    return (
        f"{property_record.street_address}, {property_record.city}, "
        f"{property_record.state} {property_record.postal_code}"
    )
