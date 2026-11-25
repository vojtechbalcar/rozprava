"""Keep word_form small while tagging updates its counts after every batch.

The first full tagging run updated the same common form/lemma pairs in every
batch. Autovacuum fell behind: 175,000 live rows carried 2.3 million dead ones
and the upsert slowed from 0.7 to 4.8 seconds per batch. Free space on each
page lets PostgreSQL update a count in place (a HOT update, since count is not
indexed), and vacuuming at 2 % dead rows instead of 20 % keeps up.

Revision ID: 0004
Revises: 0003
Created: 2026-11-19
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE word_form SET (fillfactor = 50, autovacuum_vacuum_scale_factor = 0.02, "
        "autovacuum_analyze_scale_factor = 0.05)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE word_form RESET (fillfactor, autovacuum_vacuum_scale_factor, "
        "autovacuum_analyze_scale_factor)"
    )
