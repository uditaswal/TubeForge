# Reference motion quality plan

Date: 6 November 2026. Branch: `feature/reference-motion-quality`, based on
`dev` at `ea14e5e`. Implementation is IMPLEMENTED on this feature branch, and the local saved-media workflow is VERIFIED. Overall acceptance is IMPLEMENTED while applying the operator’s dark article-card revision; full watch/listen will follow the revised artifact. Story checklist parity is demonstrated locally; unsupported layouts fail explicitly.

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

### 1. Reproduce the reference craft — IMPLEMENTED

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

### 2. Make it a reusable scene — IMPLEMENTED

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

### 3. Integrate with speech and operator review — VERIFIED for local saved-media workflow

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

### 4. Prove full-video quality — IMPLEMENTED

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

1. Watch/listen to the dark-reader revision below (replaces the prior native final as the current candidate); record timestamped feedback.
2. Resolve playback findings, including terminal reading hold, small terminal labels and music balance.
3. Review the completed native workflow evidence alongside the exact final; production script generation and publishing remain outside this run.
4. Rerun only checks affected by repairs and inspect the exact revised artifact.
5. Submit the feature branch and evidence for review; merge requires explicit approval.

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
- [x] Add reviewed code-line word indices and bind them to saved timeline timestamps in the encoder.
- [x] Render an offline comparison with accepted narration and saved Whisper timing; inspect encoded frames.
- [x] Verify signed-in desktop/mobile Chromium review and anchor visibility.
- [x] Render a current-profile 49.7-second loop artifact; pass blocking delivery QA checks.
- [x] Repair source-capture Ask AI controls and partial neighbouring-line fragments; inspect real recapture.
- [x] Add Story checklist typing, syntax colours, active-row highlights and following cursor; preserve all supported lines/items.
- [x] Check exact Unicode text and forward/backward seeking in Chromium.
- [x] Regenerate all five source captures and render the full Story Short within the production 20× budget.
- [x] Inspect actual source cards, terminal/output hold, code reveal frames and every scene entrance.
- [x] Fix Story frame-zero headline, canonical loop endpoint and source-image zoom clipping; invalidate render identities.
- [x] Verify signed-in desktop/mobile review for the exact revised package.
- [ ] Complete full watch/listen acceptance of the exact revised Short.
- [x] Prove native worker preview → exact dashboard approval → final with a fresh worker, and audit restart/ownership/stale-approval safeguards.
- [ ] Close creative acceptance and the full phase audit before calling the overall goal VERIFIED.

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

## Word-anchor integration checkpoint

**IMPLEMENTED**: optional `CodeVisual.line_reveal_words` supplies an exact reviewed
word index per line. Old serialization omits empty anchors. Scene validation checks
coverage/order/range; the encoder compiles windows from its saved timeline before
animation. A one-second completed-code hold is required. QA records resolved
windows and the original alignment method, including estimated/test provenance.
Story/HyperFrames and motion-disabled encodes reject explicit anchors. The pipeline
identity is now render-5 and changed anchor data also changes the topic/render hash.

Tests cover old serialization, invalid anchors, timeline binding, missing reading
hold, unsupported renderer rejection and changed cache identity. The actual-speech
benchmark is still pending: the accepted M3 package has a 29.6-second legacy ending,
so it cannot establish current 30–90-second loop-profile acceptance unchanged.
Next: use its exact narration/alignment for an explicitly labelled offline visual
comparison, then obtain compliant full-video/signed-in evidence without rewriting
accepted copy or claiming automatic production approval.

Word-anchor evidence: 37 editor/plate tests and 11 renderer tests pass. The
four-second synthetic anchored clip and encoded contact sheet are under
`artifacts/review/reference-motion-anchors/`; `timing.json` records windows,
synthetic alignment provenance and SHA-256
`70b8fc2d1ae21dc9c635f149fc10eb21494db79739c65ad0cd347a0ae7a329c6`.
Contact-sheet inspection confirms ordered line reveal and final hold without
heading/caption collision. The script review details now include reference
scenes and their explicit anchors, so these directions are visible before
approval. Signed-in API verification is recorded separately when it finishes;
real-browser interaction and actual narration remain unverified.

