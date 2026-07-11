import structlog

logger = structlog.get_logger()


def main() -> None:
    logger.info("worker_started", service="real-estate-wholesale-worker")


if __name__ == "__main__":
    main()
