# TubeForge Status

Last reviewed: 2026-10-05
Release target: R1 — Reliable Local Studio

`docs/STATUS.md` is the authoritative current-status record. Historical work
evidence belongs in `AUTONOMOUS_PROGRESS.md`; historical overnight planning is
retained under `docs/overnight/`.

## Release gates

| Gate | Status | Evidence | Blocker / next action |
| --- | --- | --- | --- |
| Automated regression suite | NEEDS REVALIDATION | The current unfiltered suite collected all 280 tests in the Compose web container on 2026-10-05 (`--collect-only -q`, 4.32s). `httpx2` is now a deprecation warning, not a collection error. Completed bounded groups: publishing account/auth 3, dashboard workflow 8, worker leases/ownership 6, legacy publication/provider 13, core contracts 38, analytics/experiments 7, optimization 5, topic scheduling 3, account OAuth/credential/YouTube adapter 11, manual publishing/asset/presence 4, and selected publication orchestrator 11 passed. The earlier orchestrator group timeout was cumulative; all selected cases passed when split. | Continue remaining bounded regressions; the local real-media publishing smoke has passed separately. |
| Database migrations | PASS (FOCUSED) | All five migration tests, including fresh SQLite and legacy upgrade paths, passed alone in the Compose web container against head `20261005_0028` (`5 passed, 90.29s`). | Recheck after further migrations; full regression remains open. |
| Restricted host Codex runner | BLOCKED | The Studio prompt-version fix is deployed. A subsequent real response had 62 narration words for a 60-second brief, below the 90–240 requirement. The checkout now gives Codex explicit word budgets shared with validation and corrects retry reservation state; four focused tests passed in 16.82s. | Operator must reinstall the root-owned host wheel and restart its service to activate the prompt correction (commands in README). Then validate a bounded real script; prior exhausted counters remain unchanged. |
| Local FFmpeg/Piper smoke | PASS | Dedicated Shorts smoke: `1 passed, 2 deselected` in 284.99s on 2026-09-27. Retained output is 53.417s, 1080x1920, 30 fps H.264/AAC; its gate verified 168 locally aligned words and a 2.871s maximum visual hold. The earlier widescreen stock smoke also remains retained. | Use a non-fake production writer and complete signed-in browser acceptance. |
| Local Kokoro voice smoke | PASS | `af_bella` generated a valid 24 kHz local WAV (3.776 seconds) using the INT8 ONNX model on 2026-09-13. | Run a selected-voice job smoke after rebuilding the durable Compose image. |
| Docker/Compose runtime | READY FOR REVIEW | Recreated migration, web, worker, and scheduler services on 2026-09-13 with local-UID bind-mount ownership. The scheduler now also mounts the configured local models; all services are running and `GET http://127.0.0.1:62065/healthz` returned `{"status":"ok","database":"ok"}`. | Sign in and exercise the Visuals selector with a stock-selected job. |
| Production dashboard auth | IN PROGRESS | Auth implementation, script viewing, and safe artifact cleanup have focused API/dashboard coverage. The current signed-in auth test passed, and all six scripts in an isolated assembled Studio page passed Node syntax checks after repairing a review-panel newline. | Run a browser workflow check after sign-in. |
| Publishing safety | IN PROGRESS | Approval gates, private/dry-run defaults, fenced delivery attempts, and read-only uncertain-outcome reconciliation passed focused offline tests. A real Shorts file passed the local manual publishing path with a fake provider. | Verify Instagram Login against its own provider contract, then inspect signed-in and controlled remote behavior with operator credentials and authorization. |

## Active milestone

Publishing pipeline Phase 1 follows the repository inventory in `plan.md`.
The existing Shorts quality work remains open under `docs/SHORTS_WORKFLOW.md`;
its state has not been upgraded by the publishing plan.

## Publishing milestone tracker

| Phase | Status | Evidence | Blocker / next action |
| --- | --- | --- | --- |
| 0. Inventory and readiness | **VERIFIED** | `plan.md` inventories actual scheduler, database, publisher, dispatch, account, auth, and Studio contracts and records the migration order and account-readiness checklist. The attached HTML was inspected as a mockup. Baseline: 13 focused tests passed in the Compose web container; tests are baked into that image. | Start local Phase 1 implementation. |
| 1. Connect and manual publish | **BLOCKED** | Google OAuth, fenced queue, credential refresh, saved-session reconciliation and same-session resume have focused offline coverage. An isolated publisher process, signed-in exact-review private YouTube submit, durable operator inspect/resume requests, reconnect recovery and Studio audit passed focused tests. The retained 53.417s 1080×1920 Shorts MP4 staged with identical bytes, then a local fake-provider run reached one `published` parent/destination after exactly one upload and one read-only inspection. No live upload or browser interaction has been verified. | Obtain an accessible Instagram Login OAuth, publishing and media contract, then add its adapter; inspect the signed-in browser and controlled remote posts. Operator applications, credentials, exact test accounts/media and upload authorization are required for live acceptance. |
| 2. Backlog autopilot | **NOT STARTED** | No canonical folder catalog, publishing automation, or safe archive worker. | Begin after Phase 1 acceptance. |
| 3. Presets and account control | **NOT STARTED** | No versioned publishing preset or field-lock workflow. | Begin after Phase 2 acceptance. |
| 4. Generation source | **NOT STARTED** | Existing generation does not feed the shared multi-destination publishing path. | Begin after Phase 3 acceptance and approved script-provider evidence. |
| 5. Clipping source | **NOT STARTED** | Existing operator-supplied clipping does not reserve and deliver stream moments. | Begin after Phase 4 acceptance. |
| 6. Expansion contract | **NOT STARTED** | Provider-neutral interfaces exist but lack this pipeline's capability/reconciliation contract. | Begin after Phase 5 acceptance. |

