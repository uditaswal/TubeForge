# yt-script production automation integration

2026-10-11. Status: phases 1–2 **VERIFIED**; phase 3 workflow verified, creative visuals BLOCKED. Preserve existing uncommitted work and invocation ledgers.
No publication is authorized.

| Phase | User-visible outcome | Acceptance test | Evidence | Out of scope |
| --- | --- | --- | --- | --- |
| 1 | Updated canonical `.agents/skills/yt-script`, bundled into runtime resources | Inspect supplied references and hook tools; compare source/runtime/wheel hashes | Resource inventory and executed hook scorer | Other content skills, editorial rules in application code |
| 2 | Every production generation, retry, repair and revision carries the skill and complete brief; strict narration separation and blocked-source handling | Focused provider/schema/worker/API/UI tests, malformed and insufficient-source cases, exact approval/TTS checks | Captured prompts, resource hashes, regression results | New publishing features, raw-text fallbacks |
| 3 | Reviewed tutorial, explainer and comparison narration plus an approved local preview | Actual production invocation; source/creative review including “bare minimum Git commands required”; signed-in approval; inspect preview substance, pacing, visuals and captions | Real packages, invocation provenance, exact revision identity, media/browser inspection | YouTube publication, exhausted-ledger resets |

Complete one phase and report acceptance before the next. Stop after two failed
script attempts per brief; retain rejected output and reasons. Existing final
export/OOM blocker remains separate from this requested local preview.

## Initial trace

- Direct CLI: `CodexCliContentProvider.generate_package` builds the generation
  prompt; `_validate_or_repair` builds field repair prompts. Both ultimately
  invoke `_invoke` with structured output files and JSON validation.
- Isolated production host: `HostRunnerContentProvider.generate_package`
  preflights the prompt; `host_codex_runner.run_request` builds the actual prompt
  sent through stdin to the fixed sandboxed Codex command. Its durable ledger
  bounds retries. Only v5 currently embeds skill resources.
- Dashboard revision: `/api/jobs/{job_id}/script-revision` saves ordered local
  narration edits and requires new exact-artifact approval. The browser's
  “Copy Codex prompt” currently omits skill and full source/request context.
- TTS: `segment_content_package` reads only ordered
  `script_sections[].narration`; orchestrator voice generation consumes these
  phrases after the script approval gate.
- Resource loader: `youtube_skills.load_resources` embeds a fixed inventory;
  supplied new references need explicit inclusion and installed-wheel checks.
- Repair context currently lacks topic, audience, language and duration.
  Editorial directions currently exist in `prompts.py`; integration must move
  applicable writing guidance into the supplied skill without broad changes.

## Resolved input and scope

The operator identified `.agents/skills/yt-script` as the supplied folder and
explicitly restricted skill changes to this folder alone. Do not modify any
other downloaded skill installation. Installed-wheel copies are deployment
artifacts built from the canonical folder, not competing source installations.

## Acceptance evidence

Phase 1: **VERIFIED**. Canonical four-file yt-script inventory, real hook scorer,
container resource preflight and byte-identical wheel inclusion passed. No other
skill folder was edited in this request. The operator deployed wheel SHA256
`41eaaa2b7d3b092d5adf737b70e1ef1e7f3b2002ac7858eab85950a885d94c5f`.
All 85 Python source files match it. Actual host preflight matches all seven
selected resource hashes without a model call.

Phase 2: **VERIFIED** for invocation/output-handling integration. Final provider,
skill and automation batch: 63 passed in 269.72s. API, approval, worker,
checkpoint, TTS and Shorts batch: 84 passed in 1028.67s. Compatibility batch:
26 passed plus one moved-instruction assertion subsequently passed; no local
model was invoked. Actual host preflight confirms the expected assembled prompt
SHA256 as well as all seven resource hashes. Mechanical string bounds stripped
by the CLI schema adapter are derived from the domain schema in the prompt.
Signed-in API tests prove source blocking and fresh exact-revision approval.
Real generated content and browser/media acceptance remain Phase 3 scope.


## 2026-10-11 production acceptance update

Phase 3: **BLOCKED** on host deployment of repaired wheel SHA256
`307fab40c9cc95a7429504a186049864687302e4d29fb3a3097f9a1abd422d0a`.
The first actual tutorial call failed the existing ten-title acceptance gate.
No script was approved or sent to TTS. The previous host discarded the rejected
draft; its narration is unavailable. The narrow repair explicitly requests all
ten titles, enforces existing title/hook counts in the CLI envelope and retains
future domain-valid rejected drafts. Repair tests: 48 passed in 73.56s.
Preserve the existing tutorial job and its one consumed attempt. Next: verify
host deployment hashes, use the second and final tutorial attempt, then inspect
tutorial/explainer/comparison scripts and an exact-approved local preview.
No new creative artifact acceptance or publication is claimed.

## Final current evidence

Repaired wheel deployed; actual accepted calls for all three briefs match its
resources and exact prompt hashes. Tutorial and comparison each used two
attempts; explainer used one. Exact revised tutorial reached preview_ready and
signed-in browser checks passed. Creative visuals are **BLOCKED** by the existing
abstract renderer; auditory quality was not verified by listening. See
[the final report](YT_SCRIPT_AUTOMATION_REPORT.md) for changed files and evidence.
