"""Cached AI summaries of search results (queries/summary.py).

A summary is keyed by the model, prompt version, query and the exact speech
revisions and paragraphs it was given, so it is generated once and stays valid:
revisions are immutable.

Revision ID: 0006
Revises: 0005
Created: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "summary",
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("sentences", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_summary")),
    )


def downgrade() -> None:
    op.drop_table("summary")