Signed-in API verification: the focused authenticated dashboard test passed (1 in
3.31 s) outside the sandbox. The sandbox run stalled in TestClient's blocking
portal startup before the test admin existed; a diagnostic run captured that
thread stack and was explicitly interrupted before the successful escalated run.
No application workaround was added. Total focused checks this checkpoint: 49
(37 editor/plate + 11 renderer + 1 signed-in API). Browser review is still pending.

## Actual-speech and browser checkpoint — 6 November

**IMPLEMENTED**, with narrow technical and browser evidence. Reproduction:
`PYTHONPATH=src python scripts/benchmark_reference_motion_speech.py --source
<accepted-M3-folder> --output <fresh-comparison-folder>`. The script validates the
original topic/audio/timeline identities, preserves narration and scene timing,
and records a distinct unapproved illustrative Rust overlay. No provider calls.

Artifact: `artifacts/review/reference-motion-speech/final.mp4`, SHA-256
`14c102c9382e05ba6b9bab6a406a23bb2ad7b6f2579faed6f6510b74e118444c`.
1080×1920/30 fps H.264/AAC, 29.629 s, full decode passed; encoded audio −14.31 LUFS,
−2.45 dBTP. Source alignment is whisper-base-en-dtw-v1. Code-line windows resolved
to 0.25–1.11 s and 1.11–3.51 s within scene 2. Runtime was about 340 s on this host.
The encoded overview and full-size editor frame were inspected: stable syntax,
cursor position, readable code and separate heading/caption zones. The full mix
has not been listened to for this revision; no complete creative acceptance claim.

Delivery QA was run and remains **BLOCKED for full-profile acceptance**: duration
29.6 s fails the 30–90 s gate; legacy CTA is warned rather than a current loop.
Other warnings: two pre-existing dead stretches, missing historical narration-health
provenance and no thumbnail. Loudness passes. The duration/ending were not changed
or hidden to pass QA. This is a comparison, not an approved production output.

Opt-in real-browser test:
`TUBEFORGE_MOTION_BROWSER=1 PYTHONPATH=src python -m pytest -q
tests/test_reference_motion_browser.py` (requires this comparison package).
One test passed in 63.23 s using isolated SQLite and transient loopback hosting;
1440×1000 and 390×844 Chromium both signed in, selected Generations → Needs review,
opened script review, found line anchors [0,3], and reported no JS errors or page
overflow. Screenshots and review.json: `artifacts/review/reference-motion-browser/`.
The harness first missed a required app name and then targeted hidden Studio
controls; both setup errors were corrected. No production app changes were needed.

Next: locate an already reviewed current-profile local package for full 30–90 s
proof, or present the exact comparison and request a narration/profile decision.
Do not rewrite accepted narration or silently invoke a live provider. Highlight/
output cues and Story-renderer parity remain pending scope; do not mark the overall
goal complete from this Pillow-only comparison.

## Current-profile render and loop checkpoint — 6 November

**IMPLEMENTED**, with local technical scope proven. Read-only database inspection
located job `batch-caaacb77d5659ea27ce1292d20f45c6f6b6f857c30d4ad97` and verified its
stored script approval, artifact checksum and actual package SHA-256 all equal
`9ac7023134536f9d3a29e860cdb85379499b604d46fde9fdacc4f1f082ba7811` (actor
local-dashboard). This authorizes reuse of the exact captured inputs; the visual
overlay/output is distinct and has no inherited production approval.

Reproduce with `scripts/benchmark_reference_motion_speech.py --profile rate-limit`
and the named source folder, supplying a fresh `--output`. Code lines retain the
accepted identifiers/values and now reveal rate before burst, at reviewed local
word indices [3,6]. Original narration, scene timing and accepted audio mix are
reused. Source audio provenance is copied only after verifying its narration hash,
and is explicitly annotated as original mix metadata reused through source AAC.
No live provider calls, original artifact edits, approval writes or publication.

