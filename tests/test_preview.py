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
    expected = tokens.render(tokens.frontmatter(tokens.DESIGN.read_text(encoding="utf-8")))
    assert tokens.OUT.read_text(encoding="utf-8") == expected


def test_preview_quotes_are_verbatim(tmp_path):
    pages = load_script("render_preview").render(out=tmp_path)
    data = json.loads((ROOT / "preview/data.json").read_text(encoding="utf-8"))

    cards = data["search"]["results"] + data["mp"]["speeches"] + data["home_cards"]
    shown = set(quotes_in(pages["search"]) + quotes_in(pages["mp"]) + quotes_in(pages["home"]))
    for card in cards:
        assert card["text"] in shown, card["text"][:60]

    paragraphs = [
        p.get("text") or p["before"] + p["mark"] + p["after"]
        for speech in data["transcript"]["speeches"]
        for p in speech["paras"]
    ]
    assert quotes_in(pages["transcript"]) == paragraphs


def test_quote_card_marks_cuts_inside_sentences_only():
    from rozprava.templating import make_env

    env = make_env(link=lambda name, **kw: "#", static=lambda path: path)
    card = env.get_template("_macros.html").module.quote_card  # type: ignore[attr-defined]
    base = {
        "speaker": {"name": "Jan Novák", "slug": "1-jan-novak", "party": None, "role": None},
        "date": "2026-11-06",
        "sitting": 34,
        "page": 644,
        "term": 10,
        "anchor": "r2",
        "status": None,
        "agenda": None,
        "psp_url": "https://www.psp.cz/",
    }
    whole = str(card({**base, "text": "Celá věta.", "lead": True, "trail": True}))
    cut = str(card({**base, "text": "a pak řekl, že", "lead": True, "trail": True}))
    assert "quote__cut" not in whole
    assert cut.count("quote__cut") == 2
    assert "a pak řekl, že" in cut.replace(" ", " ")
