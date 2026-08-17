import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session
from sqlalchemy.sql.elements import ColumnElement

from app.core.auth import Principal
from app.core.config import Settings, get_settings
from app.integrations.marketing_conversions import (
    ConversionDeliveryError,
    MarketingConversionClient,
)
from app.models.foundation import (
    ActivityEvent,
    Appointment,
    AttributionTouch,
    AuditEvent,
    ContactMethod,
    ConversionEvent,
    Lead,
    MarketingSpend,
    MetaLeadEvent,
    OfflineConversionExport,
    RevenueRecord,
    StaffLeadAlert,
    Transaction,
    WorkerHeartbeat,
)
from app.schemas.marketing import (
    MarketingCampaignPerformance,
    MarketingMeasurementSummary,
    MarketingOverview,
    MarketingProviderReadiness,
    MarketingSummary,
    MarketingWorkerReadiness,
    MetaMatchCoverage,
    OfflineConversionExportRead,
    PublicFunnelSummary,
    WebVitalSummary,
)
from app.services.operations import (
    COMMUNICATIONS_WORKER,
    get_worker_readiness,
    meta_pixel_id_fingerprint,
)

ATTRIBUTION_MODEL = "last_eligible_platform_click"
MEASUREMENT_POLICY_VERSION = "stonegate-marketing-measurement-v1"
CONSENT_BASIS = "privacy_notice_first_party_measurement"
META_WEB_ATTRIBUTION_MODEL = "meta_browser_server_deduplicated_v1"
META_WEB_CONSENT_BASIS = "website_contact_and_measurement_notice_v1"
META_WEB_ENRICHABLE_EXPORT_STATUSES = frozenset({"pending", "retry", "blocked"})
META_BROWSER_CLICK_ID_STORAGE_LENGTH = 255
META_MATCH_COVERAGE_WINDOW_DAYS = 30
QUALIFIED_STAGES = {
    "qualified",
    "appointment_scheduled",
    "underwriting",
    "offer_presented",
    "negotiating",
    "under_contract",
    "closed",
}


@dataclass
class CampaignRow:
    source: str
    medium: str
    campaign: str
    page_views: int = 0
    form_starts: int = 0
    form_abandons: int = 0
    form_submits: int = 0
    address_leads: int = 0
    contact_completed_leads: int = 0
    call_clicks: int = 0
    leads_created: int = 0
    contracted_leads: int = 0
    collected_revenue_cents: int = 0
    marketing_spend_cents: int = 0


@dataclass(frozen=True)
class ConversionOutcome:
    event_name: str
    source_record_type: str
    source_record_id: UUID
    lead_id: UUID
    occurred_at: datetime
    value_cents: int | None = None
    revenue_record_id: UUID | None = None


def enqueue_meta_web_conversion(
    db: Session,
    *,
    event: ConversionEvent,
    event_name: str,
    event_id: str,
    event_source_url: str,
    fbc: str | None,
    fbp: str | None,
    email: str | None = None,
    phone: str | None = None,
    full_name: str | None = None,
    external_id: str | None = None,
    occurred_at: datetime | None = None,
) -> OfflineConversionExport | None:
    """Queue a Meta server event that shares its ID with the browser Pixel event."""
    if event_name not in {"ViewContent", "Lead", "Contact"}:
        raise ValueError(f"Unsupported immediate Meta web event: {event_name}")
    existing = db.scalar(
        select(OfflineConversionExport.id).where(
            OfflineConversionExport.organization_id == event.organization_id,
            OfflineConversionExport.platform == "meta",
            OfflineConversionExport.event_key == event_id,
        )
    )
    if existing is not None:
        return None
    settings = get_settings()
    normalized_email = normalize_email(email) if email else ""
    normalized_phone = normalize_phone(phone) if phone else ""
    first_name, last_name = split_meta_person_name(full_name)
    snapshot: dict[str, object] = {
        "policy_version": MEASUREMENT_POLICY_VERSION,
        "event_name": event_name,
        "occurred_at": (occurred_at or datetime.now(UTC)).isoformat(),
        "landing_page": safe_meta_event_source_url(
            event_source_url,
            website_base_url=settings.marketing_website_base_url,
        ),
        "client_ip_address": event.ip_address,
        "client_user_agent": event.user_agent,
        "fbc": fbc,
        "fbp": fbp,
        "fbclid": event.fbclid,
        "click_captured_at": utc_isoformat(event.fbclid_captured_at),
        "email_hashes": [sha256(normalized_email)] if normalized_email else [],
        "phone_hashes": [sha256(normalized_phone)] if normalized_phone else [],
        "first_name_hashes": [sha256(first_name)] if first_name else [],
        "last_name_hashes": [sha256(last_name)] if last_name else [],
        "external_id_hash": sha256(external_id) if external_id else None,
    }
    export = OfflineConversionExport(
        organization_id=event.organization_id,
        platform="meta",
        conversion_event_id=event.id,
        lead_id=event.lead_id,
        revenue_record_id=None,
        event_key=event_id,
        source_record_type="conversion_event",
        source_record_id=event.id,
        event_name=event_name,
        occurred_at=occurred_at or datetime.now(UTC),
        attribution_model=META_WEB_ATTRIBUTION_MODEL,
        consent_basis=META_WEB_CONSENT_BASIS,
        # The JSON snapshot is the provider payload of record and retains the
        # complete opaque Meta envelope. ``click_id`` predates the browser SDK
        # and remains a bounded operational preview because its DB column is
        # intentionally limited to 255 characters.
        click_id=meta_browser_click_id_preview(fbc=fbc, fbp=fbp),
        click_id_type="meta_browser",
        value_cents=None,
        currency="USD",
        payload_hash=payload_hash(snapshot),
        payload_snapshot=snapshot,
        delivery_mode=settings.marketing_conversion_mode,
        status="pending",
        attempt_count=0,
        exported_at=None,
        last_error=None,
    )
    db.add(export)
    db.flush()
    return export


