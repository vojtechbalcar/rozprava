"""Import psp.cz open-data metadata for the 9th and 10th terms.

Tables come in as {name: bytes} (e.g. "osoby": contents of osoby.unl), so the
import runs the same on the official dumps and on the test fixtures. Everything
is an upsert keyed by psp.cz identifiers; repeating an import changes nothing.
Transcript pages keep their import status and revisions; only their metadata
is refreshed. When psp.cz's speech index for a page changes, the page's sitting
is marked for re-assembly.
"""

import datetime as dt
import hashlib
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from rozprava import models
from rozprava.ingest import unl
from rozprava.ingest.fetch import Fetcher, zip_members

TERM_IDS = (173, 174)  # PSP9 (2021–2025), PSP10 (2025–)
CLUB_TYPE = 1  # typ_organu "Klub"
OPENDATA = "https://www.psp.cz/eknih/cdrom/opendata"
DUMPS: dict[str, tuple[str, ...]] = {
    "poslanci.zip": ("osoby", "organy", "poslanec", "zarazeni"),
    "schuze.zip": ("schuze", "bod_schuze"),
    "steno.zip": ("steno", "rec", "steno_bod"),
    "tisky.zip": ("tisky",),
}


@dataclass
class Counts:
    values: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def add(self, name: str, n: int = 1) -> None:
        self.values[name] += n

    def __repr__(self) -> str:
        return ", ".join(f"{k} {v}" for k, v in sorted(self.values.items()))


def download(fetcher: Fetcher, session: Session) -> dict[str, bytes]:
    """Fetch the current dumps and record each retrieval; return their tables."""
    tables: dict[str, bytes] = {}
    for name, members in DUMPS.items():
        fetched = fetcher.fetch(f"{OPENDATA}/{name}")
        session.execute(
            insert(models.SourceFile)
            .values(
                name=name,
                url=fetched.url,
                sha256=fetched.sha256,
                size=fetched.size,
                retrieved_at=dt.datetime.fromisoformat(fetched.retrieved_at),
                last_modified=fetched.last_modified,
            )
            .on_conflict_do_update(
                index_elements=["name", "sha256"],
                set_={"retrieved_at": dt.datetime.fromisoformat(fetched.retrieved_at)},
            )
        )
        found = zip_members(fetched.path, {f"{m}.unl" for m in members})
        tables.update({m.removesuffix(".unl"): data for m, data in found.items()})
    return tables


def mark_imported(session: Session, names: Iterable[str]) -> None:
    latest = (
        select(models.SourceFile.id)
        .where(models.SourceFile.name.in_(list(names)))
        .order_by(models.SourceFile.retrieved_at.desc())
    )
    for name in names:
        row = session.scalar(latest.where(models.SourceFile.name == name).limit(1))
        if row:
            session.execute(
                update(models.SourceFile)
                .where(models.SourceFile.id == row)
                .values(imported_at=dt.datetime.now(dt.UTC))
            )


