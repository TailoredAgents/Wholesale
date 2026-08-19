"""Add durable prospecting call-evidence links and transcript uniqueness.

Revision ID: 0107_prospecting_evidence
Revises: 0106_prospecting_dispositions
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0107_prospecting_evidence"
down_revision: str | None = "0106_prospecting_dispositions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _deduplicate_transcripts() -> None:
    """Preserve the strongest legacy transcript before enforcing one per recording."""

    bind = op.get_bind()
    duplicate_recordings = bind.execute(
        sa.text(
            "SELECT recording_id FROM call_transcripts GROUP BY recording_id HAVING COUNT(*) > 1"
        )
    ).fetchall()
    status_rank = {
        "approved": 7,
        "completed": 6,
        "needs_review": 5,
        "processing": 4,
        "queued": 3,
        "failed": 2,
        "exhausted": 1,
    }
    for (recording_id,) in duplicate_recordings:
        rows = bind.execute(
            sa.text(
                "SELECT id, status, created_at FROM call_transcripts "
                "WHERE recording_id = :recording_id"
            ),
            {"recording_id": recording_id},
        ).fetchall()
        rows = sorted(
            rows,
            key=lambda row: (
                status_rank.get(row.status, 0),
                row.created_at,
                str(row.id),
            ),
            reverse=True,
        )
        keeper_id = rows[0].id
        for duplicate in rows[1:]:
            bind.execute(
                sa.text(
                    "UPDATE prospecting_call_quality_reviews SET transcript_id = :keeper "
                    "WHERE transcript_id = :duplicate"
                ),
                {"keeper": keeper_id, "duplicate": duplicate.id},
            )
            bind.execute(
                sa.text(
                    "UPDATE approval_requests SET entity_id = :keeper "
                    "WHERE entity_type = 'call_transcript' AND entity_id = :duplicate"
                ),
                {"keeper": keeper_id, "duplicate": duplicate.id},
            )
            bind.execute(
                sa.text(
                    "UPDATE activity_events SET entity_id = :keeper "
                    "WHERE entity_type = 'call_transcript' AND entity_id = :duplicate"
                ),
                {"keeper": keeper_id, "duplicate": duplicate.id},
            )
            bind.execute(
                sa.text(
                    "UPDATE audit_events SET entity_id = :keeper "
                    "WHERE entity_type = 'call_transcript' AND entity_id = :duplicate"
                ),
                {"keeper": keeper_id, "duplicate": duplicate.id},
            )
            bind.execute(
                sa.text("DELETE FROM call_transcripts WHERE id = :duplicate"),
                {"duplicate": duplicate.id},
            )


def upgrade() -> None:
    _deduplicate_transcripts()
    op.create_unique_constraint(
        "uq_call_transcripts_recording",
        "call_transcripts",
        ["recording_id"],
    )
    op.add_column(
        "communication_records",
        sa.Column("source_call_record_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_communication_records_source_call_record_id",
        "communication_records",
        "call_records",
        ["source_call_record_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_communication_records_source_call_record_id",
        "communication_records",
        ["source_call_record_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_communication_records_source_call_record_id",
        table_name="communication_records",
    )
    op.drop_constraint(
        "fk_communication_records_source_call_record_id",
        "communication_records",
        type_="foreignkey",
    )
    op.drop_column("communication_records", "source_call_record_id")
    op.drop_constraint(
        "uq_call_transcripts_recording",
        "call_transcripts",
        type_="unique",
    )
