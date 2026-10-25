# Reference-codebase review: video and audio automation quality

Date: 23 October 2026. Scope: the five local checkouts in `/home/uditaswal/docker/tubeforge/git-repos`, compared with TubeForge source. The operator states permission from all owners to reuse their work. This task authorizes review and documentation only.

## Review plan and acceptance

One documentation phase: identify concrete capabilities TubeForge lacks, explain where the reference implementation helps, and propose bounded adoption experiments.

- Outcome: evidence-backed comparison of OpenMontage, VoiceStudio, youtube-agent-skill, youtube-automation-agent and youtube-autopilot.
- Acceptance: all five local revisions identified; important recommendations tied to inspected source and TubeForge integration points; existing features distinguished from gaps; future acceptance tests specified; document links and whitespace checked.
- Evidence: this report, the current plan's review entry, and the local progress-log entry.
- Out of scope: importing code or skills, changing configuration, downloading models, executing reference projects, paid calls, generating or publishing media, and declaring audiovisual improvements verified.

## Evidence boundary

This is a static source review, not a runtime benchmark or an audiovisual acceptance result. No reference application was installed or run, and no generated media was assessed. Proposed improvements below are **NOT STARTED**. Existing source is evidence of implementation, not proof of production quality.

TubeForge baseline: `4cd0cd36f4ad050f35a6a9ed6a7c916d9866aaf0`; working tree was clean at review start. Local checkouts, not moving online branches, are authoritative for this review.

| Repository | Reviewed local HEAD |
|---|---|
| OpenMontage | `e45f5b12bd46440b04f3675af9a77d0718e6a254` |
| VoiceStudio | `8772ec7eb956d59d3dde47a32f57df076310b0d1` |
| youtube-agent-skill | `a2feb2104981a375ffd4f87ee04f4f5344ac43c6` |
| youtube-automation-agent | `e26792ae00dc1ec2434faf32632896609396dfad` |
| youtube-autopilot | `69d8f0cf2872bd1467b4d09d12eb1109603345e7` |

Owner authorization is recorded above and is not a blocker to this review or a reason to request permission again. Future reuse should preserve attribution and provenance for the specific code, model and media components selected. This review does not make a separate determination about bundled third-party assets.

Reference working-tree check: OpenMontage has a pre-existing deleted `LICENSE`; the other four report clean working trees. No reference checkout was modified. The deletion is recorded as provenance, not an authorization blocker.

## What TubeForge already has

Do not rebuild these capabilities under a new name:

- Local Kokoro/Piper adapters, model-and-settings-aware voice caching, forced alignment and explicit estimated-timing fallback: `providers/voice/kokoro.py`, `rendering/shorts/prepare.py`, `pipeline/alignment.py`.
- Measured loudness, peak limiting, separate music/effect stems and speech ducking: `rendering/shorts/audio.py`. The missing audio work is performance/pronunciation and voice-specific processing, not basic normalization.
- Source-grounded scripts, scene contracts, visual routing, animated templates, caption timing, stock acquisition and a reusable local stock library: `pipeline/scene_contracts.py`, `pipeline/plates.py`, `providers/media/library.py`, `rendering/shorts/`.
- An operator-approved music catalog with checksums and rights records: `pipeline/music.py:25`. Reference Shorts still synthesize their music bed in `rendering/shorts/audio.py:17`; that is a path-integration gap, not an absent music catalog.
- Immutable single-scene revision drafts: `pipeline/scene_revisions.py:25`. Recommendations should extend this flow rather than mutate reviewed parent artifacts.
- Aggregate analytics, performance evaluation, packaging experiments and channel learning: `pipeline/performance.py:78`, `pipeline/learning.py:23`, `pipeline/optimization.py:24`. Moment-by-moment retention linked to the rendered timeline is a distinct gap.
- Leases, checkpoints, approvals, ownership fencing, cancellation and atomic promotion. Reference applications are sources of isolated capabilities, not replacements for these safeguards.

TubeForge paths in prose are relative to `src/tubeforge/` unless another root is stated. Linked references below identify exact files and starting lines.

