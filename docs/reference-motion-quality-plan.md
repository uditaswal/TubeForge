# Reference motion quality plan

Date: 6 November 2026. Branch: `feature/reference-motion-quality`, based on
`dev` at `ea14e5e`. Implementation is NOT STARTED. This change plans the work only.

## Outcome and evidence

Use the supplied editor GIF as a visual craft benchmark: readable code, restrained
chrome, consistent syntax colours, purposeful typing, cursor continuity and readable
result holds. The inspected reference is 840×540, 96 frames, 8.4 seconds. Its creation
time and generating stack are unknown. Match its design quality in native portrait
composition; do not stretch its landscape canvas or treat its text as factual evidence.

Reference attachment: `1000094289.gif` in the conversation. Before implementation,
copy it into ignored benchmark artifacts and record SHA-256 and frame durations.
Retain the original and sampled frames for comparison. Do not commit generated media.

## Architecture and constraints

Extend the existing shared renderer: `rendering/shorts/plates.py` has highlighted
code cards; `motion.py` has cached Pillow animation; `story.py` has HTML terminal
typing; `pipeline/reference_short.py` selects and encodes the rendering path.
Choose the smallest reusable implementation after inspecting these paths on this
branch. Prove a Pillow scene first; do not assume the Story path uses Pillow or
introduce a second production pipeline. Share timing/layout data where both paths
need it. Reuse existing design-token work after checking its actual integration.

Keep content in validated scene data and geometry in renderer code. Preserve exact
accepted narration, word anchors, source and asset identities, leases, cancellation,
checkpoint fencing and atomic output promotion. No arbitrary model-generated code
execution. Changed scene contracts or render identity require fresh review through
the existing approval flow. Cached old renders must not acquire the new styling.

The binding CONTENT_SKILLS_CONTRACT takes precedence over stale skill/rulebook
profile passages. Preserve the current loop ending, 96 px caption profile and
≤−1.5 dBTP peak gate. Resolve profile contradictions before adding validation rules.
No live provider calls, replacement narration, publishing or remote pushes are part
of this plan. Use synthetic labelled fixtures or already accepted local packages.

## Sequential phases

Report each phase's acceptance before beginning the next. Every phase starts NOT
STARTED; use IMPLEMENTED until its tests and required artifact review pass. Use
VERIFIED only for the demonstrated scope, and BLOCKED for external decisions.

### 1. Reproduce the reference craft — NOT STARTED

Outcome: a local editor scene with stable chrome, syntax colouring, timed typing,
a cursor that follows the text, and deliberate completed-code/output holds.
Create a native portrait MP4 comparison. Landscape is deferred by the operator
on 6 November; use animation within Shorts, without exporting whole videos as GIFs. Record explicit timing events instead of tying typing speed to encode FPS.

Acceptance: full decode; inspect opening, partial typing, completed lines, cursor,
output and ending at full size and phone scale. No clipping, jumping line positions,
cursor collisions or unreadably fast result flashes. Compare directly with the GIF.
Measure render wall time and memory on this host; make no unmeasured speed promise.
Tests cover multiline/token reveal and deterministic frame selection.
Evidence: MP4s, contact sheets, timing manifest, hashes, measurements and a concrete
visual pass/fail review. Out of scope: narration, dashboard and new scene families.

### 2. Make it a reusable scene — NOT STARTED

Outcome: a versioned editor/terminal scene usable by existing jobs, with shared
palette, typography, spacing, semantic colours and timing events. Include type,
pause, highlight, output reveal and hold; reject unsupported events explicitly.
Preserve distinctions between captured output and labelled illustration.

Acceptance: at least three materially different fixtures (short command/result,
multiline code, long identifiers/overflow) pass layout and timing checks; inspect
encoded results for each. Use intentional wrapping or bounded viewport movement;
never silently truncate accepted content. Check portrait caption/safe-area bounds.
Tests verify validation, renderer identity/cache invalidation and deterministic
rerender. Evidence: fixtures, encoded clips, review and test results.
Out of scope: wholesale renderer replacement and changes to narration generation.

### 3. Integrate with speech and operator review — NOT STARTED

Outcome: an opt-in versioned visual treatment through the existing CLI and Studio
flow, with typed commands/reveals anchored to actual accepted speech alignment.
Keep sufficient reading time; fail review visibly when the scene cannot fit.
Show actual chosen treatment and fallback/failure state in review/activity metadata.

Acceptance: focused API/UI and pipeline tests; signed-in desktop and mobile Studio
select → preview → review → final flow using an accepted local package. Verify stale
approval rejection, cancellation, restart and atomic promotion for touched paths.
No silent fallback that claims the requested treatment rendered successfully.
Evidence: browser captures, job/render hashes, activity record and passing tests.
Out of scope: new script providers, publishing and automatic production approval.

### 4. Prove full-video quality — NOT STARTED

Outcome: one real 30–90-second 1080×1920/30fps narrated Short within the applicable
accepted profile, combining the improved scene with purposeful existing visuals.
Avoid making every topic look like an editor; choose diagrams/comparisons when those
better explain the claim. Reuse accepted local narration and assets where available.

