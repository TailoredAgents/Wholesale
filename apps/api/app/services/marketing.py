import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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
    OfflineConversionExport,
    RevenueRecord,
    Transaction,
)
from app.schemas.marketing import (
    MarketingCampaignPerformance,
    MarketingMeasurementSummary,
    MarketingOverview,
    MarketingProviderReadiness,
    MarketingSummary,
    OfflineConversionExportRead,
    PublicFunnelSummary,
    WebVitalSummary,
)

ATTRIBUTION_MODEL = "last_eligible_platform_click"
MEASUREMENT_POLICY_VERSION = "stonegate-marketing-measurement-v1"
CONSENT_BASIS = "privacy_notice_first_party_measurement"
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
    submits = counts["form_submit"]
    funnel = PublicFunnelSummary(
        page_views=counts["page_view"],
        offer_starts=counts["offer_start"],
        form_starts=starts,
        step_completions=dict(step_completions),
        validation_errors=counts["form_validation_error"],
        submit_attempts=counts["form_submit_attempt"],
        form_submits=submits,
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
                principal,
                outcome.lead_id,
                click_id_type=click_id_type,
                occurred_at=outcome.occurred_at,
                window_days=settings.marketing_conversion_window_days,
            )
            if click_event is None:
                continue
            click_id = getattr(click_event, click_id_type)
            if not click_id:
                continue
            event_key = (
                f"{outcome.event_name}:{outcome.source_record_id}:{platform}:v1"
            )
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
                principal,
                outcome,
                click_event,
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
    principal: Principal,
    outcome: ConversionOutcome,
    click_event: ConversionEvent,
) -> dict[str, object]:
    lead = db.scalar(
        select(Lead).where(
            Lead.organization_id == principal.organization_id,
            Lead.id == outcome.lead_id,
        )
    )
    methods = (
        db.scalars(
            select(ContactMethod).where(
                ContactMethod.organization_id == principal.organization_id,
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
    return {
        "policy_version": MEASUREMENT_POLICY_VERSION,
        "event_name": outcome.event_name,
        "occurred_at": outcome.occurred_at.isoformat(),
        "click_captured_at": click_event.created_at.isoformat(),
        "landing_page": absolute_landing_page(click_event.landing_page),
        "email_hashes": email_hashes,
        "phone_hashes": phone_hashes,
        "external_id_hash": sha256(
            f"{principal.organization_id}:{outcome.lead_id}"
        ),
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
    if settings.marketing_conversion_mode == "simulate":
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
            and_(
                AttributionTouch.lead_id == Lead.id,
                AttributionTouch.organization_id == Lead.organization_id,
                AttributionTouch.touch_type == "lead_creation",
            ),
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
            and_(
                AttributionTouch.lead_id == Lead.id,
                AttributionTouch.organization_id == Lead.organization_id,
                AttributionTouch.touch_type == "lead_creation",
            ),
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
        matching_rows = [
            row
            for row in rows.values()
            if row.source == (source or "direct")
            and row.campaign == (campaign or "uncategorized")
        ]
        if not matching_rows:
            matching_rows = [ensure_row(rows, source, None, campaign)]
        for row in matching_rows:
            row.marketing_spend_cents += int(spend)


def get_best_click_event(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    *,
    click_id_type: str,
    occurred_at: datetime,
    window_days: int,
) -> ConversionEvent | None:
    click_column = (
        ConversionEvent.gclid if click_id_type == "gclid" else ConversionEvent.fbclid
    )
    return db.scalar(
        select(ConversionEvent)
        .where(
            ConversionEvent.organization_id == principal.organization_id,
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
        call_clicks=row.call_clicks,
        leads_created=row.leads_created,
        contracted_leads=row.contracted_leads,
        collected_revenue_cents=row.collected_revenue_cents,
        marketing_spend_cents=row.marketing_spend_cents,
        cost_per_lead_cents=safe_divide(row.marketing_spend_cents, row.leads_created),
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
    event_counts = {
        "total": sum(int(count) for _, count in status_rows),
        **{str(status): int(count) for status, count in status_rows},
        **{f"event:{event_name}": int(count) for event_name, count in event_rows},
    }
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
                configured=not settings.meta_conversion_configuration_blockers,
                blockers=list(settings.meta_conversion_configuration_blockers),
            ),
        ],
        event_counts=event_counts,
    )


def normalize_email(value: str) -> str:
    return value.strip().lower()


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) == 10:
        digits = f"1{digits}"
    return f"+{digits}" if 10 < len(digits) <= 15 else ""


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def payload_hash(snapshot: dict[str, object]) -> str:
    encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    return sha256(encoded)


def absolute_landing_page(value: str | None) -> str:
    if not value:
        return "https://www.stonegatehomebuyer.com"
    if value.startswith(("https://", "http://")):
        return value
    return f"https://www.stonegatehomebuyer.com/{value.lstrip('/')}"


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


def summarize_rows(
    rows: dict[tuple[str, str, str], CampaignRow],
    pending_exports: int,
) -> MarketingSummary:
    total_spend = sum(row.marketing_spend_cents for row in rows.values())
    total_revenue = sum(row.collected_revenue_cents for row in rows.values())
    total_leads = sum(row.leads_created for row in rows.values())
    total_contracts = sum(row.contracted_leads for row in rows.values())
    return MarketingSummary(
        total_spend_cents=total_spend,
        collected_revenue_cents=total_revenue,
        leads_created=total_leads,
        contracted_leads=total_contracts,
        cost_per_lead_cents=safe_divide(total_spend, total_leads),
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