Output: `artifacts/review/reference-motion-current-profile/final.mp4`, SHA-256
`2a9890e93b4d03d8bb7f00a5a9d9933a8710da2ca5d626a0ba49f5b1664af614`.
49.659 s, 1080×1920/30 fps, H.264/AAC, full decode passed; −14.17 LUFS/−2.39 dBTP.
Measured render RTF 7.18 (inside the default configured 12× budget; benchmark
permits 30× for diagnostics). qa_check.py reports no FAILs: duration, loop ending,
loudness, narration clipping/silence/level jumps, effects and licence trail pass.
Warnings retained: 3.3-second terminal dead stretch, 87 music-under-speech stretches
in reused mix metadata, and absent thumbnail. No claim of listening acceptance.

Found and repaired two Pillow motion defects: the opening hook began transparent;
and loop endpoints used current background/zoom instead of the opening frame.
Frame one now shows the hook immediately; the encoder supplies its exact opening
state for final-frame reuse in the closing speech tail. Renderer identity is
render-6. Canonical frames match byte-for-byte in tests; decoded H.264 endpoint
mean absolute RGB difference is 0.513/255 (compression). Opening, ending, editor
frame and the complete 25-panel encoded sheet were inspected.

Regression evidence: 47 editor/plate/content/endpoint checks passed, 11 encoder/
layout checks passed, and 5 strict-schema/illegal-layout checks passed. The old
strict-schema fixture needed explicit Flow defaults (diagram/danger); production
validation was not weakened. Local code-line anchors are excluded from the shared
Codex/Claude writer output schema until cross-renderer support is available, so
this optional local contract does not break Story jobs or require writer retries.

Remaining quality findings are real: inherited source captures show an Ask AI chip
and other page UI; terminal output holds static for 3.3 seconds; mix balance needs
listening. Story still truncates checklist code to three lines and uses its own
reveal implementation. Next: repair source-capture UI pollution, then complete
meaningful terminal/highlight/output motion and Story parity, with encoded review
and renewed full watch/listen before declaring the overall goal achieved.

## Clean source-capture stage — 6 November

**VERIFIED for the local capture stage only.** New captures apply
`source-capture-v4-clean-lines`: after quote selection settles, hide only matching
interactive Ask AI/Copy controls, including controls inside open shadow roots.
Ordinary article text, links and other buttons remain untouched. Visibility hiding
preserves the quote layout; native-selection/caret/animation artifacts are excluded
from the screenshot. Partial-paragraph fallback crops use complete matched line
boxes without padding that exposes fragments of adjacent lines. Full paragraph
crops retain their context padding when the paragraph fits.

The first light-DOM-only attempt failed the real recapture despite passing its
fixture. Inspection found an open shadow-root DIV; traversing it hid the actual
Ask AI button. A second artifact inspection caught the adjacent-line fragments;
the fallback crop was tightened and recaptured. This is not an image paint-over.

Validation: 30 capture/plate tests passed (one opt-in browser check skipped there);
the opt-in Chromium check passed separately in 2.59 s. It exercises normal and
shadow-root controls, preserved literal article text/links and identical quote
rectangles before/after cleanup. Real cited-page recapture matched all ten quoted
words and recorded hidden_controls=['Ask AI']. The plain and highlighted output
were inspected at full size and are clean. Evidence and exact hashes:
`artifacts/review/reference-motion-capture-v4/capture-review.json`, `source.png`,
`source-hl.png` and their native-resolution copies. Plain SHA-256:
`0cf364cc7da1187e8b2f5fac1ae55b10a97c9c153358ac0ee32e0d92b8c0477c`.

Capture policy and hidden-control labels are retained in the plate manifest's
evidence, changing new manifest/render identity. Accepted originals and checkpoints
were not rewritten or silently regenerated. The 49.7 s MP4 still uses its original
plates; a new full render/review is required to show this improvement in that file.
No provider calls, script/source-packet edits or production approvals occurred.
Next: Story parity and purposeful terminal/output motion, then fresh source plates
and an updated full Short for creative review.

## Story checklist code-animation checkpoint — 6 November

