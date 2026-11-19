"""Who spoke, and in which club on the day. Pure functions over loaded records.

Speaker attribution, in order of evidence:

1. the person linked from the label (detail.sqw?id=…), if the label ends with
   that person's name;
2. psp.cz's speech index (rec), if the label ends with that person's name;
3. the unique person whose full name ends the label, among the term's known
   speakers first and then everyone; several equally specific matches mean
   the speaker stays unresolved.

The speech index is not trusted on its own: it can lag the pages or be shifted
after editors re-cut a page.
"""

import datetime as dt
import re
import unicodedata
from collections import defaultdict
from collections.abc import Collection, Iterable
from dataclasses import dataclass


def name_key(text: str) -> str:
    text = unicodedata.normalize("NFC", text).replace("\xa0", " ")
    text = re.sub(r"[^\w\s-]", " ", text.casefold())
    return re.sub(r"\s+", " ", text).strip()


@dataclass(frozen=True)
class PersonName:
    id: int
    forename: str
    surname: str

    @property
    def key(self) -> str:
        return name_key(f"{self.forename} {self.surname}")


def label_names(label: str, name: str) -> bool:
    """Whether a label ("Poslankyně Olga Richterová") ends with the whole name."""
    label, name = name_key(label), name_key(name)
    return bool(name) and (label == name or label.endswith(" " + name))


@dataclass(frozen=True)
class Attribution:
    person_id: int | None
    evidence: str | None  # "link", "index", "name"; None when unresolved
    ambiguous: tuple[int, ...] = ()


class People:
    def __init__(self, people: Iterable[PersonName]):
        self.by_id = {p.id: p for p in people}
        self._by_last_word: dict[str, list[PersonName]] = defaultdict(list)
        for person in self.by_id.values():
            if person.key:
                self._by_last_word[person.key.rsplit(" ", 1)[-1]].append(person)

    def named_in(self, label: str, person_id: int | None) -> bool:
        person = self.by_id.get(person_id) if person_id is not None else None
        return person is not None and label_names(label, f"{person.forename} {person.surname}")

    def matching(self, label: str, among: Collection[int] | None = None) -> list[int]:
        """Ids of the most specific full-name matches at the end of the label."""
        key = name_key(label)
        if not key:
            return []
        found = [
            p
            for p in self._by_last_word.get(key.rsplit(" ", 1)[-1], [])
            if (among is None or p.id in among) and (key == p.key or key.endswith(" " + p.key))
        ]
        if not found:
            return []
        longest = max(len(p.key) for p in found)
        return sorted(p.id for p in found if len(p.key) == longest)

    def resolve(
        self,
        label: str | None,
        link_person_id: int | None = None,
        index_person_id: int | None = None,
        known_speakers: Collection[int] | None = None,
    ) -> Attribution:
        if not label:
            return Attribution(None, None)
        if self.named_in(label, link_person_id):
            return Attribution(link_person_id, "link")
        if self.named_in(label, index_person_id):
            return Attribution(index_person_id, "index")
        for among in (known_speakers, None):
            if among is not None and not among:
                continue
            ids = self.matching(label, among)
            if len(ids) == 1:
                return Attribution(ids[0], "name")
            if len(ids) > 1:
                return Attribution(None, None, tuple(ids))
        return Attribution(None, None)


# --- Dated memberships --------------------------------------------------------------


@dataclass(frozen=True)
class Spell:
    organization_id: int
    valid_from: dt.datetime
    valid_to: dt.datetime | None


@dataclass(frozen=True)
class ClubOnDate:
    """A verified club, a verified independent (Nezařazení), or unknown."""

    status: str  # "club", "independent" or "unknown"
    organization_id: int | None = None


UNKNOWN_CLUB = ClubOnDate("unknown")


def spell_on(spells: Iterable[Spell], when: dt.datetime) -> Spell | None:
    """The spell covering a moment; if several do (a change that day), the latest."""
    covering = [
        s for s in spells if s.valid_from <= when and (s.valid_to is None or when <= s.valid_to)
    ]
    return max(covering, key=lambda s: s.valid_from, default=None)


def club_on(
    spells: Iterable[Spell],
    when: dt.datetime,
    clubs: Collection[int],
    independents: Collection[int],
) -> ClubOnDate:
    """Club membership at a moment. No covering record is unknown, not independent."""
    relevant = [
        s for s in spells if s.organization_id in clubs or s.organization_id in independents
    ]
    spell = spell_on(relevant, when)
    if spell is None:
        return UNKNOWN_CLUB
    if spell.organization_id in independents:
        return ClubOnDate("independent", spell.organization_id)
    return ClubOnDate("club", spell.organization_id)
