# HANDOFF — read this first (Codex and Claude)

Shared between agents on this repo. Keep it short; update **Next step** before stopping.
Rules and safety contract: `AGENTS.md`. Public docs index: `docs/README.md`.
Longer working notes (plans, reviews, render evidence, per-feature status) live in the local, git-ignored
`doc-internal/` folder when present; nothing here depends on it.
Branches: work on `dev` (worktree `../tubeforge-dev`, which is also where the Compose stack and Claude runner run) or a feature
branch; `main` is merged only after the operator validates and approves. See `git log -5` for the checkpoint.

## Goal
Scheduled/user-briefed AI Shorts → local render (Kokoro TTS, Python/FFmpeg) → review → upload to
YouTube/Instagram across channels. The AI (Codex *or* Claude) is only the "brain": it returns a
strict JSON script + scene plan; all pixels, audio and encoding are local and cost no tokens.

## Working rules for the relay
1. Start: `git status`, `git log -5 --oneline`, read this file. One agent on the branch at a time.
   **Never commit on `main`:** work on `dev` (worktree `../tubeforge-dev`) or a new feature branch/worktree, then post a review (changes + validation evidence). Agents may merge to `main` only after asking and getting the operator's explicit approval for that specific merge; ask every time, and never push or force-push a remote without being asked. Remove temporary branches/worktrees once merged.
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

## Status in one line each (details: local `doc-internal/handoff-notes.md`)
Merged to `main`, IMPLEMENTED and not operator-VERIFIED: Claude script owner + model picker, hook/craft gates, writers' room, real-imagery plates,
HyperFrames **Story** style (diagram/terminal/word-timed key-word highlight; a diagram or terminal scene beats a captured source plate), voice delivery cues
(`[pause]`, `[breath]`, `*stress*`, `[whisper]`; scripts barely use them yet), spoken-form rules (acronyms by letter name, versions, years),
batch plans (import → queue → day review → checksum-bound staged export, thumbnails, opt-in overnight production + hold; `docs/batch-plans.md`),
Claude spend cap (rolling 24 h: 40 calls, $8, $1.50/call; env `TUBEFORGE_CLAUDE_*`, ledger `data/run/claude/usage-ledger.jsonl`).
Pilot: one 60 s Log4Shell Short rendered end to end on 1 Nov (loudness/loop checks pass). Nothing is approved or published.

## Next step
0. **Now:** Track D (audio) is in progress on branch `feature/audio-quality`: M-AU1 pronunciation check is IMPLEMENTED (`pipeline/pronunciation.py`; letter A is spelled "eh" because Kokoro reads "ay" as "eye"); not merged yet. Codex's weekly limit is exhausted, so Codex-lane tracks (B's M-S5–M-S8, E) wait.
0. **Priority order (operator, 1 Nov): D audio → F stock backdrops → B channel safety → E provider fallback → C batch UI.** Claude takes that order; Codex runs B's M-S5–M-S8 then E in parallel in its own lane. Overlaps are done once (M-AU4 covers M-S3, M-AU2 covers M-S4's cues).
1. **Track B, channel safety and originality** (local plan `doc-internal/design_doc/tubeforge-publishing-design.md`, "PRIORITY TRACK B"): Claude takes M-S1–M-S4
   (layout families chosen by content, originality gates, audio rotation + licence trail, truthful encode metadata + cue adoption); Codex takes M-S5–M-S8
   (disclosure/compliance record in the export, batch repetition report, cadence guard, checklist doc) on `feature/channel-safety`. Do NOT add detection-evasion
   (random EXIF/encoder spoofing, fingerprint jitter); metadata stays truthful.
2. **Batch gaps:** plans ignore their `sources:` list (every batch job runs web research, which fails on JS-rendered docs); run the 3-video batch pilot and a 7-day run.
3. **Accepted by the operator (1 Nov):** Codex M3 stock-footage video and the evidence-quote step. Unblocked: M4 and the design-tokens step (`doc-internal/video-quality/`). Still to listen to: voice cue A/B. **Track F:** stock-footage backdrops behind the hook/loop (and where it fits) in the Story renderer (Claude).
4. `qa_check.py` still uses an old 25–45 s duration window (Shorts profile is 30–90 s); fixing it means a skill change and a host wheel redeploy.
5. **Batch UI overhaul** (Track C, M-U1–M-U4, Claude): Batch plans and Day review look poor to the operator; redesign after Codex's M-S5–M-S8 land.
6. **Audio track D** (pronunciation check, cue adoption, mix checks; Claude) and **provider fallback track E** (dashboard mode: Claude only / Codex only / automatic fallback, so one membership can be cancelled; Codex builds the dashboard/router, Claude the runner error codes).
7. Parked until better hardware: per-channel look and UTMOS scoring (3 GB RAM, no GPU).
8. Publishing (scheduler → private YouTube, then Instagram) stays deferred until video generation is accepted.

## Gotchas learned
- Restart everything with `scripts/restart_stack.sh` (rebuild image, migrate, web/worker/scheduler, Claude runner; no sudo needed). The runner imports code at start, so restart it after any prompt/layout change.
  Restart `web` and `worker` too after schema changes (they import `src` once).
- Failed generations burn the two-attempt allowance per exact request *source packet*; change the brief or sources for a new request, never reset counts. Re-submitting an identical accepted request reuses the cached script (no Claude call).
- Source fetching follows same-host HTTPS redirects only; a cross-host redirect skips that researched source (at least two usable sources are still required).
- Dashboard and review viewer (`:62065`, `:8082`) are loopback-only; the operator reaches them over an SSH port-forward.
- Voice+alignment run fine at 2 GB; under heavy host swap Whisper can fail (now retried once, then logged estimate fallback).
- Worker image needs extras `alignment,reference-renderer` (`docker compose build worker web migrate scheduler` after pulling).
- Dashboard test login: create a temporary admin (`tubeforge create-admin`), delete it and its sessions afterwards.
- Known pre-existing test failures on the host: `test_voice_preview_is_synthesized_once…` (no `piper` on host; passes in the worker image).

## Open decisions for the operator
- Auto-fallback Codex⇄Claude when quota is exhausted (currently manual per-job choice only).
- Check the Shorts thumbnail `safe_region` against real phone screenshots.
