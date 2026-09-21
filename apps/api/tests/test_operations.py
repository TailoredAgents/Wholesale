import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.foundation import OperationalFailure, WorkerHeartbeat
from app.services.operations import (
    COMMUNICATIONS_WORKER,
    get_worker_operational_health,
    get_worker_readiness,
    mark_worker_operation_finished,
    mark_worker_operation_started,
    operation_retry_due,
    record_operation_failure,
    record_worker_heartbeat,
    register_worker,
    resolve_operation_failures,
    resolve_retired_operation_failures,
    safe_meta_runtime_metadata,
    touch_worker_heartbeat,
    touch_worker_operation_progress,
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


def test_worker_heartbeat_persists_safe_meta_runtime_readiness(
    db_session: Session,
) -> None:
    sentinel_token = "SENTINEL-WORKER-TOKEN-MUST-NOT-LEAK"
    runtime_settings = Settings.model_validate(
        {
            "MARKETING_CONVERSION_MODE": "live",
            "META_PIXEL_ID": "2118209559079623",
            "META_CONVERSIONS_ACCESS_TOKEN": sentinel_token,
            "META_TEST_EVENT_CODE": "SENTINEL-TEST-CODE-MUST-NOT-LEAK",
        }
    )
    metadata = safe_meta_runtime_metadata(runtime_settings)

    register_worker(db_session, runtime_metadata=metadata)
    record_worker_heartbeat(db_session)
    heartbeat = db_session.query(WorkerHeartbeat).one()

    assert heartbeat.worker_metadata is not None
    assert heartbeat.worker_metadata["runtime_metadata_schema_version"] == 1
    assert heartbeat.worker_metadata["marketing_conversion_mode"] == "live"
    assert heartbeat.worker_metadata["meta_configured"] is True
    assert heartbeat.worker_metadata["meta_access_token_present"] is True
    assert heartbeat.worker_metadata["meta_test_mode_enabled"] is True
    assert heartbeat.worker_metadata["zapier_facebook_leads_enabled"] is False
    assert len(str(heartbeat.worker_metadata["meta_pixel_id_fingerprint"])) == 10
    serialized = str(heartbeat.worker_metadata)
    assert "2118209559079623" not in serialized
    assert sentinel_token not in serialized
    assert "SENTINEL-TEST-CODE-MUST-NOT-LEAK" not in serialized


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


def test_retired_operation_failures_are_closed_without_hiding_active_failures(
    db_session: Session,
) -> None:
    register_worker(db_session)
    retired = record_operation_failure(
        db_session,
        service_name=COMMUNICATIONS_WORKER,
        operation_name="batchdialer_zapier",
        error=RuntimeError("retired provider path failed"),
    )
    active = record_operation_failure(
        db_session,
        service_name=COMMUNICATIONS_WORKER,
        operation_name="email_sync",
        error=RuntimeError("active provider path failed"),
    )

    resolved = resolve_retired_operation_failures(db_session, {"email_sync"})

    db_session.refresh(retired)
    db_session.refresh(active)
    assert resolved == 1
    assert retired.status == "resolved"
    assert retired.resolved_at is not None
    assert retired.failure_metadata == {"resolution_reason": "operation_retired"}
    assert active.status == "open"


def test_long_operation_can_refresh_main_loop_progress(db_session: Session) -> None:
    register_worker(db_session)
    mark_worker_operation_started(db_session, "batchdialer_direct_poll")
    heartbeat = db_session.query(WorkerHeartbeat).one()
    heartbeat.worker_metadata = {
        **(heartbeat.worker_metadata or {}),
        "main_loop_progress_at": (datetime.now(UTC) - timedelta(minutes=20)).isoformat(),
    }
    db_session.commit()

    touch_worker_operation_progress(db_session, "batchdialer_direct_poll")

    db_session.refresh(heartbeat)
    progress_at = datetime.fromisoformat(
        str((heartbeat.worker_metadata or {})["main_loop_progress_at"])
    )
    assert progress_at > datetime.now(UTC) - timedelta(seconds=5)


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


def test_operation_metrics_are_bounded_and_low_cardinality(db_session: Session) -> None:
    register_worker(db_session)
    mark_worker_operation_started(db_session, "email_sync")

    mark_worker_operation_finished(
        db_session,
        "email_sync",
        outcome="processed",
        duration_ms=125,
    )

    heartbeat = db_session.query(WorkerHeartbeat).one()
    metrics = (heartbeat.worker_metadata or {})["operation_metrics"]
    assert metrics == {
        "email_sync": {
            "last_outcome": "processed",
            "last_duration_ms": 125,
            "last_finished_at": metrics["email_sync"]["last_finished_at"],
        }
    }
    health = get_worker_operational_health(db_session, settings())
    operation = next(item for item in health.operations if item.operation_name == "email_sync")
    assert operation.last_outcome == "processed"
    assert operation.last_duration_ms == 125
    assert operation.last_finished_at is not None
    assert operation.open_failure_depth == 0


def test_configuration_only_provider_health_is_reported_as_configured(
    db_session: Session,
) -> None:
    runtime_settings = Settings.model_validate(
        {
            "APP_ENV": "production",
            "WORKER_READINESS_REQUIRED": False,
            "BATCHDIALER_API_KEY": "configured-api-key-value",
            "ZAPIER_FACEBOOK_LEADS_ENABLED": True,
            "ZAPIER_FACEBOOK_PAGE_ID": "123456789",
            "ZAPIER_FACEBOOK_ALLOWED_FORM_IDS": "form-123",
        }
    )

    health = get_worker_operational_health(db_session, runtime_settings)
    providers = {provider.provider_name: provider for provider in health.providers}

    assert providers["batchdialer"].status == "configured"
    assert providers["zapier_facebook_leads"].status == "configured"


def test_provider_health_uses_worker_runtime_configuration(
    db_session: Session,
) -> None:
    api_settings = Settings.model_validate(
        {
            "APP_ENV": "production",
            "WORKER_READINESS_REQUIRED": True,
            "BATCHDIALER_API_KEY": "configured-api-key-value",
            "ZAPIER_FACEBOOK_LEADS_ENABLED": True,
            "ZAPIER_FACEBOOK_PAGE_ID": "123456789",
            "ZAPIER_FACEBOOK_ALLOWED_FORM_IDS": "form-123",
        }
    )
    worker_settings = Settings.model_validate(
        {
            "APP_ENV": "production",
            "WORKER_READINESS_REQUIRED": True,
            "ZAPIER_FACEBOOK_LEADS_ENABLED": False,
        }
    )
    register_worker(
        db_session,
        runtime_metadata=safe_meta_runtime_metadata(worker_settings),
    )
    record_worker_heartbeat(db_session)

    health = get_worker_operational_health(db_session, api_settings)
    providers = {provider.provider_name: provider for provider in health.providers}

    assert health.status == "degraded"
    assert providers["batchdialer"].status == "not_configured"
    assert providers["batchdialer"].configuration_blockers == ("BATCHDIALER_API_KEY",)
    assert providers["zapier_facebook_leads"].status == "degraded"
    assert providers["zapier_facebook_leads"].configuration_blockers == (
        "worker:ZAPIER_FACEBOOK_LEADS_ENABLED=true",
    )


def test_required_worker_with_legacy_runtime_metadata_degrades_provider_truth(
    db_session: Session,
) -> None:
    api_settings = Settings.model_validate(
        {
            "APP_ENV": "production",
            "WORKER_READINESS_REQUIRED": True,
            "BATCHDIALER_API_KEY": "configured-api-key-value",
            "ZAPIER_FACEBOOK_LEADS_ENABLED": True,
            "ZAPIER_FACEBOOK_PAGE_ID": "123456789",
            "ZAPIER_FACEBOOK_ALLOWED_FORM_IDS": "form-123",
        }
    )
    register_worker(db_session, runtime_metadata={})
    record_worker_heartbeat(db_session)

    health = get_worker_operational_health(db_session, api_settings)
    providers = {provider.provider_name: provider for provider in health.providers}

    assert health.status == "degraded"
    for provider_name in ("batchdialer", "zapier_facebook_leads"):
        assert providers[provider_name].status == "degraded"
        assert "worker:runtime_metadata_schema_version=1" in (
            providers[provider_name].configuration_blockers
        )


def test_provider_health_detects_worker_enabled_while_api_ingress_is_disabled(
    db_session: Session,
) -> None:
    api_settings = Settings.model_validate(
        {
            "APP_ENV": "production",
            "WORKER_READINESS_REQUIRED": True,
            "ZAPIER_FACEBOOK_LEADS_ENABLED": False,
        }
    )
    worker_settings = Settings.model_validate(
        {
            "APP_ENV": "production",
            "WORKER_READINESS_REQUIRED": True,
            "ZAPIER_FACEBOOK_LEADS_ENABLED": True,
        }
    )
    register_worker(
        db_session,
        runtime_metadata=safe_meta_runtime_metadata(worker_settings),
    )
    record_worker_heartbeat(db_session)

    health = get_worker_operational_health(db_session, api_settings)
    providers = {provider.provider_name: provider for provider in health.providers}

    assert health.status == "degraded"
    assert providers["zapier_facebook_leads"].status == "degraded"
    assert providers["zapier_facebook_leads"].configuration_blockers == (
        "api:ZAPIER_FACEBOOK_LEADS_ENABLED=true",
    )


def test_zapier_provider_reports_open_meta_lead_worker_failures(
    db_session: Session,
) -> None:
    runtime_settings = Settings.model_validate(
        {
            "APP_ENV": "production",
            "WORKER_READINESS_REQUIRED": True,
            "ZAPIER_FACEBOOK_LEADS_ENABLED": True,
            "ZAPIER_FACEBOOK_PAGE_ID": "123456789",
            "ZAPIER_FACEBOOK_ALLOWED_FORM_IDS": "form-123",
        }
    )
    register_worker(
        db_session,
        runtime_metadata=safe_meta_runtime_metadata(runtime_settings),
    )
    record_worker_heartbeat(db_session)
    record_operation_failure(
        db_session,
        service_name=COMMUNICATIONS_WORKER,
        operation_name="meta_lead_ads",
        error=RuntimeError("lead processor unavailable"),
    )

    health = get_worker_operational_health(db_session, runtime_settings)
    providers = {provider.provider_name: provider for provider in health.providers}

    assert health.status == "degraded"
    assert providers["zapier_facebook_leads"].status == "degraded"
    assert providers["zapier_facebook_leads"].open_failure_depth == 1
    assert providers["zapier_facebook_leads"].oldest_open_failure_age_seconds is not None


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
    blueprint = (Path(__file__).resolve().parents[3] / "render.yaml").read_text(encoding="utf-8")
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
        "OPENAI_WEB_SEARCH_ENABLED",
        "PROSPECTING_NATIVE_DIALER_ENABLED",
        "PROSPECTING_NATIVE_DIALER_MAX_LINES",
        "PROPERTY_DATA_PROVIDER",
        "PROPERTY_INTELLIGENCE_AUTO_RESEARCH_ENABLED",
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
    }

    assert shared_runtime_keys <= api_keys
    assert shared_runtime_keys <= worker_keys
    assert {
        "TWILIO_API_KEY_SID",
        "TWILIO_API_KEY_SECRET",
        "TWILIO_TWIML_APP_SID",
    } <= api_keys
    api_values = render_service_environment_values(blueprint, "oakwell-api")
    worker_values = render_service_environment_values(blueprint, "oakwell-worker")
    for service_values in (api_values, worker_values):
        assert service_values["PROSPECTING_NATIVE_DIALER_ENABLED"] == "false"
        assert service_values["PROSPECTING_NATIVE_DIALER_MAX_LINES"] == "1"
        assert service_values["PROPERTY_DATA_PROVIDER"] == "public_web"
        assert service_values["OPENAI_WEB_SEARCH_ENABLED"] == "true"
        assert service_values["UNDERWRITING_REALESTATEAPI_COMPS_MODE"] == "disabled"
        assert "RENTCAST_API_KEY" not in service_values
        assert "REALESTATEAPI_API_KEY" not in service_values


def render_service_environment_keys(blueprint: str, service_name: str) -> set[str]:
    marker = f"    name: {service_name}"
    assert marker in blueprint
    service_block = blueprint.split(marker, 1)[1].split("\n  - type:", 1)[0]
    return set(re.findall(r"(?m)^\s+- key: ([A-Z0-9_]+)\s*$", service_block))


def render_service_environment_values(blueprint: str, service_name: str) -> dict[str, str]:
    marker = f"    name: {service_name}"
    assert marker in blueprint
    service_block = blueprint.split(marker, 1)[1].split("\n  - type:", 1)[0]
    values = re.findall(
        r"(?m)^\s+- key: ([A-Z0-9_]+)\s*\r?\n\s+value: ([^\r\n]+?)\s*$",
        service_block,
    )
    return {key: value.strip("\"'") for key, value in values}
