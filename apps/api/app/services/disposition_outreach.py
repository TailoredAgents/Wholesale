import json
from collections import Counter
from datetime import UTC, datetime
from hashlib import sha256
from string import Formatter
from typing import Any, Literal, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import Settings, get_settings
from app.models.foundation import (
    AuditEvent,
    Buyer,
    Contact,
    DispositionCampaign,
    DispositionCampaignRecipient,
    DispositionCase,
    DispositionOutreachDelivery,
    DispositionOutreachRevision,
    DispositionPackageVersion,
    EmailSenderAlias,
    Lead,
    SuppressionRecord,
    VoiceLine,
)
from app.schemas.disposition_outreach import (
    DispositionOutreachApprovalRequest,
    DispositionOutreachControlRequest,
    DispositionOutreachDeliveryRead,
    DispositionOutreachDraftCreate,
    DispositionOutreachPreparedRecipientRead,
    DispositionOutreachRevisionRead,
    DispositionOutreachSenderRead,
    DispositionOutreachWorkspaceRead,
    OutreachChannel,
    OutreachRevisionStatus,
)
from app.services.buyers import normalize_email
from app.services.communication_compliance import evaluate_sms_eligibility, format_e164
from app.services.disposition_packages import require_current_approved_version
from app.services.inbox import ensure_buyer_conversation

HARD_RECIPIENT_CAP = 25
ALLOWED_TEMPLATE_FIELDS = {
    "buyer_name",
    "company_name",
    "property_address",
    "package_reference",
}
ACTIVE_REVISION_STATUSES = {
    "review_required",
    "approved",
    "queued",
    "sending",
    "paused",
    "provider_degraded",
}
UNSENT_DELIVERY_STATUSES = {
    "prepared",
    "approved",
    "queued",
    "claimed",
    "failed_retryable",
}


def read_workspace(
    db: Session,
    principal: Principal,
    case_id: UUID,
) -> DispositionOutreachWorkspaceRead | None:
    case = _scoped_house_case(db, principal, case_id)
    if case is None:
        return None

    blockers: list[str] = []
    package: DispositionPackageVersion | None = None
    try:
        package = require_current_approved_version(
            db,
            principal,
            case,
            action="reviewing governed buyer outreach",
        )
    except ValueError as exc:
        blockers.append(str(exc))

    campaign = (
        db.scalar(
            select(DispositionCampaign)
            .where(
                DispositionCampaign.organization_id == principal.organization_id,
                DispositionCampaign.disposition_case_id == case.id,
                DispositionCampaign.package_version_id == package.id,
            )
            .order_by(DispositionCampaign.created_at.desc())
        )
        if package is not None
        else None
    )
    recipients = _prepared_recipients(db, principal, campaign) if campaign else []
    if package is not None and campaign is None:
        blockers.append("Prepare the approved buyer recipient pool before drafting outreach.")
    elif campaign is not None and not recipients:
        blockers.append("The prepared campaign has no buyer recipients.")

    revisions = list(
        db.scalars(
            select(DispositionOutreachRevision)
            .where(
                DispositionOutreachRevision.organization_id == principal.organization_id,
                DispositionOutreachRevision.disposition_case_id == case.id,
            )
            .order_by(DispositionOutreachRevision.revision_number.desc())
        ).all()
    )
    return DispositionOutreachWorkspaceRead(
        case_id=case.id,
        campaign_id=campaign.id if campaign else None,
        package_version_id=package.id if package else None,
        package_source_fingerprint=package.source_fingerprint if package else None,
        artifact_sha256=package.pdf_sha256 if package else None,
        hard_recipient_cap=HARD_RECIPIENT_CAP,
        readiness_status="blocked" if blockers else "ready",
        blockers=blockers,
        prepared_recipients=[_prepared_recipient_read(item) for item in recipients],
        available_senders=_available_senders(db, principal),
        latest_revision=_revision_read(db, revisions[0]) if revisions else None,
        revisions=[_revision_read(db, item) for item in revisions],
    )


