from datetime import UTC, datetime
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import get_settings
from app.domain.rbac import PermissionKeys
from app.models.foundation import AuditEvent, Organization, PublicProofRecord, User
from app.schemas.trust_proof import (
    PublicTrustProofRead,
    PublicTrustProofResponse,
    TrustProofAdminOverview,
    TrustProofAdminRead,
    TrustProofCreate,
    TrustProofDecisionRequest,
    TrustProofUpdate,
)

PLACEHOLDER_MARKERS = (
    "lorem ipsum",
    "sample review",
    "sample testimonial",
    "placeholder",
    "fake review",
    "[seller",
)


def list_trust_proofs(
    db: Session,
    principal: Principal,
) -> TrustProofAdminOverview:
    records = list(
        db.scalars(
            select(PublicProofRecord)
            .where(PublicProofRecord.organization_id == principal.organization_id)
            .order_by(
                PublicProofRecord.publication_status,
                PublicProofRecord.sort_order,
                PublicProofRecord.created_at.desc(),
            )
        )
    )
    user_ids = {
        user_id
        for record in records
        for user_id in (
            record.created_by_user_id,
            record.updated_by_user_id,
            record.approved_by_user_id,
        )
        if user_id is not None
    }
    users = {
        user.id: user.display_name
        for user in db.scalars(select(User).where(User.id.in_(user_ids)))
    } if user_ids else {}
    return TrustProofAdminOverview(
        can_manage=PermissionKeys.MANAGE_PUBLIC_PROOF in principal.permission_keys,
        records=[admin_read(record, users) for record in records],
    )


def create_trust_proof(
    db: Session,
    principal: Principal,
    payload: TrustProofCreate,
) -> TrustProofAdminRead:
    require_manage(principal)
    values = normalized_values(payload.model_dump())
    validate_required_values(values)
    source_url = values.get("source_url")
    validate_source_url(source_url if isinstance(source_url, str) else None)
    record = PublicProofRecord(
        organization_id=principal.organization_id,
        publication_status="draft",
        created_by_user_id=principal.user_id,
        updated_by_user_id=principal.user_id,
        **values,
    )
    db.add(record)
    db.flush()
    add_audit(
        db,
        principal,
        action="public_proof.create",
        record=record,
        reason="Created draft public proof.",
        previous=None,
    )
    db.commit()
    db.refresh(record)
    return admin_read(record, user_names(db, record))


def update_trust_proof(
    db: Session,
    principal: Principal,
    record_id: UUID,
    payload: TrustProofUpdate,
) -> TrustProofAdminRead | None:
    require_manage(principal)
    record = get_record(db, principal.organization_id, record_id)
    if record is None:
        return None
    if record.publication_status != "draft":
        raise ValueError("Return the proof to draft before editing it.")
    previous = snapshot(record)
    values = normalized_values(payload.model_dump(exclude_unset=True))
    validate_required_values(values)
    if "source_url" in values:
        source_url = values["source_url"]
        validate_source_url(source_url if isinstance(source_url, str) else None)
    for key, value in values.items():
        setattr(record, key, value)
    record.updated_by_user_id = principal.user_id
    add_audit(
        db,
        principal,
        action="public_proof.update",
        record=record,
        reason="Updated draft public proof.",
        previous=previous,
    )
    db.commit()
    db.refresh(record)
    return admin_read(record, user_names(db, record))


def decide_trust_proof(
    db: Session,
    principal: Principal,
    record_id: UUID,
    payload: TrustProofDecisionRequest,
) -> TrustProofAdminRead | None:
    require_manage(principal)
    record = get_record(db, principal.organization_id, record_id)
    if record is None:
        return None
    previous = snapshot(record)
    now = datetime.now(UTC)

    if payload.decision == "submit_review":
        if record.publication_status != "draft":
            raise ValueError("Only a draft can be submitted for review.")
        validate_review_ready(record)
        record.publication_status = "in_review"
    elif payload.decision == "publish":
        if record.publication_status != "in_review":
            raise ValueError("Proof must be reviewed before it can be published.")
        validate_publish_ready(record)
        record.publication_status = "published"
        record.approved_by_user_id = principal.user_id
        record.approved_at = now
        record.published_at = now
        record.retired_at = None
    elif payload.decision == "return_to_draft":
        if record.publication_status not in {"in_review", "published", "retired"}:
            raise ValueError("This proof is already a draft.")
        record.publication_status = "draft"
        record.approved_by_user_id = None
        record.approved_at = None
        record.published_at = None
        record.retired_at = None
    elif payload.decision == "retire":
        if record.publication_status not in {"in_review", "published"}:
            raise ValueError("Only reviewed or published proof can be retired.")
        record.publication_status = "retired"
        record.retired_at = now
    else:
        raise ValueError("Unsupported proof decision.")

    record.updated_by_user_id = principal.user_id
    add_audit(
        db,
        principal,
        action=f"public_proof.{payload.decision}",
        record=record,
        reason=payload.reason,
        previous=previous,
    )
    db.commit()
    db.refresh(record)
    return admin_read(record, user_names(db, record))


