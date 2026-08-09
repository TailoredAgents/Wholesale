from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from time import perf_counter
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import Settings, get_settings
from app.domain.assets import (
    LAND_ASSET_CLASS,
    LAND_RESEARCH_PROFILE,
    LAND_VALUATION_PROFILE,
    normalize_asset_class,
    require_land_workflow_enabled,
)
from app.domain.rbac import PermissionKeys
from app.integrations.realestateapi_client import RealEstateAPIClient, RealEstateAPIError
from app.models.foundation import (
    ActivityEvent,
    AuditEvent,
    LandOfferPolicyVersion,
    LandValuationAnalysis,
    Lead,
    Property,
    PropertyIntelligenceSnapshot,
)
from app.schemas.land_underwriting import (
    LandComparableRead,
    LandOfferPolicyCreate,
    LandOfferPolicyRead,
    LandValuationCreate,
    LandValuationRead,
)
from app.services.land_comparable_evidence import (
    SQUARE_FEET_PER_ACRE,
    evaluate_land_sales,
    land_search_bounds,
    normalize_realestateapi_land_sale,
)
from app.services.land_valuation import analyze_land_valuation
from app.services.land_valuation_state import (
    active_land_offer_policy_id,
    current_land_analysis_reasons,
)
from app.services.property_intelligence import (
    as_utc,
    current_property_snapshot,
    property_research_signature,
)

LAND_METHODOLOGY_VERSION = "land_v1.0"


def create_land_offer_policy(
    db: Session,
    principal: Principal,
    payload: LandOfferPolicyCreate,
) -> LandOfferPolicyRead:
    require_permission(principal, PermissionKeys.APPROVE_OFFERS)
    version_number = (
        int(
            db.scalar(
                select(func.coalesce(func.max(LandOfferPolicyVersion.version_number), 0)).where(
                    LandOfferPolicyVersion.organization_id == principal.organization_id
                )
            )
            or 0
        )
        + 1
    )
    policy = LandOfferPolicyVersion(
        organization_id=principal.organization_id,
        created_by_user_id=principal.user_id,
        approved_by_user_id=None,
        version_number=version_number,
        status="draft",
        title=payload.title.strip(),
        quick_sale_discount_low_basis_points=payload.quick_sale_discount_low_basis_points,
        quick_sale_discount_high_basis_points=payload.quick_sale_discount_high_basis_points,
        opening_reserve_basis_points=payload.opening_reserve_basis_points,
        assignment_fee_cents=payload.assignment_fee_cents,
        closing_title_reserve_cents=payload.closing_title_reserve_cents,
        curative_reserve_cents=payload.curative_reserve_cents,
        uncertainty_reserve_cents=payload.uncertainty_reserve_cents,
        maximum_dispersion_basis_points=payload.maximum_dispersion_basis_points,
        minimum_comparable_count=payload.minimum_comparable_count,
        notes=payload.notes.strip() if payload.notes else None,
        approved_at=None,
    )
    db.add(policy)
    db.flush()
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="land_offer_policy.create",
            entity_type="land_offer_policy",
            entity_id=policy.id,
            previous_value=None,
            new_value=policy_snapshot(policy),
            reason="Draft Land offer policy created",
        )
    )
    db.commit()
    return land_offer_policy_to_read(policy)


def activate_land_offer_policy(
    db: Session,
    principal: Principal,
    policy_id: UUID,
    *,
    reason: str,
) -> LandOfferPolicyRead | None:
    require_permission(principal, PermissionKeys.APPROVE_OFFERS)
    clean_reason = reason.strip()
    if not clean_reason:
        raise ValueError("A reason is required to activate a Land offer policy.")
    policy = db.scalar(
        select(LandOfferPolicyVersion).where(
            LandOfferPolicyVersion.organization_id == principal.organization_id,
            LandOfferPolicyVersion.id == policy_id,
        )
    )
    if policy is None:
        return None
    if policy.status == "active":
        return land_offer_policy_to_read(policy)
    previous = policy_snapshot(policy)
    db.execute(
        update(LandOfferPolicyVersion)
        .where(
            LandOfferPolicyVersion.organization_id == principal.organization_id,
            LandOfferPolicyVersion.status == "active",
            LandOfferPolicyVersion.id != policy.id,
        )
        .values(status="retired")
    )
    policy.status = "active"
    policy.approved_by_user_id = principal.user_id
    policy.approved_at = datetime.now(UTC)
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="land_offer_policy.activate",
            entity_type="land_offer_policy",
            entity_id=policy.id,
            previous_value=previous,
            new_value=policy_snapshot(policy),
            reason=clean_reason,
        )
    )
    db.commit()
    return land_offer_policy_to_read(policy)


