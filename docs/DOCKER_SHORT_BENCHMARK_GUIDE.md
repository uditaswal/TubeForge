# A production guide from the Claude reference

## What the supplied example does well

The inspected `git_short_v2.mp4` is 36.033 seconds, 1080×1920, 30 fps, H.264/AAC. FFmpeg measured −15.16 LUFS integrated loudness and −1.37 dBTP. The sampled frames show a clear hierarchy: hook, numbered step, terminal, then a separate caption zone. Typing reveals commands progressively; colored output makes staged versus unstaged files distinguishable. The workflow has a useful check before commit and a final check afterward. Its final ask is brief.

Keep these practices: show the payoff immediately; teach a small complete workflow; make terminal text real editable text; reveal state changes at the moment they are explained; use one short caption chunk in a reserved zone; add subtle clicks/transitions and keep music beneath speech. Sound design should support actions, not decorate every word.

## What still needs improvement

- The renderer estimates word timing from character length. That is not forced alignment; matching the full sentence duration cannot prove individual words line up. Align the actual synthesized audio and inspect command-name boundaries.
- Terminal text is 40 px at 1080 width. Dense output is small on a phone. Our command block should use at least 48–54 px, with fewer output lines and intentional shell continuations for long commands.
- The reference terminal output is scripted illustration, not a captured command run. Preserve accurate syntax, cite official command behavior, and distinguish edited or abbreviated output from exact output.
- The scripts hardcode the story and paths, duplicate narration between TTS and render sources, assume seven scenes, and do not reject a failed FFmpeg encode. Use one topic document, measured timings, explicit validation and checked process exit codes.
- A generated music bed avoids copying a commercial recording, but “generated means no licensing issues” is too broad. Retain source provenance and the applicable model/dependency terms.
- No measured audience performance was supplied. Hooks and retention devices are creative choices, not proof of improved retention. I have inspected frames and measured the reference audio; I have not claimed a subjective listening comparison.

## Apply to every technical Short

1. Scope the promise to one achievable task. For this video, Docker is already installed and the viewer manages one disposable practice container.
2. Source each command and its effect from official documentation. Show the same container name throughout; stop it before removing it.
3. Write the spoken script once. Keep sources, hook alternatives, scores and directions out of narration. Render from the approved text and actual audio timings.
4. Give the opening a readable statement on frame one. Show a command or concrete result early; skip logos and introductions.
5. Reserve a text-safe region away from the right action rail and bottom platform UI. Keep captions below the terminal, not on top of it. Check at phone scale.
6. Pace typed commands to narration, then hold the completed command long enough to read. Use color for command/output/state, never as the sole signal.
7. Mix speech first. Target roughly −15 to −16 LUFS, true peak at or below −1 dBTP after AAC; measure the final encoded MP4.
8. Inspect start, every command completion, state transitions, caption boundaries and final frame; perform full decode and duration checks. Report any remaining uncertainty honestly.

## Deliverables and acceptance

The [finished 44.4-second MP4](../artifacts/benchmark/docker-short/final/docker-short.mp4), [narration/outline](../examples/docker-short-benchmark/script.md) and [reusable sources](../examples/docker-short-benchmark/README.md) are ready. Technical and visual checks passed; subjective listening/comparison acceptance remains pending. The [detailed audit and final review](DOCKER_SHORT_BENCHMARK_REVIEW.md) records archive safety, exact measurements, timecoded inspection and limitations. No publication.
