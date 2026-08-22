from __future__ import annotations

import hashlib
import html
import json
import re
import socket
import unicodedata
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import structlog
from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.integrations.batchdialer_client import (
    BatchDialerAPIError,
    BatchDialerClient,
    BatchDialerContractError,
)
from app.models.foundation import (
    ActivityEvent,
    AttributionTouch,
    BatchDialerCampaign,
    BatchDialerSyncCheckpoint,
    CallRecord,
    CallRecording,
    CallTranscript,
    CommunicationRecord,
    Lead,
    ProspectingProviderEvent,
    Task,
)
from app.schemas.public_intake import SellerIntakeAttribution, SellerIntakeCreate
from app.services.ai_operations import enqueue_lead_created_ai_work
from app.services.communication_compliance import format_e164
from app.services.inbox import ensure_primary_conversation, update_conversation_activity
from app.services.lead_manager import ensure_inbound_case
from app.services.property_intelligence import enqueue_property_research
from app.services.public_intake import (
    apply_public_intake_context,
    create_contact,
    create_lead,
    create_property,
    ensure_contact_methods,
    find_duplicate_match,
    get_default_organization,
)
from app.services.staff_lead_alerts import queue_staff_lead_alerts_for_lead
from app.services.tasks import ensure_speed_to_lead_task

PROVIDER = "batchdialer"
CHECKPOINT_STREAM = "cdrs"
CONTRACT_VERSION = "batchdialer_direct_v1"
QUALIFIED_DISPOSITIONS = {
    "qualified seller - follow up": "interested",
    "appointment set": "appointment_set",
}
KNOWN_NON_LEAD_DISPOSITIONS = frozenset(
    {
        "answering machine",
        "call back",
        "callback",
        "do not call",
        "no answer",
        "not interested",
        "successful sale",
        "voicemail",
        "wrong number",
    }
)
OPEN_EVENT_STATUSES = frozenset({"pending", "retry", "processing"})
MAX_TRANSCRIPT_ATTEMPTS = 12
TRANSCRIPT_RECHECK_SECONDS = 600
MAX_STORED_COMMENT_LENGTH = 2_000
MAX_TRANSCRIPT_LENGTH = 100_000

logger = structlog.get_logger()


class BatchDialerNeedsReview(ValueError):
    """The provider observation is durable but not safe to mutate into CRM data."""


def poll_batchdialer_direct(db: Session, settings: Settings) -> UUID | None:
    """Scan bounded rolling date partitions and durably archive each CDR."""
    if not settings.batchdialer_configured:
        return None
    organization = get_default_organization(db)
    now = datetime.now(UTC)
    checkpoint = _acquire_checkpoint(db, organization.id, settings, now=now)
    if checkpoint is None:
        return None
    checkpoint_id = checkpoint.id
    lease_token = checkpoint.lease_token
    assert lease_token is not None

    fetched = archived = updated = qualified = quarantined = 0
    anomalies: list[str] = []
    try:
        client = BatchDialerClient(settings)
        if _campaign_refresh_due(checkpoint, settings, now=now):
            _refresh_campaigns(db, organization.id, client, now=now)
            checkpoint = _locked_checkpoint(db, checkpoint_id, lease_token)
            checkpoint.last_campaign_refresh_at = now
            db.commit()

        account_today = now.astimezone(ZoneInfo(settings.batchdialer_account_timezone)).date()
        for days_ago in range(settings.batchdialer_scan_days):
            scan_date = account_today - timedelta(days=days_ago)
            cursor: str | None = None
            seen_cursors: set[str] = set()
            for _page_number in range(1, settings.batchdialer_max_pages_per_day + 1):
                page = client.get_cdr_page(
                    call_date=scan_date,
                    page_length=settings.batchdialer_page_length,
                    next_page=cursor,
                )
                fetched += len(page.items)
                if not page.items:
                    if page.next_page:
                        anomalies.append(f"empty_page_cursor:{scan_date.isoformat()}")
                    break
                for raw_cdr in page.items:
                    result = archive_batchdialer_cdr(
                        db,
                        organization_id=organization.id,
                        cdr=raw_cdr,
                        now=now,
                    )
                    archived += result == "archived"
                    updated += result == "updated"
                    disposition_kind = classify_disposition(raw_cdr.get("disposition"))
                    qualified += result == "archived" and disposition_kind in {
                        "interested",
                        "appointment_set",
                    }
                    quarantined += result == "archived" and disposition_kind == "unknown"
                    _record_campaign_cdr(
                        db,
                        organization.id,
                        raw_cdr,
                        archive_result=result,
                        disposition_kind=disposition_kind,
                        now=now,
                    )
                db.commit()
                checkpoint = _locked_checkpoint(db, checkpoint_id, lease_token)
                checkpoint.scan_date = scan_date
                checkpoint.next_page_cursor = page.next_page
                checkpoint.lease_expires_at = datetime.now(UTC) + timedelta(
                    seconds=settings.batchdialer_checkpoint_lease_seconds
                )
                db.commit()
                if not page.next_page:
                    break
                if page.next_page == cursor or page.next_page in seen_cursors:
                    raise BatchDialerContractError(
                        "BatchDialer repeated a CDR cursor before the scan completed."
                    )
                seen_cursors.add(page.next_page)
                cursor = page.next_page
            else:
                raise BatchDialerContractError(
                    "BatchDialer CDR scan reached the configured page safety limit."
                )

        checkpoint = _locked_checkpoint(db, checkpoint_id, lease_token)
        checkpoint.status = "healthy"
        checkpoint.lease_token = None
        checkpoint.lease_owner = None
        checkpoint.lease_expires_at = None
        checkpoint.next_poll_at = now + timedelta(seconds=settings.batchdialer_poll_seconds)
        checkpoint.scan_date = None
        checkpoint.next_page_cursor = None
        checkpoint.last_success_at = now
        checkpoint.last_error = None
        checkpoint.consecutive_failure_count = 0
        checkpoint.success_count += 1
        checkpoint.fetched_cdr_count += fetched
        checkpoint.archived_event_count += archived
        checkpoint.updated_event_count += updated
        checkpoint.qualified_event_count += qualified
        checkpoint.quarantined_event_count += quarantined
        checkpoint.sync_metadata = {
            **(checkpoint.sync_metadata or {}),
            "last_run": {
                "fetched": fetched,
                "archived": archived,
                "updated": updated,
                "qualified": qualified,
                "quarantined": quarantined,
                "anomalies": anomalies,
                "completed_at": now.isoformat(),
            },
        }
        db.commit()
        logger.info(
            "batchdialer_direct_poll_completed",
            fetched=fetched,
            archived=archived,
            updated=updated,
            qualified=qualified,
            quarantined=quarantined,
            anomalies=anomalies,
        )
        return checkpoint_id
    except Exception as exc:
        db.rollback()
        checkpoint = db.get(BatchDialerSyncCheckpoint, checkpoint_id)
        if checkpoint is not None and checkpoint.lease_token == lease_token:
            checkpoint.status = "failed"
            checkpoint.lease_token = None
            checkpoint.lease_owner = None
            checkpoint.lease_expires_at = None
            checkpoint.next_poll_at = now + timedelta(seconds=settings.batchdialer_poll_seconds)
            checkpoint.last_error = _safe_error(exc)
            checkpoint.consecutive_failure_count += 1
            checkpoint.failure_count += 1
            checkpoint.sync_metadata = {
                **(checkpoint.sync_metadata or {}),
                "last_failure_at": now.isoformat(),
            }
            db.commit()
        raise


