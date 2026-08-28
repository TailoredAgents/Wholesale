from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import exists, select
from sqlalchemy.orm import Session
from twilio.base.exceptions import TwilioRestException  # type: ignore[import-untyped]

from app.core.config import Settings
from app.integrations.communications import (
    OutboundMessageRequest,
    SimulatedCommunicationProvider,
)
from app.integrations.email_delivery import EmailDeliveryRequest, EmailProviderError
from app.integrations.resend_email import ResendEmailError
from app.integrations.twilio_messaging import (
    TwilioMessagingError,
    TwilioMessagingProvider,
)
from app.models.foundation import (
    ActivityEvent,
    AuditEvent,
    Buyer,
    BuyerEngagement,
    CommunicationDispatch,
    CommunicationParticipant,
    CommunicationRecord,
    Contact,
    Conversation,
    ConversationContextLink,
    DispositionCampaign,
    DispositionCampaignRecipient,
    DispositionCase,
    DispositionOutreachDelivery,
    DispositionOutreachRevision,
    DispositionPackageVersion,
    DispositionReplyLink,
    EmailSenderAlias,
    SuppressionRecord,
    Task,
    VoiceLine,
)
from app.services.communication_compliance import evaluate_sms_eligibility, format_e164
from app.services.communication_participants import record_email_participants
from app.services.disposition_outreach import require_stored_approval_integrity
from app.services.email import get_email_delivery_provider
from app.services.inbox import ensure_buyer_conversation, update_conversation_activity

CLAIM_LEASE = timedelta(minutes=5)
ACTIVE_REVISION_STATUSES = {"queued", "sending"}
SENDABLE_DELIVERY_STATUSES = {"queued", "claimed"}
DELIVERY_TERMINAL_STATUSES = {
    "ineligible",
    "delivered",
    "replied",
    "failed_retryable",
    "failed_terminal",
    "delivery_unknown",
    "suppressed",
    "opted_out",
    "cancelled",
}
DELIVERY_FAILURE_STATUSES = {
    "ineligible",
    "failed_retryable",
    "failed_terminal",
    "delivery_unknown",
    "suppressed",
    "opted_out",
}
COMMUNICATION_TO_DELIVERY_STATUS = {
    "pending": "provider_accepted",
    "accepted": "provider_accepted",
    "queued": "provider_accepted",
    "sending": "sent",
    "sent": "sent",
    "delivery_delayed": "sent",
    "delivered": "delivered",
    "read": "delivered",
    "received": "delivered",
    "bounced": "failed_terminal",
    "canceled": "failed_terminal",
    "failed": "failed_terminal",
    "undelivered": "failed_terminal",
    "complained": "suppressed",
    "suppressed": "suppressed",
}
DELIVERY_STATUS_RANK = {
    "prepared": 0,
    "approved": 5,
    "queued": 10,
    "claimed": 15,
    "provider_accepted": 20,
    "sent": 30,
    "delivered": 40,
    "replied": 50,
}


class DeliveryPreflightError(RuntimeError):
    def __init__(self, message: str, *, status: str = "ineligible") -> None:
        super().__init__(message)
        self.delivery_status = status


class DeliveryAlreadyProcessed(RuntimeError):
    pass


class DeliveryDeferred(RuntimeError):
    """The operator changed campaign state before provider submission."""

    pass


def process_next_disposition_outreach_delivery(
    db: Session,
    settings: Settings,
) -> UUID | None:
    """Claim and process one approved buyer message without blocking other worker lanes."""
    delivery_id = _claim_next_delivery(db)
    if delivery_id is None:
        return None
    provider_started = False
    try:
        revision, delivery = _locked_revision_delivery(db, delivery_id)
        if delivery is None:
            return delivery_id
        if revision is None:
            _fail_delivery(db, delivery, "revision_missing", "Outreach revision is missing.")
            return delivery_id
        conversation, contact = _live_preflight(db, settings, delivery, revision)
        _ensure_case_context(db, conversation, delivery, revision.created_by_user_id)
        _ensure_dispatch(db, settings, delivery, revision, conversation, contact)
        db.commit()

        (
            loaded_revision,
            delivery,
            loaded_conversation,
            loaded_contact,
            loaded_dispatch,
        ) = _provider_boundary_context(
            db,
            settings,
            delivery_id,
            allowed_delivery_statuses={"claimed"},
        )

        if delivery.channel == "email":
            provider_started = True
            _send_email(
                db,
                settings,
                delivery,
                loaded_revision,
                loaded_conversation,
                loaded_contact,
                loaded_dispatch,
            )
        else:
            # Twilio does not offer a caller-supplied idempotency key. Persist the
            # uncertain state before crossing the provider boundary so a worker
            # crash can never turn into an automatic duplicate SMS.
            _mark_sms_submission_uncertain(db, delivery, loaded_dispatch)
            processing_token = delivery.processing_token
            db.commit()
            (
                loaded_revision,
                delivery,
                loaded_conversation,
                loaded_contact,
                loaded_dispatch,
            ) = _provider_boundary_context(
                db,
                settings,
                delivery_id,
                allowed_delivery_statuses={"delivery_unknown"},
                expected_processing_token=processing_token,
            )
            provider_started = True
            _send_sms(
                db,
                settings,
                delivery,
                loaded_revision,
                loaded_conversation,
                loaded_contact,
                loaded_dispatch,
            )
        _sync_revision_status(db, loaded_revision.id)
        db.commit()
    except DeliveryPreflightError as exc:
        db.rollback()
        _revision, delivery = _locked_revision_delivery(db, delivery_id)
        if delivery is not None:
            _fail_delivery(
                db,
                delivery,
                "preflight_blocked",
                str(exc),
                status=exc.delivery_status,
            )
    except DeliveryAlreadyProcessed:
        db.commit()
    except DeliveryDeferred:
        db.commit()
    except TwilioMessagingError as exc:
        db.rollback()
        _revision, delivery = _locked_revision_delivery(db, delivery_id)
        if delivery is not None:
            provider_rejected = isinstance(exc.__cause__, TwilioRestException)
            _fail_delivery(
                db,
                delivery,
                "twilio_rejected" if provider_rejected else "twilio_delivery_unknown",
                str(exc),
                status="failed_terminal" if provider_rejected else "delivery_unknown",
            )
    except EmailProviderError as exc:
        db.rollback()
        _revision, delivery = _locked_revision_delivery(db, delivery_id)
        if delivery is not None:
            retry_safe = isinstance(exc, ResendEmailError) and exc.retry_safe
            acceptance_unknown = (
                not isinstance(exc, ResendEmailError) or exc.acceptance_unknown
            )
            _fail_delivery(
                db,
                delivery,
                (
                    "email_delivery_unknown"
                    if acceptance_unknown
                    else "email_provider_retryable"
                    if retry_safe
                    else "email_provider_rejected"
                ),
                str(exc),
                status=(
                    "delivery_unknown"
                    if acceptance_unknown
                    else "failed_retryable"
                    if retry_safe
                    else "failed_terminal"
                ),
            )
    except Exception as exc:
        db.rollback()
        _revision, delivery = _locked_revision_delivery(db, delivery_id)
        if delivery is not None:
            _fail_delivery(
                db,
                delivery,
                "post_provider_uncertain" if provider_started else "delivery_error",
                "Provider acceptance could not be reconciled."
                if provider_started
                else str(exc),
                status=(
                    "delivery_unknown" if provider_started else "failed_retryable"
                ),
            )
    return delivery_id


