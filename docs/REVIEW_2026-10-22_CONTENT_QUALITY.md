# Content quality review — script, hook, engagement, audio, video (22 Oct 2026)

Author: Claude (Opus 5.5). Scope: why the reference Shorts are "acceptable but AI slop", and what to change.
Constraints honoured: all rendering/TTS/processing stays on the homeserver (4 cores, 3.7 GB RAM, no GPU);
the only paid AI is the existing Codex and Claude subscriptions; free APIs/assets are allowed where noted.
Companion to `docs/REVIEW_2026-10-21_END_TO_END.md` (architecture). Status labels per `AGENTS.md`.

## 1. TL;DR

The pipeline is now technically clean (sync, loudness, layout, QA). What reads as slop is **sameness and
lack of a point of view**, not bugs:

1. **The script has no opinion and no surprise.** It reports a stat, then explains it. The payoff (76 % → 24 %)
   is revealed in scene 3 of 7, so nothing holds the viewer for the second half, and the ending
   ("Safer new code pays off first. Follow for more Rust.") is a summary, not a punch.
2. **Our hook gate is being gamed.** All five hook candidates have the same skeleton — *"Your …, but what/why?"* —
   because the scorer rewards "you in the first six words + risk word + question word". The selected hook
   ("Your phone's security risk was 76% memory bugs, but what changed?") is grammatically odd and reads machine-made.
   A keyword scorer cannot judge a hook; it can only enforce a floor.
3. **The voice sounds like TTS because of how we use it.** Each scene is synthesised separately at speed 1.0,
   so intonation resets seven times, and the narration has **14 pauses of ~0.45 s (6.0 s of 34.2 s, 17 % dead air)**.
   That is ~139 wpm; good Shorts narration runs 165–190 wpm with almost no gaps.
4. **Music is a procedural synth pad** (`rendering/shorts/audio.py::synth_music`), the same one on every video.
5. **Visuals are text-on-navy slides with three copies of the same words** (headline, card text, burnt-in caption),
   empty placeholder boxes before each reveal, DejaVu Sans, and the lower ~40 % of the frame unused. Every video
   will look identical across topics and channels.
6. **Topic selection and feedback are manual.** No signal on what is trending or what retained viewers, although
   the analytics plumbing (`pipeline/performance.py`, `learning.py`) already exists.

The single highest-leverage change is a **multi-pass "writers' room"** (angle → draft → ruthless edit → judge)
using the Claude/Codex subscriptions we already pay for, plus **voice pacing fixes**, which are cheap and local.

## 2. Evidence (job `8c23e099f53640688fb8c26957ea4e57`, Sonnet 5.5, final 1080×1920)

Narration as rendered:

```
Your phone's security risk was 76% memory bugs, but what changed?
So Android's team moved new code to safer languages around 2019.
Memory bugs fell from 76% to 24% in six years.          <- payoff spent at 11 s
But old code matters less, because bugs mostly hide in new code.
Can AI turn old C into Rust? DARPA's TRACTOR program aims for that.
In one study, people wrote safe Rust, but automatic tools could not.
Safer new code pays off first. Follow for more Rust.     <- summary + generic CTA
```

- Hooks offered: 5/5 end in "but what/why?" or are "How did your…?" questions → formula fatigue.
- Silence in `reference/narration.wav` (silencedetect −35 dB, ≥0.25 s): 14 gaps, 0.31–0.48 s each.
- Kokoro call: `providers/voice/kokoro.py:54` hard-codes `speed=1.0`; voice `af_bella`; per-scene WAVs `voice-00..06`.
- Fonts: `rendering/shorts/layout.py:35` loads DejaVu Bold only (system has DejaVu + Fira Code).
- Frames: `final-sheet.png` / `review-sheet.png` next to the job — headline, card and caption repeat the narration;
  empty outline boxes are visible before reveals; the caption sits mid-frame, below it is empty space.

## 3. Script and hook

### What is wrong
- **No angle.** The brief was "why companies move to Rust"; the script lists findings in source order. Good Shorts
  pick *one* counterintuitive claim and defend it ("Rewriting old C is a waste of money — Google proved it").
- **Open loop closed too early.** The hook asks a question, scene 3 answers it, scenes 4–7 are trivia.
- **Hedge-shaped grounding.** "around 2019", "aims for that", "In one study" — faithful to sources, but every
  hedge costs energy. Grounding belongs in the on-screen source line and claim IDs, not in the voice.
- **Formula prompts produce formula output.** Our prompt literally prescribes the hook shape and the scorer
  rewards it, so every hook converges to the same template.
