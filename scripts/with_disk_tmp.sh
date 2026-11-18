#!/usr/bin/env bash
# Run any command with its scratch files on the data disk instead of a RAM-backed /tmp:
#   scripts/with_disk_tmp.sh pytest -q tests/...      scripts/with_disk_tmp.sh pip install ...
# Keep the folder path short (browser profile sockets have a path-length limit).
set -euo pipefail
export TMPDIR="${TUBEFORGE_TMPDIR:-$HOME/tmp}"
mkdir -p "$TMPDIR"
exec "$@"
