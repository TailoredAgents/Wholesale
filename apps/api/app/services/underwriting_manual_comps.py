from datetime import UTC, date, datetime
from typing import Any, Literal, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.models.foundation import (
    ActivityEvent,
    AuditEvent,
    Lead,
    Property,
    UnderwritingManualComparable,
    UnderwritingMarketAnalysis,
)
from app.schemas.leads import (
    ManualComparableSource,
    UnderwritingManualComparableCreate,
    UnderwritingManualComparableRead,
)
from app.services.property_validation import canonical_address_key


def list_manual_comparables(
    db: Session,
    principal: Principal,
    lead_id: UUID,
) -> list[UnderwritingManualComparableRead] | None:
    lead = scoped_lead(db, principal, lead_id)
    if lead is None:
        return None
    records = db.scalars(
        select(UnderwritingManualComparable)
        .where(
            UnderwritingManualComparable.organization_id == principal.organization_id,
            UnderwritingManualComparable.lead_id == lead.id,
            UnderwritingManualComparable.status == "active",
        )
        .order_by(
            UnderwritingManualComparable.sale_date.desc(),
            UnderwritingManualComparable.created_at.desc(),
        )
    ).all()
    return [manual_comparable_to_read(record) for record in records]


def create_manual_comparable(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    payload: UnderwritingManualComparableCreate,
) -> UnderwritingManualComparableRead | None:
    lead = scoped_lead(db, principal, lead_id)
    if lead is None:
        return None
    property_record = db.get(Property, lead.property_id)
    if property_record is None:
        raise ValueError("Lead is missing a property record.")
    if payload.sale_date > datetime.now(UTC).date():
        raise ValueError("A comparable sale date cannot be in the future.")
    if payload.condition_classification != "unknown" and not clean(
        payload.condition_evidence
    ):
        raise ValueError(
            "Condition evidence is required when a manual sale is classified as as-is or renovated."
        )

    normalized_key = canonical_address_key(
        payload.street_address,
        payload.city,
        payload.state,
        payload.postal_code,
    )
    subject_key = property_record.normalized_address_key or canonical_address_key(
        property_record.street_address,
        property_record.city,
        property_record.state,
        property_record.postal_code,
    )
    if normalized_key == subject_key:
        raise ValueError("The subject property cannot be entered as its own comparable sale.")
    duplicate = db.scalar(
        select(UnderwritingManualComparable).where(
            UnderwritingManualComparable.organization_id == principal.organization_id,
            UnderwritingManualComparable.lead_id == lead.id,
            UnderwritingManualComparable.status == "active",
            UnderwritingManualComparable.normalized_address_key == normalized_key,
            UnderwritingManualComparable.sale_date == payload.sale_date,
        )
    )
    if duplicate is not None:
        raise ValueError("That address and sale date are already saved as a manual comparable.")
    if latest_provider_sale_is_duplicate(
        db,
        principal,
        lead,
        normalized_address_key=normalized_key,
        sale_date=payload.sale_date,
    ):
        raise ValueError(
            "That closed sale already exists in the latest provider evidence and does not need "
            "manual entry."
        )

    formatted_address = (
        f"{payload.street_address.strip()}, {payload.city.strip()}, "
        f"{payload.state.strip().upper()} {payload.postal_code.strip()}"
    )
    record = UnderwritingManualComparable(
        organization_id=principal.organization_id,
        lead_id=lead.id,
        property_id=lead.property_id,
        created_by_user_id=principal.user_id,
        status="active",
        street_address=payload.street_address.strip(),
        city=payload.city.strip(),
        state=payload.state.strip().upper(),
        postal_code=payload.postal_code.strip(),
        formatted_address=formatted_address,
        normalized_address_key=normalized_key,
        sale_date=payload.sale_date,
        sale_price_cents=payload.sale_price_cents,
        property_type=payload.property_type.strip(),
        bedrooms=payload.bedrooms,
        bathrooms_hundredths=(
            round(payload.bathrooms * 100) if payload.bathrooms is not None else None
        ),
        square_footage=payload.square_footage,
        year_built=payload.year_built,
        lot_size=payload.lot_size,
        distance_hundredths=(
            round(payload.distance_miles * 100)
            if payload.distance_miles is not None
            else None
        ),
        subdivision=clean(payload.subdivision),
        condition_classification=payload.condition_classification,
        condition_evidence=clean(payload.condition_evidence),
        source_type=payload.source_type,
        source_reference=payload.source_reference.strip(),
        source_url=clean(payload.source_url),
        verification_notes=payload.verification_notes.strip(),
    )
    db.add(record)
    db.flush()
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            event_type="underwriting.manual_comparable.create",
            summary=(
                f"Verified manual sale added for {formatted_address} at "
                f"${record.sale_price_cents / 100:,.0f}."
            ),
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="underwriting.manual_comparable.create",
            entity_type="underwriting_manual_comparable",
            entity_id=record.id,
            previous_value=None,
            new_value=manual_comparable_audit_value(record),
            reason="Verified closed-sale evidence entered manually",
        )
    )
    db.commit()
    db.refresh(record)
    return manual_comparable_to_read(record)


