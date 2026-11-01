"""Source fetching follows same-host HTTPS canonicalising redirects only."""
from urllib.request import Request

import pytest

from tubeforge.core.errors import ProviderValidationError
from tubeforge.pipeline.sources import _RejectRedirects


def follow(start, target):
    return _RejectRedirects().redirect_request(Request(start), None, 301, "Moved", {}, target)


def test_same_host_https_redirect_is_followed():
    assert follow("https://docs.example.org/a", "https://docs.example.org/en/a").full_url == "https://docs.example.org/en/a"
    assert follow("https://Docs.Example.org/a", "https://docs.example.org/a/").full_url.endswith("/a/")


@pytest.mark.parametrize("target", [
    "https://evil.example.net/a", "http://docs.example.org/a", "https://docs.example.org:8443/a",
    "https://user:pw@docs.example.org/a", "https://docs.example.org.evil.net/a"])
def test_cross_host_downgrade_port_and_credential_redirects_are_refused(target):
    with pytest.raises(ProviderValidationError):
        follow("https://docs.example.org/a", target)
