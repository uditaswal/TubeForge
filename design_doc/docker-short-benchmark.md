# Docker Short quality benchmark

## 13 October 2026: reusable rulebook and music revision

The operator supplied a reusable rulebook, music/CTA notes, a prompt and a guide,
and asked for the existing guide to become topic independent and for a new video
with background music. The prior viewer review said the first preview needs
revision; no timecoded defects were supplied. Keep the accepted, source-grounded
narration and its exact ContentPackage for this render.

| Phase | User-visible outcome | Acceptance test and evidence | Out of scope |
| --- | --- | --- | --- |
| 5. Reusable guide | A concise topic-independent rulebook under a topic-neutral filename, with project audit details kept in the review report | Compare every attached rule against the updated guide; include safe-zone pixels, topic schema, audio method, two-pass loudness, provenance and inspection gates | Replacing the canonical narration skill or making unsupported retention claims |
| 6. Music revision | A fresh local Short with a clearly present, speech-ducked original music bed and existing approved narration | Inspect isolated bed and voice/music balance, final AAC loudness/true peak, 9:16 spec, caption/rail bounds, encoded contact sheet and full decode; retain output hash | Publication, live platform APIs, new script attempts, unrelated production-worker refactor |
| 7. Creative review | Show the new MP4 and record the operator's comparison and any concrete defects | Viewer confirms or describes audible/visual defects; update status honestly | Claiming subjective listening from signal measurements |

Phases 5–6 can be implemented without another script invocation. Phase 7 is an
external creative acceptance gate. The attached files are reference material;
their instructions to install packages, copy an example project or publish do
not authorize those actions here.

**Phase 5 VERIFIED:** The guide was rewritten and renamed to the
[topic-independent rulebook](../docs/SHORT_FORM_VIDEO_RULEBOOK.md). It now has
canvas/action-rail bounds, a structured topic example, audio-based alignment
and fallback, music provenance, two-pass loudness and final-media gates. The
attachment and session observations remain in the separate review.

**Phase 6 VERIFIED for technical and visual acceptance:** The exact accepted
115-word package is unchanged. The local renderer now reads an original
pad/bass/pluck music configuration, saves isolated stems and provenance, ducks
under speech, and targets −14 LUFS with two-pass normalization. A revised
44.405-second 1080×1920/30 fps H.264/AAC MP4 was encoded from all 1,333
frames and fully decoded. `verify.py` passed exact package/stem/output hashes,
71 short caption chunks, revised text bounds, −14.75 LUFS, −1.34 dBTP and
−18.11 dB active-window music/speech balance. FFmpeg found no black span
≥0.2 seconds or mixed-audio silence ≥1 second. The encoded 12-frame sheet
with safe-zone guides and a full-size command/caption frame were inspected.
Final SHA-256: `7755224465e17831f61365081fb2930a1e935a04177e48233fa00ac96c183bdb`.

**Phase 7 review received:** The operator watched the music version and named
one remaining defect: it needs a spoken “follow for more” ending. That concrete
feedback authorizes the local CTA revision below. No publication. The local
benchmark renderer is separate from the production worker; this revision does
not verify publishing tasks 6–7.

### Operator revision: closing CTA

The operator reviewed the music version and requested an ending line like
“follow for more.” This is concrete creative feedback; the prior external
review gate is no longer blocked for that revision. Keep the earlier accepted
source-grounded package immutable and derive a new local benchmark revision.

| Phase | User-visible outcome | Acceptance and retained evidence | Out of scope |
| --- | --- | --- | --- |
| 8. Closing line and visual | One brief spoken follow CTA and matching on-screen ending, with the same factual Docker teaching | Diff the new package against the accepted package; only final CTA and related scene/brief fields change; review source grounding and one-ask rule | New model provider, new domain claims, publication |
| 9. Re-render and inspect | Fresh portrait MP4 with the approved factual sequence, music and the new close | Actual Kokoro/audio alignment, safe-zone storyboard, checked encode, final-byte verification, full decode, loudness/music balance and encoded ending frame | Production-worker rollout, platform upload |

The single requested CTA is an operator-directed local benchmark revision of
the previously Codex-written script. The application production job and its
approval state are untouched. If this were applied to a production job, its
exact script revision would require a fresh dashboard approval before render.

**Phase 8 VERIFIED:** The original accepted package remains byte-identical,
SHA-256 `de23b3589769c1587ec374fb75138494997878a06bec9e830ec8810d8a4793b4`.
The new local package SHA-256 is
`468301d15958c751e9d0562bd4de061e23e5d5e810a58bd67aec7374b1738197`.
A field-level comparison confirmed the same source packet, claims, hook,
metadata, first five narration sections and five scene directions. Only the
final ask, its matching scene directions and the request note changed. The
closing narration is “Follow for more practical Docker lessons.” It adds no
new factual claim and replaces the earlier save/try ask.