## Capability status

| Capability | Status | Remaining work |
| --- | --- | --- |
| Dedicated Shorts rendering | DONE | The Studio preset enforces 30–55s; previews are portrait and finals are 1080x1920/30 fps. Local waveform-based word timing, highlighted safe-area ASS captions, <=3s visual holds, and final-media gates passed real Piper/FFmpeg acceptance. Evidence: `artifacts/smoke/shorts_piper_1080x1920_smoke.{mp4,wav,json}` and the contact sheet. |
| Local generation/rendering | READY FOR REVIEW | Per-job visual-source selection routes generated scene art or rights-safe Wikimedia stock through the same asset manifest. If Commons is unavailable or strict filtering yields no permissible result, the hybrid provider explicitly falls back to local generated CC0 art and records both requests and the reason in that manifest. Focused tests and a stock-selected FFmpeg/Piper smoke passed on 2026-09-13. |
| VideoPlan and visual routing | IN PROGRESS | Move render consumers from legacy `ContentPackage`; implement any required motion-graphics/derivative renderer. |
| Source clipping | NEEDS REVALIDATION | Re-run source acquisition/render smoke and validate deployment behavior. |
| Topic queue and scheduling | IN PROGRESS | Add schedule editing/history and validate concurrent scheduler/recovery behavior. |
| Dashboard and authentication | READY FOR REVIEW | Dashboard now shows creation and activity timestamps in IST, a read-only script view after script approval, safe exact-script editing during review, persistent voice previews, deletion for paused pre-publication jobs, and published-item local artifact cleanup that retains the audit record. `127.0.0.1:62065` is the single documented local dashboard URL. The documented Debian home-server access path keeps that binding private and uses Tailnet HTTPS proxying. | Run full dashboard/browser regression and the Tailnet browser acceptance after the Debian host enables `tailscaled`; split embedded dashboard assets before further UI expansion. |
| YouTube publishing | BLOCKED | Operator OAuth credentials and private upload/reconciliation smoke required. |
| Instagram/Facebook publishing | TODO | Implement official Graph API adapters, then credentialed contract/sandbox tests. |
| Snapchat and other platforms | TODO | Retain manual handoff unless an approved official publishing API is available. |
| Growth/research/monetization | TODO | Source-backed research, fact checks, topic scoring, analytics, revenue attribution, and human-review policy. |

## Current blockers

1. Controlled live publication needs operator-provided Google and Meta
   applications, approved permissions, exact test accounts and media, and
   explicit authorization for each test. Current configuration contains no
   application credentials. Meta's Business Login reference currently returns
   a login gate or HTTP 429 in this environment. The accessible Meta Postman
   Reels examples use Facebook Login and a Page token, a different integration
   from the planned Instagram Login path; its OAuth and publishing contracts
   still need primary-source verification before implementation.
   See `plan.md` for the readiness checklist.
2. Both host-side attempts for the original README-grounded packet failed
   before producing a script; that packet remains exhausted. Both attempts
   for the revised review-gates packet also failed before a script because
   Codex rejected successive schema constraints (`required`, then `format: uri`).
   The compatibility repair was deployed before the new caption-timing test.
   The operator chose a new caption-timing topic and approved one live test.
   That request reached the model but its output failed host validation because
   two fallback visuals exceeded 100 characters. The operator-approved narrow
   local normalizer is deployed and passed installed-wheel/socket checks. Its
   remaining attempt was found exhausted by the runner's durable ledger on
   2026-10-04 before any model call. Do not reset the allowance or reuse the
   packet; a substantively new source packet requires separate approval.
3. The current full suite collects, but execution of all 280 tests has not
   been revalidated after the publishing changes. The local real-media
   publishing smoke passed with an in-process fake provider; remote receipts
   and signed-in browser interaction remain unverified.

## Next five tasks

1. Verify the Instagram Login endpoint and media contract, then implement its
   account-scoped OAuth/adapter, identity, token lifecycle, reconnect behavior,
   container processing and failure recovery.
2. Test the signed-in browser's exact-review, connection, activity and
   reconciliation flows against the running dashboard.
3. Run full API/UI, worker lease and concurrency regressions after Instagram
   integration; inspect a real staged artifact and provider receipts.
4. Obtain explicit test-upload authorization and application access, then
   inspect controlled remote posts on YouTube and Instagram. Keep public
   readiness separate from private test success.
5. After Phase 1 acceptance, start the Phase 2 folder backlog contract.

## Update protocol

- Update this file whenever a milestone state, blocker, release gate, or next
  task changes.
- Every `DONE` item requires a linked test/artifact/command result.
- Append detailed command output and investigation history to
  `AUTONOMOUS_PROGRESS.md`; do not duplicate it here.
