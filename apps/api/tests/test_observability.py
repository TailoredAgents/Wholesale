from pytest import MonkeyPatch

from app.core.config import Settings
from app.core.observability import initialize_error_monitoring


def test_error_monitoring_is_disabled_without_dsn(monkeypatch: MonkeyPatch) -> None:
    initialized = False

    def fake_init(**_kwargs: object) -> None:
        nonlocal initialized
        initialized = True

    monkeypatch.setattr("app.core.observability.sentry_sdk.init", fake_init)

    enabled = initialize_error_monitoring(
        Settings.model_validate({"APP_ENV": "local"}),
        service_name="api",
    )

    assert enabled is False
    assert initialized is False


def test_error_monitoring_uses_privacy_preserving_defaults(monkeypatch: MonkeyPatch) -> None:
    init_options: dict[str, object] = {}
    tags: dict[str, str] = {}

    def fake_init(**kwargs: object) -> None:
        init_options.update(kwargs)

    def fake_set_tag(key: str, value: str) -> None:
        tags[key] = value

    monkeypatch.setattr("app.core.observability.sentry_sdk.init", fake_init)
    monkeypatch.setattr("app.core.observability.sentry_sdk.set_tag", fake_set_tag)

    enabled = initialize_error_monitoring(
        Settings.model_validate(
            {
                "APP_ENV": "production",
                "SENTRY_DSN": "https://public@example.test/1",
                "SENTRY_TRACES_SAMPLE_RATE": 0.1,
            }
        ),
        service_name="worker",
    )

    assert enabled is True
    assert init_options["environment"] == "production"
    assert init_options["traces_sample_rate"] == 0.1
    assert init_options["send_default_pii"] is False
    assert init_options["max_request_body_size"] == "never"
    assert init_options["include_local_variables"] is False
    assert tags["stonegate.service"] == "worker"

