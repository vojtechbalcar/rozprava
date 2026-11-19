"""Coverage and MP activity against PostgreSQL, including unknown source data."""

import datetime as dt

import pytest
from sqlalchemy import func, select

from rozprava import models
from rozprava.ingest import metadata
from rozprava.queries import activity, archive, common, people
from tests import factories

DAY = dt.date(2026, 11, 6)


@pytest.fixture
def member(db):
    factories.term(db)
    factories.person(db, 1, "Jan", "Novák")
    mandate = models.Mandate(
        id=1,
        person_id=1,
        term_id=174,
        valid_from=dt.datetime(2026, 11, 6, 10),
        valid_to=dt.datetime(2026, 11, 6, 18),
    )
    db.add(mandate)
    db.add(models.SittingDay(term_id=174, sitting_number=1, day_number=1, date=DAY))
    db.flush()
    return mandate


def vote(db, id, code=None, **values):
    db.add(
        models.Vote(
            id=id,
            term_id=174,
            sitting_number=1,
            number=id,
            held_at=values.pop("held_at", dt.datetime(2026, 11, 6, 12)),
            kind=values.pop("kind", "N"),
            result="A",
            **values,
        )
    )
    db.flush()
    if code is not None:
        db.add(models.VoteRecord(vote_id=id, mandate_id=1, code=code))
    db.flush()


def test_vote_codes_and_eligibility(db, member):
    for id, code in enumerate("ABNCFK@MW", 1):
        vote(db, id, code)
    vote(db, 20, "@", invalidated=True)
    vote(db, 21, "@", kind="R")
    vote(db, 22, "@", kind="E")
    vote(db, 23, "@", held_at=dt.datetime(2026, 11, 6, 9, 59))
    vote(db, 24, "@", held_at=dt.datetime(2026, 11, 6, 18, 1))
    result = activity.term_activity(db, 174)
    p = result.participation[1]
    assert (p.registered, p.absent, p.unknown, p.percent) == (6, 2, 0, 75)
    assert result.day_view(1, DAY)["state"] == "present"
    assert result.day_view(1, DAY)["votes_total"] == 8


@pytest.mark.parametrize("code", [None, "?", "W"])
def test_unknown_and_ineligible_votes_never_imply_absence(db, member, code):
    vote(db, 1, code)
    result = activity.term_activity(db, 174)
    assert result.participation[1].percent is None
    assert result.day_view(1, DAY)["state"] == "unknown"


def test_missing_vote_suppresses_percentage_even_with_known_registration(db, member):
    vote(db, 1, "A")
    vote(db, 2)
    result = activity.term_activity(db, 174)
    assert result.participation[1].percent is None
    assert result.participation[1].unknown == 1
    assert result.day_view(1, DAY)["state"] == "present"
    profile = people.profile(db, common.terms(db)[10], 1, result)
    assert profile and profile["stats"]["median_attendance"] is None


def test_absence_requires_all_eligible_votes_known(db, member):
    vote(db, 1, "@")
    vote(db, 2, "M")
    result = activity.term_activity(db, 174)
    assert result.participation[1].percent == 0
    assert result.day_view(1, DAY)["state"] == "absent"


def test_empty_and_pending_coverage_is_not_complete(db, member):
    assert archive.home(db, dt.datetime.now(dt.UTC))["last_day"] is None
    assert archive.coverage(db)[0]["complete"] is False
    assert activity.term_activity(db, 174).provisional
    for id, status in enumerate(("pending", "failed", "unavailable"), 1):
        factories.source_page(db, id, id, sitting=1, status=status, day_number=1)
    coverage = archive.coverage(db)[0]
    assert (
        coverage["expected"],
        coverage["pending"],
        coverage["failed"],
        coverage["unavailable"],
    ) == (3, 1, 1, 1)
    assert not coverage["complete"]
    result = activity.term_activity(db, 174)
    assert not result.day_view(1, DAY)["complete"]
    assert result.day_view(1, DAY)["state"] == "unknown"


def test_sitting_without_day_metadata_remains_addressable(db, member):
    db.add(models.Sitting(id=2, term_id=174, number=2))
    db.flush()
    view = archive.sittings(db, common.terms(db)[10])
    sitting = next(s for s in view if s["number"] == 2)
    assert sitting["from"] is None and sitting["to"] is None
    assert sitting["days"] == 0 and sitting["day_levels"] == []