def list_land_offer_policies(
    db: Session,
    principal: Principal,
) -> list[LandOfferPolicyRead]:
    require_permission(principal, PermissionKeys.EDIT_UNDERWRITING)
    policies = db.scalars(
        select(LandOfferPolicyVersion)
        .where(LandOfferPolicyVersion.organization_id == principal.organization_id)
        .order_by(LandOfferPolicyVersion.version_number.desc())
    ).all()
    return [land_offer_policy_to_read(policy) for policy in policies]


def latest_land_valuation(
    db: Session,
    principal: Principal,
    lead_id: UUID,
) -> LandValuationRead | None:
    require_permission(principal, PermissionKeys.EDIT_UNDERWRITING)
    lead = scoped_land_lead(db, principal, lead_id)
    if lead is None:
        return None
    analysis = db.scalar(
        select(LandValuationAnalysis)
        .where(
            LandValuationAnalysis.organization_id == principal.organization_id,
            LandValuationAnalysis.lead_id == lead.id,
            LandValuationAnalysis.valuation_profile == LAND_VALUATION_PROFILE,
        )
        .order_by(
            LandValuationAnalysis.version_number.desc(),
            LandValuationAnalysis.created_at.desc(),
        )
    )
    return (
        current_land_valuation_to_read(db, lead, analysis)
        if analysis is not None
        else None
    )


def list_land_valuations(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    *,
    limit: int = 25,
) -> list[LandValuationRead] | None:
    require_permission(principal, PermissionKeys.EDIT_UNDERWRITING)
    lead = scoped_land_lead(db, principal, lead_id)
    if lead is None:
        return None
    analyses = db.scalars(
        select(LandValuationAnalysis)
        .where(
            LandValuationAnalysis.organization_id == principal.organization_id,
            LandValuationAnalysis.lead_id == lead.id,
            LandValuationAnalysis.valuation_profile == LAND_VALUATION_PROFILE,
        )
        .order_by(
            LandValuationAnalysis.version_number.desc(),
            LandValuationAnalysis.created_at.desc(),
        )
        .limit(max(1, min(limit, 100)))
    ).all()
    return [current_land_valuation_to_read(db, lead, analysis) for analysis in analyses]


