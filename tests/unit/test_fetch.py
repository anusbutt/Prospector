import httpx
import pytest
import respx

from prospector.fetch import BlockedHostError, FetchError, Fetcher, is_blocked_host


def instant_fetcher(**kwargs):
    """Fetcher with neutralized timing for tests."""
    return Fetcher(clock=lambda: 0.0, sleep=lambda s: None, **kwargs)


class TestFacebookBlock:
    @pytest.mark.parametrize(
        "url",
        [
            "https://facebook.com/somepage",
            "https://www.facebook.com/somepage",
            "https://m.facebook.com/x",
            "http://fb.com/x",
            "https://fb.me/x",
            "https://scontent.fbcdn.net/img.jpg",
            "https://www.messenger.com/t/x",
        ],
    )
    @respx.mock
    def test_blocked_hosts_raise_with_zero_requests(self, url):
        catch_all = respx.route().mock(return_value=httpx.Response(200))
        with pytest.raises(BlockedHostError):
            instant_fetcher().fetch(url)
        assert catch_all.call_count == 0, "a request escaped to the network layer"

    def test_lookalike_hosts_are_not_blocked(self):
        assert not is_blocked_host("https://notfacebook.com/x")
        assert not is_blocked_host("https://facebook.com.example.com/x")
        assert not is_blocked_host("https://myfb.company.com/x")


class TestRetries:
    @respx.mock
    def test_retries_on_5xx_then_succeeds(self):
        route = respx.get("https://site.test/").mock(
            side_effect=[httpx.Response(500), httpx.Response(200, text="ok")]
        )
        response = instant_fetcher().fetch("https://site.test/")
        assert response.status_code == 200
        assert route.call_count == 2

    @respx.mock
    def test_gives_up_after_retries(self):
        route = respx.get("https://site.test/").mock(return_value=httpx.Response(500))
        with pytest.raises(FetchError, match="after 3 attempts"):
            instant_fetcher().fetch("https://site.test/")
        assert route.call_count == 3

    @respx.mock
    def test_retries_on_timeout(self):
        route = respx.get("https://site.test/").mock(
            side_effect=[httpx.ConnectTimeout("slow"), httpx.Response(200)]
        )
        response = instant_fetcher().fetch("https://site.test/")
        assert response.status_code == 200
        assert route.call_count == 2

    @respx.mock
    def test_4xx_returned_not_retried(self):
        route = respx.get("https://site.test/missing").mock(return_value=httpx.Response(404))
        response = instant_fetcher().fetch("https://site.test/missing")
        assert response.status_code == 404
        assert route.call_count == 1


class TestPoliteness:
    @respx.mock
    def test_same_host_requests_are_spaced(self):
        respx.get(url__startswith="https://site.test/").mock(return_value=httpx.Response(200))
        now = {"t": 100.0}
        sleeps: list[float] = []

        def clock():
            return now["t"]

        def sleep(seconds):
            sleeps.append(seconds)
            now["t"] += seconds

        fetcher = Fetcher(clock=clock, sleep=sleep)
        fetcher.fetch("https://site.test/a")
        fetcher.fetch("https://site.test/b")
        assert sleeps and abs(sleeps[0] - 1.0) < 0.01

    @respx.mock
    def test_different_hosts_not_spaced(self):
        respx.route().mock(return_value=httpx.Response(200))
        sleeps: list[float] = []
        fetcher = Fetcher(clock=lambda: 50.0, sleep=lambda s: sleeps.append(s))
        fetcher.fetch("https://one.test/")
        fetcher.fetch("https://two.test/")
        assert sleeps == []


class TestRobots:
    @respx.mock
    def test_robots_disallow_respected(self):
        respx.get("https://site.test/robots.txt").mock(
            return_value=httpx.Response(200, text="User-agent: *\nDisallow: /about\n")
        )
        page = respx.get("https://site.test/about").mock(return_value=httpx.Response(200))
        with pytest.raises(FetchError, match="robots.txt disallows"):
            instant_fetcher().fetch("https://site.test/about", check_robots=True)
        assert page.call_count == 0

    @respx.mock
    def test_missing_robots_allows(self):
        respx.get("https://site.test/robots.txt").mock(return_value=httpx.Response(404))
        respx.get("https://site.test/about").mock(return_value=httpx.Response(200, text="hi"))
        response = instant_fetcher().fetch("https://site.test/about", check_robots=True)
        assert response.status_code == 200
