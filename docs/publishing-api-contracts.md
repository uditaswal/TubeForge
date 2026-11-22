# Publishing API contracts

Moved verbatim from `docs/HANDOFF.md` on 18 Nov 2026. Status lives in HANDOFF; this file is the contract.
Instagram work is PARKED (operator decision, 16 Nov 2026).

## Cross-post API

For an approved and unchanged Day-review short, `GET /api/batch-plans/{short_id}/post-defaults?reviewed_identity=<sha256>` previews YouTube and Instagram metadata without creating a post. `POST /api/batch-plans/{short_id}/prepare-post` takes `{"reviewed_identity":"<sha256>","destination_account_ids":["<youtube-account-id>","<instagram-account-id>"]}` and returns one draft, its source and draft review identities, and per-destination metadata. It stages the reviewed final and thumbnail; it never uploads or publishes. Instagram hashtags are already included in `caption`; the `hashtags` array describes those tags and must not be appended again. The endpoint rejects stale approval or disconnected accounts.

The service's `submit(..., confirmed_public_accounts=frozenset({...}))` requires every Instagram account ID in that set and records the actor, draft identity and confirmation. The existing API submit gate still supports private YouTube only; Claude must connect a signed-in, exact-post public confirmation to this service and its own per-platform gate before any Instagram submission. Never infer approval from draft creation or Day review. A failed destination does not cancel the other destination. Day review now prepares drafts through this endpoint; public Instagram submission remains unavailable.

## Scheduling API

`GET /api/publishing/slots?day=YYYY-MM-DD` returns the 13:00 and 19:00 Asia/Kolkata slots. `POST /api/publishing/drafts/{post_id}/schedule` accepts the draft `reviewed_identity`, timezone-aware `scheduled_for`, `cadence_override`, `confirmed_public_accounts` and `allow_future_public_youtube`. A 409 with `detail.warnings` requires showing the M-S7 warning and an explicit override; override and actor are durable. The Instagram public account IDs and future-public YouTube flag are separate explicit confirmations. `youtube_api_audited` defaults false; the schedule snapshots that setting and confirmation, so changing the flag later cannot silently enable a public schedule. With the flag false the YouTube upload stays private and sends no `publishAt`.

`POST /api/publishing/deliveries/{delivery_id}/pending-action` accepts `pause`, `resume` or `cancel`; it rejects in-flight or already remote work, and a YouTube upload session already opened must be reconciled. The draft list includes slots and pending-action capability booleans. Instagram begins container preparation no earlier than slot minus 30 minutes and publishes at/after slot within a 30-minute grace; past grace is `missed`. Audited YouTube refuses a past `publishAt`, even inside the grace, rather than publishing immediately. A post or slot requires the operator's separate exact-post permission for real use. A date-and-slot control is available for private YouTube drafts; a full calendar and Instagram scheduling UI remain unbuilt.

## Instagram adapter contract

Implement `ContainerDestinationAdapter` in `pipeline/delivery_executor.py`; do not
publish during `upload`. `open_session(...)` returns `RemoteSession(session_id,
expires_at)`: the session string is encrypted in the queue and the timezone-aware
expiry is the provider's actual container deadline (Instagram normally 24 hours).
`upload(...)` returns `ContainerReceipt(container_id)` only after bytes are accepted;
`inspect_session(...)` / `resume_session(...)` can return that receipt during
reconciliation of an interrupted upload. Keep the container ID stable. The executor
persists it before processing or publishing.

`inspect_container(container_id, external_account_id, credential)` is read-only and
returns `ContainerObservation(state, remote_id=None, remote_url=None,
retry_after_seconds=None)`, where state is `processing`, `ready`, `published`,
`expired` or `failed`; `published` requires the actual media ID. A read-only rate
limit may raise `ProviderRateLimitHint(seconds)`; polling delays are bounded to 1–3600 s.
`publish_container(..., heartbeat)` is the separate mutation and returns
`UploadReceipt(media_id, remote_url)` after success. Call the heartbeat before remote
writes; never retry publication inside the adapter. Any ambiguous publish exception or
expired publish lease becomes `unknown_outcome`; inspection must prove a published
media ID, and a still-ready or expired container does not authorize another publish.
`inspect(...)` verifies the final account and caption. The API's separate exact-post
confirmation and Claude's per-platform gate are still required before a real Reel.
The reviewed `claude/publish-instagram` adapter at `5ec244b` publishes from `upload`
and `resume_session`, lacks the separate inspection/publication methods and appends
hashtags already present in the caption. Adapt it before integration; the executor now
rejects that protocol before any remote operation and supplies `confirm_public` only
after validating the recorded exact-draft confirmation. A published container without
a provable media ID stays unknown; do not guess or publish again. Quota exhaustion
must pause rather than retry. Migrations on this branch are `20261111_0033` → `20261111_0034` → `20261111_0035`; reconcile any parallel
migration heads deliberately when integrating.