**IMPLEMENTED**. Story checklist code now shares Pillow's timing compiler and
syntax palette. It types each line, highlights its active row and follows it with
a cursor; checklist items remain visible and their ticks appear after the green
reveal completes. All six supported code lines are retained when they fit; if the
code and checklist cannot fit above captions, rendering fails with a revision
message instead of taking the first three lines. Explicit anchors on other Story
templates or classic HyperFrames remain unsupported and fail clearly. Production
writer schemas continue to omit local code-line anchors.

Timing/character handling is deterministic: tokens are inserted as text, script
closing sequences are escaped as data, and Unicode code points are preserved.
Forward → backward → forward Chromium seeking restores the correct text without
stale future lines. Code animation metadata reaches final HyperFrames QA reports.
Cache identities advance to render-7 / hyperframes-5; older pixels are not reused.

Validation: 71 focused routing/content/editor/plate/Story checks passed (one opt-in
browser check skipped in that group); the real Chromium seek/Unicode check passed
separately in 19.02 s. The prior seek attempt was interrupted; it is not a pass.
The actual pinned HyperFrames CLI 0.8.192 checked and rendered the captured rate/
burst scene at 1080×1920/30 fps. Lint, runtime, layout, contrast and craft checks
all report ok. The first real check exposed low-contrast premature ticks, cursor
occlusion and small labels; those were repaired before the successful render.

Encoded scene evidence is on the project artifact disk, outside the /tmp worktree:
`/home/uditaswal/docker/tubeforge/Youtube_Video_Producer/artifacts/review/reference-motion-story-code-feature/`.
Files: silent.mp4, contact.png, hold.png, scene-report.json, render-report.json and
project/index.html. MP4 SHA-256:
`a7afd4304b0f56ebe7d2fc5ee180799a25f54b105551f194290f8a8906a6fe54`.
The encoded sheet and full-size hold were inspected: ordered typing, cursor spacing,
readable labels, meaningful checklist changes and caption separation pass sampled
visual review. This is a silent scene comparison, not a completed narrated job.

Environment evidence: /tmp had only about 0.9 GB free, so the first encode hit the
CLI disk guard. Scratch/output moved to the project artifact disk (766 GB free);
the guard stayed enabled. The scene run took 131.5 s including checks/startup and
used a diagnostic 60× budget. Full-video production budget (20× in production.yaml)
acceptance is still unverified and must be tested on the next full render. The
latest Unicode normalization is additionally covered by the real-browser test.

Next: regenerate the current-profile source plates with the verified v4 capture
policy, then render the complete Story Short through its actual CLI/QA path under
the production budget. Review terminal/output motion, full playback and mix balance;
no operator creative approval, deployment, merge or publication has occurred.

Additional traceability check passed: scene-local code windows and absolute timeline windows are reported separately, with the scene start and original alignment method retained. One nonzero-origin metadata test passed after the 71-check group; no extra render claim is made for this metadata-only addition.

## Full Story comparison checkpoint — 6 November

Overall **IMPLEMENTED**; local technical render and source-framing checks are
**VERIFIED** for the scope below. This is a separate, unapproved comparison,
not a production approval or a publishing job.

- Artifact: main-project `artifacts/review/reference-motion-story-full-v3/final.mp4`.
  SHA-256 `ba17462cde4307c1657a46abcaa7eaa0b670cf7e0d4722e2c959015563902155`.
- Native portrait H.264/AAC, 1080×1920/30fps, 1,490 video frames, 49.659 s
  narration; full decode passed. Encoded loudness −14.17 LUFS, true peak
  −2.39 dBTP. Whole benchmark 448.83 s; encoder QA 443.93 s / RTF 8.94,
  below the production 20× budget. These are measured host results, not a speed promise.
- All five source quotes recaptured with full matches under v4 clean-lines.
  Shadow-root Ask AI controls removed where present. A bounded visual-only
  sc08 quote revision takes an exact substring of both the old quote and saved
  cited-source excerpt; the original approved package/narration remain untouched.
  The new comparison package requires its own review. Fixture:
  `tests/fixtures/reference_motion_quote_revision.json`.
