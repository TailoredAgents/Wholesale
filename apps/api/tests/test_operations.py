import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.foundation import OperationalFailure, WorkerHeartbeat
from app.services.operations import (
    COMMUNICATIONS_WORKER,
    get_worker_readiness,
    mark_worker_operation_started,
    operation_retry_due,
    record_operation_failure,
    record_worker_heartbeat,
    register_worker,
    resolve_operation_failures,
    touch_worker_heartbeat,
)


def settings(
    *,
    required: bool = True,
    stale_after: int = 120,
    operation_stall_after: int = 600,
) -> Settings:
    return Settings.model_validate(
        {
            "APP_ENV": "local",
            "WORKER_READINESS_REQUIRED": required,
            "WORKER_STALE_AFTER_SECONDS": stale_after,
            "WORKER_OPERATION_STALL_SECONDS": operation_stall_after,
        }
    )


def test_worker_heartbeat_reports_healthy_and_stale(db_session: Session) -> None:
    register_worker(db_session)
    record_worker_heartbeat(db_session)

    healthy = get_worker_readiness(db_session, settings())

    assert healthy.status == "healthy"
    assert healthy.required is True
    heartbeat = db_session.query(WorkerHeartbeat).one()
    heartbeat.heartbeat_at = datetime.now(UTC) - timedelta(minutes=10)
    db_session.commit()

    stale = get_worker_readiness(db_session, settings(stale_after=60))

    assert stale.status == "stale"


def test_operation_failures_are_grouped_and_resolved(db_session: Session) -> None:
    register_worker(db_session)

    first = record_operation_failure(
        db_session,
        service_name=COMMUNICATIONS_WORKER,
        operation_name="email_sync",
        error=RuntimeError("provider unavailable"),
    )
    second = record_operation_failure(
        db_session,
        service_name=COMMUNICATIONS_WORKER,
        operation_name="email_sync",
        error=RuntimeError("provider unavailable"),
    )

    assert second.id == first.id
    assert second.attempt_count == 2
    assert (
        operation_retry_due(
            db_session,
            service_name=COMMUNICATIONS_WORKER,
            operation_name="email_sync",
        )
        is False
    )
    assert db_session.query(OperationalFailure).count() == 1
    heartbeat = db_session.query(WorkerHeartbeat).one()
    assert heartbeat.status == "degraded"
    assert heartbeat.consecutive_failures == 2
    assert heartbeat.total_failures == 2

    resolve_operation_failures(
        db_session,
        service_name=COMMUNICATIONS_WORKER,
        operation_name="email_sync",
    )

    db_session.refresh(second)
    assert second.status == "resolved"
    assert second.resolved_at is not None


def test_liveness_touch_preserves_degraded_worker_state(db_session: Session) -> None:
    register_worker(db_session)
    failure = record_operation_failure(
        db_session,
        service_name=COMMUNICATIONS_WORKER,
        operation_name="call_transcription",
        error=RuntimeError("provider unavailable"),
    )
    heartbeat = db_session.query(WorkerHeartbeat).one()
    original_heartbeat_at = heartbeat.heartbeat_at

    touch_worker_heartbeat(db_session)

    db_session.refresh(heartbeat)
    assert heartbeat.heartbeat_at >= original_heartbeat_at
    assert heartbeat.status == "degraded"
    assert heartbeat.consecutive_failures == 1
    assert failure.status == "open"


def test_liveness_touch_does_not_hide_a_stalled_main_loop(db_session: Session) -> None:
    register_worker(db_session)
    record_worker_heartbeat(db_session)
    mark_worker_operation_started(db_session, "call_transcription")
    heartbeat = db_session.query(WorkerHeartbeat).one()
    heartbeat.worker_metadata = {
        **(heartbeat.worker_metadata or {}),
        "main_loop_progress_at": (datetime.now(UTC) - timedelta(minutes=20)).isoformat(),
        "operation_started_at": (datetime.now(UTC) - timedelta(minutes=20)).isoformat(),
    }
    db_session.commit()

    touch_worker_heartbeat(db_session)
    stalled = get_worker_readiness(db_session, settings(stale_after=60))

    assert stalled.status == "stalled"
    assert stalled.current_operation == "call_transcription"


