from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import Select, and_, func, or_, select, update
from sqlalchemy.orm import Session

from app.core.auth import Principal, principal_for_user
from app.core.config import Settings, get_settings
from app.domain.assets import (
    HOUSE_RESEARCH_PROFILE,
    LAND_ASSET_CLASS,
    LAND_RESEARCH_PROFILE,
    normalize_parcel_id,
    parcel_identity_key,
    property_identity_label,
    research_profile_for_asset,
)
from app.domain.rbac import PermissionKeys
from app.integrations.realestateapi_client import (
    RealEstateAPIClient,
    RealEstateAPIError,
    get_realestateapi_image,
    is_realestateapi_image_url,
    realestateapi_primary_image_url,
)
from app.models.foundation import (
    ActivityEvent,
    FieldInspection,
    FieldInspectionPhoto,
    LandValuationAnalysis,
    Lead,
    Property,
    PropertyIntelligenceSnapshot,
    PropertyResearchRun,
    UnderwritingMarketAnalysis,
    User,
)
from app.schemas.leads import LeadMarketAnalysisCreate, PropertyIntelligenceRead
from app.services.document_storage import read_content
from app.services.land_valuation_state import (
    active_land_offer_policy_id,
    current_land_analysis_reasons,
)
from app.services.property_validation import canonical_address_key, normalize_postal_code
from app.services.underwriting_comparable_evidence import normalize_address_key

ACTIVE_RESEARCH_STATUSES = {"queued", "processing", "retry"}
PROPERTY_IMAGE_VIEWS = ("listing",)
LAND_WORKFLOW_DISABLED_MESSAGE = (
    "Land property research is disabled. Enable LAND_WORKFLOW_ENABLED to collect the "
    "land property record; residential comps and value math were not run."
)
LAND_VALUATION_PENDING_MESSAGE = (
    "Land property research is ready. Run Land Valuation when you want to search closed "
    "land sales and calculate evidence-backed guidance."
)
LAND_RESIDENTIAL_SKIP_MESSAGE = (
    "Land leads use the dedicated Land valuation workflow; residential ARV and repair "
    "math were intentionally skipped."
)


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


def property_research_signature(
    property_record: Property,
    *,
    research_profile: str,
) -> str:
    if research_profile == LAND_RESEARCH_PROFILE:
        parcel_key = parcel_identity_key(
            property_record.parcel_id,
            county=property_record.county,
            state=property_record.state,
        )
        property_record.normalized_parcel_key = parcel_key
        if parcel_key:
            return f"parcel:{parcel_key}"
    # Preserve the legacy address signature byte-for-byte so existing House and
    # addressed-Land snapshots remain reusable after this upgrade.
    return property_address_signature(property_record)


def research_profile_for_lead(lead: Lead) -> str:
    """Return the property-research profile owned by this lead's asset lane."""
    return research_profile_for_asset(lead.asset_class)


def research_lead_for_request(
    db: Session,
    property_record: Property,
    source_lead_id: UUID | None,
) -> Lead | None:
    if source_lead_id is not None:
        lead = db.get(Lead, source_lead_id)
        if (
            lead is None
            or lead.organization_id != property_record.organization_id
            or lead.property_id != property_record.id
        ):
            raise ValueError("The property research request does not belong to its source lead.")
        return lead
    return db.scalar(
        select(Lead)
        .where(
            Lead.organization_id == property_record.organization_id,
            Lead.property_id == property_record.id,
            Lead.archived_at.is_(None),
        )
        .order_by(Lead.created_at.desc())
    )


