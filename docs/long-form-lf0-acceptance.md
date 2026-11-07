# LF0 local design acceptance — 7 November 2026

This record covers the contracts/budget baseline and the completed editorial proposal originally assigned to Claude. The operator asked Codex to take over that assignment. It does not accept a production script, media artifact, publishing package or live deployment. Current implementation status remains solely in `doc-internal/design_doc/tubeforge-publishing-design.md`.

## Inputs and branch review

- Core parent: `f39516b` on `codex/long-form-reference-plan`.
- Separate content branch: `codex/long-form-content`, created from local `dev` `4b56e9b` in `/tmp/tubeforge-long-form-content`.
- Content handoff: `37f5737` (proposal plus description-bound correction; initial copied-doc/proposal commit `97e8fb8`). Only the reviewed new proposal was copied into the core branch; unrelated `dev` changes were not merged or cherry-picked.
- Proposal: `docs/long-form-editorial-proposal.md`. Required skills and helper resources were inspected from the canonical project copies; no competing narration skill was installed or loaded.

The content branch contains the copied plan/core interface and proposal, as assigned. Core integration adds the golden acceptance fixtures and the read-only reference identity contract below. No production narration prompts or skill resources changed. The temporary content worktree is retained as an unmerged review branch; no merge/push/deployment is part of this record.

## Requirement-by-requirement evidence

| LF0 requirement | Evidence inspected | Result and limit |
|---|---|---|
| Versioned native landscape profile | `domain/long_form.py`, profile/schema fixtures, 600/720/900-second tests | Typed design requires 16:9 and 600–900 s; no production preset/host operation registered |
| Reference record and truthful intake states | `domain/reference_video.py`; request/read schemas and four golden intake examples | Canonical links, bounded timestamped cues, origin/language/limitations, ready/pending/needs-input/failed consistency; no fetching implied |
| Exact chapter/scene/source bindings | Long-form package/reference verifiers and shared source-packet checks | Stale hashes, conflicting reference/source data, wrong section/scene/chapter order and missing approval identity rejected |
| Input/output limit inventory | `docs/long-form-contract-interface.md`; runner transport and representative envelope tests | UTF-8 request cap, prompt character caps, socket/output/time bounds and synthetic sizes documented; model output-token capacity must be checked in later host admission |
| Bounded call/retry/usage rules | Call ledger, usage/context helpers, five-call/two-narration and pending-call tests | Unknown usage retained; no reset by provider/capture-only change; checkpoint must later be persisted atomically under job ownership |
| Long-form editorial standard | Proposal §§1–2, 8; synthetic editorial cases read against their explicit fictional evidence | Audience promise, coherent chapters, supported improvements, originality and payoff rubric defined; no claim of actual audience demand/retention |
| Compact prompt/resource proposal | Proposal §§4–6; canonical resource contents, byte counts and hashes | Mandatory four yt-script resources retained; stages avoid repeated full transcript/request echoes; proposed header/envelope not installed |
| Skill precedence | Proposal §3 | Shorts-only loop/duration/portrait rules scoped out of the proposed long profile; narration remains separate from production panels; Short behavior preserved |
| Description/thumbnail conflicts | Proposal §7; local title tool and existing application checks; publication regression tests | Four-word thumbnail rejected by application even though helper misses it; long description proposal uses stricter 5,000-char QA bound, measured chapters and sources; Short two-line behavior unchanged |
| Review/generation gates | Synthetic local fixtures and existing exact-identity tests | Independent review supplies defects, not approval; schema/scorer success cannot approve or publish; future live trial remains separate |
| Frozen API examples | `editorial/intake_examples.json`, `ReferenceIntakeViewResponse.schema.json` and serialization tests | Read-only `reference_snapshot_sha256` derives from canonical snapshot bytes; client hash injection rejected; endpoints remain unregistered |
| Full local smoke and regression | Existing 60-scene preflight report plus new editorial reports; final test command below | 318 passed, reports opened and reviewed; no real video, full watch/listen or signed-in long-form workflow claim |

## Core/API reconciliation

The existing script and chapter models can express the proposed editorial design, so no duplicate VideoPlan or production schema replacement was added. The intake read projection lacked the server-derived reference identity described by the interface. It now serializes a read-only computed `reference_snapshot_sha256`. Future capture persistence must store the same canonical `ReferenceSnapshot.model_dump_json()` bytes, and the planning companion binds that exact hash. This field proves identity only; it does not establish factual accuracy, capture authenticity, originality or approval. Read projections use the serialization schema; the strict create request cannot accept the hash.

