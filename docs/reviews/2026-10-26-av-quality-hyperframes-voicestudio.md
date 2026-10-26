# Reference review 2: what to take for audio and video quality (HyperFrames first)

Date: 26 October 2026. Reviewer: Claude. Scope: the six local checkouts in
`/home/uditaswal/docker/tubeforge/git-repos`, compared with TubeForge `dev` at `dff6733`.
This is a documentation-only review: no TubeForge code or configuration was changed.
The operator states licences are in place for reuse; this review does not re-examine licensing.

Companion to [2026-10-23-reference-codebases.md](2026-10-23-reference-codebases.md) (Codex's
review of five repos, which skipped HyperFrames) and [video-quality/milestones.md](../video-quality/milestones.md)
(the Codex M1–M4 work merged on 25 Oct).

> **Status (26 Oct, same day):** this review stays as the point-in-time document it was
> written as — it is not edited after the fact. All three §8 decisions below were approved by
> the operator the same day, and phases 0, 1 and 2b were implemented against that approval on
> `claude/av-quality-phase1`. The live, updated state of every phase (including two VoiceStudio
> items found and deliberately deferred, not in this review) is
> [video-quality/av-quality-implementation-log.md](../video-quality/av-quality-implementation-log.md).

## 1. Summary

**Why the Codex branch produced no visible or audible change.** Codex's milestones measured
defects (M1), fixed spoken forms and phrase grouping (M2), and re-ranked stock clips (M3).
Those changes are real but invisible: the code that decides what every frame looks like and
what the music is did not change. Codex explicitly scoped out "importing a second renderer"
(M3) and never looked at HyperFrames. The four things that dominate how a Short looks and
sounds are all still the same:

1. **One frame template for every scene.** Every scene is drawn by the PIL compositor in
   `rendering/shorts/layout.py` and `motion.py`: navy gradient, floating dots, a progress rail,
   an icon in a circle, a header, a card, a two-word caption. Ten scenes, one look.
2. **One motion for everything.** Every element enters with the same scale-from-0.78
   back-overshoot (`motion.py:32`, `:125`). Every scene enters with the same 60 px fade-slide-up
   (`motion.py:140–146`). There is a constant 2 % creeping push-in (`motion.py:162`). HyperFrames'
   motion guide lists each of these by name as a "default that looks generated".
3. **Synthesised music.** `rendering/shorts/audio.py:19` (`synth_music`) plays the same
   four-chord sine pad, bass and plucks at 96 BPM under every video. The music catalog in
   `config/production.yaml:57` is empty. HyperFrames' `sound.md` §3 says plainly "do not
   spend the run … writing music in code: nobody can hear whether it is good."
4. **One sound effect.** The only effect is filtered noise at every scene start
   (`audio.py:66`). HyperFrames calls "the same whoosh on every cut" "the most common tell".

There is also no metric that would show an improvement: `final.qa.json` checks decode,
loudness, peak and layout bounds, and the sample video below passes all of them.

**The recommendation in one line:** adopt HyperFrames' craft rules now (cheap). Replace the
synthesised music and noise accents with a real music bed and a small SFX library (cheap,
large audible gain). Trial HyperFrames as the frame renderer for Shorts behind a flag (the
one change that can make the videos look different). Add numeric gates for each of these so
the next improvement is measurable.