- Saved narration, mix and Whisper timing reused. Code sc10 reveals rate then
  burst at global 39.741–40.321 s and 40.321–41.934 s, with a one-second
  completed-code hold. No provider call or allowance reset.
- Story hooks now show their headline at frame zero. Canonical last frame replays
  the first, preserving frame count; decoded H.264 endpoint MAE 0.787/255
  (compression means encoded pixels are not byte-identical). Source images stay
  fixed inside cards while their highlights animate, avoiding clipped quote edges.
  Identities are render-9 / hyperframes-7.
- Reproducible local benchmark: `scripts/benchmark_story_short.py`. Fresh outputs
  recapture only cited sources; `--resume` verifies every prepared file hash and
  reuses captures/audio. Inputs, renderer hashes, exact package and reports are
  retained next to the MP4. Failed/intermediate v2 remains separate.
- Regression: 77 passed, four opt-in browser checks skipped in the default run.
  Separate actual Chromium tests passed for source bounds (early/middle/late)
  and signed-in desktop/mobile anchor review (no JS exceptions/overflow).
  The tested v2 and rendered v3 content-package hashes are identical:
  `1e5593e236905d4d15b55a5e0f09e48939eef44635e0760ef1e5405f37a59b86`.

| Time/scene | Evidence and expected behavior | Observed / remaining review | Severity / action |
|---|---|---|---|
| 0 / 49.63 s | Full-size decoded endpoints; visible hook and matching loop | Hook/caption readable; canonical opening replay confirmed | Pass for sampled endpoints |
| All 12 entrances | `boundaries.png`, 0.15 s after each scene start | Headings visible; deliberate card/diagram entrances follow | Sample pass; full playback pending |
| 11.39–16.79 s, sc04 | Full-size source frame at 14 s, native Chromium bounds | Complete line edges, source label and highlight visible; no inner zoom | Pass for framing |
| 25.46–29.99 s, sc07 | Full-size terminal at 29 s plus overview | Command/result visible and labelled illustrative; 3.3 s reading-hold warning | Advisory: judge pace in playback |
| 39.06–42.93 s, sc10 | Four reveal samples + full-size 42 s | Correct syntax, following cursor, checklist progresses, full code fits | Pass for samples/timing; playback pending |
| Complete audio | Encoded loudness/health checks, inherited mix provenance | Blocking checks pass; 87 music-within-12-dB stretches flagged | Listening required; no claim of audible acceptance |
| Craft advisories | Pinned HyperFrames report | Terminal badge/language below 28 px during entrance; short late diagram/chip holds | Review at phone scale before acceptance |

`qa_check.py` has no FAILs. It warns about terminal hold, inherited music balance
and missing publishing thumbnail (publishing is out of scope). HyperFrames checks
have no runtime/layout/contrast errors; its silent-project warning refers to the
intermediate visual-only HTML, before accepted audio mux. The complete mix has
not been listened to here. Full-video playback and operator acceptance remain open;
no phase is promoted to overall VERIFIED from a contact sheet or tests alone.

Lifecycle regression audit: 15 selected existing orchestrator/worker/approval tests
passed in 190.05 s. Coverage includes interruption resume, version-invalidated
preview identity, six stale-input cases, changed word timing requiring fresh
approval, cancellation lease cleanup, ownership fencing and conflicting approvals.
These are local automated safeguards, not proof of the complete signed-in
preview → final workflow for the new comparison. That live workflow evidence
and full watch/listen remain open.

## Native dashboard workflow acceptance — local scope VERIFIED

Phase 3's saved-media workflow is **VERIFIED**. Overall video quality remains
**IMPLEMENTED** pending complete watch/listen review. No production script,
preview or publication approval was created.

`tests/test_reference_motion_workflow.py` imports the exact hash-verified prepared
narration/alignment/source files into a fresh database, records a test-only script
approval and starts at caption generation. The new request explicitly selects
Story. Content, TTS, media and publishing providers raise if accessed; no provider
call was used. This deliberately exercises already reviewed media through native
caption/render/review stages, not production script generation.

