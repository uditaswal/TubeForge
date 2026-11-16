"""Instagram Login exchange proves one professional account; refresh never guesses."""
from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from tubeforge.core.errors import ProviderAuthenticationError
from tubeforge.security.account_credentials import CredentialReconnectRequired, CredentialRefreshTemporary, InstagramCredentialRefresher
from tubeforge.security.instagram_oauth import InstagramAccountOAuth


def _oauth(handler, redirect="https://localhost:62065/oauth/instagram/callback") -> InstagramAccountOAuth:
    return InstagramAccountOAuth("app", "secret", redirect, client=httpx.Client(transport=httpx.MockTransport(handler)))


def _happy(account_type="BUSINESS", permissions="instagram_business_basic,instagram_business_content_publish"):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.instagram.com":
            assert b"authorization_code" in request.content
            return httpx.Response(200, json={"access_token": "short", "user_id": 1, "permissions": permissions})
        if request.url.path == "/access_token":
            assert request.url.params["grant_type"] == "ig_exchange_token" and request.url.params["access_token"] == "short"
            return httpx.Response(200, json={"access_token": "long", "token_type": "bearer", "expires_in": 5_184_000})
        assert request.headers["Authorization"] == "Bearer long"
        return httpx.Response(200, json={"user_id": "1784", "username": "shorts", "account_type": account_type})
    return handler


def test_authorization_url_and_verified_exchange() -> None:
    oauth = _oauth(_happy())
    query = parse_qs(urlsplit(oauth.authorization_url("state-1")).query)
    assert query["state"] == ["state-1"] and query["scope"] == ["instagram_business_basic,instagram_business_content_publish"]
    account = oauth.exchange_and_discover(code="code")
    assert (account.user_id, account.label) == ("1784", "@shorts")
    assert account.credential["token"] == "long" and account.credential["token_type"] == "instagram_long_lived"


@pytest.mark.parametrize("kwargs", [{"account_type": "MEDIA_CREATOR"}])
def test_creator_account_is_accepted(kwargs) -> None:
    assert _oauth(_happy(**kwargs)).exchange_and_discover(code="c").user_id == "1784"


@pytest.mark.parametrize("kwargs", [{"account_type": "PERSONAL"}, {"permissions": "instagram_business_basic"}])
def test_personal_account_or_missing_permission_is_rejected(kwargs) -> None:
    with pytest.raises(ProviderAuthenticationError):
        _oauth(_happy(**kwargs)).exchange_and_discover(code="c")


def test_http_callback_is_refused() -> None:
    with pytest.raises(ValueError):
        InstagramAccountOAuth("app", "secret", "http://localhost/cb")


def test_refresher_paths() -> None:
    credential = {"token": "old", "token_type": "instagram_long_lived", "user_id": "1"}

    def client(status: int, body: dict | None = None) -> InstagramCredentialRefresher:
        return InstagramCredentialRefresher(httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(status, json=body or {}))))

    refreshed = client(200, {"access_token": "new", "expires_in": 5_184_000})(credential)
    assert refreshed.value["token"] == "new" and refreshed.value["user_id"] == "1"
    with pytest.raises(CredentialReconnectRequired):
        client(400, {"error": {"code": 190}})(credential)
    with pytest.raises(CredentialRefreshTemporary):
        client(400, {"error": {"code": 1}})(credential)
    with pytest.raises(CredentialRefreshTemporary):
        client(500)(credential)
    with pytest.raises(CredentialReconnectRequired):
        client(200)({"token": "x"})


def test_wrapped_token_response_and_list_permissions_are_accepted() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.instagram.com":
            return httpx.Response(200, json={"data": [{"access_token": "short", "user_id": 1, "permissions": ["instagram_business_basic", "instagram_business_content_publish"]}]})
        return _happy()(request)

    assert _oauth(handler).exchange_and_discover(code="c").user_id == "1784"