- **Generic CTA.** "Follow for more Rust" gives no reason to follow and no reason to comment.

### Actions (ordered)
| # | Action | Where | Effort | Acceptance |
|---|---|---|---|---|
| S1 | **Writers' room, 3 passes** in the runner: (a) *Angle pass* — from sources, return 3 candidate theses that are surprising, defensible and take a side, each with the single strongest proof and the "twist"; pick one. (b) *Draft pass* — current writer, but given the chosen thesis and a format recipe. (c) *Editor pass* — a separate call with the anti-slop checklist (S4) that rewrites for rhythm, cuts hedges/filler, enforces the payoff position, keeps claim IDs. Claude Sonnet medium for (a)/(b), same model for (c); Opus only when the operator picks it. | `host_claude_runner.py`, `providers/content/prompts.py` | M | Package records all three passes in evidence; ~1.5–2× current cost (~$0.6–0.8 list per script, covered by subscription) |
| S2 | **Hook tournament instead of keyword gate.** Writer returns 10 hooks across formulas; a judge call (Claude, no web) ranks them pairwise against a rubric: *stops scroll in 1.5 s, makes sense out of context, specific, true to sources, sounds like a person said it*. Keep `hookscore.py` only as a floor (≥45) and for clarity/length; drop the "you in the first six words" requirement from the prompt. | `youtube_skills.hook_gate`, prompts | S–M | Hooks no longer share one skeleton (check: ≤2 of 10 end with a question); operator picks winner in review when not auto |
| S3 | **Format recipes** (pick one per video, recorded in the package): *Myth → truth*, *"Stop doing X"*, *3 mistakes*, *X vs Y verdict*, *"Nobody tells you…"*, *Before/after with a number*, *Story of one person/company in 30 s*, *Ranking*. Each recipe fixes where the payoff lands (≥70 % of runtime) and how the last line loops to the first. | new resource under `yt-script` (wheel hash → Codex redeploy) or a Claude-runner-only prompt block | S | Two consecutive jobs on different recipes look structurally different on the contact sheet |
| S4 | **Anti-slop list** enforced by validator + editor pass: ban "game-changer", "here's the thing", "let's dive", "the truth is", "pays off", "but what changed?", "in today's world", triplets of adjectives, rhetorical question in more than 2 scenes, sentences starting with "So" twice, "Follow for more X". Validator rejects banned phrases → repair loop. | `youtube_skills.py` validator | S | Unit test with a slop sample; live job passes without banned phrases |
| S5 | **Payoff-late + loop ending rule:** the biggest number/twist must be in the last 35 % of runtime; the final line must set up rewatch (echo hook words or answer it with a twist). | prompt + validator (position of the highest `big_stat`/reveal) | S | Validator test; live job reveal ≥ 0.65 × duration |
| S6 | **Swipe file (operator-curated, real, free).** `data/swipe/hooks.jsonl` with 30–100 hooks from Shorts that actually did well in our niches (link + views as seen by the operator). Inject 8 random examples per run as *style* examples, never as facts. | new file + prompt | S (operator time ~1 h) | Prompt carries examples; rejected if any example text is copied verbatim |
| S7 | **Read-aloud check.** Editor pass must keep sentences ≤ 12 words *and* vary length (one 3–5-word punch line per 2 scenes). | editor prompt + validator (std-dev of sentence length) | S | Validator test |

## 4. Engagement ("comment bait") — what is allowed and works

Done today: `metadata.engagement_comment` (pinned debate question, reviewed with the script).

| # | Action | Notes |
|---|---|---|
| E1 | **Take a side in the video.** The thesis from S1 must be arguable ("Rewriting C is wasted money"). A stance is what people argue with; a neutral summary gets no comments. | biggest driver of comments |
| E2 | **Spoken + on-screen comment prompt replaces "Follow for more".** Final line asks a binary choice tied to the stance ("Rust or C for your next project? Tell me I'm wrong."). Keep follow as on-screen chip only. | change CTA rule in prompts and `cta` template |
| E3 | **Pinned comment** = the strongest counter-argument to our own thesis, not a repeat of the CTA. Invites "well actually" replies. | tweak the prompt added today |
| E4 | **Reply engine (later, needs scope):** fetch top comments 1 h/24 h after publish, Claude drafts 3–5 replies (yt-comment skill), operator approves in Studio, post via `commentThreads`/`comments.insert` (`youtube.force-ssl` scope). Early replies boost comment velocity. | free API quota; needs UI (Codex branch) |
| E5 | **Deliberate "error bait" is out.** Planting false facts to get corrections violates our grounding rules and YouTube's misleading-content policy; also avoid "like if…/sub4sub" style incentives (spam policy). Controversy must come from *opinion*, never from false claims or insults. | guardrail stays in validator |

