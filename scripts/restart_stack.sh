#!/usr/bin/env bash
# Rebuild and restart the TubeForge stack from the dev worktree. No sudo needed: Docker is available to the
# operator's user and the Claude runner is a user-level process.
#   scripts/restart_stack.sh            rebuild the image, migrate, restart web/worker/scheduler/publisher-worker and the Claude runner
#   scripts/restart_stack.sh --no-build restart only (code already built)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[ "$(basename "$ROOT")" = "tubeforge-dev" ] || { echo "run this from the dev worktree (tubeforge-dev), not $ROOT" >&2; exit 1; }
git status --short | head -5
echo "commit: $(git log -1 --oneline)"
# Scratch files go to the data disk, not a RAM-backed /tmp (docker compose build writes metadata there).
export TMPDIR="${TUBEFORGE_TMPDIR:-$HOME/tmp}"; mkdir -p "$TMPDIR"
if [ "${1:-}" != "--no-build" ]; then docker compose build web; fi
docker compose run --rm migrate
docker compose up -d web worker scheduler publisher-worker
# Claude runner. Prefer the systemd user service (it restarts on failure and, with linger enabled, survives SSH logout);
# fall back to a plain background process only when the unit is not installed.
if systemctl --user cat tubeforge-claude-runner >/dev/null 2>&1; then
  pkill -f "[t]ubeforge.host_claude_runner" || true   # a leftover hand-started runner would hold the socket
  sleep 2
  systemctl --user restart tubeforge-claude-runner
else
  pkill -f "[t]ubeforge.host_claude_runner" || true
  sleep 2
  PY="${TUBEFORGE_PYTHON:-$ROOT/../Youtube_Video_Producer/.venv-benchmark/bin/python}"
  BIN="${TUBEFORGE_CLAUDE_BIN:-$(ls "$HOME"/.vscode-server/extensions/anthropic.claude-code-*-linux-x64/resources/native-binary/claude 2>/dev/null | tail -1)}"
  mkdir -p "$ROOT/data/logs"
  TUBEFORGE_PYTHON="$PY" TUBEFORGE_CLAUDE_BIN="$BIN" nohup scripts/run_claude_runner.sh > "$ROOT/data/logs/claude-runner.out" 2>&1 &
fi
for _ in $(seq 1 30); do curl -fsS -o /dev/null http://127.0.0.1:62065/login 2>/dev/null && break; sleep 2; done
curl -fsS -o /dev/null -w "dashboard: HTTP %{http_code}\n" http://127.0.0.1:62065/login
docker compose ps --format '{{.Name}} {{.Status}}'
echo "claude runner pid: $(pgrep -f '[t]ubeforge.host_claude_runner' | head -1)"
