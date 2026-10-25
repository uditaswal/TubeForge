# Content skills and research contract

Moved verbatim from `AGENTS.md` on 2026-10-21 to cut per-session token cost. **`AGENTS.md` links here; read this file when working on content skills, scripts, scene plans, research or the reference-short profile.** It remains binding. Whenever skill locations or the content pipeline change, update this file and the applicable `readme.md` sections in the same change.

## YouTube content skills

The supplied, reviewed `.agents/skills/viral-short-form/` is optional creative
reference material. Its promotional text and unverified platform-performance
claims do not override this contract. Keep `.agents/skills/yt-script/` as the
sole production narration skill; the benchmark guide is
`docs/SHORT_FORM_VIDEO_RULEBOOK.md`.

Use the installed project skills in `.agents/skills/` for relevant TubeForge
content tasks. Read the selected SKILL.md and required resources first; review
supporting scripts before execution and resolve resources against their skill
directory. Use `yt-script` for narration, hook candidates and scene directions,
and execute its hook scorer. Use `yt-package` for coordinated titles/thumbnail
text and execute its title checker; use `yt-seo` for descriptions and metadata.
Use `yt-shorts` for supplied long-form repurposing, `yt-plan` for calendars,
`yt-chapters` for appropriate long-form transcripts, and `yt-edit` for
transcript-based edit recommendations. Use `yt-retention`, `yt-viral`,
`yt-audit`, and `yt-comment` only with their required source data/capabilities.
Never fabricate analytics, trends, sources, performance or tool execution.
Heuristic scores are review signals, never predictions of views.

Preserve channel voice profiles, selected format, script provider, review,
scheduler and publishing policies. Skills supply content instructions/tools;
rendering, narration, scheduling, analytics retrieval and publishing belong to
the application/integrations. Interactive discovery does not install resources
for the isolated runtime: verify installed-wheel resources and host deployment.
Whenever skill locations or the content pipeline change, update these rules
and the applicable README sections in the same change.

The canonical yt-script source is `.agents/skills/yt-script/` only; do not update
or load competing downloaded copies. Read its `SKILL.md`, `automation.md`,
`hooks.json` and `hookscore.py` for narration generation/retries/revisions.
Production prompts explicitly embed these resources and the complete brief;
installed wheels must hash-match this source folder. Automation returns finished
ordered narration separately from hooks, sources and production notes.
Insufficient-source results block before TTS and require operator correction.
Scene plans also carry source-grounded visual subjects, purposes, compositions
and display elements into the existing VideoPlan and asset stage. Keep the
asset-stage storyboard manifest/contact sheets tied to accepted hashes, and
inspect their teaching value before claiming creative acceptance. Declarative
scene layouts must remain topic-independent, compile only after the exact script
gate, preserve legacy layout/checkpoint behavior, and record supported graphics
versions and their shared palette for mixed-layout Shorts.
Word-anchored reveal order and any layout variant belong to the accepted scene
contract and render identity; a captured test-fixture approval is never an
operator approval for a production job.

`.agents/skills/om-short-production/` applies the project's topic-independent
short-form production standard after narration acceptance. It must defer to the
rulebook, preserve `yt-script` as the sole narration authority, and distinguish
benchmark evidence from production acceptance.

The newer reference-short-v1 profile follows docs/CLAUDE_PIPELINE_REVIEW.md:
6–16 scenes (scaled to the target), 8–15 spoken words each, 25–90 seconds, final 1080×1920/30fps,
720×1280 drafts, one-line 96px Anton captions, Kokoro at 1.15× with pauses capped at 0.15 s and
0.18 s scene tails (22 Oct 2026), ≤96 narration words, and encoded true peak ≤−1.5 dBTP.
Script-craft checks (`providers/content/craft.py`: banned clichés, ≤2 rhetorical questions, late payoff,
loop ending (no follow request; open last sentence; last frame equals first), no echo headings) are repairable writer errors.
Keep geometry in the shared rendering/shorts library, not model output. Run
native local Kokoro and forced alignment sequentially to bound model memory;
Piper and estimated alignment are explicit, recorded fallbacks. The canonical
yt-script automation resource owns this profile's narration guidance. Changed
skill resources require installed-wheel hash verification before host use.

Reference Short speech preparation may use the opt-in `spoken-v1` profile after
the exact reviewed scene copy is accepted. It expands only bounded whole-token
numbers, percentages, currency and common technical initials, plus an explicit
single-display-token channel lexicon. The original `vo` and caption remain the
reviewed/display text. The voice manifest must retain the spoken text, applied
rules, exact spoken-to-display word spans, profile identity and raw/processed
audio hashes. Alignment must cover every spoken word before it is collapsed to
display-word timing; missing or extra words fail closed. Grouped synthesis and
voice-only processing are opt-in render settings, not writer instructions or
approval. Any changed audio requires a new listener review of the exact render.

Reference Short stock selection may rank locally cached Pixabay assets using
the scene's accepted visual query, source tags, rights metadata and prior-shot
diversity. Ranking is a candidate review signal, not evidence that a clip proves
the narration. Record the selected asset, license, source URL, ranking version
and fallback reason in the plate manifest. Inspect selected pixels and the
complete encoded video before creative acceptance. Encoded-frame black intervals
are a render failure; frozen intervals are advisory because intentional static
cards may be valid. Keep temporal QA bound to the exact rendered file hash.


### Topic research before narration

When production source research is enabled, notes-only v7 briefs use the typed
host `ResearchSourcesV1` operation before narration. Treat topic/angle/notes as
hypotheses, never approved factual evidence. Keep research separate from the
canonical yt-script narration skill. Use live web-search evidence and public
primary URLs; local Python captures bounded text and source hashes. Preserve
explicit source packets and accepted checkpoints. Cache research, record usage
and activity, enforce one research invocation per exact brief, and retain the
separate two-attempt script limit. Never silently reset an exhausted allowance
or turn a research assessment into a factual source or operator approval.

Envelope-generation output must not ask the writer to echo immutable request/source
text. Application code binds that trusted request before domain validation;
conflicting legacy echoes and unknown source citations must still be rejected.

Animated landscape card/teaching scenes must use native landscape composition and locally derived word timing; do not stretch portrait canvases or remove accepted cues to make a render pass. Preserve comparison reveal ordering and exact approved copy. Recovery from initial preview validation may reuse approved media checkpoints only before any preview artifact exists, with the same ownership, source-integrity and exact-script checks as asset recovery.


## Delivery QA skill (23 Oct 2026)

`.agents/skills/om-video-quality/` (checklist + `qa_check.py`) and `.agents/skills/om-social-delivery/` (upload-ready package standard) hold the lessons from earlier failures: narration length vs voice speed, card heading width, repeated on-screen words, loudness windows, logo/stock use, stale services and cached scripts. They are **not** in the hashed prompt resource sets (`youtube_skills.RESOURCES`), so editing them does not change prompt identities or require a host redeploy. Run `qa_check.py <job folder>` before reporting a video job done. Writer-facing rules live in `providers/content/prompts.py` and the repairable checks in `providers/content/craft.py` (thumbnail text is checked there for v8 scripts).
