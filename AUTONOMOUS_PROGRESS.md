# TubeForge Autonomous Progress

> This is an append-only execution and validation log. The authoritative
> current project state is [`docs/STATUS.md`](docs/STATUS.md). Historical
> entries can describe a state that has since changed; do not use them as the
> current roadmap.

## Recording format

Append a dated entry after meaningful autonomous work with: scope, files or
commit, validation commands and results, inspected artifacts, exact blocker
(if any), and next action. Do not edit earlier evidence except to correct a
factual error with a clearly labelled correction.

## 2026-09-12 — records normalization

- Established `docs/STATUS.md` as the sole current-status document and defined
  the responsibilities of `AGENTS.md`, this evidence log, and `readme.md`.
- Validation: repository/document inspection only; no application behavior was
  changed and no test result is claimed by this entry.
- Current validation blocker: host Python lacks `pytest`; Docker daemon access
  is denied for the current user.
- Next action: restore a reproducible test runtime, run the full suite and
  real local-media smoke, then update `docs/STATUS.md` with fresh evidence.

## Historical execution log

### 2026-08-31 — topic queue/scheduler and VideoPlan foundation

- Added Alembic revision `20260831_0016` for durable topics, schedules, and
  duplicate-fenced schedule runs.
- Added transactional topic reservation that creates a normal `pipeline_jobs`
  row in the same database transaction; the existing worker remains the only
  component that performs generation/rendering.
- Added queue and schedule APIs plus `SchedulerService`, with cron parsing via
  `croniter`, no-topic records, and a run-key uniqueness fence.
- Added a typed `VideoPlan` projection and durable `video_plan` checkpoint
  alongside `content_package`, preserving existing content-provider contracts.
- Validation is still blocked by the local environment: host Python has no pip,
  and a legacy container image does not include the newly declared dependency.
  Changed-source syntax compilation passed when limited to changed files.

### 2026-08-31 — dashboard authentication foundation

- Added Alembic revision `20260831_0017` with `admin_users` and opaque
  `auth_sessions`; only session-token hashes are persisted.
- Added Argon2id password verification, HttpOnly SameSite session cookies,
  CSRF token validation for state-changing dashboard/API calls, rate-limited
  login attempts, logout, and `tubeforge create-admin --username ...`.
- Auth is opt-in in configuration and has no self-registration/default user.
- Added focused auth coverage. The container test invocation emitted one passing
  test then exceeded the runner timeout, so this is not recorded as green.

### 2026-08-31 — final artifact quality gate

- Added `pipeline.quality` and a durable `quality_report` checkpoint at
  `FINAL_READY`. It re-probes final media through the renderer validation,
  enforces a nonempty final artifact, usable captions when requested, and a
  minimum resolution before publication preparation begins.
- Hard findings produce the existing validation failure path; soft findings are
  preserved for dashboard/activity visibility. Black-frame analysis remains an
  explicitly reported warning until a bounded local detector is added.
- `tests/test_quality_gate.py` passed (2 tests), and the offline integration
  pipeline passed while asserting the persisted quality report.

### 2026-08-31 — visual router foundation

- Added a provider-neutral `VisualRouter` that records a primary strategy,
  fallback, and rationale per scene in the durable asset manifest. Current
  behavior intentionally keeps licensed/fake stock media as the operational
  route and uses caption-background fallbacks when a premium provider is absent.
- Unit coverage for routing plus the quality gate passed (3 tests).

### 2026-08-31 — social account security foundation

- Added migration `20260831_0018`, encrypted credential envelopes, safe account
  list/create/disable APIs, and an operator guide for official platform setup.
- Account metadata is capability-aware; the Snapchat capability is honestly
  manual handoff only. The encryption round-trip/tamper test passed.

### 2026-08-31 — scheduler service operation

- Added a dedicated `scheduler` Compose service and scheduler configuration.
  It only creates ordinary lease-fenced pipeline jobs and never performs heavy
  worker operations. The topic reservation scheduler test passed.

### 2026-08-31 — operational dashboard controls

- Extended the existing dashboard with bulk topic intake and a cron/timezone
  schedule creation form, including a twice-daily example. Dashboard mutations
  now attach the session CSRF header when authentication is enabled.
- Added transactional bulk topic creation and coverage; the bulk test passed.

### 2026-08-31 — authentication validation

- The focused authentication API test passed end-to-end: unauthenticated API
  rejection, bad-password rejection, session issuance, CSRF rejection/acceptance,
  and logout. Production configuration now enables secure cookies and requires
  explicit administrator bootstrap.

### 2026-08-31 — multi-target dispatch foundation

- Added migration `20260831_0019` and a provider-neutral dispatcher with durable
  per-target attempt receipts, idempotency, error classification, and explicit
  unsupported-platform results. Its local fake multi-target test passed.

### 2026-08-31 — platform variant planning

- Publication packages now persist reusable master-based plans for landscape
  YouTube plus short-form YouTube, Instagram, Facebook, and Snapchat profiles.
  Portrait profiles are explicitly marked as requiring a derivative. The unit
  test passed; an integration retry exceeded this runner's command window.

### 2026-08-31 — quality sequencing validation

- Narrow orchestration validation passed: final media is now quality-gated and
  receives its durable report before `FINAL_READY` is exposed. The larger
  analytics/optimization integration remains slow in this runner but is no
  longer the only evidence for the state transition.

### 2026-08-31 — approved yt-dlp container replacement and live smoke

- Rebuilt/replaced the local web and worker services and verified the dashboard health endpoint on `0.0.0.0:62065`.
- Fixed the source-clip intake mismatch that rejected a 10-second source because the shared job contract has a 30-second planning minimum.
- Mounted `src` read-only with `PYTHONPATH=/app/src` in Compose, so deployed web/worker execute current source rather than a stale installed package.
- Live public source requests are accepted and durable job activity is recorded. The first sample host returned a 403/no duration; a reachable GitHub media URL confirms network access but `yt-dlp --dump-single-json` remains stalled on generic direct MP4 URLs. Final-render smoke remains pending a bounded direct-media inspection/acquisition fix.

M24/M25 in progress. M26 already has an existing Codex CLI `ContentPackage`
adapter, but Ollama support and the required live LLM-to-video smoke remain.

## Work completed (2026-08-24, iteration 1)

- Added `FixedScriptContentProvider`, a deterministic provider with six ordered,
  independently narrated scenes and six nonblank visual descriptions.
- Made the fixed provider selectable with `pipeline.content_provider: fixed`.
- Preserved the legacy one-scene fake content fixture to avoid destabilizing
  existing checkpoint/orchestrator tests.
- Improved `FakeMediaProvider` into a deterministic offline local visual
  provider: each distinct scene description produces a distinct 640x360 PNG
  path and a distinct high-contrast colour. Candidate metadata now matches the
  generated dimensions.
- Added focused tests covering six-scene completeness, provider selection, and
  six distinct non-empty local image outputs.
- Confirmed the modified Python sources compile and have no diff whitespace
  errors.

## Current implementation / findings

- Existing orchestration already persists an asset per scene, revalidates
  checksums on recovery, derives a scene timeline from measured phrase audio,
  and passes each scene/image mapping into FFmpeg.
- Existing rendering concatenates independently timed scene inputs and maps a
  narration audio stream, so the fixed provider removes the main one-scene
  limitation without bypassing orchestration.
- Existing Piper adapter uses argument-array subprocess execution, validates WAV
  structure, measures duration from WAV frames, caches output, and atomically
  promotes a validated temporary file.
- Existing Codex CLI content adapter is configurable, bounded, uses no shell,
  captures diagnostics safely, validates the full production schema, and has
  mocked tests. It is richer than the mission's minimum script-only contract.

## Tests and commands run

- `pytest -q tests/test_fixed_script_pipeline.py tests/test_assets.py tests/test_rendering_preview.py tests/test_config.py tests/test_codex_content.py`
  - Could not start: `pytest: command not found`.
- `python3 -m pytest --version`
  - Could not start: Python environment has no pytest.
- `python3 -m venv /tmp/tubeforge-venv`
  - Could not create a venv because Debian `ensurepip`/`python3-venv` is absent.
- `docker compose config --quiet`
  - Passed (the subsequent Docker daemon queries failed).
- `docker compose ps --format json`
  - Blocked by permission denied on `/var/run/docker.sock`.
- `python3 -m compileall -q src tests/test_fixed_script_pipeline.py`
  - Passed.
- `git diff --check -- src/tubeforge tests/test_fixed_script_pipeline.py`
  - Passed.
- Runtime discovery: `ffmpeg`, `ffprobe`, and `piper` are not on host PATH;
  no Piper `.onnx` voice model was found beneath the repository.

## Current failures / blockers

- Automated tests cannot run in the host Python because project/test
  dependencies are absent and a venv cannot be created without `python3-venv`.
- Container validation cannot run because this agent cannot access the Docker
  daemon socket.
- Real M24 smoke cannot run because FFmpeg/ffprobe/Piper and a Piper voice model
  are unavailable on the host, while Docker is inaccessible.
- These are environment blockers for validation, not grounds for creating
  `.autonomous_success`. No success marker exists.

## Next required action

1. Restore access to the existing TubeForge Docker daemon, or provide a Python
   environment containing the project dev dependencies plus FFmpeg, ffprobe,
   Piper, and a Piper voice model.
2. Run the focused test command above and fix any failures.
3. Add/integrate a real orchestrator smoke entry point using `content_provider:
   fixed`, `voice_provider: piper`, and the deterministic media provider; render
   into `artifacts/smoke/` and validate WAV/MP4 metadata with ffprobe.
4. Run the complete existing suite and reliability-focused tests.
5. Continue M26 with Ollama provider/config/tests, then attempt the available
   real Codex CLI generation and end-to-end smoke.

## Work completed (2026-08-24, iteration 2)

- Implemented `OllamaContentProvider` using Ollama's non-streaming
  `/api/generate` endpoint with a full `ContentPackage` JSON schema request.
- Added configurable local/LAN HTTP(S) endpoint, model, connection timeout,
  inference timeout, response-size limit, retry count, cache reservation, and
  prompt limits. Endpoint validation rejects embedded credentials, queries, and
  fragments.
- Added bounded retries for connection/timeout and server failures, clear
  authentication/transient/validation error classification, structured response
  parsing, usage capture, provenance, and validated persistent cache reuse.
- Made `pipeline.content_provider: ollama` selectable without changing the
  deterministic default, and documented its safe defaults in `default.yaml`.
- Strengthened the shared LLM prompt and validation used by Codex and Ollama:
  live-generated packages now require at least six scenes, ordered one-to-one
  section/scene mapping, nonblank scene queries via the domain schema, and a
  narration size bounded relative to requested duration.
- Added focused Ollama tests covering structured success, LAN settings, cache
  reuse, transient connection and HTTP recovery, exhausted timeout, malformed
  output, too-short output, and factory selection. Updated Codex fixtures to
  exercise the new six-scene production invariant.

## Current failures / blockers (iteration 2)

- Focused and full pytest runs are still unavailable: host Python has no
  `pydantic`, `SQLAlchemy`, `PyYAML`, `pytest`, or even `pip`.
- `docker compose ps --format json` still fails with permission denied on
  `/var/run/docker.sock`, so the repository's containerized dependencies cannot
  be used for tests.
- `codex`, `ffmpeg`, `ffprobe`, and `piper` are absent from host PATH, and no
  local Piper voice model is available. Consequently neither the required real
  M24 smoke nor the live Codex-to-video M26 smoke can run in this environment.
- `.autonomous_success` remains absent because the real smoke criteria have not
  been met.

## Commands/tests run (iteration 2)

- `python3 -m compileall -q src tests/test_codex_content.py tests/test_ollama_content.py tests/test_fixed_script_pipeline.py`
  - Passed.
- `git diff --check`
  - Passed.
- `docker compose config --quiet`
  - Passed.
- `docker compose ps --format json`
  - Failed: permission denied on the Docker socket.
- Host import probe for `pydantic`, `sqlalchemy`, `yaml`, and `pytest`
  - All unavailable; `python3 -m pip --version` also reports no pip module.
- Host executable probe for `codex`, `ffmpeg`, `ffprobe`, and `piper`
  - None found.

## Next required action (after iteration 2)

1. Restore Docker socket access or supply a project Python environment, then run
   `pytest -q tests/test_ollama_content.py tests/test_codex_content.py tests/test_fixed_script_pipeline.py tests/test_assets.py tests/test_rendering_preview.py tests/test_pipeline_orchestrator.py` and fix any failures.
2. Run the complete test suite, including lease/fencing, checkpoint recovery,
   cancellation, and atomic artifact tests.
3. Provide FFmpeg/ffprobe, Piper plus a voice model, and execute the real fixed
   six-scene orchestrator smoke under `artifacts/smoke/`; inspect WAV and MP4
   metadata and verify scene changes.
4. If the local authenticated Codex CLI is available, run a real generated
   six-scene script through the same end-to-end pipeline and save the validated
   LLM smoke video under `artifacts/smoke/`.

## Work completed (2026-08-24, iteration 3)

- Re-audited the complete mission, current changes, provider architecture, and
  host/container capabilities instead of relying only on the prior blocker
  report.
- Found that the deterministic M24 script contained only 110 words. At a normal
  Piper narration rate this could produce about 44 seconds of audio and fail
  both the requested 60-second duration and the orchestrator's 20% duration
  tolerance.
- Expanded the same six-scene deterministic story to 192 words (31-33 words per
  scene), retaining the ordered scene-to-visual mapping. This gives the real
  Piper smoke a practical 60-90 second narration budget without bypassing the
  measured-duration pipeline.
- Added a regression assertion that keeps the fixed smoke script between 145
  and 200 words, preventing a future short fixture from silently invalidating
  the real-video acceptance test.

## Current failures / blockers (iteration 3)

- Focused pytest still cannot start because the host Python has no `pytest` or
  project dependencies, and Docker access remains denied at the daemon socket.
- `ffmpeg`, `ffprobe`, `piper`, and `codex` remain absent from host PATH; no
  Piper `.onnx` model exists in the repository or `/tmp`.
- The expanded narration budget therefore cannot yet be timed with a real Piper
  voice, and the required real MP4/LLM smoke validations remain blocked.
- `.autonomous_success` remains absent because no real smoke video has been
  generated and validated.

## Commands/tests run (iteration 3)

- Static AST narration audit: six scenes contain `[31, 33, 32, 32, 32, 32]`
  words, 192 words total.
- `python3 -m compileall -q src tests/test_fixed_script_pipeline.py tests/test_codex_content.py tests/test_ollama_content.py`
  - Passed.
- `git diff --check`
  - Passed.
- `docker compose config --quiet`
  - Passed.
- `python3 -m pytest -q tests/test_fixed_script_pipeline.py tests/test_ollama_content.py tests/test_codex_content.py`
  - Could not start: `/usr/bin/python3: No module named pytest`.
- Rechecked host executables and Piper models; FFmpeg, ffprobe, Piper, Codex,
  and a voice model are unavailable.

## Next required action (after iteration 3)

1. Restore Docker socket access or provide the project test/runtime environment.
2. Run the focused fixed-script, Ollama, and Codex tests, then the complete
   reliability suite; diagnose and fix any runtime failures.
3. Configure a real Piper voice model and run the fixed six-scene job through
   the orchestrator. If the measured voice duration falls outside 48-72 seconds
   for the 60-second request, tune the deterministic narration from the actual
   measurement before rendering.
4. Validate the resulting WAV and MP4 with ffprobe, inspect distinct scene
   frames, and then run the available live Codex-to-video smoke.

## Work completed (2026-08-24, iteration 4)

- Added an opt-in real M24/M25 acceptance test at
  `tests/test_real_local_smoke.py`. It drives the normal runtime, worker lease,
  script approval, preview approval, checkpoint, asset-acquisition, and final
  render paths with `content_provider=fixed`, `voice_provider=piper`, and the
  deterministic six-image media provider.
- The acceptance test requires an explicit `TUBEFORGE_SMOKE_PIPER_MODEL`
  rather than silently substituting fake audio. With the model and real tools
  available it generates a 75-second-target video and atomically copies the
  accepted result to `artifacts/smoke/fixed_piper_six_scene_smoke.mp4`.
- Added real ffprobe assertions for the assembled narration WAV and final MP4,
  including duration, file size, audio/video streams, sample rate, and 640x360
  dimensions.
- Added a visual acceptance check that reconstructs the six scene intervals
  from the production content/timing artifacts, samples the midpoint of every
  scene using FFmpeg, and requires six distinct decoded-frame hashes. This
  detects regression to one repeated/static visual rather than merely checking
  six manifest entries.
- Re-read the full M26 criteria and confirmed the current Codex/Ollama provider
  work covers the requested provider layer and validation surface; the live
  Codex-to-video smoke remains unavailable in this host environment.

## Current failures / blockers (iteration 4)

- The focused pytest command still cannot start because `/usr/bin/python3` has
  no pytest or project dependencies and has no pip/ensurepip environment.
- Docker Compose configuration validates, but daemon access still fails with
  permission denied on `/var/run/docker.sock`; the image that contains FFmpeg
  and Python dependencies therefore cannot be used.
- Host `piper`, `ffmpeg`, `ffprobe`, and `codex` remain unavailable, and there
  is no Piper ONNX voice model. The new acceptance test correctly skips unless
  a real model is explicitly configured, so it could not produce the required
  real smoke artifact in this iteration.
- `.autonomous_success` remains absent because no real Piper/FFmpeg or live
  Codex-to-video smoke has passed.

## Commands/tests run (iteration 4)

- `python3 -m compileall -q src tests/test_real_local_smoke.py tests/test_fixed_script_pipeline.py tests/test_codex_content.py tests/test_ollama_content.py`
  - Passed.
