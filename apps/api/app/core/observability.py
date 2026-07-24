import os

import sentry_sdk

from app.core.config import Settings


def initialize_error_monitoring(settings: Settings, *, service_name: str) -> bool:
    dsn = (settings.sentry_dsn or "").strip()
    if not dsn:
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=settings.sentry_environment or settings.app_env,
        release=os.getenv("RENDER_GIT_COMMIT"),
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
        max_request_body_size="never",
        include_local_variables=False,
    )
    sentry_sdk.set_tag("stonegate.service", service_name)
    return True

