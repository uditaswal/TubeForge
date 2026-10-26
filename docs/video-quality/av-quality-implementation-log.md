# A/V quality implementation log (26 Oct 2026)

Branch: `claude/av-quality-phase1` (worktree `../tubeforge-av-quality`, based on `dev` at `2e98f49`).
Plan of record: [reviews/2026-10-26-av-quality-hyperframes-voicestudio.md](../reviews/2026-10-26-av-quality-hyperframes-voicestudio.md) §7
(phases 0–5). The operator approved all three §8 decisions on 26 Oct: HyperFrames music too
(in addition to a curated catalog), the HyperFrames renderer trial, and a Kokoro fp32 A/B.
This log records what was actually run and built against that approval, with evidence.

## Phase 0 — baseline benchmark: can HyperFrames render on this host?

**Outcome: yes, comfortably within budget.** This was the biggest open risk in the review
(§7: "If HyperFrames cannot render... within budget on this host, the fallback is..."). It is
resolved.

### What was run

`npm install hyperframes@0.8.192` in a throwaway directory
(`/home/uditaswal/docker/tubeforge/hf-bench`, outside any TubeForge repo, not committed).
`hyperframes doctor` reported: Node v24.19.0 OK, FFmpeg 7.1.5 OK, FFprobe OK, system Chrome at
`/usr/bin/chromium` OK (the same binary the TubeForge worker image already installs), 4 CPU
cores (Intel i3-5005U @ 2.00GHz — a weak, low-power chip), memory flagged low (3.7 GB total,
~1.4–2.0 GB available alongside the running Docker services), and disk flagged low **only**
because HyperFrames defaults its frame cache and temp directory to `/tmp`, which on this host
is a 1.9 GB tmpfs — not the 797 GB real disk. Both resolved by pointing
`HYPERFRAMES_EXTRACT_CACHE_DIR` and `TMPDIR` at a real-disk path.

A scaffolded portrait (1080×1920, 30 fps) test composition was extended from the default 10 s
blank title card to a 60-second, 20-beat animated composition (a title, a card, three dots
tweened with GSAP 20 times across the minute) — deliberately closer to a real reference Short's
shot count than a static frame, so the capture engine has continuous motion to track the whole
way through, not one frozen image.

`hyperframes check --json` on the first draft of that composition caught a real authoring bug
(the title sat behind an opaque card — `text_occluded`, `coveredFraction: 1`) and seven GSAP
tween-overlap warnings, both genuine defects in the throwaway test file, not tool noise — direct
confirmation that the review's §4.6 craft gate (`check`'s layout/lint findings) catches real
problems before a frame is ever rendered.

### Render results (draft quality, 1 worker, system Chromium — no GPU, no `chrome-headless-shell` acceleration)

| Composition | Duration | Wall time (tool-reported) | RTF | Peak memory available during render |
|---|---|---|---|---|
| 10 s, 1 title | 10.0 s | 45.7 s | 4.57× | ≥1.5 GB free throughout |
| 60 s, 20 beats, continuous motion | 60.0 s | 1 m 47.2 s | **1.79×** | ≥1.8 GB free throughout, stable before/after |

Our reference-short config's `budget_realtime_factor` is **20×**. Both renders landed far
under that ceiling, and the longer, more realistic composition was *faster* per second of
output than the trivial one — HyperFrames' built-in static-frame dedup
(`[static-dedup] reused 909/1800 frame(s) (51%)`) skips re-encoding unchanged frames, and real
content (held shots, cuts) has more of those than a constantly-moving synthetic test.
Memory stayed flat across both renders; no swell, no OOM, no visible impact on the TubeForge
Docker services running alongside it.

