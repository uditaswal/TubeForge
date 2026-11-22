# TubeForge agent rules

Durable rules and safety contract. **No status or history here**: current focus and next step are in `docs/HANDOFF.md`.
Rules enforced by hooks (`.pre-commit-config.yaml`) are listed once and not repeated as prose.

## Never
- Commit on `main`, push to any remote, force-push, or merge to `main` without explicit approval for that exact merge.
- Publish to YouTube/Instagram, use paid external APIs, or make a live writer (Claude/Codex) call without the operator's go-ahead (state provider, calls and cost first).
- Reset a script-attempt allowance, expose secrets, alter host networking/firewall, touch unrelated Docker workloads, delete unrelated user files, or run destructive DB operations outside the TubeForge test/local DB.
- Use `--no-verify` or add AI-attribution trailers (hook-enforced).

## Allowed without asking
Inspect and edit repo files, add tests, install Python packages in the project env, run pytest, run this project's Docker Compose and read its logs, run FFmpeg/ffprobe, create temporary test artifacts, change local TubeForge config needed for tests.

## Branches (hook-enforced: `scripts/check_branch_name.sh`)
- Names are `<type>/<topic>`: `feat/`, `feature/`, `fix/`, `chore/`, `docs/`, `exp/`, `backup/`, `release/`. **Never `claude/`, `codex/` or any tool name**, including branches created by a tool's worktree feature — rename with `git branch -m` before the first commit.
- Work on `dev` or a feature branch/worktree; one agent per branch. Post a review (changes + validation evidence). Remove the branch and worktree after merging.

## Before you start
- `git status`, `git log -5 --oneline`, read `docs/HANDOFF.md`. Work only on the HANDOFF "Current focus" or what the operator asked; do not start frozen items.
- Read only what the task needs. Files over ~50 KB (`readme.md`, `api/app.py`, `pipeline/orchestrator.py`, `db/repositories.py`, design docs): line ranges via `rg -n`. No `grep -r`/`find`/`ls -R` sweeps over `data/`, `artifacts/`, `autonomous_logs/`; never read `.venv*/`, `models/` or media as text.
- Python with renderer deps: `.venv-benchmark/bin/python` with `PYTHONPATH=src`. Full suite ≈ 18 min: run it in the background.

## Working
- Multi-phase work: write a short plan first (per phase: user-visible outcome, acceptance test, evidence, out of scope). One phase at a time.
- Run relevant tests after a coherent stage, not after every edit. Fix failures rather than reporting them.
- Same root problem after two repair attempts or 45 min: stop and report evidence, two options and a recommendation.
- Preserve worker leases, ownership fencing, checkpoint/restart safety, atomic artifact promotion and cancellation.
- Status labels, exactly: **NOT STARTED**, **IMPLEMENTED** (code exists, not proven end to end), **VERIFIED** (tests + real-artifact inspection passed), **BLOCKED** (needs a user decision or external dependency).

## Video and scripts
- Judge video by looking at frames (`ffmpeg … tile=6x2` contact sheet, view the PNG), then run `.agents/skills/om-video-quality/qa_check.py <artifact dir>`. Tests alone never verify creative work. Standard: `docs/SHORT_FORM_VIDEO_RULEBOOK.md`.
- Production scripts come from Codex CLI or Claude only (no local LLM without approval). Accept a script only after reviewing creative quality and, while Settings "Require verified sources" is on (default), source grounding. When the operator turns it off, their material is the evidence: do not re-impose source checks.
- After two failed attempts or at the agreed budget: stop, show rejected scripts and reasons, ask Codex, Claude or a revised brief.
- Before any script, skill, research or scene-plan work read `doc-internal/CONTENT_SKILLS_CONTRACT.md`. `yt-script` is the only production narration skill. Never fabricate analytics, trends, sources or tool execution. Installed wheels must hash-match `.agents/skills`.

## Dashboard UI
- **Load a design skill first** (`frontend-design`, `impeccable` or `design-taste-frontend`) and keep the existing dark navy system (there is no dashboard token file yet; the video tokens in `docs/video-design-tokens.md` are not for the UI). Reuse components.
- **Look at the result:** signed-in screenshots at 390, 768 and 1440 px before reporting UI work done.
- Every control calls a real, tested API action and shows success, pending, disabled and failure truthfully; loading/empty/error states and keyboard access are part of the change.
- Background refresh is silent (no flicker; open dialogs stay open). Never show approval, deletion, render or publication as done before the backend confirms it; edits need a new approval of the exact artifact.
- `http://127.0.0.1:62065` is the only documented dashboard URL (loopback).

## Module boundaries and settings
- `src/tubeforge/clips/` imports nothing from the rest of TubeForge (`tests/test_clips_boundary.py`); reach it only via `pipeline/clip_runs.py`; OpenCV `<5`; AI calls only through the host Claude runner. `docs/clips.md`.
- Any limit, timeout or cap that can stall a run belongs on `/settings`: read it with `runtime_settings.shared().value(key, default)` at the point of use and test that the override reaches the code. Keep security, secret, geometry and safety-contract values (attempt allowance, auth, ports, sockets) locked. Never show a secret value. Update `docs/settings.md`.

## Repository hygiene
- Before each commit check `git status --short`; add any new generated/local path to `.gitignore` in the same change (`git check-ignore -v` to verify). Never untrack files just to make an ignore rule apply; flag it.

## Scratch space

The host `/tmp` is a small RAM-backed tmpfs. Containers run with `TMPDIR=/app/data/tmp` (compose.yaml; `core/tempdir.py` creates it and sweeps day-old leftovers). On the host, run builds, tests and installs through `scripts/with_disk_tmp.sh <command>` (or `export TMPDIR=$HOME/tmp`); `restart_stack.sh` and `stackctl.sh` already do. Never put large downloads or renders in `/tmp`.

## Definition of done
1. Relevant tests pass and existing tests still pass.
2. For video or UI: the real artifact or screenshot was inspected, with concrete pass/fail notes.
3. `docs/HANDOFF.md` "Open" and "Next command" updated (keep it under 60 lines; detail goes in the linked doc).
4. Only when an operator-visible workflow or setup changed: `readme.md` / the feature's doc updated, with a focused UI/API test.

Commit messages are the change log: say what changed and how it was validated. There is no separate progress log.
