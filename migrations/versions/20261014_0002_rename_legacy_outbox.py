"""Rename the legacy outbox_events table if upgrading an earlier checkout.

Revision ID: 20261014_0002
Revises: 20261014_0001
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261014_0002"
down_revision: str | None = "20261014_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.outbox') IS NULL
               AND to_regclass('public.outbox_events') IS NOT NULL THEN
                ALTER TABLE outbox_events RENAME TO outbox;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    # This compatibility migration is intentionally a no-op on downgrade:
    # revision 0001 already creates and removes the correctly named table.
    pass