def create_draft(
    db: Session,
    principal: Principal,
    case_id: UUID,
    payload: DispositionOutreachDraftCreate,
    *,
    settings: Settings | None = None,
) -> DispositionOutreachRevisionRead | None:
    settings = settings or get_settings()
    case = _scoped_house_case(db, principal, case_id, lock=True)
    if case is None:
        return None
    package = require_current_approved_version(
        db,
        principal,
        case,
        action="drafting buyer outreach",
    )
    campaign = db.scalar(
        select(DispositionCampaign)
        .where(
            DispositionCampaign.id == payload.campaign_id,
            DispositionCampaign.organization_id == principal.organization_id,
            DispositionCampaign.disposition_case_id == case.id,
            DispositionCampaign.package_version_id == package.id,
            DispositionCampaign.status == "prepared_not_sent",
        )
        .with_for_update()
    )
    if campaign is None:
        raise ValueError("Select the current prepared campaign for this approved package.")

    selection_ids = [item.campaign_recipient_id for item in payload.recipients]
    if len(set(selection_ids)) != len(selection_ids):
        raise ValueError("Each prepared buyer may be selected only once.")
    delivery_count = sum(len(item.channels) for item in payload.recipients)
    if len(selection_ids) > HARD_RECIPIENT_CAP or delivery_count > HARD_RECIPIENT_CAP:
        raise ValueError(
            f"Supervised outreach is limited to {HARD_RECIPIENT_CAP} recipient-channel "
            "deliveries per revision."
        )

    prepared = list(
        db.scalars(
            select(DispositionCampaignRecipient).where(
                DispositionCampaignRecipient.organization_id == principal.organization_id,
                DispositionCampaignRecipient.disposition_campaign_id == campaign.id,
                DispositionCampaignRecipient.package_version_id == package.id,
                DispositionCampaignRecipient.id.in_(selection_ids),
                DispositionCampaignRecipient.status == "prepared_not_sent",
            )
        ).all()
    )
    by_id = {item.id: item for item in prepared}
    if set(by_id) != set(selection_ids):
        raise ValueError("One or more selected recipients are not in the prepared campaign.")
    if any(item.artifact_sha256 != package.pdf_sha256 for item in prepared):
        raise ValueError("The prepared recipient pool is bound to a different package artifact.")

    channels = {channel for item in payload.recipients for channel in item.channels}
    if (
        "email" in channels
        and not settings.disposition_outreach_physical_postal_address.strip()
    ):
        raise ValueError(
            "Email outreach requires DISPOSITION_OUTREACH_PHYSICAL_POSTAL_ADDRESS "
            "to contain Stonegate's complete physical postal address."
        )
    email_alias = _selected_email_alias(
        db,
        principal,
        payload.email_sender_alias_id if "email" in channels else None,
    )
    sms_line = _selected_sms_line(
        db,
        principal,
        payload.sms_voice_line_id if "sms" in channels else None,
    )
    sender_snapshot = _sender_snapshot(email_alias, sms_line)
    property_address = _public_property_address(package)

    _validate_template(payload.email_subject, field_name="email subject")
    _validate_template(payload.email_body, field_name="email body")
    _validate_template(payload.sms_body, field_name="SMS body")

    active = list(
        db.scalars(
            select(DispositionOutreachRevision)
            .where(
                DispositionOutreachRevision.organization_id == principal.organization_id,
                DispositionOutreachRevision.disposition_campaign_id == campaign.id,
                DispositionOutreachRevision.status.in_(ACTIVE_REVISION_STATUSES),
            )
            .with_for_update()
        ).all()
    )
    if any(item.status in {"queued", "sending", "paused", "provider_degraded"} for item in active):
        raise ValueError(
            "Cancel unsent work or finish the current outreach release before drafting a revision."
        )
    for item in active:
        item.status = "invalidated"
        item.cancelled_at = datetime.now(UTC)
        item.lock_version += 1

    revision_number = (
        db.scalar(
            select(func.max(DispositionOutreachRevision.revision_number)).where(
                DispositionOutreachRevision.disposition_campaign_id == campaign.id
            )
        )
        or 0
    ) + 1
    revision = DispositionOutreachRevision(
        organization_id=principal.organization_id,
        disposition_campaign_id=campaign.id,
        disposition_case_id=case.id,
        package_version_id=package.id,
        created_by_user_id=principal.user_id,
        approved_by_user_id=None,
        revision_number=revision_number,
        lock_version=1,
        status="review_required",
        mode="supervised",
        recipient_cap=HARD_RECIPIENT_CAP,
        recipient_manifest_hash="0" * 64,
        approval_hash=None,
        package_source_fingerprint=package.source_fingerprint,
        artifact_sha256=str(package.pdf_sha256),
        email_sender_alias_id=email_alias.id if email_alias else None,
        sms_voice_line_id=sms_line.id if sms_line else None,
        sender_snapshot=sender_snapshot,
        approval_reason=None,
        approved_at=None,
        queued_at=None,
        paused_at=None,
        cancelled_at=None,
        completed_at=None,
    )
    db.add(revision)
    db.flush()

    selections = {item.campaign_recipient_id: item for item in payload.recipients}
    for recipient_id in selection_ids:
        recipient = by_id[recipient_id]
        buyer = db.scalar(
            select(Buyer).where(
                Buyer.id == recipient.buyer_id,
                Buyer.organization_id == principal.organization_id,
            )
        )
        if buyer is None:
            raise ValueError("A prepared buyer is no longer available.")
        variables = {
            "buyer_name": str(recipient.captured_identity.get("buyer_name") or buyer.name),
            "company_name": str(recipient.captured_identity.get("company_name") or ""),
            "property_address": property_address,
            "package_reference": str(case.id),
        }
        for channel in selections[recipient_id].channels:
            delivery = _build_delivery(
                db,
                principal,
                settings=settings,
                revision=revision,
                campaign=campaign,
                package=package,
                recipient=recipient,
                buyer=buyer,
                channel=channel,
                variables=variables,
                email_alias=email_alias,
                sms_line=sms_line,
                email_subject=str(payload.email_subject or ""),
                email_body=str(payload.email_body or ""),
                sms_body=str(payload.sms_body or ""),
            )
            db.add(delivery)
    db.flush()

    deliveries = _revision_deliveries(db, revision.id)
    revision.recipient_manifest_hash = _recipient_manifest_hash(deliveries)
    revision.approval_hash = _approval_hash(revision, deliveries)
    _audit(
        db,
        principal,
        action="disposition.outreach_draft_created",
        revision=revision,
        reason="Immutable supervised outreach revision created for human review.",
        details={
            "revision_number": revision.revision_number,
            "delivery_count": len(deliveries),
            "eligible_count": sum(item.eligibility_status == "eligible" for item in deliveries),
            "approval_hash": revision.approval_hash,
        },
    )
    db.commit()
    return _revision_read(db, revision)


