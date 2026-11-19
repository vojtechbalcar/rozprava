"""Routes against the imported fixture corpus: search, reader, permalinks, errors."""

import re
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from rozprava import main
from rozprava.web import SHARED, link
from tests.psp_source import FIXTURE_PAGES, fixture_url


def visible(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).replace("\xa0", " ")


def test_link_builds_app_urls():
    assert link("transcript", term=10, sitting=34, page=644, anchor="s-10-034-0644-2") == (
        "/prepis/10/34/644#s-10-034-0644-2"
    )
    url = link("search", q="důchodová reforma", klub=["ANO", "STAN"], stranka=None)
    assert parse_qs(urlsplit(url).query) == {"q": ["důchodová reforma"], "klub": ["ANO", "STAN"]}
    with pytest.raises(ValueError):
        link("transcript", page=644)


def test_health(client: TestClient):
    assert client.get("/health").json()["database"] == "ok"


def test_search_page_shows_real_results_with_reader_links(client: TestClient):
    response = client.get("/hledat", params={"q": "jednorazovych darecku"})
    assert response.status_code == 200
    text = visible(response.text)
    assert "1 projev" in text and "Olga Richterová" in text
    assert "jednorázových dárečků" in text
    assert 'href="/prepis/10/34/644#p-10-034-0642-2-' in response.text
    assert "Shrnutí" not in text and "ukázkových" not in text  # no AI or sample claims


def test_search_errors_are_explained_and_escaped(client: TestClient):
    response = client.get("/hledat", params={"q": "<script>alert(1)</script>", "obdobi": "7"})
    assert response.status_code == 200
    assert "<script>alert(1)</script>" not in response.text
    assert "Volební období „7“ neznáme" in visible(response.text)


def test_reader_shows_stored_text_attribution_and_neighbours(client: TestClient):
    response = client.get("/prepis/10/34/644")
    assert response.status_code == 200
    html = response.text
    text = visible(html)
    assert "Poslanec Jan Papajanovský" not in text  # names, not raw labels
    assert "Jan Papajanovský" in text and "Místopředseda PSP, řídí schůzi" in text
    assert "Ve třetím pilíři máme dnes 3,9 milionu osob" in text
    assert 'href="/prepis/10/34/643"' in html and 'href="/prepis/10/34/645"' in html
    assert 'data-copy="/projev/10-034-0644-2?verze=' in html
    assert "Pokračování projevu ze" in text  # Richterová's speech from 642


def test_pending_and_unavailable_pages_say_so(client: TestClient):
    response = client.get("/prepis/10/34/645")  # 404 at the source in the fixture run
    assert response.status_code == 200
    assert "Strana není na psp.cz dostupná." in visible(response.text)


def test_unknown_ids_are_404(client: TestClient):
    for url in ("/prepis/10/34/999", "/prepis/11/1/1", "/projev/10-034-0644-9", "/projev/x"):
        response = client.get(url, follow_redirects=False)
        assert response.status_code == 404, url
        assert "Tahle strana v" in response.text
    assert client.get("/prepis/10/34/644?revize=abc").status_code == 404


def test_catalog_permalink_resolves_current_position(client: TestClient):
    response = client.get("/projev/10-034-0644-2", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/prepis/10/34/644#s-10-034-0644-2"


def test_citations_keep_working_after_a_source_revision(client: TestClient, corpus):
    runner, source = corpus
    page = client.get("/prepis/10/34/644").text
    old = re.search(r'data-copy="/projev/10-034-0644-2\?verze=(\d+)"', page)
    assert old
    url = fixture_url("2025ps-s034644")
    source.pages[url] = FIXTURE_PAGES[url].replace(
        "Proč na tom záleží?".encode("cp1250"), "Proč na tom tolik záleží?".encode("cp1250")
    )
    runner.refresh(terms=[10])

    current = visible(client.get("/prepis/10/34/644").text)
    assert "Proč na tom tolik záleží?" in current
    pinned = client.get(f"/projev/10-034-0644-2?verze={old.group(1)}", follow_redirects=False)
    location = pinned.headers["location"]
    assert re.fullmatch(r"/prepis/10/34/644\?revize=\d+#s-10-034-0644-2", location)
    historical = visible(client.get(location).text)
    assert "Proč na tom záleží?" in historical and "tolik" not in historical
    assert "Čtete verzi přepisu staženou" in historical


def test_database_outage_is_503_without_sample_data(client: TestClient):
    def broken():
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))
        yield  # pragma: no cover

    main.app.dependency_overrides[main.get_db] = broken
    response = client.get("/hledat", params={"q": "penze"})
    assert response.status_code == 503
    assert "Archiv je teď nedostupný." in visible(response.text)
    assert "Papajanovský" not in response.text
    assert client.get("/health").status_code == 503
    for url in ("/api/palette?q=penze", "/api/quote"):
        response = client.get(url)
        assert response.status_code == 503 and response.json()["status"] == "unavailable"


