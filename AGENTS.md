# TubeForge autonomous development rules

You are developing TubeForge, an automated YouTube-video generation system. This file is the durable rules/safety contract (no milestone history). Current phase and next step: `docs/HANDOFF.md`.

## Project records (keep consistent; never copy status between them)

- `design_doc/tubeforge-publishing-design.md` — single current plan/status: contracts, phases, release state, blockers, next five actions. Full former text: `docs/archive/` (do not read unless needed). Update affected stages, status, evidence and next action after each coherent stage.
- `AUTONOMOUS_PROGRESS.md` — local-only (gitignored) append-only evidence log: scope, validation commands/results, artifacts inspected, blocker, next action, **≤ ~15 lines per entry**. Append with `cat >> AUTONOMOUS_PROGRESS.md <<'EOF'`; never Read/grep/cat it whole. **Rotate** when it exceeds 40 KB (`wc -c`) or a new calendar month starts: rename to the next free `AUTONOMOUS_PROGRESS.md_N`, create a fresh file with a short summary of the archive plus the last entry. Never read `AUTONOMOUS_PROGRESS.md_*` unless the operator asks. Do not claim a milestone complete there unless its plan stage is **VERIFIED** with linked evidence.
- `readme.md` — operator setup/workflow guide; update when supported setup, configuration or workflow changes.
- `docs/SHORT_FORM_VIDEO_RULEBOOK.md` — video quality and creative review.
- `docs/CONTENT_SKILLS_CONTRACT.md` — binding rules for `.agents/skills`, `yt-script`, research, scene plans and the reference-short profile. **Read it before any script, skill, research or scene-plan work.**

- Delivery QA: before any video job is called done, run `.agents/skills/om-video-quality/qa_check.py` on its artifact folder and apply that skill's checklist; publishing-package rules are in `om-social-delivery`.

## Context hygiene (token cost)

Large files and generated trees are fine to use for debugging, but read them by exact path and in slices; never sweep them.
- Never read `AUTONOMOUS_PROGRESS.md_*`, `.venv*/`, `models/`, or media files as text. Inspect video via FFmpeg frames/ffprobe.
- No `grep -r`, `find`, `ls -R` or glob sweeps over `data/`, `artifacts/`, `autonomous_logs/`. Open the named job file, `tail -n 100` logs, query `data/tubeforge.db` with targeted `sqlite3` SELECTs.
- Prefer `rg`/`grep -n` over whole-file reads. For files over ~50 KB (`readme.md`, the design doc, `api/app.py`, `pipeline/orchestrator.py`, `db/repositories.py`) read only the needed line range.
- Delegate broad exploration to a subagent; report conclusions, not file dumps.

## Working policy

- Inspect the existing architecture first; implement the requested milestone completely.
- Run relevant tests after a coherent stage and before reporting acceptance; do not rerun suites after each small edit. Diagnose and fix failures rather than reporting them. No completion claim until validation passes.
- Preserve worker leases, ownership fencing, checkpoint/restart safety, atomic artifact promotion and cancellation handling.
- Multi-phase work: write a plan first. Per phase: one user-visible outcome, acceptance test, required artifact/evidence, out-of-scope items. One phase at a time; report its acceptance before the next.
- Status labels exactly: **NOT STARTED**, **IMPLEMENTED** (code exists, not proven end to end), **VERIFIED** (required tests and real-artifact inspection passed), **BLOCKED** (needs a user decision or external dependency). Never call IMPLEMENTED work complete. Creative work needs a real generated artifact inspected against the quality bar, with concrete pass/fail evidence; tests alone are insufficient.
- Same root problem after two repair attempts or 45 min of active debugging (downloads and healthy renders excluded): stop; report failure, evidence, two options, and a recommendation. Add no adjacent features while the phase's highest-risk acceptance test fails.
- Long runs: report every 20 min — phase, verified result or blocker, next acceptance test, whether a decision is needed.
- Before claiming the full Shorts workflow complete: inspect one real 30–120 s 1080×1920 video against the standard in `readme.md`, verify the signed-in dashboard flow, and update status docs. Test the signed-in dashboard whenever an operator-facing workflow changes.

