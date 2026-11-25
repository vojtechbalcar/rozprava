"""Schema behaviour against PostgreSQL: migrations, natural keys and normalized search."""

import datetime as dt

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from rozprava import models
from tests import factories
from tests.conftest import alembic_config, reset_schema


def test_migrations_build_the_model_schema_from_empty_and_back(connection: Connection):
    reset_schema(connection)
    config = alembic_config(connection)
    command.upgrade(config, "head")
    tables = set(inspect(connection).get_table_names())
    assert set(models.Base.metadata.tables) <= tables
    head = ScriptDirectory.from_config(config).get_current_head()
    assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == head

    command.downgrade(config, "base")
    assert set(inspect(connection).get_table_names()) <= {"alembic_version"}
    command.upgrade(config, "head")  # repeatable after a full downgrade
    assert set(models.Base.metadata.tables) <= set(inspect(connection).get_table_names())


def test_search_dictionary_preserves_phrase_positions(db: Session):
    row = db.execute(
        text("""
        SELECT to_tsvector('rozprava', 'důchodová reforma')
          @@ websearch_to_tsquery('rozprava', '"duchodova reforma"')
    """)
    ).scalar_one()
    assert row is True


@pytest.mark.parametrize(
    ("document", "query", "matches"),
    [
        ("Důchodová reforma", "DUCHODOVA", True),
        ("důchodová reforma", '"reforma duchodova"', False),  # word order matters in phrases
        ("Penzijní spoření a důchody", "penzijni -duchody", False),
        ("Penzijní spoření", "duchody OR sporeni", True),
        ("spoření", "spořit", False),  # no stemming is claimed
    ],
)
def test_search_is_accent_and_case_insensitive_without_stemming(
    db: Session, document: str, query: str, matches: bool
):
    result = db.execute(
        text("SELECT to_tsvector('rozprava', :d) @@ websearch_to_tsquery('rozprava', :q)"),
        {"d": document, "q": query},
    ).scalar_one()
    assert result is matches


def test_source_pages_are_unique_per_term_sitting_and_page(db: Session):
    factories.source_page(db, id=33716, page=644)
    factories.source_page(db, id=5435, page=644, term_number=9)  # same numbers, other term
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            factories.source_page(db, id=99999, page=644)


def test_bill_numbers_repeat_across_terms(db: Session):
    nine, ten = factories.term(db, 9), factories.term(db, 10)
    db.add_all(
        [
            models.Bill(id=1, term_id=nine.id, number=285, short_title="Ninth-term tisk 285"),
            models.Bill(id=43407, term_id=ten.id, number=285, short_title="Penzijní spoření"),
        ]
    )
    db.flush()
    found = db.scalars(
        select(models.Bill.short_title).where(
            models.Bill.term_id == ten.id, models.Bill.number == 285
        )
    ).all()
    assert found == ["Penzijní spoření"]


def test_speech_revision_search_vector_is_generated_from_stored_text(db: Session):
    page = factories.source_page(db, id=33716, page=644)
    speech = models.Speech(term_id=page.term_id, sitting_number=34, page=644, anchor=2)
    db.add(speech)
    db.flush()
    revision = models.SpeechRevision(
        speech_id=speech.id,
        content_sha256="0" * 64,
        term_id=page.term_id,
        date=dt.date(2026, 11, 6),
        role="unknown",  # speaker not resolved: allowed
        first_page=644,
        last_page=644,
        stage="draft",
        words=4,
        text="Zavádí automatickou účast v penzijním spoření.",
    )
    db.add(revision)
    db.flush()
    hit = db.scalar(
        select(models.SpeechRevision.id).where(
            text("search @@ websearch_to_tsquery('rozprava', :q)").bindparams(
                q='"automatickou ucast"'
            )
        )
    )
    assert hit == revision.id
    with pytest.raises(IntegrityError):  # the same content is one revision, not two
        with db.begin_nested():
            db.add(
                models.SpeechRevision(
                    **{
                        c: getattr(revision, c)
                        for c in (
                            "speech_id content_sha256 term_id date role first_page "
                            "last_page stage words text"
                        ).split()
                    }
                )
            )