def next_property_snapshot_version(
    db: Session,
    *,
    property_id: UUID,
    research_profile: str,
) -> int:
    return (
        int(
            db.scalar(
                select(
                    func.coalesce(func.max(PropertyIntelligenceSnapshot.version_number), 0)
                ).where(
                    PropertyIntelligenceSnapshot.property_id == property_id,
                    PropertyIntelligenceSnapshot.research_profile == research_profile,
                )
            )
            or 0
        )
        + 1
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


def usable_research_identity(
    property_record: Property,
    *,
    research_profile: str,
) -> bool:
    if usable_research_address(property_record):
        return True
    return bool(
        research_profile == LAND_RESEARCH_PROFILE
        and parcel_identity_key(
            property_record.parcel_id,
            county=property_record.county,
            state=property_record.state,
        )
    )


def current_property_snapshot(
    db: Session,
    *,
    organization_id: UUID,
    property_id: UUID,
    research_profile: str,
) -> PropertyIntelligenceSnapshot | None:
    return db.scalar(
        select(PropertyIntelligenceSnapshot)
        .where(
            PropertyIntelligenceSnapshot.organization_id == organization_id,
            PropertyIntelligenceSnapshot.property_id == property_id,
            PropertyIntelligenceSnapshot.research_profile == research_profile,
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
    source_lead = research_lead_for_request(db, property_record, source_lead_id)
    research_profile = (
        research_profile_for_lead(source_lead)
        if source_lead is not None
        else HOUSE_RESEARCH_PROFILE
    )
    signature = property_research_signature(
        property_record,
        research_profile=research_profile,
    )
    if (
        source_lead is not None
        and source_lead.asset_class == LAND_ASSET_CLASS
        and not active_settings.land_workflow_enabled
    ):
        return record_disabled_land_research(
            db,
            property_record,
            source_lead=source_lead,
            research_profile=research_profile,
            address_signature=signature,
            trigger_source=trigger_source,
            force_refresh=force_refresh,
        )
    if not active_settings.property_intelligence_auto_research_enabled and not force_refresh:
        return None
    if not usable_research_identity(property_record, research_profile=research_profile):
        property_record.research_status = "needs_identity"
        property_record.research_last_error = (
            "House research requires a complete address. Land research requires either a "
            "complete address or APN with county and state."
        )
        return None
    now = datetime.now(UTC)
    snapshot = current_property_snapshot(
        db,
        organization_id=property_record.organization_id,
        property_id=property_record.id,
        research_profile=research_profile,
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
            PropertyResearchRun.research_profile == research_profile,
            PropertyResearchRun.address_signature == signature,
            PropertyResearchRun.status.in_(ACTIVE_RESEARCH_STATUSES),
        )
    )
    if active is not None:
        return active
    next_version = next_property_snapshot_version(
        db,
        property_id=property_record.id,
        research_profile=research_profile,
    )
    mode = "refresh" if force_refresh else "automatic"
    idempotency_key = (
        f"property-research:{property_record.id}:{research_profile}:{signature}:"
        f"v{next_version}:{mode}"
    )
    existing = db.scalar(
        select(PropertyResearchRun).where(
            PropertyResearchRun.organization_id == property_record.organization_id,
            PropertyResearchRun.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        return existing
    run = PropertyResearchRun(
        organization_id=property_record.organization_id,
        property_id=property_record.id,
        source_lead_id=source_lead_id,
        research_profile=research_profile,
        idempotency_key=idempotency_key,
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


def record_disabled_land_research(
    db: Session,
    property_record: Property,
    *,
    source_lead: Lead,
    research_profile: str,
    address_signature: str,
    trigger_source: str,
    force_refresh: bool,
) -> PropertyResearchRun:
    idempotency_key = (
        f"property-research:{property_record.id}:{research_profile}:{address_signature}:"
        "land-workflow-disabled"
    )
    existing = db.scalar(
        select(PropertyResearchRun).where(
            PropertyResearchRun.organization_id == property_record.organization_id,
            PropertyResearchRun.idempotency_key == idempotency_key,
        )
    )
    now = datetime.now(UTC)
    if existing is None:
        existing = PropertyResearchRun(
            organization_id=property_record.organization_id,
            property_id=property_record.id,
            source_lead_id=source_lead.id,
            research_profile=research_profile,
            idempotency_key=idempotency_key,
            trigger_source=trigger_source[:120],
            address_signature=address_signature,
            status="needs_review",
            force_refresh=force_refresh,
            attempt_count=0,
            completed_at=now,
            last_error=LAND_WORKFLOW_DISABLED_MESSAGE,
            run_metadata={
                "requested_at": now.isoformat(),
                "completed_at": now.isoformat(),
                "reason_code": "land_workflow_disabled",
                "residential_market_analysis_skipped": True,
            },
        )
        db.add(existing)
    property_record.research_status = "needs_review"
    property_record.research_requested_at = now
    property_record.research_completed_at = now
    property_record.research_last_error = LAND_WORKFLOW_DISABLED_MESSAGE
    db.flush()
    return existing


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
        if (
            property_research_signature(
                property_record,
                research_profile=run.research_profile,
            )
            != run.address_signature
        ):
            return finish_research_needs_review(
                db,
                run,
                "The property identity changed while research was queued. Request a new refresh.",
            )
        lead = research_lead(db, run)
        if lead is None:
            return finish_research_needs_review(
                db, run, "No active lead is available to host the research evidence."
            )
        expected_profile = research_profile_for_lead(lead)
        if run.research_profile != expected_profile:
            return finish_research_needs_review(
                db,
                run,
                "The lead asset class changed while research was queued. Request a new refresh.",
            )
        if lead.asset_class == LAND_ASSET_CLASS and not settings.land_workflow_enabled:
            return finish_research_needs_review(db, run, LAND_WORKFLOW_DISABLED_MESSAGE)
        existing_snapshot = current_property_snapshot(
            db,
            organization_id=run.organization_id,
            property_id=run.property_id,
            research_profile=run.research_profile,
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
        if not usable_research_identity(
            property_record,
            research_profile=run.research_profile,
        ):
            return finish_research_needs_review(
                db,
                run,
                "House research requires a complete address. Land research requires either a "
                "complete address or APN with county and state.",
            )
        if lead.asset_class == LAND_ASSET_CLASS:
            return process_land_property_research(
                db,
                settings,
                run=run,
                property_record=property_record,
                lead=lead,
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


def process_land_property_research(
    db: Session,
    settings: Settings,
    *,
    run: PropertyResearchRun,
    property_record: Property,
    lead: Lead,
) -> UUID:
    """Collect land property facts without entering the residential valuation pipeline."""
    if not settings.realestateapi_api_key:
        return finish_research_needs_review(
            db,
            run,
            "Land property research requires REALESTATEAPI_API_KEY. Residential comps and "
            "value math were not run.",
        )
    use_address = usable_research_address(property_record)
    try:
        detail = RealEstateAPIClient(settings).get_property_detail(
            address=format_property_address(property_record) if use_address else None,
            apn=property_record.parcel_id if not use_address else None,
            county=property_record.county if not use_address else None,
            state=property_record.state if not use_address else None,
            include_comps=False,
        )
    except RealEstateAPIError as exc:
        raise RuntimeError(str(exc)) from exc
    if not detail.found:
        return finish_research_needs_review(
            db,
            run,
            "RealEstateAPI found no exact land property match. Residential comps and value "
            "math were not run.",
        )
    requested_parcel = normalize_parcel_id(property_record.parcel_id)
    returned_parcel = normalize_parcel_id(realestateapi_property_parcel_id(detail.property))
    returned_components = realestateapi_property_address_components(detail.property)
    requested_parcel_key = parcel_identity_key(
        property_record.parcel_id,
        county=property_record.county,
        state=property_record.state,
    )
    returned_parcel_key = parcel_identity_key(
        returned_parcel,
        county=returned_components.get("county"),
        state=returned_components.get("state"),
    )
    if requested_parcel and (
        returned_parcel != requested_parcel
        or (not use_address and returned_parcel_key != requested_parcel_key)
    ):
        return finish_research_needs_review(
            db,
            run,
            "RealEstateAPI returned a different Land parcel/APN. Its facts were excluded, "
            "and residential comps and value math were not run.",
        )
    returned_address = realestateapi_property_address(detail.property)
    requested_address = format_property_address(property_record)
    if (
        use_address
        and returned_address
        and normalize_address_key(returned_address) != normalize_address_key(requested_address)
    ):
        return finish_research_needs_review(
            db,
            run,
            "RealEstateAPI returned a different land property address. Its facts were excluded, "
            "and residential comps and value math were not run.",
        )
    if not use_address:
        apply_realestateapi_parcel_address(property_record, detail.property)
        property_record.address_validation_status = "provider_confirmed"
        property_record.address_validation_provider = "realestateapi"
        property_record.provider_property_id = string_value(detail.property.get("id"))
        property_record.validated_formatted_address = returned_address
        property_record.address_validated_at = datetime.now(UTC)
        property_record.address_validation_metadata = {
            "lookup_mode": "parcel",
            "requested_parcel_key": requested_parcel_key,
            "returned_parcel_key": returned_parcel_key,
            "match_score": 100,
            "issues": [],
        }
    snapshot = create_land_property_snapshot(
        db,
        settings,
        property_record=property_record,
        lead=lead,
        property_payload=detail.property,
        trigger_source=run.trigger_source,
        lookup_mode="address" if use_address else "parcel",
        requested_identity=(
            requested_address if use_address else requested_parcel_key or "parcel-unavailable"
        ),
    )
    completed_at = datetime.now(UTC)
    run.status = snapshot.status
    run.completed_at = completed_at
    run.last_error = None
    run.run_metadata = {
        **(run.run_metadata or {}),
        "snapshot_id": str(snapshot.id),
        "completed_at": completed_at.isoformat(),
        "provider": "realestateapi",
        "provider_status": "completed",
        "provider_credits_estimated": 1,
        "lookup_mode": "address" if use_address else "parcel",
        "requested_identity": (
            format_property_address(property_record)
            if use_address
            else requested_parcel_key
        ),
        "residential_market_analysis_skipped": True,
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
                "Land property-record research is ready. Residential comps and value math "
                "were intentionally skipped."
            ),
        )
    )
    db.commit()
    return run.id


def create_land_property_snapshot(
    db: Session,
    settings: Settings,
    *,
    property_record: Property,
    lead: Lead,
    property_payload: dict[str, Any],
    trigger_source: str,
    lookup_mode: str = "address",
    requested_identity: str | None = None,
) -> PropertyIntelligenceSnapshot:
    research_profile = research_profile_for_lead(lead)
    if lead.asset_class != LAND_ASSET_CLASS:
        raise ValueError("Land property snapshots require a Land lead.")
    captured_at = datetime.now(UTC)
    facts = fallback_property_facts(property_record)
    formatted_address = format_property_address(property_record)
    if formatted_address and usable_research_address(property_record):
        facts["address"] = fact_value(
            formatted_address,
            property_record.address_validation_provider or "stonegate_crm",
            captured_at,
        )
    facts["asset_class"] = fact_value("land", "stonegate_crm", captured_at)
    conflicts = merge_realestateapi_property_facts(facts, property_payload, captured_at)
    # RealEstateAPI's generic AVM is not land valuation evidence. Keep raw record facts such
    # as sale history and assessed land value, but do not expose its estimate as a conclusion.
    facts.pop("realestateapi_estimated_value", None)
    parcel_fact = facts.get("parcel_id")
    parcel_value = parcel_fact.get("value") if isinstance(parcel_fact, dict) else None
    normalized_parcel = string_value(parcel_value)
    if not property_record.parcel_id and normalized_parcel:
        property_record.parcel_id = normalized_parcel
    property_record.normalized_parcel_key = parcel_identity_key(
        property_record.parcel_id,
        county=property_record.county,
        state=property_record.state,
    )
    media = realestateapi_media_snapshot(property_payload)
    completeness_score = land_property_completeness_score(facts, media)
    status = "ready" if completeness_score >= 65 else "partial"
    db.execute(
        update(PropertyIntelligenceSnapshot)
        .where(
            PropertyIntelligenceSnapshot.organization_id == property_record.organization_id,
            PropertyIntelligenceSnapshot.property_id == property_record.id,
            PropertyIntelligenceSnapshot.research_profile == research_profile,
            PropertyIntelligenceSnapshot.is_current.is_(True),
        )
        .values(is_current=False)
    )
    snapshot = PropertyIntelligenceSnapshot(
        organization_id=property_record.organization_id,
        property_id=property_record.id,
        source_lead_id=lead.id,
        source_market_analysis_id=None,
        research_profile=research_profile,
        version_number=next_property_snapshot_version(
            db,
            property_id=property_record.id,
            research_profile=research_profile,
        ),
        status=status,
        is_current=True,
        address_signature=property_research_signature(
            property_record,
            research_profile=research_profile,
        ),
        completeness_score=completeness_score,
        confidence_score=50,
        facts=facts,
        valuation={},
        comparables=[],
        market_context={
            "asset_class": "land",
            "research_profile": research_profile,
            "provider_property_records": {
                "realestateapi": safe_provider_property_payload(property_payload)
            },
            "residential_market_analysis": {
                "status": "skipped",
                "reason": LAND_RESIDENTIAL_SKIP_MESSAGE,
            },
            "manual_review_required": True,
            "review_reasons": [LAND_VALUATION_PENDING_MESSAGE],
        },
        sources=[
            {
                "source": "realestateapi",
                "captured_at": captured_at.isoformat(),
                "role": "canonical_land_property_record",
            },
            {
                "source": "stonegate",
                "captured_at": captured_at.isoformat(),
                "role": "crm_property_identity",
            },
        ],
        conflicts=conflicts[:100],
        media=media,
        snapshot_metadata={
            "trigger_source": trigger_source,
            "asset_class": "land",
            "research_profile": research_profile,
            "lookup_mode": lookup_mode,
            "requested_identity": requested_identity,
            "residential_market_analysis_skipped": True,
            "land_valuation_status": "not_started",
        },
        captured_at=captured_at,
        expires_at=captured_at + timedelta(days=settings.property_intelligence_fresh_days),
    )
    db.add(snapshot)
    db.flush()
    return snapshot


def realestateapi_property_address(property_payload: dict[str, Any]) -> str | None:
    info = property_payload.get("propertyInfo")
    info_values = info if isinstance(info, dict) else {}
    address = info_values.get("address")
    if not isinstance(address, dict):
        raw_address = property_payload.get("address")
        address = raw_address if isinstance(raw_address, dict) else {}
    direct = string_value(address.get("formattedAddress")) or string_value(
        address.get("fullAddress")
    )
    if direct:
        return direct
    street = (
        string_value(address.get("address"))
        or string_value(address.get("addressLine1"))
        or string_value(address.get("streetAddress"))
    )
    if not street:
        return None
    locality = ", ".join(
        value
        for value in (
            string_value(address.get("city")),
            string_value(address.get("state")),
        )
        if value
    )
    postal_code = (
        string_value(address.get("zip"))
        or string_value(address.get("zipCode"))
        or string_value(address.get("postalCode"))
    )
    return ", ".join(value for value in (street, locality) if value) + (
        f" {postal_code}" if postal_code else ""
    )


def realestateapi_property_parcel_id(property_payload: dict[str, Any]) -> str | None:
    lot_info = property_payload.get("lotInfo")
    lot_values = lot_info if isinstance(lot_info, dict) else {}
    return (
        string_value(lot_values.get("apn"))
        or string_value(lot_values.get("apnUnformatted"))
        or string_value(property_payload.get("apn"))
    )


def realestateapi_property_address_components(
    property_payload: dict[str, Any],
) -> dict[str, str | None]:
    info = property_payload.get("propertyInfo")
    info_values = info if isinstance(info, dict) else {}
    address_value = info_values.get("address")
    if not isinstance(address_value, dict):
        direct = property_payload.get("address")
        address_value = direct if isinstance(direct, dict) else {}
    return {
        "street_address": (
            string_value(address_value.get("address"))
            or string_value(address_value.get("addressLine1"))
            or string_value(address_value.get("streetAddress"))
            or string_value(address_value.get("street"))
        ),
        "city": string_value(address_value.get("city")),
        "state": string_value(address_value.get("state")),
        "postal_code": (
            string_value(address_value.get("zip"))
            or string_value(address_value.get("zipCode"))
            or string_value(address_value.get("postalCode"))
        ),
        "county": string_value(address_value.get("county")),
    }


def apply_realestateapi_parcel_address(
    property_record: Property,
    property_payload: dict[str, Any],
) -> None:
    """Fill missing address parts only after an APN lookup has been verified."""
    components = realestateapi_property_address_components(property_payload)
    street = string_value(components.get("street_address"))
    city = string_value(components.get("city"))
    state = string_value(components.get("state"))
    postal_code = string_value(components.get("postal_code"))
    county = string_value(components.get("county"))
    if street and (
        not property_record.street_address.strip()
        or property_record.street_address.lower().startswith("address pending")
    ):
        property_record.street_address = street
    if city and (
        not property_record.city.strip() or property_record.city.strip().lower() == "unknown"
    ):
        property_record.city = city
    if state and len(state) == 2 and not property_record.state.strip():
        property_record.state = state.upper()
    if postal_code and (
        not property_record.postal_code.strip()
        or property_record.postal_code.strip().lower() == "unknown"
    ):
        property_record.postal_code = postal_code
    if county and not property_record.county:
        property_record.county = county
    if usable_research_address(property_record):
        property_record.normalized_address_key = canonical_address_key(
            property_record.street_address,
            property_record.city,
            property_record.state,
            property_record.postal_code,
        )
    property_record.normalized_parcel_key = parcel_identity_key(
        property_record.parcel_id,
        county=property_record.county,
        state=property_record.state,
    )


def safe_provider_property_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): safe_provider_property_payload(item)
            for key, item in value.items()
            if "phone" not in str(key).lower()
            and "email" not in str(key).lower()
            and str(key).lower() not in {"comps", "comparables", "estimatedvalue"}
        }
    if isinstance(value, list):
        return [safe_provider_property_payload(item) for item in value]
    return value


def land_property_completeness_score(
    facts: dict[str, Any],
    media: dict[str, Any],
) -> int:
    required_facts = {
        "address",
        "property_type",
        "parcel_id",
        "lot_size",
        "lot_size_acres",
        "zoning",
        "latitude",
        "longitude",
        "annual_property_tax",
        "assessed_land_value",
    }
    fact_points = round(95 * len(required_facts.intersection(facts)) / len(required_facts))
    realestateapi = media.get("realestateapi")
    image_points = (
        5 if isinstance(realestateapi, dict) and realestateapi.get("status") == "available" else 0
    )
    return min(100, fact_points + image_points)


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
    trigger_source: str,
) -> PropertyIntelligenceSnapshot:
    research_profile = research_profile_for_lead(lead)
    if lead.asset_class == LAND_ASSET_CLASS:
        raise ValueError(
            "Residential market analysis cannot create a Land property intelligence snapshot."
        )
    captured_at = datetime.now(UTC)
    metadata = analysis.analysis_metadata or {}
    assumptions = metadata.get("assumptions")
    assumption_values = assumptions if isinstance(assumptions, dict) else {}
    provenance = assumption_values.get("subject_fact_provenance")
    provenance_values = provenance if isinstance(provenance, dict) else {}
    subject = analysis.subject_property or {}
    facts = normalized_fact_snapshot(subject, provenance_values, captured_at)
    realestateapi_subject = realestateapi_subject_property(analysis)
    realestateapi_conflicts = merge_realestateapi_property_facts(
        facts,
        realestateapi_subject,
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
    media = realestateapi_media_snapshot(realestateapi_subject)
    selected = [item for item in analysis.selected_comps if isinstance(item, dict)]
    rejected = [item for item in analysis.rejected_comps if isinstance(item, dict)]
    conflicts = [
        *property_conflicts(metadata, selected, rejected),
        *realestateapi_conflicts,
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
        "provider_property_records": {
            "realestateapi": realestateapi_subject,
        }
        if realestateapi_subject
        else {},
    }
    source_names = {analysis.provider, "stonegate"}
    if realestateapi_subject:
        source_names.add("realestateapi")
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
            PropertyIntelligenceSnapshot.research_profile == research_profile,
            PropertyIntelligenceSnapshot.is_current.is_(True),
        )
        .values(is_current=False)
    )
    version_number = next_property_snapshot_version(
        db,
        property_id=property_record.id,
        research_profile=research_profile,
    )
    snapshot = PropertyIntelligenceSnapshot(
        organization_id=property_record.organization_id,
        property_id=property_record.id,
        source_lead_id=lead.id,
        source_market_analysis_id=analysis.id,
        research_profile=research_profile,
        version_number=version_number,
        status=status,
        is_current=True,
        address_signature=property_research_signature(
            property_record,
            research_profile=research_profile,
        ),
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
            "asset_class": lead.asset_class,
            "research_profile": research_profile,
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
        "rentcast_property_id": "id",
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


REALESTATEAPI_PROPERTY_FACTS: tuple[tuple[tuple[str, ...], str, str | None], ...] = (
    (("estimatedValue",), "realestateapi_estimated_value", "dollars"),
    (("estimatedEquity",), "estimated_equity_amount", "dollars"),
    (("equityPercent",), "estimated_equity_percentage", "percent"),
    (("estimatedMortgageBalance",), "estimated_loan_balance", "dollars"),
    (("openMortgageBalance",), "open_mortgage_balance", "dollars"),
    (("lastSaleDate",), "last_sale_date", None),
    (("lastSalePrice",), "last_sale_price", "dollars"),
    (("propertyType",), "property_type", None),
    (("mlsListingPrice",), "current_listing_price", "dollars"),
    (("mlsDaysOnMarket",), "days_on_market", "days"),
    (("mlsLastStatusDate",), "listing_status_date", None),
    (("floodZone",), "flood_zone", None),
    (("floodZoneDescription",), "flood_zone_description", None),
    (("ownerOccupied",), "owner_occupied", None),
    (("vacant",), "vacant", None),
    (("preForeclosure",), "pre_foreclosure", None),
    (("auction",), "auction", None),
    (("lien",), "lien_reported", None),
    (("freeClear",), "free_and_clear", None),
    (("propertyInfo", "bedrooms"), "bedrooms", "count"),
    (("propertyInfo", "bathrooms"), "bathrooms", "count"),
    (("propertyInfo", "livingSquareFeet"), "square_footage", "square_feet"),
    (("propertyInfo", "buildingSquareFeet"), "building_square_footage", "square_feet"),
    (("propertyInfo", "yearBuilt"), "year_built", None),
    (("propertyInfo", "stories"), "stories", None),
    (("propertyInfo", "unitsCount"), "unit_count", "count"),
    (("propertyInfo", "construction"), "construction_type", None),
    (("propertyInfo", "garage"), "garage_type", None),
    (("propertyInfo", "basement"), "basement", None),
    (("propertyInfo", "pool"), "pool", None),
    (("propertyInfo", "porchType"), "porch", None),
    (("propertyInfo", "roofConstruction"), "roof_type", None),
    (("propertyInfo", "roofMaterial"), "roof_cover", None),
    (("propertyInfo", "heatingType"), "heating_type", None),
    (("propertyInfo", "airConditioningType"), "air_conditioning", None),
    (("propertyInfo", "waterSource"), "water", None),
    (("propertyInfo", "sewer"), "sewer", None),
    (("propertyInfo", "address", "county"), "county", None),
    (("propertyInfo", "address", "state"), "state", None),
    (("propertyInfo", "address", "fips"), "county_fips", None),
    (("propertyInfo", "latitude"), "latitude", None),
    (("propertyInfo", "longitude"), "longitude", None),
    (("propertyInfo", "propertyUse"), "property_use", None),
    (("propertyInfo", "propertyUseCode"), "property_use_code", None),
    (("latitude",), "latitude", None),
    (("longitude",), "longitude", None),
    (("lotInfo", "apn"), "parcel_id", None),
    (("lotInfo", "lotSquareFeet"), "lot_size", "square_feet"),
    (("lotInfo", "lotAcres"), "lot_size_acres", "acres"),
    (("lotInfo", "legalDescription"), "legal_description", None),
    (("lotInfo", "lotNumber"), "lot_number", None),
    (("lotInfo", "zoning"), "zoning", None),
    (("lotInfo", "landUse"), "land_use", None),
    (("lotInfo", "propertyClass"), "property_class", None),
    (("taxInfo", "taxAmount"), "annual_property_tax", "dollars"),
    (("taxInfo", "assessedValue"), "assessed_total_value", "dollars"),
    (("taxInfo", "assessedImprovementValue"), "assessed_improvement_value", "dollars"),
    (("taxInfo", "assessedLandValue"), "assessed_land_value", "dollars"),
    (("taxInfo", "assessmentYear"), "tax_assessment_year", None),
    (("ownerInfo", "ownershipLength"), "ownership_length_months", "months"),
    (("ownerInfo", "owner1FullName"), "recorded_owner", None),
    (("ownerInfo", "owner2FullName"), "recorded_co_owner", None),
    (("ownerInfo", "companyName"), "owner_company", None),
    (("ownerInfo", "mailAddress", "address"), "owner_mailing_street", None),
    (("ownerInfo", "mailAddress", "city"), "owner_mailing_city", None),
    (("ownerInfo", "mailAddress", "state"), "owner_mailing_state", None),
    (("ownerInfo", "mailAddress", "zip"), "owner_mailing_zip", None),
)


def realestateapi_subject_property(analysis: UnderwritingMarketAnalysis) -> dict[str, Any]:
    raw_response = analysis.raw_response if isinstance(analysis.raw_response, dict) else {}
    provider_payload = raw_response.get("realestateapi")
    if not isinstance(provider_payload, dict):
        return {}
    property_payload = provider_payload.get("property")
    return property_payload if isinstance(property_payload, dict) else {}


def merge_realestateapi_property_facts(
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
    for path, fact_key, unit in REALESTATEAPI_PROPERTY_FACTS:
        value = nested_value(property_payload, path)
        if value is None:
            continue
        existing = facts.get(fact_key)
        if existing is None:
            facts[fact_key] = fact_value(
                value,
                "realestateapi_property_detail",
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
                        f"RentCast and RealEstateAPI disagree on {fact_key.replace('_', ' ')}."
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
                        {"source": "realestateapi_property_detail", "value": value},
                    ],
                }
            )
        if fact_key in conflict_targets:
            facts[fact_key] = fact_value(
                value,
                "realestateapi_property_detail",
                captured_at,
                unit=unit,
            )
    if "market_status" not in facts:
        market_status = next(
            (
                label
                for key, label in (
                    ("mlsActive", "active"),
                    ("mlsPending", "pending"),
                    ("mlsSold", "sold"),
                    ("mlsCancelled", "cancelled"),
                    ("mlsFailed", "failed"),
                )
                if property_payload.get(key) is True
            ),
            None,
        )
        if market_status:
            facts["market_status"] = fact_value(
                market_status,
                "realestateapi_property_detail",
                captured_at,
            )
    return conflicts


def nested_value(payload: dict[str, Any], path: tuple[str, ...]) -> Any:
    value: Any = payload
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


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


def realestateapi_media_snapshot(property_payload: dict[str, Any]) -> dict[str, Any]:
    media = property_payload.get("media")
    media_values = media if isinstance(media, dict) else {}
    image_url = realestateapi_primary_image_url(property_payload)
    return {
        "realestateapi": {
            "status": "available" if image_url else "unavailable",
            "primary_listing_image_url": image_url,
            "photos_count": media_values.get("photosCount"),
            "attribution": "RealEstateAPI licensed listing media",
            "usage": "listing_media_returned_by_provider",
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
    realestateapi = media.get("realestateapi")
    image_points = (
        5 if isinstance(realestateapi, dict) and realestateapi.get("status") == "available" else 0
    )
    return min(100, fact_points + valuation_points + comp_points + image_points)


def source_role(name: str) -> str:
    return {
        "rentcast": "independent_comparable_and_market_evidence",
        "realestateapi": "canonical_property_record_and_candidate_comparable_evidence",
        "dealmachine": "candidate_comparable_evidence",
        "cited_public_research": "supplemental_review_only",
        "stonegate": "crm_and_calculation_record",
    }.get(name, "supporting_evidence")


def latest_property_research_run(
    db: Session,
    *,
    organization_id: UUID,
    property_id: UUID,
    research_profile: str,
    address_signature: str,
) -> PropertyResearchRun | None:
    return db.scalar(
        select(PropertyResearchRun)
        .where(
            PropertyResearchRun.organization_id == organization_id,
            PropertyResearchRun.property_id == property_id,
            PropertyResearchRun.research_profile == research_profile,
            PropertyResearchRun.address_signature == address_signature,
        )
        .order_by(PropertyResearchRun.created_at.desc(), PropertyResearchRun.id.desc())
    )


def profile_research_state(
    property_record: Property,
    *,
    research_profile: str,
    snapshot: PropertyIntelligenceSnapshot | None,
    run: PropertyResearchRun | None,
) -> tuple[str, str | None, dict[str, Any]]:
    run_is_newer = bool(
        run is not None
        and (
            snapshot is None
            or as_utc(run.created_at) >= as_utc(snapshot.captured_at)
        )
    )
    if run is not None and run_is_newer and run.status in {
        *ACTIVE_RESEARCH_STATUSES,
        "failed",
        "needs_review",
    }:
        metadata = run.run_metadata or {}
        context = (
            {
                "asset_class": "land",
                "research_profile": research_profile,
                "workflow_status": "disabled",
                "residential_market_analysis": {
                    "status": "skipped",
                    "reason": run.last_error or LAND_WORKFLOW_DISABLED_MESSAGE,
                },
                "manual_review_required": True,
                "review_reasons": [run.last_error or LAND_WORKFLOW_DISABLED_MESSAGE],
            }
            if metadata.get("reason_code") == "land_workflow_disabled"
            else {}
        )
        return run.status, run.last_error, context
    if snapshot is not None:
        return snapshot.status, None, {}
    if property_record.research_status in {"needs_address", "needs_identity"}:
        return property_record.research_status, property_record.research_last_error, {}
    return "not_started", None, {}


def build_property_intelligence_read(
    db: Session,
    principal: Principal,
    lead: Lead,
) -> PropertyIntelligenceRead:
    property_record = db.get(Property, lead.property_id)
    if property_record is None:
        return PropertyIntelligenceRead(
            research_status="unavailable",
            research_profile=research_profile_for_lead(lead),
        )
    research_profile = research_profile_for_lead(lead)
    address_signature = property_research_signature(
        property_record,
        research_profile=research_profile,
    )
    snapshot = current_property_snapshot(
        db,
        organization_id=principal.organization_id,
        property_id=property_record.id,
        research_profile=research_profile,
    )
    if snapshot is not None and snapshot.address_signature != address_signature:
        snapshot = None
    latest_run = latest_property_research_run(
        db,
        organization_id=principal.organization_id,
        property_id=property_record.id,
        research_profile=research_profile,
        address_signature=address_signature,
    )
    research_status, last_error, fallback_market_context = profile_research_state(
        property_record,
        research_profile=research_profile,
        snapshot=snapshot,
        run=latest_run,
    )
    image_source = "placeholder"
    image_available = False
    image_views: list[str] = []
    image_attribution = None
    imagery_date = None
    photo = latest_property_photo(db, principal.organization_id, property_record.id)
    realestateapi_media: dict[str, Any] = {}
    if snapshot is not None:
        raw_media = snapshot.media.get("realestateapi")
        if isinstance(raw_media, dict):
            realestateapi_media = raw_media
    listing_image_url = string_value(realestateapi_media.get("primary_listing_image_url"))
    if photo is not None:
        image_source = "inspection_photo"
        image_available = True
        image_views = ["listing"]
        image_attribution = "Stonegate field inspection"
        imagery_date = (photo.captured_at or photo.created_at).date().isoformat()
    elif listing_image_url and is_realestateapi_image_url(listing_image_url):
        image_source = "realestateapi_listing"
        image_available = True
        image_views = ["listing"]
        image_attribution = str(
            realestateapi_media.get("attribution") or "RealEstateAPI licensed listing media"
        )
    valuation = dict(snapshot.valuation) if snapshot else {}
    comparables = list(snapshot.comparables) if snapshot else []
    market_context = dict(snapshot.market_context) if snapshot else dict(fallback_market_context)
    sources = list(snapshot.sources) if snapshot else []
    confidence_score = snapshot.confidence_score if snapshot else 0
    if lead.asset_class == LAND_ASSET_CLASS and snapshot is not None:
        land_analysis = latest_land_valuation_for_snapshot(
            db,
            organization_id=principal.organization_id,
            lead_id=lead.id,
            property_snapshot_id=snapshot.id,
        )
        if land_analysis is not None:
            current_state_reasons = current_land_analysis_reasons(
                land_analysis,
                property_record=property_record,
                current_snapshot=snapshot,
                current_identity_signature=address_signature,
                active_policy_id=active_land_offer_policy_id(
                    db, principal.organization_id
                ),
            )
            combined_blockers = list(
                dict.fromkeys(
                    [*land_analysis.guidance_blockers, *current_state_reasons]
                )
            )
            combined_review_reasons = list(
                dict.fromkeys([*land_analysis.review_reasons, *current_state_reasons])
            )
            valuation = land_valuation_overlay(
                land_analysis,
                current_state_reasons=current_state_reasons,
            )
            comparables = [land_comparable_overlay(item) for item in land_analysis.selected_comps]
            confidence_score = land_analysis.confidence_score
            market_context = {
                **market_context,
                "manual_review_required": bool(
                    combined_review_reasons or combined_blockers
                ),
                "review_reasons": list(
                    dict.fromkeys(
                        [
                            *combined_review_reasons,
                            *combined_blockers,
                        ]
                    )
                ),
                "land_valuation": {
                    "analysis_id": str(land_analysis.id),
                    "version_number": land_analysis.version_number,
                    "status": (
                        "needs_review"
                        if current_state_reasons
                        and land_analysis.status != "insufficient_evidence"
                        else land_analysis.status
                    ),
                    "guidance_status": (
                        "withheld"
                        if current_state_reasons
                        else land_analysis.guidance_status
                    ),
                    "is_current": not current_state_reasons,
                    "valuation_basis": land_analysis.valuation_basis,
                    "review_reasons": combined_review_reasons,
                    "guidance_blockers": combined_blockers,
                    "created_at": as_utc(land_analysis.created_at).isoformat(),
                },
            }
            sources = [
                *sources,
                {
                    "source": "stonegate",
                    "captured_at": as_utc(land_analysis.created_at).isoformat(),
                    "role": "dedicated_land_comparable_and_offer_analysis",
                },
            ]
    return PropertyIntelligenceRead(
        research_status=research_status,
        research_profile=research_profile,
        snapshot_id=snapshot.id if snapshot else None,
        version_number=snapshot.version_number if snapshot else None,
        snapshot_status=snapshot.status if snapshot else None,
        completeness_score=snapshot.completeness_score if snapshot else 0,
        confidence_score=confidence_score,
        captured_at=as_utc(snapshot.captured_at) if snapshot else None,
        expires_at=as_utc(snapshot.expires_at) if snapshot else None,
        is_stale=bool(snapshot and as_utc(snapshot.expires_at) <= datetime.now(UTC)),
        facts=snapshot.facts if snapshot else fallback_property_facts(property_record),
        valuation=valuation,
        comparables=comparables,
        market_context=market_context,
        sources=sources,
        conflicts=snapshot.conflicts if snapshot else [],
        image_source=image_source,
        image_available=image_available,
        image_views=image_views,
        image_url=f"/api/v1/leads/{lead.id}/property-image" if image_available else None,
        image_attribution=image_attribution,
        imagery_date=imagery_date,
        last_error=last_error,
    )


def latest_land_valuation_for_snapshot(
    db: Session,
    *,
    organization_id: UUID,
    lead_id: UUID,
    property_snapshot_id: UUID,
) -> LandValuationAnalysis | None:
    return db.scalar(
        select(LandValuationAnalysis)
        .where(
            LandValuationAnalysis.organization_id == organization_id,
            LandValuationAnalysis.lead_id == lead_id,
            LandValuationAnalysis.property_snapshot_id == property_snapshot_id,
        )
        .order_by(
            LandValuationAnalysis.version_number.desc(),
            LandValuationAnalysis.created_at.desc(),
        )
    )


def land_valuation_overlay(
    analysis: LandValuationAnalysis,
    *,
    current_state_reasons: list[str],
) -> dict[str, Any]:
    guidance_is_current = not current_state_reasons
    return {
        "land_value_low_cents": analysis.supported_value_low_cents,
        "land_value_point_cents": analysis.supported_value_cents,
        "land_value_high_cents": analysis.supported_value_high_cents,
        "quick_sale_low_cents": (
            analysis.quick_sale_low_cents if guidance_is_current else None
        ),
        "quick_sale_high_cents": (
            analysis.quick_sale_high_cents if guidance_is_current else None
        ),
        "opening_offer_cents": analysis.opening_offer_cents if guidance_is_current else None,
        "seller_contract_ceiling_cents": (
            analysis.seller_contract_ceiling_cents if guidance_is_current else None
        ),
        "guidance_status": analysis.guidance_status if guidance_is_current else "withheld",
        "is_current": guidance_is_current,
        "valuation_basis": analysis.valuation_basis,
        "source_note": (
            "Stonegate Land math uses saved, reviewed closed-sale evidence. "
            "Residential ARV and provider AVMs are excluded."
        ),
    }


def land_comparable_overlay(comparable: dict[str, Any]) -> dict[str, Any]:
    return {
        **comparable,
        "price_cents": comparable.get("sale_price_cents"),
        "comp_grade": comparable.get("evidence_tier"),
    }


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
    run = enqueue_property_research(
        db,
        property_record,
        source_lead_id=lead.id,
        trigger_source="manual_property_refresh",
        force_refresh=True,
    )
    disabled_land = bool(
        run is not None
        and (run.run_metadata or {}).get("reason_code") == "land_workflow_disabled"
    )
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            event_type="property.research_requested",
            summary=(
                "Land property research needs review because the Land workflow is disabled; "
                "residential comps and value math were not run."
                if disabled_land
                else "Property research refresh requested; provider calls or credits may be used."
            ),
        )
    )
    db.commit()
    return build_property_intelligence_read(db, principal, lead)


def fallback_property_facts(property_record: Property) -> dict[str, Any]:
    now = property_record.updated_at
    formatted_address = format_property_address(property_record)
    facts = (
        {"address": fact_value(formatted_address, "stonegate_crm", now)}
        if formatted_address and usable_research_address(property_record)
        else {}
    )
    if property_record.property_type:
        facts["property_type"] = fact_value(property_record.property_type, "stonegate_crm", now)
    if property_record.county:
        facts["county"] = fact_value(property_record.county, "stonegate_crm", now)
    if property_record.parcel_id:
        facts["parcel_id"] = fact_value(property_record.parcel_id, "stonegate_crm", now)
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
    view: str = "listing",
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
    photo = latest_property_photo(db, principal.organization_id, lead.property_id)
    if photo is not None:
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
        research_profile=research_profile_for_lead(lead),
    )
    realestateapi = snapshot.media.get("realestateapi") if snapshot else None
    image_url = (
        string_value(realestateapi.get("primary_listing_image_url"))
        if isinstance(realestateapi, dict)
        else None
    )
    if image_url and is_realestateapi_image_url(image_url):
        content, content_type = get_realestateapi_image(
            image_url,
            timeout_seconds=settings.realestateapi_request_timeout_seconds,
        )
        return PropertyImageContent(
            content=content,
            content_type=content_type,
            source="realestateapi_listing",
        )
    return None


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


