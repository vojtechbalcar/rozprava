"""The Rozprava web app. Every request reads PostgreSQL only; nothing is fetched.

uv run fastapi dev src/rozprava/main.py
"""

import datetime as dt
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException

from rozprava.db import get_session_factory
from rozprava.queries import activity, archive, common, people, search, transcripts
from rozprava.templating import STATIC
from rozprava.web import SHARED, activity_views, link, render, safe_back

app = FastAPI(title="Rozprava", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


def get_db() -> Iterator[Session]:
    with get_session_factory()() as session:
        yield session


DB = Annotated[Session, Depends(get_db)]


def not_found() -> HTTPException:
    return HTTPException(status_code=404)


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException) -> Response:
    if exc.status_code == 404:
        return render(request, "notfound.html", "notfound", {}, status=404)
    return HTMLResponse(str(exc.detail), status_code=exc.status_code)


@app.exception_handler(OperationalError)
@app.exception_handler(InterfaceError)
async def database_error(request: Request, exc: Exception) -> Response:
    """The database is down or unreachable: say so, never fall back to sample data."""
    SHARED.clear()
    if request.url.path.startswith(("/api/", "/health")):
        return JSONResponse({"status": "unavailable", "database": "unavailable"}, 503)
    return render(request, "error.html", "error", {"code": 503}, status=503)


def query_lists(request: Request) -> dict[str, list[str]]:
    return {key: request.query_params.getlist(key) for key in request.query_params.keys()}


def optional_int(request: Request, name: str) -> int | None:
    value = request.query_params.get(name)
    if value is None:
        return None
    if not value.isascii() or not value.isdigit() or len(value) > 9:
        raise not_found()
    return int(value)


@app.get("/health")
def health(db: DB) -> dict:
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok", "updated": common.last_import(db)}


@app.get("/")
def home(request: Request, db: DB) -> Response:
    view = archive.home(db, dt.datetime.now(dt.UTC))
    return render(
        request, "home.html", "home", {"home": view, "archive": view["archive"]}, SHARED.get(db)
    )


def selected_term(request: Request, db: Session) -> common.TermInfo | None:
    terms = common.terms(db)
    number = optional_int(request, "obdobi")
    if number is not None:
        if number not in terms:
            raise not_found()
        return terms[number]
    return terms.get(10) or (terms[max(terms)] if terms else None)


@app.get("/poslanci")
def directory_page(request: Request, db: DB) -> Response:
    term = selected_term(request, db)
    query = request.query_params.get("q", "").strip()[:200]
    clubs = tuple(request.query_params.getlist("klub")[:20])
    region = request.query_params.get("kraj", "")[:200]
    sort = request.query_params.get("razeni", "name")
    if sort not in ("name", "party", "region", "speeches", "attendance"):
        sort = "name"
    a = activity.term_activity(db, term.id) if term else None
    view = (
        people.directory(db, term, a, query, clubs, region, sort)
        if term and a
        else {
            "mps": [],
            "parties": [],
            "regions": [],
            "unknown_club": 0,
            "total_mps": 0,
        }
    )
    params = {
        "obdobi": term.number if term else None,
        "q": query,
        "klub": list(clubs),
        "kraj": region,
        "razeni": sort,
    }
    return render(
        request,
        "mps.html",
        "mps",
        view
        | {
            "term": term,
            "provisional": a.provisional if a else True,
            "directory": {
                "query": query,
                "clubs": clubs,
                "region": region,
                "sort": sort,
                "params": params,
            },
        },
        SHARED.get(db),
    )


@app.get("/poslanec/{slug}")
def profile_page(request: Request, slug: str, db: DB) -> Response:
    person_id = common.parse_slug(slug)
    term = selected_term(request, db)
    page = optional_int(request, "stranka")
    if person_id is None or term is None or (page is not None and not 1 <= page <= 10000):
        raise not_found()
    a = activity.term_activity(db, term.id)
    view = people.profile(db, term, person_id, a, page or 1)
    if view is None:
        raise not_found()
    graphs, compact = activity_views(view["activity"])
    return render(
        request,
        "mp.html",
        "mp",
        {
            "mp": view,
            "term": term,
            "graphs": graphs,
            "compact": compact,
        },
        SHARED.get(db),
    )


