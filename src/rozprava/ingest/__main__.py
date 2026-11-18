"""Import psp.cz data into the local database.

    uv run python -m rozprava.ingest metadata            # official dumps: people, sittings, index
    uv run python -m rozprava.ingest backfill [--term 9|10] [--limit N]
    uv run python -m rozprava.ingest update              # metadata, new pages, non-final pages
    uv run python -m rozprava.ingest refresh [--term …]  # re-download imported pages
    uv run python -m rozprava.ingest assemble            # re-assemble changed sittings
    uv run python -m rozprava.ingest retry [--unavailable]
    uv run python -m rozprava.ingest status

Downloads are polite (one request per second) and cached outside the repository.
Each page is committed separately, so an interrupted run can simply be repeated.
A log is appended to <data dir>/log/ingest.log.
"""

import argparse
import logging
import sys

from sqlalchemy import func, select

from rozprava import models
from rozprava.db import get_engine, get_session_factory
from rozprava.ingest import metadata
from rozprava.ingest.fetch import Cache, Fetcher, FetchError
from rozprava.ingest.runner import TERM_NUMBERS, ImportLocked, Runner, coverage, import_lock
from rozprava.settings import get_settings


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
    for name in ("backfill", "update", "refresh"):
        sub = commands.add_parser(name)
        sub.add_argument("--term", type=int, choices=sorted(TERM_NUMBERS), action="append")
        sub.add_argument("--limit", type=int, help="at most this many pages")
    assemble = commands.add_parser("assemble", help="re-assemble sittings whose pages changed")
    assemble.add_argument("--term", type=int, choices=sorted(TERM_NUMBERS), action="append")
    retry = commands.add_parser("retry", help="queue failed pages again")
    retry.add_argument("--term", type=int, choices=sorted(TERM_NUMBERS), action="append")
    retry.add_argument("--unavailable", action="store_true", help="also pages marked unavailable")
    commands.add_parser("status", help="coverage per term and recent runs")
    args = parser.parse_args(argv)

    if args.command == "status":
        print_status()
        return 0

    configure_logging()
    settings = get_settings()
    terms = getattr(args, "term", None) or sorted(TERM_NUMBERS)
    cache = Cache(settings.cache_dir / "http")  # type: ignore[operator]
    try:
        with (
            get_engine().connect() as lock_connection,
            import_lock(lock_connection),
            Fetcher(cache) as fetcher,
        ):
            runner = Runner(get_session_factory(), fetcher)
            if args.command == "metadata":
                result = runner.metadata(lambda s: metadata.download(fetcher, s))
            elif args.command == "backfill":
                result = runner.backfill(terms, args.limit)
            elif args.command == "update":
                runner.metadata(lambda s: metadata.download(fetcher, s))
                result = runner.update(terms, args.limit)
            elif args.command == "refresh":
                result = runner.refresh(terms, args.limit)
            elif args.command == "assemble":
                result = runner.assemble_pending(terms)
            else:
                result = {"queued again": runner.retry(terms, args.unavailable)}
            print(result)
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
