#!/usr/bin/env bash
# Example invocation for an isolated fake-provider stack with auth disabled.
set -Eeuo pipefail
BASE_URL=http://127.0.0.1:62065 \
ACTOR=offline-smoke-test \
TARGET_DURATION_SECONDS=30 \
bash scripts/test_offline_workflow.sh
