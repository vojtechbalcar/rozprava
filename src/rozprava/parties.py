"""Party identity swatches (DESIGN.md §3.4).

Parties are identified by abbreviation plus a small square swatch. Official colours
are normalised in OKLCH to L = 0.62, C = 0.12, keeping only the hue, so no party
looks louder than another. Parties whose hues fall within 20° of an earlier one
(alphabetically by abbreviation) get a hatched swatch.

Colours must come from each party's official brand manual. Until a colour is
verified it stays None, and every party is drawn with the same neutral "pending"
swatch: showing colours for some parties and not others would not be neutral.
"""

import math
from dataclasses import dataclass

L_FIXED = 0.62
C_FIXED = 0.12
COLLISION_DEGREES = 20.0
ACHROMATIC_CHROMA = 0.03  # below this an official colour counts as black/grey branding


@dataclass(frozen=True)
class Party:
    abbr: str  # "ODS", as psp.cz names the club
    label: str  # the pill text: mono, uppercase
    official_hex: str | None = None  # from the brand manual; None until verified
    source: str | None = None  # where official_hex was verified


INDEPENDENT = "Nezařazení"

# Clubs of the 10th term (2025–). Fill official_hex only from brand manuals.
PARTIES: dict[str, Party] = {
    p.abbr: p
    for p in (
        Party("ANO", "ANO"),
        Party("KDU-ČSL", "KDU-ČSL"),
        Party("Motoristé", "MOTORISTÉ"),
        Party("ODS", "ODS"),
        Party("Piráti", "PIRÁTI"),
        Party("SPD", "SPD"),
        Party("STAN", "STAN"),
        Party("TOP 09", "TOP 09"),
        Party(INDEPENDENT, "NEZ."),
    )
}


def _srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_to_oklch(hex_colour: str) -> tuple[float, float, float]:
    """Convert #RRGGBB to OKLCH (L 0–1, C, hue in degrees)."""
    h = hex_colour.lstrip("#")
    r, g, b = (_srgb_to_linear(int(h[i : i + 2], 16) / 255) for i in (0, 2, 4))
    lms = (
        0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b,
        0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b,
        0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b,
    )
    l_, m_, s_ = (math.copysign(abs(v) ** (1 / 3), v) for v in lms)
    lightness = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    b2 = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    chroma = math.hypot(a, b2)
    hue = math.degrees(math.atan2(b2, a)) % 360
    return lightness, chroma, hue


def _hue_distance(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


@dataclass(frozen=True)
class Swatch:
    kind: str  # "colour", "achromatic", "pending" or "independent"
    css: str | None = None  # the fill, e.g. "oklch(0.62 0.12 258)"
    hatched: bool = False


def swatches(parties: dict[str, Party] = PARTIES) -> dict[str, Swatch]:
    """Swatch for every party, applying normalisation and the hue collision rule."""
    out: dict[str, Swatch] = {}
    taken: list[float] = []
    for abbr in sorted(parties):
        party = parties[abbr]
        if abbr == INDEPENDENT:
            out[abbr] = Swatch("independent")
        elif party.official_hex is None:
            out[abbr] = Swatch("pending")
        else:
            _, chroma, hue = hex_to_oklch(party.official_hex)
            if chroma < ACHROMATIC_CHROMA:
                out[abbr] = Swatch("achromatic", "oklch(0.35 0 0)")
                continue
            hatched = any(_hue_distance(hue, t) < COLLISION_DEGREES for t in taken)
            taken.append(hue)
            out[abbr] = Swatch("colour", f"oklch({L_FIXED} {C_FIXED} {hue:.0f})", hatched)
    return out


def label(abbr: str | None) -> str:
    if abbr is None:
        return ""
    party = PARTIES.get(abbr)
    return party.label if party else abbr.upper()