def approve_revision(
    db: Session,
    principal: Principal,
    campaign_id: UUID,
    revision_id: UUID,
    payload: DispositionOutreachApprovalRequest,
) -> DispositionOutreachRevisionRead | None:
    revision = _scoped_revision(db, principal, campaign_id, revision_id, lock=True)
    if revision is None:
        return None
    if revision.status not in {"draft", "review_required"}:
        raise ValueError("Only a revision awaiting review can be approved.")
    if revision.lock_version != payload.expected_lock_version:
        raise ValueError("This outreach revision changed. Refresh before approving it.")
    _require_revision_package_current(db, principal, revision, action="approving outreach")
    deliveries = _revision_deliveries(db, revision.id)
    calculated_manifest = _recipient_manifest_hash(deliveries)
    calculated_approval = _approval_hash(revision, deliveries)
    if revision.recipient_manifest_hash != calculated_manifest:
        raise ValueError("The outreach recipient manifest changed. Create a new revision.")
    if payload.expected_approval_hash != calculated_approval:
        raise ValueError("The outreach content or recipient manifest changed. Refresh and review.")
    if not any(item.eligibility_status == "eligible" for item in deliveries):
        raise ValueError("At least one structurally eligible delivery is required for approval.")

    now = datetime.now(UTC)
    revision.approval_hash = calculated_approval
    revision.status = "approved"
    revision.approved_by_user_id = principal.user_id
    revision.approval_reason = payload.reason
    revision.approved_at = now
    revision.lock_version += 1
    for delivery in deliveries:
        if delivery.status == "prepared" and delivery.eligibility_status == "eligible":
            delivery.status = "approved"
    _audit(
        db,
        principal,
        action="disposition.outreach_approved",
        revision=revision,
        reason=payload.reason,
        details={"approval_hash": calculated_approval, "attestation": True},
    )
    db.commit()
    return _revision_read(db, revision)


def release_revision(
    db: Session,
    principal: Principal,
    campaign_id: UUID,
    revision_id: UUID,
    payload: DispositionOutreachControlRequest,
    *,
    settings: Settings | None = None,
) -> DispositionOutreachRevisionRead | None:
    settings = settings or get_settings()
    revision = _scoped_revision(db, principal, campaign_id, revision_id, lock=True)
    if revision is None:
        return None
    if revision.status not in {"approved", "provider_degraded"}:
        raise ValueError("Only an approved or provider-blocked revision can be released.")
    _check_lock(revision, payload.expected_lock_version)
    _require_approval_integrity(db, principal, revision, action="releasing outreach")
    result = _queue_after_dynamic_preflight(db, principal, revision, settings=settings)
    revision.lock_version += 1
    _audit(
        db,
        principal,
        action="disposition.outreach_released",
        revision=revision,
        reason=payload.reason,
        details=result,
    )
    db.commit()
    return _revision_read(db, revision)


def pause_revision(
    db: Session,
    principal: Principal,
    campaign_id: UUID,
    revision_id: UUID,
    payload: DispositionOutreachControlRequest,
) -> DispositionOutreachRevisionRead | None:
    revision = _scoped_revision(db, principal, campaign_id, revision_id, lock=True)
    if revision is None:
        return None
    if revision.status not in {"queued", "sending", "provider_degraded"}:
        raise ValueError("Only active outreach can be paused.")
    _check_lock(revision, payload.expected_lock_version)
    revision.status = "paused"
    revision.paused_at = datetime.now(UTC)
    revision.lock_version += 1
    _audit(
        db,
        principal,
        action="disposition.outreach_paused",
        revision=revision,
        reason=payload.reason,
        details={"unsent_count": _unsent_count(db, revision.id)},
    )
    db.commit()
    return _revision_read(db, revision)


def resume_revision(
    db: Session,
    principal: Principal,
    campaign_id: UUID,
    revision_id: UUID,
    payload: DispositionOutreachControlRequest,
    *,
    settings: Settings | None = None,
) -> DispositionOutreachRevisionRead | None:
    settings = settings or get_settings()
    revision = _scoped_revision(db, principal, campaign_id, revision_id, lock=True)
    if revision is None:
        return None
    if revision.status not in {"paused", "provider_degraded"}:
        raise ValueError("Only paused or provider-blocked outreach can be resumed.")
    _check_lock(revision, payload.expected_lock_version)
    _require_approval_integrity(db, principal, revision, action="resuming outreach")
    result = _queue_after_dynamic_preflight(db, principal, revision, settings=settings)
    revision.paused_at = None
    revision.lock_version += 1
    _audit(
        db,
        principal,
        action="disposition.outreach_resumed",
        revision=revision,
        reason=payload.reason,
        details=result,
    )
    db.commit()
    return _revision_read(db, revision)


def cancel_unsent(
    db: Session,
    principal: Principal,
    campaign_id: UUID,
    revision_id: UUID,
    payload: DispositionOutreachControlRequest,
) -> DispositionOutreachRevisionRead | None:
    revision = _scoped_revision(db, principal, campaign_id, revision_id, lock=True)
    if revision is None:
        return None
    if revision.status in {"completed", "cancelled", "invalidated"}:
        raise ValueError("This outreach revision has no cancellable unsent work.")
    _check_lock(revision, payload.expected_lock_version)
    cancelled = 0
    for delivery in _revision_deliveries(db, revision.id, lock=True):
        if delivery.status in UNSENT_DELIVERY_STATUSES:
            delivery.status = "cancelled"
            delivery.error_code = "cancelled_by_user"
            delivery.error_message = payload.reason
            cancelled += 1
    if cancelled == 0:
        raise ValueError("No unsent outreach deliveries remain to cancel.")
    revision.status = "cancelled"
    revision.cancelled_at = datetime.now(UTC)
    revision.lock_version += 1
    _audit(
        db,
        principal,
        action="disposition.outreach_unsent_cancelled",
        revision=revision,
        reason=payload.reason,
        details={"cancelled_count": cancelled},
    )
    db.commit()
    return _revision_read(db, revision)


