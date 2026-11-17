"""Generate src/rozprava/static/css/tokens.css from the YAML frontmatter of DESIGN.md.

DESIGN.md is the source of truth for colours, type, radii, spacing and layout widths.
Components are written by hand in app.css on top of these primitives.

Usage: uv run python scripts/build_tokens.py [--check]
"""

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DESIGN = ROOT / "DESIGN.md"
OUT = ROOT / "src/rozprava/static/css/tokens.css"
GENERIC = {"serif": "serif", "sans-serif": "sans", "monospace": "mono"}


def frontmatter(text: str) -> dict:
    _, head, _ = text.split("---\n", 2)
    return yaml.safe_load(head)


def family(stack: str) -> str:
    """Quote family names that contain spaces: JetBrains Mono -> 'JetBrains Mono'."""
    names = [n.strip() for n in stack.split(",")]
    return ", ".join(f"'{n}'" if " " in n else n for n in names)


def render(spec: dict) -> str:
    lines = [
        "/* Generated from DESIGN.md by scripts/build_tokens.py. Do not edit by hand. */",
        ":root {",
    ]

    lines.append("  /* colours */")
    for name, value in spec["colors"].items():
        lines.append(f"  --color-{name}: {value};")

    lines.append("\n  /* font stacks */")
    stacks: dict[str, str] = {}
    for style in spec["typography"].values():
        stack = family(style["fontFamily"])
        generic = stack.rsplit(",", 1)[-1].strip()
        stacks.setdefault(GENERIC[generic], stack)
    for role, stack in stacks.items():
        lines.append(f"  --font-{role}: {stack};")

    lines.append("\n  /* type styles: use font: var(--x) plus letter-spacing: var(--x-tracking) */")
    for name, s in spec["typography"].items():
        role = GENERIC[family(s["fontFamily"]).rsplit(",", 1)[-1].strip()]
        lines += [
            f"  --{name}-size: {s['fontSize']};",
            f"  --{name}-leading: {s['lineHeight']};",
            f"  --{name}-tracking: {s['letterSpacing'] or 0};",
            f"  --{name}: {s['fontWeight']} var(--{name}-size)/var(--{name}-leading)"
            f" var(--font-{role});",
        ]

    lines.append("\n  /* radii */")
    for name, value in spec["rounded"].items():
        lines.append(f"  --radius-{name}: {value};")

    lines.append("\n  /* spacing */")
    for name, value in spec["spacing"].items():
        lines.append(f"  --space-{name}: {value};")

    lines.append("\n  /* layout */")
    for name, value in spec["layout"].items():
        lines.append(f"  --{name}: {value};")

    lines.append("}")
    return "\n".join(lines) + "\n"


def main() -> int:
    css = render(frontmatter(DESIGN.read_text(encoding="utf-8")))
    if "--check" in sys.argv:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != css:
            print("tokens.css is out of date; run scripts/build_tokens.py")
            return 1
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(css, encoding="utf-8")
    print("wrote", OUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
