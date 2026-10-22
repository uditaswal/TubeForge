#!/usr/bin/env bash
# Start the user-level Claude script runner (alternative to the Codex host runner).
# The worker reaches it through ./data/run/claude/claude.sock (bind-mounted at /app/data).
# Run in the foreground, or as a service:  systemctl --user enable --now tubeforge-claude-runner
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${TUBEFORGE_PYTHON:-$ROOT/.venv-benchmark/bin/python}"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
exec "$PY" -m tubeforge.host_claude_runner