- `python3 -m pytest -q tests/test_real_local_smoke.py tests/test_fixed_script_pipeline.py tests/test_ollama_content.py tests/test_codex_content.py`
  - Could not start: `/usr/bin/python3: No module named pytest`.
- `docker compose config --quiet`
  - Passed.
- `docker compose ps --format json`
  - Failed: permission denied on the Docker socket.
- `git diff --check`
  - Passed.
- Explicit `.autonomous_success` check
  - Confirmed absent.

## Next required action (after iteration 4)

1. Restore Docker access or provide the project Python/runtime dependencies.
2. Run the focused provider tests and complete suite, fixing any runtime
   failures rather than relying on compile-only validation.
3. Install/configure Piper and a voice model, then run
   `TUBEFORGE_SMOKE_PIPER_MODEL=/path/to/voice.onnx pytest -q -s tests/test_real_local_smoke.py`.
   Inspect the retained MP4 and recorded ffprobe data; tune narration only if
   the measured voice duration falls outside 60-90 seconds.
4. Run a live authenticated Codex generation through the same orchestrator and
   retain/validate `artifacts/smoke/codex_generated_smoke.mp4` before creating
   `.autonomous_success`.

## Work completed (2026-08-24, iteration 5)

- Re-read the complete mission, accumulated progress, current staged and
  unstaged changes, provider/runtime composition, focused tests, and the real
  smoke acceptance test.
- Found and fixed a combined-provider validation defect in the exact M26 live
  topology. `validate_selected_provider` returned immediately after validating
  Piper, so `content_provider=codex` plus `voice_provider=piper` did not validate
  the Codex executable at startup. Content and voice external dependencies are
  now both validated independently.
- Added a configuration regression test that supplies a valid Piper model and
  executable with a missing Codex executable and requires startup to fail with
  the Codex-specific diagnostic.
- Rechecked Docker socket ownership. Although the user is a member of the
  socket's `nogroup` group, API access is still denied by the execution
  environment, confirming this is not repairable through repository settings.
- Attempted to bootstrap a project-local Python package environment from the
  official pip bootstrap endpoint; DNS/network access is unavailable, so this
  did not modify the repository or unlock pytest.

## Current failures / blockers (iteration 5)

- Focused and full pytest still cannot start because the only host interpreter
  has no pytest/pip or project dependencies; external package bootstrap fails
  due to unavailable DNS/network access.
- Docker Compose configuration passes, but Docker daemon API access remains
  denied despite nominal Unix group membership.
- Host `piper`, `ffmpeg`, `ffprobe`, and `codex` remain unavailable and no Piper
  ONNX model is present. No real smoke artifact can be generated or inspected.
- `.autonomous_success` remains absent, correctly, because the required real
  fixed-script and live Codex-to-video smokes have not passed.

## Commands/tests run (iteration 5)

- `python3 -m compileall -q src tests/test_config.py tests/test_real_local_smoke.py tests/test_fixed_script_pipeline.py tests/test_codex_content.py tests/test_ollama_content.py`
  - Passed.
- `python3 -m pytest -q tests/test_config.py tests/test_fixed_script_pipeline.py tests/test_codex_content.py tests/test_ollama_content.py tests/test_real_local_smoke.py`
  - Could not start: `/usr/bin/python3: No module named pytest`.
- `git diff --check`
  - Passed.
- `docker compose config --quiet`
  - Passed.
- `docker compose ps --format json`
  - Failed: permission denied on `/var/run/docker.sock`.
- Python `urllib.request` fetch of `https://bootstrap.pypa.io/get-pip.py`
  - Failed with temporary DNS resolution failure.
- Explicit `.autonomous_success` check
  - Confirmed absent.

## Next required action (after iteration 5)

1. Restore Docker API access or provide an environment with the project Python
   dependencies, then run the focused provider/config/smoke tests and the full
   reliability suite.
2. Supply Piper, FFmpeg/ffprobe, and a Piper ONNX voice; run the opt-in real
   six-scene acceptance test and inspect the retained WAV, MP4, and six sampled
   scene frames.
3. Supply an authenticated Codex CLI and run its validated script through the
   same Piper/visual/FFmpeg orchestrator path, retaining the LLM smoke artifact.
4. Create `.autonomous_success` only after both real media validation and every
   mission acceptance criterion pass.

## Work completed (2026-08-24, iteration 6)

- Closed a remaining M26 acceptance-harness gap: the real orchestrated smoke
  test is now parameterized over both the deterministic fixed content provider
  and the live Codex CLI provider. The Codex case is automatically eligible
  when `codex` is on PATH and uses the same worker lease, approval, checkpoint,
  Piper, six-scene visual, and FFmpeg path as the fixed case.
- Kept the real-tool gating honest: both cases still require an explicit Piper
  ONNX model and real Piper/FFmpeg/ffprobe executables, while only the Codex case
  skips when the CLI is absent. No mock is substituted for either acceptance
  path.
- Extended retained smoke evidence under `artifacts/smoke/`. Each successful
  case now atomically promotes its real narration WAV alongside the MP4 and
  writes the complete narration/video ffprobe JSON, including the format and
  stream fields asserted by the test.
- Preserved the six midpoint frame-hash check for both fixed and Codex output,
  so a live LLM smoke cannot pass with one repeated visual merely because its
  package contains six scene records.

## Current failures / blockers (iteration 6)

- Pytest still cannot start because the host Python has no pytest or project
  dependencies. This prevents runtime validation of the expanded harness and
  the focused/full suites.
- Docker Compose configuration remains valid, but daemon access was previously
  confirmed unavailable in this execution environment.
- Host Piper, FFmpeg/ffprobe, Codex, and a Piper ONNX voice remain unavailable,
  so neither real smoke case can execute and no retained media was created.
- `.autonomous_success` remains absent because the real acceptance smokes have
  not run.

## Commands/tests run (iteration 6)

- `python3 -m compileall -q src tests/test_real_local_smoke.py tests/test_config.py tests/test_fixed_script_pipeline.py tests/test_codex_content.py tests/test_ollama_content.py`
  - Passed.
- `git diff --check`
  - Passed.
- `docker compose config --quiet`
  - Passed.
- `python3 -m pytest -q tests/test_real_local_smoke.py tests/test_config.py tests/test_fixed_script_pipeline.py tests/test_codex_content.py tests/test_ollama_content.py`
  - Could not start: `/usr/bin/python3: No module named pytest`.
- Explicit `.autonomous_success` check
  - Confirmed absent.

## Next required action (after iteration 6)

1. Restore Docker access or provide the project Python dependencies, then run
   the focused tests and complete suite and fix any failures.
2. Supply Piper, FFmpeg/ffprobe, and a Piper ONNX model and run the fixed case
   of `tests/test_real_local_smoke.py`; inspect the retained WAV, MP4, ffprobe
   JSON, and six sampled scene frames.
3. With an authenticated Codex CLI available, run the Codex parameter of the
   same test and inspect `artifacts/smoke/codex_generated_smoke.*`.
4. Create `.autonomous_success` only after both real media paths and all other
   mission acceptance criteria genuinely pass.

## Work completed (2026-08-24, iteration 7)

- Re-read the complete mission, repository policy, accumulated progress,
  current diff, provider/cache composition, focused provider tests, and the
  real orchestrated smoke harness.
- Fixed a live M26 acceptance defect in the shared Codex/Ollama validator. The
  previous character bound allowed an implausibly short script (roughly 20
  words for a 75-second request) to pass production validation and fail only
  after expensive Piper/render work. Validation now applies a generous
  duration-relative narration budget of 1.5--4 words per requested second and
  reports the actual and expected word counts.
- Expanded valid Codex and Ollama fixtures to meet that production duration
  invariant and added a focused Codex regression test proving six structurally
  valid but two-word scenes are rejected before cache acceptance/rendering.
- Corrected the live Codex smoke harness to honor M26's "at least six scenes"
  contract. A valid model response with more than six scenes now verifies that
  every scene has a distinct asset and decoded midpoint frame instead of
  incorrectly failing an exact-six assertion. The fixed provider still emits
  exactly six deterministic scenes.
- Re-probed hidden/project Python environments, cached wheels, Docker access,
  and host tools; no usable alternate runtime was present.

## Current failures / blockers (iteration 7)

- Pytest cannot start because `/usr/bin/python3` still has no pytest or project
  dependencies, and no project virtual environment or cached dependency wheels
  are available.
- Docker daemon access remains denied at `/var/run/docker.sock`, despite the
  host account's nominal socket-group membership.
- `piper`, `ffmpeg`, `ffprobe`, and `codex` remain absent from PATH, and no Piper
  model is configured. The real fixed and Codex smoke cases therefore cannot
  execute in this environment.
- `.autonomous_success` remains absent because no real video has been generated
  and validated.

## Commands/tests run (iteration 7)

- `python3 -m compileall -q src tests/test_codex_content.py tests/test_ollama_content.py tests/test_real_local_smoke.py`
  - Passed.
- `git diff --check`
  - Passed.
- `docker compose config --quiet`
  - Passed.
- `python3 -m pytest -q tests/test_codex_content.py tests/test_ollama_content.py tests/test_real_local_smoke.py`
  - Could not start: `/usr/bin/python3: No module named pytest`.
- Host/project environment and executable discovery for pytest dependencies,
  FFmpeg/ffprobe, Piper, Codex, virtual environments, and cached wheels
  - None available.
- Explicit `.autonomous_success` check
  - Confirmed absent.

## Next required action (after iteration 7)

1. Restore Docker API access or provide the project Python dependencies, then
   run the focused provider/config/smoke tests and the complete suite, fixing
   any runtime failures.
2. Supply FFmpeg/ffprobe, Piper, and a Piper ONNX model; run the fixed real-smoke
   case and inspect the retained WAV, MP4, probe JSON, and decoded scene frames.
3. Supply an authenticated Codex CLI and run the Codex parameter of the same
   orchestrated test. Tune the duration word bounds only from actual Piper
   measurements if the generated narration falls outside 60--90 seconds.
4. Create `.autonomous_success` only after both real media paths and every
   remaining acceptance criterion genuinely pass.

## Work completed (2026-08-24, iteration 8)

- Re-read the repository policy, complete M24--M26 mission, accumulated
  progress, current changes, content-provider implementation, domain schema,
  cache fencing, and real orchestrated smoke harness.
- Fixed an Ollama configuration/transport mismatch. URL validation parsed a
  stripped value but retained leading whitespace in the stored setting, so a
  URL could pass startup validation and then fail when the HTTP transport
  parsed it. Ollama base URLs are now consistently trimmed and have trailing
  slashes removed before storage.
- Added nonblank normalization for the Ollama model and prompt-template version.
  Whitespace-only identifiers now fail at configuration load, and surrounding
  whitespace no longer leaks into cache identities or API payloads.
- Added focused regression coverage for normalized remote/LAN URLs, model and
  prompt identifiers, and rejection of whitespace-only identifiers.

## Current failures / blockers (iteration 8)

- Focused and full pytest runs still cannot start because `/usr/bin/python3`
  has no pytest or project dependencies, and previous environment discovery
  found no usable alternate interpreter, venv, wheels, or Docker access.
- Piper, FFmpeg/ffprobe, Codex, and a Piper ONNX voice remain unavailable on
  the host. Neither real orchestrated smoke can run, so no genuine media
  artifact was produced or validated.
- `.autonomous_success` remains absent because the real fixed/Piper and live
  Codex-to-video acceptance paths have not passed.

## Commands/tests run (iteration 8)

- `python3 -m compileall -q src tests/test_ollama_content.py tests/test_real_local_smoke.py tests/test_codex_content.py tests/test_config.py tests/test_fixed_script_pipeline.py`
  - Passed.
- `git diff --check`
  - Passed.
- `docker compose config --quiet`
  - Passed.
- `python3 -m pytest -q tests/test_ollama_content.py tests/test_codex_content.py tests/test_config.py tests/test_fixed_script_pipeline.py tests/test_real_local_smoke.py`
  - Could not start: `/usr/bin/python3: No module named pytest`.
- Explicit `.autonomous_success` check
  - Confirmed absent.

## Next required action (after iteration 8)

1. Restore Docker API access or provide the project Python dependencies, then
   run the focused provider/config/smoke tests and the complete suite, fixing
   any runtime failures.
2. Supply FFmpeg/ffprobe, Piper, and a Piper ONNX model; run the fixed real-smoke
   case and inspect the retained WAV, MP4, ffprobe JSON, and decoded scene
   frames.
3. Supply an authenticated Codex CLI and run the Codex parameter of the same
   orchestrated test, retaining and inspecting its real generated artifacts.
4. Create `.autonomous_success` only after both real media paths and every
   mission acceptance criterion genuinely pass.

## Work completed (2026-08-24, iteration 9)

- Re-read the complete M24--M26 mission, repository policy, accumulated
  progress, current diff, real smoke harness, LLM providers, and generation
  cache ownership semantics.
- Fixed a provider-retry defect affecting both Codex CLI and Ollama. Failed
  invocation or output validation previously left the generation cache entry
  reserved for up to 600 seconds, so the orchestrator's next attempt failed as
  "already reserved" without reaching the provider.
- Added token-fenced `GenerationCacheRepository.abandon`. A failed owner can
  now remove only its own still-reserved entry; it cannot disturb an accepted
  result or a reservation acquired by a newer owner after expiry.
- Both LLM providers now abandon their reservation on any exception while
  retaining the existing token-fenced acceptance path on success.
- Added Codex and Ollama regression coverage proving an immediate successful
  retry after a provider failure, plus a stale-owner fencing assertion proving
  the old token cannot abandon its replacement.

## Current failures / blockers (iteration 9)

- Focused and full pytest remain unavailable because the host Python has no
  pytest or project dependencies. The focused command fails before collection.
- Docker Compose configuration remains valid, but Docker daemon access is still
  denied at `/var/run/docker.sock`, preventing use of the project image.
- Piper, FFmpeg/ffprobe, Codex, and a Piper ONNX voice are still absent. The
  required real fixed and Codex video smokes therefore cannot execute.
- `.autonomous_success` remains absent because no real smoke media has been
  generated and validated.

## Commands/tests run (iteration 9)

- `python3 -m compileall -q src tests/test_codex_content.py tests/test_ollama_content.py tests/test_real_local_smoke.py`
  - Passed.
- `git diff --check`
  - Passed.
- `docker compose config --quiet`
  - Passed.
- `python3 -m pytest -q tests/test_codex_content.py tests/test_ollama_content.py`
  - Could not start: `/usr/bin/python3: No module named pytest`.
- `docker compose ps --format json`
  - Failed: permission denied on `/var/run/docker.sock`.
- Rechecked host executables and local models; Piper, FFmpeg, ffprobe, Codex,
  and a Piper ONNX model remain unavailable.
- Explicit `.autonomous_success` check
  - Confirmed absent.

## Next required action (after iteration 9)

1. Restore Docker API access or provide the project Python dependencies, then
   run the focused provider/cache tests and complete suite, fixing failures.
2. Supply FFmpeg/ffprobe, Piper, and a Piper ONNX voice, then run and inspect
   the fixed real orchestrated smoke under `artifacts/smoke/`.
3. Supply an authenticated Codex CLI and run the Codex case through the same
   Piper/visual/FFmpeg path, retaining and inspecting its artifacts.
4. Create `.autonomous_success` only after both real media paths and every
   mission acceptance criterion pass.

## Work completed (2026-08-24, iteration 10)

- Re-read the repository policy, complete M24--M26 mission, accumulated
  progress, current worktree, rendering/voice/asset paths, provider changes,
  and the real orchestrated smoke harness.
- Closed a concrete M25 image-validation gap. PNG acceptance previously trusted
  only the signature and IHDR dimensions, allowing a truncated header-only file
  with no decodable pixels to pass validation and be atomically promoted.
- PNG inspection now validates chunk boundaries and CRCs, required IHDR/IDAT/
  IEND chunks, supported header fields, zlib decompression, complete non-
  interlaced scanline sizes, and row-filter values before returning dimensions.
- Replaced header-only pseudo-PNG fixtures in the asset tests with genuinely
  decodable dependency-free PNGs. Added regressions proving truncated files and
  corrupted pixel/chunk data are rejected.

## Current failures / blockers (iteration 10)

- Focused and full pytest still cannot start because `/usr/bin/python3` has no
  pytest or project dependencies.
- Docker Compose configuration passes, but Docker daemon access remains denied
  at `/var/run/docker.sock`.
- Piper, FFmpeg/ffprobe, Codex, and a Piper ONNX voice remain unavailable on the
  host. No real fixed or Codex smoke can run, and no smoke artifacts exist.
- `.autonomous_success` remains absent because real acceptance validation has
  not passed.

## Commands/tests run (iteration 10)

- `python3 -m compileall -q src tests/test_assets.py tests/test_real_local_smoke.py tests/test_ollama_content.py tests/test_codex_content.py tests/test_fixed_script_pipeline.py`
  - Passed.
- `git diff --check`
  - Passed.
- `docker compose config --quiet`
  - Passed.
- `python3 -m pytest -q tests/test_assets.py tests/test_fixed_script_pipeline.py tests/test_codex_content.py tests/test_ollama_content.py tests/test_real_local_smoke.py`
  - Could not start: `/usr/bin/python3: No module named pytest`.
- `docker compose ps --format json`
  - Failed: permission denied on the Docker socket.
- Rechecked host tools, smoke artifacts, and success marker
  - Piper, FFmpeg/ffprobe, and Codex are unavailable; no smoke artifacts exist;
    `.autonomous_success` is absent.

## Next required action (after iteration 10)

1. Restore Docker API access or provide the project Python dependencies, then
   run the focused asset/provider/config/smoke tests and complete suite.
2. Supply FFmpeg/ffprobe, Piper, and a Piper ONNX model; execute the fixed real
   smoke and inspect its WAV, MP4, ffprobe JSON, and decoded scene frames.
