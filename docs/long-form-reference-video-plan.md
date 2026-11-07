# 10–15 minute videos and original videos from a reference link

Planning baseline: 6 November 2026, local `dev` commit `a330748`.
Planning branch: `codex/long-form-reference-plan`.

This is an implementation specification, not a claim that long-form production works today. The single current implementation-status tracker remains `doc-internal/design_doc/tubeforge-publishing-design.md`; this versioned document defines tasks and acceptance. No live generation, paid service, upload or deployment is authorized by this plan. No reference URL was supplied for this planning task.

Design references: [editorial/prompt proposal](long-form-editorial-proposal.md), [LF0 local acceptance evidence](long-form-lf0-acceptance.md). These define the new profile without enabling live generation.

## 1. Intended result

Paste one public YouTube link, select the channel and a 10, 12 or 15 minute target, and receive an original, grounded video for review: a strong opening, coherent explanation, useful examples, native landscape visuals, intelligible narration, captions, chapters, title options and thumbnail candidates. Use channel defaults for audience, language, voice and writer; ask only when a missing input prevents a sound result.

The reference supplies the topic and an editorial benchmark. It is not automatically factual evidence, a source of reusable footage, or a script to paraphrase. The new video must offer a demonstrable improvement: clearer explanation, a verified correction/update, a reproducible example, an overlooked trade-off, or a more useful decision framework. “Better” is an editorial hypothesis until audience data supports it; hooks and checklists cannot guarantee views.

Reuse the existing job, source, approval, asset, voice, rendering and delivery architecture. Add a versioned long-form profile and reference-intake adapter. Keep one canonical ContentPackage/VideoPlan and the existing state machine. Do not revive retired formats or stretch a portrait Short to landscape.

## 2. What the repository already supports, and what blocks this

All paths below are repository-relative. Recheck these observations after rebasing; the baseline does not include unmerged feature branches.

| Area | Evidence at baseline | Required change |
|---|---|---|
| General content contract | `src/tubeforge/domain/contracts.py`: ContentRequest allows 25–7,200 seconds; ContentPackage allows up to 500 claims, sections and scenes | Generic capacity is not a working long-form pipeline. Add explicit profile validation, chapter identities and bounded scene density |
| Production profile | `config/production.yaml`: reference-short preset is 30–90 seconds, 9:16, `m6-content-v8`; versions v1–v7 are retired | New opt-in profile/version, native 16:9, 600–900 seconds; retain retirement guards |
| Short schema | `rendering/shorts/schema.py`: ShortsTopic has 6–20 scenes and hook/loop/CTA constraints; v8 request validator requires portrait and at most 90 seconds | Keep Shorts unchanged; do not apply its word count, loop ending or scene ceiling to long-form |
| Reference URL | Generated requests forbid `source_url`; source_clip requires it (`domain/contracts.py`) | Separate reference-intake contract with immutable provenance; do not misuse source_clip |
| Existing clip workflow | `pipeline/orchestrator.py` source-clip branch downloads media and selects audio-energy highlights | Reuse safe acquisition primitives where appropriate, but original-script adaptation is a different operation |
| Landscape | `rendering/animated_landscape.py`; short PHP benchmark in `docs/video-direction-review.md` explicitly does not enable retired production | Reuse tested teaching primitives; prove native landscape composition, long-duration memory use and real workflow integration |
| Prompts/runners | `providers/content/prompts.py`, `youtube_skills.py`, host runners; Codex prompt build uses 60,000-character ceiling; Claude default/config 90,000; Claude request envelope limit 65,536 bytes | Measure complete input/schema/output envelopes. A character limit is neither a token budget nor an output allowance. Audit both runners, protocol, sockets, timeouts and reservations |
| Claude budget | `src/tubeforge/claude_budget.py`: defaults 40 calls / $8 per rolling 24h, $1.50 per call; environment can override | Preserve caps; report effective values. Local dollar accounting does not reveal subscription allowance |
| Approval/recovery | Existing durable jobs, source/scene hashes, leases, exact reviewed artifacts and stage checkpoints | Extend dependency keys for reference, profile, chapter, voice and renderer identities; keep fencing/cancellation/atomic promotion |
| Packaging | `pipeline/thumbnail.py`, `om-social-delivery`: local thumbnail composition and exactly two description lines | Profile-specific long-form description with chapters, sources and credits; retain current Short behavior |

Some skill resources contain older Shorts numbers and endings that differ from the binding content contract and current code. Resolve precedence explicitly during the profile task; never import those numbers into long-form or quietly change the existing Short profile.

