"""Database schema.

Upstream psp.cz identifiers are primary keys wherever they exist (id_osoba,
id_organ, id_schuze, id_bod, id_tisk, id_steno, id_hlasovani, id_poslanec).
Sitting and bill numbers repeat in every term, so their natural keys always
include the term. A person's name is a label, never a key.

Transcripts are stored in three layers:

- source_page: one row per official transcript page ("turn"), with its import
  status and a pointer to the page revision currently in use;
- page_revision / page_segment: immutable parsed content of one fetched version
  of a page, never overwritten;
- speech / speech_revision / speech_paragraph: speeches assembled across pages.
  A speech keeps every revision; citations pin a revision, search uses the
  current one (retired_at IS NULL).
"""

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    cast,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import UserDefinedType

SEARCH_CONFIG = "rozprava"
# Exact words (accent-insensitive) followed by lemma lexemes, which have their own prefix.
SEARCH_VECTOR = f"to_tsvector('{SEARCH_CONFIG}'::regconfig, text) || coalesce(forms, ''::tsvector)"

PAGE_STATUSES = ("pending", "imported", "failed", "unavailable")
ROLES = ("speaker", "chair", "unknown")
STAGES = ("draft", "edited", "final")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_N_name)s",
            "uq": "uq_%(table_name)s_%(column_0_N_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


# --- Provenance -------------------------------------------------------------------


class SourceFile(Base):
    """One retrieval of an official open-data dump (poslanci.zip, steno.zip, …)."""

    __tablename__ = "source_file"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    url: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(BigInteger)
    retrieved_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    last_modified: Mapped[str | None] = mapped_column(Text)
    imported_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("name", "sha256"),)


class ImportRun(Base):
    __tablename__ = "import_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    command: Mapped[str] = mapped_column(String(32))
    arguments: Mapped[dict] = mapped_column(JSONB, default=dict)
    pid: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="running")
    counts: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(_in("status", ("running", "succeeded", "failed", "interrupted")), "status"),
    )


# --- People and organizations -------------------------------------------------------


class Term(Base):
    """An electoral term of the Chamber: organ 173 is the 9th (2021), 174 the 10th (2025)."""

    __tablename__ = "term"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)  # id_organ
    number: Mapped[int] = mapped_column(SmallInteger, unique=True)
    year: Mapped[int] = mapped_column(SmallInteger)  # first year, as in /eknih/2025ps/
    started_on: Mapped[dt.date] = mapped_column(Date)
    ended_on: Mapped[dt.date | None] = mapped_column(Date)


class Organization(Base):
    """psp.cz organ: a term, club, committee, region, party, government…"""

    __tablename__ = "organization"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)  # id_organ
    parent_id: Mapped[int | None] = mapped_column(Integer, index=True)
    type_id: Mapped[int] = mapped_column(Integer, index=True)  # id_typ_organu; 1 = club
    abbr: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    valid_from: Mapped[dt.date | None] = mapped_column(Date)
    valid_to: Mapped[dt.date | None] = mapped_column(Date)


class Person(Base):
    __tablename__ = "person"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)  # id_osoba
    title_before: Mapped[str] = mapped_column(Text, default="")
    forename: Mapped[str] = mapped_column(Text)
    surname: Mapped[str] = mapped_column(Text, index=True)
    title_after: Mapped[str] = mapped_column(Text, default="")
    born_on: Mapped[dt.date | None] = mapped_column(Date)
    died_on: Mapped[dt.date | None] = mapped_column(Date)
    sex: Mapped[str | None] = mapped_column(String(1))  # "M", "F" or unknown

    __table_args__ = (CheckConstraint("sex IN ('M', 'F')", "sex"),)

    @property
    def name(self) -> str:
        return f"{self.forename} {self.surname}"


class Mandate(Base):
    """A person's seat in one term (psp.cz poslanec)."""

    __tablename__ = "mandate"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)  # id_poslanec
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id"), index=True)
    term_id: Mapped[int] = mapped_column(ForeignKey("term.id"))
    region_id: Mapped[int | None] = mapped_column(ForeignKey("organization.id"))
    list_id: Mapped[int | None] = mapped_column(Integer)  # id_kandidatka (electoral party)
    valid_from: Mapped[dt.datetime | None] = mapped_column(DateTime)
    valid_to: Mapped[dt.datetime | None] = mapped_column(DateTime)

    person: Mapped[Person] = relationship()

    __table_args__ = (UniqueConstraint("term_id", "person_id"),)