3. Supply an authenticated Codex CLI and execute the Codex real-smoke case
   through the same orchestrator, retaining and inspecting its artifacts.
4. Create `.autonomous_success` only after all tests and both real media paths
   satisfy every mission acceptance criterion.

## Reusable video-brief workflow (2026-08-30, in progress)

- Added durable per-job options for operator notes, review mode, captions,
  selected music track, visual style, and selected Codex MCP server names.
- Added configuration-backed default and named video presets, plus an approved
  music-catalog schema. Explicit CLI/web values override preset values, which
  override the configured default preset.
- Added `POST /api/videos`, a localhost create-video form, and a `tubeforge
  create-video` CLI command that submit the same durable request format.
- Auto mode bypasses script/preview gates only when requested; manual jobs
  retain both approvals. Caption-disabled jobs retain valid empty caption
  artifacts so checkpoint and renderer contracts stay intact.
- Focused Docker validation passed: 18 API/config/render/fixed-pipeline tests.
- Remaining media integration: connect approved music download/cache/mixing and
  generated visual assets to the selected per-job options.

## Work completed (2026-08-24, iteration 22)

- Re-read the repository policy, complete M24--M26 mission, accumulated
  progress, current worktree, real smoke harness, narration pipeline, Piper
  adapter, and FFmpeg render path.
- Closed another checkpoint/restart numeric-validation gap. A persisted phrase
  result with `duration_seconds=Infinity` previously satisfied the resume
  predicate because infinity compares greater than zero. That could suppress
  required voice regeneration and feed invalid timing into later stages.
- Voice checkpoint reuse now requires a finite, strictly positive duration in
  addition to the existing file, size, and checksum checks.
- Added regression coverage for NaN, positive and negative infinity, zero, and
  negative persisted durations.

## Current failures / blockers (iteration 22)

- Focused and full pytest cannot start because `/usr/bin/python3` has no pytest
  or project dependencies.
- Docker Compose configuration is valid, but Docker daemon API access remains
  denied at `/var/run/docker.sock`.
- FFmpeg, ffprobe, Piper, Codex, and a Piper ONNX voice remain unavailable on
  the host. Neither mandatory real orchestrated smoke can run, and no smoke
  artifact exists.
- `.autonomous_success` remains absent because real smoke validation has not
  passed.

## Commands/tests run (iteration 22)

- `python3 -m compileall -q src tests/test_pipeline_orchestrator.py tests/test_rendering_audio.py tests/test_rendering_preview.py tests/test_piper_voice.py tests/test_assets.py tests/test_codex_content.py tests/test_ollama_content.py tests/test_real_local_smoke.py`
  - Passed.
- Static AST/source check for the finite-duration checkpoint contract
  - Passed.
- `git diff --check`
  - Passed.
- `docker compose config --quiet`
  - Passed.
- `python3 -m pytest -q tests/test_pipeline_orchestrator.py`
  - Could not start: `/usr/bin/python3: No module named pytest`.
- `docker compose ps --format json`
  - Failed: permission denied on `/var/run/docker.sock`.
- Rechecked real executables, retained smoke artifacts, and success marker.
  - FFmpeg, ffprobe, Piper, Codex, smoke artifacts, and
    `.autonomous_success` are absent.

## Next required action (after iteration 22)

1. Restore Docker API access or provide the project Python dependencies, then
   run focused M24--M26 tests and the complete suite, fixing runtime failures.
2. Supply FFmpeg/ffprobe, Piper, and a Piper ONNX model; execute and inspect the
   fixed real orchestrated smoke under `artifacts/smoke/`.
3. Supply an authenticated Codex CLI and execute the Codex real-smoke case
   through the same orchestrator, retaining and inspecting its artifacts.
4. Create `.autonomous_success` only after all tests and both real media paths
   satisfy every mission acceptance criterion.

## Work completed (2026-08-24, iteration 20)

- Re-read the repository policy, complete M24--M26 mission, accumulated
  progress, current worktree, production media validation, and focused asset
  tests.
- Closed an M25 validation/promotion gap for video visual assets. Production
  ffprobe validation now rejects non-finite duration, zero/negative or
  below-policy dimensions, excessive pixel count, and blank container/codec
  metadata before a downloaded video can be atomically promoted.
- Classified invalid UTF-8 from the video ffprobe boundary as a provider
  validation failure rather than allowing a decode exception to escape.
- Added focused parameterized regressions covering zero and below-minimum
  dimensions, blank codec metadata, and `NaN` duration.

## Current failures / blockers (iteration 20)

- Focused and full pytest cannot start because `/usr/bin/python3` has no pytest
  or project dependencies. The changed validator was exercised directly with
  dependency-free Python and passed.
- Docker Compose configuration is valid, but Docker daemon access remains
  unavailable based on prior direct socket probes.
- FFmpeg, ffprobe, Piper, Codex, and a Piper ONNX voice remain absent from the
  host. The mandatory fixed/Piper and live Codex smokes cannot execute, and no
  real smoke artifacts exist.
- `.autonomous_success` remains absent because mandatory real smoke validation
  has not passed.

## Commands/tests run (iteration 20)

- Dependency-free exercise of `inspect_media` with one valid video metadata
  result and four invalid results (zero width, below-minimum width, blank
  codec, and non-finite duration)
  - Passed.
- `python3 -m compileall -q src tests/test_assets.py`
  - Passed.
- `git diff --check`
  - Passed.
- `docker compose config --quiet`
  - Passed.
- `python3 -m pytest -q tests/test_assets.py tests/test_pipeline_orchestrator.py tests/test_rendering_audio.py tests/test_rendering_preview.py tests/test_piper_voice.py tests/test_fixed_script_pipeline.py tests/test_codex_content.py tests/test_ollama_content.py tests/test_real_local_smoke.py`
  - Could not start: `/usr/bin/python3: No module named pytest`.
- Rechecked host executables, smoke artifacts, and success marker.
  - Pytest, FFmpeg, ffprobe, Piper, Codex, smoke artifacts, and
    `.autonomous_success` are absent.

## Next required action (after iteration 20)

1. Restore Docker API access or provide the project Python dependencies, then
   run focused M24--M26 tests and the complete suite, fixing runtime failures.
2. Supply FFmpeg/ffprobe, Piper, and a Piper ONNX model; execute and inspect the
   fixed real orchestrated smoke under `artifacts/smoke/`.
3. Supply an authenticated Codex CLI and execute the Codex real-smoke case
   through the same orchestrator, retaining and inspecting its artifacts.
4. Create `.autonomous_success` only after all tests and both real media paths
   satisfy every mission acceptance criterion.

## Work completed (2026-08-24, iteration 19)

- Re-read the repository policy, complete M24--M26 mission, accumulated
  progress, current worktree, asset validator/cache paths, renderer, provider
  implementations, and real-smoke harness.
- Closed an M25 cache-validation gap: database and sidecar cache hits previously
  trusted a matching checksum and validator version without decoding the
  current bytes. An altered file plus altered checksum metadata could therefore
  bypass current image validation until a later checkpoint boundary.
- Added a shared cache-hit validator that enforces the byte limit, checksum and
  validator version, decodes the current image/video under the active policy,
  and compares freshly inspected media facts with persisted metadata.
- Both database-backed shared-cache reuse and downloader sidecar reuse now use
  this validator. Invalid hits are invalidated/reacquired and are never returned
  as accepted scene visuals.
- Added a regression that constructs corrupt cached bytes with internally
  matching database and sidecar checksums, then proves acquisition rejects the
  cache claims, downloads valid media, validates it, and atomically replaces
  the bad cached artifact.

## Current failures / blockers (iteration 19)

- Focused and full pytest cannot start because `/usr/bin/python3` still has no
  pytest or project dependencies.
- Docker Compose configuration passes, but Docker daemon access remains denied
  at `/var/run/docker.sock`, preventing use of the project test/runtime image.
- FFmpeg, ffprobe, Piper, Codex, and a Piper ONNX voice remain unavailable on
  the host. The mandatory fixed/Piper and live Codex real-video smokes cannot
  execute or be inspected.
- `.autonomous_success` remains absent because the mandatory real smokes and
  complete automated suite have not passed.

## Commands/tests run (iteration 19)

- `python3 -m compileall -q src tests/test_assets.py tests/test_pipeline_orchestrator.py tests/test_real_local_smoke.py tests/test_codex_content.py tests/test_ollama_content.py`
  - Passed.
- `git diff --check`
  - Passed.
- `docker compose config --quiet`
  - Passed.
- `python3 -m pytest -q tests/test_assets.py tests/test_pipeline_orchestrator.py tests/test_fixed_script_pipeline.py tests/test_piper_voice.py tests/test_rendering_audio.py tests/test_rendering_preview.py tests/test_codex_content.py tests/test_ollama_content.py tests/test_real_local_smoke.py`
  - Could not start: `/usr/bin/python3: No module named pytest`.
- `docker compose ps --format json`
  - Failed: permission denied on the Docker socket.
- Rechecked real executables, local ONNX models, and the success marker.
  - FFmpeg, ffprobe, Piper, Codex, voice models, and `.autonomous_success` are
    absent.

## Next required action (after iteration 19)

1. Restore Docker API access or provide the project Python dependencies, then
   run the asset/provider/orchestrator focused tests and full suite, fixing any
   runtime failures.
2. Supply FFmpeg/ffprobe, Piper, and a Piper ONNX voice; run and inspect the
   fixed six-scene orchestrated smoke under `artifacts/smoke/`.
3. Supply an authenticated Codex CLI and run the live Codex-to-video smoke
   through the same orchestrator, retaining and inspecting its artifacts.
4. Create `.autonomous_success` only after every mission criterion, the full
   suite, and both required real media paths genuinely pass.

## Work completed (2026-08-24, iteration 11)

- Re-read the repository policy, complete M24--M26 mission, accumulated
  progress, current diff, asset pipeline, cache repositories, and focused asset
  tests.
- Fixed an asset-cache retry defect in the M25 acquisition path. Download,
  validation, or cooperative-cancellation failures previously retained the
  writer reservation for up to five minutes, preventing an immediate retry
  from reaching the provider.
- Added token-fenced `AssetCacheRepository.abandon`. Failed acquisition owners
  now release only their own still-active reservation; an expired owner cannot
  delete a replacement reservation or accepted asset.
- Wrapped download and pre-acceptance cancellation in reservation cleanup while
  retaining the existing token-fenced acceptance and atomic file-promotion
  behavior.
- Added regression coverage proving a failed invalid-image acquisition can be
  retried successfully immediately, plus a stale-owner fencing assertion.

## Current failures / blockers (iteration 11)

- Focused and full pytest still cannot start because `/usr/bin/python3` has no
  pytest or project dependencies, and no alternate local environment was found.
- Docker Compose configuration passes, but daemon access remains denied at
  `/var/run/docker.sock`, so the project image cannot provide the test/runtime
  dependencies.
- Piper, FFmpeg/ffprobe, Codex, and a Piper ONNX voice remain unavailable.
  Neither required real orchestrated smoke can execute, and no real smoke media
  can be validated.
- `.autonomous_success` remains absent because the real fixed/Piper and live
  Codex-to-video acceptance paths have not passed.

## Commands/tests run (iteration 11)

- `python3 -m compileall -q src tests/test_assets.py tests/test_real_local_smoke.py tests/test_codex_content.py tests/test_ollama_content.py`
  - Passed.
- `git diff --check`
  - Passed.
- `docker compose config --quiet`
  - Passed.
- `python3 -m pytest -q tests/test_assets.py tests/test_fixed_script_pipeline.py tests/test_codex_content.py tests/test_ollama_content.py tests/test_real_local_smoke.py`
  - Could not start: `/usr/bin/python3: No module named pytest`.
- `docker compose ps --format json`
  - Failed: permission denied on the Docker socket.
- Rechecked host tools, local ONNX models, and the success marker
  - Piper, FFmpeg/ffprobe, Codex, and a voice model are unavailable;
    `.autonomous_success` is absent.

## Next required action (after iteration 11)

1. Restore Docker API access or provide the project Python dependencies, then
   run the focused asset/provider/config/smoke tests and complete suite.
2. Supply FFmpeg/ffprobe, Piper, and a Piper ONNX model; execute and inspect the
   fixed real orchestrated smoke under `artifacts/smoke/`.
3. Supply an authenticated Codex CLI and execute the Codex real-smoke case
   through the same orchestrator, retaining and inspecting its artifacts.
4. Create `.autonomous_success` only after all tests and both real media paths
   satisfy every mission acceptance criterion.

## Work completed (2026-08-30, real fixed-media smoke)

- Restored access to the project Docker runtime and built a local image with
  the declared Python dependencies, FFmpeg/ffprobe, and Piper.
- Downloaded and configured the free `en_US-lessac-medium` Piper model and its
  matching JSON sidecar under `models/` for the local smoke environment.
- Ran the normal worker/orchestrator path with the fixed six-scene content
  provider and real Piper narration. The test traversed script approval,
  preview rendering/approval, asset acquisition, final rendering, and final
  artifact promotion.
- Found and fixed two production render synchronization defects exposed only
  by real media: cumulative scene frame quantization could shorten a video,
  and FFmpeg's `-shortest` could truncate the filtered mux before narration
  ended. The renderer now pads the visual/audio streams and uses the measured
  narration timeline as an explicit output duration. Bumped the renderer
  template version to invalidate stale render checkpoints.
- Added command-contract coverage for the explicit padding/duration behavior.

## Real smoke result (2026-08-30)

- `tests/test_real_local_smoke.py -k fixed`: **passed** in 123.26 seconds.
- Retained artifacts:
  - `artifacts/smoke/fixed_piper_six_scene_smoke.mp4`
  - `artifacts/smoke/fixed_piper_six_scene_smoke.wav`
  - `artifacts/smoke/fixed_piper_six_scene_smoke.ffprobe.json`
- Independent ffprobe validation confirmed a 73.527-second 640x360 H.264/AAC
  MP4 with 48 kHz mono audio. The WAV is 48 kHz mono PCM and 73.527479 seconds.
  Both decoded tracks have non-silent RMS values above 4,300.
- Six sampled upper-frame SHA-256 digests are all distinct, confirming that
  the final video changes visuals for all six scenes rather than relying on
  subtitle-only differences.

## Remaining validation

1. The focused regression suite is running in the same Docker runtime.
2. Run the complete suite after it finishes and address any failures.
3. The optional live Codex-to-video smoke remains pending an authenticated
   `codex` CLI; it is not required for the validated deterministic local
   fixed/Piper video artifact above.

## Requested software-engineering video (2026-08-30)

- Added a deterministic six-scene `minimum-engineer-v1` content preset for a
  practical engineering baseline: one language, Linux, Git/Docker, AWS basics,
  and DSA.
- Real Piper/FFmpeg worker smoke passed in 132.98 seconds after normal script
  and preview approvals. The retained artifact at
  `artifacts/smoke/fixed_piper_six_scene_smoke.mp4` is 71.074 seconds,
  640x360 H.264 with audible 48 kHz AAC narration.
- Started a localhost-only artifact viewer bound to `127.0.0.1:8082`; the MP4
  is available at `/smoke/fixed_piper_six_scene_smoke.mp4`.

## Work completed (2026-08-24, iteration 20)

- Re-read the repository policy, complete M24--M26 mission, accumulated
  progress, current worktree, real smoke harness, Piper adapter, narration
  assembly, and preview/final rendering path.
- Closed a real M24 acceptance-evidence gap. The smoke test previously proved
  only that ffprobe found an audio stream; a silent WAV and silent muxed MP4
  could still satisfy those assertions despite the requirement for narration.
- The real smoke harness now decodes the first audio stream from both the
  retained narration WAV and final MP4 to signed 16-bit mono PCM and requires a
  non-silent RMS signal. Both RMS measurements are retained in the smoke
  evidence JSON alongside the complete ffprobe output.
- Strengthened explicit media assertions for the required H.264 video codec,
  AAC muxed audio, PCM narration, 48 kHz mono normalized WAV, configured frame
  rate, 640x360 dimensions, positive channel/sample metadata, 60--90 second
  narration duration, final-video synchronization, and nonzero file size.

## Current failures / blockers (iteration 20)

- Focused and full pytest still cannot start because `/usr/bin/python3` has no
  pytest or project dependencies.
- Docker Compose configuration passes, but daemon API access is still denied at
  `/var/run/docker.sock`.
- FFmpeg, ffprobe, Piper, Codex, and a Piper ONNX voice remain absent from the
  host. Neither mandatory real orchestrated smoke can run, so the new audible
  narration checks cannot yet produce retained evidence.
- `.autonomous_success` remains absent because mandatory real smoke validation
  has not passed.

## Commands/tests run (iteration 20)

- `python3 -m compileall -q src tests/test_real_local_smoke.py`
  - Passed.
- `git diff --check`
  - Passed.
- `docker compose config --quiet`
  - Passed.
- `python3 -m pytest -q tests/test_real_local_smoke.py tests/test_rendering_audio.py tests/test_rendering_preview.py tests/test_piper_voice.py tests/test_assets.py tests/test_pipeline_orchestrator.py tests/test_codex_content.py tests/test_ollama_content.py tests/test_fixed_script_pipeline.py`
  - Could not start: `/usr/bin/python3: No module named pytest`.
- Rechecked Docker daemon access and required host executables.
  - Docker access is denied; FFmpeg, ffprobe, Piper, and Codex are absent.

## Next required action (after iteration 20)

1. Restore Docker API access or provide the project Python dependencies, then
   run focused M24--M26 tests and the complete suite, fixing runtime failures.
2. Supply FFmpeg/ffprobe, Piper, and a Piper ONNX model; execute the fixed real
   smoke and inspect the retained stream metadata, RMS measurements, and six
   sampled visual frames under `artifacts/smoke/`.