## VoiceStudio: highest-value audio source

Keep Kokoro as the first comparison baseline. These improvements concern speech preparation, processing and evaluation; they do not require adopting another model or the full VoiceStudio application.

| Gap | Inspected source | TubeForge adaptation |
|---|---|---|
| Configurable pronunciation | [pronunciation.py:86](/home/uditaswal/docker/tubeforge/git-repos/VoiceStudio/backend/services/pronunciation.py:86), `:110`, `:259`, `:386`; applied by [generation.py:2133](/home/uditaswal/docker/tubeforge/git-repos/VoiceStudio/backend/api/routers/generation.py:2133) | Longest-first, boundary-aware, noncascading substitutions and language-scoped dictionaries. Add a versioned channel lexicon, spoken-text hash and explicit display/spoken token mapping. Include lexicon identity in the voice cache and render identity. |
| Conservative number/abbreviation expansion | [text_normalization.py:525](/home/uditaswal/docker/tubeforge/git-repos/VoiceStudio/backend/services/text_normalization.py:525), `:660`; generation applies normalization before dictionary overrides | TubeForge's [normalizer:30](/home/uditaswal/docker/tubeforge/Youtube_Video_Producer/src/tubeforge/pipeline/narration.py:30) mainly normalizes Unicode and whitespace. Introduce tested spoken forms for percentages, currency and abbreviations while preserving ambiguous identifiers/version strings and the reviewed display text. |
| Timestamped audio defects | [audio_quality.py:23](/home/uditaswal/docker/tubeforge/git-repos/VoiceStudio/backend/services/audio_quality.py:23) | Bounded 100-ms analysis locates silence, clipping, invalid samples and relative level changes. Analyze raw voice, narration and encoded delivery separately; attach warnings to scene IDs and artifact hashes. Existing integrated-loudness checks cannot locate these defects. |
| Speech chunks independent of visual scenes | [chunked_tts.py:97](/home/uditaswal/docker/tubeforge/git-repos/VoiceStudio/backend/services/chunked_tts.py:97), `:133`, `:428` | Reuse sentence/clause splitting and bounded joining ideas. TubeForge already splits phrases, but [reference preparation:54](/home/uditaswal/docker/tubeforge/Youtube_Video_Producer/src/tubeforge/rendering/shorts/prepare.py:54) synthesizes per scene, compresses internal pauses and inserts scene tails. Trial natural sentence groups and derive visual timing from speech. |
| Optional voice-only processing | [audio_dsp.py:108](/home/uditaswal/docker/tubeforge/git-repos/VoiceStudio/backend/services/audio_dsp.py:108), `:114`, `:209` | Trial high-pass filtering and gentle compression before music mixing, using existing FFmpeg where practical. Keep raw speech, processing parameters, processed hashes and the current final loudness/true-peak gate. |
| Repeatable audio comparison | [compare_generation_quality.py:13](/home/uditaswal/docker/tubeforge/git-repos/VoiceStudio/scripts/compare_generation_quality.py:13) | Adapt fixed-text/settings comparisons, serial engine loading, latency and diagnostic reporting into a Kokoro-first comparison harness. Add listener findings; bit depth and signal warnings are not perceptual quality scores. |

### Integration constraints that change the implementation plan

1. Whole-short synthesis is not a one-line switch: [alignment.py:268](/home/uditaswal/docker/tubeforge/Youtube_Video_Producer/src/tubeforge/pipeline/alignment.py:268) rejects audio longer than 30 seconds. Longer narration needs bounded alignment windows and consistent global offsets.
2. [timeline.py:45](/home/uditaswal/docker/tubeforge/Youtube_Video_Producer/src/tubeforge/rendering/shorts/timeline.py:45) requires word coverage and one-to-one display/spoken token counts. Expanding `76%` into several spoken words needs an explicit mapping; weakening exact-word validation would hide defects.
3. Pause compression, scene tails and voice speed are part of the current content contract. Evaluate an explicit alternate profile and its resulting media before changing defaults.
4. VoiceStudio's chunk joining can retain partial output after dropped chunks (`chunked_tts.py:385`). TubeForge should reject incomplete approved narration, not adopt that continuation policy.
5. VoiceStudio dictionaries allow empty replacements; its DSP can return unchanged audio if dependencies fail; normalization can fall back to raw text. Adapt those behaviors to prohibit unreviewed deletion and record applied/skipped/fallback state truthfully.
6. VoiceStudio's peak normalization is not a substitute for TubeForge's measured LUFS and encoded true-peak checks.

