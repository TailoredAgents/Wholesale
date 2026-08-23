from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.foundation import (
    BatchDialerAgentIdentity,
    BatchDialerCallFact,
    BatchDialerSyncCheckpoint,
    Organization,
    ProspectingProviderEvent,
)

PROVIDER = "batchdialer"
CALL_EVENT_TYPE = "cdr.observed"
NORMALIZATION_VERSION = "batchdialer_call_fact_v1"
BATCHDIALER_CALL_FACT_BACKFILL_BATCH_SIZE = 250
CALL_FACT_RECONCILIATION_STREAM = "call_facts"
CALL_FACT_RECONCILIATION_INTERVAL = timedelta(minutes=10)
BACKFILL_AUDIT_KEY = "_stonegate_call_fact_normalization"

logger = structlog.get_logger()


@dataclass(frozen=True)
class BatchDialerCallFactBackfillResult:
    scanned: int
    created: int
    updated: int
    skipped: int
    has_more: bool
    first_handled_event_id: UUID | None


def upsert_batchdialer_agent_identity(
    db: Session,
    *,
    organization_id: UUID,
    provider_agent_id: str,
    first_name: str | None,
    last_name: str | None,
    observed_at: datetime,
    provider_snapshot: dict[str, Any] | None = None,
) -> BatchDialerAgentIdentity:
    """Observe a provider agent without ever inferring a Stonegate user mapping."""
    normalized_id = _string(provider_agent_id)
    if not normalized_id:
        raise ValueError("A BatchDialer provider agent ID is required.")
    observed_at = _aware(observed_at)
    identity = db.scalar(
        select(BatchDialerAgentIdentity)
        .where(
            BatchDialerAgentIdentity.organization_id == organization_id,
            BatchDialerAgentIdentity.provider_agent_id == normalized_id,
        )
        .with_for_update(of=BatchDialerAgentIdentity)
    )
    normalized_first = _optional_string(first_name, 255)
    normalized_last = _optional_string(last_name, 255)
    display_name = _optional_string(
        " ".join(value for value in (normalized_first, normalized_last) if value),
        255,
    )
    snapshot = provider_snapshot if isinstance(provider_snapshot, dict) else {}
    if identity is None:
        identity = BatchDialerAgentIdentity(
            organization_id=organization_id,
            provider_agent_id=normalized_id[:255],
            first_name=normalized_first,
            last_name=normalized_last,
            display_name=display_name,
            mapped_user_id=None,
            mapped_by_user_id=None,
            mapped_at=None,
            first_seen_at=observed_at,
            last_seen_at=observed_at,
            provider_snapshot=snapshot,
        )
        db.add(identity)
        db.flush()
        return identity

    if normalized_first:
        identity.first_name = normalized_first
    if normalized_last:
        identity.last_name = normalized_last
    if display_name:
        identity.display_name = display_name
    identity.first_seen_at = min(_aware(identity.first_seen_at), observed_at)
    identity.last_seen_at = max(_aware(identity.last_seen_at), observed_at)
    if snapshot:
        identity.provider_snapshot = snapshot
    # mapped_user_id is intentionally untouched. Provider observations are never
    # allowed to guess identity from a similar name or email address.
    return identity


