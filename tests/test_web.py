"""Routes against the imported fixture corpus: search, reader, permalinks, errors."""

import re
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from rozprava import main
from rozprava.web import SHARED, link
from tests.psp_source import FIXTURE_PAGES, fixture_url


@pytest.fixture
def client(corpus, sessions):
    def db():
        with sessions() as session:
            yield session

    SHARED.clear()
    main.app.dependency_overrides[main.get_db] = db
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()
    SHARED.clear()


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
