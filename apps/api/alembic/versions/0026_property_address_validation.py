"""Property address validation and provider provenance.

Revision ID: 0026_property_address_validation
Revises: 0025_acquisition_operations
Create Date: 2026-07-21 00:00:00
"""

import re
import unicodedata
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0026_property_address_validation"
down_revision: str | None = "0025_acquisition_operations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STREET_SUFFIXES = {
    "avenue": "ave",
    "boulevard": "blvd",
    "circle": "cir",
    "court": "ct",
    "drive": "dr",
    "highway": "hwy",
    "lane": "ln",
    "parkway": "pkwy",
    "place": "pl",
    "road": "rd",
    "street": "st",
    "terrace": "ter",
    "trail": "trl",
}
DIRECTIONS = {
    "north": "n",
    "south": "s",
    "east": "e",
    "west": "w",
    "northeast": "ne",
    "northwest": "nw",
    "southeast": "se",
    "southwest": "sw",
}
UNIT_MARKERS = {"apartment": "unit", "apt": "unit", "suite": "unit", "ste": "unit", "#": "unit"}


def upgrade() -> None:
    op.add_column(
        "properties",
        sa.Column(
            "address_validation_status",
            sa.String(40),
            server_default="unverified",
            nullable=False,
        ),
    )
    op.add_column(
        "properties",
        sa.Column("address_validation_provider", sa.String(80), nullable=True),
    )
    op.add_column(
        "properties",
        sa.Column("provider_property_id", sa.String(500), nullable=True),
    )
    op.add_column(
        "properties",
        sa.Column("validated_formatted_address", sa.String(500), nullable=True),
    )
    op.add_column(
        "properties",
        sa.Column("address_validated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "properties",
        sa.Column("address_validation_metadata", sa.JSON(), nullable=True),
    )
    properties = sa.table(
        "properties",
        sa.column("id", sa.Uuid()),
        sa.column("street_address", sa.String()),
        sa.column("city", sa.String()),
        sa.column("state", sa.String()),
        sa.column("postal_code", sa.String()),
        sa.column("normalized_address_key", sa.String()),
    )
    connection = op.get_bind()
    rows = connection.execute(
        sa.select(
            properties.c.id,
            properties.c.street_address,
            properties.c.city,
            properties.c.state,
            properties.c.postal_code,
        )
    ).all()
    for row in rows:
        connection.execute(
            properties.update()
            .where(properties.c.id == row.id)
            .values(
                normalized_address_key=_canonical_address_key(
                    row.street_address,
                    row.city,
                    row.state,
                    row.postal_code,
                )
            )
        )


def downgrade() -> None:
    op.drop_column("properties", "address_validation_metadata")
    op.drop_column("properties", "address_validated_at")
    op.drop_column("properties", "validated_formatted_address")
    op.drop_column("properties", "provider_property_id")
    op.drop_column("properties", "address_validation_provider")
    op.drop_column("properties", "address_validation_status")


def _canonical_address_key(street: str, city: str, state: str, postal_code: str) -> str:
    street_tokens = _normalize_words(street).split()
    normalized_street = " ".join(
        STREET_SUFFIXES.get(token, DIRECTIONS.get(token, UNIT_MARKERS.get(token, token)))
        for token in street_tokens
    )
    postal_digits = "".join(character for character in postal_code if character.isdigit())
    return "|".join(
        (
            normalized_street,
            _normalize_words(city),
            _normalize_words(state).upper(),
            postal_digits[:5],
        )
    )


def _normalize_words(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    cleaned = re.sub(r"[^a-zA-Z0-9#]+", " ", ascii_value.lower())
    return " ".join(cleaned.split())
