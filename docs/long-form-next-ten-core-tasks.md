# Next ten Codex core tasks

Scope agreed from the active request to perform the next ten Codex tasks. Parent contract: `90314ba`. These complete core prerequisites within LF0 without taking Claude's editorial/prompt/UI files. Implementation status belongs only to the current design plan; this file defines acceptance and evidence.

| ID | Outcome | Dependencies | Acceptance / evidence |
|---|---|---|---|
| C01 | Canonical public YouTube reference URL contract | existing long-form profile | Equivalent watch/short URLs canonicalize; malformed/credential/private/arbitrary-host URLs fail |
| C02 | Timestamped transcript and reference snapshot contract | C01 | Finite bounded ordered cues, language/origin/metadata and unavailable-transcript truthfulness |
| C03 | Deterministic reference identity and exact-brief cache key | C02 | Same content stable, semantic changes invalidate, capture time retained separately |
| C04 | Strict proposed intake request/status projection | C01–03 | No client approval/hash injection; ready/needs-input/failed states consistent; schema fixtures |
| C05 | Validate a reference snapshot against planning and script | C02–03 | Hash, URL/language/identity integrity; changed/missing evidence fails without approval mutation |
| C06 | Bounded stage/call and narration-attempt accounting | accepted lean envelope | Persistable immutable attempt records; research once, narration twice total, auxiliary calls cannot rewrite narration |
| C07 | Aggregate observed usage without inventing missing totals | C06 | Mixed/unknown token/cost fields remain explicitly incomplete; no subscription conversion |
| C08 | Compact source-context builder with hard UTF-8 bounds | source packet provenance, C03 | Exact source IDs/excerpts, no silent truncation; oversized context fails; repeat use stable |
| C09 | Export chapters from measured section starts | approved package/chapter mapping | Absolute timeline, 00:00, strictly ordered ≥10s chapters, no guessed timestamps |
| C10 | Combined local preflight smoke and regression evidence | C01–09 | Synthetic reference→plan→approved-package identity→bounded context/budget→measured chapters; adversarial failures; no live service |

Allowed implementation paths: new `domain/reference_video.py`, `domain/long_form_budget.py`, `pipeline/long_form_reference.py`, `pipeline/long_form_budget.py`, `pipeline/long_form_chapters.py`, existing `pipeline/long_form_contracts.py`, new context/chapter/preflight modules, and source-provenance helpers as needed, focused tests/fixtures and shared integration records. Forbidden lane paths: production narration skills, content prompts/youtube_skills, Claude editorial proposal and dashboard UI. No API endpoint, migration or preset registration is part of these contract tasks. Proposed HTTP-facing shapes remain explicitly unregistered until LF1 UI/API work can land together.

Each task uses the existing long-form and ContentPackage identities. Test artifacts use temporary directories, never the local production database. Test fixtures are synthetic, never operator approval or creative evidence. Acceptance requires focused tests plus one combined smoke, not a claim that full long-form generation works. The subsequent editorial/description-policy reconciliation is recorded in `docs/long-form-lf0-acceptance.md`; these core tasks alone did not establish full LF0 acceptance.

## Acceptance evidence for the ten-task checkpoint

Final relevant group: **295 passed**. The local evidence report at `artifacts/review/long-form-core-20261107/preflight.json` and `scope.txt` was opened and inspected. It is synthetic contract evidence, with 60 scenes / 2,160 synthetic narration words and a supplied 900-second timing manifest. It is not a rendered video or operator approval.

| Task | Authoritative implementation | Focused evidence |
|---|---|---|
| C01 | `domain/reference_video.py::canonical_reference_url` | URL-equivalence and unsafe/ambiguous-link cases in `test_reference_video_contracts.py` |
| C02 | `ReferenceSnapshot`, `TranscriptCue` | Finite timestamps, overlap/order, byte cap, language/timezone/origin and missing-transcript cases |
| C03 | `pipeline/long_form_reference.py` identities | Capture-time stability; transcript/title/extractor/target changes invalidate keys |
| C04 | `ReferenceIntakeRequest`, `ReferenceIntakeView` | Schema snapshots; supplied cues; client identity/approval injection and inconsistent states rejected |
| C05 | `validate_planned_reference` and package verifier | Exact bytes, video identity, language, intake and supplied transcript binding tests |
| C06 | `domain/long_form_budget.py`, reservation/finalization helpers | Five-call history, one research, draft+repair, unresolved calls, restart serialization and rejected retry cases |
| C07 | `summarize_usage` | Partial/unknown tokens and reported cost; zero only for confirmed unstarted calls; no subscription fraction |
| C08 | `build_source_context`, shared source-packet verifier | Exact excerpt preservation, stable serialization, byte ceiling, forged evidence and spoofing rejection |
| C09 | `LongFormTimingManifest`, `export_chapters` | Script/audio/final hash checks, measured-only methods, exact inventory, ≥10s intervals and newline injection cases |
| C10 | `audit_reference_package` | Combined smoke plus nine conflicting-checkpoint failures; inspected local report |

The smoke report shows 13,769 UTF-8 source-context bytes, 14,449 request bytes, four simulated reserved calls, one narration attempt, and chapters at 00:00 / 02:30 / 05:00 / 07:30 / 10:00 / 12:30. Simulated usage is test data; missing costs and subscription fractions are null. Provider/model/capture-only changes do not reset the semantic allowance key. Approval identity and media hashes must come from existing durable repositories when the integration is enabled.

The budget helpers are pure immutable checkpoint transformations: the later job integration must atomically save a reservation under its lease before launch. They do not create a parallel database, replace host allowances or claim concurrency enforcement on their own. URL normalization makes no network-safety or access claim; future fetches must retain public-DNS and redirect checks. Proposed request/read schemas are not registered endpoints. The chapter exporter uses actual supplied absolute section timing and floors timestamps to seconds; it does not perform alignment or create timestamps by script proportions.

During regression, the existing source redirect test exposed missing-origin handling raising AttributeError. It now fails closed with the expected validation error. No source validator was loosened. The content-spoofing test initially expected ValueError instead of the existing ProviderValidationError; only its expectation changed.

Validation command:

```bash
PYTHONPATH=src .venv-benchmark/bin/python -m pytest -q \
  tests/test_reference_video_contracts.py tests/test_long_form_reference_binding.py \
  tests/test_long_form_budget.py tests/test_long_form_chapters.py \
  tests/test_long_form_core_preflight.py tests/test_long_form_contract.py \
  tests/test_long_form_envelopes.py tests/test_scene_contracts.py \
  tests/test_sources.py tests/test_source_redirects.py \
  tests/test_reference_content.py tests/test_reference_shorts.py \
  tests/test_runner_request_transport.py tests/test_host_codex_runner.py \
  tests/test_host_claude_runner_connections.py tests/test_runner_failure_codes.py \
  tests/test_content_research.py tests/test_codex_content.py tests/test_provider_fallback.py
```

Local socket access was enabled for the transport tests. No live provider calls, reference fetching, real-video QA, signed-in workflow change, deployment or publication occurred. Claude's production prompts, skills and UI files were not edited. The subsequent editorial/description-policy and API reconciliation is recorded separately in `docs/long-form-lf0-acceptance.md`; these ten core tasks do not stand in for the full long-form workflow.