def _mark_sms_submission_uncertain(
    db: Session,
    delivery: DispositionOutreachDelivery,
    dispatch: CommunicationDispatch,
) -> None:
    delivery.status = "delivery_unknown"
    delivery.error_code = "provider_submission_in_progress"
    delivery.error_message = (
        "Twilio submission started; provider acceptance has not yet been recorded."
    )
    dispatch.status = "delivery_unknown"
    dispatch.error_code = delivery.error_code
    dispatch.error_message = delivery.error_message


def process_next_disposition_outreach_reconciliation(
    db: Session,
    _settings: Settings,
) -> UUID | None:
    communication = _next_unlinked_buyer_reply(db)
    if communication is not None:
        _reconcile_reply(db, communication)
        db.commit()
        return UUID(str(communication.id))
    delivery_id = _next_delivery_id_needing_reconciliation(db)
    if delivery_id is not None:
        _revision, delivery = _locked_revision_delivery(db, delivery_id)
        if delivery is not None and _delivery_needs_reconciliation(delivery):
            _reconcile_delivery_status(db, delivery)
        db.commit()
        return UUID(str(delivery_id))
    return None


def _claim_next_delivery(db: Session) -> UUID | None:
    now = datetime.now(UTC)
    stale_before = now - CLAIM_LEASE
    candidate = db.execute(
        select(
            DispositionOutreachRevision.id,
            DispositionOutreachDelivery.id,
        )
        .join(
            DispositionOutreachDelivery,
            DispositionOutreachRevision.id
            == DispositionOutreachDelivery.outreach_revision_id,
        )
        .where(
            DispositionOutreachDelivery.status.in_(("queued", "claimed")),
            (
                DispositionOutreachDelivery.next_attempt_at.is_(None)
                | (DispositionOutreachDelivery.next_attempt_at <= now)
            ),
            (
                (DispositionOutreachDelivery.status == "queued")
                | (DispositionOutreachDelivery.processing_started_at <= stale_before)
            ),
            DispositionOutreachRevision.status.in_(tuple(ACTIVE_REVISION_STATUSES)),
        )
        .order_by(DispositionOutreachDelivery.created_at.asc())
        .limit(1)
    ).first()
    if candidate is None:
        return None
    revision_id, delivery_id = candidate
    revision = db.scalar(
        select(DispositionOutreachRevision)
        .where(DispositionOutreachRevision.id == revision_id)
        .with_for_update()
    )
    delivery = db.scalar(
        select(DispositionOutreachDelivery)
        .where(
            DispositionOutreachDelivery.id == delivery_id,
            DispositionOutreachDelivery.outreach_revision_id == revision_id,
        )
        .with_for_update()
    )
    if revision is None or delivery is None:
        db.rollback()
        return None
    still_claimable = (
        revision.status in ACTIVE_REVISION_STATUSES
        and delivery.status in {"queued", "claimed"}
        and (
            delivery.next_attempt_at is None
            or _as_utc(delivery.next_attempt_at) <= now
        )
        and (
            delivery.status == "queued"
            or (
                delivery.processing_started_at is not None
                and _as_utc(delivery.processing_started_at) <= stale_before
            )
        )
    )
    if not still_claimable:
        db.rollback()
        return None
    delivery.status = "claimed"
    delivery.processing_token = uuid4()
    delivery.processing_started_at = now
    delivery.attempt_count += 1
    if revision.status == "queued":
        revision.status = "sending"
    db.commit()
    return UUID(str(delivery.id))


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _locked_revision_delivery(
    db: Session,
    delivery_id: UUID,
) -> tuple[DispositionOutreachRevision | None, DispositionOutreachDelivery | None]:
    """Lock revision before delivery everywhere that can also update revision state."""
    revision_id = db.scalar(
        select(DispositionOutreachDelivery.outreach_revision_id).where(
            DispositionOutreachDelivery.id == delivery_id
        )
    )
    if revision_id is None:
        return None, None
    revision = db.scalar(
        select(DispositionOutreachRevision)
        .where(DispositionOutreachRevision.id == revision_id)
        .with_for_update()
    )
    delivery = db.scalar(
        select(DispositionOutreachDelivery)
        .where(DispositionOutreachDelivery.id == delivery_id)
        .with_for_update()
    )
    if delivery is None or delivery.outreach_revision_id != revision_id:
        return revision, None
    return revision, delivery


def _provider_boundary_context(
    db: Session,
    settings: Settings,
    delivery_id: UUID,
    *,
    allowed_delivery_statuses: set[str],
    expected_processing_token: UUID | None = None,
) -> tuple[
    DispositionOutreachRevision,
    DispositionOutreachDelivery,
    Conversation,
    Contact,
    CommunicationDispatch,
]:
    """Fence the exact approved request immediately before provider submission.

    Revision is always locked before its deliveries so pause/cancel and the worker use
    one lock order. The transaction remains open across the provider call; therefore an
    operator control cannot report success while this worker later submits the message.
    """
    revision_id = db.scalar(
        select(DispositionOutreachDelivery.outreach_revision_id).where(
            DispositionOutreachDelivery.id == delivery_id
        )
    )
    if revision_id is None:
        raise DeliveryAlreadyProcessed
    revision = db.scalar(
        select(DispositionOutreachRevision)
        .where(DispositionOutreachRevision.id == revision_id)
        .with_for_update()
    )
    if revision is None:
        raise DeliveryPreflightError("Outreach revision is missing.")
    try:
        locked_deliveries = require_stored_approval_integrity(
            db,
            revision,
            lock_deliveries=True,
        )
    except ValueError as exc:
        raise DeliveryPreflightError(str(exc)) from exc
    delivery = next(
        (candidate for candidate in locked_deliveries if candidate.id == delivery_id),
        None,
    )
    if delivery is None:
        raise DeliveryPreflightError("The approved outreach delivery is missing.")
    if (
        expected_processing_token is not None
        and delivery.processing_token != expected_processing_token
    ):
        raise DeliveryAlreadyProcessed
    if revision.status not in ACTIVE_REVISION_STATUSES:
        _defer_delivery_for_operator_control(db, delivery, revision)
        raise DeliveryDeferred

    conversation, contact = _live_preflight(
        db,
        settings,
        delivery,
        revision,
        allowed_delivery_statuses=allowed_delivery_statuses,
    )
    dispatch = (
        db.get(CommunicationDispatch, delivery.communication_dispatch_id)
        if delivery.communication_dispatch_id
        else None
    )
    if (
        dispatch is None
        or dispatch.organization_id != delivery.organization_id
        or dispatch.conversation_id != conversation.id
        or dispatch.contact_id != contact.id
        or dispatch.channel != delivery.channel
        or dispatch.recipient != delivery.normalized_destination
    ):
        raise DeliveryPreflightError(
            "The approved dispatch context changed before provider submission."
        )
    request_hash = _provider_request_hash(db, delivery, revision)
    if dispatch.request_body_hash != request_hash:
        raise DeliveryPreflightError(
            "The exact provider request changed after human approval."
        )
    return revision, delivery, conversation, contact, dispatch


