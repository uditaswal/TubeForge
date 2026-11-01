#!/usr/bin/env bash
# Rebuild and restart the TubeForge stack from the dev worktree. No sudo needed: Docker is available to the
# operator's user and the Claude runner is a user-level process.
#   scripts/restart_stack.sh            rebuild the image, migrate, restart web/worker/scheduler and the Claude runner
#   scripts/restart_stack.sh --no-build restart only (code already built)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[ "$(basename "$ROOT")" = "tubeforge-dev" ] || { echo "run this from the dev worktree (tubeforge-dev), not $ROOT" >&2; exit 1; }
git status --short | head -5
echo "commit: $(git log -1 --oneline)"
if [ "${1:-}" != "--no-build" ]; then docker compose build web; fi
docker compose run --rm migrate
docker compose up -d web worker scheduler
# Claude runner: stop any running one, then start it from this tree (spend limits come from TUBEFORGE_CLAUDE_* env).
pkill -f "[t]ubeforge.host_claude_runner" || true
sleep 2
PY="${TUBEFORGE_PYTHON:-$ROOT/../Youtube_Video_Producer/.venv-benchmark/bin/python}"
BIN="${TUBEFORGE_CLAUDE_BIN:-$(ls "$HOME"/.vscode-server/extensions/anthropic.claude-code-*-linux-x64/resources/native-binary/claude 2>/dev/null | tail -1)}"
mkdir -p "$ROOT/data/logs"
TUBEFORGE_PYTHON="$PY" TUBEFORGE_CLAUDE_BIN="$BIN" nohup scripts/run_claude_runner.sh > "$ROOT/data/logs/claude-runner.out" 2>&1 &
for _ in $(seq 1 30); do curl -fsS -o /dev/null http://127.0.0.1:62065/login 2>/dev/null && break; sleep 2; done
curl -fsS -o /dev/null -w "dashboard: HTTP %{http_code}\n" http://127.0.0.1:62065/login
docker compose ps --format '{{.Name}} {{.Status}}'
echo "claude runner pid: $(pgrep -f '[t]ubeforge.host_claude_runner' | head -1)"
