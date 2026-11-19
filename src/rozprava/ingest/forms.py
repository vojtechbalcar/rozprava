"""Index word forms: tag current speech revisions and record which lemma each form stood for.

Revisions tagged by a different (or no) model are processed in id order and
committed in batches, so an interrupted run continues where it stopped. A rebuild
clears the form statistics and tags every current revision again.
"""

from collections import Counter
from collections.abc import Callable

from sqlalchemy import Integer, Text, cast, column, delete, func, or_, select, update, values
from sqlalchemy.dialects.postgresql import TSVECTOR, insert
from sqlalchemy.orm import Session, sessionmaker

from rozprava import models
from rozprava.morphology import Analyzer, forms_vector
from rozprava.typography import fold

BATCH = 500  # revisions per transaction; common forms are recounted once per batch
UPSERT_ROWS = 7500  # four parameters per row, below psycopg's 65,535 limit
SR = models.SpeechRevision


def _todo(model: str):
    return SR.retired_at.is_(None) & or_(SR.forms_model.is_(None), SR.forms_model != model)


def pending(session: Session, model: str) -> int:
    """Current revisions not yet tagged with this model."""
    return session.scalar(select(func.count()).select_from(SR).where(_todo(model))) or 0


def index_forms(
    sessions: sessionmaker[Session],
    analyzer: Analyzer,
    rebuild: bool = False,
    limit: int | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> dict[str, int]:
    with sessions.begin() as session:
        if rebuild:
            session.execute(delete(models.WordForm))
            session.execute(update(SR).values(forms_model=None))
        query = select(SR.id).where(_todo(analyzer.name)).order_by(SR.id)
        ids = list(session.scalars(query.limit(limit) if limit is not None else query))

    counts = {"revisions": 0, "words": 0}
    for start in range(0, len(ids), BATCH):
        batch = ids[start : start + BATCH]
        pairs: Counter[tuple[str, str]] = Counter()
        rows = []
        with sessions.begin() as session:
            for revision, text in session.execute(
                select(SR.id, SR.text).where(SR.id.in_(batch)).order_by(SR.id)
            ):
                tokens = analyzer.tokens(text)
                rows.append((revision, forms_vector(tokens)))
                pairs.update((t.form.lower(), t.key) for t in tokens)
                counts["words"] += len(tokens)
            if rows:
                tagged = values(column("id", Integer), column("vector", Text), name="tagged").data(
                    rows
                )
                session.execute(
                    update(SR)
                    .where(SR.id == tagged.c.id)
                    .values(forms=cast(tagged.c.vector, TSVECTOR), forms_model=analyzer.name)
                    .execution_options(synchronize_session=False)
                )
            add_counts(session, pairs)
        counts["revisions"] += len(rows)
        if progress:
            progress(counts["revisions"], len(ids))
    return counts


def add_counts(session: Session, pairs: Counter[tuple[str, str]]) -> None:
    rows = [
        {"form": form, "lemma": lemma, "folded": fold(form), "count": n}
        for (form, lemma), n in pairs.items()
    ]
    wf = models.WordForm
    for start in range(0, len(rows), UPSERT_ROWS):
        statement = insert(wf).values(rows[start : start + UPSERT_ROWS])
        session.execute(
            statement.on_conflict_do_update(
                index_elements=["form", "lemma"],
                set_={"count": wf.count + statement.excluded["count"]},
            )
        )
