import pytest
from pydantic import ValidationError
from pytest import MonkeyPatch

from app.core.config import Settings, get_settings
from app.main import create_app


def test_app_environment_is_normalized_and_rejects_unknown_values() -> None:
    settings = Settings.model_validate({"APP_ENV": " Production "})

    assert settings.app_env == "production"
    with pytest.raises(ValidationError):
        Settings.model_validate({"APP_ENV": "prod"})


def test_native_prospecting_dialer_defaults_to_disabled_single_line() -> None:
    settings = Settings.model_validate({"APP_ENV": "test"})

    assert settings.prospecting_native_dialer_enabled is False
    assert settings.prospecting_native_dialer_max_lines == 1
    assert settings.prospecting_native_dialer_implemented_line_cap == 1
    assert settings.prospecting_native_dialer_effective_line_cap == 1


def test_native_prospecting_dialer_stores_future_limit_without_activating_it() -> None:
    settings = Settings.model_validate(
        {
            "APP_ENV": "test",
            "PROSPECTING_NATIVE_DIALER_ENABLED": True,
            "PROSPECTING_NATIVE_DIALER_MAX_LINES": 3,
        }
    )

    assert settings.prospecting_native_dialer_max_lines == 3
    assert settings.prospecting_native_dialer_effective_line_cap == 1


@pytest.mark.parametrize("configured_limit", [0, 4])
def test_native_prospecting_dialer_rejects_out_of_range_limits(
    configured_limit: int,
) -> None:
    with pytest.raises(ValueError):
        Settings.model_validate(
            {
                "APP_ENV": "test",
                "PROSPECTING_NATIVE_DIALER_MAX_LINES": configured_limit,
            }
        )


def test_production_rejects_native_prospecting_multi_line_configuration() -> None:
    with pytest.raises(
        ValidationError,
        match="PROSPECTING_NATIVE_DIALER_MAX_LINES cannot exceed 1",
    ):
        Settings.model_validate(
            {
                "APP_ENV": "production",
                "PROSPECTING_NATIVE_DIALER_MAX_LINES": 2,
            }
        )


def test_production_api_startup_requires_complete_clerk_configuration(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CLERK_ISSUER", "https://clerk.example.test")
    monkeypatch.delenv("CLERK_JWKS_URL", raising=False)
    monkeypatch.delenv("CLERK_SECRET_KEY", raising=False)
    monkeypatch.setenv("CLERK_AUTHORIZED_PARTIES", "https://app.example.test")
    get_settings.cache_clear()

    try:
        with pytest.raises(ValueError, match="CLERK_SECRET_KEY"):
            create_app()
    finally:
        get_settings.cache_clear()


def test_production_api_derives_jwks_and_disables_docs(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", " Production ")
    monkeypatch.setenv("CLERK_ISSUER", "https://clerk.example.test")
    monkeypatch.delenv("CLERK_JWKS_URL", raising=False)
    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test_not-a-real-secret")
    monkeypatch.setenv("CLERK_AUTHORIZED_PARTIES", "https://app.example.test")
    monkeypatch.delenv("CLERK_AUDIENCE", raising=False)
    get_settings.cache_clear()

    try:
        production_app = create_app()
        settings = get_settings()
    finally:
        get_settings.cache_clear()

    assert settings.clerk_jwks_endpoint == ("https://clerk.example.test/.well-known/jwks.json")
    assert production_app.docs_url is None
    assert production_app.redoc_url is None


def test_production_api_rejects_local_only_authorized_parties(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CLERK_ISSUER", "https://clerk.example.test")
    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test_not-a-real-secret")
    monkeypatch.setenv(
        "CLERK_AUTHORIZED_PARTIES",
        "http://localhost:3000,https://127.0.0.1",
    )
    get_settings.cache_clear()

    try:
        with pytest.raises(ValueError, match="non-local HTTPS origin"):
            create_app()
    finally:
        get_settings.cache_clear()


def test_production_api_startup_rejects_enabled_zapier_without_form_allowlist(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CLERK_ISSUER", "https://clerk.example.test")
    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test_not-a-real-secret")
    monkeypatch.setenv("CLERK_AUTHORIZED_PARTIES", "https://app.example.test")
    monkeypatch.setenv("ZAPIER_FACEBOOK_LEADS_ENABLED", "true")
    monkeypatch.setenv("ZAPIER_FACEBOOK_PAGE_ID", "123456789")
    monkeypatch.delenv("ZAPIER_FACEBOOK_ALLOWED_FORM_IDS", raising=False)
    get_settings.cache_clear()

    try:
        with pytest.raises(ValueError, match="ZAPIER_FACEBOOK_ALLOWED_FORM_IDS"):
            create_app()
    finally:
        get_settings.cache_clear()
