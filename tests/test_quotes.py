"""Quotation links resolve only stored paragraphs and remain stable after corrections."""

import json
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from bs4 import BeautifulSoup

from rozprava import models
from tests.psp_source import FIXTURE_PAGES, fixture_url


@pytest.fixture
def quote_link(client):
    response = client.get("/hledat", params={"q": "jednorazovych darecku"})
    link = BeautifulSoup(response.text, "html.parser").select_one(".obj__card")
    assert link
    return str(link["href"])


def params(url):
    return {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}


def card_data(response):
    tag = BeautifulSoup(response.text, "html.parser").select_one("#card-default")
    assert tag
    return json.loads(tag.get_text())


def test_result_quote_is_verbatim_and_revision_pinned(client, quote_link):
    response = client.get(quote_link)
    assert response.status_code == 200
    card = card_data(response)
    assert card["span"] == card["source"]["text"][card["start"] : card["end"]]
    assert "jednorázových dárečků" in card["span"]
    assert card["source"]["speaker"]["name"] == "Olga Richterová"
    assert len(card["span"]) <= 280
    assert card["cut_start"] and not card["cut_end"]
    assert "verze=" in card["url"] and "revize=" in card["source"]["reader_url"]
    assert client.get(card["source"]["reader_url"]).status_code == 200
    assert card_data(client.get(card["url"])) == card


def test_supplied_text_and_attribution_never_enter_a_quote(client, quote_link):
    query = params(quote_link) | {
        "text": "FORGED QUOTE",
        "speaker": "FORGED SPEAKER",
        "highlight": "FORGED HIGHLIGHT",
    }
    response = client.get("/api/quote", params=query)
    assert response.status_code == 200
    assert "FORGED" not in response.text
    assert response.json()["highlight"] == ""


@pytest.mark.parametrize(
    "change",
    [
        {"start": "-1"},
        {"start": "abc"},
        {"start": "²"},
        {"start": "99999999999"},
        {"start": "0", "end": "0"},
        {"start": "10", "end": "3"},
        {"start": "0", "end": "999999"},
        {"start": "0", "end": "281"},
        {"format": "1x1"},
        {"verze": "invalid"},
    ],
)
def test_invalid_selection_is_explained(client, quote_link, change):
    query = params(quote_link) | change
    assert client.get("/api/quote", params=query).status_code == 400
    response = client.get("/karta", params=query)
    assert response.status_code == 400
    assert "card-default" not in response.text


def test_missing_version_or_half_selection_is_rejected(client, quote_link):
    query = params(quote_link)
    del query["verze"]
    assert client.get("/api/quote", params=query).status_code == 400
    query = params(quote_link)
    del query["end"]
    assert client.get("/api/quote", params=query).status_code == 400


@pytest.mark.parametrize(
    "change",
    [
        {"source": "paragraph-10-034-0644-2-999999"},
        {"source": "invalid"},
        {"source": "paragraph-9-034-0642-2-1"},
        {"verze": "99999999"},
    ],
)
def test_unknown_or_mismatched_source_is_404(client, quote_link, change):
    query = params(quote_link) | change
    assert client.get("/karta", params=query).status_code == 404
    response = client.get("/api/quote", params=query)
    assert response.status_code == 404 and response.json()["error"]


def test_empty_composer_explains_how_to_choose_a_quote(client):
    response = client.get("/karta")
    assert response.status_code == 200
    assert "Vyberte projev" in response.text
    assert "card-default" not in response.text


def test_offsets_use_unicode_characters_and_trim_whitespace(client, quote_link, sessions):
    query = params(quote_link)
    position = int(query["source"].rsplit("-", 1)[1]) - 1
    text = "😀  Příliš žluťoučký kůň.  Další věta."
    with sessions.begin() as db:
        paragraph = db.get(models.SpeechParagraph, (int(query["verze"]), position))
        assert paragraph
        paragraph.text = text
    query.update(start="1", end=str(text.index("Další")))
    response = client.get("/api/quote", params=query)
    assert response.status_code == 200
    card = response.json()
    assert card["span"] == "Příliš žluťoučký kůň."
    assert card["start"] == 3 and card["cut_start"] and card["cut_end"]
    query.update(start="1", end="3")
    assert client.get("/api/quote", params=query).status_code == 400


def test_quotation_length_limit_is_enforced_before_rendering(client, quote_link, sessions):
    query = params(quote_link)
    with sessions.begin() as db:
        paragraph = db.get(
            models.SpeechParagraph,
            (
                int(query["verze"]),
                int(query["source"].rsplit("-", 1)[1]) - 1,
            ),
        )
        assert paragraph
        paragraph.text = "Žluťoučký kůň. " * 40
    query.update(start="0", end="281")
    response = client.get("/api/quote", params=query)
    assert response.status_code == 400 and "280" in response.json()["error"]
    query.update(end="280")
    assert client.get("/api/quote", params=query).status_code == 200


def test_quote_stays_exact_after_source_revision(client, quote_link, corpus):
    old = card_data(client.get(quote_link))
    runner, source = corpus
    url = fixture_url("2025ps-s034644")
    source.pages[url] = FIXTURE_PAGES[url].replace(
        "jednorázových dárečků".encode("cp1250"), "jednorázových dárků".encode("cp1250")
    )
    runner.refresh(terms=[10])
    historical = card_data(client.get(old["url"]))
    assert historical == old
    assert "jednorázových dárečků" in client.get(old["source"]["reader_url"]).text


@pytest.mark.parametrize("size", ["1200x630", "1080x1350", "1080x1920"])
def test_format_is_preserved_in_shared_url(client, quote_link, size):
    response = client.get("/karta", params=params(quote_link) | {"format": size})
    card = card_data(response)
    assert params(card["url"])["format"] == size
    doc = BeautifulSoup(response.text, "html.parser")
    visible = doc.select("[data-card-panel]:not([hidden])")
    assert len(visible) == 1 and visible[0]["data-card-panel"] == size


def test_source_markup_is_escaped(client, quote_link, sessions):
    query = params(quote_link)
    with sessions.begin() as db:
        paragraph = db.get(
            models.SpeechParagraph,
            (int(query["verze"]), int(query["source"].rsplit("-", 1)[1]) - 1),
        )
        assert paragraph
        paragraph.text = '</script><script>alert("stored")</script>'
    query.pop("start")
    query.pop("end")
    response = client.get("/karta?" + urlencode(query))
    assert response.status_code == 200
    assert '<script>alert("stored")' not in response.text
    assert card_data(response)["span"] == '</script><script>alert("stored")</script>'
