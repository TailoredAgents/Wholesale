from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session

from app.core.auth import Principal, principal_for_user
from app.core.config import Settings, get_settings
from app.domain.rbac import PermissionKeys
from app.integrations.dealmachine_client import (
    get_dealmachine_image,
    is_dealmachine_image_url,
)
from app.integrations.google_street_view import (
    GoogleStreetViewClient,
    GoogleStreetViewError,
)
from app.models.foundation import (
    ActivityEvent,
    FieldInspection,
    FieldInspectionPhoto,
    Lead,
    Property,
    PropertyIntelligenceSnapshot,
    PropertyResearchRun,
    UnderwritingMarketAnalysis,
    User,
)
from app.schemas.leads import LeadMarketAnalysisCreate, PropertyIntelligenceRead
from app.services.document_storage import read_content
from app.services.property_validation import canonical_address_key, normalize_postal_code

ACTIVE_RESEARCH_STATUSES = {"queued", "processing", "retry"}
PROPERTY_IMAGE_VIEWS = ("street_view", "satellite", "roadmap")


@dataclass(frozen=True)
class PropertyImageContent:
    content: bytes
    content_type: str
    source: str


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def property_address_signature(property_record: Property) -> str:
    return canonical_address_key(
        property_record.street_address,
        property_record.city,
        property_record.state,
        property_record.postal_code,
    )


def usable_research_address(property_record: Property) -> bool:
    street = property_record.street_address.strip().lower()
    city = property_record.city.strip().lower()
    return bool(
        street
        and city
        and city != "unknown"
        and not street.startswith("address pending")
        and any(character.isdigit() for character in street)
    )


def current_property_snapshot(
    db: Session,
    *,
    organization_id: UUID,
    property_id: UUID,
) -> PropertyIntelligenceSnapshot | None:
    return db.scalar(
        select(PropertyIntelligenceSnapshot)
        .where(
            PropertyIntelligenceSnapshot.organization_id == organization_id,
            PropertyIntelligenceSnapshot.property_id == property_id,
            PropertyIntelligenceSnapshot.is_current.is_(True),
        )
        .order_by(
            PropertyIntelligenceSnapshot.version_number.desc(),
            PropertyIntelligenceSnapshot.created_at.desc(),
        )
    )


def enqueue_property_research(
    db: Session,
    property_record: Property,
    *,
    source_lead_id: UUID | None,
    trigger_source: str,
    force_refresh: bool = False,
    settings: Settings | None = None,
) -> PropertyResearchRun | None:
    active_settings = settings or get_settings()
    if not active_settings.property_intelligence_auto_research_enabled and not force_refresh:
        return None
    if not usable_research_address(property_record):
        property_record.research_status = "needs_address"
        property_record.research_last_error = "A complete street address and city are required."
        return None
    signature = property_address_signature(property_record)
    now = datetime.now(UTC)
    snapshot = current_property_snapshot(
        db,
        organization_id=property_record.organization_id,
        property_id=property_record.id,
    )
    if (
        not force_refresh
        and snapshot is not None
        and snapshot.address_signature == signature
        and as_utc(snapshot.expires_at) > now
    ):
        property_record.research_status = snapshot.status
        property_record.research_completed_at = snapshot.captured_at
        property_record.research_last_error = None
        return None
    active = db.scalar(
        select(PropertyResearchRun).where(
            PropertyResearchRun.organization_id == property_record.organization_id,
            PropertyResearchRun.property_id == property_record.id,
            PropertyResearchRun.address_signature == signature,
            PropertyResearchRun.status.in_(ACTIVE_RESEARCH_STATUSES),
        )
    )
    if active is not None:
        return active
    next_version = (
        int(
            db.scalar(
                select(
                    func.coalesce(func.max(PropertyIntelligenceSnapshot.version_number), 0)
                ).where(PropertyIntelligenceSnapshot.property_id == property_record.id)
            )
            or 0
        )
        + 1
    )
    mode = "refresh" if force_refresh else "automatic"
    run = PropertyResearchRun(
        organization_id=property_record.organization_id,
        property_id=property_record.id,
        source_lead_id=source_lead_id,
        idempotency_key=f"property-research:{property_record.id}:{signature}:v{next_version}:{mode}",
        trigger_source=trigger_source[:120],
        address_signature=signature,
        status="queued",
        force_refresh=force_refresh,
        attempt_count=0,
        run_metadata={"requested_at": now.isoformat(), "mode": mode},
    )
    db.add(run)
    property_record.research_status = "queued"
    property_record.research_requested_at = now
    property_record.research_last_error = None
    db.flush()
    return run


def invalidate_property_intelligence(db: Session, property_record: Property) -> None:
    db.execute(
        update(PropertyIntelligenceSnapshot)
        .where(
            PropertyIntelligenceSnapshot.organization_id == property_record.organization_id,
            PropertyIntelligenceSnapshot.property_id == property_record.id,
            PropertyIntelligenceSnapshot.is_current.is_(True),
        )
        .values(is_current=False)
    )
    property_record.research_status = "not_started"
    property_record.research_completed_at = None
    property_record.research_last_error = None