**Acceptance for this group:** golden text cases for numbers, names, overlapping keys and identifiers; dictionary/cache invalidation; timestamped injected defects; exact spoken coverage; listening to baseline and candidate at matched loudness; captions aligned to canonical display text; real encoded-video QA. Listen for clipped phonemes, seam clicks, pumping and changed emphasis. Keep test results distinct from operator approval.

## OpenMontage: visual selection and footage editing

| Gap or refinement | Inspected implementation | Use in TubeForge and limits |
|---|---|---|
| Visual-semantic asset ranking and diversity | [clip_search.py:274](/home/uditaswal/docker/tubeforge/git-repos/OpenMontage/tools/video/clip_search.py:274); [corpus.py:234](/home/uditaswal/docker/tubeforge/git-repos/OpenMontage/lib/corpus.py:234), `:317`, `:384` | Embed scene text, combine visual/tag similarity and diversify candidates. TubeForge currently ranks metadata/tags in `pipeline/assets.py:57`, `providers/media/pixabay.py:218` and its stock library. Add bounded local ranking after eligibility checks, with cached embeddings and deterministic fallback. Similarity is not evidence that footage proves a factual claim. |
| Subject-aware portrait crop | [face_tracker.py:190](/home/uditaswal/docker/tubeforge/git-repos/OpenMontage/tools/analysis/face_tracker.py:190), `:254`; [auto_reframe.py:334](/home/uditaswal/docker/tubeforge/git-repos/OpenMontage/tools/video/auto_reframe.py:334) | Useful for source footage; TubeForge's [clip renderer:22](/home/uditaswal/docker/tubeforge/Youtube_Video_Producer/src/tubeforge/clipping/render.py:22) center-crops statically. Reuse detection/smoothing concepts while preserving actual detection timestamps. This does not improve code cards or generated diagrams. |
| Source-footage silence edit decisions | [silence_cutter.py:111](/home/uditaswal/docker/tubeforge/git-repos/OpenMontage/tools/video/silence_cutter.py:111), `:220`, `:269` | Mark/remove/speed-up modes and padded speech intervals. Distinct from our generated-TTS pause trimming. Start with reviewable cut marks; editing requires remapped audio, subtitles and source-time provenance. |
| Subject-specific footage catalogs | [direct_clip_search.py:245](/home/uditaswal/docker/tubeforge/git-repos/OpenMontage/tools/video/direct_clip_search.py:245), `:422`; adapters in `tools/video/stock_sources/` | NASA, NOAA, ESA, NARA, Library of Congress and other adapters can expand science/history footage coverage. TubeForge already has stock acquisition; import selected adapters into existing download/provenance contracts, not a second acquisition subsystem. Each asset retains its own terms. |
| Better final-output inspection evidence | [visual_qa.py:145](/home/uditaswal/docker/tubeforge/git-repos/OpenMontage/tools/analysis/visual_qa.py:145), `:201`, `:291` | Final-video frame extraction, technical probing and short audio-window measurements are useful review artifacts. Extend our final-output reports, retaining explicit limits on what each check establishes. |
| Music-led montage experiments | [bmts_lite.py:52](/home/uditaswal/docker/tubeforge/git-repos/OpenMontage/tools/video/bmts_lite.py:52), `:318`; [bmts_lite_runner.py:26](/home/uditaswal/docker/tubeforge/git-repos/OpenMontage/tools/video/bmts_lite_runner.py:26) | Lower priority and a separate format. This is an adapter to external BMTS-Lite `worker.run`, not a contained beat-editing engine. It declares semantic selection unsupported. Preserve narration-led explanatory timing in existing Shorts. |

