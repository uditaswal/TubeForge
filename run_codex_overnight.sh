#!/usr/bin/env bash
# Compatibility entry point for existing local cron invocations.
set -Eeuo pipefail
exec bash "$(dirname "${BASH_SOURCE[0]}")/scripts/run_codex_overnight.sh" "$@"