class Membership(Base):
    """Dated membership of a person in an organ (zarazeni with cl_funkce = 0)."""

    __tablename__ = "membership"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id"))
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), index=True)
    valid_from: Mapped[dt.datetime] = mapped_column(DateTime)
    valid_to: Mapped[dt.datetime | None] = mapped_column(DateTime)

    __table_args__ = (
        UniqueConstraint("person_id", "organization_id", "valid_from"),
        Index("ix_membership_person_from", "person_id", "valid_from"),
    )


# --- Sittings, agenda and bills -------------------------------------------------------


class Sitting(Base):
    __tablename__ = "sitting"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)  # id_schuze
    term_id: Mapped[int] = mapped_column(ForeignKey("term.id"))
    number: Mapped[int] = mapped_column(SmallInteger)
    starts_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    ends_at: Mapped[dt.datetime | None] = mapped_column(DateTime)

    __table_args__ = (UniqueConstraint("term_id", "number"),)


class SittingDay(Base):
    """A sitting day, numbered within its sitting (the jd of /034schuz/34-12.html)."""

    __tablename__ = "sitting_day"

    id: Mapped[int] = mapped_column(primary_key=True)
    term_id: Mapped[int] = mapped_column(ForeignKey("term.id"))
    sitting_number: Mapped[int] = mapped_column(SmallInteger)
    day_number: Mapped[int] = mapped_column(SmallInteger)
    date: Mapped[dt.date] = mapped_column(Date, index=True)

    __table_args__ = (UniqueConstraint("term_id", "sitting_number", "day_number"),)


class Bill(Base):
    """A sněmovní tisk. Its number is unique only within a term (and sub-number)."""

    __tablename__ = "bill"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)  # id_tisk
    term_id: Mapped[int] = mapped_column(ForeignKey("term.id"))
    number: Mapped[int] = mapped_column(Integer)
    sub_number: Mapped[int] = mapped_column(Integer, default=0)
    kind_id: Mapped[int | None] = mapped_column(Integer)
    short_title: Mapped[str] = mapped_column(Text, default="")
    title: Mapped[str] = mapped_column(Text, default="")
    proposer: Mapped[str] = mapped_column(Text, default="")
    submitted_on: Mapped[dt.date | None] = mapped_column(Date)

    __table_args__ = (Index("ix_bill_term_number", "term_id", "number"),)


class AgendaItem(Base):
    """An item of a sitting's agenda (bod schůze), possibly about a bill."""

    __tablename__ = "agenda_item"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)  # id_bod
    sitting_id: Mapped[int] = mapped_column(ForeignKey("sitting.id"), index=True)
    bill_id: Mapped[int | None] = mapped_column(ForeignKey("bill.id"), index=True)
    number: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(Text, default="")
    title_suffix: Mapped[str] = mapped_column(Text, default="")  # "/sněmovní tisk 285/ …"
    label: Mapped[str] = mapped_column(Text, default="")  # psp.cz keyword ("zkratka")
    state_id: Mapped[int | None] = mapped_column(SmallInteger)


# --- Transcript pages ------------------------------------------------------------


class SourcePage(Base):
    """One official transcript page (steno row): what we expect to import."""

    __tablename__ = "source_page"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)  # id_steno
    term_id: Mapped[int] = mapped_column(ForeignKey("term.id"))
    sitting_number: Mapped[int] = mapped_column(SmallInteger)
    page: Mapped[int] = mapped_column(SmallInteger)  # turn
    day_number: Mapped[int | None] = mapped_column(SmallInteger)
    date: Mapped[dt.date | None] = mapped_column(Date)
    start_minute: Mapped[int | None] = mapped_column(SmallInteger)
    end_minute: Mapped[int | None] = mapped_column(SmallInteger)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    unavailable_reason: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0)
    last_attempt_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    current_revision_id: Mapped[int | None] = mapped_column(
        ForeignKey("page_revision.id", use_alter=True)
    )
    # The revision the sitting's speeches were last assembled from; differs from
    # current_revision_id (or is reset) when the sitting needs assembling again.
    assembled_revision_id: Mapped[int | None] = mapped_column(
        ForeignKey("page_revision.id", use_alter=True)
    )
    # Digest of psp.cz's speech-index rows for this page, to notice when they change.
    index_digest: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (
        UniqueConstraint("term_id", "sitting_number", "page"),
        CheckConstraint(_in("status", PAGE_STATUSES), "status"),
    )


