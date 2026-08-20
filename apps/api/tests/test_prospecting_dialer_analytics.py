from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from uuid import uuid4

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.main import app
from app.models.foundation import (
    AttributionTouch,
    CallRecord,
    Campaign,
    CampaignCost,
    Contact,
    Lead,
    Market,
    MarketingSpend,
    Property,
    ProspectingCohort,
    ProspectingWorkSession,
    VoiceLine,
)
from app.schemas.prospecting import ProspectingDialerScorecardMetricsRead
from app.services.bootstrap import bootstrap_foundation
from app.services.prospecting_dialer_analytics import (
    BATCHDIALER_SOURCE,
    NATIVE_SOURCE,
    PAID_ADS_SOURCE,
    AnalyticsFilters,
    AttemptFact,
    DownstreamFact,
    LeadFact,
    ScoreAccumulator,
    _add_downstream,
    _daily_trend,
    _filter_options,
    _finalize_metrics,
    _launch_readiness,
    _load_non_prospecting_lead_facts,
    _metric_definitions,
    _score,
    _source_scorecards,
    _technical_measurement_gaps,
)
from tests.test_native_prospecting_dialer import (
    add_attempt,
    add_leg,
    add_profile,
    add_session,
    seed_dialer_graph,
)

OWNER_EMAIL = "dialer-analytics-owner@example.com"


def _create_user(
    client: TestClient,
    headers: dict[str, str],
    *,
    email: str,
    role_key: str,
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/operations/users",
        headers=headers,
        json={"email": email, "display_name": email.split("@")[0], "role_key": role_key},
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json())


def test_analytics_endpoint_is_manager_only_no_store_and_tenant_scoped(
    db_session: Session,
    api_db_override: None,
) -> None:
    foundation = bootstrap_foundation(
        db_session,
        organization_name="Dialer Analytics Workspace",
        admin_email=OWNER_EMAIL,
        admin_name="Analytics Owner",
    )
    client = TestClient(app)
    owner_headers = {"X-Dev-User-Email": OWNER_EMAIL}
    caller_email = "dialer-analytics-caller@example.com"
    _create_user(client, owner_headers, email=caller_email, role_key="prospecting_caller")

    response = client.get("/api/v1/prospecting/dialer/analytics", headers=owner_headers)
    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.json()["attribution_model_version"]

    anonymous = client.get("/api/v1/prospecting/dialer/analytics")
    assert anonymous.status_code == 401

    forbidden = client.get(
        "/api/v1/prospecting/dialer/analytics",
        headers={"X-Dev-User-Email": caller_email},
    )
    assert forbidden.status_code == 403

    other = bootstrap_foundation(
        db_session,
        organization_name="Other Analytics Workspace",
        admin_email="other-dialer-analytics-owner@example.com",
        admin_name="Other Owner",
    )
    assert other.admin_user is not None
    cross_tenant = client.get(
        "/api/v1/prospecting/dialer/analytics",
        headers=owner_headers,
        params={"caller_user_id": str(other.admin_user.id)},
    )
    assert cross_tenant.status_code == 422
    assert cross_tenant.headers["Cache-Control"] == "private, no-store"
    assert foundation.organization.id != other.organization.id


def test_analytics_rejects_oversized_range_with_no_store(
    db_session: Session,
    api_db_override: None,
) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Analytics Range Workspace",
        admin_email=OWNER_EMAIL,
        admin_name="Analytics Owner",
    )
    response = TestClient(app).get(
        "/api/v1/prospecting/dialer/analytics",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        params={"date_from": "2020-01-01", "date_to": "2022-01-01"},
    )
    assert response.status_code == 422
    assert "366" in response.json()["detail"]
    assert response.headers["Cache-Control"] == "private, no-store"


def test_analytics_query_validation_errors_are_no_store(
    db_session: Session,
    api_db_override: None,
) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Analytics Validation Workspace",
        admin_email=OWNER_EMAIL,
        admin_name="Analytics Owner",
    )
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    for params in (
        {"date_from": "not-a-date"},
        {"campaign_id": "not-a-uuid"},
    ):
        response = client.get(
            "/api/v1/prospecting/dialer/analytics",
            headers=headers,
            params=params,
        )
        assert response.status_code == 422
        assert response.headers["Cache-Control"] == "private, no-store"