def create_land_valuation(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    payload: LandValuationCreate,
    *,
    settings: Settings | None = None,
    client: RealEstateAPIClient | None = None,
) -> LandValuationRead | None:
    active_settings = settings or get_settings()
    require_land_workflow_enabled(active_settings.land_workflow_enabled)
    require_permission(principal, PermissionKeys.EDIT_UNDERWRITING)
    lead = scoped_land_lead(db, principal, lead_id, lock_for_update=True)
    if lead is None:
        return None
    request_idempotency_key = clean_idempotency_key(payload.idempotency_key)
    request_payload_fingerprint = analysis_fingerprint(
        {
            "lead_id": str(lead.id),
            "payload": payload.model_dump(
                mode="json",
                exclude={"idempotency_key"},
            ),
        }
    )
    if payload.refresh_comps and request_idempotency_key is None:
        raise ValueError(
            "An idempotency key is required for a paid Land comparable search."
        )
    if request_idempotency_key is not None:
        existing_request = db.scalar(
            select(LandValuationAnalysis).where(
                LandValuationAnalysis.organization_id == principal.organization_id,
                LandValuationAnalysis.lead_id == lead.id,
                LandValuationAnalysis.request_idempotency_key
                == request_idempotency_key,
            )
        )
        if existing_request is not None:
            existing_request_fingerprint = str(
                (existing_request.analysis_metadata or {}).get(
                    "request_payload_fingerprint"
                )
                or ""
            )
            if existing_request_fingerprint != request_payload_fingerprint:
                raise ValueError(
                    "This Land-search idempotency key was already used for different inputs."
                )
            return current_land_valuation_to_read(db, lead, existing_request)
    property_record = db.get(Property, lead.property_id)
    if property_record is None:
        raise ValueError("The Land lead is missing its property record.")
    snapshot = current_property_snapshot(
        db,
        organization_id=principal.organization_id,
        property_id=property_record.id,
        research_profile=LAND_RESEARCH_PROFILE,
    )
    if snapshot is None or snapshot.address_signature != property_research_signature(
        property_record,
        research_profile=LAND_RESEARCH_PROFILE,
    ):
        raise ValueError("Refresh Land property research before running valuation.")
    subject_acres = subject_acres_from_snapshot(snapshot, payload)
    if subject_acres is None or subject_acres <= 0:
        raise ValueError(
            "Land valuation requires positive acreage from saved research or an evidenced override."
        )
    subject_parcel_id = property_record.parcel_id or fact_string(snapshot, "parcel_id")
    subject_county = property_record.county or fact_string(snapshot, "county")
    subject_state = property_record.state.strip().upper()
    subject_latitude = fact_float(snapshot, "latitude")
    subject_longitude = fact_float(snapshot, "longitude")
    provider_subject_use = (
        fact_string(snapshot, "land_use")
        or fact_string(snapshot, "property_use")
        or fact_string(snapshot, "zoning")
    )
    subject_use = payload.subject_use_override or provider_subject_use

    source_analysis = source_land_analysis(
        db,
        principal,
        lead,
        payload.source_analysis_id,
    )
    selected_keys = (
        None
        if payload.selected_comp_keys is None
        else set(payload.selected_comp_keys)
    )
    if source_analysis is not None:
        if source_analysis.property_snapshot_id != snapshot.id:
            raise ValueError(
                "The saved Land analysis belongs to an older property snapshot. Start a new "
                "comparable search."
            )
        require_compatible_saved_subject(
            source_analysis,
            subject_acres=subject_acres,
            subject_lot_count=payload.subject_lot_count,
            valuation_basis=payload.valuation_basis,
        )
        normalized_candidates = [
            dict(item)
            for item in [*source_analysis.selected_comps, *source_analysis.rejected_comps]
            if isinstance(item, dict)
        ]
        if selected_keys is None:
            selected_keys = {
                str(item.get("key"))
                for item in source_analysis.selected_comps
                if isinstance(item, dict) and item.get("key")
            }
        search_snapshot = {
            **source_analysis.search_snapshot,
            "provider_call_made": False,
            "source_analysis_id": str(source_analysis.id),
            "reused_saved_evidence": True,
        }
    else:
        if not payload.refresh_comps:
            raise ValueError(
                "The first Land valuation requires an explicit comparable refresh. This may "
                "consume RealEstateAPI credits."
            )
        if not active_settings.realestateapi_api_key:
            raise ValueError("REALESTATEAPI_API_KEY is required for Land comparable research.")
        bounds = land_search_bounds(
            subject_acres=subject_acres,
            tier=payload.search_tier,
            today=date.today(),
        )
        provider = client or RealEstateAPIClient(active_settings)
        started = perf_counter()
        try:
            result = provider.search_land_sales(
                state=subject_state,
                county=subject_county,
                latitude=subject_latitude,
                longitude=subject_longitude,
                radius_miles=float(bounds["radius_miles"]),
                sale_date_min=str(bounds["sale_date_min"]),
                lot_size_min=int(bounds["lot_size_min"]),
                lot_size_max=int(bounds["lot_size_max"]),
                size=active_settings.land_valuation_max_provider_results,
            )
        except RealEstateAPIError as exc:
            raise RuntimeError(str(exc)) from exc
        latency_ms = round((perf_counter() - started) * 1000)
        normalized_candidates = [
            normalize_realestateapi_land_sale(
                item,
                subject_acres=subject_acres,
                subject_lot_count=payload.subject_lot_count,
                valuation_basis=payload.valuation_basis,
                subject_latitude=subject_latitude,
                subject_longitude=subject_longitude,
                today=date.today(),
            )
            for item in result.properties
        ]
        search_snapshot = {
            **bounds,
            "provider": "realestateapi",
            "provider_call_made": True,
            "provider_endpoint": "/v2/PropertySearch",
            "provider_returned_count": len(result.properties),
            "provider_result_count": result.result_count,
            "provider_response_count": result.response_count,
            "provider_credits_estimated": result.response_count,
            "provider_latency_ms": latency_ms,
            "maximum_requested_results": active_settings.land_valuation_max_provider_results,
            "one_paid_call_boundary": True,
            "arms_length_filter": True,
            "property_type_filter": "LAND",
            "location_mode": (
                "radius"
                if subject_latitude is not None and subject_longitude is not None
                else "county"
            ),
            "reused_saved_evidence": False,
        }

    selected_comps, rejected_comps = evaluate_land_sales(
        normalized_candidates,
        subject_parcel_id=subject_parcel_id,
        subject_county=subject_county,
        subject_state=subject_state,
        subject_use=subject_use,
        selected_keys=selected_keys,
    )
    policy = active_land_offer_policy(db, principal.organization_id)
    policy_values = policy_snapshot(policy) if policy is not None else None
    snapshot_is_fresh = as_utc(snapshot.expires_at) > datetime.now(UTC)
    identity_conflicted = subject_identity_conflicted(snapshot)
    result_values = analyze_land_valuation(
        selected_comps=selected_comps,
        subject_acres=subject_acres,
        subject_lot_count=payload.subject_lot_count,
        valuation_basis=payload.valuation_basis,
        subject_parcel_id=subject_parcel_id,
        subject_use=subject_use,
        subject_coordinates_available=(
            subject_latitude is not None and subject_longitude is not None
        ),
        access_evidence_status=payload.access_evidence_status,
        access_evidence_reference=payload.access_evidence_reference,
        snapshot_is_fresh=snapshot_is_fresh,
        subject_identity_conflicted=identity_conflicted,
        active_policy=policy_values,
    )
    subject_snapshot = {
        "property_snapshot_id": str(snapshot.id),
        "property_identity_signature": snapshot.address_signature,
        "parcel_id": subject_parcel_id,
        "county": subject_county,
        "state": subject_state,
        "acres": float(subject_acres),
        "acreage_source": (
            "human_override"
            if payload.subject_acres_override is not None
            else "saved_property_snapshot"
        ),
        "acreage_evidence_reference": payload.subject_acres_evidence_reference,
        "lot_count": payload.subject_lot_count,
        "lot_count_evidence_reference": payload.subject_lot_count_evidence_reference,
        "land_use": subject_use,
        "land_use_source": (
            "human_override"
            if payload.subject_use_override is not None
            else "saved_property_snapshot"
        ),
        "land_use_evidence_reference": payload.subject_use_evidence_reference,
        "provider_land_use": provider_subject_use,
        "latitude": subject_latitude,
        "longitude": subject_longitude,
        "captured_at": snapshot.captured_at.isoformat(),
        "expires_at": snapshot.expires_at.isoformat(),
        "snapshot_is_fresh": snapshot_is_fresh,
        "identity_conflicted": identity_conflicted,
        "access_evidence_status": payload.access_evidence_status,
        "access_evidence_reference": payload.access_evidence_reference,
    }
    assumptions = {
        **dict(result_values["calculation"]),
        "methodology_version": LAND_METHODOLOGY_VERSION,
        "provider_avm_excluded": True,
        "residential_arv_excluded": True,
        "rehab_math_excluded": True,
        "review_note": payload.review_note,
    }
    fingerprint = analysis_fingerprint(
        {
            "lead_id": str(lead.id),
            "snapshot_id": str(snapshot.id),
            "source_analysis_id": str(source_analysis.id) if source_analysis else None,
            "policy_id": str(policy.id) if policy else None,
            "payload": payload.model_dump(mode="json"),
            "selected_comps": selected_comps,
            "rejected_comp_keys": [item.get("key") for item in rejected_comps],
            "methodology_version": LAND_METHODOLOGY_VERSION,
        }
    )
    existing = db.scalar(
        select(LandValuationAnalysis).where(
            LandValuationAnalysis.organization_id == principal.organization_id,
            LandValuationAnalysis.lead_id == lead.id,
            LandValuationAnalysis.analysis_fingerprint == fingerprint,
        )
    )
    if existing is not None:
        return current_land_valuation_to_read(db, lead, existing)
    version_number = (
        int(
            db.scalar(
                select(func.coalesce(func.max(LandValuationAnalysis.version_number), 0)).where(
                    LandValuationAnalysis.lead_id == lead.id
                )
            )
            or 0
        )
        + 1
    )
    analysis = LandValuationAnalysis(
        organization_id=principal.organization_id,
        lead_id=lead.id,
        property_id=property_record.id,
        property_snapshot_id=snapshot.id,
        source_analysis_id=source_analysis.id if source_analysis else None,
        policy_version_id=policy.id if policy else None,
        created_by_user_id=principal.user_id,
        version_number=version_number,
        valuation_profile=LAND_VALUATION_PROFILE,
        methodology_version=LAND_METHODOLOGY_VERSION,
        analysis_fingerprint=fingerprint,
        request_idempotency_key=request_idempotency_key,
        status=str(result_values["status"]),
        guidance_status=str(result_values["guidance_status"]),
        valuation_basis=payload.valuation_basis,
        access_evidence_status=payload.access_evidence_status,
        subject_acres_ten_thousandths=decimal_acres_to_ten_thousandths(subject_acres),
        subject_lot_count=payload.subject_lot_count,
        supported_value_low_cents=optional_int(result_values["supported_value_low_cents"]),
        supported_value_cents=optional_int(result_values["supported_value_cents"]),
        supported_value_high_cents=optional_int(result_values["supported_value_high_cents"]),
        quick_sale_low_cents=optional_int(result_values["quick_sale_low_cents"]),
        quick_sale_high_cents=optional_int(result_values["quick_sale_high_cents"]),
        opening_offer_cents=optional_int(result_values["opening_offer_cents"]),
        seller_contract_ceiling_cents=optional_int(
            result_values["seller_contract_ceiling_cents"]
        ),
        assignment_fee_cents=int(result_values["assignment_fee_cents"]),
        closing_title_reserve_cents=int(result_values["closing_title_reserve_cents"]),
        curative_reserve_cents=int(result_values["curative_reserve_cents"]),
        uncertainty_reserve_cents=int(result_values["uncertainty_reserve_cents"]),
        confidence_score=int(result_values["confidence_score"]),
        selected_comp_count=len(selected_comps),
        rejected_comp_count=len(rejected_comps),
        selected_comps=selected_comps,
        rejected_comps=rejected_comps,
        subject_snapshot=subject_snapshot,
        search_snapshot=search_snapshot,
        assumptions=assumptions,
        review_reasons=list(result_values["review_reasons"]),
        guidance_blockers=list(result_values["guidance_blockers"]),
        policy_snapshot=policy_values or {},
        analysis_metadata={
            "dispersion_basis_points": result_values["dispersion_basis_points"],
            "minimum_comparable_count": result_values["minimum_comparable_count"],
            "broad_market_comp_count": result_values["broad_market_comp_count"],
            "one_provider_call_maximum": True,
            "request_payload_fingerprint": request_payload_fingerprint,
        },
    )
    db.add(analysis)
    db.flush()
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            event_type="land.valuation_created",
            summary=(
                f"Land valuation v{version_number} saved with {len(selected_comps)} selected "
                f"closed sale(s); offer guidance is {analysis.guidance_status}."
            ),
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="land_valuation.create",
            entity_type="land_valuation",
            entity_id=analysis.id,
            previous_value=None,
            new_value={
                "lead_id": str(lead.id),
                "version_number": version_number,
                "status": analysis.status,
                "guidance_status": analysis.guidance_status,
                "selected_comp_count": len(selected_comps),
                "provider_call_made": search_snapshot.get("provider_call_made"),
                "provider_credits_estimated": search_snapshot.get(
                    "provider_credits_estimated"
                ),
            },
            reason=payload.review_note or "Land comparable valuation created",
        )
    )
    db.commit()
    return current_land_valuation_to_read(db, lead, analysis)


