#!/usr/bin/env bash
# Start the user-level Claude script runner (alternative to the Codex host runner).
# The worker reaches it through ./data/run/claude/claude.sock (bind-mounted at /app/data).
# Run in the foreground, or as a service:  systemctl --user enable --now tubeforge-claude-runner
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${TUBEFORGE_PYTHON:-$ROOT/.venv-benchmark/bin/python}"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
# The CLI is not on PATH: find the VS Code extension's bundled binary when the service or caller did not set it.
if [ -z "${TUBEFORGE_CLAUDE_BIN:-}" ]; then
  TUBEFORGE_CLAUDE_BIN="$(ls "$HOME"/.vscode-server/extensions/anthropic.claude-code-*-linux-x64/resources/native-binary/claude 2>/dev/null | tail -1 || true)"
  export TUBEFORGE_CLAUDE_BIN
fi
exec "$PY" -m tubeforge.host_claude_runner
