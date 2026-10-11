# YouTube skills integration plan

2026-10-11. Preserve the existing uncommitted publishing work and host Codex
provider. No publication is authorized by this verification request.

| Phase | User-visible outcome | Acceptance test | Required evidence | Out of scope |
| --- | --- | --- | --- | --- |
| 1 | Discoverable, application-compatible skills and durable instructions | Inspect all skill resources; verify one canonical installation and wheel resource mapping | Resource inventory and executable tool reports | Production invocation, rendering |
| 2 | Dashboard and scheduled generated jobs carry channel voice and integrated writing instructions | Focused provider, schema, scheduler and API tests; installed-wheel resource preflight | Skill hashes, hook/title reports, validated package and review response | Live publishing; analytics retrieval; automatic use of unrelated skills |
| 3 | One real Codex Short reaches review and, after creative/source inspection, local rendering | Actual application job, signed-in review, 30–55s 1080×1920 output inspection | Exact source packet, invocation/tool provenance, dashboard evidence, ffprobe and visual/audio inspection | Remote upload; resetting old attempt allowances |

Work proceeds in order; report each acceptance result before the next phase.
A missing host deployment or authentication is an external blocker, not proof
of production success. Local preflight does not consume a Codex invocation.

## Acceptance evidence — 2026-10-11

Phase 1: **VERIFIED**. Eleven canonical skills, no `agent/skills` duplicate;
required resource inventory and real hook/title CLI execution passed. Skill
instructions now use project voice profiles and application review controls.

Phase 2: **VERIFIED**. The final focused regression batch passed **63 tests
in 318.86 seconds**, covering skills, host/direct Codex providers, schema,
configuration, scheduling, auth, worker leases/fencing and Shorts contracts.
The installed wheel resolves its own six selected resources and executes both
tools. At build time, every Python file in the installed host wheel matched source;
subsequent worker/render fixes are supplied by the source mounts. Six signed-in
Studio inline scripts pass Node syntax checking. Offline tool reports and
signed-in HTML use explicitly labelled synthetic fixture content; they are
not evidence of a real model response or browser interaction.

Phase 3: **BLOCKED** by the operator's explicit decision to leave final
rendering blocked. The host deployment, revised real Codex package, worker
handoff, source/creative inspection and signed-in Chromium review passed.
A new 40.663s 540×960 preview passed metadata and sampled-frame checks;
the operator confirmed clear and complete narration. Final 1080×1920 export
failed with a retained project Docker OOM event. The original verification
job remains `failed_exhausted` after three worker attempts. Two targeted
renderer repairs passed 12 focused checks and enabled the preview, but do
not prove final production quality. No further retry/memory change is made.

The original source packet exhausted two Codex attempts (restart interruption,
then rejected closing CTA); its counters were preserved. The operator approved
one revised brief, which generated valid content in 45.788s. Final provider
regression: 39 passed in 385.82s; existing API workflow: 8 passed in 828.52s;
legacy compatibility batch: 38 passed in 121.24s. Default voice fields preserve
v1–v4 worker/host cache keys. Installed host wheel SHA256:
`38ff4faeb5d55d34dcabffddf7bcc71a52c37e814d9ee8f17a4e3da9976daf70`.
Subsequent worker-only rejected-draft retention and render thread limits are
loaded from the source mounts. Host generation/scoring resources match the
installed wheel. Web, worker and scheduler were recreated with read-only
canonical skill mounts; public web `/healthz` confirms database health.

Retained local evidence (ignored):

- `artifacts/smoke/skills-integration/focused-tests.log`
- `artifacts/smoke/skills-integration/wheel-build.log`
- `artifacts/smoke/skills-integration/installed-wheel-preflight.json`
- `artifacts/smoke/skills-integration/syntax-and-wheel-inspection.json`
- `artifacts/smoke/skills-integration/offline-tool-report.json`
- `artifacts/smoke/skills-integration/offline-package.json`
- `artifacts/smoke/skills-integration/signed-in-studio.html`
- `artifacts/smoke/skills-integration/verification-request.json`
- `artifacts/smoke/skills-integration/host-preflight.json`
- `artifacts/wheels/tubeforge-0.1.0-py3-none-any.whl`

### Changed files and integration points

- All eleven `.agents/skills/*/SKILL.md` files: project-compatible voice and
  review instructions. Supporting Python/JSON resources are preserved.