### Do not inherit misleading checks or crop timing

- `auto_reframe.py:356` discards real timestamps when returning crop coordinates; `:474` reconstructs approximately five samples per second. Detection gaps can shift crops away from the subject. Preserve timestamped trajectories and test missing detections and scene cuts before reuse. The inspected crop calculation also does not apply its `face_padding` argument.
- [video_compose.py:2393](/home/uditaswal/docker/tubeforge/git-repos/OpenMontage/tools/video/video_compose.py:2393) samples only four frames and calls a small PNG file a black frame. This is not robust temporal black-frame detection. Its broken-overlay/missing-asset/unreadable-text flags default to false without corresponding detection in that spotcheck.
- TubeForge [quality.py:47](/home/uditaswal/docker/tubeforge/Youtube_Video_Producer/src/tubeforge/pipeline/quality.py:47) explicitly reports black-frame analysis unavailable. Actual temporal black/freeze detection remains useful new work, but OpenMontage does not supply a proven drop-in solution. Distinguish intended black/static cards from failures.
- `tools/audio/audio_enhance.py:27` contains useful FFmpeg cleanup presets for recordings. Denoising/gating is not automatically helpful for clean synthesized speech. Do not replace our mastering or assume a preset improves intelligibility.
- Existing TubeForge motion/templates/storyboards and `om-*` skills overlap much of OpenMontage's presentation guidance. More transitions alone do not fix irrelevant visuals.

**Acceptance:** manually inspect ranked assets against exact scene claims, compare adjacent-shot repetition, and record memory/latency. For reframing, inspect complete moving/off-center/multiple-speaker clips and missing-detection intervals. For editing, verify intact phonemes and remapped captions. For temporal QA, use known defect intervals plus intentional-dark/static controls, followed by inspection of a real final video.

## youtube-agent-skill: connect what is already installed

Read-only byte comparisons found these four upstream helpers identical to their existing `.agents/skills/` copies:

| Existing helper | Useful application integration |
|---|---|
| [yt-retention/retention.py:35](/home/uditaswal/docker/tubeforge/git-repos/youtube-agent-skill/skills/yt-retention/retention.py:35) | Import a real retention CSV and transcript; produce a reviewable timestamped drop report. |
| [yt-edit/deadair.py:43](/home/uditaswal/docker/tubeforge/git-repos/youtube-agent-skill/skills/yt-edit/deadair.py:43) | Present suggested filler/dead-air/restart cuts for source footage, not automatic edits. |
| [yt-chapters/chapters.py:1](/home/uditaswal/docker/tubeforge/git-repos/youtube-agent-skill/skills/yt-chapters/chapters.py:1) | Validate chapter candidates for eligible long-form exports. |
| [yt-viral/swipe.py:32](/home/uditaswal/docker/tubeforge/git-repos/youtube-agent-skill/skills/yt-viral/swipe.py:32) | Rank niche outliers from supplied real measurements, with source/date context. |

No runtime callers for those helper filenames were found in TubeForge `src/tubeforge`. The opportunity is workflow integration and discoverability, not another installation. Preserve the sole canonical `yt-script`; no competing narration skill was loaded for this review.

**Hardening needed before automation:** `deadair.py:25` calls `.get()` before checking whether parsed JSON is a list, so list input fails. Its removed-duration sum counts overlapping cut intervals separately (`:70`); its English-only normalization (`:41`) weakens multilingual repeat detection. These defects also exist in our identical copy. The utility emits an edit-decision list, not edited media. None was fixed in this documentation-only task.

**Acceptance:** object/list JSON, overlapping intervals, Unicode text, intentional repetition, invalid durations, consistent units and explicit unavailable-data handling. Keep recommendations human-reviewable; do not claim performance or removed duration from unchecked inputs.

## youtube-automation-agent: connect measured outcomes to scenes

### Highest-value addition: actual retention curves on the rendered timeline

