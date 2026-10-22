# HANDOFF — read this first (Codex and Claude)

Last updated: 2026-10-22 by Claude · branch `dev` · see `git log -3` for the checkpoint.
Rules live in `AGENTS.md`. Evidence log `AUTONOMOUS_PROGRESS.md` is local-only and small (append-only; archives `_N` — do **not** read them).
Full review of the project (why videos look bad, phases): `docs/REVIEW_2026-10-21_END_TO_END.md`.

## Goal
Scheduled/user-briefed AI Shorts → local render (Kokoro TTS, Python/FFmpeg) → review → upload to
YouTube/Instagram across channels. The AI (Codex *or* Claude) is only the "brain": it returns a
strict JSON script + scene plan; all pixels, audio and encoding are local and cost no tokens.

## Working rules for the relay
1. Start: `git status`, `git log -5 --oneline`, read this file. One agent on the branch at a time.
2. Commit at every green checkpoint; before stopping (or near your token limit) commit and edit
   **Next step** below with a concrete file/command.
3. Judge video work by looking at frames: `ffmpeg -i x.mp4 -vf "fps=1/3,scale=270:480,tile=6x2" -frames:v 1 sheet.png`, then view the PNG.
4. Python with renderer deps: `.venv-benchmark/bin/python` (`PYTHONPATH=src`). Heavy renders: run in background.
5. Do not publish anything. Do not reset script-attempt allowances.

## Architecture in one screen
- Dashboard (`api/app.py`, port 62065) → durable job → worker (`workers/`, Docker) → `pipeline/orchestrator.py` state machine.
- **Script owner** is per job (`ContentRequest.script_owner`, `codex` default | `claude`), chosen in the Creator Studio form.
  - Codex: root-owned host runner behind `/run/tubeforge-codex/codex.sock` (needs sudo to redeploy).
  - Claude: user-level runner `scripts/run_claude_runner.sh` → `data/run/claude/claude.sock`
    (`src/tubeforge/host_claude_runner.py`; CLI binary resolved from the VS Code extension or `TUBEFORGE_CLAUDE_BIN`).
    Start it before using Claude jobs (`systemctl --user` unit in `docs/tubeforge-claude-runner.service`).
  - Routing: `providers/content/factory.py::ScriptOwnerRouter`. Config: `pipeline.claude` in `config/production.yaml`.
- **Reference Shorts path** (`m6-content-v8`, 9:16, 25–45 s): package carries `reference_short` scenes.
  Orchestrator branches to `pipeline/reference_short.py` → `rendering/shorts/` (layout, timeline, audio, encode).
  Legacy path (`rendering/preview.py`, `providers/media/local_graphics.py`) remains only for old jobs.
- Preview = 720×1280 draft; final = 1080×1920. Both pass the library's QA (decode, loudness −15..−13 LUFS, TP ≤ −1.5).

## Status (use AGENTS.md labels)
| Item | Status | Evidence |
|---|---|---|
| Claude as script owner (runner, router, API field, Studio selector) | IMPLEMENTED | Live Claude scripts through the dashboard API (3 jobs, ~$0.4–0.8 list price each); `tests/test_script_owner.py`. Studio selector exists but was not browser-tested. |
| Orchestrator uses `rendering/shorts` for `m6-content-v8` jobs | IMPLEMENTED | Dashboard job `41e2ee9a…` rendered through it (below) |
| Dashboard-generated Rust Short, 720×1280 preview, motion + icons | IMPLEMENTED (preview only) | below; creative acceptance by the operator is still open |
| Script-writer picker in Studio: Sonnet 5.5 medium (default), Opus 5.5 high, Codex GPT-5.6 Sol | IMPLEMENTED | `script_model` on `/api/videos`; `/api/content-profiles` lists models; Sonnet job `8c23e099…` end to end |
| Hook/script craft: prompt block + scored hook gate (≥58) + repairable skill/layout checks | IMPLEMENTED | Sonnet hooks scored 56–70 vs 42 before; selected "76% memory bugs, then what?" (67). Gate lives in `providers/content/youtube_skills.hook_gate` and `validate_video_package` |
| Motion layer (`rendering/shorts/motion.py`) + 22 procedural icons (`icons.py`) | IMPLEMENTED | stills + full encode inspected |
| Preview approval → 1080×1920 final → quality gate for reference jobs | NOT STARTED (code paths written, never run) | `_reference_render_checkpoint`/`_reference_quality` |
| Publication prep for reference jobs | NOT STARTED | `_publication_checkpoints` expects legacy `timing_map.phrases`, assets, thumbnail inputs |
| Instagram publisher | NOT STARTED | |

