# TubeForge — publishing and video production plan (current)

Condensed 21 October 2026 from the full 190 KB plan. The **complete former text** (donor reuse map, every stage report, detailed E2E logs, section 5 dashboard/section 9 source notes) is preserved verbatim in [`docs/archive/publishing-design-2026-10-21-full.md`](../docs/archive/publishing-design-2026-10-21-full.md). Agents: do not read the archive unless a detail below is insufficient; then grep it by heading (`rg -n "^#+ " <archive>`) and read only that range.

**Goal.** Produce a good Short (reference-short-v1) from a brief, review it, then deliver reviewed videos through one shared publishing path. Quality first; stream clipping is second last; Next.js migration is last ([fine-grained order](tubeforge-implementation-order.md)). Interactive UI reference: [`tubeforge-dashboard.html`](tubeforge-dashboard.html).

**Record roles** (no competing trackers): this file = contracts, phases, current status/next actions; `AGENTS.md` = durable rules; `AUTONOMOUS_PROGRESS.md` = local append-only evidence log; `readme.md` = operator setup/workflows; `docs/SHORT_FORM_VIDEO_RULEBOOK.md` = creative/video quality; `docs/HANDOFF.md` = Codex/Claude relay and next step. Status labels exactly: NOT STARTED, IMPLEMENTED, VERIFIED, BLOCKED.

> Sections 1, 2, 5, 8 and 9 of the old plan (inputs/donor repos, donor reuse review, dashboard-from-HTML plan, record rules, source notes) now live only in the archive. Numbering below is kept so existing links resolve.

## 3. Shared publishing product contract

An **automation** = source pool + exact destination accounts + recurrence + versioned metadata preset + review mode + completion policy. Manual Compose uses the same path.

| Source | One occurrence |
|---|---|
| Folder backlog (first delivery) | reserve eligible file → analyze/draft metadata → validate/review → deliver to selected accounts → reconcile → archive |
| Video generation | reserve topic → skills → storyboard/media/narration → inspect final → stage canonical asset → shared delivery/archive |
| Stream clipping | reserve unused moment → render/inspect → stage canonical asset → shared delivery/archive |

- **One distinct video per slot, delivered to every selected account.** A failing destination never changes the video or re-uploads to successful destinations; retry only the failed destination. Skipping a required account needs an audit event.
- **Scheduling.** Default `Asia/Kolkata`, slots 13:00 IST (07:30 UTC) and optional 19:00 IST. Store timezone/recurrence plus materialized UTC occurrences; unique `(automation_id, scheduled_utc)`; atomic source claims. "Publish at" mode prepares ahead (default 60 min lead, ready buffer 2); "Start preparing at" mode begins at the slot. Late policy: 30 min grace, else missed and roll to next slot; never burst-publish after downtime. Empty source skips and alerts. YouTube scheduling uses a private never-published video with `status.publishAt` (reject past times locally); Instagram container IDs are stored and their lifetime respected. Pause stops new preparation; Cancel pending is a separate action.
- **Folder catalog.** Approved mounts only (`/media/inbox|work|archive|quarantine`); reject traversal/symlink escapes; hash stable bytes once; oldest-first with stable tie-break; atomic reservation snapshotting destinations/config; immutable content-addressed staging. Archive only after every required destination reaches its confirmed requested state; same-FS atomic move, cross-FS copy→verify→rename→remove with a journal; archive failure = "Published · archive pending" (retry archival only). Edition uniqueness `(canonical asset, account, edition)`; intentional repost = new visible edition.
- **Accounts/metadata.** Exact YouTube channels / Instagram professional accounts via official OAuth; show immutable remote identity; encrypted tokens, server-side exchange, state/PKCE; never collect platform passwords. Instagram Login and Facebook Login contracts stay separate. Metadata from script/transcript/sidecar (not filenames alone); cached by source hash + analyzer version. Precedence: workspace defaults → versioned preset → automation → destination → locked manual fields; freeze effective version per job; edits affect future jobs unless explicitly applied. Private test success ≠ public-scheduling readiness.

## 4. Generation that produces a useful finished video

