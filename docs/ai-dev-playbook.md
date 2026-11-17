# AI-driven development playbook

Lessons from TubeForge (Oct–Nov 2026), written to reuse when starting a new project with Claude Code, Codex or
similar agents. The numbers come from this repo's own history.

## What went wrong here (evidence)

| Symptom | Evidence | Cost |
|---|---|---|
| Agents spent their turns on paperwork | 128 of 349 commits (37%) touched no `src/` or `tests/`; `docs/HANDOFF.md` was changed in 181 commits, more than any code file | Roughly a third of agent time went into describing work |
| Heavy context at every session start | `CLAUDE.md` auto-loaded HANDOFF (18 KB) + AGENTS (10.5 KB) ≈ 7–8k tokens before any work | Less room for the actual code; slower, costlier runs |
| Write-only log | ~200 KB `AUTONOMOUS_PROGRESS.md` + archives, with reading deny-listed | Pure cost: written every run, read by nobody |
| "Done" meant updating 6+ records | design doc, progress log, readme, HANDOFF, status section, `.gitignore` | Every task ended in a documentation pass |
| Rules repeated in chat were ignored | "No `claude/`/`codex/` branches" was never written anywhere; HANDOFF even used those names as examples, and tool worktrees create them by default | The same correction, repeatedly |
| Poor UI despite design skills installed | ~400 KB of HTML/CSS/JS inside Python strings, no design tokens, no rule to load a design skill or look at screenshots | Skills never triggered; agents couldn't see what they built |
| Too many fronts for one person | Shorts, long-form, YouTube + Instagram, scheduling, batch, clips, provider fallback, Docker seccomp — nothing published after two months; most next steps waiting on the operator | Progress bottlenecked on approvals and context switching |

## Good practices worth keeping

- **A real test suite** and committing at every green checkpoint.
- **Mechanical guards** for things that must never happen: gitleaks, no attribution trailers, no generated files, a read-deny list for big/binary paths.
- **Judging creative output by looking at it** (frame contact sheets, screenshots) plus a QA script, not by tests alone.
- **Hard spend caps** and a bounded retry allowance for paid model calls.
- **Honest status labels** (NOT STARTED / IMPLEMENTED / VERIFIED / BLOCKED).
- **One agent per branch**, worktrees per feature, nothing on `main` without approval, never auto-publish.

## Rules for the next project

### 1. Scope
- **One user-visible goal at a time** ("publish one Short a day"), written at the top of HANDOFF. Everything else goes in an explicit **Frozen** list.
- Ship the thinnest end-to-end path first (input → output → delivered), then deepen. Don't build the second platform before the first works live.
- Give agents a **standing budget** ("up to N model calls / $X a day for testing") instead of a go-ahead per call, so work doesn't park waiting on you.
- Clear your approval queue in one batch a day.

### 2. Agent instructions
- **Instruction files hold rules, never status.** Status goes in one place (HANDOFF), history goes in git.
- **Size limits, written in the files themselves:** `AGENTS.md` ≤ 6 KB, `HANDOFF.md` ≤ 60 lines, `CLAUDE.md` ≤ 1 KB plus includes. Contracts and designs live in `docs/` and are linked, not inlined.
- **No progress logs.** Commit messages are the log: what changed + how it was validated.
- **Definition of done ≤ 4 items:** tests pass; artifact/screenshot inspected; HANDOFF updated; user docs only if a user-visible workflow changed.
- **If you've said a rule twice in chat, it goes in the file and, if possible, a hook.** Chat doesn't persist between sessions.

### 3. Guardrails: hooks over prose
- Anything that must *never* happen gets a hook or a CI check: secrets, branch names, attribution trailers, generated files, forbidden imports (a boundary test).
- Prose rules are for judgement calls only. Delete prose rules nobody can check (e.g. "report every 20 minutes").
- Every prose rule costs context in every session, so keep the list short enough to actually be followed.

### 4. Branches
- Names are `<type>/<topic>` (`feat/`, `fix/`, `chore/`, `docs/`, `exp/`), **never the tool's name**. Enforce with a hook (template below), because Claude Code and Codex create `claude/…` and `codex/…` worktree branches by default.
- One front = one agent. Two agents on overlapping files produce reconciliation branches that are pure overhead.

### 5. UI
- Never write UI as strings inside backend code. Use real `templates/` + `static/` files from day one.
- Create `DESIGN.md` (tokens: colour, type scale, spacing, radius) **before** the first screen; do one deliberate design pass, not patch fixes.
- Instruction file rule: *"For any UI change load the `frontend-design`/`impeccable` skill, then screenshot at 390/768/1440 px and look at it."* Skills trigger on how the task reads; a task that reads as "edit `batch_ui.py`" won't trigger a design skill unless you say so.
- Make sure the browser tool (Playwright) actually works in the agent environment before relying on it.

### 6. Skills
- Install few, and **name them in the instruction file next to the task they serve** (UI → design skill, video → QA skill). An installed but unnamed skill is mostly invisible.
- Prefer skills that ship a runnable checker (like `qa_check.py`) over prose-only skills.

## Starter templates

### `AGENTS.md` (skeleton)
```markdown
# <Project> agent rules
Rules only; status is in docs/HANDOFF.md. Hook-enforced rules are listed once.

## Never
- Commit on main / push / publish / call paid APIs without explicit approval.
## Allowed without asking
- Edit source, add tests, install deps in the project env, run tests and local services.
## Branches (hook: scripts/check_branch_name.sh)
- <type>/<topic>; never claude/ or codex/.
## Working
- Plan multi-step work first; test after each coherent stage; stop after 2 failed fixes and report options.
## UI
- Load the frontend-design skill; follow DESIGN.md; screenshot at 390/768/1440 px before calling it done.
## Done
1. Tests pass. 2. Artifact/screenshot inspected. 3. HANDOFF updated. 4. User docs if a workflow changed.
```

### `docs/HANDOFF.md` (skeleton, ≤ 60 lines)
```markdown
# HANDOFF
## Goal            (one sentence)
## Current focus   (one item)
## Open            (status label — next action — link)
## Frozen          (one line)
## Next command    (exact command)
## Gotchas         (≤ 6 bullets)
```

### `CLAUDE.md`
```markdown
@docs/HANDOFF.md
@AGENTS.md
- Tool worktrees create claude/… branches: rename before committing.
- UI work: invoke the frontend-design skill first; Read your screenshots.
```

### Branch-name hook
Copy `scripts/check_branch_name.sh` and add to `.pre-commit-config.yaml`:
```yaml
default_install_hook_types: [pre-commit, commit-msg, pre-push]
repos:
  - repo: local
    hooks:
      - id: branch-name
        name: reject branches named after an AI tool
        language: script
        entry: scripts/check_branch_name.sh
        pass_filenames: false
        always_run: true
        stages: [pre-commit, pre-push]
```
Then run `pre-commit install` once per clone.

## Day-one checklist
1. Write the one-sentence goal and the thinnest end-to-end path.
2. `AGENTS.md`, `HANDOFF.md`, `CLAUDE.md` from the templates above, within their size limits.
3. Hooks: gitleaks, branch names, attribution trailers, large/generated files; `pre-commit install`.
4. `.gitignore` for media, models, DBs, logs, venvs; a read-deny list in `.claude/settings.json` for the same paths.
5. For a UI: a `DESIGN.md` and a `templates/`+`static/` layout before the first screen.
6. A standing spend budget for model calls.
7. A weekly check: share of commits touching code vs docs; HANDOFF line count; branches named after tools (`git branch | grep -E '^ *(claude|codex)/'`).
