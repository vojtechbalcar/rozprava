"""Parse psp.cz transcript pages and assemble speeches across pages. No I/O here.

A page (sNNNTTT.htm, about ten minutes of debate) holds the text between the
<!-- sx --> and <!-- sy --> markers: an optional status line, an optional time,
an optional "(pokračuje Jméno Příjmení)" marker when the page opens mid-speech,
and paragraphs. A speech starts with a bold link carrying id="rN":

    <p><b><a href="/sqw/detail.sqw?id=7030" id="r2">Poslanec Jan Papajanovský</a></b>: …

Text is kept as written: markup is removed and entities decoded, whitespace
(including the non-breaking spaces psp.cz inserts) collapsed, nothing reworded.
Centred bold paragraphs are agenda headings, not speech.
"""

import hashlib
import html
import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field

PARSER_VERSION = 1
UNANCHORED_BASE = 100  # speech order for labelled starts without an rN anchor
ENCODING = "cp1250"

DRAFT = "Neprošlo jazykovou korekturou, neautorizováno!"
EDITED = "Neautorizováno!"

_BODY = re.compile(r"(?s)<!-- sx -->(.*?)<!-- sy -->")
_STATUS = re.compile(r'(?is)<p class="status[^"]*">(.*?)</p>')
_NAV = re.compile(r'(?is)<div class="document-nav.*?</div>')
_TIME = re.compile(r"(?s)<!-- sttm -->(.*?)<!-- ettm -->")
_CONTINUES = re.compile(r"(?is)^\s*(?:<br\s*/?>\s*)*\(pokračuje\s+([^)<]+?)\s*\)")
_EMPTY_P = re.compile(r"(?is)<p\b[^>]*>\s*(?:<b>\s*</b>\s*)?</p>")
_HEADING = re.compile(r'(?is)<p[^>]*\balign="?center"?[^>]*>(.*?)</p>')
_SPEAKER = re.compile(
    r"(?is)<b>\s*(?:<b>\s*)?<a\s+([^>]*\bid=\"(?:r\d+|unanchored)\"[^>]*)>(.*?)</a>"
    r"\s*</b>(?:\s*</b>)?\s*:?"
)
# A label link opening a paragraph but lacking id="rN" (seen when editors re-cut a page).
_UNANCHORED = re.compile(
    r"(?is)(<p\b[^>]*>\s*)(?:<b>\s*)?<a\s+(href=\"[^\"]*\")\s*>([^<]{3,200})</a>\s*(?:</b>\s*)?:"
)
_ATTR = re.compile(r'(\w+)="([^"]*)"')
_BLOCK = re.compile(r"(?i)<p\b[^>]*>|<br\s*/?>")
_TAG = re.compile(r"(?s)<[^>]+>")
_PERSON_LINK = re.compile(r"^(?:https?://www\.psp\.cz)?/sqw/detail\.sqw\?id=(\d+)(?:&|$)")
_END_MARK = re.compile(r"\s*\*{3}\s*$")
_HEADING_MARK = "\x00heading\x00"


class ParseError(ValueError):
    """The page does not have the expected transcript layout."""


@dataclass(frozen=True)
class Segment:
    """A labelled speech start, a headerless run of text, or an agenda heading.

    A start normally has psp.cz's anchor number (rN). A start whose label has no
    anchor gets None; assembly numbers it UNANCHORED_BASE + position.
    """

    position: int
    anchor: int | None = None
    label: str | None = None
    link_url: str | None = None
    link_person_id: int | None = None
    paragraphs: tuple[str, ...] = ()
    heading: bool = False


@dataclass(frozen=True)
class ParsedPage:
    stage: str  # "draft", "edited" or "final"
    status_line: str | None
    time_label: str | None
    continues: str | None  # the name in "(pokračuje …)", if the page opens mid-speech
    segments: tuple[Segment, ...]
    replaced_characters: int = 0  # undecodable bytes; should be 0

    @property
    def content_sha256(self) -> str:
        data = asdict(self)
        data.pop("replaced_characters")
        blob = json.dumps(data, ensure_ascii=False, sort_keys=True).encode()
        return hashlib.sha256(blob).hexdigest()

    @property
    def opening(self) -> Segment | None:
        """Text before the first speech label: the tail of an earlier speech."""
        first = self.segments[0] if self.segments else None
        if first and first.label is None and not first.heading and first.paragraphs:
            return first
        return None