def void_manual_comparable(
    db: Session,
    principal: Principal,
    lead_id: UUID,
    comparable_id: UUID,
) -> bool | None:
    lead = scoped_lead(db, principal, lead_id)
    if lead is None:
        return None
    record = db.scalar(
        select(UnderwritingManualComparable).where(
            UnderwritingManualComparable.id == comparable_id,
            UnderwritingManualComparable.organization_id == principal.organization_id,
            UnderwritingManualComparable.lead_id == lead.id,
            UnderwritingManualComparable.status == "active",
        )
    )
    if record is None:
        return False
    previous = manual_comparable_audit_value(record)
    record.status = "voided"
    record.voided_at = datetime.now(UTC)
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            event_type="underwriting.manual_comparable.void",
            summary=f"Manual sale removed from future analyses: {record.formatted_address}.",
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="underwriting.manual_comparable.void",
            entity_type="underwriting_manual_comparable",
            entity_id=record.id,
            previous_value=previous,
            new_value=manual_comparable_audit_value(record),
            reason="Manual comparable removed from future analyses",
        )
    )
    db.commit()
    return True


def resolve_manual_comparable_records(
    db: Session,
    principal: Principal,
    lead: Lead,
    requested_ids: list[UUID] | None,
    *,
    source_analysis: UnderwritingMarketAnalysis | None,
) -> tuple[list[dict[str, Any]], list[UUID]]:
    effective_ids = requested_ids
    if effective_ids is None and source_analysis is not None:
        inherited = (source_analysis.analysis_metadata or {}).get("manual_comp_ids")
        if isinstance(inherited, list):
            effective_ids = []
            for value in inherited:
                try:
                    effective_ids.append(UUID(str(value)))
                except (TypeError, ValueError):
                    continue

    query = select(UnderwritingManualComparable).where(
        UnderwritingManualComparable.organization_id == principal.organization_id,
        UnderwritingManualComparable.lead_id == lead.id,
        UnderwritingManualComparable.status == "active",
    )
    if effective_ids is not None:
        unique_ids = list(dict.fromkeys(effective_ids))
        if not unique_ids:
            return [], []
        records = db.scalars(query.where(UnderwritingManualComparable.id.in_(unique_ids))).all()
        by_id = {record.id: record for record in records}
        missing = [record_id for record_id in unique_ids if record_id not in by_id]
        if missing:
            raise ValueError(
                "One or more selected manual comparables are unavailable for this lead."
            )
        ordered = [by_id[record_id] for record_id in unique_ids]
    else:
        ordered = list(
            db.scalars(
                query.order_by(
                    UnderwritingManualComparable.sale_date.desc(),
                    UnderwritingManualComparable.created_at.desc(),
                )
            ).all()
        )
    return [manual_comparable_to_sale_record(record) for record in ordered], [
        record.id for record in ordered
    ]


