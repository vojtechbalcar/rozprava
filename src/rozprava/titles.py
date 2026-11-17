"""Short titles for bills and agenda items (DESIGN.md §10.3).

psp.cz titles run to 200 characters. A short title (max 60 characters) comes from,
in order: a manual override keyed by tisk number; psp.cz's own short title of the
tisk (tisky.nazev_tisku) with its abbreviations written out; or the full title
with the standard legal boilerplate stripped. The reading stage is returned
separately, for its own label.
"""

import re

MAX_LENGTH = 60

# Manual overrides keyed by tisk number win over the rules (DESIGN.md §10.3, step 1).
OVERRIDES: dict[int, str] = {
    90: "Změny zákonů v oblasti veřejných rozpočtů",
}

# psp.cz's short titles abbreviate heavily ("Novela z. o …", "Vl.n.z.").
_EXPAND: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bVl\.\s?n\.\s?z\."), "Vládní návrh zákona"),
    (re.compile(r"\bNovela z\."), "Novela zákona"),
    (re.compile(r"\bněkteré z\."), "některé zákony"),
    (re.compile(r"\bkt\."), "kterým"),
    (re.compile(r"\bz\. -"), "zákona -"),
    (re.compile(r" - "), " – "),
]

_RULES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"^Vládní návrh zákona, kterým se mění zákon č\. \d+/\d+ Sb\., o "),
        "Novela zákona o ",
    ),
    (
        re.compile(r"^Návrh poslanců .+? na vydání zákona, kterým se mění "),
        "Poslanecký návrh: změna ",
    ),
    (re.compile(r", ve znění pozdějších předpisů"), ""),
    # Not in the spec's list; added because it ends most amending bills (see DESIGN.md §10.3).
    (
        re.compile(
            r",? a (?:mění|kterým se mění)(?: a (?:zrušují|ruší))? (?:další )?související zákony?$"
        ),
        "",
    ),
    (re.compile(r"\s*/sněmovní tisk \d+/\s*-\s*(?:prvé|druhé|třetí) čtení$"), ""),
]
_READING = re.compile(r"/sněmovní tisk \d+/\s*-\s*(prvé|druhé|třetí) čtení$")
_READING_LABEL = {"prvé": "1. čtení", "druhé": "2. čtení", "třetí": "3. čtení"}


def reading(title: str) -> str | None:
    """'2. čtení' from a title ending '/sněmovní tisk 285/ - druhé čtení'."""
    m = _READING.search(title.strip())
    return _READING_LABEL[m.group(1)] if m else None


def expand_psp_title(text: str) -> str:
    """Write out psp.cz's abbreviations: "Novela z. o …" -> "Novela zákona o …"."""
    text = re.sub(r"\s+", " ", text).strip()
    for pattern, replacement in _EXPAND:
        text = pattern.sub(replacement, text)
    return text


def short_title(title: str, tisk: int | None = None, psp_short: str | None = None) -> str:
    if tisk is not None and tisk in OVERRIDES:
        return OVERRIDES[tisk]
    if psp_short and psp_short.strip():
        text = expand_psp_title(psp_short)
    else:
        text = re.sub(r"\s+", " ", title).strip()
        for pattern, replacement in _RULES:
            text = pattern.sub(replacement, text).strip()
    if len(text) <= MAX_LENGTH:
        return text
    cut = text[: MAX_LENGTH - 1].rsplit(" ", 1)[0].rstrip(",;:–- ")
    return cut + "…"


def catalog_number(term: int, sitting: int, page: int, order: int) -> str:
    """Accession number of a speech (DESIGN.md §7.5): 10/034/0644/2."""
    return f"{term}/{sitting:03d}/{page:04d}/{order}"


def catalog_slug(term: int, sitting: int, page: int, order: int) -> str:
    """The same number for URLs: 10-034-0644-2."""
    return catalog_number(term, sitting, page, order).replace("/", "-")
