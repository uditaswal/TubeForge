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