class PageRevision(Base):
    """Immutable parsed content of one version of a page."""

    __tablename__ = "page_revision"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_page_id: Mapped[int] = mapped_column(ForeignKey("source_page.id"))
    url: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    raw_sha256: Mapped[str] = mapped_column(String(64))  # the cached original bytes
    content_sha256: Mapped[str] = mapped_column(String(64))  # the parsed content
    stage: Mapped[str] = mapped_column(String(8))
    status_line: Mapped[str | None] = mapped_column(Text)  # None once final
    time_label: Mapped[str | None] = mapped_column(Text)  # "(12.50 hodin)"
    continues: Mapped[str | None] = mapped_column(Text)  # name in "(pokračuje …)"
    parser_version: Mapped[int] = mapped_column(SmallInteger)

    segments: Mapped[list["PageSegment"]] = relationship(order_by="PageSegment.position")

    __table_args__ = (
        UniqueConstraint("source_page_id", "content_sha256"),
        CheckConstraint(_in("stage", STAGES), "stage"),
    )


class PageSegment(Base):
    """A run of text on a page: a labelled speech start, or a headerless continuation."""

    __tablename__ = "page_segment"

    revision_id: Mapped[int] = mapped_column(ForeignKey("page_revision.id"), primary_key=True)
    position: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    anchor: Mapped[int | None] = mapped_column(SmallInteger)  # rN; None for continuations
    label: Mapped[str | None] = mapped_column(Text)  # "Místopředseda PSP Jan Skopeček"
    link_person_id: Mapped[int | None] = mapped_column(Integer)  # from the label's link
    link_url: Mapped[str | None] = mapped_column(Text)
    paragraphs: Mapped[list[str]] = mapped_column(ARRAY(Text))
    heading: Mapped[bool] = mapped_column(Boolean, default=False)  # agenda heading, not speech


class TranscriptIndexEntry(Base):
    """psp.cz's own index of speeches (steno/rec): may lag or be stale; see ingest."""

    __tablename__ = "transcript_index_entry"

    source_page_id: Mapped[int] = mapped_column(ForeignKey("source_page.id"), primary_key=True)
    anchor: Mapped[int] = mapped_column(SmallInteger, primary_key=True)  # aname
    person_id: Mapped[int | None] = mapped_column(Integer)
    agenda_item_id: Mapped[int | None] = mapped_column(Integer)  # 0 / missing -> None
    kind: Mapped[int | None] = mapped_column(SmallInteger)  # druh: 2/4 chair, 3/5 speaker


class PageAgenda(Base):
    """Where the discussion of an agenda item starts or resumes (steno_bod)."""

    __tablename__ = "page_agenda"

    source_page_id: Mapped[int] = mapped_column(ForeignKey("source_page.id"), primary_key=True)
    position: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    agenda_item_id: Mapped[int | None] = mapped_column(Integer)


# --- Speeches ----------------------------------------------------------------------


class Speech(Base):
    """A speech's stable identity: where it starts (catalog 10/034/0644/2).

    anchor 0 is a fragment at the top of a page whose beginning is unknown.
    """

    __tablename__ = "speech"

    id: Mapped[int] = mapped_column(primary_key=True)
    term_id: Mapped[int] = mapped_column(ForeignKey("term.id"))
    sitting_number: Mapped[int] = mapped_column(SmallInteger)
    page: Mapped[int] = mapped_column(SmallInteger)
    anchor: Mapped[int] = mapped_column(SmallInteger)
    current_revision_id: Mapped[int | None] = mapped_column(
        ForeignKey("speech_revision.id", use_alter=True)
    )

    __table_args__ = (UniqueConstraint("term_id", "sitting_number", "page", "anchor"),)


