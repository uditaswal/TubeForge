"""Studio routes that connect one verified Instagram professional account."""
from __future__ import annotations

import html
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from tubeforge.security.instagram_oauth import InstagramAccountOAuth
from tubeforge.security.oauth_state import OAuthStateStore


class _Start(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: str | None = Field(default=None, max_length=64)


class _Confirm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: str = Field(min_length=1, max_length=200)


def register_instagram_connection(app: FastAPI, *, runtime: Any, auth_enabled: bool, oauth_store: OAuthStateStore | None, instagram_oauth: InstagramAccountOAuth | None) -> None:
    def session_of(request: Request) -> Any:
        login = runtime.auth.session(request.cookies.get("tubeforge_session"))
        if login is None:
            raise HTTPException(status_code=401, detail="Studio sign-in is required")
        return login

    @app.get("/api/oauth/instagram/status", tags=["social accounts"])
    def instagram_oauth_status() -> dict[str, object]:
        configured = auth_enabled and instagram_oauth is not None and oauth_store is not None
        return {"configured": configured, "reason": None if configured else "Instagram app, HTTPS callback, account encryption key, and Studio login are required"}

    @app.post("/api/oauth/instagram/start", tags=["social accounts"])
    def start_instagram_oauth(value: _Start, request: Request) -> dict[str, str]:
        if not auth_enabled or instagram_oauth is None or oauth_store is None:
            raise HTTPException(status_code=503, detail="Instagram connection is not configured")
        login = session_of(request)
        if value.account_id:
            account = next((item for item in runtime.accounts.list() if item.id == value.account_id), None)
            if account is None or account.platform != "instagram":
                raise HTTPException(status_code=404, detail="Instagram account not found")
        state = oauth_store.begin(platform="instagram", account_id=value.account_id, session_id=login.id, redirect_uri=instagram_oauth.redirect_uri)
        return {"authorization_url": instagram_oauth.authorization_url(state)}

    @app.get("/oauth/instagram/callback", response_class=HTMLResponse, include_in_schema=False)
    def instagram_oauth_callback(request: Request, state: str = "", code: str = "", error: str = "") -> str:
        if instagram_oauth is None or oauth_store is None:
            raise HTTPException(status_code=503, detail="Instagram connection is not configured")
        login = session_of(request)
        pending = oauth_store.consume(state, platform="instagram", session_id=login.id)
        if pending is None:
            raise HTTPException(status_code=400, detail="Instagram authorization state is expired or invalid")
        if error or not code:
            raise HTTPException(status_code=400, detail="Instagram authorization was declined or incomplete")
        try:
            # Meta appends "#_" to the code; it is not part of the value.
            verified = instagram_oauth.exchange_and_discover(code=code.removesuffix("#_"))
            candidate = oauth_store.stage_verified(state, session_id=login.id, external_id=verified.user_id, label=verified.label, credential=verified.credential, scopes=verified.scopes, expires_at=verified.expires_at)
        except Exception as failure:
            raise HTTPException(status_code=400, detail="Instagram account verification failed; reconnect and try again") from failure
        return _confirm_page(candidate.label, candidate.external_id, state)

    @app.post("/api/oauth/instagram/confirm", tags=["social accounts"])
    def confirm_instagram_oauth(value: _Confirm, request: Request) -> dict[str, object]:
        if oauth_store is None:
            raise HTTPException(status_code=503, detail="Instagram connection is not configured")
        login = session_of(request)
        try:
            account_id = oauth_store.confirm(value.state, session_id=login.id)
        except ValueError as failure:
            raise HTTPException(status_code=409, detail=str(failure)) from failure
        account = next(item for item in runtime.accounts.list() if item.id == account_id)
        return {"id": account.id, "platform": account.platform, "display_name": account.display_name, "external_account_id": account.external_account_id, "status": account.status}


def _confirm_page(label: str, external_id: str, state: str) -> str:
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Confirm Instagram account — TubeForge</title><style>body{{background:#080d1a;color:#f3f7ff;font:16px system-ui;max-width:520px;margin:10vh auto;padding:20px}}main{{background:#111a2e;border:1px solid #253451;border-radius:16px;padding:24px}}button{{background:#5ee8ff;color:#07111e;border:0;border-radius:9px;padding:12px;font:inherit;font-weight:700;cursor:pointer}}button:disabled{{opacity:.6}}a{{color:#5ee8ff}}</style><main><h1>Confirm Instagram account</h1><p>TubeForge found <strong>{html.escape(label)}</strong>.</p><p>Account ID: <code>{html.escape(external_id)}</code></p><p>Posts to this account are public as soon as they publish. Confirm this exact destination before saving the encrypted connection.</p><input id="oauthState" type="hidden" value="{html.escape(state)}"><button id="confirm" type="button">Connect this account</button><p id="result" role="status" aria-live="polite"></p><a href="/">Return to Studio</a></main><script>document.querySelector('#confirm').onclick=async()=>{{const button=document.querySelector('#confirm'),result=document.querySelector('#result');button.disabled=true;button.textContent='Saving connection…';const csrf=(document.cookie.match(/(?:^|; )tubeforge_csrf=([^;]+)/)||[])[1];try{{const response=await fetch('/api/oauth/instagram/confirm',{{method:'POST',headers:{{'content-type':'application/json','x-csrf-token':decodeURIComponent(csrf||'')}},body:JSON.stringify({{state:document.querySelector('#oauthState').value}})}});if(!response.ok)throw Error(await response.text());result.textContent='Account connected. Returning to Studio…';location.assign('/');}}catch(_){{result.textContent='Could not save this connection. Start authorization again.';button.disabled=false;button.textContent='Connect this account';}}}};</script></html>"""