One pipeline: grounded brief → script/storyboard → real assets and scene narration → preview/repair → final render → canonical staged asset → shared publishing. Reuse existing checkpoints; no extra writers/review rounds/orchestration service; no competing `VideoPlan` (version existing contracts).

- **Scene fields:** stable ID/revision, beat role, narration, source/claim IDs, measured audio duration, visual subject/action + relevance, asset kind/shot/motion, deterministic overlay text, actual asset hash/provenance/provider identity, separate visual/narration freshness, lock and approval identity.
- **Media.** Rights-cleared stock/user uploads, accurate vector/FFmpeg diagrams and tasteful stills are enough; no expensive video provider required. Never substitute decorative placeholders as success; freeze provider/model + request hash with the scene revision; persist submission intent before calling a provider; bound polling/retries/cost; estimated vs observed vs billed cost stay separate; a new paid provider needs a concrete provider/cost/fallback proposal first.
- **Narration/rendering.** Codex CLI or Claude write production scripts (no local-LLM fallback, no attempt resets). Use measured narration pace; scene visuals are placed by actual scene audio; script edits regenerate only affected dependencies. Render text/labels deterministically (not via image generation); charts need real cited data. Do not label approximate timing as forced alignment.
- **Scene editor/approval.** Edit narration/visual direction, upload replacement, regenerate scene, lock, reorder, rebuild preview — all real API actions with optimistic revision checks. Editing invalidates dependent approvals; rebuilds create new immutable artifacts; approved/submitted jobs are never silently edited.
- **Creative acceptance** is separate from technical validation: keep MP4, storyboard sheet, transcript, asset manifest and timing report; inspect images and watch/listen to the full video with timecoded defects. Prove one real production video with a non-fake writer, then a second distinct topic, before any bounded batch. Fixture renders prove engineering only. A model's self-score, a checksum or passing tests never replace artifact inspection.

## 6. Durable architecture and failure handling

- Extend the existing FastAPI/SQLite/Alembic stack; logical roles: catalog/preparation, scheduler, per-account publisher, reconciliation, archival. No Node sidecar, Postgres/Redis migration or new daemon by default; no parallel asset/publish-job database — add only missing fields (presets, source pools, automations/occurrences, reservations/lineage, archive tasks, scene/media revisions).
- Parent progression: planning → preparing → ready → dispatching → verifying → completed → archive pending → archived (map onto existing enums). Each destination records upload/processing/scheduling/visibility/retry/auth/failure independently.
- No universal exactly-once with platforms/paid providers: keep leases, heartbeats, fencing, saved sessions, uniqueness and conservative reconciliation; inspect/resume a saved operation before any new upload; unprovable outcomes block only that destination.
- Bounded backoff/jitter with provider hints; quota/auth/validation errors pause/reconnect rather than loop. Serve only the specific Instagram staging asset over approved HTTPS for the fetch lifetime. Readiness is scoped and evidence-based (stale/skipped/simulated checks are not verified); missed/empty slots and auth problems raise in-app alerts.

## 7. Delivery sequence and acceptance

One phase at a time; report acceptance before the next. Split local engineering, creative artifact and external publication gates. Lack of live credentials never blocks independent local work, but blocks claiming remote delivery.

| Phase | Outcome | Required evidence |
|---|---|---|
| 0 Reconcile current work | accurate minimal delta | paths/SHAs/changed files, status, next acceptance test |
| 1 Local-video Compose | select/upload media, prepare exact account deliveries | staged hash, signed-in review flow, publishing/auth tests, account/metadata/visibility snapshots |
| 2 Folder backlog autopilot (first operational target) | daily 13:00 IST selection, dedup, safe archival | competing claims, restart mid-upload, partial retry, missed slot, rename dedup, archive-copy failure/recovery |
| 3 Profiles and presets | shared settings, per-account/manual locks | two accounts, effective settings, future-only preset update |
| 4A Storyboard and relevant assets | skills drive a compact plan and real scene assets | approved non-fake script, grounding, contact sheet, rights evidence, measured audio |
| 4B One finished video and scene repair | good portrait video enters canonical library | full MP4 inspection vs §4, one-scene edit/rebuild/reapproval, second topic, generation→delivery bridge |
| 5 Clipping source | self-contained unused moment enters the same engine | source ID/time range, semantic review, no-repeat reservation |
| 6 Bounded batch and learning | small resumable batches, measured feedback | restart reuses work; limits/cancellation; real timestamps/retention data |

