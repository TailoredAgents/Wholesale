from datetime import UTC, datetime

from app.models.foundation import ProspectHandoff, ProspectingAttempt
from app.services.prospecting_measurement import (
    ProspectingCostBreakdown,
    allocate_cost_cents,
    apply_outcome_measurement,
    classify_outcome,
    cost_per_accepted_warm_lead_cents,
    is_accepted_warm_lead,
    labor_cost_cents,
)


def test_outcome_classification_uses_one_definition_for_both_dialer_modes() -> None:
    assert classify_outcome("no_answer").answer == "no_answer"
    assert classify_outcome("left_voicemail").answer == "machine"
    wrong_number = classify_outcome("wrong_number")
    assert wrong_number.answer == "live_person"
    assert wrong_number.party == "wrong_party"
    warm = classify_outcome("appointment_set")
    assert warm.answer == "live_person"
    assert warm.party == "right_party"
    assert warm.interest == "interested"
    assert warm.follow_up_permission == "granted"


def test_accepted_warm_lead_requires_complete_evidence_and_manager_acceptance() -> None:
    now = datetime.now(UTC)
    attempt = ProspectingAttempt(
        status="completed",
        outcome="interested",
        started_at=now,
        required_answer_count=4,
        answered_required_count=4,
        answer_classification="unknown",
        party_classification="unknown",
        interest_classification="not_assessed",
        follow_up_permission="not_recorded",
        dialer_mode="one_line_power",
        classification_source="manual_outcome",
        measurement_metadata={},
        qualification_answers={},
    )
    apply_outcome_measurement(attempt, outcome="interested", completed_at=now)
    handoff = ProspectHandoff(
        status="accepted",
        decision_code="accepted_interested",
        submitted_at=now,
        reviewed_at=now,
    )
    assert is_accepted_warm_lead(attempt, handoff) is True

    attempt.answered_required_count = 3
    assert is_accepted_warm_lead(attempt, handoff) is False
    attempt.answered_required_count = 4
    handoff.status = "pending"
    assert is_accepted_warm_lead(attempt, handoff) is False


def test_cost_formulas_are_reproducible_and_round_to_cents() -> None:
    assert labor_cost_cents(60, 800) == 800
    assert labor_cost_cents(91, 800) == 1213
    assert allocate_cost_cents(10_000, 30, 100) == 3_000
    costs = ProspectingCostBreakdown(
        labor_cents=80_000,
        list_cents=10_000,
        dialer_license_cents=14_900,
        phone_number_cents=500,
        voice_usage_cents=3_000,
        other_attributable_cents=1_600,
    )
    assert costs.total_cents == 110_000
    assert cost_per_accepted_warm_lead_cents(costs, 10) == 11_000
    assert cost_per_accepted_warm_lead_cents(costs, 0) is None
