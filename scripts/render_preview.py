"""Render the static design preview from the app's real templates and sample data.

preview/data.json holds real excerpts from psp.cz transcripts and open data (built by
scratch/scripts/build_preview.py, with every quote checked as an exact substring of
its transcript). The output in preview/site/ is plain HTML: open index.html directly.

Usage: uv run python scripts/render_preview.py
"""

import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path

from rozprava.templating import STATIC, make_env
from rozprava.typography import czech_initial, czech_sort_key

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "preview/data.json"
OUT = ROOT / "preview/site"

PAGES = {
    "home": ("index.html", "Úvod"),
    "search": ("hledat.html", "Výsledky hledání"),
    "transcript": ("prepis.html", "Přepis"),
    "mp": ("poslanec.html", "Profil poslance"),
    "mps": ("poslanci.html", "Poslanci"),
    "states": ("stavy.html", "Stavy"),
}
SAMPLE_PAGE = 644  # the one transcript page in the sample data
PASSAGE_RESULT = 1  # the search result whose passage that page highlights


def link(name: str, anchor: str | None = None, **params: object) -> str:
    """Map app routes onto the handful of static preview pages."""
    if name == "methodology":
        return "index.html#jak-to-funguje"
    url = PAGES[name][0]
    if name == "transcript":
        if params.get("page") != SAMPLE_PAGE:
            return url
        if params.get("result") == PASSAGE_RESULT:
            return url + "#pasaz"
    return f"{url}#{anchor}" if anchor else url


def static(path: str) -> str:
    return f"static/{path}"


def by_party(rows: list[dict]) -> list[tuple[str, int]]:
    """Parties alphabetically, with non-attached MPs last. Never by size or side."""
    counts = Counter(r["party"] for r in rows if r["party"])
    named = sorted((p for p in counts if p != "Nezařazení"), key=czech_sort_key)
    return [(p, counts[p]) for p in named] + (
        [("Nezařazení", counts["Nezařazení"])] if "Nezařazení" in counts else []
    )


def search_facets(results: list[dict]) -> dict:
    speakers = Counter(r["speaker"]["name"] for r in results)
    return {
        "parties": by_party([r["speaker"] for r in results]),
        "speakers": sorted(speakers.items(), key=lambda kv: czech_sort_key(kv[0].split()[-1])),
    }


def mp_index(mps: list[dict]) -> list[tuple[str, list[dict]]]:
    groups: dict[str, list[dict]] = defaultdict(list)

    def key(m: dict) -> tuple:
        return czech_sort_key(m["surname"]), czech_sort_key(m["forename"])

    for mp in sorted(mps, key=key):
        groups[czech_initial(mp["surname"])].append(mp)
    return sorted(groups.items(), key=lambda kv: czech_sort_key(kv[0]))


def render(out: Path = OUT, data_path: Path = DATA) -> dict[str, Path]:
    """Render every preview page into out/ and return {page name: file}."""
    data = json.loads(data_path.read_text(encoding="utf-8"))
    for speech in data["transcript"]["speeches"]:
        speech.setdefault("continued_from", None)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(STATIC, out / "static")

    env = make_env(link=link, static=static, preview=data["meta"], preview_pages=PAGES)
    context = {
        "home": {"archive": data["archive"], "cards": data["home_cards"]},
        "search": {"search": data["search"], "facets": search_facets(data["search"]["results"])},
        "transcript": {"t": data["transcript"]},
        "mp": {"mp": data["mp"]},
        "mps": {
            "groups": mp_index(data["mps"]),
            "parties": by_party(data["mps"]),
            "total": len(data["mps"]),
        },
        "states": {"search": data["search"]},
    }
    written = {}
    for name, (filename, _) in PAGES.items():
        html = env.get_template(f"{name}.html").render(page=name, **context[name])
        written[name] = out / filename
        written[name].write_text(html, encoding="utf-8")
    return written


def main() -> None:
    for path in render().values():
        print("wrote", path.relative_to(ROOT))


if __name__ == "__main__":
    main()
