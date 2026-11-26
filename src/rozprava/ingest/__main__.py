"""Import psp.cz data into the local database.

    uv run python -m rozprava.ingest metadata            # official dumps: people, sittings, index
    uv run python -m rozprava.ingest votes               # votes and apologies (may run alongside)
    uv run python -m rozprava.ingest backfill [--term 9|10] [--limit N]
    uv run python -m rozprava.ingest update              # metadata, votes, new and non-final pages
    uv run python -m rozprava.ingest refresh [--term …]  # re-download imported pages
    uv run python -m rozprava.ingest assemble            # re-assemble changed sittings
    uv run python -m rozprava.ingest retry [--unavailable]
    uv run python -m rozprava.ingest forms [--rebuild] [--limit N]  # Czech word forms
    uv run python -m rozprava.ingest embed [--limit N]  # meaning search (Voyage, paid)
    uv run python -m rozprava.ingest status

Downloads are polite (one request per second) and cached outside the repository.
Each page is committed separately, so an interrupted run can simply be repeated.
A log is appended to <data dir>/log/ingest.log.

Commands that can add speech revisions (backfill, update, refresh, assemble) tag
them with the Czech morphology model afterwards, if it is installed
(scripts/fetch_morphology.py). Without it, new speeches match only exact words
until `forms` runs. With a VOYAGE_API_KEY in .env they also embed new speeches for
meaning search; `embed` covers the rest, within ROZPRAVA_EMBEDDING_TOKEN_LIMIT.
"""

import argparse
import logging
import sys

from sqlalchemy import func, select

from rozprava import ai, models
from rozprava.db import get_engine, get_session_factory
from rozprava.ingest import embed, forms, metadata
from rozprava.ingest.fetch import Cache, Fetcher, FetchError
from rozprava.ingest.runner import (
    LOCK_KEY,
    TERM_NUMBERS,
    VOTES_LOCK_KEY,
    ImportLocked,
    Runner,
    coverage,
    import_lock,
)
from rozprava.morphology import MODEL, Lemmatizer, MorphologyUnavailable, model_path
from rozprava.settings import get_settings

log = logging.getLogger("rozprava.ingest")


