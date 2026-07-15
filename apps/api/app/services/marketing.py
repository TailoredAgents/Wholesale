from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.models.foundation import (
    ActivityEvent,
    AttributionTouch,
    AuditEvent,
    ConversionEvent,
    Lead,
    MarketingSpend,
    OfflineConversionExport,
    RevenueRecord,
)
from app.schemas.marketing import (
    MarketingCampaignPerformance,
    MarketingOverview,
    MarketingSummary,
    OfflineConversionExportRead,
)


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


def get_marketing_overview(db: Session, principal: Principal) -> MarketingOverview:
    campaign_rows = build_campaign_rows(db, principal)
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
    total_spend = sum(row.marketing_spend_cents for row in campaign_rows.values())
    total_revenue = sum(row.collected_revenue_cents for row in campaign_rows.values())
    total_leads = sum(row.leads_created for row in campaign_rows.values())
    total_contracts = sum(row.contracted_leads for row in campaign_rows.values())
    return MarketingOverview(
        summary=MarketingSummary(
            total_spend_cents=total_spend,
            collected_revenue_cents=total_revenue,
            leads_created=total_leads,
            contracted_leads=total_contracts,
            cost_per_lead_cents=safe_divide(total_spend, total_leads),
            cost_per_contract_cents=safe_divide(total_spend, total_contracts),
            return_on_ad_spend_basis_points=safe_basis_points(total_revenue, total_spend),
            pending_offline_exports=sum(1 for export in exports if export.status == "pending"),
        ),
        campaigns=campaigns[:100],
        offline_exports=[offline_export_to_read(export) for export in exports],
    )


def generate_offline_conversion_exports(db: Session, principal: Principal) -> int:
    created = 0
    revenue_records = db.scalars(
        select(RevenueRecord).where(
            RevenueRecord.organization_id == principal.organization_id,
            RevenueRecord.status == "collected",
            RevenueRecord.lead_id.is_not(None),
        )
    ).all()
    for revenue in revenue_records:
        if revenue.lead_id is None:
            continue
        click_event = get_best_click_event(db, principal, revenue.lead_id)
        if click_event is None:
            continue
        platform = "google_ads" if click_event.gclid else "meta"
        click_id = click_event.gclid or click_event.fbclid
        click_id_type = "gclid" if click_event.gclid else "fbclid"
        if click_id is None:
            continue
        existing = db.scalar(
            select(OfflineConversionExport).where(
                OfflineConversionExport.organization_id == principal.organization_id,
                OfflineConversionExport.platform == platform,
                OfflineConversionExport.revenue_record_id == revenue.id,
            )
        )
        if existing is not None:
            continue
        db.add(
            OfflineConversionExport(
                organization_id=principal.organization_id,
                platform=platform,
                conversion_event_id=click_event.id,
                lead_id=revenue.lead_id,
                revenue_record_id=revenue.id,
                event_name="qualified_revenue",
                click_id=click_id,
                click_id_type=click_id_type,
                value_cents=revenue.amount_cents,
                currency="USD",
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
                new_value={"created": created},
                reason="Manual offline conversion export generation",
            )
        )
    db.commit()
    return created


def build_campaign_rows(
    db: Session,
    principal: Principal,
) -> dict[tuple[str, str, str], CampaignRow]:
    rows: dict[tuple[str, str, str], CampaignRow] = {}
    add_conversion_events(db, principal, rows)
    add_leads(db, principal, rows)
    add_revenue(db, principal, rows)
    add_spend(db, principal, rows)
    return rows


def add_conversion_events(
    db: Session,
    principal: Principal,
    rows: dict[tuple[str, str, str], CampaignRow],
) -> None:
    event_rows = db.execute(
        select(
            ConversionEvent.source,
            ConversionEvent.medium,
            ConversionEvent.campaign,
            ConversionEvent.event_type,
            func.count(ConversionEvent.id),
        )
        .where(ConversionEvent.organization_id == principal.organization_id)
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
        .where(Lead.organization_id == principal.organization_id)
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
) -> None:
    spend_rows = db.execute(
        select(
            MarketingSpend.source,
            MarketingSpend.campaign,
            func.coalesce(func.sum(MarketingSpend.amount_cents), 0),
        )
        .where(MarketingSpend.organization_id == principal.organization_id)
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
) -> ConversionEvent | None:
    return db.scalar(
        select(ConversionEvent)
        .where(
            ConversionEvent.organization_id == principal.organization_id,
            ConversionEvent.lead_id == lead_id,
            (ConversionEvent.gclid.is_not(None) | ConversionEvent.fbclid.is_not(None)),
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
        event_name=export.event_name,
        click_id=export.click_id,
        click_id_type=export.click_id_type,
        value_cents=export.value_cents,
        currency=export.currency,
        status=export.status,
        attempt_count=export.attempt_count,
        exported_at=export.exported_at,
        last_error=export.last_error,
        created_at=export.created_at,
    )


def safe_divide(numerator: int, denominator: int) -> int | None:
    if denominator == 0:
        return None
    return round(numerator / denominator)


def safe_basis_points(revenue: int, spend: int) -> int | None:
    if spend == 0:
        return None
    return round(revenue / spend * 10000)