def clean(fragment: str) -> str:
    """Visible text of an HTML fragment, whitespace collapsed."""
    text = html.unescape(_TAG.sub(" ", fragment)).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def stage_of(status_line: str | None) -> str:
    if status_line is None:
        return "final"
    if status_line == EDITED:
        return "edited"
    return "draft"  # DRAFT, or anything unexpected: treat as least final


def _paragraphs(chunk: str) -> list[str]:
    out = []
    for block in _BLOCK.split(chunk):
        if _HEADING_MARK in block:
            continue
        text = clean(block)
        if text:
            out.append(text)
    return out


def decode(raw: bytes) -> tuple[str, int]:
    text = raw.decode(ENCODING, errors="replace")
    return text, text.count("�")


def parse_page(raw: bytes) -> ParsedPage:
    text, replaced = decode(raw)
    match = _BODY.search(text)
    if not match:
        raise ParseError("No transcript body (<!-- sx --> … <!-- sy -->)")
    body = match.group(1)
    status = _STATUS.search(body)
    status_line = clean(status.group(1)) if status else None
    body = _STATUS.sub(" ", body)
    body = _NAV.sub(" ", body)
    body = body.split("<!-- ex -->", 1)[-1]
    time = _TIME.search(body)
    time_label = clean(time.group(1)) if time else None
    body = _TIME.sub(" ", body)
    body = _EMPTY_P.sub(" ", body)
    marker = _CONTINUES.match(body)
    continues = clean(marker.group(1)) if marker else None
    if marker:
        body = body[marker.end() :]

    # Headings become their own segments; keep their place in the flow.
    headings: list[str] = []

    def mark_heading(m: re.Match[str]) -> str:
        headings.append(clean(m.group(1)))
        return f"<p>{_HEADING_MARK}{len(headings) - 1}{_HEADING_MARK}</p>"

    body = _HEADING.sub(mark_heading, body)
    body = _UNANCHORED.sub(r'\1<b><a \2 id="unanchored">\3</a></b>:', body)

    segments: list[Segment] = []
    pieces = _SPEAKER.split(body)  # [text, attrs, label, text, attrs, label, text, …]

    def add_text(chunk: str, anchor_segment: Segment | None) -> None:
        # Split a chunk on heading markers; text after a heading is its own segment.
        parts = re.split(rf"{_HEADING_MARK}(\d+){_HEADING_MARK}", chunk)
        for i, part in enumerate(parts):
            if i % 2 == 1:
                if headings[int(part)]:
                    segments.append(
                        Segment(len(segments), paragraphs=(headings[int(part)],), heading=True)
                    )
                continue
            paragraphs = tuple(_paragraphs(part))
            if i == 0 and anchor_segment is not None:
                segments.append(Segment(**{**asdict(anchor_segment), "paragraphs": paragraphs}))
            elif paragraphs:
                segments.append(Segment(len(segments), paragraphs=paragraphs))

    add_text(pieces[0], None)
    for i in range(1, len(pieces), 3):
        attrs = dict(_ATTR.findall(pieces[i]))
        href = attrs.get("href") or None
        link = _PERSON_LINK.match(href) if href else None
        start = Segment(
            position=len(segments),
            anchor=int(attrs["id"][1:]) if attrs["id"] != "unanchored" else None,
            label=clean(pieces[i + 1]).rstrip(":").strip(),
            link_url=href,
            link_person_id=int(link.group(1)) if link else None,
        )
        add_text(pieces[i + 2], start)

    if segments:  # "***" marks the end of the page, not of the speech
        last = segments[-1]
        if last.paragraphs:
            tail = _END_MARK.sub("", last.paragraphs[-1])
            paragraphs = last.paragraphs[:-1] + ((tail,) if tail else ())
            segments[-1] = Segment(**{**asdict(last), "paragraphs": paragraphs})
    return ParsedPage(
        stage=stage_of(status_line),
        status_line=status_line,
        time_label=time_label,
        continues=continues,
        segments=tuple(segments),
        replaced_characters=replaced,
    )


