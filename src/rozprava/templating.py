"""The Jinja environment shared by the web app and the static design preview.

Templates never build URLs themselves. They call two globals:
- link(name, **params) for pages ("search", "transcript", "mp", ...)
- static(path) for files under src/rozprava/static
The web app and the preview renderer each supply their own versions.
"""

from collections.abc import Callable
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from rozprava import typography

PACKAGE = Path(__file__).resolve().parent
TEMPLATES = PACKAGE / "templates"
STATIC = PACKAGE / "static"


def make_env(
    link: Callable[..., str], static: Callable[[str], str], **globals: object
) -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html"]),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters.update(
        nbsp=typography.typeset,
        highlight=typography.highlight,
        cz_date=typography.cz_date,
        cz_date_long=typography.cz_date_long,
        cz_number=typography.cz_number,
        plural=typography.plural,
        count=typography.count,
    )
    env.globals.update(link=link, static=static, **globals)
    return env
