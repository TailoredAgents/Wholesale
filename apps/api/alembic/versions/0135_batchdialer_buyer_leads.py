"""Keep BatchDialer investor prospects in Buyer Leads until promotion.

Revision ID: 0135_batchdialer_buyer_leads
Revises: 0134_pg_stat_statements
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0135_batchdialer_buyer_leads"
down_revision: str | None = "0134_pg_stat_statements"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # This deliberately targets only the exact records created by the investor-campaign
    # handoff. Existing verified relationships and completed purchasers remain untouched.
    op.execute(
        sa.text(
            """
            UPDATE buyers
            SET status = 'needs_review', updated_at = CURRENT_TIMESTAMP
            WHERE source_key = 'batchdialer'
              AND status = 'active'
              AND completed_deals = 0
              AND verification_status <> 'verified'
              AND notes = 'Created from a BatchDialer investor-disposition result.'
              AND EXISTS (
                  SELECT 1
                  FROM disposition_buyer_pool_candidates candidate
                  WHERE candidate.buyer_id = buyers.id
                    AND candidate.organization_id = buyers.organization_id
                    AND candidate.provider = 'batchdialer'
              )
            """
        )
    )


def downgrade() -> None:
    # Promotion is a business decision. A rollback must not silently promote leads.
    pass
