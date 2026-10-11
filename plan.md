# Publishing pipeline delivery plan

This plan turns the 4 October 2026 publishing design and dashboard concept into
repository work. The attached HTML is a **sample interaction**, not an app to
deploy or evidence of connected accounts. `docs/STATUS.md` is the authoritative
current status; the tracker below is updated with it after each phase.

## Rules and release boundary

- Work through phases in order. Report each acceptance result before starting
  the next. `IMPLEMENTED` means code exists; only `VERIFIED` means the tests and
  real output inspection in that phase passed.
- No live upload or public scheduling without explicit operator authorization.
  The repository's current private/dry-run default stays in force. Offline
  adapters and test accounts can prove code paths but cannot prove remote
  publication or application approval.
- A slot selects one canonical video for all selected destinations. A separate
  delivery receipt is required per account. Only failed destinations retry;
  unresolved outcomes stop for reconciliation. Archive starts only after every
  required destination is confirmed published.
- Preserve the existing worker lease, ownership fence, checkpoint, atomic
  artifact promotion, cancellation, approval, and script-provider policies.

## Architecture inventory, 5 October 2026

| Existing contract | Location | Publishing gap |
| --- | --- | --- |
| SQLite/Alembic, jobs, leases, artifacts and approval records | `src/tubeforge/db/models.py`, `db/repositories.py`, migrations through `20260927_0020` | No canonical backlog asset/fingerprint, automation occurrence, per-destination delivery, archive task or outbox schema. |
| Topic cron scheduler and durable schedule runs | `src/tubeforge/scheduling/service.py`, `scheduling/main.py` | Creates generation jobs only; no daily slot preparation, grace/rollover policy or destination snapshot. |
| YouTube private-first publication and reconciliation | `src/tubeforge/providers/publishing/youtube.py`, `pipeline/orchestrator.py`, `db/repositories.py` | Uses one configured channel and file-backed OAuth token; no account-scoped OAuth flow, multi-account delivery, `publishAt`, or cancellation of an accepted schedule. |
| Separate generic dispatch attempts | `src/tubeforge/pipeline/dispatch.py` | Prototype is not wired to the worker; success means upload response, has no remote verification, and cannot safely retry an unknown outcome. |
| Social-account metadata with encrypted envelopes | `src/tubeforge/db/models.py`, `db/repositories.py`, `security/secrets.py`, `api/app.py` | API accepts operator-supplied credential JSON and marks it connected without remote identity check; no OAuth callback/reconnect or credential refresh lock. Do not use this as proof of a connection. |
| Authenticated Creator Studio | `src/tubeforge/api/app.py` | Generation and activity UI exist; attached publishing screens are illustrative only. Publishing actions must be wired to durable API states. |
| Generation and operator-supplied clip sources | `src/tubeforge/pipeline/`, `clipping/` | Neither feeds a canonical, no-repeat publishing pool; stream moment discovery is not yet a publisher source. |

Migration sequence: add independent publishing tables for account credentials,
canonical assets and fingerprints, source lineage, versioned presets, automations
and UTC occurrences, parent runs and child deliveries, attempts, archive tasks,
outbox and audit events. Add unique `(asset, account, edition)` and
`(automation, scheduled_utc)` constraints. Backfill only explicitly selected
existing artifacts; do not infer that historic generation or upload rows are
published. Keep old publication tables readable until a tested upgrade maps
them. Prove fresh and upgrade migrations before enabling workers.

Platform readiness checklist (no application credentials found in tracked
configuration): supply separate Google and Meta application identities, approved
redirect URLs, scopes/roles, test accounts, encryption key backup and a secure
HTTPS callback route. Verify the selected YouTube channel ID and Instagram
professional account ID before storing a connection; reconnect must match the
same identity. Confirm Google API audit/public-upload eligibility and Meta
publishing access for the actual applications. Official YouTube documentation
states that affected unverified projects' uploads remain private and that
`publishAt` applies only to a never-published private video. Record actual app
review evidence during Phase 1; a local mock or private-only upload is not it.
For Instagram Login, Meta's current published collection identifies professional
Business/Creator accounts and the `instagram_business_content_publish` scope;
do not substitute the Facebook Login permission set or imply a Facebook Page is
required for the Instagram Login route.

