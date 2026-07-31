import pytest
from pytest import MonkeyPatch

from app.core.config import get_settings
from app.services.underwriting_methodology import resolve_underwriting_methodology


def test_v2_2_is_the_only_active_methodology(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("UNDERWRITING_ACTIVE_METHODOLOGY_VERSION", "v2.2")
    monkeypatch.setenv("UNDERWRITING_V3_SHADOW_ENABLED", "false")
    get_settings.cache_clear()

    control = resolve_underwriting_methodology(get_settings())

    assert control.as_dict() == {
        "requested_version": "v2.2",
        "active_version": "v2.2",
        "planned_version": "v3",
        "v3_available": False,
        "shadow_enabled": False,
    }
    get_settings.cache_clear()


def test_v3_cannot_be_activated_before_its_runner_exists(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("UNDERWRITING_ACTIVE_METHODOLOGY_VERSION", "v3")
    monkeypatch.setenv("UNDERWRITING_V3_SHADOW_ENABLED", "false")
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="not available for live calculations"):
        resolve_underwriting_methodology(get_settings())
    get_settings.cache_clear()


def test_v3_shadow_cannot_be_enabled_before_replay_exists(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("UNDERWRITING_ACTIVE_METHODOLOGY_VERSION", "v2.2")
    monkeypatch.setenv("UNDERWRITING_V3_SHADOW_ENABLED", "true")
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="shadow execution is not available"):
        resolve_underwriting_methodology(get_settings())
    get_settings.cache_clear()