def retry_failed(
    db: Session,
    principal: Principal,
    campaign_id: UUID,
    revision_id: UUID,
    payload: DispositionOutreachControlRequest,
    *,
    settings: Settings | None = None,
) -> DispositionOutreachRevisionRead | None:
    settings = settings or get_settings()
    revision = _scoped_revision(db, principal, campaign_id, revision_id, lock=True)
    if revision is None:
        return None
    if revision.status not in {"completed_with_failures", "provider_degraded", "paused"}:
        raise ValueError("Retry is only available for a failed or provider-blocked revision.")
    _check_lock(revision, payload.expected_lock_version)
    _require_approval_integrity(db, principal, revision, action="retrying failed outreach")
    retryable = [
        item
        for item in _revision_deliveries(db, revision.id, lock=True)
        if item.status == "failed_retryable"
    ]
    if not retryable:
        raise ValueError("No safely retryable deliveries are available.")
    result = _queue_after_dynamic_preflight(
        db,
        principal,
        revision,
        settings=settings,
        candidates=retryable,
    )
    revision.lock_version += 1
    _audit(
        db,
        principal,
        action="disposition.outreach_failed_retried",
        revision=revision,
        reason=payload.reason,
        details=result,
    )
    db.commit()
    return _revision_read(db, revision)


def _scoped_house_case(
    db: Session,
    principal: Principal,
    case_id: UUID,
    *,
    lock: bool = False,
) -> DispositionCase | None:
    statement = select(DispositionCase).where(
        DispositionCase.id == case_id,
        DispositionCase.organization_id == principal.organization_id,
    )
    if lock:
        statement = statement.with_for_update()
    case = db.scalar(statement)
    if case is None:
        return None
    lead = db.scalar(
        select(Lead).where(
            Lead.id == case.lead_id,
            Lead.organization_id == principal.organization_id,
        )
    )
    if lead is None or lead.asset_class != "house":
        raise ValueError("Governed disposition outreach currently supports House deals only.")
    return case


def _prepared_recipients(
    db: Session,
    principal: Principal,
    campaign: DispositionCampaign,
) -> list[DispositionCampaignRecipient]:
    return list(
        db.scalars(
            select(DispositionCampaignRecipient)
            .where(
                DispositionCampaignRecipient.organization_id == principal.organization_id,
                DispositionCampaignRecipient.disposition_campaign_id == campaign.id,
                DispositionCampaignRecipient.status == "prepared_not_sent",
            )
            .order_by(DispositionCampaignRecipient.prepared_at, DispositionCampaignRecipient.id)
        ).all()
    )


def _prepared_recipient_read(
    recipient: DispositionCampaignRecipient,
) -> DispositionOutreachPreparedRecipientRead:
    if recipient.buyer_id is None:
        raise ValueError("Prepared outreach recipients must reference a Stonegate buyer.")
    destinations = recipient.captured_destination or {}
    channels: list[OutreachChannel] = []
    if destinations.get("email"):
        channels.append("email")
    if destinations.get("phone"):
        channels.append("sms")
    return DispositionOutreachPreparedRecipientRead(
        id=recipient.id,
        buyer_id=recipient.buyer_id,
        buyer_name=str(recipient.captured_identity.get("buyer_name") or "Buyer"),
        company_name=recipient.captured_identity.get("company_name"),
        available_channels=channels,
        captured_email=destinations.get("email"),
        captured_phone=destinations.get("phone"),
    )


def _available_senders(db: Session, principal: Principal) -> list[DispositionOutreachSenderRead]:
    aliases = list(
        db.scalars(
            select(EmailSenderAlias)
            .where(
                EmailSenderAlias.organization_id == principal.organization_id,
                EmailSenderAlias.provider == "resend",
                EmailSenderAlias.status == "active",
                EmailSenderAlias.outbound_enabled.is_(True),
            )
            .order_by(EmailSenderAlias.is_default.desc(), EmailSenderAlias.email_address)
        ).all()
    )
    lines = list(
        db.scalars(
            select(VoiceLine)
            .where(
                VoiceLine.organization_id == principal.organization_id,
                VoiceLine.provider == "twilio",
                VoiceLine.department_key == "dispositions",
                VoiceLine.purpose_key == "buyer_relations",
                VoiceLine.status == "active",
            )
            .order_by(VoiceLine.is_default.desc(), VoiceLine.phone_number)
        ).all()
    )
    return [
        DispositionOutreachSenderRead(
            id=item.id,
            channel="email",
            label=item.display_name,
            address=item.email_address,
            is_default=item.is_default,
        )
        for item in aliases
    ] + [
        DispositionOutreachSenderRead(
            id=item.id,
            channel="sms",
            label=item.label,
            address=item.phone_number,
            is_default=item.is_default,
        )
        for item in lines
    ]


def _selected_email_alias(
    db: Session,
    principal: Principal,
    alias_id: UUID | None,
) -> EmailSenderAlias | None:
    if alias_id is None:
        return None
    alias = db.scalar(
        select(EmailSenderAlias).where(
            EmailSenderAlias.id == alias_id,
            EmailSenderAlias.organization_id == principal.organization_id,
            EmailSenderAlias.provider == "resend",
            EmailSenderAlias.status == "active",
            EmailSenderAlias.outbound_enabled.is_(True),
        )
    )
    if alias is None:
        raise ValueError("Select an active outbound Resend sender owned by Stonegate.")
    return alias


def _selected_sms_line(
    db: Session,
    principal: Principal,
    line_id: UUID | None,
) -> VoiceLine | None:
    if line_id is None:
        return None
    line = db.scalar(
        select(VoiceLine).where(
            VoiceLine.id == line_id,
            VoiceLine.organization_id == principal.organization_id,
            VoiceLine.provider == "twilio",
            VoiceLine.department_key == "dispositions",
            VoiceLine.purpose_key == "buyer_relations",
            VoiceLine.status == "active",
        )
    )
    if line is None:
        raise ValueError("Select an active Stonegate Dispositions buyer-relations line.")
    return line


def _sender_snapshot(
    email_alias: EmailSenderAlias | None,
    sms_line: VoiceLine | None,
) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    if email_alias:
        snapshot["email"] = {
            "alias_id": str(email_alias.id),
            "provider": email_alias.provider,
            "display_name": email_alias.display_name,
            "email_address": email_alias.email_address,
            "signature_text": email_alias.signature_text or "",
        }
    if sms_line:
        snapshot["sms"] = {
            "voice_line_id": str(sms_line.id),
            "provider": sms_line.provider,
            "label": sms_line.label,
            "phone_number": sms_line.phone_number,
        }
    return snapshot