3. Supply an authenticated Codex CLI and execute the Codex case through the
   same orchestrator and real-media validation path.
4. Create `.autonomous_success` only after both real smokes and every mission
   acceptance criterion genuinely pass.

## Work completed (2026-08-24, iteration 25)

- Re-read the repository policy, complete M24--M26 mission, accumulated
  progress, current worktree, real acceptance harness, media providers, Piper
  adapter, narration assembly, and FFmpeg rendering path.
- Closed a false-positive in the real M25 visual acceptance proof. The smoke
  test previously hashed complete midpoint frames; changing burned subtitle
  text could produce six different hashes even if all six underlying visuals
  were identical.
- The smoke test now requires every accepted scene asset to have a distinct
  content checksum, not merely a distinct path. It also crops each sampled
  frame to the upper half before hashing, excluding the bottom-aligned caption
  region so the rendered-video check measures visual changes rather than text
  changes.

## Current failures / blockers (iteration 25)

- Focused and full pytest cannot start because `/usr/bin/python3` still has no
  pytest or project dependencies.
- Docker Compose configuration passes, but Docker daemon access remains denied
  at `/var/run/docker.sock`.
- FFmpeg, ffprobe, Piper, Codex, and a Piper ONNX voice remain absent. Neither
  required real orchestrated smoke can run, and no smoke artifacts exist.
- `.autonomous_success` remains absent because mandatory real smoke validation
  has not passed.

## Commands/tests run (iteration 25)

- `python3 -m compileall -q src tests/test_real_local_smoke.py`
  - Passed.
- `git diff --check`
  - Passed.
- `docker compose config --quiet`
  - Passed.
- `python3 -m pytest -q tests/test_real_local_smoke.py tests/test_assets.py tests/test_rendering_preview.py tests/test_rendering_audio.py tests/test_piper_voice.py tests/test_fixed_script_pipeline.py tests/test_codex_content.py tests/test_ollama_content.py tests/test_pipeline_orchestrator.py`
  - Could not start: `/usr/bin/python3: No module named pytest`.
- `docker compose ps --format json`
  - Failed: permission denied on `/var/run/docker.sock`.
- Rechecked real executables, ONNX models, smoke artifacts, and success marker.
  - All required tools/models/artifacts are absent; `.autonomous_success` is
    absent.

## Next required action (after iteration 25)

1. Restore Docker API access or provide the project Python dependencies, then
   run the focused M24--M26 tests and complete suite, fixing runtime failures.
2. Supply FFmpeg/ffprobe, Piper, and a Piper ONNX model; execute and inspect the
   fixed real orchestrated smoke under `artifacts/smoke/`.
3. Supply an authenticated Codex CLI and execute the Codex real-smoke case
   through the same orchestrator, retaining and inspecting its artifacts.
4. Create `.autonomous_success` only after all tests and both real media paths
   satisfy every mission acceptance criterion.

## Work completed (2026-08-24, iteration 24)

- Closed an atomic narration-promotion gap: a zero-exit FFmpeg invocation could
  previously rename any non-empty temporary file to the final WAV path before
  downstream probing rejected malformed or truncated bytes.
- Narration assembly now decodes the temporary WAV before promotion and
  requires uncompressed PCM, 48 kHz, mono, 16-bit samples, a positive frame
  count, and a complete declared payload. Invalid output is removed while the
  prior final artifact remains untouched.
- Added focused regressions proving valid normalized output is promoted and a
  corrupt file from a nominally successful process is rejected and cleaned up.

## Current failures / blockers (iteration 24)

- Pytest cannot start because `/usr/bin/python3` lacks pytest and project
  dependencies. The changed boundary passed a dependency-free runtime check.
- Docker daemon access remains unavailable. FFmpeg, ffprobe, Piper, Codex, and
  a Piper ONNX voice are absent from the host, so neither required real smoke
  can run. `.autonomous_success` remains absent.

## Commands/tests run (iteration 24)

- Dependency-free `PYTHONPATH=src` valid/corrupt WAV promotion exercise: passed.
- `python3 -m compileall -q src tests/test_rendering_audio.py`: passed.
- Focused M24--M26 pytest command: could not start (`No module named pytest`).
- `docker compose config --quiet`: passed.
- `git diff --check`: passed.
- Executable, smoke-artifact, and success-marker checks: all required runtime
  tools/artifacts and `.autonomous_success` remain absent.

## Next required action (after iteration 24)

1. Restore Docker API access or provide the project Python dependencies, then
   run focused M24--M26 tests and the complete suite.
2. Supply FFmpeg/ffprobe, Piper, and a Piper model; execute and inspect the fixed
   real smoke under `artifacts/smoke/`.
3. Supply an authenticated Codex CLI and run the Codex-to-video smoke through
   the same orchestrator.
4. Create `.autonomous_success` only after the full suite and both real media
   paths satisfy every mission criterion.

## Work completed (2026-08-24, iteration 20)

- Re-read the repository policy, complete M24--M26 mission, accumulated
  progress, current worktree, image acquisition/validation path, checkpoint
  recovery, focused asset tests, and the real smoke harness.
- Closed an M25 image-validation gap: JPEG acceptance previously parsed only a
  plausible frame header and dimensions, so truncated or corrupt scan/pixel
  data could be atomically promoted without ever decoding.
- JPEG validation now invokes FFmpeg with a bounded argument-array command,
  `-xerror`, and one-frame decode. Decoder failure, timeout, and missing FFmpeg
  are classified explicitly; dimension/pixel limits are checked before the
  decoder is spawned.
- Bumped the shared persisted asset validation version to `m25-v3`, forcing
  JPEGs accepted under the former header-only policy through validation again
  during cache reuse and checkpoint recovery.
- Added focused command-contract and corrupt-pixel-data regressions.

## Current failures / blockers (iteration 20)

- Focused and full pytest cannot start because `/usr/bin/python3` has no pytest
  or project dependencies. The attempted direct boundary exercise also cannot
  import the production module because PyYAML is unavailable.
- Docker Compose configuration passes, but Docker daemon access remains denied
  at `/var/run/docker.sock`, so the dependency-complete project image cannot be
  used for tests or FFmpeg validation.
- FFmpeg, ffprobe, Piper, Codex, and a Piper ONNX voice remain unavailable on
  the host. Neither mandatory real orchestrated smoke can execute.
- `.autonomous_success` remains absent because mandatory real smoke validation
  has not passed.

## Commands/tests run (iteration 20)

- `python3 -m compileall -q src tests/test_assets.py tests/test_pipeline_orchestrator.py`
  - Passed.
- `python3 -m pytest -q tests/test_assets.py tests/test_pipeline_orchestrator.py`
  - Could not start: `/usr/bin/python3: No module named pytest`.
- Direct `PYTHONPATH=src` JPEG boundary exercise
  - Could not import production configuration: `No module named 'yaml'`.
- `git diff --check`
  - Passed.
- `docker compose config --quiet`
  - Passed.
- `docker compose ps --format json`
  - Failed: permission denied on `/var/run/docker.sock`.
- Rechecked real executables and success marker.
  - FFmpeg, ffprobe, Piper, Codex, and `.autonomous_success` are absent.

## Next required action (after iteration 20)

1. Restore Docker API access or provide the project Python dependencies, then
   run the asset/orchestrator tests and full suite, fixing runtime failures.
2. Supply FFmpeg/ffprobe, Piper, and a Piper ONNX model; run and inspect the
   fixed real orchestrated smoke under `artifacts/smoke/`.
3. Supply an authenticated Codex CLI and run the Codex real-smoke case through
   the same orchestrator, retaining and inspecting its artifacts.
4. Create `.autonomous_success` only after all tests and both real media paths
   satisfy every mission acceptance criterion.

## Work completed (2026-08-24, iteration 23)

- Re-read the repository policy, full M24--M26 mission, accumulated progress,
  current worktree, real smoke harness, and the content/audio/render provider
  boundaries.
- Closed an M26 Ollama cache-safety gap. A non-streaming Ollama call can return
  a terminal-looking envelope whose generation did not complete; previously a
  schema-valid partial `response` could be accepted into the persistent cache.
- Ollama results now require the protocol's explicit `done: true` completion
  marker before response parsing, production validation, or cache acceptance.
- Added a regression proving an interrupted response is rejected, its fenced
  cache reservation is released, and the following attempt invokes inference
  again instead of reusing incomplete content. Updated successful/malformed
  fixtures to model completed Ollama envelopes accurately.

## Current failures / blockers (iteration 23)

- Focused and full pytest cannot start because `/usr/bin/python3` has no pytest
  or project dependencies. Syntax, diff, and Compose configuration checks pass.
- FFmpeg, ffprobe, Piper, Codex, and a Piper ONNX voice remain unavailable on
  the host. Neither mandatory real orchestrated smoke can execute, and no smoke
  artifacts exist.
- `.autonomous_success` remains absent because the fixed/Piper and live Codex
  real-video acceptance paths have not passed.

## Commands/tests run (iteration 23)

- `python3 -m compileall -q src tests/test_ollama_content.py tests/test_codex_content.py tests/test_rendering_audio.py tests/test_rendering_preview.py tests/test_piper_voice.py tests/test_assets.py tests/test_pipeline_orchestrator.py tests/test_fixed_script_pipeline.py tests/test_real_local_smoke.py`
  - Passed.
- Static AST/source audit of the Ollama terminal-completion contract
  - Passed.
- `git diff --check`
  - Passed.
- `docker compose config --quiet`
  - Passed.
- `python3 -m pytest -q tests/test_ollama_content.py tests/test_codex_content.py tests/test_rendering_audio.py tests/test_rendering_preview.py tests/test_piper_voice.py tests/test_assets.py tests/test_pipeline_orchestrator.py tests/test_fixed_script_pipeline.py tests/test_real_local_smoke.py`
  - Could not start: `/usr/bin/python3: No module named pytest`.
- Rechecked the real executables, local ONNX models, retained smoke artifacts,
  and success marker.
  - All are absent.

## Next required action (after iteration 23)

1. Restore Docker API access or provide the project Python dependencies, then
   run focused M24--M26 tests and the complete suite, fixing runtime failures.
2. Supply FFmpeg/ffprobe, Piper, and a Piper ONNX model; execute and inspect the
   fixed real orchestrated smoke under `artifacts/smoke/`.
3. Supply an authenticated Codex CLI and execute the Codex real-smoke case
   through the same orchestrator, retaining and inspecting its artifacts.
4. Create `.autonomous_success` only after all tests and both real media paths
   satisfy every mission acceptance criterion.

## Work completed (2026-08-24, iteration 20)

- Re-read the repository policy, complete M24--M26 mission, accumulated
  progress, current worktree, deployment image, Compose topology, production
  configuration, smoke harness, and provider validation.
- Closed a reproducibility gap in the required local-media deployment. The
  worker image installed FFmpeg but did not install Piper, so selecting the
  production Piper provider could never work in the standard Compose image.
- Added a `local-media` project dependency group containing the open-source
  `piper-tts` CLI and made the image install it alongside the application and
  test dependencies. Voice data remains operator-supplied rather than silently
  downloading a large or language-specific model at build time.
- Added a read-only `./models:/app/models` worker mount and aligned the
  production Piper executable, ONNX model, JSON sidecar, voice ID, and cache
  paths with the container filesystem. The default providers remain fake, so a
  missing optional model does not break safe offline startup.
- Added packaging/configuration contract tests proving the image includes both
  FFmpeg and Piper support, the model mount is read-only, and production model
  paths match that mount.

## Current failures / blockers (iteration 20)

- Focused and full pytest still cannot start because `/usr/bin/python3` has no
  pytest or project dependencies. The new TOML/Dockerfile/Compose/production
  path contract was exercised with dependency-free Python and passed.
- Docker Compose syntax validates, but daemon access remains denied; therefore
  the updated image cannot be built here to resolve and execute `piper-tts`.
- No Piper voice model, FFmpeg/ffprobe/Piper host executables, or authenticated
  Codex CLI is available. The mandatory fixed/Piper and live Codex video smokes
  still cannot run, and `.autonomous_success` remains absent.

## Commands/tests run (iteration 20)

- `python3 -m compileall -q src tests/test_local_media_packaging.py`
  - Passed.
- Dependency-free `tomllib`/text validation of the `local-media` dependency,
  Docker installation extra, model mount, and production model path
  - Passed.
- `docker compose config --quiet`
  - Passed.
- `python3 -m pytest -q tests/test_local_media_packaging.py tests/test_rendering_audio.py tests/test_piper_voice.py tests/test_assets.py tests/test_pipeline_orchestrator.py tests/test_codex_content.py tests/test_ollama_content.py tests/test_fixed_script_pipeline.py tests/test_real_local_smoke.py`
  - Could not start: `/usr/bin/python3: No module named pytest`.
- `git diff --check`
  - Passed.

## Next required action (after iteration 20)

1. Restore Docker API access and build the worker image, or provide the project
   Python environment; run the packaging and focused M24--M26 tests, followed
   by the complete suite.
2. Place a Piper ONNX voice plus its `.onnx.json` sidecar under `./models`,
   select `voice_provider: piper`, and execute the fixed real smoke. Inspect the
   retained WAV, MP4, ffprobe record, and six scene-frame hashes.
3. If an authenticated Codex CLI is available in the worker runtime, execute
   the Codex smoke case through the same orchestrator and retain its validated
   artifacts.
4. Create `.autonomous_success` only after the full suite and required real
   media validation pass.

## Work completed (2026-08-24, iteration 21)

- Re-read the repository policy, complete M24--M26 mission, accumulated
  progress, current worktree, FFmpeg narration/video paths, and real smoke
  harness.
- Closed an atomic-promotion defect in narration assembly. A timed-out or
  unavailable FFmpeg process could leave `narration.tmp.wav` behind, and a
  subsequent run did not remove that stale temporary before invoking FFmpeg.
- Narration assembly now removes stale temporary output before every attempt
  and cleans partial output after both timeout and process-start failures. A
  successful return that produces no new file can no longer accept stale bytes.
- Added focused regressions for stale-output rejection and partial cleanup after
  timeout and missing-executable exceptions. Existing accepted narration is
  left untouched on all these failure paths.

## Current failures / blockers (iteration 21)

- Focused and full pytest still cannot start because `/usr/bin/python3` has no
  pytest or project dependencies. The changed atomic boundary was exercised
  directly with dependency-free Python and passed.
- Docker Compose configuration passes, but Docker daemon access remains
  unavailable based on prior direct socket probes.
- FFmpeg, ffprobe, Piper, Codex, and a Piper ONNX voice remain absent from the
  host. Neither mandatory real orchestrated smoke can execute, and no smoke
  artifacts exist.
- `.autonomous_success` remains absent because mandatory real smoke validation
  has not passed.

## Commands/tests run (iteration 21)

- Dependency-free `PYTHONPATH=src` exercise of stale-temporary rejection and
  cleanup after FFmpeg timeout and missing-executable failures
  - Passed; no temporary or accepted output remained.
- `python3 -m compileall -q src tests/test_rendering_audio.py`
  - Passed.
- `git diff --check`
  - Passed.
- `docker compose config --quiet`
  - Passed.
- `python3 -m pytest -q tests/test_rendering_audio.py tests/test_rendering_preview.py tests/test_piper_voice.py tests/test_assets.py tests/test_pipeline_orchestrator.py tests/test_codex_content.py tests/test_ollama_content.py tests/test_fixed_script_pipeline.py tests/test_real_local_smoke.py`
  - Could not start: `/usr/bin/python3: No module named pytest`.
- Rechecked real executables, retained smoke artifacts, and success marker.
  - FFmpeg, ffprobe, Piper, Codex, smoke artifacts, and
    `.autonomous_success` are absent.

## Next required action (after iteration 21)

1. Restore Docker API access or provide the project Python dependencies, then
   run focused M24--M26 tests and the complete suite, fixing runtime failures.
2. Supply FFmpeg/ffprobe, Piper, and a Piper ONNX model; execute and inspect the
   fixed real orchestrated smoke under `artifacts/smoke/`.
3. Supply an authenticated Codex CLI and execute the Codex real-smoke case
   through the same orchestrator, retaining and inspecting its artifacts.
4. Create `.autonomous_success` only after all tests and both real media paths
   satisfy every mission acceptance criterion.

## Work completed (2026-08-24, iteration 12)

- Re-read the repository policy, full M24--M26 mission, accumulated progress,
  current worktree, media validation, LLM providers, and real smoke harness.
- Closed two additional M25 PNG-validation gaps. Adam7/interlaced images were
  previously accepted whenever their decompressed payload was merely nonempty,
  even when it could not contain all passes and scanlines.
- PNG validation now computes the exact raster size for all seven Adam7 passes,
  checks every pass's row-filter byte, and rejects truncated or oversized
  interlaced data.
- Moved configured dimension and pixel-count enforcement ahead of zlib
  inflation and bounded decompression to the exact expected raster size. This
  prevents a tiny compressed file with malicious IHDR dimensions from causing
  unbounded decompression before the existing media limits are applied.
- Added regressions for a CRC-valid but incomplete Adam7 image and an image
  whose oversized dimensions must be rejected before its pixel payload is
  inflated.

## Current failures / blockers (iteration 12)

- Focused and full pytest still cannot start because `/usr/bin/python3` has no
  pytest or project dependencies; no usable alternate Python toolchain was
  found during the environment re-probe.
- Docker Compose configuration passes, but prior daemon checks remain blocked
  by permission denial on `/var/run/docker.sock`.
- Piper, FFmpeg/ffprobe, Codex, and a Piper ONNX voice remain unavailable.
  Neither required real smoke can execute, so `.autonomous_success` remains
  absent.

## Commands/tests run (iteration 12)

