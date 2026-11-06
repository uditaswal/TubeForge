# LF0-A: long-form planning interface

This interface is isolated in `src/tubeforge/domain/long_form.py`; no API, production preset, runner operation or rendering path registers it yet. It wraps the existing ContentRequest and does not introduce a second script or VideoPlan.

## Contract for the content lane

- Schema: `tests/fixtures/long_form/planning_contract.schema.json`.
- Synthetic example: `tests/fixtures/long_form/planning_contract.json`.
- Required profile: `m6-content-long-v1`, native 16:9, target 600–900 seconds, original generated content.
- `section_ids` is the canonical ordered section inventory. Every section belongs to exactly one chapter, in that order; chapter IDs are unique. Actual narration and scenes continue to belong to ContentPackage. The separate verifier in `pipeline/long_form_contracts.py` now validates correspondence with the finished ContentPackage and its existing script approval identity.
- `cited_source_ids` must resolve to request sources. Packet/reference hashes bind identity only; they do not prove retrieval, factual correctness, freshness or approval. Packet byte verification belongs to intake/integration.
- Chapter titles and membership have no timestamps. Media stages derive timestamps from actual accepted audio. Three to twelve chapters is an interface bound, with five to eight the editorial starting range.
- Do not send this companion wrapper to either current host runner. The current host operation is still GenerateShortsScriptV1; long-form admission is not wired.

Claude can now draft an editorial proposal against these field names. Request schema changes through the core owner rather than modifying this module or the generated schema.

## Measured local envelope and limits

Measurements use Pydantic compact JSON encoded as UTF-8, not token estimates. The synthetic fixture has only three short sections and one tiny source; these are lower-bound interface measurements, not representative production payloads.

| Item | Observed size / configured bound |
|---|---|
| Synthetic planning fixture serialization | 1,430 bytes |
| Existing host request wrapping the synthetic canonical brief | 997 bytes |
| Compact planning JSON schema | 6,679 bytes |
| Codex / Claude socket input | 65,536 bytes each |
| Host response and client receive ceiling | 4,000,000 bytes |
| Codex output file / Claude structured output bound | 2,000,000 bytes |
| Codex script prompt ceiling | 60,000 characters at build call |
| Claude script prompt ceiling | 90,000 characters by default/environment/config |
| Codex CLI timeout / socket timeout / reservation | 480 / 490 / 1,200 seconds |
| Claude CLI timeout / socket timeout / reservation | 540 / 900 / 1,800 seconds |
| QA reference-short duration | 30–90 seconds; non-Short target tolerance currently 40% |

Sources: host_codex_runner.py, host_claude_runner.py, providers/content/host_runner.py, config/production.yaml and .agents/skills/om-video-quality/qa_check.py. Recheck effective runtime overrides before deployment. Output file limits do not establish a model's maximum output tokens. The baseline runners used one recv call. The 7 November core checkpoint now reads fragmented requests within a 65,536-byte / 30-second bound, preserving legacy complete-JSON clients and checking peer identity before reading. The worker checks encoded size before provider invocation reservation or transport. Long-form must not inherit the generic QA 40% duration tolerance as its acceptance rule.

## Package binding and final measurement interface

`pipeline/long_form_contracts.py::validate_long_form_package` consumes exact package/source bytes and an existing durable script-gate identity. It rejects a missing/stale gate, changed canonical brief, changed source packet, conflicting chapter boundaries/titles, reordered/missing scenes or sections, citation mismatch and missing/unbound reference bytes. It delegates source-packet semantic validation to the existing scene-contract validator. It never creates approval. The caller must obtain the identity from the approval repository, not from user-submitted JSON. Reference bytes are checked for identity only; reference extraction/content validation belongs to LF1.

`LongFormTechnicalProbe` and `tests/fixtures/long_form/technical_probe.schema.json` define a final measurement interface: 1920×1080/30fps H.264/AAC, 48 kHz, 600–900 seconds, −15..−13 LUFS, true peak ≤−1.5 dBTP and a successful full decode. `validate_target` binds the actual artifact identity, chapter count and ±5% requested-target tolerance while retaining the absolute 600–900 second range. Chapter intervals start at zero, increase and last at least ten seconds, including the final chapter. Nonfinite measurements fail. These are proposed long-form acceptance thresholds with automated fixtures; the real QA adapter and listening review remain future work. The model cannot prove supplied measurements actually ran.

### Representative envelope measurements

`tests/test_long_form_envelopes.py` builds synthetic packages locally without writers. Both include a 13,000-character source excerpt; UTF-8 compact JSON sizes are:

| Synthetic shape | Narration words | Host request | Package | Host response |
|---|---:|---:|---:|---:|
| 30 scenes × 45 words | 1,350 | 14,449 B | 40,598 B | 40,673 B |
| 60 scenes × 36 words | 2,160 | 14,449 B | 61,352 B | 61,427 B |

These fit current measured byte ceilings. Repeated synthetic prose is deliberately not quality evidence. Richer visual contracts, research, schema instructions and model reasoning are not represented; no model output-token capacity or subscription cost is inferred.