def process_next_property_research(db: Session, settings: Settings) -> UUID | None:
    now = datetime.now(UTC)
    stale_before = now - timedelta(minutes=15)
    run = db.scalar(
        select(PropertyResearchRun)
        .where(
            or_(
                PropertyResearchRun.status == "queued",
                and_(
                    PropertyResearchRun.status == "retry",
                    or_(
                        PropertyResearchRun.next_attempt_at.is_(None),
                        PropertyResearchRun.next_attempt_at <= now,
                    ),
                ),
                and_(
                    PropertyResearchRun.status == "processing",
                    PropertyResearchRun.started_at <= stale_before,
                ),
            )
        )
        .order_by(PropertyResearchRun.created_at.asc())
        .with_for_update(skip_locked=True)
    )
    if run is None:
        return None
    run.status = "processing"
    run.attempt_count += 1
    run.started_at = now
    run.next_attempt_at = None
    run.last_error = None
    property_record = db.get(Property, run.property_id)
    if property_record is not None:
        property_record.research_status = "processing"
        property_record.research_last_error = None
    db.commit()
    run_id = run.id

    try:
        run = db.get(PropertyResearchRun, run_id)
        if run is None:
            return run_id
        property_record = db.get(Property, run.property_id)
        if property_record is None:
            return finish_research_needs_review(db, run, "The property record no longer exists.")
        if property_address_signature(property_record) != run.address_signature:
            return finish_research_needs_review(
                db,
                run,
                "The property address changed while research was queued. Request a new refresh.",
            )
        existing_snapshot = current_property_snapshot(
            db,
            organization_id=run.organization_id,
            property_id=run.property_id,
        )
        if (
            not run.force_refresh
            and existing_snapshot is not None
            and existing_snapshot.address_signature == run.address_signature
            and as_utc(existing_snapshot.expires_at) > datetime.now(UTC)
        ):
            run.status = existing_snapshot.status
            run.completed_at = datetime.now(UTC)
            run.run_metadata = {
                **(run.run_metadata or {}),
                "snapshot_id": str(existing_snapshot.id),
                "completed_at": run.completed_at.isoformat(),
                "fresh_snapshot_reused": True,
            }
            property_record.research_status = existing_snapshot.status
            property_record.research_completed_at = existing_snapshot.captured_at
            property_record.research_last_error = None
            db.commit()
            return run_id
        if not usable_research_address(property_record):
            return finish_research_needs_review(
                db, run, "A complete street address and city are required."
            )
        lead = research_lead(db, run)
        if lead is None:
            return finish_research_needs_review(
                db, run, "No active lead is available to host the valuation evidence."
            )
        user = research_owner(db, lead)
        if user is None:
            return finish_research_needs_review(
                db, run, "No active Stonegate user can own this research run."
            )
        principal = principal_for_user(db, user)
        from app.services.leads import create_lead_market_analysis

        analysis_read = create_lead_market_analysis(
            db,
            principal,
            lead.id,
            LeadMarketAnalysisCreate(
                refresh_market_data=run.force_refresh,
                research_only=True,
                input_verification_status="preliminary",
            ),
        )
        if analysis_read is None:
            raise ValueError("The property valuation result was not created.")
        analysis = db.get(UnderwritingMarketAnalysis, analysis_read.id)
        if analysis is None:
            raise ValueError("The saved property valuation evidence could not be loaded.")
        snapshot = create_snapshot_from_analysis(
            db,
            settings,
            property_record=property_record,
            lead=lead,
            analysis=analysis,
            include_street_view=True,
            trigger_source=run.trigger_source,
        )
        run = db.get(PropertyResearchRun, run_id)
        if run is not None:
            run.status = snapshot.status
            run.completed_at = datetime.now(UTC)
            run.last_error = None
            run.run_metadata = {
                **(run.run_metadata or {}),
                "snapshot_id": str(snapshot.id),
                "market_analysis_id": str(analysis.id),
                "completed_at": run.completed_at.isoformat(),
            }
        property_record.research_status = snapshot.status
        property_record.research_completed_at = snapshot.captured_at
        property_record.research_last_error = None
        db.add(
            ActivityEvent(
                organization_id=lead.organization_id,
                actor_user_id=None,
                entity_type="lead",
                entity_id=lead.id,
                event_type="property.research_ready",
                summary=(
                    "Property research is ready with saved facts, comparable evidence, "
                    "and valuation context."
                ),
            )
        )
        from app.services.ai_operations import enqueue_property_research_ai_work

        enqueue_property_research_ai_work(db, lead=lead, snapshot_id=snapshot.id)
        db.commit()
        return run_id
    except Exception as exc:
        db.rollback()
        return mark_research_failure(db, run_id, settings, str(exc))