def enrich_meta_web_conversion_identifiers(
    export: OfflineConversionExport,
    *,
    fbc: str | None,
    fbp: str | None,
    fbclid: str | None,
    click_captured_at: datetime | None,
) -> bool:
    """Add newly recovered Meta identifiers before a conversion is final.

    Address capture may arrive before Meta's in-app browser bridge finishes
    recovering ``fbc``. A same-event retry is allowed to fill identifiers that
    were absent from the queued payload, but final provider evidence is never
    rewritten after delivery, simulation, or exhaustion.
    """
    if not can_enrich_meta_web_conversion_identifiers(export):
        return False

    snapshot = dict(export.payload_snapshot)
    changed = False
    additions: tuple[tuple[str, object | None], ...] = (
        ("fbc", non_empty_string(fbc)),
        ("fbp", non_empty_string(fbp)),
    )
    for key, incoming in additions:
        if incoming is None or snapshot_has_non_empty_value(snapshot, key):
            continue
        snapshot[key] = incoming
        changed = True

    incoming_fbclid = non_empty_string(fbclid)
    persisted_fbclid = non_empty_string(snapshot.get("fbclid"))
    if persisted_fbclid is None and incoming_fbclid is not None:
        snapshot["fbclid"] = incoming_fbclid
        persisted_fbclid = incoming_fbclid
        changed = True
    incoming_click_captured_at = utc_isoformat(click_captured_at)
    if (
        incoming_click_captured_at is not None
        and incoming_fbclid is not None
        and persisted_fbclid == incoming_fbclid
        and not snapshot_has_non_empty_value(snapshot, "click_captured_at")
    ):
        snapshot["click_captured_at"] = incoming_click_captured_at
        changed = True

    if not changed:
        return False

    export.payload_snapshot = snapshot
    export.payload_hash = payload_hash(snapshot)
    preferred_fbc = non_empty_string(snapshot.get("fbc"))
    preferred_fbp = non_empty_string(snapshot.get("fbp"))
    export.click_id = meta_browser_click_id_preview(
        fbc=preferred_fbc,
        fbp=preferred_fbp,
    )
    return True


def can_enrich_meta_web_conversion_identifiers(export: OfflineConversionExport) -> bool:
    return export.platform == "meta" and export.status in META_WEB_ENRICHABLE_EXPORT_STATUSES


def meta_browser_click_id_preview(*, fbc: str | None, fbp: str | None) -> str:
    """Return the bounded legacy-column preview without truncating CAPI data."""
    value = non_empty_string(fbc) or non_empty_string(fbp) or ""
    return value[:META_BROWSER_CLICK_ID_STORAGE_LENGTH]


def snapshot_has_non_empty_value(snapshot: dict[str, object], key: str) -> bool:
    value = snapshot.get(key)
    return bool(value.strip()) if isinstance(value, str) else value is not None


def non_empty_string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def enqueue_meta_schedule_conversion(
    db: Session,
    *,
    appointment: Appointment,
    lead: Lead,
) -> OfflineConversionExport | None:
    """Queue a new seller appointment for Meta without requiring a manual export run."""
    if appointment.status in {"cancelled", "canceled"}:
        return None
    settings = get_settings()
    occurred_at = appointment.created_at
    click_event = get_best_click_event(
        db,
        organization_id=appointment.organization_id,
        lead_id=lead.id,
        click_id_type="fbclid",
        occurred_at=occurred_at,
        window_days=settings.marketing_conversion_window_days,
    )
    if click_event is None or not click_event.fbclid:
        return None
    event_key = f"appointment_scheduled:{appointment.id}:meta:v1"
    existing = db.scalar(
        select(OfflineConversionExport.id).where(
            OfflineConversionExport.organization_id == appointment.organization_id,
            OfflineConversionExport.platform == "meta",
            OfflineConversionExport.event_key == event_key,
        )
    )
    if existing is not None:
        return None
    outcome = ConversionOutcome(
        event_name="appointment_scheduled",
        source_record_type="appointment",
        source_record_id=appointment.id,
        lead_id=lead.id,
        occurred_at=occurred_at,
    )
    snapshot = build_payload_snapshot(
        db,
        organization_id=appointment.organization_id,
        outcome=outcome,
        click_event=click_event,
        website_base_url=settings.marketing_website_base_url,
    )
    export = OfflineConversionExport(
        organization_id=appointment.organization_id,
        platform="meta",
        conversion_event_id=click_event.id,
        lead_id=lead.id,
        revenue_record_id=None,
        event_key=event_key,
        source_record_type="appointment",
        source_record_id=appointment.id,
        event_name="appointment_scheduled",
        occurred_at=occurred_at,
        attribution_model=ATTRIBUTION_MODEL,
        consent_basis=CONSENT_BASIS,
        click_id=click_event.fbclid,
        click_id_type="fbclid",
        value_cents=None,
        currency="USD",
        payload_hash=payload_hash(snapshot),
        payload_snapshot=snapshot,
        delivery_mode=settings.marketing_conversion_mode,
        status="pending",
        attempt_count=0,
        exported_at=None,
        last_error=None,
    )
    db.add(export)
    db.flush()
    return export


def get_marketing_overview(
    db: Session,
    principal: Principal,
    period_days: int | None = None,
) -> MarketingOverview:
    settings = get_settings()
    period_end_at = datetime.now(UTC)
    period_start_at = (
        period_end_at - timedelta(days=period_days) if period_days is not None else None
    )
    campaign_rows = build_campaign_rows(
        db,
        principal,
        start_at=period_start_at,
        end_at=period_end_at,
    )
    exports = db.scalars(
        select(OfflineConversionExport)
        .where(OfflineConversionExport.organization_id == principal.organization_id)
        .order_by(OfflineConversionExport.created_at.desc())
        .limit(100)
    ).all()
    campaigns = [
        row_to_performance(row)
        for row in sorted(
            campaign_rows.values(),
            key=lambda item: (
                -item.collected_revenue_cents,
                -item.contact_completed_leads,
                -item.address_leads,
                -item.leads_created,
                -item.form_submits,
                item.source,
            ),
        )
    ]
    pending_exports = count_pending_exports(
        db,
        principal,
        start_at=period_start_at,
        end_at=period_end_at,
    )
    public_funnel, web_vitals = get_public_experience_summary(
        db,
        principal,
        start_at=period_start_at,
        end_at=period_end_at,
    )
    previous_summary = None
    if period_start_at is not None and period_days is not None:
        previous_start = period_start_at - timedelta(days=period_days)
        previous_rows = build_campaign_rows(
            db,
            principal,
            start_at=previous_start,
            end_at=period_start_at,
        )
        previous_summary = summarize_rows(
            previous_rows,
            count_pending_exports(
                db,
                principal,
                start_at=previous_start,
                end_at=period_start_at,
            ),
        )
    return MarketingOverview(
        period_days=period_days,
        period_start_at=period_start_at,
        period_end_at=period_end_at,
        previous_summary=previous_summary,
        summary=summarize_rows(campaign_rows, pending_exports),
        public_funnel=public_funnel,
        web_vitals=web_vitals,
        measurement=get_measurement_summary(db, principal, settings),
        campaigns=campaigns[:100],
        offline_exports=[offline_export_to_read(export) for export in exports],
    )