def archive_batchdialer_cdr(
    db: Session,
    *,
    organization_id: UUID,
    cdr: dict[str, Any],
    now: datetime,
) -> str:
    cdr_id = _required_numeric_id(cdr.get("id"), "CDR")
    sanitized = sanitize_cdr(cdr)
    digest = _payload_hash(sanitized)
    external_event_id = f"cdr:{cdr_id}"
    existing = db.scalar(
        select(ProspectingProviderEvent).where(
            ProspectingProviderEvent.organization_id == organization_id,
            ProspectingProviderEvent.provider == PROVIDER,
            ProspectingProviderEvent.external_event_id == external_event_id,
        )
    )
    if existing is None:
        event = ProspectingProviderEvent(
            organization_id=organization_id,
            provider_campaign_sync_id=None,
            provider_contact_sync_id=None,
            batch_entry_id=None,
            attempt_id=None,
            dial_session_id=None,
            dial_leg_id=None,
            provider=PROVIDER,
            external_event_id=external_event_id,
            event_type="cdr.observed",
            processing_status="pending",
            provider_call_id=_string(cdr.get("callid")) or cdr_id,
            provider_recording_id=None,
            provider_sequence_number=int(cdr_id),
            occurred_at=_cdr_occurred_at(cdr),
            signature_verified=False,
            signature_fingerprint=None,
            payload_sha256=digest,
            payload={
                "_stonegate_contract": CONTRACT_VERSION,
                "cdr": sanitized,
            },
            retry_count=0,
            error_message=None,
            received_at=now,
            processed_at=None,
        )
        db.add(event)
        try:
            with db.begin_nested():
                db.flush()
        except IntegrityError:
            return "unchanged"
        return "archived"
    if existing.payload_sha256 == digest:
        if _transcript_recheck_due(existing, now=now):
            existing.processing_status = "pending"
            existing.error_message = None
            existing.processed_at = None
            return "updated"
        return "unchanged"
    prior_result = dict(existing.payload or {}).get("_stonegate")
    existing.payload_sha256 = digest
    existing.payload = {
        "_stonegate_contract": CONTRACT_VERSION,
        "cdr": sanitized,
        **({"_stonegate": prior_result} if isinstance(prior_result, dict) else {}),
    }
    existing.provider_call_id = _string(cdr.get("callid")) or cdr_id
    existing.provider_sequence_number = int(cdr_id)
    existing.occurred_at = _cdr_occurred_at(cdr)
    existing.processing_status = "pending"
    existing.error_message = None
    existing.processed_at = None
    return "updated"


def process_next_batchdialer_direct_event(
    db: Session,
    settings: Settings,
) -> UUID | None:
    now = datetime.now(UTC)
    retry_cutoff = now - timedelta(seconds=settings.batchdialer_event_retry_base_seconds)
    stale_cutoff = now - timedelta(minutes=10)
    event = db.scalar(
        select(ProspectingProviderEvent)
        .where(
            ProspectingProviderEvent.provider == PROVIDER,
            ProspectingProviderEvent.event_type == "cdr.observed",
            ProspectingProviderEvent.payload["_stonegate_contract"].as_string()
            == CONTRACT_VERSION,
            or_(
                ProspectingProviderEvent.processing_status == "pending",
                (
                    (ProspectingProviderEvent.processing_status == "retry")
                    & (ProspectingProviderEvent.updated_at <= retry_cutoff)
                ),
                (
                    (ProspectingProviderEvent.processing_status == "processing")
                    & (ProspectingProviderEvent.updated_at <= stale_cutoff)
                ),
            ),
        )
        .order_by(ProspectingProviderEvent.occurred_at, ProspectingProviderEvent.received_at)
        .with_for_update(skip_locked=True)
    )
    if event is None:
        return None
    event.processing_status = "processing"
    event.retry_count += 1
    event.error_message = None
    event_id = event.id
    db.commit()

    try:
        result = _process_batchdialer_event(db, event_id, settings)
    except BatchDialerNeedsReview as exc:
        db.rollback()
        _mark_event(db, event_id, "quarantined", str(exc), processed=True)
        logger.warning(
            "batchdialer_direct_event_quarantined",
            event_id=str(event_id),
            reason=str(exc),
        )
        return event_id
    except (BatchDialerAPIError, ValidationError, ValueError) as exc:
        db.rollback()
        _mark_event_failure(db, event_id, settings, _safe_error(exc))
        return event_id
    except Exception as exc:
        db.rollback()
        logger.exception("batchdialer_direct_event_failed", event_id=str(event_id))
        _mark_event_failure(db, event_id, settings, _safe_error(exc))
        return event_id

    event = db.get(ProspectingProviderEvent, event_id)
    if event is None:
        raise RuntimeError("BatchDialer event disappeared during processing.")
    event.processing_status = "processed"
    event.processed_at = datetime.now(UTC)
    event.error_message = None
    event.payload = {**dict(event.payload or {}), "_stonegate": result}
    db.commit()
    return event_id


