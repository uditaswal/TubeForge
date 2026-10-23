---
name: om-video-quality
description: Review actual generated video artifacts for visual meaning, source fidelity, narration, captions and delivery quality.
---

# Review the actual video

Use after rendering or for a supplied production artifact. Follow TubeForge's rulebook and configured production targets; do not substitute generic platform statistics for acceptance evidence. This is review guidance, not a renderer or an approval mechanism.

Require the reviewed file, accepted script/scene identities, expected format and the actual technical probe. If they are unavailable, report the missing evidence and leave the result unverified.

1. Check container, streams, dimensions, orientation, duration, frame rate and audio presence against the actual brief. Decode/check the artifact with approved existing tools. Report command results accurately; never claim an unrun probe passed.
2. Inspect an overview contact sheet, every scene boundary and reveal, and watch the full final video for creative acceptance. Check the opening, middle and closing frames explicitly. Detect clipping, blank frames, bad reframes, unreadable labels, inconsistent identities, misleading generated imagery, watermarks and broken continuity. A four-frame sample cannot prove the entire video is good.
3. Compare each scene with its source claim and intended purpose. A visually attractive scene can fail if it teaches the wrong relationship. Flag repetitive cards, irrelevant stock, unsupported cinematic claims and motion that hides information. Allow purposeful holds long enough to understand the material.
4. Listen to the complete mix. Check pronunciations, speech cutoffs, missing words, unwanted pauses, distortion and music masking. Measure integrated loudness/true peak against project configuration; sample peak and integrated loudness are different measurements. Check phone-speaker intelligibility rather than blindly applying EQ recipes.
5. Verify captions against narration, word/reveal timing and accepted contract. Inspect text size, contrast and platform overlay clearance in the actual framing. Preserve accessible captions even when on-screen text overlaps; solve collisions through layout. Do not apply universal safe-zone numbers without checking the target presentation.
6. Confirm any motion/quality promise and approved fallback were honored. Tie findings to the exact artifact hash and timecodes. Changed artifacts require review again under existing TubeForge approval rules.

Return a review table: timecode/scene, evidence inspected, expected behavior, observed behavior, severity and repair. Separate verified passes, failures and missing evidence. Recommend acceptance only after required automated checks and real-artifact inspection pass. Do not claim operator approval or publish the file.

## TubeForge known-failure checklist (run before calling a job done)

Run `python .agents/skills/om-video-quality/qa_check.py data/artifacts/<job_id>` first. It prints PASS/WARN/FAIL for the failures we have already hit; a FAIL blocks acceptance, a WARN needs a human look. Passing it is not creative acceptance: still view the contact sheet and listen.

1. **Duration vs voice.** The writer's word budget is spoken words ÷ speaking rate, and the rate depends on the voice (Kokoro ≈ 2.3 words/s, Piper ≈ 2.7). 60 s ≈ 140 words, not 190. Landscape jobs must land within ±40 % of the target; Shorts within 25–45 s. If a script is long, shorten the script; do not widen the gate again.
2. **Card text length.** Animated-card headings must be ≤ 30 characters (a label, never a sentence) and elements ≤ 32. Long hook sentences belong in the narration, not the heading.
3. **No repeated words on screen.** The thumbnail headline, the on-frame headline and the narration must not say the same thing twice. Thumbnail text is 2–3 words (or a short question plus payoff) and the thumbnail's video frame comes from after the opening hook.
4. **Loudness.** Reference Shorts: −15…−13 LUFS and true peak ≤ −1.5 dBTP; legacy jobs −16.5…−12.5 LUFS, ≤ −1 dBTP. Peaky voices land a little under target; re-measure the encoded file, not the narration.
5. **Logos and stock.** A scene about a named technology gets its `logo` slug (list in the v8 prompt, assets in `src/tubeforge/assets/logos`); stock comes from the local library first (`origin` in `reference/plates/manifest.json`). Check the badge is legible on the light disc and the stock matches the scene.
6. **Publishing package.** Title ≤ 100 characters, description exactly two lines (hook + call to action/source/hashtags), thumbnail 1280×720 JPEG ≤ 2 MB. Everything stays editable on the Publishing page before a draft is saved.
7. **Services run stale code.** After any change to prompts, layout or skills restart the Claude runner and `web worker scheduler`; the publisher worker needs a restart for adapter changes. A "prompt differs; redeploy host wheel" preflight error means a runner is on old code.
8. **Cache and allowances.** An identical request replays its cached script. Change the brief to get a new script; never reset an attempt allowance.

Provenance: docs/reviews/openmontage/README.md (repo-only archive, not packaged). No external reviewer, provider or script is installed by this skill.