def scoped_land_lead(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    *,
    lock_for_update: bool = False,
) -> Lead | None:
    filters = [
        Lead.organization_id == principal.organization_id,
        Lead.id == lead_id,
        Lead.archived_at.is_(None),
    ]
    if (
        PermissionKeys.VIEW_LEADS not in principal.permission_keys
        and PermissionKeys.EDIT_LEADS not in principal.permission_keys
    ):
        filters.append(Lead.assigned_user_id == principal.user_id)
    statement = select(Lead).where(*filters)
    if lock_for_update:
        statement = statement.with_for_update()
    lead = db.scalar(statement)
    if lead is not None and normalize_asset_class(lead.asset_class) != LAND_ASSET_CLASS:
        raise ValueError("Land valuation is available only for Land leads.")
    return lead


def source_land_analysis(
    db: Session,
    principal: Principal,
    lead: Lead,
    source_analysis_id: UUID | None,
) -> LandValuationAnalysis | None:
    if source_analysis_id is None:
        return None
    source = db.scalar(
        select(LandValuationAnalysis).where(
            LandValuationAnalysis.organization_id == principal.organization_id,
            LandValuationAnalysis.lead_id == lead.id,
            LandValuationAnalysis.id == source_analysis_id,
            LandValuationAnalysis.valuation_profile == LAND_VALUATION_PROFILE,
        )
    )
    if source is None:
        raise ValueError("The saved Land analysis is unavailable for this lead.")
    return source


