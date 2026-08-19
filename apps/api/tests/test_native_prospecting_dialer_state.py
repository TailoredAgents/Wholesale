from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.models.foundation import ProspectingDialLeg
from app.schemas.prospecting import ProspectingDialerProfileUpsert
from app.services.prospecting_dialer import advance_dial_leg_provider_state


def test_dialer_profile_payload_cannot_inject_runtime_capacity() -> None:
    with pytest.raises(ValidationError, match="effective_line_count"):
        ProspectingDialerProfileUpsert.model_validate(
            {
                "status": "active",
                "default_line_count": 3,
                "max_line_count": 3,
                "effective_line_count": 3,
            }
        )


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"default_line_count": 0}, "greater than or equal to 1"),
        ({"max_line_count": 4}, "less than or equal to 3"),
        (
            {"default_line_count": 2, "max_line_count": 1},
            "Default line count cannot exceed",
        ),
    ],
)
def test_dialer_profile_rejects_invalid_capacity(
    payload: dict[str, int],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        ProspectingDialerProfileUpsert.model_validate(payload)


def test_provider_state_advances_and_ignores_out_of_order_callbacks() -> None:
    started_at = datetime(2026, 8, 19, 14, 0, tzinfo=UTC)
    leg = ProspectingDialLeg(
        status="queued",
        last_provider_event_sequence=0,
    )

    assert advance_dial_leg_provider_state(
        leg,
        target_status="ringing",
        provider_sequence_number=2,
        occurred_at=started_at,
    ) == (True, "processed")
    assert leg.status == "ringing"
    assert leg.ringing_at == started_at

    assert advance_dial_leg_provider_state(
        leg,
        target_status="dialing",
        provider_sequence_number=1,
        occurred_at=started_at - timedelta(seconds=1),
    ) == (False, "ignored_stale")
    assert leg.status == "ringing"
    assert leg.last_provider_event_sequence == 2


def test_provider_state_never_regresses_a_terminal_leg() -> None:
    started_at = datetime(2026, 8, 19, 14, 0, tzinfo=UTC)
    leg = ProspectingDialLeg(
        status="connected",
        last_provider_event_sequence=4,
        last_provider_event_at=started_at,
        answered_at=started_at,
        connected_at=started_at,
    )

    assert advance_dial_leg_provider_state(
        leg,
        target_status="completed",
        provider_sequence_number=5,
        occurred_at=started_at + timedelta(seconds=30),
    ) == (True, "processed")
    completed_at = leg.completed_at

    assert advance_dial_leg_provider_state(
        leg,
        target_status="connected",
        provider_sequence_number=6,
        occurred_at=started_at + timedelta(seconds=31),
    ) == (False, "ignored_terminal")
    assert leg.status == "completed"
    assert leg.completed_at == completed_at


@pytest.mark.parametrize("terminal_status", ["no_answer", "busy", "cancelled"])
def test_connected_leg_rejects_incompatible_terminal_regressions(
    terminal_status: str,
) -> None:
    connected_at = datetime(2026, 8, 19, 14, 0, tzinfo=UTC)
    leg = ProspectingDialLeg(
        status="connected",
        last_provider_event_sequence=4,
        last_provider_event_at=connected_at,
        answered_at=connected_at,
        connected_at=connected_at,
    )

    assert advance_dial_leg_provider_state(
        leg,
        target_status=terminal_status,
        provider_sequence_number=5,
        occurred_at=connected_at + timedelta(seconds=30),
    ) == (False, "ignored_regression")
    assert leg.status == "connected"
    assert leg.completed_at is None


def test_provider_state_normalizes_naive_provider_times_to_utc() -> None:
    naive_time = datetime(2026, 8, 19, 14, 0)
    leg = ProspectingDialLeg(
        status="queued",
        last_provider_event_sequence=0,
    )

    applied, status = advance_dial_leg_provider_state(
        leg,
        target_status="dialing",
        provider_sequence_number=0,
        occurred_at=naive_time,
    )

    assert (applied, status) == (True, "processed")
    assert leg.dialing_at is not None
    assert leg.dialing_at.tzinfo == UTC
