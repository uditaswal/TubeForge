# HANDOFF — read this first (Codex and Claude)

Shared between agents. Keep it short; update **Next step** before stopping.
Rules and safety contract: `AGENTS.md`. Docs index: `docs/README.md`.
The long per-feature history (everything before 9 Nov 2026) is in git history and the local, git-ignored
`doc-internal/handoff-archive-20261109.md`; nothing here depends on it.
Branches: work on `dev` (worktree `../tubeforge-dev`, also where the Compose stack and Claude runner run) or a feature
branch/worktree; `main` is merged only after the operator approves that specific merge.

## Goal
Scheduled/user-briefed AI Shorts → local render (Kokoro TTS, Python/FFmpeg) → review → upload to
YouTube/Instagram. The AI (Codex *or* Claude) is only the "brain": it returns a strict JSON script + scene plan;
all pixels, audio and encoding are local and cost no tokens.

## Working rules
1. Start: `git status`, `git log -5 --oneline`, read this file. One agent per branch at a time.
2. Never commit on `main`. Work on `dev` or a feature branch, then post a review. Merge to `main` only after asking and getting explicit approval for that merge; never push or force-push a remote unless asked. Remove temporary branches/worktrees once merged.
3. Commit at every green checkpoint; before stopping update **Next step**. No AI attribution trailers; never `--no-verify`.
4. Judge video by looking at frames (`ffmpeg ... tile=6x2` contact sheet, then view the PNG) and run `.agents/skills/om-video-quality/qa_check.py`.
5. Python with renderer deps: `.venv-benchmark/bin/python` (`PYTHONPATH=src`). Heavy renders and the full test suite (about 18 min): run in the background.
6. Do not publish anything. Do not reset script-attempt allowances. No live writer (Claude/Codex) call without the operator's go-ahead.

## Architecture in one screen
- Dashboard (`api/app.py`, port 62065, loopback only; the operator uses an SSH tunnel) → durable job → worker (`workers/`, Docker) → `pipeline/orchestrator.py`.
- **Script owner** per job (`codex` default | `claude`). Codex: root-owned host runner (`/run/tubeforge-codex/codex.sock`, sudo to redeploy). Claude: user runner `scripts/run_claude_runner.sh` (`data/run/claude/claude.sock`). Routing: `providers/content/factory.py::ScriptOwnerRouter`.
- **Reference Shorts** (`m6-content-v8`, 9:16, 30–90 s): `pipeline/reference_short.py` → `rendering/shorts/` (Story style via HyperFrames). Preview 720×1280, final 1080×1920; QA: decode, −15..−13 LUFS, TP ≤ −1.5.
- Batch plans (`api/batch*.py`): import → queue (strictly FIFO) → Day review (checksum-bound approval, staged export). Spend cap: 40 calls / $8 / 24 h (`data/run/claude/usage-ledger.jsonl`).
- Long-form (Codex lane): reference intake, then LF2 primary-source grounding and bounded script admission (`docs/long-form-lf2-plan.md`).

## State (9 Nov 2026)
- `dev` is pushed to origin (merged: Batch plans cards/stage chips/drop zone/line-numbered errors/warnings, Day review Reject/Regenerate confirmation, stale-test refresh, `[whisper]` disabled by config). **Needs a stack rebuild to take effect:** `scripts/restart_stack.sh`.
- Operator verified: pronunciation fix and selective acronym gaps sound right; plain narration preferred over `[whisper]`; the Day review shorts (2026-11-04 `story-*`, and `pilot-ms1`) were watched and are fine. **Nothing is approved or published**; Approve/Stage is clicked in Day review (`/batch/review`).
- `[whisper]` is OFF: `pipeline.reference_short.delivery_whisper: "off"` (`config/production.yaml`); whisper cues are spoken plainly. The yt-script prompt still teaches it (changing it needs the host wheel redeploy, operator sudo). Test clips: `artifacts/review/whisper-test-20261109/`.
- Full suite on `dev`: 1020 passed; the only failure is `test_voice_preview_is_synthesized_once…` (no `piper` on the host; passes in the worker image). Fresh worktrees need the gitignored `models/` folder symlinked in.
- Operator review (9 Nov): "all looks fine" for the Batch plans / Day review changes and the shorts above. That is the visual sign-off for batch UI M-U1 and M-U2 (confirmations); Approve/Stage in Day review is still the operator's click.
- Real bug fixed: `GET /api/batch-plans` returned 500 when a topic's job had been deleted (shows "job missing" now).

## Next step (in order)
1. **Operator:** approve/stage the 2026-11-04 shorts in Day review (rebuild with `scripts/restart_stack.sh` if not done); click "Retry approved media stages" on job `49bfc7ef…`.
2. **Codex (LF2):** operator approved more Claude spend for the long-form pilots and said the long-form branch may merge after review. Still needs a spend figure per pilot, and deployment review of migrations `20261108_0033` and `0034`. Phase D is blocked on structured-draft failures (`docs/long-form-lf2-d-*.md`).
3. **Claude, UI:** Day review shows the script beside its sources; then M-U4 (empty/loading/error/disabled states, focus order, contrast).
4. **Claude, scripts:** one go-ahead Claude call to confirm a writer honours an operator script; script-naturalness leftovers (a running example with concrete values, v1/v2 scope, a figure in the hook; `docs/script-naturalness-plan.md`); `claude/script-audit` worktree holds Round 3.
5. **Operator, whenever:** review candidates `artifacts/review/php-m4-landscape-20261105-v2/final.mp4` and `artifacts/review/m4-portrait-20261105/final.mp4`; the 10 Nov 09:00 UTC check-in (`trig_01BehFQ3ksjkkZxXQkVccSmd`) reports the first overnight production run.
6. **Queued at the bottom (operator decision 9 Nov):** Codex⇄Claude auto-fallback (Track E is verified only on the unmerged `codex/provider-fallback`; needs merge, migration `20261105_0032`, rebuild; `docs/provider-fallback-review.md`) and the Shorts thumbnail `safe_region` check (needs the operator's real phone screenshot).

## Gotchas
- Batch jobs are strictly FIFO: a script parked at `script_approval_required` blocks every later batch job, including the 22:00 overnight run. Clear stray trial jobs first; rejecting a script does not unblock, deleting the job does.
- Failed generations burn the two-attempt allowance per exact request source packet: change the brief or sources, never reset counts. An identical accepted request reuses the cached script (no Claude call).
- Brief sources: small HTTPS `text/html`/`text/plain` pages on an allowlisted host, same-host HTTPS redirects only; fewer than two usable sources triggers a Claude research step. Very long sources fail before any model call (prompt over 90,000 characters).
- The Claude runner imports code at start: restart it after any prompt/layout change; restart `web` and `worker` after schema changes. Worker image extras: `alignment,reference-renderer`.
- Dashboard first load asks for thumbnails/ffprobe per ready job; on a busy host `/api/jobs` took 12–64 s and the worker once hit `database is locked`.
- Dashboard test login: create a temporary admin (`tubeforge create-admin`) and delete it and its sessions afterwards.
- Under heavy swap Whisper alignment can fail (retried once, then a logged estimate fallback).
