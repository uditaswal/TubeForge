#!/usr/bin/env bash
set -Eeuo pipefail

# Run from the TubeForge repository root.
# Keep this session persistent; do NOT use --ephemeral because we resume it.

PROMPT_FILE="${PROMPT_FILE:-CODEX_OVERNIGHT_TUBEFORGE.md}"
ROUNDS="${ROUNDS:-10}"
SLEEP_SECONDS="${SLEEP_SECONDS:-20}"
LOG_DIR="${LOG_DIR:-.codex-overnight}"

mkdir -p "$LOG_DIR"

if [[ ! -f "$PROMPT_FILE" ]]; then
  echo "Prompt file not found: $PROMPT_FILE" >&2
  exit 1
fi

printf 'Starting TubeForge overnight Codex run at %s\n' "$(date -Is)" | tee -a "$LOG_DIR/runner.log"

# First long turn.
# workspace-write keeps Codex bounded to the repo/workspace.
# 'never' avoids waiting for a human approval overnight. It does NOT magically
# grant network access; configure sandbox_workspace_write.network_access=true
# separately if you intentionally want network access.
set +e
codex exec \
  --sandbox workspace-write \
  --ask-for-approval never \
  --json \
  --output-last-message "$LOG_DIR/final-00.md" \
  - < "$PROMPT_FILE" \
  > "$LOG_DIR/events-00.jsonl" 2> "$LOG_DIR/stderr-00.log"
rc=$?
set -e
printf 'Round 0 exit=%s at %s\n' "$rc" "$(date -Is)" | tee -a "$LOG_DIR/runner.log"

for ((i=1; i<=ROUNDS; i++)); do
  printf 'Starting continuation round %s at %s\n' "$i" "$(date -Is)" | tee -a "$LOG_DIR/runner.log"

  CONTINUE_PROMPT=$(cat <<'PROMPT'
Continue the TubeForge overnight mission autonomously.

First read `docs/overnight/STATUS.md`, `MASTER_PLAN.md`, `BLOCKERS.md`, `TEST_RESULTS.md`, current git diff/status, and the previous work from this session. Do NOT repeat completed work.

Pick the highest-priority unfinished, non-blocked milestone that improves the working vertical slice. Implement it fully, run focused tests, fix failures, update the overnight status/docs, and commit if safe. Then continue to the next useful task within this turn.

Do not stop for routine questions. Do not perform destructive external actions or real social-media publication. If an external credential/approval blocks a live test, record it and continue with implementation/tests/docs that do not require the credential.

If every meaningful milestone in the master plan is either DONE or genuinely BLOCKED, run the broadest safe verification you can, update the final status, and state `OVERNIGHT_MISSION_COMPLETE` in your final message.
PROMPT
)

  set +e
  codex exec \
    --sandbox workspace-write \
    --ask-for-approval never \
    --json \
    --output-last-message "$LOG_DIR/final-$(printf '%02d' "$i").md" \
    resume --last "$CONTINUE_PROMPT" \
    > "$LOG_DIR/events-$(printf '%02d' "$i").jsonl" \
    2> "$LOG_DIR/stderr-$(printf '%02d' "$i").log"
  rc=$?
  set -e

  printf 'Round %s exit=%s at %s\n' "$i" "$rc" "$(date -Is)" | tee -a "$LOG_DIR/runner.log"

  if grep -q 'OVERNIGHT_MISSION_COMPLETE' "$LOG_DIR/final-$(printf '%02d' "$i").md" 2>/dev/null; then
    printf 'Mission reported complete after round %s.\n' "$i" | tee -a "$LOG_DIR/runner.log"
    break
  fi

  sleep "$SLEEP_SECONDS"
done

printf 'Overnight runner finished at %s\n' "$(date -Is)" | tee -a "$LOG_DIR/runner.log"

