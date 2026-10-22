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
- Python with the renderer deps: `.venv-benchmark/bin/python`.
- Before stopping or near your token limit: commit at a green checkpoint and update the
  "Next step" section of `docs/HANDOFF.md` with a concrete file/command.