def get_public_experience_summary(
    db: Session,
    principal: Principal,
    *,
    start_at: datetime | None,
    end_at: datetime | None,
) -> tuple[PublicFunnelSummary, list[WebVitalSummary]]:
    event_types = {
        "page_view",
        "offer_start",
        "form_start",
        "form_step_complete",
        "form_validation_error",
        "form_submit_attempt",
        "address_capture",
        "contact_complete",
        "form_submit",
        "form_submit_error",
        "form_abandon",
        "web_vital",
    }
    events = db.scalars(
        select(ConversionEvent).where(
            ConversionEvent.organization_id == principal.organization_id,
            ConversionEvent.event_type.in_(event_types),
            *period_conditions(ConversionEvent.created_at, start_at, end_at),
        )
    ).all()
    counts = Counter(event.event_type for event in events)
    step_completions: Counter[str] = Counter()
    vital_values: defaultdict[str, list[tuple[float, str]]] = defaultdict(list)
    for event in events:
        metadata = event.event_metadata or {}
        if event.event_type == "form_step_complete":
            step_key = metadata.get("step_key")
            if isinstance(step_key, str) and step_key in {
                "property",
                "situation",
                "details",
                "contact",
            }:
                step_completions[step_key] += 1
        elif event.event_type == "web_vital":
            metric = metadata.get("metric")
            value = metadata.get("value")
            rating = metadata.get("rating")
            if metric in {"LCP", "INP", "CLS"} and isinstance(value, (int, float)):
                vital_values[str(metric)].append((float(value), str(rating or "unknown")))

    starts = counts["form_start"]
    contact_completed_leads = counts["contact_complete"]
    submits = counts["form_submit"] + contact_completed_leads
    address_leads = counts["address_capture"]
    funnel = PublicFunnelSummary(
        page_views=counts["page_view"],
        offer_starts=counts["offer_start"],
        form_starts=starts,
        step_completions=dict(step_completions),
        validation_errors=counts["form_validation_error"],
        submit_attempts=counts["form_submit_attempt"],
        form_submits=submits,
        address_leads=address_leads,
        contact_completed_leads=contact_completed_leads,
        address_to_contact_rate_basis_points=(
            round(contact_completed_leads / address_leads * 10000) if address_leads else None
        ),
        submit_errors=counts["form_submit_error"],
        form_abandons=counts["form_abandon"],
        start_to_submit_rate_basis_points=(round(submits / starts * 10000) if starts else None),
    )
    vitals = []
    for metric in ("LCP", "INP", "CLS"):
        samples = vital_values.get(metric, [])
        if not samples:
            continue
        values = sorted(value for value, _ in samples)
        p75_index = max(0, min(len(values) - 1, (3 * len(values) - 1) // 4))
        good_count = sum(1 for _, rating in samples if rating == "good")
        vitals.append(
            WebVitalSummary(
                metric=metric,
                sample_count=len(samples),
                p75_value=values[p75_index],
                good_rate_basis_points=round(good_count / len(samples) * 10000),
            )
        )
    return funnel, vitals


def generate_offline_conversion_exports(
    db: Session,
    principal: Principal,
    settings: Settings | None = None,
) -> int:
    settings = settings or get_settings()
    created = 0
    for outcome in get_conversion_outcomes(db, principal):
        for platform, click_id_type in (("google_ads", "gclid"), ("meta", "fbclid")):
            click_event = get_best_click_event(
                db,
                organization_id=principal.organization_id,
                lead_id=outcome.lead_id,
                click_id_type=click_id_type,
                occurred_at=outcome.occurred_at,
                window_days=settings.marketing_conversion_window_days,
            )
            if click_event is None:
                continue
            click_id = getattr(click_event, click_id_type)
            if not click_id:
                continue
            event_key = f"{outcome.event_name}:{outcome.source_record_id}:{platform}:v1"
            existing = db.scalar(
                select(OfflineConversionExport.id).where(
                    OfflineConversionExport.organization_id == principal.organization_id,
                    OfflineConversionExport.platform == platform,
                    OfflineConversionExport.event_key == event_key,
                )
            )
            if existing is not None:
                continue
            snapshot = build_payload_snapshot(
                db,
                organization_id=principal.organization_id,
                outcome=outcome,
                click_event=click_event,
                website_base_url=settings.marketing_website_base_url,
            )
            db.add(
                OfflineConversionExport(
                    organization_id=principal.organization_id,
                    platform=platform,
                    conversion_event_id=click_event.id,
                    lead_id=outcome.lead_id,
                    revenue_record_id=outcome.revenue_record_id,
                    event_key=event_key,
                    source_record_type=outcome.source_record_type,
                    source_record_id=outcome.source_record_id,
                    event_name=outcome.event_name,
                    occurred_at=outcome.occurred_at,
                    attribution_model=ATTRIBUTION_MODEL,
                    consent_basis=CONSENT_BASIS,
                    click_id=click_id,
                    click_id_type=click_id_type,
                    value_cents=outcome.value_cents,
                    currency="USD",
                    payload_hash=payload_hash(snapshot),
                    payload_snapshot=snapshot,
                    delivery_mode=settings.marketing_conversion_mode,
                    status="pending",
                    attempt_count=0,
                    exported_at=None,
                    last_error=None,
                )
            )
            created += 1
    if created:
        db.add(
            ActivityEvent(
                organization_id=principal.organization_id,
                actor_user_id=principal.user_id,
                entity_type="marketing",
                entity_id=principal.organization_id,
                event_type="marketing.offline_exports_generated",
                summary=f"Generated {created} offline conversion export records.",
            )
        )
        db.add(
            AuditEvent(
                organization_id=principal.organization_id,
                actor_user_id=principal.user_id,
                actor_type="user",
                action="marketing.offline_exports_generate",
                entity_type="marketing",
                entity_id=principal.organization_id,
                previous_value=None,
                new_value={
                    "created": created,
                    "attribution_model": ATTRIBUTION_MODEL,
                    "window_days": settings.marketing_conversion_window_days,
                    "policy_version": MEASUREMENT_POLICY_VERSION,
                },
                reason="Prepared governed advertising conversion events",
            )
        )
    db.commit()
    return created


def get_conversion_outcomes(
    db: Session,
    principal: Principal,
) -> list[ConversionOutcome]:
    outcomes: list[ConversionOutcome] = []
    leads = db.scalars(
        select(Lead).where(
            Lead.organization_id == principal.organization_id,
            Lead.archived_at.is_(None),
            Lead.stage_key.in_(QUALIFIED_STAGES),
        )
    ).all()
    outcomes.extend(
        ConversionOutcome(
            event_name="qualified_lead",
            source_record_type="lead",
            source_record_id=lead.id,
            lead_id=lead.id,
            occurred_at=lead.updated_at,
        )
        for lead in leads
    )
    appointments = db.scalars(
        select(Appointment).where(
            Appointment.organization_id == principal.organization_id,
            Appointment.status.not_in({"cancelled", "canceled"}),
        )
    ).all()
    outcomes.extend(
        ConversionOutcome(
            event_name="appointment_scheduled",
            source_record_type="appointment",
            source_record_id=appointment.id,
            lead_id=appointment.lead_id,
            occurred_at=appointment.created_at,
        )
        for appointment in appointments
    )
    transactions = db.scalars(
        select(Transaction).where(
            Transaction.organization_id == principal.organization_id,
            Transaction.contract_executed_at.is_not(None),
        )
    ).all()
    outcomes.extend(
        ConversionOutcome(
            event_name="contract_signed",
            source_record_type="transaction",
            source_record_id=transaction.id,
            lead_id=transaction.lead_id,
            occurred_at=transaction.contract_executed_at,
        )
        for transaction in transactions
        if transaction.contract_executed_at is not None
    )
    revenue_records = db.scalars(
        select(RevenueRecord).where(
            RevenueRecord.organization_id == principal.organization_id,
            RevenueRecord.status == "collected",
            RevenueRecord.lead_id.is_not(None),
        )
    ).all()
    outcomes.extend(
        ConversionOutcome(
            event_name="funded_deal",
            source_record_type="revenue_record",
            source_record_id=revenue.id,
            lead_id=revenue.lead_id,
            occurred_at=revenue.received_at,
            value_cents=revenue.amount_cents,
            revenue_record_id=revenue.id,
        )
        for revenue in revenue_records
        if revenue.lead_id is not None
    )
    return sorted(outcomes, key=lambda item: item.occurred_at)


def build_payload_snapshot(
    db: Session,
    *,
    organization_id: UUID,
    outcome: ConversionOutcome,
    click_event: ConversionEvent,
    website_base_url: str,
) -> dict[str, object]:
    lead = db.scalar(
        select(Lead).where(
            Lead.organization_id == organization_id,
            Lead.id == outcome.lead_id,
        )
    )
    methods = (
        db.scalars(
            select(ContactMethod).where(
                ContactMethod.organization_id == organization_id,
                ContactMethod.contact_id == lead.contact_id,
            )
        ).all()
        if lead is not None
        else []
    )
    email_hashes = sorted(
        {
            sha256(normalize_email(method.normalized_value))
            for method in methods
            if method.method_type == "email" and normalize_email(method.normalized_value)
        }
    )
    phone_hashes = sorted(
        {
            sha256(normalize_phone(method.normalized_value))
            for method in methods
            if method.method_type == "phone" and normalize_phone(method.normalized_value)
        }
    )
    meta_context = (
        click_event.event_metadata.get("meta_browser_event")
        if isinstance(click_event.event_metadata, dict)
        else None
    )
    return {
        "policy_version": MEASUREMENT_POLICY_VERSION,
        "event_name": outcome.event_name,
        "occurred_at": outcome.occurred_at.isoformat(),
        # Do not manufacture a historical click time from event creation. Existing
        # records remain nullable because only the browser knows the original click.
        "click_captured_at": utc_isoformat(click_event.fbclid_captured_at),
        "fbclid": click_event.fbclid,
        "landing_page": absolute_landing_page(
            click_event.landing_page,
            website_base_url=website_base_url,
        ),
        "email_hashes": email_hashes,
        "phone_hashes": phone_hashes,
        "external_id_hash": sha256(f"{organization_id}:{outcome.lead_id}"),
        "client_ip_address": click_event.ip_address,
        "client_user_agent": click_event.user_agent,
        "fbc": meta_context.get("fbc") if isinstance(meta_context, dict) else None,
        "fbp": meta_context.get("fbp") if isinstance(meta_context, dict) else None,
    }


def process_next_marketing_conversion(
    db: Session,
    settings: Settings,
    client: MarketingConversionClient | None = None,
    *,
    organization_id: UUID | None = None,
) -> UUID | None:
    if settings.marketing_conversion_mode == "disabled":
        return None
    now = datetime.now(UTC)
    configured_platforms: list[str] = []
    if not settings.google_conversion_configuration_blockers:
        configured_platforms.append("google_ads")
    if not settings.meta_conversion_configuration_blockers:
        configured_platforms.append("meta")
    conditions: list[ColumnElement[bool]] = [
        or_(
            OfflineConversionExport.status.in_({"pending", "retry"}),
            and_(
                OfflineConversionExport.status == "blocked",
                OfflineConversionExport.platform.in_(configured_platforms),
            ),
        ),
        (
            OfflineConversionExport.next_attempt_at.is_(None)
            | (OfflineConversionExport.next_attempt_at <= now)
        ),
    ]
    if organization_id is not None:
        conditions.append(OfflineConversionExport.organization_id == organization_id)
    export = db.scalar(
        select(OfflineConversionExport)
        .where(*conditions)
        .order_by(OfflineConversionExport.occurred_at, OfflineConversionExport.created_at)
        .with_for_update(skip_locked=True)
    )
    if export is None:
        return None
    export.delivery_mode = settings.marketing_conversion_mode
    export.attempt_count += 1
    export.last_attempt_at = now
    previous_status = export.status
    occurred_at = export.occurred_at
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=UTC)
    if (
        settings.marketing_conversion_mode == "live"
        and export.platform == "meta"
        and occurred_at < now - timedelta(days=7)
    ):
        export.status = "exhausted"
        export.next_attempt_at = None
        export.last_error = "Meta rejects events more than 7 days after they occurred."
    elif settings.marketing_conversion_mode == "simulate":
        export.status = "simulated"
        export.exported_at = now
        export.next_attempt_at = None
        export.provider_response = {"simulated": True, "external_request_sent": False}
        export.last_error = None
    else:
        blockers = (
            settings.google_conversion_configuration_blockers
            if export.platform == "google_ads"
            else settings.meta_conversion_configuration_blockers
        )
        if blockers:
            export.status = "blocked"
            export.next_attempt_at = None
            export.last_error = f"Missing configuration: {', '.join(blockers)}"
        else:
            delivery_client = client or MarketingConversionClient(settings)
            try:
                result = delivery_client.deliver(export)
            except ConversionDeliveryError as exc:
                export.provider_response = exc.response
                export.provider_request_id = exc.request_id or export.provider_request_id
                export.last_error = str(exc)[:1000]
                if export.attempt_count >= settings.marketing_conversion_max_attempts:
                    export.status = "exhausted"
                    export.next_attempt_at = None
                else:
                    export.status = "retry"
                    export.next_attempt_at = now + timedelta(
                        seconds=(
                            settings.marketing_conversion_retry_base_seconds
                            * (2 ** (export.attempt_count - 1))
                        )
                    )
            else:
                export.status = "delivered"
                export.exported_at = now
                export.next_attempt_at = None
                export.provider_request_id = result.request_id
                export.provider_response = result.response
                export.last_error = None
            finally:
                if client is None:
                    delivery_client.close()
    db.add(
        AuditEvent(
            organization_id=export.organization_id,
            actor_user_id=None,
            actor_type="system",
            action="marketing.offline_conversion_delivery",
            entity_type="offline_conversion_export",
            entity_id=export.id,
            previous_value={"status": previous_status},
            new_value={
                "status": export.status,
                "attempt_count": export.attempt_count,
                "platform": export.platform,
                "provider_request_id": export.provider_request_id,
            },
            reason="Governed advertising conversion delivery attempt",
        )
    )
    db.commit()
    return export.id


def build_campaign_rows(
    db: Session,
    principal: Principal,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> dict[tuple[str, str, str], CampaignRow]:
    rows: dict[tuple[str, str, str], CampaignRow] = {}
    add_conversion_events(db, principal, rows, start_at, end_at)
    add_leads(db, principal, rows, start_at, end_at)
    add_revenue(db, principal, rows, start_at, end_at)
    add_spend(db, principal, rows, start_at, end_at)
    return rows


def add_conversion_events(
    db: Session,
    principal: Principal,
    rows: dict[tuple[str, str, str], CampaignRow],
    start_at: datetime | None,
    end_at: datetime | None,
) -> None:
    event_rows = db.execute(
        select(
            ConversionEvent.source,
            ConversionEvent.medium,
            ConversionEvent.campaign,
            ConversionEvent.event_type,
            func.count(ConversionEvent.id),
        )
        .where(
            ConversionEvent.organization_id == principal.organization_id,
            *period_conditions(ConversionEvent.created_at, start_at, end_at),
        )
        .group_by(
            ConversionEvent.source,
            ConversionEvent.medium,
            ConversionEvent.campaign,
            ConversionEvent.event_type,
        )
    ).all()
    for source, medium, campaign, event_type, count in event_rows:
        row = ensure_row(rows, source, medium, campaign)
        count_value = int(count)
        if event_type == "page_view":
            row.page_views += count_value
        elif event_type == "form_start":
            row.form_starts += count_value
        elif event_type == "form_abandon":
            row.form_abandons += count_value
        elif event_type == "address_capture":
            row.address_leads += count_value
        elif event_type == "contact_complete":
            row.form_submits += count_value
            row.contact_completed_leads += count_value
        elif event_type == "form_submit":
            row.form_submits += count_value
        elif event_type == "call_click":
            row.call_clicks += count_value


def add_leads(
    db: Session,
    principal: Principal,
    rows: dict[tuple[str, str, str], CampaignRow],
    start_at: datetime | None,
    end_at: datetime | None,
) -> None:
    canonical_touch_id = (
        select(AttributionTouch.id)
        .where(
            AttributionTouch.lead_id == Lead.id,
            AttributionTouch.organization_id == Lead.organization_id,
            AttributionTouch.touch_type == "lead_creation",
        )
        .order_by(AttributionTouch.created_at.asc(), AttributionTouch.id.asc())
        .limit(1)
        .correlate(Lead)
        .scalar_subquery()
    )
    lead_rows = db.execute(
        select(
            func.coalesce(AttributionTouch.source, Lead.source),
            AttributionTouch.medium,
            AttributionTouch.campaign,
            Lead.stage_key,
            func.count(Lead.id),
        )
        .select_from(Lead)
        .outerjoin(
            AttributionTouch,
            AttributionTouch.id == canonical_touch_id,
        )
        .where(
            Lead.organization_id == principal.organization_id,
            Lead.archived_at.is_(None),
            *period_conditions(Lead.created_at, start_at, end_at),
        )
        .group_by(
            func.coalesce(AttributionTouch.source, Lead.source),
            AttributionTouch.medium,
            AttributionTouch.campaign,
            Lead.stage_key,
        )
    ).all()
    for source, medium, campaign, stage_key, count in lead_rows:
        row = ensure_row(rows, source, medium, campaign)
        row.leads_created += int(count)
        if stage_key in {"under_contract", "closed"}:
            row.contracted_leads += int(count)


def add_revenue(
    db: Session,
    principal: Principal,
    rows: dict[tuple[str, str, str], CampaignRow],
    start_at: datetime | None,
    end_at: datetime | None,
) -> None:
    canonical_touch_id = (
        select(AttributionTouch.id)
        .where(
            AttributionTouch.lead_id == Lead.id,
            AttributionTouch.organization_id == Lead.organization_id,
            AttributionTouch.touch_type == "lead_creation",
        )
        .order_by(AttributionTouch.created_at.asc(), AttributionTouch.id.asc())
        .limit(1)
        .correlate(Lead)
        .scalar_subquery()
    )
    revenue_rows = db.execute(
        select(
            func.coalesce(AttributionTouch.source, Lead.source),
            AttributionTouch.medium,
            AttributionTouch.campaign,
            func.coalesce(func.sum(RevenueRecord.amount_cents), 0),
        )
        .join(Lead, Lead.id == RevenueRecord.lead_id)
        .outerjoin(
            AttributionTouch,
            AttributionTouch.id == canonical_touch_id,
        )
        .where(
            RevenueRecord.organization_id == principal.organization_id,
            RevenueRecord.status == "collected",
            *period_conditions(RevenueRecord.received_at, start_at, end_at),
        )
        .group_by(
            func.coalesce(AttributionTouch.source, Lead.source),
            AttributionTouch.medium,
            AttributionTouch.campaign,
        )
    ).all()
    for source, medium, campaign, revenue in revenue_rows:
        row = ensure_row(rows, source, medium, campaign)
        row.collected_revenue_cents += int(revenue)


def add_spend(
    db: Session,
    principal: Principal,
    rows: dict[tuple[str, str, str], CampaignRow],
    start_at: datetime | None,
    end_at: datetime | None,
) -> None:
    spend_rows = db.execute(
        select(
            MarketingSpend.source,
            MarketingSpend.campaign,
            func.coalesce(func.sum(MarketingSpend.amount_cents), 0),
        )
        .where(
            MarketingSpend.organization_id == principal.organization_id,
            *period_conditions(MarketingSpend.spend_month_at, start_at, end_at),
        )
        .group_by(MarketingSpend.source, MarketingSpend.campaign)
    ).all()
    for source, campaign, spend in spend_rows:
        target_source = source or "direct"
        target_campaign = campaign or "uncategorized"
        matching_keys = [
            key
            for key, row in rows.items()
            if row.source == target_source and row.campaign == target_campaign
        ]
        if not matching_keys:
            target = ensure_row(rows, source, None, campaign)
        elif len(matching_keys) == 1:
            target = rows[matching_keys[0]]
        else:
            # Spend is recorded only at source + campaign grain. Collapse multiple
            # media into one row rather than assigning the full spend to every row.
            target = CampaignRow(
                source=target_source,
                medium="mixed",
                campaign=target_campaign,
            )
            for key in matching_keys:
                merge_campaign_row(target, rows.pop(key))
            rows[(target_source, "mixed", target_campaign)] = target
        target.marketing_spend_cents += int(spend)


def merge_campaign_row(target: CampaignRow, source: CampaignRow) -> None:
    target.page_views += source.page_views
    target.form_starts += source.form_starts
    target.form_abandons += source.form_abandons
    target.form_submits += source.form_submits
    target.address_leads += source.address_leads
    target.contact_completed_leads += source.contact_completed_leads
    target.call_clicks += source.call_clicks
    target.leads_created += source.leads_created
    target.contracted_leads += source.contracted_leads
    target.collected_revenue_cents += source.collected_revenue_cents
    target.marketing_spend_cents += source.marketing_spend_cents


def get_best_click_event(
    db: Session,
    *,
    organization_id: UUID,
    lead_id: UUID,
    click_id_type: str,
    occurred_at: datetime,
    window_days: int,
) -> ConversionEvent | None:
    click_column = ConversionEvent.gclid if click_id_type == "gclid" else ConversionEvent.fbclid
    return db.scalar(
        select(ConversionEvent)
        .where(
            ConversionEvent.organization_id == organization_id,
            ConversionEvent.lead_id == lead_id,
            click_column.is_not(None),
            ConversionEvent.created_at <= occurred_at,
            ConversionEvent.created_at >= occurred_at - timedelta(days=window_days),
        )
        .order_by(ConversionEvent.created_at.desc())
    )


def ensure_row(
    rows: dict[tuple[str, str, str], CampaignRow],
    source: str | None,
    medium: str | None,
    campaign: str | None,
) -> CampaignRow:
    key = (source or "direct", medium or "unknown", campaign or "uncategorized")
    if key not in rows:
        rows[key] = CampaignRow(source=key[0], medium=key[1], campaign=key[2])
    return rows[key]


def row_to_performance(row: CampaignRow) -> MarketingCampaignPerformance:
    return MarketingCampaignPerformance(
        source=row.source,
        medium=row.medium,
        campaign=row.campaign,
        page_views=row.page_views,
        form_starts=row.form_starts,
        form_abandons=row.form_abandons,
        form_submits=row.form_submits,
        address_leads=row.address_leads,
        contact_completed_leads=row.contact_completed_leads,
        address_to_contact_rate_basis_points=safe_rate_basis_points(
            row.contact_completed_leads,
            row.address_leads,
        ),
        call_clicks=row.call_clicks,
        leads_created=row.leads_created,
        contracted_leads=row.contracted_leads,
        collected_revenue_cents=row.collected_revenue_cents,
        marketing_spend_cents=row.marketing_spend_cents,
        cost_per_lead_cents=safe_divide(row.marketing_spend_cents, row.leads_created),
        cost_per_address_lead_cents=safe_divide(
            row.marketing_spend_cents,
            row.address_leads,
        ),
        cost_per_contact_completed_lead_cents=safe_divide(
            row.marketing_spend_cents,
            row.contact_completed_leads,
        ),
        cost_per_contract_cents=safe_divide(row.marketing_spend_cents, row.contracted_leads),
        return_on_ad_spend_basis_points=safe_basis_points(
            row.collected_revenue_cents,
            row.marketing_spend_cents,
        ),
    )


def offline_export_to_read(export: OfflineConversionExport) -> OfflineConversionExportRead:
    return OfflineConversionExportRead(
        id=export.id,
        platform=export.platform,
        conversion_event_id=export.conversion_event_id,
        lead_id=export.lead_id,
        revenue_record_id=export.revenue_record_id,
        event_key=export.event_key,
        source_record_type=export.source_record_type,
        source_record_id=export.source_record_id,
        event_name=export.event_name,
        occurred_at=export.occurred_at,
        attribution_model=export.attribution_model,
        consent_basis=export.consent_basis,
        masked_click_id=mask_click_id(export.click_id),
        click_id_type=export.click_id_type,
        value_cents=export.value_cents,
        currency=export.currency,
        delivery_mode=export.delivery_mode,
        status=export.status,
        attempt_count=export.attempt_count,
        last_attempt_at=export.last_attempt_at,
        next_attempt_at=export.next_attempt_at,
        exported_at=export.exported_at,
        provider_request_id=export.provider_request_id,
        provider_accepted_count=provider_accepted_count(export.provider_response),
        provider_warnings=provider_warnings(export.provider_response),
        last_error=export.last_error,
        created_at=export.created_at,
    )


def get_measurement_summary(
    db: Session,
    principal: Principal,
    settings: Settings,
) -> MarketingMeasurementSummary:
    status_rows = db.execute(
        select(
            OfflineConversionExport.status,
            func.count(OfflineConversionExport.id),
        )
        .where(OfflineConversionExport.organization_id == principal.organization_id)
        .group_by(OfflineConversionExport.status)
    ).all()
    event_rows = db.execute(
        select(
            OfflineConversionExport.event_name,
            func.count(OfflineConversionExport.id),
        )
        .where(OfflineConversionExport.organization_id == principal.organization_id)
        .group_by(OfflineConversionExport.event_name)
    ).all()
    meta_lead_rows = db.execute(
        select(MetaLeadEvent.status, func.count(MetaLeadEvent.id))
        .where(MetaLeadEvent.organization_id == principal.organization_id)
        .group_by(MetaLeadEvent.status)
    ).all()
    staff_alert_rows = db.execute(
        select(StaffLeadAlert.status, func.count(StaffLeadAlert.id))
        .where(
            StaffLeadAlert.organization_id == principal.organization_id,
            StaffLeadAlert.source_type != "inbound_sms",
        )
        .group_by(StaffLeadAlert.status)
    ).all()
    meta_web_exports = db.scalars(
        select(OfflineConversionExport).where(
            OfflineConversionExport.organization_id == principal.organization_id,
            OfflineConversionExport.platform == "meta",
            OfflineConversionExport.attribution_model == META_WEB_ATTRIBUTION_MODEL,
            OfflineConversionExport.created_at
            >= datetime.now(UTC) - timedelta(days=META_MATCH_COVERAGE_WINDOW_DAYS),
        )
    ).all()
    meta_accepted = sum(
        1 for export in meta_web_exports if provider_accepted_count(export.provider_response) == 1
    )
    oldest_meta_pending_at = db.scalar(
        select(func.min(OfflineConversionExport.created_at)).where(
            OfflineConversionExport.organization_id == principal.organization_id,
            OfflineConversionExport.platform == "meta",
            OfflineConversionExport.status.in_({"pending", "retry"}),
        )
    )
    worker_readiness = get_worker_readiness(db, settings)
    heartbeat = db.scalar(
        select(WorkerHeartbeat).where(WorkerHeartbeat.service_name == COMMUNICATIONS_WORKER)
    )
    worker_metadata = heartbeat.worker_metadata if heartbeat and heartbeat.worker_metadata else {}
    event_counts = {
        "total": sum(int(count) for _, count in status_rows),
        **{str(status): int(count) for status, count in status_rows},
        **{f"event:{event_name}": int(count) for event_name, count in event_rows},
        "meta_leads:total": sum(int(count) for _, count in meta_lead_rows),
        **{f"meta_leads:{status}": int(count) for status, count in meta_lead_rows},
        "staff_alerts:total": sum(int(count) for _, count in staff_alert_rows),
        **{f"staff_alerts:{status}": int(count) for status, count in staff_alert_rows},
        "meta_web:total": len(meta_web_exports),
        "meta_web:provider_accepted": meta_accepted,
    }
    meta_blockers = list(settings.meta_conversion_configuration_blockers)
    return MarketingMeasurementSummary(
        mode=settings.marketing_conversion_mode,
        attribution_model=ATTRIBUTION_MODEL,
        attribution_window_days=settings.marketing_conversion_window_days,
        policy_version=MEASUREMENT_POLICY_VERSION,
        providers=[
            MarketingProviderReadiness(
                platform="google_ads",
                configured=not settings.google_conversion_configuration_blockers,
                blockers=list(settings.google_conversion_configuration_blockers),
            ),
            MarketingProviderReadiness(
                platform="meta",
                configured=not meta_blockers,
                blockers=meta_blockers,
                delivery_mode=settings.marketing_conversion_mode,
                test_mode_enabled=bool(settings.meta_test_event_code),
                pixel_id_fingerprint=meta_pixel_id_fingerprint(settings.meta_pixel_id),
                access_token_present=bool(settings.meta_conversions_access_token),
            ),
            MarketingProviderReadiness(
                platform="zapier_facebook_leads",
                configured=settings.zapier_facebook_leads_configured,
                blockers=list(settings.zapier_facebook_leads_configuration_blockers),
            ),
            MarketingProviderReadiness(
                platform="facebook_address_enrichment",
                configured=not settings.facebook_address_enrichment_configuration_blockers,
                blockers=list(settings.facebook_address_enrichment_configuration_blockers),
            ),
            MarketingProviderReadiness(
                platform="staff_lead_alert_sms",
                configured=not settings.staff_lead_alert_configuration_blockers,
                blockers=list(settings.staff_lead_alert_configuration_blockers),
            ),
        ],
        event_counts=event_counts,
        worker=MarketingWorkerReadiness(
            status=worker_readiness.status,
            required=worker_readiness.required,
            heartbeat_at=worker_readiness.heartbeat_at,
            consecutive_failures=worker_readiness.consecutive_failures,
            current_operation=worker_readiness.current_operation,
            marketing_conversion_mode=string_or_none(
                worker_metadata.get("marketing_conversion_mode")
            ),
            meta_pixel_id_fingerprint=string_or_none(
                worker_metadata.get("meta_pixel_id_fingerprint")
            ),
            meta_test_mode_enabled=bool_or_none(worker_metadata.get("meta_test_mode_enabled")),
            meta_configured=bool_or_none(worker_metadata.get("meta_configured")),
            meta_configuration_blockers=string_list(
                worker_metadata.get("meta_configuration_blockers")
            ),
            meta_access_token_present=bool_or_none(
                worker_metadata.get("meta_access_token_present")
            ),
        ),
        meta_match_coverage=build_meta_match_coverage(meta_web_exports),
        meta_match_coverage_window_days=META_MATCH_COVERAGE_WINDOW_DAYS,
        oldest_meta_pending_at=oldest_meta_pending_at,
    )


def build_meta_match_coverage(
    exports: Sequence[OfflineConversionExport],
) -> list[MetaMatchCoverage]:
    groups = [
        ("all", exports),
        *[
            (event_name, [export for export in exports if export.event_name == event_name])
            for event_name in ("ViewContent", "Lead", "Contact")
        ],
    ]
    result: list[MetaMatchCoverage] = []
    for event_name, group in groups:
        total = len(group)
        fbp_count = count_snapshot_value(group, "fbp")
        fbc_count = sum(1 for export in group if export_snapshot_has_fbc(export))
        client_ip_count = sum(1 for export in group if export_snapshot_has_client_ip(export))
        client_user_agent_count = count_snapshot_value(group, "client_user_agent")
        result.append(
            MetaMatchCoverage(
                event_name=event_name,
                total=total,
                fbp_count=fbp_count,
                fbc_count=fbc_count,
                client_ip_count=client_ip_count,
                client_user_agent_count=client_user_agent_count,
                fbp_basis_points=coverage_basis_points(fbp_count, total),
                fbc_basis_points=coverage_basis_points(fbc_count, total),
                client_ip_basis_points=coverage_basis_points(client_ip_count, total),
                client_user_agent_basis_points=coverage_basis_points(
                    client_user_agent_count, total
                ),
            )
        )
    return result


def count_snapshot_value(exports: Sequence[OfflineConversionExport], key: str) -> int:
    return sum(
        1
        for export in exports
        if isinstance(export.payload_snapshot.get(key), str)
        and str(export.payload_snapshot[key]).strip()
    )


def export_snapshot_has_fbc(export: OfflineConversionExport) -> bool:
    snapshot = export.payload_snapshot
    if isinstance(snapshot.get("fbc"), str) and str(snapshot["fbc"]).strip():
        return True
    return bool(
        isinstance(snapshot.get("fbclid"), str)
        and str(snapshot["fbclid"]).strip()
        and isinstance(snapshot.get("click_captured_at"), str)
        and str(snapshot["click_captured_at"]).strip()
    )


def export_snapshot_has_client_ip(export: OfflineConversionExport) -> bool:
    value = export.payload_snapshot.get("client_ip_address")
    return bool(
        isinstance(value, str)
        and value.strip()
        and value.strip().lower() not in {"unknown", "edge-unknown", "testclient"}
    )


def coverage_basis_points(count: int, total: int) -> int | None:
    return round(count / total * 10000) if total else None


def provider_accepted_count(response: dict[str, object] | None) -> int | None:
    if not isinstance(response, dict):
        return None
    value = response.get("events_received")
    return value if type(value) is int else None


def provider_warnings(response: dict[str, object] | None) -> list[str]:
    if not isinstance(response, dict):
        return []
    messages = response.get("messages")
    if not isinstance(messages, list):
        return []
    warnings: list[str] = []
    for item in messages[:10]:
        if isinstance(item, dict):
            message = item.get("message") or item.get("description")
            code = item.get("code")
            if isinstance(message, str) and message.strip():
                prefix = f"{code}: " if isinstance(code, (str, int)) else ""
                warnings.append(f"{prefix}{message.strip()}"[:300])
        elif isinstance(item, str) and item.strip():
            warnings.append(item.strip()[:300])
    return warnings


def string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def bool_or_none(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)][:20]


def utc_isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    normalized = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return normalized.isoformat()


def normalize_email(value: str) -> str:
    return value.strip().lower()


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) == 10:
        digits = f"1{digits}"
    return f"+{digits}" if 10 < len(digits) <= 15 else ""


