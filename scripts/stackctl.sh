#!/usr/bin/env bash
# Choose what the worker does, so one render kind never competes with the other for memory.
#   scripts/stackctl.sh clips    the worker takes only clip jobs; Shorts stay queued
#   scripts/stackctl.sh shorts   the worker takes only Shorts; clip jobs stay queued
#   scripts/stackctl.sh all      the worker takes everything (default)
#   scripts/stackctl.sh status   show the mode and the queue
# The dashboard stays up in every mode. A render in progress finishes before the worker restarts.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mode="${1:-status}"
case "$mode" in
  clips|shorts|all)
    TUBEFORGE_WORKER_MODES="$mode" docker compose up -d --no-deps worker
    echo "worker mode: $mode" ;;
  status)
    docker compose ps --format '{{.Name}} {{.Status}}' worker web
    docker compose exec -T worker printenv TUBEFORGE_WORKER_MODES | sed 's/^/worker mode: /' || true ;;
  *) echo "usage: $0 clips|shorts|all|status" >&2; exit 2 ;;
esac
