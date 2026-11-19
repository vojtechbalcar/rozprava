"""Metadata import, page revisions and speech assembly against PostgreSQL.

Pages come from the captured fixtures through a fake source; nothing is fetched.
"""

import datetime as dt
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from rozprava import models
from rozprava.ingest import metadata, store
from rozprava.ingest.fetch import TransientError
from rozprava.ingest.parser import UNANCHORED_BASE, parse_page
from rozprava.ingest.runner import ImportLocked, Runner, coverage, import_lock
from tests.psp_source import FIXTURE_PAGES, TABLES, FakeSource, fixture_url


@pytest.fixture
def source(tmp_path: Path) -> FakeSource:
    return FakeSource(tmp_path)


@pytest.fixture
def runner(sessions: sessionmaker[Session], source: FakeSource) -> Runner:
    runner = Runner(sessions, source)
    runner.metadata(lambda session: TABLES)
    return runner


def current(
    db: Session, term: int, sitting: int, page: int, anchor: int
) -> tuple[models.Speech, models.SpeechRevision]:
    speech = db.scalar(
        select(models.Speech).where(
            models.Speech.term_id == term,
            models.Speech.sitting_number == sitting,
            models.Speech.page == page,
            models.Speech.anchor == anchor,
        )
    )
    assert speech is not None and speech.current_revision_id is not None
    return speech, db.get_one(models.SpeechRevision, speech.current_revision_id)


def table_counts(db: Session) -> dict[str, int]:
    return {
        t.name: db.scalar(select(func.count()).select_from(t)) or 0
        for t in models.Base.metadata.sorted_tables
        if t.name not in ("import_run", "source_file")
    }


def test_metadata_import_is_idempotent_and_keyed_by_term(db: Session):
    metadata.import_metadata(db, TABLES)
    first = table_counts(db)
    metadata.import_metadata(db, TABLES)
    assert table_counts(db) == first

    bill = db.get_one(models.Bill, 43407)
    assert (bill.term_id, bill.number, bill.short_title) == (
        174,
        285,
        "Novela z. o doplňkovém penzijním spoření",
    )
    item = db.get_one(models.AgendaItem, 60222)
    assert item.bill_id == 43407 and item.number == 17
    day = db.scalar(
        select(models.SittingDay).where(
            models.SittingDay.term_id == 174,
            models.SittingDay.sitting_number == 34,
            models.SittingDay.day_number == 12,
        )
    )
    assert day is not None and day.date == dt.date(2026, 11, 6)
    vondrak = db.scalar(
        select(models.Mandate).where(
            models.Mandate.person_id == 6492, models.Mandate.term_id == 173
        )
    )
    assert vondrak is not None
    assert vondrak.valid_from == dt.datetime(2021, 10, 9, 14)
    assert vondrak.valid_to == dt.datetime(2025, 10, 8)
    assert db.get_one(models.Person, 6473).sex == "F"  # "Ž" in the source


def test_unchanged_reimport_does_not_duplicate(db: Session, source: FakeSource):
    metadata.import_metadata(db, TABLES)
    page = db.get_one(models.SourcePage, 33716)
    url = fixture_url("2025ps-s034644")
    first = store.store_page(db, page, source.get(url), parse_page(FIXTURE_PAGES[url]))
    second = store.store_page(db, page, source.get(url), parse_page(FIXTURE_PAGES[url]))
    assert first.id == second.id
    count = db.scalar(select(func.count()).where(models.PageRevision.source_page_id == page.id))
    assert count == 1


def test_backfill_imports_pages_and_attributes_speeches(runner: Runner, sessions):
    counts = runner.backfill(terms=[10])
    assert counts["imported"] == 6 and counts["failed"] == 0
    with sessions() as db:
        statuses = dict(
            db.execute(
                select(models.SourcePage.page, models.SourcePage.status).where(
                    models.SourcePage.term_id == 174, models.SourcePage.sitting_number == 34
                )
            ).all()
        )
        assert statuses[644] == "imported" and statuses[645] == "unavailable"
        _, richterova = current(db, 174, 34, 642, 2)
        assert (richterova.person_id, richterova.attribution, richterova.role) == (
            6473,
            "link",
            "speaker",
        )
        assert (richterova.first_page, richterova.last_page) == (642, 644)
        assert richterova.agenda_item_id == 60222 and richterova.stage == "draft"
        _, chair = current(db, 174, 34, 644, 1)
        assert (chair.person_id, chair.role) == (6418, "chair")
        _, minister = current(db, 174, 34, 648, 2)
        assert minister.person_id == 6545 and minister.attribution in ("index", "name")
        paragraphs = db.scalars(
            select(models.SpeechParagraph.page).where(
                models.SpeechParagraph.revision_id == richterova.id
            )
        ).all()
        assert set(paragraphs) == {642, 643, 644}
        # Searchable without accents, including words from every page of the speech.
        hit = db.scalar(
            select(models.SpeechRevision.id).where(
                models.SpeechRevision.retired_at.is_(None),
                models.SpeechRevision.search.op("@@")(
                    func.websearch_to_tsquery("rozprava", '"jednorazovych darecku"')
                ),
            )
        )
        assert hit == richterova.id
        assert coverage(db)[1]["imported"] == 6