def research_lead(db: Session, run: PropertyResearchRun) -> Lead | None:
    if run.source_lead_id is not None:
        lead = db.get(Lead, run.source_lead_id)
        if lead is not None and lead.archived_at is None and lead.property_id == run.property_id:
            return lead
    return db.scalar(
        select(Lead)
        .where(
            Lead.organization_id == run.organization_id,
            Lead.property_id == run.property_id,
            Lead.archived_at.is_(None),
        )
        .order_by(Lead.created_at.desc())
    )


def research_owner(db: Session, lead: Lead) -> User | None:
    if lead.assigned_user_id is not None:
        assigned = db.get(User, lead.assigned_user_id)
        if assigned is not None and assigned.is_active:
            return assigned
    from app.services.ai_operations import default_ai_work_owner

    fallback_id = default_ai_work_owner(db, lead.organization_id)
    fallback = db.get(User, fallback_id) if fallback_id else None
    return fallback if fallback is not None and fallback.is_active else None


def create_snapshot_from_analysis(
    db: Session,
    settings: Settings,
    *,
    property_record: Property,
    lead: Lead,
    analysis: UnderwritingMarketAnalysis,
    include_street_view: bool,
    trigger_source: str,
) -> PropertyIntelligenceSnapshot:
    captured_at = datetime.now(UTC)
    metadata = analysis.analysis_metadata or {}
    assumptions = metadata.get("assumptions")
    assumption_values = assumptions if isinstance(assumptions, dict) else {}
    provenance = assumption_values.get("subject_fact_provenance")
    provenance_values = provenance if isinstance(provenance, dict) else {}
    subject = analysis.subject_property or {}
    facts = normalized_fact_snapshot(subject, provenance_values, captured_at)
    dealmachine_subject = dealmachine_subject_property(analysis)
    dealmachine_conflicts = merge_dealmachine_property_facts(
        facts,
        dealmachine_subject,
        captured_at,
    )
    facts["address"] = {
        "value": analysis.requested_address,
        "source": property_record.address_validation_provider or "stonegate_crm",
        "observed_at": captured_at.isoformat(),
    }
    if property_record.county and "county" not in facts:
        facts["county"] = fact_value(
            property_record.county,
            property_record.address_validation_provider or "stonegate_crm",
            captured_at,
        )
    media = (
        property_media_snapshot(
            settings,
            property_record,
            subject,
            dealmachine_subject,
        )
        if include_street_view
        else dealmachine_media_snapshot(dealmachine_subject)
    )
    selected = [item for item in analysis.selected_comps if isinstance(item, dict)]
    rejected = [item for item in analysis.rejected_comps if isinstance(item, dict)]
    conflicts = [
        *property_conflicts(metadata, selected, rejected),
        *dealmachine_conflicts,
    ][:100]
    valuation = {
        "estimated_value_cents": analysis.estimated_value_cents,
        "estimated_value_low_cents": analysis.estimated_value_low_cents,
        "estimated_value_high_cents": analysis.estimated_value_high_cents,
        "as_is_value_low_cents": metadata.get("as_is_value_low_cents"),
        "as_is_value_cents": metadata.get("as_is_value_cents"),
        "as_is_value_high_cents": metadata.get("as_is_value_high_cents"),
        "arv_low_cents": analysis.arv_low_cents,
        "arv_point_cents": metadata.get("arv_point_cents"),
        "arv_high_cents": analysis.arv_high_cents,
        "confidence_tier": metadata.get("confidence_tier"),
        "report_stage": metadata.get("report_stage"),
        "source_note": (
            "Stonegate comp math uses saved closed-sale evidence; provider AVMs are "
            "benchmarks only."
        ),
    }
    market_context = {
        "supporting_evidence": metadata.get("supporting_evidence"),
        "secondary_evidence": metadata.get("secondary_evidence"),
        "comp_search_summary": metadata.get("comp_search_summary"),
        "comp_intelligence": metadata.get("comp_intelligence"),
        "market_data_captured_at": metadata.get("market_data_captured_at"),
        "manual_review_required": metadata.get("human_review_required") is True,
        "review_reasons": metadata.get("review_reasons") or [],
    }
    source_names = {analysis.provider, "stonegate"}
    if dealmachine_subject:
        source_names.add("dealmachine")
    comp_intelligence = metadata.get("comp_intelligence")
    if isinstance(comp_intelligence, dict):
        provider_values = comp_intelligence.get("providers")
        if isinstance(provider_values, list):
            for provider in provider_values:
                if isinstance(provider, dict) and isinstance(provider.get("provider"), str):
                    source_names.add(provider["provider"])
    if isinstance(metadata.get("secondary_evidence"), dict):
        secondary_sources = metadata["secondary_evidence"].get("sources")
        if isinstance(secondary_sources, list) and secondary_sources:
            source_names.add("cited_public_research")
    sources = [
        {
            "source": name,
            "captured_at": captured_at.isoformat(),
            "role": source_role(name),
        }
        for name in sorted(source_names)
    ]
    completeness_score = property_completeness_score(facts, valuation, selected, media)
    status = "ready" if completeness_score >= 65 and analysis.confidence_score >= 35 else "partial"
    db.execute(
        update(PropertyIntelligenceSnapshot)
        .where(
            PropertyIntelligenceSnapshot.organization_id == property_record.organization_id,
            PropertyIntelligenceSnapshot.property_id == property_record.id,
            PropertyIntelligenceSnapshot.is_current.is_(True),
        )
        .values(is_current=False)
    )
    version_number = (
        int(
            db.scalar(
                select(
                    func.coalesce(func.max(PropertyIntelligenceSnapshot.version_number), 0)
                ).where(PropertyIntelligenceSnapshot.property_id == property_record.id)
            )
            or 0
        )
        + 1
    )
    snapshot = PropertyIntelligenceSnapshot(
        organization_id=property_record.organization_id,
        property_id=property_record.id,
        source_lead_id=lead.id,
        source_market_analysis_id=analysis.id,
        version_number=version_number,
        status=status,
        is_current=True,
        address_signature=property_address_signature(property_record),
        completeness_score=completeness_score,
        confidence_score=max(0, min(100, analysis.confidence_score)),
        facts=facts,
        valuation=valuation,
        comparables=selected,
        market_context=market_context,
        sources=sources,
        conflicts=conflicts,
        media=media,
        snapshot_metadata={
            "trigger_source": trigger_source,
            "rejected_comparable_count": len(rejected),
            "methodology_version": metadata.get("methodology_version"),
            "market_data_reused": metadata.get("market_data_reused") is True,
        },
        captured_at=captured_at,
        expires_at=captured_at + timedelta(days=settings.property_intelligence_fresh_days),
    )
    db.add(snapshot)
    db.flush()
    return snapshot