Evidence folder in the main project:
`artifacts/review/reference-motion-native-workflow-v1/`.
Current candidate: `jobs/motion-native-workflow/final.mp4`.
SHA-256 `4ae2df5ec4a128fcf527d3b438e36c902b21cd0f2bb5219365036fc626bc6ee3`.

- Native leased worker rendered a 720×1280 preview and released its claim at
  PREVIEW_READY. No approval existed and another worker tick did no work.
- Signed-in desktop1440×1000/mobile390×844 Chromium loaded the actual preview.
  A stale preview identity received HTTP409; the real dashboard button recorded
  durable approval for the exact current identity (HTTP200).
- A fresh runtime and worker loaded that approval and rendered the actual
  1080×1920 final. The final manifest references the exact preview identity and
  approval ID. Current DB state FINAL_READY, no worker claim, no publication
  approval. Saved events include both render_started/render_completed pairs.
- Initial test failed at an outdated button label after preview success. The
  corrected harness resumed only after checking the saved package/proof hashes
  and native preview-current predicate; it did not regenerate the preview.
  Native workflow test then passed in356.82s. A separate actual-playback check
  passed in15.77s: muted frames advanced from41.5 to42.1s on both screen sizes,
  97 presented frames reported, no JS exceptions or horizontal overflow.
  `*-played-final.png` captures are taken after playback settles; the earlier
  seek-only captures contain Chromium's transient loading spinner.
- Preview encoder QA314.08s,RTF6.32; final312.35s,RTF6.29 (whole worker final
  stage324.71s). Both under configured production20×. Full decode passed for
  both; native final is49.659s,1490frames,H.264/AAC,−14.16LUFS/−2.47dBTP.
- Actual native rendering remasters the saved narration through the normal
  mixer. Its mix differs from the earlier direct comparison and needs its own
  full listener review; no fresh narration was generated.
- `qa_check.py` on the native job folder has no FAILs. Remaining WARNs:
  terminal3.3s reading hold and87 music-under-speech stretches. A local thumbnail
  exists; no publishing action occurred. Earlier small-label/short-hold craft
  advisories still need full playback judgement.
- Inspected native final overview/contact sheet, full-size source/code frames
  and opening/closing frames. Decoded endpoint MAE0.793/255; canonical opening
  replay and readable headline/caption remain intact. `workflow-review.json`,
  `playback-review.json`, native manifests, exact-file QA and screenshots retain
  detailed evidence. A short muted browser sample is not full watch/listen.

Reproduce with `PYTHONPATH=src .venv-motion/bin/python -m pytest -q -s
 tests/test_reference_motion_workflow.py`, setting
`TUBEFORGE_MOTION_WORKFLOW=1`, `TUBEFORGE_MOTION_WORKFLOW_INPUT` to the prepared
full-v3 folder, `TUBEFORGE_MOTION_WORKFLOW_OUTPUT` to a fresh artifact-disk folder,
and `TUBEFORGE_HYPERFRAMES_BIN` to pinned CLI0.8.192; put Node24 on PATH.
`TUBEFORGE_MOTION_WORKFLOW_RESUME=1` is limited to an intact PREVIEW_READY test
checkpoint. To recheck playback of an existing completed native run, select only
`::test_saved_native_final_plays_on_desktop_and_mobile` and set OUTPUT plus the
opt-in flag. Do not point this harness at the production database or job folder.

## Completion audit — 6 November, after native workflow proof

The previous goal turn made concrete progress (native worker/UI acceptance and
commit23a6066). This audit checks current state rather than inferring completion
from that commit. Current renderer sources are unchanged; native final SHA matches
both workflow-review and exact-file QA. Overall completion is **not proven**.