def _process_batchdialer_event(
    db: Session,
    event_id: UUID,
    settings: Settings,
) -> dict[str, Any]:
    event = db.get(ProspectingProviderEvent, event_id)
    if event is None:
        raise RuntimeError("BatchDialer event is unavailable.")
    raw_cdr = (event.payload or {}).get("cdr")
    if not isinstance(raw_cdr, dict):
        raise BatchDialerNeedsReview("BatchDialer CDR evidence is missing.")
    outcome = classify_disposition(raw_cdr.get("disposition"))
    if outcome == "unknown":
        raise BatchDialerNeedsReview(
            "BatchDialer disposition is not mapped for automatic lead creation."
        )
    if outcome == "non_lead":
        return {
            "outcome": "ignored",
            "raw_disposition": _string(raw_cdr.get("disposition")),
        }

    prior_result = (event.payload or {}).get("_stonegate")
    prior_result = prior_result if isinstance(prior_result, dict) else {}
    client = BatchDialerClient(settings)
    provider_contact_id = _contact_id(raw_cdr)
    contact_payload: dict[str, Any] = {}
    if provider_contact_id:
        contact_payload = sanitize_contact(client.get_contact(provider_contact_id))
    normalized = normalize_qualified_handoff(raw_cdr, contact_payload, outcome=outcome)

    lead, created = _ensure_batchdialer_lead(
        db,
        event=event,
        normalized=normalized,
        prior_result=prior_result,
    )
    call = _ensure_call_evidence(
        db,
        event=event,
        lead=lead,
        normalized=normalized,
    )
    transcript_result = (
        _sync_transcript(
            db,
            client=client,
            event=event,
            call=call,
            prior_result=prior_result,
        )
        if settings.batchdialer_transcript_sync_enabled
        else {"status": "disabled", "attempts": 0}
    )
    if outcome == "appointment_set":
        _ensure_manual_appointment_task(db, lead=lead, call=call, event=event)
    if created:
        _record_campaign_import(db, lead.organization_id, normalized["campaign_id"])
    db.flush()
    return {
        "outcome": outcome,
        "lead_id": str(lead.id),
        "contact_id": str(lead.contact_id),
        "property_id": str(lead.property_id),
        "call_record_id": str(call.id),
        "created_lead": created,
        "transcript_status": transcript_result["status"],
        "transcript_attempts": transcript_result["attempts"],
        "transcript_checked_at": datetime.now(UTC).isoformat(),
    }


def normalize_qualified_handoff(
    cdr: dict[str, Any],
    contact: dict[str, Any],
    *,
    outcome: str,
) -> dict[str, Any]:
    provider_contact_id = _string(contact.get("id")) or _contact_id(cdr)
    first_name = _string(contact.get("firstname")) or _nested_string(
        cdr, "contact", "firstname"
    )
    last_name = _string(contact.get("lastname")) or _nested_string(
        cdr, "contact", "lastname"
    )
    full_name = " ".join(part for part in (first_name, last_name) if part).strip()
    if not full_name:
        full_name = f"BatchDialer seller {provider_contact_id or 'unknown'}"
    phone = _contact_phone(contact) or format_e164(_string(cdr.get("customerNumber")))
    if phone is None:
        raise BatchDialerNeedsReview("Qualified BatchDialer contact has no valid phone number.")
    email_value: str | None = _string(contact.get("email")) or _nested_string(
        cdr, "contact", "email"
    )
    email_value = email_value if _looks_like_email(email_value) else None

    address = _string(contact.get("address")) or _nested_string(cdr, "contact", "address")
    city = _string(contact.get("city")) or _nested_string(cdr, "contact", "city")
    state = _string(contact.get("state")) or _nested_string(cdr, "contact", "state")
    postal_code = _string(contact.get("postalcode")) or _nested_string(
        cdr, "contact", "zip"
    )
    has_complete_address = bool(address and city and len(state) == 2 and postal_code)
    if not has_complete_address:
        suffix = provider_contact_id or _required_numeric_id(cdr.get("id"), "CDR")
        address = f"Address pending (BatchDialer {suffix})"
        city = "Unknown"
        state = "GA"
        postal_code = "Unknown"
    notes = _collect_provider_notes(cdr, contact)
    raw_agent = cdr.get("agent")
    agent: dict[str, Any] = raw_agent if isinstance(raw_agent, dict) else {}
    raw_campaign = cdr.get("campaign")
    campaign: dict[str, Any] = raw_campaign if isinstance(raw_campaign, dict) else {}
    return {
        "outcome": outcome,
        "provider_contact_id": provider_contact_id,
        "provider_cdr_id": _required_numeric_id(cdr.get("id"), "CDR"),
        "provider_call_id": _string(cdr.get("callid")),
        "full_name": full_name[:255],
        "phone": phone,
        "email": email_value,
        "property_address": address[:255],
        "property_city": city[:120],
        "property_state": state.upper()[:2],
        "property_zip_code": postal_code[:20],
        "has_complete_address": has_complete_address,
        "notes": notes,
        "raw_disposition": _string(cdr.get("disposition")),
        "campaign_id": _string(campaign.get("id")),
        "campaign_name": _string(campaign.get("name")),
        "agent_id": _string(agent.get("id")),
        "agent_name": " ".join(
            part
            for part in (_string(agent.get("firstname")), _string(agent.get("lastname")))
            if part
        ).strip(),
        "direction": _normalize_direction(cdr.get("direction")),
        "status": _string(cdr.get("status")) or "completed",
        "from_number": _call_numbers(cdr)[0],
        "to_number": _call_numbers(cdr)[1],
        "started_at": _parse_datetime(cdr.get("callStartTime")),
        "ended_at": _parse_datetime(cdr.get("callEndTime")),
        "duration_seconds": _nonnegative_int(cdr.get("duration")),
    }