Enabling live delivery for a destination requires that destination's real acceptance. Carry-over check for Phase 4: scheduler emits `prompt_version="topic-queue-v1"` while content prompts use `m6-content-*`; align if not already fixed.

## 10. Bounded AI planning and repeatable local production — approved direction

AI is the bounded "brain": strict JSON scripts/scene plans with source isolation; all pixels, audio and encoding are local. Key approved rules (full text in archive §10):
- **Source isolation:** brief/source text is data, never instructions; role-spoofing text is rejected before reserving a provider attempt. Research (`ResearchSourcesV1`) runs once per exact brief, separately from narration, with hashed public primary-source snapshots.
- **AI budgets:** two script attempts per brief; independent fresh-context claim reviewer; exhausted budgets stop and require an operator decision; never silently reset.
- **Local media:** Kokoro (primary)/Piper (recorded fallback) TTS, word-anchored reveal order, one-line captions, two-pass loudness mastering, partial rebuilds, runtime compatibility manifest, retention protecting approved/in-flight artifacts.
- **Performance targets are measured, not enforced.**

### Execution stages (13 October 2026) — status snapshot

| Stage | Status | Note |
|---|---|---|
| 1.1 Untrusted inputs | VERIFIED (defined boundary) | adversarial prompt-builder tests |
| 1.2 Records/compatibility inventory | VERIFIED | old status preserved byte-for-byte; inventory of 21 jobs/364 artifacts |
| 1.3 Retention/measurement baseline | VERIFIED (read-only baseline) | no deletion performed |
| 2.1 Captured packages + scene contracts | VERIFIED | two topics; 59 scene/asset + 42 orchestrator tests |
| 2.2 Local media production (A, B1–B3, C1, C2) | VERIFIED per sub-stage | renderer, two captured full videos, narration mix, rights-backed music |
| 2.2 C3 caption-timing acceptance | **FAILED / open** | independent audit p95 765 ms, max 1,115 ms vs 150/300 ms; opt-in `whisper-base-en-dtw-v1` aligner stays disabled |
| 2.3, 3.1–3.3, 4.1–4.2, 5.1 | no acceptance report recorded | treat as NOT STARTED/partially IMPLEMENTED; confirm in archive before relying |

E2E phases (19 Oct): E2E-1 creative→render contract **IMPLEMENTED**; E2E-2 local Piper speech service **IMPLEMENTED**; E2E-3 exact approved final **BLOCKED** on signed-in Studio retry of job `studio-review-cbec5a9ff3264c94a8e3` (stale-worker packet error; checkpoint intact); E2E-4 repeatability **NOT STARTED**. E2E-3a Studio request fidelity and creative-check presentation **VERIFIED**; approved-checkpoint recovery **VERIFIED**; caption-timeline repair (`m14-preserved-caption-timeline-v1`) **VERIFIED**.

## 11. Current release status and next action

Updated 21 October 2026. Evidence detail: local `AUTONOMOUS_PROGRESS.md` (current + `_N` archives), `docs/HANDOFF.md`, and the archive of this plan.

### Reference-codebase quality review (23 October 2026)

Documentation review **VERIFIED** (documentation scope only): [five local codebases compared with TubeForge](../docs/REVIEW_2026-10-23_REFERENCE_CODEBASES.md); five local revisions recorded, 38 file/line links checked, report whitespace and `git diff --check` passed. No runtime or creative milestone changes. Owner reuse authorization is recorded. Adoption experiments are **NOT STARTED**: first establish a Kokoro comparison/diagnostics baseline, then pronunciation mappings, speech-grouped synthesis, semantic footage ranking and real retention curves tied to scenes. Blocker for the review: none. Next action: use the report to scope a future implementation task with real-artifact acceptance; implementation was explicitly excluded from this request. Existing release blockers and next five release actions below are unchanged.

