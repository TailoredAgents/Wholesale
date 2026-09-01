from dataclasses import dataclass
from typing import Any, Protocol


class ProviderTransportUnavailableError(RuntimeError):
    """Raised when code attempts an unverified provider-network operation."""


@dataclass(frozen=True)
class ProviderCapabilities:
    provider_key: str
    provider_label: str
    mode: str
    api_contract_verified: bool
    live_transport_enabled: bool
    credential_required: bool
    supported_manual_capabilities: tuple[str, ...]
    unverified_capabilities: tuple[str, ...]
    blockers: tuple[str, ...]

    def snapshot(self) -> dict[str, Any]:
        return {
            "provider_key": self.provider_key,
            "provider_label": self.provider_label,
            "mode": self.mode,
            "api_contract_verified": self.api_contract_verified,
            "live_transport_enabled": self.live_transport_enabled,
            "credential_required": self.credential_required,
            "supported_manual_capabilities": list(self.supported_manual_capabilities),
            "unverified_capabilities": list(self.unverified_capabilities),
            "blockers": list(self.blockers),
        }


class DispositionProviderAdapter(Protocol):
    @property
    def capabilities(self) -> ProviderCapabilities: ...

    def build_public_listing_payload(
        self,
        *,
        package_version: int,
        package_status: str,
        package_was_current_at_prepare: bool,
        package_preliminary: bool,
        package_snapshot_at: str,
        package_snapshot: dict[str, Any],
    ) -> dict[str, Any]: ...

    def publish(self, _payload: dict[str, Any]) -> None: ...


class ManualInvestorLiftAdapter:
    """Manual-only boundary until InvestorLift supplies a written API contract.

    This adapter deliberately contains no base URL, authentication shape, endpoint,
    polling behavior, or network client. It prepares a buyer-safe handoff artifact and
    refuses live publication so an undocumented provider contract cannot leak into the
    production workflow.
    """

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_key="investorlift",
            provider_label="InvestorLift",
            mode="manual",
            api_contract_verified=False,
            live_transport_enabled=False,
            credential_required=False,
            supported_manual_capabilities=(
                "exact_package_export",
                "manual_listing_link",
                "manual_status_refresh",
                "staged_inquiry_evidence",
                "staged_offer_evidence",
                "independent_export",
            ),
            unverified_capabilities=(
                "api_authentication",
                "property_publish_api",
                "property_update_api",
                "provider_webhooks",
                "buyer_discovery_api",
                "engagement_sync_api",
                "offer_sync_api",
                "rate_limits_and_retry_contract",
            ),
            blockers=(
                "InvestorLift has not supplied Stonegate with a verified direct API contract.",
                "Live provider transport remains disabled; use the governed manual handoff.",
            ),
        )

    def build_public_listing_payload(
        self,
        *,
        package_version: int,
        package_status: str,
        package_was_current_at_prepare: bool,
        package_preliminary: bool,
        package_snapshot_at: str,
        package_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "schema_version": "stonegate.disposition_provider.v2",
            "provider": "investorlift",
            "handoff_mode": "manual",
            "package": {
                "version": package_version,
                "status_at_prepare": package_status,
                "was_current_at_prepare": package_was_current_at_prepare,
                "snapshot_at_prepare": package_snapshot_at,
                "preliminary_at_prepare": package_preliminary,
            },
            "listing": package_snapshot,
        }

    def publish(self, _payload: dict[str, Any]) -> None:
        raise ProviderTransportUnavailableError(
            "InvestorLift live publication is unavailable until its direct API contract "
            "is verified in writing. Download the governed manual handoff bundle instead."
        )


def get_disposition_provider_adapter(provider_key: str) -> DispositionProviderAdapter:
    if provider_key != "investorlift":
        raise ValueError(f"Unsupported disposition provider: {provider_key}.")
    return ManualInvestorLiftAdapter()
