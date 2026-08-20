from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from pytest import MonkeyPatch
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.foundation import (
    AuditEvent,
    ProspectingDialerPilot,
    ProspectingDialerProfile,
    ProspectingDialLeg,
    ProspectingDialSession,
)
from app.services.prospecting_dialer import (
    ProspectingDialerConfigurationError,
    cohort_local_date,
    load_runtime_graph,
    reject_and_record_daily_dial_cap,
    start_dial_session,
)
from app.services.prospecting_dialer_acceptance import pilot_configuration_fingerprint
from tests.test_prospecting_dialer_coordinator import (
    CoordinatorGraph,
    seed_coordinator_graph,
    session_start,
)

CAP_AUDIT_ACTION = "prospecting.dialer_pilot_daily_cap_blocked"


@pytest.fixture
def dialer_settings(monkeypatch: MonkeyPatch) -> Iterator[Settings]:
    values = {
        "PROSPECTING_NATIVE_DIALER_ENABLED": "true",
        "PROSPECTING_NATIVE_DIALER_MAX_LINES": "3",
        "PROSPECTING_NATIVE_DIALER_LEASE_SECONDS": "90",
        "PROSPECTING_NATIVE_DIALER_STALE_AFTER_SECONDS": "60",
        "PROSPECTING_NATIVE_DIALER_ORPHAN_GRACE_SECONDS": "60",
        "PROSPECTING_NATIVE_DIALER_RESERVED_COST_CENTS": "5",
        "TWILIO_VOICE_ENABLED": "true",
        "TWILIO_ACCOUNT_SID": "AC00000000000000000000000000000000",
        "TWILIO_AUTH_TOKEN": "daily-cap-audit-test-auth-token",
        "TWILIO_WEBHOOK_BASE_URL": "https://api.stonegate.test",
        "TWILIO_VALIDATE_WEBHOOK_SIGNATURES": "true",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


def _seed_counted_dial_and_pilot(
    db: Session,
    settings: Settings,
    *,
    daily_dial_limit: int,
    observed_dial_count: int,
) -> tuple[CoordinatorGraph, ProspectingDialSession, ProspectingDialerPilot, datetime]:
    graph = seed_coordinator_graph(db)
    profile = db.scalar(
        select(ProspectingDialerProfile).where(
            ProspectingDialerProfile.organization_id == graph.organization.id,
            ProspectingDialerProfile.user_id == graph.caller.id,
        )
    )
    assert profile is not None
    profile.daily_dial_limit = daily_dial_limit
    db.commit()

    observed_at = datetime.now(UTC)
    started = start_dial_session(
        db,
        graph.principal,
        session_start(graph, suffix=f"daily-cap-{daily_dial_limit}"),
        settings=settings,
        now=observed_at,
    )
    assert started is not None
    session = db.get(ProspectingDialSession, started.snapshot.session.id)
    assert session is not None
    first_leg = db.scalar(
        select(ProspectingDialLeg).where(
            ProspectingDialLeg.dial_session_id == session.id,
        )
    )
    assert first_leg is not None
    assert observed_dial_count >= 1
    db.add_all(
        ProspectingDialLeg(
            organization_id=first_leg.organization_id,
            dial_session_id=first_leg.dial_session_id,
            prospect_id=first_leg.prospect_id,
            batch_entry_id=first_leg.batch_entry_id,
            attempt_id=first_leg.attempt_id,
            contact_point_id=first_leg.contact_point_id,
            voice_line_id=first_leg.voice_line_id,
            line_slot=1,
            recipient=first_leg.recipient,
            provider=first_leg.provider,
            idempotency_key=f"daily-cap-counted-leg-{number}",
            status="completed",
            queued_at=observed_at,
            completed_at=observed_at,
            answer_classification="unknown",
            party_classification="unknown",
            leg_metadata={"daily_cap_test": True},
        )
        for number in range(2, observed_dial_count + 1)
    )

    runtime_graph = load_runtime_graph(
        db,
        graph.principal,
        campaign_id=graph.campaign.id,
        cohort_id=graph.cohort.id,
        batch_id=graph.batch.id,
    )
    assert runtime_graph is not None
    pilot = ProspectingDialerPilot(
        organization_id=graph.organization.id,
        caller_user_id=graph.caller.id,
        campaign_id=graph.campaign.id,
        cohort_id=graph.cohort.id,
        prospect_calling_batch_id=graph.batch.id,
        voice_line_id=runtime_graph.line.id,
        status="running",
        daily_dial_limit=daily_dial_limit,
        daily_spend_limit_cents=1000,
        configuration_fingerprint=pilot_configuration_fingerprint(runtime_graph, settings),
        started_by_user_id=graph.owner.id,
        started_at=observed_at,
        created_by_user_id=graph.owner.id,
        updated_by_user_id=graph.owner.id,
    )
    db.add(pilot)
    db.flush()
    session.pilot_id = pilot.id
    db.commit()
    return graph, session, pilot, observed_at


def test_d10_daily_cap_denial_commits_exact_audit_event(
    db_session: Session,
    dialer_settings: Settings,
) -> None:
    graph, session, pilot, queued_at = _seed_counted_dial_and_pilot(
        db_session,
        dialer_settings,
        daily_dial_limit=25,
        observed_dial_count=25,
    )
    denied_at = queued_at + timedelta(seconds=1)
    pilot_id = pilot.id
    session_id = session.id

    runtime_graph = load_runtime_graph(
        db_session,
        graph.principal,
        campaign_id=graph.campaign.id,
        cohort_id=graph.cohort.id,
        batch_id=graph.batch.id,
    )
    assert runtime_graph is not None
    with pytest.raises(
        ProspectingDialerConfigurationError,
        match="daily dial limit has been reached",
    ):
        reject_and_record_daily_dial_cap(
            db_session,
            graph.principal,
            runtime_graph,
            pilot,
            session=session,
            now=denied_at,
            commit_audit=True,
        )

    # The denial raises after committing its evidence. A fresh transaction must
    # still observe the event even after the caller rolls back the failed action.
    db_session.rollback()
    with Session(bind=db_session.get_bind()) as verifier:
        audits = verifier.scalars(
            select(AuditEvent).where(AuditEvent.action == CAP_AUDIT_ACTION)
        ).all()

    assert len(audits) == 1
    audit = audits[0]
    assert audit.action == CAP_AUDIT_ACTION
    assert audit.entity_type == "prospecting_dialer_pilot"
    assert audit.entity_id == pilot_id
    assert audit.new_value == {
        "pilot_id": str(pilot_id),
        "session_id": str(session_id),
        "caller_user_id": str(graph.caller.id),
        "campaign_id": str(graph.campaign.id),
        "cohort_id": str(graph.cohort.id),
        "prospect_calling_batch_id": str(graph.batch.id),
        "local_date": cohort_local_date(runtime_graph.cohort, denied_at).isoformat(),
        "observed_dial_count": 25,
        "daily_dial_limit": 25,
    }


def test_d10_daily_cap_does_not_audit_below_limit(
    db_session: Session,
    dialer_settings: Settings,
) -> None:
    graph, session, pilot, queued_at = _seed_counted_dial_and_pilot(
        db_session,
        dialer_settings,
        daily_dial_limit=25,
        observed_dial_count=24,
    )
    runtime_graph = load_runtime_graph(
        db_session,
        graph.principal,
        campaign_id=graph.campaign.id,
        cohort_id=graph.cohort.id,
        batch_id=graph.batch.id,
    )
    assert runtime_graph is not None

    reject_and_record_daily_dial_cap(
        db_session,
        graph.principal,
        runtime_graph,
        pilot,
        session=session,
        now=queued_at + timedelta(seconds=1),
        commit_audit=True,
    )

    assert (
        db_session.scalar(
            select(AuditEvent.id).where(AuditEvent.action == CAP_AUDIT_ACTION)
        )
        is None
    )
