"""Transcript parsing and cross-page assembly, on real captured pages (no network)."""

from pathlib import Path

import pytest

from rozprava.ingest import unl
from rozprava.ingest.parser import (
    UNANCHORED_BASE,
    PageInput,
    ParsedPage,
    ParseError,
    Segment,
    assemble,
    parse_page,
    word_count,
)

PAGES = Path(__file__).parent / "fixtures/psp/pages"


def page(name: str) -> ParsedPage:
    return parse_page((PAGES / f"{name}.htm").read_bytes())


def inputs(term: str, sitting: int, *numbers: int) -> list[PageInput]:
    return [PageInput(n, n, page(f"{term}-s{sitting:03d}{n:03d}")) for n in numbers]


def test_windows_1250_is_decoded_and_speech_labels_found():
    parsed = page("2025ps-s034644")
    assert parsed.replaced_characters == 0
    starts = [(s.anchor, s.label, s.link_person_id) for s in parsed.segments if s.label]
    assert starts == [
        (1, "Místopředseda PSP Jan Skopeček", 6418),
        (2, "Poslanec Jan Papajanovský", 7030),
    ]


def test_paragraphs_keep_their_order_and_wording():
    speech = page("2025ps-s034644").segments[2]
    assert len(speech.paragraphs) == 13
    assert speech.paragraphs[0].startswith(
        "Vážený pane předsedající, vážené kolegyně, vážení kolegové, vážená paní ministryně,"
    )
    # Entities decoded, non-breaking spaces collapsed, nothing else changed.
    assert speech.paragraphs[3].startswith(
        "Proč na tom záleží? Ve třetím pilíři máme dnes 3,9 milionu osob a v úsporách "
        "zhruba 660 miliard korun."
    )
    assert "zavádí automatickou účast zaměstnanců s příspěvkem zaměstnavatele" in (
        " ".join(speech.paragraphs)
    )


def test_page_end_mark_is_not_part_of_the_speech():
    for path in PAGES.glob("*.htm"):
        parsed = parse_page(path.read_bytes())
        assert all(not p.endswith("***") for s in parsed.segments for p in s.paragraphs)


@pytest.mark.parametrize(
    ("name", "stage", "status"),
    [
        ("2025ps-s034644", "draft", "Neprošlo jazykovou korekturou, neautorizováno!"),
        ("2021ps-s112001", "edited", "Neautorizováno!"),
        ("2021ps-s050071", "final", None),
    ],
)
def test_publication_status(name: str, stage: str, status: str | None):
    parsed = page(name)
    assert (parsed.stage, parsed.status_line) == (stage, status)


def test_non_psp_speaker_links_are_kept_but_give_no_person_id():
    minister = page("2025ps-s034648").segments[1]
    assert minister.label == "Místopředsedkyně vlády a ministryně financí ČR Alena Schillerová"
    assert minister.link_person_id is None
    assert minister.link_url and minister.link_url.startswith("https://vlada.gov.cz/")


def test_page_without_labels_is_one_continuation():
    parsed = page("2025ps-s034643")
    assert parsed.continues == "Olga Richterová"
    assert len(parsed.segments) == 1 and parsed.opening is parsed.segments[0]
    assert parsed.time_label == "(12.40 hodin)"


def test_speech_is_joined_across_consecutive_pages():
    speeches = assemble(inputs("2025ps", 34, 642, 643, 644))
    richterova = next(s for s in speeches if s.label == "Poslankyně Olga Richterová")
    assert (richterova.page, richterova.anchor, richterova.pages) == (642, 2, (642, 644))
    assert {p.page for p in richterova.paragraphs} == {642, 643, 644}
    assert richterova.text.endswith("Děkuji za případné odpovědi.")
    assert not richterova.incomplete
    # 642 opens mid-speech and its previous page is not loaded: a fragment.
    assert speeches[0].anchor == 0 and speeches[0].incomplete
    assert speeches[0].continues == "Hana Ančincová"


def test_missing_page_breaks_speech_continuation():
    speeches = assemble(inputs("2025ps", 34, 642, 644))  # 643 missing
    richterova = next(s for s in speeches if s.label == "Poslankyně Olga Richterová")
    assert richterova.pages == (642, 642)
    fragment = next(s for s in speeches if s.page == 644 and s.anchor == 0)
    assert fragment.incomplete and fragment.label is None
    assert fragment.continues == "Olga Richterová"
    assert fragment.text == "Bez tohohle všeho to nebude fungovat. Vy jste si zatím vybrali " + (
        "jenom cestu jednorázových dárečků. Mě to mrzí, ale pořád je prostor se vrátit k těm "
        "nezbytným změnám systémovým. Děkuji za případné odpovědi."
    )