class SpeechRevision(Base):
    __tablename__ = "speech_revision"

    id: Mapped[int] = mapped_column(primary_key=True)
    speech_id: Mapped[int] = mapped_column(ForeignKey("speech.id"), index=True)
    content_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    retired_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    # Denormalised for search and filtering; constant within a revision.
    term_id: Mapped[int] = mapped_column(ForeignKey("term.id"))
    date: Mapped[dt.date | None] = mapped_column(Date)
    person_id: Mapped[int | None] = mapped_column(ForeignKey("person.id"))
    label: Mapped[str | None] = mapped_column(Text)
    # How person_id was established: "link", "index" or "name"; None if unresolved.
    attribution: Mapped[str | None] = mapped_column(String(8))
    role: Mapped[str] = mapped_column(String(8))
    agenda_item_id: Mapped[int | None] = mapped_column(ForeignKey("agenda_item.id"))
    first_page: Mapped[int] = mapped_column(SmallInteger)
    last_page: Mapped[int] = mapped_column(SmallInteger)
    incomplete: Mapped[bool] = mapped_column(Boolean, default=False)  # start not available
    stage: Mapped[str] = mapped_column(String(8))  # the least final constituent page
    words: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    # "~lemma" lexemes from the Czech tagger (morphology.py); None until indexed.
    forms: Mapped[str | None] = mapped_column(TSVECTOR)
    forms_model: Mapped[str | None] = mapped_column(String(64))
    search: Mapped[str] = mapped_column(TSVECTOR, Computed(SEARCH_VECTOR, persisted=True))

    paragraphs: Mapped[list["SpeechParagraph"]] = relationship(order_by="SpeechParagraph.position")

    __table_args__ = (
        UniqueConstraint("speech_id", "content_sha256"),
        CheckConstraint(_in("role", ROLES), "role"),
        CheckConstraint(_in("stage", STAGES), "stage"),
        Index(
            "ix_speech_revision_search_current",
            "search",
            postgresql_using="gin",
            postgresql_where="retired_at IS NULL",
        ),
        Index(
            "ix_speech_revision_current_date",
            "date",
            "id",
            postgresql_where="retired_at IS NULL",
        ),
        Index(
            "ix_speech_revision_current_person",
            "person_id",
            "date",
            postgresql_where="retired_at IS NULL",
        ),
    )


class SpeechParagraph(Base):
    """A paragraph of a speech revision, with the page revision it came from."""

    __tablename__ = "speech_paragraph"

    revision_id: Mapped[int] = mapped_column(ForeignKey("speech_revision.id"), primary_key=True)
    position: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    page_revision_id: Mapped[int] = mapped_column(ForeignKey("page_revision.id"))
    page: Mapped[int] = mapped_column(SmallInteger)
    segment_position: Mapped[int] = mapped_column(SmallInteger)
    text: Mapped[str] = mapped_column(Text)


# --- Votes -------------------------------------------------------------------------


class Vote(Base):
    __tablename__ = "vote"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)  # id_hlasovani
    term_id: Mapped[int] = mapped_column(ForeignKey("term.id"))
    sitting_number: Mapped[int] = mapped_column(SmallInteger)
    number: Mapped[int] = mapped_column(Integer)
    agenda_number: Mapped[int | None] = mapped_column(Integer)
    held_at: Mapped[dt.datetime] = mapped_column(DateTime, index=True)
    kind: Mapped[str] = mapped_column(String(1))  # N normal, R manual, E technical fault
    result: Mapped[str] = mapped_column(String(1))  # A passed, R rejected, X/Q/K other
    invalidated: Mapped[bool] = mapped_column(Boolean, default=False)  # zmatečné
    title: Mapped[str] = mapped_column(Text, default="")
    short_title: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (UniqueConstraint("term_id", "sitting_number", "number"),)


class VoteRecord(Base):
    """One MP's result in a vote: A/B/N/C/F/K registered, @/M absent, W before oath."""

    __tablename__ = "vote_record"

    vote_id: Mapped[int] = mapped_column(ForeignKey("vote.id"), primary_key=True)
    mandate_id: Mapped[int] = mapped_column(ForeignKey("mandate.id"), primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(1))


class Apology(Base):
    """A recorded apology from a sitting day (omluvy); no times = whole day."""

    __tablename__ = "apology"

    id: Mapped[int] = mapped_column(primary_key=True)
    term_id: Mapped[int] = mapped_column(ForeignKey("term.id"))
    mandate_id: Mapped[int] = mapped_column(ForeignKey("mandate.id"), index=True)
    day: Mapped[dt.date] = mapped_column(Date)
    from_time: Mapped[str | None] = mapped_column(String(5))
    to_time: Mapped[str | None] = mapped_column(String(5))


