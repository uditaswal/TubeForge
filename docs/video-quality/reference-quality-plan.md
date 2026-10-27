# Reference-quality plan — closing the gap to the "Cloudflare/Pingora" Short

Written 27 Oct 2026 · branch `claude/av-quality-phase1` · all steps below **NOT STARTED** unless a status says otherwise.
Follow the steps **one at a time, in order**. Each step has one outcome, an acceptance test on a real
artifact (frames inspected / audio heard, per AGENTS.md) and what is out of scope. Do not start a step
until the previous one is accepted by the operator. Append evidence to `av-quality-implementation-log.md`.

## 1. The reference

- Video: "Why Cloudflare replaced nginx with Pingora (even though nginx won our race)", channel
  @AuroraAlgorithm. 127.6 s, 720×1280, 30 fps, −14.1 LUFS, peak −1.8 dBFS (our mastering target, so loudness is not the gap).
- Local copy (outside git, media): `/home/uditaswal/docker/tubeforge/reference-videos/cloudflare-pingora-aurora-algorithm.mp4`.
- Images kept for future reference (committed): `reference/cloudflare-pingora/contact-sheet-24-frames.jpg`
  (24 frames across the full video, one every ≈5.3 s) and `reference/cloudflare-pingora/phone-screenshot-flow-scene.jpg`
  (what a viewer sees on a phone, inside the Shorts UI).
- Judged from frames only. Voice and music were not assessed (see step 10 for an audio review).

## 2. What it does (the quality bar)

1. **Each scene is a purpose-built visual of the claim**, not a text card: node flow with a labelled link
   ("no handshake"), logo → logo transition, animated bar race (45.7k vs 19.4k, ×2.4), 16 workers' connections as
   dots on a time axis, two architecture panels ("own pools vs one pool"), a line chart (reuse 99.8 % → 31 %),
   quote card, recap, outro.
2. **Real evidence from its own experiment**: actual terminal output ("Active connections: 4051"), the real config
   line, machine spec (AWS c7g.4xlarge), exact test parameters. This is also what separates it from an AI template.
3. **Entity colour coding stays fixed for the whole video** (nginx green, Pingora/Cloudflare orange), in headlines,
   bars, panels and labels.
4. **Dim, then light up**: the whole diagram is on screen dimmed, each part lights as it is narrated.
5. **Long scenes, animation inside them**: ≈22 scenes in 127 s (≈5–6 s each); one scene spans 2–3 caption phrases
   while its data keeps animating.
6. **Anchoring and polish**: persistent two-tone headline, one phrase caption in a dark pill in the lower third,
   a small source/method footnote under it, content kept clear of the Shorts UI rails, recap scene before the outro.
7. Flat near-black background; no gradient, dots or progress rail. One accent colour per subject.

## 3. Where we are today (gap table)

| Reference capability | TubeForge now | Gap |
|---|---|---|
| Diagram with logos, labelled edges, dim→light, word-synced | `flow` = heading + 2–3 text nodes (`schema.py` `Flow`) | **Large** |
| Bar race with real numbers | `big_stat` (two figures + bars, count-up) | Small |
| Two-panel comparison | `before_after` | Small |
| Terminal evidence screen | `terminal` (synthetic prototype only) | Medium (needs real data) |
| Line chart, timeline dots, quote card, logo transition | none | **Large** |
| Highlighted source screenshot when citing | exists in the PIL path (`plates.py::source_card`, marker sweep) — **not in the HyperFrames path** | Medium; operator wants it back (§5) |
| Entity colour system, footnote, anchor headline | none | Medium |
| Real experiment/source-verified numbers | research is "context, not evidence" (AGENTS.md) | **Large** (content, not code) |
| Restrained sound | `sfx.py` places a cue on **every** scene entry at peak .30; operator: "too much" | Medium; operator wants it back (§5) |
| Length 127 s | 30–90 s cap | Decision |

State of the renderer at this writing (read, do not assume): Codex wired an opt-in HyperFrames path on this branch
(`901d77c`, tip `2ea2a7a`, `renderer: hyperframes`, default `pil`); all 7 templates exist as prototypes
(`terminal` synthetic). The steps below extend that path.

## 4. How the gap is overcome (root causes → fixes)

