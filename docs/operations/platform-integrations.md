# Platform integrations

## Shared account security

TubeForge stores only encrypted OAuth credential envelopes. Set
`TUBEFORGE_ACCOUNT_ENCRYPTION_KEY` to a Fernet key generated outside source
control before submitting an account credential. Account APIs never return
access or refresh tokens. Password-based platform automation is unsupported.

## YouTube

The existing publisher uses the official YouTube Data API/OAuth upload scope.
Create a Google OAuth client, configure its redirect URI for the deployment,
and supply the existing YouTube client/token settings. Live upload remains
operator-credential-blocked and defaults to dry-run/private behavior.

## Instagram (Reels)

TubeForge uses **Instagram Login** for a Professional (Business or Creator) account. No Facebook
Page is needed, and Facebook Login stays a separate contract.

Setup (operator, once): create a Meta Business app, add *Instagram → API setup with Instagram login*,
request `instagram_business_basic` and `instagram_business_content_publish`, keep the app in
Development mode, add your account as an Instagram tester and accept the invite in the Instagram app.
Set the redirect URI to `https://localhost:62065/oauth/instagram/callback` (Meta requires https;
see the TLS note below) and put these in `.env`:
`TUBEFORGE_INSTAGRAM_APP_ID`, `TUBEFORGE_INSTAGRAM_APP_SECRET`, `TUBEFORGE_INSTAGRAM_OAUTH_REDIRECT_URI`.

- **Connect / reconnect:** Studio → Accounts → *Connect Instagram* (or *Reconnect this account*).
  Studio shows the exact `@handle` and account ID; nothing is saved until you confirm. A
  reconnect for a different account is refused.
- **Token life:** the long-lived token lasts 60 days and is refreshed in place by the publisher
  worker when it is within five minutes of expiry (Instagram needs it to be at least 24 h old). An
  unused account whose token expires needs a reconnect.
- **Publishing:** every Instagram post is public the moment it publishes. A draft needs the
  "this goes public" box ticked per post, and that tick is part of the reviewed identity.
  Video bytes go straight from local disk (resumable upload); no public URL is served.
  A post is refused before any remote call if the 24-hour publishing limit (100) is reached.
- **Uncertain outcomes:** if the worker loses the result, Studio offers *Inspect* and *Resume* on
  the saved container. A container Instagram reports as already published is never republished,
  and its media id is not guessed: check the account before retrying.
- **TLS note:** the dashboard is plain HTTP on loopback. For the Instagram redirect, terminate TLS
  for `localhost:62065` locally (tunnel your browser to it) or use the token-paste fallback in
  `docs/publishing-plan.md` (decision D1). Status: BLOCKED on the operator's choice.

## Facebook

Account records can be created, but no live adapter is claimed.

## Snapchat

TubeForge explicitly exposes Snapchat as `manual_handoff_required` until an
operator confirms an approved official Snap publishing capability. It does not
store Snapchat passwords or use browser automation/private APIs.