| Requirement | Current authoritative evidence | Audit result |
|---|---|---|
| Isolated feature branch/worktree and checked plan | `feature/reference-motion-quality`, `/tmp/tubeforge-reference-motion-quality`, tracked checklist; commits through23a6066 | VERIFIED for branch/plan scope |
| Native vertical video, purposeful animation within scenes | Native1080×1920/30 final,49.659s,1490frames; code sc10 typing/cursor/checklist, existing diagram/terminal/highlight scenes | Technical delivery VERIFIED; creative judgement pending |
| Preserve and measure supplied reference | `artifacts/review/reference-motion-audit/reference/{original.gif,reference.json,first.png,middle.png,last.png}` in main project | VERIFIED:840×540,96frames,8400ms; SHA4935bdc88227e264e1b7d4e73e9aa6874ccb3848b19bc2251c0cbdfecf107be1; generating stack/time unknown |
| Stable editor chrome, token colours, multiline/width handling, explicit holds | Current-code command,width,multiline fixtures re-rendered/decoded; contact sheets inspected against reference middle; editor/timing/overflow tests | VERIFIED for fixtures and sampled native frames; full motion review pending |
| Determinism and measured host cost | Fresh fixture MP4 hashes byte-identical to retained clips; `fixture-resources.json` records23.273s and567020KiB maximum waited-child RSS (not simultaneous aggregate). Native QA records463776KiB parent/609024KiB child peaks and RTF6.29 | VERIFIED for these measured runs; no seconds-per-full-video promise |
| Existing renderer integration, code timing/hold, explicit unsupported layouts | Shared compiler/colours used by Pillow cards and Story checklist; saved Whisper anchors in native manifests;77 focused regressions previously pass | VERIFIED for demonstrated supported paths; no claim of all-layout support |
| Exact source/narration/timing preservation | Prepared-file hash proof, native import record, source quote bounded-excerpt fixture, timeline validation; providers forbidden in actual workflow | VERIFIED for saved inputs; normal mixer creates a distinct mix requiring listening |
| Review visibility and durable media workflow | Actual signed-in script review plus native720×1280 preview→HTTP409 stale identity→HTTP200 exact approval→fresh worker final; final manifest binds approval; settled desktop/mobile playback samples | VERIFIED for imported local-media workflow; all approvals test-only |
| Ownership, restart, invalidation and cancellation safety |15 selected existing lifecycle tests passed; native worker claims released at both gates; no rerender while waiting; versioned identities and exact-file QA | VERIFIED for tested local scope; worker lease/promotion code unchanged |
| Technical final gates | Exact final4ae2df5ec4a128fcf527d3b438e36c902b21cd0f2bb5219365036fc626bc6ee3; full decode,H.264/AAC,−14.16LUFS/−2.47dBTP; qa_check no FAILs | VERIFIED for this file |
| Complete creative/audio acceptance | Full overview, entrances, source/code/endpoint frames and short muted browser sample inspected. No full watch/listen feedback exists | Missing: whole-video pacing/continuity, pronunciation and phone-speaker mix judgement; terminal3.3s/music87-stretch/small-label advisories remain |
| Repo/document hygiene and delivery scope | Source checkpoints committed with hooks; generated artifacts/local DBs remain ignored; readme/plan/handoff updated; no push/merge/publish/provider call | VERIFIED for checkpoint scope; branch review awaits creative findings |

Fresh fixture evidence: main-project
`artifacts/review/reference-motion-audit/current-fixtures/{command,width,multiline}/`.
Command4s SHA20f625c96b9256498cea43605c2016f266422ba1552dbd67017dbffd4c889648;
width5s SHA61f199d0876240642976480f1131dfb9591dfb118498c2ea576b8bfa4e4ae105;
multiline6.4s SHA9ee9fc090d582b44c2d99d5baadcb6ad887c7772d6c3d974dd73229779ac9875.
No fixture review promotes the complete narrated video to creative acceptance.

Remaining dependency is exact-native-final full watch/listen feedback. It has
remained open across the direct comparison, native workflow and current audit
turns. More rerenders or unrelated features would not supply that evidence.
The quality skill explicitly requires “watch the full final video” and “Listen to
the complete mix.” No operator approval is inferred from silence or test passes.

## Operator revision — consistent dark article cards (6 November)

Operator selected “Dark article cards; keep other scenes.” Overall implementation
is **IMPLEMENTED** and this revision is **IMPLEMENTED**. Full-video acceptance
of the previous candidate is superseded by this requested visual revision.

