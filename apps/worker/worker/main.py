import os
import signal
import threading

import structlog

logger = structlog.get_logger()


def get_heartbeat_seconds() -> int:
    raw_value = os.getenv("WORKER_HEARTBEAT_SECONDS", "300")
    try:
        heartbeat_seconds = int(raw_value)
    except ValueError:
        logger.warning("invalid_worker_heartbeat_seconds", value=raw_value, fallback=300)
        return 300

    return max(heartbeat_seconds, 10)


def install_shutdown_handlers(stop_event: threading.Event) -> None:
    def request_shutdown(signum: int, _frame: object) -> None:
        logger.info("worker_shutdown_requested", signal=signum)
        stop_event.set()

    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)


def run_worker(stop_event: threading.Event) -> None:
    heartbeat_seconds = get_heartbeat_seconds()
    logger.info(
        "worker_started",
        service="real-estate-wholesale-worker",
        heartbeat_seconds=heartbeat_seconds,
    )

    while not stop_event.is_set():
        logger.info("worker_heartbeat", service="real-estate-wholesale-worker")
        stop_event.wait(heartbeat_seconds)

    logger.info("worker_stopped", service="real-estate-wholesale-worker")


def main() -> None:
    stop_event = threading.Event()
    install_shutdown_handlers(stop_event)
    run_worker(stop_event)


if __name__ == "__main__":
    main()