def _ensure_batchdialer_lead(
    db: Session,
    *,
    event: ProspectingProviderEvent,
    normalized: dict[str, Any],
    prior_result: dict[str, Any],
) -> tuple[Lead, bool]:
    prior_lead_id = prior_result.get("lead_id")
    if prior_lead_id:
        try:
            lead = db.get(Lead, UUID(str(prior_lead_id)))
        except ValueError:
            lead = None
        if lead is not None:
            _apply_batchdialer_context(lead, event, normalized)
            return lead, False

    organization = get_default_organization(db)
    intake = _handoff_intake(normalized, event.external_event_id)
    duplicate = find_duplicate_match(db, organization, intake)
    contact = duplicate.contact or create_contact(db, organization, intake)
    property_record = duplicate.property_record or create_property(db, organization, intake)
    lead = duplicate.lead or create_lead(db, organization, contact, property_record, intake)
    created = duplicate.lead is None
    ensure_contact_methods(db, organization, contact, intake)
    apply_public_intake_context(lead, property_record, intake)
    conversation = ensure_primary_conversation(db, lead)
    _apply_batchdialer_context(lead, event, normalized)
    if created:
        enqueue_lead_created_ai_work(db, lead, source=PROVIDER)
        if normalized["has_complete_address"]:
            enqueue_property_research(
                db,
                property_record,
                source_lead_id=lead.id,
                trigger_source=PROVIDER,
            )
    ensure_inbound_case(
        db,
        organization_id=organization.id,
        lead=lead,
        submitted_at=event.occurred_at or event.received_at,
        sla_minutes=5,
        source_label="BatchDialer",
    )
    ensure_speed_to_lead_task(db, lead, contact)
    db.add(
        ActivityEvent(
            organization_id=lead.organization_id,
            actor_user_id=None,
            entity_type="lead",
            entity_id=lead.id,
            event_type="lead.batchdialer_direct_handoff_received",
            summary=(
                f"BatchDialer {normalized['raw_disposition']} handoff received from "
                f"{normalized['agent_name'] or 'the assigned VA'}."
            ),
        )
    )
    queue_staff_lead_alerts_for_lead(
        db,
        lead=lead,
        source_type="batchdialer_warm_handoff",
        source_event_id=event.id,
        source_label="BatchDialer",
        source_entity_type="prospecting_provider_event",
    )
    _ensure_attribution(db, lead, event, normalized)
    update_conversation_activity(
        conversation,
        direction="outbound",
        occurred_at=event.occurred_at or event.received_at,
        db=db,
    )
    return lead, created


def _handoff_intake(normalized: dict[str, Any], event_id: str) -> SellerIntakeCreate:
    try:
        return SellerIntakeCreate(
            property_address=normalized["property_address"],
            property_city=normalized["property_city"],
            property_state=normalized["property_state"],
            property_postal_code=normalized["property_zip_code"],
            name=normalized["full_name"],
            phone=normalized["phone"],
            email=normalized["email"],
            preferred_contact_method="phone",
            comments=normalized["notes"][:1000] or None,
            consent_to_contact=True,
            sms_consent=False,
            attribution=SellerIntakeAttribution(
                utm_source=PROVIDER,
                utm_medium="va_outbound",
                utm_campaign=normalized["campaign_name"] or normalized["campaign_id"],
                utm_term=normalized["agent_id"] or normalized["agent_name"],
                utm_content=event_id,
            ),
        )
    except ValidationError:
        if normalized.get("email") is None:
            raise
        normalized = {**normalized, "email": None}
        return _handoff_intake(normalized, event_id)


def _apply_batchdialer_context(
    lead: Lead,
    event: ProspectingProviderEvent,
    normalized: dict[str, Any],
) -> None:
    context = dict(lead.qualification_context or {})
    context["batchdialer"] = {
        "transport": "direct_api",
        "provider_event_id": event.external_event_id,
        "provider_contact_id": normalized["provider_contact_id"],
        "provider_cdr_id": normalized["provider_cdr_id"],
        "provider_call_id": normalized["provider_call_id"],
        "campaign_id": normalized["campaign_id"],
        "campaign_name": normalized["campaign_name"],
        "agent_id": normalized["agent_id"],
        "agent_name": normalized["agent_name"],
        "disposition": normalized["raw_disposition"],
        "follow_up_permission": "unknown",
        "occurred_at": (event.occurred_at or event.received_at).isoformat(),
        "property_data_status": (
            "provided" if normalized["has_complete_address"] else "address_needed"
        ),
    }
    if normalized["outcome"] == "appointment_set":
        context["batchdialer_appointment_pending_entry"] = True
        lead.appointment_status = "needs_scheduling"
    lead.qualification_context = context


def _ensure_attribution(
    db: Session,
    lead: Lead,
    event: ProspectingProviderEvent,
    normalized: dict[str, Any],
) -> None:
    existing = db.scalar(
        select(AttributionTouch.id).where(
            AttributionTouch.organization_id == lead.organization_id,
            AttributionTouch.lead_id == lead.id,
            AttributionTouch.touch_type == "batchdialer_handoff",
            AttributionTouch.content == event.external_event_id,
        )
    )
    if existing is not None:
        return
    db.add(
        AttributionTouch(
            organization_id=lead.organization_id,
            lead_id=lead.id,
            touch_type="batchdialer_handoff",
            source=PROVIDER,
            medium="va_outbound",
            campaign=normalized["campaign_name"] or normalized["campaign_id"],
            term=normalized["agent_id"] or normalized["agent_name"],
            content=event.external_event_id,
            gclid=None,
            fbclid=None,
            fbclid_captured_at=None,
            landing_page=None,
            referrer=None,
        )
    )


