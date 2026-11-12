# HANDOFF — read this first (Codex and Claude)

Shared between agents. Keep it short; update **Next step** before stopping.
Rules and safety contract: `AGENTS.md`. Docs index: `docs/README.md`.
The long per-feature history (everything before 9 Nov 2026) is in git history and the local, git-ignored
`doc-internal/handoff-archive-20261109.md`; nothing here depends on it.
Branches: work on `dev` (worktree `../tubeforge-dev`, also where the Compose stack and Claude runner run) or a feature
branch/worktree; `main` is merged only after the operator approves that specific merge.

## Goal
Scheduled/user-briefed AI Shorts → local render (Kokoro TTS, Python/FFmpeg) → review → upload to
YouTube/Instagram. The AI (Codex *or* Claude) is only the "brain": it returns a strict JSON script + scene plan;
all pixels, audio and encoding are local and cost no tokens.

## Working rules
1. Start: `git status`, `git log -5 --oneline`, read this file. One agent per branch at a time.
2. Never commit on `main`. Work on `dev` or a feature branch, then post a review. Merge to `main` only after asking and getting explicit approval for that merge; never push or force-push a remote unless asked. Remove temporary branches/worktrees once merged.
3. Commit at every green checkpoint; before stopping update **Next step**. No AI attribution trailers; never `--no-verify`.
4. Judge video by looking at frames (`ffmpeg ... tile=6x2` contact sheet, then view the PNG) and run `.agents/skills/om-video-quality/qa_check.py`.
5. Python with renderer deps: `.venv-benchmark/bin/python` (`PYTHONPATH=src`). Heavy renders and the full test suite (about 18 min): run in the background.
6. Do not publish anything. Do not reset script-attempt allowances. No live writer (Claude/Codex) call without the operator's go-ahead.

## Architecture in one screen
- Dashboard (`api/app.py`, port 62065, loopback only; the operator uses an SSH tunnel) → durable job → worker (`workers/`, Docker) → `pipeline/orchestrator.py`.
- **Script owner** per job (`codex` default | `claude`). Codex: root-owned host runner (`/run/tubeforge-codex/codex.sock`, sudo to redeploy). Claude: user runner `scripts/run_claude_runner.sh` (`data/run/claude/claude.sock`). Routing: `providers/content/factory.py::ScriptOwnerRouter`.
- **Reference Shorts** (`m6-content-v8`, 9:16, 30–90 s): `pipeline/reference_short.py` → `rendering/shorts/` (Story style via HyperFrames). Preview 720×1280, final 1080×1920; QA: decode, −15..−13 LUFS, TP ≤ −1.5.
- Batch plans (`api/batch*.py`): import → queue (strictly FIFO) → Day review (checksum-bound approval, staged export). Spend cap: 40 calls / $8 / 24 h (`data/run/claude/usage-ledger.jsonl`).
- Long-form (Codex lane): reference intake, then LF2 primary-source grounding and bounded script admission (`docs/long-form-lf2-plan.md`).

