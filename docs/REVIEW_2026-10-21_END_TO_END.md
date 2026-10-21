# TubeForge end-to-end review — 21 October 2026

Reviewer: Claude (Opus 5.5), review only — no code was changed.
Scope: the whole repo on branch `dev` (last commit `c25fae8`, 13 Oct) **plus** the large
uncommitted working tree, the generated videos under `data/artifacts/` and
`artifacts/benchmark/`, and the project records.

---

## 1. TL;DR

1. **The good renderer isn't wired into the product.** The dashboard/worker still
   renders through the legacy path (`rendering/preview.py` + `providers/media/local_graphics.py`).
   The better-looking renderers are only used by a standalone benchmark script
   (`examples/docker-short-benchmark/produce.py`) and by a new library
   (`rendering/shorts/`) that no pipeline code calls yet. The plan's own status says
   "Phase 3 — wire dashboard to the same renderer: NOT STARTED".
2. **Even the best output is "text in boxes on dark navy".** No images, icons,
   B-roll, illustrations or real motion. Captions and terminals are legible, but
   the videos look like slides. For Shorts this reads as low effort, whatever the
   technical gates say.
3. **Scripts are over-hedged.** The latest dashboard job (Rust + AI) opens with
   "AI helps. Easy? Not proven.", runs 77 s at 854×480 (landscape), and scored its
   own hook 41/100 (WEAK). The safety and grounding rules are stopping the writer
   from writing punchy lines.
