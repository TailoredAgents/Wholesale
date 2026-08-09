from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.foundation import (
    LandOfferPolicyVersion,
    LandValuationAnalysis,
    Property,
    PropertyIntelligenceSnapshot,
)


def active_land_offer_policy_id(db: Session, organization_id: UUID) -> UUID | None:
    return db.scalar(
        select(LandOfferPolicyVersion.id)
        .where(
            LandOfferPolicyVersion.organization_id == organization_id,
            LandOfferPolicyVersion.status == "active",
        )
        .order_by(LandOfferPolicyVersion.version_number.desc())
    )


def current_land_analysis_reasons(
    analysis: LandValuationAnalysis,
    *,
    property_record: Property | None,
    current_snapshot: PropertyIntelligenceSnapshot | None,
    current_identity_signature: str | None,
    active_policy_id: UUID | None,
    now: datetime | None = None,
) -> list[str]:
    """Explain why saved Land guidance is not safe to present as current."""
    reasons: list[str] = []
    if property_record is None or analysis.property_id != property_record.id:
        reasons.append(
            "The saved analysis belongs to a different property record. Refresh Land research."
        )
    if current_snapshot is None:
        reasons.append(
            "The property has no current Land research snapshot. Refresh Land research."
        )
    else:
        if analysis.property_snapshot_id != current_snapshot.id:
            reasons.append(
                "The property research snapshot changed after this analysis. Run a new Land "
                "valuation."
            )
        saved_signature = str(
            analysis.subject_snapshot.get("property_identity_signature") or ""
        )
        if (
            not current_identity_signature
            or current_snapshot.address_signature != current_identity_signature
            or saved_signature != current_identity_signature
        ):
            reasons.append(
                "The property identity changed after this analysis. Refresh Land research and "
                "run a new valuation."
            )
        current_time = now or datetime.now(UTC)
        expires_at = _as_utc(current_snapshot.expires_at)
        if expires_at <= _as_utc(current_time):
            reasons.append(
                "The saved Land research snapshot has expired. Refresh research before using "
                "offer guidance."
            )
    if analysis.policy_version_id != active_policy_id:
        reasons.append(
            "The active Land offer policy changed after this analysis. Review the saved evidence "
            "under the current policy."
        )
    return list(dict.fromkeys(reasons))


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
