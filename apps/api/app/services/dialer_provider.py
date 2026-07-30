import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID

import httpx
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import Settings, get_settings
from app.models.foundation import (
    AuditEvent,
    Prospect,
    ProspectCallingBatch,
    ProspectCallingBatchEntry,
    ProspectContactPoint,
    ProspectingAttempt,
    ProspectingCohort,
    ProspectingProviderCampaign,
    ProspectingProviderContact,
    ProspectingProviderEvent,
    ProspectingScriptVersion,
    SuppressionRecord,
    User,
)
from app.schemas.campaign_management import (
    DialerCampaignSyncRead,
    DialerProviderConfigurationRead,
    DialerProviderEventCreate,
    DialerProviderEventRead,
)
from app.services.prospecting import get_active_script, refresh_batch_status
from app.services.prospecting_measurement import apply_outcome_measurement

PROVIDER = "batchdialer"
NORMALIZED_OUTCOMES = {
    "no_answer": "no_answer",
    "no-answer": "no_answer",
    "unanswered": "no_answer",
    "busy": "no_answer",
    "failed": "no_answer",
    "voicemail": "left_voicemail",
    "left_voicemail": "left_voicemail",
    "callback": "callback_requested",
    "callback_requested": "callback_requested",
    "follow_up": "follow_up",
    "interested": "interested",
    "hot_lead": "interested",
    "appointment": "appointment_set",
    "appointment_set": "appointment_set",
    "not_interested": "not_interested",
    "wrong_number": "wrong_number",
    "dnc": "do_not_call",
    "do_not_call": "do_not_call",
}
CONTACT_OUTCOMES = {
    "callback_requested",
    "follow_up",
    "interested",
    "appointment_set",
    "not_interested",
    "do_not_call",
}