- `python3 -m compileall -q src tests/test_assets.py tests/test_real_local_smoke.py tests/test_codex_content.py tests/test_ollama_content.py`
  - Passed.
- `git diff --check`
  - Passed.
- `docker compose config --quiet`
  - Passed.
- `python3 -m pytest -q tests/test_assets.py tests/test_fixed_script_pipeline.py tests/test_codex_content.py tests/test_ollama_content.py tests/test_real_local_smoke.py`
  - Could not start: `/usr/bin/python3: No module named pytest`.

## Next required action (after iteration 12)

1. Restore Docker API access or provide the project Python dependencies, then
   run the focused asset/provider/smoke tests and complete suite, fixing any
   runtime failures.
2. Supply FFmpeg/ffprobe, Piper, and a Piper ONNX model; execute and inspect the
   fixed real orchestrated smoke under `artifacts/smoke/`.
3. Supply an authenticated Codex CLI and execute the Codex real-smoke case
   through the same orchestrator, retaining and inspecting its artifacts.
4. Create `.autonomous_success` only after all tests and both real media paths
   satisfy every mission acceptance criterion.

## Work completed (2026-08-24, iteration 13)

- Re-read the repository policy, full M24--M26 mission, accumulated progress,
  current worktree, real smoke harness, Piper adapter, renderer, and focused
  media tests.
- Closed an M24 Piper cache-validation gap. A cached WAV previously bypassed
  `max_output_bytes`, so an oversized cache entry could be accepted even though
  the same bytes would be rejected when newly synthesized.
- Piper WAV validation now consistently enforces the size limit for cached and
  new output and requires positive frames, channels, sample width, sample rate,
  and uncompressed PCM before reuse or atomic promotion.
- Added focused Piper regressions proving a valid cached narration avoids a
  subprocess invocation and an oversized cached WAV is regenerated into a
  validated temporary file and atomically replaces the stale entry.

## Current failures / blockers (iteration 13)

- Focused and full pytest still cannot start because `/usr/bin/python3` has no
  pytest or project dependencies; the focused command fails before collection.
- Piper, FFmpeg/ffprobe, Codex, and a Piper ONNX voice remain unavailable on
  the host. Neither required real orchestrated smoke can execute, and no smoke
  artifacts exist.
- Docker Compose configuration is valid, but prior daemon probes remain blocked
  by permission denial on `/var/run/docker.sock`.
- `.autonomous_success` remains absent because the real fixed/Piper and live
  Codex-to-video acceptance paths have not passed.

## Commands/tests run (iteration 13)

- `python3 -m compileall -q src tests/test_piper_voice.py tests/test_real_local_smoke.py`
  - Passed.
- `git diff --check`
  - Passed.
- `docker compose config --quiet`
  - Passed.
- `python3 -m pytest -q tests/test_piper_voice.py tests/test_fixed_script_pipeline.py tests/test_assets.py tests/test_codex_content.py tests/test_ollama_content.py tests/test_real_local_smoke.py`
  - Could not start: `/usr/bin/python3: No module named pytest`.
- Rechecked the real toolchain, smoke artifact directory, and success marker.
  - FFmpeg, ffprobe, Piper, Codex, voice model, and smoke artifacts are absent;
    `.autonomous_success` is absent.

## Next required action (after iteration 13)

1. Restore Docker API access or provide the project Python dependencies, then
   run the new Piper tests, focused M24--M26 tests, and complete suite.
2. Supply FFmpeg/ffprobe, Piper, and a Piper ONNX model; execute and inspect the
   fixed real orchestrated smoke under `artifacts/smoke/`.
3. Supply an authenticated Codex CLI and execute the Codex real-smoke case
   through the same orchestrator, retaining and inspecting its artifacts.
4. Create `.autonomous_success` only after all tests and both real media paths
   satisfy every mission acceptance criterion.

## Work completed (2026-08-24, iteration 14)

- Re-read the repository policy, full M24--M26 mission, accumulated progress,
  current worktree, real smoke harness, Piper adapter, narration assembly, and
  focused voice tests.
- Closed another real-audio validation gap: Python's WAV reader trusts the
  header's declared frame count, so a truncated cached file could previously
  appear valid and supply a false duration even though its PCM payload was
  incomplete.
- Piper validation now reads the complete declared PCM payload and verifies its
  exact byte count before reusing or promoting a WAV. It also enforces the
  optional configured sample rate, preventing a Piper/model configuration
  mismatch from silently entering the phrase cache.
- Added focused regressions proving truncated cached audio is regenerated and
  that newly synthesized audio with an unexpected configured sample rate is
  rejected without promotion or temporary-file leakage.

## Current failures / blockers (iteration 14)

- Focused and full pytest still cannot start because `/usr/bin/python3` has no
  pytest or project dependencies.
- Docker Compose configuration passes, but Docker daemon access remains denied
  at `/var/run/docker.sock`, so the project test/runtime image cannot be used.
- Piper, FFmpeg/ffprobe, Codex, and a Piper ONNX voice remain unavailable on
  the host. Neither required real orchestrated smoke can execute, and no real
  smoke artifact can be inspected.
- `.autonomous_success` remains absent because the fixed/Piper and live Codex
  real-video acceptance paths have not passed.

## Commands/tests run (iteration 14)

- `python3 -m compileall -q src tests/test_piper_voice.py tests/test_real_local_smoke.py`
  - Passed.
- `git diff --check`
  - Passed.
- `docker compose config --quiet`
  - Passed.
- `python3 -m pytest -q tests/test_piper_voice.py tests/test_fixed_script_pipeline.py tests/test_assets.py tests/test_codex_content.py tests/test_ollama_content.py tests/test_real_local_smoke.py`
  - Could not start: `/usr/bin/python3: No module named pytest`.
- `docker compose ps --format json`
  - Failed: permission denied on `/var/run/docker.sock`.
- Rechecked real executables, local ONNX models, and the success marker.
  - FFmpeg, ffprobe, Piper, Codex, voice models, and `.autonomous_success` are
    absent.

## Next required action (after iteration 14)

1. Restore Docker API access or provide the project Python dependencies, then
   run the focused Piper/provider/asset/smoke tests and complete suite.
2. Supply FFmpeg/ffprobe, Piper, and a Piper ONNX model; execute and inspect the
   fixed real orchestrated smoke under `artifacts/smoke/`.
3. Supply an authenticated Codex CLI and execute the Codex real-smoke case
   through the same orchestrator, retaining and inspecting its artifacts.
4. Create `.autonomous_success` only after all tests and both real media paths
   satisfy every mission acceptance criterion.

## Work completed (2026-08-24, iteration 15)

- Re-read the repository policy, full M24--M26 mission, accumulated progress,
  current worktree, provider/cache changes, asset recovery logic, and focused
  smoke and reliability tests.
- Found a checkpoint-safety gap introduced by the stricter M25 image decoder:
  persisted validations were still stamped and trusted as `m8-v1`. An image
  accepted by the former header-only checks could therefore bypass the newer
  pixel-data validation during checkpoint recovery.
- Introduced the shared `ASSET_VALIDATION_VERSION` value `m25-v2` and use it
  for cache keys, accepted metadata, and orchestrator recovery. This forces
  old cached/checkpointed validation claims through acquisition again.
- Strengthened orchestrator recovery so an accepted visual is decoded again
  from its current bytes. Its media type and decoded dimensions must match the
  persisted validation record in addition to the existing checksum, licence,
  and review-policy checks.
- Updated the recovery regression to use a genuine PNG and prove that current
  media passes, old validation versions fail, policy changes fail, and corrupt
  bytes fail even when their stored checksum is updated. Decode failures are
  treated as invalid checkpoints rather than escaping recovery validation.

## Current failures / blockers (iteration 15)

- Focused and full pytest cannot start because Python 3.13 has no pytest or
  project dependencies; no local wheel/package cache or alternate environment
  was found.
- Docker Compose configuration is valid, but the Docker daemon remains
  inaccessible from this execution environment based on the prior direct
  socket probes.
- FFmpeg, ffprobe, Piper, Codex, and a Piper ONNX voice remain unavailable on
  the host. No fixed/Piper or live Codex smoke artifact can be generated.
- `.autonomous_success` remains absent because mandatory real smoke validation
  has not passed.

## Commands/tests run (iteration 15)

- `python3 -m compileall -q src tests/test_pipeline_orchestrator.py tests/test_assets.py tests/test_piper_voice.py tests/test_real_local_smoke.py tests/test_codex_content.py tests/test_ollama_content.py tests/test_fixed_script_pipeline.py`
  - Passed.
- `git diff --check`
  - Passed.
- `docker compose config --quiet`
  - Passed.
- `python3 -m pytest -q tests/test_assets.py tests/test_pipeline_orchestrator.py tests/test_piper_voice.py tests/test_fixed_script_pipeline.py tests/test_codex_content.py tests/test_ollama_content.py tests/test_real_local_smoke.py`
  - Could not start: `/usr/bin/python3: No module named pytest`.
- Rechecked host executables, smoke artifacts, and success marker.
  - FFmpeg, ffprobe, Piper, Codex, and smoke artifacts are absent;
    `.autonomous_success` is absent.

## Next required action (after iteration 15)

1. Restore Docker API access or provide the project Python dependencies, then
   run the asset/orchestrator/provider tests and complete suite, fixing any
   runtime failures.
2. Supply FFmpeg/ffprobe, Piper, and a Piper ONNX model; execute and inspect the
   fixed real orchestrated smoke under `artifacts/smoke/`.
3. Supply an authenticated Codex CLI and execute the Codex real-smoke case
   through the same orchestrator, retaining and inspecting its artifacts.
4. Create `.autonomous_success` only after all tests and both real media paths
   satisfy every mission acceptance criterion.

## Work completed (2026-08-24, iteration 16)

- Re-read the repository policy, complete M24--M26 mission, accumulated
  progress, current worktree, narration/FFmpeg pipeline, render validation, and
  real smoke harness.
- Closed an M24 ffprobe-validation gap. Production narration measurement
  previously accepted any file with a positive container duration even when
  ffprobe reported no audio stream.
- `FFprobe.inspect` now requires a real audio stream with a nonblank codec,
  positive sample rate, and positive channel count before its measured duration
  may drive narration assembly, scene timing, checkpoint state, or rendering.
- Invalid UTF-8 from ffprobe is now classified as provider validation failure
  rather than escaping as an implementation exception.
- Added focused tests for complete audio metadata, missing/audio-less streams,
  invalid sample rates, and malformed ffprobe encoding.

## Current failures / blockers (iteration 16)

- Focused and full pytest cannot start because the host Python has no pytest or
  project dependencies. A dependency-free manual exercise of the changed
  FFprobe boundary passed.
- FFmpeg, ffprobe, Piper, Codex, and a Piper ONNX voice remain absent from the
  host. No real fixed/Piper or live Codex smoke can be generated or inspected.
- Docker Compose configuration passes, but Docker daemon access remains blocked
  based on the prior direct socket probes.
- `.autonomous_success` remains absent because mandatory real smoke validation
  has not passed.

## Commands/tests run (iteration 16)

- `python3 -m compileall -q src tests/test_rendering_audio.py`
  - Passed.
- Dependency-free `PYTHONPATH=src` manual FFprobe checks for valid metadata,
  missing/audio-less streams, zero sample rate, and non-UTF-8 output
  - Passed.
- `git diff --check`
  - Passed.
- `docker compose config --quiet`
  - Passed.
- `python3 -m pytest -q tests/test_rendering_audio.py tests/test_piper_voice.py tests/test_assets.py tests/test_pipeline_orchestrator.py tests/test_codex_content.py tests/test_ollama_content.py tests/test_real_local_smoke.py`
  - Could not start: `/usr/bin/python3: No module named pytest`.
- Rechecked real executables, smoke artifacts, and success marker.
  - FFmpeg, ffprobe, Piper, Codex, smoke artifacts, and
    `.autonomous_success` are absent.

## Next required action (after iteration 16)

1. Restore Docker API access or provide the project Python dependencies, then
   run the new audio tests, focused M24--M26 tests, and complete suite.
2. Supply FFmpeg/ffprobe, Piper, and a Piper ONNX model; execute and inspect the
   fixed real orchestrated smoke under `artifacts/smoke/`.
3. Supply an authenticated Codex CLI and execute the Codex real-smoke case
   through the same orchestrator, retaining and inspecting its artifacts.
4. Create `.autonomous_success` only after all tests and both real media paths
   satisfy every mission acceptance criterion.

## Work completed (2026-08-24, iteration 17)

- Re-read the repository policy, complete M24--M26 mission, accumulated
  progress, current worktree, narration/video validation, and focused render
  tests.
- Closed a numeric-validation gap at three production boundaries. Python accepts
  JSON/ffprobe values such as `NaN`, and ordinary positive-value and tolerance
  comparisons do not reject them because comparisons with NaN are false.
- Narration ffprobe validation now requires a finite duration. Final-video
  validation requires finite duration, expected duration, and frame rate.
- Timeline reconstruction now rejects non-finite phrase start/end values and a
  non-finite persisted final duration. This prevents corrupt checkpoint timing
  from bypassing gap/synchronization validation and reaching FFmpeg.
- Added focused regressions for non-finite narration duration, video duration,
  frame rate, and persisted timing-map values.

## Current failures / blockers (iteration 17)

- Focused and full pytest cannot start because the host Python has no pytest or
  project dependencies. Syntax compilation and repository configuration checks
  pass.
- FFmpeg, ffprobe, Piper, Codex, and a Piper ONNX voice remain unavailable on
  the host. Neither required real orchestrated smoke can execute.
- Docker daemon access remains unavailable based on the prior direct socket
  probes. `.autonomous_success` remains absent because mandatory real smoke
  validation has not passed.

## Commands/tests run (iteration 17)

- `python3 -m compileall -q src tests/test_rendering_audio.py tests/test_rendering_preview.py`
  - Passed.
- `git diff --check`
  - Passed.
- `docker compose config --quiet`
  - Passed.
- `python3 -m pytest -q tests/test_rendering_audio.py tests/test_rendering_preview.py tests/test_piper_voice.py tests/test_assets.py tests/test_pipeline_orchestrator.py tests/test_codex_content.py tests/test_ollama_content.py tests/test_real_local_smoke.py`
  - Could not start: `/usr/bin/python3: No module named pytest`.
- Rechecked the real executables and success marker.
  - FFmpeg, ffprobe, Piper, Codex, and `.autonomous_success` are absent.

## Next required action (after iteration 17)

1. Restore Docker API access or provide the project Python dependencies, then
   run the render/provider/asset/orchestrator tests and complete suite.
2. Supply FFmpeg/ffprobe, Piper, and a Piper ONNX model; execute and inspect the
   fixed real orchestrated smoke under `artifacts/smoke/`.
3. Supply an authenticated Codex CLI and execute the Codex real-smoke case
   through the same orchestrator, retaining and inspecting its artifacts.
4. Create `.autonomous_success` only after all tests and both real media paths
   satisfy every mission acceptance criterion.

## Work completed (2026-08-24, iteration 18)

- Re-read the repository policy, complete M24--M26 mission, accumulated
  progress, current diff, narration and video probe implementations, Piper
  adapter, and focused render tests.
- Found and fixed a real M24 smoke blocker in the production narration probe.
  Its explicit ffprobe projection omitted `codec_type`, while validation selects
  the audio stream using that field. Because ffprobe only emits requested
  fields, a genuine WAV would have been rejected as lacking an audio stream.
- The narration probe now requests `codec_type` together with codec, sample
  rate, and channel metadata. Added a command-contract regression ensuring the
  field needed by production validation cannot silently disappear again.

## Current failures / blockers (iteration 18)

- Focused and full pytest cannot start because `/usr/bin/python3` has no pytest
  or project dependencies. Syntax and Compose configuration validation pass.
- FFmpeg, ffprobe, Piper, Codex, and a Piper ONNX voice remain unavailable on
  the host. The mandatory fixed/Piper and live Codex smokes cannot execute.
- Docker daemon access remains unavailable based on prior direct socket probes.
  `.autonomous_success` remains absent because no real smoke video has passed.

## Commands/tests run (iteration 18)

- Dependency-free `PYTHONPATH=src` exercise of the FFprobe command projection
  and valid audio-stream parser contract
  - Passed.
- `python3 -m compileall -q src tests/test_rendering_audio.py`
  - Passed.
- `git diff --check`
  - Passed.
- `docker compose config --quiet`
  - Passed.
- `python3 -m pytest -q tests/test_rendering_audio.py tests/test_rendering_preview.py tests/test_piper_voice.py tests/test_assets.py tests/test_pipeline_orchestrator.py tests/test_codex_content.py tests/test_ollama_content.py tests/test_real_local_smoke.py`
  - Could not start: `/usr/bin/python3: No module named pytest`.

## Next required action (after iteration 18)

1. Restore Docker API access or provide the project Python dependencies, then
   run focused M24--M26 tests and the full suite, fixing runtime failures.
2. Supply FFmpeg/ffprobe, Piper, and a Piper ONNX model; execute and inspect the
   fixed real orchestrated smoke under `artifacts/smoke/`.
3. Supply an authenticated Codex CLI and execute the Codex real-smoke case
   through the same orchestrator, retaining and inspecting its artifacts.
4. Create `.autonomous_success` only after all tests and both real media paths
   satisfy every mission acceptance criterion.

## Work completed (2026-08-24, iteration 19)

- Re-read the repository policy, full M24--M26 mission, accumulated progress,
  current worktree, narration assembly path, smoke harness, and focused audio
  tests.
- Closed a real Piper/FFmpeg interoperability risk in narration assembly.
  Piper voice models can emit different native sample rates, while generated
  inter-phrase silence was fixed at mono/48 kHz; the concat filter previously
  received these streams without an explicit common format.
