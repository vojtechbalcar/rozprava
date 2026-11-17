"""Render the static design preview from the app's real templates and sample data.

preview/data.json holds real excerpts from psp.cz transcripts and open data (built by
scratch/scripts/build_preview.py, with every quote checked as an exact substring of
its transcript). The output in preview/site/ is plain HTML: serve the folder and open
index.html.

Usage: uv run python scripts/render_preview.py
"""

import json
import shutil
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

from rozprava.activity import calendar
from rozprava.parties import INDEPENDENT, PARTIES, Party, swatches
from rozprava.templating import STATIC, make_env
from rozprava.typography import MONTHS_GENITIVE, czech_sort_key

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "preview/data.json"
OUT = ROOT / "preview/site"

PAGES = {
    "home": ("index.html", "Úvod"),
    "search": ("hledat.html", "Hledání"),
    "transcript": ("prepis.html", "Přepis"),
    "mp": ("poslanec.html", "Poslanec"),
    "mps": ("poslanci.html", "Poslanci"),
    "sessions": ("schuze.html", "Schůze"),
    "how": ("jak-to-funguje.html", "Jak to funguje"),
    "card": ("karta.html", "Karta citace"),
    "notfound": ("404.html", "404"),
    "design": ("design.html", "/_design"),
}
TEMPLATES = {"notfound": "notfound.html"}
SAMPLE_PAGE = 644  # the one transcript page in the sample data
PASSAGE_RESULT = 1  # the search result whose passage that page highlights
MONTH_SHORT = ("led", "úno", "bře", "dub", "kvě", "čvn", "čvc", "srp", "zář", "říj", "lis", "pro")
MONTH_NOMINATIVE = (
    "leden",
    "únor",
    "březen",
    "duben",
    "květen",
    "červen",
    "červenec",
    "srpen",
    "září",
    "říjen",
    "listopad",
    "prosinec",
)


def link(name: str, anchor: str | None = None, **params: object) -> str:
    """Map app routes onto the handful of static preview pages."""
    if name == "methodology":
        name = "how"
    url = PAGES[name][0]
    if name == "transcript":
        if params.get("page") not in (None, SAMPLE_PAGE):
            return url
        if params.get("result") == PASSAGE_RESULT:
            return url + "#pasaz"
    if name in ("search", "mps", "card") and params:
        url += "?" + urlencode(params)
    return f"{url}#{anchor}" if anchor else url


def static(path: str) -> str:
    return f"static/{path}"


def by_count(counter: Counter, key=lambda k: czech_sort_key(k)) -> list[tuple[str, int]]:
    """Facets: by count, ties alphabetical in Czech order (DESIGN.md §10.4)."""
    return sorted(counter.items(), key=lambda kv: (-kv[1], key(kv[0])))


def alphabetical_parties(names) -> list[str]:
    """Party lists that aren't counts of results: alphabetical, independents last."""
    named = sorted((p for p in names if p != INDEPENDENT), key=czech_sort_key)
    return named + ([INDEPENDENT] if INDEPENDENT in names else [])


def search_facets(search: dict) -> dict:
    results = search["results"]
    parties = by_count(Counter(r["speaker"]["party"] for r in results if r["speaker"]["party"]))
    speakers = by_count(
        Counter(r["speaker"]["name"] for r in results), key=lambda n: czech_sort_key(n.split()[-1])
    )
    months = [
        {**m, "label": f"{MONTH_SHORT[int(m['month'][5:]) - 1]} {m['month'][:4]}"}
        for m in search["months"]
    ]
    return {
        "parties": parties,
        "parties_max": max(n for _, n in parties),
        "speakers": speakers,
        "speakers_max": max(n for _, n in speakers),
        "months": months,
        "months_max": max(m["count"] for m in months) or 1,
    }


def activity_views(mp: dict, term: dict) -> tuple[dict, list]:
    days = mp["activity"]
    first, last = date.fromisoformat(term["first_day"]), date.fromisoformat(term["last_day"])
    graphs = {
        "term": calendar(days, first, last),
        "2026": calendar(days, date(2026, 1, 1), last),
        "2025": calendar(days, first, date(2025, 12, 31)),
    }
    months: dict[str, list] = defaultdict(list)
    for d in days:
        y, m = int(d["date"][:4]), int(d["date"][5:7])
        months[f"{MONTH_NOMINATIVE[m - 1]} {y}"].append(d)
    return graphs, list(months.items())


def quote_card(search: dict) -> dict:
    """The composer's sample: a span of result 1, chosen mid-sentence, so it needs a leading …"""
    source = search["results"][0]
    start = source["text"].index("zavádí automatickou účast")
    end = source["text"].index("říct ne.") + len("říct ne.")
    span = source["text"][start:end]
    assert span in source["text"] and len(span) <= 280
    return {
        "source": source,
        "span": span,
        "highlight": "automatickou účast",
        "cut_start": start > 0,
        "cut_end": False,
    }


def card_sources(data: dict) -> dict:
    """Only stored, verbatim sources can enter the quote composer."""
    sources = {}
    for result in data["search"]["results"]:
        c = result["catalog"]
        slug = f"{c['term']}-{c['sitting']:03d}-{c['page']:04d}-{c['order']}"
        sources[f"result-{slug}"] = result
    transcript = data["transcript"]
    for speech in transcript["speeches"]:
        c = speech["catalog"]
        slug = f"{c['term']}-{c['sitting']:03d}-{c['page']:04d}-{c['order']}"
        for n, para in enumerate(speech["paras"], 1):
            sources[f"paragraph-{slug}-{n}"] = {
                "text": para.get("text") or para["before"] + para["mark"] + para["after"],
                "speaker": speech["speaker"],
                "catalog": c,
                "date": transcript["date"],
                "page": transcript["page"],
                "sitting": transcript["sitting"],
                "status": transcript["status"],
                "psp_url": transcript["psp_url"],
            }
    return sources