Acceptance: full decode, H.264/AAC, encoded loudness −15..−13 LUFS and peak ≤−1.5 dBTP;
run om-video-quality/qa_check.py on the job folder and apply its full checklist.
Inspect every scene/transition and captions, watch the full video and listen to the
mix; compare phone-scale readability and purposeful motion with the baseline.
Record operator watch/listen acceptance separately; pending human review stays
unverified. Evidence: exact final hash, contact sheet, QA report, full-video review,
measured runtime and signed-in dashboard evidence. Out of scope: publishing,
claims of improved retention and broad rollout before acceptance.

## Next five actions

1. Preserve and hash the GIF; inspect every animation state and record timing.
2. Inspect existing design tokens and scene timing APIs on this branch.
3. Render vertical command, multiline and maximum-width fixtures locally (landscape deferred).
4. Review encoded clips against the reference and record defects before abstraction.
5. Report phase 1 acceptance, then proceed to the reusable scene contract.

Stop after two failed repairs of the same root issue or 45 minutes of active
debugging, per AGENTS.md; report evidence, two options and a recommendation.
Update the canonical internal plan and append local progress evidence per phase.
Update operator docs when the opt-in workflow exists; planning changes no setup.

## Working checklist — 6 November

- [x] Prioritize native vertical Shorts; defer landscape comparison.
- [x] Inspect existing Pillow code-card reveal and geometry.
- [x] Build and test portrait editor animation primitive (7 focused tests pass).
- [x] Render vertical MP4 fixtures; inspect encoded contact sheets and full-size hold frame.
- [x] Add validated per-line reveal windows and multiline syntax colouring.
- [x] Integrate native card rendering into the existing Pillow code-visual path and invalidate old cache identities.
- [ ] Bind explicit line windows to accepted speech anchors in production jobs.
- [ ] Verify full narrated Short and signed-in workflow.

## First implementation checkpoint

Phase 1 **IMPLEMENTED** for a synthetic vertical editor primitive, pending full
motion review and speech integration. `editor.py` provides stable syntax-coloured
layout, multiline cursor positioning, deterministic timing and a minimum result
hold. Production job paths are not yet connected. Reproduce with:
`PYTHONPATH=src python scripts/benchmark_portrait_editor.py`.

Evidence: `artifacts/review/reference-motion/editor-portrait.mp4`, `benchmark.json`,
opening/typing/hold PNGs and an encoded contact sheet. Silent 6.4 s H.264 scene,
1080×1920/30 fps, full FFmpeg decode passed; render measured 9.64 s on this host.
SHA-256: `9ee9fc090d582b44c2d99d5baadcb6ad887c7772d6c3d974dd73229779ac9875`.
Seven focused tests pass under Pillow 12.3.0. Full-size hold frame inspected:
code and label fit the safe area, with room for future headline/caption overlays.
No full narrated-video or operator creative acceptance is claimed. The job QA
script requires a real content package and will run at the integrated-job phase;
this labelled synthetic scene is not a production video job.

## Second implementation checkpoint

Reusable editor work is **IMPLEMENTED**, with validated scene-local per-line reveal
windows, holds between lines and correct multiline lexer state. The caller must
still bind these windows to exact accepted word anchors; the fixtures use synthetic
timing explicitly. Fourteen tests pass, including ordered/nonoverlapping/finite
window validation, cursor movement, held lines and multiline string colours.

Reproduction now creates its output folders and checks FFmpeg exit/decode before
promoting each benchmark MP4. Run `PYTHONPATH=src python
scripts/benchmark_portrait_editor.py --fixture all`.

Three 1080×1920/30fps H.264 clips fully decoded. Their encoded half-second contact
sheets were inspected: command holds stable after typing; the 30-character line
and cursor fit the right edge; multiline reveal keeps indentation and positions.
Evidence is under `artifacts/review/reference-motion-v2/{command,width,multiline}/`;
each folder contains a benchmark JSON with exact hash, timing provenance and runtime.
This is sampled visual evidence, not a full motion/watch or speech review. Phase 2
still needs highlights/output events and render-identity integration; phase 3 and
full narrated QA remain pending. Next: adapt the primitive to the existing visual
zone and bind opt-in scene timing/render identity through the shared pipeline.

## Shared-compositor integration checkpoint

**IMPLEMENTED**: existing Pillow `CodeVisual` scenes now use the same editor
primitive at the native 810×670 card size. Existing heading/caption composition
and source-card behavior remain owned by the shared compositor. The existing
code-visual selection is the opt-in; no additional dashboard control is needed.
This replaces the earlier proposed separate visual-treatment selector. Story and
HyperFrames paths still use their existing implementations and need separate review.

The pipeline renderer identity is now `reference-short-v1/render-4`, preventing reuse
of old rendered pixels. Render QA reports record the editor version; code-frame
caching retains at most 12 frames. Existing output approval rules still apply.
Current job typing remains explicitly proportional to scene duration; per-line
speech-anchor binding is NOT STARTED and must not be described as measured sync.

Validation: 39 editor/plate/layout/real-encoder tests passed in 67.82 s, plus the
new cache-identity test passed separately. A four-second synthetic 1080×1920 MP4
through the real Animator/Plates compositor fully decoded. Evidence:
`artifacts/review/reference-motion-integrated/composite.mp4`, `composite.png`,
`encoded.png`. Inspected the integrated hold frame: heading, code, cursor and
caption have separate readable zones. This fixture is not factual narration or
production acceptance. Full narrated rendering, signed-in review, speech events,
highlights/output cues and operator watch/listen remain pending.
