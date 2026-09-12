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

## Dashboard UI contract

Treat the Creator Studio dashboard, login page, and their HTTP APIs as one
operator workflow. When a change affects an operator-visible capability,
update the UI in the same change whenever it is exposed through the dashboard.

- Do not add a dashboard control unless it invokes a real, tested API action
  and reports success, pending, disabled, and failure states truthfully.
- Do not add or change a dashboard API workflow without considering its
  corresponding UI state, labels, permissions, loading/empty/error treatment,
  mobile layout, and activity/audit visibility.
- Keep background refresh silent after initial load: preserve visible data and
  open dialogs instead of replacing them with a loading screen or flickering.
- Keep reviews explicit and safe: edits/revisions require a new approval of
  the exact reviewed artifact; never imply that an approval, deletion, render,
  publication, or AI revision completed before the durable backend confirms it.
- Preserve the Studio’s dark navy visual system, readable hierarchy, keyboard
  accessibility, and responsive desktop/tablet/mobile behavior. Reuse existing
  components and styles where practical.
- Add or update focused API/UI tests for changed workflows, and update
  `readme.md` when an operator-visible flow, login behavior, or dashboard URL
  changes.

### Development dashboard URL

`http://127.0.0.1:62065` is the sole documented developer dashboard URL.
Compose must bind it to loopback only. Do not document or reserve additional
host ports for the dashboard; application-preview proxy ports are transient
tooling URLs and are not part of TubeForge configuration.

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
9. the Dashboard UI contract has been applied and its focused workflow tests
   pass whenever an operator-visible capability changed

When validation fails, continue debugging.