def test_activity_uses_current_nonchair_mp_words_and_one_term_scale(db, member):
    for id in range(2, 6):
        factories.person(db, id, "Osoba", str(id))
        if id < 5:
            db.add(models.Mandate(id=id, person_id=id, term_id=174))
    db.flush()
    for id, person, words, role, retired in (
        (1, 1, 10, "speaker", False),
        (2, 2, 20, "speaker", False),
        (3, 3, 30, "unknown", False),
        (4, 4, 40, "speaker", False),
        (5, 1, 1000, "chair", False),
        (6, 1, 1000, "speaker", True),
        (7, 5, 1000, "speaker", False),
        (8, 1, 1000, "speaker", False),  # spoke as a non-MP after the mandate ended
    ):
        db.add(models.Speech(id=id, term_id=174, sitting_number=1, page=1, anchor=id))
        db.flush()
        db.add(
            models.SpeechRevision(
                speech_id=id,
                content_sha256=str(id),
                term_id=174,
                date=DAY + dt.timedelta(days=1) if id == 8 else DAY,
                person_id=person,
                role=role,
                first_page=1,
                last_page=2,
                stage="final",
                words=words,
                text="Text.",
                retired_at=dt.datetime.now(dt.UTC) if retired else None,
            )
        )
    db.flush()
    result = activity.term_activity(db, 174)
    assert result.words == {1: 10, 2: 20, 3: 30, 4: 40}
    assert result.speeches[1] == 1
    assert [result.day_view(p, DAY)["level"] for p in range(1, 5)] == [1, 2, 3, 4]


def test_home_sample_is_hourly_and_source_backed(db, corpus):
    now = dt.datetime(2026, 11, 18, 12, tzinfo=dt.UTC)
    first = archive.home(db, now)
    second = archive.home(db, now + dt.timedelta(minutes=59))
    assert first["featured"] == second["featured"]
    featured = first["featured"]
    assert featured
    stored = db.get(models.SpeechRevision, featured["revision"])
    assert stored and stored.words >= 60 and featured["text"] in stored.text
    assert stored.role != "chair"


def unl(*rows):
    return "\n".join("|".join(map(str, row)) + "|" for row in rows).encode("cp1250")


def vote_row(id, title="Hlasování"):
    return (id, 174, 1, id, 1, "06.11.2026", "12:00", 0, 0, 0, 0, 0, 0, "N", "A", title, "")


def test_vote_import_replaces_changed_and_removed_records_and_apologies(db, member):
    tables = metadata.vote_tables(
        {
            "hl2025s.unl": unl(vote_row(1), vote_row(2)),
            "hl2025h1.unl": unl((1, 1, "A")),
            "hl2025h10.unl": unl((1, 2, "M"), (999, 2, "A")),
            "zmatecne.unl": unl((2,)),
            "omluvy.unl": unl((174, 1, "06.11.2026", "10:00", "11:00")),
            "hl2025h.unl": b"not a records table",
        }
    )
    metadata.import_votes(db, 174, tables)
    metadata.import_votes(db, 174, tables)
    assert db.scalar(select(func.count()).select_from(models.VoteRecord)) == 2
    assert db.scalar(select(models.Vote.invalidated).where(models.Vote.id == 2))
    assert db.scalar(select(func.count()).select_from(models.Apology)) == 1
    tables.update(votes=[unl(vote_row(1, "Oprava"))], records=[unl((1, 1, "B"))], apologies=[])
    metadata.import_votes(db, 174, tables)
    assert db.scalar(select(func.count()).select_from(models.Vote)) == 1
    assert db.scalar(select(models.Vote.title)) == "Oprava"
    assert db.scalar(select(models.VoteRecord.code)) == "B"
    assert db.scalar(select(func.count()).select_from(models.Apology)) == 0


def test_incomplete_vote_dump_cannot_erase_previous_import(db, member):
    vote(db, 1, "A")
    with pytest.raises(ValueError, match="missing"):
        metadata.import_votes(db, 174, metadata.vote_tables({"omluvy.unl": b""}))
    assert db.scalar(select(models.VoteRecord.code)) == "A"


def test_failed_vote_import_rolls_back_replacement(db, member):
    vote(db, 1, "A")
    tables = metadata.vote_tables(
        {
            "hl2025s.unl": unl(vote_row(2)),
            "hl2025h1.unl": unl((1, 2, "AB")),
        }
    )
    with pytest.raises(ValueError, match="Invalid vote record"):
        with db.begin_nested():
            metadata.import_votes(db, 174, tables)
    assert db.scalar(select(models.Vote.id)) == 1
    assert db.scalar(select(models.VoteRecord.code)) == "A"
