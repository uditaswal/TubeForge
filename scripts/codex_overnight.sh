#!/usr/bin/env bash

set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1

LOG_DIR="$ROOT/autonomous_logs"
mkdir -p "$LOG_DIR"

MAX_ITERATIONS=30
SLEEP_SECONDS=30

echo "================================================"
echo " TubeForge Codex Overnight Supervisor"
echo " Root: $ROOT"
echo " Started: $(date)"
echo "================================================"

for ((i=1; i<=MAX_ITERATIONS; i++)); do

    TS="$(date +%Y%m%d_%H%M%S)"
    LOG="$LOG_DIR/codex_${i}_${TS}.log"

    echo
    echo "================================================"
    echo " ITERATION $i / $MAX_ITERATIONS"
    echo " $(date)"
    echo " Log: $LOG"
    echo "================================================"

    PROMPT=$(cat <<'EOF'
Continue the autonomous TubeForge task described in OVERNIGHT_MISSION.md.

First read:

- AGENTS.md
- OVERNIGHT_MISSION.md
- AUTONOMOUS_PROGRESS.md if it exists
- current git diff/status
- relevant source and tests

You are one iteration of an overnight autonomous engineering loop.

Your job is to make concrete progress toward satisfying EVERY acceptance
criterion in OVERNIGHT_MISSION.md.

Do not merely explain what should be done.

Inspect the repository, edit the implementation, add/fix tests, and run
appropriate validation yourself.

If previous work is partially complete, continue from it.

If previous validation failed, diagnose the actual root cause and fix it.

Do not undo working changes from previous iterations merely to redesign them.

Before finishing this iteration:

1. run relevant tests
2. perform whatever validation is currently possible
3. update AUTONOMOUS_PROGRESS.md with:
   - work completed
   - current failures
   - next required action
   - commands/tests run
4. If and only if ALL acceptance criteria are genuinely satisfied and the
   real smoke video was successfully generated and validated, create:

   .autonomous_success

Do NOT create .autonomous_success based only on unit tests or mocks.

Continue working until you either make meaningful progress or encounter a
genuine blocker that cannot be solved locally.
EOF
)

    codex exec "$PROMPT" 2>&1 | tee "$LOG"

    CODEX_EXIT=${PIPESTATUS[0]}

    echo "Codex exit code: $CODEX_EXIT"

    if [ -f ".autonomous_success" ]; then
        echo
        echo "================================================"
        echo " SUCCESS MARKER FOUND"
        echo " Running independent supervisor validation..."
        echo "================================================"

        # Independent sanity validation.
        # Change/add commands here as the project evolves.

        docker compose ps

        if [ -d "tests" ]; then
            python3 -m pytest -q 2>&1 | tee "$LOG_DIR/final_pytest_${TS}.log"
            TEST_EXIT=${PIPESTATUS[0]}
        else
            TEST_EXIT=1
        fi

        if [ "$TEST_EXIT" -eq 0 ]; then
            echo
            echo "================================================"
            echo " OVERNIGHT MISSION PASSED"
            echo " Finished: $(date)"
            echo "================================================"
            exit 0
        fi

        echo "Independent validation FAILED."
        echo "Removing false success marker and continuing."
        rm -f .autonomous_success
    fi

    if [ "$CODEX_EXIT" -ne 0 ]; then
        echo "Codex invocation failed."
        echo "Will retry after $SLEEP_SECONDS seconds."
    fi

    sleep "$SLEEP_SECONDS"
done

echo
echo "================================================"
echo " Maximum iterations reached."
echo " Review AUTONOMOUS_PROGRESS.md and autonomous_logs/"
echo "================================================"

exit 1