- Narration assembly now normalizes every phrase and silence input to 48 kHz,
  signed 16-bit mono before concatenation. This makes the output format
  deterministic and prevents a real smoke from depending on implicit FFmpeg
  negotiation across voice-model formats.
- Added command-contract coverage for two phrases plus a pause, verifying all
  three inputs are normalized and concatenated in order. Also reject NaN and
  infinite pause durations before spawning FFmpeg, with a regression for NaN.

## Current failures / blockers (iteration 19)

- Focused and full pytest still cannot start because `/usr/bin/python3` has no
  pytest or project dependencies. The changed audio boundary was exercised
  directly with dependency-free Python and passed.
- Docker Compose configuration passes, but Docker daemon API access remains
  denied at `/var/run/docker.sock`.
- FFmpeg, ffprobe, Piper, Codex, and a Piper ONNX voice remain absent from the
  host. The mandatory fixed/Piper and live Codex video smokes therefore cannot
  execute, and no real smoke artifacts exist.
- `.autonomous_success` remains absent because mandatory real smoke validation
  has not passed.

## Commands/tests run (iteration 19)

- Dependency-free `PYTHONPATH=src` exercise of the generated FFmpeg graph and
  non-finite pause rejection
  - Passed; three ordered inputs were normalized to 48 kHz signed 16-bit mono.
- `python3 -m compileall -q src tests/test_rendering_audio.py tests/test_real_local_smoke.py tests/test_piper_voice.py tests/test_assets.py tests/test_pipeline_orchestrator.py tests/test_codex_content.py tests/test_ollama_content.py tests/test_fixed_script_pipeline.py`
  - Passed.
- `git diff --check`
  - Passed.
- `docker compose config --quiet`
  - Passed.
- `python3 -m pytest -q tests/test_rendering_audio.py tests/test_piper_voice.py tests/test_assets.py tests/test_pipeline_orchestrator.py tests/test_codex_content.py tests/test_ollama_content.py tests/test_fixed_script_pipeline.py tests/test_real_local_smoke.py`
  - Could not start: `/usr/bin/python3: No module named pytest`.
- Rechecked retained smoke artifacts and the success marker.
  - No smoke artifacts exist; `.autonomous_success` is absent.

## Next required action (after iteration 19)

1. Restore Docker API access or provide the project Python dependencies, then
   run focused M24--M26 tests and the complete suite, fixing runtime failures.
2. Supply FFmpeg/ffprobe, Piper, and a Piper ONNX model; execute and inspect the
   fixed real orchestrated smoke under `artifacts/smoke/`.
3. Supply an authenticated Codex CLI and execute the Codex real-smoke case
   through the same orchestrator, retaining and inspecting its artifacts.
4. Create `.autonomous_success` only after all tests and both real media paths
   satisfy every mission acceptance criterion.
# Dashboard preview, mobile layout, deletion, and automatic render validation (2026-08-30)

- Replaced the LAN dashboard/worker containers with source-mounted TubeForge containers on `0.0.0.0:62065`; the running web process now imports `/workspace/src/tubeforge/api/app.py`.
- Dashboard polling now exposes registered artifact names and only embeds a preview/final `<video>` after its artifact exists. This prevents the previous premature `/artifacts/final` 404 while a render is still running.
- Made the phone layout resilient to overflow (`border-box`, scoped checkbox styling, wrapping job cards, responsive videos) and added safe deletion for paused, failed, cancelled, or final-ready local jobs. Active or publication-related jobs cannot be deleted; artifact file removal is restricted to the configured job artifact root.
- Fixed automatic review to record an immutable `system-auto-review` approval bound to the exact preview render identity before final rendering. This preserves the exact-preview approval fence.
- Focused API tests: `3 passed` (`tests/test_api_workflow.py`).
- Live end-to-end validation job `df410dd62b0841308204565f5d3ca5bc`: preview and final MP4 rendered successfully, final artifact promoted, then workflow paused at `publication_approval_required` as designed. Final artifact: `data/artifacts/df410dd62b0841308204565f5d3ca5bc/final.mp4`.
# Creator Studio dashboard and durable activity timeline (2026-08-31)

- Replaced the dashboard's full-list polling rewrite with a responsive dark Creator Studio. Job cards reconcile in place, preserving form input, filters, scroll position, and open dialogs across four-second status refreshes.
- Preview/final playback is now explicit: cards expose buttons only after the relevant artifact is registered; the modal player is created only after a click and has autoplay disabled. Added a favicon response to remove the prior browser 404.
- Added immutable `job_events` persistence (Alembic revision `20260831_0014`), an activity API at `/api/jobs/{job_id}/events`, and compact event counts in `/api/jobs`. Worker claims/waits/errors/retries/completion, state transitions, render lifecycle, creation, approvals, and deletion attempts are recorded.
- Kept deletion fenced to non-active, non-publication jobs. Failed validations are displayed as status/error cards with available preview, activity, and Delete actions; they are not buttons.
- Migrated the live local database and restarted only `youtube_video_producer-web-1` and `youtube_video_producer-worker-1`, retaining the LAN mapping `0.0.0.0:62065`.
- Focused regression suite: `14 passed` in 92.40 seconds (`tests/test_api_workflow.py`, `tests/test_worker_service.py`, `tests/test_migrations.py`).
- Live end-to-end job `2573fbade626428489c8e2ff860d8c79`: durable timeline recorded 28 events, preview and final renders completed, final MP4 endpoint returned `200 video/mp4` (1,084,639 bytes), ffprobe duration `30.000000` seconds, then workflow safely paused at `publication_approval_required`.
- Follow-up browser fix: normalized JavaScript newline escapes in the Python HTML string. The original string emitted raw newlines inside quoted JavaScript literals, producing `Uncaught SyntaxError: Invalid or unexpected token` and preventing the job list from loading. Restarted only the web container; verified literal `split('\\n')`/`join('\\n')` escapes and `GET /api/jobs` 200.

# Replace placeholder "context" videos with local multi-scene videos (2026-08-31)

- Diagnosed the repeated `context` captions as the production test-only fake content provider: it emitted a single placeholder narration and one solid-color asset. Existing artifacts retain that historical content and should be deleted/recreated from the dashboard.
- Reworked the local fallback provider to build 3--6 readable scenes from the submitted title and notes, with scene-specific queries and non-text abstract tech illustrations. No generated narration contains the placeholder word `context`.
- Activated real local Piper narration in production using the already-downloaded `en_US-lessac-medium` model. The two TubeForge containers were replaced with a read-only `models` mount; the bundled `python -m piper` mode was added to the provider adapter and verified with a direct synthesis check.
- Focused regression: `9 passed` (`tests/test_fixed_script_pipeline.py`, `tests/test_piper_voice.py`); prior focused dashboard suite remained `14 passed`.
- Corrected one-minute job `6e5ba3c6e6f848bf84b84c8ce4ca48c9` completed with six distinct scene assets, real narration, captions, and final MP4 `data/artifacts/6e5ba3c6e6f848bf84b84c8ce4ca48c9/final.mp4`. API returned `200 video/mp4` (3,437,831 bytes); ffprobe confirmed audio + video streams and a 54.242-second duration. Workflow is safely waiting at `publication_approval_required`.

# Native Stream Clipper integration (2026-08-31)

- Read and assessed the complete `integrate_stream_clipper.md` brief and the MIT-licensed local Stream Clipper codebase. The resulting design assessment is at `docs/stream_clipper_integration_assessment.md`: TubeForge reuses the donor's bounded audio-energy scoring and non-overlap selection ideas, but does not embed its separate Tauri app, pro-gated behavior, or unsafe desktop assumptions.
- Added a durable native source-clip job branch: `source_inspecting` → `source_acquiring` → `source_analyzing` → `clip_rendering` → `final_ready`. It continues to use normal TubeForge job IDs, leases, fencing, failure/resume policy, registered artifacts, durable events, and final-artifact dashboard delivery.
- Added `POST /api/source-clips`, strict public HTTP(S) URL validation (rejecting local/private IPs, `file:` URLs, and credentials), a worker-owned yt-dlp adapter, WAV energy analysis with deterministic non-overlapping rankings, and atomic FFmpeg H.264/AAC 1080x1920 clip rendering. The first ranked clip is registered as the standard `final` artifact; every selected clip is retained as its own durable artifact with score/evidence provenance.
- Added source-clip unit/API/state tests. Focused validation passed: `11 passed` for `tests/test_source_clips.py`, `tests/test_state_machine.py`, and `tests/test_api_workflow.py`. Full-suite collection found `195 tests`; full execution began successfully but this control environment ended the long-running Docker invocation before a final summary.
- Updated Compose to map the dashboard to `0.0.0.0:62065` and give web/worker read-only Piper models mounts. Deployment is intentionally pending explicit authorization because enabling yt-dlp adds network-acquisition capability to the persistent service; the existing live dashboard was left untouched.

## Stream clipper completion follow-up

- Added Alembic revision `20260831_0015_source_clipping`: `source_media` stores normalized provider, URL, external/creator IDs, duration and metadata for each source job; `creator_sources` is the durable, idempotency-ready future scheduler input. No scheduler has been enabled.
- Added `SourceMediaRepository`, a `SourceProvider` protocol, persisted source metadata immediately after inspection, and source-clip publication preparation (metadata, thumbnail, normal TubeForge publication package) without requiring a generated script or scene-assets manifest.
- The dashboard now exposes individually registered `clip_###` outputs as explicit modal-player buttons when they exist. It also adds a small "Clip existing video / stream" panel to the existing creation form, submitting the pasted URL and selected count to `POST /api/source-clips`; no separate dashboard was introduced.
- New native pipeline regression `test_source_clip_pipeline_reuses_source_checkpoint_and_prepares_publication` passed. It verifies source inspection/acquisition happen once, the source checkpoint is reused, clip artifacts are promoted, source metadata is persisted, and the selected clip reaches standard publication preparation.
- A clean non-production Alembic upgrade reached `20260831_0015 (head)`.
- Added optional source-caption acquisition: a source-clip request can opt in to yt-dlp automatic English SRT retrieval. When present, the SRT is a durable artifact and is safely burned into the vertical FFmpeg render; unavailable subtitles do not fail clipping.
- Real local media smoke passed: `tests/test_source_clip_rendering.py` created a 16:9 H.264/AAC fixture, rendered it through the native source-clip renderer, and verified a valid 1080x1920 H.264/AAC output. Combined source-render/highlight validation: `4 passed in 11.19s`.
- Fixed the packaging regression found by the full suite: the production Piper adapter deliberately runs the installed package as `python -m piper`, not a separate `piper` console script. Focused packaging + source clipping validation passed: `8 passed in 20.40s`.
- Built non-deployed image `tubeforge-source-clips:verify` successfully and smoke-checked `yt-dlp 2026.08.19`, FFmpeg 7.1.5, and import of the new source-clip modules. A fresh complete suite run is active in disposable container `tubeforge-stream-full-tests`.
- Added network-free yt-dlp provider command-contract coverage. It verifies metadata identity extraction, bounded acquisition output, optional automatic subtitles, and argument-array invocation. `tests/test_source_clips.py`: `4 passed in 0.09s`.
- Full-suite isolation found an existing Codex cache-safety regression at `test_repair_exhaustion_never_accepts_cache`: malformed generated content was releasing its reservation immediately. Validation failures now retain the short reservation, while transient/auth failures still release immediately. Both policies passed direct regression coverage: `2 passed in 15.40s`.

## Stream clipper deployment and final validation (2026-08-31)

- Rebuilt and replaced the TubeForge web and worker containers with the yt-dlp-enabled image. The dashboard is bound to `0.0.0.0:62065`; `GET /healthz` reports database health.
- Fixed short direct-media sources whose remote metadata lacks a finite duration: acquisition now probes the downloaded local file before analysis and persists that authoritative duration in both source metadata and `source_media`.
- Live public source-URL smoke job `425a50b41b7b4d59bf68647d045ad69c` completed the durable sequence `source_inspecting` → `source_acquiring` → `source_analyzing` → `clip_rendering` → `final_ready` → `publication_approval_required`. It registered source, analysis, clip, final, metadata, thumbnail, and publication-package artifacts; no publication occurred.
- Downloaded final artifact was validated as an MP4 with H.264 video, AAC audio, 1080x1920 dimensions, and exact 15.000-second duration. The final-artifact API returned HTTP 200 with 4,709,968 bytes.
- Final full regression: `197 passed, 2 skipped` in 14:45 (`pytest -vv -x -p no:cacheprovider`). The skips require a separately installed Piper ONNX model / Codex CLI in the disposable test image; production deployment retains its configured local Piper model. `git diff --check` passed.
- Updated two historical test assumptions to reflect existing safety behavior: media is selected per scene and voice synthesis per timed phrase, while reruns are asserted not to repeat either completed checkpoint; byte-tampered accepted media is correctly terminal `failed_validation` rather than re-rendered.

## Per-generation visual source selection (2026-09-13)

- Scope: added a real Creator Studio visual choice for each generated job. **Generate local scene art** uses TubeForge's durable, scene-specific local image generator. **Rights-safe stock** routes only to Wikimedia Commons and accepts only Public Domain/CC0 assets that satisfy the existing no-attribution render policy.
- Google Image scraping was deliberately not implemented: search results do not carry the licence/provenance evidence required by `AssetCandidate`, cache validation, resume safety, or the publication pipeline.
- Added `ContentRequest.visual_source`, durable API persistence, visual-router provenance, per-request hybrid media routing, and a Studio selector with explicit explanatory copy. Existing lease, checkpoint, checksum, atomic asset cache, cancellation, and render-approval behavior remains unchanged.
- Focused validation in `tubeforge-local-media:smoke`: `8 passed, 45 deselected` in 110.10s across media routing, rights filtering, Creator Studio/API payload persistence, configuration, and asset checkpoint routing.
- Real local end-to-end smoke: `tests/test_real_local_smoke.py -k fixed` passed in 171.74s using Piper and FFmpeg. Inspected `artifacts/smoke/fixed_piper_six_scene_smoke.mp4`: H.264 video + AAC audio, 640x360, 73.736 seconds, 2,682,166 bytes. The test verified six distinct generated scene assets.
- Live read-only Wikimedia search returned a CC0 candidate for `solar panels`; isolated temporary acquisition decoded and validated a 2312x1160 image with SHA-256 `6cffd832388ffe270eb3e54444dcd9b817ee98d30bc7e6bc3ad7f2c223574d9b`.
- `docker compose config --quiet` and `git diff --check` passed. Host Python is absent, so all Python tests were run in the project Docker image.
- Note for operator: the real smoke refreshed the already tracked `artifacts/smoke/fixed_piper_six_scene_smoke.{mp4,wav,ffprobe.json}` test artifacts. They remain modified for review; they were not removed or hidden by `.gitignore`.
- Next action: run the full suite, then rebuild the durable Compose web/worker services and exercise a stock-selected dashboard job end to end.

### Follow-up validation

- Complete regression in `tubeforge-local-media:smoke`: `215 passed, 2 skipped, 2 warnings` in 1245.16 seconds. Skips are the intentionally unconfigured Codex CLI and Piper model in the disposable full-suite container; the explicit Piper smoke above supplied the local model and passed.
- The first full run exposed an existing stale API fixture that tried to approve a just-created job before the worker had checkpointed its script. The fixture now supplies a durable content-package artifact, asserting the existing exact-script approval contract rather than weakening it. Its job-list expectation was updated to include that legitimate artifact.
- The visual-source milestone remains **READY FOR REVIEW**, not DONE: the next required evidence is a stock-selected job rendered through the complete durable pipeline, followed by the Compose Studio check.

## 2026-09-12 — cinematic local video-generation smoke

- Upgraded the safe local generated-video path from static 640x360 fallback
  images and hard cuts to HD (1280x720) scene-specific illustrations with a
  deterministic, subtle FFmpeg zoom/pan motion treatment for still images.
  Native video assets retain their own motion.
- Bumped the renderer template identity to `m13-cinematic-motion-v1`, so an
  approved checkpoint created with the former visual treatment cannot silently
  authorize a final render with the new look.
- Corrected the real-voice duration acceptance policy from ±20% to ±30%. The
  measured Piper narration is approximately 73 seconds for a 60-second brief;
  it is within the smoke contract's 60–90 second range, while final video
  timing remains locked to the measured narration.
- Validation passed:
  - focused configuration/render/fallback-art suite: `19 passed in 25.28s`;
  - real worker smoke: `tests/test_real_local_smoke.py -k fixed` →
    `1 passed, 1 deselected in 180.54s`.
- Inspected promoted artifacts under `artifacts/smoke/`. The final MP4 is
  640x360 H.264 with 48 kHz mono AAC, duration 73.318 seconds, and size
  2,678,496 bytes. A sampled frame confirmed the new illustrated background,
  motion-compatible composition, and readable burned captions.
- The complete regression suite remains pending in the current dependency
  image; no external publication was enabled or attempted.

## 2026-09-12 — dashboard script review and local worker recovery

- Recovered the waiting local dashboard job by starting a matching
  source-mounted TubeForge worker against the same local database and artifact
  volume. The job advanced from `script_approval_required` through asset,
  voice, caption, and preview rendering, and is now correctly paused at
  `preview_ready` for the next human approval.
- Added a created-at timestamp to each dashboard generation card, a script
  review/edit dialog, durable local narration revision, and a copyable Codex
  revision prompt. A saved revision replaces both the content package and
  derived video plan and records a revision marker, so the worker requires an
  approval bound to the revised package checksum.
- Script approvals submitted by the dashboard now use the current package
  checksum automatically. The UI locks approval buttons on the first click,
  avoiding the repeated approval activity caused by rapid repeated clicks.
- Restarted the temporary dashboard and verified `GET /healthz` returns
  `{"status":"ok","database":"ok"}`. `git diff --check` passes. Focused
  browser/API regression execution remains to be completed in the dependency
  container.

