"""Google connection uses PKCE and saves only the discovered channel identity."""
from __future__ import annotations

from datetime import UTC, datetime
import json
from unittest.mock import Mock

import pytest

from tubeforge.core.errors import ProviderAuthenticationError
from tubeforge.security.google_oauth import GoogleAccountOAuth, SCOPES


def test_google_authorization_is_offline_pkce_and_identity_is_discovered() -> None:
    flow = Mock()
    flow.authorization_url.return_value = ("https://accounts.google.com/authorize?state=state-1", "state-1")
    flow.credentials.refresh_token = "refresh-secret"
    flow.credentials.granted_scopes = SCOPES
    flow.credentials.expiry = datetime.now(UTC)
    flow.credentials.to_json.return_value = json.dumps({"refresh_token": "refresh-secret"})
    factory = Mock(return_value=flow)
    service = Mock()
    service.channels().list().execute.return_value = {"items": [{"id": "UC-channel", "snippet": {"title": "My Shorts"}}]}
    builder = Mock(return_value=service)
    oauth = GoogleAccountOAuth("client", "secret", "https://studio.example/oauth/youtube/callback", flow_factory=factory, build_service=builder)
    verifier = "generated-verifier"
    url = oauth.authorization_url("state-1", verifier)
    assert url.startswith("https://accounts.google.com/")
    assert factory.call_args_list[0].kwargs == {"scopes": SCOPES, "state": "state-1", "code_verifier": verifier}
    assert flow.authorization_url.call_args.kwargs == {"access_type": "offline", "prompt": "consent"}
    verified = oauth.exchange_and_discover(code="code", state="state-1", code_verifier=verifier)
    assert verified.channel_id == "UC-channel" and verified.label == "My Shorts"
    assert verified.credential == {"refresh_token": "refresh-secret"}
    assert factory.call_args_list[1].kwargs == {"scopes": SCOPES, "state": "state-1", "code_verifier": verifier}
    assert service.channels().list.call_args.kwargs == {"part": "id,snippet", "mine": True}


def test_google_oauth_rejects_missing_refresh_or_channel() -> None:
    flow = Mock()
    flow.credentials.refresh_token = None
    oauth = GoogleAccountOAuth("client", "secret", "https://studio.example/callback", flow_factory=Mock(return_value=flow))
    with pytest.raises(ProviderAuthenticationError, match="offline access"):
        oauth.exchange_and_discover(code="code", state="state", code_verifier="verifier")
    flow.credentials.refresh_token = "secret"
    flow.credentials.granted_scopes = (SCOPES[0],)
    with pytest.raises(ProviderAuthenticationError, match="both requested"):
        oauth.exchange_and_discover(code="code", state="state", code_verifier="verifier")
    flow.credentials.granted_scopes = SCOPES
    service = Mock()
    service.channels().list().execute.return_value = {"items": []}
    oauth = GoogleAccountOAuth("client", "secret", "https://studio.example/callback", flow_factory=Mock(return_value=flow), build_service=Mock(return_value=service))
    with pytest.raises(ProviderAuthenticationError, match="exactly one"):
        oauth.exchange_and_discover(code="code", state="state", code_verifier="verifier")