def get_public_trust_proofs(db: Session) -> PublicTrustProofResponse:
    settings = get_settings()
    organization = db.scalar(
        select(Organization).where(Organization.name == settings.default_organization_name)
    )
    if organization is None or not organization.is_active:
        organization = next(
            (
                candidate
                for candidate in db.scalars(
                    select(Organization).order_by(Organization.created_at)
                )
                if candidate.is_active
            ),
            None,
        )
    if organization is None:
        return PublicTrustProofResponse(records=[])

    records = list(
        db.scalars(
            select(PublicProofRecord)
            .where(
                PublicProofRecord.organization_id == organization.id,
                PublicProofRecord.publication_status == "published",
                PublicProofRecord.permission_status.in_(("granted", "not_required")),
                PublicProofRecord.published_at.is_not(None),
            )
            .order_by(
                PublicProofRecord.featured.desc(),
                PublicProofRecord.sort_order,
                PublicProofRecord.published_at.desc(),
            )
        )
    )
    return PublicTrustProofResponse(
        records=[
            PublicTrustProofRead(
                id=record.id,
                proof_type=record.proof_type,
                title=record.title,
                content=record.content,
                attribution_name=record.attribution_name,
                attribution_detail=record.attribution_detail,
                location_label=record.location_label,
                rating=record.rating,
                metric_label=record.metric_label,
                metric_value=record.metric_value,
                methodology=record.methodology if record.proof_type == "statistic" else None,
                as_of_date=record.as_of_date,
                source_type=record.source_type,
                source_url=record.source_url if record.show_source_link else None,
                disclosure=record.disclosure,
                featured=record.featured,
                published_at=record.published_at,
            )
            for record in records
            if record.published_at is not None
        ]
    )


def validate_review_ready(record: PublicProofRecord) -> None:
    if not record.title.strip():
        raise ValueError("A public title is required.")
    if not record.source_type.strip():
        raise ValueError("The evidence source type is required.")
    if not (clean(record.source_url) or clean(record.source_reference)):
        raise ValueError("Add a source URL or internal evidence reference before review.")
    validate_source_url(record.source_url)
    reject_placeholder_content(record)


def validate_publish_ready(record: PublicProofRecord) -> None:
    validate_review_ready(record)
    if record.permission_status not in {"granted", "not_required"}:
        raise ValueError("Usage permission must be granted or documented as not required.")
    if not clean(record.permission_evidence_notes):
        raise ValueError("Document the permission or why permission is not required.")
    if record.material_connection and not clean(record.disclosure):
        raise ValueError("A visible disclosure is required for a material connection.")
    if record.show_source_link and not clean(record.source_url):
        raise ValueError("A public source link requires a source URL.")

    if record.proof_type in {"review", "seller_story"}:
        if not clean(record.content):
            raise ValueError("Reviews and seller stories require the approved public text.")
        if not clean(record.attribution_name):
            raise ValueError("Reviews and seller stories require an approved public attribution.")
        if record.permission_status != "granted":
            raise ValueError("Reviews and seller stories require documented usage permission.")
    elif record.proof_type == "completed_purchase":
        if record.as_of_date is None:
            raise ValueError("Completed-purchase proof requires the completion date.")
        if record.attribution_name and record.permission_status != "granted":
            raise ValueError("Named completed-purchase proof requires documented permission.")
    elif record.proof_type == "statistic":
        if not clean(record.metric_label) or not clean(record.metric_value):
            raise ValueError("Statistics require a public metric label and value.")
        if record.as_of_date is None:
            raise ValueError("Statistics require an as-of date.")
        if not clean(record.methodology):
            raise ValueError("Statistics require a documented calculation method.")


