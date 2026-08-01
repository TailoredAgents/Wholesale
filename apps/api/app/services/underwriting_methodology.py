from dataclasses import dataclass

from app.core.config import Settings

ACTIVE_METHODOLOGY_VERSION = "v3"
ROLLBACK_METHODOLOGY_VERSION = "v2.2"
PLANNED_METHODOLOGY_VERSION = "v3"


@dataclass(frozen=True)
class UnderwritingMethodologyControl:
    requested_version: str
    active_version: str
    planned_version: str
    v3_available: bool
    shadow_enabled: bool

    def as_dict(self) -> dict[str, str | bool]:
        return {
            "requested_version": self.requested_version,
            "active_version": self.active_version,
            "planned_version": self.planned_version,
            "v3_available": self.v3_available,
            "shadow_enabled": self.shadow_enabled,
        }


def resolve_underwriting_methodology(
    settings: Settings,
) -> UnderwritingMethodologyControl:
    requested = settings.underwriting_active_methodology_version
    if requested not in {ACTIVE_METHODOLOGY_VERSION, ROLLBACK_METHODOLOGY_VERSION}:
        raise ValueError(
            "Choose the live Stonegate V3 method or the V2.2 rollback method."
        )
    return UnderwritingMethodologyControl(
        requested_version=requested,
        active_version=requested,
        planned_version=PLANNED_METHODOLOGY_VERSION,
        v3_available=True,
        shadow_enabled=(
            requested == ROLLBACK_METHODOLOGY_VERSION
            and settings.underwriting_v3_shadow_enabled
        ),
    )