def configure_logging() -> None:
    settings = get_settings()
    log_dir = settings.data_dir / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = logging.FileHandler(log_dir / "ingest.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger = logging.getLogger("rozprava.ingest")
    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.addHandler(console)


def print_status() -> None:
    with get_session_factory()() as session:
        for term in coverage(session):
            others = ", ".join(f"{k} {v}" for k, v in term.items() if k not in ("term", "expected"))
            print(f"term {term['term']}: {term['expected']} pages expected; {others}")
        speeches = session.scalar(
            select(func.count()).where(models.Speech.current_revision_id.is_not(None))
        )
        print(f"speeches: {speeches}")
        untagged = forms.pending(session, MODEL)
        print(f"word forms: {(speeches or 0) - untagged} tagged, {untagged} waiting ({MODEL})")
        model = get_settings().embedding_model
        chunks = session.scalar(
            select(func.count(func.distinct(models.SpeechChunk.revision_id))).where(
                models.SpeechChunk.model == model
            )
        )
        used = ai.tokens_used(session, model)
        print(
            f"meaning search: {chunks} speeches embedded, {embed.pending(session, model)} "
            f"waiting ({model}, {used:,} of {get_settings().embedding_token_limit:,} tokens)"
        )
        for run in session.scalars(
            select(models.ImportRun).order_by(models.ImportRun.id.desc()).limit(5)
        ):
            finished = run.finished_at.isoformat(timespec="seconds") if run.finished_at else "-"
            print(f"run {run.id} {run.command} {run.status} (pid {run.pid}, finished {finished})")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m rozprava.ingest", description=(__doc__ or "").split("\n\n")[0]
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("metadata", help="download and import the official open-data dumps")
    commands.add_parser("votes", help="download and import votes and apologies")
    for name in ("backfill", "update", "refresh"):
        sub = commands.add_parser(name)
        sub.add_argument("--term", type=int, choices=sorted(TERM_NUMBERS), action="append")
        sub.add_argument("--limit", type=int, help="at most this many pages")
    assemble = commands.add_parser("assemble", help="re-assemble sittings whose pages changed")
    assemble.add_argument("--term", type=int, choices=sorted(TERM_NUMBERS), action="append")
    retry = commands.add_parser("retry", help="queue failed pages again")
    retry.add_argument("--term", type=int, choices=sorted(TERM_NUMBERS), action="append")
    retry.add_argument("--unavailable", action="store_true", help="also pages marked unavailable")
    tag = commands.add_parser("forms", help="tag speeches with Czech lemmas for search")
    tag.add_argument("--rebuild", action="store_true", help="tag every current speech again")
    tag.add_argument("--limit", type=int, help="at most this many speeches")
    vectors = commands.add_parser("embed", help="embed speeches for meaning search (Voyage)")
    vectors.add_argument("--limit", type=int, help="at most this many speeches")
    commands.add_parser("status", help="coverage per term and recent runs")
    args = parser.parse_args(argv)

    if args.command == "status":
        print_status()
        return 0

    configure_logging()
    settings = get_settings()
    terms = getattr(args, "term", None) or sorted(TERM_NUMBERS)
    cache = Cache(settings.cache_dir / "http")  # type: ignore[operator]
    model = model_path(settings.data_dir)
    try:
        lock_key = VOTES_LOCK_KEY if args.command == "votes" else LOCK_KEY
        with (
            get_engine().connect() as lock_connection,
            import_lock(lock_connection, lock_key),
            Fetcher(cache) as fetcher,
        ):
            runner = Runner(get_session_factory(), fetcher)
            if args.command == "metadata":
                result = runner.metadata(lambda s: metadata.download(fetcher, s))
            elif args.command == "votes":
                result = runner.votes(lambda s: metadata.download_votes(fetcher, s))
            elif args.command == "backfill":
                result = runner.backfill(terms, args.limit)
            elif args.command == "update":
                runner.metadata(lambda s: metadata.download(fetcher, s))
                with import_lock(lock_connection, VOTES_LOCK_KEY):
                    runner.votes(lambda s: metadata.download_votes(fetcher, s))
                result = runner.update(terms, args.limit)
            elif args.command == "refresh":
                result = runner.refresh(terms, args.limit)
            elif args.command == "assemble":
                result = runner.assemble_pending(terms)
            elif args.command == "forms":
                result = runner.forms(Lemmatizer(model), args.rebuild, args.limit)
            elif args.command == "embed":
                if (embedder := ai.embedder(settings)) is None:
                    raise ai.AIUnavailable("Add VOYAGE_API_KEY to .env to embed speeches.")
                result = runner.embed(embedder, settings.embedding_token_limit, args.limit)
            else:
                result = {"queued again": runner.retry(terms, args.unavailable)}
            if args.command in ("backfill", "update", "refresh", "assemble"):
                try:
                    result = {**result, "forms": runner.forms(Lemmatizer(model))}
                except MorphologyUnavailable as error:  # the import itself succeeded
                    log.warning("word forms not tagged: %s", error)
                if (embedder := ai.embedder(settings)) is not None:
                    try:
                        limit = settings.embedding_token_limit
                        result = {**result, "embedded": runner.embed(embedder, limit)}
                    except ai.AIUnavailable as error:
                        log.warning("new speeches not embedded for meaning search: %s", error)
            print(result)
    except (MorphologyUnavailable, ai.AIUnavailable) as error:
        print(error, file=sys.stderr)
        return 1
    except ImportLocked as error:
        print(error, file=sys.stderr)
        return 2
    except FetchError as error:
        print(f"Download failed: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted; run the same command again to continue.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
