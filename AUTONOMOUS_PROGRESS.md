# TubeForge Autonomous Progress

## Current milestone

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