## 3. Link to original video: step-by-step workflow

1. **Capture once.** Validate/canonicalize the public URL; fetch bounded metadata and accessible caption text with language/timecodes. Record video ID, title, creator, duration, retrieval time, transcript origin and hashes. Use redirects/URL checks that reject private-network targets; impose size/time limits. Source text is untrusted data, never instructions.
2. **Handle missing access honestly.** Missing/private/deleted video, disabled captions or failed retrieval produces a visible actionable state. Allow a supplied transcript; local transcription of authorized media is an explicit fallback with compute/storage cost. Do not silently use a title as if the video was watched, or bypass authentication/paywalls.
3. **Build a compact reference brief.** Extract audience, promise, questions answered, key claims, examples, explanation order and unresolved questions, with timestamped evidence. Store the full transcript once; pass a small indexed digest to the writer. Inspect a few relevant frames only when available and needed to understand a visual claim. Record when visual/audio inspection was unavailable.
4. **Research once per exact brief.** Verify material factual claims against primary sources; retain bounded excerpts and source hashes. Separate `reference_observation` from `verified_claim`. Mark unsupported, conflicting and outdated claims. An inference about an audience need is a hypothesis, not analytics. Insufficient evidence stops before script/TTS.
5. **Choose the improvement.** Produce a short table: reference timestamp/observation → viewer problem → our change → supporting evidence → planned scene. Choose one clear audience promise and two or three substantive additions. Avoid padding a five-minute idea to fifteen minutes.
6. **Plan the story.** Use canonical yt-script, channel voice and verified claim packet. Generate five distinct hooks and a chapter outline, then score hooks locally. The first 15 seconds confirms the title promise and previews credible value; by 45 seconds the explanation is underway. Prefer an early useful result, then deeper mechanism and trade-offs, followed by an explicit final payoff.
7. **Write one coherent script.** Target roughly 1,350–2,250 spoken words at an initial planning pace of 135–150 words/minute. Actual speech and purposeful pauses decide duration. Use about 5–8 chapters and 30–60 purposeful teaching beats as initial design ranges, not universal rules. Each chapter resolves a question and leads naturally to the next. No repeated intro/CTA per chapter, fabricated personal experience, fake urgency, or invented demonstrations.
8. **Review grounding, originality and usefulness.** Run local schema, citation, repetition, hook and title checks, followed by one bounded editorial/claim review. Compare wording and distinctive structure against the reference transcript, not just selected evidence excerpts. Shingle overlap is a flag, not an originality verdict or legal clearance. Reject close paraphrase, copied distinctive hooks/examples/order/thumbnail composition; retain necessary factual terms. Save reasons and timestamped comparisons. Only one repair allowance remains after a failed first draft; do not multiply attempts by chapter or switch providers to reset them.
9. **Approve exact narration.** Show source-linked claims, improvement table, top two scored hooks, script, estimated duration, provider and usage. A revision invalidates the exact affected approvals. Research and model review never constitute operator approval.
10. **Storyboard and produce locally.** Bind visual plans to accepted script/scene hashes. Use real evidence, original diagrams, safe reproducible demonstrations, licensed assets and purposeful comparisons. Do not copy the reference's audio, music, footage or thumbnail. Reference linkage does not grant reuse rights. Default to existing local assets and renderers; optional generated images require separate authorization and measured benefit.
11. **Package the result.** Generate ten coordinated title options, score locally, show the top three and compose two or three thumbnail candidates. Inspect at about 168×94 pixels using om-thumbnail-craft. One focal point, readable 2–3 words, no duplicated title text, truthful promise. Derive chapter timestamps from final aligned narration; use yt-seo for useful description, sources and credits.
12. **Review/export.** Preview, inspect the complete final, validate artifact hashes and export the reviewed bundle through the existing workflow. Nothing is automatically approved or published. Optional Shorts come from the accepted original long-form video, not the reference creator's footage.

### Creative acceptance for the first pilot

A reviewer must identify the specific promise, see it delivered, and name the concrete improvements over the reference. Every factual beat must resolve to supporting evidence; every teaching scene must show something meaningful. Review the opening, each chapter transition, examples, conclusion and the entire audio/video—not just contact sheets. Record timecoded defects for unclear explanation, redundant narration, monotonous cards, illegible text and misleading demonstrations. If the idea only supports eight good minutes, revise the brief instead of stretching it.

## 4. Long-form technical design

