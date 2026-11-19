"""Quick navigation is bounded, accent insensitive and term qualified."""

from sqlalchemy import select

from rozprava import models
from rozprava.queries import palette


def test_people_match_accents_and_reversed_names(client):
    for query in ("richterova", "RICHTEROVÁ", "Richterova Olga"):
        response = client.get("/api/palette", params={"q": query})
        assert response.status_code == 200
        people = response.json()["mps"]
        assert [p["name"] for p in people] == ["Olga Richterová"]
        assert people[0]["url"] == "/poslanec/6473-olga-richterova?obdobi=10"


def test_bills_with_identical_numbers_keep_their_terms(client, sessions):
    with sessions.begin() as db:
        db.add(models.Bill(id=999999, term_id=173, number=285, title="Jiný tisk", short_title=""))
    bills = client.get("/api/palette?q=tisk+285").json()["bills"]
    assert [b["term"] for b in bills] == [10, 9]
    assert {b["url"] for b in bills} == {"/hledat?tisk=10-285", "/hledat?tisk=9-285"}
    assert not client.get("/api/palette?q=schuze+34").json()["bills"]


def test_previous_only_mp_links_to_existing_profile(client, sessions):
    with sessions() as db:
        person = db.scalar(
            select(models.Person)
            .join(models.Mandate)
            .where(
                models.Mandate.term_id == 173,
                models.Person.id.not_in(
                    select(models.Mandate.person_id).where(models.Mandate.term_id == 174)
                ),
            )
            .limit(1)
        )
        assert person
        name = person.name
    result = client.get("/api/palette", params={"q": name}).json()["mps"]
    assert result and result[0]["term"] == 9
    assert client.get(result[0]["url"]).status_code == 200


def test_sitting_lookup_has_real_destinations(client):
    for query in ("schůze 34", "34"):
        sittings = client.get("/api/palette", params={"q": query}).json()["sittings"]
        assert sittings
        for sitting in sittings:
            assert client.get(sitting["url"]).status_code == 200


def test_palette_bounds_empty_queries_and_literal_wildcards(client):
    assert client.get("/api/palette?q=").json() == {
        "query": "",
        "mps": [],
        "bills": [],
        "sittings": [],
    }
    assert client.get("/api/palette", params={"q": "a" * 201}).status_code == 400
    for query in (
        "a",
        "%",
        "_",
        "' OR 1=1 --",
        "<script>alert(1)</script>",
        "999999",
        "schuze 32768",
    ):
        result = client.get("/api/palette", params={"q": query}).json()
        assert all(len(result[key]) <= palette.LIMIT for key in ("mps", "bills", "sittings"))
        if query != "a":
            assert not any(result[key] for key in ("mps", "bills", "sittings"))
