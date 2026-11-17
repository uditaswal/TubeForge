# HANDOFF — read this first (Codex and Claude)

**Hard limit: 60 lines.** Current focus, open items, next command. Detail goes in the linked doc, history in git
(previous long version: `git show 01dad7f:docs/HANDOFF.md`). Rules: `AGENTS.md`. Docs index: `docs/README.md`.

## Goal
Scheduled/user-briefed AI Shorts → local render (Kokoro TTS, Python/FFmpeg) → review → upload to YouTube.
The AI (Codex or Claude) only returns a strict JSON script + scene plan; pixels, audio and encoding are local.

## Current focus (one at a time)
**Publish the first private YouTube Short end to end.** Everything not listed under "Open" is frozen.

## Architecture in one screen
- Dashboard (`api/app.py`, port 62065, loopback; operator uses an SSH tunnel) → durable job → worker (`workers/`, Docker) → `pipeline/orchestrator.py`.
- Script owner per job (`codex` default | `claude`): Codex host runner `/run/tubeforge-codex/codex.sock` (sudo to redeploy); Claude user runner `scripts/run_claude_runner.sh` (`data/run/claude/claude.sock`). Routing: `providers/content/factory.py::ScriptOwnerRouter`.
- Reference Shorts (9:16, 30–120 s): `pipeline/reference_short.py` → `rendering/shorts/`. Preview 720×1280, final 1080×1920; QA −15..−13 LUFS, TP ≤ −1.5.
- Batch plans (`api/batch*.py`): import → strictly FIFO queue → Day review (`/batch/review`). Spend cap 40 calls / $8 / 24 h.
- Settings `/settings` (`docs/settings.md`); exact-script mode `script_mode: exact` (`pipeline/exact_fit.py`).

## Open (status label — next action)
1. **Stack rebuild — waiting on operator.** `dev` has unpushed merges (exact-fit, M-U4, story beats, disclosure fix). Run `scripts/restart_stack.sh`.
2. **Reference Shorts reconciliation — IMPLEMENTED.** Review the final, then verify the signed-in production flow without publishing. `docs/reference-shorts-plan.md`.
3. **Publishing (private YouTube) — IMPLEMENTED, live BLOCKED** on credentials + a named approved final + exact-post permission. `docs/publishing-backend-review.md`, contracts in `docs/publishing-api-contracts.md`.
4. **Clips — IMPLEMENTED** on `feature/clipforge-engine` (worktree `../tubeforge-clipforge`). Next: restart runner, rebuild worker (`clips` extra), run one job from `/clips` with the operator. Before merge, remind the operator of the deferred performance loop. `docs/clips.md`.
5. **Long-form LF2 D — BLOCKED** on operator installing the reviewed host wheel (sudo). `docs/long-form-lf2-d-codex-preflight.md`.
6. **Script audit P5 — IMPLEMENTED,** before/after NOT MEASURED; needs the operator's go-ahead for one Claude call (state cost first). `docs/original-script-audit.md`.
7. **Operator queue:** LeetCode job `642dc2b2…` waits at `script_approval_required` (blocks the FIFO queue); "Retry approved media stages" on `49bfc7ef…` if still wanted; 2026-11-04 shorts are dropped.

## Frozen (do not work on until the operator reopens)
Instagram publishing (16 Nov) · Docker runner qualification · landscape/LF3 · provider auto-fallback · thumbnail `safe_region`.

## Next command
`scripts/restart_stack.sh` (operator), then open `/batch/review` and approve one short for a private YouTube draft.

## Gotchas
- Batch queue is strictly FIFO: a script at `script_approval_required` blocks every later job, incl. the 22:00 run. Deleting the job unblocks; rejecting does not.
- Two-attempt allowance per exact source packet: change brief/sources, never reset counts. Identical accepted requests reuse the cached script.
- Sources: small HTTPS html/plain pages on allowlisted hosts; < 2 usable sources triggers a research call; prompt cap 90,000 chars.
- Claude runner imports code at start: restart it after prompt/layout changes; restart `web` + `worker` after schema changes.
- Full suite ≈ 18 min (run in background). Known host-only failure: `test_voice_preview_is_synthesized_once…` (no `piper`). Fresh worktrees need `models/` symlinked.
- Dashboard test login: temporary admin via `tubeforge create-admin`; delete it and its sessions afterwards.