def merge_verified_manual_sales(
    provider_records: list[dict[str, Any]],
    manual_records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    merged = list(provider_records)
    seen = {sale_identity(record) for record in provider_records}
    duplicate_ids: list[str] = []
    for record in manual_records:
        identity = sale_identity(record)
        if identity in seen:
            manual_id = clean(record.get("_stonegateManualComparableId"))
            if manual_id:
                duplicate_ids.append(manual_id)
            continue
        seen.add(identity)
        merged.append(record)
    return merged, duplicate_ids


def manual_comparable_to_sale_record(
    record: UnderwritingManualComparable,
) -> dict[str, Any]:
    return {
        "id": f"manual:{record.id}",
        "formattedAddress": record.formatted_address,
        "addressLine1": record.street_address,
        "city": record.city,
        "state": record.state,
        "zipCode": record.postal_code,
        "propertyType": record.property_type,
        "lastSalePrice": round(record.sale_price_cents / 100),
        "lastSaleDate": record.sale_date.isoformat(),
        "bedrooms": record.bedrooms,
        "bathrooms": (
            record.bathrooms_hundredths / 100
            if record.bathrooms_hundredths is not None
            else None
        ),
        "squareFootage": record.square_footage,
        "yearBuilt": record.year_built,
        "lotSize": record.lot_size,
        "distance": (
            record.distance_hundredths / 100
            if record.distance_hundredths is not None
            else None
        ),
        "subdivision": record.subdivision,
        "_stonegateSearchLevel": "manual",
        "_stonegateManualComparableId": str(record.id),
        "_stonegateVerificationStatus": "manual_verified",
        "_stonegateEvidenceSource": record.source_type,
        "_stonegateSourceReference": record.source_reference,
        "_stonegateSourceUrl": record.source_url,
        "_stonegateVerificationNotes": record.verification_notes,
        "_stonegateConditionClassification": record.condition_classification,
        "_stonegateConditionEvidence": record.condition_evidence,
    }


def manual_comparable_to_read(
    record: UnderwritingManualComparable,
) -> UnderwritingManualComparableRead:
    return UnderwritingManualComparableRead(
        id=record.id,
        lead_id=record.lead_id,
        property_id=record.property_id,
        status=cast(Literal["active", "voided"], record.status),
        formatted_address=record.formatted_address,
        sale_date=record.sale_date,
        sale_price_cents=record.sale_price_cents,
        property_type=record.property_type,
        bedrooms=record.bedrooms,
        bathrooms=(
            record.bathrooms_hundredths / 100
            if record.bathrooms_hundredths is not None
            else None
        ),
        square_footage=record.square_footage,
        year_built=record.year_built,
        lot_size=record.lot_size,
        distance_miles=(
            record.distance_hundredths / 100
            if record.distance_hundredths is not None
            else None
        ),
        subdivision=record.subdivision,
        condition_classification=cast(
            Literal["unknown", "as_is", "renovated"],
            record.condition_classification,
        ),
        condition_evidence=record.condition_evidence,
        source_type=cast(ManualComparableSource, record.source_type),
        source_reference=record.source_reference,
        source_url=record.source_url,
        verification_notes=record.verification_notes,
        created_by_user_id=record.created_by_user_id,
        created_at=record.created_at,
        voided_at=record.voided_at,
    )


def latest_provider_sale_is_duplicate(
    db: Session,
    principal: Principal,
    lead: Lead,
    *,
    normalized_address_key: str,
    sale_date: date,
) -> bool:
    analysis = db.scalar(
        select(UnderwritingMarketAnalysis)
        .where(
            UnderwritingMarketAnalysis.organization_id == principal.organization_id,
            UnderwritingMarketAnalysis.lead_id == lead.id,
        )
        .order_by(
            UnderwritingMarketAnalysis.created_at.desc(),
            UnderwritingMarketAnalysis.id.desc(),
        )
    )
    raw_sales = (analysis.raw_response or {}).get("recorded_sales") if analysis else None
    if not isinstance(raw_sales, list):
        return False
    for record in raw_sales:
        if not isinstance(record, dict):
            continue
        if provider_address_key(record) != normalized_address_key:
            continue
        if sale_date_key(record.get("lastSaleDate")) == sale_date.isoformat():
            return True
    return False


def provider_address_key(record: dict[str, Any]) -> str:
    street = clean(record.get("addressLine1"))
    city = clean(record.get("city"))
    state = clean(record.get("state"))
    postal_code = clean(record.get("zipCode"))
    if street and city and state and postal_code:
        return canonical_address_key(street, city, state, postal_code)
    return compact_address(clean(record.get("formattedAddress")))


def sale_identity(record: dict[str, Any]) -> tuple[str, str]:
    return provider_address_key(record), sale_date_key(record.get("lastSaleDate"))


def sale_date_key(value: Any) -> str:
    return value[:10] if isinstance(value, str) else ""


def compact_address(value: str | None) -> str:
    return "".join(character for character in (value or "").lower() if character.isalnum())


def scoped_lead(db: Session, principal: Principal, lead_id: UUID) -> Lead | None:
    return db.scalar(
        select(Lead).where(
            Lead.id == lead_id,
            Lead.organization_id == principal.organization_id,
        )
    )


def clean(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def manual_comparable_audit_value(
    record: UnderwritingManualComparable,
) -> dict[str, Any]:
    return {
        "lead_id": str(record.lead_id),
        "property_id": str(record.property_id),
        "status": record.status,
        "formatted_address": record.formatted_address,
        "sale_date": record.sale_date.isoformat(),
        "sale_price_cents": record.sale_price_cents,
        "property_type": record.property_type,
        "square_footage": record.square_footage,
        "condition_classification": record.condition_classification,
        "condition_evidence": record.condition_evidence,
        "source_type": record.source_type,
        "source_reference": record.source_reference,
        "source_url": record.source_url,
        "verification_notes": record.verification_notes,
        "voided_at": record.voided_at.isoformat() if record.voided_at else None,
    }
