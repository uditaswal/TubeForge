# Docker benchmark: attachment audit and final review

See the [concise production guide](DOCKER_SHORT_BENCHMARK_GUIDE.md) for lessons to apply to future videos.

## Archive and attachment review

All four attachments were available: MP4, `tts.py`, `render.py`, and `skills.zip`. The ZIP SHA-256 is `885a76a3bea4f3f6e44d8eb12ed42ea1c4978aa94189d3a7f059bdd3e59be2ce`. It contains 81 Markdown files (420,201 uncompressed bytes), seven content skills, no executable members, symlinks, traversal/absolute paths, dependencies, or installer hooks. Its README contains an optional `npx skills add …` command; this was **not executed**. The selected `viral-short-form` skill's ten files were read and copied directly into `.agents/skills/viral-short-form/`. The named `ai-video`, brand-profile and voice-builder skills are not in this archive.

The archive includes promotional instructions and unsourced platform/algorithm assertions. These are not part of the user's request or TubeForge policy. Use only the craft guidance relevant to this benchmark; do not add advertising, fabricate metrics, or replace the canonical yt-script production contract. External image links are decorative and are not downloaded.

The two Python scripts were reviewed as text before reuse. They read local weights/audio/fonts, synthesize audio, construct frames, and invoke FFmpeg; no network download, package installation, credential access, or shell execution was found. Requirements include NumPy, SoundFile, Pillow, kokoro-onnx and FFmpeg. Local model and font paths must be supplied. The new renderer will borrow the useful layout/timing concepts, retaining attribution here, with its own topic-driven implementation.

## Finished artifact and measured comparison

The [finished local Docker Short](../artifacts/benchmark/docker-short/final/docker-short.mp4) is ready for review. Exact SHA-256: `8e442b7a9c525bddd8f2f305943b0f669d9a8a59c2b4ccdb34359c1596207aba`. [Reusable source and reproduction commands](../examples/docker-short-benchmark/README.md) and the [narration/scene outline](../examples/docker-short-benchmark/script.md) are versioned. The renderer is a local benchmark implementation; production-worker integration and publishing tasks 6–7 are not claimed complete.

| Check | Claude reference | Docker benchmark |
|---|---|---|
| Encoded format | 1080×1920, 30 fps, H.264/AAC | Same |
| Duration | 36.033s | 44.405s |
| Integrated loudness | −15.16 LUFS | −15.73 LUFS |
| True peak | −1.37 dBTP | −1.67 dBTP |
| Main terminal command font | 40 px in supplied source | 48 px, with 76 px headings |
| Caption timing | Word-length estimates in supplied source | Audio-based Whisper DTW, then exact ASR-match onset refinement; 52 chunks of at most three words |
| Command/output evidence | Scripted Git example | Five-command disposable Docker run verified; condensed output and shortened log excerpt labelled |
| Sound design | Kokoro, keys, transitions, synthesized bed | Local Kokoro af_bella, quieter keys/transitions, original synthesized pulse/bed ducked beneath speech |

The Docker version is deliberately less brisk: the extra seconds explain the background flag and the distinction between stopping and removing a container. It matches the reference's measurable portrait/codec/audio standard and improves the provenance of command output and caption timing. That does not prove it is more engaging. The reference's opening is shorter and its seven-scene rhythm is faster; the final creative comparison remains the viewer's judgment.

## Final inspection evidence

- `produce.py render` encoded 1,333 frames with every drawn text box checked inside x=70–932 and y=210–1490. Final source, phrase-audio, timeline, mix and MP4 hashes passed `verify.py`; the whole encoded file decoded without errors.
- The final encoded two-second contact sheet and a full-size 9.5s frame were inspected. No collisions or clipped command/caption text were found. Important text leaves the right action rail and lower platform controls clear; this is a conservative layout inspection, not a screenshot from every platform/device.
- 0–4.57s: topic visible immediately; direct spoken hook; five command chips reveal the promised workflow. 4.57–12.08s: complete shell command, named container, and timed `--name`/`-d` explanations. 12.08–19.25s: `ps` output rows highlight alongside narration. 19.25–25.64s: actual shortened startup-log excerpt. 25.64–33.90s: stopping is distinguished from deletion. 33.90–44.41s: removal leaves the image; final saveable recap and one viewer ask.
- Caption text reconstructs the accepted narration exactly. Two collapsed short-word boundaries stay in measured groups (“The detached” and “Save this”); eight late group onsets were refined only when contiguous ASR words matched and measured endings agreed. Original words were never replaced by ASR guesses. The separate ASR recognition pass recovered the workflow, including Docker PS and RM; one “what”/“with” recognition discrepancy is retained in the report rather than treated as proof of perfect pronunciation.
- The final MP4 measured −15.73 LUFS / −1.67 dBTP. FFmpeg found no black span ≥0.2s and no mixed-audio silence ≥1s below −40 dB. These checks do not establish subjective sound quality.
- A listening preview was attempted, but the tool explicitly reported that this environment does not support audio input. No claim of listening is made. The finished video has been shown to the user for full voice, pacing and sound-balance acceptance. **Technical and visual checks passed; subjective listening/benchmark acceptance remains pending.** Nothing was published.