Description reconciliation uses the stricter current local QA/delivery bound of 5,000 characters rather than the generic package schema's 10,000. The long-form description structure is accepted as a new-profile design: concise opening, final measured chapters, factual sources, separate reference/media credits and actual disclosures. Its implementation must land with metadata preparation/validation/QA and Publishing UI tests. The current Short publishing flow stays two-line until that opt-in profile branch exists.

The new profile must not inherit legacy resource loading blindly. The current generic evaluator can run local scoring on a synthetic package, but `m6-content-long-v1` remains outside the supported host prompt versions. Local evaluator success is not generation readiness. Later LF2 needs a strict writer envelope carrying package-owned fields plus chapter grouping; application code binds trusted request, source/reference hashes and section inventory. Existing legacy/Short resource identities must remain stable.

## Actual local tool and fixture review

Evidence directory: `artifacts/review/long-form-editorial-20261107/`.

- `hooks-report.json`: canonical hookscore.py executed on all five synthetic candidates. The top scores are **53** and **44**, both WEAK. These fixtures test tooling/field separation and do not qualify as production hook recommendations. No unsupported figures were added to inflate scores.
- `titles-report.json`: canonical title.py executed on all ten synthetic titles with the paired thumbnail text. Its warnings are heuristics, not audience measurements or an instruction to fabricate a number.
- `review.json`: exact fixture hash, explicit synthetic scope, three editorial review verdicts, unchanged canonical resource hashes and missing production evidence.
- `intake-responses.json`: pending/ready/needs-input/failed examples, visible caption-only limitation and computed identity when a snapshot exists.
- Existing core smoke: `artifacts/review/long-form-core-20261107/preflight.json`, 60 synthetic scenes, supplied 900-second timing, 13,769 context bytes, 14,449 request bytes, six measured-fixture chapter starts and explicit unknown cost/subscription fields.

Manual fixture judgments: the synonym-swapped framing is rejected because it preserves the reference's distinctive order without improvement; the 100% debugging-time claim is rejected because the fictional packet contains no measurement; the qualified new trace comparison is acceptable only as a fixture example because it adds a supported observation while withholding causal/performance claims. These judgments are not a real reference-video originality review or legal clearance.

The existing seven-file legacy resource block measures **35,835 characters / 35,857 UTF-8 bytes**, before the remaining instructions, schema, brief and sources. All seven hashes match parent `f39516b`. This is byte/character evidence, not a tokenizer result or a subscription allowance estimate. No resource was changed, installed or deployed; installed-wheel parity remains a gate when LF2 changes resources before host use.

## Validation

Final group: **318 passed**. Local socket access was enabled for the runner tests. No live provider, network reference retrieval, paid API, production database write, migration, render or publication occurred.

```bash
PYTHONPATH=src .venv-benchmark/bin/python -m pytest -q \
  tests/test_long_form_editorial_contract.py tests/test_reference_video_contracts.py \
  tests/test_long_form_reference_binding.py tests/test_long_form_budget.py \
  tests/test_long_form_chapters.py tests/test_long_form_core_preflight.py \
  tests/test_long_form_contract.py tests/test_long_form_envelopes.py \
  tests/test_scene_contracts.py tests/test_sources.py tests/test_source_redirects.py \
  tests/test_reference_content.py tests/test_reference_shorts.py \
  tests/test_runner_request_transport.py tests/test_host_codex_runner.py \
  tests/test_host_claude_runner_connections.py tests/test_runner_failure_codes.py \
  tests/test_content_research.py tests/test_codex_content.py \
  tests/test_provider_fallback.py tests/test_publication_suggest.py
```

## Next phase boundary

LF0's design/contract evidence is sufficient to begin LF1 implementation. LF1 must implement real bounded link/caption acquisition, immutable durable intake records/cache/revisions and truthful source/limitation display, with API and signed-in dashboard flow together. It needs fixture tests for access/missing captions, language, prompt-control data, redirects/private-network targets, timeouts, oversized text, duplicate intake, retry/revision and mobile/desktop behavior. Keep source_clip separate and preserve worker fencing/cancellation/exact approvals.

The later content task is LF2's opt-in production prompt/envelope/resources and one separately authorized grounded script trial, after LF1 acceptance. New resource hashes, wheel parity, real host admission and observed usage remain required there. The long-form renderer, actual QA adapter, local export and real 10/15-minute creative pilots remain later phases. Nothing in LF0 acceptance substitutes for those outcomes.
