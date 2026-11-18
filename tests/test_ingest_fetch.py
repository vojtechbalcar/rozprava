"""The polite fetcher, against a mock transport: no network, no real sleeping."""

import io
import zipfile
from pathlib import Path

import httpx
import pytest

from rozprava.ingest.fetch import (
    USER_AGENT,
    Cache,
    Fetcher,
    FetchError,
    Forbidden,
    NotFound,
    TransientError,
    zip_members,
)

PAGE = "https://www.psp.cz/eknih/2025ps/stenprot/034schuz/s034644.htm"
ROBOTS = "User-agent: *\nDisallow: /sqw/hlasovani.sqw\nDisallow: /eknih/secret/\n"


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(round(seconds, 3))
        self.now += seconds


def make(
    tmp_path: Path,
    responses: dict[str, list[httpx.Response | Exception]],
    seen: list[httpx.Request],
):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS)
        queue = responses[str(request.url)]
        response = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(response, Exception):
            raise response
        return response

    clock = Clock()
    client = httpx.Client(
        transport=httpx.MockTransport(handler), headers={"User-Agent": USER_AGENT}
    )
    fetcher = Fetcher(Cache(tmp_path), client=client, sleep=clock.sleep, clock=clock.time)
    return fetcher, clock


def test_only_psp_transcript_urls_are_allowed(tmp_path: Path):
    fetcher, _ = make(tmp_path, {}, [])
    for url in (
        "https://example.com/eknih/x.htm",
        "http://www.psp.cz/eknih/x.htm",
        "https://www.psp.cz/sqw/hlasovani.sqw",
        "https://www.psp.cz/eknih/x.htm?id=1",
    ):
        with pytest.raises(Forbidden):
            fetcher.fetch(url)


def test_robots_txt_is_honoured(tmp_path: Path):
    seen: list[httpx.Request] = []
    fetcher, _ = make(tmp_path, {}, seen)
    with pytest.raises(Forbidden, match="robots"):
        fetcher.fetch("https://www.psp.cz/eknih/secret/page.htm")
    assert [r.url.path for r in seen] == ["/robots.txt"]


def test_requests_start_at_least_a_second_apart_and_identify_us(tmp_path: Path):
    seen: list[httpx.Request] = []
    other = PAGE.replace("644", "645")
    fetcher, clock = make(
        tmp_path, {PAGE: [httpx.Response(200, content=b"a")], other: [httpx.Response(200)]}, seen
    )
    fetcher.fetch(PAGE)
    clock.now += 0.25  # parsing took a quarter of a second
    fetcher.fetch(other)
    assert clock.slept == [1.0, 0.75]  # robots -> page, then the remainder before the next
    assert {r.headers["User-Agent"] for r in seen} == {USER_AGENT}


def test_transient_errors_are_retried_with_backoff(tmp_path: Path):
    fetcher, clock = make(
        tmp_path,
        {
            PAGE: [
                httpx.Response(503),
                httpx.ConnectTimeout("slow"),
                httpx.Response(200, content=b"ok"),
            ]
        },
        [],
    )
    assert fetcher.fetch(PAGE).read() == b"ok"
    assert 2.0 in clock.slept and 4.0 in clock.slept


def test_persistent_server_errors_are_transient_not_missing(tmp_path: Path):
    fetcher, _ = make(tmp_path, {PAGE: [httpx.Response(500)]}, [])
    with pytest.raises(TransientError):
        fetcher.fetch(PAGE)


def test_404_means_not_found(tmp_path: Path):
    fetcher, _ = make(tmp_path, {PAGE: [httpx.Response(404)]}, [])
    with pytest.raises(NotFound):
        fetcher.fetch(PAGE)


def test_bodies_are_cached_by_hash_and_reused(tmp_path: Path):
    seen: list[httpx.Request] = []
    fetcher, _ = make(
        tmp_path,
        {PAGE: [httpx.Response(200, content=b"v1", headers={"Last-Modified": "Wed"})]},
        seen,
    )
    first = fetcher.get(PAGE)
    again = fetcher.get(PAGE)
    assert again == first and first.last_modified == "Wed"
    assert first.path.read_bytes() == b"v1" and first.path.name == first.sha256
    assert sum(r.url.path.endswith(".htm") for r in seen) == 1
    assert not list(tmp_path.rglob(".tmp-*"))  # atomic writes leave nothing behind


def test_zip_members_refuse_paths(tmp_path: Path):
    def archive(names: list[str]) -> Path:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as z:
            for name in names:
                z.writestr(name, b"1|2|")
        path = tmp_path / "a.zip"
        path.write_bytes(buffer.getvalue())
        return path

    assert zip_members(archive(["steno.unl", "rec.unl"]), {"rec.unl"}) == {"rec.unl": b"1|2|"}
    for bad in (["../evil.unl"], ["dir/steno.unl"], ["/abs.unl"]):
        with pytest.raises(FetchError):
            zip_members(archive(bad))