def normalized_fact_snapshot(
    subject: dict[str, Any], provenance: dict[str, Any], captured_at: datetime
) -> dict[str, Any]:
    mappings = {
        "property_type": "propertyType",
        "bedrooms": "bedrooms",
        "bathrooms": "bathrooms",
        "square_footage": "squareFootage",
        "lot_size": "lotSize",
        "year_built": "yearBuilt",
        "subdivision": "subdivision",
        "county": "county",
        "parcel_id": "id",
        "latitude": "latitude",
        "longitude": "longitude",
        "last_sale_date": "lastSaleDate",
        "last_sale_price": "lastSalePrice",
        "property_taxes": "propertyTaxes",
        "features": "features",
    }
    return {
        target: fact_value(
            subject[source],
            str(provenance.get(source) or "rentcast_property_record"),
            captured_at,
        )
        for target, source in mappings.items()
        if subject.get(source) is not None
    }


DEALMACHINE_PROPERTY_FACTS: dict[str, tuple[str, str | None]] = {
    "estimated_value": ("dealmachine_estimated_value", "dollars"),
    "estimated_equity_amount": ("estimated_equity_amount", "dollars"),
    "estimated_equity_percentage": ("estimated_equity_percentage", "percent"),
    "num_bedrooms": ("bedrooms", "count"),
    "num_bathrooms": ("bathrooms", "count"),
    "living_area_sqft": ("square_footage", "square_feet"),
    "year_built": ("year_built", None),
    "num_units": ("unit_count", "count"),
    "num_buildings": ("building_count", "count"),
    "building_style": ("building_style", None),
    "stories": ("stories", None),
    "property_construction_type": ("construction_type", None),
    "property_type": ("property_type", None),
    "property_class": ("property_class", None),
    "school_district_name": ("school_district", None),
    "num_mortgages": ("mortgage_count", "count"),
    "estimated_loan_to_value_percentage": ("estimated_loan_to_value", "percent"),
    "total_estimated_loan_balance": ("estimated_loan_balance", "dollars"),
    "mortgage_1_loan_balance": ("first_mortgage_balance", "dollars"),
    "mortgage_1_loan_interest_rate": ("first_mortgage_rate", "percent"),
    "mortgage_1_loan_type": ("first_mortgage_type", None),
    "mortgage_1_loan_due_date": ("first_mortgage_due_date", None),
    "mortgage_1_loan_recording_date": ("first_mortgage_recording_date", None),
    "market_status": ("market_status", None),
    "mls_current_listing_price": ("current_listing_price", "dollars"),
    "mls_days_on_market": ("days_on_market", "days"),
    "mls_last_initial_listing_date": ("initial_listing_date", None),
    "last_sale_date": ("last_sale_date", None),
    "last_sale_price": ("last_sale_price", "dollars"),
    "last_sale_doc_type": ("last_sale_document_type", None),
    "tax_amount": ("annual_property_tax", "dollars"),
    "tax_delinquent_year": ("tax_delinquent_year", None),
    "tax_year": ("tax_year", None),
    "assessed_total_value": ("assessed_total_value", "dollars"),
    "assessed_improvement_value": ("assessed_improvement_value", "dollars"),
    "assessed_land_value": ("assessed_land_value", "dollars"),
    "tax_assessment_year": ("tax_assessment_year", None),
    "num_total_active_liens": ("active_lien_count", "count"),
    "num_total_open_liens": ("open_lien_count", "count"),
    "hoa_1_fee_amount": ("hoa_fee", "dollars"),
    "lot_size_acres": ("lot_size_acres", "acres"),
    "lot_size_frontage_feet": ("lot_frontage", "feet"),
    "lot_size_depth_feet": ("lot_depth", "feet"),
    "zoning": ("zoning", None),
    "parcel_number_raw": ("parcel_id", None),
    "legal_description": ("legal_description", None),
    "lot_number": ("lot_number", None),
    "municipality_name": ("municipality", None),
    "subdivision_name": ("subdivision", None),
    "pool": ("pool", None),
    "garage_type": ("garage_type", None),
    "basement": ("basement", None),
    "patio": ("patio", None),
    "porch": ("porch", None),
    "driveway": ("driveway", None),
    "air_conditioning": ("air_conditioning", None),
    "heating_type": ("heating_type", None),
    "heating_fuel": ("heating_fuel", None),
    "sewer": ("sewer", None),
    "water": ("water", None),
    "has_fireplaces": ("has_fireplaces", None),
    "exterior_walls": ("exterior_walls", None),
    "roof_type": ("roof_type", None),
    "roof_cover": ("roof_cover", None),
    "floor_cover": ("floor_cover", None),
    "building_condition": ("building_condition", None),
    "building_quality": ("building_quality", None),
    "flood_zone": ("flood_zone", None),
}


