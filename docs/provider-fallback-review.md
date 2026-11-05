# Track E review

Branch: `codex/provider-fallback`. Approved contract: `provider-fallback-contract.md`.
Only stub runners were used. No live generation, paid calls, publishing, remote
pushes, or merges occurred.

## Durable policy checkpoint

Saved Studio defaults have append-only actor/time audit history and revision
conflicts. Manual, batch and scheduled jobs inherit them when submitted. Existing
jobs retain their request across policy changes and process restarts. Migration
`20261105_0032` adds the policy history table. Auth/CSRF and disabled-mode cases
are covered. Initial acceptance: 30 policy/batch tests plus five migration tests.

## Router checkpoint

Rebased onto Claude's `7d19e7c` before integration. No edits to the Claude runner
or its protocol error-code definitions.

- Single modes contact only their selected writer. Automatic routing tries the
  preferred writer and then the other enabled writer once, only for structured
  `quota_exhausted` / `runner_unavailable` signals. Missing/refused sockets map
  to availability; timeouts retain retry semantics without fallback.
- Authentication, legacy `unavailable`, invalid output, grounding/craft rejection,
  exhausted allowance, timeout and cancellation never trigger fallback.
- Shared allowance consumption is serialized over the exact normalized source
  packet across owner/model choices, including existing counters. No counters
  are rewritten or reset. Accepted routing receipts replay locally after restart;
  a failed fallback is terminal for that routing policy and preserves both
  redacted failure categories instead of cycling back.
- Each accepted package contains application-owned routing evidence, actual
  provider, usage and fallback reasons. The pipeline persists that evidence and
  records Activity; job-list data exposes the actual route. Routing metadata is
  excluded from writer schemas. Existing grounding/creative validation still runs.
- Research stays on the preferred owner; the router never repeats it on fallback.
  Known runner limitation: unstructured CLI quota messages still arrive as
  `invalid_output`, and are deliberately ineligible for fallback.

Validation with `PYTHONPATH=src .venv-benchmark/bin/python -m pytest -q`:
`tests/test_provider_fallback.py tests/test_provider_routing_api.py tests/test_host_codex_runner.py tests/test_codex_content.py tests/test_runner_failure_codes.py tests/test_script_owner.py tests/test_migrations.py`
— 89 passed before the final cancellation preflight case; the five-case preflight
check then passed. A stubbed pipeline reached exact-script review, persisted
package/usage/Activity, and resumed after app restart without runner calls.
Concurrent owners could not both consume the last allowance.

The historical caption-timing source fixture remains unchanged; its test now
checks the captured excerpt hash instead of comparing it with today's README.
The factory test checks the host adapter inside its new router.

## Remaining acceptance

Dashboard mode controls and signed-in desktop/mobile browser inspection are the
next checkpoint. No production video or live provider behavior is claimed verified.
