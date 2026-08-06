import hashlib
import re
from collections import defaultdict
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import Settings, get_settings
from app.integrations.dealmachine_client import DealMachineClient, DealMachineError
from app.models.foundation import (
    ActivityEvent,
    AuditEvent,
    Buyer,
    BuyerCriteria,
    BuyerDiscoveryCandidate,
    BuyerDiscoveryRun,
    DispositionCase,
    Property,
)
from app.schemas.buyers import (
    BuyerDataProviderRead,
    BuyerDiscoveryCandidateRead,
    BuyerDiscoveryCreate,
    BuyerDiscoveryEstimateCreate,
    BuyerDiscoveryEstimateRead,
    BuyerDiscoveryImport,
    BuyerDiscoveryRunRead,
)

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
    enabled = bool(paid is not False and remaining is not None and remaining > 0)
    if enabled:
        message = "DealMachine is connected and ready for cost-previewed buyer discovery."
    elif paid is False:
        message = "DealMachine is connected, but the account does not have a paid API plan."
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
    case, property_record, provider_request = _discovery_context(db, principal, payload, settings)
    provider_client = client or DealMachineClient(settings)
    try:
        _add_property_type_filter(
            provider_request,
            property_record=property_record,
            filters=provider_client.list_property_filters(),
        )
        usage = provider_client.get_usage()
        estimate = provider_client.estimate_property_search(provider_request)
    except DealMachineError as exc:
        raise ValueError(str(exc)) from exc
    return _estimate_read(case.id, payload, provider_request, estimate, usage)


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
    case, property_record, provider_request = _discovery_context(db, principal, payload, settings)
    postal_code = property_record.postal_code.strip()[:5]
    provider_client = client or DealMachineClient(settings)
    try:
        _add_property_type_filter(
            provider_request,
            property_record=property_record,
            filters=provider_client.list_property_filters(),
        )
        usage = provider_client.get_usage()
        estimate = provider_client.estimate_property_search(provider_request)
    except DealMachineError as exc:
        raise ValueError(str(exc)) from exc
    estimate_read = _estimate_read(
        case.id,
        payload,
        provider_request,
        estimate,
        usage,
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
        disposition_case_id=case.id,
        requested_by_user_id=principal.user_id,
        provider="dealmachine",
        status="running",
        search_snapshot={
            "property_address": _address(property_record),
            "postal_code": postal_code,
            "property_type": property_record.property_type,
            "asking_price_cents": case.asking_price_cents,
            "max_candidates": payload.max_candidates,
        },
        provider_request=provider_request,
        result_count=0,
        imported_count=0,
        credit_summary=None,
        error_message=None,
        completed_at=None,
    )
    db.add(run)
    db.flush()
    try:
        response = provider_client.search_properties(provider_request)
        candidates = _candidate_groups(
            response.get("data", []),
            case=case,
            property_record=property_record,
            max_candidates=payload.max_candidates,
        )
    except DealMachineError as exc:
        run.status = "failed"
        run.error_message = str(exc)
        run.completed_at = datetime.now(UTC)
        db.commit()
        raise ValueError(str(exc)) from exc

    for item in candidates:
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
                state=property_record.state.upper(),
                property_types=item["property_types"],
                observed_purchase_count=item["observed_purchase_count"],
                no_mortgage_count=item["no_mortgage_count"],
                last_purchase_date=item["last_purchase_date"],
                min_purchase_price_cents=item["min_purchase_price_cents"],
                max_purchase_price_cents=item["max_purchase_price_cents"],
                score_basis_points=item["score_basis_points"],
                score_components=item["score_components"],
                evidence_snapshot=item["evidence_snapshot"],
                provider_snapshot=item["provider_snapshot"],
                status="review",
                imported_at=None,
            )
        )
    run.status = "completed"
    run.result_count = len(candidates)
    run.credit_summary = _credit_summary(response)
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
                "disposition_case_id": str(case.id),
                "candidate_count": len(candidates),
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
    case = db.get(DispositionCase, run.disposition_case_id)
    property_record = db.get(Property, case.property_id) if case else None
    if case is None or property_record is None:
        raise ValueError("The source disposition case is unavailable.")

    existing_buyers = list(
        db.scalars(select(Buyer).where(Buyer.organization_id == principal.organization_id)).all()
    )
    by_name = {_normalized_name(item.company_name or item.name): item for item in existing_buyers}
    imported = 0
    duplicates = 0
    now = datetime.now(UTC)
    for candidate in candidates:
        if candidate.buyer_id is not None:
            candidate.status = "duplicate"
            duplicates += 1
            continue
        previous = db.scalar(
            select(BuyerDiscoveryCandidate)
            .where(
                BuyerDiscoveryCandidate.organization_id == principal.organization_id,
                BuyerDiscoveryCandidate.provider == candidate.provider,
                BuyerDiscoveryCandidate.external_key == candidate.external_key,
                BuyerDiscoveryCandidate.buyer_id.is_not(None),
                BuyerDiscoveryCandidate.id != candidate.id,
            )
            .order_by(BuyerDiscoveryCandidate.imported_at.desc())
            .limit(1)
        )
        buyer = (
            db.get(Buyer, previous.buyer_id)
            if previous and previous.buyer_id is not None
            else by_name.get(_normalized_name(candidate.company_name or candidate.name))
        )
        if buyer is not None:
            candidate.buyer_id = buyer.id
            candidate.status = "duplicate"
            candidate.imported_at = now
            duplicates += 1
            continue

        observed_max = candidate.max_purchase_price_cents
        buyer = Buyer(
            organization_id=principal.organization_id,
            name=candidate.name,
            company_name=candidate.company_name,
            email=candidate.email,
            phone=candidate.phone,
            buyer_type="cash_buyer",
            status="active",
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
        candidate.buyer_id = buyer.id
        candidate.status = "imported"
        candidate.imported_at = now
        by_name[_normalized_name(candidate.company_name or candidate.name)] = buyer
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
    )


