# yt-script automation integration: implementation and verification

2026-10-11. Invocation and output handling: **VERIFIED**. Three production
scripts and exact-approved local preview workflow: **VERIFIED**. Creative visual
acceptance: **BLOCKED**. No publication, remote push or invocation-ledger reset.

## Changed files for this request

These changes sit alongside pre-existing uncommitted project work; this list
identifies the automation integration, not every dirty file in the checkout.

| Files | Change |
| --- | --- |
| `.agents/skills/yt-script/SKILL.md`, `automation.md` | Canonical automation instructions and referenced editorial contract; existing hook formulas/scorer preserved |
| `src/tubeforge/providers/content/youtube_skills.py` | Explicit seven-resource inventory, v6 template, hash/preflight/tool evidence |
| `src/tubeforge/providers/content/prompts.py` | Explicit resources and complete brief in generation, repair and revision; mechanical domain bounds and exact stdin evidence |
| `src/tubeforge/providers/content/output.py`, `src/tubeforge/core/errors.py` | Strict ready/source-failure envelope; typed insufficient-source rejection |
| `src/tubeforge/providers/content/codex_cli.py` | Strict generation parsing, explicit repair resources/context, invocation provenance and preserved attempt bounds |
| `src/tubeforge/providers/content/host_runner.py`, `host_runner_protocol.py` | Host resource/prompt-hash preflight; typed failures and rejected draft retention |
| `src/tubeforge/host_codex_runner.py` | Actual stdin proof, strict schema envelope, existing candidate-count gates, no-source precheck and domain-valid rejection handback |
| `src/tubeforge/domain/contracts.py` | Reject blank/panel/fenced narration in generated and saved revisions |
| `src/tubeforge/api/app.py` | Full-skill revision-prompt endpoint and truthful clipboard UI; insufficient-source blocked label |
| `config/default.yaml`, `production.yaml`, `production.example.yaml` | v6 for new configured production jobs |
| `tests/test_script_automation.py`, `test_youtube_skills.py`, `test_codex_content.py`, `test_host_codex_runner.py`, `test_ollama_content.py` | Focused integration/compatibility coverage and moved-instruction assertions |
| `AGENTS.md`, `readme.md`, `docs/STATUS.md`, runtime guide, automation plan, `AUTONOMOUS_PROGRESS.md` | Canonical resource/deployment/workflow rules and evidence |

Only the requested canonical yt-script folder was edited for this skill update.
Downloaded copies remain untouched. Wheel resource copies are deployment assets
built from this canonical source, not alternative skill installations. Existing
TTS and approval/render infrastructure was reused.

Repository cleanup is documented separately in `REPOSITORY_HYGIENE.md`: generated
files removed from tracking, intentional docs/scripts organized, exact ignore
rules and Docker context exclusions. No local artifact was deleted.

## Production invocation trace and proof

- CLI generation uses `build_content_prompt` before `_invoke`. Legacy field
  repair uses `build_repair_prompt` with the full request and explicit resources.
  v6 malformed output fails immediately; it is not converted into a repair/raw
  speech fallback. Durable attempt allowances remain in force.
- Worker retries call the same provider with the saved request. Host preflight
  compares seven resource hashes and the exact assembled prompt SHA256 before
  charging an invocation. `host_codex_runner.run_request` supplies that prompt
  through the actual Codex stdin and records its hash in invocation provenance.
- Dashboard “Copy Codex prompt” requests the backend revision prompt containing
  the saved package, sources, skill and complete brief. It copies instructions;
  it does not run Codex or silently save/approve a revision. Returned edits are
  saved through the existing revision endpoint and require fresh exact approval.
- TTS segmentation consumes only ordered `script_sections[].narration`. A source
  refusal becomes a blocked dashboard job; malformed output is rejected. Neither
  becomes speech. Atomic promotion, leases, fencing and cancellation remain in
  the existing pipeline.

Deployed wheel SHA256:
`307fab40c9cc95a7429504a186049864687302e4d29fb3a3097f9a1abd422d0a`.
All 85 application Python sources and canonical yt-script resources byte-match
that wheel. Actual preflight and all accepted invocations match the canonical
resource hashes; `skill_loaded` is `yt-script/SKILL.md`, automation mode is true.
Every brief explicitly includes topic, audience, language, duration, format,
tone/voice profile and source requirements.

| Actual brief | Accepted stdin SHA256 | Attempts / result |
| --- | --- | --- |
| Tutorial: bare minimum Git commands required | `791c5aff07ddabde567884bbeaae537ae53329ac1976bb6433497f25cc036749` | 2; first title-count rejection, second reached script review |
| Explainer: image versus running container | `7d762c2b42b58d21dfeb1de500440b9b7ce48d6ec04db7094ee12605d2e2c18a` | 1; reached script review |
| Comparison: Git merge versus rebase | `86f225266c92df38ddb14121f0f9a7dd69a8efe8240acd83727350bd1e50c094` | 2; first overlength visual field rejected, second reached review |

