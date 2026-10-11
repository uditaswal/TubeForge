"""Server-side Google OAuth handshake for one verified YouTube channel."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any, Callable

from tubeforge.core.errors import ProviderAuthenticationError

SCOPES = (
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
)


@dataclass(frozen=True, slots=True)
class VerifiedGoogleAccount:
    channel_id: str
    label: str
    credential: dict[str, object]
    scopes: tuple[str, ...]
    expires_at: datetime | None


class GoogleAccountOAuth:
    def __init__(
        self, client_id: str, client_secret: str, redirect_uri: str,
        *, flow_factory: Callable[..., Any] | None = None,
        build_service: Callable[..., Any] | None = None,
    ) -> None:
        if not client_id or not client_secret or not redirect_uri.startswith("https://"):
            raise ValueError("Google OAuth needs a client ID, secret, and HTTPS callback")
        self.client_id, self.client_secret, self.redirect_uri = client_id, client_secret, redirect_uri
        self._flow_factory, self._build_service = flow_factory, build_service

    def _flow(self, **kwargs: object) -> Any:
        if self._flow_factory is None:
            from google_auth_oauthlib.flow import Flow
            factory = Flow.from_client_config
        else:
            factory = self._flow_factory
        config = {"web": {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [self.redirect_uri],
        }}
        flow = factory(config, scopes=SCOPES, **kwargs)
        flow.redirect_uri = self.redirect_uri
        return flow

    def authorization_url(self, state: str, code_verifier: str) -> str:
        flow = self._flow(state=state, code_verifier=code_verifier)
        url, returned_state = flow.authorization_url(access_type="offline", prompt="consent")
        if returned_state != state:
            raise ProviderAuthenticationError("Google OAuth did not establish a PKCE-bound state")
        return url

    def exchange_and_discover(self, *, code: str, state: str, code_verifier: str) -> VerifiedGoogleAccount:
        flow = self._flow(state=state, code_verifier=code_verifier)
        try:
            flow.fetch_token(code=code)
            credentials = flow.credentials
            if not credentials.refresh_token:
                raise ProviderAuthenticationError("Google did not grant offline access; reconnect required")
            granted = set(credentials.granted_scopes or ())
            if not set(SCOPES).issubset(granted):
                raise ProviderAuthenticationError("Google did not grant both requested YouTube permissions")
            if self._build_service is None:
                from googleapiclient.discovery import build
                service = build("youtube", "v3", credentials=credentials, cache_discovery=False)
            else:
                service = self._build_service("youtube", "v3", credentials=credentials, cache_discovery=False)
            items = service.channels().list(part="id,snippet", mine=True).execute().get("items", [])
            if len(items) != 1 or not items[0].get("id"):
                raise ProviderAuthenticationError("Google authorization did not identify exactly one YouTube channel")
            channel = items[0]
            envelope = json.loads(credentials.to_json())
            return VerifiedGoogleAccount(
                channel_id=str(channel["id"]),
                label=str((channel.get("snippet") or {}).get("title") or channel["id"]),
                credential=envelope,
                scopes=tuple(sorted(granted)),
                expires_at=credentials.expiry,
            )
        except ProviderAuthenticationError:
            raise
        except Exception as error:
            raise ProviderAuthenticationError("Google authorization or channel verification failed") from error