def _discovery_context(
    db: Session,
    principal: Principal,
    payload: BuyerDiscoveryEstimateCreate,
    settings: Settings,
) -> tuple[DispositionCase, Property, dict[str, Any]]:
    case = db.scalar(
        select(DispositionCase).where(
            DispositionCase.id == payload.disposition_case_id,
            DispositionCase.organization_id == principal.organization_id,
        )
    )
    if case is None:
        raise ValueError("Disposition case not found.")
    property_record = db.scalar(
        select(Property).where(
            Property.id == case.property_id,
            Property.organization_id == principal.organization_id,
        )
    )
    if property_record is None:
        raise ValueError("The disposition case has no property record.")
    postal_code = (property_record.postal_code or "").strip()[:5]
    if not re.fullmatch(r"\d{5}", postal_code):
        raise ValueError("A five-digit property ZIP code is required for buyer discovery.")
    return case, property_record, _provider_request(case, property_record, payload, settings)


def _estimate_read(
    case_id: UUID,
    payload: BuyerDiscoveryEstimateCreate,
    provider_request: dict[str, Any],
    estimate: dict[str, Any],
    usage: dict[str, Any],
) -> BuyerDiscoveryEstimateRead:
    estimated = _dictionary(estimate.get("estimated_credits"))
    breakdown = _dictionary(estimated.get("breakdown"))
    pagination = _dictionary(estimate.get("pagination"))
    totals = _dictionary(estimate.get("totals"))
    credits = _dictionary(usage.get("credits"))
    plan = _dictionary(usage.get("plan"))
    estimated_credits = _integer(estimated.get("this_page")) or 0
    credits_remaining = _integer(credits.get("total_available")) or 0
    paid = plan.get("is_paid")
    enough_credits = paid is not False and credits_remaining >= estimated_credits
    if paid is False:
        message = "The connected DealMachine account does not have a paid API plan."
    elif enough_credits:
        message = (
            f"This search can use up to {estimated_credits} DealMachine credits; "
            f"{credits_remaining} are currently available."
        )
    else:
        message = (
            f"This search can use up to {estimated_credits} DealMachine credits, but only "
            f"{credits_remaining} are currently available. Reduce the search or add credits."
        )
    return BuyerDiscoveryEstimateRead(
        disposition_case_id=case_id,
        requested_candidates=payload.max_candidates,
        provider_result_limit=_integer(provider_request.get("per_page")) or 0,
        total_matching_properties=(
            _integer(pagination.get("total_results")) or _integer(totals.get("properties")) or 0
        ),
        estimated_credits=estimated_credits,
        estimated_property_credits=_integer(breakdown.get("properties")) or 0,
        estimated_people_credits=_integer(breakdown.get("people")) or 0,
        credits_remaining=credits_remaining,
        enough_credits=enough_credits,
        message=message,
    )


def _provider_request(
    case: DispositionCase,
    property_record: Property,
    payload: BuyerDiscoveryEstimateCreate,
    settings: Settings,
) -> dict[str, Any]:
    target_dollars = max(round(case.asking_price_cents / 100), 1)
    filters: list[dict[str, Any]] = [
        {"filter_id": "is_recently_sold", "value": True},
        {
            "filter_id": "last_sale_price",
            "operator": "range",
            "value": {
                "min": max(round(target_dollars * 0.5), 1),
                "max": round(target_dollars * 1.75),
            },
        },
    ]
    return {
        "locations": [{"type": "zip_code", "code": property_record.postal_code.strip()[:5]}],
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
            max(payload.max_candidates * 4, payload.max_candidates),
        ),
        "sort": [{"field_id": "last_sale_date", "direction": "desc"}],
    }


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
                        "Recent recorded purchases sampled by DealMachine in the subject ZIP. "
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
