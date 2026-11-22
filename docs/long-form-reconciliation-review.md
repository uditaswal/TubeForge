# Long-form reconciliation review

Base branch `codex/long-form-reference-plan` at `d50558ea60d1624fdfe447bbff682f2fa8061670` was backed up locally as `backup/long-form-pre-reconcile-20261115`. `dev` was merged into it without rebasing. No deployment, remote push, main merge, or live writer/provider call is part of this reconciliation.

## Conflict decisions

- `docs/HANDOFF.md`: kept dev's structure and publishing next steps; restored short LF2 D, Docker qualification and landscape status with links to the detailed blocker records.
- `docs/batch-plans.md`: kept dev's script alias and exact-script documentation alongside the remaining long-form branch additions.
- `src/tubeforge/api/app.py`: kept dev's exact-script request handling, publishing schedule and settings routes, and retained the reference intake and long-form routes.
- `src/tubeforge/api/batch.py`, `batch_ui.py`, `batch_plans.py`, and `scheduling/batch_requests.py`: retained dev's scoped cadence, import UI and exact-script behavior; non-conflicting long-form code remains.
- `src/tubeforge/api/script_tools_ui.py`: kept dev's version; comparison showed the branch version was its earlier form and its own-script functionality is retained in dev.
- `src/tubeforge/domain/contracts.py` and `providers/content/prompts.py`: combined dev's exact-script and number-guard behavior with the branch's long-form fields and prompts.
- `src/tubeforge/pipeline/script_fit.py`: retained dev's own-script alias, exact mode and number checks; its non-conflicting long-form branch functionality is retained.
- `tests/test_api_workflow.py`, `test_script_fit.py`, and `test_youtube_skills.py`: retained dev's checks and changes along with non-conflicting long-form tests. `tests/test_migrations.py` keeps long-form head expectations and uses the new immediate parent for reference-intake round trips.
- The long-form planning schema fixture was regenerated because dev adds the `exact_script` field to the shared request model.

## Migration chain

`20261105_0032` → `20261111_0033` → `20261111_0034` → `20261111_0035` → `20261108_0033` → `20261108_0034` (single head). Only the parent of long-form `20261108_0033` was changed; dev's migrations were left intact.

## Validation

- `alembic heads`: only `20261108_0034`.
- Requested long-form/migration group with the existing local tokenizer cache: **379 passed, 5 skipped**; the skips are opt-in browser/render checks.
- Requested batch/review/publishing group: **43 passed, 1 failed**, the previously identified dev failure `test_review_javascript_disables_stale_artifact_without_replacing_player`.
- Full suite: **1,462 passed, 29 skipped, 10 failed** (`/tmp/tubeforge-reconcile-full.log`). One is the known stale-player failure; eight renderer tests could not find Node on PATH, and the publisher-worker startup test timed out under load. The publisher test passed alone; a representative renderer test passed with Node on PATH after the full suite. All eight renderer tests subsequently passed with Node on PATH and without the full suite competing for resources (`/tmp/tubeforge-reconcile-renders-final.log`).
- Staged comparison with the backup found no deleted long-form files in the requested paths.
