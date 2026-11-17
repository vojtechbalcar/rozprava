"""Download the self-hosted fonts (Latin + Latin Extended only) and write fonts.css.

Families (DESIGN.md §4.1):
- Cooper Hewitt (sans: UI and display), from the museum's official OTF release,
  subset and converted to woff2 here. It passed the §4.5 diacritics test.
- Source Serif 4 (serif: verbatim speech), variable with its optical-size axis.
- IBM Plex Mono (mono: meta, catalogue numbers, labels), 400 and 500.
- Schibsted Grotesk, the sans fallback named in the spec. Cooper Hewitt has no
  narrow no-break space (U+202F, the Czech thousands separator), so the browser
  takes that one glyph from here.

Czech needs both subsets: ě, š, č, ř, ž, ů live in Latin Extended, while „ “ and
the no-break spaces live in Latin.

Usage: uv run python scripts/fetch_fonts.py
"""

import io
import re
import shutil
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "src/rozprava/static/fonts"
CSS = ROOT / "src/rozprava/static/css/fonts.css"

GOOGLE_FAMILIES = (
    "family=Source+Serif+4:ital,opsz,wght@0,8..60,400..600;1,8..60,400..600"
    "&family=IBM+Plex+Mono:wght@400;500"
    "&family=Schibsted+Grotesk:wght@400..600"
)
GOOGLE_API = f"https://fonts.googleapis.com/css2?{GOOGLE_FAMILIES}&display=swap"
# Google only serves woff2 with unicode-range subsets to a modern browser.
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"
KEEP = ("latin", "latin-ext")
BLOCK = re.compile(r"/\* ([\w-]+) \*/\s*@font-face \{(.*?)\}", re.S)

# Google's Latin subset leaves out arrows; links use → ← ↗ (DESIGN.md §6).
ARROWS = "←↑→↓↗"
ARROW_FAMILIES = {
    "IBM Plex Mono": ("ibm-plex-mono", "400;500"),
    "Source Serif 4": ("source-serif-4", "400..600"),
}

COOPER_ZIP = "https://www.cooperhewitt.org/wp-content/uploads/fonts/CooperHewitt-OTF-public.zip"
COOPER_WEIGHTS = {"Book": 400, "Medium": 500, "Semibold": 600}
# Latin + Latin-1 + Latin Extended-A/B + punctuation, spaces, arrows, currency.
COOPER_UNICODES = "U+0000-024F,U+02C6-02DD,U+2000-206F,U+20AC,U+2122,U+2190-2199,U+2212"

LICENSES = {
    "source-serif-4": "https://raw.githubusercontent.com/google/fonts/main/ofl/sourceserif4/OFL.txt",
    "ibm-plex-mono": "https://raw.githubusercontent.com/google/fonts/main/ofl/ibmplexmono/OFL.txt",
    "schibsted-grotesk": "https://raw.githubusercontent.com/google/fonts/main/ofl/schibstedgrotesk/OFL.txt",
}


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def face(family: str, style: str, weight: str, name: str, ranges: str) -> str:
    return (
        f"@font-face {{\n  font-family: '{family}';\n  font-style: {style};\n"
        f"  font-weight: {weight};\n  font-display: swap;\n"
        f"  src: url(../fonts/{name}) format('woff2');\n  unicode-range: {ranges};\n}}\n"
    )


def google_fonts(out: list[str]) -> None:
    css = get(GOOGLE_API).decode()
    for subset_name, body in BLOCK.findall(css):
        if subset_name not in KEEP:
            continue
        family = re.search(r"font-family: '([^']+)'", body)
        style = re.search(r"font-style: (\w+)", body)
        weight = re.search(r"font-weight: ([\d ]+);", body)
        url = re.search(r"src: url\((\S+?)\)", body)
        ranges = re.search(r"unicode-range: ([^;]+);", body)
        assert family and style and weight and url and ranges, body
        slug = family.group(1).lower().replace(" ", "-")
        italic = "-italic" if style.group(1) == "italic" else ""
        static_weight = "" if " " in weight.group(1) else f"-{weight.group(1)}"
        name = f"{slug}{italic}{static_weight}-{subset_name}.woff2"
        (FONTS / name).write_bytes(get(url.group(1)))
        out.append(f"/* {family.group(1)} {style.group(1)} {weight.group(1)}, {subset_name} */\n")
        out.append(face(family.group(1), style.group(1), weight.group(1), name, ranges.group(1)))
        print("saved", name)

    for family, (slug, weights) in ARROW_FAMILIES.items():
        query = urllib.parse.urlencode({"family": f"{family}:wght@{weights}", "text": ARROWS})
        body = get(f"https://fonts.googleapis.com/css2?{query}").decode()
        for i, (w, url) in enumerate(
            re.findall(r"font-weight: ([\d ]+);.*?src: url\((\S+?)\)", body, re.S)
        ):
            name = f"{slug}-arrows-{i}.woff2"
            (FONTS / name).write_bytes(get(url))
            ranges = ", ".join(f"U+{ord(c):04X}" for c in ARROWS)
            out.append(f"/* {family} {w}, arrows */\n" + face(family, "normal", w, name, ranges))
            print("saved", name)


def cooper_hewitt(out: list[str]) -> None:
    archive = zipfile.ZipFile(io.BytesIO(get(COOPER_ZIP)))
    for style, weight in COOPER_WEIGHTS.items():
        member = next(n for n in archive.namelist() if n.endswith(f"CooperHewitt-{style}.otf"))
        font = TTFont(io.BytesIO(archive.read(member)))
        options = subset.Options()
        options.layout_features = ["*"]
        options.name_IDs = sorted({record.nameID for record in font["name"].names})
        subsetter = subset.Subsetter(options)
        subsetter.populate(unicodes=subset.parse_unicodes(COOPER_UNICODES))
        subsetter.subset(font)
        name = f"cooper-hewitt-{weight}.woff2"
        font.flavor = "woff2"
        font.save(FONTS / name)
        out.append(f"/* Cooper Hewitt {style} */\n")
        out.append(
            face("Cooper Hewitt", "normal", str(weight), name, COOPER_UNICODES.replace(",", ", "))
        )
        print("saved", name)
    licence = next((n for n in archive.namelist() if "OFL" in n or "LICENSE" in n.upper()), None)
    if licence:
        (FONTS / "cooper-hewitt-OFL.txt").write_bytes(archive.read(licence))
    else:
        (FONTS / "cooper-hewitt-OFL.txt").write_text(
            "Cooper Hewitt by Chester Jenkins / Village, released by Cooper Hewitt,\n"
            "Smithsonian Design Museum under the SIL Open Font License 1.1.\n"
            "https://www.cooperhewitt.org/open-source-at-cooper-hewitt/"
            "cooper-hewitt-the-typeface-by-chester-jenkins/\n",
            encoding="utf-8",
        )


def main() -> None:
    if FONTS.exists():
        shutil.rmtree(FONTS)
    FONTS.mkdir(parents=True)
    out = ["/* Generated by scripts/fetch_fonts.py. Do not edit by hand. */\n"]
    cooper_hewitt(out)
    google_fonts(out)
    for slug, url in LICENSES.items():
        (FONTS / f"{slug}-OFL.txt").write_bytes(get(url))
    CSS.write_text("\n".join(out), encoding="utf-8")
    print("wrote", CSS.relative_to(ROOT))


if __name__ == "__main__":
    main()