def dealmachine_subject_property(analysis: UnderwritingMarketAnalysis) -> dict[str, Any]:
    raw_response = analysis.raw_response if isinstance(analysis.raw_response, dict) else {}
    provider_payload = raw_response.get("dealmachine")
    if not isinstance(provider_payload, dict):
        return {}
    lookup = provider_payload.get("lookup")
    if not isinstance(lookup, dict):
        return {}
    property_payload = lookup.get("property")
    return property_payload if isinstance(property_payload, dict) else {}


def merge_dealmachine_property_facts(
    facts: dict[str, Any],
    property_payload: dict[str, Any],
    captured_at: datetime,
) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    conflict_targets = {
        "bedrooms",
        "bathrooms",
        "square_footage",
        "year_built",
        "property_type",
        "last_sale_date",
        "last_sale_price",
    }
    for provider_key, (fact_key, unit) in DEALMACHINE_PROPERTY_FACTS.items():
        value = property_payload.get(provider_key)
        if value is None:
            continue
        existing = facts.get(fact_key)
        if existing is None:
            facts[fact_key] = fact_value(
                value,
                "dealmachine_property_record",
                captured_at,
                unit=unit,
            )
            continue
        existing_value = existing.get("value") if isinstance(existing, dict) else None
        if fact_key in conflict_targets and comparable_fact_value(existing_value) != (
            comparable_fact_value(value)
        ):
            conflicts.append(
                {
                    "scope": "property",
                    "field": fact_key,
                    "severity": "review",
                    "message": (
                        f"RentCast and DealMachine disagree on {fact_key.replace('_', ' ')}."
                    ),
                    "observations": [
                        {
                            "source": (
                                str(existing.get("source"))
                                if isinstance(existing, dict)
                                else "primary_property_record"
                            ),
                            "value": existing_value,
                        },
                        {"source": "dealmachine_property_record", "value": value},
                    ],
                }
            )
    return conflicts


def comparable_fact_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.3f}"
    if isinstance(value, list):
        return "|".join(sorted(str(item).strip().lower() for item in value))
    return str(value).strip().lower()


def fact_value(
    value: Any,
    source: str,
    observed_at: datetime,
    *,
    unit: str | None = None,
) -> dict[str, Any]:
    result = {"value": value, "source": source, "observed_at": observed_at.isoformat()}
    if unit:
        result["unit"] = unit
    return result


