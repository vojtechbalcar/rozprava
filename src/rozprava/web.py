"""URL building, the template environment and page rendering for the web app."""

import datetime as dt
import time
from collections import defaultdict
from collections.abc import Callable
from urllib.parse import quote, urlencode

from fastapi import Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment
from sqlalchemy import select
from sqlalchemy.orm import Session

from rozprava import models
from rozprava.activity import calendar
from rozprava.parties import PARTIES
from rozprava.queries import archive, common
from rozprava.settings import get_settings
from rozprava.templating import make_env
from rozprava.typography import MONTHS_GENITIVE, czech_sort_key

ROUTES = {
    "home": "/",
    "search": "/hledat",
    "mps": "/poslanci",
    "mp": "/poslanec/{slug}",
    "sessions": "/schuze",
    "sitting": "/schuze/{term}/{sitting}",
    "transcript": "/prepis/{term}/{sitting}/{page}",
    "speech": "/projev/{catalog}",
    "card": "/karta",
    "how": "/jak-to-funguje",
    "methodology": "/jak-to-funguje",
    "palette": "/api/palette",
    "summary": "/api/shrnuti",
}
DROPPED = {"result"}  # preview-only parameters


def link(name: str, anchor: str | None = None, **params: object) -> str:
    """The app URL for a named page; leftover parameters become the query string."""
    path = ROUTES[name]
    while "{" in path:
        key = path[path.index("{") + 1 : path.index("}")]
        value = params.pop(key, None)
        if value in (None, ""):
            raise ValueError(f"link({name!r}) needs {key}")
        path = path.replace(f"{{{key}}}", quote(str(value), safe=""))
    query = {k: v for k, v in params.items() if k not in DROPPED and v not in (None, "", [], ())}
    url = path + ("?" + urlencode(query, doseq=True) if query else "")
    return f"{url}#{anchor}" if anchor else url


_STARTED = str(int(time.time()))


def static(path: str) -> str:
    return f"/static/{path}?v={_STARTED}"


ENV: Environment = make_env(link=link, static=static, preview=None, preview_pages={}, live=True)


class Shared:
    """Per-request data every page needs (header palette, filter options, update time),
    cached briefly because it changes only when an import finishes."""

    ttl = 60.0

    def __init__(self) -> None:
        self._value: dict | None = None
        self._at = 0.0

    def get(self, session: Session) -> dict:
        if self._value is None or time.monotonic() - self._at > self.ttl:
            self._value = shared_context(session)
            self._at = time.monotonic()
        return self._value

    def clear(self) -> None:
        self._value = None


SHARED = Shared()

EMPTY_CONTEXT = {
    "updated": None,
    "palette": {
        "mps": [],
        "bills": [],
        "sittings": [],
        "actions": [],
        "search": link("search"),
        "months": MONTHS_GENITIVE,
    },
    "filters": {},
    "terms": [],
    "coverage": [],
}


def shared_context(session: Session) -> dict:
    terms = common.terms(session)
    current_term = max(terms) if terms else None
    mps = session.execute(
        select(models.Person, models.Mandate.term_id)
        .join(models.Mandate, models.Mandate.person_id == models.Person.id)
        .order_by(models.Person.surname)
    ).all()
    seen: dict[int, models.Person] = {}
    for person, _ in mps:
        seen.setdefault(person.id, person)
    people = sorted(seen.values(), key=lambda p: (czech_sort_key(p.surname), p.forename))
    return {
        "updated": common.last_import(session),
        "coverage": archive.coverage(session),
        "forms_waiting": archive.forms_waiting(session),
        "meaning": archive.meaning_coverage(session, get_settings().embedding_model),
        # The Claude model writing summaries, or None when they are switched off.
        "summaries": get_settings().summary_model if get_settings().anthropic_api_key else None,
        "terms": [{"value": str(t.number), "label": t.label} for t in terms.values()],
        "current_term": current_term,
        "palette": {
            "endpoint": link("palette"),
            "mps": [],
            "bills": [],
            "sittings": [],
            "actions": [
                {"title": "Přepnout motiv", "action": "theme"},
                {"title": "Jak to funguje", "url": link("how")},
                {"title": "Schůze", "url": link("sessions")},
            ],
            "search": link("search"),
            "months": MONTHS_GENITIVE,
        },
        "filters": {
            "obdobi": [{"value": str(t.number), "label": t.label} for t in terms.values()],
            "poslanec": [
                {"value": str(p.id), "label": f"{p.forename} {p.surname}"} for p in people
            ],
            "klub": [k for k in sorted(PARTIES, key=czech_sort_key)],
            "tisk": [],
        },
    }


def render(
    request: Request,
    template: str,
    page: str,
    context: dict,
    shared: dict | None = None,
    status: int = 200,
) -> HTMLResponse:
    html = ENV.get_template(template).render(
        page=page, request_path=request.url.path, **(shared or EMPTY_CONTEXT), **context
    )
    return HTMLResponse(html, status_code=status)


def safe_back(value: str | None, fallback: Callable[[], str]) -> str:
    """A back link only within the app: a path, never another site."""
    if value and value.startswith("/") and not value.startswith("//") and "\\" not in value:
        return value
    return fallback()


def activity_views(days: list[dict]) -> tuple[dict, list]:
    if not days:
        return {}, []
    first, last = dt.date.fromisoformat(days[0]["date"]), dt.date.fromisoformat(days[-1]["date"])
    graphs = {"term": calendar(days, first, last)}
    for year in range(last.year, first.year - 1, -1):
        graphs[str(year)] = calendar(
            days, max(first, dt.date(year, 1, 1)), min(last, dt.date(year, 12, 31))
        )
    months: dict[str, list] = defaultdict(list)
    for day in days:
        months[day["date"][:7]].append(day)
    return graphs, list(months.items())