- `AGENTS.md`, `readme.md`, `docs/STATUS.md`, `docs/SHORTS_WORKFLOW.md`,
  `docs/tubeforge-codex-runner-runtime.md`, this plan and
  `AUTONOMOUS_PROGRESS.md`: durable usage, deployment and acceptance records.
- `pyproject.toml`, `Dockerfile`, `compose.yaml`, `.gitignore`: wheel-shipped
  skills, read-only runtime mounts, runtime/test documentation and ignored
  deployment wheels. One canonical skill source installation remains.
- `config/default.yaml`, `config/production.yaml`,
  `config/production.example.yaml`: configured v5 prompt and profile guidance.
- `src/tubeforge/domain/contracts.py`, `core/config.py`, `db/repositories.py`: legacy cache-key compatibility, bounded hook options,
  channel identity/voice snapshots and validated profile configuration.
- `src/tubeforge/providers/content/youtube_skills.py`, `prompts.py`,
  `host_runner_protocol.py`, `host_runner.py`, `codex_cli.py`, and
  `src/tubeforge/host_codex_runner.py`: resource preflight/prompt embedding,
  real score/check execution, hook selection, hash handshake and provenance.
  The production factory still selects the existing isolated host provider.
- `src/tubeforge/core/runtime.py`, `scheduling/service.py`,
  `scheduling/main.py`: configured prompt/voice/format propagation with durable
  invalid-request handling before a topic reservation.
- `src/tubeforge/api/app.py`: channel selector/read API, schedule option
  propagation and pending/error states, script scene/metadata/tool review,
  and repaired preset dataset assignment.
- `src/tubeforge/pipeline/orchestrator.py`: durable generation provenance/usage
  checkpoint before content handoff; existing approval/ownership gates remain.
- `tests/test_youtube_skills.py`: focused resources, scoring/selection,
  preflight-counting, scheduler, host provenance and signed-in review coverage.

Content generation: **VERIFIED**. Preview rendering: **VERIFIED** at 540×960.
Final rendering: **BLOCKED** by the recorded OOM and operator decision.
Dashboard script review: **VERIFIED** in actual signed-in Chromium. Publishing:
**BLOCKED** under the existing milestone; no upload was attempted.

### Real acceptance follow-up

The revised Codex brief produced a grounded six-scene package in 45.788s;
real worker handoff reached script approval and signed-in script API returned
live scoring reports. Final provider regression: 39 passed in 385.82s.
Actual Chromium login and script review passed with no JavaScript page errors
and no mobile horizontal overflow. Screenshots retained at desktop/mobile
widths. Preview render failed: cgroup evidence recorded `oom_kill 1` at the
1GiB worker limit. FFmpeg filter and encoder threads were still automatic;
now both use the configured thread limit, preserving cancellation and atomic
promotion. Checkpointed preview retry and 12 renderer regressions subsequently passed. This adds
`src/tubeforge/rendering/preview.py` and `tests/test_shorts_workflow.py` to the
changed-file inventory. Narration WAV is 40.663s; the operator subsequently confirmed clear, complete
speech because this session does not support audio input.

Preview retry with bounded inputs reached `preview_ready`: 40.663s,
540×960, 30fps, H264/AAC, 48kHz mono. Six sampled frames inspected:
readable highlighted captions inside the safe area, no clipping or black
frames, varied abstract portrait graphics. Renderer regressions: 12 passed
in 15.91s. Actual final export was attempted after approval of exact preview
identity `d339cad8c787a280c75c67c527e210cfde328011b226f12d1cfac4cc8fe9c028`.
No publication approval was recorded.

Final acceptance record: `real-final-workflow.log`, `real-final-job.json`,
`project-oom-events.log`, `operator-audio-review.json`, and
`real-preview-inspection.json`. The operator explicitly selected "Leave final
rendering BLOCKED". Future continuation requires a new decision; preserve
this exhausted job and both source-packet invocation ledgers.

Final runtime verification: `docker compose ps web worker scheduler` confirms
all three services running. Deployed worker local preflight reports
`prompt=m6-content-v5`, six skill resources, `content_provider=codex`, without
invoking a model. `git diff --check` passes; `git check-ignore -v` confirms
browser/media evidence and deployment wheels are ignored. No release-wide
full-suite claim is made; this delivery used the recorded focused regressions
and real application artifact/browser checks.