[analytics-optimization-agent.js:776](/home/uditaswal/docker/tubeforge/git-repos/youtube-automation-agent/agents/analytics-optimization-agent.js:776) requests retention metrics by elapsed-video ratio and reports unavailability on failure. [scene-retention-engine.js:10](/home/uditaswal/docker/tubeforge/git-repos/youtube-automation-agent/utils/scene-retention-engine.js:10), `:97`, `:134`, `:154` excludes simulated/unavailable evidence, maps curves to scenes and proposes experiments around drops, replays and holds.

TubeForge already evaluates aggregate retention and packaging results; it lacks this inspected curve-to-scene feedback path. Use the exact published artifact's measured timeline and scene roles, expose timestamped evidence, and turn findings into reviewed next-video experiments. Do not copy the upstream proportional rescaling of estimated scene lengths (`:71`), which can attribute a drop to the wrong scene. Low-view thresholds are heuristics; correlation does not prove a scene caused abandonment.

**Acceptance:** known curve fixtures map to correct measured scenes; sparse, missing and simulated inputs produce no confident diagnosis; a real channel export produces inspectable timestamped evidence. No automatic rewriting or publication follows from a score.

### Existing workflows to refine, not rebuild

- [scene-repair-service.js:197](/home/uditaswal/docker/tubeforge/git-repos/youtube-automation-agent/utils/scene-repair-service.js:197), `:263`, `:384`, `:530` distinguishes stale visual/narration components and records regeneration cost/change evidence. TubeForge already forks immutable scene revisions. Useful follow-up: measure whether a visual-only change can preserve valid speech/alignment and report expected regeneration work. Do not import mutable scene edits into our approved-parent artifacts.
- [shorts-repurposing-service.js:167](/home/uditaswal/docker/tubeforge/git-repos/youtube-automation-agent/utils/shorts-repurposing-service.js:167), `:209`, `:247` renders and validates crop/blur/stacked clip layouts with approval handling. TubeForge already has source intake, energy-based highlights and a real render path: [analysis.py:20](/home/uditaswal/docker/tubeforge/Youtube_Video_Producer/src/tubeforge/clipping/analysis.py:20), [orchestrator.py:256](/home/uditaswal/docker/tubeforge/Youtube_Video_Producer/src/tubeforge/pipeline/orchestrator.py:256). The gaps are better framing/layout choices and semantically self-contained selection, not an absent clipping workflow.
- The external clip selector uses evenly spaced scene anchors (`shorts-repurposing-service.js:92`), while TubeForge uses audio energy. Neither establishes that the excerpt makes sense on its own. The external seven-word equal-duration captions (`:231`) are not an upgrade to measured speech timing. Reuse layout ideas and source-span evidence; evaluate highlight meaning separately.
- Preserve simulated/unavailable states. This repository contains genuine API implementations but also simulated analytics (`analytics-optimization-agent.js:711`) and media fallbacks (`utils/ai-video-generator.js:928`). Mock output must never become production quality or analytics evidence.

**Acceptance for refinements:** visual-only edits preserve valid narration; narration edits invalidate affected timing/captions; changed output needs new approval; restart/cancel cannot promote stale output. Source clips must be understandable alone, with intact words, visible subjects and measured caption timing.

## youtube-autopilot: editorial ideas, not a demonstrated media engine

Useful inspected planning code:

- [cinematographer.py:125](/home/uditaswal/docker/tubeforge/git-repos/youtube-autopilot/yt_autopilot/agents/cinematographer.py:125), `:452`, `:568` describes shots using narration, position, prior shot, lighting and emotion. Adapt a small vocabulary of purposeful shot choices into our existing scene contracts. TubeForge already has subject/purpose/composition; the opportunity is controlled cross-scene variety, not another storyboard system. Upstream variety scores are model self-reports (`:183`) and fallback shot cycling (`:208`) is not evidence of visual meaning. Audio cues are descriptions, not signal processing.
- [memory_store.py:127](/home/uditaswal/docker/tubeforge/git-repos/youtube-autopilot/yt_autopilot/core/memory_store.py:127) stores recent titles; [trend_hunter.py:126](/home/uditaswal/docker/tubeforge/git-repos/youtube-autopilot/yt_autopilot/agents/trend_hunter.py:126) filters repeated topics; [series_manager.py:86](/home/uditaswal/docker/tubeforge/git-repos/youtube-autopilot/yt_autopilot/core/series_manager.py:86) loads YAML series formats. Consider reviewed recurring formats and channel-specific recently-covered-angle memory supplied to the existing writer. Title overlap is only a duplicate hint; retain legitimate follow-ups and isolate channels. Series matching at `:58` uses English/Italian keywords despite broader descriptive claims.