1. Shared dark capture treatment: outcome is a consistent navy/white source-card
   theme with the existing animated reading highlight. Acceptance: actual Chromium
   proves exact quoted text and line geometry unchanged for light/dark/shadow-root
   content; all five real saved quotes fully match and look dark/readable. Evidence:
   focused tests, capture provenance, plain/highlight PNGs. Out of scope: narration,
   article rewriting, code/diagram/terminal/hook layout changes.
2. Revised vertical Short: reuse the latest native narration, mix, timing, topic
   and non-source assets in a separate comparison; regenerate only source plates.
   Acceptance: native1080×1920/30 MP4, exact-file decode/loudness QA, full contact
   sheet and source frames inspected; compare non-source frames with prior native
   output and verify audio reuse. Full watch/listen remains an exact-artifact gate.
   Record hash/runtime and check tasks as evidence passes; no production approval,
   paid provider call, merge, push or publication.

- [x] Implement and test shared dark-reader capture theme; retain provenance.
- [x] Inspect all five actual dark source captures and highlight variants.
- [x] Render and inspect revised Short with other scenes and saved audio preserved.
- [ ] Obtain full review of the exact revised artifact.

Dark-capture phase **VERIFIED** locally:34 focused tests pass (one browser check
skipped in that default run); separate Chromium light/dark/shadow-root geometry
and exact-text test passes2.81s. Five actual cited quotes fully recaptured under
v5 dark-reader, all `matched=true`; plain/highlight contact sheet inspected at
`artifacts/review/reference-motion-dark-reader-v1/dark-source-review.png` in the
main project. Capture evidence retains appearance/theme-root count and targeted
Ask AI cleanup. Topic/narration/mix are hash-identical to latest native inputs;
only source plates were regenerated. The revised render subsequently completed
from those verified prepared files under production20× budget; its evidence is
recorded below. Existing outputs remain separate.

Dark-card full render: local technical/appearance scope **VERIFIED**; complete
creative acceptance remains **IMPLEMENTED** pending review. Current candidate:
main-project `artifacts/review/reference-motion-dark-reader-v1/final.mp4`, SHA
`a1f7d279578fd502aff81c09fde2a1cd8ba178a3b478384295796b9a76724a67`.
49.659s,1490frames,1080×1920/30,H.264/AAC,full decode passed. Benchmark334.70s;
encoder330.05s,RTF6.65<20; encoded−14.16LUFS/−2.47dBTP.

| Revision check | Exact evidence | Result |
|---|---|---|
| All five article cards use the same dark reader palette | `dark-source-review.png`, full exported `contact.png`, `source-frames.png` at5.5/14/23/33/45s; full-size23s source frame inspected | VERIFIED: navy/light text/yellow highlight, no white article panels; complete quote matches/source labels retained |
| Original source geometry retained | New/old plate dimensions match for all five; Chromium fixture exact ranges/holder rectangles unchanged | VERIFIED for measured sources/fixture |
| Other scenes preserved |7 paired decoded frames at1/9.5/18.5/28.5/37/42/48s; `revision-comparison.json` |4 identical; remaining mean absolute differences0.217,0.265,0.315 out of255 from encoding; layouts/content/timing unchanged |
| Audio preserved | Exact input mix hash, decoded PCM hash, encoded AAC packet hash compared to native final | Both decoded PCM and encoded AAC packets identical |
| Existing technical/loop gates | Exact-file final.qa.json and qa_check.py; endpoint MAE0.793/255 | No FAILs; existing terminal hold/music warnings remain, no comparison thumbnail (publishing excluded) |
| Whole-video creative acceptance | Complete playback/listening feedback has not been supplied for this revision | Pending; do not infer acceptance from tests or the requested colour change |

The shared capture change is committed as71528aa. Existing accepted captures and
outputs retain their bytes; newly captured assets record v5 policy/appearance and
receive new plate/render identities through the existing hash-bound asset path.
The native workflow and lifecycle evidence remain valid for unchanged workflow
code. This revision does not change dashboard controls, providers, narration,
scene contracts, worker leases or publication behavior.
