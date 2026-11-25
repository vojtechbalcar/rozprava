"""The design preview renders, the tokens match DESIGN.md, and quotes stay verbatim."""

import importlib.util
import json
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class QuoteText(HTMLParser):
    """Collect the visible text of every <blockquote> and every transcript paragraph."""

    def __init__(self) -> None:
        super().__init__()
        self.depth = 0
        self.hidden = 0
        self.current: list[str] = []
        self.quotes: list[str] = []

    def handle_starttag(self, tag, attrs):
        classes = (dict(attrs).get("class") or "").split()
        if tag == "blockquote" or (tag == "p" and "speech__text" in classes):
            self.depth += 1
        elif self.depth and dict(attrs).get("aria-hidden") == "true":
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag == "span" and self.hidden:
            self.hidden -= 1
        elif self.depth and tag in ("blockquote", "p"):
            self.depth -= 1
            if not self.depth:
                self.quotes.append("".join(self.current))
                self.current = []

    def handle_data(self, data):
        if self.depth and not self.hidden:
            self.current.append(data)


def quotes_in(path: Path) -> list[str]:
    parser = QuoteText()
    parser.feed(path.read_text(encoding="utf-8"))
    # Templates indent the markup; the quote itself is compared exactly, nbsp as space.
    return [q.strip().replace("\u00a0", " ") for q in parser.quotes]


def test_tokens_css_matches_design_md():
    tokens = load_script("build_tokens")
    expected = tokens.render(tokens.DESIGN.read_text(encoding="utf-8"))
    assert tokens.OUT.read_text(encoding="utf-8") == expected


def test_preview_quotes_are_verbatim(tmp_path):
    pages = load_script("render_preview").render(out=tmp_path)
    data = json.loads((ROOT / "preview/data.json").read_text(encoding="utf-8"))

    from rozprava.typography import clip, typeset

    for name, cards in (
        ("search", data["search"]["results"]),
        ("mp", data["mp"]["speeches"]),
        ("home", [data["home"]["featured"]]),
    ):
        expected = [
            typeset(clip(c["text"], 280) if name != "home" else c["text"]).replace("\u00a0", " ")
            for c in cards
        ]
        assert quotes_in(pages[name]) == expected

    paragraphs = [
        p.get("text") or p["before"] + p["mark"] + p["after"]
        for speech in data["transcript"]["speeches"]
        for p in speech["paras"]
    ]
    assert quotes_in(pages["transcript"]) == paragraphs


def test_quote_card_marks_cuts_inside_sentences_only():
    from rozprava.templating import make_env

    env = make_env(link=lambda name, **kw: "#", static=lambda path: path)
    card = env.get_template("_macros.html").module.result_object  # type: ignore[attr-defined]
    base = {
        "speaker": {"name": "Jan Novák", "slug": "1-jan-novak", "party": None, "role": None},
        "date": "2026-11-06",
        "sitting": 34,
        "page": 644,
        "term": 10,
        "anchor": "r2",
        "catalog": {"term": 10, "sitting": 34, "page": 644, "order": 2},
        "status": None,
        "agenda": None,
        "psp_url": "https://www.psp.cz/",
    }
    whole = str(card({**base, "text": "Celá věta.", "lead": True, "trail": True}))
    cut = str(card({**base, "text": "a pak řekl, že", "lead": True, "trail": True}))
    assert 'class="cut"' not in whole
    assert cut.count('class="cut"') == 2
    assert "a pak řekl, že" in cut.replace(" ", " ")


def test_summary_drops_uncited_and_missing_sources(tmp_path):
    data = json.loads((ROOT / "preview/data.json").read_text(encoding="utf-8"))
    data["search"]["answer"] += [
        {"text": "UNSUPPORTED_SENTENCE", "cites": []},
        {"text": "MISSING_SOURCE_SENTENCE", "cites": [999]},
    ]
    fixture = tmp_path / "fixture.json"
    fixture.write_text(json.dumps(data), encoding="utf-8")
    pages = load_script("render_preview").render(out=tmp_path / "site", data_path=fixture)
    html = pages["search"].read_text(encoding="utf-8")
    assert "UNSUPPORTED_SENTENCE" not in html and "MISSING_SOURCE_SENTENCE" not in html
    assert data["search"]["answer"][0]["text"][:20] in html.replace("\u00a0", " ")


def test_filter_links_preserve_czech_query_and_anchor():
    from urllib.parse import parse_qs, urlparse

    url = load_script("render_preview").link(
        "search", q="lékařská fakulta", klub="STAN", anchor="v1"
    )
    parts = urlparse(url)
    assert parse_qs(parts.query) == {"q": ["lékařská fakulta"], "klub": ["STAN"]}
    assert parts.fragment == "v1"


def test_composer_sources_are_exact_stored_paragraphs():
    data = json.loads((ROOT / "preview/data.json").read_text(encoding="utf-8"))
    sources = load_script("render_preview").card_sources(data)
    expected = [
        p.get("text") or p["before"] + p["mark"] + p["after"]
        for speech in data["transcript"]["speeches"]
        for p in speech["paras"]
    ]
    assert [v["text"] for k, v in sources.items() if k.startswith("paragraph-")] == expected


def test_local_fonts_cover_czech_regular_and_bold():
    from fontTools.ttLib import TTFont

    required = set(
        map(
            ord,
            "Příliš žluťoučký kůň úpěl ďábelské ódy. PŘÍLIŠ ŽLUŤOUČKÝ KŮŇ ÚPĚL ĎÁBELSKÉ ÓDY. „“–",
        )
    )
    directory = ROOT / "src/rozprava/static/fonts"
    for family in (
        "cooper-hewitt-400",
        "cooper-hewitt-600",
        "source-serif-4",
        "ibm-plex-mono-400",
        "ibm-plex-mono-500",
    ):
        covered = set()
        files = list(directory.glob(f"{family}*.woff2"))
        assert files
        for path in files:
            with TTFont(path) as font:
                cmap = font.getBestCmap()
                assert cmap is not None
                covered.update(cmap)
        assert required <= covered, (family, required - covered)