def upsert(
    session: Session,
    model: type[models.Base],
    rows: Sequence[dict],
    keys: Sequence[str] = ("id",),
    update_columns: Sequence[str] | None = None,
) -> None:
    if not rows:
        return
    columns = list(rows[0])
    size = max(1, 30000 // len(columns))
    for start in range(0, len(rows), size):
        statement = insert(model).values(rows[start : start + size])
        changing = (
            update_columns if update_columns is not None else [c for c in columns if c not in keys]
        )
        if changing:
            statement = statement.on_conflict_do_update(
                index_elements=list(keys), set_={c: statement.excluded[c] for c in changing}
            )
        else:
            statement = statement.on_conflict_do_nothing(index_elements=list(keys))
        session.execute(statement)


def insert_rows(session: Session, model: type[models.Base], rows: Sequence[dict]) -> None:
    if not rows:
        return
    size = max(1, 30000 // len(rows[0]))
    for start in range(0, len(rows), size):
        session.execute(insert(model).values(rows[start : start + size]))


def _int(value: str | None) -> int | None:
    return unl.integer(value)


def _sex(value: str | None) -> str | None:
    """M is male; Ž (older rows) and Z (newer rows) are female; anything else unknown."""
    return {"M": "M", "Ž": "F", "Z": "F"}.get(value or "")


def _prefer_final(rows: Iterable[list[str | None]], invitation_column: int) -> dict[str, list]:
    """psp.cz repeats sittings and agenda items as invitation rows (pozvanka = 1);
    keep the actual row when there is one."""
    chosen: dict[str, list] = {}
    for row in rows:
        key = row[0] or ""
        invitation = row[invitation_column] == "1"
        if key not in chosen or (chosen[key][invitation_column] == "1" and not invitation):
            chosen[key] = row
    return chosen


def import_metadata(
    session: Session, tables: Mapping[str, bytes], terms: Sequence[int] = TERM_IDS
) -> Counts:
    counts = Counts()
    term_ids = {str(t) for t in terms}

    organy = list(unl.rows(tables["organy"], 10))
    upsert(
        session,
        models.Organization,
        [
            dict(
                id=int(r[0]),  # type: ignore[arg-type]
                parent_id=_int(r[1]),
                type_id=int(r[2] or 0),
                abbr=r[3] or "",
                name=r[4] or "",
                valid_from=unl.date(r[6]),
                valid_to=unl.date(r[7]),
            )
            for r in organy
        ],
    )
    counts.add("organizations", len(organy))
    term_rows = [r for r in organy if r[0] in term_ids]
    upsert(
        session,
        models.Term,
        [
            dict(
                id=int(r[0]),  # type: ignore[arg-type]
                number=int((r[3] or "PSP0").removeprefix("PSP")),
                year=unl.date(r[6]).year,  # type: ignore[union-attr]
                started_on=unl.date(r[6]),
                ended_on=unl.date(r[7]),
            )
            for r in term_rows
        ],
    )
    clubs = {
        int(r[0])  # type: ignore[arg-type]
        for r in organy
        if r[1] in term_ids and r[2] == str(CLUB_TYPE)
    }

    osoby = list(unl.rows(tables["osoby"], 9))
    upsert(
        session,
        models.Person,
        [
            dict(
                id=int(r[0]),  # type: ignore[arg-type]
                title_before=r[1] or "",
                surname=r[2] or "",
                forename=r[3] or "",
                title_after=r[4] or "",
                born_on=unl.date(r[5]),
                sex=_sex(r[6]),
                died_on=unl.date(r[8]),
            )
            for r in osoby
        ],
    )
    counts.add("people", len(osoby))
    people = {int(r[0]) for r in osoby}  # type: ignore[arg-type]

    zarazeni = [r for r in unl.rows(tables["zarazeni"], 7) if r[2] == "0"]
    seat: dict[tuple[int, int], list[tuple[dt.datetime, dt.datetime | None]]] = defaultdict(list)
    memberships: dict[tuple[int, int, dt.datetime], dict] = {}
    for r in zarazeni:
        person, organ = int(r[0]), int(r[1])  # type: ignore[arg-type]
        start, end = unl.timestamp(r[3]), unl.timestamp(r[4])
        if start is None or person not in people:
            continue
        if organ in terms:
            seat[(person, organ)].append((start, end))
        if organ in terms or organ in clubs:
            memberships[(person, organ, start)] = dict(
                person_id=person, organization_id=organ, valid_from=start, valid_to=end
            )
    session.execute(
        delete(models.Membership).where(models.Membership.organization_id.in_(clubs | set(terms)))
    )
    insert_rows(session, models.Membership, list(memberships.values()))
    counts.add("memberships", len(memberships))

    mandates = []
    for r in unl.rows(tables["poslanec"], 15):
        if r[4] not in term_ids:
            continue
        person, term = int(r[1]), int(r[4])  # type: ignore[arg-type]
        spells = seat.get((person, term), [])
        mandates.append(
            dict(
                id=int(r[0]),  # type: ignore[arg-type]
                person_id=person,
                term_id=term,
                region_id=_int(r[2]),
                list_id=_int(r[3]),
                valid_from=min((s for s, _ in spells), default=None),
                valid_to=None
                if not spells or any(e is None for _, e in spells)
                else max(e for _, e in spells if e is not None),
            )
        )
    upsert(session, models.Mandate, mandates)
    counts.add("mandates", len(mandates))

    sittings = _prefer_final((r for r in unl.rows(tables["schuze"], 7) if r[1] in term_ids), 6)
    upsert(
        session,
        models.Sitting,
        [
            dict(
                id=int(r[0]),
                term_id=int(r[1]),
                number=int(r[2]),
                starts_at=unl.timestamp(r[3]),
                ends_at=unl.timestamp(r[4]),
            )
            for r in sittings.values()
        ],
    )
    counts.add("sittings", len(sittings))

    bills = [
        dict(
            id=int(r[0]),  # type: ignore[arg-type]
            term_id=int(r[7]),  # type: ignore[arg-type]
            number=int(r[3] or 0),
            sub_number=int(r[4] or 0),
            kind_id=_int(r[1]),
            short_title=r[10] or "",
            title=r[15] or "",
            proposer=r[9] or "",
            submitted_on=unl.date(r[11]),
        )
        for r in unl.rows(tables["tisky"], 25)
        if r[7] in term_ids
    ]
    upsert(session, models.Bill, bills)
    counts.add("bills", len(bills))
    bill_ids = {b["id"] for b in bills}

    sitting_ids = set(sittings)
    items = _prefer_final((r for r in unl.rows(tables["bod_schuze"], 15) if r[1] in sitting_ids), 9)
    upsert(
        session,
        models.AgendaItem,
        [
            dict(
                id=int(r[0]),
                sitting_id=int(r[1]),
                bill_id=_int(r[2]) if _int(r[2]) in bill_ids else None,
                number=_int(r[4]),
                title=r[5] or "",
                title_suffix=r[6] or "",
                label=r[14] or "",
                state_id=_int(r[8]),
            )
            for r in items.values()
        ],
    )
    counts.add("agenda items", len(items))
    agenda_ids = {int(k) for k in items}

    steno = [r for r in unl.rows(tables["steno"], 8) if r[1] in term_ids]
    upsert(
        session,
        models.SourcePage,
        [
            dict(
                id=int(r[0]),  # type: ignore[arg-type]
                term_id=int(r[1]),  # type: ignore[arg-type]
                sitting_number=int(r[2]),  # type: ignore[arg-type]
                page=int(r[3]),  # type: ignore[arg-type]
                day_number=_int(r[5]),
                date=unl.date(r[4]),
                start_minute=unl.minutes(r[6]),
                end_minute=unl.minutes(r[7]),
            )
            for r in steno
        ],
    )
    counts.add("transcript pages", len(steno))
    days: dict[tuple[int, int, int], dt.date] = {}
    for r in steno:
        day, number = unl.date(r[4]), _int(r[5])
        if day is None or number is None:
            continue
        key = (int(r[1]), int(r[2]), number)  # type: ignore[arg-type]
        days[key] = min(days.get(key, day), day)
    upsert(
        session,
        models.SittingDay,
        [dict(term_id=t, sitting_number=s, day_number=n, date=d) for (t, s, n), d in days.items()],
        keys=("term_id", "sitting_number", "day_number"),
    )
    counts.add("sitting days", len(days))

    page_ids = {int(r[0]) for r in steno}  # type: ignore[arg-type]
    entries: dict[int, list[dict]] = defaultdict(list)
    for r in unl.rows(tables["rec"], 5):
        page = int(r[0])  # type: ignore[arg-type]
        if page not in page_ids or r[2] is None:
            continue
        agenda = _int(r[3])
        entries[page].append(
            dict(
                source_page_id=page,
                anchor=int(r[2]),
                person_id=_int(r[1]),
                agenda_item_id=agenda if agenda in agenda_ids else None,
                kind=_int(r[4]),
            )
        )
    session.execute(
        delete(models.TranscriptIndexEntry).where(
            models.TranscriptIndexEntry.source_page_id.in_(
                select(models.SourcePage.id).where(models.SourcePage.term_id.in_(terms))
            )
        )
    )
    rows = {(e["source_page_id"], e["anchor"]): e for page in entries.values() for e in page}
    insert_rows(session, models.TranscriptIndexEntry, list(rows.values()))
    counts.add("speech index entries", len(rows))
    counts.add("pages re-queued for assembly", _update_index_digests(session, entries, terms))

    agenda_rows = {
        (int(r[0]), int(r[1])): dict(  # type: ignore[arg-type]
            source_page_id=int(r[0]),  # type: ignore[arg-type]
            position=int(r[1]),  # type: ignore[arg-type]
            agenda_item_id=_int(r[2]) if _int(r[2]) in agenda_ids else None,
        )
        for r in unl.rows(tables["steno_bod"], 3)
        if r[0] and int(r[0]) in page_ids and r[1] is not None
    }
    session.execute(
        delete(models.PageAgenda).where(
            models.PageAgenda.source_page_id.in_(
                select(models.SourcePage.id).where(models.SourcePage.term_id.in_(terms))
            )
        )
    )
    insert_rows(session, models.PageAgenda, list(agenda_rows.values()))
    return counts


def _digest(entries: list[dict]) -> str:
    rows = sorted((e["anchor"], e["person_id"], e["agenda_item_id"], e["kind"]) for e in entries)
    return hashlib.sha256(repr(rows).encode()).hexdigest()


def _update_index_digests(
    session: Session, entries: Mapping[int, list[dict]], terms: Sequence[int]
) -> int:
    """Store each page's index digest; re-queue assembled pages whose index changed."""
    pages = session.execute(
        select(models.SourcePage.id, models.SourcePage.index_digest).where(
            models.SourcePage.term_id.in_(terms)
        )
    ).all()
    changed: dict[str | None, list[int]] = defaultdict(list)
    for page_id, old in pages:
        new = _digest(entries[page_id]) if page_id in entries else None
        if new != old:
            changed[new].append(page_id)
    requeued = 0
    for digest, ids in changed.items():
        for start in range(0, len(ids), 5000):
            chunk = ids[start : start + 5000]
            session.execute(
                update(models.SourcePage)
                .where(models.SourcePage.id.in_(chunk))
                .values(index_digest=digest)
            )
            result = session.execute(
                update(models.SourcePage)
                .where(
                    models.SourcePage.id.in_(chunk),
                    models.SourcePage.assembled_revision_id.is_not(None),
                )
                .values(assembled_revision_id=None)
            )
            requeued += result.rowcount  # type: ignore[attr-defined]
    return requeued