def test_stale_speech_index_does_not_override_the_page(runner: Runner, sessions):
    runner.backfill(terms=[9])
    with sessions() as db:
        _, chair = current(db, 173, 50, 72, 1)
        assert (chair.person_id, chair.role, chair.agenda_item_id) == (6418, "chair", 49681)
        # rec says r2 is Blažek; the page says Skopeček (linked). Index rejected: no role.
        _, shifted = current(db, 173, 50, 72, 2)
        assert (shifted.person_id, shifted.attribution, shifted.role) == (6418, "link", "unknown")
        assert shifted.agenda_item_id is None
        _, minister = current(db, 173, 50, 71, UNANCHORED_BASE + 13)
        assert (minister.person_id, minister.attribution) == (6079, "name")
        assert (minister.first_page, minister.last_page) == (71, 72)


def test_changed_source_keeps_the_cited_revision(runner: Runner, source: FakeSource, sessions):
    runner.backfill(terms=[10])
    with sessions() as db:
        speech, old = current(db, 174, 34, 644, 2)
        old_id, old_text = old.id, old.text
    url = fixture_url("2025ps-s034644")
    source.pages[url] = (
        FIXTURE_PAGES[url]
        .replace(b'<p class="status invalid">', b'<p class="x">')
        .replace(
            "Proč na tom záleží?".encode("cp1250"), "Proč na tom tolik záleží?".encode("cp1250")
        )
    )
    counts = runner.refresh(terms=[10])
    assert counts["imported"] == 1 and counts["unchanged"] == 5
    with sessions() as db:
        _, new = current(db, 174, 34, 644, 2)
        assert new.id != old_id and "Proč na tom tolik záleží?" in new.text
        retired = db.get_one(models.SpeechRevision, old_id)
        assert retired.retired_at is not None and retired.text == old_text
        assert (
            db.scalar(select(func.count()).where(models.PageRevision.source_page_id == 33716)) == 2
        )


def test_interrupted_import_resumes_without_duplicates(
    runner: Runner, source: FakeSource, sessions
):
    def stop_at_644(url: str) -> None:
        if url.endswith("s034644.htm"):
            raise KeyboardInterrupt

    source.before = stop_at_644
    with pytest.raises(KeyboardInterrupt):
        runner.backfill(terms=[10])
    with sessions() as db:
        run = db.scalars(select(models.ImportRun).order_by(models.ImportRun.id.desc())).first()
        assert run is not None and run.status == "interrupted"
        assert db.get_one(models.SourcePage, 33715).status == "imported"  # page 643
        assert db.get_one(models.SourcePage, 33716).status == "pending"  # page 644
    source.before = None
    runner.backfill(terms=[10])
    runner.backfill(terms=[10])  # nothing left: a no-op
    with sessions() as db:
        speeches = db.scalar(
            select(func.count()).where(
                models.Speech.term_id == 174, models.Speech.sitting_number == 34
            )
        )
        revisions = db.scalar(
            select(func.count())
            .select_from(models.SpeechRevision)
            .join(models.Speech, models.Speech.id == models.SpeechRevision.speech_id)
            .where(models.Speech.sitting_number == 34, models.SpeechRevision.retired_at.is_(None))
        )
        assert speeches == revisions
        assert store.sittings_to_assemble(db) == []


def test_repaired_missing_page_rejoins_the_speech(runner: Runner, source: FakeSource, sessions):
    url = fixture_url("2025ps-s034643")
    source.errors[url] = TransientError("HTTP 503 after 4 attempts")
    runner.backfill(terms=[10])
    with sessions() as db:
        page = db.get_one(models.SourcePage, 33715)
        assert page.status == "failed" and page.current_revision_id is None  # retryable
        _, head = current(db, 174, 34, 642, 2)
        assert head.last_page == 642
        fragment, tail = current(db, 174, 34, 644, 0)
        assert tail.incomplete and tail.person_id == 6473 and tail.attribution == "name"
        fragment_revision = tail.id
    del source.errors[url]
    runner.backfill(terms=[10])  # failed pages are retried
    with sessions() as db:
        _, joined = current(db, 174, 34, 642, 2)
        assert (joined.first_page, joined.last_page) == (642, 644)
        fragment = db.get_one(models.Speech, fragment.id)
        assert fragment.current_revision_id is None
        assert db.get_one(models.SpeechRevision, fragment_revision).retired_at is not None


def test_only_one_import_runs_at_a_time(engine):
    with engine.connect() as first, engine.connect() as second:
        with import_lock(first):
            with pytest.raises(ImportLocked):
                with import_lock(second):
                    pass
        with import_lock(second):
            pass


@pytest.mark.parametrize("requeue", [False, True])
def test_retry_downloads_again_after_a_cached_parse_failure(sessions, tmp_path, requeue):
    class CachedSource(FakeSource):
        def get(self, url, refresh=False):
            cached = self.cache.latest(url)
            return cached if cached and not refresh else super().get(url, refresh)

    source = CachedSource(tmp_path)
    url = fixture_url("2025ps-s034643")
    source.pages[url] = b""
    runner = Runner(sessions, source)
    runner.metadata(lambda db: TABLES)
    runner.backfill(terms=[10])
    with sessions() as db:
        page = db.get_one(models.SourcePage, 33715)
        assert page.status == "failed" and "ParseError" in (page.last_error or "")
    source.pages[url] = FIXTURE_PAGES[url]
    if requeue:
        runner.retry(terms=[10])
    runner.backfill(terms=[10])
    with sessions() as db:
        page = db.get_one(models.SourcePage, 33715)
        assert page.status == "imported" and page.last_error is None
        _, joined = current(db, 174, 34, 642, 2)
        assert joined.last_page == 644
