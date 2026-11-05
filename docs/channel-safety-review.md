# Channel safety checkpoint review

Branch: `codex/channel-safety`. Review only; no merge, remote push, publication,
production script generation, or production approval occurred.

| Milestone | State | Evidence |
| --- | --- | --- |
| M-S5 disclosure record | **VERIFIED** | Per-final atomic, lease-fenced checkpoint; reused finals backfill without rendering. Signed-in API and export tests cover explicit disclosure choice, missing evidence, changed-evidence invalidation and checksummed staging. Real-final record persisted and inspected in an isolated database. |
| M-S6 repetition report | **VERIFIED** | Versioned structured endpoint; configurable overlap/phrase thresholds; recent undated Shorts use stored creation time. Deliberately repetitive fixtures and channel/window isolation tested. Read-only inspection of 11 real recent entries found four title-similarity pairs. |
| M-S7 cadence guard | **VERIFIED** | Advisory daily limits and minimum spacing, per-channel timezone/configuration; cross-plan import warnings, midnight/boundary/missing-time tests. Real plans produced four missing-publish-time warnings. No scheduler or upload change. |
| M-S8 checklist | **VERIFIED** | Short public checklist, linked from batch documentation and the review page; authenticated route/browser checks pass. Contains no credentials or machine paths. |

## Validation

Use `PYTHONPATH=src .venv-benchmark/bin/python -m pytest -q` with these focused groups:

- `tests/test_channel_reports.py tests/test_channel_safety.py tests/test_batch_review_api.py tests/test_batch_exports.py tests/test_batch_ui_runtime.py tests/test_batch_import_api.py tests/test_config.py tests/test_batch_queue.py tests/test_batch_automation.py tests/test_reference_shorts.py tests/test_story_primitives.py`: 88 passed at the first integrated report checkpoint.
- Final source/rights and channel overrides: 33 passed across report/disclosure/import/review/export/UI-runtime tests; subsequent focused checks verified undated-window fallback, durable records, ownership fencing, strict audio evidence and silent refresh.
- Final checkpoint-specific runs: 13 passed for disclosure/report checks; 22 passed for review/export/UI runtime; 15 passed for final refresh/disclosure/report checks. Final broader run: `tests/test_channel_safety.py tests/test_channel_reports.py tests/test_pipeline_orchestrator.py tests/test_batch_exports.py tests/test_batch_review_api.py` — **90 passed in 556.11 seconds**.
- Chromium used an isolated temporary database: signed-in review, missing disclosure choice rejected, explicit choice → approve → stage, and checklist navigation. Desktop 1280×900, tablet 768×1024 and mobile 390×844 showed no horizontal overflow after fixing the dropdown width. No JavaScript exceptions. Fixture media were placeholders; these browser tests do not prove media playback or creative quality.
- Impeccable mechanical check returned no findings for the two batch/review surfaces.

## Actual artifact inspected

Existing rate-limit-v2 final, job
`batch-caaacb77d5659ea27ce1292d20f45c6f6b6f857c30d4ad97`:
49.7 seconds, 1080×1920, final SHA-256
`1651e48e71df50866a152ce7e0618115457ce164d3255a9b833bec934673bbc7`.
`om-video-quality/qa_check.py` reported no FAIL. Warnings: scene 7 dead stretch,
music-under-speech proximity, and missing composed thumbnail. A twelve-position
contact sheet was inspected; the existing “Ask AI” chip remains visible in a
source crop. No full new listener/creative acceptance is claimed.

The real-final disclosure record was persisted and checksum-registered in an
isolated database with `platform_disclosure_required` unset. Sources and the
reused music/SFX licence trail were present; the existing M-S2 originality check
passed. No real job was approved or staged for this smoke test.

## Limits and next action

Warnings are heuristics, not monetization/policy verdicts. Missing render layout
or voice evidence remains unknown. Older render reports dropped `layout_family`
from the encoder envelope; new reports now preserve that existing field. The
report does not invent older layout choices. Catalog music terms are resolved
by actual audio checksum; a catalog pointer alone fails the rights gate.

Track E is **BLOCKED** pending the operator's approval of
[the routing proposal](provider-fallback-contract.md). Runner error-code interface
and concrete next files/commands are in `HANDOFF.md`. M4/design tokens remain
**NOT STARTED** in this checkpoint.