def _ensure_call_evidence(
    db: Session,
    *,
    event: ProspectingProviderEvent,
    lead: Lead,
    normalized: dict[str, Any],
) -> CallRecord:
    provider_call_id = normalized["provider_call_id"] or normalized["provider_cdr_id"]
    existing = db.scalar(
        select(CallRecord).where(
            CallRecord.organization_id == lead.organization_id,
            CallRecord.provider == PROVIDER,
            CallRecord.provider_call_id == provider_call_id,
        )
    )
    if existing is not None:
        return existing
    conversation = ensure_primary_conversation(db, lead)
    occurred_at = normalized["started_at"] or event.occurred_at or event.received_at
    body = _call_summary_body(normalized)
    communication = CommunicationRecord(
        organization_id=lead.organization_id,
        conversation_id=conversation.id,
        lead_id=lead.id,
        contact_id=lead.contact_id,
        actor_user_id=None,
        direction=normalized["direction"],
        channel="call",
        status=normalized["status"],
        provider=PROVIDER,
        provider_message_id=f"cdr:{normalized['provider_cdr_id']}",
        subject="BatchDialer seller call",
        body=body,
        occurred_at=occurred_at,
        external_payload={
            "cdr_id": normalized["provider_cdr_id"],
            "call_id": provider_call_id,
            "campaign_id": normalized["campaign_id"],
            "contact_id": normalized["provider_contact_id"],
        },
        communication_metadata={
            "source": "batchdialer_direct_api",
            "disposition": normalized["raw_disposition"],
            "agent_name": normalized["agent_name"],
        },
    )
    db.add(communication)
    db.flush()
    call = CallRecord(
        organization_id=lead.organization_id,
        conversation_id=conversation.id,
        lead_id=lead.id,
        contact_id=lead.contact_id,
        prospect_id=None,
        prospecting_attempt_id=None,
        prospecting_dial_leg_id=None,
        prospecting_inbound_callback_id=None,
        actor_user_id=None,
        communication_record_id=communication.id,
        voice_line_id=None,
        call_intent_id=None,
        provider=PROVIDER,
        provider_call_id=provider_call_id,
        child_provider_call_id=None,
        direction=normalized["direction"],
        status=normalized["status"],
        from_number=normalized["from_number"],
        to_number=normalized["to_number"],
        started_at=normalized["started_at"],
        answered_at=normalized["started_at"],
        ended_at=normalized["ended_at"],
        duration_seconds=normalized["duration_seconds"],
        disposition=normalized["raw_disposition"],
        recording_consent_status="provider_transcript",
        call_metadata={
            "source": "batchdialer_direct_api",
            "provider_cdr_id": normalized["provider_cdr_id"],
            "provider_contact_id": normalized["provider_contact_id"],
            "campaign_id": normalized["campaign_id"],
            "campaign_name": normalized["campaign_name"],
            "agent_id": normalized["agent_id"],
            "agent_name": normalized["agent_name"],
            "provider_event_id": str(event.id),
        },
    )
    db.add(call)
    db.flush()
    communication.source_call_record_id = call.id
    return call


def _sync_transcript(
    db: Session,
    *,
    client: BatchDialerClient,
    event: ProspectingProviderEvent,
    call: CallRecord,
    prior_result: dict[str, Any],
) -> dict[str, Any]:
    existing_recording = db.scalar(
        select(CallRecording).where(
            CallRecording.organization_id == call.organization_id,
            CallRecording.provider == PROVIDER,
            CallRecording.provider_recording_id == f"transcript:{event.provider_sequence_number}",
        )
    )
    if existing_recording is not None:
        existing_transcript = db.scalar(
            select(CallTranscript).where(CallTranscript.recording_id == existing_recording.id)
        )
        if existing_transcript is not None and existing_transcript.transcript_text:
            return {
                "status": "available",
                "attempts": int(prior_result.get("transcript_attempts") or 1),
            }

    attempts = int(prior_result.get("transcript_attempts") or 0) + 1
    if attempts > MAX_TRANSCRIPT_ATTEMPTS:
        return {"status": "unavailable", "attempts": attempts - 1}
    try:
        segments = client.get_transcript(event.provider_sequence_number or "")
    except BatchDialerAPIError as exc:
        logger.info(
            "batchdialer_transcript_not_ready",
            event_id=str(event.id),
            cdr_id=event.provider_sequence_number,
            error_type=type(exc).__name__,
        )
        return {"status": "pending", "attempts": attempts}
    text_segments = [
        {
            "time": segment.get("time"),
            "role": _string(segment.get("role")) or "speaker",
            "text": _clean_text(segment.get("text"))[:10_000],
        }
        for segment in segments
        if _clean_text(segment.get("text"))
    ]
    transcript_text = "\n".join(
        f"{segment['role']}: {segment['text']}" for segment in text_segments
    )[:MAX_TRANSCRIPT_LENGTH]
    if not transcript_text:
        return {"status": "pending", "attempts": attempts}
    recording = existing_recording
    if recording is None:
        recording = CallRecording(
            organization_id=call.organization_id,
            call_record_id=call.id,
            provider=PROVIDER,
            provider_recording_id=f"transcript:{event.provider_sequence_number}",
            status="transcript_only",
            media_reference=None,
            duration_seconds=call.duration_seconds,
            channel_count=None,
            consent_status="provider_transcript",
            recorded_at=call.started_at,
            retention_expires_at=None,
            deleted_at=None,
            deleted_by_user_id=None,
            deletion_reason=None,
            recording_metadata={
                "source": "batchdialer_direct_api",
                "media_available": False,
            },
        )
        db.add(recording)
        db.flush()
    transcript = db.scalar(
        select(CallTranscript).where(CallTranscript.recording_id == recording.id)
    )
    if transcript is None:
        transcript = CallTranscript(
            organization_id=call.organization_id,
            recording_id=recording.id,
            provider=PROVIDER,
            model_name="batchdialer",
            status="queued",
            language=None,
            transcript_text=transcript_text,
            speaker_segments=text_segments,
            confidence_score=None,
            approved_by_user_id=None,
            approved_at=None,
            error_message=None,
            transcript_metadata={
                "attempts": 0,
                "human_review_required": False,
                "source": "batchdialer_direct_api",
            },
        )
        db.add(transcript)
    elif not transcript.transcript_text:
        transcript.transcript_text = transcript_text
        transcript.speaker_segments = text_segments
        transcript.status = "queued"
        transcript.error_message = None
    return {"status": "available", "attempts": attempts}


