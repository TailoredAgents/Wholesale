from datetime import UTC, date, datetime, timedelta
from typing import cast
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from app.models.base import Base
from app.models.foundation import (
    BatchDialerCampaign,
    BatchDialerSyncCheckpoint,
    Organization,
)


def _table(model: type[BatchDialerCampaign] | type[BatchDialerSyncCheckpoint]) -> sa.Table:
    return cast(sa.Table, model.__table__)


def _organization_values(*, organization_id: object, slug: str) -> dict[str, object]:
    return {
        "id": organization_id,
        "name": f"Organization {slug}",
        "slug": slug,
    }


def _engine() -> sa.Engine:
    engine = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            cast(sa.Table, Organization.__table__),
            cast(sa.Table, BatchDialerSyncCheckpoint.__table__),
            cast(sa.Table, BatchDialerCampaign.__table__),
        ],
    )
    return engine


def test_batchdialer_models_are_organization_scoped_and_polling_ready() -> None:
    checkpoint = _table(BatchDialerSyncCheckpoint)
    campaign = _table(BatchDialerCampaign)

    checkpoint_constraints = {
        str(constraint.name)
        for constraint in checkpoint.constraints
        if constraint.name is not None
    }
    campaign_constraints = {
        str(constraint.name)
        for constraint in campaign.constraints
        if constraint.name is not None
    }
    assert {
        "uq_batchdialer_sync_checkpoints_org_stream",
        "ck_batchdialer_sync_checkpoints_lease",
        "ck_batchdialer_sync_checkpoints_counters",
    } <= checkpoint_constraints
    assert {
        "uq_batchdialer_campaigns_org_provider",
        "ck_batchdialer_campaigns_identity",
        "ck_batchdialer_campaigns_counters",
    } <= campaign_constraints

    for table in (checkpoint, campaign):
        organization_id = table.c.organization_id
        foreign_key = next(iter(organization_id.foreign_keys))
        assert foreign_key.target_fullname == "organizations.id"
        assert foreign_key.ondelete == "CASCADE"

    assert {
        "stream",
        "lease_token",
        "lease_owner",
        "lease_expires_at",
        "next_poll_at",
        "scan_date",
        "next_page_cursor",
        "last_attempt_at",
        "last_success_at",
        "last_campaign_refresh_at",
        "last_error",
        "poll_count",
        "fetched_cdr_count",
        "archived_event_count",
        "qualified_event_count",
        "sync_metadata",
    } <= set(checkpoint.c.keys())
    assert {
        "provider_campaign_id",
        "parent_campaign_id",
        "external_campaign_id",
        "name",
        "mode",
        "status",
        "is_active",
        "contact_count",
        "cdr_seen_count",
        "qualified_cdr_count",
        "imported_lead_count",
        "first_seen_at",
        "last_seen_at",
        "last_cdr_at",
        "provider_snapshot",
    } <= set(campaign.c.keys())

    checkpoint_indexes = {
        str(index.name): tuple(column.name for column in index.columns)
        for index in checkpoint.indexes
        if index.name is not None
    }
    campaign_indexes = {
        str(index.name): tuple(column.name for column in index.columns)
        for index in campaign.indexes
        if index.name is not None
    }
    assert checkpoint_indexes["ix_batchdialer_sync_checkpoints_due"] == (
        "stream",
        "next_poll_at",
    )
    assert checkpoint_indexes["ix_batchdialer_sync_checkpoints_lease"] == (
        "stream",
        "lease_expires_at",
    )
    assert campaign_indexes["ix_batchdialer_campaigns_org_active_status"] == (
        "organization_id",
        "is_active",
        "status",
    )


def test_checkpoint_enforces_one_stream_and_complete_lease_per_organization() -> None:
    engine = _engine()
    organization_id = uuid4()
    now = datetime.now(UTC)

    with engine.begin() as connection:
        connection.execute(
            sa.insert(Organization),
            _organization_values(organization_id=organization_id, slug="checkpoint-org"),
        )
        connection.execute(
            sa.insert(BatchDialerSyncCheckpoint),
            {
                "id": uuid4(),
                "organization_id": organization_id,
                "stream": "cdrs",
                "status": "polling",
                "lease_token": uuid4().hex,
                "lease_owner": "worker-1",
                "lease_expires_at": now + timedelta(seconds=90),
                "next_poll_at": now,
                "scan_date": date.today(),
                "sync_metadata": {"contract": "direct-v1"},
            },
        )

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.insert(BatchDialerSyncCheckpoint),
            {
                "id": uuid4(),
                "organization_id": organization_id,
                "stream": "cdrs",
            },
        )

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.update(BatchDialerSyncCheckpoint)
            .where(BatchDialerSyncCheckpoint.organization_id == organization_id)
            .values(lease_owner=None)
        )

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.update(BatchDialerSyncCheckpoint)
            .where(BatchDialerSyncCheckpoint.organization_id == organization_id)
            .values(fetched_cdr_count=-1)
        )


def test_campaign_identity_is_unique_per_organization_and_counters_are_nonnegative() -> None:
    engine = _engine()
    first_organization_id = uuid4()
    second_organization_id = uuid4()

    with engine.begin() as connection:
        connection.execute(
            sa.insert(Organization),
            [
                _organization_values(
                    organization_id=first_organization_id,
                    slug="campaign-org-one",
                ),
                _organization_values(
                    organization_id=second_organization_id,
                    slug="campaign-org-two",
                ),
            ],
        )
        connection.execute(
            sa.insert(BatchDialerCampaign),
            {
                "id": uuid4(),
                "organization_id": first_organization_id,
                "provider_campaign_id": "377626",
                "name": "Distressed Homeowners",
                "status": "active",
                "contact_count": 100,
                "provider_snapshot": {"mode": "preview"},
            },
        )
        connection.execute(
            sa.insert(BatchDialerCampaign),
            {
                "id": uuid4(),
                "organization_id": second_organization_id,
                "provider_campaign_id": "377626",
                "name": "Another Organization Campaign",
            },
        )

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.insert(BatchDialerCampaign),
            {
                "id": uuid4(),
                "organization_id": first_organization_id,
                "provider_campaign_id": "377626",
                "name": "Renamed Campaign",
            },
        )

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.insert(BatchDialerCampaign),
            {
                "id": uuid4(),
                "organization_id": first_organization_id,
                "provider_campaign_id": "negative-count",
                "name": "Invalid Campaign",
                "qualified_cdr_count": -1,
            },
        )