def reject_placeholder_content(record: PublicProofRecord) -> None:
    combined = " ".join(
        value
        for value in (
            record.title,
            record.content,
            record.attribution_name,
            record.metric_label,
            record.metric_value,
        )
        if value
    ).lower()
    if any(marker in combined for marker in PLACEHOLDER_MARKERS):
        raise ValueError("Placeholder or sample proof cannot enter review.")


def validate_source_url(value: str | None) -> None:
    if not clean(value):
        return
    parsed = urlparse(value or "")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Source URL must be a complete HTTP or HTTPS URL.")


def normalized_values(values: dict[str, object]) -> dict[str, object]:
    return {
        key: value.strip() if isinstance(value, str) else value
        for key, value in values.items()
    }


def validate_required_values(values: dict[str, object]) -> None:
    for key, label in (
        ("proof_type", "Proof type"),
        ("title", "Public title"),
        ("source_type", "Source type"),
    ):
        current = values.get(key)
        if key in values and not (
            isinstance(current, str) and current.strip()
        ):
            raise ValueError(f"{label} cannot be empty.")


def clean(value: str | None) -> str:
    return (value or "").strip()


def require_manage(principal: Principal) -> None:
    if PermissionKeys.MANAGE_PUBLIC_PROOF not in principal.permission_keys:
        raise PermissionError("Public proof management requires Marketing or Owner access.")


def get_record(
    db: Session,
    organization_id: UUID,
    record_id: UUID,
) -> PublicProofRecord | None:
    return db.scalar(
        select(PublicProofRecord).where(
            PublicProofRecord.organization_id == organization_id,
            PublicProofRecord.id == record_id,
        )
    )


def user_names(db: Session, record: PublicProofRecord) -> dict[UUID, str]:
    ids = {
        user_id
        for user_id in (
            record.created_by_user_id,
            record.updated_by_user_id,
            record.approved_by_user_id,
        )
        if user_id is not None
    }
    return {
        user.id: user.display_name
        for user in db.scalars(select(User).where(User.id.in_(ids)))
    }


def admin_read(
    record: PublicProofRecord,
    users: dict[UUID, str],
) -> TrustProofAdminRead:
    return TrustProofAdminRead(
        id=record.id,
        proof_type=record.proof_type,
        title=record.title,
        content=record.content,
        attribution_name=record.attribution_name,
        attribution_detail=record.attribution_detail,
        location_label=record.location_label,
        rating=record.rating,
        metric_label=record.metric_label,
        metric_value=record.metric_value,
        methodology=record.methodology,
        as_of_date=record.as_of_date,
        source_type=record.source_type,
        source_url=record.source_url,
        source_reference=record.source_reference,
        show_source_link=record.show_source_link,
        permission_status=record.permission_status,
        permission_evidence_notes=record.permission_evidence_notes,
        material_connection=record.material_connection,
        disclosure=record.disclosure,
        publication_status=record.publication_status,
        featured=record.featured,
        sort_order=record.sort_order,
        created_by_name=users.get(record.created_by_user_id, "Unknown user"),
        updated_by_name=users.get(record.updated_by_user_id, "Unknown user"),
        approved_by_name=users.get(record.approved_by_user_id)
        if record.approved_by_user_id
        else None,
        approved_at=record.approved_at,
        published_at=record.published_at,
        retired_at=record.retired_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def snapshot(record: PublicProofRecord) -> dict[str, object]:
    return {
        "proof_type": record.proof_type,
        "title": record.title,
        "publication_status": record.publication_status,
        "permission_status": record.permission_status,
        "source_type": record.source_type,
        "source_url": record.source_url,
        "source_reference": record.source_reference,
        "featured": record.featured,
        "sort_order": record.sort_order,
    }


def add_audit(
    db: Session,
    principal: Principal,
    *,
    action: str,
    record: PublicProofRecord,
    reason: str,
    previous: dict[str, object] | None,
) -> None:
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action=action,
            entity_type="public_proof_record",
            entity_id=record.id,
            previous_value=previous,
            new_value=snapshot(record),
            reason=reason,
        )
    )