**Do not treat the README as implementation evidence.** The inspected tracked inventory does not contain the advertised `produce_render_publish.py` or matching render/TTS/Veo/FFmpeg modules. [youtube_analytics.py:15](/home/uditaswal/docker/tubeforge/git-repos/youtube-autopilot/yt_autopilot/services/youtube_analytics.py:15) is a TODO/mock service and generates random metrics at `:80`. It provides no trustworthy production feedback or demonstrated superior voice/rendering path in this checkout. Embedded platform/monetization assumptions in `agents/duration_strategist.py:89` were not verified and should not become product policy.

**Acceptance:** compare scene plans/contact sheets and real outputs for meaningful variety; flag repeated angles without rejecting useful follow-ups; test multilingual/channel isolation; keep all mock metrics excluded. Do not import competing script agents or fixed intros/outros that weaken the current short-form hook.

## Recommended adoption order

These are recommendations for a future implementation task, not an expansion of this task's authorization. Each row is **NOT STARTED** as an adoption experiment; existing related source remains as described above. Relative effort includes integration and evidence, not just copying a helper.

| Order | One user-visible outcome | Required acceptance artifact | Effort / dependency |
|---|---|---|---|
| 1 | A trustworthy baseline and localized narration-defect report | Same approved passage, raw/current voice and encoded result, hashes/settings/runtime/memory, timestamped defect fixtures and listener notes | Small–medium; local Kokoro and current QA. Establish evidence before changing defaults. |
| 2 | Correct, consistent pronunciation with unchanged caption spelling | Lexicon/normalization cases, explicit spoken/display mappings, cache/review invalidation checks, real aligned comparison video | Medium–large; contract and timeline changes. Include signed-in dictionary/review workflow testing if controls are exposed. |
| 3 | More continuous, natural narration | Current vs sentence-grouped narration, bounded alignment windows, exact coverage and seams checked, then optional loudness-matched DSP comparison | Medium–large; current 30-second alignment limit and profile/tail invariants. Evaluate grouping and DSP separately to identify the cause of improvement. |
| 4 | Footage that better matches the explanation and repeats less | Fixed scene set, candidate thumbnails, baseline vs visual-semantic ranks, reviewed real montage/video and recorded resource use | Medium–large; embedding model availability, memory budget and unchanged asset provenance. Trial cached/offline ranking first. |
| 5 | Evidence showing where viewers leave | Real CSV or API curve bound to exact published timeline, low-data tests, timestamped scene report and reviewed next-video experiment | Medium; requires genuine channel data. Start with our existing retention helper after input hardening. |

After these: final-output temporal defect detection; subject-aware crops and approved source-footage cuts; selected subject-specific stock adapters; channel editorial memory and purposeful shot vocabulary. Music-led montage is a separate, lower-priority format with an external dependency. Component-aware revision cost/reuse is an optimization of an existing workflow, not a quality prerequisite.

### Integration rules for later implementation

