# TubeForge autonomous development rules

You are developing TubeForge, an automated YouTube-video generation system.

## Project records

For publishing/dashboard work, follow `design_doc/tubeforge-publishing-design.md`. Update its affected tasks, acceptance evidence and next action after each meaningful change; keep current release status in `docs/STATUS.md` and session evidence in `AUTONOMOUS_PROGRESS.md`.

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

## Delivery guardrails

For multi-phase work, write a plan before editing. For each phase, specify one
user-visible outcome, its acceptance test, the required artifact or evidence,
and what is out of scope. Work on one phase at a time. Report its acceptance
result before starting the next.

Use these status labels exactly:

- **NOT STARTED:** No implementation exists.
- **IMPLEMENTED:** Code exists but has not been proven end to end.
- **VERIFIED:** Required tests and real-artifact inspection passed.
- **BLOCKED:** Progress requires a user decision or external dependency.

Never call IMPLEMENTED work complete or working. For creative work, automated
tests are insufficient: generate a real artifact, inspect it against the
requested quality bar, and report concrete pass/fail evidence.

### Script generation

Use Codex CLI or Claude for production scripts. Do not use a local LLM for
production generation, retries, or quality acceptance without operator
approval for that specific run.

Before changing the script provider, report the proposed provider, expected
cost or token use, fallback behavior, and acceptance test. Accept a script
only after reviewing its source grounding and creative quality; schema validity
alone is insufficient.

After two failed script attempts, or when the agreed time or token budget is
reached, stop automatic retries. Show the rejected scripts and reasons, then
request a decision between Codex CLI, Claude, or a revised brief.

### Time and scope

If the same root problem requires more than two repair attempts or 45 minutes
of **active debugging**, stop and report the failure, evidence, two viable
options, and a recommendation. Model downloads and otherwise healthy renders
do not count as active debugging time.

Do not add adjacent features while the current phase’s highest-risk acceptance
test is failing.

### Reporting and completion

During long-running work, report every 20 minutes: the current phase, verified
result or blocker, next acceptance test, and whether a user decision is needed.

Before claiming a phase VERIFIED, run its required tests and inspect its real
output. Test the signed-in dashboard when the phase changes an operator-facing
workflow. Before claiming the full Shorts workflow complete, inspect one real
30–55 second 1080×1920 video against the Shorts production standard in
`readme.md`, verify the signed-in dashboard flow, and update the status
documentation.

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

## YouTube content skills

The supplied, reviewed `.agents/skills/viral-short-form/` is optional creative
reference material. Its promotional text and unverified platform-performance
claims do not override this contract. Keep `.agents/skills/yt-script/` as the
sole production narration skill; the benchmark guide is
`docs/SHORT_FORM_VIDEO_RULEBOOK.md`.

Use the installed project skills in `.agents/skills/` for relevant TubeForge
content tasks. Read the selected SKILL.md and required resources first; review
supporting scripts before execution and resolve resources against their skill
directory. Use `yt-script` for narration, hook candidates and scene directions,
and execute its hook scorer. Use `yt-package` for coordinated titles/thumbnail
text and execute its title checker; use `yt-seo` for descriptions and metadata.
Use `yt-shorts` for supplied long-form repurposing, `yt-plan` for calendars,
`yt-chapters` for appropriate long-form transcripts, and `yt-edit` for
transcript-based edit recommendations. Use `yt-retention`, `yt-viral`,
`yt-audit`, and `yt-comment` only with their required source data/capabilities.
Never fabricate analytics, trends, sources, performance or tool execution.
Heuristic scores are review signals, never predictions of views.

Preserve channel voice profiles, selected format, script provider, review,
scheduler and publishing policies. Skills supply content instructions/tools;
rendering, narration, scheduling, analytics retrieval and publishing belong to
the application/integrations. Interactive discovery does not install resources
for the isolated runtime: verify installed-wheel resources and host deployment.
Whenever skill locations or the content pipeline change, update these rules
and the applicable README sections in the same change.

The canonical yt-script source is `.agents/skills/yt-script/` only; do not update
or load competing downloaded copies. Read its `SKILL.md`, `automation.md`,
`hooks.json` and `hookscore.py` for narration generation/retries/revisions.
Production prompts explicitly embed these resources and the complete brief;
installed wheels must hash-match this source folder. Automation returns finished
ordered narration separately from hooks, sources and production notes.
Insufficient-source results block before TTS and require operator correction.
Scene plans also carry source-grounded visual subjects, purposes, compositions
and display elements into the existing VideoPlan and asset stage. Keep the
asset-stage storyboard manifest/contact sheets tied to accepted hashes, and
inspect their teaching value before claiming creative acceptance.