def require_compatible_saved_subject(
    source: LandValuationAnalysis,
    *,
    subject_acres: Decimal,
    subject_lot_count: int | None,
    valuation_basis: str,
) -> None:
    source_acres = (
        Decimal(source.subject_acres_ten_thousandths) / Decimal(10_000)
    ).quantize(Decimal("0.0001"))
    requested_acres = subject_acres.quantize(Decimal("0.0001"))
    if source_acres != requested_acres:
        raise ValueError(
            "Changing subject acreage requires a fresh Land comparable search because saved "
            "sale indications were calculated against the original acreage."
        )
    if source.valuation_basis != valuation_basis:
        raise ValueError(
            "Changing between per-acre and per-lot valuation requires a fresh Land "
            "comparable search."
        )
    if valuation_basis == "per_lot" and source.subject_lot_count != subject_lot_count:
        raise ValueError(
            "Changing the verified subject lot count requires a fresh Land comparable search."
        )


def active_land_offer_policy(
    db: Session,
    organization_id: UUID,
) -> LandOfferPolicyVersion | None:
    return db.scalar(
        select(LandOfferPolicyVersion)
        .where(
            LandOfferPolicyVersion.organization_id == organization_id,
            LandOfferPolicyVersion.status == "active",
        )
        .order_by(LandOfferPolicyVersion.version_number.desc())
    )


