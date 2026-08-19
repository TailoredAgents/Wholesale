import warnings
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from app.models.base import Base
from app.models.foundation import (
    CallRecord,
    ProspectingDialLeg,
    ProspectingProviderEvent,
    VoiceCallIntent,
)


def constraint_names(model: type[VoiceCallIntent] | type[CallRecord]) -> set[str]:
    table = cast(sa.Table, model.__table__)
    return {
        str(constraint.name)
        for constraint in table.constraints
        if constraint.name is not None
    }


def test_voice_models_expose_explicit_warm_and_prospecting_context() -> None:
    for model in (VoiceCallIntent, CallRecord):
        table = cast(sa.Table, model.__table__)
        assert table.c.conversation_id.nullable is True
        assert table.c.contact_id.nullable is True
        for column_name, target in (
            ("prospect_id", "prospects.id"),
            ("prospecting_attempt_id", "prospecting_attempts.id"),
            ("prospecting_dial_leg_id", "prospecting_dial_legs.id"),
        ):
            column = table.c[column_name]
            assert column.nullable is True
            assert {foreign_key.target_fullname for foreign_key in column.foreign_keys} == {target}

    assert "ck_voice_call_intents_context" in constraint_names(VoiceCallIntent)
    assert "ck_call_records_context" in constraint_names(CallRecord)
    assert "uq_voice_call_intents_prospecting_dial_leg" in constraint_names(VoiceCallIntent)
    assert "uq_call_records_prospecting_dial_leg" in constraint_names(CallRecord)
    dial_leg_table = cast(sa.Table, ProspectingDialLeg.__table__)
    assert "uq_prospecting_dial_legs_call_record" in {
        str(constraint.name)
        for constraint in dial_leg_table.constraints
        if constraint.name is not None
    }


def test_prospecting_voice_foreign_keys_have_acyclic_metadata_ordering() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", sa.exc.SAWarning)
        assert CallRecord.__table__ in Base.metadata.sorted_tables
        assert VoiceCallIntent.__table__ in Base.metadata.sorted_tables


def test_provider_reconciliation_indexes_are_leg_scoped_and_ordered() -> None:
    provider_event_table = cast(sa.Table, ProspectingProviderEvent.__table__)
    indexes = {
        str(index.name): index
        for index in provider_event_table.indexes
        if index.name is not None
    }
    sequence_index = indexes["ix_prospecting_provider_events_leg_sequence"]

    assert sequence_index.unique is False
    assert tuple(column.name for column in sequence_index.columns) == (
        "organization_id",
        "provider",
        "dial_leg_id",
        "provider_sequence_number",
    )
    assert str(sequence_index.dialect_options["postgresql"]["where"]) == (
        "dial_leg_id IS NOT NULL AND provider_sequence_number IS NOT NULL"
    )
    assert tuple(
        column.name
        for column in indexes["ix_prospecting_provider_events_call_lookup"].columns
    ) == ("organization_id", "provider", "provider_call_id")


def voice_intent_values(*, context: str, dial_leg_id: UUID | None = None) -> dict[str, object]:
    values: dict[str, object] = {
        "id": uuid4(),
        "organization_id": uuid4(),
        "actor_user_id": uuid4(),
        "voice_line_id": uuid4(),
        "idempotency_key": f"voice-test-{uuid4()}",
        "recipient": "+16785550100",
        "status": "pending",
        "recording_consent_status": "one_party_consent",
        "expires_at": datetime.now(UTC) + timedelta(minutes=5),
    }
    if context == "warm":
        values.update(conversation_id=uuid4(), contact_id=uuid4())
    elif context == "cold":
        values.update(
            prospect_id=uuid4(),
            prospecting_attempt_id=uuid4(),
            prospecting_dial_leg_id=dial_leg_id or uuid4(),
        )
    return values


def call_record_values(*, context: str, dial_leg_id: UUID | None = None) -> dict[str, object]:
    values: dict[str, object] = {
        "id": uuid4(),
        "organization_id": uuid4(),
        "provider": "twilio",
        "provider_call_id": f"CA{uuid4().hex}",
        "direction": "outbound",
        "status": "queued",
        "recording_consent_status": "one_party_consent",
    }
    if context == "warm":
        values.update(conversation_id=uuid4(), contact_id=uuid4())
    elif context == "cold":
        values.update(
            prospect_id=uuid4(),
            prospecting_attempt_id=uuid4(),
            prospecting_dial_leg_id=dial_leg_id or uuid4(),
        )
    return values


def test_database_checks_accept_only_complete_warm_or_cold_contexts() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(sa.insert(VoiceCallIntent), voice_intent_values(context="warm"))
        connection.execute(sa.insert(VoiceCallIntent), voice_intent_values(context="cold"))
        connection.execute(sa.insert(CallRecord), call_record_values(context="warm"))
        connection.execute(sa.insert(CallRecord), call_record_values(context="cold"))

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(sa.insert(VoiceCallIntent), voice_intent_values(context="missing"))

    invalid_mixed = voice_intent_values(context="cold")
    invalid_mixed["conversation_id"] = uuid4()
    invalid_mixed["contact_id"] = uuid4()
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(sa.insert(VoiceCallIntent), invalid_mixed)

    invalid_cold_call = call_record_values(context="cold")
    invalid_cold_call["communication_record_id"] = uuid4()
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(sa.insert(CallRecord), invalid_cold_call)


def test_one_dial_leg_cannot_bind_to_two_voice_intents() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    dial_leg_id = uuid4()

    with engine.begin() as connection:
        connection.execute(
            sa.insert(VoiceCallIntent),
            voice_intent_values(context="cold", dial_leg_id=dial_leg_id),
        )

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.insert(VoiceCallIntent),
            voice_intent_values(context="cold", dial_leg_id=dial_leg_id),
        )