def property_conflicts(
    metadata: dict[str, Any],
    selected: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    for message in metadata.get("data_disagreements") or []:
        conflicts.append({"scope": "property", "message": str(message), "severity": "review"})
    for comp in [*selected, *rejected]:
        raw_conflicts = comp.get("field_conflicts")
        if not isinstance(raw_conflicts, list):
            continue
        for conflict in raw_conflicts:
            if isinstance(conflict, dict):
                conflicts.append(
                    {
                        "scope": "comparable",
                        "address": comp.get("formatted_address"),
                        **conflict,
                    }
                )
    return conflicts[:100]


def property_media_snapshot(
    settings: Settings,
    property_record: Property,
    subject: dict[str, Any],
    dealmachine_subject: dict[str, Any],
) -> dict[str, Any]:
    dealmachine = dealmachine_media_snapshot(dealmachine_subject)
    provider_media = dealmachine.get("dealmachine")
    if isinstance(provider_media, dict) and provider_media.get("status") == "available":
        return dealmachine
    return {
        **dealmachine,
        **google_street_view_snapshot(settings, property_record, subject),
    }


def dealmachine_media_snapshot(property_payload: dict[str, Any]) -> dict[str, Any]:
    raw_images = property_payload.get("images")
    images = raw_images if isinstance(raw_images, dict) else {}
    views = {
        view: image_url
        for view in PROPERTY_IMAGE_VIEWS
        if (image_url := string_value(images.get(view))) and is_dealmachine_image_url(image_url)
    }
    return {
        "dealmachine": {
            "status": "available" if views else "unavailable",
            "views": views,
            "attribution": "DealMachine property imagery",
            "credit_cost": "no_additional_image_credit",
        }
    }


def google_street_view_snapshot(
    settings: Settings,
    property_record: Property,
    subject: dict[str, Any],
) -> dict[str, Any]:
    if not settings.google_street_view_api_key:
        return {"street_view": {"status": "not_configured"}}
    latitude = number_value(subject.get("latitude"))
    longitude = number_value(subject.get("longitude"))
    location = (
        f"{latitude},{longitude}"
        if latitude is not None and longitude is not None
        else format_property_address(property_record)
    )
    try:
        metadata = GoogleStreetViewClient(
            api_key=settings.google_street_view_api_key,
            base_url=settings.google_street_view_base_url,
        ).get_metadata(location=location)
    except GoogleStreetViewError as exc:
        return {"street_view": {"status": "error", "error": str(exc)}}
    return {
        "street_view": {
            "status": "available" if metadata.available and metadata.panorama_id else "unavailable",
            "panorama_id": metadata.panorama_id,
            "imagery_date": metadata.imagery_date,
            "latitude": metadata.latitude,
            "longitude": metadata.longitude,
            "copyright": metadata.copyright,
            "attribution": "Google Street View",
        }
    }


def property_completeness_score(
    facts: dict[str, Any],
    valuation: dict[str, Any],
    comparables: list[dict[str, Any]],
    media: dict[str, Any],
) -> int:
    required_facts = {
        "address",
        "property_type",
        "bedrooms",
        "bathrooms",
        "square_footage",
        "lot_size",
        "year_built",
        "latitude",
        "longitude",
        "last_sale_date",
    }
    fact_points = round(55 * len(required_facts.intersection(facts)) / len(required_facts))
    valuation_points = (
        20
        if valuation.get("arv_point_cents")
        else 10
        if valuation.get("estimated_value_cents")
        else 0
    )
    comp_points = min(20, len(comparables) * 7)
    dealmachine = media.get("dealmachine")
    dealmachine_views = dealmachine.get("views") if isinstance(dealmachine, dict) else None
    street_view = media.get("street_view")
    image_points = (
        5
        if (
            isinstance(dealmachine_views, dict)
            and bool(dealmachine_views)
            or isinstance(street_view, dict)
            and street_view.get("status") == "available"
        )
        else 0
    )
    return min(100, fact_points + valuation_points + comp_points + image_points)


def source_role(name: str) -> str:
    return {
        "rentcast": "canonical_property_and_market_evidence",
        "dealmachine": "candidate_comparable_evidence",
        "cited_public_research": "supplemental_review_only",
        "stonegate": "crm_and_calculation_record",
    }.get(name, "supporting_evidence")


def build_property_intelligence_read(
    db: Session,
    principal: Principal,
    lead: Lead,
) -> PropertyIntelligenceRead:
    property_record = db.get(Property, lead.property_id)
    if property_record is None:
        return PropertyIntelligenceRead(research_status="unavailable")
    snapshot = current_property_snapshot(
        db,
        organization_id=principal.organization_id,
        property_id=property_record.id,
    )
    if snapshot is not None and snapshot.address_signature != property_address_signature(
        property_record
    ):
        snapshot = None
    image_source = "placeholder"
    image_available = False
    image_views: list[str] = []
    image_attribution = None
    imagery_date = None
    photo = latest_property_photo(db, principal.organization_id, property_record.id)
    dealmachine_views: dict[str, Any] = {}
    street_view: dict[str, Any] = {}
    if snapshot is not None:
        dealmachine = snapshot.media.get("dealmachine")
        raw_views = dealmachine.get("views") if isinstance(dealmachine, dict) else None
        if isinstance(raw_views, dict):
            dealmachine_views = raw_views
        raw_street_view = snapshot.media.get("street_view")
        if isinstance(raw_street_view, dict):
            street_view = raw_street_view
    provider_views = [
        view
        for view in ("street_view", "satellite", "roadmap")
        if string_value(dealmachine_views.get(view))
    ]
    if photo is not None:
        image_source = "inspection_photo"
        image_available = True
        image_views = ["street_view", *[view for view in provider_views if view != "street_view"]]
        image_attribution = "Stonegate field inspection"
        imagery_date = (photo.captured_at or photo.created_at).date().isoformat()
    elif provider_views:
        image_source = "dealmachine"
        image_available = True
        image_views = provider_views
        image_attribution = "DealMachine property imagery"
    elif street_view.get("status") == "available":
        image_source = "google_street_view"
        image_available = True
        image_views = ["street_view"]
        image_attribution = str(street_view.get("attribution") or "Google Street View")
        imagery_date = string_value(street_view.get("imagery_date"))
    return PropertyIntelligenceRead(
        research_status=property_record.research_status,
        snapshot_id=snapshot.id if snapshot else None,
        version_number=snapshot.version_number if snapshot else None,
        snapshot_status=snapshot.status if snapshot else None,
        completeness_score=snapshot.completeness_score if snapshot else 0,
        confidence_score=snapshot.confidence_score if snapshot else 0,
        captured_at=as_utc(snapshot.captured_at) if snapshot else None,
        expires_at=as_utc(snapshot.expires_at) if snapshot else None,
        is_stale=bool(snapshot and as_utc(snapshot.expires_at) <= datetime.now(UTC)),
        facts=snapshot.facts if snapshot else fallback_property_facts(property_record),
        valuation=snapshot.valuation if snapshot else {},
        comparables=snapshot.comparables if snapshot else [],
        market_context=snapshot.market_context if snapshot else {},
        sources=snapshot.sources if snapshot else [],
        conflicts=snapshot.conflicts if snapshot else [],
        image_source=image_source,
        image_available=image_available,
        image_views=image_views,
        image_url=f"/api/v1/leads/{lead.id}/property-image" if image_available else None,
        image_attribution=image_attribution,
        imagery_date=imagery_date,
        last_error=property_record.research_last_error,
    )


def request_property_research(
    db: Session,
    principal: Principal,
    lead_id: UUID,
) -> PropertyIntelligenceRead | None:
    lead = db.scalar(
        select(Lead).where(
            Lead.organization_id == principal.organization_id,
            Lead.id == lead_id,
            Lead.archived_at.is_(None),
        )
    )
    if lead is None:
        return None
    if (
        PermissionKeys.VIEW_LEADS not in principal.permission_keys
        and PermissionKeys.EDIT_LEADS not in principal.permission_keys
        and lead.assigned_user_id != principal.user_id
    ):
        return None
    property_record = db.get(Property, lead.property_id)
    if property_record is None:
        raise ValueError("Lead is missing its property record.")
    enqueue_property_research(
        db,
        property_record,
        source_lead_id=lead.id,
        trigger_source="manual_property_refresh",
        force_refresh=True,
    )
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            event_type="property.research_requested",
            summary="Property research refresh requested; provider calls or credits may be used.",
        )
    )
    db.commit()
    return build_property_intelligence_read(db, principal, lead)