**Phase 9 VERIFIED for technical and visual acceptance:** Local Kokoro/Whisper
generation produced 42.869 seconds of narration and a final follow card
visible for 2.689 seconds starting with the spoken word. The checked render
encoded 1,287 frames. `verify.py` passed the actual final MP4: 1080×1920,
30 fps H.264/AAC, −14.73 LUFS, −1.37 dBTP, 69 short caption chunks,
−18.72 dB active-window music/speech balance, exact revision/stem/output
hashes and full decode. ASR recovered the closing line. FFmpeg detected no
black ≥0.2 seconds or mixed-audio silence ≥1 second. The 12-frame encoded
sheet with action-rail overlay and the full-size encoded follow card were
inspected without clipping or collision. MP4 SHA-256:
`de94b5e2841755c91de41c9544e80dfef8149a85cbb4c41fe0d0fe125fa6dfce`.
The operator has been shown the final revision; the new playback confirmation
is recorded below. The app production workflow remains untouched.

The operator then reported that the shared video did not say the new line. The
file at the reused output path was rechecked, and AAC audio extracted from
those exact encoded bytes was locally transcribed as “in place. Follow for more
practical Docker lessons.” from 39.00 to 42.16 seconds. A full MP4 with the
same SHA-256 and an extracted ending WAV were supplied under new, unique
filenames to rule out an older cached preview. The exact cause of the earlier
playback mismatch is unproven; the operator confirmed the line is audible in
the new preview. The requested CTA playback gate is VERIFIED. Overall
subjective superiority to the reference remains unclaimed.

Requested outcome: a finished 30–55 second 1080×1920 Docker tutorial on **The only Docker commands you need to get started**, with a candid comparison to the supplied `git_short_v2.mp4`, reusable source, and a concise production guide. No publication.

## Execution plan

| Phase | User-visible outcome | Acceptance and retained evidence | Out of scope |
|---|---|---|---|
| 1. Inspect reference and archive | Concrete lessons from Claude's video, scripts, comments and supplied skills | ZIP path/type/content audit before selective installation; source review; ffprobe, loudness and representative frames; concise guide | Executing attachment code before review; treating archive marketing claims as verified facts |
| 2. Ground and write | Accurate beginner command sequence with a strong promise and payoff | Official Docker sources, complete brief, canonical yt-script resources and actual hook scorer, production Codex script review | Paid APIs, local LLM scripts, unsupported claims |
| 3. Produce | Finished portrait Short with animated readable terminal, clear narration, short aligned captions and restrained sound design | Reusable topic data and renderer; real narration/alignment; final MP4 | Dashboard redesign, platform publication |
| 4. Inspect and deliver | Reviewable finished video and honest benchmark comparison | Dimensions/duration/full decode, measured loudness/true peak, caption timing and bounds, representative frames and audio review; fix defects before delivery | Claiming subjective superiority without evidence |

Earlier phases 1–3 and phase 4 technical/visual checks are **VERIFIED**. The operator later gave concrete revision feedback and confirmed the follow line audible in the fresh preview; broader comparative superiority is unclaimed. All four referenced attachments are available. The ZIP contains 81 Markdown files across seven Vyral content skills; it does **not** contain the `ai-video` skill described in Claude's comments. No executable files, symlinks, absolute/traversal paths, package installers or install hooks were found in the archive inventory and command-pattern scan. All ten selected viral-short-form files were read before installation. The frame contact sheet and source code were inspected; the measured reference is 36.033s, 1080×1920, 30fps, −15.16 LUFS and −1.37 dBTP. See `docs/SHORT_FORM_VIDEO_RULEBOOK.md`. The supplied scripts require Python, NumPy, SoundFile, Pillow, kokoro-onnx, local voice weights/fonts and FFmpeg; neither script installs packages or downloads files.

Prior tasks 6–7 remain unfinished. The temporary tasks 5–7 reviewer account and sessions were removed and the token was verified invalid. Task 6's new stale-identity API check returned HTTP 409 in production for the parent identity; its final focused tests did not run because the one-off image contained stale tests. A migration dependency also reported missing revision `20261005_0028`. These results are not a verification of task 6.

## Script acceptance

Two actual production Codex calls were used. Attempt one was source-grounded but rejected editorially for a formal question opening and padding (127 words); the raw package remains in `data/benchmark/docker-short/attempt-1-content-package.json`. Attempt two is accepted at 115 words with the direct opening “Stop memorizing Docker commands—run your first container with these five.” All six claims map to the five official Docker references in the supplied source packet. The approved package is versioned under `examples/docker-short-benchmark/content-package.json` (SHA-256 `de23b3589769c1587ec374fb75138494997878a06bec9e830ec8810d8a4793b4`).

The final call explicitly loaded `yt-script/SKILL.md`, automation mode, and seven matching resource hashes; prompt SHA-256 `1933ddee9b936c3d5c8c088b37023db627af028111c94a538c70a865e1203325`. Actual hook scorer execution returned 44/100 for the selected opening and the runner-up “Run, inspect, stop, and remove your first Docker container with five commands.” These are heuristic review signals; direct wording and the concrete visual demonstration justify the editorial choice. No fabricated score or retention claim.