def _defer_delivery_for_operator_control(
    db: Session,
    delivery: DispositionOutreachDelivery,
    revision: DispositionOutreachRevision,
) -> None:
    dispatch = (
        db.get(CommunicationDispatch, delivery.communication_dispatch_id)
        if delivery.communication_dispatch_id
        else None
    )
    if revision.status == "paused":
        delivery.status = "queued"
        delivery.error_code = None
        delivery.error_message = None
        if dispatch is not None and dispatch.communication_record_id is None:
            dispatch.status = "pending"
            dispatch.error_code = None
            dispatch.error_message = None
    else:
        delivery.status = "cancelled"
        delivery.error_code = "cancelled_before_provider_submission"
        delivery.error_message = "Outreach was cancelled before provider submission."
        if dispatch is not None and dispatch.communication_record_id is None:
            dispatch.status = "cancelled"
            dispatch.error_code = delivery.error_code
            dispatch.error_message = delivery.error_message
            dispatch.completed_at = datetime.now(UTC)
    delivery.processing_started_at = None
    delivery.processing_token = None


def _live_preflight(
    db: Session,
    settings: Settings,
    delivery: DispositionOutreachDelivery,
    revision: DispositionOutreachRevision,
    *,
    allowed_delivery_statuses: set[str] | None = None,
) -> tuple[Conversation, Contact]:
    allowed_delivery_statuses = allowed_delivery_statuses or {"claimed"}
    if (
        delivery.status not in allowed_delivery_statuses
        or revision.status not in ACTIVE_REVISION_STATUSES
    ):
        raise DeliveryPreflightError("The campaign is not currently released for delivery.")
    if revision.approval_hash is None or revision.approved_by_user_id is None:
        raise DeliveryPreflightError("The exact outreach revision is not approved.")
    case = db.get(DispositionCase, delivery.disposition_case_id)
    package = db.get(DispositionPackageVersion, delivery.package_version_id)
    campaign = db.get(DispositionCampaign, delivery.disposition_campaign_id)
    prepared = db.get(
        DispositionCampaignRecipient,
        delivery.disposition_campaign_recipient_id,
    )
    if (
        case is None
        or package is None
        or campaign is None
        or prepared is None
        or revision.organization_id != delivery.organization_id
        or case.organization_id != delivery.organization_id
        or package.organization_id != delivery.organization_id
        or campaign.organization_id != delivery.organization_id
        or prepared.organization_id != delivery.organization_id
        or revision.disposition_case_id != delivery.disposition_case_id
        or revision.disposition_campaign_id != delivery.disposition_campaign_id
        or revision.package_version_id != delivery.package_version_id
        or campaign.disposition_case_id != delivery.disposition_case_id
        or prepared.disposition_campaign_id != delivery.disposition_campaign_id
    ):
        raise DeliveryPreflightError("The approved campaign source record is unavailable.")
    if case.status not in {"buyer_matching", "marketed", "offers_received"}:
        raise DeliveryPreflightError(
            "The disposition case is no longer in an outreach-eligible stage.",
            status="cancelled",
        )
    latest_package = db.scalar(
        select(DispositionPackageVersion)
        .where(
            DispositionPackageVersion.organization_id == delivery.organization_id,
            DispositionPackageVersion.disposition_case_id == case.id,
        )
        .order_by(DispositionPackageVersion.version_number.desc())
    )
    if (
        case.package_status != "approved"
        or package.status != "approved"
        or latest_package is None
        or latest_package.id != package.id
        or package.source_fingerprint != revision.package_source_fingerprint
        or package.pdf_sha256 != revision.artifact_sha256
        or package.pdf_data is None
    ):
        raise DeliveryPreflightError(
            "The disposition package changed after outreach approval. Build a new revision."
        )
    if (
        prepared.buyer_id != delivery.buyer_id
        or prepared.package_version_id != package.id
        or prepared.artifact_sha256 != revision.artifact_sha256
        or prepared.status != "prepared_not_sent"
    ):
        raise DeliveryPreflightError("The prepared buyer record changed after approval.")
    buyer = db.get(Buyer, delivery.buyer_id)
    if (
        buyer is None
        or buyer.organization_id != delivery.organization_id
        or buyer.status != "active"
        or buyer.relationship_status == "do_not_contact"
        or buyer.archived_at is not None
    ):
        raise DeliveryPreflightError("This buyer is no longer eligible for outreach.")
    conversation = ensure_buyer_conversation(
        db,
        buyer,
        actor_user_id=revision.approved_by_user_id,
    )
    contact = db.get(Contact, conversation.contact_id)
    if contact is None:
        raise DeliveryPreflightError("The buyer conversation is missing contact data.")
    delivery.conversation_id = conversation.id
    delivery.contact_id = contact.id

    if settings.communication_provider_mode == "disabled":
        raise DeliveryPreflightError(
            "External communications are disabled.", status="failed_retryable"
        )
    if delivery.channel == "email":
        current_email = (buyer.normalized_email or (buyer.email or "").strip().lower()).strip()
        if not current_email or current_email != delivery.normalized_destination:
            raise DeliveryPreflightError("The buyer email changed after outreach approval.")
        suppression = db.scalar(
            select(SuppressionRecord).where(
                SuppressionRecord.organization_id == delivery.organization_id,
                SuppressionRecord.channel.in_(("email", "all")),
                SuppressionRecord.normalized_address == current_email,
                SuppressionRecord.status == "active",
            )
        )
        if suppression is not None:
            raise DeliveryPreflightError(
                "This email address is currently suppressed.", status="suppressed"
            )
        alias = db.get(EmailSenderAlias, revision.email_sender_alias_id)
        snapshot = revision.sender_snapshot.get("email", {})
        if (
            alias is None
            or alias.organization_id != delivery.organization_id
            or alias.status != "active"
            or not alias.outbound_enabled
            or alias.provider != "resend"
            or alias.email_address.strip().lower() != str(snapshot.get("email_address", ""))
            or alias.display_name != str(snapshot.get("display_name", ""))
        ):
            raise DeliveryPreflightError(
                "The approved email sender changed or is unavailable.",
                status="failed_retryable",
            )
        if not settings.communication_simulation_enabled and settings.email_configuration_blockers:
            raise DeliveryPreflightError(
                "Resend email delivery is not configured.", status="failed_retryable"
            )
    else:
        sms = evaluate_sms_eligibility(db, contact, settings=settings)
        if sms.recipient != delivery.normalized_destination:
            raise DeliveryPreflightError("The buyer phone changed after outreach approval.")
        if not sms.can_send:
            status = (
                "suppressed"
                if sms.is_suppressed
                else "ineligible"
                if sms.recipient is None or sms.consent_status != "granted"
                else "failed_retryable"
            )
            raise DeliveryPreflightError(" ".join(sms.blockers), status=status)
        all_channel_suppression = db.scalar(
            select(SuppressionRecord.id).where(
                SuppressionRecord.organization_id == delivery.organization_id,
                SuppressionRecord.channel == "all",
                SuppressionRecord.normalized_address == delivery.normalized_destination,
                SuppressionRecord.status == "active",
            )
        )
        if all_channel_suppression is not None:
            raise DeliveryPreflightError(
                "This buyer is suppressed from all communication channels.",
                status="suppressed",
            )
        line = db.get(VoiceLine, revision.sms_voice_line_id)
        snapshot = revision.sender_snapshot.get("sms", {})
        if (
            line is None
            or line.organization_id != delivery.organization_id
            or line.status != "active"
            or line.provider != "twilio"
            or line.department_key != "dispositions"
            or line.purpose_key != "buyer_relations"
            or format_e164(line.phone_number) != format_e164(str(snapshot.get("phone_number", "")))
        ):
            raise DeliveryPreflightError(
                "The approved buyer-relations SMS line changed or is unavailable.",
                status="failed_retryable",
            )
    return conversation, contact