def upsert_batchdialer_call_fact(
    db: Session,
    *,
    event: ProspectingProviderEvent,
    disposition_classification: str | None = None,
    final_result: dict[str, Any] | None = None,
) -> BatchDialerCallFact | None:
    """Normalize one archived provider event into a revision-safe call fact."""
    if event.provider != PROVIDER or event.event_type != CALL_EVENT_TYPE:
        return None
    payload = event.payload if isinstance(event.payload, dict) else {}
    cdr = payload.get("cdr")
    if not isinstance(cdr, dict):
        return None
    provider_cdr_id = _string(cdr.get("id"))
    if not provider_cdr_id:
        return None

    raw_agent = cdr.get("agent")
    raw_contact = cdr.get("contact")
    raw_campaign = cdr.get("campaign")
    agent: dict[str, Any] = raw_agent if isinstance(raw_agent, dict) else {}
    contact: dict[str, Any] = raw_contact if isinstance(raw_contact, dict) else {}
    campaign: dict[str, Any] = raw_campaign if isinstance(raw_campaign, dict) else {}
    provider_agent_id = _optional_string(agent.get("id"), 255)
    agent_first_name = _optional_string(agent.get("firstname"), 255)
    agent_last_name = _optional_string(agent.get("lastname"), 255)
    provider_agent_name = _optional_string(
        " ".join(
            value for value in (agent_first_name, agent_last_name) if value
        ),
        255,
    )
    observed_at = _aware(event.occurred_at or event.received_at)
    agent_identity = None
    if provider_agent_id:
        agent_identity = upsert_batchdialer_agent_identity(
            db,
            organization_id=event.organization_id,
            provider_agent_id=provider_agent_id,
            first_name=agent_first_name,
            last_name=agent_last_name,
            observed_at=observed_at,
            provider_snapshot=agent,
        )

    fact = db.scalar(
        select(BatchDialerCallFact)
        .where(BatchDialerCallFact.provider_event_id == event.id)
        .with_for_update(of=BatchDialerCallFact)
    )
    if fact is None:
        fact = BatchDialerCallFact(
            organization_id=event.organization_id,
            provider_event_id=event.id,
            provider_cdr_id=provider_cdr_id[:255],
            received_at=_aware(event.received_at),
        )
        db.add(fact)

    stored_result = payload.get("_stonegate")
    stored_result = stored_result if isinstance(stored_result, dict) else {}
    result = final_result if isinstance(final_result, dict) else stored_result
    result_is_current = final_result is not None or _stored_result_is_current(event, result)
    qualification = result.get("qualification")
    qualification = qualification if isinstance(qualification, dict) else {}

    started_at = _parse_datetime(cdr.get("callStartTime"))
    ended_at = _parse_datetime(cdr.get("callEndTime"))
    duration_seconds = _nonnegative_int(cdr.get("duration"))
    if duration_seconds is None and started_at is not None and ended_at is not None:
        duration_seconds = max(0, int((ended_at - started_at).total_seconds()))
    normalized_classification = disposition_classification or (
        _classify_archived_disposition(cdr.get("disposition"))
    )
    transcript_status = (
        _optional_string(result.get("transcript_status"), 80)
        if result_is_current
        else None
    )
    transcript_sha256 = _string(qualification.get("transcript_sha256"))
    evidence_excerpts = qualification.get("evidence_excerpts")
    evidence_present = bool(
        transcript_sha256
        or (isinstance(evidence_excerpts, list) and evidence_excerpts)
    )
    final_outcome = (
        _optional_string(result.get("outcome"), 80) if result_is_current else None
    )
    qualification_status = (
        _optional_string(result.get("qualification_status"), 80)
        or _optional_string(qualification.get("status"), 80)
        if result_is_current
        else None
    )
    if result_is_current and not qualification_status:
        if final_outcome == "ignored":
            qualification_status = "not_candidate"
        elif final_outcome == "needs_review":
            qualification_status = "needs_review"
        elif final_outcome == "awaiting_qualification_evidence":
            qualification_status = "pending"
        elif final_outcome == "review_rejected":
            qualification_status = "rejected_by_human"

    lead_id = _uuid_or_none(result.get("lead_id"))
    call_record_id = _uuid_or_none(result.get("call_record_id"))
    if not result_is_current and fact.id is not None:
        lead_id = lead_id or fact.lead_id
        call_record_id = call_record_id or fact.call_record_id

    fact.organization_id = event.organization_id
    fact.provider_event_id = event.id
    fact.agent_identity_id = agent_identity.id if agent_identity is not None else None
    fact.lead_id = lead_id
    fact.call_record_id = call_record_id
    fact.provider_cdr_id = provider_cdr_id[:255]
    fact.provider_call_id = _optional_string(cdr.get("callid"), 255) or (
        _optional_string(event.provider_call_id, 255)
    )
    fact.provider_contact_id = _optional_string(contact.get("id"), 255)
    fact.provider_campaign_id = _optional_string(campaign.get("id"), 255)
    fact.provider_campaign_name = _optional_string(campaign.get("name"), 255)
    fact.provider_agent_id = provider_agent_id
    fact.provider_agent_name = provider_agent_name
    fact.occurred_at = _aware(event.occurred_at) if event.occurred_at else None
    fact.started_at = started_at
    fact.ended_at = ended_at
    fact.received_at = _aware(event.received_at)
    fact.processed_at = _aware(event.processed_at) if event.processed_at else None
    fact.duration_seconds = duration_seconds
    fact.direction = _normalize_direction(cdr.get("direction"))
    fact.provider_status = _optional_string(cdr.get("status"), 80)
    fact.raw_disposition = _optional_string(cdr.get("disposition"), 255)
    fact.disposition_classification = normalized_classification[:40]
    fact.final_outcome = final_outcome
    fact.final_qualification_status = qualification_status
    fact.mood = _optional_string(cdr.get("mood"), 80)
    fact.is_voicemail = _is_voicemail(cdr)
    fact.recording_available = bool(
        _string(cdr.get("callRecordUrl"))
        or _truthy(cdr.get("recordingenabled"))
        or event.provider_recording_id
    )
    fact.transcript_status = transcript_status
    fact.transcript_available = bool(
        transcript_sha256
        or transcript_status in {"available", "completed", "processed"}
    )
    fact.qualification_evidence_present = evidence_present
    fact.lead_created_by_event = bool(result.get("created_lead"))
    fact.source_payload_sha256 = event.payload_sha256
    fact.normalization_version = NORMALIZATION_VERSION
    fact.final_processing_status = event.processing_status
    db.flush()
    return fact