4. **The AI isn't acting as a director yet.** Codex returns text fields; a fixed
   renderer decides everything visual. You described the right design ("AI is the
   brain, local Python + TTS do the work"), but the contract between the two is too
   thin on the visual side and too heavy on the governance side.
5. **The process burns tokens.** Agents are told to read and update a 476 KB
   progress log and a 190 KB design doc (about 170k tokens together). About 5,000
   lines of changes plus ~40 new files have sat uncommitted on `dev` since 13 Oct.
   There is no Claude content provider and no `CLAUDE.md`, so switching to Claude
   mid-stream has no clean handoff.
6. **Hardware is tight:** 4 CPU cores, 3.7 GB RAM, Intel HD 5500, no GPU. Local
   image or video diffusion isn't feasible. The visual quality has to come from
   better *programmatic* graphics, free stock or Wikimedia media, and AI-authored
   vector graphics, not from generative pixels.

**Recommendation:** freeze new features. Stabilise the repo, then do one
focused phase: "one renderer, wired into the dashboard, with a richer visual
vocabulary". Then upgrade the brain contract and add a Claude provider. Publishing
and Instagram come after one video passes your own eye test. See §7 for phases
and §8 for the Codex ⇄ Claude relay protocol.

---

## 2. Current state snapshot

| Area | What exists | Status (AGENTS.md labels) | Notes |
|---|---|---|---|
| Job pipeline / worker | SQLite + Alembic, leases, fencing, checkpoints, cancellation, atomic promotion; ~30 job states | **VERIFIED** (strong) | The best part of the codebase. Keep it. |
| Dashboard (Creator Studio) | FastAPI `api/app.py` (143 KB single file), auth, approvals, scene editor, activity | IMPLEMENTED | Works end to end for the Docker topic; a very large single module. |
| Script brain | Codex CLI via a root-owned host runner + socket, JSON schema output, research step, `yt-script` skill embedded | IMPLEMENTED | Codex only. `repair_attempt_limit: 0`, ≤60k-char prompts. No Claude provider. |
| Research | `ResearchSourcesV1`: web search → local fetch → hashed source packets | IMPLEMENTED | Good grounding. Prompts reach ~55–57k chars, so they are expensive. |
| TTS | Piper (dashboard default), Kokoro INT8 (benchmark), HTTP TTS server | IMPLEMENTED | The dashboard Rust job used **Piper**; the benchmark used **Kokoro** (noticeably better). |
| Alignment / captions | Estimated timing + optional Whisper forced alignment; ASS captions | IMPLEMENTED | 1–3-word, 84 px captions in the newer paths. |
| Renderers | **Four** paths: `rendering/preview.py` (+ `local_graphics.py`), `rendering/animated_*.py`, `rendering/shorts/` (reference library), `examples/.../produce.py` | Fragmented | Only `preview.py` is called by the orchestrator. |
| Music / mastering | Synth music bed, ducking, two-pass loudnorm | IMPLEMENTED | The dashboard Rust preview measured −17.5 LUFS / 0.0 dBFS peak (fails). The fixture finals pass (−14.4 LUFS). |
| Scheduler | cron + timezone, topic queue, duplicate-run guard | IMPLEMENTED | Not proven as a scheduled autopilot. |
| YouTube publish | OAuth, encrypted credentials, resumable upload, delivery queue/reconcile | IMPLEMENTED | Live upload not verified (by design, no publishing allowed yet). |
| Instagram publish | Variant profile + reconcile-match stub only | **NOT STARTED** | No Graph API publisher exists. |
| Multi-channel | Accounts/destinations modelled; channel voice profiles | IMPLEMENTED (partial) | No per-channel *visual* theme packs. |
| Long-form | Landscape animated path for one test | NOT STARTED as a product | |
| Stream clips | `clipping/` with audio-energy highlight detection + yt-dlp | IMPLEMENTED (basic) | Audio energy alone won't find good moments. |
| Tests | 494 tests collected | — | Slow: one focused batch of 57 tests took 746 s. |

---

## 3. Why the videos look bad — evidence

### 3.1 What I looked at

Contact sheets were extracted with FFmpeg from these files and inspected:

| Video | Specs | Verdict |
|---|---|---|
| `data/artifacts/584fd95de80047649d959af2d9075363/preview.mp4` (latest **dashboard** job, Rust + AI) | 854×480, 77.2 s, −17.5 LUFS, peak 0.0 dBFS | **Fail.** Landscape, sentence-long captions up to 8 lines laid *over* the diagram boxes, overlapping and clipped labels, tiny 10–14 px box text, hedging hook, no CTA, too long. |
| `data/artifacts/9df50ade.../final.mp4` (Task 4, approved Docker Short) | 1080×1920, 43 s | Readable but plain. Small low-contrast labels in thin boxes, ~40% of the frame empty, static diagrams. |
| `data/artifacts/stage22_repeatability_second_topic/.../final.mp4` | 1080×1920, 42.7 s, −14.4 LUFS | Better: progress bar, bigger headings, terminal typing. Still mostly empty frame and box diagrams. |
| `artifacts/benchmark/docker-short/final/docker-short.mp4` (standalone "good" benchmark) | 1080×1920, 42.9 s, −14.6 LUFS, −1.4 dBTP | Best of the set: strong hook card, state chips, terminal typing, CTA. But it's still all text and boxes, the lower ~40% of the frame is empty, and nothing moves except the typing. |

### 3.2 Root causes (ordered by impact)

**R1 — Wrong renderer in production.** `pipeline/orchestrator.py` imports only
`rendering.preview.PreviewRenderer`. `rendering/shorts/` (reference-quality layout,
collision and safe-zone checks, event-driven raw-frame encoding) is referenced only
by `domain/contracts.py`, `pipeline/reference_contract.py` and tests. The Docker
benchmark's `produce.py` has topic-specific scene kinds (`run`, `ps`, `logs`, …) and
can't serve as the product renderer. So every improvement Codex made to "the good
renderer" never reached a dashboard job.

**R2 — The visual vocabulary is too small.** Every renderer can draw only
text, rounded rectangles, arrows, chips, a terminal and a progress bar. Shorts that
hold attention need some of these:
- an image or B-roll layer (photo, stock clip, screenshot, logo, map)
- icons and illustrations (vector)
- motion on every beat: pop/scale-in entrances, slides, count-up numbers, highlight
  sweeps, camera push-ins, transitions between scenes
- visual hierarchy that fills the 1080×1920 canvas (the safe zone runs y=200–1500,
  but content usually ends near y≈1160)
- a modern type pairing. DejaVu Sans Bold is the only face and looks dated; bundle
  OFL fonts such as Inter/Montserrat plus JetBrains Mono.

The rulebook already says "a video made only from still cards … fails creative
acceptance", but the template set (`hook`, `big_stat`, `before_after`, `flow`,
`checklist`, `terminal`, `cta`) can't produce anything else.