| Root cause | Fix | Steps |
|---|---|---|
| Our scenes are text cards; the reference draws the mechanism | A small **visual vocabulary** of data-driven primitives; the writer fills data, never layout | 4, 6, 7, 8 |
| No consistency system | Shared design tokens: entity colours, dim→light reveal, anchor headline, caption pill, footnote | 3 |
| Content is generic; reference shows its own evidence | Evidence primitives (highlighted source screenshot, real terminal/data) + a rule that every number carries a verified source | 2, 9 |
| Sound is the same cue everywhere | A sound **budget**: few, caused, quiet cues | 1 |
| Token spend does not change what viewers see | Renderer work is one-time engineering and costs no tokens; the script stays **one** Claude call returning typed scene data | 9 |

## 5. Operator requirements for the next video (27 Oct)

- **Screenshots with highlighted text come back** wherever the video references something directly (a blog post,
  docs page, paper, tweet). Quote the exact words; the highlight sweeps in as the claim is spoken.
- **Sound effects stay, in limited capacity.** The last audio with SFX overdid it. "Modesty is gold": fewer cues,
  quieter, only where something on screen causes them.

## 6. Steps (one by one)

Each step: one commit series, tests, one real render inspected, operator OK before the next. All NOT STARTED.

**Step 1 — Sound budget (quick win, audio only). VERIFIED; operator accepted and authorized Step 2.** Files: `rendering/shorts/sfx.py`, `audio.py`, `config/production.yaml`.
- Cues only for: a number landing (`big_stat`), a typed key/command reveal (`terminal`), the final payoff
  (riser/impact), and at most one whoosh per ~10 s for a hard topic change. Scene cuts are silent by default.
- Config: `sfx.max_per_minute` (default 4), `sfx.min_gap_s` (default 6), `sfx.peak` (default .18, was .30),
  never the same cue twice in a row; the existing `sfx_enabled` switch stays.
- Acceptance: re-master the reviewed fixture (job `e53f4e83…`); the cue log shows ≤ 4 cues/minute and ≥ 6 s apart;
  −14 LUFS / TP ≤ −1.5 still pass; **operator listens and says "modest"**. Tests for budget, spacing and no repeat.
- Out of scope: new sounds, music changes.
- Evidence (28 Oct): job `e53f4e8387424f65b6a6b50fbb166efa` re-mastered with its real narration,
  scene templates and aligned reveal words. Nine old cut cues became two caused cues
  (`pop` at 29.355 s, `riser` at 37.719 s); the 40.41 s budget permits two. Effects stem
  peak .180; muxed file −14.27 LUFS / −2.53 dBTP, clean FFmpeg decode. A dense 60 s
  SYNTHETIC 60 s worst-case narration tiling placed four cues, 12/24/36/57 s,
  rotating `pop`/`ping`; effects peak .180, −14.10 LUFS / −2.34 dBTP. `qa_check.py`
  passed with only a thumbnail warning for this listening copy. Full contact sheet inspected.
  Listen: `http://localhost:8082/review/railway-breach-modest-sfx.mp4`
  (`/home/uditaswal/docker/tubeforge/Youtube_Video_Producer/artifacts/review/railway-breach-modest-sfx.mp4`).
  The operator confirmed acceptance in the conversation and instructed work to proceed to Step 2.

**Step 2 — Evidence quote primitive (highlighted source screenshot). IMPLEMENTED; operator watch pending.** Port `plates.py::source_card` behaviour
(captured paragraph + marker highlight sweeping left→right) into the HyperFrames path as `evidence_quote`.
- Data: source screenshot path, highlight mask or text range, source label/URL footnote.
- Current renderer rule: a scene with `SourceVisual` and a captured plate uses `evidence_quote`;
  without a captured plate it falls back to that scene's normal template, never a fake screenshot.