def test_continuation_naming_someone_else_is_not_joined():
    first = ParsedPage(
        "final", None, None, None, (Segment(0, 1, "Poslanec Jan Novák", None, None, ("A.",)),)
    )
    second = ParsedPage("final", None, None, "Petr Svoboda", (Segment(0, paragraphs=("B.",)),))
    speeches = assemble([PageInput(5, 50, first), PageInput(6, 60, second)])
    assert [(s.page, s.anchor, s.text, s.incomplete) for s in speeches] == [
        (5, 1, "A.", False),
        (6, 0, "B.", True),
    ]


def test_headings_are_left_out_and_do_not_split_the_chairs_speech():
    speeches = assemble(inputs("2025ps", 1, 2, 3))
    fragment = speeches[0]  # page 1 is not loaded: Věra Kovářová's speech is a fragment
    assert fragment.continues == "Věra Kovářová"
    assert "Slib poslanců" not in fragment.text
    assert fragment.text.startswith("Nyní přistoupíme k druhému bodu, kterým je")
    assert "Vlastní akt slibu bude probíhat takto" in fragment.text
    oath = speeches[1]
    assert oath.label == "Poslanec Karel Havlíček" and oath.pages == (2, 3)
    assert oath.text.endswith("Miloslav Janulík. (Slibuji.)")


def test_first_page_opening_note_is_not_a_speech():
    speeches = assemble(inputs("2021ps", 112, 1))
    assert [(s.anchor, s.label) for s in speeches] == [
        (1, "Předsedkyně PSP Markéta Pekarová Adamová")
    ]


def test_unanchored_label_starts_a_speech_without_reusing_psp_anchors():
    speeches = assemble(inputs("2021ps", 50, 71, 72))
    blazek = [s for s in speeches if s.label == "Ministr spravedlnosti ČR Pavel Blažek"]
    assert [(s.page, s.anchor, s.pages) for s in blazek] == [
        (71, UNANCHORED_BASE + 13, (71, 72)),
        (72, UNANCHORED_BASE + 2, (72, 72)),
    ]
    chair = next(s for s in speeches if s.page == 71 and s.anchor == 11)
    # The chair goes on after the agenda heading, then the minister takes over.
    assert chair.text.endswith(
        "Z pověření vlády předložený návrh uvede ministr spravedlnosti Pavel Blažek, "
        "kterého prosím, aby se ujal slova."
    )
    assert blazek[0].text.startswith("Dobrý den. Děkuji za slovo.")
    on_72 = [(s.anchor, s.label) for s in speeches if s.page == 72]
    assert on_72[2:] == [
        (2, "Místopředseda PSP Jan Skopeček"),
        (3, "Poslanec Marek Výborný"),
        (4, "Místopředseda PSP Jan Skopeček"),
        (5, "Poslanec Radek Vondráček"),
    ]


def test_pages_without_a_transcript_body_are_rejected():
    with pytest.raises(ParseError):
        parse_page("<html><body>Stránka nenalezena</body></html>".encode("cp1250"))


def test_content_hash_ignores_nothing_that_is_shown():
    a = page("2025ps-s034644")
    assert a.content_sha256 == page("2025ps-s034644").content_sha256
    edited = ParsedPage("edited", "Neautorizováno!", a.time_label, a.continues, a.segments)
    assert edited.content_sha256 != a.content_sha256


def test_word_count():
    assert word_count("Pan poslanec Kupka Martin se omlouvá od 12.20 hodin.") == 10
    assert word_count("opt-out, tzv. „automatická“ účast") == 4


def test_unl_rows_and_dates():
    data = "5435|173|112|2|2024-09-10|1|850|860|\n7030|Mgr.|a\\|b||\n".encode("cp1250")
    assert list(unl.rows(data)) == [
        ["5435", "173", "112", "2", "2024-09-10", "1", "850", "860"],
        ["7030", "Mgr.", "a|b", None],
    ]
    assert unl.date("06.06.1992").isoformat() == "1992-06-06"  # type: ignore[union-attr]
    assert unl.timestamp("2023-02-21 14").isoformat() == "2023-02-21T14:00:00"  # type: ignore[union-attr]
    assert unl.minutes("-1") is None and unl.minutes("770") == 770