def _ensure_case_context(
    db: Session,
    conversation: Conversation,
    delivery: DispositionOutreachDelivery,
    actor_user_id: UUID,
) -> None:
    existing = db.scalar(
        select(ConversationContextLink).where(
            ConversationContextLink.organization_id == delivery.organization_id,
            ConversationContextLink.conversation_id == conversation.id,
            ConversationContextLink.context_type == "disposition",
            ConversationContextLink.disposition_case_id == delivery.disposition_case_id,
        )
    )
    if existing is None:
        db.add(
            ConversationContextLink(
                organization_id=delivery.organization_id,
                conversation_id=conversation.id,
                context_type="disposition",
                lead_id=None,
                transaction_id=None,
                buyer_id=None,
                disposition_case_id=delivery.disposition_case_id,
                created_by_user_id=actor_user_id,
                is_primary=False,
                link_metadata={
                    "source": "disposition_outreach",
                    "campaign_id": str(delivery.disposition_campaign_id),
                    "delivery_id": str(delivery.id),
                },
            )
        )


def _ensure_dispatch(
    db: Session,
    settings: Settings,
    delivery: DispositionOutreachDelivery,
    revision: DispositionOutreachRevision,
    conversation: Conversation,
    contact: Contact,
) -> CommunicationDispatch:
    request_hash = _provider_request_hash(db, delivery, revision)
    existing = db.scalar(
        select(CommunicationDispatch).where(
            CommunicationDispatch.organization_id == delivery.organization_id,
            CommunicationDispatch.idempotency_key == delivery.idempotency_key,
        )
    )
    if existing is not None:
        if existing.request_body_hash != request_hash:
            raise DeliveryPreflightError("The approved delivery idempotency key conflicts.")
        delivery.communication_dispatch_id = existing.id
        if existing.communication_record_id is not None:
            communication = db.get(CommunicationRecord, existing.communication_record_id)
            if communication is not None:
                delivery.communication_record_id = communication.id
                delivery.provider_message_id = communication.provider_message_id
                delivery.provider = communication.provider
                delivery.status = _mapped_delivery_status(communication.status)
                delivery.processing_started_at = None
                delivery.processing_token = None
                _sync_revision_status(db, delivery.outreach_revision_id)
                raise DeliveryAlreadyProcessed
        if existing.status not in {"pending", "failed"}:
            raise DeliveryPreflightError(
                "This approved message already has an active provider dispatch.",
                status="delivery_unknown",
            )
        existing.status = "pending"
        existing.error_code = None
        existing.error_message = None
        existing.completed_at = None
        dispatch = existing
    else:
        provider = (
            "simulated"
            if settings.communication_simulation_enabled
            else "resend"
            if delivery.channel == "email"
            else "twilio"
        )
        dispatch = CommunicationDispatch(
            organization_id=delivery.organization_id,
            conversation_id=conversation.id,
            lead_id=None,
            contact_id=contact.id,
            actor_user_id=revision.approved_by_user_id,
            communication_record_id=None,
            idempotency_key=delivery.idempotency_key,
            channel=delivery.channel,
            recipient=delivery.normalized_destination,
            request_body_hash=request_hash,
            status="pending",
            provider=provider,
            provider_message_id=None,
            error_code=None,
            error_message=None,
            completed_at=None,
            dispatch_metadata={
                "source": "disposition_outreach",
                "disposition_case_id": str(delivery.disposition_case_id),
                "disposition_campaign_id": str(delivery.disposition_campaign_id),
                "outreach_revision_id": str(delivery.outreach_revision_id),
                "outreach_delivery_id": str(delivery.id),
                "package_version_id": str(delivery.package_version_id),
                "approval_hash": revision.approval_hash,
                "provider_request_hash_version": 1,
            },
        )
        db.add(dispatch)
        db.flush()
    delivery.communication_dispatch_id = dispatch.id
    return dispatch


