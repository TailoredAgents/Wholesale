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
from app.services.call_intelligence import process_next_call_transcript
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
    operation_retry_due,
    record_operation_failure,
    record_worker_heartbeat,
    register_worker,
    resolve_operation_failures,
)
from app.services.property_intelligence import (
    backfill_next_property_snapshot,
    process_next_property_research,
)
from app.services.resend_email_events import (
    process_next_resend_event,
    recover_next_received_email,
)
from app.services.voice import purge_next_expired_recording

logger = structlog.get_logger()
WorkerOperation = Callable[[Session, Settings], UUID | None]


def install_shutdown_handlers(stop_event: threading.Event) -> None:
    def request_shutdown(signum: int, _frame: object) -> None:
        logger.info("worker_shutdown_requested", signal=signum)
        stop_event.set()

    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)


def run_worker(stop_event: threading.Event) -> None:
    settings = get_settings()
    with SessionLocal() as db:
        register_worker(db)
    logger.info(
        "worker_started",
        service=COMMUNICATIONS_WORKER,
        transcription_enabled=settings.call_transcription_enabled,
        poll_seconds=settings.call_transcription_poll_seconds,
    )
    operations: tuple[tuple[str, WorkerOperation], ...] = (
        ("meta_lead_ads", process_next_meta_lead_event),
        ("staff_lead_alerts", process_next_staff_lead_alert),
        ("meta_address_enrichment", process_next_meta_address_enrichment),
        ("property_intelligence", process_next_property_research),
        ("ai_operations", process_next_ai_operation),
        ("call_transcription", process_next_call_transcript),
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
    while not stop_event.is_set():
        processed_operation: str | None = None
        processed_id: UUID | None = None
        had_error = False
        for operation_name, operation in operations:
            try:
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
            if result is not None:
                processed_operation = operation_name
                processed_id = result
                break
        try:
            with SessionLocal() as db:
                record_worker_heartbeat(db, had_error=had_error)
        except Exception:
            logger.exception("communications_worker_heartbeat_failed")
        if processed_operation is not None and processed_id is not None:
            logger.info(
                "communications_worker_item_processed",
                operation=processed_operation,
                record_id=str(processed_id),
            )
            continue
        stop_event.wait(
            min(
                settings.call_transcription_poll_seconds,
                settings.worker_heartbeat_interval_seconds,
            )
        )
    logger.info("worker_stopped", service=COMMUNICATIONS_WORKER)


def main() -> None:
    initialize_error_monitoring(get_settings(), service_name="worker")
    stop_event = threading.Event()
    install_shutdown_handlers(stop_event)
    run_worker(stop_event)


if __name__ == "__main__":
    main()