def backfill_batchdialer_call_facts(
    db: Session,
    *,
    organization_id: UUID | None = None,
    limit: int = 1_000,
) -> BatchDialerCallFactBackfillResult:
    """Idempotently normalize a bounded page of missing or stale archived CDRs."""
    if not 1 <= limit <= 10_000:
        raise ValueError("BatchDialer call-fact backfill limit must be between 1 and 10000.")
    skip_status = ProspectingProviderEvent.payload[
        (BACKFILL_AUDIT_KEY, "status")
    ].as_string()
    skip_version = ProspectingProviderEvent.payload[
        (BACKFILL_AUDIT_KEY, "normalization_version")
    ].as_string()
    skip_source_hash = ProspectingProviderEvent.payload[
        (BACKFILL_AUDIT_KEY, "source_payload_sha256")
    ].as_string()
    missing_fact_is_eligible = and_(
        BatchDialerCallFact.id.is_(None),
        or_(
            skip_status.is_(None),
            skip_status != "skipped",
            skip_version.is_(None),
            skip_version != NORMALIZATION_VERSION,
            func.coalesce(skip_source_hash, "")
            != func.coalesce(ProspectingProviderEvent.payload_sha256, ""),
        ),
    )
    existing_fact_is_stale = and_(
        BatchDialerCallFact.id.is_not(None),
        or_(
            BatchDialerCallFact.normalization_version != NORMALIZATION_VERSION,
            func.coalesce(BatchDialerCallFact.source_payload_sha256, "")
            != func.coalesce(ProspectingProviderEvent.payload_sha256, ""),
            BatchDialerCallFact.final_processing_status
            != ProspectingProviderEvent.processing_status,
        ),
    )
    statement = (
        select(ProspectingProviderEvent, BatchDialerCallFact.id)
        .outerjoin(
            BatchDialerCallFact,
            BatchDialerCallFact.provider_event_id == ProspectingProviderEvent.id,
        )
        .where(
            ProspectingProviderEvent.provider == PROVIDER,
            ProspectingProviderEvent.event_type == CALL_EVENT_TYPE,
            or_(
                missing_fact_is_eligible,
                existing_fact_is_stale,
            ),
        )
        .order_by(
            ProspectingProviderEvent.received_at,
            ProspectingProviderEvent.id,
        )
        .limit(limit)
    )
    if organization_id is not None:
        statement = statement.where(
            ProspectingProviderEvent.organization_id == organization_id
    )
    rows = db.execute(statement).all()
    created = updated = skipped = 0
    first_handled_event_id: UUID | None = None
    for event, existing_fact_id in rows:
        first_handled_event_id = first_handled_event_id or event.id
        fact = upsert_batchdialer_call_fact(event=event, db=db)
        if fact is None:
            skipped += 1
            _record_backfill_skip(event)
        elif existing_fact_id is None:
            created += 1
        else:
            updated += 1
    return BatchDialerCallFactBackfillResult(
        scanned=len(rows),
        created=created,
        updated=updated,
        skipped=skipped,
        has_more=len(rows) == limit,
        first_handled_event_id=first_handled_event_id,
    )