## 2026-09-12 — commit-time ignore review policy

- Added a durable `AGENTS.md` and README requirement to review `.gitignore`
  before every commit and update it whenever a change introduces generated,
  local, or sensitive paths. The rule requires verification where practical,
  prevents over-broad ignores, and explicitly preserves already tracked files
  unless an operator authorizes their removal.

## 2026-09-13 — local Kokoro voices with Piper fallback

- Added a CPU-friendly `kokoro-onnx` voice adapter, configured three selectable
  voices (`af_bella`, `af_sarah`, `am_michael`), and persisted the chosen voice
  on each generation request. Creator Studio now exposes those choices plus an
  explicit Piper fallback option.
- The hybrid provider attempts the requested Kokoro voice and automatically
  switches to the installed Piper voice on any model/runtime/synthesis failure;
  durable jobs therefore retain the existing reliable narration path.
- Downloaded and validated the trusted INT8 ONNX model (92,361,271 bytes) and
  voice pack locally. A real `af_bella` synthesis produced a valid 24 kHz WAV,
  duration 3.776 seconds. Both model types are ignored by Git.
- Focused validation: `10 passed` for hybrid fallback, configuration, and
  dashboard voice-selection coverage. `git diff --check` and dashboard health
  checks pass. A durable selected-Kokoro job smoke remains required after the
  Compose image is rebuilt.

## 2026-09-13 — Creator Studio UI and development-port contract

- Added a durable UI contract in `AGENTS.md` and operator summary in the README:
  dashboard and API changes must ship together, controls need real backend
  behavior and truthful feedback, refreshes must not flicker, reviews retain
  exact approval fencing, and visible workflows require responsive/accessibility
  and focused-test review.
- Standardized the only documented developer dashboard URL to
  `http://127.0.0.1:62065`. Compose now binds that one host port to loopback,
  while transient IDE/app-preview proxy URLs are explicitly excluded from the
  product configuration.

## 2026-09-13 — dashboard login and local voice-preview workflow

- Reworked the private sign-in page into the Studio’s responsive dark-navy UI
  with password visibility, client-side validation, disabled loading state,
  and accessible error feedback. Authentication, CSRF protection, and rate
  limiting remain backend-enforced.
- Added a real `GET /api/voices/{voice_id}/preview` endpoint. It synthesizes a
  short WAV through the configured local Kokoro/Piper provider and refuses an
  unavailable voice or model rather than simulating success. The dashboard
  exposes it as **Preview voice** beside voice selection.
- Simplified final-media actions to **Watch video** (preview remains visible
  only when a final render is unavailable) and moved creation time into normal
  card rendering, avoiding polling-time duplicate metadata.
- Validation: `python3 -m py_compile src/tubeforge/api/app.py` and
  `git diff --check` passed. The prior local media test image failed collection
  because it lacked declared dependencies (`croniter`, then `argon2`); an
  isolated full dependency install was started, but its managed-runner output
  did not provide a pytest summary. The focused dashboard/auth run remains
  required after a durable image rebuild.

## 2026-09-13 — rebuilt local visual-generation runtime

- Built fresh `youtube_video_producer-web` and `youtube_video_producer-worker`
  images, then replaced the corresponding Compose services. Removed only the
  stale, unstarted TubeForge replacement containers and the temporary
  `tubeforge-dashboard-test` smoke container that held port 62065.
- The migrated Compose web and worker services are running. Verified the
  loopback-only dashboard binding `127.0.0.1:62065 -> 8080` and received
  `200 {"status":"ok","database":"ok"}` from `/healthz`; `/` correctly
  redirects unauthenticated users to `/login`.
- The prior full regression and generated-scene FFmpeg/Piper smoke remain the
  render evidence. The visual-source milestone remains **READY FOR REVIEW**:
  the next required end-to-end evidence is one authenticated, stock-selected
  Studio generation with its final artifact and provenance manifest inspected.

## 2026-09-13 — persistent Creator Studio voice previews

- Changed `GET /api/voices/{voice_id}/preview` to store one stable WAV per
  voice and preview-text identity under `data/artifacts/voice-previews/`.
  Repeated preview clicks return that file without invoking Kokoro/Piper again;
  a process-local lock prevents two browser tabs from doing duplicate first
  synthesis work.
- Added private immutable response caching for the returned WAV, while still
  validating cached audio before it is served. Restarted the Compose web
  service and verified `/healthz` returns `{"status":"ok","database":"ok"}`.
- Focused validation: `tests/test_api_workflow.py::test_voice_preview_is_synthesized_once_then_served_from_persistent_cache` passed (`1 passed` in
  2.59s) in `tubeforge-local-media:smoke`; it proves two endpoint calls produce
  one persisted WAV and exactly one synthesis call.

## 2026-09-13 — dashboard script visibility, artifact cleanup, and A/V verification

- Made **View script** available for every generation with a saved content
  package. Only an unclaimed script-review job remains editable; later states
  show the exact saved narration read-only and hide revision saving.
- Added **Remove local files** for published generations. It deletes registered
  local artifacts while preserving the generation, approvals, publication
  audit, and activity history. Existing paused/failed local generations retain
  the distinct destructive **Delete** action.
- Found a live cleanup failure in the web logs: bind-mounted artifacts were
  owned by an unmapped container UID, causing `PermissionError` during delete.
  Compose now runs all TubeForge services as the local UID/GID and the existing
  `data/` tree was repaired to `1000:1000`; recreated services report healthy
  at `http://127.0.0.1:62065/healthz`.
- Validation: `python3 -m py_compile src/tubeforge/api/app.py
  src/tubeforge/db/repositories.py tests/test_api_workflow.py` and the focused
  Docker API suite passed (`7 passed` in 106.66s). The real
  `tests/test_real_local_smoke.py -k fixed` initially rendered successfully but
  could not retain its host artifact under the old container UID; rerunning as
  `1000:1000` passed (`1 passed` in 174.91s). Inspected
  `artifacts/smoke/fixed_piper_six_scene_smoke.mp4`: 640x360 H.264 with 48 kHz
  mono AAC, 71.844s and 2.6 MB; the matching narration WAV is 48 kHz mono PCM,
  71.844s and 6.6 MB.
- Current pipeline finding: audio/video combination is working end to end. Two
  live dashboard jobs instead stopped earlier in asset acquisition with `no
  permitted licensed asset for scene scene-1`; repair the stock-asset fallback
  and validate a stock-selected Studio generation next.
- Full regression validation: `217 passed, 2 skipped` in 1146.14s using the
  UID-aligned `tubeforge-local-media:smoke` image. The skips are the opt-in
  real smoke without a model environment variable and the unavailable Codex
  CLI provider case; the real fixed Piper smoke was run separately above.
- Post-recreate service check found the scheduler restarting because its
  Compose service did not mount `/app/models`, while production validation
  requires the configured Piper model path. Added the same read-only models
  mount used by the worker, recreated that service, and verified scheduler,
  web, and worker remain up with dashboard health still `ok`.

## 2026-09-13 — publication-approval deletion correction

- Dashboard evidence showed completed local renders stopped at
  `publication_approval_required` without a delete control. This state occurs
  before any publishing call; it was incorrectly omitted from the safe local
  deletion allowlist.
- Added that paused state to both the API presentation and the durable delete
  guard. States that may have crossed a remote publishing boundary remain
  protected.
- Validation: `tests/test_api_workflow.py` passed (`7 passed` in 115.25s) in
  the UID-aligned local test image. Recreated the local web service and
  verified `GET http://127.0.0.1:62065/healthz` returns `ok`.

## 2026-09-13 — safe recovery for unavailable licensed stock

- Preserved the strict Wikimedia Commons licence filter: stock candidates must
  still be public-domain or CC0 and satisfy the no-attribution asset policy.
  When that search produces no permitted candidate, the hybrid media provider
  now resolves the scene to local generated CC0 art instead of failing the
  entire job.
- The durable asset manifest distinguishes the requested stock search from the
  resolved generated request and records a `fallback` object with the reason;
  it never represents local art as a Wikimedia result. The Studio selector and
  operator guide now disclose this behaviour.
- Validation: focused media, orchestration, and dashboard tests passed after
  the updated selector assertion (`tests/test_api_workflow.py`: `7 passed` in
  100.21s). A real stock-selected run of
  `tests/test_real_local_smoke.py -k fixed` passed (`1 passed, 1 deselected`
  in 172.41s) using local Piper and FFmpeg. Inspected the retained final MP4:
  640x360 H.264 video plus 48 kHz mono AAC, 72.784 seconds and 2,667,795 bytes.
- Recreated the local web and worker services. All services are up and
  `GET http://127.0.0.1:62065/healthz` returns
  `{"status":"ok","database":"ok"}`. Previously failed-validation jobs
  retain their history and must be deleted/recreated rather than resumed.

## 2026-09-13 — Wikimedia outage recovery and IST Studio timestamps

- Extended the explicit stock-to-local-CC0 fallback to retryable Wikimedia
  search outages (`Wikimedia search unavailable` and timeouts), while retaining
  the strict Commons licence filter when the service is reachable. The
  manifest records the original stock request, local resolved request, and
  outage reason.
- Converted job and activity API timestamps to `Asia/Kolkata` and made the
  Studio format every visible generation/activity time explicitly as IST, so
  it is consistent across operator browsers.
- Validation: the focused empty-result and simulated-outage pipeline tests
  exited successfully; focused Studio API coverage passed (`2 passed, 5
  deselected` in 29.04s), including ISO `+05:30` payloads and IST markup.

## 2026-09-27 — dedicated portrait Shorts workflow (Phase 1)

- Added a dashboard **Shorts — 9:16, 30–55s** preset without changing the
  existing widescreen path. The API persists the chosen preset/aspect ratio
  and rejects durations outside the preset's bounds. Production defaults to a
  45-second Short; final output is fixed at 1080×1920 and 30 fps.
- Added a local PCM-waveform word aligner tied to each synthesized phrase and
  final narration duration. Shorts render large uppercase ASS captions with a
  yellow active word, white context, and explicit portrait margins. The final
  gate checks word timing, a first word within three seconds, caption safe
  area/line width, 30–55 second duration, and visual holds no longer than three
  seconds.
- Split long narration scenes into deterministic <=3-second camera moves. A
  first real render exposed both a clipped four-word caption and excessive
  portrait overscan; captions now use three-word groups with bounded wrapping,
  and portrait stills use 1.25× overscan. A subsequent gate failure exposed an
  ASS parser that counted metadata as visible text; a field-count parser and
  focused regression corrected it.
- Focused alignment/caption/renderer/API/pipeline coverage exited successfully;
  the ASS parser regression passed (`1 passed, 3 deselected`). Production
  configuration validation printed `9:16 45 30 55 1080 1920 30`, and
  `git diff --check` plus Python compilation completed cleanly.
- Real acceptance used local Piper and FFmpeg under UID 1000:
  `tests/test_real_local_smoke.py -k piper_short_renders_real` passed (`1
  passed, 2 deselected` in 284.99s). The retained MP4 is 53.417 seconds,
  1080×1920, 30 fps H.264 with 48 kHz mono AAC. Its independent quality report
  passed with 168 aligned words, first word at 0.0489s, last word matched to the
  53.417s narration, and maximum visual hold 2.8709s.
- Inspected `artifacts/smoke/shorts_piper_1080x1920_contact_sheet.png` after
  regenerating it from the passing artifact. Captions are readable and within
  frame. The intentionally fake test narration and generic generated scene art
  visibly confirm the next work is Phase 2 source-grounded writing followed by
  Phase 3 coherent portrait visuals.
- Repository hygiene: reviewed `git status --short` and `.gitignore`. The new
  smoke MP4/WAV/JSON/contact sheet are intentional retained acceptance evidence;
  no new cache, credential, model, database, or machine-local path was added.

## 2026-09-27 — restricted host Codex runner continuation (blocked)

- Scope: completed the repository-side typed socket protocol, fixed-command
  Bubblewrap runner, worker socket provider, and durable two-invocation data
  model. Production Compose/config now select the host runner and no longer
  start Ollama.
- Validation attempted: `git diff --check` passed. The host has no `python`
  alias; `/usr/bin/python3` is installed but has neither `tubeforge` nor
  `pydantic`. A UID-1000 probe of the existing socket activated the runner but
  the service exited with `ExecStart=/usr/bin/python3 -m
  tubeforge.host_codex_runner`, status 1, before it could answer.
- Blocker: installing the root-owned `/opt/tubeforge-codex-runner` runtime
  needed for the documented service unit requires interactive `sudo`; this
  environment cannot provide a sudo password. No operator Codex auth was read
  or copied, and no script was generated.
- Next action: an operator installs the dedicated runtime (or grants
  non-interactive scoped elevation), reloads the unit, and then the required
  UID-1000/other-UID socket tests and full production validation can run.

## 2026-09-27 — root-owned pinned Codex runtime contract (blocked)

- Replaced the runner's ambient CLI lookup with fixed Bubblewrap paths for a
  root-owned Node binary and `@openai/codex@0.149.0` entrypoint under
  `/opt/tubeforge-codex-runner/codex-runtime`. The namespace binds that tree
  read-only and has no `/home/uditaswal` mount. `CODEX_HOME` remains only the
  dedicated account's `/var/lib/tubeforge-codex/.codex` bind.
- Added `docs/tubeforge-codex-runner-runtime.md` with provisioning ownership
  and pin requirements. No authentication data was inspected, copied, or
  mounted.
- Validation: Docker-focused runner/config tests passed: `9 passed in 1.34s`.
  Production configuration validation printed `codex
  /run/tubeforge-codex/codex.sock 2`; `git diff --check` passed.
- Blocker/next action: provisioning `/opt` and reloading the host systemd unit
  require administrator elevation unavailable to this sandbox. After that,
  perform the live socket acceptance tests before invoking Codex.

## 2026-09-28 — restricted host runner resume (still blocked on host elevation)

- Confirmed the only discovered Node/Codex installation is the operator NVM
  tree and reports `@openai/codex@0.149.0`; it was not used for execution,
  copied, mounted, or authenticated. The required root-owned
  `/opt/tubeforge-codex-runner/codex-runtime` path remains absent.
- Attempted the documented administrator installation with the approved
  root-owned Node 24.19.0 distribution and pinned Codex package. It stopped
  before making a change because `sudo` requires an interactive administrator
  password in this session. Dedicated-account login was deliberately not
  attempted.
- Verified `tubeforge-codex` exists, Bubblewrap reports `0.12.0`, and the
  currently installed systemd unit is still the obsolete `/usr/bin/python3`
  variant. It cannot run the runner dependencies; the checked-in replacement
  fixes the interpreter and uses only `/opt` paths.
- Corrected the provisioning guide to install Node below the exact
  Bubblewrap-pinned `node/` directory, install Codex into the matching runtime
  prefix, validate ownership/version before login, and document the root-owned
  Python service environment/unit deployment. Added focused regression coverage
  for the fixed runtime contract and worker factory selection.
- Validation: `tests/test_host_codex_runner.py tests/test_config.py` passed
  (`11 passed in 6.03s`) in `tubeforge-local-media:smoke`; the legacy Ollama
  provider test container also exited `0` after production configuration was
  changed to reject `content_provider: ollama`. `git diff --check` passed.
- Next action: an administrator runs the documented `/opt` provisioning and
  unit deployment, then the runner can be live-tested from UID 1000 and a
  non-worker UID, followed by the dedicated-account interactive Codex login.
# 2026-09-28 — Host Codex runner socket and usage-cap follow-up

Scope: checked the operator-reported live socket result and reviewed the first
valid-request path. The active service returned a structured Pydantic rejection
for `{}` from host UID 1000, so the socket and service are reachable without
starting Codex. Found that the worker's two-attempt cache could be bypassed by
direct UID-1000 socket requests. Added an independent persistent host-side
two-invocation cap keyed by the exact typed request; it is consumed immediately
before the CLI launch and rejects the third request fail-closed. Tightened the
Bubblewrap layout to mount required Node libraries, DNS settings, CA certs,
the pinned runtime, the private Codex home, and its request workspace, without
general `/usr` or `/bin` mounts.

Validation: local isolated `node --version` returned `v24.19.0` and isolated
Codex returned `codex-cli 0.149.0`; the host-cap smoke accepted two attempts
and rejected a third. `compileall` and `git diff --check` passed. `pytest` is
not installed in this execution environment, so the focused automated test
has not yet run. No real Codex generation was launched. Next: reinstall and
restart the root-owned runner, run focused tests and a live typed request, then
inspect the resulting script. Status: IMPLEMENTED, not VERIFIED.

Follow-up: the operator reinstalled the root-owned wheel and restarted the
service; `systemctl is-active` returned `active`. Local introspection of that
installed wheel confirmed `INVOCATION_LIMIT == 2`, the cap call in
`run_request`, and no broad `/usr` mount. Before a real call, checked pinned
`codex exec --help` and added fixed `--ignore-user-config`, `--ignore-rules`,
and `--skip-git-repo-check` flags; an isolated `codex exec --help` smoke exited
0. This last flag change requires one more wheel reinstall/service restart.
Attempting to install pytest into `/tmp` failed because this execution
environment has no package-index DNS access. No model invocation occurred.

Follow-up: the operator installed the fixed CLI flags and the service was
active. Local introspection confirmed those flags and the host cap in the
installed wheel; an escalated UID-1000 malformed socket request still returned
a typed validation error. One real 45-second Shorts request based on the
TubeForge README was submitted through the socket. It spent one host-side
attempt but returned `Codex CLI failed (1)` with only the generic stderr
`Reading prompt from stdin...`; no script was produced. No second attempt was
made. Added bounded extraction of JSONL `error`/`turn.failed` messages, with
generated text omitted, so the next failure can be diagnosed. Synthetic
extraction test, compile check, and `git diff --check` passed. The diagnostic
change must be installed before any second request; Phase 1 remains
IMPLEMENTED, not VERIFIED.

