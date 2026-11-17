"""Generate src/rozprava/static/css/tokens.css from DESIGN.md.

DESIGN.md is the single source of truth. This script copies or derives:
- §14.1: the CSS variables block (colours, dark theme, shadows, base rules), verbatim
- §4.1: font stacks (family plus its listed fallbacks)
- §4.2: the type scale table, and its "Mobile (<640px)" overrides
- §5.1: the spacing scale

Components are written by hand in app.css on top of these.

Usage: uv run python scripts/build_tokens.py [--check]
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESIGN = ROOT / "DESIGN.md"
OUT = ROOT / "src/rozprava/static/css/tokens.css"
GENERIC = {"Sans": "sans-serif", "Serif": "serif", "Mono": "monospace"}


def section(text: str, heading: str) -> str:
    """The body of a section, from its heading to the next heading of any level."""
    start = text.index(heading)
    rest = text[start + len(heading) :]
    end = re.search(r"\n#{2,4} ", rest)
    return rest[: end.start()] if end else rest


def table_rows(block: str) -> list[list[str]]:
    rows = [
        line.strip().strip("|").split("|") for line in block.splitlines() if line.startswith("|")
    ]
    return [[c.strip() for c in row] for row in rows[2:]]  # skip header and separator


def quoted(name: str) -> str:
    return f'"{name}"' if " " in name else name


def font_stacks(text: str) -> dict[str, str]:
    stacks = {}
    for row in table_rows(section(text, "### 4.1 Families")):
        role = re.search(r"\*\*(Sans|Serif|Mono)", row[0])
        if not role:
            continue  # the dot-matrix row is SVG, not a font
        family = re.search(r"\*\*(.+?)\*\*", row[1])
        assert family, row
        fallbacks = re.findall(r"`([^`]+)`", row[2])
        names = [family.group(1), *fallbacks, GENERIC[role.group(1)]]
        stacks[role.group(1).lower()] = ", ".join(quoted(n) for n in dict.fromkeys(names))
    return stacks


def type_scale(text: str) -> tuple[list[str], list[str]]:
    block = section(text, "### 4.2 Type scale")
    lines, mobile = [], []
    for token, family, size, leading, tracking, weight, _use in table_rows(block):
        name = token.strip("`")
        px = re.match(r"\d+px", size)
        weight_value = re.match(r"\d+", weight)
        assert px and weight_value, (token, size, weight)
        role = family.lower()
        lines += [
            f"  --t-{name}-size: {px.group()};",
            f"  --t-{name}-leading: {leading};",
            f"  --t-{name}-tracking: {tracking};",
            f"  --t-{name}: {weight_value.group()} var(--t-{name}-size)/var(--t-{name}-leading)"
            f" var(--font-{role});",
        ]
        if "UPPERCASE" in weight:
            lines.append(f"  --t-{name}-case: uppercase;")
    rule = re.search(r"Mobile \(<(\d+)px\): (.+)", block)
    assert rule, "mobile overrides missing from §4.2"
    for name, px in re.findall(r"`([\w-]+)` → (\d+px)", rule.group(2)):
        mobile.append(f"    --t-{name}-size: {px};")
    return lines, [
        f"@media (max-width: {int(rule.group(1)) - 1}px) {{",
        "  :root {",
        *mobile,
        "  }",
        "}",
    ]


def spacing(text: str) -> list[str]:
    scale = re.search(r"`([\d, ]+)` px → tokens", section(text, "### 5.1 Spacing scale"))
    assert scale, "spacing scale missing from §5.1"
    return [f"  --space-{i}: {v.strip()}px;" for i, v in enumerate(scale.group(1).split(","))]


def css_block(text: str) -> str:
    block = re.search(r"```css\n(.*?)```", section(text, "### 14.1 CSS variables"), re.S)
    assert block, "CSS block missing from §14.1"
    return block.group(1).rstrip() + "\n"


def light_theme(css: str) -> list[str]:
    """[data-theme="light"] with the light colours from §14.1's :root, so a light
    subtree (the /_design panes) stays light inside a dark system theme."""
    root = re.search(r":root \{(.*?)\}", css, re.S)
    dark = re.search(r'\[data-theme="dark"\] \{(.*?)\}', css, re.S)
    assert root and dark, "§14.1 needs :root and [data-theme=dark] blocks"
    themed = set(re.findall(r"(--[\w-]+):", dark.group(1)))
    lines = [line for line in root.group(1).splitlines() if line.strip().split(":")[0] in themed]
    return ['[data-theme="light"] {', *lines, "}"]


def render(text: str) -> str:
    stacks = font_stacks(text)
    scale, mobile = type_scale(text)
    css = css_block(text)
    out = [
        "/* Generated from DESIGN.md by scripts/build_tokens.py. Do not edit by hand. */",
        "",
        "/* §14.1, verbatim */",
        css,
        "/* Light colours again for explicitly light subtrees (derived from §14.1) */",
        *light_theme(css),
        "",
        "/* §4.1 font stacks, §4.2 type scale, §5.1 spacing */",
        ":root {",
        *(f"  --font-{role}: {stack};" for role, stack in stacks.items()),
        "",
        *scale,
        "",
        *spacing(text),
        "}",
        "",
        *mobile,
    ]
    return "\n".join(out) + "\n"


def main() -> int:
    css = render(DESIGN.read_text(encoding="utf-8"))
    if "--check" in sys.argv:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != css:
            print("tokens.css is out of date; run scripts/build_tokens.py")
            return 1
        return 0
    OUT.write_text(css, encoding="utf-8")
    print("wrote", OUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