## State (9 Nov 2026)
- `dev` is pushed to origin (merged: Batch plans cards/stage chips/drop zone/line-numbered errors/warnings, Day review Reject/Regenerate confirmation, stale-test refresh, `[whisper]` disabled by config). **Needs a stack rebuild to take effect:** `scripts/restart_stack.sh`.
- Operator verified: pronunciation fix and selective acronym gaps sound right; plain narration preferred over `[whisper]`; the Day review shorts (2026-11-04 `story-*`, and `pilot-ms1`) were watched and are fine. **Nothing is approved or published**; Approve/Stage is clicked in Day review (`/batch/review`).
- `[whisper]` is OFF: `pipeline.reference_short.delivery_whisper: "off"` (`config/production.yaml`); whisper cues are spoken plainly. The yt-script prompt still teaches it (changing it needs the host wheel redeploy, operator sudo). Test clips: `artifacts/review/whisper-test-20261109/`.
- Full suite on `dev`: 1020 passed; the only failure is `test_voice_preview_is_synthesized_once…` (no `piper` on the host; passes in the worker image). Fresh worktrees need the gitignored `models/` folder symlinked in.
- Operator review (9 Nov): "all looks fine" for the Batch plans / Day review changes and the shorts above. That is the visual sign-off for batch UI M-U1 and M-U2 (confirmations); Approve/Stage in Day review is still the operator's click.
- **Settings page `/settings` (10 Nov, merged to `dev`, live):** prompt size limits, source trimming, automatic retry of rejected scripts, worker retries; stored in `data/config/runtime-settings.json`, audited. The two-attempt allowance is not a setting (`docs/settings.md`). A request is size-checked when built (Studio, Batch, retry-as-new): long excerpts are trimmed at sentence ends or the brief is refused with the numbers. The length meter warns about scenes with more than two spoken numbers. `script:` is accepted as the YAML field for your own narration (same as `narration:`).
- **Exact-script mode (11 Nov, merged to `dev`, live):** `script_mode: exact` in a batch yaml block, the Studio "Use my script exactly" checkbox, or Settings `script.exact_by_default`. The Claude writer only plans visuals; the operator's wording is forced in before binding (`providers/content/exact_script.py`, hooked in `output.unwrap_generation`); hook/craft/number/title checks and the runner's angle/editor/hook passes are skipped; structure, layout, length cap and claim/source binding still apply; Codex owner is refused. `ContentRequest.exact_script` is part of generation identity only when true. Not yet seen on a real render: the first exact video needs the operator's go-ahead for one Claude call.
- Unmerged, waiting for the operator's go-ahead: `claude/cadence-scope` (import cadence warnings only for the imported shorts, worktree `../tubeforge-claude-cad`) and `claude/template-polish` (copy-template tidy, worktree `../tubeforge-claude-tpl`). Remove both worktrees after merging.
- Real bug fixed: `GET /api/batch-plans` returned 500 when a topic's job had been deleted (shows "job missing" now).

## Next step (in order)
- **Publishing P1, P3–P5 backend — IMPLEMENTED; live acceptance BLOCKED.** Fake upload, scheduling, reconciliation and responsive signed-in checks passed; the seven-day fake soak delivered 42 of 42 destinations without duplicates or losses (`artifacts/review/publishing-backend-soak-20261112/summary.json`). Migrations 0033–0035 passed temporary-DB round trips. Full suite passed: 1,140 passed, 34 skipped (`/tmp/tubeforge-publish-full-20261112.log`). Next: integrate the parallel adapter and gate after review. A real upload needs credentials, a named approved final and permission for that exact post; no upload is authorized yet. Claude's UI and Instagram integration remain unverified. See `docs/publishing-backend-review.md` for blockers and evidence.
- **Parallel integration:** Claude owns Instagram Login, the Reels adapter and the API per-platform gate on `claude/publish-instagram`; follow the contracts below. Every real upload needs the operator’s go-ahead for that exact post.
- **Next command:** `git -C /home/uditaswal/docker/tubeforge/tubeforge-publish-ig log -1 --oneline` — check whether Claude's branch has advanced beyond reviewed commit `5ec244b`, then review its adapter and gate against the contract below before integration. Do not merge or upload without the required authorization.

### Cross-post API handoff for Claude

For an approved and unchanged Day-review short, `GET /api/batch-plans/{short_id}/post-defaults?reviewed_identity=<sha256>` previews YouTube and Instagram metadata without creating a post. `POST /api/batch-plans/{short_id}/prepare-post` takes `{"reviewed_identity":"<sha256>","destination_account_ids":["<youtube-account-id>","<instagram-account-id>"]}` and returns one draft, its source and draft review identities, and per-destination metadata. It stages the reviewed final and thumbnail; it never uploads or publishes. Instagram hashtags are already included in `caption`; the `hashtags` array describes those tags and must not be appended again. The endpoint rejects stale approval or disconnected accounts.

The service's `submit(..., confirmed_public_accounts=frozenset({...}))` requires every Instagram account ID in that set and records the actor, draft identity and confirmation. The existing API submit gate still supports private YouTube only; Claude must connect a signed-in, exact-post public confirmation to this service and its own per-platform gate before any Instagram submission. Never infer approval from draft creation or Day review. A failed destination does not cancel the other destination. No new cross-post UI has been built here.

### Scheduling API handoff for Claude

`GET /api/publishing/slots?day=YYYY-MM-DD` returns the 13:00 and 19:00 Asia/Kolkata slots. `POST /api/publishing/drafts/{post_id}/schedule` accepts the draft `reviewed_identity`, timezone-aware `scheduled_for`, `cadence_override`, `confirmed_public_accounts` and `allow_future_public_youtube`. A 409 with `detail.warnings` requires showing the M-S7 warning and an explicit override; override and actor are durable. The Instagram public account IDs and future-public YouTube flag are separate explicit confirmations. `youtube_api_audited` defaults false; the schedule snapshots that setting and confirmation, so changing the flag later cannot silently enable a public schedule. With the flag false the YouTube upload stays private and sends no `publishAt`.