def test_analytics_minimum_end_date_clamps_default_window_without_500(
    db_session: Session,
    api_db_override: None,
) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Analytics Minimum Date Workspace",
        admin_email=OWNER_EMAIL,
        admin_name="Analytics Owner",
    )
    response = TestClient(app).get(
        "/api/v1/prospecting/dialer/analytics",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        params={"date_to": date.min.isoformat()},
    )
    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.json()["period"]["date_from"] == date.min.isoformat()
    assert response.json()["period"]["date_to"] == date.min.isoformat()


def test_analytics_origin_volume_ceiling_fails_closed(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Analytics Volume Workspace",
        admin_email=OWNER_EMAIL,
        admin_name="Analytics Owner",
    )
    monkeypatch.setattr(
        "app.services.prospecting_dialer_analytics.MAX_ORIGIN_RECORDS",
        -1,
    )
    response = TestClient(app).get(
        "/api/v1/prospecting/dialer/analytics",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    assert response.status_code == 422
    assert "origin-record limit" in response.json()["detail"].lower()
    assert response.headers["Cache-Control"] == "private, no-store"


def test_analytics_volume_ceiling_includes_bounded_marketing_spend(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    foundation = bootstrap_foundation(
        db_session,
        organization_name="Analytics Spend Volume Workspace",
        admin_email=OWNER_EMAIL,
        admin_name="Analytics Owner",
    )
    spend_month = datetime.now(UTC).replace(
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    db_session.add(
        MarketingSpend(
            organization_id=foundation.organization.id,
            source="facebook_ads",
            campaign="D9 guard test",
            amount_cents=100,
            spend_month_at=spend_month,
        )
    )
    db_session.commit()
    monkeypatch.setattr(
        "app.services.prospecting_dialer_analytics.MAX_ORIGIN_RECORDS",
        0,
    )
    response = TestClient(app).get(
        "/api/v1/prospecting/dialer/analytics",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    assert response.status_code == 422
    assert "origin-record limit" in response.json()["detail"].lower()
    assert response.headers["Cache-Control"] == "private, no-store"


def test_non_finance_manager_gets_complete_financial_redaction(
    db_session: Session,
    api_db_override: None,
) -> None:
    graph = seed_dialer_graph(db_session)
    attempt = add_attempt(db_session, graph, entry_index=0, caller=graph.va, status="completed")
    attempt.dial_started_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.commit()
    client = TestClient(app)
    owner_headers = {"X-Dev-User-Email": graph.owner.email}
    manager_email = "analytics-acquisition-manager@example.com"
    _create_user(client, owner_headers, email=manager_email, role_key="acquisition_manager")
    response = client.get(
        "/api/v1/prospecting/dialer/analytics",
        headers={"X-Dev-User-Email": manager_email},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["financials_visible"] is False
    finance_keys = (
        "labor_cost_cents",
        "provider_cost_cents",
        "list_cost_cents",
        "other_cost_cents",
        "total_cost_cents",
        "gross_revenue_cents",
        "contribution_profit_cents",
        "profit_per_paid_hour_cents",
        "cost_per_qualified_seller_cents",
        "cost_per_contract_cents",
    )
    scorecards = [payload["summary"]]
    for dimension in (
        "by_va",
        "by_campaign",
        "by_cohort",
        "by_list",
        "by_dial_mode",
        "by_source",
    ):
        scorecards.extend(row["metrics"] for row in payload[dimension])
    assert len(scorecards) > 1
    for scorecard in scorecards:
        for key in finance_keys:
            assert scorecard[key] is None
            assert scorecard["status_by_key"][key] == "not_applicable"
        assert scorecard["coverage"]["provider_cost_basis_points"] is None
        assert scorecard["coverage"]["profit_basis_points"] is None
        warnings = " ".join(scorecard["coverage"]["warnings"]).lower()
        assert not any(
            word in warnings for word in ("provider cost", "profit", "marketing spend")
        )


def test_work_only_dialer_evidence_never_reports_fake_zero_total_cost() -> None:
    accumulator = ScoreAccumulator(
        raw_mode="unavailable",
        paid_time_applicable=True,
        work_session_count=1,
        paid_minutes=60,
        productive_calling_minutes=45,
    )
    metrics = _finalize_metrics(accumulator, [], financials_visible=True)
    assert metrics.total_cost_cents is None
    assert metrics.status_by_key["total_cost_cents"] == "unknown"
    assert metrics.status_by_key["labor_cost_cents"] == "unknown"
    assert metrics.status_by_key["provider_cost_cents"] == "unknown"
    assert metrics.status_by_key["list_cost_cents"] == "unknown"
    assert metrics.status_by_key["accepted_handoff_rate_basis_points"] == "not_applicable"


def test_actual_provider_cost_wins_over_voice_fallback_without_double_counting() -> None:
    accumulator = ScoreAccumulator(
        raw_mode="measured",
        paid_time_applicable=True,
        leg_count=2,
        leg_actual_cost_count=2,
        leg_actual_cost_cents=125,
        campaign_voice_cost_record_count=1,
        campaign_voice_cost_cents=900,
        fixed_provider_cost_record_count=1,
        fixed_provider_cost_cents=25,
    )
    metrics = _finalize_metrics(accumulator, [], financials_visible=True)
    assert metrics.provider_cost_cents == 150
    assert metrics.status_by_key["provider_cost_cents"] == "known"


def test_voice_usage_fallback_makes_provider_cost_coverage_complete() -> None:
    accumulator = ScoreAccumulator(
        raw_mode="measured",
        paid_time_applicable=True,
        attempt_ids={uuid4()},
        leg_count=3,
        leg_actual_cost_count=1,
        leg_actual_cost_cents=40,
        campaign_voice_cost_record_count=1,
        campaign_voice_cost_cents=300,
        fixed_provider_cost_record_count=1,
        fixed_provider_cost_cents=25,
    )
    metrics = _finalize_metrics(accumulator, [], financials_visible=True)
    assert metrics.provider_cost_cents == 325
    assert metrics.status_by_key["provider_cost_cents"] == "known"
    assert metrics.coverage.provider_cost_basis_points == 10_000


def test_pending_appointment_keeps_held_metric_partial() -> None:
    held_id = uuid4()
    pending_id = uuid4()
    accumulator = ScoreAccumulator(raw_mode="unavailable")
    accumulator.appointment_ids.update({held_id, pending_id})
    accumulator.appointment_status_by_id[held_id] = "held"
    accumulator.appointment_status_by_id[pending_id] = "scheduled"
    metrics = _finalize_metrics(accumulator, [], financials_visible=True)
    assert metrics.appointments_held == 1
    assert metrics.appointment_held_rate_basis_points is None
    assert metrics.status_by_key["appointments_held"] == "partial"
    assert metrics.status_by_key["appointment_held_rate_basis_points"] == "partial"


def test_downstream_is_bounded_by_origin_as_of_and_assignment_transactions() -> None:
    origin = datetime(2026, 8, 1, tzinfo=UTC)
    as_of = datetime(2026, 8, 15, tzinfo=UTC)
    in_window_transaction = uuid4()
    future_transaction = uuid4()
    unrelated_transaction = uuid4()
    in_window_appointment = uuid4()
    accumulator = ScoreAccumulator(raw_mode="unavailable")
    fact = DownstreamFact(
        lead_id=uuid4(),
        appointments=(
            (uuid4(), "held", origin - timedelta(seconds=1)),
            (in_window_appointment, "held", origin + timedelta(days=1)),
            (uuid4(), "held", as_of + timedelta(seconds=1)),
        ),
        transaction_ids=(in_window_transaction, future_transaction, unrelated_transaction),
        signed_transactions=(
            (in_window_transaction, origin + timedelta(days=2)),
            (future_transaction, as_of + timedelta(days=1)),
            (unrelated_transaction, origin - timedelta(days=1)),
        ),
        closed_transactions=(
            (in_window_transaction, origin + timedelta(days=3)),
            (future_transaction, as_of + timedelta(days=2)),
            (unrelated_transaction, origin + timedelta(days=3)),
        ),
        reconciliations=(
            (in_window_transaction, 50_000, 30_000, origin + timedelta(days=4)),
            (future_transaction, 60_000, 40_000, as_of + timedelta(days=2)),
        ),
        collected_revenue=(
            (uuid4(), 50_000, origin + timedelta(days=5), in_window_transaction),
            (uuid4(), 99_000, origin + timedelta(days=5), unrelated_transaction),
            (uuid4(), 60_000, as_of + timedelta(days=2), future_transaction),
        ),
    )
    _add_downstream(accumulator, fact, origin_at=origin, as_of=as_of)
    metrics = _finalize_metrics(accumulator, [], financials_visible=True)
    assert accumulator.appointment_ids == {in_window_appointment}
    assert metrics.signed_contracts == 1
    assert metrics.closed_assignments == 1
    assert metrics.gross_revenue_cents == 50_000
    assert metrics.contribution_profit_cents == 30_000


def test_paid_acquisition_and_later_batch_activity_both_survive_without_summary_duplication(
    db_session: Session,
) -> None:
    foundation = bootstrap_foundation(
        db_session,
        organization_name="Analytics Overlap Workspace",
        admin_email=OWNER_EMAIL,
        admin_name="Analytics Owner",
    )
    assert foundation.admin_user is not None
    observed_at = datetime.now(UTC).replace(microsecond=0)
    contact = Contact(
        organization_id=foundation.organization.id,
        legal_name="Overlap Seller",
        contact_type="seller",
        assigned_user_id=foundation.admin_user.id,
    )
    property_record = Property(
        organization_id=foundation.organization.id,
        street_address="100 Overlap Way",
        city="Atlanta",
        state="GA",
        postal_code="30303",
    )
    db_session.add_all([contact, property_record])
    db_session.flush()
    lead = Lead(
        organization_id=foundation.organization.id,
        contact_id=contact.id,
        property_id=property_record.id,
        assigned_user_id=foundation.admin_user.id,
        source="Website",
        stage_key="new",
        created_at=observed_at - timedelta(hours=2),
    )
    db_session.add(lead)
    db_session.flush()
    db_session.add_all(
        [
            AttributionTouch(
                organization_id=foundation.organization.id,
                lead_id=lead.id,
                touch_type="lead_creation",
                source="Facebook Lead Ads",
                medium="Paid Social",
                created_at=observed_at - timedelta(days=7),
            ),
            AttributionTouch(
                organization_id=foundation.organization.id,
                lead_id=lead.id,
                touch_type="batchdialer_handoff",
                source="batchdialer",
                medium="dialer",
                created_at=observed_at - timedelta(hours=1),
            ),
        ]
    )
    db_session.commit()
    filters = AnalyticsFilters(
        date_from=(observed_at - timedelta(days=1)).date(),
        date_to=observed_at.date(),
    )
    facts = _load_non_prospecting_lead_facts(
        db_session,
        foundation.organization.id,
        filters,
        observed_at,
    )
    assert [(fact.source, fact.lead.id) for fact in facts] == [
        (PAID_ADS_SOURCE, lead.id),
        (BATCHDIALER_SOURCE, lead.id),
    ]
    assert facts[0].entry_at == observed_at - timedelta(hours=2)
    summary = _score([], facts, [], [], [], raw_mode="unavailable", as_of=observed_at)
    assert len(summary.entered_lead_ids) == 1
    source_rows = _source_scorecards(
        [], facts, [], [], [], financials_visible=True, as_of=observed_at
    )
    by_source = {row.source: row for row in source_rows}
    assert by_source[PAID_ADS_SOURCE].metrics.entered_leads == 1
    assert by_source[BATCHDIALER_SOURCE].metrics.entered_leads == 1


def test_batch_creation_touch_without_handoff_enters_at_lead_creation(
    db_session: Session,
) -> None:
    foundation = bootstrap_foundation(
        db_session,
        organization_name="Analytics Batch Creation Workspace",
        admin_email=OWNER_EMAIL,
        admin_name="Analytics Owner",
    )
    assert foundation.admin_user is not None
    observed_at = datetime.now(UTC).replace(microsecond=0)
    lead_created_at = observed_at - timedelta(hours=2)
    contact = Contact(
        organization_id=foundation.organization.id,
        legal_name="Batch Creation Seller",
        contact_type="seller",
        assigned_user_id=foundation.admin_user.id,
    )
    property_record = Property(
        organization_id=foundation.organization.id,
        street_address="150 Creation Way",
        city="Atlanta",
        state="GA",
        postal_code="30303",
    )
    db_session.add_all([contact, property_record])
    db_session.flush()
    lead = Lead(
        organization_id=foundation.organization.id,
        contact_id=contact.id,
        property_id=property_record.id,
        assigned_user_id=foundation.admin_user.id,
        source="Website",
        stage_key="new",
        created_at=lead_created_at,
    )
    db_session.add(lead)
    db_session.flush()
    db_session.add(
        AttributionTouch(
            organization_id=foundation.organization.id,
            lead_id=lead.id,
            touch_type="lead_creation",
            source="BatchDialer",
            medium="dialer",
            created_at=observed_at - timedelta(hours=1),
        )
    )
    db_session.commit()
    facts = _load_non_prospecting_lead_facts(
        db_session,
        foundation.organization.id,
        AnalyticsFilters(
            date_from=(observed_at - timedelta(days=1)).date(),
            date_to=observed_at.date(),
        ),
        observed_at,
    )
    assert [(fact.source, fact.lead.id, fact.entry_at) for fact in facts] == [
        (BATCHDIALER_SOURCE, lead.id, lead_created_at)
    ]


def test_batch_daily_trend_reports_durable_handoff_count_as_known() -> None:
    report_date = date(2026, 8, 18)
    entry_at = datetime(2026, 8, 18, 14, tzinfo=UTC)
    lead_fact = LeadFact(
        lead=Lead(id=uuid4()),
        source=BATCHDIALER_SOURCE,
        entry_at=entry_at,
        downstream=DownstreamFact(
            lead_id=uuid4(),
            appointments=(),
            transaction_ids=(),
            signed_transactions=(),
            closed_transactions=(),
            reconciliations=(),
            collected_revenue=(),
        ),
    )
    trend = _daily_trend(
        AnalyticsFilters(date_from=report_date, date_to=report_date),
        [],
        [lead_fact],
        as_of=entry_at + timedelta(hours=1),
    )
    assert len(trend) == 1
    assert trend[0].accepted_handoffs == 1


def test_batch_replay_does_not_reenter_after_first_touch_window(db_session: Session) -> None:
    foundation = bootstrap_foundation(
        db_session,
        organization_name="Analytics Replay Workspace",
        admin_email=OWNER_EMAIL,
        admin_name="Analytics Owner",
    )
    assert foundation.admin_user is not None
    observed_at = datetime.now(UTC).replace(microsecond=0)
    contact = Contact(
        organization_id=foundation.organization.id,
        legal_name="Replay Seller",
        contact_type="seller",
        assigned_user_id=foundation.admin_user.id,
    )
    property_record = Property(
        organization_id=foundation.organization.id,
        street_address="200 Replay Way",
        city="Atlanta",
        state="GA",
        postal_code="30303",
    )
    db_session.add_all([contact, property_record])
    db_session.flush()
    lead = Lead(
        organization_id=foundation.organization.id,
        contact_id=contact.id,
        property_id=property_record.id,
        assigned_user_id=foundation.admin_user.id,
        source="BatchDialer",
        stage_key="new",
        created_at=observed_at - timedelta(days=4),
    )
    db_session.add(lead)
    db_session.flush()
    db_session.add_all(
        [
            AttributionTouch(
                organization_id=foundation.organization.id,
                lead_id=lead.id,
                touch_type="batchdialer_handoff",
                source="BatchDialer",
                created_at=observed_at - timedelta(days=3),
            ),
            AttributionTouch(
                organization_id=foundation.organization.id,
                lead_id=lead.id,
                touch_type="batchdialer_handoff",
                source="BatchDialer",
                created_at=observed_at - timedelta(minutes=1),
            ),
        ]
    )
    db_session.commit()
    facts = _load_non_prospecting_lead_facts(
        db_session,
        foundation.organization.id,
        AnalyticsFilters(
            date_from=(observed_at - timedelta(days=1)).date(),
            date_to=observed_at.date(),
        ),
        observed_at,
    )
    assert facts == []


def test_missing_call_duration_is_not_counted_as_short_call(
    db_session: Session,
    api_db_override: None,
) -> None:
    graph = seed_dialer_graph(db_session)
    attempt = add_attempt(db_session, graph, entry_index=0, caller=graph.va, status="completed")
    attempt.dial_started_at = datetime.now(UTC) - timedelta(minutes=1)
    attempt.answer_classification = "live_person"
    attempt.party_classification = "wrong_party"
    call = CallRecord(id=uuid4(), duration_seconds=None)
    fact = AttemptFact(
        attempt=attempt,
        campaign=graph.campaign,
        cohort=None,
        batch=graph.batch,
        caller=graph.va,
        call=call,
        quality=None,
        handoff=None,
        downstream=None,
        legs=(),
        source=NATIVE_SOURCE,
    )
    accumulator = _score(
        [fact], [], [], [], [], raw_mode="measured", as_of=datetime.now(UTC)
    )
    assert accumulator.short_calls == 0


def test_metric_definitions_cover_every_scorecard_and_coverage_field() -> None:
    definition_keys = {definition.key for definition in _metric_definitions()}
    scorecard_keys = set(ProspectingDialerScorecardMetricsRead.model_fields) - {
        "status_by_key",
        "coverage",
    }
    coverage_keys = {
        "coverage.raw_attempts_basis_points",
        "coverage.paid_hours_basis_points",
        "coverage.provider_cost_basis_points",
        "coverage.appointment_outcomes_basis_points",
        "coverage.profit_basis_points",
        "coverage.reputation_basis_points",
    }
    assert scorecard_keys | coverage_keys <= definition_keys


def test_historical_disabled_caller_remains_filterable(
    db_session: Session,
    api_db_override: None,
) -> None:
    graph = seed_dialer_graph(db_session)
    attempt = add_attempt(db_session, graph, entry_index=0, caller=graph.va, status="completed")
    attempt.dial_started_at = datetime.now(UTC)
    graph.va.calling_enabled = False
    db_session.commit()
    options = _filter_options(db_session, graph.organization.id)
    assert graph.va.id in {option.id for option in options.callers}


def test_readiness_blocks_two_org_live_legs_and_stale_profile_link(
    db_session: Session,
    api_db_override: None,
) -> None:
    graph = seed_dialer_graph(db_session)
    graph.va.calling_enabled = True
    graph.other_va.calling_enabled = True
    inactive_line = VoiceLine(
        organization_id=graph.organization.id,
        assigned_user_id=graph.va.id,
        provider="twilio",
        phone_number="+16785550199",
        label="Inactive prospecting line",
        department_key="acquisitions",
        purpose_key="prospecting_outbound",
        status="inactive",
        is_default=False,
        inbound_route="conversation_owner",
        ring_strategy="simultaneous",
        coverage_timezone="America/New_York",
        coverage_start_hour=0,
        coverage_end_hour=24,
        prospecting_dialer_max_concurrent_legs=1,
        missed_call_action="fallback_then_voicemail",
        line_metadata={},
    )
    db_session.add(inactive_line)
    db_session.flush()
    profile_one = add_profile(db_session, graph, user=graph.va, line_count=1)
    profile_one.voice_line_id = inactive_line.id
    profile_one.daily_dial_limit = 100
    profile_one.daily_spend_limit_cents = 1000
    profile_two = add_profile(db_session, graph, user=graph.other_va, line_count=1)
    profile_two.daily_dial_limit = 100
    profile_two.daily_spend_limit_cents = 1000
    session_one = add_session(db_session, graph, profile_one, caller=graph.va, key="analytics-one")
    session_two = add_session(
        db_session,
        graph,
        profile_two,
        caller=graph.other_va,
        key="analytics-two",
    )
    add_leg(db_session, graph, session_one, prospect_index=0, entry_index=0, slot=1, key="leg-one")
    add_leg(db_session, graph, session_two, prospect_index=1, entry_index=1, slot=1, key="leg-two")
    db_session.commit()

    readiness = _launch_readiness(
        db_session,
        graph.organization.id,
        get_settings(),
        datetime.now(UTC),
    )
    checks = {check.key: check for check in readiness.checks}
    assert checks["assigned_prospecting_lines"].status == "block"
    assert checks["single_line_caps"].status == "block"
    assert checks["session_recovery"].status == "block"
    assert "2 live leg(s)" in checks["session_recovery"].detail


def test_external_work_does_not_satisfy_native_measurement_readiness(
    db_session: Session,
    api_db_override: None,
) -> None:
    graph = seed_dialer_graph(db_session)
    attempt = add_attempt(db_session, graph, entry_index=0, caller=graph.va, status="completed")
    attempt.dial_started_at = datetime.now(UTC) - timedelta(days=1)
    market = Market(
        organization_id=graph.organization.id,
        name="External measurement market",
        code="external-measurement-market",
        state_code="GA",
        timezone="America/New_York",
        status="active",
        is_primary=False,
    )
    db_session.add(market)
    db_session.flush()
    campaign = Campaign(
        organization_id=graph.organization.id,
        market_id=market.id,
        owner_user_id=graph.owner.id,
        name="External Batch Campaign",
        code="external-batch-campaign",
        channel="cold_call",
        asset_class="house",
        status="active",
    )
    db_session.add(campaign)
    db_session.flush()
    cohort = ProspectingCohort(
        organization_id=graph.organization.id,
        campaign_id=campaign.id,
        created_by_user_id=graph.owner.id,
        name="External Batch Cohort",
        code="external-batch-cohort",
        status="active",
        source_name="BatchDialer",
        list_type="distressed",
        market_label="Atlanta",
        dialer_mode="batchdialer",
        call_window_start_hour=9,
        call_window_end_hour=17,
        timezone="America/New_York",
        starts_on=date.today(),
        cohort_metadata={},
    )
    db_session.add(cohort)
    db_session.flush()
    cost = CampaignCost(
        organization_id=graph.organization.id,
        campaign_id=campaign.id,
        cohort_id=cohort.id,
        worker_user_id=graph.va.id,
        category="va_labor",
        vendor_name="BatchDialer",
        amount_cents=1000,
        labor_minutes=60,
        hourly_rate_cents=1000,
        incurred_on=date.today(),
        created_by_user_id=graph.owner.id,
    )
    db_session.add(cost)
    db_session.flush()
    db_session.add(
        ProspectingWorkSession(
            organization_id=graph.organization.id,
            campaign_id=campaign.id,
            cohort_id=cohort.id,
            caller_user_id=graph.va.id,
            campaign_cost_id=cost.id,
            created_by_user_id=graph.owner.id,
            work_date=date.today(),
            paid_minutes=60,
            productive_calling_minutes=45,
            hourly_rate_cents=1000,
            labor_cost_cents=1000,
            source="provider_import",
        )
    )
    db_session.commit()
    gaps = _technical_measurement_gaps(db_session, graph.organization.id, datetime.now(UTC))
    assert "Recent native attempts have no durable paid-time work session." in gaps
    assert "Recent native attempts have no durable provider dial-leg telemetry." in gaps