def normalize_meta_name(value: str) -> str:
    """Normalize a name component to Meta's lowercase, unpunctuated matching form."""
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", ascii_value.lower())


def split_meta_person_name(value: str | None) -> tuple[str, str]:
    parts = value.strip().split() if value and value.strip() else []
    if not parts:
        return "", ""
    first_name = normalize_meta_name(parts[0])
    last_name = normalize_meta_name(parts[-1]) if len(parts) > 1 else ""
    return first_name, last_name


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def payload_hash(snapshot: dict[str, object]) -> str:
    encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    return sha256(encoded)


def absolute_landing_page(value: str | None, *, website_base_url: str) -> str:
    base_url = website_base_url.rstrip("/")
    if not value:
        return base_url
    if value.startswith(("https://", "http://")):
        return value
    return f"{base_url}/{value.lstrip('/')}"


def safe_meta_event_source_url(value: str | None, *, website_base_url: str) -> str:
    candidate = absolute_landing_page(value, website_base_url=website_base_url)
    candidate_url = urlparse(candidate)
    website_url = urlparse(website_base_url)
    candidate_host = (candidate_url.hostname or "").removeprefix("www.")
    website_host = (website_url.hostname or "").removeprefix("www.")
    if candidate_url.scheme in {"http", "https"} and candidate_host == website_host:
        return candidate
    return website_base_url.rstrip("/")


