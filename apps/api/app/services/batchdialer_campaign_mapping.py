from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.domain.assets import AssetClass
from app.domain.rbac import PermissionKeys
from app.models.foundation import (
    ApprovalRequest,
    AuditEvent,
    BatchDialerCampaign,
    Lead,
    ProspectingProviderEvent,
)
from app.schemas.prospecting import (
    BatchDialerCampaignMappingListRead,
    BatchDialerCampaignMappingRead,
    BatchDialerCampaignMappingUpdateRead,
)

PROVIDER = "batchdialer"
QUALIFICATION_REVIEW_REQUEST_TYPE = "batchdialer_lead_qualification"
MAPPING_REVIEW_REASON_CODES = frozenset(
    {"campaign_asset_unmapped", "campaign_asset_invalid"}
)
MISMATCH_SAMPLE_LIMIT = 25


@dataclass
class _HistoricalCampaignFacts:
    lead_count: int = 0
    mismatch_count: int = 0
    mismatch_sample_lead_ids: list[UUID] = field(default_factory=list)


def list_batchdialer_campaign_mappings(
    db: Session,
    principal: Principal,
) -> BatchDialerCampaignMappingListRead:
    _require_manager(principal)
    campaigns = list(
        db.scalars(
            select(BatchDialerCampaign)
            .where(BatchDialerCampaign.organization_id == principal.organization_id)
            .order_by(
                BatchDialerCampaign.is_active.desc(),
                BatchDialerCampaign.name,
                BatchDialerCampaign.provider_campaign_id,
            )
        ).all()
    )
    historical = _historical_campaign_facts(db, principal.organization_id, campaigns)
    return BatchDialerCampaignMappingListRead(
        items=[
            _mapping_read(campaign, historical.get(campaign.provider_campaign_id))
            for campaign in campaigns
        ]
    )


def update_batchdialer_campaign_mapping(
    db: Session,
    principal: Principal,
    *,
    mapping_id: UUID,
    asset_class: AssetClass | None,
) -> BatchDialerCampaignMappingUpdateRead | None:
    _require_manager(principal)
    campaign = db.scalar(
        select(BatchDialerCampaign)
        .where(
            BatchDialerCampaign.organization_id == principal.organization_id,
            BatchDialerCampaign.id == mapping_id,
        )
        .with_for_update(of=BatchDialerCampaign)
    )
    if campaign is None:
        return None

    previous_asset_class = campaign.asset_class
    mapping_changed = previous_asset_class != asset_class
    now = datetime.now(UTC)
    if mapping_changed or (asset_class is not None and campaign.asset_class_mapped_at is None):
        campaign.asset_class = asset_class
        campaign.asset_class_mapped_by_user_id = principal.user_id
        campaign.asset_class_mapped_at = now

    requeued_event_ids = (
        _requeue_mapping_blocked_events(
            db,
            organization_id=principal.organization_id,
            provider_campaign_id=campaign.provider_campaign_id,
            now=now,
        )
        if asset_class is not None
        else []
    )
    if mapping_changed or requeued_event_ids:
        if previous_asset_class is None and asset_class is not None:
            action = "prospecting.batchdialer_campaign_asset_mapping_set"
        elif asset_class is None:
            action = "prospecting.batchdialer_campaign_asset_mapping_cleared"
        elif mapping_changed:
            action = "prospecting.batchdialer_campaign_asset_mapping_changed"
        else:
            action = "prospecting.batchdialer_campaign_asset_mapping_reapplied"
        db.add(
            AuditEvent(
                organization_id=principal.organization_id,
                actor_user_id=principal.user_id,
                actor_type="user",
                action=action,
                entity_type="batchdialer_campaign",
                entity_id=campaign.id,
                previous_value={
                    "provider_campaign_id": campaign.provider_campaign_id,
                    "asset_class": previous_asset_class,
                },
                new_value={
                    "provider_campaign_id": campaign.provider_campaign_id,
                    "asset_class": asset_class,
                    "requeued_event_count": len(requeued_event_ids),
                },
                reason="BatchDialer campaign asset mapping updated",
            )
        )

    db.commit()
    db.refresh(campaign)
    historical = _historical_campaign_facts(
        db,
        principal.organization_id,
        [campaign],
    )
    return BatchDialerCampaignMappingUpdateRead(
        item=_mapping_read(campaign, historical.get(campaign.provider_campaign_id)),
        requeued_event_count=len(requeued_event_ids),
    )