**R3 — Script style.** The writer is boxed in by many hard rules (grounding,
exact-hash approval, no unsupported claims, hedge wording). Grounding is good, but
the outcome is cautious, essay-like narration ("Google reported Android's
memory-safety vulnerability share falling from 76 percent in 2019 to 24 percent in
2024."). There is a hook scorer (`yt-script/hookscore.py`), but a 41/100 hook was
still allowed through to rendering. A Short needs: a provocative first line within 1 s,
one idea per 2–4 s beat, payoff, CTA, 25–40 s.

**R4 — Audio inconsistency.** The dashboard path defaults to Piper (flatter voice).
Kokoro (`af_bella`) is installed and clearly better. Mastering passes in the fixture
paths but failed in the latest dashboard preview (−17.5 LUFS, clipping peak).

**R5 — The brain/executor contract is upside down.** The AI spends most of its
tokens satisfying governance (echo rules, schema repairs, source binding) and very
little on *creative direction*: which image, which emphasis word, which motion,
what the viewer sees at second 0. The renderer then has no creative inputs to work with.

**R6 — Hardware ceiling.** 3.7 GB RAM total, 1 GB worker container limit, no GPU.
Earlier 1080×1920 renders hit OOM. Local Stable Diffusion or video models are out.
The design has to rely on cheap per-frame compositing (cached layers, redraw only
what changes), which the `rendering/shorts/encode.py` work already moves toward.

---

## 4. Process and token findings

| Finding | Impact | Recommendation |
|---|---|---|
| `AUTONOMOUS_PROGRESS.md` is 476 KB (4,686 lines); the design doc is 190 KB with paragraph-long single lines; AGENTS.md is 14 KB of rules | Any agent that reads them spends ~150–180k tokens before working. The rules also produce long "evidence" prose instead of code. | Archive the log (`docs/archive/`), keep a ≤2-page `docs/HANDOFF.md` as the only file agents must read, and cut the design doc to current architecture + phase table. |
| ~5,000 changed lines + ~40 untracked source/test files uncommitted since 13 Oct | One bad `git checkout`/`clean` loses a week. The other agent can't tell what's finished. | Commit as WIP on a branch (e.g. `wip/reference-renderer`) before any new work. |
| Three status systems: design doc §11, `AUTONOMOUS_PROGRESS.md`, `docs/overnight/*` (stale since 11 Oct), plus `docs/STATUS.md` redirect | Contradictions and drift (e.g. a 16:9 Rust test kept alive after the portrait reference was chosen) | One source of truth: `HANDOFF.md` (now) + design doc phase table (plan). Delete or archive `docs/overnight/`. |
| Four renderers; legacy style versions v9–v13 kept "for compatibility" | Every fix has to be made in several places; Codex fixed the wrong one | One renderer for new Shorts. Keep legacy only to replay old approved jobs, frozen. |
| Codex host runner: root-owned Node/Codex pinned at 0.149.0 (local CLI is 0.160.0), systemd socket, separate Unix user | Strong isolation, but heavy to redeploy (wheel builds + hash checks after every prompt change). This caused several "deployment blocker" cycles. | Keep for production. For development, allow a direct-CLI provider in the worker behind a config flag. |
| No `CLAUDE.md`; no Claude content provider | Claude Code can't pick up project rules automatically; production can't fall back when Codex quota runs out | Add `CLAUDE.md` containing `@AGENTS.md` and `@docs/HANDOFF.md`. Add a `claude` content provider (see §6.4). |
| Slow tests (57 tests ≈ 12.5 min) | Agents skip tests or burn time waiting | A `fast` marker suite (<3 min, no real FFmpeg encodes) plus a separate `render` suite. |
| `api/app.py` 143 KB and `orchestrator.py` 104 KB, single files | Expensive for agents to read, and edit conflicts between agents | Split by router/stage when touched; no big-bang refactor. |

---

## 5. Target architecture — "AI brain, local muscle"

```
Brief / schedule ──► [BRAIN: Codex or Claude, 1–2 calls]
                         │  research (cached per brief)
                         │  VideoSpec JSON  ◄── strict schema, semantic only
                         ▼
                 [VALIDATOR + QA pre-check]  ──fail──► 1 repair call with
                         │                              structured errors
                         ▼
   [LOCAL EXECUTOR — no LLM tokens]
     Kokoro TTS (Piper fallback) → Whisper/forced alignment
     → asset fetch (icons, Wikimedia, optional free stock, AI-authored SVG)
     → ONE renderer (rendering/shorts) → music/SFX mix → 2-pass loudnorm
     → post-encode QA (ffprobe, decode, ebur128, bbox, contact sheet)
                         │
                         ▼
     Dashboard review (preview → approve) → publish queue (YouTube, IG) per channel
```

### 5.1 Brain output: `VideoSpec` v2 (suggested shape)

The brain chooses *what* and *why*. The renderer owns *where* and *how*. Coordinates
stay out of model output, as the existing rulebook requires, and that's right.

```json
{
  "schema_version": "videospec-v2",
  "channel_theme": "tech-dark",          // picks palette, fonts, music, SFX pack
  "title": "…", "sources": [{"id": "s1", "name": "Android Security Blog", "url": "…"}],
  "scenes": [
    {
      "id": "hook", "template": "hook_bigtext",
      "vo": "Google cut memory bugs from 76 to 24 percent. Here's how.",
      "emphasis": ["76", "24"],                       // caption highlight + SFX hits
      "visual": {
        "headline": ["76% → 24%"],
        "image": {"kind": "icon", "query": "shield-check"},   // or wikimedia / stock / svg
        "motion": "count_up"                          // from a fixed preset list
      },
      "sfx": "whoosh_in"
    }
  ]
}
```

- **Fixed preset lists** (`template`, `motion`, `sfx`, `image.kind`) keep output small
  and safe to validate.
- **`image.kind: "svg"`** lets the brain write a small vector illustration
  (≤4 KB, a restricted SVG subset, rasterised locally with `resvg`/`cairosvg`). That
  is the cheapest way to get *topic-specific* visuals with no GPU.
- **Token budget per video:** about 8–15k input (compact skill + brief + trimmed
  source excerpts) and about 2–4k output. That is roughly 4× less than the current
  ~57k-character prompts. Research is cached per brief, so a schedule never pays twice.

### 5.2 Executor rules

- One worker, sequential model use (Kokoro then Whisper) to bound RAM. Already in plan.
- Draft at 720×1280 for preview and final at 1080×1920. Already in plan.
- Every QA failure produces structured JSON (`{"code":"text_overflow","scene":"s3","element":"heading"}`),
  sent back to the brain **once**. After that the job fails visibly in the dashboard.

---

## 6. Changes required

### 6.1 Video quality (highest priority)

1. **Wire `rendering/shorts/` into the orchestrator** for new Shorts jobs
   (replace `PreviewRenderer` + `LocalMotionGraphicsProvider` on that path). Keep
   the legacy renderer only for replaying already-approved jobs.
2. **Motion layer:** easing-based entrances (pop, slide, fade), number count-ups,
   bar fills, highlight sweeps, a 2–4% slow camera push on every scene, 6–10-frame
   scene transitions. Rule: something visible changes at least every ~2 s.
3. **Image layer** (add a `media` slot to every template):
   - offline icon set (Tabler/Lucide SVG, MIT/ISC licensed) bundled in the repo
   - Wikimedia (already present) for real-world subjects, with rights recorded
   - optional free stock video/images (Pexels/Pixabay APIs are free but need a key,
     so **operator decision**: AGENTS.md bans paid APIs, not free ones)
   - AI-authored SVG illustrations (see §5.1)
   - software topics: real terminal capture (already done in the benchmark) and
     optionally browser screenshots
4. **New templates:** `image_focus` (full-bleed image + caption), `versus`
   (split screen), `timeline`, `ranked_list`, `quote`, `code_diff`, `map_pin`.
   Keep the existing seven.
5. **Fill the frame:** use 200–1300 for content (today it stops near 1160). Raise
   minimum body text to 56–64 px, headings to 96–130 px and terminal text to 52–56 px.
6. **Fonts and theme packs:** bundle 2–3 OFL fonts. Define `theme` JSON (palette,
   fonts, music preset, SFX pack, caption style) **per channel**, so multiple
   channels don't all look like the same navy template.
7. **Captions:** keep 1–3 words at 84 px. Add a pop-scale on the active word and an
   emphasis colour from `emphasis[]`.
8. **Audio:** Kokoro as the default voice everywhere, Piper as a logged fallback.
   Add a 0.3 s riser/hit on the hook and soft whooshes on transitions. Enforce
   −14 LUFS / ≤−1.5 dBTP on the *encoded* file on every path.

### 6.2 Script quality

- Prompt for **punchy, declarative** narration. Keep grounding through `sources[]`
  and the on-screen "Source:" line, but stop hedging in the VO itself.
- **Gate on the hook score:** below 65 means one rewrite of the hook only, then
  the job pauses for an operator decision.
- Length 25–40 s, 6–8 scenes, 8–15 words each (already the reference-short-v1 profile).
  Retire the 60–77 s / 16:9 test brief for Shorts.
- Add 3–5 **format recipes** per channel (myth-vs-fact, 3 mistakes, X in 30
  seconds, before/after, stat shock) so the brain picks a proven structure instead
  of inventing one each time.

### 6.3 Pipeline and product

- **Commit WIP**, then make `reference-short-v1` the only profile for new Shorts.
- Scheduler → topic queue → auto-generate → **pause at preview approval**. Full
  auto-publish should stay off until about 10 videos have passed manual review.
- Instagram Reels publisher (Graph API container → publish → status poll) on the
  existing delivery queue.
- Per-channel automation: channel → theme + voice + format recipes + schedule +
  destinations.
- Later: long-form (landscape template set, chapters via `yt-chapters`), and stream
  clips (add transcript-based moment scoring via Whisper + brain, on top of the
  audio-energy candidates).

### 6.4 Brain providers (Codex + Claude)

- Add a `ClaudeContentProvider` next to `HostRunnerContentProvider`, behind the
  existing `ContentProvider` interface and `pipeline.content_provider` config. It
  can call the Claude Code CLI in print mode or the Anthropic API. Each needs
  separate operator approval (cost and credentials). Use the same `VideoSpec`
  schema, validation and cache key.
- **Quota fallback:** when one provider returns a quota/rate-limit error, mark it
  `exhausted_until` and route the next job to the other. Per AGENTS.md, a provider
  change needs operator approval, so **approve this fallback policy once,
  explicitly**, and record it in AGENTS.md.
- Record `provider`, `model` and token usage per job (partly exists) so you can
  compare cost and quality between the two.

---

## 7. Phased plan

Each phase has one user-visible outcome. Do them one at a time.

| # | Outcome | Acceptance test | Evidence | Out of scope |
|---|---|---|---|---|
| **P0** | Repo is safe to hand between agents | WIP committed on a branch; `docs/HANDOFF.md` + `CLAUDE.md` exist; progress log archived; `pytest -m fast` < 3 min passes | Commit SHA, test output | Any feature work |
| **P1** | A dashboard-created Short renders through the **single** `rendering/shorts` library at 1080×1920 | Signed-in dashboard job → preview → final; 25–45 s; −15..−13 LUFS; layout QA report clean | Contact sheet with safe rails, ffprobe, ebur128, QA JSON | New templates, images |
| **P2** | The video *looks* like a Short: motion every ≤2 s, image/icon layer, fuller frame, new fonts | Same topic re-rendered; you watch it on a phone and rate it ≥ the Docker benchmark | Before/after contact sheets, your verdict | Stock API keys unless approved |
| **P3** | Brain v2: compact `VideoSpec` + Claude provider + quota fallback | Same brief generated by Codex and by Claude, both valid and rendered; prompt tokens ≤15k | Token usage per job, two rendered videos | Auto-publishing |
| **P4** | Hooks and formats: recipes + hook-score gate | 3 topics × 1 recipe each; every hook ≥65; your watch-through review | Scores, videos | — |
| **P5** | Scheduled autopilot to private YouTube on one channel | Schedule fires, video generated, waits for approval, uploads as **private** after approval | Remote video ID, reconcile record | Public publishing (needs your go) |
| **P6** | Instagram Reels delivery | Same asset delivered to an IG test account | Container/media IDs | — |
| **P7+** | Multi-channel themes, long-form, stream clipper | Per-feature | — | — |

---

## 8. How Codex and Claude can take turns

Both agents work on the same checkout and the same branch, **one at a time**.
The handoff is the git history plus one short file.

### 8.1 Files

| File | Who reads it | Content |
|---|---|---|
| `AGENTS.md` | Codex (auto), Claude (via `CLAUDE.md`) | Durable rules only. Trim to ≤5 KB: safety, test commands, definition of done. |
| `CLAUDE.md` | Claude Code (auto) | Two lines: `@AGENTS.md` and `@docs/HANDOFF.md`. |
| `docs/HANDOFF.md` | Both, **first thing every session** | ≤2 pages: current phase and its acceptance test; what's done/in progress; exact next step; commands to verify; open decisions for you; last updated by (Codex/Claude) + date + commit. |
| design doc | Only when changing the plan | Architecture + phase table (cut down). |
| `docs/archive/` | Nobody by default | Old progress log, old status files. |

### 8.2 Session protocol (both agents)

1. **Start:** `git status`, `git log -5 --oneline`, read `docs/HANDOFF.md`. Don't
   read the archive. Don't re-audit the repo.
2. **Work:** stay inside the current phase. Commit at every green checkpoint
   (`wip(P2): motion presets for flow template`), at least every ~30–45 min. When
   tokens run out mid-task, the other agent loses at most one checkpoint.
3. **Before stopping, or when near the token limit:** run `pytest -m fast`, commit,
   update the HANDOFF "next step" with a concrete command or file:line. This takes
   ~5 minutes of budget, so start it early.
4. **Never** both at once on the same branch. If you want parallel work, give each
   agent its own branch or git worktree and merge after review.

### 8.3 Suggested split (soft, not exclusive)

| Codex is good for | Claude is good for |
|---|---|
| Bulk implementation against a clear spec, tests, refactors, migrations | Viewing frames/contact sheets and judging visual quality (multimodal); creative/script direction; architecture review; root-causing tricky failures; writing the VideoSpec prompt and recipes |

A practical rhythm: **Claude** writes the phase spec and reviews the rendered
artifact. **Codex** implements and tests. **Claude** inspects the frames and either
accepts or writes a concrete fix list into HANDOFF. When one agent runs out of
tokens, the other continues the same loop alone.

### 8.4 Runtime vs. development

Keep two things separate:
- **Development agents** (Codex CLI / Claude Code editing this repo): the relay above.
- **Production brain** (the content provider the worker calls per video): chosen
  by config, with the approved quota fallback from §6.4. The development relay
  doesn't depend on which brain production uses.

---

## 9. Decisions needed from you

1. Approve **committing the current uncommitted work** to a WIP branch (P0).
2. Approve **retiring the legacy renderer** for new Shorts (old approved jobs keep it).
3. **Free stock media** (Pexels/Pixabay API key): yes or no? Icons, Wikimedia and
   AI-authored SVG work without it.
4. **Claude as a production brain**: through the Claude Code CLI (your subscription)
   or the Anthropic API (pay per token)? And approve the Codex⇄Claude quota-fallback
   policy.
5. OK to **archive** `AUTONOMOUS_PROGRESS.md` and `docs/overnight/` and slim
   AGENTS.md, so agents spend tokens on code, not records?

---

## Appendix — reproduction commands used in this review

```bash
# specs
ffprobe -v error -show_entries format=duration:stream=codec_name,width,height,r_frame_rate -of csv=p=0 <video>
# contact sheet (portrait)
ffmpeg -i <video> -vf "fps=1/3.6,scale=216:384,tile=6x2" -frames:v 1 sheet.png
# loudness
ffmpeg -nostats -i <video> -af ebur128=peak=true -f null - 2>&1 | grep -E 'I:|Peak:'
# which renderer the pipeline uses
grep -rn "from tubeforge.rendering" src --include=*.py | grep -v "^src/tubeforge/rendering"
```