### Video/audio quality implementation branch (23 October 2026)

Branch `codex/video-quality-implementation` (isolated worktree); [four sequential quality milestones](../docs/VIDEO_QUALITY_MILESTONES.md). Milestone 1 **IMPLEMENTED**: [acceptance evidence](../docs/VIDEO_QUALITY_M1_EVIDENCE.md) records 11 focused tests, fresh Kokoro/Whisper-to-final render, 1080×1920 full decode, −14.3 LUFS/−2.52 dBTP, artifact-bound audio health reports and inspected contact sheet. Full listening and browser JavaScript interaction are unverified, so it is not **VERIFIED**. Milestones 2–4 **NOT STARTED**. The attached 16:9 PHP brief remains unreviewed, not an approved script. Acceptance limits: operator listening feedback is pending; the worker browser failed after two launch attempts, with normal signed-in Studio inspection recommended over repairing that container. Next action: listen to the complete video and verify the Generation record in a working signed-in browser before starting milestone 2. Publishing and retention analytics are excluded from this quality run.

### Reference-renderer integration — active priority

**22 Oct update (Claude):** phases 2–3 are now **IMPLEMENTED** for the preview path: dashboard `reference-short` preset → shared `rendering/shorts` (Kokoro, Whisper alignment, motion, icons, QA). Evidence: job `41e2ee9a…` 720×1280, 34 s, −14.3 LUFS. Phase 4 (final 1080×1920 + operator audiovisual acceptance) remains open. Details and next steps: `docs/HANDOFF.md`.

**Homeserver operator runbook: IMPLEMENTED.** `docs/HOMESERVER_OPERATOR_GUIDE.md` now records the supported Compose startup, loopback health check, Codex/Claude runner checks, Windows `homeserver` SSH tunnel, logs, restart, and first-admin workflow. Live availability remains determined by the documented `/healthz` check; this documentation change does not alter the pipeline release state.

Supersedes the earlier landscape test per [`docs/CLAUDE_PIPELINE_REVIEW.md`](../docs/CLAUDE_PIPELINE_REVIEW.md). Overall **IMPLEMENTED**. Target (reference-short-v1): 1080×1920/30 fps final, 720×1280 draft, 25–45 s, 6–8 scenes, 8–15 spoken words each, 0.3–0.4 s speech tails, immediate first-frame hook, fixed templates, visible sources, one-line 1–3-word 84 px captions, music/SFX, closing follow CTA, −15..−13 LUFS and ≤ −1.5 dBTP encoded. Native Python, Kokoro INT8 → Piper fallback, concurrency one.

| Phase | Status | Acceptance / evidence |
|---|---|---|
| 1 Shared topic-independent layout library (`rendering/shorts/`) | **VERIFIED** | 5 tests; seven-template contact sheet `data/artifacts/reference-renderer-layout/contact-sheet.png` + `layout-qa.json`; synthetic fixture proves geometry only |
| 2 Content contracts, local TTS/alignment/music, event-driven encode, mastering, post-encode QA | **IMPLEMENTED** | encoder test 1 passed (19.8 s); 7 real Kokoro scenes, 34.0 s, Whisper DTW alignment; m6-content-v8 profile + `ReferenceContract` bound to approved hashes (30 tests). **1080×1920 final blocked** by the host swap-growth gate (4 GB host); options: less-loaded runtime (recommended) or operator-approved memory-policy change |
| 3 Dashboard/native leased worker use the same adapter | **NOT STARTED** (orchestrator branch to `pipeline/reference_short.py` exists, **IMPLEMENTED**) | signed-in Studio creates a Rust/AI job with new defaults; no test-only render path; truthful artifact/error UI |
| 4 Render and inspect the real Rust/AI video from dashboard intake | **NOT STARTED** | final MP4, safe-rail contact sheet, ffprobe, loudness, layout QA, first/last frame, full audiovisual review |

No completion claim before phase 4 passes. Claude is available as an alternative script owner (`script_owner=claude`, user-level runner `scripts/run_claude_runner.sh`) — **IMPLEMENTED**; live script generation succeeded once.

