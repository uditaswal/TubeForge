# Docker benchmark: attachment audit and final review

See the [topic-independent production rulebook](SHORT_FORM_VIDEO_RULEBOOK.md) for lessons to apply to future videos. This report retains benchmark-specific attachment and inspection evidence.

## Archive and attachment review

All four attachments were available: MP4, `tts.py`, `render.py`, and `skills.zip`. The ZIP SHA-256 is `885a76a3bea4f3f6e44d8eb12ed42ea1c4978aa94189d3a7f059bdd3e59be2ce`. It contains 81 Markdown files (420,201 uncompressed bytes), seven content skills, no executable members, symlinks, traversal/absolute paths, dependencies, or installer hooks. Its README contains an optional `npx skills add …` command; this was **not executed**. The selected `viral-short-form` skill's ten files were read and copied directly into `.agents/skills/viral-short-form/`. The named `ai-video`, brand-profile and voice-builder skills are not in this archive.

The archive includes promotional instructions and unsourced platform/algorithm assertions. These are not part of the user's request or TubeForge policy. Use only the craft guidance relevant to this benchmark; do not add advertising, fabricate metrics, or replace the canonical yt-script production contract. External image links are decorative and are not downloaded.

The two Python scripts were reviewed as text before reuse. They read local weights/audio/fonts, synthesize audio, construct frames, and invoke FFmpeg; no network download, package installation, credential access, or shell execution was found. Requirements include NumPy, SoundFile, Pillow, kokoro-onnx and FFmpeg. Local model and font paths must be supplied. The local renderer borrows the layout/timing concepts and synthesizes its own music from topic data.

The later supplied `RULEBOOK.md`, `MUSIC_AND_CTA.md`, `PROMPT.md` and `GUIDE.md` were read as reference material on 13 October. They informed the updated rulebook, original pad/bass/pluck bed, safe rail and two-pass loudness check. Their instructions to install packages, copy a new project or publish were not followed. The note that synthesized music has “no licensing” is overbroad: the rendered music has no sampled track, but dependency, voice and font terms still need review before distribution. The supplied `render.py` was read for its music/SFX method before adaptation.

## Finished artifact and measured comparison

The [revised local Docker Short](../artifacts/benchmark/docker-short/final/docker-short.mp4) is ready for review. Exact SHA-256: `de94b5e2841755c91de41c9544e80dfef8149a85cbb4c41fe0d0fe125fa6dfce`. [Reusable source and reproduction commands](../examples/docker-short-benchmark/README.md) and the [narration/scene outline](../examples/docker-short-benchmark/script.md) are versioned. The renderer is a local benchmark implementation; production-worker integration and publishing tasks 6–7 are not claimed complete.

| Check | Claude reference | Docker benchmark |
|---|---|---|
| Encoded format | 1080×1920, 30 fps, H.264/AAC | Same |
| Duration | 36.033s | 42.869s |
| Integrated loudness | −15.16 LUFS | −14.73 LUFS |
| True peak | −1.37 dBTP | −1.37 dBTP |
| Main terminal command font | 40 px in supplied source | 48 px, with 76 px headings |
| Caption timing | Word-length estimates in supplied source | Audio-based Whisper DTW and exact ASR matches; 69 chunks of at most three words, 84 px |
| Command/output evidence | Scripted Git example | Five-command disposable Docker run verified; condensed output and shortened log excerpt labelled |
| Sound design | Kokoro, keys, transitions, synthesized bed | Local Kokoro af_bella, action effects, configurable original pad/bass/pluck bed with speech ducking; music measures −18.72 dB relative to speech in voiced windows |

The Docker version is deliberately less brisk: the extra seconds explain the background flag and the distinction between stopping and removing a container. It matches the reference's measurable portrait/codec/audio standard and improves the provenance of command output and caption timing. That does not prove it is more engaging. The reference's opening is shorter and its seven-scene rhythm is faster; the final creative comparison remains the viewer's judgment.

## Final inspection evidence

- `produce.py render` encoded 1,287 frames with every drawn text box checked inside x=60–930 and y=210–1490. Final source, phrase-audio, music/effect stems, timeline, mix and MP4 hashes passed `verify.py`; the whole encoded file decoded without errors.
- The [encoded 12-frame sheet](../artifacts/benchmark/docker-short/final/encoded-contact-sheet-cta.jpg) with safe-zone guides and a full-size 11.38s command/caption frame and a full-size encoded 42.42s follow card were inspected. No collisions or clipped command/caption text were found. Important text leaves the right action rail and lower platform controls clear; this is a conservative layout inspection, not a screenshot from every platform/device.
- 0–4.57s: topic visible immediately; direct spoken hook; five command chips reveal the promised workflow. 4.57–12.08s: complete shell command, named container, and timed `--name`/`-d` explanations. 12.08–19.25s: `ps` output rows highlight alongside narration. 19.25–25.64s: actual shortened startup-log excerpt. 25.64–33.90s: stopping is distinguished from deletion. 33.90–40.18s: removal leaves the image. 40.18–42.87s: a spoken and visible follow CTA closes the video.
- Caption text reconstructs the operator-directed local revision exactly. “commands—run”, “The detached” and “Follow for” were split at matching ASR word times so the 84 px caption line fits; five late group onsets were refined only when contiguous ASR words matched and measured endings agreed. Original words were never replaced by ASR guesses. The separate ASR pass recovered the workflow and closing line; an earlier “what”/“with” recognition discrepancy remains documented rather than treated as proof of perfect pronunciation.
- The final MP4 measured −14.73 LUFS / −1.37 dBTP after two-pass normalization and AAC encoding. Music provenance and exact stem hashes are in `music-provenance.json`; active-window music is −18.72 dB below speech. FFmpeg found no black span ≥0.2s and no mixed-audio silence ≥1s below −40 dB. These checks do not establish subjective sound quality.
- A listening preview was attempted earlier, but the tool explicitly reported that this environment does not support audio input. No claim of listening is made. The operator requested the follow ending after reviewing the music version. The final encoded AAC was independently extracted and transcribed as “in place. Follow for more practical Docker lessons.” from 39.00 to 42.16s. After the user reported that the shared preview did not say the line, an identical-byte MP4 was supplied under a new filename to avoid a possible cached preview. The operator confirmed the line is audible in the new preview. **The requested ending is VERIFIED by playback; overall subjective benchmark superiority remains unclaimed.** Nothing was published.
