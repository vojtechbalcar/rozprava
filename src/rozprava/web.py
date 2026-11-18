"""URL building, the template environment and page rendering for the web app."""

import time
from collections.abc import Callable
from urllib.parse import quote, urlencode

from fastapi import Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment
from sqlalchemy import select
from sqlalchemy.orm import Session

from rozprava import models
from rozprava.parties import PARTIES
from rozprava.queries import common
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
        "terms": [{"value": str(t.number), "label": t.label} for t in terms.values()],
        "current_term": current_term,
        "palette": {
            "mps": [
                {
                    "name": f"{p.forename} {p.surname}",
                    "sort": p.surname,
                    "party": "",
                    "region": "",
                    "initials": (p.forename[:1] + p.surname[:1]).upper(),
                    "url": link("mp", slug=common.person_slug(p.id, p.forename, p.surname)),
                }
                for p in people
            ],
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