def subject_acres_from_snapshot(
    snapshot: PropertyIntelligenceSnapshot,
    payload: LandValuationCreate,
) -> Decimal | None:
    if payload.subject_acres_override is not None:
        return payload.subject_acres_override.quantize(Decimal("0.0001"))
    acres = fact_decimal(snapshot, "lot_size_acres")
    if acres is not None and acres > 0:
        return acres.quantize(Decimal("0.0001"))
    square_feet = fact_decimal(snapshot, "lot_size")
    if square_feet is not None and square_feet > 0:
        return (square_feet / SQUARE_FEET_PER_ACRE).quantize(Decimal("0.0001"))
    return None


def fact_value(snapshot: PropertyIntelligenceSnapshot, key: str) -> Any:
    value = snapshot.facts.get(key)
    return value.get("value") if isinstance(value, dict) else value


def fact_string(snapshot: PropertyIntelligenceSnapshot, key: str) -> str | None:
    value = fact_value(snapshot, key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def fact_decimal(snapshot: PropertyIntelligenceSnapshot, key: str) -> Decimal | None:
    value = fact_value(snapshot, key)
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def fact_float(snapshot: PropertyIntelligenceSnapshot, key: str) -> float | None:
    value = fact_decimal(snapshot, key)
    return float(value) if value is not None else None


def subject_identity_conflicted(snapshot: PropertyIntelligenceSnapshot) -> bool:
    identity_fields = {"parcel_id", "county", "state", "lot_size", "lot_size_acres"}
    return any(
        isinstance(conflict, dict)
        and str(conflict.get("field") or "") in identity_fields
        and str(conflict.get("severity") or "review") in {"high", "critical", "review"}
        for conflict in snapshot.conflicts
    )


def policy_snapshot(policy: LandOfferPolicyVersion) -> dict[str, Any]:
    return {
        "id": str(policy.id),
        "version_number": policy.version_number,
        "status": policy.status,
        "title": policy.title,
        "notes": policy.notes,
        "created_by_user_id": str(policy.created_by_user_id),
        "created_at": policy.created_at.isoformat(),
        "quick_sale_discount_low_basis_points": (
            policy.quick_sale_discount_low_basis_points
        ),
        "quick_sale_discount_high_basis_points": (
            policy.quick_sale_discount_high_basis_points
        ),
        "opening_reserve_basis_points": policy.opening_reserve_basis_points,
        "assignment_fee_cents": policy.assignment_fee_cents,
        "closing_title_reserve_cents": policy.closing_title_reserve_cents,
        "curative_reserve_cents": policy.curative_reserve_cents,
        "uncertainty_reserve_cents": policy.uncertainty_reserve_cents,
        "maximum_dispersion_basis_points": policy.maximum_dispersion_basis_points,
        "minimum_comparable_count": policy.minimum_comparable_count,
        "approved_by_user_id": (
            str(policy.approved_by_user_id) if policy.approved_by_user_id else None
        ),
        "approved_at": policy.approved_at.isoformat() if policy.approved_at else None,
    }


def land_offer_policy_to_read(policy: LandOfferPolicyVersion) -> LandOfferPolicyRead:
    return LandOfferPolicyRead(
        id=policy.id,
        version_number=policy.version_number,
        status=policy.status,  # type: ignore[arg-type]
        title=policy.title,
        quick_sale_discount_low_basis_points=policy.quick_sale_discount_low_basis_points,
        quick_sale_discount_high_basis_points=policy.quick_sale_discount_high_basis_points,
        opening_reserve_basis_points=policy.opening_reserve_basis_points,
        assignment_fee_cents=policy.assignment_fee_cents,
        closing_title_reserve_cents=policy.closing_title_reserve_cents,
        curative_reserve_cents=policy.curative_reserve_cents,
        uncertainty_reserve_cents=policy.uncertainty_reserve_cents,
        maximum_dispersion_basis_points=policy.maximum_dispersion_basis_points,
        minimum_comparable_count=policy.minimum_comparable_count,
        notes=policy.notes,
        approved_by_user_id=policy.approved_by_user_id,
        approved_at=policy.approved_at,
        created_at=policy.created_at,
    )


def land_valuation_to_read(analysis: LandValuationAnalysis) -> LandValuationRead:
    return LandValuationRead(
        id=analysis.id,
        lead_id=analysis.lead_id,
        property_id=analysis.property_id,
        property_snapshot_id=analysis.property_snapshot_id,
        source_analysis_id=analysis.source_analysis_id,
        policy_version_id=analysis.policy_version_id,
        version_number=analysis.version_number,
        valuation_profile="land_v1",
        methodology_version=analysis.methodology_version,
        status=analysis.status,  # type: ignore[arg-type]
        guidance_status=analysis.guidance_status,  # type: ignore[arg-type]
        valuation_basis=analysis.valuation_basis,  # type: ignore[arg-type]
        access_evidence_status=analysis.access_evidence_status,  # type: ignore[arg-type]
        subject_acres=analysis.subject_acres_ten_thousandths / 10_000,
        subject_lot_count=analysis.subject_lot_count,
        supported_value_low_cents=analysis.supported_value_low_cents,
        supported_value_cents=analysis.supported_value_cents,
        supported_value_high_cents=analysis.supported_value_high_cents,
        quick_sale_low_cents=analysis.quick_sale_low_cents,
        quick_sale_high_cents=analysis.quick_sale_high_cents,
        opening_offer_cents=analysis.opening_offer_cents,
        seller_contract_ceiling_cents=analysis.seller_contract_ceiling_cents,
        assignment_fee_cents=analysis.assignment_fee_cents,
        closing_title_reserve_cents=analysis.closing_title_reserve_cents,
        curative_reserve_cents=analysis.curative_reserve_cents,
        uncertainty_reserve_cents=analysis.uncertainty_reserve_cents,
        confidence_score=analysis.confidence_score,
        selected_comps=[
            LandComparableRead.model_validate(item) for item in analysis.selected_comps
        ],
        rejected_comps=[
            LandComparableRead.model_validate(item) for item in analysis.rejected_comps
        ],
        subject_snapshot=analysis.subject_snapshot,
        search_snapshot=analysis.search_snapshot,
        assumptions=analysis.assumptions,
        review_reasons=list(analysis.review_reasons),
        guidance_blockers=list(analysis.guidance_blockers),
        policy_snapshot=analysis.policy_snapshot,
        created_at=analysis.created_at,
    )


def current_land_valuation_to_read(
    db: Session,
    lead: Lead,
    analysis: LandValuationAnalysis,
) -> LandValuationRead:
    value = land_valuation_to_read(analysis)
    property_record = db.get(Property, lead.property_id)
    snapshot = (
        current_property_snapshot(
            db,
            organization_id=lead.organization_id,
            property_id=property_record.id,
            research_profile=LAND_RESEARCH_PROFILE,
        )
        if property_record is not None
        else None
    )
    current_signature = (
        property_research_signature(
            property_record,
            research_profile=LAND_RESEARCH_PROFILE,
        )
        if property_record is not None
        else None
    )
    current_state_reasons = current_land_analysis_reasons(
        analysis,
        property_record=property_record,
        current_snapshot=snapshot,
        current_identity_signature=current_signature,
        active_policy_id=active_land_offer_policy_id(db, lead.organization_id),
    )
    if not current_state_reasons:
        return value.model_copy(update={"is_current": True})
    return value.model_copy(
        update={
            "is_current": False,
            "status": (
                "insufficient_evidence"
                if value.status == "insufficient_evidence"
                else "needs_review"
            ),
            "guidance_status": "withheld",
            "quick_sale_low_cents": None,
            "quick_sale_high_cents": None,
            "opening_offer_cents": None,
            "seller_contract_ceiling_cents": None,
            "review_reasons": list(
                dict.fromkeys([*value.review_reasons, *current_state_reasons])
            ),
            "guidance_blockers": list(
                dict.fromkeys([*value.guidance_blockers, *current_state_reasons])
            ),
        }
    )


def analysis_fingerprint(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def clean_idempotency_key(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    return cleaned or None


def decimal_acres_to_ten_thousandths(value: Decimal) -> int:
    return int((value * 10_000).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def optional_int(value: Any) -> int | None:
    return int(value) if value is not None else None


def require_permission(principal: Principal, permission: str) -> None:
    if permission not in principal.permission_keys:
        raise PermissionError("You do not have permission to manage Land underwriting.")