## 5. Voice and audio

| # | Action | Where | Effort | Acceptance |
|---|---|---|---|---|
| A1 | **Synthesize the whole narration in one Kokoro call** (or 2–3 chunks at sentence boundaries), then split per scene from forced alignment — keeps natural intonation across scenes. | `rendering/shorts/prepare.py`, `providers/voice/kokoro.py` | M | Whisper alignment still ≥ 6/7 scenes; listening test |
| A2 | **Speed 1.12–1.18** (configurable per channel); target 165–185 wpm. | `kokoro.py:54` → config | S | Measured wpm in QA report |
| A3 | **Trim gaps:** inter-scene tail 0.35 s → 0.12–0.18 s; compress intra-scene pauses > 0.25 s to 0.15 s. Keep one deliberate 0.4 s beat before the payoff only. | `timeline.py`, `prepare.py` | S | silencedetect: ≤ 3 gaps ≥ 0.25 s in 30 s |
| A4 | **Voice choice + chain:** A/B `af_heart` (Kokoro's top-rated voice), `am_fenrir`/`am_puck` vs `af_bella`; optional style-vector blend (Kokoro supports mixing voices) for a unique channel voice. Add a light chain in FFmpeg: high-pass 80 Hz, gentle compression, +2–3 dB presence at 3–5 kHz, de-ess. | config + `audio.py` | S | Operator picks by ear from a 3-voice sample sheet |
| A5 | **Real music library** instead of `synth_music`: 20–40 tracks tagged by mood/BPM from licences that allow YouTube + Instagram monetised use (Pixabay Music licence, YouTube Audio Library for YouTube-only, CC0/CC-BY with attribution via the existing `music_catalog` attribution path). Beat-detect locally (librosa, CPU) and snap scene cuts to beats. | `pipeline/music.py`, `audio.py` | M (+ operator curation) | Each track has stored licence evidence; cuts within 60 ms of a beat |
| A6 | **SFX pack (CC0):** whoosh on transitions, pop on reveals, bass hit on the payoff stat, riser into the hook's first word, keyboard clicks on terminal scenes. Kenney.nl and Freesound CC0 sounds are free. | `audio.py` effects bus (exists) | S | ≤ −18 dB under voice; listening test |
| A7 | **Your own voice (optional, free):** a human VO is the strongest anti-slop signal. Keep Kokoro for drafts; allow an operator-recorded WAV to replace narration before final (alignment already handles it). | upload step (UI → Codex branch) | M | — |

Not recommended on this box: XTTS/F5/Chatterbox-class voice cloning — they need a GPU or >4 GB RAM and run far
slower than realtime on 4 cores.

## 6. Video

| # | Action | Where | Effort | Acceptance |
|---|---|---|---|---|
| V1 | **One copy of the words.** Captions carry narration; scene graphics carry *different* information (number, object, comparison, image). Ban headline text that repeats > 50 % of the scene's narration words. | layout validator + prompt | S | Validator test; contact sheet shows no duplicate text |
| V2 | **Remove empty placeholder boxes** before reveals; animate elements *in* from nothing (pop/slide). | `motion.py`, templates | S | No outline-only cards in stills |
| V3 | **Fonts:** bundle 2–3 OFL fonts (e.g. Inter or Manrope for body, Anton/Bebas Neue/Archivo Black for numbers and hooks, JetBrains Mono for code), per-channel choice. Free from Google Fonts. | `layout.py::font`, assets | S | Fonts' OFL text stored in repo |
| V4 | **Active-word captions:** current word in accent colour + 8–10 % scale pop; place captions in the lower-middle safe band (y≈1150–1350) so the top 60 % is free for the visual. | `layout.py`, `motion.py` | S–M | Stills show highlighted word; safe-zone tests pass |
| V5 | **Real imagery, still local and free:** (a) **headless Chromium screenshots/recordings** (Playwright is already installed) of real pages — GitHub repos, docs, release notes, charts — with scroll/zoom; (b) Wikimedia Commons (rights path exists); (c) free Pexels/Pixabay API key for stock B-roll (operator decision; free, no subscription); (d) matplotlib-rendered real-data charts. Every scene gets a `media` slot. | `providers/media/`, new `image_focus` / `screen` templates | M–L | ≥ 50 % of scenes show a non-text visual |
| V6 | **AI-authored SVG illustrations:** the brain (Claude/Codex) writes small SVGs in a fixed style guide (flat, 2–3 colours, thick strokes); render with `resvg`/`cairosvg` on CPU. Validate size/complexity and render-check. | new template + prompt | M | Illustrations render < 1 s each; operator eye test |
| V7 | **Visual QA by Claude (vision):** after the preview, send the 12-frame contact sheet to Claude with a rubric (readability, redundancy, empty space, "looks like a slide?"); findings become repair hints or review notes. Same subscription, ~1 call/video. | runner op `ReviewFramesV1` | M | Findings stored with the preview; operator sees them in review |
| V8 | **Pattern interrupts:** a visible change every 1.5–2.5 s — punch-in zoom on numbers, quick shake on the payoff, colour flash on the twist, split-screen for "vs". | `motion.py` | S–M | `distinct_frame_events` per second ≥ 0.5 in QA |
| V9 | **Theme packs per channel:** palette, fonts, caption style, music mood, SFX set, background motif (JSON). Stops every channel looking like the same navy template. | config + renderer | M | Two channels render visibly different from the same script |

Not feasible on this machine for now: Stable Diffusion / video diffusion (no GPU, 3.7 GB RAM; even SD-Turbo via
OpenVINO would swap). Revisit when there is income for a GPU box or a paid image API.

## 7. Topic selection and learning loop (free)

| # | Action | Notes |
|---|---|---|
| T1 | **Topic radar:** daily job pulls candidates from free sources — YouTube Data API search (top Shorts in niche, last 7 days, by views; free quota), Hacker News/Reddit top posts, GitHub trending, release notes RSS. Claude ranks them for "surprising + arguable + sourced". Operator approves the shortlist. | uses existing research step; no paid API |
| T2 | **Close the loop:** `performance.py`/`learning.py` already collect analytics. Store per video: recipe, hook formula, voice, music, first-3-s visual, length → compare *viewed vs swiped away*, average percentage viewed, comments per 1k views. Feed the top/bottom 5 summaries into the angle and hook passes as "what worked for this channel". | numbers, never fabricated; ≥ 10 videos before trusting trends |
| T3 | **A/B by publishing variants:** two hooks for the same body on different days/channels; keep the winner's formula. | after publishing is live |

## 8. Skills to add or change

`yt-script` stays the only narration skill (contract). Edits to it change wheel hashes → Codex host redeploy (sudo).

- `yt-script/recipes.md` — the format recipes (S3) with payoff position and loop rules.
- `yt-script/anti-slop.md` — banned phrases and rhythm rules (S4, S7); the validator reads the same list.
- `yt-script/angles.md` — how to find a defensible, surprising thesis from sources (S1a, E1).
- `yt-comment` — extend for pinned-comment counter-argument (E3) and reply drafting (E4).
- New `visual-director` (non-narration) — maps each beat to the best visual type (image, screen capture, chart,
  SVG, stat) and writes SVG briefs (V5/V6).
- New `frame-critic` — rubric for Claude's contact-sheet review (V7).

## 9. Suggested order (each step = one acceptance video inspected by the operator)

1. **Quick wins, 1 session:** A2, A3, S4, S5, E2, V1, V2, V3. Re-render the same Rust brief; compare with
   job `8c23e099…` side by side.
2. **Writers' room:** S1, S2, S3, E1, E3 (+ skills files). Two briefs on different recipes.
3. **Sound:** A1, A4, A5, A6 (operator curates ~20 tracks + picks a voice).
4. **Visual depth:** V4, V5 (screen capture first, then Wikimedia/stock), V8, V7.
5. **Channel identity + loop:** V9, T1, T2; later E4 and T3 once publishing is live.

Rough cost per video after step 2: 3–4 Claude calls (angle, draft, edit, hook judge) + 1 vision call ≈ $0.8–1.2 at
list price, all inside the subscription; render time unchanged except A1 (+ a few seconds).

## 10. Decisions for the operator

- Free Pexels/Pixabay API key for B-roll: yes/no (free, but an external account).
- Which voice(s) per channel after the A4 sample sheet; whether you want to record your own VO sometimes.
- Music licence policy: Pixabay-licence + CC0 only, or also CC-BY with attribution in descriptions.
- How hard the stance can be (E1): "opinionated but fair" default, or per-channel tone settings.
- Budget per script (number of passes / Opus vs Sonnet) when quotas are tight.
