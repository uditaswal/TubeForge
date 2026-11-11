# Platform integrations

## Shared account security

TubeForge stores only encrypted OAuth credential envelopes. Set
`TUBEFORGE_ACCOUNT_ENCRYPTION_KEY` to a Fernet key generated outside source
control before submitting an account credential. Account APIs never return
access or refresh tokens. Password-based platform automation is unsupported.

## YouTube

For setup, follow [the publishing plan](../publishing-plan.md#1-operator-credentials-only-one-time).
Keep `TUBEFORGE_ACCOUNT_ENCRYPTION_KEY` backed up separately: loss of the key makes the
encrypted account credentials unreadable and requires reconnecting each account. Never
put secrets in a draft or commit them. Configure `TUBEFORGE_GOOGLE_OAUTH_CLIENT_ID`,
`TUBEFORGE_GOOGLE_OAUTH_CLIENT_SECRET`, and `TUBEFORGE_GOOGLE_OAUTH_REDIRECT_URI` in
`.env`; the Google redirect may be loopback HTTP at `127.0.0.1` or `localhost`, and
other hosts require HTTPS. Start the optional publisher using the `publishing` Compose
profile after applying migrations. In Studio → Accounts, connect and confirm the exact
Google channel. To reconnect, use the existing connection flow and confirm the same
channel; retry a delivery only when its state allows that action.

Approve the exact final and its platform disclosure choice in Day review before creating
a YouTube draft. Review the draft and submit only after separately authorizing that exact
post. The adapter currently permits private uploads only. The Publishing screen reports
worker, authorization, connection and estimated quota readiness. `pipeline.youtube`
settings `category_id` (default `"22"`), `self_declared_made_for_kids` (default false),
`max_upload_bytes` (default 2,000,000,000), `daily_quota_units` (10,000) and
`upload_quota_units` (1,600) control local checks. The durable ledger reserves upload
units by Pacific calendar day, and conservatively keeps reservations after uncertain
outcomes. It cannot see API use by other clients in the Google project; inspect Google
Cloud quota as well. A quota refusal is recorded on the delivery and does not trigger
repeated remote requests.

Google may restrict an unaudited API project to private uploads. Complete the YouTube
API Services audit before relying on scheduled/public publishing; scheduling and its
audit control are not implemented on this branch. Local fake tests are not proof of a
real upload. A real private upload requires separate operator permission for that final.

## Instagram and Facebook

These account records can be created, but live publishing requires a Meta app,
eligible professional Instagram account or Facebook Page, approved publishing
permissions, app review where required, and official Graph API OAuth. No live
adapter is claimed yet.

## Snapchat

TubeForge explicitly exposes Snapchat as `manual_handoff_required` until an
operator confirms an approved official Snap publishing capability. It does not
store Snapchat passwords or use browser automation/private APIs.
