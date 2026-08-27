import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.models.foundation import (
    ActivityEvent,
    AuditEvent,
    Buyer,
    BuyerCriteria,
    ConsentRecord,
    Conversation,
    ConversationContextLink,
    SuppressionRecord,
    User,
)
from app.schemas.buyers import (
    BuyerCreate,
    BuyerCriteriaCreate,
    BuyerCriteriaRead,
    BuyerCriteriaUpdate,
    BuyerDuplicateMatchRead,
    BuyerDuplicatePreflightRead,
    BuyerDuplicatePreflightRequest,
    BuyerListResponse,
    BuyerOwnerOptionRead,
    BuyerPermissionEvidenceRead,
    BuyerPermissionHistoryRead,
    BuyerRead,
    BuyerUpdate,
)
from app.services.communication_compliance import format_e164
from app.services.inbox import ensure_buyer_conversation, sync_buyer_conversation

BUYER_TYPES = {"cash_buyer", "landlord", "flipper", "builder", "hedge_fund", "agent"}
BUYER_STATUSES = {"active", "needs_review", "paused", "do_not_contact"}
BUYER_READ_STATUSES = {*BUYER_STATUSES, "archived"}
PROOF_OF_FUNDS_STATUSES = {
    "unknown",
    "requested",
    "received",
    "verified",
    "expired",
    "rejected",
}


@dataclass(frozen=True)
class DuplicateBuyerError(ValueError):
    matches: list[BuyerDuplicateMatchRead]


class BuyerOwnerNotFoundError(ValueError):
    pass


class BuyerSourceConflictError(ValueError):
    pass


