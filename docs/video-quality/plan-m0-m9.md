# Video-quality milestones (learned from 3 reference videos + a process guide)

Written 24 Oct 2026 by Claude. Goal: raise the quality and *distinctiveness* of TubeForge videos so they are worth watching and clearly not "generic / template-based / mass-produced" (YouTube YPP, see memory `monetization-goal-and-policy`).
Sources studied (downloaded privately for analysis only; nothing reused or republished):

| Ref | What it is | Facts measured |
|---|---|---|
| **A** YouTube Short "Does try/catch make your code slow?" (Aurora Algorithm) | Original benchmark explainer | 78 s, 205 words, 2.6 words/s, −14.1 LUFS, ~20 scenes, 466 subs / 237 views on day 1 |
| **B** Instagram Reel "emudhra security issue" (rickaiengineer) | Story-led security explainer | 77 s, 217 words, 2.8 words/s, −14.1 LUFS, 20 numbered scenes |
| **C** Instagram Reel "Claude + 20 repos = motion studio" (MSB Intel) | Presenter + screenshot list with comment-gated giveaway | 44 s, 137 words, 3.1 words/s, −14.1 LUFS, 1,480 likes / 2,101 comments |
| **D** PDF "Lyric Video Process Guide" (Claude Code × Remotion) | A *process* for art-directed video; lyric-specific tools are irrelevant | 6 gated stages, frozen inputs, hero proof before scale |

Caveat: A and B are tiny channels with no proven results, and A/B look template-generated themselves. We copy *craft and process*, not their content, characters or footage. Cadence figures are from 2–3.2 s frame sampling.

## 1. What they do better (the learning)

**Content (A, B, C)**
1. **Original or specific evidence.** A ran a real 10-million-loop benchmark and shows method + numbers (+0.0 %, +4.2 %, 1,400 ns vs 69 ns). B tells one named case with hard figures (key "4", key "56", under one second). Ours summarise an advisory.
2. **A full arc in 75–80 s.** B: absurd specific hook → prerequisite concept → mechanism → numbers → stakes → response → caveat → echo of the hook. A: myth → evidence → verdict → rule of thumb. We ship ~36 s / ~86 words.
3. **Honesty cues.** "No confirmed evidence of abuse", "HYPOTHETICAL SCENARIO", "middle of 9 runs". Builds trust and keeps content out of the manipulative bucket.
4. **Curation with real artifacts (C).** A numbered list of tools, each with its real logo / repo page screenshot, recap card at the end ("A full motion studio"), and a resource-giveaway CTA that produced 2,101 comments.
5. **Full description (A):** numbers, source, tags. Ours is two lines.

**Craft (A, B, C)**
6. **Series identity.** Mascot, case numbers ("CASE / 004"), section tags ("THE HOOK", "THE STAKES"), progress footer ("01 / 20"). A distinct story per episode inside one brand — the pattern YouTube's policy allows.
7. **Visuals carry the explanation.** Bars animate with the spoken number, code panels highlight the changed lines, real logos (Chrome, Firefox, company) appear, key words in the 2–4-word caption get highlighted, big numerals fill the frame.
8. **Cadence.** A new visual state every ~2–4 s (C: ~2 s) versus our ~4.5 s scenes with fewer reveals.
9. **Human presence (C)** raises authenticity but is not available to us (no own voice/face, decision of 22 Oct). A recurring *character* is the substitute (see M3).

**Process (D)** — the most transferable part
10. **Gated stages with frozen, checksummed approvals.** Inputs → timing → sync test → creative direction → hero proof → sections. Later stages read frozen files and never change them.
11. **Review pictures, not code.** Every stage ends in something watchable (sync-test video, contact sheets, 5-second proof). The agent inspects its own frames and fixes defects before showing them.
12. **Prove quality on a small piece first** (5-second hero proof set the bar before a 70-second section).
13. **Meaning drives the visual.** A separate *creative-direction* stage turns each line into a visual metaphor, groups lines into sequences, designs an intensity curve with contrast (including real silences) and then **self-reviews to reject generic/repeated ideas** before any code.
14. **A design system, not effects:** 3 "worlds" (palette/material), one signature continuity device (the red line), fonts chosen from a test sheet that includes the hardest words, per-material motion physics, a 2.5D camera, **motivated transitions** (an object from scene A becomes scene B), beat-map used *selectively*, deterministic seeded randomness, platform safe zones.
15. **Written weaknesses list** (`implementation-notes.md`) and a time/cost table per stage.

## 1b. Operator retention rules (24 Oct 2026) — how they map to what exists

