"""Dot-matrix numbers rendered as inline SVG (DESIGN.md §8).

Digits and space . , % – only. Each glyph is a 5×7 grid of circles; "off" dots
are drawn faintly so the matrix shows, like an LED panel. A space (including the
Czech thousands separator) is a 2-cell blank. The real number is also given as
visually hidden text, for screen readers and copy and paste.
"""

from markupsafe import Markup, escape

# DESIGN.md §8.2, row by row (top to bottom), 1 = on.
GLYPHS: dict[str, str] = {
    "0": "01110 10001 10011 10101 11001 10001 01110",
    "1": "00100 01100 00100 00100 00100 00100 01110",
    "2": "01110 10001 00001 00010 00100 01000 11111",
    "3": "11111 00010 00100 00010 00001 10001 01110",
    "4": "00010 00110 01010 10010 11111 00010 00010",
    "5": "11111 10000 11110 00001 00001 10001 01110",
    "6": "00110 01000 10000 11110 10001 10001 01110",
    "7": "11111 00001 00010 00100 01000 01000 01000",
    "8": "01110 10001 10001 01110 10001 10001 01110",
    "9": "01110 10001 10001 01111 00001 00010 01100",
    ",": "00000 00000 00000 00000 00110 00100 01000",
    ".": "00000 00000 00000 00000 00000 01100 01100",
    "%": "11000 11001 00010 00100 01000 10011 00011",
    "–": "00000 00000 00000 11111 00000 00000 00000",
}
SPACES = {" ", " ", " "}

# token: (dot diameter, gap) in px
SIZES: dict[str, tuple[int, int]] = {"s": (3, 1), "m": (4, 2), "l": (6, 2), "xl": (8, 3)}


def columns(text: str) -> list[list[bool] | None]:
    """The text as matrix columns, left to right: 7 booleans each, None for a gap."""
    cols: list[list[bool] | None] = []
    for i, ch in enumerate(text):
        if ch in SPACES:
            cols += [None, None]
            continue
        if ch not in GLYPHS:
            raise ValueError(f"no dot-matrix glyph for {ch!r}")
        rows = GLYPHS[ch].split()
        cols += [[row[x] == "1" for row in rows] for x in range(5)]
        if i < len(text) - 1:
            cols.append(None)  # 1-cell gap between glyphs
    return cols


def render(text: str, size: str = "m", label: str | None = None, animate: bool = False) -> Markup:
    dot, gap = SIZES[size]
    pitch = dot + gap
    cols = columns(text)
    width = len(cols) * pitch - gap
    height = 7 * pitch - gap
    r = dot / 2
    parts = []
    for x, col in enumerate(cols):
        if col is None:
            continue
        circles = "".join(
            f'<circle cx="{x * pitch + r:g}" cy="{y * pitch + r:g}" r="{r:g}"'
            f"{'' if on else ' class="dm-off"'}/>"
            for y, on in enumerate(col)
        )
        parts.append(f'<g style="--c:{x}">{circles}</g>')
    spoken = escape(label or text)
    classes = f"dm dm-{size}" + (" dm-animate" if animate else "")
    svg = (
        f'<svg class="{classes}" style="--columns:{max(1, len(cols) - 1)}"'
        f' width="{width}" height="{height}" viewBox="0 0 {width} {height}"'
        f' role="img" aria-label="{spoken}">{"".join(parts)}</svg>'
    )
    return Markup(
        f'<span class="dm-wrap">{svg}<span class="visually-hidden" aria-hidden="true">'
        f"{escape(text)}</span></span>"
    )
