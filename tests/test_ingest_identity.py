"""Speaker attribution and dated club membership, on real fixture records."""

import datetime as dt
from pathlib import Path

import pytest

from rozprava.ingest import unl
from rozprava.ingest.identity import (
    UNKNOWN_CLUB,
    ClubOnDate,
    People,
    PersonName,
    Spell,
    club_on,
    label_names,
)

OPENDATA = Path(__file__).parent / "fixtures/psp/opendata"
ANO_9, INDEPENDENT_9 = 1537, 1720


def table(name: str) -> list[list[str | None]]:
    return list(unl.rows((OPENDATA / name).read_bytes()))


@pytest.fixture(scope="module")
def people() -> People:
    return People(
        PersonName(int(r[0]), r[3] or "", r[2] or "")  # type: ignore[arg-type]
        for r in table("osoby.unl")
    )


def spells(person_id: int) -> list[Spell]:
    return [
        Spell(int(r[1]), unl.timestamp(r[3]), unl.timestamp(r[4]))  # type: ignore[arg-type]
        for r in table("zarazeni.unl")
        if r[0] == str(person_id)
    ]


def test_link_is_accepted_when_the_label_names_the_same_person(people: People):
    found = people.resolve("Poslanec Jan Papajanovský", link_person_id=7030)
    assert (found.person_id, found.evidence) == (7030, "link")


def test_stale_index_is_rejected_in_favour_of_the_label(people: People):
    # 2021ps s050072 r2: the page says Skopeček (no usable link here), rec says Blažek.
    found = people.resolve("Místopředseda PSP Jan Skopeček", index_person_id=6079)
    assert (found.person_id, found.evidence) == (6418, "name")


def test_unlinked_minister_resolved_by_unique_full_name(people: People):
    found = people.resolve("Ministr spravedlnosti ČR Pavel Blažek")
    assert (found.person_id, found.evidence) == (6079, "name")
    schillerova = people.resolve(
        "Místopředsedkyně vlády a ministryně financí ČR Alena Schillerová", index_person_id=6545
    )
    assert (schillerova.person_id, schillerova.evidence) == (6545, "index")


def test_namesakes_stay_unresolved_unless_the_evidence_is_unique(people: People):
    found = people.resolve("Poslanec Jan Černý")
    assert found.person_id is None and found.ambiguous == (22, 888, 889, 890)
    # Among the term's known speakers only one Jan Černý remains.
    assert people.resolve("Poslanec Jan Černý", known_speakers={22, 7030}).person_id == 22


def test_names_match_on_whole_words_only():
    people = People([PersonName(1, "Jan", "Novák"), PersonName(2, "Karel Jan", "Novák")])
    assert people.resolve("Poslanec Jan Nováková").person_id is None
    assert people.resolve("Poslanec Karel Jan Novák").person_id == 2  # the most specific
    assert people.resolve("Poslanec Jan Novák").person_id == 1
    assert label_names("Poslankyně Olga Richterová", "Olga Richterová")
    assert not label_names("Poslankyně Olga Richterová", "Richterová Olga")


def test_club_on_date_around_a_club_change():
    vondrak = spells(6492)
    clubs, independents = {ANO_9}, {INDEPENDENT_9}
    before = club_on(vondrak, dt.datetime(2023, 2, 21, 13, 0), clubs, independents)
    after = club_on(vondrak, dt.datetime(2023, 2, 21, 15, 0), clubs, independents)
    assert before == ClubOnDate("club", ANO_9)
    assert after == ClubOnDate("independent", INDEPENDENT_9)


def test_no_membership_record_is_unknown_not_independent():
    vondrak = spells(6492)
    # Mandate from 9 Oct 2021, club membership only from 12 Oct.
    on_10_october = club_on(vondrak, dt.datetime(2021, 10, 10), {ANO_9}, {INDEPENDENT_9})
    assert on_10_october == UNKNOWN_CLUB and on_10_october.status == "unknown"
