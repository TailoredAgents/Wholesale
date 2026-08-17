import signal
import threading
from collections.abc import Callable
from uuid import UUID

import sentry_sdk
import structlog
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import SessionLocal
from app.core.observability import initialize_error_monitoring
from app.integrations.operations_alerts import send_operational_failure_alert
from app.services.acquisition_operations import process_next_acquisition_reminder
from app.services.ai_operations import process_next_ai_operation
from app.services.batchdialer_zapier import process_next_batchdialer_event
from app.services.call_intelligence import (
    process_next_call_transcript,
    process_next_pending_call_note_approval,
)
from app.services.email import sync_next_email_account
from app.services.lead_manager import process_next_escalation
from app.services.mailbox_notifications import process_next_mailbox_notification
from app.services.marketing import process_next_marketing_conversion
from app.services.meta_lead_ads import (
    process_next_meta_address_enrichment,
    process_next_meta_lead_event,
    process_next_staff_lead_alert,
)
from app.services.operations import (
    COMMUNICATIONS_WORKER,
    mark_worker_operation_finished,
    mark_worker_operation_started,
    operation_retry_due,
    record_operation_failure,
    record_worker_heartbeat,
    register_worker,
    resolve_operation_failures,
    safe_meta_runtime_metadata,
    touch_worker_heartbeat,
)
from app.services.property_intelligence import (
    backfill_next_property_snapshot,
    process_next_property_research,
)
from app.services.resend_email_events import (
    process_next_resend_event,
    recover_next_received_email,
)
from app.services.staff_lead_alerts import (
    eligible_staff_alert_recipients,
    eligible_staff_inbound_message_alert_recipients,
)
from app.services.twilio_mms import process_next_twilio_mms_media
from app.services.voice import purge_next_expired_recording

logger = structlog.get_logger()
WorkerOperation = Callable[[Session, Settings], UUID | None]

WORKER_OPERATIONS: tuple[tuple[str, WorkerOperation], ...] = (
    ("batchdialer_zapier", process_next_batchdialer_event),
    ("meta_lead_ads", process_next_meta_lead_event),
    ("staff_lead_alerts", process_next_staff_lead_alert),
    ("twilio_mms_media", process_next_twilio_mms_media),
    ("meta_address_enrichment", process_next_meta_address_enrichment),
    ("property_intelligence", process_next_property_research),
    ("ai_operations", process_next_ai_operation),
    ("call_transcription", process_next_call_transcript),
    ("call_note_auto_post", process_next_pending_call_note_approval),
    ("recording_retention", purge_next_expired_recording),
    ("email_sync", sync_next_email_account),
    ("resend_email_events", process_next_resend_event),
    ("resend_email_recovery", recover_next_received_email),
    ("mailbox_notifications", process_next_mailbox_notification),
    ("acquisition_reminders", process_next_acquisition_reminder),
    ("lead_manager_escalations", process_next_escalation),
    ("marketing_conversions", process_next_marketing_conversion),
    ("property_intelligence_backfill", backfill_next_property_snapshot),
)


def install_shutdown_handlers(stop_event: threading.Event) -> None:
    def request_shutdown(signum: int, _frame: object) -> None:
        logger.info("worker_shutdown_requested", signal=signum)
        stop_event.set()

    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)