Platform references: [YouTube uploads and audit](https://developers.google.com/youtube/v3/docs/videos/insert),
[YouTube `publishAt`](https://developers.google.com/youtube/v3/docs/videos),
[Meta's Instagram Login collection](https://www.postman.com/meta/instagram/folder/1z5vxzu/instagram-api-with-instagram-login).

## Milestone tracker

| Phase | Status | One user-visible outcome | Acceptance test and required evidence | Out of scope |
| --- | --- | --- | --- | --- |
| 0. Inventory and readiness | **VERIFIED** | An actionable build and connection plan based on this checkout. | Inspect code, migration head, design and concept; write this inventory, dependency checklist and migration order; verify plan/status consistency. | Production upload. |
| 1. Connect and manual publish | **BLOCKED** | Select a video and exact YouTube/Instagram accounts; draft, preview and submit one post per destination. | Authenticated dashboard and API tests; encrypted account-scoped OAuth, identity and reconnect tests; controlled real posts to both accounts with inspected remote captions/video, IDs/links and verified publication. Separate public-release eligibility check. Google connection, canonical drafts, an offline-tested fenced delivery core, credential refresh, opt-in worker and private YouTube submit exist. Instagram Login's provider contract is inaccessible here; browser and controlled remote acceptance also remain. | Folder autopilot. |
| 2. Backlog autopilot | **NOT STARTED** | 13:00 IST folder scheduling with one new video per slot and safe archive. | Real multi-destination scheduled run; source/archive hashes and manifest; restart and concurrent-worker tests; retry failed destination without reposting successful one; archive failure recovery; late and empty-source behavior. | Generated or clipped sources. |
| 3. Presets and account control | **NOT STARTED** | Reusable, versioned metadata and per-account manual overrides. | Persist and inspect multiple account selections, content-derived drafts and locked fields; prove future-only preset changes and explicit pending-job edit/reapproval; signed-in UI tests. | Generation/clipping changes. |
| 4. Generation source | **NOT STARTED** | A reserved topic becomes a scheduled post using the same delivery engine. | Inspect real 30–55 second 1080×1920 output and grounded script; approved provider evidence; destination receipts and preparation-deadline failure test. | Stream discovery. |
| 5. Clipping source | **NOT STARTED** | An unused stream/VOD moment becomes a scheduled short. | Inspect clip, provenance and timestamps; prove segment exclusion, empty-stream behavior, receipts and signed-in UI. | Other platforms. |
| 6. Expansion contract | **NOT STARTED** | Platform capabilities can extend without changing scheduling. | Contract tests with stub and an actual authorized adapter; capability-driven UI and unsupported-state tests. | Unrequested platform launches. |

## Phase 1 implementation order

1. Replace the unsafe account-create credential handoff with server-side OAuth
   initiation/callback and identity confirmation. Keep credentials encrypted and
   invisible to the browser; pin one account identity to each connection.
2. Build canonical asset registration and a draft/submit API with destination
   snapshots. A manual post and later automation use the same delivery identity.
3. Add destination workers and reconciliation. Save remote operation IDs before
   advancing; treat ambiguous results as `UNKNOWN_OUTCOME`, never an automatic
   fresh upload. Confirm publication before parent success.
4. Integrate a real Studio composer/accounts/activity workflow with pending,
   success, failure and reconnect states. Sign-in remains required.
5. Run offline failure/concurrency/migration tests, inspect a local smoke
   artifact, then request explicit permission and credentials for controlled
   remote validation. Phase 1 remains `IMPLEMENTED` or `BLOCKED` until remote
   evidence is captured.

## Decisions and dependencies

- Preferred source order for early value is folder backlog, then existing
  generation, then clipping. Phase 1 still establishes the shared manual
  destination path so Phase 2 does not build a second publisher.
- Default recurrence is daily 13:00 Asia/Kolkata. Optional 19:00, weekdays,
  timing mode, 60-minute configurable preparation lead and 30-minute grace
  enter with Phase 2. Scheduler stores UTC occurrences and never burst-publishes
  missed slots.
- Metadata generation reuses the approved production provider configuration;
  no local LLM or paid fallback is introduced automatically. Content analysis
  needs a separately visible budget and low-confidence review path.
- Exact duplicate exclusion uses a stable SHA-256 fingerprint; intentional
  repost creates a new visible edition. Near-duplicate matching is later work.
- Instagram needs an official publishing route, professional-account eligibility
  and a narrowly staged HTTPS media URL. The staging endpoint must not expose
  the inbox or arbitrary host files.
- Before any live test, the operator must provide app configuration and select
  the exact test accounts/video and authorize the upload. The repo's `AGENTS.md`
  expressly forbids publishing to YouTube without that authorization.

## Acceptance log

| Date | Phase | Result | Evidence and next action |
| --- | --- | --- | --- |
| 2026-10-05 | 0 | **VERIFIED** | Repository contracts and attached design inspected; plan and migration order recorded. Existing publishing/scheduler baseline: 13 focused tests passed in the Compose web container (its test files are baked into the image; source is bind-mounted). Next: Phase 1 local implementation; remote acceptance requires account access and explicit upload authorization. |
| 2026-10-05 | 1 | **IMPLEMENTED** | Google OAuth state, PKCE, channel discovery and explicit confirmation; credential handoff blocked; Studio account states added. Seven focused tests and a reconnect identity test passed; no remote exchange, Instagram connection or manual destination delivery yet. Next: complete those paths before remote acceptance. |
| 2026-10-05 | 1 | **IMPLEMENTED** | A real FFmpeg MP4 passed canonical staging, SHA-256, probe, dedupe and source-change checks. New parent/child draft tables and signed-in API/Studio composer save exact account and metadata snapshots; focused asset, draft, migration, OAuth and signed-in API tests passed. Submit, Instagram connection, worker/reconciliation and real browser/remote checks remain. |
| 2026-10-05 | 1 | **IMPLEMENTED** | Migration `20261005_0024` adds fenced delivery claims and attempts. Offline executor tests cover encrypted session storage, account serialization, hash failure before remote work, timeout as `unknown_outcome`, and matching read-only publication verification before parent success. All five migration tests passed. An account-scoped YouTube resumable adapter passed mocked HTTP channel, upload and inspection tests. Credential refresh, Instagram adapter/OAuth, deployed worker, submit UI and real remote acceptance remain. |
| 2026-10-05 | 1 | **IMPLEMENTED** | Migration `20261005_0025` adds per-account refresh leases and fences. Mocked Google refresh tests cover one refresh across workers, invalid-grant reconnect, and a reconnect racing an old refresh; the delivery executor now waits safely on transient refresh failures. Five migration tests and nine focused credential/adapter/executor tests passed. Instagram, deployed worker, submit UI, provider session-status reconciliation and remote acceptance remain. |
| 2026-10-05 | 1 | **IMPLEMENTED** | An explicit read-only reconciler queries the saved YouTube resumable session. Mocked HTTP and executor tests proved a timed-out upload can recover its remote ID and finish verification without a second upload (`10 passed`). An incomplete session stays `unknown_outcome` pending same-session resumption; live behavior and worker wiring remain unverified. |
| 2026-10-05 | 1 | **IMPLEMENTED** | An explicit same-session resume uses Google's acknowledged byte range and never opens a replacement session; mocked adapter and executor tests passed. The opt-in Compose publisher worker now polls only supported destinations and maintains a separate presence heartbeat. Signed-in API/UI readiness tests and all five migrations passed at head `20261005_0026`; real worker and remote behavior remain unverified. |
| 2026-10-05 | 1 | **IMPLEMENTED** | A real isolated publisher process starts, advertises readiness and exits cleanly without provider requests (`1 passed`). Migration `20261005_0027` records the exact reviewed identity and submitting operator. Signed-in API tests exercise staged MP4 preview, CSRF and stale-review rejection, durable private YouTube queueing and duplicate rejection (`1 passed`); Studio exposes exact video/metadata review, truthful submit and activity refresh. Instagram, signed-in browser interaction, remote receipts and public eligibility remain unverified. |
| 2026-10-05 | 1 | **IMPLEMENTED** | Stop condition: the full migration file at head `20261005_0027` timed out at 110 seconds after two tests when run concurrently with another Compose test. The fresh migration test passed separately, but the complete upgrade path requires an isolated rerun. No remote upload was attempted. |
| 2026-10-05 | 1 | **IMPLEMENTED** | The full five-test migration file passed alone at head `20261005_0027` in 88.23 seconds. The earlier concurrent timeout did not repeat. Instagram, signed-in browser and controlled remote acceptance remain open. |
| 2026-10-05 | 1 | **IMPLEMENTED** | Migration `20261005_0028` persists operator inspect/resume requests for uncertain YouTube sessions. The worker picks them up under existing delivery/account fences; inspection reads remote status, and continuation is allowed only after inspection proves an incomplete saved session. Signed-in API and fresh migration tests passed (2, 43.17s), queue/executor/isolated worker tests passed (8, 54.00s), and all five migration paths passed alone (90.29s). A later signed-in test confirmed bounded attempt history omits encrypted sessions (1, 22.59s). No live provider request or signed-in browser inspection occurred. |
| 2026-10-05 | 1 | **IMPLEMENTED** | Reconnect recovery releases `auth_required` work only after the exact account is connected: no remote session returns to pending, a recorded remote ID returns to verification, and an unconfirmed saved session remains uncertain. Focused queue tests passed (4, 23.23s) and signed-in API/UI assertions passed (1, 23.62s). No provider request occurred. |
| 2026-10-05 | 1 | **IMPLEMENTED** | The reconnect and signed-in API tests passed together after stale request cleanup (`5 passed`, 45.22s). Instagram OAuth is pending primary-source verification: Meta's Business Login reference currently requires login and Get Started returned HTTP 429 in this environment. Stop under the operator's two-minute stuck-task rule rather than guess its exchange contract. |
| 2026-10-05 | 1 | **IMPLEMENTED** | The current full suite collects all 280 tests; `httpx2` is only a deprecation warning. Bounded auth/account regressions (3), all eight existing dashboard workflow tests, and six worker lease/ownership tests passed. Browser interaction and remote acceptance remain unverified. |
| 2026-10-05 | 1 | **IMPLEMENTED** | The retained 53.417s, 1080×1920 H.264/AAC Shorts artifact passed an isolated publishing-stage smoke. The staged copy matched all 6,898,889 source bytes and SHA-256 `dfa1621209ae854a5457f2bfab1702e9a357876c7b0477dafb45d43373236d93`; the registry reported 53.417s and 1080×1920. This proves local canonical handoff, not remote publication. |
| 2026-10-05 | 1 | **IMPLEMENTED** | Legacy publication/provider regressions passed (13) and core state/approval/media contracts passed (38). A later combined scheduling/analytics group timed out at 110 seconds after 13 passing indicators, so it is not claimed passing; isolate its slow case next session under the operator's stop rule. |
| 2026-10-05 | 1 | **IMPLEMENTED** | The timed-out regression group passed when split: analytics/experiments 7, optimization 5, and topic scheduling 3. The pending scheduling test passed alone in 20.35s; the combined command's cumulative runtime caused the earlier 110-second timeout. Full-suite execution remains open. |
| 2026-10-05 | 1 | **IMPLEMENTED** | Account OAuth/credential/YouTube adapter tests passed (11) and manual publish/asset/presence tests passed (4). A selected legacy publication checkpoint group timed out cumulatively at 110 seconds after five indicators, so it remains unverified as a group and will be split next session. |
| 2026-10-05 | 1 | **IMPLEMENTED** | All 11 selected legacy publication orchestrator cases passed in bounded pairs/singles, covering remote-ID restart, ambiguous outcomes, mutation fencing, cancellation, exact approval, checkpoint versions and source-clip reuse. The earlier combined timeout was cumulative; full-suite and controlled remote acceptance remain open. |
| 2026-10-05 | 1 | **IMPLEMENTED** | Fixed an invalid newline escape in Studio's script-review panel. The signed-in dashboard auth test passed, and all six inline scripts from an isolated assembled page passed Node syntax checks. Browser interaction remains unverified. |
| 2026-10-05 | 1 | **IMPLEMENTED** | A local end-to-end smoke used the retained 53.417s 1080×1920 Shorts MP4, exact-account draft submission, the fenced executor, one fake remote session/upload receipt and one matching read-only inspection. The parent and destination became `published`; SHA-256 remained `dfa1621209ae854a5457f2bfab1702e9a357876c7b0477dafb45d43373236d93`. No live provider call or browser proof occurred. |
| 2026-10-05 | 1 | **IMPLEMENTED** | Meta's accessible Instagram Login collection confirms its distinct scopes, but its Business Login reference is login-gated and its content-publishing reference is inaccessible here. Meta's accessible Reels examples belong to Facebook Login and use a Page token. The Instagram Login OAuth and publishing adapter therefore await the correct provider contract; no endpoint behavior is inferred from the other login route. |
| 2026-10-05 | 1 | **BLOCKED** | Phase 1 cannot reach its Instagram or controlled-remote acceptance with the available provider documentation, application credentials, test accounts and upload authorization. Existing local YouTube and shared delivery work remains implemented and offline-tested; no remote publication is claimed. |