def list_buyers(
    db: Session,
    principal: Principal,
    *,
    query: str | None = None,
    buyer_status: str | None = None,
    owner_id: UUID | None = None,
    source_key: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> BuyerListResponse:
    filters: list[Any] = [Buyer.organization_id == principal.organization_id]
    if buyer_status:
        normalized_status = normalize_read_status(buyer_status)
        if normalized_status not in BUYER_READ_STATUSES:
            raise ValueError(f"Unsupported buyer status: {buyer_status}")
        if normalized_status == "archived":
            filters.append(Buyer.archived_at.is_not(None))
        elif normalized_status == "paused":
            filters.extend((Buyer.archived_at.is_(None), Buyer.status.in_(("paused", "inactive"))))
        else:
            filters.extend((Buyer.archived_at.is_(None), Buyer.status == normalized_status))
    else:
        filters.append(Buyer.archived_at.is_(None))
    if owner_id is not None:
        filters.append(Buyer.relationship_owner_user_id == owner_id)
    if source_key:
        filters.append(Buyer.source_key == normalize_source_key(source_key))
    cleaned_query = collapse_whitespace(query)
    if cleaned_query:
        pattern = f"%{escape_like(cleaned_query)}%"
        normalized_company = normalize_company(cleaned_query)
        normalized_phone = format_e164(cleaned_query)
        search_filters: list[Any] = [
            Buyer.name.ilike(pattern, escape="\\"),
            Buyer.company_name.ilike(pattern, escape="\\"),
            Buyer.email.ilike(pattern, escape="\\"),
            Buyer.phone.ilike(pattern, escape="\\"),
        ]
        if normalized_company:
            company_pattern = f"%{escape_like(normalized_company)}%"
            search_filters.append(Buyer.normalized_company_name.ilike(company_pattern, escape="\\"))
        if normalized_phone:
            search_filters.append(Buyer.normalized_phone == normalized_phone)
        filters.append(or_(*search_filters))

    total = int(db.scalar(select(func.count()).select_from(Buyer).where(*filters)) or 0)
    buyers = list(
        db.scalars(
            select(Buyer)
            .where(*filters)
            .order_by(Buyer.created_at.desc(), Buyer.id.desc())
            .offset(offset)
            .limit(limit)
        ).all()
    )
    owner_options = list_active_owner_options(db, principal)
    source_options = list(
        db.scalars(
            select(Buyer.source_key)
            .where(Buyer.organization_id == principal.organization_id)
            .distinct()
            .order_by(Buyer.source_key.asc())
        ).all()
    )
    return BuyerListResponse(
        items=buyers_to_read(db, principal, buyers),
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(buyers) < total,
        owner_options=owner_options,
        source_options=source_options,
    )


def get_buyer(db: Session, principal: Principal, buyer_id: UUID) -> BuyerRead | None:
    buyer = db.scalar(
        select(Buyer).where(
            Buyer.organization_id == principal.organization_id,
            Buyer.id == buyer_id,
        )
    )
    if buyer is None:
        return None
    return buyers_to_read(db, principal, [buyer])[0]


def create_buyer(db: Session, principal: Principal, payload: BuyerCreate) -> BuyerRead:
    values = normalized_create_values(payload)
    validate_buyer_values(values)
    _require_phone_for_permission_grant(
        values["normalized_phone"],
        phone_permission=payload.phone_contact_permission,
        sms_permission=payload.sms_consent,
    )
    _validate_active_owner(db, principal, payload.relationship_owner_user_id)
    matches = duplicate_matches(
        db,
        principal,
        normalized_email=values["normalized_email"],
        normalized_phone=values["normalized_phone"],
        normalized_company_name=values["normalized_company_name"],
    )
    require_duplicate_override(
        payload.allow_separate_record,
        payload.separate_record_reason,
        matches,
    )
    source_key = normalize_source_key(payload.source_key)
    source_external_key = collapse_whitespace(payload.source_external_key)
    _validate_source_external_uniqueness(
        db,
        principal,
        source_key=source_key,
        source_external_key=source_external_key,
    )

    buyer = Buyer(
        organization_id=principal.organization_id,
        name=values["name"],
        company_name=values["company_name"],
        email=values["email"],
        phone=values["phone"],
        normalized_email=values["normalized_email"],
        normalized_phone=values["normalized_phone"],
        normalized_company_name=values["normalized_company_name"],
        buyer_type=payload.buyer_type,
        # A requested active state still enters review. Moving to active is a
        # separate, authenticated PATCH that records the reviewer in the audit trail.
        # Explicit safety states (paused/do-not-contact) remain enforceable on create.
        status=(
            "needs_review"
            if normalize_write_status(payload.status) == "active"
            else normalize_write_status(payload.status)
        ),
        source_key=source_key,
        source_detail=collapse_whitespace(payload.source_detail),
        source_external_key=source_external_key,
        created_by_user_id=principal.user_id,
        relationship_owner_user_id=payload.relationship_owner_user_id,
        last_verified_at=payload.last_verified_at,
        proof_of_funds_status=payload.proof_of_funds_status,
        max_purchase_price_cents=payload.max_purchase_price_cents,
        notes=normalize_text(payload.notes),
    )
    db.add(buyer)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise BuyerSourceConflictError(
            "A buyer with this source and external key already exists."
        ) from exc
    criteria = _create_criteria_version(db, buyer, payload.criteria, version_number=1)
    conversation = ensure_buyer_conversation(db, buyer, actor_user_id=principal.user_id)
    _sync_do_not_contact_suppression(db, buyer)
    now = datetime.now(UTC)
    if payload.phone_contact_permission:
        _record_permission(
            db,
            buyer=buyer,
            contact_id=conversation.contact_id,
            channel="phone",
            status="granted",
            source=payload.permission_evidence_source,
            recorded_at=now,
        )
    if payload.sms_consent:
        _record_permission(
            db,
            buyer=buyer,
            contact_id=conversation.contact_id,
            channel="sms",
            status="granted",
            source=payload.permission_evidence_source,
            recorded_at=now,
        )
    _activity(db, principal, buyer, "buyer.created", f"Buyer created: {buyer.name}.")
    _audit(
        db,
        principal,
        buyer,
        "buyer.create",
        None,
        _buyer_snapshot(buyer, criteria),
        "Manual buyer creation",
    )
    if matches:
        _audit_duplicate_override(db, principal, buyer, matches, payload.separate_record_reason)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise BuyerSourceConflictError(
            "A buyer with this source and external key already exists."
        ) from exc
    result = get_buyer(db, principal, buyer.id)
    if result is None:
        raise RuntimeError("Buyer was not available after creation.")
    return result


def update_buyer(
    db: Session,
    principal: Principal,
    buyer_id: UUID,
    payload: BuyerUpdate,
) -> BuyerRead | None:
    buyer = db.scalar(
        select(Buyer)
        .where(
            Buyer.organization_id == principal.organization_id,
            Buyer.id == buyer_id,
        )
        .with_for_update()
    )
    if buyer is None:
        return None
    if buyer.archived_at is not None:
        raise ValueError("Restore this buyer before editing it.")
    supplied = payload.model_fields_set
    if "relationship_owner_user_id" in supplied:
        _validate_active_owner(db, principal, payload.relationship_owner_user_id)

    previous_criteria = current_criteria(db, principal, buyer.id)
    previous_snapshot = _buyer_snapshot(buyer, previous_criteria)
    display_email = (
        (normalize_text(str(payload.email)) if payload.email is not None else None)
        if "email" in supplied
        else buyer.email
    )
    display_phone = (
        (normalize_text(payload.phone) if payload.phone is not None else None)
        if "phone" in supplied
        else buyer.phone
    )
    prospective = {
        "name": normalize_name(payload.name) if "name" in supplied else buyer.name,
        "company_name": (
            collapse_whitespace(payload.company_name)
            if "company_name" in supplied
            else buyer.company_name
        ),
        "email": display_email,
        "phone": display_phone,
        "normalized_email": (
            normalize_email(display_email) if "email" in supplied else buyer.normalized_email
        ),
        "normalized_phone": (
            normalize_phone(display_phone) if "phone" in supplied else buyer.normalized_phone
        ),
        "normalized_company_name": (
            normalize_company(payload.company_name)
            if "company_name" in supplied
            else buyer.normalized_company_name
        ),
    }
    if "email" in supplied and display_email and prospective["normalized_email"] is None:
        raise ValueError("Buyer email address is invalid.")
    if "phone" in supplied and display_phone and prospective["normalized_phone"] is None:
        raise ValueError("Buyer phone number is invalid.")
    _require_phone_for_permission_grant(
        prospective["normalized_phone"],
        phone_permission=(
            payload.phone_contact_permission is True
            if "phone_contact_permission" in supplied
            else False
        ),
        sms_permission=payload.sms_consent is True if "sms_consent" in supplied else False,
    )
    validate_contact_identity(
        prospective["normalized_email"],
        prospective["normalized_phone"],
    )

    identity_changed = any(
        (
            prospective["normalized_email"] != buyer.normalized_email,
            prospective["normalized_phone"] != buyer.normalized_phone,
            prospective["normalized_company_name"] != buyer.normalized_company_name,
        )
    )
    matches = (
        duplicate_matches(
            db,
            principal,
            normalized_email=prospective["normalized_email"],
            normalized_phone=prospective["normalized_phone"],
            normalized_company_name=prospective["normalized_company_name"],
            exclude_buyer_id=buyer.id,
        )
        if identity_changed
        else []
    )
    require_duplicate_override(
        payload.allow_separate_record,
        payload.separate_record_reason,
        matches,
    )

    prospective_name = prospective["name"]
    if prospective_name is None:
        raise ValueError("Buyer name is required.")
    buyer.name = prospective_name
    buyer.company_name = prospective["company_name"]
    buyer.email = prospective["email"]
    buyer.phone = prospective["phone"]
    buyer.normalized_email = prospective["normalized_email"]
    buyer.normalized_phone = prospective["normalized_phone"]
    buyer.normalized_company_name = prospective["normalized_company_name"]
    scalar_fields = (
        "buyer_type",
        "source_detail",
        "source_external_key",
        "relationship_owner_user_id",
        "last_verified_at",
        "proof_of_funds_status",
        "max_purchase_price_cents",
        "notes",
    )
    for field in scalar_fields:
        if field in supplied:
            value = getattr(payload, field)
            if field in {"source_detail", "source_external_key", "notes"}:
                value = normalize_text(value)
            setattr(buyer, field, value)
    if "source_key" in supplied and payload.source_key is not None:
        buyer.source_key = normalize_source_key(payload.source_key)
    if "status" in supplied and payload.status is not None:
        buyer.status = normalize_write_status(payload.status)
    _validate_source_external_uniqueness(
        db,
        principal,
        source_key=buyer.source_key,
        source_external_key=buyer.source_external_key,
        exclude_buyer_id=buyer.id,
    )
    validate_buyer_values(
        {
            "buyer_type": buyer.buyer_type,
            "status": buyer.status,
            "proof_of_funds_status": buyer.proof_of_funds_status,
            "email": buyer.email,
            "phone": buyer.phone,
            "normalized_email": buyer.normalized_email,
            "normalized_phone": buyer.normalized_phone,
        }
    )

    criteria = previous_criteria
    if "criteria" in supplied and payload.criteria is not None:
        requested_criteria = merge_criteria_update(previous_criteria, payload.criteria)
        if _criteria_values(requested_criteria) != _criteria_values(previous_criteria):
            if previous_criteria is not None:
                previous_criteria.is_current = False
                db.flush()
            criteria = _create_criteria_version(
                db,
                buyer,
                requested_criteria,
                version_number=(previous_criteria.version_number + 1 if previous_criteria else 1),
            )

    conversation = ensure_buyer_conversation(db, buyer, actor_user_id=principal.user_id)
    phone_changed = buyer.normalized_phone != previous_snapshot["normalized_phone"]
    permission_changed = False
    permission_changes: list[dict[str, str | None]] = []
    now = datetime.now(UTC)
    if phone_changed:
        for index, channel in enumerate(("phone", "sms")):
            permission_field = "phone_contact_permission" if channel == "phone" else "sms_consent"
            status = (
                "granted"
                if permission_field in supplied and getattr(payload, permission_field)
                else "denied"
                if permission_field in supplied
                else "missing"
            )
            _record_permission(
                db,
                buyer=buyer,
                contact_id=conversation.contact_id,
                channel=channel,
                status=status,
                source=payload.permission_evidence_source,
                recorded_at=now + timedelta(microseconds=index),
            )
            permission_changes.append(
                {
                    "channel": channel,
                    "status": status,
                    "source": payload.permission_evidence_source,
                    "normalized_address": buyer.normalized_phone,
                }
            )
        permission_changed = True
    else:
        for channel, field in (("phone", "phone_contact_permission"), ("sms", "sms_consent")):
            if field not in supplied or getattr(payload, field) is None:
                continue
            _record_permission(
                db,
                buyer=buyer,
                contact_id=conversation.contact_id,
                channel=channel,
                status="granted" if getattr(payload, field) else "denied",
                source=payload.permission_evidence_source,
                recorded_at=now,
            )
            permission_changes.append(
                {
                    "channel": channel,
                    "status": "granted" if getattr(payload, field) else "denied",
                    "source": payload.permission_evidence_source,
                    "normalized_address": buyer.normalized_phone,
                }
            )
            permission_changed = True
    sync_buyer_conversation(
        db,
        buyer,
        conversation,
        actor_user_id=principal.user_id,
        reassign="relationship_owner_user_id" in supplied,
    )
    if phone_changed:
        _lift_buyer_lifecycle_suppression(
            db,
            organization_id=buyer.organization_id,
            normalized_phone=previous_snapshot["normalized_phone"],
        )
    _sync_do_not_contact_suppression(db, buyer)
    new_snapshot = _buyer_snapshot(buyer, criteria)
    changed = previous_snapshot != new_snapshot or permission_changed
    if changed:
        _activity(db, principal, buyer, "buyer.updated", f"Buyer updated: {buyer.name}.")
        _audit(
            db,
            principal,
            buyer,
            "buyer.update",
            previous_snapshot,
            new_snapshot,
            "Buyer profile updated",
        )
    if permission_changes:
        description = ", ".join(
            f"{change['channel']} {change['status']}" for change in permission_changes
        )
        _activity(
            db,
            principal,
            buyer,
            "buyer.permissions_updated",
            f"Buyer contact permissions updated: {description}.",
        )
        _audit(
            db,
            principal,
            buyer,
            "buyer.permission_update",
            None,
            {"changes": permission_changes},
            "Buyer contact permission evidence updated",
        )
    if matches:
        _audit_duplicate_override(db, principal, buyer, matches, payload.separate_record_reason)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise BuyerSourceConflictError(
            "A buyer with this source and external key already exists."
        ) from exc
    return get_buyer(db, principal, buyer.id)


def archive_buyer(
    db: Session,
    principal: Principal,
    buyer_id: UUID,
    reason: str,
) -> BuyerRead | None:
    buyer = _locked_buyer(db, principal, buyer_id)
    if buyer is None:
        return None
    if buyer.archived_at is not None:
        return get_buyer(db, principal, buyer.id)
    previous = _buyer_snapshot(buyer, current_criteria(db, principal, buyer.id))
    now = datetime.now(UTC)
    # Preserve the lifecycle DNC state while the record is archived.  The
    # archived_at marker is the source of truth for archive visibility, and
    # read_status() still exposes this record as archived.  Keeping the
    # underlying DNC state prevents a later restore from silently lifting the
    # phone/SMS suppression that the buyer explicitly required.
    if buyer.status != "do_not_contact":
        buyer.status = "archived"
    buyer.archived_at = now
    buyer.archived_by_user_id = principal.user_id
    buyer.archive_reason = collapse_whitespace(reason)
    sync_buyer_conversation(db, buyer)
    _activity(db, principal, buyer, "buyer.archived", f"Buyer archived: {buyer.name}.")
    _audit(
        db,
        principal,
        buyer,
        "buyer.archive",
        previous,
        _buyer_snapshot(buyer, current_criteria(db, principal, buyer.id)),
        buyer.archive_reason,
    )
    db.commit()
    return get_buyer(db, principal, buyer.id)


def restore_buyer(db: Session, principal: Principal, buyer_id: UUID) -> BuyerRead | None:
    buyer = _locked_buyer(db, principal, buyer_id)
    if buyer is None:
        return None
    if buyer.archived_at is None:
        return get_buyer(db, principal, buyer.id)
    previous = _buyer_snapshot(buyer, current_criteria(db, principal, buyer.id))
    buyer.status = "do_not_contact" if buyer.status == "do_not_contact" else "needs_review"
    buyer.archived_at = None
    buyer.archived_by_user_id = None
    buyer.archive_reason = None
    sync_buyer_conversation(db, buyer)
    _sync_do_not_contact_suppression(db, buyer)
    _activity(db, principal, buyer, "buyer.restored", f"Buyer restored: {buyer.name}.")
    _audit(
        db,
        principal,
        buyer,
        "buyer.restore",
        previous,
        _buyer_snapshot(buyer, current_criteria(db, principal, buyer.id)),
        (
            "Buyer restored with do-not-contact suppression preserved"
            if buyer.status == "do_not_contact"
            else "Buyer restored to needs review"
        ),
    )
    db.commit()
    return get_buyer(db, principal, buyer.id)


def preflight_duplicates(
    db: Session,
    principal: Principal,
    payload: BuyerDuplicatePreflightRequest,
) -> BuyerDuplicatePreflightRead:
    normalized_email = normalize_email(str(payload.email) if payload.email else None)
    normalized_phone = normalize_phone(payload.phone)
    if payload.phone and normalized_phone is None:
        raise ValueError("Buyer phone number is invalid.")
    normalized_company_name = normalize_company(payload.company_name)
    matches = duplicate_matches(
        db,
        principal,
        normalized_email=normalized_email,
        normalized_phone=normalized_phone,
        normalized_company_name=normalized_company_name,
        exclude_buyer_id=payload.exclude_buyer_id,
    )
    return BuyerDuplicatePreflightRead(
        has_matches=bool(matches),
        normalized_email=normalized_email,
        normalized_phone=normalized_phone,
        normalized_company_name=normalized_company_name,
        matches=matches,
    )


def duplicate_matches(
    db: Session,
    principal: Principal,
    *,
    normalized_email: str | None,
    normalized_phone: str | None,
    normalized_company_name: str | None,
    exclude_buyer_id: UUID | None = None,
) -> list[BuyerDuplicateMatchRead]:
    comparisons: list[Any] = []
    if normalized_email:
        comparisons.append(Buyer.normalized_email == normalized_email)
    if normalized_phone:
        comparisons.append(Buyer.normalized_phone == normalized_phone)
    if normalized_company_name:
        comparisons.append(Buyer.normalized_company_name == normalized_company_name)
    if not comparisons:
        return []
    filters: list[Any] = [
        Buyer.organization_id == principal.organization_id,
        or_(*comparisons),
    ]
    if exclude_buyer_id is not None:
        filters.append(Buyer.id != exclude_buyer_id)
    rows = db.scalars(select(Buyer).where(*filters).order_by(Buyer.created_at.desc())).all()
    result: list[BuyerDuplicateMatchRead] = []
    for row in rows:
        matched_fields: list[str] = []
        reasons: list[str] = []
        if normalized_phone and row.normalized_phone == normalized_phone:
            matched_fields.append("phone")
            reasons.append("Phone number already belongs to this buyer record.")
        if normalized_email and row.normalized_email == normalized_email:
            matched_fields.append("email")
            reasons.append("Email address already belongs to this buyer record.")
        if normalized_company_name and row.normalized_company_name == normalized_company_name:
            matched_fields.append("company_name")
            reasons.append("Normalized company name matches this buyer record.")
        result.append(
            BuyerDuplicateMatchRead(
                buyer_id=row.id,
                name=row.name,
                company_name=row.company_name,
                email=row.email,
                phone=row.phone,
                status=read_status(row),
                matched_fields=matched_fields,
                reasons=reasons,
            )
        )
    return result


def list_active_owner_options(
    db: Session,
    principal: Principal,
) -> list[BuyerOwnerOptionRead]:
    users = db.scalars(
        select(User)
        .where(
            User.organization_id == principal.organization_id,
            User.is_active.is_(True),
        )
        .order_by(User.display_name.asc(), User.email.asc())
    ).all()
    return [
        BuyerOwnerOptionRead(user_id=user.id, display_name=user.display_name, email=user.email)
        for user in users
    ]


def current_criteria(
    db: Session,
    principal: Principal,
    buyer_id: UUID,
) -> BuyerCriteria | None:
    return db.scalar(
        select(BuyerCriteria)
        .where(
            BuyerCriteria.organization_id == principal.organization_id,
            BuyerCriteria.buyer_id == buyer_id,
            BuyerCriteria.is_current.is_(True),
        )
        .order_by(BuyerCriteria.version_number.desc(), BuyerCriteria.created_at.desc())
        .limit(1)
    )


def get_criteria_by_buyer_id(
    db: Session,
    principal: Principal,
    buyer_ids: Sequence[UUID],
) -> dict[UUID, BuyerCriteria]:
    if not buyer_ids:
        return {}
    criteria_rows = db.scalars(
        select(BuyerCriteria)
        .where(
            BuyerCriteria.organization_id == principal.organization_id,
            BuyerCriteria.buyer_id.in_(buyer_ids),
            BuyerCriteria.is_current.is_(True),
        )
        .order_by(BuyerCriteria.version_number.desc(), BuyerCriteria.created_at.desc())
    ).all()
    criteria_by_buyer: dict[UUID, BuyerCriteria] = {}
    for criteria in criteria_rows:
        criteria_by_buyer.setdefault(criteria.buyer_id, criteria)
    return criteria_by_buyer


def buyers_to_read(db: Session, principal: Principal, buyers: list[Buyer]) -> list[BuyerRead]:
    if not buyers:
        return []
    buyer_ids = [buyer.id for buyer in buyers]
    criteria_by_buyer = get_criteria_by_buyer_id(db, principal, buyer_ids)
    user_ids = {
        user_id
        for buyer in buyers
        for user_id in (buyer.created_by_user_id, buyer.relationship_owner_user_id)
        if user_id is not None
    }
    users = (
        {
            user.id: user
            for user in db.scalars(
                select(User).where(
                    User.organization_id == principal.organization_id,
                    User.id.in_(user_ids),
                )
            ).all()
        }
        if user_ids
        else {}
    )
    contact_by_buyer = {
        buyer_id: contact_id
        for buyer_id, contact_id in db.execute(
            select(ConversationContextLink.buyer_id, Conversation.contact_id)
            .join(Conversation, Conversation.id == ConversationContextLink.conversation_id)
            .where(
                ConversationContextLink.organization_id == principal.organization_id,
                ConversationContextLink.context_type == "buyer",
                ConversationContextLink.buyer_id.in_(buyer_ids),
            )
        ).all()
        if buyer_id is not None
    }
    contact_ids = list(contact_by_buyer.values())
    consents = (
        db.scalars(
            select(ConsentRecord)
            .where(
                ConsentRecord.organization_id == principal.organization_id,
                ConsentRecord.contact_id.in_(contact_ids),
                ConsentRecord.channel.in_(("phone", "sms")),
            )
            .order_by(ConsentRecord.created_at.desc(), ConsentRecord.id.desc())
        ).all()
        if contact_ids
        else []
    )
    consents_by_contact: dict[tuple[UUID, str], list[ConsentRecord]] = {}
    for consent in consents:
        consents_by_contact.setdefault((consent.contact_id, consent.channel), []).append(consent)

    result: list[BuyerRead] = []
    for buyer in buyers:
        owner = (
            users.get(buyer.relationship_owner_user_id)
            if buyer.relationship_owner_user_id is not None
            else None
        )
        creator = (
            users.get(buyer.created_by_user_id) if buyer.created_by_user_id is not None else None
        )
        contact_id = contact_by_buyer.get(buyer.id)
        phone_consents = (
            consents_by_contact.get((contact_id, "phone"), []) if contact_id is not None else []
        )
        sms_consents = (
            consents_by_contact.get((contact_id, "sms"), []) if contact_id is not None else []
        )
        criteria = criteria_by_buyer.get(buyer.id)
        result.append(
            BuyerRead(
                id=buyer.id,
                name=buyer.name,
                company_name=buyer.company_name,
                email=buyer.email,
                phone=buyer.phone,
                normalized_email=buyer.normalized_email,
                normalized_phone=buyer.normalized_phone,
                buyer_type=buyer.buyer_type,
                status=read_status(buyer),
                source_key=buyer.source_key,
                source_detail=buyer.source_detail,
                source_external_key=buyer.source_external_key,
                created_by_user_id=buyer.created_by_user_id,
                created_by_name=creator.display_name if creator else None,
                created_by_email=creator.email if creator else None,
                relationship_owner_user_id=buyer.relationship_owner_user_id,
                relationship_owner_name=owner.display_name if owner else None,
                last_verified_at=buyer.last_verified_at,
                archived_at=buyer.archived_at,
                archived_by_user_id=buyer.archived_by_user_id,
                archive_reason=buyer.archive_reason,
                proof_of_funds_status=buyer.proof_of_funds_status,
                max_purchase_price_cents=buyer.max_purchase_price_cents,
                reliability_score_basis_points=buyer.reliability_score_basis_points,
                completed_deals=buyer.completed_deals,
                failed_deals=buyer.failed_deals,
                proof_of_funds_expires_at=buyer.proof_of_funds_expires_at,
                notes=buyer.notes,
                phone_permission=_permission_read(phone_consents, buyer.normalized_phone),
                sms_permission=_permission_read(sms_consents, buyer.normalized_phone),
                permission_history=[
                    BuyerPermissionHistoryRead(
                        channel=channel,
                        status=consent.status,
                        source=consent.source,
                        recorded_at=consent.created_at,
                        normalized_address=consent.normalized_address,
                        wording_version=consent.wording_version,
                    )
                    for channel in ("phone", "sms")
                    for consent in (phone_consents if channel == "phone" else sms_consents)
                ],
                criteria=BuyerCriteriaRead(
                    version_number=criteria.version_number,
                    markets=criteria.markets,
                    property_types=criteria.property_types,
                    min_price_cents=criteria.min_price_cents,
                    max_price_cents=criteria.max_price_cents,
                    rehab_levels=criteria.rehab_levels,
                    notes=criteria.notes,
                )
                if criteria
                else None,
                created_at=buyer.created_at,
                updated_at=buyer.updated_at,
            )
        )
    return result


def normalized_create_values(payload: BuyerCreate) -> dict[str, Any]:
    display_email = normalize_text(str(payload.email)) if payload.email else None
    display_phone = normalize_text(payload.phone)
    normalized_email = normalize_email(display_email)
    normalized_phone = normalize_phone(display_phone)
    if display_email and normalized_email is None:
        raise ValueError("Buyer email address is invalid.")
    if display_phone and normalized_phone is None:
        raise ValueError("A valid phone number is required when a buyer phone is provided.")
    company_name = collapse_whitespace(payload.company_name)
    return {
        "name": normalize_name(payload.name),
        "company_name": company_name,
        "email": display_email,
        "phone": display_phone,
        "normalized_email": normalized_email,
        "normalized_phone": normalized_phone,
        "normalized_company_name": normalize_company(company_name),
        "buyer_type": payload.buyer_type,
        "status": normalize_write_status(payload.status),
        "proof_of_funds_status": payload.proof_of_funds_status,
    }


def validate_buyer_values(values: dict[str, Any]) -> None:
    if values["buyer_type"] not in BUYER_TYPES:
        raise ValueError(f"Unsupported buyer type: {values['buyer_type']}")
    if normalize_write_status(values["status"]) not in BUYER_STATUSES:
        raise ValueError(f"Unsupported buyer status: {values['status']}")
    if values["proof_of_funds_status"] not in PROOF_OF_FUNDS_STATUSES:
        raise ValueError(f"Unsupported proof of funds status: {values['proof_of_funds_status']}")
    validate_contact_identity(
        values.get("normalized_email", values.get("email")),
        values.get("normalized_phone", values.get("phone")),
    )


def validate_contact_identity(email: str | None, phone: str | None) -> None:
    if email is None and phone is None:
        raise ValueError("A buyer requires at least one valid phone number or email address.")


def _require_phone_for_permission_grant(
    normalized_phone: str | None,
    *,
    phone_permission: bool,
    sms_permission: bool,
) -> None:
    if normalized_phone is None and (phone_permission or sms_permission):
        raise ValueError("A valid buyer phone number is required to grant phone or SMS permission.")


def normalize_name(value: str | None) -> str:
    normalized = collapse_whitespace(value)
    if not normalized:
        raise ValueError("Buyer name is required.")
    return normalized


def normalize_email(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    try:
        return validate_email(value.strip(), check_deliverability=False).normalized.lower()
    except EmailNotValidError:
        return None


def normalize_phone(value: str | None) -> str | None:
    return format_e164(value)


def normalize_company(value: str | None) -> str | None:
    normalized = collapse_whitespace(value)
    return normalized.casefold() if normalized else None


def normalize_text(value: str | None) -> str | None:
    return value.strip() if value and value.strip() else None


def collapse_whitespace(value: str | None) -> str | None:
    if not value:
        return None
    normalized = " ".join(value.split())
    return normalized or None


def escape_like(value: str) -> str:
    """Escape SQL LIKE metacharacters so buyer search is literal and predictable."""

    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def normalize_source_key(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    if not normalized:
        raise ValueError("Buyer source is required.")
    return normalized


def normalize_write_status(value: str) -> str:
    normalized = value.strip().lower()
    if normalized == "inactive":
        return "paused"
    if normalized == "archived":
        raise ValueError("Use the archive endpoint to archive a buyer.")
    return normalized


def normalize_read_status(value: str) -> str:
    normalized = value.strip().lower()
    return "paused" if normalized == "inactive" else normalized


def read_status(buyer: Buyer) -> str:
    if buyer.archived_at is not None or buyer.status == "archived":
        return "archived"
    return normalize_read_status(buyer.status)


def require_duplicate_override(
    allow_separate_record: bool,
    reason: str | None,
    matches: list[BuyerDuplicateMatchRead],
) -> None:
    if not matches:
        return
    if not allow_separate_record:
        raise DuplicateBuyerError(matches)
    if len(collapse_whitespace(reason) or "") < 3:
        raise ValueError("Explain why this duplicate should remain a separate buyer record.")


def _validate_active_owner(
    db: Session,
    principal: Principal,
    owner_id: UUID | None,
) -> None:
    if owner_id is None:
        return
    owner = db.scalar(
        select(User).where(
            User.organization_id == principal.organization_id,
            User.id == owner_id,
            User.is_active.is_(True),
        )
    )
    if owner is None:
        raise BuyerOwnerNotFoundError("Active relationship owner not found.")


def _validate_source_external_uniqueness(
    db: Session,
    principal: Principal,
    *,
    source_key: str,
    source_external_key: str | None,
    exclude_buyer_id: UUID | None = None,
) -> None:
    if source_external_key is None:
        return
    filters: list[Any] = [
        Buyer.organization_id == principal.organization_id,
        Buyer.source_key == source_key,
        Buyer.source_external_key == source_external_key,
    ]
    if exclude_buyer_id is not None:
        filters.append(Buyer.id != exclude_buyer_id)
    if db.scalar(select(Buyer.id).where(*filters).limit(1)) is not None:
        raise BuyerSourceConflictError("A buyer with this source and external key already exists.")


def _locked_buyer(db: Session, principal: Principal, buyer_id: UUID) -> Buyer | None:
    return db.scalar(
        select(Buyer)
        .where(
            Buyer.organization_id == principal.organization_id,
            Buyer.id == buyer_id,
        )
        .with_for_update()
    )


def _create_criteria_version(
    db: Session,
    buyer: Buyer,
    payload: BuyerCriteriaCreate | None,
    *,
    version_number: int,
) -> BuyerCriteria | None:
    if payload is None:
        return None
    _validate_criteria(payload)
    criteria = BuyerCriteria(
        organization_id=buyer.organization_id,
        buyer_id=buyer.id,
        version_number=version_number,
        is_current=True,
        markets=normalize_text(payload.markets),
        property_types=normalize_text(payload.property_types),
        min_price_cents=payload.min_price_cents,
        max_price_cents=payload.max_price_cents,
        rehab_levels=normalize_text(payload.rehab_levels),
        notes=normalize_text(payload.notes),
    )
    db.add(criteria)
    db.flush()
    return criteria


def merge_criteria_update(
    current: BuyerCriteria | None,
    payload: BuyerCriteriaUpdate,
) -> BuyerCriteriaCreate:
    values = _criteria_values(current)
    for field in payload.model_fields_set:
        values[field] = getattr(payload, field)
    return BuyerCriteriaCreate(**values)


def _validate_criteria(payload: BuyerCriteriaCreate) -> None:
    if (
        payload.min_price_cents is not None
        and payload.max_price_cents is not None
        and payload.min_price_cents > payload.max_price_cents
    ):
        raise ValueError("Buyer minimum price cannot exceed maximum price.")


def _criteria_values(criteria: BuyerCriteriaCreate | BuyerCriteria | None) -> dict[str, Any]:
    if criteria is None:
        return {
            "markets": None,
            "property_types": None,
            "min_price_cents": None,
            "max_price_cents": None,
            "rehab_levels": None,
            "notes": None,
        }
    return {
        "markets": normalize_text(criteria.markets),
        "property_types": normalize_text(criteria.property_types),
        "min_price_cents": criteria.min_price_cents,
        "max_price_cents": criteria.max_price_cents,
        "rehab_levels": normalize_text(criteria.rehab_levels),
        "notes": normalize_text(criteria.notes),
    }


def _record_permission(
    db: Session,
    *,
    buyer: Buyer,
    contact_id: UUID,
    channel: str,
    status: str,
    source: str,
    recorded_at: datetime,
) -> None:
    db.add(
        ConsentRecord(
            organization_id=buyer.organization_id,
            contact_id=contact_id,
            channel=channel,
            status=status,
            source=source,
            wording_version="buyer-contact-v2",
            wording=(
                "Buyer contact permission was recorded in the Buyer Network."
                if status in {"granted", "denied"}
                else "Buyer contact information changed; permission must be reconfirmed."
            ),
            normalized_address=buyer.normalized_phone,
            captured_ip=None,
            user_agent=None,
            created_at=recorded_at,
            updated_at=recorded_at,
        )
    )


def _permission_read(
    consents: list[ConsentRecord],
    normalized_phone: str | None,
) -> BuyerPermissionEvidenceRead:
    consent = next(
        (item for item in consents if item.normalized_address in {None, normalized_phone}),
        None,
    )
    return BuyerPermissionEvidenceRead(
        status=consent.status if consent else "missing",
        source=consent.source if consent else None,
        recorded_at=consent.created_at if consent else None,
        normalized_address=consent.normalized_address if consent else None,
        wording_version=consent.wording_version if consent else None,
    )


def _sync_do_not_contact_suppression(db: Session, buyer: Buyer) -> None:
    normalized_phone = buyer.normalized_phone
    if not normalized_phone or buyer.status == "archived":
        return
    if buyer.status != "do_not_contact":
        _lift_buyer_lifecycle_suppression(
            db,
            organization_id=buyer.organization_id,
            normalized_phone=normalized_phone,
        )
        return
    contact_id = db.scalar(
        select(Conversation.contact_id)
        .join(
            ConversationContextLink,
            ConversationContextLink.conversation_id == Conversation.id,
        )
        .where(
            ConversationContextLink.organization_id == buyer.organization_id,
            ConversationContextLink.context_type == "buyer",
            ConversationContextLink.buyer_id == buyer.id,
        )
    )
    now = datetime.now(UTC)
    for channel in ("phone", "sms"):
        suppression = db.scalar(
            select(SuppressionRecord).where(
                SuppressionRecord.organization_id == buyer.organization_id,
                SuppressionRecord.channel == channel,
                SuppressionRecord.normalized_address == normalized_phone,
            )
        )
        if suppression is None:
            db.add(
                SuppressionRecord(
                    organization_id=buyer.organization_id,
                    contact_id=contact_id,
                    channel=channel,
                    normalized_address=normalized_phone,
                    status="active",
                    reason="Buyer relationship marked do not contact.",
                    source="buyer_lifecycle",
                    provider=None,
                    external_event_id=None,
                    suppressed_at=now,
                    lifted_at=None,
                    suppression_metadata={"buyer_id": str(buyer.id)},
                )
            )
        elif suppression.status != "active":
            suppression.contact_id = contact_id
            suppression.status = "active"
            suppression.reason = "Buyer relationship marked do not contact."
            suppression.source = "buyer_lifecycle"
            suppression.suppressed_at = now
            suppression.lifted_at = None
            suppression.suppression_metadata = {"buyer_id": str(buyer.id)}


def _lift_buyer_lifecycle_suppression(
    db: Session,
    *,
    organization_id: UUID,
    normalized_phone: str | None,
) -> None:
    if normalized_phone is None:
        return
    if (
        db.scalar(
            select(Buyer.id)
            .where(
                Buyer.organization_id == organization_id,
                Buyer.normalized_phone == normalized_phone,
                Buyer.status == "do_not_contact",
            )
            .limit(1)
        )
        is not None
    ):
        return
    now = datetime.now(UTC)
    suppressions = db.scalars(
        select(SuppressionRecord).where(
            SuppressionRecord.organization_id == organization_id,
            SuppressionRecord.channel.in_(("phone", "sms")),
            SuppressionRecord.normalized_address == normalized_phone,
            SuppressionRecord.source == "buyer_lifecycle",
            SuppressionRecord.status == "active",
        )
    ).all()
    for suppression in suppressions:
        suppression.status = "lifted"
        suppression.lifted_at = now


def _buyer_snapshot(buyer: Buyer, criteria: BuyerCriteria | None) -> dict[str, Any]:
    return {
        "name": buyer.name,
        "company_name": buyer.company_name,
        "email": buyer.email,
        "phone": buyer.phone,
        "normalized_email": buyer.normalized_email,
        "normalized_phone": buyer.normalized_phone,
        "normalized_company_name": buyer.normalized_company_name,
        "buyer_type": buyer.buyer_type,
        "status": read_status(buyer),
        "source_key": buyer.source_key,
        "source_detail": buyer.source_detail,
        "source_external_key": buyer.source_external_key,
        "relationship_owner_user_id": (
            str(buyer.relationship_owner_user_id) if buyer.relationship_owner_user_id else None
        ),
        "last_verified_at": buyer.last_verified_at.isoformat() if buyer.last_verified_at else None,
        "proof_of_funds_status": buyer.proof_of_funds_status,
        "max_purchase_price_cents": buyer.max_purchase_price_cents,
        "notes": buyer.notes,
        "archived_at": buyer.archived_at.isoformat() if buyer.archived_at else None,
        "archive_reason": buyer.archive_reason,
        "criteria": _criteria_values(criteria),
        "criteria_version": criteria.version_number if criteria else None,
    }


def _activity(
    db: Session,
    principal: Principal,
    buyer: Buyer,
    event_type: str,
    summary: str,
) -> None:
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="buyer",
            entity_id=buyer.id,
            event_type=event_type,
            summary=summary,
        )
    )


def _audit(
    db: Session,
    principal: Principal,
    buyer: Buyer,
    action: str,
    previous_value: dict[str, Any] | None,
    new_value: dict[str, Any] | None,
    reason: str | None,
) -> None:
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action=action,
            entity_type="buyer",
            entity_id=buyer.id,
            previous_value=previous_value,
            new_value=new_value,
            reason=reason,
        )
    )


def _audit_duplicate_override(
    db: Session,
    principal: Principal,
    buyer: Buyer,
    matches: list[BuyerDuplicateMatchRead],
    reason: str | None,
) -> None:
    _audit(
        db,
        principal,
        buyer,
        "buyer.duplicate_override",
        {"matched_buyer_ids": [str(match.buyer_id) for match in matches]},
        {"separate_buyer_id": str(buyer.id)},
        collapse_whitespace(reason),
    )
