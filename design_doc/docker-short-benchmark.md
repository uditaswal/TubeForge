# Docker Short quality benchmark

Requested outcome: a finished 30–55 second 1080×1920 Docker tutorial on **The only Docker commands you need to get started**, with a candid comparison to the supplied `git_short_v2.mp4`, reusable source, and a concise production guide. No publication.

## Execution plan

| Phase | User-visible outcome | Acceptance and retained evidence | Out of scope |
|---|---|---|---|
| 1. Inspect reference and archive | Concrete lessons from Claude's video, scripts, comments and supplied skills | ZIP path/type/content audit before selective installation; source review; ffprobe, loudness and representative frames; concise guide | Executing attachment code before review; treating archive marketing claims as verified facts |
| 2. Ground and write | Accurate beginner command sequence with a strong promise and payoff | Official Docker sources, complete brief, canonical yt-script resources and actual hook scorer, production Codex script review | Paid APIs, local LLM scripts, unsupported claims |
| 3. Produce | Finished portrait Short with animated readable terminal, clear narration, short aligned captions and restrained sound design | Reusable topic data and renderer; real narration/alignment; final MP4 | Dashboard redesign, platform publication |
| 4. Inspect and deliver | Reviewable finished video and honest benchmark comparison | Dimensions/duration/full decode, measured loudness/true peak, caption timing and bounds, representative frames and audio review; fix defects before delivery | Claiming subjective superiority without evidence |

Current phase: **1–3 VERIFIED; 4 BLOCKED, pending listening/comparison acceptance**. All four referenced attachments are available. The ZIP contains 81 Markdown files across seven Vyral content skills; it does **not** contain the `ai-video` skill described in Claude's comments. No executable files, symlinks, absolute/traversal paths, package installers or install hooks were found in the archive inventory and command-pattern scan. All ten selected viral-short-form files were read before installation. The frame contact sheet and source code were inspected; the measured reference is 36.033s, 1080×1920, 30fps, −15.16 LUFS and −1.37 dBTP. See `docs/DOCKER_SHORT_BENCHMARK_GUIDE.md`. The supplied scripts require Python, NumPy, SoundFile, Pillow, kokoro-onnx, local voice weights/fonts and FFmpeg; neither script installs packages or downloads files.

Prior tasks 6–7 remain unfinished. The temporary tasks 5–7 reviewer account and sessions were removed and the token was verified invalid. Task 6's new stale-identity API check returned HTTP 409 in production for the parent identity; its final focused tests did not run because the one-off image contained stale tests. A migration dependency also reported missing revision `20261005_0028`. These results are not a verification of task 6.

## Script acceptance

Two actual production Codex calls were used. Attempt one was source-grounded but rejected editorially for a formal question opening and padding (127 words); the raw package remains in `data/benchmark/docker-short/attempt-1-content-package.json`. Attempt two is accepted at 115 words with the direct opening “Stop memorizing Docker commands—run your first container with these five.” All six claims map to the five official Docker references in the supplied source packet. The approved package is versioned under `examples/docker-short-benchmark/content-package.json` (SHA-256 `de23b3589769c1587ec374fb75138494997878a06bec9e830ec8810d8a4793b4`).

The final call explicitly loaded `yt-script/SKILL.md`, automation mode, and seven matching resource hashes; prompt SHA-256 `1933ddee9b936c3d5c8c088b37023db627af028111c94a538c70a865e1203325`. Actual hook scorer execution returned 44/100 for the selected opening and the runner-up “Run, inspect, stop, and remove your first Docker container with five commands.” These are heuristic review signals; direct wording and the concrete visual demonstration justify the editorial choice. No fabricated score or retention claim.

The five-command Docker exercise ran successfully in one newly created, unexposed disposable container, which was then stopped and removed. Captured output is retained at `data/benchmark/docker-short/docker-command-evidence.json`. The film will label edited listing output and the shortened log excerpt explicitly.

## Final artifact review

The final MP4 is `artifacts/benchmark/docker-short/final/docker-short.mp4`, SHA-256 `8e442b7a9c525bddd8f2f305943b0f669d9a8a59c2b4ccdb34359c1596207aba`. Exact-byte verification passed: 44.405s, 1080×1920, 30fps, H.264/AAC, −15.73 LUFS and −1.67 dBTP; complete decode; 52 caption chunks with at most three words; all-frame text safe bounds; no detected black span ≥0.2s or mixed-audio silence ≥1s. The final encoded contact sheet and full-size 9.5s command/caption frame were inspected without clipping or collisions. Eight late caption starts were refined against exact ASR word matches while retaining measured ends. A separate recognition pass agrees on 109 aligned word groups with a median start difference of 12ms and maximum 164ms after refinement; this is corroboration, not subjective listening.

The finished MP4, concise guide and versioned reusable sources are delivered for review. The user has been asked to assess full-video narration, pacing, sound balance and the comparison to Claude. This environment explicitly cannot accept audio input, so full subjective acceptance is not claimed. Next action: incorporate the user’s concrete review; keep the goal active until that quality gate is resolved. No publication and no claimed completion of prior tasks 6–7.

## Completion audit against the supplied objective

| Requirement | Authoritative evidence | Result |
|---|---|---|
| Review the video, scripts, comments and ZIP before reuse | Attachment paths, inventory/hash, full selected-skill/source reads, reference frame sheet and loudness measurements in the review report | VERIFIED |
| Inspect suspicious files, commands, dependencies and install behavior before skill copy | 81 Markdown-only members; selected ten files read; optional npx installer not executed; direct copy to canonical project skill directory | VERIFIED |
| Concise lessons document usable for future videos | `docs/DOCKER_SHORT_BENCHMARK_GUIDE.md`, 577 words, plus separate detailed audit/review | VERIFIED |
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

## Blocked audit

The same external listening/comparison dependency has remained through three consecutive goal turns: finished-video delivery, requirement audit, and this revalidation. No review answer has arrived. The final file still exists and its hash matches the verified manifest; no generation/render process remains active. The available tools cannot accept audio input, and repeated signal checks cannot establish subjective narration/sound quality or the requested overall comparison. No further independent action can close that evidence gap. Goal status is BLOCKED pending the already-requested review; resume with the assessment or concrete defects. The delivered video and reusable sources remain available.