# --- Assembly across pages ---------------------------------------------------------


@dataclass(frozen=True)
class PageInput:
    """A page's current parsed revision, as stored."""

    page: int
    revision_id: int
    parsed: ParsedPage


@dataclass(frozen=True)
class Paragraph:
    page: int
    revision_id: int
    segment_position: int
    text: str


@dataclass
class AssembledSpeech:
    page: int  # where it starts
    anchor: int  # rN, or 0 for a fragment whose beginning is not available
    label: str | None
    link_person_id: int | None
    continues: str | None  # for fragments: the name from "(pokračuje …)"
    incomplete: bool
    paragraphs: list[Paragraph] = field(default_factory=list)
    stages: set[str] = field(default_factory=set)

    @property
    def text(self) -> str:
        return "\n\n".join(p.text for p in self.paragraphs)

    @property
    def pages(self) -> tuple[int, int]:
        pages = [p.page for p in self.paragraphs] or [self.page]
        return min(pages), max(pages)

    @property
    def stage(self) -> str:
        for stage in ("draft", "edited", "final"):
            if stage in self.stages:
                return stage
        return "final"

    def add(self, page: PageInput, segment: Segment) -> None:
        self.stages.add(page.parsed.stage)
        self.paragraphs += [
            Paragraph(page.page, page.revision_id, segment.position, text)
            for text in segment.paragraphs
        ]


def _name_key(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip().casefold()


def _continuation_supported(previous: AssembledSpeech | None, marker: str | None) -> bool:
    """Opening text continues the previous page's last speech only if there is one and
    the "(pokračuje …)" marker, when present, names the same speaker."""
    if previous is None:
        return False
    if marker is None:
        return True
    name = _name_key(marker)
    if previous.label is not None:
        label = _name_key(previous.label)
        return label == name or label.endswith(" " + name)
    return previous.continues is not None and _name_key(previous.continues) == name


def assemble(pages: Iterable[PageInput]) -> list[AssembledSpeech]:
    """Speeches of one sitting from its available pages, in page order.

    A speech continues onto the next page only across consecutive available pages
    with a supported continuation. Opening text that cannot be attached becomes a
    fragment (anchor 0, incomplete). The first page of a sitting has no earlier
    page, so its opening text is a note ("Schůze zahájena …"), not a speech.
    Headings are left out of speech text.
    """
    speeches: list[AssembledSpeech] = []
    previous_page: int | None = None
    last: AssembledSpeech | None = None
    for page in sorted(pages, key=lambda p: p.page):
        consecutive = previous_page is not None and page.page == previous_page + 1
        if not consecutive:
            last = None
        opening = page.parsed.opening
        if opening is not None:
            if consecutive and _continuation_supported(last, page.parsed.continues):
                assert last is not None
                last.add(page, opening)
            elif page.page > 1:
                last = AssembledSpeech(
                    page=page.page,
                    anchor=0,
                    label=None,
                    link_person_id=None,
                    continues=page.parsed.continues,
                    incomplete=True,
                )
                last.add(page, opening)
                speeches.append(last)
        for segment in page.parsed.segments:
            if segment.label is None:
                # Agenda headings are inserted mid-speech: the chair announces an item
                # and goes on. Untitled text after one continues the same speech.
                if segment is not opening and not segment.heading and last is not None:
                    last.add(page, segment)
                continue
            last = AssembledSpeech(
                page=page.page,
                anchor=(
                    segment.anchor
                    if segment.anchor is not None
                    else UNANCHORED_BASE + segment.position
                ),
                label=segment.label,
                link_person_id=segment.link_person_id,
                continues=None,
                incomplete=False,
            )
            last.add(page, segment)
            speeches.append(last)
        previous_page = page.page
    return [s for s in speeches if s.paragraphs]


def word_count(text: str) -> int:
    return len(re.findall(r"\w+(?:[-'’]\w+)*", text))


def content_hash(values: Sequence[object]) -> str:
    blob = json.dumps(values, ensure_ascii=False, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()
