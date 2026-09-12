# TubeForge autonomous development rules

You are developing TubeForge, an automated YouTube-video generation system.

## Project records

These files have distinct purposes. Keep them consistent rather than copying
the same status into each one:

- `AGENTS.md` is the durable working contract: safety rules, required checks,
  and documentation-update rules. Do not put milestone history here.
- `docs/STATUS.md` is the single source of truth for the *current* release,
  milestone state, blockers, and next five tasks.
- `AUTONOMOUS_PROGRESS.md` is an append-only evidence log. Each meaningful
  autonomous work session records its scope, validation commands/results,
  artifacts inspected, blocker (if any), and next action.
- `readme.md` is the operator-facing product, setup, and local-operation guide.
  Update it whenever supported setup, configuration, or workflow changes.

Do not claim a milestone is complete in `AUTONOMOUS_PROGRESS.md` unless its
corresponding row is `DONE` in `docs/STATUS.md` with validation evidence.

## Working policy

For requested implementation work:

- Inspect the existing architecture before changing anything.
- Implement the requested milestone completely.
- Run relevant tests after every meaningful change.
- Diagnose failures and fix them rather than merely reporting them.
- Do not claim completion until validation passes.
- Preserve existing reliability guarantees including:
  - worker leases
  - ownership fencing
  - checkpoint/restart safety
  - atomic artifact promotion
  - cancellation handling

## Repository hygiene

Before every commit (including autonomous commits), review `git status --short`
and whether the change introduced generated, machine-local, or sensitive files.
Update `.gitignore` in the same change whenever a new ignorable path is
introduced. This includes generated media/artifacts, model weights and caches,
local databases, logs, virtual environments, build/test output, credentials,
and editor/OS files.

- Use `git check-ignore -v <path>` to verify a new ignore rule when practical.
- Do not use broad ignore rules that hide source, migrations, fixtures, or
  intentionally versioned configuration.
- Never remove already tracked files merely to make an ignore rule take effect;
  flag that decision for the operator.

## Allowed autonomous actions

You may without asking:

- inspect repository files
- edit source code
- add tests
- install Python packages inside the project environment when necessary
- run pytest
- run Docker Compose commands for this project
- inspect project Docker logs
- run FFmpeg/ffprobe
- create temporary test artifacts
- modify local TubeForge configuration required for tests

## Do not

- delete unrelated user files
- alter host networking/firewall
- expose secrets
- push to remote Git repositories
- publish anything to YouTube
- use paid external APIs
- modify unrelated Docker workloads
- run destructive database operations against anything except the TubeForge test/local database

## Definition of done

"Implemented" is not done.

Completion requires:

1. relevant automated tests pass
2. existing tests remain passing
3. the requested end-to-end smoke test passes
4. produced artifacts are inspected/validated
5. important findings are appended to `AUTONOMOUS_PROGRESS.md`
6. `docs/STATUS.md` is updated with the current state, evidence, blocker, and
   next action
7. `readme.md` and the relevant operator documentation are updated when the
   externally visible setup or workflow changed
8. `.gitignore` has been reviewed and updated when the change introduced
   generated, local, or sensitive paths

When validation fails, continue debugging.
