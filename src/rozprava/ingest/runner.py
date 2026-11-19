"""Resumable import orchestration. One import runs at a time (a PostgreSQL lock).

Every page is committed on its own, so an interrupted run loses at most the page
in flight; the next run continues with what is still pending. Sittings are
assembled after their pages are stored, and again whenever a page revision or
psp.cz's speech index for one of their pages changes.
"""

import datetime as dt
import logging
import os
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import Connection, func, select, text, update
from sqlalchemy.orm import Session, sessionmaker

from rozprava import models
from rozprava.ingest import metadata, store
from rozprava.ingest.fetch import Fetched, FetchError, Forbidden, NotFound
from rozprava.ingest.parser import ParseError, parse_page

LOCK_KEY = 0x526F7A70  # "Rozp": transcripts and metadata
VOTES_LOCK_KEY = LOCK_KEY + 1  # votes touch separate tables and may run alongside
TERM_NUMBERS = {9: 173, 10: 174}

log = logging.getLogger("rozprava.ingest")


class PageSource(Protocol):
    def get(self, url: str, refresh: bool = False) -> Fetched: ...


class ImportLocked(RuntimeError):
    pass


@contextmanager
def import_lock(connection: Connection, key: int = LOCK_KEY) -> Iterator[None]:
    if not connection.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": key}).scalar():
        raise ImportLocked("Another import is running; try again when it has finished.")
    try:
        yield
    finally:
        connection.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})


@dataclass
class PageCounts:
    imported: int = 0
    unchanged: int = 0
    failed: int = 0
    unavailable: int = 0

    def as_dict(self) -> dict[str, int]:
        return dict(vars(self))


