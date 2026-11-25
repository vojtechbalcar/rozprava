"""Polite, cached downloads from psp.cz. Only the ingest job uses this module.

- Only https://www.psp.cz/eknih/… URLs are allowed, and robots.txt is honoured.
- Request starts are at least MIN_INTERVAL seconds apart, across all calls.
- Timeouts, connection errors, 429 and 5xx are retried with backoff and, if they
  persist, raised as TransientError. Only 404/410 is NotFound. Callers must not
  record a transient failure as permanent unavailability.
- Every response body is cached under its SHA-256, written atomically, with a
  small JSON record of the URL, retrieval time and Last-Modified header.
"""

import hashlib
import json
import os
import tempfile
import time
import zipfile
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

USER_AGENT = "Rozprava/0.1 (+https://github.com/vojtechbalcar/rozprava)"
ORIGIN = "https://www.psp.cz"
ALLOWED_PREFIXES = ("/eknih/",)
MIN_INTERVAL = 1.0
TIMEOUT = httpx.Timeout(30.0, connect=10.0)
RETRIES = 4
BACKOFF = 2.0  # seconds, doubled after each failed attempt


class FetchError(Exception):
    pass


class NotFound(FetchError):
    """The server says the resource does not exist (404/410)."""


class TransientError(FetchError):
    """Timeouts, connection failures, 429 and 5xx after all retries: try again later."""


class Forbidden(FetchError):
    """The URL is outside the allowlist or disallowed by robots.txt."""


@dataclass(frozen=True)
class Fetched:
    url: str
    sha256: str
    size: int
    retrieved_at: str  # ISO 8601, UTC
    last_modified: str | None
    path: Path

    def read(self) -> bytes:
        return self.path.read_bytes()


def check_url(url: str) -> None:
    parts = urlsplit(url)
    if f"{parts.scheme}://{parts.netloc}" != ORIGIN or not parts.path.startswith(ALLOWED_PREFIXES):
        raise Forbidden(f"Not an allowed psp.cz source URL: {url}")
    if parts.query or parts.fragment:
        raise Forbidden(f"Source URLs must not carry a query or fragment: {url}")


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


class Cache:
    """Content-addressed bodies plus the latest record per URL."""

    def __init__(self, root: Path):
        self.root = root

    def _record_path(self, url: str) -> Path:
        key = hashlib.sha256(url.encode()).hexdigest()
        return self.root / "urls" / key[:2] / f"{key}.json"

    def blob_path(self, sha256: str) -> Path:
        return self.root / "blobs" / sha256[:2] / sha256

    def store(self, url: str, body: bytes, last_modified: str | None) -> Fetched:
        sha = hashlib.sha256(body).hexdigest()
        blob = self.blob_path(sha)
        if not blob.exists():
            _atomic_write(blob, body)
        fetched = Fetched(
            url=url,
            sha256=sha,
            size=len(body),
            retrieved_at=datetime.now(UTC).isoformat(timespec="seconds"),
            last_modified=last_modified,
            path=blob,
        )
        record = {k: v for k, v in asdict(fetched).items() if k != "path"}
        _atomic_write(self._record_path(url), json.dumps(record).encode())
        return fetched

    def latest(self, url: str) -> Fetched | None:
        """The last stored response for a URL, if its body is still present."""
        path = self._record_path(url)
        if not path.exists():
            return None
        record = json.loads(path.read_text())
        blob = self.blob_path(record["sha256"])
        if not blob.exists():
            return None
        return Fetched(**record, path=blob)


class Fetcher:
    def __init__(
        self,
        cache: Cache,
        client: httpx.Client | None = None,
        min_interval: float = MIN_INTERVAL,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.cache = cache
        self.client = client or httpx.Client(
            headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, follow_redirects=False
        )
        self.min_interval = min_interval
        self.sleep = sleep
        self.clock = clock
        self._last_start: float | None = None
        self._robots: RobotFileParser | None = None
        self.requests = 0

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "Fetcher":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _wait_turn(self) -> None:
        if self._last_start is not None:
            remaining = self.min_interval - (self.clock() - self._last_start)
            if remaining > 0:
                self.sleep(remaining)
        self._last_start = self.clock()

    def _get(self, url: str) -> httpx.Response:
        delay = BACKOFF
        problem = ""
        for attempt in range(RETRIES):
            if attempt:
                self.sleep(delay)
                delay *= 2
            self._wait_turn()
            self.requests += 1
            try:
                response = self.client.get(url)
            except httpx.TransportError as error:
                problem = f"{type(error).__name__}: {error}"
                continue
            if response.status_code in (404, 410):
                raise NotFound(f"HTTP {response.status_code} for {url}")
            if response.status_code == 429 or response.status_code >= 500:
                problem = f"HTTP {response.status_code}"
                continue
            if response.status_code != 200:
                raise FetchError(f"Unexpected HTTP {response.status_code} for {url}")
            return response
        raise TransientError(f"{problem} for {url} after {RETRIES} attempts")

    def _allowed_by_robots(self, url: str) -> bool:
        if self._robots is None:
            robots = RobotFileParser()
            try:
                robots.parse(self._get(f"{ORIGIN}/robots.txt").text.splitlines())
            except NotFound:
                robots.parse([])
            self._robots = robots
        return self._robots.can_fetch(USER_AGENT, url)

    def fetch(self, url: str) -> Fetched:
        """Download a URL now and cache the body."""
        check_url(url)
        if not self._allowed_by_robots(url):
            raise Forbidden(f"robots.txt disallows {url}")
        response = self._get(url)
        return self.cache.store(url, response.content, response.headers.get("Last-Modified"))

    def get(self, url: str, refresh: bool = False) -> Fetched:
        """The cached body if there is one (unless refresh), otherwise download it."""
        if not refresh and (cached := self.cache.latest(url)):
            return cached
        return self.fetch(url)


def zip_members(path: Path, expected: set[str] | None = None) -> dict[str, bytes]:
    """Read a ZIP's flat members into memory, refusing paths and unexpected names."""
    out: dict[str, bytes] = {}
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            name = info.filename
            if info.is_dir() or "/" in name or "\\" in name or name.startswith(".."):
                raise FetchError(f"Unexpected path in {path.name}: {name!r}")
            if expected is not None and name not in expected:
                continue
            out[name] = archive.read(info)
    return out
