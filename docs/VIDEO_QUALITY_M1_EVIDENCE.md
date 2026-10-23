# Milestone 1 acceptance evidence — 23 October 2026

State: **IMPLEMENTED**. The new signal diagnostics ran through a real local video; full audiovisual acceptance is still open.

The source was the previously reviewed `8c23e099f53640688fb8c26957ea4e57` reference topic. `scripts/video_quality_smoke.py` used that exact topic as a test fixture and generated fresh Kokoro speech, alignment, mix and final video. This test does not create a production approval. Its output is [final.mp4](/home/uditaswal/docker/tubeforge/Youtube_Video_Producer/artifacts/benchmark/video-quality-m1-20261023/final.mp4), SHA-256 `e149976b40506cca42979141aa7e90d9b45c6a7a75877eee5e09fb3e1318757a`.

| Gate | Observed result |
|---|---|
| Focused tests | `11 passed, 1 deselected` on the isolated branch: audio-health, signed-in ASGI dashboard and reference Shorts excluding the long duplicate encoder test. The duplicate encoder test was interrupted after a slow sandbox run; the separate full render exercises encoding and post-encode QA. |
| Synthesis and alignment | Seven Kokoro scenes, seven measured `whisper-base-en-dtw-v1` alignments, zero timing fallback warnings; 28.802-second timeline. |
| Encoded format | FFprobe: 1080×1920, H.264, 30 fps, AAC 48 kHz, 28.802 seconds. Full `ffmpeg -xerror` decode passed. |
| Audio gate | Encoded −14.3 LUFS and −2.52 dBTP; library QA `passed: true`. Narration and encoded-health reports each recorded zero advisory warnings. Their hashes match narration WAV and final MP4. Zero signal warnings does not establish a natural-sounding performance. |
| Delivery QA | `.agents/skills/om-video-quality/qa_check.py` passed duration, speaking rate (79 words / 28.8 s), card headings, title and description checks. It warned that this isolated fixture has no composed thumbnail; thumbnail acceptance is outside this audio milestone. |
| Visual inspection | [Contact sheet](/home/uditaswal/docker/tubeforge/Youtube_Video_Producer/artifacts/benchmark/video-quality-m1-20261023/contact-sheet.png) inspected at phone scale: hook, progress, captions and closing CTA are legible in sampled frames. Teaching scenes are visually repetitive; this is a known failure for the later visual milestone, not a claim of visual quality acceptance. |
| Dashboard | Signed-in ASGI route test passed with authentication required before login, a successful login, served audio-report UI and authenticated missing-artifact 404. A live browser JavaScript interaction has not been observed. The sandbox stalls even a minimal FastAPI synchronous route; the local focused suite passed outside that sandbox. |

The agent could inspect the encoded contact sheet and signal data but could not hear the complete mix. A full listen must check every scene for pronunciation, missing/cut words, pauses, music masking and caption alignment. This is the remaining acceptance gate before milestone 1 can be **VERIFIED**. The report must stay separate from operator approval, and any changed audio requires fresh review.

The original shared worktree received an unrelated thumbnail commit during this run. The five changed render-path files in the isolated worktree were checked byte-for-byte against those used for the completed render. The isolated branch excludes that thumbnail change.