class Runner:
    def __init__(self, sessions: sessionmaker[Session], source: PageSource):
        self.sessions = sessions
        self.source = source
        self._context: store.Context | None = None

    # --- run records ------------------------------------------------------------

    @contextmanager
    def run(self, command: str, **arguments: object) -> Iterator[dict]:
        counts: dict = {}
        with self.sessions.begin() as session:
            record = models.ImportRun(
                command=command, arguments=arguments, pid=os.getpid(), counts={}
            )
            session.add(record)
            session.flush()
            run_id = record.id
        log.info("run %s: %s %s (pid %s)", run_id, command, arguments, os.getpid())
        status, error = "succeeded", None
        try:
            yield counts
        except KeyboardInterrupt:
            status, error = "interrupted", "Interrupted"
            raise
        except BaseException as exc:
            status, error = "failed", f"{type(exc).__name__}: {exc}"
            raise
        finally:
            with self.sessions.begin() as session:
                session.execute(
                    update(models.ImportRun)
                    .where(models.ImportRun.id == run_id)
                    .values(
                        status=status,
                        error=error,
                        counts=counts,
                        finished_at=dt.datetime.now(dt.UTC),
                    )
                )
            log.info("run %s %s: %s", run_id, status, counts)

    # --- commands -----------------------------------------------------------------

    def metadata(self, download: Callable[[Session], dict[str, bytes]]) -> dict:
        with self.run("metadata") as counts, self.sessions.begin() as session:
            tables = download(session)
            result = metadata.import_metadata(session, tables)
            metadata.mark_imported(session, metadata.DUMPS)
            counts.update(result.values)
            self._context = None
        return counts

    def votes(self, download: Callable[[Session], dict[int, dict[str, list[bytes]]]]) -> dict:
        with self.run("votes") as counts, self.sessions.begin() as session:
            for term_id, tables in download(session).items():
                result = metadata.import_votes(session, term_id, tables)
                counts[str(term_id)] = dict(result.values)
            metadata.mark_imported(session, metadata.VOTE_DUMPS)
        return counts

    def backfill(
        self,
        terms: Iterable[int] = TERM_NUMBERS,
        limit: int | None = None,
        include_failed: bool = True,
    ) -> dict:
        statuses = ["pending", "failed"] if include_failed else ["pending"]
        with self.run("backfill", terms=list(terms), limit=limit) as counts:
            pages = self._select(terms, models.SourcePage.status.in_(statuses), limit)
            counts.update(self._process(pages, refresh=False))
        return counts

    def update(self, terms: Iterable[int] = TERM_NUMBERS, limit: int | None = None) -> dict:
        """New pages, then pages whose current revision is not final yet."""
        with self.run("update", terms=list(terms), limit=limit) as counts:
            pending = self._select(terms, models.SourcePage.status == "pending", limit)
            counts["new"] = self._process(pending, refresh=False)
            not_final = self._select(
                terms,
                models.SourcePage.current_revision_id.in_(
                    select(models.PageRevision.id).where(models.PageRevision.stage != "final")
                ),
                limit,
            )
            counts["revisited"] = self._process(not_final, refresh=True)
            counts["assembled"] = self.assemble_pending(terms)
        return counts

    def refresh(self, terms: Iterable[int] = TERM_NUMBERS, limit: int | None = None) -> dict:
        """Download every imported page again, to pick up later corrections."""
        with self.run("refresh", terms=list(terms), limit=limit) as counts:
            pages = self._select(terms, models.SourcePage.status == "imported", limit)
            counts.update(self._process(pages, refresh=True))
        return counts

    def retry(self, terms: Iterable[int] = TERM_NUMBERS, unavailable: bool = False) -> int:
        """Put failed (and optionally unavailable) pages back in the queue."""
        statuses = ["failed", "unavailable"] if unavailable else ["failed"]
        with self.sessions.begin() as session:
            result = session.execute(
                update(models.SourcePage)
                .where(
                    models.SourcePage.term_id.in_(self._term_ids(terms)),
                    models.SourcePage.status.in_(statuses),
                )
                .values(status="pending", unavailable_reason=None)
            )
            return result.rowcount  # type: ignore[attr-defined]

    def assemble_pending(self, terms: Iterable[int] = TERM_NUMBERS) -> dict:
        totals = {"sittings": 0, "speeches": 0, "new revisions": 0, "retired": 0, "unresolved": 0}
        with self.sessions() as session:
            todo = store.sittings_to_assemble(session, self._term_ids(terms))
        for term_id, sitting in todo:
            result = self._assemble(term_id, sitting)
            totals["sittings"] += 1
            totals["speeches"] += result.speeches
            totals["new revisions"] += result.new_revisions
            totals["retired"] += result.retired
            totals["unresolved"] += len(result.unresolved)
        return totals

    # --- internals ------------------------------------------------------------------

    def _term_ids(self, terms: Iterable[int]) -> list[int]:
        return [TERM_NUMBERS[t] for t in terms]

    def _select(self, terms: Iterable[int], condition, limit: int | None) -> list[int]:
        with self.sessions() as session:
            query = (
                select(models.SourcePage.id)
                .where(models.SourcePage.term_id.in_(self._term_ids(terms)), condition)
                .order_by(
                    models.SourcePage.term_id,
                    models.SourcePage.sitting_number,
                    models.SourcePage.page,
                )
            )
            if limit is not None:
                query = query.limit(limit)
            return list(session.scalars(query))

    def _context_for(self, session: Session) -> store.Context:
        if self._context is None:
            self._context = store.Context.load(session)
        return self._context

    def _assemble(self, term_id: int, sitting: int) -> store.AssemblyResult:
        with self.sessions.begin() as session:
            result = store.assemble_sitting(session, term_id, sitting, self._context_for(session))
        for line in result.unresolved[:20]:
            log.info("unresolved speaker %s", line)
        log.info(
            "assembled term %s sitting %s: %s speeches, %s new revisions, %s retired",
            term_id,
            sitting,
            result.speeches,
            result.new_revisions,
            result.retired,
        )
        return result

    def _process(self, page_ids: list[int], refresh: bool) -> dict:
        """Import pages in order, assembling each sitting once its pages are done."""
        counts = PageCounts()
        with self.sessions() as session:
            sitting_of = {
                page_id: (term_id, sitting)
                for page_id, term_id, sitting in session.execute(
                    select(
                        models.SourcePage.id,
                        models.SourcePage.term_id,
                        models.SourcePage.sitting_number,
                    ).where(models.SourcePage.id.in_(page_ids))
                )
            }
        current: tuple[int, int] | None = None
        for page_id in page_ids:
            if current is not None and sitting_of[page_id] != current:
                self._assemble(*current)
            current = sitting_of[page_id]
            self._process_page(page_id, refresh, counts)
        if current is not None:
            self._assemble(*current)
        return counts.as_dict()

    def _process_page(self, page_id: int, refresh: bool, counts: PageCounts) -> None:
        with self.sessions.begin() as session:
            page = session.get_one(models.SourcePage, page_id)
            term = session.get_one(models.Term, page.term_id)
            url = store.page_url(term.year, page.sitting_number, page.page)
            previous = page.current_revision_id
            try:
                # A failed parse may have cached an empty/error body. Retry the
                # source, including after `retry` changes the status to pending.
                fetched = self.source.get(url, refresh=refresh or bool(page.last_error))
                parsed = parse_page(fetched.read())
            except NotFound as error:
                store.record_failure(session, page, str(error), unavailable=True)
                counts.unavailable += 1
                log.warning("unavailable %s: %s", url, error)
                return
            except (FetchError, ParseError, OSError) as error:
                if isinstance(error, Forbidden):
                    raise
                store.record_failure(session, page, f"{type(error).__name__}: {error}")
                counts.failed += 1
                log.warning("failed %s: %s", url, error)
                return
            if parsed.replaced_characters:
                log.warning("%s: %s undecodable bytes", url, parsed.replaced_characters)
            revision = store.store_page(session, page, fetched, parsed)
            if revision.id == previous:
                counts.unchanged += 1
            else:
                counts.imported += 1
            log.info("page %s: revision %s (%s)", url, revision.id, parsed.stage)


def coverage(session: Session) -> list[dict]:
    """Per-term page counts by status, and the last successful import."""
    rows = session.execute(
        select(
            models.Term.number,
            models.SourcePage.status,
            func.count(),
        )
        .join(models.Term, models.Term.id == models.SourcePage.term_id)
        .group_by(models.Term.number, models.SourcePage.status)
    ).all()
    by_term: dict[int, dict] = {}
    for number, status, n in rows:
        by_term.setdefault(number, {"term": number, "expected": 0})
        by_term[number][status] = n
        by_term[number]["expected"] += n
    return [by_term[k] for k in sorted(by_term)]