All local evidence files referenced here are under ignored
`artifacts/smoke/yt-script-automation/`. The Git topic is only a source-backed
acceptance brief, not a code special case. No local LLM or provider fallback was
used; actual writer was the dedicated host Codex runner with `gpt-5.6-sol`.

## Source and creative inspection

The tutorial distinguishes local stage/commit from remote sharing and optional
history inspection. A manual six-section revision added a check for other staged
files before committing the selected file. Sources: supplied paraphrases from
[status](https://git-scm.com/docs/git-status),
[add](https://git-scm.com/docs/git-add),
[commit](https://git-scm.com/docs/git-commit) and
[everyday Git](https://git-scm.com/docs/giteveryday).

The 140-word explainer connects packaged files/layers to the isolated process,
using the supplied Python-app example from
[Docker's image concepts](https://docs.docker.com/get-started/docker-concepts/the-basics/what-is-an-image/).
The 141-word comparison distinguishes file result from history, limits its merge
commit example to divergent branches, and warns against rebasing commits others
depend on, grounded in [Pro Git](https://git-scm.com/book/en/v2/Git-Branching-Rebasing).
Both remain in script approval; no render approval was fabricated.

The first tutorial rejection was discarded by the earlier host path and its
narration cannot be recovered. The repair now retains domain-valid rejected
packages. The malformed comparison never became a domain package or speech.
Rejected reasons remain in the evidence/ledgers; no allowance was reset.

## Exact-approved local preview

Tutorial job: `26b9cb4377b448e5ac70786f8c2ec8ad`.
Approved revision checksum:
`43d8792884172beb13876675a81f337848c9db5e52e30b00a3a07df10037b6f3`.
The script-revised event, durable script approval and preview input checksum all
match. The initial generated draft was not rendered. Segmentation, actual Piper
voice texts and SRT caption text match the approved narration in order.

- Media: 52.117 seconds, 540×960 preview, H.264/AAC, 30 fps, 150 narration words;
  about 173 words/minute including pauses. This is a local preview, not a final
  1080×1920 export.
- Substance: actionable local Git sequence and staged-file boundary; no spoken
  alternatives, scores, source lists, production instructions or refusal.
- Captions: exact narration text and sampled readable highlighted words within
  the safe area; no sampled clipping. Timing/order inspected structurally.
- Visuals: **FAIL** the tutorial teaching standard. Existing abstract graphics
  do not implement the planned terminal/staging-area demonstrations. The renderer
  was not broadened as part of the integration-only request.
- Auditory quality: not verified by listening. Objective audio duration and
  phrase/timing evidence passed; subjective pronunciation/audio review remains.
- Signed-in Chromium on the isolated acceptance database: real script review, explicit revision prompt in clipboard,
  silent refresh/dialog preservation, desktop/mobile layout and approved preview
  metadata loading passed. No JS errors or horizontal mobile overflow.

Artifacts: `tutorial-approved-narration.txt`, other topic narration files,
`preview-inspection.json`, `signed-in-browser-evidence.json`, screenshots and
`rendered/26b9cb4377b448e5ac70786f8c2ec8ad/preview.mp4`.

## Checks and practical limits

- Provider/skill/automation batch: 63 passed (269.72s).
- API/approval/worker/checkpoint/TTS/Shorts batch: 84 passed (1028.67s).
- Compatibility: 26 passed; one obsolete assertion updated and its rerun passed.
  Ollama coverage used mocks only, not a production local-model call.
- Final candidate-count/rejected-draft repair batch: 48 passed (73.56s).
- Real hook scorer, wheel/source checks, exact-revision approval, insufficient
  source blocking, actual three-brief invocations, ffprobe and artifact inspection
  passed as described above. Counts overlap; these are not unique-test totals.
- Repository shell syntax, tracked-artifact/ignore checks, local doc links,
  credential-signature scan and `git diff --check` passed. The signature scan is
  not a guarantee about all past Git history. Curl guide inspected against API
  contracts; not executed against a live job.

Remaining blockers: visual teaching quality and listening review. The old
exhausted final-export/OOM job remains unchanged and outside this local-preview
scope. No full release-wide suite or final-export success is claimed. No upload.


## Local deployment follow-through

Production web/worker/scheduler were restarted after confirming zero active
pipeline claims. Existing checkout migrations had not been applied to the local
primary database; Studio heartbeat reads revealed that mismatch. An online backup
was created under ignored `data/backups/`, then existing migrations advanced
`20260927_0020` to `20261005_0028`. Heartbeat table existence, zero active claims,
health and login HTTP 200 passed. No migration code was added, no publisher
started, and no upload performed. Signed-in creative/browser acceptance above
used the isolated acceptance database, not a primary operator account.
