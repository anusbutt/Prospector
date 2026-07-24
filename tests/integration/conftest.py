import httpx
import pytest
import respx

from helpers import install_stubs


@pytest.fixture
def stubbed_network():
    with respx.mock(assert_all_called=False) as mock:
        routes = install_stubs(mock)
        routes["mock"] = mock
        yield routes