def backfill_next_batchdialer_call_fact_batch(
    db: Session,
    _settings: Settings,
) -> UUID | None:
    """Backfill one bounded batch and yield so the worker can service every queue.

    Returning a processed provider-event ID tells the worker to begin another full
    operation cycle immediately. This steadily drains migration-era history without
    delaying live lead, messaging, or call-intelligence work.
    """
    now = datetime.now(UTC)
    checkpoint = _acquire_call_fact_reconciliation_checkpoint(db, now=now)
    if checkpoint is None:
        return None
    checkpoint_id = checkpoint.id
    organization_id = checkpoint.organization_id
    # Persist the claim before touching tenant history. If normalization fails,
    # its transaction can roll back without erasing the tenant-specific backoff.
    checkpoint.next_poll_at = now + CALL_FACT_RECONCILIATION_INTERVAL
    db.commit()
    try:
        result = backfill_batchdialer_call_facts(
            db,
            organization_id=organization_id,
            limit=BATCHDIALER_CALL_FACT_BACKFILL_BATCH_SIZE,
        )
    except Exception as exc:
        db.rollback()
        _record_call_fact_reconciliation_failure(
            db,
            checkpoint_id=checkpoint_id,
            now=now,
            error=exc,
        )
        raise
    checkpoint = db.scalar(
        select(BatchDialerSyncCheckpoint)
        .where(BatchDialerSyncCheckpoint.id == checkpoint_id)
        .with_for_update()
    )
    if checkpoint is None:
        db.rollback()
        raise RuntimeError("The BatchDialer call-fact reconciliation checkpoint was removed.")
    checkpoint.status = "idle"
    checkpoint.last_success_at = now
    checkpoint.success_count += 1
    checkpoint.consecutive_failure_count = 0
    checkpoint.last_error = None
    checkpoint.next_poll_at = (
        now if result.has_more else now + CALL_FACT_RECONCILIATION_INTERVAL
    )
    checkpoint.sync_metadata = {
        **(checkpoint.sync_metadata or {}),
        "last_reconciliation": {
            "scanned": result.scanned,
            "created": result.created,
            "updated": result.updated,
            "skipped": result.skipped,
            "has_more": result.has_more,
            "completed_at": now.isoformat(),
        },
    }
    db.commit()
    if result.scanned:
        logger.info(
            "batchdialer_call_fact_backfill_completed",
            scanned=result.scanned,
            created=result.created,
            updated=result.updated,
            skipped=result.skipped,
            has_more=result.has_more,
            organization_id=str(checkpoint.organization_id),
            next_reconciliation_at=checkpoint.next_poll_at,
        )
    return result.first_handled_event_id


def _record_call_fact_reconciliation_failure(
    db: Session,
    *,
    checkpoint_id: UUID,
    now: datetime,
    error: Exception,
) -> None:
    checkpoint = db.scalar(
        select(BatchDialerSyncCheckpoint)
        .where(BatchDialerSyncCheckpoint.id == checkpoint_id)
        .with_for_update()
    )
    if checkpoint is None:
        db.rollback()
        return
    error_message = str(error).strip() or error.__class__.__name__
    checkpoint.status = "error"
    checkpoint.last_error = error_message[:4_000]
    checkpoint.consecutive_failure_count += 1
    checkpoint.failure_count += 1
    checkpoint.next_poll_at = now + CALL_FACT_RECONCILIATION_INTERVAL
    checkpoint.sync_metadata = {
        **(checkpoint.sync_metadata or {}),
        "last_reconciliation_failure": {
            "error_type": error.__class__.__name__,
            "error_message": error_message[:1_000],
            "failed_at": now.isoformat(),
        },
    }
    db.commit()
    logger.exception(
        "batchdialer_call_fact_backfill_failed",
        checkpoint_id=str(checkpoint.id),
        organization_id=str(checkpoint.organization_id),
        next_reconciliation_at=checkpoint.next_poll_at,
    )