An attempt to install `chrome-headless-shell` for HyperFrames' faster `BeginFrame` capture path
succeeded (`npx @puppeteer/browsers install chrome-headless-shell`), but the render still fell
back to the slower screenshot-capture path even with `HYPERFRAMES_BROWSER_PATH` set — not
investigated further since the slow path already fits comfortably inside budget. The faster
path, if it can be made to engage (the tool's own hint: "A BeginFrame probe timeout can occur
when browsers start together on one GPU; fewer `--workers` may help" — already at `--workers 1`
here), is pure upside for a future pass, not a blocker.

The rendered 60 s file was inspected: `ffprobe` confirms 1080×1920, 30 fps, 60.0 s, H.264; a
6-frame contact sheet shows the three dots at genuinely different x-positions frame to frame
(real per-frame motion capture, not a frozen render). Evidence files on this host (not
committed — throwaway benchmark, reproducible with the commands above):
`/home/uditaswal/docker/tubeforge/hf-bench/{testproj-draft.mp4,bench60-draft.mp4}`.

### What this does and doesn't prove

It proves the engine runs, renders at the right resolution/frame rate, tracks real motion, and
fits the time/memory budget on exactly this host, for a synthetic composition. It does **not**
prove: a real content composition built from ~25 vendored registry components renders at the
same speed (richer compositions — real stock footage, source-screenshot plates, multiple text
layers — will likely be slower than three tweened divs); that captions/audio muxing adds
meaningful time; or that the full vendoring/integration work in the review's §4.2–§4.3 (Node +
Chrome in the worker image, ≈25 registry components ported to portrait, GSAP/fonts vendored
off-CDN) is itself quick. Phase 4 (the actual renderer integration) remains **NOT STARTED** —
this was the go/no-go check for attempting it, and the answer is go.

## Phase 1 — real music variety and licensed, caused sound effects

**Outcome: implemented and tested on the feature branch; not yet merged or heard by the
operator.** This is the §4.5 "cheapest large improvement" from the review, done without
touching the renderer.

### What changed