def fallback_property_facts(property_record: Property) -> dict[str, Any]:
    now = property_record.updated_at
    facts = {
        "address": fact_value(format_property_address(property_record), "stonegate_crm", now),
    }
    if property_record.property_type:
        facts["property_type"] = fact_value(property_record.property_type, "stonegate_crm", now)
    if property_record.county:
        facts["county"] = fact_value(property_record.county, "stonegate_crm", now)
    metadata_facts = (property_record.address_validation_metadata or {}).get("facts")
    if isinstance(metadata_facts, dict):
        facts.update(normalized_fact_snapshot(metadata_facts, {}, now))
    return facts


def latest_property_photo(
    db: Session, organization_id: UUID, property_id: UUID
) -> FieldInspectionPhoto | None:
    return db.scalar(
        select(FieldInspectionPhoto)
        .join(FieldInspection, FieldInspection.id == FieldInspectionPhoto.inspection_id)
        .where(
            FieldInspectionPhoto.organization_id == organization_id,
            FieldInspection.property_id == property_id,
        )
        .order_by(
            FieldInspectionPhoto.captured_at.desc().nullslast(),
            FieldInspectionPhoto.created_at.desc(),
        )
    )


def get_property_image_content(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    settings: Settings,
    *,
    view: str = "street_view",
) -> PropertyImageContent | None:
    if view not in PROPERTY_IMAGE_VIEWS:
        raise ValueError("The requested property image view is unsupported.")
    lead = db.scalar(
        select(Lead).where(
            Lead.organization_id == principal.organization_id,
            Lead.id == lead_id,
        )
    )
    if lead is None:
        return None
    if (
        PermissionKeys.VIEW_LEADS not in principal.permission_keys
        and PermissionKeys.EDIT_LEADS not in principal.permission_keys
        and lead.assigned_user_id != principal.user_id
    ):
        return None
    photo = (
        latest_property_photo(db, principal.organization_id, lead.property_id)
        if view == "street_view"
        else None
    )
    if photo is not None and view == "street_view":
        return PropertyImageContent(
            content=read_content(
                provider=photo.storage_provider,
                key=photo.storage_key,
                database_bytes=photo.image_data,
            ),
            content_type=photo.content_type,
            source="inspection_photo",
        )
    snapshot = current_property_snapshot(
        db,
        organization_id=principal.organization_id,
        property_id=lead.property_id,
    )
    dealmachine = snapshot.media.get("dealmachine") if snapshot else None
    views = dealmachine.get("views") if isinstance(dealmachine, dict) else None
    image_url = string_value(views.get(view)) if isinstance(views, dict) else None
    if image_url and is_dealmachine_image_url(image_url):
        content, content_type = get_dealmachine_image(
            image_url,
            timeout_seconds=settings.dealmachine_request_timeout_seconds,
        )
        return PropertyImageContent(
            content=content,
            content_type=content_type,
            source=f"dealmachine_{view}",
        )
    if view != "street_view":
        return None
    street_view = snapshot.media.get("street_view") if snapshot else None
    if (
        not isinstance(street_view, dict)
        or street_view.get("status") != "available"
        or not settings.google_street_view_api_key
    ):
        return None
    panorama_id = string_value(street_view.get("panorama_id"))
    if not panorama_id:
        return None
    content, content_type = GoogleStreetViewClient(
        api_key=settings.google_street_view_api_key,
        base_url=settings.google_street_view_base_url,
    ).get_image(panorama_id=panorama_id)
    return PropertyImageContent(
        content=content, content_type=content_type, source="google_street_view"
    )


