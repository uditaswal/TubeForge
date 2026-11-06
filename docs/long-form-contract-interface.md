# LF0-A: long-form planning interface

This interface is isolated in `src/tubeforge/domain/long_form.py`; no API, production preset, runner operation or rendering path registers it yet. It wraps the existing ContentRequest and does not introduce a second script or VideoPlan.

## Contract for the content lane

- Schema: `tests/fixtures/long_form/planning_contract.schema.json`.
- Synthetic example: `tests/fixtures/long_form/planning_contract.json`.
- Required profile: `m6-content-long-v1`, native 16:9, target 600–900 seconds, original generated content.
- `section_ids` is the canonical ordered section inventory. Every section belongs to exactly one chapter, in that order; chapter IDs are unique. Actual narration and scenes continue to belong to ContentPackage. This draft contract does not yet validate correspondence with a finished package.
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

Sources: host_codex_runner.py, host_claude_runner.py, providers/content/host_runner.py, config/production.yaml and .agents/skills/om-video-quality/qa_check.py. Recheck effective runtime overrides before deployment. Output file limits do not establish a model's maximum output tokens. Both runners currently receive using one bounded recv call; fragmented-message handling needs integration review before larger payloads. Long-form must not inherit the generic QA 40% duration tolerance as its acceptance rule.

## Acceptance and remaining work

Command: `PYTHONPATH=src .venv-benchmark/bin/python -m pytest -q tests/test_long_form_contract.py tests/test_reference_content.py` — **22 passed**. This proves the isolated interface and existing reference-content regression scope.

LF0 still needs a representative 30–60-beat script/output envelope, profile-aware QA fixtures, final ContentPackage binding, reviewed editorial/skill precedence and API fixtures before the entire phase can be accepted. No real reference/video, provider invocation, browser change, migration or deployment occurred. Continue LF0, then report its full acceptance before LF1.
