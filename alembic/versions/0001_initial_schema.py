"""Initial schema, accent-insensitive search configuration and indexes.

Revision ID: 0001
Revises:
Created: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Search: lowercase and strip accents, no stemming, so "duchodova" finds "důchodová"
# and quoted phrases keep their word positions. Queries must use the same config.
SEARCH_CONFIG = """
CREATE TEXT SEARCH CONFIGURATION rozprava (COPY = simple);
ALTER TEXT SEARCH CONFIGURATION rozprava
    ALTER MAPPING FOR hword, hword_part, word WITH unaccent, simple;
"""

# Two tables point at each other (current revision); add those keys after both exist.
CURRENT_REVISION_KEYS = [
    ("source_page", "page_revision"),
    ("speech", "speech_revision"),
]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.execute(SEARCH_CONFIG)
    op.create_table(
        "import_run",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("command", sa.String(length=32), nullable=False),
        sa.Column("arguments", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("pid", sa.Integer(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("counts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed', 'interrupted')",
            name=op.f("ck_import_run_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_run")),
    )
    op.create_table(
        "organization",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("type_id", sa.Integer(), nullable=False),
        sa.Column("abbr", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organization")),
    )
    op.create_index(op.f("ix_organization_parent_id"), "organization", ["parent_id"], unique=False)
    op.create_index(op.f("ix_organization_type_id"), "organization", ["type_id"], unique=False)
    op.create_table(
        "person",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("title_before", sa.Text(), nullable=False),
        sa.Column("forename", sa.Text(), nullable=False),
        sa.Column("surname", sa.Text(), nullable=False),
        sa.Column("title_after", sa.Text(), nullable=False),
        sa.Column("born_on", sa.Date(), nullable=True),
        sa.Column("died_on", sa.Date(), nullable=True),
        sa.Column("sex", sa.String(length=1), nullable=True),
        sa.CheckConstraint("sex IN ('M', 'F')", name=op.f("ck_person_sex")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_person")),
    )
    op.create_index(op.f("ix_person_surname"), "person", ["surname"], unique=False)
    op.create_table(
        "source_file",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_modified", sa.Text(), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_file")),
        sa.UniqueConstraint("name", "sha256", name=op.f("uq_source_file_name_sha256")),
    )
    op.create_table(
        "term",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("number", sa.SmallInteger(), nullable=False),
        sa.Column("year", sa.SmallInteger(), nullable=False),
        sa.Column("started_on", sa.Date(), nullable=False),
        sa.Column("ended_on", sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_term")),
        sa.UniqueConstraint("number", name=op.f("uq_term_number")),
    )
    op.create_table(
        "bill",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("term_id", sa.Integer(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("sub_number", sa.Integer(), nullable=False),
        sa.Column("kind_id", sa.Integer(), nullable=True),
        sa.Column("short_title", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("proposer", sa.Text(), nullable=False),
        sa.Column("submitted_on", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["term_id"], ["term.id"], name=op.f("fk_bill_term_id_term")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bill")),
    )
    op.create_index("ix_bill_term_number", "bill", ["term_id", "number"], unique=False)
    op.create_table(
        "mandate",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("term_id", sa.Integer(), nullable=False),
        sa.Column("region_id", sa.Integer(), nullable=True),
        sa.Column("list_id", sa.Integer(), nullable=True),
        sa.Column("valid_from", sa.DateTime(), nullable=True),
        sa.Column("valid_to", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["person_id"], ["person.id"], name=op.f("fk_mandate_person_id_person")
        ),
        sa.ForeignKeyConstraint(
            ["region_id"], ["organization.id"], name=op.f("fk_mandate_region_id_organization")
        ),
        sa.ForeignKeyConstraint(["term_id"], ["term.id"], name=op.f("fk_mandate_term_id_term")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mandate")),
        sa.UniqueConstraint("term_id", "person_id", name=op.f("uq_mandate_term_id_person_id")),
    )
    op.create_index(op.f("ix_mandate_person_id"), "mandate", ["person_id"], unique=False)
    op.create_table(
        "membership",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("valid_from", sa.DateTime(), nullable=False),
        sa.Column("valid_to", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.id"],
            name=op.f("fk_membership_organization_id_organization"),
        ),
        sa.ForeignKeyConstraint(
            ["person_id"], ["person.id"], name=op.f("fk_membership_person_id_person")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_membership")),
        sa.UniqueConstraint(
            "person_id",
            "organization_id",
            "valid_from",
            name=op.f("uq_membership_person_id_organization_id_valid_from"),
        ),
    )
    op.create_index(
        op.f("ix_membership_organization_id"), "membership", ["organization_id"], unique=False
    )
    op.create_index(
        "ix_membership_person_from", "membership", ["person_id", "valid_from"], unique=False
    )
    op.create_table(
        "sitting",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("term_id", sa.Integer(), nullable=False),
        sa.Column("number", sa.SmallInteger(), nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=True),
        sa.Column("ends_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["term_id"], ["term.id"], name=op.f("fk_sitting_term_id_term")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sitting")),
        sa.UniqueConstraint("term_id", "number", name=op.f("uq_sitting_term_id_number")),
    )
    op.create_table(
        "sitting_day",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("term_id", sa.Integer(), nullable=False),
        sa.Column("sitting_number", sa.SmallInteger(), nullable=False),
        sa.Column("day_number", sa.SmallInteger(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(["term_id"], ["term.id"], name=op.f("fk_sitting_day_term_id_term")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sitting_day")),
        sa.UniqueConstraint(
            "term_id",
            "sitting_number",
            "day_number",
            name=op.f("uq_sitting_day_term_id_sitting_number_day_number"),
        ),
    )
    op.create_index(op.f("ix_sitting_day_date"), "sitting_day", ["date"], unique=False)
    op.create_table(
        "source_page",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("term_id", sa.Integer(), nullable=False),
        sa.Column("sitting_number", sa.SmallInteger(), nullable=False),
        sa.Column("page", sa.SmallInteger(), nullable=False),
        sa.Column("day_number", sa.SmallInteger(), nullable=True),
        sa.Column("date", sa.Date(), nullable=True),
        sa.Column("start_minute", sa.SmallInteger(), nullable=True),
        sa.Column("end_minute", sa.SmallInteger(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("unavailable_reason", sa.Text(), nullable=True),
        sa.Column("attempts", sa.SmallInteger(), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("current_revision_id", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'imported', 'failed', 'unavailable')",
            name=op.f("ck_source_page_status"),
        ),
        sa.ForeignKeyConstraint(["term_id"], ["term.id"], name=op.f("fk_source_page_term_id_term")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_page")),
        sa.UniqueConstraint(
            "term_id",
            "sitting_number",
            "page",
            name=op.f("uq_source_page_term_id_sitting_number_page"),
        ),
    )
    op.create_index(op.f("ix_source_page_status"), "source_page", ["status"], unique=False)
    op.create_table(
        "speech",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("term_id", sa.Integer(), nullable=False),
        sa.Column("sitting_number", sa.SmallInteger(), nullable=False),
        sa.Column("page", sa.SmallInteger(), nullable=False),
        sa.Column("anchor", sa.SmallInteger(), nullable=False),
        sa.Column("current_revision_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["term_id"], ["term.id"], name=op.f("fk_speech_term_id_term")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_speech")),
        sa.UniqueConstraint(
            "term_id",
            "sitting_number",
            "page",
            "anchor",
            name=op.f("uq_speech_term_id_sitting_number_page_anchor"),
        ),
    )
    op.create_table(
        "vote",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("term_id", sa.Integer(), nullable=False),
        sa.Column("sitting_number", sa.SmallInteger(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("agenda_number", sa.Integer(), nullable=True),
        sa.Column("held_at", sa.DateTime(), nullable=False),
        sa.Column("kind", sa.String(length=1), nullable=False),
        sa.Column("result", sa.String(length=1), nullable=False),
        sa.Column("invalidated", sa.Boolean(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("short_title", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["term_id"], ["term.id"], name=op.f("fk_vote_term_id_term")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vote")),
        sa.UniqueConstraint(
            "term_id",
            "sitting_number",
            "number",
            name=op.f("uq_vote_term_id_sitting_number_number"),
        ),
    )
    op.create_index(op.f("ix_vote_held_at"), "vote", ["held_at"], unique=False)
    op.create_table(
        "agenda_item",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("sitting_id", sa.Integer(), nullable=False),
        sa.Column("bill_id", sa.Integer(), nullable=True),
        sa.Column("number", sa.Integer(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("title_suffix", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("state_id", sa.SmallInteger(), nullable=True),
        sa.ForeignKeyConstraint(["bill_id"], ["bill.id"], name=op.f("fk_agenda_item_bill_id_bill")),
        sa.ForeignKeyConstraint(
            ["sitting_id"], ["sitting.id"], name=op.f("fk_agenda_item_sitting_id_sitting")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agenda_item")),
    )
    op.create_index(op.f("ix_agenda_item_bill_id"), "agenda_item", ["bill_id"], unique=False)
    op.create_index(op.f("ix_agenda_item_sitting_id"), "agenda_item", ["sitting_id"], unique=False)
    op.create_table(
        "apology",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("term_id", sa.Integer(), nullable=False),
        sa.Column("mandate_id", sa.Integer(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("from_time", sa.String(length=5), nullable=True),
        sa.Column("to_time", sa.String(length=5), nullable=True),
        sa.ForeignKeyConstraint(
            ["mandate_id"], ["mandate.id"], name=op.f("fk_apology_mandate_id_mandate")
        ),
        sa.ForeignKeyConstraint(["term_id"], ["term.id"], name=op.f("fk_apology_term_id_term")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_apology")),
    )
    op.create_index(op.f("ix_apology_mandate_id"), "apology", ["mandate_id"], unique=False)
    op.create_table(
        "page_agenda",
        sa.Column("source_page_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("agenda_item_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["source_page_id"],
            ["source_page.id"],
            name=op.f("fk_page_agenda_source_page_id_source_page"),
        ),
        sa.PrimaryKeyConstraint("source_page_id", "position", name=op.f("pk_page_agenda")),
    )
    op.create_table(
        "page_revision",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_page_id", sa.Integer(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_sha256", sa.String(length=64), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("stage", sa.String(length=8), nullable=False),
        sa.Column("status_line", sa.Text(), nullable=True),
        sa.Column("time_label", sa.Text(), nullable=True),
        sa.Column("parser_version", sa.SmallInteger(), nullable=False),
        sa.CheckConstraint(
            "stage IN ('draft', 'edited', 'final')", name=op.f("ck_page_revision_stage")
        ),
        sa.ForeignKeyConstraint(
            ["source_page_id"],
            ["source_page.id"],
            name=op.f("fk_page_revision_source_page_id_source_page"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_page_revision")),
        sa.UniqueConstraint(
            "source_page_id",
            "content_sha256",
            name=op.f("uq_page_revision_source_page_id_content_sha256"),
        ),
    )
    op.create_table(
        "transcript_index_entry",
        sa.Column("source_page_id", sa.Integer(), nullable=False),
        sa.Column("anchor", sa.SmallInteger(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=True),
        sa.Column("agenda_item_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.SmallInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["source_page_id"],
            ["source_page.id"],
            name=op.f("fk_transcript_index_entry_source_page_id_source_page"),
        ),
        sa.PrimaryKeyConstraint("source_page_id", "anchor", name=op.f("pk_transcript_index_entry")),
    )
    op.create_table(
        "vote_record",
        sa.Column("vote_id", sa.Integer(), nullable=False),
        sa.Column("mandate_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=1), nullable=False),
        sa.ForeignKeyConstraint(
            ["mandate_id"], ["mandate.id"], name=op.f("fk_vote_record_mandate_id_mandate")
        ),
        sa.ForeignKeyConstraint(["vote_id"], ["vote.id"], name=op.f("fk_vote_record_vote_id_vote")),
        sa.PrimaryKeyConstraint("vote_id", "mandate_id", name=op.f("pk_vote_record")),
    )
    op.create_index(op.f("ix_vote_record_mandate_id"), "vote_record", ["mandate_id"], unique=False)
    op.create_table(
        "page_segment",
        sa.Column("revision_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("anchor", sa.SmallInteger(), nullable=True),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("link_person_id", sa.Integer(), nullable=True),
        sa.Column("link_url", sa.Text(), nullable=True),
        sa.Column("paragraphs", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["revision_id"],
            ["page_revision.id"],
            name=op.f("fk_page_segment_revision_id_page_revision"),
        ),
        sa.PrimaryKeyConstraint("revision_id", "position", name=op.f("pk_page_segment")),
    )
    op.create_table(
        "speech_revision",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("speech_id", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("term_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=True),
        sa.Column("person_id", sa.Integer(), nullable=True),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("role", sa.String(length=8), nullable=False),
        sa.Column("agenda_item_id", sa.Integer(), nullable=True),
        sa.Column("first_page", sa.SmallInteger(), nullable=False),
        sa.Column("last_page", sa.SmallInteger(), nullable=False),
        sa.Column("incomplete", sa.Boolean(), nullable=False),
        sa.Column("stage", sa.String(length=8), nullable=False),
        sa.Column("words", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "search",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('rozprava'::regconfig, text)", persisted=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('speaker', 'chair', 'unknown')", name=op.f("ck_speech_revision_role")
        ),
        sa.CheckConstraint(
            "stage IN ('draft', 'edited', 'final')", name=op.f("ck_speech_revision_stage")
        ),
        sa.ForeignKeyConstraint(
            ["agenda_item_id"],
            ["agenda_item.id"],
            name=op.f("fk_speech_revision_agenda_item_id_agenda_item"),
        ),
        sa.ForeignKeyConstraint(
            ["person_id"], ["person.id"], name=op.f("fk_speech_revision_person_id_person")
        ),
        sa.ForeignKeyConstraint(
            ["speech_id"], ["speech.id"], name=op.f("fk_speech_revision_speech_id_speech")
        ),
        sa.ForeignKeyConstraint(
            ["term_id"], ["term.id"], name=op.f("fk_speech_revision_term_id_term")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_speech_revision")),
        sa.UniqueConstraint(
            "speech_id", "content_sha256", name=op.f("uq_speech_revision_speech_id_content_sha256")
        ),
    )
    op.create_index(
        "ix_speech_revision_current_date",
        "speech_revision",
        ["date", "id"],
        unique=False,
        postgresql_where="retired_at IS NULL",
    )
    op.create_index(
        "ix_speech_revision_current_person",
        "speech_revision",
        ["person_id", "date"],
        unique=False,
        postgresql_where="retired_at IS NULL",
    )
    op.create_index(
        "ix_speech_revision_search_current",
        "speech_revision",
        ["search"],
        unique=False,
        postgresql_using="gin",
        postgresql_where="retired_at IS NULL",
    )
    op.create_index(
        op.f("ix_speech_revision_speech_id"), "speech_revision", ["speech_id"], unique=False
    )
    op.create_table(
        "speech_paragraph",
        sa.Column("revision_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("page_revision_id", sa.Integer(), nullable=False),
        sa.Column("page", sa.SmallInteger(), nullable=False),
        sa.Column("segment_position", sa.SmallInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["page_revision_id"],
            ["page_revision.id"],
            name=op.f("fk_speech_paragraph_page_revision_id_page_revision"),
        ),
        sa.ForeignKeyConstraint(
            ["revision_id"],
            ["speech_revision.id"],
            name=op.f("fk_speech_paragraph_revision_id_speech_revision"),
        ),
        sa.PrimaryKeyConstraint("revision_id", "position", name=op.f("pk_speech_paragraph")),
    )
    for table, target in CURRENT_REVISION_KEYS:
        op.create_foreign_key(
            op.f(f"fk_{table}_current_revision_id_{target}"),
            table,
            target,
            ["current_revision_id"],
            ["id"],
        )


def downgrade() -> None:
    for table, target in CURRENT_REVISION_KEYS:
        op.drop_constraint(op.f(f"fk_{table}_current_revision_id_{target}"), table)
    op.drop_table("speech_paragraph")
    op.drop_index(op.f("ix_speech_revision_speech_id"), table_name="speech_revision")
    op.drop_index(
        "ix_speech_revision_search_current",
        table_name="speech_revision",
        postgresql_using="gin",
        postgresql_where="retired_at IS NULL",
    )
    op.drop_index(
        "ix_speech_revision_current_person",
        table_name="speech_revision",
        postgresql_where="retired_at IS NULL",
    )
    op.drop_index(
        "ix_speech_revision_current_date",
        table_name="speech_revision",
        postgresql_where="retired_at IS NULL",
    )
    op.drop_table("speech_revision")
    op.drop_table("page_segment")
    op.drop_index(op.f("ix_vote_record_mandate_id"), table_name="vote_record")
    op.drop_table("vote_record")
    op.drop_table("transcript_index_entry")
    op.drop_table("page_revision")
    op.drop_table("page_agenda")
    op.drop_index(op.f("ix_apology_mandate_id"), table_name="apology")
    op.drop_table("apology")
    op.drop_index(op.f("ix_agenda_item_sitting_id"), table_name="agenda_item")
    op.drop_index(op.f("ix_agenda_item_bill_id"), table_name="agenda_item")
    op.drop_table("agenda_item")
    op.drop_index(op.f("ix_vote_held_at"), table_name="vote")
    op.drop_table("vote")
    op.drop_table("speech")
    op.drop_index(op.f("ix_source_page_status"), table_name="source_page")
    op.drop_table("source_page")
    op.drop_index(op.f("ix_sitting_day_date"), table_name="sitting_day")
    op.drop_table("sitting_day")
    op.drop_table("sitting")
    op.drop_index("ix_membership_person_from", table_name="membership")
    op.drop_index(op.f("ix_membership_organization_id"), table_name="membership")
    op.drop_table("membership")
    op.drop_index(op.f("ix_mandate_person_id"), table_name="mandate")
    op.drop_table("mandate")
    op.drop_index("ix_bill_term_number", table_name="bill")
    op.drop_table("bill")
    op.drop_table("term")
    op.drop_table("source_file")
    op.drop_index(op.f("ix_person_surname"), table_name="person")
    op.drop_table("person")
    op.drop_index(op.f("ix_organization_type_id"), table_name="organization")
    op.drop_index(op.f("ix_organization_parent_id"), table_name="organization")
    op.drop_table("organization")
    op.drop_table("import_run")
    op.execute("DROP TEXT SEARCH CONFIGURATION rozprava")
    op.execute("DROP EXTENSION unaccent")