class WordForm(Base):
    """How often a written form stood for a lemma in tagged speeches (morphology.py).

    Search expands each query word to the lemmas its form usually stands for, and
    highlights the other forms of those lemmas. Counts only grow between rebuilds.
    """

    __tablename__ = "word_form"

    form: Mapped[str] = mapped_column(Text, primary_key=True)  # lowercase, with accents
    lemma: Mapped[str] = mapped_column(Text, primary_key=True)
    folded: Mapped[str] = mapped_column(Text, index=True)  # typography.fold(form)
    count: Mapped[int] = mapped_column(Integer)

    # Counts change after every tagging batch; migration 0004 sets fillfactor and
    # autovacuum storage parameters so updates stay in place and dead rows go early.
    __table_args__ = (Index("ix_word_form_lemma", "lemma"),)


DIMENSIONS = 1024  # Voyage 4 series default (docs/related-search.md)


class HalfVector(UserDefinedType):
    """pgvector's halfvec: 16-bit floats, half the size of vector and ample for cosine
    distance. Lists of floats are sent as '[…]' text and cast in SQL."""

    cache_ok = True

    def __init__(self, dimensions: int = DIMENSIONS):
        self.dimensions = dimensions

    def get_col_spec(self, **kw) -> str:
        return f"halfvec({self.dimensions})"

    def bind_processor(self, dialect):
        def process(value):
            return None if value is None else "[" + ",".join(f"{v:.6g}" for v in value) + "]"

        return process

    def bind_expression(self, bindvalue):
        return cast(bindvalue, self)

    def result_processor(self, dialect, coltype):
        def process(value):
            return None if value is None else [float(v) for v in value.strip("[]").split(",")]

        return process

    class comparator_factory(UserDefinedType.Comparator):
        def cosine_distance(self, other):
            return self.op("<=>", return_type=Float)(other)


class SpeechChunk(Base):
    """A passage of a current speech revision, embedded for meaning search (ingest/embed.py).

    A chunk covers consecutive paragraphs, first to last position; a long paragraph is
    split, so several chunks can share one. Chair remarks and speeches under 40 words
    are not embedded.
    """

    __tablename__ = "speech_chunk"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    revision_id: Mapped[int] = mapped_column(
        ForeignKey("speech_revision.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(SmallInteger)
    first_paragraph: Mapped[int] = mapped_column(SmallInteger)
    last_paragraph: Mapped[int] = mapped_column(SmallInteger)
    digest: Mapped[str] = mapped_column(String(64), index=True)  # SHA-256 of the embedded text
    model: Mapped[str] = mapped_column(String(64))
    embedding: Mapped[list[float]] = mapped_column(HalfVector())

    # Migration 0005 adds the HNSW index for cosine distance.
    __table_args__ = (UniqueConstraint("revision_id", "position"),)


class QueryEmbedding(Base):
    """Embedded search queries, so a repeated query costs nothing and waits for no one."""

    __tablename__ = "query_embedding"

    model: Mapped[str] = mapped_column(String(64), primary_key=True)
    query: Mapped[str] = mapped_column(Text, primary_key=True)
    embedding: Mapped[list[float]] = mapped_column(HalfVector())
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AIUsage(Base):
    """Every paid AI request (ai.py), at list price, for the spending limits."""

    __tablename__ = "ai_usage"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    provider: Mapped[str] = mapped_column(String(16))  # "voyage", "anthropic"
    model: Mapped[str] = mapped_column(String(64))
    purpose: Mapped[str] = mapped_column(String(16))  # "documents", "query", "summary"
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6))


class Summary(Base):
    """An AI summary of search results, kept so the same request is answered once.

    `sentences` holds only cited sentences: text, the result numbers it cites and
    the cited (revision, paragraph) pairs. An empty list means the sources did not
    answer the query.
    """

    __tablename__ = "summary"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)  # SHA-256 of the request
    model: Mapped[str] = mapped_column(String(64))
    query: Mapped[str] = mapped_column(Text)
    sentences: Mapped[list] = mapped_column(JSONB)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
