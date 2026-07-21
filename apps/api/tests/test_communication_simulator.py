import pytest

from app.core.config import Settings
from app.integrations.communications import (
    OutboundMessageRequest,
    SimulatedCommunicationProvider,
)


def test_simulated_provider_is_deterministic_and_never_delivers() -> None:
    provider = SimulatedCommunicationProvider()
    request = OutboundMessageRequest(
        lead_id="lead-1",
        contact_id="contact-1",
        channel="sms",
        recipient="+14045550123",
        body="Stonegate simulation message",
        idempotency_key="simulation-message-1",
    )

    first = provider.send(request, dry_run=True)
    second = provider.send(request, dry_run=True)

    assert first == second
    assert first.provider == "simulated"
    assert first.provider_message_id is not None
    assert first.provider_message_id.startswith("sim-sms-")
    assert first.status == "sent"
    assert first.raw_payload["simulated"] is True


def test_simulated_provider_changes_id_for_different_content() -> None:
    provider = SimulatedCommunicationProvider()
    first = provider.send(
        OutboundMessageRequest(
            lead_id="lead-1",
            contact_id="contact-1",
            channel="email",
            recipient="seller@example.test",
            subject="First subject",
            body="First body",
            idempotency_key="email-simulation-1",
        )
    )
    second = provider.send(
        OutboundMessageRequest(
            lead_id="lead-1",
            contact_id="contact-1",
            channel="email",
            recipient="seller@example.test",
            subject="Second subject",
            body="Second body",
            idempotency_key="email-simulation-2",
        )
    )

    assert first.provider_message_id != second.provider_message_id


def test_simulation_is_rejected_in_production() -> None:
    with pytest.raises(ValueError, match="simulate is forbidden in production"):
        Settings.model_validate(
            {"APP_ENV": "production", "COMMUNICATION_PROVIDER_MODE": "simulate"}
        )
