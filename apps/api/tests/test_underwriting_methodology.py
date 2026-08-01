from pytest import MonkeyPatch

from app.core.config import get_settings
from app.services.underwriting_methodology import resolve_underwriting_methodology


def test_v3_is_the_live_methodology(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("UNDERWRITING_ACTIVE_METHODOLOGY_VERSION", "v3")
    monkeypatch.setenv("UNDERWRITING_V3_SHADOW_ENABLED", "false")
    get_settings.cache_clear()

    control = resolve_underwriting_methodology(get_settings())

    assert control.as_dict() == {
        "requested_version": "v3",
        "active_version": "v3",
        "planned_version": "v3",
        "v3_available": True,
        "shadow_enabled": False,
    }
    get_settings.cache_clear()


def test_v2_2_remains_an_explicit_technical_rollback(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("UNDERWRITING_ACTIVE_METHODOLOGY_VERSION", "v2.2")
    monkeypatch.setenv("UNDERWRITING_V3_SHADOW_ENABLED", "false")
    get_settings.cache_clear()

    control = resolve_underwriting_methodology(get_settings())

    assert control.active_version == "v2.2"
    assert control.v3_available is True
    assert control.shadow_enabled is False
    get_settings.cache_clear()


def test_v3_shadow_can_run_without_becoming_live_authority(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("UNDERWRITING_ACTIVE_METHODOLOGY_VERSION", "v2.2")
    monkeypatch.setenv("UNDERWRITING_V3_SHADOW_ENABLED", "true")
    get_settings.cache_clear()

    control = resolve_underwriting_methodology(get_settings())

    assert control.active_version == "v2.2"
    assert control.v3_available is True
    assert control.shadow_enabled is True
    get_settings.cache_clear()
