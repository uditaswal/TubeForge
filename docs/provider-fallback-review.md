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

## Dashboard acceptance — VERIFIED (local stub scope)

Rebased onto `dev` at `04ab27b`, including Claude's `ab12d63` parser fix. The
saved UI candidate was restored; no new repair allowance or production script
allowance was reset. The previous inline-script blocker is resolved upstream.

Final focused command (using `PYTHONPATH=src .venv-benchmark/bin/python -m pytest -q`):

```
tests/test_provider_fallback.py tests/test_provider_routing_api.py
tests/test_script_routing_ui.py tests/test_host_codex_runner.py
tests/test_codex_content.py tests/test_runner_failure_codes.py
tests/test_script_owner.py tests/test_migrations.py tests/test_batch_queue.py
tests/test_batch_automation.py
tests/test_api_workflow.py::test_every_inline_dashboard_script_parses
tests/test_api_workflow.py::test_dashboard_shows_signed_in_user_copy_script_and_markdown_mode_controls
tests/test_api_workflow.py::test_video_brief_uses_defaults_and_persists_user_options
tests/test_api_workflow.py::test_studio_brief_preserves_separate_angle_and_exact_multi_source_cache_request
tests/test_pipeline_orchestrator.py::test_ownership_loss_during_content_generation_cannot_promote_checkpoint_or_state
tests/test_pipeline_orchestrator.py::test_topic_research_checkpoint_survives_restart_without_regeneration
```

Result: **121 passed**; five existing Starlette 422-name deprecation warnings.
The syntax gate and asynchronous form-reset/policy-restoration regression pass.
A failed or unconfirmed save preserves the form and requires a reload; saves
carry actor/time audit information and stale revisions return a conflict.

Isolated signed-in Chromium verification passed: real policy API save; disabled
writer filtering; stale conflict and reload; preserved unsaved form; automatic
primary selection inherited by a newly queued job; actual fallback writer on the
Generations card. Desktop 1280×900, tablet 768×1024 and mobile 390×844 had no
horizontal overflow or JavaScript exceptions. Desktop/mobile captures and actual
writer capture were inspected. Local evidence: `artifacts/review/provider-fallback-20261105/`.
Impeccable mechanical detection returned no findings for the mode editor.

The browser used an isolated temporary database and stubbed runners. Package,
usage and Activity were inspected at script review; no production approvals,
publication, live provider calls or full video acceptance occurred. Older jobs
keep their original routing choices. The historical caption-timing fixture is
unchanged, and its existing README mismatch is addressed by snapshot-hash
verification rather than changing the immutable source packet.

## Requested recheck — VERIFIED (5 November 2026, local stub scope)

Tested branch head `7f90f80`. `dev` remains at `04ab27b`, containing the inline
script escape fix `ab12d63`. The working tree was clean and `git rebase dev`
returned `Current branch codex/provider-fallback is up to date.` No commits
needed replaying and no stash was reapplied.

```sh
PYTHONPATH=src .venv-benchmark/bin/python -m pytest -q \
 tests/test_api_workflow.py::test_every_inline_dashboard_script_parses \
 tests/test_provider_routing_api.py tests/test_script_routing_ui.py
```

Result: **14 passed**, one existing Starlette 422-name deprecation warning.
The inline-script parse test passes; Chromium reported no SyntaxError or other
page exceptions, so there is no failing script index/Node syntax output to report.

Fresh signed-in Chromium check used an isolated temporary database and stub
runners. It passed desktop 1280×900, tablet 768×1024 and mobile 390×844 checks,
with no horizontal overflow. Actual API actions covered Codex only, Claude only
and automatic fallback; save/conflict/reload, form preservation, filtered writer
choices, inherited routing and actual fallback writer display. Additional mobile
actions saved Claude only, submitted a job, changed defaults to Codex only,
reloaded, and confirmed the existing mobile job still retained Claude only.
Desktop/mobile and actual-writer screenshots were inspected.

Fresh captures, replay harnesses and tested-head evidence are saved locally in
`artifacts/review/provider-fallback-recheck-20261105/`. This verifies the current
branch's local stub workflow; it does not claim deployment or live-provider
acceptance. No production data, runner code, approvals or allowances changed.

## Next scope

Operator review of Track E; migration `20261105_0032` is required when deploying
updated web/worker/scheduler processes. M4 and design-token acceptance are tracked
separately and retain their existing status. No merge or remote push is authorized.