`src/tubeforge/rendering/shorts/audio.py`:
- `synth_music()` now picks one of **four** distinct moods (`steady` 96 BPM, `driving` 112 BPM,
  `moody` 84 BPM/sparser, `bright` 104 BPM), each a different chord progression and pluck
  density, deterministically from the topic's title (`sha256(title) % 4`) — reproducible per
  job, but no longer the identical bed under every video (the review's §1 P0 finding).
- `master()` gained required `templates` (each scene's template string) and `title` parameters.

`src/tubeforge/rendering/shorts/sfx.py` (new): places one licensed sound effect per scene cut,
chosen by the **destination scene's template** — a real cause on screen, replacing the old
near-inaudible filtered-noise burst (`.035` amplitude against a `.75` voice peak, ≈ −26 dB
below voice — effectively unheard) with an audible, purposeful effect (peak normalized to
`.30`, roughly between the music bed and the voice, per the sound-design levels in the review):

| Destination scene | Effect | Cause |
|---|---|---|
| `big_stat` | `pop` | a number landing |
| `before_after`, `flow` | `whoosh-short` | a transition |
| `checklist` | `click` | an item checked off |
| `terminal` | `key-press` | typed input |
| `cta` / `loop` (the payoff) | `riser` (10.03 s cinematic build) | crests exactly on the final cut, trimmed from its front if there isn't a full 10 s of lead time |
| any other/future template | `whoosh-short` (fallback) | — |

`src/tubeforge/assets/sfx/` (new, 19 files, 1.3 MB): the Pixabay Content License sound-effect
library vendored byte-for-byte from the reviewed `heygen-com/hyperframes` checkout
(`skills/media-use/audio/assets/sfx/`, local commit `24965372dbbe`), with `manifest.json`
(cue → file, duration, description, source, license) and `LICENSE-pixabay.md` recording the
chain of custody, mirroring the existing `assets/logos/` provenance convention. The Pixabay
Content License permits commercial use, redistribution in a derivative work, and needs no
attribution — matching the operator's no-Content-ID-strike stance, independent of HyperFrames'
own Apache-2.0 license (which covers its code, not this audio).

`src/tubeforge/pipeline/reference_short.py`: `render()` now passes each scene's template and
the topic's title into `master()`. `RENDERER_VERSION` bumped to
`reference-short-v1/render-2` so a config/code change like this correctly invalidates any
cached/checkpointed render under the old audio pipeline (the existing mechanism for this,
unused since the constant's introduction).

### What was not pursued, and why

**Real licensed music tracks** (the review's first recommendation) are still **not** in the
(still-empty) `music_catalog` — that needs the operator to supply or approve specific tracks
with verifiable source/license records (`pipeline/music.py`'s `MusicTrackRecord` already
enforces a named license, not a generic "free" label), which is a licensing judgment call this
session should not make unilaterally, especially given the explicit no-strike constraint.
**What *was* found and fixed: `music_catalog` was already fully built (schema, checksums,
license records, dashboard upload) but only ever consulted for publication-description
attribution — never actually mixed into a render.** That integration gap is real and still
open; wiring a catalog track into `master()`'s `bed` (instead of `synth_music()`, loudness- and
duration-matched, with the mood synth kept as the no-catalog fallback) is a small, well-scoped
follow-up once at least one real track is approved — most of the plumbing (the `templates`/
`title` parameters, the provenance fields) is already in place to extend.

**HyperFrames' own bundled music** turned out not to exist as a usable asset: the only `.mp3`
found outside its SFX library (`.agents/skills/changelog-video/assets/bgm.mp3`, a single track
for one internal HeyGen skill) is a 132-byte Git LFS pointer in the local checkout, not real
audio (`git lfs pull` was not attempted — a single unverified track for an unrelated skill is
not a catalog). HyperFrames' actual free-music *methodology* — enter at the track's strongest
bar, 0.4 s fade-in / 1.5 s fade-out, local Lyria/MusicGen generation as a fallback when no
catalog exists — is captured in the review (§4.5) for when real tracks are sourced.

**Local MusicGen generation** (`transformers` + `torch`, ~300 MB first download, slow on CPU)
was not attempted this session: `torch`/`transformers` are not installed in `.venv-benchmark`,
and installing them on a 3.7 GB host already running the TubeForge Docker services carried a
real risk of destabilizing those services for a generation path whose output quality is
unverified. This is a candidate follow-up, gated on the operator wanting to spend that
install/runtime budget.

### Evidence

- 9 new tests (`tests/test_shorts_audio.py`): mood determinism and coverage across 200 varied
  titles; reproducibility (same title → byte-identical audio); every `CUE_BY_TEMPLATE` /
  fallback / riser entry resolves to a real vendored file with a named license; a real-ffmpeg
  decode of a vendored cue is peak-normalized within 0.1%; cue placement trims correctly when
  a cue needs more lead time than is available (the riser case) and raises if a cue would start
  past the end of the mastered audio (a real scheduling bug, not silently dropped); a full
  `master()` run end-to-end on synthetic narration with the real cue set, asserting the exact
  per-scene cue sequence and that loudness/true-peak gates still pass; a rejected
  template-count mismatch; `reference_short.render()` correctly forwards `templates`/`title`.
  All 9 pass.
- Existing suite: 47 tests across `test_reference_shorts.py`, `test_audio_health.py`,
  `test_plates.py`, `test_ending_and_length.py`, `test_spoken_short.py`,
  `test_reference_content.py`, `test_script_craft.py`, `test_writers_room.py` — all pass
  unchanged.
- **Full repository suite** (607 tests): **586 passed**, 18 skipped (opt-in smoke tests needing
  Piper/Ollama/captured media, not present on this host), **3 failed — all three confirmed
  pre-existing** by running the same two tests against clean `dev` (`2e98f49`, before any of
  this branch's changes): `test_voice_preview_is_synthesized_once_then_served_from_persistent_cache`
  (already documented in `docs/HANDOFF.md` — no local Piper), plus two more not yet documented
  there — `test_config.py::test_production_shorts_use_codex_local_piper_and_measured_audio`
  (same cause: `pipeline.piper.model_path` does not exist on this host) and
  `test_shorts_workflow.py::test_shorts_renderer_is_portrait_30fps_and_caps_visual_holds` (a
  subtitle-margin assertion against the **retired legacy 16:9** `PreviewRenderer`, unrelated to
  the reference-short pipeline touched here). **This branch introduces zero test regressions.**
- End-to-end manual run: the same 120-word reviewed narration text from job `e53f4e8387424f65b6a6b50fbb166efa`
  (the Railway-breach Short inspected in the review) was mastered through the new pipeline with
  all 7 scene templates; the resulting provenance recorded mood `driving` (112 BPM), the cue
  sequence `pop, whoosh-short, whoosh-short, click, key-press, riser`, and a mastered mix at
  −14.0 LUFS / −1.92 dBTP (inside the existing gate). Stem-level check via `ffmpeg volumedetect`:
  effects peak −10.5 dB, music bed peak −29.1 dB, final mix peak −2.6 dB — effects are now
  genuinely audible, under the voice, above the bed, as intended.

**Not done: the operator has not heard this.** Per AGENTS.md ("Creative work needs a real
generated artifact inspected against the quality bar... tests alone are insufficient") this
remains **IMPLEMENTED**, not **VERIFIED**, until a real rendered video with this audio path is
watched end to end. Rendering a full real job through the orchestrator (not just `master()` in
isolation) was not done this session — the next action.

## Phase 2 — Kokoro voice model A/B (evidence gathered, not decided)

**Outcome: both renders produced; the two are close enough by every available objective
measure that the choice genuinely needs the operator's ear**, exactly as the review predicted.

### What was run

The production Kokoro fp32 ONNX weights (325,532,387 bytes) were downloaded from
`thewh1teagle/kokoro-onnx`'s GitHub release (the same weights the bundled `voices-v1.0.bin`
style vectors already pair with) to a throwaway location, **not** wired into
`config/production.yaml` — no production config was changed. The exact 120-word reviewed
narration text from job `e53f4e8387424f65b6a6b50fbb166efa` was synthesized with both the
current `kokoro-v1.0.int8.onnx` and the new fp32 model, same voice (`af_bella`), same speed
(`1.0`), via `kokoro_onnx.Kokoro` directly (bypassing the adapter's cache so both runs are
independent).

| Model | Wall time | Audio duration | RTF | Peak level | Mean level |
|---|---|---|---|---|---|
| int8 (current production) | 57.1 s | 45.2 s | 1.263 | −0.5 dB | −21.2 dB |
| fp32 | 50.3 s | 45.3 s | 1.111 | −2.3 dB | −21.0 dB |

Both comfortably inside `budget_realtime_factor: 20`; fp32 was marginally *faster* on this CPU
(int8 dequantization overhead without SIMD-optimized int8 kernels is a known quirk on some
ONNX Runtime CPU builds) — so adopting fp32 would not cost render time.

A coarse frequency-band energy comparison (no quantization-artifact detector installed) found
the two spectra nearly identical (low/mid/high/very-high band energy ratios within 0.003 of
each other) — this rough check found no measurable signature of quantization degradation, which
means it is not useful for deciding between them; only listening is.

### Evidence delivered

Both WAV files (`int8.wav`, `fp32.wav`, same text, same voice, volume-matched to within 2 dB)
are at `/home/uditaswal/docker/tubeforge/kokoro-ab/` on this host and were sent to the operator
for a blind-ish A/B listen. **No config change was made and none should be, until the operator
reports a preference** — per the review's own acceptance criteria for this phase ("operator
prefers by blind listen") and AGENTS.md ("Accept a script only after reviewing... not test
results alone", applied here to voice).

### Next action if fp32 is preferred

Swap `pipeline.kokoro.model_path` in `config/production.yaml` to the fp32 file (vendor it under
`models/`, outside this session's git changes since `models/` holds operator-supplied binaries
per the existing convention), bump `pipeline.kokoro.adapter_version` so the voice cache key
changes and no stale int8 renders are served from cache, and re-run a real job to confirm.

## Phase 2b — Kokoro voice blending (VoiceStudio competitive-analysis Action 12)

**Why this, and not more of VoiceStudio.** The operator asked directly whether VoiceStudio had
actually contributed anything to this round of code, beyond being reviewed in writing — it
had not; the music/SFX work (phase 1) is entirely from HyperFrames, and the Kokoro fp32 test
(phase 2) is just the official weights, not a VoiceStudio technique. Two concrete VoiceStudio
items were weighed for this session:

- **UTMOS naturalness scoring** (review §5.2) was judged too large and too risky to rush here:
  it needs the specific `UTMOS22Strong` architecture *and* a trained checkpoint (not just a pip
  package), plus `torch` (a 178 MB CPU-only wheel, checked but not installed), and real
  inference RAM on a host already at ~1.5–2 GB available alongside the live TubeForge services.
  Left for a dedicated phase with its own plan, per AGENTS.md's multi-phase-work rule.
- **`[pause]`/`[slow]`/`[emphasis]` inline tags** (review §5.3) were judged to need a schema
  change, not an audio-code change: `Scene.vo` is the exact reviewed, word-counted narration
  (`8 <= len(words) <= 15`, `reveal_words` indexed into it, display/spoken mapping validated by
  exact word count at three separate stages in `prepare.py`/`spoken.py`). Making a tag system
  safe means either a new schema field carrying pause positions (versioned, validated,
  surfaced to the writers'-room/yt-script authoring flow) or bracket-tag parsing that every one
  of those word-count validators must correctly see through. That is real, valuable, and
  explicitly pending — but it touches script authorship and the approval contract, not just the
  render path, so it is **not started** here rather than rushed.

**What was safe to do now: weighted voice blending** (`docs/competitive-analysis.md:199,:917` —
ported from Kokoro-FastAPI, Apache-2.0). A blend is a different Kokoro *style vector* — nothing
about the text, its word count, its timing or its alignment changes; only the acoustic timbre
does. `kokoro_onnx.Kokoro.create()` already accepts a raw `numpy.float32` array in place of a
voice name (confirmed via `inspect.signature`), so this needed no new dependency.

### What was built

- `src/tubeforge/providers/voice/voice_blend.py` (new): `parse_blend_spec` validates a
  `"name:weight+name:weight[+...]"` spec (≥2 distinct components, positive finite weights,
  normalized to sum to 1); `resolve_blend` builds the weighted vector from
  `Kokoro.get_voice_style`.
- `KokoroProviderConfig.voice_blends: dict[str, str]` (new, default empty): named blends,
  validated at config load so every referenced voice is in `voices` and no blend name collides
  with a plain voice name. **Deliberately not added to `voices`** — the Studio voice picker
  (`api/app.py:1447`) reads `voices` directly, so blends stay config-only/experimental until
  someone decides they should be an operator-facing choice, which is a product call, not mine
  to make unasked.
- `KokoroVoiceProvider.synthesize()`: accepts a blend name alongside plain voice names; resolves
  it to a style vector only at the point of a real synthesis call (cache hits never touch
  Kokoro). The existing cache key (keyed on `request.voice_id`, which is the blend name) and
  model-file-hash identity already make this correct with no further change.

### Evidence

11 new tests (`tests/test_voice_blend.py`): spec parsing/normalization; six malformed/degenerate
specs rejected (one component, duplicate name, zero/negative/non-numeric weight, wrong
separator); config rejects a blend naming an unconfigured voice or colliding with a plain voice
name; a real-Kokoro integration test (skipped here only because this worktree has no local
`models/` symlink — the sandbox's own file-access policy blocks creating one from this
directory; the mechanism was exercised directly instead, see below) asserting a blend's output
checksum differs from both pure voices and its duration is close to either one's.

**Real audible evidence**, synthesized with the production int8 model and the exact text "Railway
confirmed a cyberattack that let hackers reach some customer secrets.": a 60/40 `af_bella`/
`af_sarah` blend produced genuinely distinct audio (different SHA-256 from either pure voice,
4.71 s vs. 4.78 s / 4.48 s — the blended style vector changes pacing too, not just timbre).
Files are on this host, not delivered this turn (see the operator reply): `pure-bella.wav`,
`pure-sarah.wav`, `blend-bella60-sarah40.wav` in `/home/uditaswal/docker/tubeforge/kokoro-ab/`.

This is **IMPLEMENTED, not operator-watched**: nobody has asked for a blended channel voice yet,
and nobody has heard this one. It is a capability, demonstrated working, waiting on a decision
about whether any channel wants it and what ratio.

## Summary: state per phase

| Phase | State | Evidence | Next action |
|---|---|---|---|
| 0. Benchmark | **VERIFIED** — go decision made | this log, §Phase 0 | none (informs phase 4 go/no-go) |
| 1. Sound (music variety + SFX) | **IMPLEMENTED**, not operator-watched | this log, §Phase 1; 9 new + 47 existing + 586/607 full-suite tests pass, zero regressions | render one real job end to end through the orchestrator (not just `master()`), watch/listen to the full video, then mark VERIFIED |
| 2. Voice (Kokoro fp32 A/B) | Evidence gathered, **decision pending** | this log, §Phase 2; two WAVs on disk | operator listens, reports a preference; if fp32, make the two-line config change above |
| 2b. Voice blending | **IMPLEMENTED**, not operator-watched, no channel has opted in | this log, §Phase 2b; 11 new tests, real audible sample on disk | decide whether/which channel wants a blend; if so, add it to `config/production.yaml` and set `reference_short.voice` |
| 3. Craft gate (HyperFrames thresholds in our QA) | **NOT STARTED** | — | port `line_unread`/`dead_stretch`/transition-variety checks into `qa_check.py` |
| 4. Renderer trial (HyperFrames for Shorts) | **NOT STARTED**, go/no-go resolved by phase 0 | — | the full §4.2–§4.3 integration: Node+Chrome in the worker image, ≈25 registry components ported to portrait, GSAP/fonts vendored off-CDN, compose step in `reference_short.py` |
| 5. Per-channel look | **NOT STARTED** | — | — |
| — UTMOS naturalness scoring (VoiceStudio §5.2) | **NOT STARTED** — judged too heavy/risky to rush on this host | this log, §Phase 2b rationale | its own plan: source the checkpoint, install CPU-only `torch`, verify host memory headroom before running it anywhere near the live services |
| — Inline pause/emphasis tags (VoiceStudio §5.3) | **NOT STARTED** — needs a schema change, not an audio change | this log, §Phase 2b rationale | its own plan: new `Scene` field or bracket-tag parsing, updated word-count validators, yt-script prompt changes, writers'-room review |

## How to reproduce

```bash
# Phase 0 benchmark (throwaway, not part of any repo):
mkdir -p ~/hf-bench && cd ~/hf-bench && npm init -y
npm install hyperframes@0.8.192
export TMPDIR=~/hf-bench/tmp HYPERFRAMES_EXTRACT_CACHE_DIR=~/hf-bench/.hf-cache
npx hyperframes init testproj --resolution portrait --non-interactive
cd testproj && npx hyperframes check --json && npx hyperframes render --quality draft --output out.mp4

# Phase 1 tests:
cd Youtube_Video_Producer   # or this worktree
PYTHONPATH=src .venv-benchmark/bin/python -m pytest tests/test_shorts_audio.py -v

# Phase 2 A/B:
curl -L -o kokoro-v1.0.fp32.onnx \
  https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
# then synthesize the same text with both models via kokoro_onnx.Kokoro(model_path, voices_path)
```