def _build_delivery(
    db: Session,
    principal: Principal,
    *,
    settings: Settings,
    revision: DispositionOutreachRevision,
    campaign: DispositionCampaign,
    package: DispositionPackageVersion,
    recipient: DispositionCampaignRecipient,
    buyer: Buyer,
    channel: str,
    variables: dict[str, str],
    email_alias: EmailSenderAlias | None,
    sms_line: VoiceLine | None,
    email_subject: str,
    email_body: str,
    sms_body: str,
) -> DispositionOutreachDelivery:
    destinations = recipient.captured_destination or {}
    if channel == "email":
        captured = str(destinations.get("email") or "")
        normalized = normalize_email(captured) or captured.strip().lower()
        subject = _render_template(email_subject, variables)
        rendered = _render_template(email_body, variables)
        signature = (
            email_alias.signature_text.strip()
            if email_alias and email_alias.signature_text
            else ""
        )
        body_parts = [rendered.rstrip()]
        if signature:
            body_parts.append(signature)
        body_parts.append(_email_outreach_footer(settings))
        body = "\n\n".join(body_parts)
        conversation_id = None
        contact_id = None
        eligibility = _email_preflight(
            db,
            principal,
            settings=settings,
            buyer=buyer,
            captured_destination=normalized,
            alias=email_alias,
        )
    else:
        captured = str(destinations.get("phone") or "")
        normalized = format_e164(captured) or captured
        subject = None
        body = _render_template(sms_body, variables)
        conversation = ensure_buyer_conversation(
            db,
            buyer,
            actor_user_id=principal.user_id,
        )
        db.flush()
        conversation_id = conversation.id
        contact_id = conversation.contact_id
        contact = db.get(Contact, conversation.contact_id)
        eligibility = _sms_preflight(
            db,
            settings=settings,
            buyer=buyer,
            contact=contact,
            captured_destination=normalized,
            line=sms_line,
        )
    body_hash = sha256(body.encode("utf-8")).hexdigest()
    idempotency_key = sha256(
        f"{revision.id}:{recipient.id}:{channel}:{normalized}:{body_hash}".encode()
    ).hexdigest()
    draft_snapshot = dict(eligibility)
    return DispositionOutreachDelivery(
        organization_id=principal.organization_id,
        outreach_revision_id=revision.id,
        disposition_campaign_id=campaign.id,
        disposition_case_id=revision.disposition_case_id,
        package_version_id=package.id,
        disposition_campaign_recipient_id=recipient.id,
        buyer_id=buyer.id,
        contact_id=contact_id,
        conversation_id=conversation_id,
        channel=channel,
        normalized_destination=normalized,
        captured_destination=captured,
        captured_identity={
            "buyer_name": variables["buyer_name"],
            "company_name": variables["company_name"] or None,
        },
        subject=subject,
        body=body,
        body_hash=body_hash,
        idempotency_key=idempotency_key,
        eligibility_status="eligible" if eligibility["structurally_eligible"] else "ineligible",
        eligibility_snapshot={"draft": draft_snapshot, "latest": draft_snapshot},
        exclusion_reason=(
            None
            if eligibility["structurally_eligible"]
            else "; ".join(str(item) for item in eligibility["permanent_blockers"])
        ),
        status="prepared" if eligibility["structurally_eligible"] else "ineligible",
        provider=None,
        provider_message_id=None,
        communication_record_id=None,
        communication_dispatch_id=None,
        attempt_count=0,
        next_attempt_at=None,
        processing_started_at=None,
        processing_token=None,
        provider_accepted_at=None,
        sent_at=None,
        delivered_at=None,
        replied_at=None,
        failed_at=None,
        error_code=None,
        error_message=None,
    )


def _email_preflight(
    db: Session,
    principal: Principal,
    *,
    settings: Settings,
    buyer: Buyer,
    captured_destination: str,
    alias: EmailSenderAlias | None,
) -> dict[str, Any]:
    permanent: list[str] = []
    transient: list[str] = []
    if not settings.disposition_outreach_physical_postal_address.strip():
        permanent.append(
            "Email outreach requires Stonegate's complete physical postal address."
        )
    current = buyer.normalized_email or normalize_email(buyer.email)
    if not captured_destination or normalize_email(captured_destination) is None:
        permanent.append("A valid captured buyer email address is required.")
    if not current or current != captured_destination:
        permanent.append("The buyer email changed after recipient preparation.")
    permanent.extend(_buyer_relationship_blockers(buyer))
    suppression = db.scalar(
        select(SuppressionRecord.id).where(
            SuppressionRecord.organization_id == principal.organization_id,
            SuppressionRecord.channel.in_(("email", "all")),
            SuppressionRecord.normalized_address == captured_destination,
            SuppressionRecord.status == "active",
        )
    )
    if suppression is not None:
        permanent.append("This buyer email address is actively suppressed.")
    if alias is None:
        permanent.append("An active Resend sender is required.")
    if not settings.communication_simulation_enabled and (
        settings.email_provider != "resend" or settings.email_configuration_blockers
    ):
        transient.append("Resend delivery is not currently configured.")
    return _preflight_snapshot(permanent, transient)


def _email_outreach_footer(settings: Settings) -> str:
    postal_address = settings.disposition_outreach_physical_postal_address.strip()
    if not postal_address:
        raise ValueError(
            "Email outreach requires DISPOSITION_OUTREACH_PHYSICAL_POSTAL_ADDRESS "
            "to contain Stonegate's complete physical postal address."
        )
    return (
        "This Stonegate Home Buyers property-opportunity email is a solicitation.\n"
        f"{postal_address}\n"
        "To stop receiving these emails, reply UNSUBSCRIBE."
    )


