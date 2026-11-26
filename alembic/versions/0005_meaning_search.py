"""Meaning search: embedded speech chunks, cached query embeddings and AI usage.

pgvector is not a trusted extension, so the application role cannot create it.
`scripts/local_db.py vectors` (also part of `init`) installs it as the cluster
administrator in the `extensions` schema and adds that schema to the search path.

Revision ID: 0005
Revises: 0004
Created: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


class HalfVector(sa.types.UserDefinedType):
    cache_ok = True

    def get_col_spec(self, **kw) -> str:
        return "halfvec(1024)"


def upgrade() -> None:
    installed = sa.text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
    if not op.get_bind().execute(installed).first():
        raise RuntimeError(
            "pgvector is missing in this database. Run `brew install pgvector` and "
            "`uv run python scripts/local_db.py vectors`, then migrate again."
        )
    op.create_table(
        "speech_chunk",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("revision_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("first_paragraph", sa.SmallInteger(), nullable=False),
        sa.Column("last_paragraph", sa.SmallInteger(), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("embedding", HalfVector(), nullable=False),
        sa.ForeignKeyConstraint(
            ["revision_id"],
            ["speech_revision.id"],
            name=op.f("fk_speech_chunk_revision_id_speech_revision"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_speech_chunk")),
        sa.UniqueConstraint(
            "revision_id", "position", name=op.f("uq_speech_chunk_revision_id_position")
        ),
    )
    op.create_index("ix_speech_chunk_revision_id", "speech_chunk", ["revision_id"])
    op.create_index("ix_speech_chunk_digest", "speech_chunk", ["digest"])
    op.execute(
        "CREATE INDEX ix_speech_chunk_embedding ON speech_chunk "
        "USING hnsw (embedding halfvec_cosine_ops)"
    )
    op.create_table(
        "query_embedding",
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("embedding", HalfVector(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("model", "query", name=op.f("pk_query_embedding")),
    )
    op.create_table(
        "ai_usage",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_usage")),
    )
    op.create_index("ix_ai_usage_created_at", "ai_usage", ["created_at"])


def downgrade() -> None:
    op.drop_table("ai_usage")
    op.drop_table("query_embedding")
    op.drop_table("speech_chunk")