A 24,000-character non-ASCII excerpt produces a **72,949-byte request**, exceeding the **65,536-byte socket input** while satisfying SourceReference's character bound. The worker now counts the final encoded request before reserving a provider attempt or contacting its runner, and returns an explicit actionable oversize error. Do not truncate accepted evidence silently. Socket fragmentation is addressed by the shared reader; actual model output-token caps still require long-form admission integration. Increasing prompt character limits does not resolve transport byte bounds.

## Proposed API boundary for LF1 review

No endpoint is enabled by this checkpoint. Freeze these semantics with the intake implementation and its browser tests:

- Intake create input: reference URL, target seconds (600–900), channel identity, language and optional supplied transcript. The server resolves channel defaults and validates public-network access. Clients cannot supply approval, packet hashes, fetch success or provider usage as trusted evidence.
- Intake read output: opaque intake ID/revision; extraction state (`pending`, `ready`, `needs_input`, `failed`); captured metadata; transcript availability/origin; limitations; server-computed reference hash; and an actionable bounded failure code. A response never says the video was watched when only captions were retrieved.
- Ready intake conversion: server binds captured reference identity and verified source packet to the canonical generated ContentRequest. Repeated exact intake reuses cached extraction; a revision changes identity. The existing source_clip operation remains separate.
- Review projection: canonical package plus planning companion, grounding/originality findings and observed-or-unknown usage. Exact narration approval remains the existing durable operation; client-provided script hashes cannot grant it.
- Rejection examples: duration 599/901, unavailable captions without fallback, oversize encoded request, unknown evidence identity and stale intake revision. No provider call occurs on these preflight failures.

## Acceptance and remaining work

Validation group: `PYTHONPATH=src .venv-benchmark/bin/python -m pytest -q tests/test_long_form_contract.py tests/test_long_form_envelopes.py tests/test_reference_content.py tests/test_scene_contracts.py`.

LF0-A's isolated contract, byte measurements and technical-policy fixtures now have automated evidence. LF0 as a whole remains IMPLEMENTED until Claude's editorial/skill precedence proposal is reviewed and the proposed API semantics are reconciled. These API semantics are a design boundary, not implemented HTTP workflows or signed-in browser evidence. Production long-form routing, actual QA extraction and real source/video validation belong to later integration. Transport preflight and fragmented-request handling are now implemented and locally tested for both existing providers. No live provider, migration, deployment or render occurred. Do not begin LF1 until the full LF0 acceptance is reported.

## 7 November transport checkpoint

Final focused group: **145 passed** across runner request transport, Codex runner/client, Claude connections, failure codes, research, provider fallback and long-form contracts/envelopes. New tests use real local Unix sockets, including seven-byte receive fragments splitting UTF-8, byte-limit boundaries, truncated EOF, bounded read timeout, unauthorized peers, and old/new client compatibility. Four provider tests prove oversized generation/research requests call neither transport nor provider reservation/consumption for both Codex and Claude. The first run lacked local-socket access; rerunning with that access passed. No live writer or service deployment was involved.

Validation command: `PYTHONPATH=src .venv-benchmark/bin/python -m pytest -q tests/test_runner_request_transport.py tests/test_host_codex_runner.py tests/test_host_claude_runner_connections.py tests/test_runner_failure_codes.py tests/test_content_research.py tests/test_codex_content.py tests/test_provider_fallback.py tests/test_long_form_contract.py tests/test_long_form_envelopes.py`.

Worker request writes now end with a write-side shutdown; existing runners still receive the same JSON bytes. Updated runners also accept older clients that wait without EOF. The read deadline applies only to request receipt, not generation. Codex clears per-connection request state so a failed read cannot report the preceding client's invocation state. No source excerpts are truncated or included in the oversize error.

LF0-B editorial proposal was not present in available branches/worktrees on inspection. Reconcile that proposal and finalize the API fixtures before declaring the full LF0 phase accepted. This transport work does not enable the proposed long-form profile or change provider fallback eligibility. Deploying the updated worker/host code remains separate from local validation.

## Next ten core-task interfaces (7 November)

The next ten core tasks and their per-task evidence are in `docs/long-form-next-ten-core-tasks.md`; final relevant regression group: 295 passed. Additional exported schemas cover reference snapshots, intake request/state projections, a five-call checkpoint ledger and a measured timing manifest. Core adapters now verify typed references, preserve unknown usage, build exact bounded source context and export chapters from measured absolute section timing. `pipeline/long_form_preflight.py` combines these checks without provider/render calls.

The inspected local smoke report is `artifacts/review/long-form-core-20261107/preflight.json`: synthetic 60-scene/900-second supplied-timing data, 13,769 context bytes, 14,449 request bytes and six chapters. It proves local contract compatibility and rejection behavior; it does not prove a video exists or was approved. Exact source-packet validation is shared before and after narration, with existing provenance semantics retained. API projections remain unregistered, and durable checkpoint reservation must be integrated under the existing worker lease before a future launch.