`POST /api/publishing/deliveries/{delivery_id}/pending-action` accepts `pause`, `resume` or `cancel`; it rejects in-flight or already remote work, and a YouTube upload session already opened must be reconciled. The draft list includes slots and pending-action capability booleans. Instagram begins container preparation no earlier than slot minus 30 minutes and publishes at/after slot within a 30-minute grace; past grace is `missed`. Audited YouTube refuses a past `publishAt`, even inside the grace, rather than publishing immediately. A post or slot requires the operator's separate exact-post permission for real use; the calendar UI is not built on this branch.

### Instagram adapter contract for Claude

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

0. **LeetCode video (10 Nov): job `642dc2b2…` is at `script_approval_required`: operator reviews the script in Generations** (12 scenes, 169 words, your wording kept in 7 scenes; grounded claims c1-c10, scene 10's "more than half" is claim c9). Earlier failures and their causes: prompt over the 90,000 ceiling (three 24k-character excerpts + the 57k fixed prompt), then the craft gate's numbers rule (two..billion count; at most 2 per scene) on an operator script. Both are now handled before queueing; see `docs/settings.md`.
1. **Operator:** approve/stage the 2026-11-04 shorts in Day review (rebuild with `scripts/restart_stack.sh` if not done); click "Retry approved media stages" on job `49bfc7ef…`.
2. **Codex (LF2):** operator approved more Claude spend for the long-form pilots and said the long-form branch may merge after review. Still needs a spend figure per pilot, and deployment review of migrations `20261108_0033` and `0034`. Phase D is blocked on structured-draft failures (`docs/long-form-lf2-d-*.md`).
3. **Claude, UI:** Day review shows the script beside its sources; then M-U4 (empty/loading/error/disabled states, focus order, contrast).
4. **Claude, scripts:** Round 3 (P5) is merged: `docs/original-script-audit.md`, fixtures in `tests/fixtures/scripts/`, advisory `craft.py::spoken_craft_problems` / `rewrite_keeps_evidence`, `tests/test_script_audit.py` (IMPLEMENTED, not VERIFIED; the before/after generation is NOT MEASURED and needs the operator's go-ahead for a real Claude call: provider, calls and cost are stated first). Also one go-ahead call to confirm a writer honours an operator script, and the leftovers in `docs/script-naturalness-plan.md` (a running example with concrete values, v1/v2 scope, a figure in the hook). Remove the `../tubeforge-script-audit` worktree and branch once the operator is happy.
5. **Operator, whenever:** review candidates `artifacts/review/php-m4-landscape-20261105-v2/final.mp4` and `artifacts/review/m4-portrait-20261105/final.mp4`; the 10 Nov 09:00 UTC check-in (`trig_01BehFQ3ksjkkZxXQkVccSmd`) reports the first overnight production run.
6. **Queued at the bottom (operator decision 9 Nov):** Codex⇄Claude auto-fallback (Track E is verified only on the unmerged `codex/provider-fallback`; needs merge, migration `20261105_0032`, rebuild; `docs/provider-fallback-review.md`) and the Shorts thumbnail `safe_region` check (needs the operator's real phone screenshot).

## Gotchas
- Batch jobs are strictly FIFO: a script parked at `script_approval_required` blocks every later batch job, including the 22:00 overnight run. Clear stray trial jobs first; rejecting a script does not unblock, deleting the job does.
- Failed generations burn the two-attempt allowance per exact request source packet: change the brief or sources, never reset counts. An identical accepted request reuses the cached script (no Claude call).
- Brief sources: small HTTPS `text/html`/`text/plain` pages on an allowlisted host, same-host HTTPS redirects only; fewer than two usable sources triggers a Claude research step. Very long sources fail before any model call (prompt over 90,000 characters).
- The Claude runner imports code at start: restart it after any prompt/layout change; restart `web` and `worker` after schema changes. Worker image extras: `alignment,reference-renderer`.
- Dashboard first load asks for thumbnails/ffprobe per ready job; on a busy host `/api/jobs` took 12–64 s and the worker once hit `database is locked`.
- Dashboard test login: create a temporary admin (`tubeforge create-admin`) and delete it and its sessions afterwards.
- Under heavy swap Whisper alignment can fail (retried once, then a logged estimate fallback).