Proposed profile name: `long-form-v1`; proposed prompt identity: `m6-content-long-v1`. These are design names, not accepted configuration values today.

- Final: 1920×1080, 30 fps, H.264/AAC; preview: native 1280×720. Target actual runtime 600–900 seconds. Use measured speech before approving pacing. Keep the configured audio target explicit; proposed encoded acceptance is −15 to −13 LUFS and ≤−1.5 dBTP, pending profile fixtures and listening review.
- Extend existing contracts with ordered chapter IDs, stable scene IDs, claim IDs, reference identity, source-packet hash, profile version and accepted package hash. Chapter timing is calculated from audio; the writer does not guess word timestamps or pixel geometry.
- Start with one script draft and one compact scene plan. If output cannot fit, use a predeclared bounded chapter-writing protocol with a shared outline, glossary and claim map. A logical script attempt spans the entire assembly; chunk calls do not grant new repair allowances. Do not adopt chunked writing merely because the video is long.
- Render and checkpoint bounded scenes or chapters sequentially. Load TTS, alignment and browser-heavy stages within the memory budget; avoid retaining a whole 15-minute frame sequence. Reuse unchanged audio/visual chunks and stream the final assembly. Benchmark actual disk, wall time and peak RSS before setting production timeouts.
- Persist narration, alignment, source/asset manifests, scene chunks and assembly manifests. Cache keys include content and renderer/profile/tool versions. Reordering changes timeline/assembly identity; narration edits invalidate affected audio/captions/reveals and final approvals. New sources or changed claim meaning require review even if media bytes can be reused.
- Keep heartbeats alive during long subprocesses; cancellation terminates child processes, stale owners cannot promote artifacts, interrupted output stays temporary. Resume only validated chunks with matching hashes. Never re-run research/writing merely because encoding failed.
- Full-duration QA must detect decode errors, missing/repeated chunks, black intervals, unexpected silence, clipping, cumulative caption drift and broken chapter boundaries. Intentional holds remain reviewable advisories, not automatic motion failures.
- Use a landscape caption treatment and readable diagrams, not portrait safe zones/font sizes. Show one idea at a time, varying terminal, comparison, diagram, evidence and demonstration layouts when the content calls for it.
- Chapter export starts at 00:00, has at least three entries, is increasing and gives every chapter at least ten seconds, including the last. Validate against final duration, not estimated script timing. Recheck destination requirements before a real upload.

## 5. Skills: use what helps, at the stage where it helps

The content skill definitions were reviewed for this plan; their scoring tools were not run because there is no candidate script, title, transcript or video. Before execution, read each selected skill's required resources and review its helper scripts. Keep the canonical source at `.agents/skills/yt-script`; changes to hashed production resources need installed-wheel hash verification before host use.

| Skill | Application |
|---|---|
| yt-script | Sole production narration/hook authority; five hooks, local hookscore.py, source-grounded script and scene directions; load SKILL.md, automation.md, hooks.json and hookscore.py |
| yt-package | Ten title options, title.py checks, coordinated thumbnail brief; score is a heuristic |
| om-thumbnail-craft | Review actual local thumbnail candidates at phone size, compare 2–3, record winner rationale; no image-generation service |
| yt-seo | Audience queries, useful opening description, sources/credits; do not spend heavily on tags |
| yt-chapters | Final transcript/alignment boundaries, chapters.py validation, concise meaningful chapter names |
| yt-edit | Timed transcript recommendations for dead air/repetition; preserve intentional explanation/demo pauses |
| om-storyboard | Post-approval visual purpose, evidence and asset plan; cannot rewrite narration |
| om-video-quality | qa_check.py plus full watch/listen, source fidelity, captions, technical and creative review |
| om-social-delivery | Exact reviewed local bundle and destination handoff; add tested long-form metadata policy before chapters are supported |
| yt-shorts / om-short-production | Optional later derivative Shorts from our accepted master; keep existing Short contract |
| yt-retention | Only when real retention exports exist; compare the channel's own baseline, do not treat generic thresholds as guarantees |
| yt-viral | Optional public comparison set with at least four videos/channel; relative views are descriptive, not proof of why a video worked |
| yt-audit | Optional channel review when actual titles/thumbnails/openings and channel context exist |
| yt-comment | Optional supplied real comments for unanswered questions; no automatic replies |
| yt-plan | Optional publishing calendar after capacity and content are known; outside first-video acceptance |
| viral-short-form | Optional reference for derivative Shorts only; never a competing production writer |
| OpenAI Docs | Official usage-limit verification; keep observed account allowance separate from estimates |
| Writing-style guidance | Plain, direct planning prose from the user's request; no retrieved personal writing samples were available |

