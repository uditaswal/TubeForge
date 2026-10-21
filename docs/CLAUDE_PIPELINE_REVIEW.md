# Claude pipeline review supplied by the operator

Video reviewed: preview.mp4 produced by the dashboard/backend pipeline (topic: Rust migration + AI). Reference: the standalone Codex video and the reference/ renderer in codex_pack, which look good. Root cause in one line: the pipeline runs a different, weaker render path with no QA gate. Fix it by making the pipeline call the SAME renderer as the good videos, and by adding automated checks.
- 854x480, 16:9, 77.2 s, 30 fps. (Target: 1080x1920 9:16, 25-45 s; 720x1280 acceptable for drafts.)
- Loudness -17.5 LUFS integrated, sample peak 0.0 dBFS (clipping risk). No pauses >=0.5 s anywhere (narration is continuous). No music or SFX detected. (Target: -14 LUFS, TP <= -1.5 dBTP, ducked music.)
- Header says "03 / 06" etc.; only 6 scenes for 77 s -> ~13 s per scene, far too slow.
1. Wrong format. 16:9 480p cannot be published as a Short/Reel. -> 1080x1920, safe zones per RULEBOOK.md (top 200px, bottom 420px, right edge x>930 empty).
2. Captions are whole sentences, up to 8 lines, centred over the visuals. At ~11.5 s and ~31 s the caption block covers the scene title and the diagram boxes; it even breaks mid-word ("memory / -safe"). -> Captions = max 3 words per chunk, ONE line, fixed zone below the visuals (y~1385 at 1080x1920), current word highlighted, thick stroke, never wrapped. Visuals never sit under the caption zone.
3. Visuals are anonymous labelled rectangles. Box text is ~10-14 px, boxes overlap each other, labels are clipped at box/canvas edges (e.g. "language", "Static analysis"), and the key stat "76% -> 24%" is shown as tiny header text. There are no arrows, no numbers rendered as visuals, nothing that explains the idea. -> Use scene TEMPLATES, not free layout: big_stat (huge number, e.g. 76% -> 24% with a bar/arrow), before_after, flow (2-3 nodes with arrows), checklist, terminal. Max 3 elements per scene, text 
4. No hook, too long, too dense. Frame 1 is a tiny heading ("AI helps. Easy? Not proven.") and a 24-word sentence. -> Frame 1 must show the hook large (a number or question) within 1 s. VO 8-15 words per scene, 6-8 scenes, 25-45 s total, 0.3-0.4 s tail after each scene.
5. Audio is not mastered. -> Two-pass loudnorm to -14 LUFS, TP -1.5; synthesized music bed ducked under speech; subtle SFX on scene changes (see MUSIC_AND_CTA.md).
6. No ending. -> Final scene = CTA ("Follow for more <topic>"), spec in MUSIC_AND_CTA.md.
7. Decorative counter "03 / 06" in a corner sits in a UI-unsafe area and adds nothing. -> Replace with the segmented progress bar at y~215.
8. Factual claims have no sources on screen. The video states specific figures (Google/Android 76% -> 24%, DARPA TRACTOR). Each factual scene needs a source field in the topic JSON (name + URL), and a small "Source: ..." line on screen. Verify claims against the primary source in the pipeline; do not trust the LLM's memory.
9. No QA gate. Every defect above is detectable by code. Add, before encoding: 
   - bounding-box checks: every text/box inside the canvas and inside the safe zones; no two content boxes intersect; no content box intersects the caption zone; text fits its box (shrink or fail);
   - min font-size check;
   - after encoding: ffprobe specs, full decode (ffmpeg -v error -i out.mp4 -f null -), ebur128 thresholds, contact sheet with the safe-zone rails drawn over it. Failures return a structured error to the LLM step (bounded retry, max 2) instead of producing a bad video.
- ONE renderer, used as a library by both the CLI and the dashboard backend. Delete or retire the older one.
- The LLM only returns topic JSON that validates against a strict schema (scene template + fields). It never chooses coordinates, colours or font sizes.
- vo (spoken) and caption (displayed) are separate fields; derive everything else from them.
- Word timing from forced alignment of the real TTS audio; fall back to estimates with a logged warning.
- TTS: Kokoro int8 ONNX; Piper only as fallback. Native Python venv (no Docker). Worker concurrency = 1.
- Pipe raw frames to ffmpeg (no temp PNGs). Cache static layers (background, card, shadows) once.
- Do NOT recompute identical frames: between events (typing steps, scene changes, caption chunks) frames are identical; render once and repeat the bytes.
- Draw on RGB and only redraw changed regions; avoid full-canvas RGBA alpha-composites every frame.
- Provide --draft (720x1280, -preset veryfast) and final (1080x1920). Benchmark on this machine, log the realtime factor (render seconds / video seconds) and set a budget; on a fast multi-core cloud box the reference renderer ran ~2x slower than realtime unoptimised, so measure here and optimise with the points above.
- Watch RAM: never hold all frames in memory; log peak RSS and fail if swap grows during a render.
Re-render the same Rust/AI topic through the dashboard path and show: contact sheet (with rails drawn), ffprobe output, loudness numbers, and the QA report. Do not call it done until: 1080x1920, 25-45 s, -15..-13 LUFS, no overlaps, hook large on frame 1, CTA present, sources shown.