def _ensure_manual_appointment_task(
    db: Session,
    *,
    lead: Lead,
    call: CallRecord,
    event: ProspectingProviderEvent,
) -> Task:
    task = db.scalar(
        select(Task).where(
            Task.organization_id == lead.organization_id,
            Task.lead_id == lead.id,
            Task.task_type == "batchdialer_manual_appointment",
            Task.status.in_(("open", "in_progress")),
        )
    )
    if task is not None:
        return task
    task = Task(
        organization_id=lead.organization_id,
        lead_id=lead.id,
        deal_id=None,
        prospecting_inbound_callback_id=None,
        prospect_id=None,
        call_record_id=call.id,
        responsible_user_id=lead.assigned_user_id,
        task_type="batchdialer_manual_appointment",
        work_kind="supporting",
        title="Enter and verify the BatchDialer seller appointment",
        status="open",
        priority="urgent",
        due_at=datetime.now(UTC) + timedelta(minutes=5),
        completed_at=None,
        completed_by_user_id=None,
        outcome=None,
        completion_notes=None,
        successor_task_id=None,
    )
    db.add(task)
    db.flush()
    db.add(
        ActivityEvent(
            organization_id=lead.organization_id,
            actor_user_id=None,
            entity_type="lead",
            entity_id=lead.id,
            event_type="lead.batchdialer_appointment_entry_required",
            summary=(
                "BatchDialer marked Appointment Set. A VA must enter the agreed time "
                "in Stonegate Calendar."
            ),
        )
    )
    return task


def classify_disposition(value: object) -> str:
    normalized = normalize_disposition(value)
    mapped = QUALIFIED_DISPOSITIONS.get(normalized)
    if mapped:
        return mapped
    if normalized in KNOWN_NON_LEAD_DISPOSITIONS:
        return "non_lead"
    return "unknown"


