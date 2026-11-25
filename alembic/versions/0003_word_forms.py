"""Index Czech word forms: lemma lexemes in the search vector and form statistics.

The generated search column cannot change its expression in place, so it is
dropped and added again; PostgreSQL recomputes it for every row and the GIN index
is rebuilt. Lemma lexemes stay empty until `python -m rozprava.ingest forms` runs.

Revision ID: 0003
Revises: 0002
Created: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EXACT = "to_tsvector('rozprava'::regconfig, text)"
WITH_FORMS = f"{EXACT} || coalesce(forms, ''::tsvector)"


def _replace_search(expression: str) -> None:
    op.drop_index("ix_speech_revision_search_current", table_name="speech_revision")
    op.drop_column("speech_revision", "search")
    op.add_column(
        "speech_revision",
        sa.Column(
            "search",
            postgresql.TSVECTOR(),
            sa.Computed(expression, persisted=True),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_speech_revision_search_current",
        "speech_revision",
        ["search"],
        unique=False,
        postgresql_using="gin",
        postgresql_where="retired_at IS NULL",
    )


def upgrade() -> None:
    op.add_column("speech_revision", sa.Column("forms", postgresql.TSVECTOR(), nullable=True))
    op.add_column("speech_revision", sa.Column("forms_model", sa.String(length=64), nullable=True))
    _replace_search(WITH_FORMS)
    op.create_table(
        "word_form",
        sa.Column("form", sa.Text(), nullable=False),
        sa.Column("lemma", sa.Text(), nullable=False),
        sa.Column("folded", sa.Text(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("form", "lemma", name=op.f("pk_word_form")),
    )
    op.create_index(op.f("ix_word_form_folded"), "word_form", ["folded"], unique=False)
    op.create_index("ix_word_form_lemma", "word_form", ["lemma"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_word_form_lemma", table_name="word_form")
    op.drop_index(op.f("ix_word_form_folded"), table_name="word_form")
    op.drop_table("word_form")
    _replace_search(EXACT)
    op.drop_column("speech_revision", "forms_model")
    op.drop_column("speech_revision", "forms")