@app.get("/schuze")
def sessions_page(request: Request, db: DB) -> Response:
    term = selected_term(request, db)
    return render(
        request,
        "sessions.html",
        "sessions",
        {
            "sessions": archive.sittings(db, term) if term else [],
            "term": term,
            "selected_sitting": None,
        },
        SHARED.get(db),
    )


@app.get("/schuze/{term}/{sitting}")
def sitting_page(request: Request, term: int, sitting: int, db: DB) -> Response:
    info = common.terms(db).get(term)
    views = [s for s in archive.sittings(db, info) if s["number"] == sitting] if info else []
    if not views:
        raise not_found()
    return render(
        request,
        "sessions.html",
        "sessions",
        {
            "sessions": views,
            "term": info,
            "selected_sitting": sitting,
        },
        SHARED.get(db),
    )


@app.get("/jak-to-funguje")
def methodology(request: Request, db: DB) -> Response:
    return render(request, "how.html", "how", {}, SHARED.get(db))


@app.get("/hledat")
def search_page(request: Request, db: DB) -> Response:
    shared = SHARED.get(db)
    known = sorted(common.terms(db))
    filters, errors = search.SearchFilters.parse(query_lists(request), known)
    result = search.search(db, filters, errors)
    scope_terms = filters.terms or tuple(known)
    scope = (
        f"v {scope_terms[0]}. volebním období"
        if len(scope_terms) == 1
        else "v " + " a ".join(f"{t}." for t in scope_terms) + " volebním období"
    )
    active = []
    labels = {p["value"]: p["label"] for p in shared["filters"]["poslanec"]}
    for t in filters.terms:
        active.append({"label": "Období", "value": f"{t}.", "params": filters.toggled("terms", t)})
    for p in filters.people:
        active.append(
            {
                "label": "Řečník",
                "value": labels.get(str(p), p),
                "params": filters.toggled("people", p),
            }
        )
    for c in filters.clubs:
        active.append({"label": "Klub", "value": c, "params": filters.toggled("clubs", c)})
    for b in filters.bills:
        active.append(
            {
                "label": "Tisk",
                "value": f"{b[1]} ({b[0]}. obd.)",
                "params": filters.toggled("bills", b),
            }
        )
    if filters.date_from or filters.date_to:
        span = f"{filters.date_from or '…'} – {filters.date_to or '…'}"
        active.append(
            {
                "label": "Datum",
                "value": span,
                "params": filters.params(date_from=None, date_to=None),
            }
        )
    keep = filters.params()
    keep.pop("q", None)
    view = {
        "query": filters.q,
        "highlights": result.highlights,
        "total": result.total,
        "answer": [],
        "results": result.results,
        "scope": scope,
        "sort": filters.sort,
        "sort_params": {
            "relevance": filters.params(sort="relevance"),
            "nejnovejsi": filters.params(sort="nejnovejsi"),
        },
        "page": filters.page,
        "pages": result.pages,
        "prev_params": filters.params(page=filters.page - 1),
        "next_params": filters.params(page=filters.page + 1),
        "last_page_params": filters.params(page=result.pages),
        "out_of_range": result.out_of_range,
        "errors": result.errors,
        "active": active,
        "keep": keep,
        "keep_without_dates": {k: v for k, v in keep.items() if k not in ("od", "do")}
        | ({"q": filters.q} if filters.q else {}),
        "date_from": filters.date_from.isoformat() if filters.date_from else None,
        "date_to": filters.date_to.isoformat() if filters.date_to else None,
        "coverage_note": None,
    }
    return render(
        request, "search.html", "search", {"search": view, "facets": result.facets}, shared
    )


@app.get("/prepis/{term}/{sitting}/{page}")
def transcript_page(request: Request, term: int, sitting: int, page: int, db: DB) -> Response:
    revision = optional_int(request, "revize")
    view = transcripts.reader(db, term, sitting, page, revision)
    if view is None:
        raise not_found()
    back = safe_back(request.query_params.get("zpet"), lambda: link("search"))
    return render(
        request, "transcript.html", "transcript", {"t": view, "back": back}, SHARED.get(db)
    )


@app.get("/projev/{catalog}")
def speech(request: Request, catalog: str, db: DB) -> Response:
    location = transcripts.locate_speech(db, catalog, optional_int(request, "verze"))
    if location is None:
        raise not_found()
    return RedirectResponse(
        link(
            "transcript",
            term=location.term,
            sitting=location.sitting,
            page=location.page,
            revize=location.page_revision,
            anchor=location.anchor,
        ),
        status_code=302,
    )
