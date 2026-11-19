"""A fake psp.cz page source serving the captured fixtures (see fixtures/psp/README.md)."""

from collections.abc import Callable
from pathlib import Path

from rozprava.ingest.fetch import Cache, Fetched, NotFound

FIXTURES = Path(__file__).parent / "fixtures/psp"
TABLES = {p.stem: p.read_bytes() for p in (FIXTURES / "opendata").glob("*.unl")}


def fixture_url(name: str) -> str:
    year, page = name.split("-")
    sitting = int(page[1:4])
    return f"https://www.psp.cz/eknih/{year}/stenprot/{sitting:03d}schuz/{page}.htm"


FIXTURE_PAGES = {fixture_url(p.stem): p.read_bytes() for p in (FIXTURES / "pages").glob("*.htm")}


class FakeSource:
    """Serves fixture pages; other URLs are missing. Tests can override per URL."""

    def __init__(self, cache_dir: Path):
        self.cache = Cache(cache_dir)
        self.pages = dict(FIXTURE_PAGES)
        self.errors: dict[str, Exception] = {}
        self.requests: list[str] = []
        self.before: Callable[[str], None] | None = None

    def get(self, url: str, refresh: bool = False) -> Fetched:
        self.requests.append(url)
        if self.before:
            self.before(url)
        if url in self.errors:
            raise self.errors[url]
        if url not in self.pages:
            raise NotFound(f"HTTP 404 for {url}")
        return self.cache.store(url, self.pages[url], None)