def normalize_disposition(value: object) -> str:
    raw = _string(value)
    raw = raw.replace("â€“", "-").replace("â€”", "-").replace("\u2013", "-")
    normalized = unicodedata.normalize("NFKC", raw)
    normalized = re.sub(r"[\u2010-\u2015]", "-", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip().casefold()
    return normalized


def sanitize_cdr(cdr: dict[str, Any]) -> dict[str, Any]:
    allowed_scalars = (
        "id",
        "direction",
        "callStartTime",
        "callEndTime",
        "did",
        "customerNumber",
        "disposition",
        "mood",
        "duration",
        "status",
        "callid",
        "voicemailid",
        "recordingenabled",
    )
    result = {key: cdr.get(key) for key in allowed_scalars if key in cdr}
    for key, fields in (
        ("agent", ("id", "firstname", "lastname")),
        (
            "contact",
            (
                "id",
                "firstname",
                "lastname",
                "address",
                "city",
                "state",
                "zip",
                "status",
                "email",
            ),
        ),
        ("campaign", ("id", "name")),
        ("client", ("id", "name")),
    ):
        value = cdr.get(key)
        if isinstance(value, dict):
            result[key] = {field: value.get(field) for field in fields if field in value}
    comments = cdr.get("comments")
    if isinstance(comments, list):
        result["comments"] = [
            _clean_text(comment)[:MAX_STORED_COMMENT_LENGTH]
            for comment in comments[:20]
            if _clean_text(comment)
        ]
    record_url = _string(cdr.get("callRecordUrl"))
    if record_url:
        result["callRecordUrl"] = _strip_url_query(record_url)[:1000]
    return result


def sanitize_contact(contact: dict[str, Any]) -> dict[str, Any]:
    scalar_fields = (
        "id",
        "vendorcontactid",
        "firstname",
        "middlename",
        "lastname",
        "address",
        "city",
        "state",
        "postalcode",
        "country",
        "email",
        "comments",
        "status",
        "datelasttouched",
        "federaldnc",
        "dateadded",
        "datemodified",
        "phonenumber1",
    )
    result = {key: contact.get(key) for key in scalar_fields if key in contact}
    phones = contact.get("phonenumbers")
    if isinstance(phones, list):
        result["phonenumbers"] = [
            {
                key: phone.get(key)
                for key in ("id", "phonenumber", "numbertype", "dnc", "tested", "reachable")
                if key in phone
            }
            for phone in phones[:20]
            if isinstance(phone, dict)
        ]
    custom_fields = contact.get("customfields")
    if isinstance(custom_fields, dict):
        result["customfields"] = _sanitize_custom_fields(custom_fields)
    return result


def _acquire_checkpoint(
    db: Session,
    organization_id: UUID,
    settings: Settings,
    *,
    now: datetime,
) -> BatchDialerSyncCheckpoint | None:
    checkpoint = db.scalar(
        select(BatchDialerSyncCheckpoint)
        .where(
            BatchDialerSyncCheckpoint.organization_id == organization_id,
            BatchDialerSyncCheckpoint.stream == CHECKPOINT_STREAM,
        )
        .with_for_update()
    )
    if checkpoint is None:
        checkpoint = BatchDialerSyncCheckpoint(
            organization_id=organization_id,
            stream=CHECKPOINT_STREAM,
            status="idle",
            sync_metadata={},
        )
        db.add(checkpoint)
        try:
            with db.begin_nested():
                db.flush()
        except IntegrityError:
            checkpoint = db.scalar(
                select(BatchDialerSyncCheckpoint)
                .where(
                    BatchDialerSyncCheckpoint.organization_id == organization_id,
                    BatchDialerSyncCheckpoint.stream == CHECKPOINT_STREAM,
                )
                .with_for_update()
            )
    if checkpoint is None:
        return None
    if checkpoint.next_poll_at and _aware(checkpoint.next_poll_at) > now:
        return None
    if checkpoint.lease_expires_at and _aware(checkpoint.lease_expires_at) > now:
        return None
    token = uuid4().hex
    checkpoint.status = "polling"
    checkpoint.lease_token = token
    checkpoint.lease_owner = socket.gethostname()[:255]
    checkpoint.lease_expires_at = now + timedelta(
        seconds=settings.batchdialer_checkpoint_lease_seconds
    )
    checkpoint.last_attempt_at = now
    checkpoint.poll_count += 1
    checkpoint.last_error = None
    db.commit()
    return checkpoint


def _locked_checkpoint(
    db: Session,
    checkpoint_id: UUID,
    lease_token: str,
) -> BatchDialerSyncCheckpoint:
    checkpoint = db.scalar(
        select(BatchDialerSyncCheckpoint)
        .where(BatchDialerSyncCheckpoint.id == checkpoint_id)
        .with_for_update()
    )
    if checkpoint is None or checkpoint.lease_token != lease_token:
        raise RuntimeError("BatchDialer polling lease was lost.")
    return checkpoint


def _campaign_refresh_due(
    checkpoint: BatchDialerSyncCheckpoint,
    settings: Settings,
    *,
    now: datetime,
) -> bool:
    if checkpoint.last_campaign_refresh_at is None:
        return True
    return _aware(checkpoint.last_campaign_refresh_at) <= now - timedelta(
        seconds=settings.batchdialer_campaign_refresh_seconds
    )


def _refresh_campaigns(
    db: Session,
    organization_id: UUID,
    client: BatchDialerClient,
    *,
    now: datetime,
) -> None:
    campaigns = client.get_campaigns()
    observed: set[str] = set()
    for raw in campaigns:
        campaign_id = _required_numeric_id(raw.get("id"), "campaign")
        observed.add(campaign_id)
        campaign = db.scalar(
            select(BatchDialerCampaign).where(
                BatchDialerCampaign.organization_id == organization_id,
                BatchDialerCampaign.provider_campaign_id == campaign_id,
            )
        )
        if campaign is None:
            campaign = BatchDialerCampaign(
                organization_id=organization_id,
                provider_campaign_id=campaign_id,
                name=_string(raw.get("name")) or f"BatchDialer campaign {campaign_id}",
                first_seen_at=now,
                last_seen_at=now,
                provider_snapshot={},
            )
            db.add(campaign)
        campaign.parent_campaign_id = _string(raw.get("parentid")) or None
        campaign.external_campaign_id = _string(raw.get("externalid")) or None
        campaign.name = _string(raw.get("name")) or campaign.name
        campaign.mode = _string(raw.get("mode")) or None
        campaign.status = _string(raw.get("status")) or "unknown"
        campaign.is_active = campaign.status.casefold() == "active"
        campaign.recycle_count = _nonnegative_int(raw.get("recyclecount")) or 0
        campaign.hierarchy_level = _nonnegative_int(raw.get("level")) or 0
        campaign.contact_count = _nonnegative_int(raw.get("number_of_contacts")) or 0
        campaign.provider_created_at = _parse_datetime(raw.get("date_added"))
        campaign.last_seen_at = now
        campaign.provider_snapshot = sanitize_campaign(raw)
    for campaign in db.scalars(
        select(BatchDialerCampaign).where(
            BatchDialerCampaign.organization_id == organization_id,
            BatchDialerCampaign.is_active.is_(True),
        )
    ).all():
        if campaign.provider_campaign_id not in observed:
            campaign.is_active = False
            campaign.status = "not_returned_by_active_campaigns"
    db.flush()


def sanitize_campaign(campaign: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "id",
        "parentid",
        "name",
        "mode",
        "recyclecount",
        "level",
        "externalid",
        "number_of_contacts",
        "date_added",
        "status",
    )
    return {key: campaign.get(key) for key in fields if key in campaign}


def _record_campaign_cdr(
    db: Session,
    organization_id: UUID,
    cdr: dict[str, Any],
    *,
    archive_result: str,
    disposition_kind: str,
    now: datetime,
) -> None:
    raw_campaign = cdr.get("campaign")
    if not isinstance(raw_campaign, dict):
        return
    campaign_id = _string(raw_campaign.get("id"))
    if not campaign_id:
        return
    campaign = db.scalar(
        select(BatchDialerCampaign).where(
            BatchDialerCampaign.organization_id == organization_id,
            BatchDialerCampaign.provider_campaign_id == campaign_id,
        )
    )
    if campaign is None:
        campaign = BatchDialerCampaign(
            organization_id=organization_id,
            provider_campaign_id=campaign_id,
            name=_string(raw_campaign.get("name")) or f"BatchDialer campaign {campaign_id}",
            status="observed_in_cdr",
            is_active=True,
            first_seen_at=now,
            last_seen_at=now,
            provider_snapshot={"id": campaign_id, "name": raw_campaign.get("name")},
        )
        db.add(campaign)
    campaign.last_seen_at = now
    if archive_result == "archived":
        campaign.cdr_seen_count += 1
        if disposition_kind in {"interested", "appointment_set"}:
            campaign.qualified_cdr_count += 1
    occurred_at = _cdr_occurred_at(cdr)
    if occurred_at and (campaign.last_cdr_at is None or _aware(campaign.last_cdr_at) < occurred_at):
        campaign.last_cdr_at = occurred_at


def _record_campaign_import(
    db: Session,
    organization_id: UUID,
    campaign_id: str,
) -> None:
    if not campaign_id:
        return
    campaign = db.scalar(
        select(BatchDialerCampaign).where(
            BatchDialerCampaign.organization_id == organization_id,
            BatchDialerCampaign.provider_campaign_id == campaign_id,
        )
    )
    if campaign is not None:
        campaign.imported_lead_count += 1


def _mark_event(
    db: Session,
    event_id: UUID,
    status: str,
    error: str | None,
    *,
    processed: bool,
) -> None:
    event = db.get(ProspectingProviderEvent, event_id)
    if event is None:
        return
    event.processing_status = status
    event.error_message = error[:2000] if error else None
    event.processed_at = datetime.now(UTC) if processed else None
    db.commit()


def _mark_event_failure(
    db: Session,
    event_id: UUID,
    settings: Settings,
    error: str,
) -> None:
    event = db.get(ProspectingProviderEvent, event_id)
    if event is None:
        return
    exhausted = event.retry_count >= settings.batchdialer_event_max_attempts
    event.processing_status = "exhausted" if exhausted else "retry"
    event.error_message = error[:2000]
    event.processed_at = datetime.now(UTC) if exhausted else None
    db.commit()


def _transcript_recheck_due(event: ProspectingProviderEvent, *, now: datetime) -> bool:
    if event.processing_status != "processed":
        return False
    result = (event.payload or {}).get("_stonegate")
    if not isinstance(result, dict) or result.get("transcript_status") != "pending":
        return False
    if int(result.get("transcript_attempts") or 0) >= MAX_TRANSCRIPT_ATTEMPTS:
        return False
    checked_at = _parse_datetime(result.get("transcript_checked_at"))
    return checked_at is None or checked_at <= now - timedelta(
        seconds=TRANSCRIPT_RECHECK_SECONDS
    )


def _contact_id(cdr: dict[str, Any]) -> str | None:
    contact = cdr.get("contact")
    return _string(contact.get("id")) if isinstance(contact, dict) else None


def _contact_phone(contact: dict[str, Any]) -> str | None:
    candidates: list[str] = []
    primary = _string(contact.get("phonenumber1"))
    if primary:
        candidates.append(primary)
    phones = contact.get("phonenumbers")
    if isinstance(phones, list):
        candidates.extend(
            _string(item.get("phonenumber"))
            for item in phones
            if isinstance(item, dict) and _string(item.get("phonenumber"))
        )
    for candidate in candidates:
        normalized = format_e164(candidate)
        if normalized:
            return normalized
    return None


def _collect_provider_notes(cdr: dict[str, Any], contact: dict[str, Any]) -> str:
    values: list[str] = []
    comments = cdr.get("comments")
    if isinstance(comments, list):
        values.extend(_clean_text(item) for item in comments)
    contact_comment = _clean_text(contact.get("comments"))
    if contact_comment:
        values.append(contact_comment)
    custom_fields = contact.get("customfields")
    if isinstance(custom_fields, dict):
        values.extend(
            f"{_clean_text(key)[:120]}: {_clean_text(field_value)[:1000]}"
            for key, field_value in list(custom_fields.items())[:50]
            if _clean_text(key) and _clean_text(field_value)
        )
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        compact = value.strip()
        if not compact or compact.casefold() in seen:
            continue
        seen.add(compact.casefold())
        unique.append(compact)
    return "\n\n".join(unique)[:10_000]


def _sanitize_custom_fields(values: dict[Any, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_key, raw_value in list(values.items())[:50]:
        key = _clean_text(raw_key)[:120]
        if not key:
            continue
        if isinstance(raw_value, (list, tuple, set)):
            value = ", ".join(
                part
                for part in (_clean_text(item)[:500] for item in list(raw_value)[:20])
                if part
            )
        else:
            value = _clean_text(raw_value)[:1000]
        if value:
            result[key] = value
    return result


def _call_summary_body(normalized: dict[str, Any]) -> str:
    heading = (
        f"BatchDialer call completed with result: {normalized['raw_disposition'] or 'Unknown'}."
    )
    agent = f"VA: {normalized['agent_name']}." if normalized["agent_name"] else ""
    notes = normalized["notes"]
    return "\n\n".join(part for part in (heading, agent, notes) if part)[:20_000]


def _call_numbers(cdr: dict[str, Any]) -> tuple[str | None, str | None]:
    direction = _normalize_direction(cdr.get("direction"))
    company_number = format_e164(_string(cdr.get("did")))
    customer_number = format_e164(_string(cdr.get("customerNumber")))
    if direction == "inbound":
        return customer_number, company_number
    return company_number, customer_number


def _normalize_direction(value: object) -> str:
    normalized = _string(value).casefold()
    return "inbound" if normalized in {"in", "inbound"} else "outbound"


def _cdr_occurred_at(cdr: dict[str, Any]) -> datetime | None:
    return _parse_datetime(cdr.get("callEndTime")) or _parse_datetime(
        cdr.get("callStartTime")
    )


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _nested_string(value: dict[str, Any], parent: str, child: str) -> str:
    nested = value.get(parent)
    return _string(nested.get(child)) if isinstance(nested, dict) else ""


def _string(value: object) -> str:
    if value is None or isinstance(value, (dict, list, tuple, set)):
        return ""
    return str(value).strip()


def _clean_text(value: object) -> str:
    raw = _string(value)
    if not raw:
        return ""
    without_markup = re.sub(r"<[^>]+>", " ", html.unescape(raw))
    return re.sub(r"\s+", " ", without_markup).strip()


def _looks_like_email(value: str | None) -> bool:
    if not value:
        return False
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value.strip()))


def _nonnegative_int(value: object) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if not isinstance(value, (int, float, str, bytes, bytearray)):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, int(result))


def _required_numeric_id(value: object, label: str) -> str:
    normalized = _string(value)
    if not normalized.isdigit():
        raise BatchDialerNeedsReview(f"BatchDialer {label} has no numeric identifier.")
    return normalized


def _payload_hash(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _strip_url_query(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "[invalid provider URL]"
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, BatchDialerAPIError):
        return str(exc)[:2000]
    if isinstance(exc, BatchDialerNeedsReview):
        return str(exc)[:2000]
    return f"{type(exc).__name__}: BatchDialer direct integration operation failed."[:2000]