def finish_research_needs_review(db: Session, run: PropertyResearchRun, error: str) -> UUID:
    run.status = "needs_review"
    run.completed_at = datetime.now(UTC)
    run.last_error = error[:2000]
    property_record = db.get(Property, run.property_id)
    if property_record is not None:
        property_record.research_status = "needs_review"
        property_record.research_last_error = error[:2000]
    db.commit()
    return run.id


def mark_research_failure(
    db: Session,
    run_id: UUID,
    settings: Settings,
    error: str,
) -> UUID:
    run = db.get(PropertyResearchRun, run_id)
    if run is None:
        return run_id
    run.last_error = error[:2000]
    property_record = db.get(Property, run.property_id)
    if run.attempt_count >= settings.property_intelligence_max_attempts:
        run.status = "failed"
        run.completed_at = datetime.now(UTC)
        next_status = "failed"
    else:
        run.status = "retry"
        run.next_attempt_at = datetime.now(UTC) + timedelta(
            seconds=settings.property_intelligence_retry_base_seconds
            * (2 ** max(0, run.attempt_count - 1))
        )
        next_status = "queued"
    if property_record is not None:
        property_record.research_status = next_status
        property_record.research_last_error = error[:2000]
    db.commit()
    return run_id


def backfill_next_property_snapshot(db: Session, settings: Settings) -> UUID | None:
    analysis = db.scalar(
        select(UnderwritingMarketAnalysis)
        .join(Property, Property.id == UnderwritingMarketAnalysis.property_id)
        .outerjoin(
            PropertyIntelligenceSnapshot,
            and_(
                PropertyIntelligenceSnapshot.property_id == UnderwritingMarketAnalysis.property_id,
                PropertyIntelligenceSnapshot.is_current.is_(True),
            ),
        )
        .where(PropertyIntelligenceSnapshot.id.is_(None))
        .order_by(UnderwritingMarketAnalysis.created_at.desc())
        .with_for_update(skip_locked=True)
    )
    if analysis is None:
        return None
    property_record = db.get(Property, analysis.property_id)
    lead = db.get(Lead, analysis.lead_id)
    if property_record is None or lead is None:
        return None
    snapshot = create_snapshot_from_analysis(
        db,
        settings,
        property_record=property_record,
        lead=lead,
        analysis=analysis,
        include_street_view=False,
        trigger_source="existing_market_analysis_backfill",
    )
    property_record.research_status = snapshot.status
    property_record.research_completed_at = snapshot.captured_at
    property_record.research_last_error = None
    completed_at = datetime.now(UTC)
    for run in db.scalars(
        select(PropertyResearchRun).where(
            PropertyResearchRun.organization_id == property_record.organization_id,
            PropertyResearchRun.property_id == property_record.id,
            PropertyResearchRun.address_signature == snapshot.address_signature,
            PropertyResearchRun.force_refresh.is_(False),
            PropertyResearchRun.status.in_(ACTIVE_RESEARCH_STATUSES),
        )
    ):
        run.status = snapshot.status
        run.completed_at = completed_at
        run.last_error = None
        run.run_metadata = {
            **(run.run_metadata or {}),
            "snapshot_id": str(snapshot.id),
            "completed_at": completed_at.isoformat(),
            "existing_analysis_backfilled": True,
        }
    db.commit()
    return property_record.id


def format_property_address(property_record: Property) -> str:
    locality = " ".join(
        value
        for value in (
            property_record.state.strip().upper(),
            normalize_postal_code(property_record.postal_code),
        )
        if value
    )
    return ", ".join(
        value
        for value in (
            property_record.street_address.strip(),
            property_record.city.strip(),
            locality,
        )
        if value
    )


def string_value(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def number_value(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)