def _requeue_mapping_blocked_events(
    db: Session,
    *,
    organization_id: UUID,
    provider_campaign_id: str,
    now: datetime,
) -> list[UUID]:
    candidates = list(
        db.scalars(
            select(ProspectingProviderEvent)
            .where(
                ProspectingProviderEvent.organization_id == organization_id,
                ProspectingProviderEvent.provider == PROVIDER,
                ProspectingProviderEvent.event_type == "cdr.observed",
                ProspectingProviderEvent.processing_status == "quarantined",
            )
            .with_for_update(of=ProspectingProviderEvent)
        ).all()
    )
    requeued: list[ProspectingProviderEvent] = []
    for event in candidates:
        payload = event.payload if isinstance(event.payload, dict) else {}
        result = payload.get("_stonegate")
        result = result if isinstance(result, dict) else {}
        qualification = result.get("qualification")
        qualification = qualification if isinstance(qualification, dict) else {}
        if qualification.get("reason_code") not in MAPPING_REVIEW_REASON_CODES:
            continue
        cdr = payload.get("cdr")
        cdr = cdr if isinstance(cdr, dict) else {}
        provider_campaign = cdr.get("campaign")
        provider_campaign = provider_campaign if isinstance(provider_campaign, dict) else {}
        if str(provider_campaign.get("id") or "").strip() != provider_campaign_id:
            continue
        event.processing_status = "pending"
        event.retry_count = 0
        event.processed_at = None
        event.error_message = None
        event.payload = {
            **payload,
            "_stonegate": {
                **result,
                "outcome": "awaiting_campaign_asset_reprocessing",
                "campaign_asset_requeued_at": now.isoformat(),
            },
        }
        requeued.append(event)

    if not requeued:
        return []
    requeued_ids = [event.id for event in requeued]
    approvals = list(
        db.scalars(
            select(ApprovalRequest)
            .where(
                ApprovalRequest.organization_id == organization_id,
                ApprovalRequest.request_type == QUALIFICATION_REVIEW_REQUEST_TYPE,
                ApprovalRequest.entity_type == "prospecting_provider_event",
                ApprovalRequest.entity_id.in_(requeued_ids),
                ApprovalRequest.status == "pending",
            )
            .with_for_update(of=ApprovalRequest)
        ).all()
    )
    for approval in approvals:
        approval.status = "cancelled"
        approval.decision_notes = (
            "The campaign asset mapping was supplied; the provider event was requeued."
        )
        approval.decided_at = now
    return requeued_ids


def _historical_campaign_facts(
    db: Session,
    organization_id: UUID,
    campaigns: list[BatchDialerCampaign],
) -> dict[str, _HistoricalCampaignFacts]:
    asset_class_by_campaign_id = {
        campaign.provider_campaign_id: campaign.asset_class for campaign in campaigns
    }
    if not asset_class_by_campaign_id:
        return {}

    facts: defaultdict[str, _HistoricalCampaignFacts] = defaultdict(
        _HistoricalCampaignFacts
    )
    provider_campaign_id_expression = Lead.qualification_context["batchdialer"][
        "campaign_id"
    ].as_string()
    count_rows = db.execute(
        select(
            provider_campaign_id_expression.label("provider_campaign_id"),
            Lead.asset_class,
            func.count(Lead.id).label("lead_count"),
        )
        .where(
            Lead.organization_id == organization_id,
            provider_campaign_id_expression.in_(tuple(asset_class_by_campaign_id)),
        )
        .group_by(provider_campaign_id_expression, Lead.asset_class)
    ).all()
    for provider_campaign_id, lead_asset_class, lead_count in count_rows:
        provider_campaign_id = str(provider_campaign_id or "").strip()
        campaign_facts = facts[provider_campaign_id]
        campaign_facts.lead_count += int(lead_count or 0)
        mapped_asset_class = asset_class_by_campaign_id[provider_campaign_id]
        if mapped_asset_class is None or lead_asset_class == mapped_asset_class:
            continue
        campaign_facts.mismatch_count += int(lead_count or 0)

    mismatch_conditions = [
        and_(
            provider_campaign_id_expression == provider_campaign_id,
            Lead.asset_class != mapped_asset_class,
        )
        for provider_campaign_id, mapped_asset_class in asset_class_by_campaign_id.items()
        if mapped_asset_class is not None
    ]
    if mismatch_conditions:
        ranked_mismatches = (
            select(
                Lead.id.label("lead_id"),
                provider_campaign_id_expression.label("provider_campaign_id"),
                func.row_number()
                .over(
                    partition_by=provider_campaign_id_expression,
                    order_by=[Lead.created_at.desc(), Lead.id],
                )
                .label("sample_rank"),
            )
            .where(
                Lead.organization_id == organization_id,
                or_(*mismatch_conditions),
            )
            .subquery()
        )
        sample_rows = db.execute(
            select(
                ranked_mismatches.c.provider_campaign_id,
                ranked_mismatches.c.lead_id,
            )
            .where(ranked_mismatches.c.sample_rank <= MISMATCH_SAMPLE_LIMIT)
            .order_by(
                ranked_mismatches.c.provider_campaign_id,
                ranked_mismatches.c.sample_rank,
            )
        ).all()
        for provider_campaign_id, lead_id in sample_rows:
            facts[str(provider_campaign_id)].mismatch_sample_lead_ids.append(lead_id)
    return dict(facts)


def _mapping_read(
    campaign: BatchDialerCampaign,
    historical: _HistoricalCampaignFacts | None,
) -> BatchDialerCampaignMappingRead:
    historical = historical or _HistoricalCampaignFacts()
    return BatchDialerCampaignMappingRead(
        id=campaign.id,
        provider_campaign_id=campaign.provider_campaign_id,
        provider_campaign_name=campaign.name,
        provider_status=campaign.status,
        is_active=campaign.is_active,
        asset_class=cast(AssetClass | None, campaign.asset_class),
        asset_class_mapped_at=campaign.asset_class_mapped_at,
        asset_class_mapped_by_user_id=campaign.asset_class_mapped_by_user_id,
        last_seen_at=campaign.last_seen_at,
        historical_lead_count=historical.lead_count,
        historical_asset_mismatch_count=historical.mismatch_count,
        historical_asset_mismatch_sample_lead_ids=historical.mismatch_sample_lead_ids,
    )


def _require_manager(principal: Principal) -> None:
    if PermissionKeys.MANAGE_ACQUISITION_OPERATIONS not in principal.permission_keys:
        raise PermissionError("Acquisition manager permission is required.")