### Script generation

Use Codex CLI or Claude for production scripts; no local LLM for production generation, retries or acceptance without operator approval for that run. Before changing the script provider, report provider, expected cost/tokens, fallback and acceptance test. Accept a script only after reviewing source grounding and creative quality (schema validity alone is insufficient). After two failed attempts or when the agreed budget is reached, stop retries, show rejected scripts and reasons, and ask: Codex CLI, Claude, or a revised brief. Never silently reset an exhausted allowance.

## Repository hygiene

Before every commit review `git status --short` for generated, machine-local or sensitive files, and update `.gitignore` in the same change for any new ignorable path (media/artifacts, model weights/caches, local DBs, logs, venvs, build/test output, credentials, editor/OS files). Verify with `git check-ignore -v`; find tracked-but-ignored files with `git ls-files -ci --exclude-standard`. Avoid broad rules that hide source, migrations, fixtures or intentionally versioned config. Never untrack files merely to make an ignore rule apply; flag that to the operator.

## Dashboard UI contract

The Creator Studio dashboard, login page and HTTP APIs are one operator workflow; update the UI in the same change as any operator-visible capability.
- A control must invoke a real, tested API action and report success, pending, disabled and failure states truthfully. Consider labels, permissions, loading/empty/error states, mobile layout and activity/audit visibility for every API workflow change.
- Background refresh stays silent after initial load: keep visible data and open dialogs; no loading screens or flicker.
- Reviews are explicit and safe: edits/revisions need a new approval of the exact reviewed artifact; never imply approval, deletion, render, publication or AI revision completed before the durable backend confirms it.
- Preserve the dark navy visual system, readable hierarchy, keyboard accessibility and desktop/tablet/mobile behavior; reuse existing components.
- Add or update focused API/UI tests for changed workflows; update `readme.md` when a flow, login behavior or dashboard URL changes.
- `http://127.0.0.1:62065` is the sole documented developer dashboard URL; Compose binds it to loopback only. Do not document or reserve other host ports (preview-proxy ports are transient).

## Allowed autonomous actions

Without asking: inspect repo files, edit source, add tests, install Python packages in the project environment, run pytest, run Docker Compose and read logs for this project, run FFmpeg/ffprobe, create temporary test artifacts, modify local TubeForge config needed for tests.

## Do not

Delete unrelated user files; alter host networking/firewall; expose secrets; push to remote Git repositories; publish anything to YouTube; use paid external APIs; modify unrelated Docker workloads; run destructive database operations against anything except the TubeForge test/local database.

## Definition of done

"Implemented" is not done. Completion requires:
1. relevant automated tests pass and existing tests remain passing;
2. the requested end-to-end smoke test passes and produced artifacts are inspected/validated;
3. important findings appended to `AUTONOMOUS_PROGRESS.md` (rotating per above);
4. the plan's current-status section updated with state, evidence, blocker and next action;
5. `readme.md`/operator docs updated for externally visible setup or workflow changes;
6. `.gitignore` reviewed; the Dashboard UI contract applied with focused workflow tests whenever an operator-visible capability changed.
When validation fails, continue debugging.

## Content skills and research

Project skills live in `.agents/skills/`; `yt-script` is the sole production narration skill (never update or load competing copies); `viral-short-form` is optional reference only. Read the selected `SKILL.md` and required resources before use, and review supporting scripts before running them. Skills supply content instructions; rendering, narration, scheduling, analytics and publishing belong to the application. Never fabricate analytics, trends, sources, performance or tool execution; heuristic scores are review signals, not view predictions. Installed wheels must hash-match `.agents/skills`; changed skill resources need installed-wheel verification before host use. Research is separate from narration, runs once per exact brief, and its output is context, never approved factual evidence or operator approval. Everything else — skill-to-task mapping, reference-short-v1 profile numbers, scene-contract and landscape rules, envelope binding — is in `docs/CONTENT_SKILLS_CONTRACT.md`.
