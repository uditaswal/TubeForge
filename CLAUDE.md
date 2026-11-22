# TubeForge — Claude Code entry point

@docs/HANDOFF.md
@AGENTS.md

Claude-specific notes:

- Claude CLI is not on PATH: `/home/uditaswal/.vscode-server/extensions/anthropic.claude-code-*-linux-x64/resources/native-binary/claude`
  (the production runner resolves it from `TUBEFORGE_CLAUDE_BIN`).
- Claude Code's worktree feature names branches `claude/…`: rename to `feat/…` (or another allowed type) before
  committing — the hook rejects `claude/` and `codex/`.
- UI work: invoke the `frontend-design` (or `impeccable`) skill before editing, and Read your own screenshots.
- Before stopping: commit at a green checkpoint and update HANDOFF "Open" / "Next command".
- **Cloud session (claude.ai/code) = isolated sandbox with its own clone, not the operator's machine.** Restarts there
  don't reach the operator's dashboard and commits exist only locally until pushed (push only on request). If the
  operator says "I don't see the change", check this first, then give them the exact `git fetch`/`merge`/
  `scripts/restart_stack.sh` commands.
