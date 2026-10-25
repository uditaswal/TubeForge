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

## Instagram and Facebook

These account records can be created, but live publishing requires a Meta app,
eligible professional Instagram account or Facebook Page, approved publishing
permissions, app review where required, and official Graph API OAuth. No live
adapter is claimed yet.

## Snapchat

TubeForge explicitly exposes Snapchat as `manual_handoff_required` until an
operator confirms an approved official Snap publishing capability. It does not
store Snapchat passwords or use browser automation/private APIs.
