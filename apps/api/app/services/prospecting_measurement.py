from dataclasses import dataclass
from datetime import datetime

from app.models.foundation import ProspectHandoff, ProspectingAttempt

METRIC_DEFINITIONS = {
    "dial_attempt": {
        "source_record": "prospecting_attempt",
        "required_fields": ["dial_started_at"],
        "timestamp_field": "dial_started_at",
    },
    "machine_answer": {
        "source_record": "prospecting_attempt",
        "required_fields": ["answer_classification=machine", "answered_at"],
        "timestamp_field": "answered_at",
    },
    "live_contact": {
        "source_record": "prospecting_attempt",
        "required_fields": ["answer_classification=live_person", "answered_at"],
        "timestamp_field": "answered_at",
    },
    "right_party_contact": {
        "source_record": "prospecting_attempt",
        "required_fields": [
            "answer_classification=live_person",
            "party_classification=right_party",
            "right_party_confirmed_at",
        ],
        "timestamp_field": "right_party_confirmed_at",
    },
    "interested_seller": {
        "source_record": "prospecting_attempt",
        "required_fields": [
            "party_classification=right_party",
            "interest_classification=interested",
            "follow_up_permission=granted",
            "interest_confirmed_at",
        ],
        "timestamp_field": "interest_confirmed_at",
    },
    "submitted_handoff": {
        "source_record": "prospect_handoff",
        "required_fields": ["status", "submitted_at"],
        "timestamp_field": "submitted_at",
    },
    "accepted_warm_lead": {
        "source_record": "prospect_handoff+prospecting_attempt",
        "required_fields": [
            "handoff.status=accepted",
            "handoff.decision_code=accepted_*",
            "right_party_contact",
            "interested_seller",
            "all_required_answers_complete",
        ],
        "timestamp_field": "prospect_handoff.reviewed_at",
    },
    "rejected_handoff": {
        "source_record": "prospect_handoff",
        "required_fields": ["status=rejected", "decision_code=rejected_*", "reviewed_at"],
        "timestamp_field": "reviewed_at",
    },
    "callback": {
        "source_record": "prospecting_attempt",
        "required_fields": ["outcome=callback_requested|follow_up", "callback_at"],
        "timestamp_field": "callback_at",
    },
    "appointment": {
        "source_record": "appointments",
        "required_fields": ["lead_id", "scheduled_start_at", "status"],
        "timestamp_field": "scheduled_start_at",
    },
    "contract": {
        "source_record": "transactions",
        "required_fields": ["lead_id", "contract_signed_at"],
        "timestamp_field": "contract_signed_at",
    },
}


@dataclass(frozen=True)
class AttemptClassification:
    answer: str
    party: str
    interest: str
    follow_up_permission: str


@dataclass(frozen=True)
class ProspectingCostBreakdown:
    labor_cents: int = 0
    list_cents: int = 0
    dialer_license_cents: int = 0
    phone_number_cents: int = 0
    voice_usage_cents: int = 0
    other_attributable_cents: int = 0

    @property
    def total_cents(self) -> int:
        return sum(
            (
                self.labor_cents,
                self.list_cents,
                self.dialer_license_cents,
                self.phone_number_cents,
                self.voice_usage_cents,
                self.other_attributable_cents,
            )
        )


OUTCOME_CLASSIFICATIONS = {
    "no_answer": AttemptClassification("no_answer", "unknown", "not_assessed", "not_recorded"),
    "left_voicemail": AttemptClassification("machine", "unknown", "not_assessed", "not_recorded"),
    "wrong_number": AttemptClassification("live_person", "wrong_party", "not_assessed", "declined"),
    "not_interested": AttemptClassification(
        "live_person", "right_party", "not_interested", "declined"
    ),
    "do_not_call": AttemptClassification(
        "live_person", "right_party", "not_interested", "declined"
    ),
    "callback_requested": AttemptClassification(
        "live_person", "right_party", "interested", "granted"
    ),
    "follow_up": AttemptClassification("live_person", "right_party", "interested", "granted"),
    "interested": AttemptClassification("live_person", "right_party", "interested", "granted"),
    "appointment_set": AttemptClassification("live_person", "right_party", "interested", "granted"),
}


def classify_outcome(outcome: str) -> AttemptClassification:
    return OUTCOME_CLASSIFICATIONS.get(
        outcome,
        AttemptClassification("unknown", "unknown", "not_assessed", "not_recorded"),
    )


def apply_outcome_measurement(
    attempt: ProspectingAttempt,
    *,
    outcome: str,
    completed_at: datetime,
    provider_evidence: bool = False,
) -> None:
    classification = classify_outcome(outcome)
    attempt.answer_classification = classification.answer
    attempt.party_classification = classification.party
    attempt.interest_classification = classification.interest
    attempt.follow_up_permission = classification.follow_up_permission
    attempt.classification_source = (
        "provider_plus_manual_outcome" if provider_evidence else "manual_outcome"
    )
    attempt.dial_started_at = attempt.dial_started_at or attempt.started_at
    if classification.answer in {"machine", "live_person"}:
        attempt.answered_at = attempt.answered_at or completed_at
    if classification.party == "right_party":
        attempt.right_party_confirmed_at = attempt.right_party_confirmed_at or completed_at
    if classification.interest == "interested":
        attempt.interest_confirmed_at = attempt.interest_confirmed_at or completed_at


def is_accepted_warm_lead(
    attempt: ProspectingAttempt,
    handoff: ProspectHandoff,
) -> bool:
    return bool(
        handoff.status == "accepted"
        and (handoff.decision_code or "").startswith("accepted_")
        and has_accepted_warm_evidence(attempt)
    )


def has_accepted_warm_evidence(attempt: ProspectingAttempt) -> bool:
    return bool(
        attempt.answer_classification == "live_person"
        and attempt.party_classification == "right_party"
        and attempt.interest_classification == "interested"
        and attempt.follow_up_permission == "granted"
        and attempt.right_party_confirmed_at is not None
        and attempt.interest_confirmed_at is not None
        and attempt.required_answer_count > 0
        and attempt.answered_required_count == attempt.required_answer_count
    )


def default_handoff_decision_code(decision: str, outcome: str | None) -> str:
    if decision == "accepted":
        return "accepted_appointment_set" if outcome == "appointment_set" else "accepted_interested"
    if decision == "needs_correction":
        return "correction_other"
    return "rejected_other"


def labor_cost_cents(paid_minutes: int, hourly_rate_cents: int) -> int:
    if paid_minutes < 0 or hourly_rate_cents < 0:
        raise ValueError("Labor inputs cannot be negative.")
    return (paid_minutes * hourly_rate_cents + 30) // 60


def allocate_cost_cents(total_cents: int, cohort_weight: int, total_weight: int) -> int:
    if total_cents < 0 or cohort_weight < 0 or total_weight < 0:
        raise ValueError("Cost-allocation inputs cannot be negative.")
    if total_weight == 0:
        return 0
    if cohort_weight > total_weight:
        raise ValueError("Cohort allocation weight cannot exceed total weight.")
    return (total_cents * cohort_weight + total_weight // 2) // total_weight


def cost_per_accepted_warm_lead_cents(
    costs: ProspectingCostBreakdown,
    accepted_warm_leads: int,
) -> int | None:
    if accepted_warm_leads < 0:
        raise ValueError("Accepted warm-lead count cannot be negative.")
    if accepted_warm_leads == 0:
        return None
    return (costs.total_cents + accepted_warm_leads // 2) // accepted_warm_leads