def _acquire_call_fact_reconciliation_checkpoint(
    db: Session,
    *,
    now: datetime,
) -> BatchDialerSyncCheckpoint | None:
    """Acquire one due tenant checkpoint without allowing a tenant to monopolize repair."""
    checkpoint_exists = (
        select(BatchDialerSyncCheckpoint.id)
        .where(
            BatchDialerSyncCheckpoint.organization_id == Organization.id,
            BatchDialerSyncCheckpoint.stream == CALL_FACT_RECONCILIATION_STREAM,
        )
        .exists()
    )
    missing_checkpoint_organization_id = db.scalar(
        select(Organization.id)
        .where(~checkpoint_exists)
        .order_by(Organization.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if missing_checkpoint_organization_id is not None:
        checkpoint = BatchDialerSyncCheckpoint(
            organization_id=missing_checkpoint_organization_id,
            stream=CALL_FACT_RECONCILIATION_STREAM,
            status="idle",
            sync_metadata={},
        )
        db.add(checkpoint)
        db.flush()
    else:
        checkpoint = db.scalar(
            select(BatchDialerSyncCheckpoint)
            .where(
                BatchDialerSyncCheckpoint.stream == CALL_FACT_RECONCILIATION_STREAM,
                or_(
                    BatchDialerSyncCheckpoint.next_poll_at.is_(None),
                    BatchDialerSyncCheckpoint.next_poll_at <= now,
                ),
            )
            .order_by(
                BatchDialerSyncCheckpoint.next_poll_at.asc().nulls_first(),
                BatchDialerSyncCheckpoint.last_attempt_at.asc().nulls_first(),
                BatchDialerSyncCheckpoint.organization_id,
            )
            .with_for_update(skip_locked=True)
            .limit(1)
        )
    if checkpoint is None:
        return None
    checkpoint.status = "polling"
    checkpoint.last_attempt_at = now
    checkpoint.poll_count += 1
    checkpoint.last_error = None
    return checkpoint


def _record_backfill_skip(event: ProspectingProviderEvent) -> None:
    """Persist why an immutable provider event could not become an analytics fact."""
    payload = event.payload if isinstance(event.payload, dict) else {}
    cdr = payload.get("cdr")
    if not isinstance(cdr, dict):
        reason = "cdr_payload_missing_or_invalid"
    elif not _string(cdr.get("id")):
        reason = "provider_cdr_id_missing"
    else:
        reason = "unsupported_cdr_payload"
    event.payload = {
        **payload,
        BACKFILL_AUDIT_KEY: {
            "status": "skipped",
            "reason": reason,
            "normalization_version": NORMALIZATION_VERSION,
            "source_payload_sha256": event.payload_sha256 or "",
            "recorded_at": datetime.now(UTC).isoformat(),
        },
    }
    logger.warning(
        "batchdialer_call_fact_backfill_skipped",
        provider_event_id=str(event.id),
        external_event_id=event.external_event_id,
        reason=reason,
        source_payload_sha256=event.payload_sha256,
    )


def _stored_result_is_current(
    event: ProspectingProviderEvent,
    result: dict[str, Any],
) -> bool:
    if not result:
        return False
    qualification = result.get("qualification")
    qualification = qualification if isinstance(qualification, dict) else {}
    source_hash = _string(qualification.get("source_payload_sha256"))
    if source_hash:
        return source_hash == _string(event.payload_sha256)
    return not (
        event.processing_status in {"pending", "processing"}
        and event.processed_at is None
    )


def _classify_archived_disposition(value: object) -> str:
    # Import lazily so the direct-ingestion module can use this normalizer without
    # introducing a module initialization cycle.
    from app.services.batchdialer_direct import classify_disposition

    return str(classify_disposition(value))


def _is_voicemail(cdr: dict[str, Any]) -> bool:
    voicemail_id = _string(cdr.get("voicemailid")).casefold()
    if voicemail_id and voicemail_id not in {"0", "false", "none", "null"}:
        return True
    disposition = _string(cdr.get("disposition")).casefold()
    return "voicemail" in disposition or "answering machine" in disposition


def _normalize_direction(value: object) -> str:
    return "inbound" if _string(value).casefold() in {"in", "inbound"} else "outbound"


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
    return _aware(parsed)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _nonnegative_int(value: object) -> int | None:
    if value is None or isinstance(value, (dict, list, tuple, set)):
        return None
    if not isinstance(value, (bool, int, float, str, bytes, bytearray)):
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return _string(value).casefold() in {"1", "true", "yes", "enabled"}


def _uuid_or_none(value: object) -> UUID | None:
    try:
        return UUID(_string(value)) if _string(value) else None
    except ValueError:
        return None


def _optional_string(value: object, max_length: int) -> str | None:
    normalized = _string(value)
    return normalized[:max_length] if normalized else None


def _string(value: object) -> str:
    if value is None or isinstance(value, (dict, list, tuple, set)):
        return ""
    return str(value).strip()