def mask_click_id(value: str) -> str:
    if len(value) <= 10:
        return value
    return f"{value[:6]}...{value[-4:]}"


def safe_divide(numerator: int, denominator: int) -> int | None:
    if denominator == 0:
        return None
    return round(numerator / denominator)


def safe_basis_points(revenue: int, spend: int) -> int | None:
    if spend == 0:
        return None
    return round(revenue / spend * 10000)


def safe_rate_basis_points(numerator: int, denominator: int) -> int | None:
    if denominator == 0:
        return None
    return round(numerator / denominator * 10000)


def summarize_rows(
    rows: dict[tuple[str, str, str], CampaignRow],
    pending_exports: int,
) -> MarketingSummary:
    total_spend = sum(row.marketing_spend_cents for row in rows.values())
    total_revenue = sum(row.collected_revenue_cents for row in rows.values())
    total_leads = sum(row.leads_created for row in rows.values())
    total_address_leads = sum(row.address_leads for row in rows.values())
    total_contact_completed_leads = sum(row.contact_completed_leads for row in rows.values())
    total_contracts = sum(row.contracted_leads for row in rows.values())
    return MarketingSummary(
        total_spend_cents=total_spend,
        collected_revenue_cents=total_revenue,
        leads_created=total_leads,
        address_leads=total_address_leads,
        contact_completed_leads=total_contact_completed_leads,
        address_to_contact_rate_basis_points=safe_rate_basis_points(
            total_contact_completed_leads,
            total_address_leads,
        ),
        contracted_leads=total_contracts,
        cost_per_lead_cents=safe_divide(total_spend, total_leads),
        cost_per_address_lead_cents=safe_divide(total_spend, total_address_leads),
        cost_per_contact_completed_lead_cents=safe_divide(
            total_spend,
            total_contact_completed_leads,
        ),
        cost_per_contract_cents=safe_divide(total_spend, total_contracts),
        return_on_ad_spend_basis_points=safe_basis_points(total_revenue, total_spend),
        pending_offline_exports=pending_exports,
    )


def count_pending_exports(
    db: Session,
    principal: Principal,
    start_at: datetime | None,
    end_at: datetime | None,
) -> int:
    return int(
        db.scalar(
            select(func.count(OfflineConversionExport.id)).where(
                OfflineConversionExport.organization_id == principal.organization_id,
                OfflineConversionExport.status.in_({"pending", "retry"}),
                *period_conditions(OfflineConversionExport.created_at, start_at, end_at),
            )
        )
        or 0
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