def property_snapshot_backfill_candidate_statement() -> Select[tuple[UnderwritingMarketAnalysis]]:
    return (
        select(UnderwritingMarketAnalysis)
        .join(Property, Property.id == UnderwritingMarketAnalysis.property_id)
        .join(Lead, Lead.id == UnderwritingMarketAnalysis.lead_id)
        .outerjoin(
            PropertyIntelligenceSnapshot,
            and_(
                PropertyIntelligenceSnapshot.property_id == UnderwritingMarketAnalysis.property_id,
                PropertyIntelligenceSnapshot.research_profile == HOUSE_RESEARCH_PROFILE,
                PropertyIntelligenceSnapshot.is_current.is_(True),
            ),
        )
        .where(
            Lead.asset_class != LAND_ASSET_CLASS,
            PropertyIntelligenceSnapshot.id.is_(None),
        )
        .order_by(UnderwritingMarketAnalysis.created_at.desc())
        .with_for_update(of=UnderwritingMarketAnalysis, skip_locked=True)
    )


def backfill_next_property_snapshot(db: Session, settings: Settings) -> UUID | None:
    analysis = db.scalar(property_snapshot_backfill_candidate_statement())
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
            PropertyResearchRun.research_profile == snapshot.research_profile,
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
    return property_identity_label(
        street_address=property_record.street_address,
        city=property_record.city,
        state=property_record.state.strip().upper(),
        postal_code=normalize_postal_code(property_record.postal_code),
        parcel_id=property_record.parcel_id,
        county=property_record.county,
    )


def string_value(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def number_value(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)
