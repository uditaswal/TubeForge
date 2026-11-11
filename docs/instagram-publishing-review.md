# Instagram publishing (P2) review

Branch `claude/publish-instagram` (from `feature/publish-pipeline` `c86ec16`). Status: **IMPLEMENTED**,
not VERIFIED: nothing has run against a real Meta app or account.

## What changed
- `security/instagram_oauth.py`: Instagram Login authorize URL, code → long-lived token, `/me` identity
  proof (Business/Creator only, both permissions granted).
- `security/account_credentials.py`: `InstagramCredentialRefresher` (in-place refresh; 400/401/403 →
  reconnect; other failures temporary).
- `providers/publishing/account_instagram.py`: `AccountInstagramAdapter` implementing `DestinationAdapter`:
  preflight (caption/hashtag limits, public confirmation, size, identity, 24 h quota) → REELS container with
  resumable upload → container saved by the executor before bytes → rupload → poll `FINISHED` → one
  `media_publish`. `inspect_session` never reports a published container as ours; `resume_session`
  continues the same container from the server offset.
- `api/instagram_connect.py` + `api/app.py`: `/api/oauth/instagram/{status,start,confirm}`,
  `/oauth/instagram/callback`; platform gates now cover Instagram (submit, actions, inspect/resume flags);
  Studio: Connect/Reconnect Instagram, per-post public confirmation, submit label.
- `pipeline/manual_publish.py`: Instagram metadata may carry `confirm_public`; submit refuses without it.
  The tick is inside the reviewed identity.
- Small shared edits for Codex to review: `delivery_executor._matches` (Instagram compares the full caption
  with hashtags via `instagram_full_caption`), `delivery_queue.request_action` (Instagram allowed),
  `publishing_worker/main.py` (registers `instagram` and its refresher), `compose.yaml` env names.

## Evidence
- New tests: 14 (`test_instagram_oauth`, `test_account_instagram_adapter`, `test_instagram_connect_api`,
  two in `test_manual_publish_drafts`) pass. Publishing/queue/oauth/account/dashboard group: all pass except
  `test_delivery_cues::test_whisper_setting_defaults_to_off_in_config_and_production_yaml`, which fails the
  same way on the base branch.
- Signed-in Chromium on a temp stack (temp admin, DB discarded): Accounts and Publishing at 1280, 820 and
  390 px: no JS errors, no horizontal overflow; *Connect Instagram* visible and enabled once status reports
  configured.

## Not done / BLOCKED
- Live connect and one real Reel: needs the Meta app, `.env` values, a decision on the HTTPS callback (D1),
  and the operator's go-ahead for that exact post.
- Duration check (Reels ≤ 90 s) and Shorts preflight are Codex's P1 preflight; this adapter only checks size.
- Proactive refresh at 10 days left and expiry alerts are P5.

## For Codex
Interface used: `SafePreflightError(category="retry"|"auth"|"invalid")`; `session_id` is a JSON string
`{"c": container_id, "u": rupload_url}` (encrypted by the executor); remote id is the media id.
Container expiry (24 h) and a separate publish step are inside the adapter; if you generalise the executor
for these (milestone 2), keep `instagram_full_caption` as the compared text.
