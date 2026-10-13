# TubeForge — publishing and video production implementation plan

Revised 11 October 2026 • Prepared for Udit • Living implementation plan

**Improve generated-video quality first, then connect reviewed videos to the shared publishing path.** Add explicit storyboards, relevant media and scene repair to TubeForge's existing pipeline. Adapt selected donor workflows rather than importing another application or adding another agent framework. The [fine-grained order](tubeforge-implementation-order.md) puts stream clipping second last and Next.js migration last. [Section 10](#10-bounded-ai-planning-and-repeatable-local-production--approved-direction) records the newer approved production direction; it is a plan, not an implemented capability.

This replaces the 4 October publishing proposal. It preserves folder backlog, manual upload, exact account selection, daily IST slots, metadata presets, deduplication and safe archival. The updated `tubeforge-dashboard.html` is the interactive UI reference, including production and scene repair. This revision adds a source-level reuse map, a practical video-quality contract and a frontend/Python implementation handoff.

The canonical content skills live only in `.agents/skills/` in this checkout. Current records verify the yt-script runtime integration and representative production calls; creative acceptance remains blocked. Consult [current status](../docs/STATUS.md) and the [integration report](../docs/YT_SCRIPT_AUTOMATION_REPORT.md) for evidence. Preserve uncommitted work; do not reinstall competing skills or treat the published `dev` branch as the complete workspace.

## 1. Inputs, local paths and evidence

The screenshot shows these existing clones:

```text
/home/uditaswal/docker/tubeforge/git-repos/youtube-agent-skill
/home/uditaswal/docker/tubeforge/git-repos/youtube-automation-agent
/home/uditaswal/docker/tubeforge/git-repos/youtube-autopilot
```

The active checkout is `/home/uditaswal/docker/tubeforge/Youtube_Video_Producer`. This plan and [dashboard prototype](tubeforge-dashboard.html) live in `design_doc/`. Inspect the relevant donor files in the existing local clones when implementing their adaptations; no donor clone, fetch or pull is required. These clones are references, not skill installation targets.

The supplied design reports the following source snapshots. A focused second-pass source review on 12 October checked all three local HEADs and the specific files in the reuse table below. Donor code was inspected, not executed or copied in that review:

| Repository | Reviewed ref and commit | Role |
|---|---|---|
| [TubeForge](https://github.com/uditaswal/Youtube_Video_Producer/tree/dev) | `dev` · `9d99e43609f1be9d6e465b12ca6541d397a40e97` | Existing product and reliability foundation |
| [youtube-automation-agent](https://github.com/darkzOGx/youtube-automation-agent) | `master` · `e26792ae00dc1ec2434faf32632896609396dfad` | Scene repair, media task lifecycle and operator workflows |
| [youtube-autopilot](https://github.com/khaoss85/youtube-autopilot) | `main` · `69d8f0cf2872bd1467b4d09d12eb1109603345e7` | Storyboards, shot direction and channel profiles |
| [youtube-agent-skill](https://github.com/Jakeschincariol/youtube-agent-skill) | Already integrated by the preceding task | Existing research, scripting, packaging and editorial instructions |

These are static source findings, not a claim that donor APIs, generated videos or live publishing were tested. The current local checkout, its uncommitted integration and applicable `AGENTS.md` instructions take precedence over this snapshot. Record local commit IDs and changed paths once, then inspect only the modules relevant to the next acceptance test.

### What TubeForge already has

The reviewed code is Python/FastAPI with typed domain contracts, SQLAlchemy/SQLite, Alembic, durable workers and FFmpeg. Preserve these working components:

| Existing TubeForge paths, relative to its checkout | Keep and extend |
|---|---|
| `pipeline/orchestrator.py` under `src/tubeforge/` | Checkpoints, leases, ownership fencing, cancellation and artifact promotion |
| `pipeline/publishing_assets.py`, `manual_publish.py`, `delivery_queue.py`, `delivery_executor.py` | Immutable staged assets, exact-review drafts, per-account deliveries, saved sessions and reconciliation |
| `providers/publishing/account_youtube.py`; `security/account_credentials.py`, `google_oauth.py`, `oauth_state.py` | Account identity, encrypted credentials, refresh coordination and resumable YouTube upload |
| `pipeline/narration.py`, `alignment.py`, `captions.py`; `rendering/preview.py`, `audio.py` | Phrase audio, portrait rendering, captions, music and final-media validation |
| `domain/contracts.py`; `pipeline/assets.py`, `visual_router.py`; `providers/media/` | Existing `ContentPackage`, `VideoPlan`, media manifests and rights checks |
| `scheduling/service.py`; `db/models.py`, `repositories.py` | Existing topic scheduling and durable relational state |
| `clipping/analysis.py`, `clipping/render.py`; `pipeline/performance.py`, `learning.py`, `optimization.py` | Clipping, analytics and learning foundations |

The published 5 October status records offline manual-publishing coverage, while live publishing, folder automation, presets and the shared generation-to-publishing bridge remain open. Reconcile this against current local evidence; do not redo completed work or upgrade its status without proof.

### Why the current generated videos can look weak

`providers/media/local_graphics.py` chooses among four geometric layouts using a hash. It can create distinct files without depicting the subject or explaining the narrated claim. The visual gate in `pipeline/assets.py` checks properties such as resolution, distinctness and permitted assets; those checks do not establish semantic relevance. Splitting one still into several pan/zoom segments in `rendering/preview.py` changes pacing without adding information.

`VideoPlan` and visual-routing declarations already exist, but the reviewed status says renderer consumers still need migration from `ContentPackage`. Connect the chosen plan fields to actual asset selection and rendering. Avoid another unused planning schema.

Word timing in `pipeline/alignment.py` is inferred within phrase audio spans; it is not demonstrated ASR or forced alignment. Keep its working path, measure pronunciation/caption errors and add an optional alignment capability only if the observed output needs it.

These are source-based explanations to test against the current output, not a judgment based on an unseen recent video. The fastest quality improvement is to make visuals explain the script and allow targeted repair.

## 2. Precisely what to take from the donors

All donor paths below are relative to the three clone directories above. TubeForge targets are relative to `src/tubeforge/`. Names of new services are suggestions, not a second domain model or framework requirement.

| Priority and donor files | Useful behavior | TubeForge adaptation and proof |
|---|---|---|
| **High: darkz** `utils/scene-repair-service.js` | Persistent scene identity; edit narration/prompt; replace media; lock/reorder; regenerate one scene; revisions and stale states | Extend existing scene contracts and orchestrator, add focused API/UI actions. Change scene 3 and prove unchanged assets/audio are reused, affected captions/timing are rebuilt and prior final approval is invalidated. |
| **High: khaoss** `yt_autopilot/agents/visual_planner.py`, `yt_autopilot/agents/cinematographer.py`, `yt_autopilot/core/schemas.py` | Narration-linked shots, concrete subjects/actions, framing, continuity, overlays and B-roll intent | Independently implement a compact typed storyboard using existing `ScenePlan`/`VideoPlan`. Wire it into `pipeline/assets.py`, `visual_router.py` and the renderer. Inspect actual frames against each narrated beat. |
| **High: darkz** `utils/media-generation-service.js`, `utils/video-providers.js` | Submitted task IDs, polling, cancellation, output reuse and provider capabilities | Add one selected real-media adapter only when needed. Persist revision/request identity and remote task state in existing DB/workers. Restart after submission and prove it resumes the same task without a second charge. Verify the chosen provider's current API rather than copying donor model names. |
| **High: khaoss** `workspaces/tech_ai_creator.json`, other workspace JSON; `config/series_formats/*.yaml` | Reusable audience, voice/style, palette and series structure | Implement versioned profiles/presets in TubeForge. Map approved settings into the integrated skills, storyboards, narration and metadata. Verify two different topics maintain the same selected channel style. |
| **High: khaoss** `yt_autopilot/services/reference_image_generator.py` | Preview scene visuals before expensive final production | Independently implement a contact-sheet/storyboard preview using selected real assets. Require complete scene coverage; do not treat a partially generated list as success. Reuse those approved assets in the final render. |
| **Medium: darkz** `utils/production-readiness-service.js` | Real text/audio/media/FFmpeg/account probes with stored evidence | Add action-specific readiness using current TubeForge checks. Local upload needs decoding and the selected publisher; generation additionally needs the selected writer, voice and media route. Skipped, stale or key-only checks do not prove readiness. |
| **Medium: darkz** `utils/autonomous-channel-operator.js` | Bounded batches, progress, stop/resume and production summaries | Adapt behavior onto the existing topic queue, scheduler and worker checkpoints after one good video is proven. Do not add its second job loop. Restart a small batch without regenerating finished items. |
| **Later: darkz** `utils/shorts-repurposing-service.js` | Choose contiguous scene windows and retain source-scene provenance | Extend existing clipping selection and portrait renderer. Review whether an excerpt has a complete hook/payoff; preserve source times and prevent repeated moments. |
| **Later: darkz** `utils/scene-retention-engine.js` | Map measured retention points to rendered scene windows | Extend existing analytics/learning with actual rendered timestamps and authorized, available metrics. Show missing data honestly; recommendations affect future content and are not causal proof. |
| **Supporting: khaoss** `yt_autopilot/agents/narrative_architect.py`, `yt_autopilot/agents/quality_reviewer.py`; **darkz** `agents/content-strategy-agent.js` | Story beats, consistent editorial checks and explicit research inputs | Fold useful criteria into the already integrated skills and content provider. Do not add a second script-writer stack or repeated model-review loop. Reject unsupported claims and simulated trend/view predictions. |

### Second-pass reuse review — 12 October 2026

The checked local commits still match the IDs above; `youtube-agent-skill` is at `a2feb2104981a375ffd4f87ee04f4f5344ac43c6`. This pass compared donor behavior with current TubeForge contracts and identified these additional small pieces. “Reuse” means adapting logic into existing Python services unless a canonical skill tool can be called as installed. No donor service is production-verified by this inspection.

| Candidate | What can speed up TubeForge | Fit, sequence and proof |
|---|---|---|
| **Soon, darkz** `utils/provenance-service.js` | Its compact source/claim review states and requirement that a supported claim link to a reviewed source can inform the existing script approval panel. | TubeForge already has source IDs, excerpts, claim IDs and claim review states in `domain/contracts.py`; add a source-review decision to the existing exact-revision approval path after visual acceptance (tasks 4–6). Prove an unsupported claim blocks approval and a reviewed source remains linked to the exact script revision. Port the rule; do not add a parallel provenance database. |
| **Soon, darkz** `utils/operator-service.js` | Its per-scene readiness checklist combines current visual, narration, rights and provenance state before approval. | Extend `pipeline/quality.py` and the existing review response for tasks 4–6. Use TubeForge artifact checksums, current revision and completed media probes rather than the donor's file-existence checks. A stale or missing scene must block final approval with a scene-specific finding; a valid rebuilt scene clears it. |
| **Later, khaoss** `config/series_formats/*.yaml` and `workspaces/*.json` | Segment order, audience expectations and palette fields are usable seed data for versioned format/channel profiles. | For task 22, map selected fields into TubeForge presets and channel voice snapshots; prove two topics retain one selected identity. Do not import the donor's Sora intro/outro prompts, invented persona credentials, language-mixed copy or fixed 20–35-second pacing. |
| **Later, installed skill** `.agents/skills/yt-chapters/chapters.py` with `.agents/skills/yt-edit/deadair.py` | The chapter tool already proposes boundaries from caption pauses and vocabulary shifts and validates the 00:00/three-chapter/10-second shape. | Both tools are already in TubeForge's canonical skill folder, so call them there for appropriate long-form jobs when that workflow is reached. Retitle against the actual script and inspect timing; Shorts do not need a chapter-generation stage. |

No whole donor module is a safe drop-in replacement for the current Python pipeline. `utils/generation-recovery-service.js` validates saved files mostly by existence and size, while TubeForge relies on checksum, lease and revision identity. `utils/youtube-metadata-validator.js` silently truncates titles/descriptions/tags; TubeForge's current `pipeline/publication.py` and `pipeline/manual_publish.py` reject invalid reviewed metadata. `utils/shorts-repurposing-service.js` picks evenly spaced anchors that can overlap and schedules clips automatically, so use only its contiguous-window idea at task 25 after uniqueness and approval checks. Khaoss `core/format_validator.py` imposes fixed aspect/duration rules, and `core/series_manager.py` claims language-agnostic classification while matching a short English/Italian keyword list; neither should override selected TubeForge presets. Khaoss `io/exports.py` writes zeroes for unavailable metrics, so it cannot be reused for the measured-insights task without preserving missing values. The donor's video-provider registry names and limits require current provider verification before any paid adapter is considered.

### Copying boundary

The operator explicitly authorized reuse of the referenced donor code and waived a separate license-review task for this work. Record each copied/adapted source path, checked commit, target path and modifications so future maintainers can trace it; retain any notice that accompanies copied code. Choose reuse based on runtime fit and TubeForge's stronger reliability contract, not on an assumed need to rebuild a donor application.

### Parts to leave behind

- Darkz's Node application, dashboard and agent framework: adapt individual workflows to Python. TubeForge already owns jobs, auth, API and rendering.
- Darkz's gradient/slideshow defaults, generic script templates and title-gradient thumbnails: their existence is not evidence of better videos. Use relevant visuals and an intentionally composed thumbnail.
- Darkz's recovery based on file existence and its readiness check that rejects only an overall failed state: preserve TubeForge's stronger hash, lease and exact-artifact guarantees; require current successful checks for the requested action.
- Donor publishing orchestration: extend TubeForge's account-scoped delivery executor. Accepted upload or accepted future schedule must not become confirmed publication immediately.
- Khaoss's coordinator as a supposed Codex subagent system: its internal role/function calls do not establish native Codex delegation. Additional orchestration is unnecessary here.
- Khaoss's README claims of complete production: `yt_autopilot/pipeline/__init__.py` explicitly says video production was removed and outputs are scene-prompt Markdown for external tools. It supplies editorial design ideas, not a replacement renderer/uploader.
- Placeholder provider success, automatic expensive fallback, stale SDK/model defaults, unsupported expertise in personas and unrelated outreach automation.

## 3. Shared publishing product contract

An **automation** combines a source pool, exact destination accounts, recurrence, versioned metadata preset, review mode and completion policy. Manual Compose uses the same publishing path.

| Source | One occurrence |
|---|---|
| Folder backlog — first delivery | Reserve an eligible existing file → analyze/draft metadata → validate/review → deliver to selected accounts → reconcile → archive |
| Video generation | Reserve topic → use integrated skills → storyboard/media/narration → inspect final → stage canonical asset → shared delivery/archive |
| Stream clipping | Reserve unused source moment → render/inspect excerpt → stage canonical asset → shared delivery/archive |

Default: **one distinct video per slot, delivered to every selected account**. Separate channel content uses separate automations/source pools. Destinations may receive valid platform renditions of the same canonical content. A failing destination does not change the selected video or cause successful destinations to upload again.

### Scheduling

Default timezone `Asia/Kolkata`; daily slot **13:00 IST**, with optional **19:00 IST**. Both are editable. Store timezone/recurrence and materialized UTC occurrences; 13:00 IST is 07:30 UTC. Show timezone beside dates and preview the next five runs.

Two timing modes must remain distinct:

1. **Publish at this time — default.** Prepare ahead of the slot. Start with configurable 60-minute lead time and a target ready buffer of two for generation/clipping, then tune from measured durations. These are defaults, not runtime guarantees.
2. **Start preparing at this time.** Selection/generation begins at the slot; show that publication follows preparation.

Enforce occurrence uniqueness `(automation_id, scheduled_utc)` and atomic source claims. Default late policy: publish within configurable 30-minute grace; otherwise mark missed and roll the prepared asset to the next eligible slot. Reconcile accepted remote schedules first. Restarting after downtime must not burst-publish missed slots or repost the previous video. Empty folder/no new eligible moment skips and alerts. Source switching is opt-in.

YouTube scheduling uses an eligible private, never-published video with `status.publishAt`; past timestamps must be rejected locally to avoid immediate publication. Confirm processing and eventual requested visibility. For Instagram, confirm the selected API's container-processing and publication contract, then dispatch at the slot. Store container IDs and respect their lifetime. Platform latency means exact-second simultaneity is not promised. [P1, P2]

**Pause** stops new local preparation/dispatch. **Cancel pending publications** is a separate action that attempts provider-supported remote cancellation and reports what was already accepted or too late to cancel.

### Folder catalog, reservation and archival

Example approved server mounts: `/media/inbox`, `/media/work`, `/media/archive`, `/media/quarantine`. A browser upload adds a file to approved storage; it does not give the browser arbitrary server-path access.

1. Incrementally catalog stable files. Ignore temporary suffixes/changing inputs; prefer producer temp-write plus atomic rename. Reject path traversal/symlink escapes and quarantine undecodable media. Probe dimensions/duration and hash stable bytes once; query indexed eligibility rather than scanning thousands of files every slot.
2. Order oldest ingestion first with stable ID tie-break and optional priority. Atomically reserve the canonical asset and snapshot destinations/configuration. Reuse immutable content-addressed staging and revalidate before delivery.
3. Record destination-specific sessions, remote IDs, requested visibility, processing/publication states, retries and receipts. Retry only failed destinations. Explicitly skipping one requires an audit event; never silently remove a required account.
4. Archive only after every required destination reaches its confirmed requested completion state. A future public schedule remains pending until public publication is confirmed. An intentionally private/manual test can have a separately stated completion policy and does not prove public autopilot.
5. Use a collision-safe target such as `/media/archive/2026/10/{asset-id}/original.mp4`, with a non-secret metadata/receipt manifest. Same-filesystem move is atomic; across filesystems copy to temporary target, verify hash/size, atomically rename target, then remove source. Journal the transition for crash recovery.

After remote success, archive failure means **Published · archive pending**. Retry archival only; the asset never returns to upload eligibility. Manual uploads may have no inbox source to move; record that explicitly and manage their staged-artifact retention separately.

Exact-byte fingerprints survive rename/reimport and retain delivery history; they do not detect every re-encode. Maintain canonical lineage through generated renditions. Enforce default-edition uniqueness for `(canonical asset, destination account, publication edition)` across manual and automatic delivery. An intentional repost creates a visible new edition. Manual delivery to a previously unused account is allowed; it does not automatically recycle the folder backlog.

### Accounts and metadata

Connect exact YouTube channels and Instagram professional accounts through the selected official OAuth route. Display immutable remote identity before saving/reconnecting. Treat TubeForge sign-in and platform authorization as separate workflows. Preserve encrypted tokens, server-side exchange, state/PKCE where applicable and per-credential refresh coordination. Never collect platform passwords or send tokens to the browser, prompts or logs.

Keep Instagram Login and Facebook Login contracts separate; an example using a Page token is not proof of the chosen Instagram Login implementation. Verify current app permissions, account capabilities, staging requirements and publishing limits against that route. Use explicit privacy settings and confirm returned remote behavior. Private test success is separate from public scheduling readiness; app credentials alone do not prove either. [P1, P2]

Generate metadata from script/transcript/clip context, sidecar metadata and, when necessary, sampled frames/OCR. Cache analysis by source hash plus analyzer version. Filenames alone are insufficient. Local speech transcription is analysis, not permission to use a local generative LLM as the production writer. Treat imported transcripts as data, not executable instructions. Low-confidence content requires review or an explicitly configured deterministic template.

| Field | YouTube | Instagram |
|---|---|---|
| Title | Separate title | Hook in caption |
| Description | Description | Caption |
| Keyword tags | Separate tag field | No equivalent general field |
| Hashtags | Title/description as configured | Caption |
| Video subtitles | Caption track/render setting | Burned-in or supported media workflow; distinct from caption text |

Precedence: workspace defaults → versioned preset → automation override → destination override → locked manual post fields. Auto/Template/Manual modes and field locks persist. Hashtags replace by default; explicit append deduplicates. Freeze the effective preset/metadata version on each job. Edits affect future jobs; applying to pending jobs requires an explicit action. Submitted remote posts use separate update operations.

Manual Compose: choose/upload video → choose exact accounts → preset → generate/edit/lock metadata → validate per destination → preview exact asset and settings → draft/schedule/publish. Reserve against automatic selection and use the same history, queue and reconciliation rules.

## 4. Generation that produces a useful finished video

The integrated skills remain the editorial layer. Discover their actual installed names and read the relevant `SKILL.md`; do not duplicate them into another set of agents. Use them for the supported research, script, packaging, Shorts and review tasks. Their suggestions enter typed TubeForge contracts and are carried through to real outputs.

### One coherent pipeline

Use one grounded brief → script/storyboard → real assets and scene narration → preview/repair → final render → canonical staged asset → shared publishing. Reuse existing checkpoints. Avoid multiple independent writers, generic review rounds and a new orchestration service.

Extend the existing scene model minimally, with versioned compatibility for old jobs. Each scene needs:

- Stable ID/revision, beat role, narration text, linked source/claim IDs and measured audio duration.
- Concrete visual subject/action and relevance rationale; planned asset kind, shot/framing/motion, continuity/style identity and safe-area requirements.
- Stock search or generated-media request, optional reference image, deterministic overlay text/data and explicitly chosen fallback.
- Actual asset hash/path/provenance, provider/model/request identity and remote task ID where applicable.
- Separate visual/narration freshness, lock, revision evidence and approval identity.

Do not introduce a competing `VideoPlan`. Version existing contracts and update the relevant host-output schema and consumers together if required. Verify that accepted fields actually affect the rendered scene. Keep compatibility with the already completed skills integration.

### Media route and cost

The first quality target can use relevant rights-cleared stock or user-owned uploads, accurate vector/FFmpeg diagrams and tasteful still motion. It does not require an expensive AI-video provider. For an astronaut topic, use suitable footage or an explicitly labelled explanatory diagram; a hash-selected circle/card layout is insufficient.

Keep current media rights/source/hash validation. Expand permitted source categories only with explicit rights evidence. User replacement does not automatically prove rights. Maintain per-scene acquisition evidence and truthful synthetic-media provenance.

Generated images are an optional selected real provider. Generated video is optional for scenes where motion adds meaning; implement one chosen provider, not every donor adapter. Verify its current model, input/output constraints and access before claiming support. Preserve existing authorization and configured spending limits; a new paid provider requires its concrete provider/cost/fallback proposal under the current working contract. Continue independent local work while it is unavailable.

Freeze provider/model and canonical request hash with the scene revision. Reuse only validated outputs with matching identities. Persist submission intent before calling the provider and save returned task IDs immediately. If submission may have succeeded but its ID was not saved, reconcile through supported idempotency/status facilities; otherwise mark unknown and stop automatic resubmission. The donor's saved-task pattern alone does not close this uncertainty window.

Bound polling, timeouts, concurrency, retries and generated seconds/cost per run. Show requested versus actual provider. Estimates, observed usage and provider-reported billing are separate fields; unknown billed cost stays unknown. Never silently change provider or substitute decorative placeholders as production success.

The current Shorts gate assumes particular generated/stock families. Extend it by actual asset capability and provenance so an intentionally mixed storyboard can pass; do not remove validation to accommodate a new provider.

### Narration, captions and rendering

Keep approved Codex CLI/Claude production writing and existing local voice providers. No local generative LLM fallback, retry-budget reset or new provider substitution is implied. Retain historical rejected-packet budgets. Diagnose schema/runtime preflight independently from model output, but do not erase already recorded attempts.

For the existing Shorts preset, default to a 45-second brief within the repository's **30–55 second, 1080×1920** production standard. Use the configured narrator's measured pace and existing word-budget contract; shorten text instead of forcing unnatural speed. Imported backlog videos are validated against the selected destination, not forced into this generated-Shorts duration.

Use each scene's actual narration audio to place visuals. Script edits regenerate only affected narration/visual dependencies, then rebuild downstream timeline/captions/final mix. Retain licensed music and ducking. Inspect pronunciation, caption timing and whether music masks speech. Do not label approximate timing as forced alignment.

Render important text/labels deterministically, separately from image generation. Charts and diagrams require actual cited data/relationships, not decorative pseudo-data. Preserve portrait-safe caption placement and existing pacing bounds; repeating the same still with tiny zoom changes must not masquerade as fresh explanatory content.

### Scene editor and exact artifact approval

From a generation job, open a storyboard contact sheet and scene list with playable audio, narration, visual intent, actual media, duration and status. Expose Edit narration, Edit visual direction, Upload replacement, Regenerate this scene, Lock, Reorder and Rebuild preview as real API actions. Show the configured cost consequence only when relevant; prior authorization within a budget remains valid.

Use optimistic revision checks and existing worker ownership. Editing a scene invalidates dependent approval/final-artifact identities. Rebuilding creates a new immutable reviewed artifact; it never changes bytes already selected for a delivery. Approved/submitted jobs are locked against silent edits. A deliberate new revision must enter review and create a separate draft; it does not automatically repost.

### Creative acceptance

Technical validation and creative review are distinct. For each initial production acceptance, retain the MP4, storyboard/contact sheet, transcript, asset manifest and measured timing report. Inspect actual images and watch/listen to the complete final video. Record timecodes and concrete defects/pass evidence.

| Check | Passing evidence |
|---|---|
| Story | Topic-specific opening, understandable progression and payoff; no unsupported facts or filler introduction |
| Visual meaning | Every narrated beat has relevant footage, illustration or explanatory graphic; no arbitrary shapes substituting for the subject |
| Continuity/pacing | Deliberate shot changes, readable overlays and consistent selected channel style; cuts support comprehension |
| Sound/captions | Clear complete narration, correct key pronunciations, acceptable synchronization, readable safe-area captions and unobtrusive music |
| Technical output | Current media gates pass; generated Shorts meet the stated portrait/duration standard; complete decodable file with no stale/missing scene dependencies |
| Repair | One edited scene rebuilds correctly while unchanged media/audio are reused; approval matches the exact final bytes |
| Delivery bridge | The approved output appears in the canonical library/Compose flow and uses existing per-destination delivery identity |

First prove **one** real production video with an approved non-fake writer. Then prove a second distinct topic in the same profile before enabling a small bounded generation batch. A fixture-script render can prove engineering behavior but cannot prove live production writing. A model's self-awarded score, a PNG checksum or passing unit tests cannot replace artifact inspection. If final playback cannot be inspected, keep the creative gate open.

## 5. Dashboard implementation from the supplied HTML

Preserve the current Creator Studio authentication, dark navy design system, responsive behavior and documented local URL `http://127.0.0.1:62065`. The updated HTML is a self-contained interactive concept with ten screens, browser-local edits and explicit simulated actions. It replaces the previous exported/escaped mockup wrapper. Its local state, timers, sample artwork and receipts are design demonstrations, not production backend data or generated-video evidence.

The recommended production frontend is Next.js/React with TypeScript, while FastAPI, Python workers, the existing database and publishers remain authoritative. Migrate the shell and Compose/Accounts/Activity workflow incrementally. Keep the local-video publishing target first; a whole-dashboard rewrite is not a prerequisite. A static Next.js export can be served through the existing ingress while browser requests go to FastAPI; use server-backed Next.js only for concrete server-feature needs. The deployment choices, component boundaries and prototype limits are consolidated below; the separate handoff is retired.

| Screen | Required production behavior |
|---|---|
| Overview | Real ready/reserved/delivered counts, next IST slots, account health, partial/missed runs, platform links, pause and Compose shortcut |
| Automations | Source cards; destination selection; preset; recurrence/weekdays/timezone; preparation lead; next five slots; empty/missed policies; review/automatic mode; pause/duplicate/edit |
| Video Library | Indexed paging, thumbnails/playback, filename/duration/source, eligibility, destination history, duplicate state, priority/exclude, Compose and archive location |
| Compose | Upload/select local video; exact accounts; effective metadata with locks/overrides; platform validation/preview; draft/schedule/publish |
| Accounts | Immutable remote ID, friendly label, type/scopes, last success, reconnect/blocked state, linked automations and connect/reconnect/pause/disconnect |
| Presets | Versioned brand/language/audience/voice/visual style, templates, tags/hashtags, CTA and platform settings; future-only updates |
| Activity | Parent run and destination children; processing/schedule/publication differences; attempts, remote IDs, retries, unknown outcome resolution and archive repair |
| Settings | Approved mounts, app/provider configuration, staging, worker health, retention/backups and existing login/session controls |
| Production Studio, including Stream Clips | Preserve existing generation/clipping access; briefs, complete contact sheets, narration/visual direction, revision-aware scene edit/replace/lock/reorder, targeted rebuild and exact final review; clips retain source ranges and prevent overlap/reuse |
| Insights | Show unavailable analytics honestly; display only authorized measured data mapped to actual rendered scene timestamps, with no invented curves or growth predictions |

Replace the mockup's 60-second generated-Shorts option with the current supported preset range. Backlog imports retain their own destination-validated durations. Separate genuine delivered totals from future schedules and dry-run results.

Every control must use a tested backend action and persisted state, with loading/empty/pending/error/disabled states. Refresh must preserve open edits/dialogs. Read-only views remain usable when one account is disconnected. No unsupported platform connect buttons or fabricated readiness/analytics.

The reviewed `api/app.py` embeds substantial HTML/JavaScript. Move affected UI components into the selected frontend while preserving API, authentication, lease and exact-review contracts. Verify each migrated signed-in workflow and mobile layout before replacing its existing production screen. Frontend route guards never replace backend authorization, and Next.js does not own video generation or publishing jobs.

### Frontend ownership and deployment

Next.js/React/TypeScript is a planned frontend recommendation, not an implemented capability or a video-quality fix. Use a `frontend/` package with a supported version and lockfile when migration starts. Preserve the existing backend login until its replacement has passed independent signed-in tests.

| Layer | Owns |
|---|---|
| Frontend | Navigation, responsive forms, scene/media previews, API state and errors, exact-review presentation |
| FastAPI | Authentication/authorization, OAuth identity and credentials, asset catalog, presets, drafts, validation, revision checks and durable command acceptance |
| Python workers/scheduler | Ingestion, transcription, generation, FFmpeg, occurrence claims, upload/reconciliation, retries and archival |
| Existing database | Jobs, leases, reservations, versions, delivery identity, receipts and audit evidence |

Use one origin through existing ingress; preserve API/auth/OAuth callback paths and the session contract. Credentials stay out of browser storage. The sole documented developer dashboard URL remains `http://127.0.0.1:62065`, bound to loopback; internal frontend containers need no additional published host port.

Start with a static Next.js export and browser requests to FastAPI when sufficient. Use fixed screen routes with query-selected record IDs; arbitrary runtime dynamic routes, Server Actions and request-time features require a different deployment. Add an internal Next.js server behind the same ingress only for a concrete server-feature requirement. Interactive editing and browser media controls belong in client components. If FastAPI serves exported assets, register API/auth routes before the static fallback.

Suggested components: `AppShell`, `StatusChip`, `AccountPicker`, `AssetTable`, `MetadataEditor`, `AutomationForm`, `PlatformPreview`, `Storyboard`, `SceneInspector`, `QualityReview`, `DeliveryTimeline`, `ReadinessPanel`. Reuse responsibilities without adding another state framework or status database. Replace local-storage/timer simulations with typed API responses and durable commands. Keep unsaved UI drafts separate from persisted state; mutations carry revision identity. Start with silent query refresh that preserves edits/dialogs; add a backend event stream or WebSocket only when justified and implemented.

### Prototype walkthrough and evidence limits

Open [tubeforge-dashboard.html](tubeforge-dashboard.html) locally. Its inline SVG artwork and interaction state are self-contained. Suggested walkthrough: repair scene 3's stale visual, rebuild its demo preview, acknowledge four quality checks, approve the demo revision and add it to the library. Then retry the failed Instagram destination without repeating YouTube, inspect the uncertain saved session separately and exercise archive-only recovery.

OAuth, providers, render tasks, receipts, schedules, filesystem changes and posting are simulated. Browser storage retains metadata/edits; selected media bytes remain in memory and must be selected again after refresh. Ten-file/100 MB import limits belong to the prototype, not production requirements. Explicit repost editions, audit export, recovery/reset and readiness dialogs are interaction references, not promises of backend support.

The supplied handoff reports a syntax check, 41 DOM-stub workflow checks, and ten parsed screen fragments without duplicate IDs or missing label targets. Those checks were not rerun in this consolidation and do not prove production behavior. Responsive layout, keyboard/focus handling, native playback/upload and speech read-out still require real-browser inspection. Migrate Compose/Accounts/Activity first, then Library/Automations, then Presets/Studio/Insights as their actual APIs become available.

## 6. Durable architecture and failure handling

Extend the existing FastAPI/SQLite/Alembic stack. Logical responsibilities are catalog/preparation, scheduler, per-account publisher, reconciliation and archival. These can use existing services/processes; no default Node sidecar, PostgreSQL/Redis migration or separate daemon is required.

Reuse existing asset, post, destination, attempt, credential and generation records. Add only missing fields/relations for presets, source pools, automations/occurrences, reservations/lineage, archive tasks and scene/media revisions. Do not create a parallel asset or publish-job database. Use indexed constraints, migrations and a committed dispatch intent/outbox equivalent that survives process failure.

Sources return a canonical asset with transcript/provenance and readiness evidence. Publisher adapters expose capabilities, validation, upload/session preparation, status/reconciliation and supported scheduling/cancellation. Capability-driven UI hides or disables unsupported operations truthfully. Generation and clipping do not call YouTube directly.

Parent progression is conceptually planning → preparing → ready → dispatching → verifying → completed → archive pending → archived. Map this to existing enums rather than renaming mature states. Each destination independently records upload, processing, scheduling, requested visibility completion, retry, auth, failure, skipped and unknown outcomes. Derive parent status from required destinations.

There is no universal exactly-once transaction with platforms or paid media providers. Preserve leases, heartbeats, fencing, saved sessions, uniqueness and conservative reconciliation. After an uncertain response or expired upload lease, inspect/resume the saved operation before any new upload. Unprovable outcomes block only that operation for review. A successful account stays successful while another is repaired.

Use bounded backoff/jitter and provider retry hints. Quota/auth/media validation errors need the appropriate pause/reconnect/repair, not endless retries. Serve only the specific Instagram staging asset through an approved HTTPS mechanism for the required fetch lifetime; never expose the inbox. Keep staged media while any pending destination needs it.

Readiness is scoped: a local imported-video flow does not depend on the script/image generator. A selected generation route needs those actual capabilities. Persist timestamp/version/account/provider evidence; stale, skipped, simulated or merely configured checks are not verified. Record in-app alerts for missed/empty slots, auth, quota, unavailable workers, partial/unknown delivery and archive failure. Do not add unrequested outbound notifications.

## 7. Delivery sequence and acceptance

The [fine-grained implementation order](tubeforge-implementation-order.md) is a proposed sequence for operator review. Until its order is approved, the phase table below remains design context rather than a mandate to start the previous publishing-first sequence.

This is the canonical execution plan for the consolidated design. The phase table defines outcomes, acceptance evidence and scope boundaries; the checklist below tracks the next concrete work. Reconcile current records once and skip work already evidenced. Work on one phase at a time and report its acceptance result before starting the next. Planning completion does not verify application behavior.

Use `NOT STARTED`, `IMPLEMENTED`, `VERIFIED` and `BLOCKED` according to the existing working contract. Split local engineering, creative artifact and external publication gates explicitly. Lack of live credentials must not prevent independent local queue/backlog/render work, but it prevents claiming the corresponding real-post gate verified.

| Phase | Outcome and relevant reuse | Required evidence | Scope boundary |
|---|---|---|---|
| **0. Reconcile current work** | Accurate minimal delta; preserve completed skills integration | Local paths/SHAs/changed files, existing contracts, license reuse record, current status and next acceptance test | No repeated full audit or skills setup |
| **1. Local-video Compose** | Select/upload existing media and prepare exact account deliveries | Actual staged video/hash; signed-in review flow; focused publishing/auth tests; requested account/metadata/visibility snapshots. Controlled remote IDs and inspection when already authorized/configured | No creative rewrite; external platform gates recorded separately |
| **2. Folder backlog autopilot — first operational target** | Daily 13:00 IST selection, deduplication and safe archival | Competing scheduler claims; two distinct files; restart after selection/upload; partial destination retry; missed slot; rename dedup; archive-copy failure/recovery. Offline adapters prove local behavior only. Real scheduled receipt/visibility/timing prove each live destination | No generation/clipping dependency; no claimed public readiness from fakes |
| **3. Profiles and presets** | Shared settings and persistent per-account/manual locks | Two accounts/profiles, exact effective settings, locked fields and version snapshots; future-only preset update | No donor agent framework |
| **4A. Storyboard and relevant assets** | Integrated skills drive a compact plan and complete real scene assets | Non-fake approved script, grounding, contact sheet, relevance check, selected provider/rights evidence and measured audio; scheduler-to-writer contract checked if still applicable | No batch or many paid adapters |
| **4B. One finished video and scene repair** | Good portrait video enters canonical library/publishing | Complete MP4 inspection against section 4; one-scene edit/rebuild/reapproval; reuse evidence; second distinct topic; generation-to-delivery bridge. External receipts only where configured/authorized | No growth promise, whole-app rewrite or full autopilot before quality proof |
| **5. Clipping source** | Self-contained unused moment enters the same engine | Actual source ID/time range, semantic clip review, portrait output, no-repeat reservation, no-new-source policy and applicable delivery evidence | No assumption every provider exposes highlight metrics |
| **6. Bounded batch and learning** | Small resumable batches and measured scene feedback | Restarted batch reuses completed work; limits/cancellation; actual scene timestamps and available retention data. Optional future adapters use the same capabilities | No simulated growth metrics or unrequested platform launches |

Phase 1's local acceptance enables Phase 2's local work while externally blocked account verification remains explicitly open. Enabling automatic live delivery for a destination requires that destination's real acceptance. Never silently drop a required destination to make a test pass.

One source-level check is worth carrying into Phase 4: the reviewed `scheduling/service.py` emitted `prompt_version="topic-queue-v1"`, while content prompts used `m6-content-*` versions. If current local integration has already fixed it, retain that fix. Otherwise align the scheduler/provider contract and add a focused boundary test. Do not reset exhausted script packets as a workaround.

### Updateable execution checklist

Unchecked means acceptance remains open, not that no code exists. Record implementation state and evidence in `docs/STATUS.md`; check a task only after its stated acceptance is verified. Existing phase-1 publishing code must be assessed and reused before adding code. Current release records distinguish local publishing tests from unverified live delivery, and verified skill integration from blocked creative acceptance.

- [ ] **P0.1 — Reconcile:** identify current APIs, auth/session paths, schema, relevant local donor revisions and existing evidence; list only the remaining delta. The focused donor reuse review above is complete; API/auth acceptance remains open.
- [ ] **P1.1 — Local Compose:** stage a real video, review its exact hash/revision/accounts/metadata and submit through existing durable delivery APIs; inspect signed-in behavior and focused tests.
- [ ] **P1.2 — Frontend slice:** choose static export versus a justified server deployment; migrate shell plus Compose/Accounts/Activity incrementally, with typed API state and desktop/mobile/keyboard inspection. Keep existing working screens until replacements pass.
- [ ] **P1.3 — External acceptance:** record separately each authorized account's remote identity, upload/processing/visibility or scheduling receipt; keep missing credentials/API approval/authorization blocked.
- [ ] **P2.1 — Backlog scheduling:** indexed eligible files, exact accounts, next-five timezone slots, exclusive occurrence/reservation claims, missed/empty handling and immutable snapshots.
- [ ] **P2.2 — Recovery:** prove two distinct files, rename deduplication, selection/upload restart, partial destination retry and archive-only recovery including cross-filesystem failure.
- [ ] **P3.1 — Presets/profiles:** prove effective settings for two accounts, locks/overrides, frozen versions and future-only updates in API and UI.
- [ ] **P4A.1 — Storyboard:** grounded production script, narration-linked scene intent, complete relevant assets/contact sheet, rights/provider evidence and measured audio; preserve canonical skill loading and writer budgets.
- [x] **P4B.1 — Creative acceptance:** inspect one complete real video against section 4, recording timecoded substance, visuals, pacing, audio and caption findings.
- [ ] **P4B.2 — Scene repair:** edit one scene, prove selective reuse and downstream rebuild/reapproval of exact final bytes, then inspect a second distinct topic in the same profile and canonical library handoff.
- [ ] **P5.1 — Clips:** inspect a real self-contained source window and portrait output, prove provenance, overlap/no-repeat reservation and shared delivery integration.
- [ ] **P6.1 — Batches/insights:** prove bounded restart/cancellation and reuse of completed work; show real scene-linked analytics only when authorized data exists.

For each active task, add a compact work entry here before editing:

| Task ID | Intended change / remaining delta | Acceptance command or inspection | Evidence path | Next action |
|---|---|---|---|---|
| Tasks 1–3: visual production | **VERIFIED**: inventory, narration-linked scenes and relevant permitted visuals | [Inventory and production evidence](../docs/VIDEO_VISUAL_INVENTORY.md); live host preflight matched complete prompt and all seven skill resources, and a Codex production call returned six source-linked scenes. A measured-duration revision was saved and approved by exact checksum `68e711a27e12…` in cache-backed job `0394bd453cd24dc4adbeee5ac5c1fee4`. Its [v9 six-scene sheet](../data/artifacts/0394bd453cd24dc4adbeee5ac5c1fee4/storyboard/contact-sheet-001.png), CC0 rights/hash manifest and 43.016-second preview were inspected; all beats have concrete teaching visuals and the preview references the approved content hash. Affected Compose suite: 58 passed, 3 environment-dependent skips in 11m39s. | [Current task states](../docs/STATUS.md): tasks 1–3 VERIFIED | Task 4 is now VERIFIED with a separate signed-in job; preserve this job's original unapproved preview for evidence. |
| Task 4: finished Short | **VERIFIED**: exact preview approval, production final render and complete operator audiovisual review passed | [Timecoded inspection and exact evidence](../docs/TASK4_VIDEO_REVIEW.md): signed-in job `9df50ade…` approved script SHA `68e711a…` and preview identity `70c4c388…`, then registered a 43.033s 1080×1920 H.264/AAC final with matching inputs and bounded render strategy. The 2-second visual sheet, caption, full decode, black/silence and focused test checks passed (57 tests); the operator watched/listened to the full final and reported no defect. Temporary login/session was removed and revoked token returns 401. | [Current task state](../docs/STATUS.md): task 4 VERIFIED | Start task 5 selective scene repair under a new exact-artifact approval. Keep publication unapproved. |
| Task 5: one-scene revision | **VERIFIED**: a separate paused draft and Studio scene editor are in place | [Real child draft and preview](../docs/TASK5_SCENE_REVIEW.md) changed only scene 3, reused five of six asset hashes and 11 of 12 phrase-audio hashes, and rebuilt timing/captions into a 43.179s preview; contact sheet and sampled frames were inspected. The signed-in production Studio API created child `8481109b…` with the same reviewed content SHA and audit event while the parent stayed unchanged. Current-worktree regression: 77 passed; final focused rerun: 2 passed. | [Current task state](../docs/STATUS.md): task 5 VERIFIED | Task 6: test stale approval and bind the new exact preview/final; publication stays unapproved. |

Replace the placeholder when implementation starts. Keep this table limited to active work; move completed acceptance details into the evidence log and link them beside the checked task. Do not store credentials, runtime logs or generated media in this document or Git.

## 8. Keep Codex work bounded and remembered

Use these records for distinct purposes; do not create competing status trackers:

- **This plan:** contracts, ordered tasks, acceptance criteria and active implementation delta. After every meaningful change, update affected task checkboxes, acceptance/evidence links and next action. Adjust the design when the implemented contract changes; never silently weaken acceptance to match a failure.
- **[docs/STATUS.md](../docs/STATUS.md):** sole source of current phase/release state, exact `NOT STARTED`, `IMPLEMENTED`, `VERIFIED` or `BLOCKED` labels, local/creative/remote gates, blockers and next five tasks. Newer evidence takes precedence over supplied snapshots.
- **[AUTONOMOUS_PROGRESS.md](../AUTONOMOUS_PROGRESS.md):** append scope, validation commands/results, inspected artifacts, donor adaptation/license mapping where relevant, blockers and next action for each meaningful session.
- **[AGENTS.md](../AGENTS.md):** durable rules and documentation-update contract; preserve canonical skill and reliability guidance, without milestone history.
- **[readme.md](../readme.md):** supported operator setup/workflows only. Update when actual account connection, publishing, presets, scene repair or dashboard behavior changes; distinguish future plans.
- **[Earlier publishing delivery plan](../docs/planning/publishing-delivery-plan.md):** retain historical inventory and acceptance evidence. This consolidated plan supplies the forward execution sequence; reconcile older tasks rather than duplicating implementation.

Before marking a task verified, run its relevant tests and required regression checks, inspect real output, and inspect the signed-in desktop/mobile workflow when operator-visible behavior changes. Log failures and leave the task open. Documentation-only updates require link/reference and content checks, not a fabricated application smoke test.

For speed, implement the smallest complete vertical slice and inspect it early. Cache research/analysis/plans and media by immutable inputs and relevant versions. Regenerate affected scenes only. Use bounded provider calls and focused meaningful tests, then the repository's required regression/acceptance checks. Respect current stop limits for script retries and repeated active debugging; do not manufacture repeated attempts through new IDs. Avoid speculative refactors and layers of model self-review.

If another Codex task is still changing overlapping files, perform read-only inventory and independent work until those edits settle; coordinate before editing shared files. Do not reset, stash, discard, checkout another branch over or independently recreate its uncommitted integration.

Prepare reviewable code, migrations, UI and local artifacts before requesting any truly missing external authorization. Existing explicit user authorization remains valid. This document/prompt alone does not authorize a live post or new paid API call. When credentials, paid access or live publication are unavailable, finish independent local work and report exactly which external gate remains blocked.

## 9. Source notes

The supplied source review is dated 11 October 2026; the additional local file comparison above was performed on 12 October. Implementation must verify installed versions and selected platform contracts; donor marketing is not execution evidence. The operator waived a separate license-review task.

- TubeForge source and current published records: [reviewed dev snapshot](https://github.com/uditaswal/Youtube_Video_Producer/tree/9d99e43609f1be9d6e465b12ca6541d397a40e97), especially `AGENTS.md`, `docs/STATUS.md` and the paths mapped above.
- Darkz source/license: [reviewed snapshot](https://github.com/darkzOGx/youtube-automation-agent/tree/e26792ae00dc1ec2434faf32632896609396dfad), especially the `utils/` services in section 2 and `LICENSE`.
- Khaoss editorial/production boundary: [reviewed snapshot](https://github.com/khaoss85/youtube-autopilot/tree/69d8f0cf2872bd1467b4d09d12eb1109603345e7), especially `yt_autopilot/pipeline/__init__.py`, scene schemas and visual-planning modules. No license found in that tree; recheck locally before copying.
- Existing skill reference: [youtube-agent-skill](https://github.com/Jakeschincariol/youtube-agent-skill). Its completed local integration is the implementation baseline, not a new task.
- **P1 — YouTube:** [video status and publishAt](https://developers.google.com/youtube/v3/docs/videos#status.publishAt). Explicit privacy, private/never-published scheduling and actual processing/visibility checks are required. Current summary/body text about unverified projects is inconsistent; verify the actual application's capability rather than hardcoding the old proposal's blanket private-only assertion.
- **P2 — Instagram:** [Meta-owned Instagram API collection](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api). It separates Instagram Login and Facebook Login examples. Developer-site content publishing was not retrievable in this review; do not substitute the accessible Page-token examples for verification of the chosen Instagram Login endpoint/auth/media contract.

Frontend references retained from the handoff; verify installed versions and deployment constraints when implementing:

- [Next.js static exports](https://nextjs.org/docs/app/guides/static-exports)
- [Next.js server and client components](https://nextjs.org/docs/app/getting-started/server-and-client-components)
- [FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/)

UI reference: [tubeforge-dashboard.html](tubeforge-dashboard.html).


### Current user priority: Docker Short benchmark

The separate [Docker benchmark plan](docker-short-benchmark.md) records the finished-video quality objective. Its local final passed technical and visual checks; the operator confirmed the revised spoken follow line is audible. Overall superiority to the Claude reference was not established by direct comparative review. It does not complete numbered tasks 6–7 or integrate the benchmark renderer into production. Task 6 has stale-identity API protection with two focused tests passing and a live HTTP 409 stale-script check, but still needs the new child’s exact preview/final acceptance. The authorized temporary review account/session was removed. See docs/STATUS.md for the current blocker and next actions.

## 10. Bounded AI planning and repeatable local production — approved direction

This section retains the approved direction in full. It adds a future production milestone to the existing publishing roadmap; prior task evidence, approvals, and external publication gates remain in the sections above. Work on one phase at a time and record its acceptance before starting the next.

### 1. Direction and safe content preparation

Preserve the existing pipeline. AI prepares and reviews structured content; reusable local components produce videos without per-topic coding or agent supervision.

**Initial scope:** English, 30–55-second technical, history and politics Shorts.

**Flow:** topic/channel settings → evidence → reviewed script and scenes → local production → finished-video review.

#### Source isolation

Complete before Phase 2:

- Treat retrieved and supplied source material as untrusted data.
- Pass it in escaped, delimited structured fields, separately from application instructions and operator preferences.
- Restrict writer/reviewer capabilities: no shell execution, filesystem mutation or publication.
- Use strict declarative schemas. Reject executable directives, unexpected fields and instruction-like payloads attempting to control the application.
- Allow legitimate narrated commands and quotations only as inert content in designated fields.
- Test injection through source text, metadata, role delimiters and tool-use requests.

Schema checks cannot detect every injection; isolation, restricted capabilities and independent review provide separate safeguards.

Resolve sources in order: supplied material → authoritative channel sources → web discovery. Supplement unless **“Use only my sources”** is selected. Preserve snapshots, dates, hashes and claim references.

#### AI budgets and independent review

Per generation cycle:

- Maximum two writer calls, including one repair.
- Maximum two reviewer calls, including review of the repair.
- Maximum two research rounds and eight retained sources.

Repairs share the original research budget. Counters survive retries and deployments. Exhaustion blocks with findings and requires an explicit operator decision before another cycle.

The reviewer receives fresh context containing only the brief, package, source snapshots and rubric. Prefer a different already-authorized model; otherwise disclose same-model use. Review every factual claim against its source snapshot.

Explicitly load canonical yt-script resources for writing and revisions. Editorial rules remain in skills.

### 2. Local media, captions and quality

Extend existing content and video-plan contracts. AI supplies declarative scenes; local code handles voice, alignment, captions, animation, music and encoding.

Support terminals, process diagrams, comparisons, timelines, source-backed maps/charts, archival media and closing cards. Never execute generated code or arbitrary shell/FFmpeg instructions.

#### Speech mappings and reveal anchors

Persist:

1. Approved narration/display text.
2. Explicit TTS-normalized speech text.
3. Tokens aligned to actual audio.

Maintain versioned many-to-many mappings between display-token IDs and spoken spans. Handle numbers, versions, symbols and pronunciation overrides explicitly.

Reveal anchors reference a section, display-token span, narration hash and boundary. Resolve timestamps through the mapping and alignment. Ambiguous mappings block; revisions invalidate affected mappings and anchors.

#### Explicit caption styles

Offer two labelled styles:

- **Verbatim captions — default:** preserve spoken wording. Split at word boundaries; never silently paraphrase or truncate.
- **Editorial captions:** permit approved concise labels, including replacements for oversized identifiers. Clearly identify these as non-verbatim.

Normal captions use one line, at most three words and 28 visible characters.

For oversized content, show the full identifier or command in a readable scene layout. Editorial mode may use a shorter approved caption label mapped to the entire spoken span. Verbatim mode requires a compliant exact representation or a narration/layout revision; otherwise block for correction.

Store caption labels and mappings before content approval. Do not introduce editorial substitutions after approval.

#### Alignment execution and retry policy

Distinguish:

- **Transient execution failure:** retry the same configuration.
- **Repairable alignment result:** permit one alternate, predefined local alignment configuration against unchanged speech text/audio.
- **Ambiguous mapping:** block immediately.

Allow at most four alignment executions overall, with at most three execution attempts per configuration. Persist both counters.

After execution failures, retry delays are **30, 60 and 120 seconds**, according to the number of retries already scheduled.

Switching to the alternate configuration after a repairable result needs **no backoff**. Schedule it as immediately eligible, release ownership/resources, then reacquire through the normal queue. It counts toward the four-execution maximum.

A failed alternate result or exhausted allowance blocks. No estimated-timing substitution.

TTS and transient music retrieval allow three attempts with 30/60-second backoff. Missing models, invalid selected assets or absent rights/provenance block. Omit music only when explicitly permitted.

All waiting happens through durable scheduling after releasing job ownership and the heavy-work slot. No worker sleeps while holding a lease or render slot.

#### Technical and timing checks

| Measurement | Requirement |
|---|---|
| Output | 1080×1920, 30 fps, H.264/AAC, 30–55 seconds |
| Captions | Readable, within safe areas, no unintended clipping/overlap |
| Encoded audio | −15 to −13 LUFS; true peak ≤−1.0 dBTP |
| Normalization target | −14 LUFS; −1.5 dBTP |
| Integrity | Full decode and accepted content/asset hashes match |

**Routine caption validation:** validate token coverage, mapping consistency, monotonic timings, audio bounds and aligner failure/confidence signals. Failed structural or alignment checks follow the repair/block policy above.

Without an independent reference, report **“Caption timing: unverified independently.”** This alone neither blocks automatic rendering nor forces an additional review checkpoint.

The numerical drift requirement—p95 ≤150 ms and maximum ≤300 ms for absolute onset/end error—is an **acceptance-test gate against independent annotations**, not an asserted pass for every routine job. Routine estimates must identify their method and limitations.

#### Creative acceptance rubric

Acceptance videos require:

- Readability at a 360×640 playback representation without zoom.
- Scene changes/reveals tied to narration and a clear teaching purpose.
- Demonstrations that show actions/results, relationships or meaningful comparisons.
- Review of every speech gap over 700 ms; unexplained dead time fails.
- Full encoded-video viewing and listening against the approved reference.
- Recorded observations on pacing, voice/music balance, clarity and ending.
- Contact sheets, relevant timecodes, measurements and explicit pass/fail findings.

Technical checks alone do not establish creative acceptance.

### 3. Diagnostics, compatibility and revisions

#### Performance targets: enforcement disabled

| Metric | Reporting target |
|---|---|
| Prepared-media render and validation | ≤15 minutes |
| Complete local production, including TTS/alignment/assets/mixing | ≤30 minutes |
| Whole-worker cgroup peak | ≤800 MiB under the existing 1 GiB limit |

Exceedances are warnings while enforcement is disabled. Actual OOM and invalid outputs remain failures.

Report submission-to-ready wall time separately, breaking out research, model calls, queues, human waits, retries and downloads. Identify hardware and cold/warm runs.

Use kernel `memory.peak` as authoritative, including page cache. One-second sampling supports attribution only. Label shared/container-lifetime measurements when per-job isolation is unavailable.

Each job exposes diagnostics and downloadable JSONL/summary files covering stage timings, CPU, memory, I/O, cache hits, model usage, retries, quality results and enforcement settings.

#### Runtime compatibility

Persist an execution manifest with immutable image/dependency identity, renderer/templates, normalization, schemas, voice/model/font checksums, alignment and production profiles.

Retain images/assets referenced by active jobs. Never overwrite pinned assets in place.

Initially resume only with a matching runtime or an explicitly tested compatibility declaration. Otherwise block the checkpoint; offer restoration of the retained runtime or a new revision under the current runtime.

Preserve approved bytes. Behavior-changing conversions require new revisions and affected approvals.

Test matching/incompatible deployments, interrupted jobs, missing assets, lossless adapters and approval invalidation.

#### Partial rebuilds

| Change | Rebuild and approval impact |
|---|---|
| Narration/normalization/pronunciation | TTS, alignment, anchors, timed scenes, mix/render; content and video review |
| Voice/model | Audio and timing-dependent outputs; video review |
| Alignment configuration | Alignment, reveals/captions, timed scenes, mix/render; video review |
| Scene content/layout/assets | Affected scenes/render; scene-plan and video review |
| Caption layout | Captions/render; video review |
| Editorial caption wording | Content review plus captions/render and video review |
| Music/mix | Mix/render; video review |
| Renderer/profile/fonts | Affected visuals/render; video review |
| Sources/claim evidence | Content review; media rebuild only if accepted content changes |

Preserve unaffected artifacts and historical approvals. Current approvals must identify exact revision/artifact identities.

### 4. Operator workflow, readiness and retention

Support full review, script-only, video-only and automatic-render modes. Publication approval remains separate.

Keep generation readiness and creative review as separate dashboard fields:

- **Automatic-render:** becomes **“Ready — creative review not performed”** after required technical checks pass.
- **Script-only:** becomes ready after the approved content is rendered; finished-video creative review remains unperformed.
- **Full/video-only:** waits at finished-video review before becoming ready.
- Independently unverified caption timing remains visibly labelled in every applicable mode.

“Ready” means a technically valid artifact is available. It must never imply human creative approval.

Revisions remain possible at either checkpoint and after completion. Invalidate affected approvals and rebuild only dependencies.

#### Retention

For newly managed artifacts:

- Failed partial renders: seven days.
- Inactive intermediate media: fourteen days.
- Detailed diagnostics: thirty days.
- Source snapshots: while active, then 180 days after completion.
- Compact approval/hash/acceptance summaries: retained with the job.
- Approved finals: retained until operator cleanup.

Protect active jobs and pinned acceptance evidence. Use an initial configurable 50 GiB generated-storage admission budget. Clean expired eligible files, then pause new generation if necessary; never silently delete protected artifacts.

Record expiration and evidence availability. Inventory existing files before applying retention.

#### Documentation and hygiene

Consolidate into operator README, agent rules, one project plan/status record and the video rulebook. Archive history and preserve specialist references where needed.

Keep skills tracked/packaged. Align Git/Docker ignores. Run `git ls-files -ci --exclude-standard` to expose tracked-ignore drift without automatically deleting or untracking files.

Every **VERIFIED** item links to its acceptance report, checks and artifact identities.

### 5. Delivery sequence and acceptance

| Phase | Required evidence |
|---|---|
| 1. Consolidation and safety | Reconciled records, injection protections/tests, runtime/schema inventory, retention and measurement definitions |
| 2. Local production | Fixed, manually approved Docker and distinct technical fixtures; technical/creative rubric, diagnostics, bounded repairs, compatibility and recovery |
| 3. Content preparation | Verified generated packages replace fixture inputs; actual skill loading, independent claim review, bounded research and domain coverage |
| 4. Reviews/revisions | Four modes in signed-in Studio; readiness labels, invalidation, stale-anchor rejection and lease-free backoff |
| 5. Unattended generation acceptance | Tutorial, explainer, comparison, history and politics jobs finish without agent-written code or supervision; include the Git-command regression |

**Phase 5 generation runs unattended. A person subsequently watches and listens to the completed acceptance videos.** The phase becomes VERIFIED only after that inspection passes the rulebook rubric and evidence is linked. This acceptance exercise does not impose mandatory human inspection on every future automatic-render job.

Performance exceedances remain visible warnings while enforcement is disabled.

Future work: disabled local-AI-imagery option, additional languages with language-specific acceptance, long-form and publishing work; stream clipping second-last; broad dashboard/Next.js migration last.

Use **NOT STARTED, IMPLEMENTED, VERIFIED and BLOCKED** accurately. This direction was approved for documentation on 13 October 2026. Implementation remains **NOT STARTED** until its first phase begins.
