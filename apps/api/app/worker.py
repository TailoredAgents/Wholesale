import signal
import threading

import structlog

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.services.call_intelligence import process_next_call_transcript
from app.services.voice import purge_next_expired_recording

logger = structlog.get_logger()


def install_shutdown_handlers(stop_event: threading.Event) -> None:
    def request_shutdown(signum: int, _frame: object) -> None:
        logger.info("worker_shutdown_requested", signal=signum)
        stop_event.set()

    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)


def run_worker(stop_event: threading.Event) -> None:
    settings = get_settings()
    logger.info(
        "worker_started",
        service="stonegate-call-intelligence-worker",
        transcription_enabled=settings.call_transcription_enabled,
        poll_seconds=settings.call_transcription_poll_seconds,
    )
    while not stop_event.is_set():
        processed_id = None
        purged_recording_id = None
        try:
            with SessionLocal() as db:
                processed_id = process_next_call_transcript(db, settings)
                if processed_id is None:
                    purged_recording_id = purge_next_expired_recording(db, settings)
        except Exception:
            logger.exception("communications_worker_iteration_failed")
        if processed_id is not None:
            logger.info("call_transcript_processed", transcript_id=str(processed_id))
            continue
        if purged_recording_id is not None:
            logger.info("expired_call_recording_deleted", recording_id=str(purged_recording_id))
            continue
        stop_event.wait(settings.call_transcription_poll_seconds)
    logger.info("worker_stopped", service="stonegate-call-intelligence-worker")


def main() -> None:
    stop_event = threading.Event()
    install_shutdown_handlers(stop_event)
    run_worker(stop_event)


if __name__ == "__main__":
    main()
