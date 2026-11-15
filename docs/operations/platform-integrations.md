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
other hosts require HTTPS. The publisher starts with the default Compose services after
migrations. Without a valid encryption key it remains idle: its process can be online
while publishing capability is unavailable. In Studio → Accounts, connect and confirm the exact
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
repeated remote requests. Resume a quota-paused delivery explicitly from Publishing
after checking the quota. Provider rate-limit hints and bounded backoff delay retries;
uncertain remote outcomes are reconciled rather than blindly repeated. Authentication
failures require reconnecting the affected account. After downtime, overdue container
publications are spaced to avoid a burst and may be marked missed after their grace period.

Google may restrict an unaudited API project to private uploads. `pipeline.youtube.youtube_api_audited` defaults to false and Studio shows “audit pending: private only”. Only set it after the project's audit is approved. A future YouTube `publishAt` also requires an explicit future-public confirmation when scheduling that exact reviewed draft; the choice is frozen at scheduling time. Instagram preparation starts 30 minutes before its slot; unstarted work over 30 minutes late is marked missed. The calendar UI is still awaiting integration. Local fake tests are not proof of a real upload or schedule. A real private upload requires separate operator permission for that final.

## Instagram (Reels)

Live Instagram publishing requires `TUBEFORGE_INSTAGRAM_APP_ID`,
`TUBEFORGE_INSTAGRAM_APP_SECRET`, `TUBEFORGE_INSTAGRAM_OAUTH_REDIRECT_URI`,
a Meta app, eligible professional account and official permissions. The parallel
Instagram adapter still requires integration with the separate container publication
contract and the exact-post confirmation gate. The Instagram connection screen and OAuth code are included, but the publishing worker does not advertise Instagram while its adapter remains incompatible with the safe delivery protocol. Connection and live publication have not been verified. Setup details are in [the Instagram review](../instagram-publishing-review.md).

## Snapchat

TubeForge explicitly exposes Snapchat as `manual_handoff_required` until an
operator confirms an approved official Snap publishing capability. It does not
store Snapchat passwords or use browser automation/private APIs.