- Acceptance: render a scene from a real captured source; frames show the highlight reaching the quoted words as they are spoken; footnote readable above the Shorts UI band.
- Out of scope: capturing new sources (the existing capture pipeline is reused).
- Evidence (28 Oct): real job `e53f4e8387424f65b6a6b50fbb166efa`, source scene 1,
  existing TechCrunch capture `reference/plates/source-1.png` plus `source-1-hl.png`
  ([source page](https://techcrunch.com/2026/10/22/developer-platform-railway-urges-all-users-to-revoke-secret-keys-after-cyberattack/)).
  HyperFrames check: zero errors in lint/runtime/layout/craft; two harmless nested-layer
  warnings. Draft render with the real aligned words and the job's mastered audio decoded
  cleanly. At scene-relative 0.9 s the marker is absent; it sweeps at the 1.081 s claim
  anchor and is full by 1.9 s, then repeats for 2.230 and 3.328 s reveal anchors.
  The 2 fps contact sheet was viewed. Source line uses the job's actual source name
  at x=90–900, y=1480–1530, clear of the right rail and bottom title band.
  Scene 5's capture had failed under the source page's CSP; a second draft render
  visibly used the ordinary `before_after` template. Review:
  `http://localhost:8082/review/evidence-quote-railway.mp4`;
  fallback: `http://localhost:8082/review/evidence-quote-fallback-railway.mp4`.
  Step 2 stays IMPLEMENTED until the operator watches the captured-source clip.

**Step 3 — Design tokens.** Shared across all HyperFrames scenes (`hyperframes_proto/compose.py` base):
entity → colour map (declared per video, e.g. `entities: {nginx: green, Pingora: orange}`), dim→light reveal helper,
persistent two-tone anchor headline, phrase caption pill in the lower third, small footnote line, safe region
clear of the Shorts UI (right rail, bottom title bar; verify against `phone-screenshot-flow-scene.jpg`).
- Acceptance: the existing 7 templates re-rendered with tokens; same entity keeps one colour across scenes; no element inside the UI rails on a phone-sized check.

**Step 4 — Node diagram primitive (`diagram`).** Replaces text-only `flow`: nodes with tile + logo/icon key + label,
edges with optional pill label, vertical or horizontal layout, whole diagram dimmed then lit node by node on the
word that names it.
- Acceptance target: recreate the reference's first two scenes (phone → Cloudflare proxy → server with "handshake" / "no handshake") from data only. Frames at the narrated words show the right node lit and the edge label present.

**Step 5 — Review checkpoint.** Operator watches one full render using steps 1–4 and chooses whether the look is
on track before more primitives are built. No code.

**Step 6 — Data charts: `bar_race` and `line_chart`.** Count-up bars with a "×N" badge; line with labelled endpoints.
Data props only (values, labels, units, source). Acceptance: reproduce the reference 45.7k vs 19.4k bars and the 99.8 % → 31 % line from data.

**Step 7 — `timeline_dots` and `two_panel`.** Dots on a time axis (events populate as narrated), and two bordered
panels with a mini-diagram each. Acceptance: reproduce the "nginx 1 vs 16 workers" and "own pools vs one pool" scenes from data.

**Step 8 — `evidence_screen` (real terminal/config/data) + `recap` + outro.** The evidence screen shows real captured text
(never invented output). Recap scene lists the takeaways; outro "full video linked below" only when a long video exists.
Acceptance: an evidence screen built from a real command's output, with the command and date in the footnote.

**Step 9 — Writer contract (one Claude call).** Update `docs/CONTENT_SKILLS_CONTRACT.md`, the yt-script/scene-plan skill and the
schema: the writer picks a primitive per scene from the vocabulary and fills typed data (`entities`, node/edge lists, numbers with a
`source`, quotes with a `source_screenshot`). Rules: prefer a diagram or chart for "how does X work" claims; use concrete named
entities, not generic nouns; **every number needs a verified source or is not shown**; "research is context, not evidence" still holds.
Acceptance: a new brief produces a valid scene plan using ≥ 4 different primitives with every number sourced; hook/craft gates updated, then one live job. Mind the two-attempt allowance; do not reset it.

**Step 10 — Full acceptance on a new topic.** Render one 60–90 s Short, run `qa_check.py`, check the §2 list
point by point against the contact sheet, and listen to the audio (voice, music, SFX modesty). Operator watches and decides whether it matches
or beats the old best video. Only then consider the PIL path for retirement.

**Step 11 (optional, content lane) — "own data" videos.** Where a topic can be tested locally (benchmark, config, timing),
capture the real output once and build the video around it; this is the reference's strongest edge and is what keeps a channel from reading as templated (see monetization memory/notes).

## 7. Decisions for the operator

1. Length cap: keep 30–90 s or allow up to 120 s for this diagram-heavy format (the reference is 127 s).
2. Is step 11 (own-data videos) wanted, and for which channel?
3. Entity colours: one per topic entity chosen by the writer, or a fixed brand palette per channel (phase 5 of the A/V plan)?

## 8. Notes

- Token cost: steps 1–8 are local engineering with no per-video token cost; only step 9's script call and step 10's job use tokens.
- Downloads/Docker/Node changes are flagged for the operator, not run by agents (standing instruction).
- Source reference for this analysis: the contact-sheet frames above; revisit them before changing a primitive's look.