def run_heartbeat(stop_event: threading.Event, settings: Settings) -> None:
    """Keep readiness fresh while a provider operation is still in flight."""
    interval_seconds = min(
        settings.worker_heartbeat_interval_seconds,
        max(1, settings.worker_stale_after_seconds // 3),
    )
    while not stop_event.wait(interval_seconds):
        try:
            with SessionLocal() as db:
                touch_worker_heartbeat(db)
        except Exception:
            logger.exception("communications_worker_heartbeat_failed")


def run_worker(stop_event: threading.Event) -> None:
    settings = get_settings()
    meta_runtime_metadata = safe_meta_runtime_metadata(settings)
    with SessionLocal() as db:
        register_worker(db, runtime_metadata=meta_runtime_metadata)
        _recipients, staff_alert_recipients = eligible_staff_alert_recipients(db)
        (
            _inbound_recipients,
            inbound_message_alert_recipients,
        ) = eligible_staff_inbound_message_alert_recipients(db)
    staff_alert_blockers = list(settings.staff_lead_alert_configuration_blockers)
    logger.info(
        "worker_started",
        service=COMMUNICATIONS_WORKER,
        transcription_enabled=settings.call_transcription_enabled,
        poll_seconds=settings.call_transcription_poll_seconds,
        marketing_conversion_mode=meta_runtime_metadata["marketing_conversion_mode"],
        meta_conversion_configured=meta_runtime_metadata["meta_configured"],
        meta_conversion_configuration_blockers=(
            meta_runtime_metadata["meta_configuration_blockers"]
        ),
        meta_pixel_id_fingerprint=meta_runtime_metadata["meta_pixel_id_fingerprint"],
        meta_access_token_present=meta_runtime_metadata["meta_access_token_present"],
        meta_test_mode_enabled=meta_runtime_metadata["meta_test_mode_enabled"],
        batchdialer_zapier_enabled=settings.zapier_batchdialer_enabled,
        batchdialer_zapier_configured=settings.zapier_batchdialer_configured,
        batchdialer_zapier_configuration_blockers=list(
            settings.zapier_batchdialer_configuration_blockers
        ),
        batchdialer_zapier_allowed_campaign_count=len(
            settings.zapier_batchdialer_allowed_campaign_ids
        ),
        staff_lead_alert_sms_mode=settings.staff_lead_alert_sms_mode,
        staff_lead_alert_configured=not staff_alert_blockers,
        staff_lead_alert_configuration_blockers=staff_alert_blockers,
        staff_lead_alert_active_opted_in_recipients=staff_alert_recipients.active_opted_in,
        staff_lead_alert_ready_recipients=staff_alert_recipients.ready,
        staff_lead_alert_recipients_missing_phone=staff_alert_recipients.missing_phone,
        staff_lead_alert_recipients_with_invalid_phone=staff_alert_recipients.invalid_phone,
        staff_inbound_message_alert_active_opted_in_recipients=(
            inbound_message_alert_recipients.active_opted_in
        ),
        staff_inbound_message_alert_ready_recipients=(inbound_message_alert_recipients.ready),
        staff_inbound_message_alert_recipients_missing_phone=(
            inbound_message_alert_recipients.missing_phone
        ),
        staff_inbound_message_alert_recipients_with_invalid_phone=(
            inbound_message_alert_recipients.invalid_phone
        ),
    )
    if staff_alert_blockers or not staff_alert_recipients.ready:
        logger.warning(
            "staff_lead_alert_readiness_failed",
            mode=settings.staff_lead_alert_sms_mode,
            configured=not staff_alert_blockers,
            blockers=staff_alert_blockers,
            active_opted_in_recipients=staff_alert_recipients.active_opted_in,
            ready_recipients=staff_alert_recipients.ready,
            recipients_missing_phone=staff_alert_recipients.missing_phone,
            recipients_with_invalid_phone=staff_alert_recipients.invalid_phone,
        )
    if staff_alert_blockers or not inbound_message_alert_recipients.ready:
        logger.warning(
            "staff_inbound_message_alert_readiness_failed",
            mode=settings.staff_lead_alert_sms_mode,
            configured=not staff_alert_blockers,
            blockers=staff_alert_blockers,
            active_opted_in_recipients=inbound_message_alert_recipients.active_opted_in,
            ready_recipients=inbound_message_alert_recipients.ready,
            recipients_missing_phone=inbound_message_alert_recipients.missing_phone,
            recipients_with_invalid_phone=inbound_message_alert_recipients.invalid_phone,
        )
    heartbeat_thread = threading.Thread(
        target=run_heartbeat,
        args=(stop_event, settings),
        name="stonegate-worker-heartbeat",
        daemon=True,
    )
    heartbeat_thread.start()
    while not stop_event.is_set():
        processed_any = False
        had_error = False
        for operation_name, operation in WORKER_OPERATIONS:
            if stop_event.is_set():
                break
            result: UUID | None = None
            try:
                with SessionLocal() as operations_db:
                    mark_worker_operation_started(operations_db, operation_name)
                with SessionLocal() as db:
                    if not operation_retry_due(
                        db,
                        service_name=COMMUNICATIONS_WORKER,
                        operation_name=operation_name,
                    ):
                        had_error = True
                        continue
                    result = operation(db, settings)
                with SessionLocal() as operations_db:
                    resolve_operation_failures(
                        operations_db,
                        service_name=COMMUNICATIONS_WORKER,
                        operation_name=operation_name,
                    )
            except Exception as exc:
                had_error = True
                sentry_sdk.capture_exception(exc)
                logger.exception(
                    "communications_worker_operation_failed",
                    operation=operation_name,
                )
                failure = None
                try:
                    with SessionLocal() as operations_db:
                        failure = record_operation_failure(
                            operations_db,
                            service_name=COMMUNICATIONS_WORKER,
                            operation_name=operation_name,
                            error=exc,
                            retry_base_seconds=settings.worker_retry_base_seconds,
                            retry_max_seconds=settings.worker_retry_max_seconds,
                        )
                except Exception:
                    logger.exception(
                        "communications_worker_failure_record_failed",
                        operation=operation_name,
                    )
                if failure is not None:
                    try:
                        send_operational_failure_alert(settings, failure)
                    except Exception:
                        logger.exception(
                            "communications_worker_alert_failed",
                            operation=operation_name,
                        )
                continue
            finally:
                try:
                    with SessionLocal() as operations_db:
                        mark_worker_operation_finished(operations_db, operation_name)
                except Exception:
                    logger.exception(
                        "communications_worker_progress_record_failed",
                        operation=operation_name,
                    )
            if result is not None:
                processed_any = True
                logger.info(
                    "communications_worker_item_processed",
                    operation=operation_name,
                    record_id=str(result),
                )
        try:
            with SessionLocal() as db:
                record_worker_heartbeat(db, had_error=had_error)
        except Exception:
            logger.exception("communications_worker_heartbeat_failed")
        if processed_any:
            continue
        stop_event.wait(
            min(
                settings.call_transcription_poll_seconds,
                settings.worker_heartbeat_interval_seconds,
            )
        )
    heartbeat_thread.join(timeout=1)
    logger.info("worker_stopped", service=COMMUNICATIONS_WORKER)


def main() -> None:
    initialize_error_monitoring(get_settings(), service_name="worker")
    stop_event = threading.Event()
    install_shutdown_handlers(stop_event)
    run_worker(stop_event)


if __name__ == "__main__":
    main()