def test_home_directory_profiles_and_sittings_use_real_data(client: TestClient):
    home = client.get("/")
    assert home.status_code == 200
    assert "Poslední načtený jednací den" in visible(home.text)
    assert "podle smyslu" not in visible(home.text)
    directory = client.get("/poslanci", params={"q": "richterova", "obdobi": 10})
    assert directory.status_code == 200
    assert 'href="/poslanec/6473-olga-richterova?obdobi=10"' in directory.text
    assert "Papajanovský" not in directory.text.split("<tbody>")[1].split("</tbody>")[0]
    profile = client.get("/poslanec/6473?obdobi=10")
    assert profile.status_code == 200
    assert "Olga Richterová" in visible(profile.text)
    assert "ukázkové projevy" not in visible(profile.text)
    assert "Účast nelze spolehlivě určit" in visible(profile.text)
    assert 'name="poslanec" value="6473"' in profile.text
    assert "tisk=10-285" in profile.text
    sessions = client.get("/schuze?obdobi=9")
    assert sessions.status_code == 200
    assert 'href="/prepis/9/50/' in sessions.text
    sitting = client.get("/schuze/10/34")
    assert sitting.status_code == 200 and '<details class="session" open>' in sitting.text
    assert "neúplnými přepisy" in visible(sitting.text)


def test_profiles_paginate_and_preserve_term(client: TestClient, monkeypatch, sessions):
    from sqlalchemy import func, select

    from rozprava import models
    from rozprava.queries import people

    monkeypatch.setattr(people, "PER_PAGE", 1)
    with sessions() as db:
        person = db.scalar(
            select(models.SpeechRevision.person_id)
            .where(
                models.SpeechRevision.term_id == 174,
                models.SpeechRevision.person_id.is_not(None),
                models.SpeechRevision.retired_at.is_(None),
            )
            .group_by(models.SpeechRevision.person_id)
            .having(func.count() > 1)
            .limit(1)
        )
    assert person
    first = client.get(f"/poslanec/{person}?obdobi=10")
    assert "stranka=2#speeches-title" in first.text
    second = client.get(f"/poslanec/{person}?obdobi=10&stranka=2")
    assert second.status_code == 200 and "Strana 2" in visible(second.text)
    assert (
        first.text.split('class="obj__excerpt"')[1] != second.text.split('class="obj__excerpt"')[1]
    )
    assert client.get("/poslanec/6473?stranka=0").status_code == 404


@pytest.mark.parametrize(
    "url",
    [
        "/poslanci?obdobi=123",
        "/poslanci?obdobi=²",
        "/schuze?obdobi=abc",
        "/poslanec/unknown",
        "/poslanec/9999999",
        "/schuze/10/999",
        "/schuze/99/1",
    ],
)
def test_invalid_archive_ids_are_404(client: TestClient, url):
    assert client.get(url).status_code == 404


def test_live_methodology_describes_actual_search_and_unknown_attendance(client: TestClient):
    response = client.get("/jak-to-funguje")
    assert response.status_code == 200
    text = visible(response.text)
    assert "kvartilů" in text and "neznámou účast" in text
    assert "Vyhledávání porovnává význam" not in text
    assert "Shrnutí nad výsledky píše" not in text


def test_empty_archive_renders_without_fake_dates(sessions):
    def db():
        with sessions() as session:
            yield session

    SHARED.clear()
    main.app.dependency_overrides[main.get_db] = db
    try:
        with TestClient(main.app) as client:
            for url in ("/", "/poslanci", "/schuze", "/jak-to-funguje"):
                response = client.get(url)
                assert response.status_code == 200, url
                assert "2026-11-06" not in response.text
            assert "Zatím nejsou načtené žádné projevy" in visible(client.get("/").text)
    finally:
        main.app.dependency_overrides.clear()
        SHARED.clear()