The five-command Docker exercise ran successfully in one newly created, unexposed disposable container, which was then stopped and removed. Captured output is retained at `data/benchmark/docker-short/docker-command-evidence.json`. The film will label edited listing output and the shortened log excerpt explicitly.

## Earlier artifact review (12 October 2026; superseded by the music revision)

The earlier MP4 had SHA-256 `8e442b7a9c525bddd8f2f305943b0f669d9a8a59c2b4ccdb34359c1596207aba`; the same output path now contains the 13 October music and CTA revision. Exact-byte verification passed: 44.405s, 1080×1920, 30fps, H.264/AAC, −15.73 LUFS and −1.67 dBTP; complete decode; 52 caption chunks with at most three words; all-frame text safe bounds; no detected black span ≥0.2s or mixed-audio silence ≥1s. The final encoded contact sheet and full-size 9.5s command/caption frame were inspected without clipping or collisions. Eight late caption starts were refined against exact ASR word matches while retaining measured ends. A separate recognition pass agrees on 109 aligned word groups with a median start difference of 12ms and maximum 164ms after refinement; this is corroboration, not subjective listening.

The finished MP4, concise guide and versioned reusable sources are delivered for review. The user has been asked to assess full-video narration, pacing, sound balance and the comparison to Claude. This environment explicitly cannot accept audio input, so full subjective acceptance is not claimed. Next action: incorporate the user’s concrete review; keep the goal active until that quality gate is resolved. No publication and no claimed completion of prior tasks 6–7.

## Earlier completion audit (12 October 2026; superseded)

| Requirement | Authoritative evidence | Result |
|---|---|---|
| Review the video, scripts, comments and ZIP before reuse | Attachment paths, inventory/hash, full selected-skill/source reads, reference frame sheet and loudness measurements in the review report | VERIFIED |
| Inspect suspicious files, commands, dependencies and install behavior before skill copy | 81 Markdown-only members; selected ten files read; optional npx installer not executed; direct copy to canonical project skill directory | VERIFIED |
| Concise lessons document usable for future videos | `docs/SHORT_FORM_VIDEO_RULEBOOK.md`, topic-independent rules, plus separate detailed audit/review | VERIFIED |
| Docker topic, accurate commands and complete beginner teaching sequence | Exact accepted ContentPackage, official source/claim mapping, actual disposable run/ps/logs/stop/rm output and cleanup | VERIFIED |
| Strong opening and readable programmatic terminal visuals | Direct first-frame/first-sentence hook, inspected full-size and encoded sheets, 48px command text and timed state changes | Visual implementation VERIFIED; comparative creative judgment pending |
| 9:16, roughly 30–55 seconds | Final exact MP4/ffprobe: 1080×1920, 44.405s, 30fps H.264/AAC | VERIFIED |
| Short well-timed captions and safe areas | 52 groups, maximum three lexical words, exact transcript reconstruction, audio-based DTW/ASR cross-check, all-frame text bounds and encoded-frame review | VERIFIED within the documented model/inspection limits |
| Narration and appropriate sound design | Local Kokoro audio, source hashes, speech-ducked synthesized bed and action accents; final −15.73 LUFS / −1.67 dBTP; ASR content check | IMPLEMENTED; subjective listening remains unverified |
| Inspect finished video and fix detected problems | Exact final decode, frames, caption-boundary refinements, black/silence checks; final SHA still matches manifest | Technical/visual VERIFIED; audible defects cannot be ruled out by the available audio-input capability |
| Deliver outline, MP4, reusable source and honest comparison | Delivered video plus guide/review, `script.md`, source README, topic/package, producer/capture/verifier and dependency lock | VERIFIED |
| State unavailable attachments precisely | All four attachments present; ai-video, brand-profile and voice-builder absent from supplied ZIP | VERIFIED |
| Match or exceed Claude's quality without exaggerating verification | Measured comparison supports format/audio parity, larger commands and audio-based timing; pace is slower; user listening/comparison question remains unanswered | Not yet proven |

The final MP4, timeline and mix hashes were rechecked on continuation and still match their manifest. No render or model process remains running. The remaining dependency is external listening/comparison feedback, already requested on the finished artifact. Further renders, repeated technical checks or unrelated publishing work would not resolve that missing evidence. The goal remains active; no completion claim is made.

## Earlier blocked audit (12 October 2026; superseded by the operator revision request)

The same external listening/comparison dependency has remained through three consecutive goal turns: finished-video delivery, requirement audit, and this revalidation. No review answer has arrived. The final file still exists and its hash matches the verified manifest; no generation/render process remains active. The available tools cannot accept audio input, and repeated signal checks cannot establish subjective narration/sound quality or the requested overall comparison. No further independent action can close that evidence gap. Goal status is BLOCKED pending the already-requested review; resume with the assessment or concrete defects. The delivered video and reusable sources remain available.