def _sms_preflight(
    db: Session,
    *,
    settings: Settings,
    buyer: Buyer,
    contact: Contact | None,
    captured_destination: str,
    line: VoiceLine | None,
) -> dict[str, Any]:
    permanent = _buyer_relationship_blockers(buyer)
    transient: list[str] = []
    current = buyer.normalized_phone or format_e164(buyer.phone)
    if not captured_destination or format_e164(captured_destination) is None:
        permanent.append("A valid captured buyer mobile number is required.")
    if not current or current != captured_destination:
        permanent.append("The buyer phone number changed after recipient preparation.")
    if line is None:
        permanent.append("An active Dispositions buyer-relations line is required.")
    if contact is None:
        permanent.append("The buyer communication contact is unavailable.")
    else:
        evaluation = evaluate_sms_eligibility(db, contact, settings=settings)
        for blocker in evaluation.blockers:
            if blocker.startswith("Text messaging is outside") or blocker.startswith(
                "Twilio SMS is not configured"
            ):
                transient.append(blocker)
            else:
                permanent.append(blocker)
    all_channel_suppression = db.scalar(
        select(SuppressionRecord.id).where(
            SuppressionRecord.organization_id == buyer.organization_id,
            SuppressionRecord.channel == "all",
            SuppressionRecord.normalized_address == captured_destination,
            SuppressionRecord.status == "active",
        )
    )
    if all_channel_suppression is not None:
        permanent.append("This buyer number is suppressed from all communications.")
    return _preflight_snapshot(permanent, transient)


def _preflight_snapshot(permanent: list[str], transient: list[str]) -> dict[str, Any]:
    permanent = list(dict.fromkeys(permanent))
    transient = list(dict.fromkeys(transient))
    return {
        "structurally_eligible": not permanent,
        "sendable_now": not permanent and not transient,
        "permanent_blockers": permanent,
        "transient_blockers": transient,
        "checked_at": datetime.now(UTC).isoformat(),
    }


def _buyer_relationship_blockers(buyer: Buyer) -> list[str]:
    blockers: list[str] = []
    if buyer.status != "active":
        blockers.append("The buyer is not active.")
    if buyer.relationship_status == "do_not_contact":
        blockers.append("The buyer relationship is marked do not contact.")
    if buyer.archived_at is not None:
        blockers.append("The buyer record is archived.")
    return blockers


def _queue_after_dynamic_preflight(
    db: Session,
    principal: Principal,
    revision: DispositionOutreachRevision,
    *,
    settings: Settings,
    candidates: list[DispositionOutreachDelivery] | None = None,
) -> dict[str, Any]:
    deliveries = candidates or [
        item
        for item in _revision_deliveries(db, revision.id, lock=True)
        if item.status in {"approved", "queued", "failed_retryable"}
    ]
    queued = 0
    permanently_blocked = 0
    temporarily_blocked = 0
    for delivery in deliveries:
        buyer = db.scalar(
            select(Buyer).where(
                Buyer.id == delivery.buyer_id,
                Buyer.organization_id == principal.organization_id,
            )
        )
        if buyer is None:
            latest = _preflight_snapshot(["The buyer record is unavailable."], [])
        elif delivery.channel == "email":
            alias = _selected_email_alias_for_revision(db, principal, revision)
            latest = _email_preflight(
                db,
                principal,
                settings=settings,
                buyer=buyer,
                captured_destination=delivery.normalized_destination,
                alias=alias,
            )
        else:
            line = _selected_sms_line_for_revision(db, principal, revision)
            contact = db.get(Contact, delivery.contact_id) if delivery.contact_id else None
            latest = _sms_preflight(
                db,
                settings=settings,
                buyer=buyer,
                contact=contact,
                captured_destination=delivery.normalized_destination,
                line=line,
            )
        snapshot = dict(delivery.eligibility_snapshot or {})
        snapshot["latest"] = latest
        delivery.eligibility_snapshot = snapshot
        if latest["permanent_blockers"]:
            delivery.eligibility_status = "ineligible"
            delivery.exclusion_reason = "; ".join(latest["permanent_blockers"])
            delivery.error_code = "dynamic_preflight_excluded"
            delivery.error_message = delivery.exclusion_reason
            if any("suppressed" in item.lower() for item in latest["permanent_blockers"]):
                delivery.status = "suppressed"
            elif any(
                phrase in item.lower()
                for item in latest["permanent_blockers"]
                for phrase in ("consent", "do not contact")
            ):
                delivery.status = "opted_out"
            else:
                delivery.status = "ineligible"
            permanently_blocked += 1
        elif latest["transient_blockers"]:
            delivery.error_code = "dynamic_preflight_blocked"
            delivery.error_message = "; ".join(latest["transient_blockers"])
            if delivery.status == "queued":
                delivery.status = "approved"
            temporarily_blocked += 1
        else:
            delivery.status = "queued"
            delivery.next_attempt_at = datetime.now(UTC)
            delivery.processing_started_at = None
            delivery.processing_token = None
            delivery.error_code = None
            delivery.error_message = None
            queued += 1
    now = datetime.now(UTC)
    if queued:
        revision.status = "queued"
        revision.queued_at = revision.queued_at or now
        revision.completed_at = None
        _mark_first_live_release(db, principal, revision, released_at=now)
    elif temporarily_blocked:
        revision.status = "provider_degraded"
    else:
        revision.status = "completed_with_failures"
        revision.completed_at = now
    return {
        "queued_count": queued,
        "permanently_blocked_count": permanently_blocked,
        "temporarily_blocked_count": temporarily_blocked,
    }


