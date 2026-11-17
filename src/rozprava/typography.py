"""Czech typesetting helpers, registered as Jinja filters.

They change how text is set, never what it says: quotes stay verbatim. Every
substitution swaps one character for one character (a space for a non-breaking
space), so offsets into the original text stay valid.
"""

import re
from collections.abc import Iterable
from datetime import date

from markupsafe import Markup, escape

NBSP = "\u00a0"
THIN_NBSP = "\u202f"  # narrow no-break space: the thousands separator (DESIGN.md §4.6)

# One-letter prepositions and conjunctions must not end a line (k, s, v, z, o, u, a, i).
_ONE_LETTER = re.compile(r"(?<![\w.,-])([KkSsVvZzOoUuAaIi]) (?=\S)")
# A number stays with what it counts ("10 let", "660 miliard") and with its other
# digit groups ("200 000"), and "č." stays with its number ("č. 427").
_NUMBER = re.compile(r"(?<=\d) (?=\d|\w)")
_ABBREV = re.compile(r"(?<![\w])(č\.|s\.|tj\.|tzv\.|např\.) (?=\d)")

MONTHS_GENITIVE = (
    "ledna",
    "února",
    "března",
    "dubna",
    "května",
    "června",
    "července",
    "srpna",
    "září",
    "října",
    "listopadu",
    "prosince",
)
WEEKDAYS = ("pondělí", "úterý", "středa", "čtvrtek", "pátek", "sobota", "neděle")


def nbsp(text: str) -> str:
    """Bind one-letter words and numbers to the next word with non-breaking spaces."""
    text = _ONE_LETTER.sub(lambda m: m.group(1) + NBSP, text)
    text = _NUMBER.sub(NBSP, text)
    return _ABBREV.sub(lambda m: m.group(1) + NBSP, text)


def typeset(text: str) -> Markup:
    """Escape plain text for HTML and apply Czech non-breaking spaces."""
    return Markup(escape(nbsp(text)))


def _as_date(value: str | date) -> date:
    return value if isinstance(value, date) else date.fromisoformat(value[:10])


def cz_date(value: str | date) -> str:
    """6. 11. 2026, with non-breaking spaces so the date never splits."""
    d = _as_date(value)
    return f"{d.day}.{NBSP}{d.month}.{NBSP}{d.year}"


def cz_date_long(value: str | date, weekday: bool = False) -> str:
    """6. listopadu 2026, optionally prefixed with the weekday."""
    d = _as_date(value)
    text = f"{d.day}.{NBSP}{MONTHS_GENITIVE[d.month - 1]} {d.year}"
    return f"{WEEKDAYS[d.weekday()]} {text}" if weekday else text


def cz_number(value: int | float, decimals: int = 0) -> str:
    """43 897 and 1,5: narrow no-break space between thousands, comma for decimals."""
    text = f"{value:,.{decimals}f}"
    return text.replace(",", THIN_NBSP).replace(".", ",")


def cz_percent(value: float, decimals: int = 0) -> str:
    """92 % and 3,5 %: Czech puts a no-break space before the per cent sign."""
    return f"{cz_number(value, decimals)}{NBSP}%"


def plural(n: int, one: str, few: str, many: str) -> str:
    """Czech plural: 1 projev, 2–4 projevy, 0 or 5+ projevů."""
    if n == 1:
        return one
    if 2 <= n <= 4:
        return few
    return many


def count(n: int, one: str, few: str, many: str) -> str:
    """'6 projevů' with the number formatted and bound to its noun."""
    return f"{cz_number(n)}{NBSP}{plural(n, one, few, many)}"


def clip(text: str, limit: int = 280) -> str:
    """The start of text, cut at a word boundary to at most `limit` characters.

    Only removes text from the end; the caller adds the "…". Trailing commas and
    dashes before the cut are dropped so the ellipsis doesn't follow punctuation.
    """
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(",;:–- ")


def highlight(text: str, terms: Iterable[str] = ()) -> Markup:
    """Typeset text and wrap each matched search term in <mark class="term">.

    Matching is case-insensitive and prefers the longest term. The text itself
    is never altered: highlighting only adds markup around existing characters.
    """
    set_text = nbsp(text)
    wanted = sorted({t for t in terms if t.strip()}, key=len, reverse=True)
    if not wanted:
        return Markup(escape(set_text))
    # Match against the original spacing; nbsp() keeps every offset the same.
    pattern = re.compile("|".join(re.escape(t) for t in wanted), re.IGNORECASE)
    out, last = [], 0
    for m in pattern.finditer(text):
        out.append(escape(set_text[last : m.start()]))
        out.append(Markup('<mark class="term">%s</mark>') % set_text[m.start() : m.end()])
        last = m.end()
    out.append(escape(set_text[last:]))
    return Markup("").join(out)


# Czech alphabetical order: "ch" is a letter after "h"; č, ř, š, ž are letters of
# their own; á, é, ě, í, ó, ú, ů, ý, ď, ň, ť sort with their base letter.
_ALPHABET = [
    "a",
    "b",
    "c",
    "č",
    "d",
    "e",
    "f",
    "g",
    "h",
    "ch",
    "i",
    "j",
    "k",
    "l",
    "m",
    "n",
    "o",
    "p",
    "q",
    "r",
    "ř",
    "s",
    "š",
    "t",
    "u",
    "v",
    "w",
    "x",
    "y",
    "z",
    "ž",
]
_RANK = {letter: i for i, letter in enumerate(_ALPHABET)}
_BASE = str.maketrans("áäďéěíňóöťúůüý", "aadeeinootuuuy")


def _units(word: str) -> list[str]:
    word = word.lower()
    units, i = [], 0
    while i < len(word):
        if word.startswith("ch", i):
            units.append("ch")
            i += 2
        else:
            units.append(word[i])
            i += 1
    return units


def czech_sort_key(text: str) -> tuple:
    """Sort key for Czech collation: base letters first, accents break ties."""
    units = _units(text)
    primary = tuple(_RANK.get(u.translate(_BASE), 100 + ord(u[0])) for u in units)
    return (primary, tuple(units))


def czech_initial(text: str) -> str:
    """Index letter for a name: Čermák -> Č, Chvojka -> Ch, Ádámková -> A."""
    first = _units(text)[0].translate(_BASE)
    return "Ch" if first == "ch" else first.upper()
