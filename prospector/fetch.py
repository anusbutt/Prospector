"""Single HTTP choke point for every outbound request.

Constitution II is enforced here: Facebook-owned hosts are blocked before any
network activity. Politeness (FR-023): bounded timeouts, per-host spacing,
limited retries, robots.txt for non-homepage paths.
"""

import time
import urllib.robotparser
from urllib.parse import urlparse

import httpx

# Facebook-owned surfaces: never contacted, under any circumstances.
BLOCKED_HOSTS = ("facebook.com", "fb.com", "fb.me", "fbcdn.net", "messenger.com")

USER_AGENT = "Prospector/0.1 (open-web outreach research; +https://www.omniveer.com)"

TIMEOUT = httpx.Timeout(15.0, connect=10.0)
MAX_RETRIES = 2
HOST_INTERVAL_SECONDS = 1.0


class BlockedHostError(Exception):
    """Raised when a URL targets a constitutionally blocked host."""


class FetchError(Exception):
    """Raised when a fetch fails after retries."""


def is_blocked_host(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == blocked or host.endswith("." + blocked) for blocked in BLOCKED_HOSTS)


class Fetcher:
    def __init__(
        self,
        client: httpx.Client | None = None,
        host_interval: float = HOST_INTERVAL_SECONDS,
        clock=time.monotonic,
        sleep=time.sleep,
    ):
        self._client = client or httpx.Client(
            timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}, follow_redirects=True
        )
        self._host_interval = host_interval
        self._clock = clock
        self._sleep = sleep
        self._last_request_at: dict[str, float] = {}
        self._robots_cache: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    def fetch(self, url: str, *, check_robots: bool = False) -> httpx.Response:
        """GET a URL politely. Raises BlockedHostError / FetchError."""
        if is_blocked_host(url):
            raise BlockedHostError(f"refusing to contact blocked host: {url}")
        if check_robots and not self._robots_allows(url):
            raise FetchError(f"robots.txt disallows {url}")
        return self._request(url)

    def _request(self, url: str) -> httpx.Response:
        host = (urlparse(url).hostname or "").lower()
        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            self._respect_spacing(host)
            try:
                response = self._client.get(url)
                self._last_request_at[host] = self._clock()
            except httpx.HTTPError as exc:
                self._last_request_at[host] = self._clock()
                last_error = exc
                self._sleep(2**attempt)
                continue
            if response.status_code >= 500:
                last_error = FetchError(f"{url} returned {response.status_code}")
                self._sleep(2**attempt)
                continue
            return response  # 2xx-4xx: caller decides
        raise FetchError(f"failed to fetch {url} after {MAX_RETRIES + 1} attempts: {last_error}")

    def _respect_spacing(self, host: str) -> None:
        last = self._last_request_at.get(host)
        if last is not None:
            elapsed = self._clock() - last
            if elapsed < self._host_interval:
                self._sleep(self._host_interval - elapsed)

    def _robots_allows(self, url: str) -> bool:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._robots_cache:
            self._robots_cache[origin] = self._load_robots(origin)
        parser = self._robots_cache[origin]
        if parser is None:
            return True  # no readable robots.txt -> allow
        return parser.can_fetch(USER_AGENT, url)

    def _load_robots(self, origin: str) -> urllib.robotparser.RobotFileParser | None:
        try:
            response = self._request(f"{origin}/robots.txt")
        except (FetchError, httpx.HTTPError):
            return None
        if response.status_code != 200:
            return None
        parser = urllib.robotparser.RobotFileParser()
        parser.parse(response.text.splitlines())
        return parser
