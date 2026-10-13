# TubeForge Status

Last reviewed: 2026-10-13
Release target: R1 — Reliable Local Studio

## Approved production direction — documentation only

The operator approved the [bounded-AI local-production plan](../design_doc/tubeforge-publishing-design.md#10-bounded-ai-planning-and-repeatable-local-production--approved-direction) on 13 October 2026. Its five implementation phases are **NOT STARTED**. The existing Docker benchmark is local evidence, not proof that the production worker implements the new plan. The first phase is documentation consolidation, source/prompt isolation, runtime/schema inventory, retention design and measurement definitions. This entry records direction; it does not revise the historical task 1–7 acceptance states or authorize publication.

**Next action:** plan Phase 1 implementation against the existing contracts and acceptance evidence, then implement and verify that phase before proceeding to reusable local production. Keep the 15-minute render, 30-minute local-production and 800 MiB cgroup targets visible but non-blocking until the operator enables enforcement.

`docs/STATUS.md` is the authoritative current-status record. Historical work
evidence belongs in `AUTONOMOUS_PROGRESS.md`; historical overnight planning is
retained under `docs/overnight/`.

## Forward implementation plan

Terminal visual quality phase 1 is **VERIFIED in the homeserver checkout**: production local-art
terminal scenes now render the approved command and result as a legible console,
and the Shorts final H.264 profile explicitly uses CRF 18 with CRF 14 temporary
clips in the memory-bounded path. The homeserver one-off Compose run passed 67
relevant tests. A three-second 1080×1920 H.264/AAC bounded render passed; the
encoded frame and full decode were inspected. See [the phase plan](planning/terminal-visual-quality-plan.md).
The running production worker has not been restarted and may retain its loaded
code/configuration until its next restart. Animated typing/reveal synced to
narration remains phase 2; this phase alone does not establish parity with
Claude's complete video.

Current priority is the user-requested [short-form rulebook and Docker music/CTA revision](../design_doc/docker-short-benchmark.md). The [topic-independent rulebook](SHORT_FORM_VIDEO_RULEBOOK.md) and local renderer revision are **VERIFIED** for their documented technical and visual gates. The operator requested a spoken “follow for more” close after reviewing the music version; a field-level review preserved the original Codex-written package, factual claims and first five sections while replacing the final ask in a separate local revision. The [final 42.869s MP4](../artifacts/benchmark/docker-short/final/docker-short.mp4) is 1080×1920/30fps H.264/AAC, −14.73 LUFS and −1.37 dBTP, SHA-256 `de94b5e2841755c91de41c9544e80dfef8149a85cbb4c41fe0d0fe125fa6dfce`. Music measures −18.72 dB relative to speech in voiced windows. Exact revision/stem/output hashes, full decode, 69 audio-aligned caption chunks, all-frame text bounds, encoded safe-zone and CTA frames, and black/silence checks passed. AAC audio extracted from the final MP4 was transcribed as “Follow for more practical Docker lessons.” at 40.3–42.16s. The user reported the reused preview path did not say the line, so an identical-byte, uniquely named preview and extracted ending audio were supplied. **The operator confirmed the line is audible** in that fresh preview; the requested music and closing-line revision is VERIFIED. This environment cannot make its own subjective listening comparison. The [reference review](DOCKER_SHORT_BENCHMARK_REVIEW.md) separates measurements from judgment. This local benchmark is not integrated into the production worker; publishing tasks 6–7 remain separate.

Publishing task 6 remains **IMPLEMENTED**, with two final focused tests passing (22.82s) and the production API rejecting a stale parent script identity with HTTP 409; its exact child preview/final acceptance remains open. Task 7 is **NOT STARTED**. The temporary tasks 5–7 reviewer and sessions have been removed and its token verified invalid. A one-off Compose migration dependency reported missing revision `20261005_0028`; no database history was modified. The benchmark uses isolated local assets and does not require this migration.

The [consolidated publishing/dashboard plan](../design_doc/tubeforge-publishing-design.md) defines ordered tasks and acceptance checks. Documentation consolidation is verified; it does not change the implementation or verification states below. Reconcile existing evidence before selecting its next task.

## Release gates

| Gate | Status | Evidence | Blocker / next action |
| --- | --- | --- | --- |
| Automated regression suite | NEEDS REVALIDATION | The current unfiltered suite collected all 280 tests in the Compose web container on 2026-10-05 (`--collect-only -q`, 4.32s). `httpx2` is now a deprecation warning, not a collection error. Completed bounded groups: publishing account/auth 3, dashboard workflow 8, worker leases/ownership 6, legacy publication/provider 13, core contracts 38, analytics/experiments 7, optimization 5, topic scheduling 3, account OAuth/credential/YouTube adapter 11, manual publishing/asset/presence 4, and selected publication orchestrator 11 passed. The earlier orchestrator group timeout was cumulative; all selected cases passed when split. | Continue remaining bounded regressions; the local real-media publishing smoke has passed separately. |
| Database migrations | PASS (FOCUSED) | All five migration tests, including fresh SQLite and legacy upgrade paths, passed alone in the Compose web container against head `20261005_0028` (`5 passed, 90.29s`). | Recheck after further migrations; full regression remains open. |
| Restricted host Codex runner | VERIFIED | Operator installed the final compatibility wheel; actual host skill preflight passes. Original verification exhausted two attempts (restart interruption, then rejected closing CTA). Operator-approved revised Codex brief produced reviewed content with actual scoring provenance. | Generation and signed-in review passed. Final render remains BLOCKED by the operator decision; exhausted counters remain unchanged. |
| Local FFmpeg/Piper smoke | PASS | Dedicated Shorts smoke: `1 passed, 2 deselected` in 284.99s on 2026-09-27. Retained output is 53.417s, 1080x1920, 30 fps H.264/AAC; its gate verified 168 locally aligned words and a 2.871s maximum visual hold. The earlier widescreen stock smoke also remains retained. | Use a non-fake production writer and complete signed-in browser acceptance. |
| Local Kokoro voice smoke | PASS | `af_bella` generated a valid 24 kHz local WAV (3.776 seconds) using the INT8 ONNX model on 2026-09-13. | Run a selected-voice job smoke after rebuilding the durable Compose image. |
| Docker/Compose runtime | READY FOR REVIEW | Recreated migration, web, worker, and scheduler services on 2026-09-13 with local-UID bind-mount ownership. The scheduler now also mounts the configured local models; all services are running and `GET http://127.0.0.1:62065/healthz` returned `{"status":"ok","database":"ok"}`. | Sign in and exercise the Visuals selector with a stock-selected job. |
| Production dashboard auth | IN PROGRESS | Auth implementation, script viewing, and safe artifact cleanup have focused API/dashboard coverage. The current signed-in auth test passed, and all six scripts in an isolated assembled Studio page passed Node syntax checks after repairing a review-panel newline. | Run a browser workflow check after sign-in. |
| Publishing safety | IN PROGRESS | Approval gates, private/dry-run defaults, fenced delivery attempts, and read-only uncertain-outcome reconciliation passed focused offline tests. A real Shorts file passed the local manual publishing path with a fake provider. | Verify Instagram Login against its own provider contract, then inspect signed-in and controlled remote behavior with operator credentials and authorization. |

## Active milestone


The updated yt-script automation request is the current integration scope.

| Automation phase | Status | Evidence | Blocker / next action |
| --- | --- | --- | --- |
| 1. Canonical skill and references | **VERIFIED** | Only `.agents/skills/yt-script` changed for this request. SKILL.md references automation.md; hook tools preserved/executed. Wheel resources byte-match this folder. | Keep downloaded copies untouched. |
| 2. Explicit invocation and strict output handling | **VERIFIED** | Final provider/skill/automation batch: 63 passed. Existing workflow batch: 84 passed. Compatibility: 26 passed plus one updated assertion rerun passed. All 85 Python files match the final wheel; actual host preflight matches prompt SHA256 and seven resource hashes. Signed-in API and exact revision checks pass. | Inspect real generated content and signed-in browser/media in Phase 3. |
| 3. Production scripts and approved local preview | **BLOCKED** | Three real scripts and invocation hashes verified. Exact revised tutorial preview: 52.117s, 540×960; narration-only TTS and captions match. Signed-in browser passed. | Visual teaching standard fails with existing abstract renderer; auditory quality unverified. No publication. |

YouTube content skills integration follows `docs/YOUTUBE_SKILLS_PLAN.md`.
Publishing Phase 1 remains BLOCKED; the existing Shorts quality gates are not
upgraded by this integration.

| Integration phase | Status | Evidence | Blocker / next action |
| --- | --- | --- | --- |
| 1. Canonical skills and durable instructions | **VERIFIED** | Eleven canonical `.agents/skills/` installations inspected; selected resources and tools reviewed; actual hook/title CLI reports and wheel inventory checked. AGENTS/README and application-compatible skill instructions updated. | Retain one canonical source installation. |
| 2. Application writing and review integration | **VERIFIED** | v5 embeds yt-script/package/seo in host prompts; real local scoring selects hooks and checks titles; channel voice snapshots, scheduler propagation, no-model hash preflight and signed-in API review have focused coverage. The final focused regression batch passed 63 tests in 318.86s. The deployed host wheel passes installed-resource preflight, and all six rendered Studio scripts pass Node syntax checks. Later worker/render fixes are loaded through the source mounts. | Actual host invocation and signed-in Chromium review passed; final provider checks: 39 passed. Existing API workflow: 8 passed. Operator listening check passed. Final 1080×1920 render is BLOCKED after OOM; the retained 540×960 preview passed visual/metadata checks. |
| 3. Real Shorts acceptance | **BLOCKED** | Operator deployment and actual host no-model resource handshake passed. Original brief exhausted its two attempts; the operator approved a revised brief with an explicit closing CTA. A new 40.663s 540×960 preview passed validation/visual inspection; operator confirmed clear/complete narration. Full-resolution export failed with a recorded Docker OOM event; job is failed_exhausted. | Operator chose to leave final rendering BLOCKED. Preserve the preview and exhausted job/counters; a future operator-approved memory or renderer change needs a new controlled job. |

Local evidence is retained under `artifacts/smoke/skills-integration/`; the
wheel is `artifacts/wheels/tubeforge-0.1.0-py3-none-any.whl`. Both paths are
ignored. Synthetic scoring fixtures are labelled explicitly and are not
production script, rendering, or browser acceptance.

## Visual production tasks 1–3 (12 October 2026)

| Task | Status | Evidence | Blocker / next action |
| --- | --- | --- | --- |
| 1. Inventory generation and donor visual code | **VERIFIED** | [Focused inventory](VIDEO_VISUAL_INVENTORY.md) maps current script/plan, routing, renderer and both donor files with checked local commits. The [second-pass reuse review](../design_doc/tubeforge-publishing-design.md#second-pass-reuse-review--12-october-2026) compares additional donor utilities with current TubeForge contracts. Operator confirmed written permission and waived license review. | Reuse the recorded source-level candidates at their planned tasks; do not add a second pipeline. |
| 2. Narration-linked scene plan | **VERIFIED** | A fresh production Codex invocation for job `42899f0c102248e3a64af4baaa41429e` used the canonical skill resources (live preflight matched prompt and seven resource hashes), then returned six source-grounded narration sections and six explicit scene subjects, purposes, compositions and element lists. All five factual claims map to supplied official Docker sources. One immutable script revision (`d506a74654f8…`) was reviewed and approved by identity; the worker used it for TTS and preview. Focused Compose tests passed (16 checks). | Keep the accepted scene fields and approved artifact identity through later scene repair. |
| 3. Relevant visuals and contact sheets | **VERIFIED** | Production job `0394bd453cd24dc4adbeee5ac5c1fee4` reused the source-grounded Codex package from cache, saved a shortened six-section revision through the existing revision handler, and rendered only after exact checksum `68e711a27e12…` was approved. The running v9 worker saved a complete [six-scene contact sheet](../data/artifacts/0394bd453cd24dc4adbeee5ac5c1fee4/storyboard/contact-sheet-001.png), accepted-asset/storyboard/license manifests and a 43.016-second local preview. Every scene was inspected against narration: the image branches to two named containers, comparison and exact commands are legible, `docker ps` shows distinct source-supported rows, and removal/state is explained. All six CC0 local assets have distinct hashes that match files; no fallback or omitted scene. The preview manifest names the approved content hash and six asset hashes. Affected Compose suite: 58 passed, 3 environment-dependent smoke tests skipped in 11m39s. | Task 3 acceptance passed. Its retained preview is unapproved; task 4 used a fresh approved job for the final. No publication. |
| 4. Render and inspect one finished Short | **VERIFIED** | [Production job `9df50ade…`](TASK4_VIDEO_REVIEW.md) used the exact approved script revision and corrected preview identity; its registered 43.033s 1080×1920 H.264/AAC final binds the same content, audio, captions and six assets. A 2-second-interval visual sheet, full decode, black/silence checks and safe-width caption audit passed. The operator watched/listened to the full final and reported good voice, pacing, captions and visuals, with no defect. The temporary signed-in review account/session was removed and its token now returns HTTP 401. Current-worktree Compose suite: 57 passed in 746.51s. | Task 4 acceptance passed. Dashboard state is `publication_approval_required`; no publication approval or upload. Continue with task 5 scene replacement. |
| 5. Replace or regenerate one scene | **VERIFIED** | [Real child draft and preview](TASK5_SCENE_REVIEW.md) changed only scene 3, reused five of six accepted asset hashes and 11 of 12 phrase-audio hashes, and rebuilt narration/timing/captions into a 43.179s preview. Its contact sheet, two-second timeline and full-size scene frame were inspected; 101 captions fit the portrait gate. The signed-in production Studio API created separate child `8481109b…` with the same reviewed content SHA while the parent script and final stayed unchanged; its audit event and authenticated script/artifact reads passed. Current-worktree regression: 77 passed; final focused rerun: 2 passed. | Task 5 accepted. The signed-in child awaits its own exact script/preview approval for task 6; no publication. |

## Publishing milestone tracker

| Phase | Status | Evidence | Blocker / next action |
| --- | --- | --- | --- |
| 0. Inventory and readiness | **VERIFIED** | `docs/planning/publishing-delivery-plan.md` inventories actual scheduler, database, publisher, dispatch, account, auth, and Studio contracts and records the migration order and account-readiness checklist. The attached HTML was inspected as a mockup. Baseline: 13 focused tests passed in the Compose web container; tests are baked into that image. | Start local Phase 1 implementation. |
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

Updated yt-script automation request (2026-10-11): invocation/output handling
and actual production generation are **VERIFIED**. Tutorial, explainer and
comparison were generated with explicit updated skill/brief evidence. The exact
revised tutorial reached local `preview_ready`; signed-in desktop/mobile review,
revision-prompt copying and preview playback passed. Creative visual acceptance
is **BLOCKED**: existing abstract graphics do not demonstrate the tutorial's
terminal/staging actions. Audio has not been verified by listening. No publishing.
Canonical `.agents/skills/yt-script` and deployed wheel hashes match. See
`YT_SCRIPT_AUTOMATION_REPORT.md`. Repository hygiene is **VERIFIED**: 44 generated
files untracked locally, all copies retained, skills staged/eligible, docs organized.

The skills host deployment and revised Codex generation are verified, as is
actual signed-in Chromium script review at desktop/mobile widths. Original
source-packet counters remain exhausted. The first preview encountered an
OOM kill under the 1GiB worker budget. Two targeted repairs bound filters,
encoder and every input decoder; 12 renderer checks pass and checkpointed
preview reached `preview_ready` with readable captions. The final 1080×1920
export failed with a Docker OOM event; the job is `failed_exhausted` after
three worker attempts. The operator confirmed clear/complete narration and
explicitly chose to leave final rendering BLOCKED. No further render attempt
or memory change is authorized in this session.


1. Controlled live publication needs operator-provided Google and Meta
   applications, approved permissions, exact test accounts and media, and
   explicit authorization for each test. Current configuration contains no
   application credentials. Meta's Business Login reference currently returns
   a login gate or HTTP 429 in this environment. The accessible Meta Postman
   Reels examples use Facebook Login and a Page token, a different integration
   from the planned Instagram Login path; its OAuth and publishing contracts
   still need primary-source verification before implementation.
   See `docs/planning/publishing-delivery-plan.md` for the readiness checklist.
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

Local deployment: existing migrations applied after online backup; schema
20261005_0028, health/database and login HTTP 200 pass. No publisher started.

## Next five tasks

1. Plan Phase 1 against the existing architecture and evidence; retain historical records during consolidation.
2. Define and test source isolation before reusable production work; treat source text as untrusted data.
3. Inventory in-flight schemas, renderer/runtime dependencies and compatibility requirements.
4. Define diagnostic measurement methods and protected-evidence retention before enabling cleanup.
5. After Phase 1 acceptance, prepare manually approved fixtures for Phase 2. Resume existing publishing tasks 6–9 separately after this production priority; their evidence and blockers above remain unchanged.