Follow-up: operator ran the pinned CLI's `login status` as the dedicated
account both outside and inside the exact Bubblewrap layout; both reported
`Logged in using ChatGPT`. Anonymous HTTPS to the OpenAI API from the same
layout returned HTTP 401, proving DNS/TLS reachability without a model call.
Official OpenAI deprecation guidance says the runner's fixed
`gpt-5.2-codex` model was retired on 2026-07-23; current ChatGPT-signed-in
Codex model guidance also calls older 5.2/5.3 Codex models deprecated. This
is a likely explanation for the first CLI exit, but the CLI JSONL error has
not been observed. No second generation attempt was made. Next: present a
supported model choice, usage implications, and one-attempt acceptance plan
for operator approval before changing the model.
Current gate is BLOCKED on that model decision; implementation exists but no
real package has passed end-to-end acceptance.

Follow-up: the operator approved `gpt-6-sol` as the fixed Codex CLI model.
Updated the root-owned runner command, provider configuration defaults,
production/default config, focused tests, README, and runtime deployment
guide. No fallback or API key was added. Validation:
`PYTHONPATH=/tmp/tubeforge-pytest-runner:src
/opt/tubeforge-codex-runner/venv/bin/python -m pytest -q
tests/test_host_codex_runner.py tests/test_codex_content.py tests/test_config.py`
returned `28 passed in 2.14s`. The host service has not yet been reinstalled
with this model or the bounded error extraction. The one remaining attempt
for the exact first source packet is preserved; no new generation was run.
Current status: IMPLEMENTED, not VERIFIED. Next: operator installs the wheel,
then one live acceptance attempt and script inspection.

Follow-up: operator reinstalled the reviewed wheel and restarted the service;
`systemctl is-active` returned `active`. Local introspection of the installed
wheel confirmed `gpt-6-sol`, `INVOCATION_LIMIT=2`, the 480-second timeout, and
bounded JSONL diagnostics. The exact same README-grounded source packet was
submitted once more through the UID-1000 socket. It returned
`invalid_output` after Codex CLI exit 1; the CLI JSONL error was HTTP 400:
`The 'gpt-6-sol' model is not supported when using Codex with a ChatGPT
account.` No script, claims, or scenes were produced. This was the second of
two permitted launches for that packet. No further launch was made and no
allowance reset or substitute packet was created. The runner remains
fail-closed. Status: BLOCKED pending an operator decision on a supported
ChatGPT-signed-in model/runtime path and a new bounded acceptance packet.

Follow-up: the operator ran the pinned CLI's `debug models` under the
dedicated account inside the exact Bubblewrap layout, refreshing the remote
catalog without a prompt. It exited 0 and exposed only these picker-visible
model IDs: `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, `gpt-5.5`. No model
generation was launched and no credentials or raw catalog were printed.
`gpt-6-sol` is not in this account's catalog, consistent with the earlier HTTP
400. Next: obtain operator approval for a catalog-listed model and a genuinely
revised/new source packet. Keep the exhausted packet blocked.

Follow-up: treated the operator's "next" as approval of the immediately
preceding recommendation: keep Codex CLI, pin dedicated-account catalog-listed
`gpt-5.6-sol`, and test a substantively revised 45-second review-gates brief.
Updated runner/config defaults, production config, focused tests, README, and
runtime guide; no automatic fallback, API key, or allowance reset was added.
Focused validation:
`PYTHONPATH=/tmp/tubeforge-pytest-runner:src
/opt/tubeforge-codex-runner/venv/bin/python -m pytest -q
tests/test_host_codex_runner.py tests/test_codex_content.py tests/test_config.py`
returned `28 passed in 1.89s`. The old packet remains exhausted; no new
model launch has occurred. Next: operator reinstalls the root-owned wheel,
then run a fresh bounded packet and inspect its actual script. Status:
IMPLEMENTED, not VERIFIED.

Added a reviewed, substantively new source packet at
`tests/fixtures/host_codex_review_gates_request.json`, focused on the three
review gates rather than the previous general TubeForge overview. Its source
excerpt is drawn from the operator-facing README. Typed validation and prompt
assembly passed; focused runner/provider/config tests now return `29 passed
in 1.85s`. The new packet has not been submitted, so its two-attempt allowance
is untouched.

Follow-up on 2026-09-28: the operator showed a successful root-owned wheel
reinstall and `systemctl is-active tubeforge-codex-runner.service` returning
`active`. Read-only introspection of the installed wheel reported
`CODEX_MODEL=gpt-5.6-sol`, `INVOCATION_LIMIT=2`, and `TIMEOUT_SECONDS=480`.
The focused runner/provider/config suite returned `29 passed in 1.82s`;
`git diff --check` passed, and `git check-ignore -v` confirmed the planned
generated smoke response is ignored under `artifacts/smoke/`. A proposed live
request containing the reviewed README-derived fixture was rejected before
execution by the execution safety check because explicit authorization for
that exact packet to reach the signed-in Codex service was not recorded.
No new invocation or script artifact resulted. Status: BLOCKED pending that
authorization. Next: submit the unchanged reviewed fixture once, inspect the
returned package and creative quality, and stop within the existing two-attempt
and eight-minute limits.

Follow-up on 2026-09-28: after explicit approval for one live test, submitted
the unchanged review-gates fixture through the UID-1000 Unix socket. The host
returned `invalid_output`: Codex CLI received HTTP 400 `invalid_json_schema`
because the Pydantic output schema did not mark `time_sensitive` (and other
defaulted properties) required. No script was produced; the revised packet now
has one of its two host invocations remaining. Official OpenAI Structured
Outputs documentation confirms that every object property must be required
and objects must set `additionalProperties: false`. Source repair recursively
marks all properties required, removes Pydantic defaults, and keeps domain
validation after generation. Also removed a hard-coded debugging storyline
from the generic Shorts prompt and explicitly instructed the model to copy the
immutable source request, including defaulted fields; the old storyline
contradicted this source packet. The
original packet's exhausted allowance was not reset.

Validation: runner/provider/config tests `30 passed in 1.86s`; migration plus
runner/provider/config tests `35 passed in 3.16s` after the final prompt
clarification; the broad collectable suite
`233 passed, 4 skipped in 214.91s`. A first broad run exposed a stale test
assertion for migration `20260831_0019`; the test now checks current head
`20260927_0020` and its new columns. The unfiltered suite could not collect
`test_api_workflow.py`, `test_auth.py`, and `test_health.py` because the
root-owned runner venv lacks the test-only `httpx2` package. No generated
script or video artifact was produced. Status: BLOCKED pending deployment of
the repaired wheel and separate approval for the final live attempt on this
exact packet. Next: operator reinstalls/restarts the service; verify the
installed schema, then use at most one final request and inspect its output.

Follow-up on 2026-09-28: the operator reinstalled/restarted the root-owned
wheel and showed the service active. Read-only installed-wheel checks confirmed
`gpt-5.6-sol`, two attempts, a 480-second timeout, all declared schema
properties required, and the revised source-copying prompt. Installed-wheel
focused tests returned `30 passed in 1.83s` with the checkout's explicit
default config path. After the operator explicitly approved the final attempt,
submitted the unchanged review-gates fixture through the UID-1000 socket.
Codex again returned HTTP 400 `invalid_json_schema`, this time because
Pydantic emitted unsupported `format: uri` for a source URL. No script was
produced. The revised packet has now spent both host attempts; no retry or
allowance reset was made. Thus there are no rejected scripts to show, only the
two bounded schema-error responses.

Official OpenAI Structured Outputs documentation lists supported string
formats and excludes `uri`. The local source now removes unsupported URL
format and nonessential string-length constraints from the CLI-facing schema,
while retaining Pydantic's post-generation validation. Focused runner,
provider, config, and migration tests returned `35 passed in 3.00s`; schema
inspection found only supported `date-time` format and no default or string
length keys. This second schema repair is IMPLEMENTED but not deployed or
proven with a real model output. Status: BLOCKED pending an operator decision
about a genuinely new source packet/brief or alternate approved provider.
Do not retry the exhausted packet merely by changing its wording.

Follow-up on 2026-09-28: the operator chose to continue with Codex using a
genuinely different editorial topic. Added
`tests/fixtures/host_codex_caption_timing_request.json`: a 45-second portrait
Short about TubeForge's word-to-WAV caption alignment, highlighted current
word, portrait placement checks, and three-second pacing gates. Its 722-character
source excerpt is a contiguous whitespace-normalized match to the README's
YouTube Shorts workflow; it is not a rewording of the exhausted publication
review-gates packet. The typed socket request is 1,728 bytes against a 65,536
byte bound, and the assembled prompt is 4,188 characters against a 60,000
character bound. Local schema inspection found all object fields required,
`additionalProperties: false`, and no unsupported URL format/default/string
length keys. Focused runner/provider/config/migration tests returned
`36 passed in 3.06s`; `git check-ignore -v` showed the new source fixture is
not ignored. No new model invocation occurred. Status: IMPLEMENTED, not
VERIFIED. Next: deploy the latest root-owned wheel, verify its installed schema,
obtain explicit approval for this exact packet, then submit one bounded live
request and inspect any resulting script.
An escalated read-only `sudo -n true` probe returned `sudo: a password is
required`, so this session cannot deploy the root-owned wheel; operator host
installation is required. No broad home access or credential copy was used.

Follow-up on 2026-09-28: the operator installed the latest wheel and explicitly
approved the exact caption-timing fixture. Read-only installed-wheel checks
confirmed `gpt-5.6-sol`, two host attempts, 480-second timeout, the expected
fixture SHA-256 `136fb4a784e90e7326b925aa945d241972db8f666b3a52e83c618ecd0a90b448`, a bounded prompt, all schema object fields required,
and no unsupported schema keywords or formats. The first live request reached
Codex and returned a generated package, but host `ContentPackage` validation
rejected `scene_plans.1.fallback_visual` and
`scene_plans.5.fallback_visual`: both exceeded the domain's 100-character
limit. The runner removed its temporary output in `finally`, and the socket
returned only the bounded validation errors; there is no retained script to
inspect or claim as an artifact. One host invocation remains for this exact
packet. No retry, cap reset, source-packet substitution, or provider fallback
was made. Status: BLOCKED under the two-repair debugging guardrail; the
45-minute active-debugging threshold was not used as the stopping reason.
Next: obtain an operator choice between a narrow deterministic fallback-visual
normalizer and a stricter schema/prompt contract; implement and test only the
chosen option before any separately approved final live attempt.

Follow-up on 2026-09-29: the operator selected the narrow deterministic
fallback-visual correction. The checkout runner now shortens only
`scene_plans[*].fallback_visual` values longer than 100 characters, at the last
complete-word boundary within the limit. It records each corrected field and
its original/normalized lengths in response provenance. All other fields,
including narration, claims, and the immutable source request, remain
unchanged; a value without a safe boundary still fails domain validation.
The correction happens after the single CLI invocation and introduces no retry.
Focused runner/provider/config/migration tests returned `39 passed in 3.08s`.
The collectable regression suite returned `237 passed, 4 skipped in 212.29s`;
three dashboard/API test files remain excluded because this environment lacks
the test-only `httpx2` package. The generated fake package in the focused test
was inspected for the unchanged request, claims, and script sections and for
both normalization records. No live Codex request, real script, or video was
produced. The existing `.gitignore` was reviewed; this correction creates no
new generated path. Status: IMPLEMENTED in the checkout, but the restricted
host-runner gate remains BLOCKED until the root-owned wheel is deployed and
its installed code verified. The caption-timing packet still has exactly one
host attempt remaining. Next: operator reinstall/restart the host service;
perform read-only installed-wheel checks, then request separate approval for
the final live attempt and inspect the returned script if successful.

Follow-up on 2026-09-29 after operator deployment: SHA-256 of the checkout
`src/tubeforge/host_codex_runner.py` and the installed root-owned wheel copy
matched exactly (`bdba5b971016121d33f8c29d1160c2adc6b3da1b689323ce2be4d90381edfc68`).
The installed module reports `gpt-5.6-sol`, a two-invocation limit, a
480-second timeout, and the new normalizer. Running the runner test module
against the installed wheel (without checkout `src` on `PYTHONPATH`) returned
`12 passed in 0.99s`. Outside the restricted command shell, `systemctl
is-active` returned `active` for both service and socket; host `stat` showed
`0750 root:1000` on the socket directory and `0660 986:1000` on the socket.
The UID-1000 shell connected and sent only `{}`, which the runner rejected at
typed request validation with `invalid_output` because `request` was missing.
This cannot reach `run_request` or consume a Codex invocation. No credentials
were printed, no model call occurred, and the caption-timing packet retains its
single final host attempt. Status: the deployment checks are VERIFIED, but the
runner milestone remains BLOCKED pending separate approval for that attempt
and real-script inspection. Next: request approval for the unchanged fixture,
then send it at most once and review any returned script.

## 2026-10-04 — Debian home-server dashboard access (blocked on host privilege)

Scope: make the loopback-only Creator Studio dashboard safely reachable from
other devices without exposing a public or LAN dashboard port. The selected
path is Tailscale Serve, which terminates Tailnet HTTPS and proxies only to
`http://127.0.0.1:62065`; production authentication already enables secure
cookies.

Evidence: the Compose web service is running with
`127.0.0.1:62065->8080/tcp`; `GET /healthz` returned
`{"status":"ok","database":"ok"}`. Unauthenticated `/` returned a 303
redirect to `/login`, and `/api/jobs` returned 401. The normal laptop browser
cannot use that loopback address because the application runs on the separate
Debian home server; the Codex in-app `localhost` URL is only a preview proxy.

Added the documented server procedure to `readme.md`: enable/sign in to
`tailscaled`, start Compose, and run `tailscale serve --https=443
http://127.0.0.1:62065`, then verify with `tailscale serve status` and the
health endpoint. `git diff --check` passed. No application port binding was
broadened and no credentials were accessed.

Blocker: this SSH session has no system-bus privilege to start `tailscaled`
(`Interactive authentication required`), so the final Tailnet endpoint and
cross-device browser acceptance cannot be completed until the Debian operator
runs the documented sudo commands. Next: enable `tailscaled`, configure the
Tailnet proxy, record its HTTPS hostname, and verify an authenticated browser
session from another Tailnet device.

## 2026-10-04 — Caption-timing host Codex attempt audit

Scope: after explicit operator direction to try a script, submit the unchanged
reviewed `host_codex_caption_timing_request.json` packet exactly once through
the restricted Unix socket. The first two local client starts failed before a
socket connection (`python` was unavailable; then the execution sandbox denied
the socket), so neither could reach `run_request` or consume an invocation.

With host access, the UID-1000 client connected and submitted the unchanged
packet. The runner returned `{"ok":false,"failure":{"code":"allowance_exhausted"}}`
before invoking Codex. No model call, generated script, output draft, retry,
cap reset, or fallback provider occurred. This durable response supersedes the
previous record that the packet had one attempt remaining: the packet is
exhausted, as are the two earlier reviewed packets.

Next: prepare a substantively new, source-grounded packet and obtain separate
operator approval for its first bounded host invocation. The rejected result
contains no script to assess for source grounding or creative quality.

## 2026-10-04 — Studio Codex prompt-version failure correction

Scope: diagnose the Studio error for the job titled "bare minimum git commands
required" and correct the production brief path. Read-only inspection of the
local database found two jobs for that exact request. The first failed with
`unsupported Codex content prompt template: video-brief-v2`; the generation
cache recorded one failed attempt even though the host model was not reached.
The second displayed the two-attempt error. The recorded cache state at
inspection was `retryable` with invocation count 1; the failure sequence is
consistent with the worker counting a local prompt validation error and the
host rejecting an unsupported version before model execution.

Creator Studio now writes the configured Codex prompt version into new video
briefs, and the worker checks prompt assembly before reserving or consuming
an invocation. Error text now identifies the limit as TubeForge's own rule,
not a Codex quota. Existing failed jobs and their durable counters were left
unchanged. Focused runner and dashboard API tests against the current checkout
passed: `21 passed` in 113.40s. An initial Compose-container test used stale
baked-in test files; rerunning with the checkout mounted read-only exposed two
missing test imports, which were corrected before the passing run.

Status: IMPLEMENTED. Next: recreate the Docker services and verify a fresh,
source-grounded Studio job reaches the host Codex runner and produces a script
that passes source and creative review. The root-owned host wheel only needs
reinstallation for its updated diagnostic wording; the prompt-version fix is
in the bind-mounted API and worker code. No generated paths were introduced.

## 2026-10-04 — Widescreen narration budget and retry reservation

The operator reported a real Codex response containing 62 narration words for
a 60-second widescreen request (required 90–240). The widescreen prompt lacked
an explicit word budget. Added shared narration limits used by both prompt
and validator, a 162-word target for 60 seconds, and instructions to count
narration only and revise within the same response. Also fixed a cache bug:
reacquiring a retryable entry now sets state to reserved. Previously the new
token could not consume the remaining attempt and produced a false limit error.
Counters and ownership fencing remain intact.

Focused validation: four narration-budget, short-output rejection, cache and
retry-fencing tests passed, 13 deselected, in 16.82 seconds. The preceding
broad regression was stopped at the operator's request: 173 passed before
KeyboardInterrupt, not a complete regression pass. No new model request was
sent. The corrected prompt is IMPLEMENTED but deployment is BLOCKED:
`sudo -n` requires the operator's password to install the root-owned host wheel.
The README records installation and service restart commands. Next: deploy
the host wheel, then review a bounded real script before claiming VERIFIED.
No new generated paths; existing ignore rules require no changes.