Use frontend skills only when implementing/reviewing the dashboard: choose the applicable existing-system guidance, preserve navy components, and inspect the signed-in workflow. Imagegen/EveryGen, Sites, Expo, pets, plugin installation and unrelated backend tools do not improve this document or the default local video path. Loading every available skill into every generation would increase tokens and introduce conflicting instructions. Keep optional analytics/derivatives outside the minimal production prompt.

## 6. Token budget and the five-hour question

**A 10–15 minute video need not consume an entire allowance, but this cannot be guaranteed from runtime.** We do not know the operator's subscription tier, remaining allowance, concurrent usage or effective model settings. Building this feature is separate from running it; development/reviews can consume much more than a single production script. During this planning task, a delegated architecture review returned a usage-limit error; that is evidence of current session constraints, not a measurement of long-form generation cost.

Official documentation checked 6 November 2026:

- [OpenAI pricing and usage](https://learn.chatgpt.com/docs/pricing): allowance depends on model, task size/context and execution mode; inspect the usage dashboard or CLI `/status`. The current page lists five-hour estimates for Plus/Standard Business and says Pro currently has no five-hour limit; weekly limits may apply. Do not assume every Codex account has the same five-hour quota.
- [Claude Code plan usage](https://support.claude.com/en/articles/11145838-use-claude-code-with-your-pro-max-or-ultra-plan): Pro/Max have five-hour and weekly limits shared with other Claude use; verified Ultra accounts have no five-hour limit. API-key authentication can instead incur API charges. Verify actual account/auth mode before any production run.

Neither source provides a universal “one video = X% of subscription” conversion. Context-window capacity, cumulative tokens, local dollar caps and subscription usage are different quantities. Do not divide estimated tokens by a guessed five-hour token allowance. Keep paid overage/API fallback disabled unless separately authorized.

### Proposed lean run envelope (planning estimates, not measured consumption)

For English narration, 1,350–2,250 words is roughly 1,800–3,000 output tokens using an illustrative 1.33 tokens/word. Technical identifiers, other languages, JSON and reasoning change this substantially. Count the actual serialized prompts with a model-appropriate tokenizer before dispatch.

| Stage | Planned AI calls | Input tokens across stage | Output tokens across stage |
|---|---:|---:|---:|
| Reference analysis + bounded primary-source research | 1 | 6k–12k | 1k–2k |
| Canonical script, outline, 5 hooks, 10 titles | 1 | 10k–18k | 5k–8k |
| Independent claim/editorial review | 1 | 8k–14k | 1k–2k |
| Scene-plan completion after narration acceptance, metadata | 1 | 8k–14k | 3k–6k |
| Normal run total | 4 | 32k–58k | 10k–18k |
| Reserved targeted repair (only if needed) | at most 1 | 8k–14k | 2k–6k |
| Total with reserve | at most 5 | 40k–72k | 12k–24k |

These are proposed visible-text budgets for a compact new long-form prompt, not current runner measurements. They exclude unknown reasoning/internal search overhead and image-token usage. They assume research fits one invocation and references are accessible. Current embedded instructions alone are documented in config as roughly 47k characters; existing multi-call writers-room behavior can exceed this lean design. Measure it before promising savings. Research, review and scene planning must have separately bounded calls while preserving the existing two-attempt narration rule. An editorial rewrite consumes the repair; metadata/scene calls cannot smuggle in extra narration rewrites.

### How to keep usage low without weakening quality

1. Cache reference/transcript and research by exact brief + source content + language + extractor version. Reference refresh creates a new evidence revision; TTL is not permission to silently change an approved packet.
2. Store evidence once; send bounded claim excerpts and IDs, not repeated full transcripts, raw HTML, entire skill libraries or repository dumps. Never reduce the evidence below what a claim needs.
3. Use one writer with one compact independent review. Do not have Codex and Claude both rewrite the same video. Separate development tasks are useful; duplicate creative passes are expensive.
4. Run schema checks, hook/title scores, repetition checks, TTS, alignment, rendering, chapter timestamp generation and artifact QA locally. These do not consume writer tokens; asking an AI to inspect images/reports still does.
5. Reuse accepted checkpoints. Repair only cited failures; a renderer retry makes zero new writer calls. Keep output envelopes free of immutable source/request echoes.
6. Record per-stage provider/model, exact prompt resource version, calls, input/output/cached/reasoning tokens when supplied, estimated versus observed cost and failure category. Unknown usage remains unknown, never zero.
7. On quota exhaustion, checkpoint and wait for reset or an explicitly selected provider. Cross-provider fallback shares attempts and evidence and must follow the reviewed routing policy. Do not reset exhausted allowances or silently charge an API key.

### Calibration before claiming affordability

Run one authorized representative 10-minute pilot with account usage snapshots before/after, no unrelated concurrent work if practical, and effective model/auth settings recorded without secrets. Capture runner usage per stage, local cap balances, elapsed time, peak memory and render time. Label dashboard deltas approximate if other work or delayed reporting is involved. Reserve headroom for the one repair and other work; a proposed 25% reserve is a local planning choice, not a provider guarantee. Repeat at 15 minutes only after the first pilot passes. A fresh development session with compact handoff is preferable to repeatedly carrying a huge chat, but it does not reset provider quotas.

## 7. Implementation sequence and acceptance

Execute one phase at a time. Within an active phase, Codex and Claude may work concurrently only on assigned non-overlapping files after the interface is frozen. Report acceptance before moving on. Every phase keeps Shorts regression tests and exact-artifact approval rules. Status is recorded only in the current plan, not duplicated here.

| Phase | User-visible outcome and concrete tasks | Acceptance test and evidence | Out of scope |
|---|---|---|---|
| LF0: contracts and budget baseline | Freeze long-form profile, reference record, chapter/scene mapping, usage envelope and API fixtures; inventory limits in both host protocols and QA; reconcile skill precedence and description policy | Schema fixtures accept 600/720/900s landscape, reject wrong format/out-of-range/stale citations; Short fixtures unchanged; serialized payload measurements and protocol/output-limit report; reviewed task ownership | Live writers, renderer rollout |
| LF1: link intake | Paste a reference, see captured metadata/transcript, extraction state, limitations and proposed improvement brief; cache once | Fixture tests for captions, missing transcript, redirects/private addresses, timeout, oversized text, language, prompt injection and duplicate intake; signed-in desktop/tablet/mobile intake review; hashed reference manifest | Copying footage, paid transcription, full video writing |
| LF2: grounded long-form writing | Primary-source packet, original outline/script, five hooks, ten titles, bounded review and usage display; add canonical long-form skill/profile resources | Stub contracts + installed-wheel hash check; one authorized real script reviewed against reference and primary sources; hook/title reports, originality rationale and measured usage; rejected drafts visible; two failures stop | Rendering, silent model changes, per-chapter retry resets |
| LF3: local long-form production | Narrate/alignment, native landscape scene chunks, resumable preview/final, full-duration QA; first prove 60–90s representative excerpt, then 10 minutes | Real 600s+ 1920×1080 master; full decode, loudness, caption/reveal timing and complete watch/listen; memory/disk/time report; kill/resume/cancel and stale-owner tests; unchanged chunks reused without writer calls | Batch concurrency, decorative AI video, removing review gates |
| LF4: complete review/export | Chapter/scene navigation, revisions with exact reapproval, title/thumbnail candidates, long description/chapters and local export bundle | Signed-in full flow at sole developer URL `http://127.0.0.1:62065`; desktop/tablet/mobile; edit one scene, invalidate approval, rebuild only dependencies; chapter validator; actual thumbnail inspection; checksum-valid bundle | Upload, schedule execution, automatic approval |
| LF5: real 10–15 minute acceptance | Reference-to-export pilot at 10 minutes, then different topic at 15; compare usefulness, originality and quota cost | Both real files inspected fully with timecoded reports, qa_check.py plus long-form-specific checks, complete listening and source audit; restart evidence; measured allowance snapshots and operator review | Claiming views/retention without analytics, unattended batch |
| LF6: optional feedback/derivatives | Use real retention/comments; propose focused improvements and standalone Shorts from our master | Actual supplied/authorized analytics with timestamps; lineage and separate Short QA; no fabricated outcomes | New platform integrations or guaranteed growth |

Suggested existing regression starting points: `tests/test_reference_content.py`, `tests/test_reference_shorts.py`, `tests/test_content_research.py`, `tests/test_sources.py`, `tests/test_source_redirects.py`, `tests/test_source_clips.py`, `tests/test_source_clip_rendering.py`, `tests/test_host_codex_runner.py`, `tests/test_host_claude_runner_connections.py`, `tests/test_runner_failure_codes.py`, `tests/test_reference_motion_workflow.py`, `tests/test_batch_thumbnails.py`. Add focused long-form tests to the owning module. Choose the exact relevant group per phase; do not repeatedly run every suite after small edits.

For every real pilot run `.agents/skills/om-video-quality/qa_check.py <artifact-folder>` and apply the skill checklist. First make the checker profile-aware with tests; a Short-only warning or inappropriate threshold must not be silently waived. Technical fixture success remains IMPLEMENTED until the phase's required real-artifact and browser evidence passes. After two repairs to the same root problem or 45 minutes of active debugging, stop with evidence, two options and a recommendation, per AGENTS.md.

## 8. Codex / Claude assignments without conflicting edits

Use this branch for the planning checkpoint. Implementation work starts from a shared accepted contract commit in separate worktrees and feature branches, e.g. `codex/long-form-core` and `codex/long-form-content`. Do not run two writers in the same checkout, change the shared `dev` worktree under the running services, or assume two agents with different branches have isolated databases/artifacts.

| Owner | Exclusive files / responsibility | Contract with other lane |
|---|---|---|
| Codex: integrator/core | `domain/contracts.py`, `core/config.py`, DB migrations/repositories, `api/app.py`, `pipeline/orchestrator.py`, shared source adapters and deployment config | Owns frozen request/response schemas, job/checkpoint keys, exact approvals and migrations; Claude requests interface changes instead of editing these |
| Claude: content/craft | Canonical `yt-script` resources, `providers/content/prompts.py`, `youtube_skills.py`, new long-form content module/tests, packaging guidance | Consumes frozen schema/evidence; returns structured script/hook/title data; no new approval system or narrator |
| Codex: media integration | Voice/alignment orchestration, renderer integration, long-form chunk cache/assembly, cancellation/lease tests, QA profile routing | Consumes accepted scene and timing contract; no script rewriting |
| Claude: dashboard/presentation, later phase | Assigned dashboard templates/static modules, thumbnail candidate presentation and isolated UI tests | Only after Codex's API fixtures are stable; no edits to `api/app.py`; use real endpoints and all pending/error states |
| Codex: shared runner plumbing | `host_codex_runner.py`, `host_claude_runner.py`, protocol, budget/reservations and usage recording | Claude supplies prompt-builder requirements and tests through its own modules; one owner changes runner wires |
| Codex: integration records | Shared HANDOFF, current design status, operator README and release evidence | Claude sends a short lane handoff; does not concurrently edit shared tracker files |

Assignments are file locks for the active phase, not a claim that existing files are ready for these changes. If a file mixes responsibilities, the owner lands the seam first, then delegates the new isolated module. Test files also need explicit ownership. Never cherry-pick unrelated branch work or modify provider fallback policy as an incidental dependency.

For each task, record: task ID, parent contract SHA, dependencies, allowed paths, forbidden shared paths, acceptance command, fixture/artifact folder, expected API/schema version, and handoff commit. Each lane uses a separate test DB and artifact folder. Only the integrator runs shared Compose/deploy/migrations. Review lane diffs and targeted tests before integration; merge to `main` requires explicit approval of that specific merge, and pushing is separately prohibited without authorization.

**First Codex task (LF0-A):** enumerate all admission/prompt/protocol/output/QA limits, draft the versioned contracts and fixture envelopes, and freeze schema/ownership. **First Claude task (LF0-B):** independently draft the long-form editorial rubric, reference-improvement review and compact skill resource proposal in an assigned new document; consume the frozen schema before modifying production content code. These may proceed together because neither edits the other's files. LF1 implementation begins only after LF0 acceptance.

## 9. Decisions and evidence needed before a live pilot

- Actual reference URL and selected channel; transcript/media access when public captions are unavailable.
- Effective Codex/Claude subscription/auth mode, model, remaining allowance and explicit bounded generation budget. Do not expose credentials or assume API access is free.
- Accepted long-form profile, reconciled skill rules and deployment of hash-matching resources.
- Measured host memory/disk headroom and resumable local rendering performance. Existing notes describe a constrained CPU-only machine; treat those historical values as a warning to measure, not current hardware evidence.
- Operator review of the exact script, preview, final and packaging as required by the existing workflow. This plan creates no approvals on the operator's behalf.

The recommended first deliverable is LF0's small contract and budget fixture set, followed by one link intake and one grounded 10-minute script. That tests the expensive creative assumptions before committing to a full long render.
