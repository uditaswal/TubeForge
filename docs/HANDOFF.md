# HANDOFF — read this first (Codex and Claude)

Last updated: 2026-10-26 (A/V quality phases 0–4) · branches `dev`, `main` and feature branch `claude/av-quality-phase1` (worktree `../tubeforge-av-quality`) · see `git log -3` for the checkpoint.
Rules: `AGENTS.md`. Detailed status table, render evidence and per-feature notes: `docs/handoff-notes.md` (read a section only when needed).
Plan/status of record: `design_doc/tubeforge-publishing-design.md`. Docs index: `docs/README.md`.
Reviews (read on demand): `docs/reviews/2026-10-21-end-to-end.md` (why videos looked bad), `2026-10-22-content-quality.md` (script/hook/voice/music/visual steps, "§9"), `2026-10-23-reference-codebases.md`, `2026-10-26-av-quality-hyperframes-voicestudio.md` (why Codex's M1–M3 changed nothing visible/audible; HyperFrames renderer, real music + SFX, Kokoro fp32, UTMOS; phases 0–5 in §7).
Video-quality work: `docs/video-quality/milestones.md` (Codex M1–M4: M1, M2 VERIFIED; M3 IMPLEMENTED, operator's full-video review pending; M4 NOT STARTED), evidence in `docs/video-quality/evidence.md`; broader M0–M9 plan in `docs/video-quality/plan-m0-m9.md`.
A/V quality phases 0–4 (HyperFrames benchmark, mood music + licensed SFX, Kokoro fp32 A/B [decided: kept int8], Kokoro voice blending, HyperFrames craft-gate checks in QA, one HyperFrames scene template proven end to end) on `claude/av-quality-phase1`, not yet merged into `dev` — full state and **every pending item** (every remaining template for phase 4, the two VoiceStudio items deliberately deferred: UTMOS scoring, inline pause/emphasis tags) in `docs/video-quality/av-quality-implementation-log.md`'s summary table.

## Goal
Scheduled/user-briefed AI Shorts → local render (Kokoro TTS, Python/FFmpeg) → review → upload to
YouTube/Instagram across channels. The AI (Codex *or* Claude) is only the "brain": it returns a
strict JSON script + scene plan; all pixels, audio and encoding are local and cost no tokens.

## Working rules for the relay
1. Start: `git status`, `git log -5 --oneline`, read this file. One agent on the branch at a time.
   **Never commit on `main`:** work on `dev` (worktree `../tubeforge-dev`) or a new feature branch/worktree, then post a review (changes + validation evidence). The operator merges to `main`; agents do not merge or push `main`. Remove temporary branches/worktrees once merged.
2. Commit at every green checkpoint; before stopping (or near your token limit) commit and edit
   **Next step** below with a concrete file/command. Commit messages carry no AI attribution trailers.
3. Judge video work by looking at frames: `ffmpeg -i x.mp4 -vf "fps=1/3,scale=270:480,tile=6x2" -frames:v 1 sheet.png`, then view the PNG.
4. Python with renderer deps: `.venv-benchmark/bin/python` (`PYTHONPATH=src`). Heavy renders: run in background.
5. Do not publish anything. Do not reset script-attempt allowances.
6. `pre-commit` (gitleaks + large-file/generated-file guards) runs on every commit; never bypass it with `--no-verify`.

## Architecture in one screen
- Dashboard (`api/app.py`, port 62065) → durable job → worker (`workers/`, Docker) → `pipeline/orchestrator.py` state machine.
- **Script owner** is per job (`ContentRequest.script_owner`, `codex` default | `claude`), chosen in the Creator Studio form.
  - Codex: root-owned host runner behind `/run/tubeforge-codex/codex.sock` (needs sudo to redeploy; `docs/deploy/codex-runner-runtime.md`).
  - Claude: user-level runner `scripts/run_claude_runner.sh` → `data/run/claude/claude.sock`
    (`src/tubeforge/host_claude_runner.py`; CLI binary resolved from the VS Code extension or `TUBEFORGE_CLAUDE_BIN`).
    Start it before using Claude jobs (`systemctl --user` unit in `docs/deploy/tubeforge-claude-runner.service`).
  - Routing: `providers/content/factory.py::ScriptOwnerRouter`. Config: `pipeline.claude` in `config/production.yaml`.
- **Reference Shorts path** (`m6-content-v8`, 9:16, 30–90 s, default 60): package carries `reference_short` scenes.
  Orchestrator branches to `pipeline/reference_short.py` → `rendering/shorts/` (layout, timeline, audio, encode, motion, icons, logos, mascot).
  Legacy v1–v7 / 16:9 box-and-caption jobs are refused.
- Preview = 720×1280 draft; final = 1080×1920. Both pass the library's QA (decode, loudness −15..−13 LUFS, TP ≤ −1.5).
- Publishing page: title/description suggestion (`pipeline/publication_suggest.py`), thumbnails (`pipeline/thumbnail.py`). Instagram publisher NOT STARTED.

## Status in one line each (details: `docs/handoff-notes.md`)
IMPLEMENTED, not operator-watched: Claude script owner + model picker, hook/craft gates, writers' room (editor applied-path not yet seen live), real-imagery plates (Pixabay + local stock library + source screenshots + code cards), brand logos, motion/icons, preview→final→publication prep (job `8c23e099…`), upload-ready title/description/thumbnail, Shorts thumbnails, display options, mascot, loop/debate ending. Nothing approved or published.

## Next step
0. **A/V quality plan — all three §8 decisions approved by the operator (26 Oct); phases 0–4 now done or prototyped on `claude/av-quality-phase1`, not merged.** Phase 0 (HyperFrames host benchmark) **VERIFIED**. Phase 1 (mood-varied music + licensed, caused SFX) **CLOSED, not pursuing further audio polish**: heard by the operator on a real render, SFX toggled off then explicitly back on the next day ("not a huge improvement" without them) — `sfx_enabled` defaults to `True` again in `master()`/`reference_short.render()`; effort moves to phase 4. File: `http://localhost:8082/review/railway-breach-new-audio.mp4` (served via the operator's own local `tubeforge-video-viewer`/nginx — a raw path alone didn't work the first time). Phase 2 (Kokoro fp32 A/B) **DECIDED**: operator kept int8, no config change. Phase 2b (Kokoro voice blending, `09e47f2`) **IMPLEMENTED**, config-only, no channel has opted in. Phase 3 (HyperFrames craft-gate checks ported into `qa_check.py`, `c07d2a4`) **DONE**. Phase 4 (HyperFrames as the Shorts renderer) **PROTOTYPE, now the priority**: three of seven scene templates (`hook`, `loop`, `big_stat`) proven end to end with real renders, real content, real audio, real QA — not wired into any job; the other four templates plus production wiring are the next work, listed in order in the implementation log. **Operator instruction (27 Oct): flag any large download (e.g. an `npm install` for the hyperframes CLI, the Dockerfile's proposed Node addition) and let the operator run it themselves rather than spending session time/tokens on it.** **Deliberately deferred, not forgotten** — UTMOS naturalness scoring and inline pause/emphasis script tags (both VoiceStudio; reasons in the log). **Full pending-item table: `docs/video-quality/av-quality-implementation-log.md`.** **Next:** continue phase 4 with `before_after` (or any of the four remaining templates — layout variations now that the one new motion idea, `big_stat`'s count-up, is done).
1. **Ending choice + length (25 Oct):** Studio "How the video ends" (`ending`: `loop` default | `debate`). Preset `reference-short` is 60 s default, 30–90 s allowed (scenes 6–20, `prompts.reference_word_budget`). Not yet rendered live at 60/90 s or with a debate ending: restart the Claude runner, run a job, check memory/RTF on a 90 s render.
2. Keep the Claude runner running (`scripts/run_claude_runner.sh`; a dead runner shows as "preflight Connection refused", now retried automatically). The old landscape caption-overlap defect (job `7646d2e9…`) only affects the retired 16:9 renderer.
3. Operator reviews: M3 full video (`docs/video-quality/evidence.md`); previews of `c93f4c29…`, `90625bb5…`, `b1c3a6b5…`, `8c23e099…`; `final.mp4` of `8c23e099…` before any publication gate (do NOT approve until watched).
4. Verify the writers' room editor applies in a live job (`provenance.writers_room.editor.applied`), then content review §9 steps 3–4: sound (A1 whole-narration synthesis, A4 voice processing, A5 licensed music, A6 SFX) and visual depth (diagrams, versus template, beat-synced cuts).
5. Scheduler → private YouTube, then Instagram.
6. **Codex v8 jobs REQUIRE the host redeploy** (`docs/deploy/codex-runner-runtime.md`): the old wheel's preflight hashes differ from the worker's, so Codex jobs stop before any model call until redeployed.

## Gotchas learned
- Kill/restart the Claude runner after *any* change to prompts/layout (it imports code at start): `scripts/run_claude_runner.sh`.
  Restart `web` and `worker` too after schema changes (they import `src` once).
- Failed generations burn the two-attempt allowance per exact request; change the brief to start a new request, never reset counts.
- Voice+alignment run fine at 2 GB; under heavy host swap Whisper can fail (now retried once, then logged estimate fallback).
- Worker image needs extras `alignment,reference-renderer` (`docker compose build worker web migrate scheduler` after pulling).
- Dashboard test login: create a temporary admin (`tubeforge create-admin`), delete it and its sessions afterwards.
- Known pre-existing test failures on the host: `test_voice_preview_is_synthesized_once…` (no `piper` on host; passes in the worker image).

## Open decisions for the operator
- Auto-fallback Codex⇄Claude when quota is exhausted (currently manual per-job choice only).
- Check the Shorts thumbnail `safe_region` against real phone screenshots.