def _provider_request_hash(
    db: Session,
    delivery: DispositionOutreachDelivery,
    revision: DispositionOutreachRevision,
) -> str:
    common: dict[str, object] = {
        "version": 1,
        "organization_id": str(delivery.organization_id),
        "channel": delivery.channel,
        "recipient": delivery.normalized_destination,
        "body": delivery.body,
        "idempotency_key": delivery.idempotency_key,
    }
    if delivery.channel == "email":
        alias = db.get(EmailSenderAlias, revision.email_sender_alias_id)
        package = db.get(DispositionPackageVersion, delivery.package_version_id)
        if (
            alias is None
            or package is None
            or package.pdf_data is None
            or not package.pdf_file_name
        ):
            raise DeliveryPreflightError("The approved email artifact is unavailable.")
        attachment = bytes(package.pdf_data)
        attachment_sha256 = sha256(attachment).hexdigest()
        if not package.pdf_sha256 or attachment_sha256 != package.pdf_sha256:
            raise DeliveryPreflightError(
                "The approved package attachment changed before provider submission."
            )
        common.update(
            {
                "provider": "resend",
                "sender_name": alias.display_name,
                "sender_email": alias.email_address,
                "subject": delivery.subject or "Property opportunity",
                "attachment": {
                    "file_name": package.pdf_file_name,
                    "content_type": package.pdf_content_type or "application/pdf",
                    "byte_length": len(attachment),
                    "sha256": attachment_sha256,
                },
            }
        )
    elif delivery.channel == "sms":
        line = db.get(VoiceLine, revision.sms_voice_line_id)
        if line is None:
            raise DeliveryPreflightError(
                "The approved buyer-relations SMS line is unavailable."
            )
        common.update(
            {
                "provider": "twilio",
                "sender_number": format_e164(line.phone_number) or line.phone_number,
            }
        )
    else:
        raise DeliveryPreflightError("The approved outreach channel is unsupported.")
    serialized = json.dumps(
        common,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return sha256(serialized.encode("utf-8")).hexdigest()


def _send_email(
    db: Session,
    settings: Settings,
    delivery: DispositionOutreachDelivery,
    revision: DispositionOutreachRevision,
    conversation: Conversation,
    contact: Contact,
    dispatch: CommunicationDispatch,
) -> None:
    alias = db.get(EmailSenderAlias, revision.email_sender_alias_id)
    package = db.get(DispositionPackageVersion, delivery.package_version_id)
    if alias is None or package is None or package.pdf_data is None or not package.pdf_file_name:
        raise DeliveryPreflightError("The approved email artifact is unavailable.")
    provider = get_email_delivery_provider(
        db,
        None,
        alias,
        settings,
        conversation_id=conversation.id,
    )
    result = provider.send(
        EmailDeliveryRequest(
            lead_id=None,
            contact_id=str(contact.id),
            sender_name=alias.display_name,
            sender_email=alias.email_address,
            recipient=delivery.normalized_destination,
            to=[delivery.normalized_destination],
            subject=delivery.subject or "Property opportunity",
            body=delivery.body,
            idempotency_key=delivery.idempotency_key,
            attachments=[
                (
                    package.pdf_file_name,
                    package.pdf_content_type or "application/pdf",
                    bytes(package.pdf_data),
                )
            ],
            provider_thread_id=None,
            in_reply_to=None,
            references=None,
        )
    )
    _record_provider_acceptance(
        db,
        delivery,
        revision,
        conversation,
        contact,
        dispatch,
        provider=result.provider,
        provider_message_id=result.provider_message_id,
        status="sent",
        external_payload=result.raw_payload,
        metadata={
            "provider_thread_id": result.provider_thread_id,
            "rfc_message_id": result.rfc_message_id,
            "references": result.rfc_message_id,
            "from": alias.email_address,
            "to": [delivery.normalized_destination],
            "attachment_count": 1,
            "email_sender_alias_id": str(alias.id),
        },
    )
    communication = db.get(CommunicationRecord, delivery.communication_record_id)
    if communication is not None:
        record_email_participants(
            db,
            communication,
            from_values=f"{alias.display_name} <{alias.email_address}>",
            to_values=[delivery.normalized_destination],
            external_contact_id=contact.id,
            external_roles={"to"},
            external_contact_email=delivery.normalized_destination,
            sender_user_id=revision.approved_by_user_id,
            sender_alias_ids=[alias.id],
            source="disposition_outreach",
        )


def _send_sms(
    db: Session,
    settings: Settings,
    delivery: DispositionOutreachDelivery,
    revision: DispositionOutreachRevision,
    conversation: Conversation,
    contact: Contact,
    dispatch: CommunicationDispatch,
) -> None:
    line = db.get(VoiceLine, revision.sms_voice_line_id)
    if line is None:
        raise DeliveryPreflightError("The approved buyer-relations SMS line is unavailable.")
    provider = (
        SimulatedCommunicationProvider()
        if settings.communication_simulation_enabled
        else TwilioMessagingProvider(settings)
    )
    result = provider.send(
        OutboundMessageRequest(
            lead_id=None,
            contact_id=str(contact.id),
            channel="sms",
            recipient=delivery.normalized_destination,
            body=delivery.body,
            idempotency_key=delivery.idempotency_key,
            metadata={
                "conversation_id": str(conversation.id),
                "sender_number": line.phone_number,
                "voice_line_id": str(line.id),
                "outreach_delivery_id": str(delivery.id),
            },
        ),
        dry_run=settings.communication_simulation_enabled,
    )
    if not result.provider_message_id:
        raise TwilioMessagingError("Twilio did not return a message identifier.")
    provider_status = str(result.status or "queued").lower()
    _record_provider_acceptance(
        db,
        delivery,
        revision,
        conversation,
        contact,
        dispatch,
        provider=result.provider,
        provider_message_id=result.provider_message_id,
        status=provider_status,
        external_payload=result.raw_payload,
        metadata={
            "sender_number": line.phone_number,
            "voice_line_id": str(line.id),
        },
    )


def _record_provider_acceptance(
    db: Session,
    delivery: DispositionOutreachDelivery,
    revision: DispositionOutreachRevision,
    conversation: Conversation,
    contact: Contact,
    dispatch: CommunicationDispatch,
    *,
    provider: str,
    provider_message_id: str,
    status: str,
    external_payload: dict[str, object],
    metadata: dict[str, object],
) -> None:
    now = datetime.now(UTC)
    previous_status = delivery.status
    communication = CommunicationRecord(
        organization_id=delivery.organization_id,
        conversation_id=conversation.id,
        lead_id=None,
        contact_id=contact.id,
        actor_user_id=revision.approved_by_user_id,
        direction="outbound",
        channel=delivery.channel,
        status=status,
        provider=provider,
        provider_message_id=provider_message_id,
        subject=delivery.subject,
        body=delivery.body,
        occurred_at=now,
        external_payload=external_payload,
        communication_metadata={
            "source": "disposition_outreach",
            "idempotency_key": delivery.idempotency_key,
            "disposition_case_id": str(delivery.disposition_case_id),
            "disposition_campaign_id": str(delivery.disposition_campaign_id),
            "outreach_revision_id": str(delivery.outreach_revision_id),
            "outreach_delivery_id": str(delivery.id),
            "package_version_id": str(delivery.package_version_id),
            "approval_hash": revision.approval_hash,
            **metadata,
        },
    )
    db.add(communication)
    db.flush()
    dispatch.communication_record_id = communication.id
    dispatch.status = status
    dispatch.provider = provider
    dispatch.provider_message_id = provider_message_id
    dispatch.completed_at = now
    delivery.communication_record_id = communication.id
    delivery.provider = provider
    delivery.provider_message_id = provider_message_id
    delivery.provider_accepted_at = now
    delivery.status = _mapped_delivery_status(status)
    if delivery.status == "sent":
        delivery.sent_at = now
    delivery.processing_started_at = None
    delivery.processing_token = None
    update_conversation_activity(conversation, direction="outbound", occurred_at=now, db=db)
    db.add(
        ActivityEvent(
            organization_id=delivery.organization_id,
            actor_user_id=revision.approved_by_user_id,
            entity_type="buyer",
            entity_id=delivery.buyer_id,
            event_type="buyer.disposition_outreach_sent",
            summary=(
                f"Approved disposition {delivery.channel} was accepted by {provider}."
            ),
        )
    )
    db.add(
        AuditEvent(
            organization_id=delivery.organization_id,
            actor_user_id=revision.approved_by_user_id,
            actor_type="user",
            action="disposition.outreach_provider_accept",
            entity_type="disposition_outreach_delivery",
            entity_id=delivery.id,
            previous_value={"status": previous_status},
            new_value={
                "status": delivery.status,
                "provider": provider,
                "provider_message_id": provider_message_id,
                "approval_hash": revision.approval_hash,
            },
            reason="Exact approved buyer outreach submitted by the worker",
        )
    )


def _fail_delivery(
    db: Session,
    delivery: DispositionOutreachDelivery,
    error_code: str,
    error_message: str,
    *,
    status: str = "failed_retryable",
) -> None:
    now = datetime.now(UTC)
    previous_status = delivery.status
    delivery.status = status
    delivery.error_code = error_code[:120]
    delivery.error_message = error_message[:2000]
    delivery.failed_at = now
    delivery.processing_started_at = None
    delivery.processing_token = None
    if status == "failed_retryable":
        delivery.next_attempt_at = None
    dispatch = (
        db.get(CommunicationDispatch, delivery.communication_dispatch_id)
        if delivery.communication_dispatch_id
        else None
    )
    if dispatch is not None and dispatch.communication_record_id is None:
        dispatch.status = status
        dispatch.error_code = error_code[:120]
        dispatch.error_message = error_message[:2000]
        dispatch.completed_at = now
    db.add(
        AuditEvent(
            organization_id=delivery.organization_id,
            actor_user_id=None,
            actor_type="system",
            action="disposition.outreach_delivery_blocked",
            entity_type="disposition_outreach_delivery",
            entity_id=delivery.id,
            previous_value={"status": previous_status},
            new_value={"status": status, "error_code": error_code},
            reason=error_message[:2000],
        )
    )
    _sync_revision_status(db, delivery.outreach_revision_id)
    db.commit()


def _sync_revision_status(db: Session, revision_id: UUID) -> None:
    # Worker sessions intentionally disable autoflush. Persist any delivery state
    # transition before deriving the revision summary from a database query.
    db.flush()
    revision = db.get(DispositionOutreachRevision, revision_id)
    if revision is None or revision.status in {"paused", "cancelled", "invalidated"}:
        return
    statuses = list(
        db.scalars(
            select(DispositionOutreachDelivery.status).where(
                DispositionOutreachDelivery.outreach_revision_id == revision_id
            )
        ).all()
    )
    if not statuses:
        return
    if any(status in {"queued", "claimed"} for status in statuses):
        revision.status = "sending"
        return
    if any(status in {"provider_accepted", "sent"} for status in statuses):
        revision.status = "sending"
        return
    if all(status in DELIVERY_TERMINAL_STATUSES for status in statuses):
        revision.status = (
            "completed_with_failures"
            if any(status in DELIVERY_FAILURE_STATUSES for status in statuses)
            else "completed"
        )
        revision.completed_at = datetime.now(UTC)


def _next_delivery_id_needing_reconciliation(
    db: Session,
) -> UUID | None:
    now = datetime.now(UTC)
    delivery_id = db.scalar(
        select(DispositionOutreachDelivery.id)
        .join(
            CommunicationRecord,
            CommunicationRecord.id == DispositionOutreachDelivery.communication_record_id,
        )
        .where(
            DispositionOutreachDelivery.status.in_(
                ("provider_accepted", "sent")
            ),
            (
                DispositionOutreachDelivery.next_attempt_at.is_(None)
                | (DispositionOutreachDelivery.next_attempt_at <= now)
            ),
        )
        .order_by(DispositionOutreachDelivery.updated_at.asc())
        .limit(1)
    )
    return UUID(str(delivery_id)) if delivery_id is not None else None


def _delivery_needs_reconciliation(delivery: DispositionOutreachDelivery) -> bool:
    if delivery.status not in {"provider_accepted", "sent"}:
        return False
    return (
        delivery.next_attempt_at is None
        or _as_utc(delivery.next_attempt_at) <= datetime.now(UTC)
    )


def _reconcile_delivery_status(
    db: Session,
    delivery: DispositionOutreachDelivery,
) -> None:
    communication = (
        db.get(CommunicationRecord, delivery.communication_record_id)
        if delivery.communication_record_id
        else None
    )
    dispatch = (
        db.get(CommunicationDispatch, delivery.communication_dispatch_id)
        if delivery.communication_dispatch_id
        else None
    )
    provider_status = communication.status if communication is not None else None
    if dispatch is not None and dispatch.status:
        dispatch_candidate = _mapped_delivery_status(dispatch.status)
        if _can_advance_delivery(delivery.status, dispatch_candidate):
            provider_status = dispatch.status
    if provider_status is None:
        return
    candidate = _mapped_delivery_status(provider_status)
    if not _can_advance_delivery(delivery.status, candidate):
        delivery.next_attempt_at = datetime.now(UTC) + timedelta(minutes=1)
        return
    now = datetime.now(UTC)
    delivery.status = candidate
    if candidate == "sent":
        delivery.sent_at = delivery.sent_at or now
    elif candidate == "delivered":
        delivery.delivered_at = delivery.delivered_at or now
    elif candidate in {"failed_terminal", "suppressed"}:
        delivery.failed_at = delivery.failed_at or now
        delivery.error_code = provider_status
        delivery.error_message = (
            (dispatch.error_message if dispatch is not None else None)
            or f"Provider reported {provider_status}."
        )[:2000]
    delivery.next_attempt_at = (
        now + timedelta(minutes=1)
        if candidate in {"provider_accepted", "sent"}
        else None
    )
    _sync_revision_status(db, delivery.outreach_revision_id)


def _mapped_delivery_status(provider_status: str) -> str:
    return COMMUNICATION_TO_DELIVERY_STATUS.get(provider_status.lower(), "provider_accepted")


def _can_advance_delivery(current: str, candidate: str) -> bool:
    if current in {"replied", "cancelled", "delivery_unknown", "opted_out"}:
        return False
    if candidate in {"failed_terminal", "suppressed"}:
        return current not in {"replied", "cancelled", "opted_out"}
    if current in {"failed_terminal", "suppressed", "ineligible"}:
        return False
    return DELIVERY_STATUS_RANK.get(candidate, 0) >= DELIVERY_STATUS_RANK.get(current, 0)


def _next_unlinked_buyer_reply(db: Session) -> CommunicationRecord | None:
    return db.scalar(
        select(CommunicationRecord)
        .join(Conversation, Conversation.id == CommunicationRecord.conversation_id)
        .outerjoin(
            DispositionReplyLink,
            DispositionReplyLink.communication_record_id == CommunicationRecord.id,
        )
        .where(
            CommunicationRecord.direction == "inbound",
            CommunicationRecord.channel.in_(("email", "sms")),
            Conversation.conversation_type == "buyer",
            DispositionReplyLink.id.is_(None),
            exists(
                select(1).where(
                    DispositionOutreachDelivery.organization_id
                    == CommunicationRecord.organization_id,
                    DispositionOutreachDelivery.conversation_id
                    == CommunicationRecord.conversation_id,
                    DispositionOutreachDelivery.channel == CommunicationRecord.channel,
                    DispositionOutreachDelivery.provider_accepted_at.is_not(None),
                    DispositionOutreachDelivery.provider_accepted_at
                    <= CommunicationRecord.occurred_at,
                )
            ),
        )
        .order_by(CommunicationRecord.occurred_at.asc())
        .with_for_update(skip_locked=True)
    )


def _reconcile_reply(db: Session, communication: CommunicationRecord) -> None:
    if communication.conversation_id is None:
        return
    buyer_link = db.scalar(
        select(ConversationContextLink).where(
            ConversationContextLink.organization_id == communication.organization_id,
            ConversationContextLink.conversation_id == communication.conversation_id,
            ConversationContextLink.context_type == "buyer",
        )
    )
    if buyer_link is None or buyer_link.buyer_id is None:
        return
    candidates = list(
        db.scalars(
            select(DispositionOutreachDelivery)
            .where(
                DispositionOutreachDelivery.organization_id == communication.organization_id,
                DispositionOutreachDelivery.conversation_id == communication.conversation_id,
                DispositionOutreachDelivery.buyer_id == buyer_link.buyer_id,
                DispositionOutreachDelivery.channel == communication.channel,
                DispositionOutreachDelivery.status.in_(
                    ("provider_accepted", "sent", "delivered")
                ),
                DispositionOutreachDelivery.replied_at.is_(None),
            )
            .order_by(DispositionOutreachDelivery.provider_accepted_at.desc())
        ).all()
    )
    matched: DispositionOutreachDelivery | None = None
    confidence = 0
    if communication.channel == "email":
        matched = _match_email_reply(db, communication, candidates)
        confidence = 100 if matched is not None else 0
    elif len(candidates) == 1:
        matched = candidates[0]
        confidence = 90
    if matched is not None:
        _revision, locked_match = _locked_revision_delivery(db, UUID(str(matched.id)))
        if (
            locked_match is None
            or locked_match.status not in {"provider_accepted", "sent", "delivered"}
            or locked_match.replied_at is not None
        ):
            matched = None
            confidence = 0
        else:
            matched = locked_match

    classification = _classify_reply(communication.body)
    now = datetime.now(UTC)
    reply_sender = (
        _unambiguous_email_reply_sender(db, communication)
        if communication.channel == "email"
        else None
    )
    if classification == "opt_out" and reply_sender is not None:
        _upsert_email_suppression(
            db,
            communication=communication,
            normalized_address=reply_sender,
            buyer_id=buyer_link.buyer_id,
            delivery=matched,
            suppressed_at=now,
        )
    if matched is None:
        task = _create_ambiguous_reply_task(db, communication)
        db.add(
            DispositionReplyLink(
                organization_id=communication.organization_id,
                communication_record_id=communication.id,
                outreach_delivery_id=None,
                outreach_revision_id=None,
                disposition_campaign_id=None,
                disposition_case_id=None,
                buyer_id=buyer_link.buyer_id,
                task_id=task.id if task is not None else None,
                routing_status="ambiguous" if candidates else "needs_review",
                routing_confidence=confidence,
                reply_classification=classification,
                linked_at=now,
            )
        )
        return

    revision = db.get(DispositionOutreachRevision, matched.outreach_revision_id)
    case = db.get(DispositionCase, matched.disposition_case_id)
    conversation = db.get(Conversation, communication.conversation_id)
    matched.status = "opted_out" if classification == "opt_out" else "replied"
    matched.replied_at = now
    if (
        classification == "opt_out"
        and communication.channel == "email"
        and reply_sender is None
    ):
        # Older imported email records may predate structured participant capture.
        # An exact delivery match still gives us one safe address to suppress.
        _upsert_email_suppression(
            db,
            communication=communication,
            normalized_address=matched.normalized_destination,
            buyer_id=matched.buyer_id,
            delivery=matched,
            suppressed_at=now,
        )
    if conversation is not None and revision is not None:
        _ensure_case_context(db, conversation, matched, revision.created_by_user_id)
    task = Task(
        organization_id=communication.organization_id,
        lead_id=None,
        deal_id=case.deal_id if case is not None else None,
        prospecting_inbound_callback_id=None,
        prospect_id=None,
        call_record_id=None,
        responsible_user_id=(
            conversation.assigned_user_id
            if conversation is not None and conversation.assigned_user_id is not None
            else case.owner_user_id
            if case is not None
            else None
        ),
        task_type="buyer_reply_review",
        work_kind="supporting",
        title="Review buyer reply to disposition outreach",
        status="open",
        priority="high",
        due_at=now,
        completed_at=None,
        completed_by_user_id=None,
        outcome=None,
        completion_notes=None,
        successor_task_id=None,
    )
    db.add(task)
    db.flush()
    db.add(
        DispositionReplyLink(
            organization_id=communication.organization_id,
            communication_record_id=communication.id,
            outreach_delivery_id=matched.id,
            outreach_revision_id=matched.outreach_revision_id,
            disposition_campaign_id=matched.disposition_campaign_id,
            disposition_case_id=matched.disposition_case_id,
            buyer_id=matched.buyer_id,
            task_id=task.id,
            routing_status="matched",
            routing_confidence=confidence,
            reply_classification=classification,
            linked_at=now,
        )
    )
    actor_user_id: UUID | None = None
    if revision is not None:
        actor_user_id = revision.approved_by_user_id or revision.created_by_user_id
    elif case is not None:
        actor_user_id = case.owner_user_id
    if actor_user_id is not None:
        db.add(
            BuyerEngagement(
                organization_id=communication.organization_id,
                disposition_case_id=matched.disposition_case_id,
                buyer_id=matched.buyer_id,
                actor_user_id=actor_user_id,
                engagement_type="reply",
                status="needs_review",
                scheduled_at=None,
                occurred_at=communication.occurred_at,
                completed_at=None,
                notes=f"Buyer reply classified as {classification}; human review required.",
            )
        )
    db.add(
        ActivityEvent(
            organization_id=communication.organization_id,
            actor_user_id=None,
            entity_type="buyer",
            entity_id=matched.buyer_id,
            event_type="buyer.disposition_reply_received",
            summary="Buyer replied to an approved disposition outreach message.",
        )
    )
    db.add(
        AuditEvent(
            organization_id=communication.organization_id,
            actor_user_id=None,
            actor_type="system",
            action="disposition.outreach_reply_reconcile",
            entity_type="communication_record",
            entity_id=communication.id,
            previous_value=None,
            new_value={
                "delivery_id": str(matched.id),
                "case_id": str(matched.disposition_case_id),
                "classification": classification,
                "routing_confidence": confidence,
                "task_id": str(task.id),
            },
            reason="Buyer reply linked to its exact outbound campaign context",
        )
    )
    _sync_revision_status(db, matched.outreach_revision_id)


def _unambiguous_email_reply_sender(
    db: Session,
    communication: CommunicationRecord,
) -> str | None:
    senders = set(
        db.scalars(
            select(CommunicationParticipant.normalized_email).where(
                CommunicationParticipant.organization_id == communication.organization_id,
                CommunicationParticipant.communication_record_id == communication.id,
                CommunicationParticipant.participant_role == "from",
            )
        ).all()
    )
    return next(iter(senders)) if len(senders) == 1 else None


def _upsert_email_suppression(
    db: Session,
    *,
    communication: CommunicationRecord,
    normalized_address: str,
    buyer_id: UUID,
    delivery: DispositionOutreachDelivery | None,
    suppressed_at: datetime,
) -> SuppressionRecord:
    normalized_address = normalized_address.strip().lower()
    suppression = db.scalar(
        select(SuppressionRecord)
        .where(
            SuppressionRecord.organization_id == communication.organization_id,
            SuppressionRecord.channel == "email",
            SuppressionRecord.normalized_address == normalized_address,
        )
        .with_for_update()
    )
    previous_value = None
    if suppression is None:
        suppression = SuppressionRecord(
            organization_id=communication.organization_id,
            contact_id=communication.contact_id,
            channel="email",
            normalized_address=normalized_address,
            status="active",
            reason="Buyer requested to unsubscribe from disposition outreach.",
            source="disposition_outreach_reply",
            provider=communication.provider,
            external_event_id=communication.provider_message_id,
            suppressed_at=suppressed_at,
            lifted_at=None,
            suppression_metadata={},
        )
        db.add(suppression)
    else:
        previous_value = {
            "status": suppression.status,
            "source": suppression.source,
            "external_event_id": suppression.external_event_id,
            "lifted_at": (
                suppression.lifted_at.isoformat() if suppression.lifted_at else None
            ),
        }
        suppression.contact_id = communication.contact_id
        suppression.status = "active"
        suppression.reason = "Buyer requested to unsubscribe from disposition outreach."
        suppression.source = "disposition_outreach_reply"
        suppression.provider = communication.provider
        suppression.external_event_id = communication.provider_message_id
        suppression.suppressed_at = suppressed_at
        suppression.lifted_at = None

    source_metadata: dict[str, object] = {
        "source": (
            "matched_disposition_outreach_reply"
            if delivery is not None
            else "unmatched_disposition_outreach_reply"
        ),
        "communication_record_id": str(communication.id),
        "buyer_id": str(buyer_id),
        "reply_classification": "opt_out",
    }
    if delivery is not None:
        source_metadata.update(
            {
                "outreach_delivery_id": str(delivery.id),
                "outreach_revision_id": str(delivery.outreach_revision_id),
                "disposition_campaign_id": str(delivery.disposition_campaign_id),
                "disposition_case_id": str(delivery.disposition_case_id),
            }
        )
    suppression.suppression_metadata = {
        **(suppression.suppression_metadata or {}),
        **source_metadata,
    }
    db.flush()
    db.add(
        AuditEvent(
            organization_id=communication.organization_id,
            actor_user_id=None,
            actor_type="system",
            action="disposition.outreach_reply_suppressed",
            entity_type="suppression_record",
            entity_id=suppression.id,
            previous_value=previous_value,
            new_value={
                "channel": suppression.channel,
                "normalized_address": suppression.normalized_address,
                "status": suppression.status,
                "source": suppression.source,
                **source_metadata,
            },
            reason="Buyer email reply clearly requested unsubscribe.",
        )
    )
    return suppression


def _match_email_reply(
    db: Session,
    communication: CommunicationRecord,
    candidates: list[DispositionOutreachDelivery],
) -> DispositionOutreachDelivery | None:
    inbound = communication.communication_metadata or {}
    inbound_thread = str(inbound.get("provider_thread_id", "")).strip()
    references = " ".join(
        str(inbound.get(key, "")) for key in ("in_reply_to", "references")
    )
    exact: list[DispositionOutreachDelivery] = []
    for delivery in candidates:
        outbound = (
            db.get(CommunicationRecord, delivery.communication_record_id)
            if delivery.communication_record_id
            else None
        )
        metadata = outbound.communication_metadata if outbound is not None else None
        metadata = metadata or {}
        thread = str(metadata.get("provider_thread_id", "")).strip()
        rfc_message_id = str(metadata.get("rfc_message_id", "")).strip()
        if (thread and inbound_thread and thread == inbound_thread) or (
            rfc_message_id and rfc_message_id in references
        ):
            exact.append(delivery)
    return exact[0] if len(exact) == 1 else None


def _create_ambiguous_reply_task(
    db: Session,
    communication: CommunicationRecord,
) -> Task | None:
    conversation = (
        db.get(Conversation, communication.conversation_id)
        if communication.conversation_id
        else None
    )
    if conversation is None:
        return None
    task = Task(
        organization_id=communication.organization_id,
        lead_id=None,
        deal_id=None,
        prospecting_inbound_callback_id=None,
        prospect_id=None,
        call_record_id=None,
        responsible_user_id=conversation.assigned_user_id,
        task_type="buyer_reply_reconciliation",
        work_kind="supporting",
        title="Reconcile buyer reply to a disposition campaign",
        status="open",
        priority="high",
        due_at=datetime.now(UTC),
        completed_at=None,
        completed_by_user_id=None,
        outcome=None,
        completion_notes=None,
        successor_task_id=None,
    )
    db.add(task)
    db.flush()
    return task


def _classify_reply(body: str) -> str:
    normalized = " ".join(body.lower().split()).strip(" .,!?:;")
    if normalized in {"stop", "unsubscribe", "cancel", "end", "quit"}:
        return "opt_out"
    clear_opt_out_phrases = (
        "please unsubscribe",
        "unsubscribe me",
        "remove me",
        "take me off your list",
        "do not email me",
        "don't email me",
        "stop emailing me",
        "no more emails",
        "do not text me",
        "don't text me",
        "stop texting me",
        "no more texts",
        "stop contacting me",
    )
    if any(value in normalized for value in clear_opt_out_phrases):
        return "opt_out"
    if any(value in normalized for value in ("not interested", "pass")):
        return "pass"
    if any(value in normalized for value in ("offer", "$", "price")):
        return "offer"
    if any(value in normalized for value in ("showing", "see the property", "walk through")):
        return "showing"
    if any(value in normalized for value in ("interested", "send the address", "more info")):
        return "interested"
    return "needs_review"