def test_long_bounded_provider_call_does_not_trigger_liveness_stale_window(
    db_session: Session,
) -> None:
    register_worker(db_session)
    record_worker_heartbeat(db_session)
    mark_worker_operation_started(db_session, "call_transcription")
    heartbeat = db_session.query(WorkerHeartbeat).one()
    heartbeat.worker_metadata = {
        **(heartbeat.worker_metadata or {}),
        "main_loop_progress_at": (datetime.now(UTC) - timedelta(minutes=3)).isoformat(),
        "operation_started_at": (datetime.now(UTC) - timedelta(minutes=3)).isoformat(),
    }
    db_session.commit()

    touch_worker_heartbeat(db_session)
    readiness = get_worker_readiness(
        db_session,
        settings(stale_after=60, operation_stall_after=600),
    )

    assert readiness.status == "healthy"
    assert readiness.current_operation == "call_transcription"


def test_render_worker_keeps_critical_provider_configuration_in_sync() -> None:
    blueprint = (Path(__file__).resolve().parents[3] / "render.yaml").read_text(
        encoding="utf-8"
    )
    api_keys = render_service_environment_keys(blueprint, "oakwell-api")
    worker_keys = render_service_environment_keys(blueprint, "oakwell-worker")
    shared_runtime_keys = {
        "AI_ENABLED",
        "CALL_TRANSCRIPTION_ENABLED",
        "CALL_TRANSCRIPTION_MAX_ATTEMPTS",
        "COMMUNICATION_PROVIDER_MODE",
        "DATABASE_URL",
        "EMAIL_ENABLED",
        "EMAIL_PROVIDER",
        "EMAIL_SYNC_ENABLED",
        "FACEBOOK_ADDRESS_ENRICHMENT_MAX_ATTEMPTS",
        "FACEBOOK_LEAD_INTAKE_MAX_ATTEMPTS",
        "MARKETING_CONVERSION_MODE",
        "META_CONVERSIONS_ACCESS_TOKEN",
        "META_PIXEL_ID",
        "OPENAI_API_KEY",
        "OPENAI_DEFAULT_MODEL",
        "OPENAI_TRANSCRIPTION_MODEL",
        "PROPERTY_DATA_PROVIDER",
        "PROPERTY_INTELLIGENCE_AUTO_RESEARCH_ENABLED",
        "REALESTATEAPI_API_KEY",
        "REALESTATEAPI_BASE_URL",
        "RENTCAST_API_KEY",
        "RENTCAST_BASE_URL",
        "RESEND_API_KEY",
        "RESEND_EVENT_MAX_ATTEMPTS",
        "RESEND_EVENT_PROCESSING_LEASE_SECONDS",
        "RESEND_EVENT_RETRY_BASE_SECONDS",
        "RESEND_EVENT_RETRY_MAX_SECONDS",
        "STAFF_LEAD_ALERT_SMS_MODE",
        "TWILIO_ACCOUNT_SID",
        "TWILIO_AUTH_TOKEN",
        "TWILIO_SMS_ENABLED",
        "TWILIO_SMS_FROM_NUMBER",
        "UNDERWRITING_DEALMACHINE_COMPS_MODE",
        "UNDERWRITING_REALESTATEAPI_COMPS_MODE",
        "WORKER_OPERATION_STALL_SECONDS",
        "ZAPIER_FACEBOOK_LEADS_ENABLED",
        "ZAPIER_FACEBOOK_PAGE_ID",
    }

    assert shared_runtime_keys <= api_keys
    assert shared_runtime_keys <= worker_keys


def render_service_environment_keys(blueprint: str, service_name: str) -> set[str]:
    marker = f"    name: {service_name}"
    assert marker in blueprint
    service_block = blueprint.split(marker, 1)[1].split("\n  - type:", 1)[0]
    return set(re.findall(r"(?m)^\s+- key: ([A-Z0-9_]+)\s*$", service_block))