class DialerAdapter(Protocol):
    def create_campaign(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class SimulationDialerAdapter:
    def create_campaign(self, payload: dict[str, Any]) -> dict[str, Any]:
        batch_id = str(payload["stonegate_batch_id"])
        return {
            "campaign_id": f"sim-campaign-{batch_id}",
            "contacts": [
                {
                    "external_id": contact["stonegate_entry_id"],
                    "contact_id": f"sim-contact-{contact['stonegate_entry_id']}",
                    "status": "synced",
                }
                for contact in payload["contacts"]
            ],
            "simulation": True,
        }


class BatchDialerHttpAdapter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def create_campaign(self, payload: dict[str, Any]) -> dict[str, Any]:
        assert self.settings.batchdialer_api_key
        assert self.settings.batchdialer_api_base_url
        assert self.settings.batchdialer_campaign_sync_path
        url = (
            self.settings.batchdialer_api_base_url.rstrip("/")
            + "/"
            + self.settings.batchdialer_campaign_sync_path.lstrip("/")
        )
        response = httpx.post(
            url,
            headers={
                "Authorization": f"Bearer {self.settings.batchdialer_api_key}",
                "Accept": "application/json",
            },
            json=payload,
            timeout=self.settings.batchdialer_request_timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("BatchDialer returned an unsupported campaign response.")
        campaign_id = data.get("campaign_id") or data.get("id")
        contacts = data.get("contacts")
        if not campaign_id or not isinstance(contacts, list):
            raise ValueError(
                "BatchDialer response mapping is incomplete. Confirm the private API schema."
            )
        return data


def provider_configuration(settings: Settings | None = None) -> DialerProviderConfigurationRead:
    resolved = settings or get_settings()
    blockers = list(resolved.dialer_provider_configuration_blockers)
    return DialerProviderConfigurationRead(
        provider=resolved.dialer_provider,
        mode=resolved.dialer_provider_mode,
        configured=not blockers,
        blockers=blockers,
        live_mapping_status=(
            "simulation_ready"
            if resolved.dialer_provider_mode == "simulate"
            else (
                "private_api_mapping_required"
                if resolved.dialer_provider_mode == "live" and blockers
                else "live_ready"
                if resolved.dialer_provider_mode == "live"
                else "disabled"
            )
        ),
    )


def list_campaign_syncs(db: Session, principal: Principal) -> list[DialerCampaignSyncRead]:
    syncs = db.scalars(
        select(ProspectingProviderCampaign)
        .where(ProspectingProviderCampaign.organization_id == principal.organization_id)
        .order_by(ProspectingProviderCampaign.created_at.desc())
        .limit(100)
    ).all()
    return [campaign_sync_read(db, sync) for sync in syncs]


def sync_calling_batch(
    db: Session,
    principal: Principal,
    batch_id: UUID,
    *,
    settings: Settings | None = None,
) -> DialerCampaignSyncRead:
    resolved = settings or get_settings()
    batch = db.scalar(
        select(ProspectCallingBatch).where(
            ProspectCallingBatch.organization_id == principal.organization_id,
            ProspectCallingBatch.id == batch_id,
        )
    )
    if batch is None:
        raise ValueError("The calling batch is unavailable.")
    if batch.dialer_mode != "multi_line_parallel":
        raise ValueError("Only multi-line calling batches are sent to the dialer provider.")
    blockers = resolved.dialer_provider_configuration_blockers
    if blockers:
        raise ValueError("Dialer provider is not configured: " + ", ".join(blockers) + ".")
    script = script_for_batch(db, batch)
    if script is None:
        raise ValueError("Approve a caller script before synchronizing a dialer campaign.")
    entries = eligible_batch_entries(db, batch)
    if not entries:
        raise ValueError(
            "This batch has no untouched, assigned, callable prospects to synchronize."
        )

    existing = db.scalar(
        select(ProspectingProviderCampaign).where(
            ProspectingProviderCampaign.prospect_calling_batch_id == batch.id
        )
    )
    now = datetime.now(UTC)
    payload = campaign_payload(db, batch, script, entries)
    sync = existing or ProspectingProviderCampaign(
        organization_id=principal.organization_id,
        prospect_calling_batch_id=batch.id,
        provider=PROVIDER,
        provider_campaign_id=None,
        mode=resolved.dialer_provider_mode,
        status="syncing",
        eligible_contact_count=len(entries),
        synced_contact_count=0,
        failed_contact_count=0,
        retry_count=0,
        request_payload=payload,
        response_payload={},
        error_message=None,
        last_synced_at=None,
        last_reconciled_at=None,
    )
    if existing:
        sync.status = "syncing"
        sync.mode = resolved.dialer_provider_mode
        sync.eligible_contact_count = len(entries)
        sync.request_payload = payload
        sync.error_message = None
        sync.retry_count += 1
    else:
        db.add(sync)
    db.flush()

    try:
        adapter: DialerAdapter = (
            SimulationDialerAdapter()
            if resolved.dialer_provider_mode == "simulate"
            else BatchDialerHttpAdapter(resolved)
        )
        result = adapter.create_campaign(payload)
        apply_campaign_response(db, sync, entries, payload, result, now)
    except (httpx.HTTPError, ValueError) as exc:
        sync.status = "failed"
        sync.error_message = str(exc)[:2000]
        sync.failed_contact_count = len(entries)
        add_audit(
            db,
            principal,
            action="dialer_provider.campaign_sync_failed",
            entity_type="prospecting_provider_campaign",
            entity_id=sync.id,
            new={"batch_id": str(batch.id), "error": sync.error_message},
            reason="Dialer campaign synchronization failed",
        )
        db.commit()
        return campaign_sync_read(db, sync)

    batch.status = "provider_ready"
    add_audit(
        db,
        principal,
        action="dialer_provider.campaign_synced",
        entity_type="prospecting_provider_campaign",
        entity_id=sync.id,
        new={
            "batch_id": str(batch.id),
            "provider_campaign_id": sync.provider_campaign_id,
            "contacts": sync.synced_contact_count,
            "mode": sync.mode,
        },
        reason="Assigned cold prospects synchronized through provider adapter",
    )
    db.commit()
    return campaign_sync_read(db, sync)


def eligible_batch_entries(
    db: Session,
    batch: ProspectCallingBatch,
) -> list[ProspectCallingBatchEntry]:
    return list(
        db.scalars(
            select(ProspectCallingBatchEntry)
            .join(Prospect, Prospect.id == ProspectCallingBatchEntry.prospect_id)
            .where(
                ProspectCallingBatchEntry.prospect_calling_batch_id == batch.id,
                ProspectCallingBatchEntry.assigned_user_id == batch.assigned_user_id,
                ProspectCallingBatchEntry.status.in_(("queued", "ready")),
                ProspectCallingBatchEntry.attempt_count == 0,
                Prospect.call_eligibility == "eligible",
                Prospect.converted_lead_id.is_(None),
                Prospect.last_contacted_at.is_(None),
            )
            .order_by(ProspectCallingBatchEntry.sequence_number)
        ).all()
    )


def campaign_payload(
    db: Session,
    batch: ProspectCallingBatch,
    script: ProspectingScriptVersion,
    entries: list[ProspectCallingBatchEntry],
) -> dict[str, Any]:
    assignee = db.get(User, batch.assigned_user_id)
    contacts: list[dict[str, Any]] = []
    for entry in entries:
        prospect = db.get(Prospect, entry.prospect_id)
        if prospect is None:
            continue
        phones = db.scalars(
            select(ProspectContactPoint)
            .where(
                ProspectContactPoint.prospect_id == prospect.id,
                ProspectContactPoint.contact_type == "phone",
                ProspectContactPoint.validation_status != "invalid",
            )
            .order_by(ProspectContactPoint.rank, ProspectContactPoint.created_at)
        ).all()
        values = [phone.value for phone in phones]
        if prospect.phone and prospect.phone not in values:
            values.insert(0, prospect.phone)
        contacts.append(
            {
                "stonegate_entry_id": str(entry.id),
                "stonegate_prospect_id": str(prospect.id),
                "legal_name": prospect.legal_name,
                "phones": values,
                "property": {
                    "street_address": prospect.street_address,
                    "city": prospect.city,
                    "state_code": prospect.state_code,
                    "postal_code": prospect.postal_code,
                },
            }
        )
    return {
        "stonegate_batch_id": str(batch.id),
        "name": batch.name,
        "dialer_mode": batch.dialer_mode,
        "assigned_agent": {
            "stonegate_user_id": str(batch.assigned_user_id),
            "email": assignee.email if assignee else None,
            "display_name": assignee.display_name if assignee else None,
        },
        "script": {
            "stonegate_script_id": str(script.id),
            "version": script.version_number,
            "title": script.title,
            "opening": script.opening_script,
        },
        "contacts": contacts,
    }


def apply_campaign_response(
    db: Session,
    sync: ProspectingProviderCampaign,
    entries: list[ProspectCallingBatchEntry],
    payload: dict[str, Any],
    result: dict[str, Any],
    now: datetime,
) -> None:
    provider_campaign_id = result.get("campaign_id") or result.get("id")
    if not isinstance(provider_campaign_id, str) or not provider_campaign_id:
        raise ValueError("Dialer provider did not return a campaign identifier.")
    result_contacts = result.get("contacts")
    if not isinstance(result_contacts, list):
        raise ValueError("Dialer provider did not return contact mappings.")
    mappings = {
        str(item.get("external_id") or item.get("stonegate_entry_id")): item
        for item in result_contacts
        if isinstance(item, dict)
    }
    synced_count = 0
    failed_count = 0
    payload_contacts = {
        str(item["stonegate_entry_id"]): item for item in payload["contacts"]
    }
    for entry in entries:
        key = str(entry.id)
        mapped = mappings.get(key)
        provider_contact_id = None
        if mapped is not None:
            provider_contact_id = mapped.get("contact_id") or mapped.get("id")
        status = "synced" if provider_contact_id else "failed"
        contact_sync = db.scalar(
            select(ProspectingProviderContact).where(
                ProspectingProviderContact.batch_entry_id == entry.id
            )
        )
        if contact_sync is None:
            contact_sync = ProspectingProviderContact(
                organization_id=sync.organization_id,
                provider_campaign_sync_id=sync.id,
                batch_entry_id=entry.id,
                prospect_id=entry.prospect_id,
                provider=sync.provider,
                provider_contact_id=str(provider_contact_id) if provider_contact_id else None,
                status=status,
                contact_payload=payload_contacts[key],
                provider_metadata=mapped or {},
                last_event_at=None,
                error_message=None if provider_contact_id else "Provider contact ID missing.",
            )
            db.add(contact_sync)
        else:
            contact_sync.provider_campaign_sync_id = sync.id
            contact_sync.provider_contact_id = (
                str(provider_contact_id) if provider_contact_id else None
            )
            contact_sync.status = status
            contact_sync.contact_payload = payload_contacts[key]
            contact_sync.provider_metadata = mapped or {}
            contact_sync.error_message = (
                None if provider_contact_id else "Provider contact ID missing."
            )
        synced_count += int(bool(provider_contact_id))
        failed_count += int(not provider_contact_id)
    sync.provider_campaign_id = provider_campaign_id
    sync.status = "ready" if failed_count == 0 else "needs_attention"
    sync.synced_contact_count = synced_count
    sync.failed_contact_count = failed_count
    sync.response_payload = result
    sync.error_message = None if failed_count == 0 else "Some contacts were not acknowledged."
    sync.last_synced_at = now


def receive_provider_event(
    db: Session,
    organization_id: UUID,
    payload: DialerProviderEventCreate,
) -> ProspectingProviderEvent:
    existing = db.scalar(
        select(ProspectingProviderEvent).where(
            ProspectingProviderEvent.organization_id == organization_id,
            ProspectingProviderEvent.provider == PROVIDER,
            ProspectingProviderEvent.external_event_id == payload.external_event_id,
        )
    )
    if existing is not None:
        return existing
    sync = db.scalar(
        select(ProspectingProviderCampaign).where(
            ProspectingProviderCampaign.organization_id == organization_id,
            ProspectingProviderCampaign.provider == PROVIDER,
            ProspectingProviderCampaign.provider_campaign_id == payload.provider_campaign_id,
        )
    )
    now = datetime.now(UTC)
    event = ProspectingProviderEvent(
        organization_id=organization_id,
        provider_campaign_sync_id=sync.id if sync else None,
        provider_contact_sync_id=None,
        batch_entry_id=None,
        attempt_id=None,
        provider=PROVIDER,
        external_event_id=payload.external_event_id,
        event_type=payload.event_type,
        processing_status="received",
        provider_call_id=payload.provider_call_id,
        provider_recording_id=payload.provider_recording_id,
        payload=payload.model_dump(mode="json"),
        retry_count=0,
        error_message=None,
        received_at=now,
        processed_at=None,
    )
    db.add(event)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        duplicate = db.scalar(
            select(ProspectingProviderEvent).where(
                ProspectingProviderEvent.organization_id == organization_id,
                ProspectingProviderEvent.provider == PROVIDER,
                ProspectingProviderEvent.external_event_id == payload.external_event_id,
            )
        )
        if duplicate is None:
            raise
        return duplicate
    process_provider_event(db, event, payload)
    db.commit()
    return event


def process_provider_event(
    db: Session,
    event: ProspectingProviderEvent,
    payload: DialerProviderEventCreate,
) -> None:
    try:
        if event.provider_campaign_sync_id is None:
            raise ValueError("Provider campaign ID is not mapped to a Stonegate batch.")
        sync = db.get(ProspectingProviderCampaign, event.provider_campaign_sync_id)
        if sync is None:
            raise ValueError("Provider campaign synchronization record is unavailable.")
        if payload.event_type == "campaign.error":
            sync.status = "failed"
            sync.error_message = payload.error_message or "Provider reported a campaign error."
            event.processing_status = "processed"
            event.processed_at = datetime.now(UTC)
            return
        if payload.event_type == "recording.ready":
            apply_recording_event(db, event, payload)
            return
        apply_call_event(db, sync, event, payload)
    except ValueError as exc:
        event.processing_status = "failed"
        event.error_message = str(exc)[:2000]
        event.processed_at = None


def apply_call_event(
    db: Session,
    sync: ProspectingProviderCampaign,
    event: ProspectingProviderEvent,
    payload: DialerProviderEventCreate,
) -> None:
    contact = db.scalar(
        select(ProspectingProviderContact).where(
            ProspectingProviderContact.organization_id == event.organization_id,
            ProspectingProviderContact.provider == PROVIDER,
            ProspectingProviderContact.provider_contact_id == payload.provider_contact_id,
        )
    )
    if contact is None:
        raise ValueError("Provider contact ID is not mapped to a Stonegate prospect.")
    entry = db.get(ProspectCallingBatchEntry, contact.batch_entry_id)
    prospect = db.get(Prospect, contact.prospect_id)
    batch = (
        db.get(ProspectCallingBatch, entry.prospect_calling_batch_id) if entry is not None else None
    )
    script = script_for_batch(db, batch) if batch is not None else None
    caller = db.get(User, entry.assigned_user_id) if entry is not None else None
    if entry is None or prospect is None or batch is None or script is None or caller is None:
        raise ValueError("The synchronized Stonegate prospecting record is incomplete.")
    outcome = normalize_outcome(payload.outcome)
    existing_attempt = db.scalar(
        select(ProspectingAttempt).where(
            ProspectingAttempt.organization_id == event.organization_id,
            ProspectingAttempt.provider == PROVIDER,
            ProspectingAttempt.provider_call_id == payload.provider_call_id,
        )
    )
    if existing_attempt is not None:
        event.provider_contact_sync_id = contact.id
        event.batch_entry_id = entry.id
        event.attempt_id = existing_attempt.id
        event.processing_status = "duplicate_call"
        event.processed_at = datetime.now(UTC)
        return
    occurred_at = as_utc(payload.occurred_at)
    started_at = as_utc(payload.started_at) if payload.started_at else occurred_at
    answered_at = as_utc(payload.answered_at) if payload.answered_at else None
    completed_at = as_utc(payload.ended_at) if payload.ended_at else occurred_at
    callback_at = as_utc(payload.callback_at) if payload.callback_at else None
    required_count = sum(
        bool(question.get("required_for_handoff"))
        for question in script.qualification_questions
    )
    attempt = ProspectingAttempt(
        organization_id=event.organization_id,
        batch_entry_id=entry.id,
        prospect_id=prospect.id,
        caller_user_id=caller.id,
        script_version_id=script.id,
        call_record_id=None,
        cohort_id=batch.cohort_id,
        status="completed",
        outcome=outcome,
        contact_made=outcome in CONTACT_OUTCOMES,
        dialer_mode=batch.dialer_mode,
        answer_classification="human" if outcome in CONTACT_OUTCOMES else "no_human",
        party_classification="unknown",
        interest_classification="not_assessed",
        follow_up_permission="not_recorded",
        classification_source="provider_event",
        provider=PROVIDER,
        provider_call_id=payload.provider_call_id,
        provider_recording_id=payload.provider_recording_id,
        provider_agent_id=payload.provider_agent_id,
        dial_started_at=started_at,
        answered_at=answered_at,
        right_party_confirmed_at=None,
        interest_confirmed_at=None,
        measurement_metadata={
            "provider_event_id": payload.external_event_id,
            "provider_duration_seconds": payload.duration_seconds,
            "provider_metadata": payload.metadata,
        },
        qualification_answers={},
        notes=None,
        callback_at=callback_at,
        started_at=started_at,
        completed_at=completed_at,
        required_answer_count=required_count,
        answered_required_count=0,
        quality_score_basis_points=0 if required_count else None,
    )
    apply_outcome_measurement(attempt, outcome=outcome, completed_at=completed_at)
    db.add(attempt)
    db.flush()
    entry.attempt_count += 1
    entry.disposition = outcome
    entry.last_attempt_at = completed_at
    entry.next_attempt_at = None
    entry.completed_at = None
    prospect.last_contacted_at = completed_at
    review_required = False
    if outcome == "no_answer":
        entry.status = "queued"
        entry.next_attempt_at = completed_at + timedelta(days=1)
    elif outcome == "left_voicemail":
        entry.status = "queued"
        entry.next_attempt_at = completed_at + timedelta(days=2)
    elif outcome in {"callback_requested", "follow_up"} and callback_at is not None:
        entry.status = "queued"
        entry.next_attempt_at = callback_at
    elif outcome in {"callback_requested", "follow_up", "interested", "appointment_set"}:
        entry.status = "needs_correction"
        review_required = True
    else:
        entry.status = "completed"
        entry.completed_at = completed_at
        prospect.status = outcome
        if outcome == "wrong_number":
            prospect.phone_validation_status = "invalid"
            prospect.call_eligibility = "blocked"
        elif outcome == "do_not_call":
            prospect.call_eligibility = "blocked"
            prospect.suppression_status = "suppressed"
            record_provider_suppression(db, event, prospect, completed_at)
    contact.status = "called"
    contact.last_event_at = occurred_at
    event.provider_contact_sync_id = contact.id
    event.batch_entry_id = entry.id
    event.attempt_id = attempt.id
    event.processing_status = "needs_review" if review_required else "processed"
    event.processed_at = datetime.now(UTC)
    event.error_message = (
        "Complete the warm or callback handoff details in Stonegate."
        if review_required
        else None
    )
    add_provider_audit(
        db,
        organization_id=event.organization_id,
        actor_user_id=caller.id,
        action="dialer_provider.call_normalized",
        entity_type="prospecting_attempt",
        entity_id=attempt.id,
        new={
            "provider_call_id": payload.provider_call_id,
            "outcome": outcome,
            "entry_status": entry.status,
        },
        reason="Provider call normalized into Stonegate prospect history",
    )
    refresh_batch_status(db, batch.id)


def apply_recording_event(
    db: Session,
    event: ProspectingProviderEvent,
    payload: DialerProviderEventCreate,
) -> None:
    attempt = db.scalar(
        select(ProspectingAttempt).where(
            ProspectingAttempt.organization_id == event.organization_id,
            ProspectingAttempt.provider == PROVIDER,
            ProspectingAttempt.provider_call_id == payload.provider_call_id,
        )
    )
    if attempt is None:
        raise ValueError("Recording arrived before its provider call was normalized.")
    attempt.provider_recording_id = payload.provider_recording_id
    attempt.measurement_metadata = {
        **attempt.measurement_metadata,
        "provider_recording_url": payload.recording_url,
        "provider_recording_event_id": payload.external_event_id,
    }
    event.attempt_id = attempt.id
    event.batch_entry_id = attempt.batch_entry_id
    event.processing_status = "processed"
    event.processed_at = datetime.now(UTC)


def simulate_campaign(
    db: Session,
    principal: Principal,
    sync_id: UUID,
    *,
    settings: Settings | None = None,
) -> DialerCampaignSyncRead:
    resolved = settings or get_settings()
    if resolved.dialer_provider_mode != "simulate":
        raise ValueError("Provider event simulation is available only in simulate mode.")
    sync = scoped_sync(db, principal, sync_id)
    if sync is None or not sync.provider_campaign_id:
        raise ValueError("Synchronize the simulated campaign before generating events.")
    contacts = db.scalars(
        select(ProspectingProviderContact)
        .where(
            ProspectingProviderContact.provider_campaign_sync_id == sync.id,
            ProspectingProviderContact.provider_contact_id.is_not(None),
        )
        .order_by(ProspectingProviderContact.created_at)
    ).all()
    outcomes = ("no_answer", "left_voicemail", "not_interested")
    base_time = datetime.now(UTC)
    for index, contact in enumerate(contacts):
        entry = db.get(ProspectCallingBatchEntry, contact.batch_entry_id)
        if entry is None:
            continue
        call_id = f"sim-call-{contact.batch_entry_id}"
        occurred_at = base_time + timedelta(seconds=index)
        call_payload = DialerProviderEventCreate(
            external_event_id=f"sim-event-call-{contact.batch_entry_id}",
            event_type="call.completed",
            provider_campaign_id=sync.provider_campaign_id,
            provider_contact_id=contact.provider_contact_id,
            provider_call_id=call_id,
            provider_agent_id=str(entry.assigned_user_id),
            occurred_at=occurred_at,
            outcome=outcomes[index % len(outcomes)],
            started_at=occurred_at - timedelta(seconds=20),
            answered_at=(
                occurred_at - timedelta(seconds=12)
                if outcomes[index % len(outcomes)] == "not_interested"
                else None
            ),
            ended_at=occurred_at,
            duration_seconds=20,
            metadata={"simulation": True},
        )
        receive_provider_event(db, principal.organization_id, call_payload)
        recording_payload = DialerProviderEventCreate(
            external_event_id=f"sim-event-recording-{contact.batch_entry_id}",
            event_type="recording.ready",
            provider_campaign_id=sync.provider_campaign_id,
            provider_call_id=call_id,
            provider_recording_id=f"sim-recording-{contact.batch_entry_id}",
            occurred_at=occurred_at + timedelta(seconds=1),
            recording_url=f"simulation://recordings/{contact.batch_entry_id}",
            metadata={"simulation": True},
        )
        receive_provider_event(db, principal.organization_id, recording_payload)
    sync.last_reconciled_at = datetime.now(UTC)
    sync.status = "reconciled"
    db.commit()
    return campaign_sync_read(db, sync)


def reconcile_campaign(
    db: Session,
    principal: Principal,
    sync_id: UUID,
) -> DialerCampaignSyncRead:
    sync = scoped_sync(db, principal, sync_id)
    if sync is None:
        raise ValueError("Provider campaign synchronization record is unavailable.")
    failed_events = db.scalars(
        select(ProspectingProviderEvent).where(
            ProspectingProviderEvent.provider_campaign_sync_id == sync.id,
            ProspectingProviderEvent.processing_status == "failed",
        )
    ).all()
    for event in failed_events:
        event.retry_count += 1
        process_provider_event(db, event, DialerProviderEventCreate.model_validate(event.payload))
    contacts = db.scalars(
        select(ProspectingProviderContact).where(
            ProspectingProviderContact.provider_campaign_sync_id == sync.id
        )
    ).all()
    sync.synced_contact_count = sum(bool(contact.provider_contact_id) for contact in contacts)
    sync.failed_contact_count = sum(not contact.provider_contact_id for contact in contacts)
    remaining_failures = db.scalar(
        select(func.count())
        .select_from(ProspectingProviderEvent)
        .where(
            ProspectingProviderEvent.provider_campaign_sync_id == sync.id,
            ProspectingProviderEvent.processing_status == "failed",
        )
    )
    sync.status = (
        "needs_attention"
        if sync.failed_contact_count or int(remaining_failures or 0)
        else "reconciled"
    )
    sync.last_reconciled_at = datetime.now(UTC)
    db.commit()
    return campaign_sync_read(db, sync)


def retry_provider_event(
    db: Session,
    principal: Principal,
    event_id: UUID,
) -> DialerProviderEventRead:
    event = db.scalar(
        select(ProspectingProviderEvent).where(
            ProspectingProviderEvent.organization_id == principal.organization_id,
            ProspectingProviderEvent.id == event_id,
        )
    )
    if event is None:
        raise ValueError("Provider event is unavailable.")
    if event.processing_status != "failed":
        raise ValueError("Only failed provider events require retry.")
    event.retry_count += 1
    process_provider_event(db, event, DialerProviderEventCreate.model_validate(event.payload))
    db.commit()
    return provider_event_read(event)


def campaign_sync_read(
    db: Session,
    sync: ProspectingProviderCampaign,
) -> DialerCampaignSyncRead:
    batch = db.get(ProspectCallingBatch, sync.prospect_calling_batch_id)
    events = db.scalars(
        select(ProspectingProviderEvent)
        .where(ProspectingProviderEvent.provider_campaign_sync_id == sync.id)
        .order_by(ProspectingProviderEvent.received_at.desc())
        .limit(20)
    ).all()
    pending = db.scalar(
        select(func.count())
        .select_from(ProspectingProviderEvent)
        .where(
            ProspectingProviderEvent.provider_campaign_sync_id == sync.id,
            ProspectingProviderEvent.processing_status.in_(("received", "needs_review")),
        )
    )
    failed = db.scalar(
        select(func.count())
        .select_from(ProspectingProviderEvent)
        .where(
            ProspectingProviderEvent.provider_campaign_sync_id == sync.id,
            ProspectingProviderEvent.processing_status == "failed",
        )
    )
    return DialerCampaignSyncRead(
        id=sync.id,
        batch_id=sync.prospect_calling_batch_id,
        batch_name=batch.name if batch else "Unknown calling batch",
        provider=sync.provider,
        provider_campaign_id=sync.provider_campaign_id,
        mode=sync.mode,
        status=sync.status,
        eligible_contact_count=sync.eligible_contact_count,
        synced_contact_count=sync.synced_contact_count,
        failed_contact_count=sync.failed_contact_count,
        pending_event_count=int(pending or 0),
        failed_event_count=int(failed or 0),
        retry_count=sync.retry_count,
        error_message=sync.error_message,
        last_synced_at=sync.last_synced_at,
        last_reconciled_at=sync.last_reconciled_at,
        recent_events=[provider_event_read(event) for event in events],
    )


def provider_event_read(event: ProspectingProviderEvent) -> DialerProviderEventRead:
    return DialerProviderEventRead(
        id=event.id,
        external_event_id=event.external_event_id,
        event_type=event.event_type,
        processing_status=event.processing_status,
        provider_call_id=event.provider_call_id,
        provider_recording_id=event.provider_recording_id,
        attempt_id=event.attempt_id,
        retry_count=event.retry_count,
        error_message=event.error_message,
        received_at=event.received_at,
        processed_at=event.processed_at,
    )


def record_provider_suppression(
    db: Session,
    event: ProspectingProviderEvent,
    prospect: Prospect,
    suppressed_at: datetime,
) -> None:
    if not prospect.normalized_phone:
        return
    existing = db.scalar(
        select(SuppressionRecord).where(
            SuppressionRecord.organization_id == event.organization_id,
            SuppressionRecord.channel == "phone",
            SuppressionRecord.normalized_address == prospect.normalized_phone,
        )
    )
    metadata = {
        "prospect_id": str(prospect.id),
        "provider_event_id": event.external_event_id,
    }
    if existing is not None:
        existing.status = "active"
        existing.reason = "Seller requested no further calls"
        existing.source = "dialer_provider_disposition"
        existing.provider = PROVIDER
        existing.external_event_id = event.external_event_id
        existing.suppressed_at = suppressed_at
        existing.lifted_at = None
        existing.suppression_metadata = metadata
        return
    db.add(
        SuppressionRecord(
            organization_id=event.organization_id,
            contact_id=None,
            channel="phone",
            normalized_address=prospect.normalized_phone,
            status="active",
            reason="Seller requested no further calls",
            source="dialer_provider_disposition",
            provider=PROVIDER,
            external_event_id=event.external_event_id,
            suppressed_at=suppressed_at,
            lifted_at=None,
            suppression_metadata=metadata,
        )
    )


def script_for_batch(
    db: Session,
    batch: ProspectCallingBatch,
) -> ProspectingScriptVersion | None:
    if batch.cohort_id is not None:
        cohort = db.get(ProspectingCohort, batch.cohort_id)
        if cohort is not None and cohort.script_version_id is not None:
            script = db.get(ProspectingScriptVersion, cohort.script_version_id)
            if (
                script is not None
                and script.organization_id == batch.organization_id
                and script.status == "approved"
            ):
                return script
            return None
    return get_active_script(db, batch.organization_id)


def scoped_sync(
    db: Session,
    principal: Principal,
    sync_id: UUID,
) -> ProspectingProviderCampaign | None:
    return db.scalar(
        select(ProspectingProviderCampaign).where(
            ProspectingProviderCampaign.organization_id == principal.organization_id,
            ProspectingProviderCampaign.id == sync_id,
        )
    )


def normalize_outcome(value: str | None) -> str:
    normalized = (value or "").strip().lower().replace(" ", "_")
    outcome = NORMALIZED_OUTCOMES.get(normalized)
    if outcome is None:
        raise ValueError(f"Unsupported provider disposition: {value or 'missing'}.")
    return outcome


def verify_webhook_signature(raw_body: bytes, signature: str | None, secret: str | None) -> bool:
    if not signature or not secret:
        return False
    provided = signature.removeprefix("sha256=").strip()
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(provided, expected)


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def add_provider_audit(
    db: Session,
    *,
    organization_id: UUID,
    actor_user_id: UUID,
    action: str,
    entity_type: str,
    entity_id: UUID,
    new: dict[str, object],
    reason: str,
) -> None:
    db.add(
        AuditEvent(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            actor_type="provider",
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            previous_value=None,
            new_value=new,
            reason=reason,
        )
    )


def add_audit(
    db: Session,
    principal: Principal,
    *,
    action: str,
    entity_type: str,
    entity_id: UUID,
    new: dict[str, object],
    reason: str,
) -> None:
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            previous_value=None,
            new_value=new,
            reason=reason,
        )
    )