def _mark_first_live_release(
    db: Session,
    principal: Principal,
    revision: DispositionOutreachRevision,
    *,
    released_at: datetime,
) -> None:
    """Record the business transition only after at least one delivery is sendable."""
    campaign = db.scalar(
        select(DispositionCampaign).where(
            DispositionCampaign.id == revision.disposition_campaign_id,
            DispositionCampaign.organization_id == principal.organization_id,
        )
    )
    if campaign is None:
        raise ValueError("The approved outreach campaign is unavailable.")
    if campaign.released_at is None:
        campaign.released_at = released_at

    case = db.scalar(
        select(DispositionCase).where(
            DispositionCase.id == revision.disposition_case_id,
            DispositionCase.organization_id == principal.organization_id,
        )
    )
    if case is None:
        raise ValueError("The disposition case is unavailable.")
    if case.status == "buyer_matching":
        case.status = "marketed"


def _selected_email_alias_for_revision(
    db: Session,
    principal: Principal,
    revision: DispositionOutreachRevision,
) -> EmailSenderAlias | None:
    if revision.email_sender_alias_id is None:
        return None
    alias = db.scalar(
        select(EmailSenderAlias).where(
            EmailSenderAlias.id == revision.email_sender_alias_id,
            EmailSenderAlias.organization_id == principal.organization_id,
            EmailSenderAlias.provider == "resend",
            EmailSenderAlias.status == "active",
            EmailSenderAlias.outbound_enabled.is_(True),
        )
    )
    expected = (revision.sender_snapshot or {}).get("email") or {}
    if alias is None or (
        alias.email_address != expected.get("email_address")
        or alias.display_name != expected.get("display_name")
        or (alias.signature_text or "") != expected.get("signature_text", "")
    ):
        return None
    return alias


def _selected_sms_line_for_revision(
    db: Session,
    principal: Principal,
    revision: DispositionOutreachRevision,
) -> VoiceLine | None:
    if revision.sms_voice_line_id is None:
        return None
    line = db.scalar(
        select(VoiceLine).where(
            VoiceLine.id == revision.sms_voice_line_id,
            VoiceLine.organization_id == principal.organization_id,
            VoiceLine.provider == "twilio",
            VoiceLine.department_key == "dispositions",
            VoiceLine.purpose_key == "buyer_relations",
            VoiceLine.status == "active",
        )
    )
    expected = (revision.sender_snapshot or {}).get("sms") or {}
    if line is None or line.phone_number != expected.get("phone_number"):
        return None
    return line


def _require_revision_package_current(
    db: Session,
    principal: Principal,
    revision: DispositionOutreachRevision,
    *,
    action: str,
) -> DispositionPackageVersion:
    case = _scoped_house_case(db, principal, revision.disposition_case_id)
    if case is None:
        raise ValueError("Disposition case not found.")
    package = require_current_approved_version(db, principal, case, action=action)
    if (
        package.id != revision.package_version_id
        or package.source_fingerprint != revision.package_source_fingerprint
        or package.pdf_sha256 != revision.artifact_sha256
    ):
        raise ValueError(
            "The approved package changed. Create and approve a new outreach revision."
        )
    return package


def _require_approval_integrity(
    db: Session,
    principal: Principal,
    revision: DispositionOutreachRevision,
    *,
    action: str,
) -> None:
    _require_revision_package_current(db, principal, revision, action=action)
    require_stored_approval_integrity(db, revision)


def require_stored_approval_integrity(
    db: Session,
    revision: DispositionOutreachRevision,
    *,
    lock_deliveries: bool = False,
) -> list[DispositionOutreachDelivery]:
    """Recompute the exact immutable approval envelope from stored provider inputs."""
    if revision.approved_by_user_id is None or revision.approved_at is None:
        raise ValueError("Human outreach approval is required before live release.")
    deliveries = _revision_deliveries(db, revision.id, lock=lock_deliveries)
    if not deliveries:
        raise ValueError("The approved outreach revision has no stored deliveries.")
    for delivery in deliveries:
        if (
            delivery.organization_id != revision.organization_id
            or delivery.outreach_revision_id != revision.id
        ):
            raise ValueError("The approved delivery scope no longer matches its revision.")
        calculated_body_hash = sha256(delivery.body.encode("utf-8")).hexdigest()
        if delivery.body_hash != calculated_body_hash:
            raise ValueError("The approved outreach body changed after human approval.")
    if revision.recipient_manifest_hash != _recipient_manifest_hash(deliveries):
        raise ValueError("The approved recipient manifest no longer matches the stored deliveries.")
    if revision.approval_hash != _approval_hash(revision, deliveries):
        raise ValueError("The approved outreach content or sender binding changed.")
    return deliveries


def _scoped_revision(
    db: Session,
    principal: Principal,
    campaign_id: UUID,
    revision_id: UUID,
    *,
    lock: bool = False,
) -> DispositionOutreachRevision | None:
    statement = select(DispositionOutreachRevision).where(
        DispositionOutreachRevision.id == revision_id,
        DispositionOutreachRevision.disposition_campaign_id == campaign_id,
        DispositionOutreachRevision.organization_id == principal.organization_id,
    )
    if lock:
        statement = statement.with_for_update()
    return db.scalar(statement)


def _revision_deliveries(
    db: Session,
    revision_id: UUID,
    *,
    lock: bool = False,
) -> list[DispositionOutreachDelivery]:
    statement = (
        select(DispositionOutreachDelivery)
        .where(DispositionOutreachDelivery.outreach_revision_id == revision_id)
        .order_by(
            DispositionOutreachDelivery.buyer_id,
            DispositionOutreachDelivery.channel,
            DispositionOutreachDelivery.id,
        )
    )
    if lock:
        statement = statement.with_for_update()
    return list(db.scalars(statement).all())


