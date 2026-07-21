from datetime import UTC, datetime

import httpx

from app.core.config import Settings
from app.integrations.operations_alerts import send_operational_failure_alert
from app.models.foundation import OperationalFailure


def test_operational_alert_is_sent_at_failure_threshold() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(202)

    now = datetime.now(UTC)
    failure = OperationalFailure(
        service_name="worker",
        operation_name="email_sync",
        status="open",
        fingerprint="test-fingerprint",
        attempt_count=3,
        error_type="RuntimeError",
        error_message="sensitive provider detail",
        first_occurred_at=now,
        last_occurred_at=now,
        next_retry_at=now,
        resolved_at=None,
        failure_metadata=None,
    )
    settings = Settings.model_validate(
        {
            "APP_ENV": "local",
            "OPERATIONS_ALERT_WEBHOOK_URL": "https://alerts.example.test/worker",
            "OPERATIONS_ALERT_AFTER_FAILURES": 3,
        }
    )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        sent = send_operational_failure_alert(settings, failure, client=client)

    assert sent is True
    assert len(requests) == 1
    assert b"sensitive provider detail" not in requests[0].content
