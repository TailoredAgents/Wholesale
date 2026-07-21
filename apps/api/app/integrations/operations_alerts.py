import httpx

from app.core.config import Settings
from app.models.foundation import OperationalFailure


def send_operational_failure_alert(
    settings: Settings,
    failure: OperationalFailure,
    *,
    client: httpx.Client | None = None,
) -> bool:
    webhook_url = settings.operations_alert_webhook_url
    threshold = settings.operations_alert_after_failures
    if not webhook_url or failure.attempt_count < threshold:
        return False
    if failure.attempt_count != threshold and failure.attempt_count % threshold != 0:
        return False

    owns_client = client is None
    http_client = client or httpx.Client(timeout=5)
    try:
        response = http_client.post(
            webhook_url,
            json={
                "event": "stonegate.worker_failure",
                "service": failure.service_name,
                "operation": failure.operation_name,
                "error_type": failure.error_type,
                "attempt_count": failure.attempt_count,
                "first_occurred_at": failure.first_occurred_at.isoformat(),
                "last_occurred_at": failure.last_occurred_at.isoformat(),
            },
        )
        response.raise_for_status()
        return True
    finally:
        if owns_client:
            http_client.close()