Four rules from the operator. The performance claims attached to them (e.g. "retention over 100 % triggers rapid distribution") are **hypotheses to test with real channel data (M9), not facts we may rely on**; the craft rules themselves are sound and cheap to enforce.

| # | Rule | Where we are today (measured on job `0072a2f4…`, 30.6 s, 7 scenes) | Gap | Milestone |
|---|---|---|---|---|
| R1 | **2-second visual hook**: bold visual / B-roll / large high-contrast captions from frame 0; never open with a greeting | Scene 1 headline is on screen at t=0, 96 px Anton captions, stock B-roll when the writer picks it, hook narration starts at 0.00 s, hook gate rejects weak openers. But scene 1 shows **no large visual event between 0 s and 4.4 s** (frame-difference > 0.006 on the top two thirds; chips and captions excluded), and nothing *forces* scene 1 to carry B-roll, a source shot, a logo or a big number. | enforce a visual in scene 1; first change inside 2 s; ban greeting openers | M1b |
| R2 | **Seamless loop**: last sentence connects back into the first | Was: spoken follow CTA last, no loop. **Now implemented (24 Oct):** `loop` template, open-ended last sentence, last frame = first frame, craft + QA checks, no follow request. Scene tails are 0.18 s, so audio loops without a gap. | listening review of a real job; first-vs-last frame similarity metric (M0) | M1b (done in part) |
| R3 | **Pacing**: no pauses in the voice; a visual cut every 1.5–2.5 s | Voice: scene tail 0.18 s, in-scene pause cap 0.15 s, Kokoro 1.15×, narration gaps already small (the Codex review lists pause compression as part of the content contract). Visuals: scenes last 3.8–5.3 s (mean 4.4 s) with reveal/motion events about every 1.5–2.9 s (largest gap 4.4 s in the hook). The `Timeline` validator **requires** a 0.12–0.4 s speech tail, so "zero pauses" would change a validator, not only a setting. | measure it (M0); a "tight" voice profile evaluated by listening; cadence budget as a QA check | M0, M5 (Codex), M4 |
| R4 | **No low-effort templates**: custom scripts, dynamic editing, original storytelling, curated audio | Fixed template set, one voice, scheduled automation; originality levers exist (stance, source screenshots, writers' room) but nothing *measures* repetition. Music: only no-Content-ID tracks (decision 22 Oct). | similarity gate vs recent videos, template rotation limit, original-evidence formats | M0, M1, M2, M3, M6, M1b |

**Decision for R2 (operator, 24 Oct): no follow request; the video just loops.** The final scene is the new `loop` template: one open-ended spoken sentence with no final full stop that hands back into scene 1's first words, and it repeats scene 1's headline, chips, icon and logo so the last frame equals the first (progress bar also resets). No follow, subscribe or like request appears in narration, headline, chips, `metadata.call_to_action` or the two-line description. The comment prompt now lives only in the pinned debate comment (`metadata.engagement_comment`). Saved jobs that end in the old `cta` template still validate and render. Implemented in `dev` (see HANDOFF); R2's remaining gap is listening/looping review of a real job.

## 2. Where we stand today (so milestones are not redundant)

Already have: forced-alignment timing (Whisper, with logged estimate fallback), contact sheets + layout QA, frame-first review habit, `qa_check.py`, writers' room (angle + editor pass), real-imagery plates (stock, source screenshots, code cards), logos, icons, motion layer, series-neutral templates, safe-zone layout, deterministic render identities, publishing package + thumbnails.
Missing relative to the references: story-arc profile > 45 s, original-data content, a concept/screenplay stage, series identity, motivated transitions/camera, selective beat reactivity, hero-proof gate, quantified quality bar.

## 3. Milestones

Order is by value ÷ effort and dependency. Each has one user-visible outcome, an acceptance test, required evidence, and what is out of scope. Status uses the AGENTS.md labels; all start **NOT STARTED**. "Owner" is a suggestion so Claude (`dev`) and Codex (separate branch) do not collide.

### M0 — Quality bar from references (S · Claude)
*Outcome:* a repeatable measurement of any video against the reference range.
*Metrics to include (from the operator rules):* leading silence, max silence gap, visual-change interval (mean/p90/max, captions excluded), time to first large visual change, first-vs-last frame similarity, scene count per minute.
*Work:* `.agents/skills/om-video-quality/ref_probe.py` (words, words/s, scene/reveal cadence from frame differences, LUFS, caption words per chunk, loudness range) + `docs/reference/benchmarks.json` holding A/B/C numbers above; extend `qa_check.py` to print "ours vs reference" (WARN, not FAIL).
*Acceptance:* run on jobs `0072a2f4…` and A/B/C; table is correct against the numbers in §0; unit test on a synthetic clip.
*Evidence:* printed table in `AUTONOMOUS_PROGRESS.md`.
*Out of scope:* judging creativity automatically.

### M1 — 60–90 s "explainer" profile with a story arc (M · Claude)
*Outcome:* a job type producing 60–90 s Shorts/Reels with the arc in §1.2, 12–20 scenes, 150–200 words, hook that names a specific absurd fact, closing line echoing the hook, mandatory caveat line when evidence is partial.
*Work:* new profile `reference-explainer-v1` beside `reference-short-v1` (schema scene count, duration 55–90 s, Timeline/Encode limits currently hard-coded 25–45 s in `timeline.py`, `schema.py`, `prompts.py`), recipe `arc` in the writers' room, craft checks (echo-hook, caveat present, no two consecutive same template, ≥1 numeric reveal per 3 scenes), UI preset, qa_check window.
*Acceptance:* tests for limits and checks; one real job inspected against M0 table; 3 viewers/operator watch it.
*Out of scope:* >90 s, landscape.

### M1b — Retention rules gate: hook, loop, pacing, variety (S–M · Claude, shares with Codex)
*Outcome:* the four operator rules become checks that fail or warn before a video is accepted, so they stay true as we change templates and voices.
*Work:*
1. **R1** — craft check: scene 1 must have a visual (stock, source shot, logo badge or big number), opener must not be a greeting/channel intro ("hello", "welcome back", "in this video"); QA: first large visual change ≤ 2.0 s, voice starts ≤ 0.25 s; hook scene gets a reveal inside 2 s in the layout.
2. **R2** — craft check for the closing line (echo or bridge into scene 1 words) once the CTA decision is made; QA compares the last and first frames (same background/headline) and the audio tail (≤ 0.2 s).
3. **R3** — add to `qa_check.py`: max silence gap (≤ 0.25 s), mean/p90/max interval between visual change events (target p90 ≤ 2.5 s; the 1.5 s lower bound is a design target, not a gate), cuts/min; layout work to add micro-reveals so no beat exceeds 2.5 s (coordinate with M4).
4. **R4** — similarity gate: compare the new script's title, hook, template sequence and visual kinds with the channel's last 20 videos (stored locally); WARN above a threshold, FAIL on near-identical template sequence + hook formula; limit repeating the same template more than N times per video.
*Acceptance:* unit tests with injected defects (greeting opener, no scene-1 visual, static 4 s hook, spoken CTA last, duplicate sequence); two real jobs inspected with contact sheet + the new numbers; listener notes for pacing changes. Measurements are reported separately from operator approval.
*Evidence:* before/after table on job `0072a2f4…` (hook static until 4.4 s today).
*Out of scope:* changing the voice profile (M5), new motion primitives (M4), claiming any effect on views.

### M2 — Concept (screenplay) stage before scenes (M · Claude)
*Outcome:* the writer first produces `visual-screenplay.json`: per scene a *visual concept* (how the claim physically appears), shared motifs, an intensity curve, and a self-review that deletes repeated/generic ideas; scenes are then written to that screenplay (the PDF's most important lesson: "the meaning drives the visual").
*Work:* extend the angle pass in `host_claude_runner.py` (Claude only; Codex later) with a `concept` call (one extra allowance, salt `concept`), schema + validator (each scene has `concept`, `motif`, `intensity` 1–5; ≥3 distinct motifs; peak not before 60 %; one deliberate quiet beat), stored as an immutable artifact with checksum, shown in script review.
*Acceptance:* validator tests; on two topics the concept sheets differ in motifs and templates; operator can approve/reject concept before scenes (UI field).
*Evidence:* concept JSON + resulting contact sheets for two jobs.
*Out of scope:* new render primitives (that is M4).

### M3 — Series identity and design system (M · shared)
*Outcome:* every video is recognisably the same series yet shows a distinct story: episode number tag, section tag per scene ("THE HOOK", "THE STAKES"), progress footer "n / N", a recurring mascot (done 24 Oct: one static original sprite "Chip", see HANDOFF; no animation by operator decision), chosen palette "worlds" (e.g. Paper/Night/Alert) and a signature continuity device (a line that becomes underline, arrow, crack).
*Work:* `rendering/shorts/brand.py` + config `pipeline.series` (name, episode counter, mascot asset, palette), layout changes, font test sheet script (hard words, numerals), safe-zone compliance, tests; episode counter kept in DB so numbers never repeat.
*Acceptance:* two consecutive jobs show different episode numbers and different section tags; layout QA passes; font sheet reviewed.
*Out of scope:* licensed characters, real people, copying any reference's mascot.

### M4 — Motion engine: motivated transitions, camera, physics, selective beats (L · Codex)
*Outcome:* video feels continuously designed rather than slides: an object from scene N becomes scene N+1, a 2.5D camera pushes/pulls, materials move differently (paper vs ink vs metal), beat/kick used only for impact moments, scene intensity follows the M2 curve.
*Work:* `rendering/shorts/camera.py`, transition library driven by the screenplay's `motif`, easing/spring families, seeded randomness, beat map from librosa/ffmpeg (secondary to word timing), reveal-synced bars/code highlights. Fits the Codex branch (video generation). Contract: renderer reads `visual-screenplay.json` and `render_options.json`; geometry stays in the library.
*Acceptance:* deterministic output (two renders byte-identical for same seed); hero proof first (see M7); frame review of every transition.
*Out of scope:* 3D engines.

### M5 — Timing and audio gates (M · Codex, audio branch)
*Outcome:* the sync-test habit from D: a plain "karaoke" verification render of the narration with the active word and debug text, a confidence report that flags estimated-alignment scenes, frozen timing checksums before design stages, whole-narration synthesis, per-reveal sound effects, ducked music (no strike risk).
*Acceptance:* sync-test video generated for any job; zero scenes silently on estimated alignment; loudness gate unchanged; operator listens.
*Evidence:* sync-test.mp4 + report.

### M6 — Original evidence formats (L · Claude)
*Outcome:* the strongest anti-"generic" lever. Three formats:
1. **Experiment** — the writer proposes a small benchmark; a sandboxed runner (no network, CPU/time limits, pinned Node/Python images) executes it; real numbers become animated bars and code panels with methodology text.
2. **Curated list** (ref C) — "N tools/repos for X": real logo + README/page screenshot per item (existing plates + logo library), recap card.
3. **Case story** (ref B) — named incident arc with a hypothetical label when speculating.
*Work:* `pipeline/experiments.py` + sandbox, new scene templates (`bars_live`, `code_highlight`, `tool_card`, `recap`), source handling, UI format picker, safety review of code execution before enabling.
*Acceptance:* sandbox tests (timeouts, no network, output size cap); an experiment video whose numbers can be reproduced from stored artifacts; list video with real logos.
*Out of scope:* running arbitrary user code outside the sandbox; unverifiable claims.

### M7 — Hero-proof and approval gates in the pipeline (M · Claude)
*Outcome:* the D process inside our product: (1) concept approved → (2) 6–8 s *hero proof* of the most important scene rendered and shown → (3) full render. Approved inputs are frozen with checksums and later stages cannot alter them (we mostly have the identities; add the explicit gate and UI step). `implementation-notes.md` equivalent: per-job "known weaknesses" appended by qa_check.
*Acceptance:* API/UI test of the new gate; refusing to render full video before proof approval when enabled; orchestrator test.
*Note:* per AGENTS.md, UI contract applies (real API action, truthful states).

### M8 — Description, CTA and funnel (S · Claude)
*Outcome:* long description with data, method, sources, tags (ref A); optional **comment-keyword CTA** ("Comment X for the list") with a stored deliverable and a manual fulfilment checklist (ref C); pinned debate comment already exists. Instagram caption variant.
*Acceptance:* publishing page shows both; qa_check validates the description; no automated DMs (Instagram publisher not started; avoid spam behaviour and platform rule breaches).
*Out of scope:* automated messaging.

### M9 — Feedback loop (L · later)
Retention and view data per hook/format feed back into recipe choice (`pipeline/learning.py` exists); needs real published data, so only after the first videos are live.

## 4. Suggested sequence and split with Codex

1. **Now (Claude):** M0 → M1b → M1 → M2. These change content and need no render-engine work.
2. **In parallel (Codex branch):** M5 (timing/audio gates) and the engine work for M4. Agree the two contracts first: `visual-screenplay.json` schema (from M2) and `render_options.json`.
3. **Then:** M3 (shared) → M6 experiment sandbox → M7 gate → M8. M9 after publishing starts.

Definition of done for each milestone: relevant tests + a real job inspected through contact sheet and `qa_check.py` + a short entry in `AUTONOMOUS_PROGRESS.md` + `docs/HANDOFF.md` status row.

## 5. Decisions needed from the operator
- Approve extending Shorts beyond 45 s to 60–90 s (M1). Reels allow it; YouTube Shorts allow up to 3 minutes.
- Mascot/character: we draw an original vector character (recommended) or go characterless.
- Is a sandbox that executes generated benchmark code on the host acceptable (M6)? Recommend Docker with no network and resource limits.
- Comment-keyword giveaway (M8): yes/no, and what the deliverable is.
