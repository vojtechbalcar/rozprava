"""Track speech assembly, continuation markers, headings and attribution evidence.

Revision ID: 0002
Revises: 0001
Created: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("page_revision", sa.Column("continues", sa.Text(), nullable=True))
    op.add_column(
        "page_segment",
        sa.Column("heading", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("source_page", sa.Column("assembled_revision_id", sa.Integer(), nullable=True))
    op.add_column("source_page", sa.Column("index_digest", sa.String(length=64), nullable=True))
    op.create_foreign_key(
        op.f("fk_source_page_assembled_revision_id_page_revision"),
        "source_page",
        "page_revision",
        ["assembled_revision_id"],
        ["id"],
    )
    op.add_column("speech_revision", sa.Column("attribution", sa.String(length=8), nullable=True))


def downgrade() -> None:
    op.drop_column("page_segment", "heading")
    op.drop_column("page_revision", "continues")
    op.drop_column("speech_revision", "attribution")
    op.drop_constraint(
        op.f("fk_source_page_assembled_revision_id_page_revision"),
        "source_page",
        type_="foreignkey",
    )
    op.drop_column("source_page", "index_digest")
    op.drop_column("source_page", "assembled_revision_id")