def _recipient_manifest(deliveries: list[DispositionOutreachDelivery]) -> list[dict[str, Any]]:
    manifest = []
    for delivery in deliveries:
        draft = (delivery.eligibility_snapshot or {}).get("draft") or {}
        manifest.append(
            {
                "campaign_recipient_id": str(delivery.disposition_campaign_recipient_id),
                "buyer_id": str(delivery.buyer_id),
                "channel": delivery.channel,
                "destination": delivery.normalized_destination,
                "identity": delivery.captured_identity,
                "subject": delivery.subject,
                "body": delivery.body,
                "body_hash": delivery.body_hash,
                "idempotency_key": delivery.idempotency_key,
                "draft_eligibility": draft,
            }
        )
    return manifest


def _recipient_manifest_hash(deliveries: list[DispositionOutreachDelivery]) -> str:
    return _canonical_hash(_recipient_manifest(deliveries))


def _approval_hash(
    revision: DispositionOutreachRevision,
    deliveries: list[DispositionOutreachDelivery],
) -> str:
    return _canonical_hash(
        {
            "organization_id": str(revision.organization_id),
            "campaign_id": str(revision.disposition_campaign_id),
            "case_id": str(revision.disposition_case_id),
            "package_version_id": str(revision.package_version_id),
            "revision_number": revision.revision_number,
            "mode": revision.mode,
            "recipient_cap": revision.recipient_cap,
            "package_source_fingerprint": revision.package_source_fingerprint,
            "artifact_sha256": revision.artifact_sha256,
            "sender_snapshot": revision.sender_snapshot,
            "recipient_manifest": _recipient_manifest(deliveries),
        }
    )


def _canonical_hash(value: object) -> str:
    serialized = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(serialized.encode("utf-8")).hexdigest()


def _validate_template(value: str | None, *, field_name: str) -> None:
    if value is None:
        return
    for _, field, format_spec, conversion in Formatter().parse(value):
        if field is None:
            continue
        if field not in ALLOWED_TEMPLATE_FIELDS:
            raise ValueError(f"Unsupported placeholder {{{field}}} in {field_name}.")
        if format_spec or conversion:
            raise ValueError(f"Formatting directives are not allowed in {field_name}.")


def _render_template(value: str, variables: dict[str, str]) -> str:
    return value.format_map(variables).strip()


def _public_property_address(package: DispositionPackageVersion) -> str:
    property_snapshot = (package.public_snapshot or {}).get("property") or {}
    return str(property_snapshot.get("address") or "Address unavailable")


def _revision_read(
    db: Session,
    revision: DispositionOutreachRevision,
) -> DispositionOutreachRevisionRead:
    deliveries = _revision_deliveries(db, revision.id)
    counts = Counter(item.status for item in deliveries)
    return DispositionOutreachRevisionRead(
        id=revision.id,
        campaign_id=revision.disposition_campaign_id,
        case_id=revision.disposition_case_id,
        package_version_id=revision.package_version_id,
        revision_number=revision.revision_number,
        lock_version=revision.lock_version,
        status=cast(OutreachRevisionStatus, revision.status),
        mode=cast(Literal["supervised"], revision.mode),
        recipient_cap=revision.recipient_cap,
        recipient_manifest_hash=revision.recipient_manifest_hash,
        approval_hash=revision.approval_hash,
        package_source_fingerprint=revision.package_source_fingerprint,
        artifact_sha256=revision.artifact_sha256,
        sender_snapshot=revision.sender_snapshot,
        created_by_user_id=revision.created_by_user_id,
        approved_by_user_id=revision.approved_by_user_id,
        approval_reason=revision.approval_reason,
        approved_at=revision.approved_at,
        queued_at=revision.queued_at,
        paused_at=revision.paused_at,
        cancelled_at=revision.cancelled_at,
        completed_at=revision.completed_at,
        delivery_counts=dict(counts),
        deliveries=[_delivery_read(item) for item in deliveries],
        created_at=revision.created_at,
    )


def _delivery_read(delivery: DispositionOutreachDelivery) -> DispositionOutreachDeliveryRead:
    identity = delivery.captured_identity or {}
    return DispositionOutreachDeliveryRead(
        id=delivery.id,
        campaign_recipient_id=delivery.disposition_campaign_recipient_id,
        buyer_id=delivery.buyer_id,
        conversation_id=delivery.conversation_id,
        buyer_name=str(identity.get("buyer_name") or "Buyer"),
        company_name=identity.get("company_name"),
        channel=cast(OutreachChannel, delivery.channel),
        destination=delivery.captured_destination,
        subject=delivery.subject,
        body=delivery.body,
        body_hash=delivery.body_hash,
        eligibility_status=cast(
            Literal["eligible", "ineligible"], delivery.eligibility_status
        ),
        eligibility_snapshot=delivery.eligibility_snapshot,
        exclusion_reason=delivery.exclusion_reason,
        status=delivery.status,
        attempt_count=delivery.attempt_count,
        provider=delivery.provider,
        provider_message_id=delivery.provider_message_id,
        created_at=delivery.created_at,
    )


def _check_lock(revision: DispositionOutreachRevision, expected: int) -> None:
    if revision.lock_version != expected:
        raise ValueError("This outreach revision changed. Refresh before continuing.")


def _unsent_count(db: Session, revision_id: UUID) -> int:
    return int(
        db.scalar(
            select(func.count(DispositionOutreachDelivery.id)).where(
                DispositionOutreachDelivery.outreach_revision_id == revision_id,
                DispositionOutreachDelivery.status.in_(UNSENT_DELIVERY_STATUSES),
            )
        )
        or 0
    )


def _audit(
    db: Session,
    principal: Principal,
    *,
    action: str,
    revision: DispositionOutreachRevision,
    reason: str,
    details: dict[str, object],
) -> None:
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action=action,
            entity_type="disposition_outreach_revision",
            entity_id=revision.id,
            previous_value=None,
            new_value={
                "campaign_id": str(revision.disposition_campaign_id),
                "case_id": str(revision.disposition_case_id),
                "status": revision.status,
                **details,
            },
            reason=reason,
        )
    )
