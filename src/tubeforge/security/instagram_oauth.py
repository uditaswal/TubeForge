"""Instagram Login (professional accounts): server-side code exchange and identity proof."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode, urlsplit

import httpx

from tubeforge.core.errors import ProviderAuthenticationError

SCOPES = ("instagram_business_basic", "instagram_business_content_publish")
AUTHORIZE_URL = "https://www.instagram.com/oauth/authorize"
SHORT_TOKEN_URL = "https://api.instagram.com/oauth/access_token"
GRAPH = "https://graph.instagram.com"
LONG_TOKEN_URL = f"{GRAPH}/access_token"
REFRESH_URL = f"{GRAPH}/refresh_access_token"
ME_URL = f"{GRAPH}/v21.0/me"


@dataclass(frozen=True, slots=True)
class VerifiedInstagramAccount:
    user_id: str
    label: str
    credential: dict[str, object]
    scopes: tuple[str, ...]
    expires_at: datetime


class InstagramAccountOAuth:
    """Instagram Login contract only; Facebook Login is a separate integration."""

    def __init__(self, app_id: str, app_secret: str, redirect_uri: str, *, client: httpx.Client | None = None) -> None:
        parsed = urlsplit(redirect_uri)
        if not app_id or not app_secret or parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("Instagram OAuth needs an app ID, secret, and HTTPS callback")
        self.app_id, self.app_secret, self.redirect_uri = app_id, app_secret, redirect_uri
        self.client = client or httpx.Client(timeout=20, follow_redirects=False)

    def authorization_url(self, state: str) -> str:
        return AUTHORIZE_URL + "?" + urlencode({
            "client_id": self.app_id, "redirect_uri": self.redirect_uri, "response_type": "code",
            "scope": ",".join(SCOPES), "state": state, "force_reauth": "true",
        })

    def exchange_and_discover(self, *, code: str) -> VerifiedInstagramAccount:
        try:
            short = self.client.post(SHORT_TOKEN_URL, data={
                "client_id": self.app_id, "client_secret": self.app_secret, "grant_type": "authorization_code",
                "redirect_uri": self.redirect_uri, "code": code,
            })
            short.raise_for_status()
            short_data = short.json()
            short_token = short_data.get("access_token")
            granted = {item for item in str(short_data.get("permissions") or "").replace(" ", "").split(",") if item}
            if not isinstance(short_token, str) or not short_token:
                raise ProviderAuthenticationError("Instagram did not return an access token")
            if not set(SCOPES).issubset(granted):
                raise ProviderAuthenticationError("Instagram did not grant both requested permissions")
            long = self.client.get(LONG_TOKEN_URL, params={
                "grant_type": "ig_exchange_token", "client_secret": self.app_secret, "access_token": short_token,
            })
            long.raise_for_status()
            long_data = long.json()
            token, lifetime = long_data.get("access_token"), long_data.get("expires_in")
            if not isinstance(token, str) or not token or not isinstance(lifetime, int) or lifetime < 3600:
                raise ProviderAuthenticationError("Instagram returned an invalid long-lived token")
            identity = self.client.get(ME_URL, params={"fields": "user_id,username,account_type"}, headers={"Authorization": f"Bearer {token}"})
            identity.raise_for_status()
            profile = identity.json()
            user_id, username = str(profile.get("user_id") or ""), str(profile.get("username") or "")
            if not user_id or not username:
                raise ProviderAuthenticationError("Instagram did not identify one account")
            if profile.get("account_type") not in {"BUSINESS", "MEDIA_CREATOR"}:
                raise ProviderAuthenticationError("Instagram account must be a Professional (Business or Creator) account")
            expires_at = datetime.now(UTC) + timedelta(seconds=lifetime)
            return VerifiedInstagramAccount(
                user_id=user_id, label=f"@{username}", scopes=tuple(sorted(granted)), expires_at=expires_at,
                credential={"token": token, "user_id": user_id, "token_type": "instagram_long_lived", "expiry": expires_at.isoformat()},
            )
        except ProviderAuthenticationError:
            raise
        except Exception as error:
            raise ProviderAuthenticationError("Instagram authorization or account verification failed") from error
