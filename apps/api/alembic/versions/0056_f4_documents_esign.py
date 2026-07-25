"""F4 private document storage and e-signature records.

Revision ID: 0056_f4_documents_esign
Revises: 0055_remove_dnc_review_gate
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0056_f4_documents_esign"
down_revision: str | None = "0055_remove_dnc_review_gate"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def add_storage_columns(
    table_name: str,
    *,
    content_column: str,
    include_deleted_at: bool = True,
) -> None:
    op.add_column(
        table_name,
        sa.Column("storage_provider", sa.String(40), server_default="database", nullable=False),
    )
    op.add_column(table_name, sa.Column("storage_key", sa.String(1000)))
    op.add_column(
        table_name,
        sa.Column(
            "malware_scan_status",
            sa.String(40),
            server_default="not_configured",
            nullable=False,
        ),
    )
    op.add_column(table_name, sa.Column("retention_until", sa.DateTime(timezone=True)))
    if include_deleted_at:
        op.add_column(table_name, sa.Column("deleted_at", sa.DateTime(timezone=True)))
    op.alter_column(table_name, content_column, existing_type=sa.LargeBinary(), nullable=True)


def upgrade() -> None:
    add_storage_columns("contract_templates", content_column="file_data")
    add_storage_columns("transaction_documents", content_column="file_data")
    add_storage_columns(
        "field_inspection_photos",
        content_column="image_data",
        include_deleted_at=False,
    )
    add_storage_columns("buyer_proof_documents", content_column="file_data")
    op.create_index(
        "ix_buyer_proof_documents_deleted_at",
        "buyer_proof_documents",
        ["deleted_at"],
    )
    op.add_column(
        "contract_templates",
        sa.Column("esign_provider_template_id", sa.String(255)),
    )
    op.add_column("contract_templates", sa.Column("esign_field_mapping", sa.JSON()))

    op.create_table(
        "esign_envelopes",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("contract_package_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("completed_document_id", sa.Uuid()),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("provider_document_id", sa.String(255), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("message", sa.String(2000)),
        sa.Column("test_mode", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("provider_payload", sa.JSON(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("declined_at", sa.DateTime(timezone=True)),
        sa.Column("expired_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("last_provider_event_at", sa.DateTime(timezone=True)),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"]),
        sa.ForeignKeyConstraint(["contract_package_id"], ["contract_packages.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["completed_document_id"], ["transaction_documents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "provider",
            "provider_document_id",
            name="uq_esign_envelope_provider_document",
        ),
    )
    for column in ("organization_id", "transaction_id", "contract_package_id", "status"):
        op.create_index(f"ix_esign_envelopes_{column}", "esign_envelopes", [column])

    op.create_table(
        "esign_recipients",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("esign_envelope_id", sa.Uuid(), nullable=False),
        sa.Column("provider_recipient_id", sa.String(255)),
        sa.Column("placeholder_name", sa.String(120), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("signing_order", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("viewed_at", sa.DateTime(timezone=True)),
        sa.Column("signed_at", sa.DateTime(timezone=True)),
        sa.Column("declined_at", sa.DateTime(timezone=True)),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["esign_envelope_id"], ["esign_envelopes.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "esign_envelope_id", "email", name="uq_esign_recipient_envelope_email"
        ),
    )
    op.create_index("ix_esign_recipients_organization_id", "esign_recipients", ["organization_id"])
    op.create_index(
        "ix_esign_recipients_esign_envelope_id",
        "esign_recipients",
        ["esign_envelope_id"],
    )

    op.create_table(
        "esign_provider_events",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("esign_envelope_id", sa.Uuid()),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("provider_event_id", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("processing_error", sa.String(2000)),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["esign_envelope_id"], ["esign_envelopes.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "provider",
            "provider_event_id",
            name="uq_esign_provider_event",
        ),
    )
    for column in ("organization_id", "esign_envelope_id", "event_type"):
        op.create_index(
            f"ix_esign_provider_events_{column}",
            "esign_provider_events",
            [column],
        )


def downgrade() -> None:
    op.drop_table("esign_provider_events")
    op.drop_table("esign_recipients")
    op.drop_table("esign_envelopes")
    op.drop_column("contract_templates", "esign_field_mapping")
    op.drop_column("contract_templates", "esign_provider_template_id")
    op.drop_index(
        "ix_buyer_proof_documents_deleted_at",
        table_name="buyer_proof_documents",
    )
    for table_name, content_column, include_deleted_at in (
        ("buyer_proof_documents", "file_data", True),
        ("field_inspection_photos", "image_data", False),
        ("transaction_documents", "file_data", True),
        ("contract_templates", "file_data", True),
    ):
        op.alter_column(
            table_name,
            content_column,
            existing_type=sa.LargeBinary(),
            nullable=False,
        )
        if include_deleted_at:
            op.drop_column(table_name, "deleted_at")
        op.drop_column(table_name, "retention_until")
        op.drop_column(table_name, "malware_scan_status")
        op.drop_column(table_name, "storage_key")
        op.drop_column(table_name, "storage_provider")