### Rust dashboard-backend end-to-end test (19–20 October) — creative acceptance FAILED

Job `584fd95de80047649d959af2d9075363` (16:9, 60 s, operator-approved script `6b7235be…cc0fe` for local rendering only). Real preview (854×480, 77.17 s, SHA-256 `af4508016eb4…cb127aa`) failed review: generic box diagrams, weak hook (41/100 WEAK), captions over diagrams, −17.59 LUFS / 0.01 dBTP. A corrective preview failed encoded-audio verification (−14.89 LUFS / −0.18 dBTP); atomic promotion kept the old preview; no final exists. Operator rejected the video. This path is superseded by the reference renderer; do not cite it as acceptance evidence.

### Repairs delivered along the way (all **IMPLEMENTED**; deployment verified where noted)

- Scene-schema repair (13 legal alternatives; no free-text layouts) — deployed and preflight-verified; 96 focused tests.
- Immutable request binding in application code (request no longer echoed by the model) — deployed, live generation verified; wheel `artifacts/wheels/request-binding/tubeforge-0.1.0-py3-none-any.whl` (SHA-256 `66f248342878…fc691e93`).
- Automatic brief research before narration (bounded one-shot Codex web research + hashed source packet; sources < 200 readable chars excluded) — deployed; one live research call succeeded; model-generated research is context, not evidence.
- Native 16:9 card/teaching composition with word timing; guarded "Retry approved media stages" recovery before any preview exists.
- Full worktree suite earlier: 429 passed, 18 skipped. Always re-run after changes.

### Multi-account creation and Creator Studio redesign (merged from `codex/multi-account-setup`, 22 October)

Local YouTube, Instagram, Snapchat and X/Twitter account profiles (name, category, default description) are **IMPLEMENTED** and, for the creation subset, **VERIFIED** on the branch (22 affected API/publishing tests, migration head, real local H.264 staged-draft smoke). A generation snapshots exact destination, account, category and description choices (`video_destination_intents`, migration `20261022_0029`) without touching writer input or opening a live connection; per-schedule destinations and account-owned topic queues (migration `20261022_0030`, topics and schedules carry `account_id`; unassigned legacy rows stay isolated and visible) are **IMPLEMENTED**. The reference-inspired Studio shell, account-first Scheduling tab and Generations view are **IMPLEMENTED**; operator desktop/390 px visual review is the open item. New Codex CLI runs save exact argv provenance. No online upload or platform connection was added. Details: `docs/planning/multi-account-setup.md`, `docs/planning/studio-ui-redesign.md`.

### Open blockers / decisions

1. 1080×1920 reference final blocked by host memory gate (see phase 2).
2. E2E-3: signed-in Studio retry for `studio-review-cbec5a9ff3264c94a8e3` (HTTP 401 from the unauthenticated runner).
3. Caption timing gate: independent human word-edge reference and a successful full-script aligner run are still missing; aligner stays disabled.
4. Canonical skill changes (`yt-script`, `om-short-production`) need host-wheel deployment and hash verification before host use; any host install needs operator sudo.
5. Operator decisions pending: stock media key (not needed for icon/procedural visuals); automatic Codex⇄Claude fallback; commit/branch policy for the large uncommitted tree; stock-vs-local-diagram choice for the stuck Git asset job `2656a7f6…`.

### Next five actions

1. Re-run the 1080×1920 reference render on a less loaded runtime (or obtain the operator's memory-policy decision) and promote the first final.
2. Phase 3: wire dashboard creation and the leased worker to `pipeline/reference_short.py`/`rendering/shorts`; keep approvals, cancellation, fencing and atomic output; add API/UI tests.
3. Phase 4: create the Rust/AI job from signed-in Studio, then inspect the real final (frames, ffprobe, loudness, QA, full watch/listen) against `docs/SHORT_FORM_VIDEO_RULEBOOK.md`.
4. Resolve caption timing with a human word-edge reference; verify repeatability (tutorial, explainer, comparison).
5. Build/install the host wheel for changed skills, verify hashes, then resume the publishing roadmap (phases 1–2). Publication remains out of scope until then.