def palette_index(data: dict) -> dict:
    """What the ⌘K palette searches, inlined as JSON (DESIGN.md §7.4)."""
    bills: dict[int, str] = {}
    for item in [data["search"]["results"][0]["agenda"], *data["mp"]["topics"]] + [
        b for s in data["sessions"] for b in s["top"]
    ]:
        if item and item.get("tisk"):
            bills.setdefault(item["tisk"], item["short"])
    return {
        "mps": [
            {
                "name": m["name"],
                "sort": m["surname"],
                "party": PARTIES[m["party"]].label if m["party"] in PARTIES else m["party"],
                "region": m["region"],
                "initials": m["initials"],
                "url": link("mp", slug=m["slug"]),
            }
            for m in sorted(data["mps"], key=lambda m: czech_sort_key(m["surname"]))
        ],
        "bills": [{"tisk": t, "title": s, "url": link("search")} for t, s in sorted(bills.items())],
        "sittings": [
            {"number": s["number"], "from": s["from"], "to": s["to"], "url": link("sessions")}
            for s in data["sessions"]
        ],
        "actions": [
            {"title": "Přepnout motiv", "action": "theme"},
            {"title": "Jak to funguje", "url": link("how")},
            {"title": "Nejnovější schůze", "url": link("sessions")},
        ],
        "search": link("search"),
        "months": MONTHS_GENITIVE,
    }


def normalise_demo() -> list[dict]:
    """Normalisation on neutral sample colours, never on party colours (§3.4)."""
    sample = {"A": "#1f6fd1", "B": "#3a5fc4", "C": "#c2185b", "D": "#2e7d32", "E": "#151515"}
    result = swatches({k: Party(k, k, v) for k, v in sample.items()})
    return [{"hex": v, "swatch": result[k]} for k, v in sample.items() if result[k].css]


def render(out: Path = OUT, data_path: Path = DATA) -> dict[str, Path]:
    """Render every preview page into out/ and return {page name: file}."""
    data = json.loads(data_path.read_text(encoding="utf-8"))
    # A summary may only refer to sources actually available in the result set.
    source_ids = {r["n"] for r in data["search"]["results"]}
    data["search"]["answer"] = [
        sentence
        for sentence in data["search"]["answer"]
        if sentence.get("cites") and set(sentence["cites"]) <= source_ids
    ]
    for speech in data["transcript"]["speeches"]:
        speech.setdefault("continued_from", None)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(STATIC, out / "static")

    env = make_env(
        link=link,
        static=static,
        preview=data["meta"],
        preview_pages=PAGES,
        updated=data["meta"]["updated"],
        palette=palette_index(data),
        term=data["term"],
        archive=data["archive"],
        filters={
            "obdobi": [{"value": "10", "label": "10. (2025–)"}],
            "poslanec": sorted(
                {r["speaker"]["name"] for r in data["search"]["results"]}, key=czech_sort_key
            ),
            "strana": [
                p
                for p, _ in by_count(
                    Counter(r["speaker"]["party"] for r in data["search"]["results"])
                )
            ],
            "tisk": [
                {
                    "value": str(data["search"]["results"][0]["agenda"]["tisk"]),
                    "label": "tisk 285 · Penzijní spoření",
                }
            ],
        },
    )
    mps = sorted(
        data["mps"], key=lambda m: (czech_sort_key(m["surname"]), czech_sort_key(m["forename"]))
    )
    for i, m in enumerate(mps):
        m["sort_key"] = f"{i:04d}"
    party_counts = Counter(m["party"] for m in mps)
    graphs, compact = activity_views(data["mp"], data["term"])
    demo_mp = next(m for m in mps if m["surname"] == "Jurečka")
    context = {
        "home": {"home": data["home"]},
        "search": {"search": data["search"], "facets": search_facets(data["search"])},
        "transcript": {"t": data["transcript"]},
        "mp": {"mp": data["mp"], "graphs": graphs, "compact": compact},
        "mps": {
            "mps": mps,
            "parties": by_count(party_counts),
            "regions": sorted({m["region"] for m in mps}, key=czech_sort_key),
        },
        "sessions": {"sessions": data["sessions"]},
        "how": {},
        "card": {"card": quote_card(data["search"]), "card_sources": card_sources(data)},
        "notfound": {},
        "design": {
            "search": data["search"],
            "party_list": alphabetical_parties(PARTIES),
            "normalise_demo": normalise_demo(),
            "demo_mp": demo_mp,
        },
    }
    written = {}
    for name, (filename, _) in PAGES.items():
        template = TEMPLATES.get(name, f"{name}.html")
        html = env.get_template(template).render(page=name, **context[name])
        written[name] = out / filename
        written[name].write_text(html, encoding="utf-8")
    # The component review is a development-only static route.
    design_dir = out / "_design"
    design_dir.mkdir()
    design_html = written["design"].read_text(encoding="utf-8")
    (design_dir / "index.html").write_text(
        design_html.replace("<head>", '<head>\n  <base href="../">', 1), encoding="utf-8"
    )
    return written


def main() -> None:
    for path in render().values():
        print("wrote", path.relative_to(ROOT))


if __name__ == "__main__":
    main()
