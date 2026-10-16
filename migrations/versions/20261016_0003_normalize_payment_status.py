"""Store payment status values in the lowercase API representation.

Revision ID: 20261016_0003
Revises: 20261014_0002
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261016_0003"
down_revision: str | None = "20261014_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE payments SET status = lower(status)")


def downgrade() -> None:
    op.execute("UPDATE payments SET status = upper(status)")
