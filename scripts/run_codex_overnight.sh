#!/usr/bin/env bash

set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1

# NOTE:
# ROUNDS=10 means:
#   1 initial master run
#   + 10 continuation runs
#   = 11 Codex executions total.
ROUNDS="${ROUNDS:-10}"

LOG_DIR=".codex-overnight"
MASTER_PROMPT="docs/overnight/MISSION.md"

mkdir -p "$LOG_DIR"

CONTINUE_PROMPT="
Continue the TubeForge overnight mission.

First read:
- docs/overnight/MISSION.md
- docs/overnight/MASTER_PLAN.md if present
- docs/overnight/STATUS.md if present
- docs/overnight/BLOCKERS.md if present
- docs/overnight/TEST_RESULTS.md if present
- AGENTS.md if present

Inspect the actual repository state and git diff.

Do not repeat completed work.

Select the highest-priority unfinished feasible milestone and continue implementing it.

Work autonomously on safe repository-local changes.

For each milestone:
1. implement it,
2. add or update tests,
3. run relevant tests,
4. fix regressions,
5. update docs/overnight/STATUS.md,
6. update docs/overnight/BLOCKERS.md,
7. update docs/overnight/TEST_RESULTS.md,
8. continue to the next feasible milestone.

Do not stop merely because one milestone is complete.

Do not invent successful external API integrations.

If real credentials are required:
- finish everything possible with mocks,
- finish configuration and UI,
- document the exact live credential requirement,
- record the live integration test as BLOCKED,
- then continue with another feasible milestone.

Before ending this turn:
- run relevant tests,
- inspect git status,
- update the overnight documentation,
- leave the repository in a clean/resumable state.
"


# ============================================================
# NETWORK CHECK
# ============================================================

wait_for_network() {

    echo "Checking network/DNS connectivity..."

    while true; do

        if getent hosts chatgpt.com >/dev/null 2>&1; then
            echo "ChatGPT DNS lookup OK."
            return 0
        fi

        echo "$(date --iso-8601=seconds): DNS unavailable."
        echo "Retrying in 60 seconds..."

        sleep 60
    done
}


# ============================================================
# RUN CODEX WITH RETRIES
# ============================================================

run_codex() {

    local ROUND="$1"
    shift

    local NUM
    NUM="$(printf '%02d' "$ROUND")"

    local MAX_ATTEMPTS=3
    local ATTEMPT=1

    while [ "$ATTEMPT" -le "$MAX_ATTEMPTS" ]; do

        wait_for_network

        echo "--------------------------------------------"
        echo "Round $ROUND"
        echo "Attempt $ATTEMPT/$MAX_ATTEMPTS"
        echo "Started: $(date --iso-8601=seconds)"
        echo "--------------------------------------------" \
            | tee -a "$LOG_DIR/runner.log"

        "$@" \
            > "$LOG_DIR/events-$NUM.jsonl" \
            2> "$LOG_DIR/stderr-$NUM.log"

        rc=$?

        echo "Round $ROUND attempt $ATTEMPT exit=$rc at $(date --iso-8601=seconds)" \
            | tee -a "$LOG_DIR/runner.log"

        if [ "$rc" -eq 0 ]; then
            echo "Round $ROUND completed successfully." \
                | tee -a "$LOG_DIR/runner.log"

            return 0
        fi

        echo
        echo "Codex attempt failed."
        echo
        echo "----- STDERR -----"
        cat "$LOG_DIR/stderr-$NUM.log"
        echo "------------------"
        echo

        if [ "$ATTEMPT" -lt "$MAX_ATTEMPTS" ]; then
            echo "Waiting 60 seconds before retry..."
            sleep 60
        fi

        ATTEMPT=$((ATTEMPT + 1))
    done

    echo
    echo "============================================"
    echo "Round $ROUND failed after $MAX_ATTEMPTS attempts."
    echo "Stopping overnight runner."
    echo "============================================"

    return 1
}


# ============================================================
# START
# ============================================================

echo "============================================"
echo " TubeForge Codex Overnight Runner"
echo " Start: $(date --iso-8601=seconds)"
echo " Continuation rounds: $ROUNDS"
echo " Total maximum Codex runs: $((ROUNDS + 1))"
echo "============================================" \
    | tee -a "$LOG_DIR/runner.log"


# ============================================================
# INITIAL MASTER RUN
# ============================================================

echo
echo "Starting MASTER Codex run..."
echo

wait_for_network

codex --ask-for-approval never exec \
    --sandbox workspace-write \
    --json \
    --output-last-message "$LOG_DIR/final-00.md" \
    - < "$MASTER_PROMPT" \
    > "$LOG_DIR/events-00.jsonl" \
    2> "$LOG_DIR/stderr-00.log"

rc=$?

echo "Round 0 exit=$rc at $(date --iso-8601=seconds)" \
    | tee -a "$LOG_DIR/runner.log"

if [ "$rc" -ne 0 ]; then

    echo
    echo "Initial Codex run FAILED."
    echo

    cat "$LOG_DIR/stderr-00.log"

    exit "$rc"
fi

echo
echo "Initial master run completed successfully."


# ============================================================
# CONTINUATION RUNS
# ============================================================

for i in $(seq 1 "$ROUNDS"); do

    NUM="$(printf '%02d' "$i")"

    echo
    echo "============================================"
    echo " Starting continuation round $i / $ROUNDS"
    echo "============================================"

    ATTEMPT=1
    SUCCESS=0

    while [ "$ATTEMPT" -le 3 ]; do

        wait_for_network

        echo "Attempt $ATTEMPT/3"

        codex --ask-for-approval never exec \
            --sandbox workspace-write \
            --json \
            --output-last-message "$LOG_DIR/final-$NUM.md" \
            resume --last "$CONTINUE_PROMPT" \
            > "$LOG_DIR/events-$NUM.jsonl" \
            2> "$LOG_DIR/stderr-$NUM.log"

        rc=$?

        echo "Round $i attempt $ATTEMPT exit=$rc at $(date --iso-8601=seconds)" \
            | tee -a "$LOG_DIR/runner.log"

        if [ "$rc" -eq 0 ]; then
            SUCCESS=1
            break
        fi

        echo
        echo "Codex round $i attempt $ATTEMPT failed:"
        cat "$LOG_DIR/stderr-$NUM.log"

        ATTEMPT=$((ATTEMPT + 1))

        if [ "$ATTEMPT" -le 3 ]; then
            echo
            echo "Waiting 60 seconds before retry..."
            sleep 60
        fi

    done

    if [ "$SUCCESS" -ne 1 ]; then

        echo
        echo "============================================"
        echo "Codex round $i failed after 3 attempts."
        echo "Stopping rather than wasting more usage."
        echo "============================================"

        exit 1
    fi

    echo "Round $i completed successfully."

    # Give services/network a little breathing room.
    sleep 20
done


# ============================================================
# FINISHED
# ============================================================

echo
echo "============================================"
echo " TubeForge overnight run completed"
echo " End: $(date --iso-8601=seconds)"
echo "============================================" \
    | tee -a "$LOG_DIR/runner.log"