| # | Change | Source | Effort | Expected impact | Section |
|---|---|---|---|---|---|
| 1 | Real music bed (curated CC0/licensed tracks, or local MusicGen) instead of `synth_music` | HyperFrames `sound.md`, `media-use/audio/references/bgm.md`; OpenMontage `sound-design.md` | S | **High (audio)** | §4.5 |
| 2 | SFX by cause (whoosh on cuts, pop on stat, tick on typing, one riser) with 2–3 rotated takes, from HyperFrames' 21 bundled files | `media-use/audio/assets/sfx/` + `manifest.json` | S | **High (audio)** | §4.5 |
| 3 | HyperFrames HTML/GSAP renderer for Shorts frames (our scene plan + word timings in, MP4 out) | HyperFrames engine/CLI; OpenMontage `tools/video/hyperframes_compose.py` as blueprint | L | **Very high (video)** | §4.2 |
| 4 | Craft rules in the scene planner and a craft audit gate (hold time per word, dead stretch, banned defaults, transition variety) | HyperFrames `motion.md`, `story.md`, `review.md`, `cli/src/utils/craftAudit.ts` | S–M | High (video, works with or without #3) | §4.1, §4.6 |
| 5 | Kokoro full-precision weights instead of `kokoro-v1.0.int8.onnx` | `config/production.yaml:74` | XS | Medium (voice timbre), to be A/B tested | §5.1 |
| 6 | Measurable audio: UTMOS naturalness + Whisper WER on every narration | VoiceStudio `omnivoice/eval/mos/utmos.py`, `docs/evaluation.md` | S | Enables measurement | §5.2 |
| 7 | Per-span pace/emphasis/pause markup from the script AI to Kokoro (`[pause 300ms]`, `[slow]…`) | VoiceStudio `ssml_lite.py`, `expressive-speech.md` | M | Medium (delivery) | §5.3 |
| 8 | Animated overlays on real source screenshots (highlight box, callout, cursor) instead of quote cards | OpenMontage `remotion-composer` `ScreenshotScene`; HyperFrames `yt-feather-highlight`, `marker-highlight`, `cursor-annotate` | M (free with #3) | Medium | §6.2 |

Effort: XS < ½ day, S ≈ 1–2 days, M ≈ 3–5 days, L ≈ 2–3 weeks (agent time, including tests and a
real render).

## 2. Evidence boundary

- **Static source review plus inspection of one real TubeForge render.** No reference
  application was installed or executed. A HyperFrames render benchmark on this host was
  attempted and blocked by the session's permission policy (npm install of external code). Its
  render speed and memory use on this 4-core, 3.8 GB host are therefore **unmeasured**. §7
  makes that benchmark the first gated step.
- Proposed work below is **NOT STARTED**. Impact ratings are review judgements, not
  measurements.
- Graphify (installed for this review, see Appendix A) built code-only knowledge graphs of
  all six repos (local tree-sitter, no LLM). They were used to locate code; every claim below
  was confirmed by reading the cited file.

| Repository | Local HEAD | Graph (nodes / edges) |
|---|---|---|
| hyperframes | `24965372dbbe` (24 Oct) | not finished (stopped at 70 % of 7 087 files to free the host; findings come from direct reads) |
| VoiceStudio | `8772ec7eb956` (23 Oct) | 40 620 / 91 863 |
| OpenMontage | `e45f5b12bd46` | 27 186 / 40 234 |
| youtube-agent-skill | `a2feb2104981` | 131 / 177 |
| youtube-automation-agent | `e26792ae00dc` | 1 309 / 3 597 |
| youtube-autopilot | `69d8f0cf2872` | 2 177 / 4 248 |

## 3. Baseline: what a current Short looks and sounds like

Job `e53f4e8387424f65b6a6b50fbb166efa` (Railway breach): 1080×1920, 40.4 s, 10 scenes
(`flow` ×3, `checklist` ×2, `before_after` ×2, `hook`, `big_stat`, `loop`), 120 spoken words.
`final.qa.json` passed. Contact sheet (one frame per 2 s) and a full-resolution frame at 5 s
were inspected.

Findings, written in HyperFrames' review format (`skills/hyperframes/references/review.md` §3):

| P | Where | Problem | Rule it breaks |
|---|---|---|---|
| P0 | whole film | 20 of 21 sampled frames share one composition: icon-in-circle, header, card, caption on navy | `story.md` §8 "a dark void with small things floating in it"; `types/explainer.md` tells "icons in circles" |
| P0 | t≈4–8 s | 45-word article excerpt on screen ≈4 s; reading needs 0.5 + 0.3 × 45 ≈ 14 s | `motion.md` Holds; `craftAudit.ts` `line_unread` |
| P0 | audio, whole film | identical synthesised pad and progression in every video; one noise accent on every cut | `sound.md` §3–4 |
| P1 | every scene change | same fade-slide-up; no transition has a cause on screen | `motion.md` "Transitions with a cause": use 3–5 kinds |
| P1 | every reveal | element pops in with back-overshoot on UI cards | `motion.md` "bounce on UI" |
| P1 | t≈5 s | highlighter sweep stops mid-word ("to ac\|cess") | precision of highlight to word boxes |
| P1 | most scenes | caption repeats words already on the card; the narrator reads the screen | `story.md` §6 "the screen never repeats the spoken sentence word for word" |
| P1 | 1100–1300 px and below caption | large empty bands; content sits in a small central card | `types/vertical.md` layout: one subject, centred, type larger than landscape |
| P2 | background | floating dots and a slow drifting glow standing in for motion | `motion.md` "breathing, floating or pulsing loops" |

Correction to my own first look: on the 270-px contact sheet the card text looked tiny; at full
resolution it is ≈36 px, above HyperFrames' 30-px read floor. Text size is not the problem;
quantity of text and hold time are.

## 4. HyperFrames (focus)

### 4.0 What it is

HyperFrames (HeyGen, Apache-2.0) renders an HTML/CSS/GSAP composition to MP4 deterministically:
headless Chrome seeks a paused timeline frame by frame (`HeadlessExperimental.beginFrame`),
captures each frame and encodes with FFmpeg (`packages/engine/README.md`). It ships a CLI
(`packages/cli`, Node ≥ 22), ≈450 registry items (`registry/`: 210 blocks, 239 components),
7 skills whose reference files hold measured craft rules (`skills/hyperframes/references/*.md`),
and a media skill with a mixing graph, 21 bundled SFX and local music/TTS fallbacks
(`skills/media-use/`). Its contract (no `Date.now()`, no unseeded random, no network, every
visible thing a function of timeline time; `skills/hyperframes/SKILL.md` "Contract") matches
TubeForge's determinism requirement.

Three separable things can be taken from it, in increasing cost:

1. **Rules** (text): usable today by our script/scene planner prompts and our QA. §4.1.
2. **Sound assets and mixing practice**: usable inside our existing Python mixer. §4.5.
3. **The renderer and registry**: replaces the PIL frame compositor for Shorts. §4.2–4.4.

### 4.1 Craft rules to adopt (no renderer change needed)

These are numbers, which makes them enforceable in our scene planner and checkable in QA.
Sources are in `skills/hyperframes/references/`.

| Area | Rule (quoted or condensed) | File | Where it lands in TubeForge |
|---|---|---|---|
| Hold time | A line meant to be read holds 0.5 s + 0.3 s/word; the last line ≥ 2 s; a 1–2 word chapter line may hold 0.4 s | `motion.md` Holds | scene planner budget; QA gate (§4.6) |
| Words per scene | TTS ≈ 2.2 words/s; ≈ 19 spoken words per scene, at most two scenes at 26 | `film.md` "Script and pacing" | `prompts.reference_word_budget` |
| Reveal timing | Reveal each part when the voice names it, across the back half of the scene; everything on screen in the first quarter, then frozen, reads as a slideshow | `film.md`, `types/explainer.md` | `timeline.py` reveal schedule |
| Vertical pacing | Shots of 1–2 s, a new beat every 2–4 s; frame 0 is the hook and thumbnail, never black/logo | `types/vertical.md` | already partly in rulebook; add to QA |
| Platform UI band | On 1080×1920: nothing in the top 168 px; words and subject inside 168–1330 px; no text under the right action rail | `types/vertical.md` | compare with our `SAFE = (60, 200, 930, 1500)`: our bottom edge 1500 > 1330, so captions near 1300–1470 risk the caption/handle area (verify on a phone, see HANDOFF open decision) |
| Eases by role | Arrival `expo.out`/`power4.out` with a long tail; camera/colour `power2.inOut`; exit `power3.in`; exits 40–50 % shorter than entrances | `motion.md` | replace `ease_out_back` everywhere |
| Stagger/overlap | Words 60–120 ms apart, list items 40–80 ms; next element starts when the previous is 30–50 % done | `motion.md` | checklist/flow reveals |
| Title entrances | Vary within a film: per-word blur-in (6 px→0, 0.13 s, 67 ms apart, no translate); grey→ink per word; whole-line blur 8→0; slot-machine word roll | `motion.md` Titles | a small rotation of entrance styles keyed by scene index |
| Landed text | A landed title is dead still; motion moves to the next element, the camera or the world | `motion.md` | remove creeping push on text layers |
| Transitions | 3–5 kinds per film, each caused by something on screen (zoom-through, object-becomes-world, morph, whip, colour flood, iris, dip cut, blur swap); ≤ 1/3 hard cuts between beats; worlds never crossfade | `motion.md` table | transition chooser in the scene plan |
| Worlds | A film visits several worlds (background, light, scale), not one dark canvas with small UI floating; enter each through an object already on screen | `story.md` §5 | per-scene backgrounds (stock, source screenshot full-bleed, solid colour field) |
| Explainer shapes | Pick the shape first: number that lands, myth struck through, before/after, converging groups, steps, real screenshot with detail circled, quote as poster, chapter card | `types/explainer.md` | maps onto our templates; add "screenshot circled" and "myth struck" |
| Copy | ≤ 6 words a line on screen (explainer ≤ 10); the screen never repeats the narration word for word; banned words list | `story.md` §6 | yt-script/scene prompt rules |
| Captions | 2–3 words per group for high energy; break on ≥ 150 ms pause; one group visible; start 0.1–0.3 s after 0; hard kill after exit; portrait ≈ 600–700 px from bottom | `captions.md` | `layout.py:138 caption_groups` already does 2–3 words; add pause breaks |
| Gradients | Full-screen linear gradients on dark grounds band under H.264; use radial or solid + local glow; accents < 15 % opacity disappear | `look.md` Video facts | `motion.py:38 ambient_background` (check for banding) |
| Look | Settle the look as numbers before the first scene; Inter / Space Grotesk / JetBrains Mono are "where generated design lands" | `look.md` | channel LOOK spec per channel |

**How much to take:** all of this table. It is text and thresholds; it costs prompt and QA
changes only, and it is the basis for judging any renderer.

### 4.2 The renderer: replace the PIL compositor for Shorts

**Why this is the main lever.** Our frame code is ≈1 400 lines of PIL (`rendering/shorts/`
layout, motion, plates, icons). Every new look needs Python drawing code; blur, masks, text
fitting, per-word animation, motion blur, shaders and 3D are impractical. HyperFrames gives all
of them through HTML/CSS/GSAP plus a library of ready, deterministic pieces. That is why its
outputs look produced and ours look templated. Codex's M3 kept the PIL renderer by design, so
no amount of ranking could change the look.

**Integration shape** (proven by OpenMontage, which already drives HyperFrames from Python:
`OpenMontage/tools/video/hyperframes_compose.py`, 1 436 lines: workspace materialisation,
`hyperframes lint`, `check`, `render --strict` as subprocesses with timeouts):

```
yt-script (unchanged) → scene plan (existing schema) → Kokoro + Whisper alignment (unchanged)
   → NEW: compose step writes a HyperFrames workspace
        index.html (root, 1080×1920, 30 fps) + compositions/scene-N.html
        word timings → caption component data; scene plan → registry blocks/components
        assets/: stock clips, source screenshots, logos, fonts, GSAP (all vendored, no network)
   → npx hyperframes check --json   (craft + layout gate, §4.6)
   → npx hyperframes render --quality draft|high --output preview.mp4|final.mp4 (no audio)
   → existing Python mastering muxes our mix.wav (keep our loudness/true-peak gate)
```

Keep in TubeForge: script authority, scene contracts, alignment, mastering, QA, leases,
checkpoints, atomic promotion. Replace only the frame renderer and the motion layer. Keep the
PIL path as the fallback renderer behind a config flag until the HyperFrames path is
**VERIFIED**.

**Constraints and risks found in source:**

| Risk | Evidence | Mitigation |
|---|---|---|
| Host capacity unknown | Chrome per render; this host has 4 cores, 3.8 GB RAM, ≈0.7 GB free and 1.8 GB in swap at review time | Benchmark first (§7 phase 0). OpenMontage estimates 30 s + 0.5 s per output second (`hyperframes_compose.py:445`). Our budget is RTF 20 (`budget_realtime_factor`). Use `--workers 1`, draft quality for previews |
| Network at render time | Registry items load GSAP and Google Fonts from CDNs (e.g. `registry/components/caption-kinetic-slam/caption-kinetic-slam.html:7–10`) | Vendor GSAP and font files into `assets/`; the contract forbids network fetches (`SKILL.md` rule 4, rule 9) |
| Most blocks are landscape | Registry tally: 202 blocks are 1920×1080, only 13 are 1080×1920 (`ai-chat-reveal`, `claude-exchange`, `chatgpt-exchange`, `flowchart-vertical`, `notification-cascade`, `message-thread-reveal`, `notes-reveal`, …); the 238 components have no fixed size | Use components (size-agnostic) as building blocks; port the few landscape blocks we want (code, charts) to portrait once |
| Toolchain | CLI needs Node ≥ 22; host has Node 24; worker image is `python:3.12-slim` with distro `chromium` | Add Node + `chrome-headless-shell` to the worker image, pinned; or a separate renderer container |
| Determinism | Contract bans clock and unseeded random; `hyperframes check` reports violations | Keep `check --json` errors as a hard gate |
| Version drift | Repo is very active (0.8.192 local vs 0.8.199 on npm at review time) | Pin one version; vendor registry items as source in our repo (they install as editable source) |
| Telemetry | `media-use/references/telemetry-dashboard.md` exists | Confirm and disable before production use |

**How much to take:** the engine/CLI as a pinned dependency, the composition contract, and a
curated subset of ≈20–30 registry components (§4.3). Do not take the Studio, desktop app,
HeyGen cloud, Lambda/Cloud Run, avatar or HeyGen TTS paths.

### 4.3 Registry pieces that map onto our scene templates

Item names are directories under `registry/blocks/` or `registry/components/`.

| Our template / need | Replace with (registry) | Notes |
|---|---|---|
| `hook` | `headline-slam`, `kinetic-center-build`, `type-match-cut`, `glass-shard-title`; behind real imagery: `cinematic-zoom`, `rack-focus` | Frame 0 must already show the hook (`types/vertical.md`) |
| `big_stat` | `count-up`, `number-pop-in`, `number-wheel`, `apple-money-count`, `mk-progress-stat` | Count-up 1.2–1.6 s, then hold (`film.md`) |
| `before_after` | `before-after-wipe`, `comparison-split`, `strikethrough-replace`, `split-tilt-cards` | "Myth turned over" shape |
| `flow` | `flowchart-vertical` (portrait block), `svg-line-draw-loader`, `tracing-beam`, `stagger-cascade` | One diagram that grows, a part per beat |
| `checklist` | `marker-checklist-card`, `success-check`, `stagger-lattice` | Avoid "three cards in a row" |
| `terminal` / code cards | `terminal-simulator`, `code-terminal-run`, `typed-prompt`; blocks `code-typing`, `code-diff`, `code-highlight`, `code-scroll` | Code blocks are 1920×1080 and reserve no caption band (`film.md` "From a pull request"); port to portrait |
| source/article cards | `yt-feather-highlight`, `marker-highlight`, `inline-highlight`, `cursor-annotate`, `ui-focus-zoom`, `browser-device-stage`, blocks `x-post`, `reddit-post`, `news-ticker`, `yt-comment-card` | Show the real screenshot full-bleed and circle or highlight the detail, rather than a quote card |
| `cta` / `loop` | `cta-close`, `logo-brand-close`, `match-cut`, `text-match-cut` | Loop ending: last frame matches first |
| Captions | `caption-highlight`, `caption-pill-karaoke`, `caption-kinetic-slam`, `caption-editorial-emphasis`, `caption-weight-shift` | All consume `[{text,start,end}]`, the shape our alignment already produces |
| Transitions | `whip-pan-cut`, `zoom-through-transition`, `match-cut`, `iris-reveal`, `directional-wipe`, `focus-blur-resolve`, `shutter-slam`; `@hyperframes/shader-transitions` | Rotate 3–5 kinds per film |
| Camera | `push-in`, `parallax-zoom`, `pull-back-reveal`, `camera-shake` (sparingly), `yt-camera-move` | Punch-ins on emphasis words |
| Texture | `grain-overlay`, `vignette`, `light-sweep-pass` | Replaces floating dots; keep subtle |
| Data | `animated-bar-chart`, `chart-story`, `decline-chart`, `mk-line-graph` | Only with source numbers |

**How much to take:** start with ≈ 25 items: 5 caption styles, 6 transitions, the stat, compare,
flow, checklist, terminal and highlight components, 3 camera moves, grain/vignette. That
covers every current template with 2–3 visual variants each, which removes the
"one template" P0 by itself.

### 4.4 Visual identity per channel (`look.md`, `frame-presets/`)

HyperFrames forces the look to be written as numbers (hex, font, weight, px) in a LOOK line
and bans the generated defaults. TubeForge has one dark navy look for every channel.
Take: a per-channel `frame.md` (palette, display and body face, accent rationing, banned list),
CSS variables on the root composition so a channel re-brands by changing variables. The 13
presets in `skills/hyperframes/assets/frame-presets/` are slide looks, not a default for films
(`look.md`), so use them only as starting points.

### 4.5 Sound: the cheapest large improvement

| Take | Source | How much |
|---|---|---|
| Replace `synth_music` with a real instrumental bed: start at the track's strongest bar, not a quiet intro; loop 15–30 s library loops with 0.4 s fade-in / 1.5 s fade-out; pick by feel and tempo, not topic | `sound.md` §3; `film.md` "On music"; `media-use/audio/references/bgm.md` | All. Fill `music_catalog` (already built: `pipeline/music.py`, with checksums and licence records) with 15–30 CC0/licensed instrumental loops grouped by mood and BPM |
| Optional local generation fallback: MusicGen-small seed clip ≤ 30 s, crossfade-looped to length | `bgm.md` "Local generation"; prompt table by topic (tech default "uplifting corporate tech, bright modern piano with synth pads, 108 BPM") | Trial only; CPU generation is slow and quality must be heard |
| 21 bundled SFX with placement notes: `whoosh`, `whoosh-short`, `whoosh-cinematic`, `pop`, `click`, `click-soft`, `key-press`, `typing`, `riser`, `impact-bass-1/2`, `glitch-1..3`, `ping`, `chime`, `notification`, `sparkle`, `error` | `skills/media-use/audio/assets/sfx/manifest.json`, `CREDITS.md` | All 21, with credits. Place by cause: whoosh on a cut or a fast card move; pop on a stat/chip landing; soft key tick on typed text; one riser into the payoff |
| Placement and levels: peak lands one frame after its picture; each hit 3–6 dB over the bed; rotate 2–3 takes of a repeated sound; music under voice ≈ 0.14 volume; true peak ≤ −1 dBTP; mix −16 to −14 LUFS | `sound.md` §4–5 | All. Our ducking (`audio.py:63`, up to −12 dB) and mastering (−14 LUFS, −2.5 dBTP) stay |
| Carve the bed in the voice band (dip only the frequencies the voice uses) instead of only ducking the whole bed | `media-use/references/mixing.md` "Music under a voice"; `audio/scripts/carve.mjs` | Port the idea to FFmpeg (sidechain-free static EQ dip at 2–4 kHz on the bed, OpenMontage `sound-design.md` "EQ trick") |
| Bed energy check: a bed whose energy is mostly under 150 Hz plays as nothing on a phone speaker | `sound.md` §4 | Add as an audio QA warning |

Our current `synth_music` is mostly sine pad and bass; on a phone speaker it is close to
inaudible apart from the plucks. A real bed plus 4–8 caused effects per Short is the single
cheapest audible change.

### 4.6 Review loop and measurable craft gates

HyperFrames' `check` computes craft warnings from the seeked timeline
(`packages/cli/src/utils/craftAudit.ts`): `line_unread` (hold < 75 % of 0.5 s + 0.3 s/word),
`dead_stretch` (> 3 s with nothing changing), `text_below_floor` (< 2.6 % of the short side),
`first_frame_empty`, `film_silent`. `snapshot --review` writes three sheets (scene start/middle,
every cut ±0.2 s, beat frames at 360 px phone width) and `review.md` gives a P0/P1/P2 note format.

Take (even before any renderer change): port these warnings into our layout QA, which already
records every text mark's bounds and the timeline (`final.qa.json` → `layout.scenes[].marks`).
Add a cut sheet (±0.2 s) and a 360-px phone sheet to the delivery QA helper
(`.agents/skills/om-video-quality/qa_check.py`). Add two variety metrics: distinct transition kinds
per film (target 3–5) and distinct scene compositions (no composition twice in a row).

## 5. VoiceStudio: what Codex took and what it missed

Codex adopted pronunciation dictionaries, number/abbreviation spoken forms, timestamped audio
defect scans, phrase grouping, and gentle voice processing (M1, M2). Those remain right.
Not covered:

### 5.1 The model file (XS, try first)

`config/production.yaml:74` loads `kokoro-v1.0.int8.onnx`. The int8 quantisation is the
smallest Kokoro build; it trades timbre (graininess, sibilance) for size and speed. On this CPU,
our measured voice stage has headroom (RTF budget 20). Action: render the same reviewed script
with the fp32 (or fp16) Kokoro v1.0 ONNX weights and the same voice. Compare by ear at matched
loudness and with UTMOS (§5.2). Keep whichever wins; record the model hash in the voice cache key
(already done: `providers/voice/kokoro.py:37`).

### 5.2 A naturalness number (S)

VoiceStudio evaluates TTS with UTMOS22-Strong (automatic MOS, 1–5) and ASR word error rate
(`docs/evaluation.md`; `omnivoice/eval/mos/utmos.py`). We already run Whisper for alignment, so
WER against the reviewed spoken text is nearly free. UTMOS is one small model on CPU. Record both
per narration in the audio provenance and show them in the Studio diagnostics. This turns
"is the voice better?" into a tracked number, which the Codex milestones lacked.
Limits: UTMOS is trained on read speech; use it for A/B on the same script, not as an absolute
quality bar.

### 5.3 Delivery control the script AI can write (M)

- `backend/services/ssml_lite.py`: inline `[slow]…[/slow]` (≈0.85×), `[fast]…[/fast]` (≈1.15×),
  `[emphasis]…[/emphasis]` (≈0.92× + flag), `[spell]…[/spell]`, nesting with innermost wins,
  unclosed tag runs to line end. Kokoro takes `speed` per call, so each span can be synthesised
  at its own speed and concatenated within our phrase groups.
- `docs/expressive-speech.md`: `[pause 500ms]` markers rendered as real stitched silence work on
  every engine; punctuation (ellipses, dashes, short fragments) genuinely shapes Kokoro's pacing.
  Unknown tags are spoken literally, so tags must be parsed out before synthesis.
- Take: let yt-script emit a small, validated tag set (`pause`, `slow`, `fast`, `emphasis`) on the
  spoken form only. Captions keep the display text (fits the M2 display↔spoken mapping).
  Acceptance: an A/B listen on the same script; WER must not rise.

### 5.4 A channel voice (S–M, needs a listen)

VoiceStudio's competitive analysis cites Kokoro-FastAPI's weighted voice mixing (blend voice
style vectors by ratio; `docs/competitive-analysis.md:199, :917`). Kokoro voices are style
vectors in `voices-v1.0.bin`, so a fixed blend (e.g. 70 % `af_bella` + 30 % `af_sarah`) gives a
channel a voice that is not a stock preset heard on thousands of other Shorts. Cheap to try;
only the operator's ear can accept it.

### 5.5 Other engines (decision needed, not recommended now)

VoiceStudio ships CPU-capable engines: PocketTTS (Kyutai, 100 M params, CPU-only, zero-shot
cloning, ≈8–9× real time on an M3 Pro; weights CC-BY-4.0 but gated on Hugging Face;
`docs/engines/pockettts.md`) and Supertonic-3 (≈99 M params, ONNX CPU, 7 preset voices,
OpenRAIL-M; `backend/engines/supertonic3/`). Its default OmniVoice and the expressive engines
(IndexTTS2, CosyVoice 3) need a GPU for practical speed. The operator decision of 22 Oct is
"Kokoro TTS only". A blind A/B of Kokoro fp32 against PocketTTS on one script is the only
evidence that should reopen it.

Not useful for us: dubbing fit planners, prosody mirror (needs a source actor), diarisation,
dictation, the Electron app.

## 6. OpenMontage and the YouTube repos: what Codex overlooked

### 6.1 OpenMontage already integrated HyperFrames

`skills/meta/animation-runtime-selector.md` routes kinetic typography, motion graphics and
registry blocks to HyperFrames and keeps Remotion for its existing React scenes. Its Python
wrapper `tools/video/hyperframes_compose.py` is the closest blueprint for our compose step:
doctor/version probe, workspace scaffold, `lint`, `check`, `render --strict`, timeouts, and
a test suite (`tests/tools/test_hyperframes_compose.py`, `tests/qa/test_09_hyperframes_compose.py`).
Codex reviewed OpenMontage's clip search and face tracking but not its render path.

### 6.2 Other OpenMontage pieces worth taking

| Take | Source | Notes |
|---|---|---|
| Animated overlays on a real screenshot: cursor, click pulse, typing, highlight box, callout balloon, normalised coordinates | `remotion-composer/SCENE_TYPES.md` `screenshot_scene`; `src/components/ScreenshotScene.tsx` | Same idea as HyperFrames `cursor-annotate`/`ui-focus-zoom`; do it in HyperFrames, not Remotion (one browser renderer, not two) |
| Sound-design reference card: music bed 18–20 dB below dialogue; whoosh starts 10–20 ms before the visual; voice EQ HPF 80 Hz, cut 500 Hz, boost 2–5 kHz, cut 6–8 kHz; 3:1 compression | `skills/creative/sound-design.md` | Check our `gentle-v1` voice chain against it |
| `voice_clarity` FFmpeg preset: `highpass=80, eq 200 Hz −3 dB, eq 3 kHz +3 dB, eq 5 kHz +2 dB, acompressor 2.5:1` | `tools/audio/audio_enhance.py:66` | A ready candidate profile for an A/B against `gentle-v1` |
| Grade presets via FFmpeg LUT/filter chains | `tools/enhancement/color_grade.py` | For stock B-roll consistency; HyperFrames `media-treatment` does the same inside compositions |
| Pixabay music scraper | `tools/audio/pixabay_music.py` | **Do not adopt**: scraping, documented as fragile; use downloaded, recorded tracks in `music_catalog` instead |

### 6.3 youtube-agent-skill, youtube-automation-agent, youtube-autopilot

Graph reports confirm these are script, packaging, analytics and scheduling projects. Their
video paths are either paid AI video APIs (automation-agent `utils/video-providers.js`:
Seedance, Kling, MiniMax, Wan) or prompt writing for Sora (autopilot `agents/cinematographer.py`).
Nothing in them improves our local render or audio beyond what Codex already recorded.
One rule worth keeping from `youtube-agent-skill/skills/yt-shorts/SKILL.md`: on-screen text for
the first two seconds uses **different words** from the spoken line. That matches HyperFrames
`story.md` §6 and fixes the caption-repeats-card P1.

## 7. Plan: phases, acceptance and measurement

One phase at a time; each ends with a real render inspected frame by frame and listened to in
full, per AGENTS.md. Metrics are recorded before and after on the **same reviewed script**
(job `e53f4e83…` is a good fixture).

| Phase | Outcome | Acceptance and evidence | Out of scope |
|---|---|---|---|
| 0. Measure | Baseline numbers for the current renderer: UTMOS, WER, craft warnings (`line_unread`, `dead_stretch`), transition kinds, composition repeats; HyperFrames benchmark on this host (one 30 s 1080×1920 test composition, `--workers 1`, draft and high quality: wall time, peak RSS) | Metrics script output committed as evidence; benchmark wall time ≤ RTF budget or a clear "does not fit" | Any visual change |
| 1. Sound | Real music bed from `music_catalog` + caused SFX from the bundled library; synth path kept as fallback | Same script rendered before/after; music audible on a phone speaker; −14 LUFS / −2.5 dBTP still pass; SFX each with an on-screen cause, ≥ 2 takes rotated; operator listen | Renderer, voice model |
| 2. Voice | Kokoro fp32/fp16 A/B; optional voice blend; `[pause]`/`[slow]`/`[emphasis]` tags | UTMOS not lower, WER not higher, operator prefers by blind listen | New TTS engine |
| 3. Craft gate | HyperFrames thresholds ported to our layout QA; cut and phone sheets in `qa_check.py`; planner rules from §4.1 | Gate flags the baseline's P0s (45-word card); new script passes | Renderer swap |
| 4. Renderer trial | HyperFrames compose step for Shorts behind `rendering.shorts.renderer: hyperframes`; ≈25 vendored registry items; captions from word timings; our mastering muxed | `hyperframes check --json` has zero errors; craft gate passes; preview and final render within budget; frames show ≥ 3 transition kinds and no repeated composition; operator full watch prefers it over PIL | Removing the PIL renderer |
| 5. Look per channel | `frame.md` per channel, CSS variables, banned-defaults list | Two channels render visibly different looks on the same script | Thumbnails |

Highest-risk acceptance test: phase 0's benchmark. If HyperFrames cannot render a 60 s Short
within budget on this host, the fallback is to port the §4.1 rules and §4.5 sound into the PIL
path (phases 1–3 still apply). The visual gain will then be much smaller.

## 8. Decisions for the operator

1. **Music source:** curated CC0/licensed loops in `music_catalog` (recommended), local MusicGen,
   or both. Licences are in place per the operator; each track still needs its record.
2. **Approve the HyperFrames renderer trial** (phase 4) and adding Node + headless Chrome to the
   worker image (or a separate renderer container). The phase 0 benchmark needs permission to
   install the pinned `hyperframes` npm package in a throwaway directory.
3. **Voice:** allow an fp32 Kokoro A/B (no policy change). Separately, decide whether a
   PocketTTS A/B may reopen "Kokoro only".

## Appendix A: Graphify

- Installed from source `Graphify-Labs/graphify@92741d162b20` (0.9.95) into
  `~/.local/share/graphify/venv`, binary linked at `~/.local/bin/graphify`, skill at
  `~/.claude/skills/graphify/` (SKILL.md + references). `graphify install` was **not** run, so
  `~/.claude/CLAUDE.md` was not modified.
- Security review before install: no `setup.py`/install hooks; no `eval`/`exec`/`base64`/
  `pickle`/`marshal`; network only via an SSRF-guarded `security.safe_fetch` (explicit URL
  ingestion), optional LLM providers when API keys are set, and CDN `<script>` tags inside
  generated HTML; query logging is opt-in (`querylog.py`); subprocess use is `git ls-files`,
  the Claude CLI (semantic pass, only when invoked) and detached rebuilds from optional git
  hooks. Watch item: the skill's bootstrap runs `pip install graphifyy --break-system-packages`
  when it cannot import graphify; the venv install above avoids that path.
- Graphs were built code-only (`GRAPHIFY_OUT=<scratch> graphify update .`, no LLM, nothing
  written into the reference repos).
- The HyperFrames graph (7 087 source files) was stopped at 70 % after ~15 min because it held
  all four host cores alongside the TubeForge worker. Rebuild off-hours with
  `cd ../git-repos/hyperframes && GRAPHIFY_OUT=<dir> nice graphify update .`.
