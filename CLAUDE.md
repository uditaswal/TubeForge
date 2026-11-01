# TubeForge — Claude Code entry point

Read these first, in order:

@docs/HANDOFF.md
@AGENTS.md

`docs/HANDOFF.md` is the current phase, next step and open decisions shared with Codex.
`AGENTS.md` is the durable rules/safety contract. Do not read `AUTONOMOUS_PROGRESS.md`
(476 KB log) or the full design doc unless the handoff tells you to.

Claude-specific notes:

- The Claude CLI binary is not on PATH. Use
  `/home/uditaswal/.vscode-server/extensions/anthropic.claude-code-*-linux-x64/resources/native-binary/claude`
  (the production runner resolves it from `TUBEFORGE_CLAUDE_BIN`).
- Judge video work by **looking at frames** (FFmpeg contact sheet + Read on the PNG),
  not by test results alone.
- Before reporting a video job done run `python .agents/skills/om-video-quality/qa_check.py data/artifacts/<job_id>` (checklist in `.agents/skills/om-video-quality/SKILL.md`).
- Python with the renderer deps: `.venv-benchmark/bin/python`.
- Before stopping or near your token limit: commit at a green checkpoint and update the
  "Next step" section of `docs/HANDOFF.md` with a concrete file/command.
- **A cloud/remote Claude Code session (claude.ai/code, "remote execution environment") runs
  in an isolated sandbox with its own fresh clone — it is not the operator's machine.**
  `docker compose`, `scripts/restart_stack.sh`, etc. run there only act on that sandbox's own
  throwaway stack; they do **not** restart or affect the dashboard the operator reaches over
  their SSH tunnel. Commits made in such a session only exist in that sandbox's local branch
  until explicitly pushed (never push without asking first — see `AGENTS.md`). If the operator
  reports "I don't see the change" after you "restarted" something, check first whether you are
  in a remote/cloud session (`pwd`/environment banner) before debugging caching or deployment —
  the actual cause is usually that the operator's machine never received the commit. Push only
  on request, then give the operator the exact `git fetch`/`merge`/`restart_stack.sh` commands
  to run themselves.