## Render evidence
Latest (Sonnet 5.5 medium, new hook gate): job `8c23e099f53640688fb8c26957ea4e57`, preview 720×1280, 34.2 s, −14.3 LUFS, `review-sheet.png` next to it; script generation 2.2 min, ~$0.38 list price.
Earlier: job `41e2ee9a44d6428885a387714a4788e8` (Claude-owned, preset `reference-short`, created/approved/rendered via the
signed-in dashboard API on 22 Oct; script approved only for a local test render, **nothing published**):
`data/artifacts/41e2…/preview.mp4` — 720×1280, 30 fps, 34.0 s, H.264/AAC 48 kHz, −14.3 LUFS, TP −2.5 dBFS,
full decode OK, Whisper forced alignment on 6/7 scenes (1 estimated — needs listening review),
render 11× realtime, peak RSS 0.64 GB. Review images next to it: `review-sheet.png` (2-s timeline), `motion-stills.png`.
Observed: readable hook, big count-up stats, icon badges, placeholders before each reveal, captions below the
graphics, sources on screen, CTA. Still weak: only boxes/stats/icons (no photos or illustrations), DejaVu type,
lower ~25% of the frame is platform-reserved space. The operator has **not** watched it yet.
Earlier job `6ddea03e…` (before motion) is the baseline for comparison.

## Next step
1. Operator watches `preview.mp4` (Studio → job → Watch preview) and gives creative feedback.
2. Run preview approval → final render (1080×1920 takes ~2.5× longer) → fix `_publication_checkpoints` for reference jobs
   (build `timing_map`-compatible chapters from `timeline.json`; skip asset-based thumbnail inputs).
3. Image layer beyond icons: Wikimedia/stock photo slot per scene (rights path exists in `providers/media/`), better fonts.
4. Hook quality gate (hookscore < 65 → one rewrite), format recipes, then scheduler → private YouTube, then Instagram.
5. Codex (gpt-sol) host runner is the old wheel — its prompts lack the craft block/icons until redeployed, so the worker's new hook gate may reject Codex scripts: icons/phone-fit prompt text only reach Codex after the root redeploy
   (`docs/tubeforge-codex-runner-runtime.md`); Codex output is still validated by the worker (fit/word-count checks).

## Gotchas learned
- Kill/restart the Claude runner after *any* change to prompts/layout (it imports code at start): `scripts/run_claude_runner.sh`.
  Restart `web` and `worker` too after schema changes (they import `src` once).
- Failed generations burn the two-attempt allowance per exact request; change the brief to start a new request, never reset counts.
- Voice+alignment run fine at 2 GB; under heavy host swap Whisper can fail (now retried once, then logged estimate fallback).
- Worker image needs extras `alignment,reference-renderer` (`docker compose build worker web migrate scheduler` after pulling).
- Dashboard test login: create a temporary admin (`tubeforge create-admin`), delete it and its sessions afterwards.

## Open decisions for the operator
- Free stock media key (Pexels/Pixabay)? Not needed for icon/procedural visuals.
- Auto-fallback Codex⇄Claude when quota is exhausted (currently manual per-job choice only).
- Commit/branch policy for the large uncommitted working tree (nothing has been committed by Claude).