- Keep application-owned rendering, scheduling, analytics and publishing. Reuse pure algorithms/adapters where possible instead of importing complete agent runtimes or their orchestration.
- Bind every material treatment to approved text/scene identity, model/asset hashes and versioned parameters. Changes invalidate the affected audio, timing, render and review identities; never silently reuse stale approvals.
- Preserve worker ownership, checkpoints, memory admission, cancellation and atomic promotion. Model downloads and remote generation are not required to start the Kokoro-first work.
- Any exposed control needs truthful pending/success/failure/fallback states and focused signed-in API/UI validation. Review-only recommendations must remain distinguishable from applied changes.
- Keep technical checks, heuristic scores, model judgments, human listening and operator approval separate. A valid WAV, diverse embedding score or model-written cinematic prompt is not audiovisual acceptance.
- No runtime, provider, skill or publishing configuration changed during this review. No real performance improvement is claimed.

## Review validation

The review checks source references and overlap against the local snapshots. It does not run any reference test suite, model, renderer or service; such execution would not establish the proposed integration's quality and is outside this task. Documentation acceptance requires all five revisions, valid local file/line links, consistent status wording and a clean whitespace check. The evidence-log entry records the actual check results.

## Addendum 24 Oct 2026: operator retention rules and overlap with this review

Added by Claude on `dev` (append-only, to keep merge conflicts with the Codex branch small). Full mapping and measurements: `docs/video-quality/plan-m0-m9.md` §1b and milestone M1b. No code from this review was imported and no performance improvement is claimed.

The operator's four rules: (R1) a visual hook in the first 2 seconds and no greeting openers, (R2) a last sentence that connects back into the first, (R3) no pauses in the voiceover and a visual change every 1.5–2.5 s, (R4) avoid low-effort/identical templates. Their stated effects (retention above 100 %, faster distribution) are unverified hypotheses.

| Rule | Overlaps with this review | Difference / conflict | Suggested owner |
|---|---|---|---|
| R1 hook | Adoption order row 4 (footage that matches the explanation) and the rule not to import "fixed intros/outros that weaken the current short-form hook" (youtube-autopilot section) | R1 adds a hard requirement: scene 1 carries a visual and the first large change lands inside 2 s; today the hook scene is visually static for about 4.4 s on job `0072a2f4…`. Selected stock still needs the claim-matching checks above. | Claude: craft/QA checks (M1b). Codex: footage ranking (row 4). |
| R2 loop | none directly; the review's "do not import fixed intros/outros" also argues against a bolt-on loop clip | **Decided 24 Oct: no follow request, the video loops.** New `loop` closing template (open-ended last sentence, last frame equals first, no follow/subscribe text); implemented on `dev` in `rendering/shorts/schema.py`, `layout.py`, `providers/content/craft.py`. Audio tails are already 0.18 s, so no gap needs removing. If whole-short synthesis (row 3) changes how scene boundaries are joined, the seam between the last and first words must be re-checked. | Claude: done on `dev`. Codex: check the seam if narration synthesis changes. |
| R3 pacing | Constraint 3 (pause compression, scene tails and voice speed are part of the content contract), adoption row 3 (sentence-grouped, more continuous narration), the 30-second alignment limit | "Remove all pauses" is stronger than row 3 and would change the `Timeline` rule that requires a 0.12–0.4 s speech tail. Treat it as an explicit alternate profile evaluated by listening at matched loudness, as this review already requires, with a measured max silence gap and a visual-change interval check added to QA. Visual cuts every 1.5–2.5 s overlap with the motion-engine milestone (M4), not with the audio rows. | Codex: voice profile and grouping (rows 1–3). Claude: measurement and QA gate (M0/M1b). |
| R4 variety | youtube-autopilot "recently covered angle" memory and recurring formats; row 4 (repeats less); "channel editorial memory and purposeful shot vocabulary" listed after the adoption rows | Same goal, two layers: this review covers *topic/angle* memory and *shot* variety; M1b adds a *script/template-sequence* similarity gate and a limit on repeated templates. They should share one stored per-channel history rather than create two. "Curated audio" is limited to licensed or no-claim sources (decision of 22 Oct), so music is not a variety lever yet; sound effects are. | Shared: one history store; Codex proposes schema, Claude adds the gates. |

Integration rules from this review still apply to all four: bind every treatment to approved text/scene identity, keep technical checks, heuristic scores and human approval separate, and give any exposed control truthful pending/success/failure states.
