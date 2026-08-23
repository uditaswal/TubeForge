# TubeForge Overnight Mission — M24 to M26

## Overall Goal

Use this overnight autonomous development session to move TubeForge from its current dummy-video state to a genuine locally runnable AI-video pipeline.

The agent has approximately 8 hours available.

Do not stop after implementing the first successful component.

Work through the milestones below sequentially:

1. **M24 — Real Local Voice + Video Smoke Test**
2. **M25 — Multi-Scene Visual Generation Pipeline**
3. **M26 — Pluggable LLM Script Generation using Codex CLI + Open-Source Models**

Continue until all milestones are complete, the time budget is exhausted, or a genuine external blocker makes further progress impossible.

Do not declare overall SUCCESS unless all three milestones have been implemented and validated.

---

# M24 — Real Local Voice + Video Smoke Test

## Goal

Replace the existing dummy/text-sheet video path with a real locally generated 60–90 second narrated multi-scene video.

No paid APIs may be required.

## Required Pipeline

```text
Fixed deterministic script
        ↓
Piper TTS
        ↓
real WAV narration
        ↓
scene timing
        ↓
multiple scene images
        ↓
FFmpeg
        ↓
real playable MP4
```

## Requirements

1. Create a deterministic test script.

2. The script must contain at least 6 scenes.

3. Every scene must have at minimum:

```text
scene_id
narration
visual_description
image_path
```

4. Do not create one static text sheet for the entire video.

5. Generate narration using **Piper locally**.

6. Piper must run without a paid API.

7. Generate a real WAV narration artifact.

8. Validate the WAV using `ffprobe`.

9. Measure actual narration duration rather than assuming duration.

10. Produce scene timings based on narration duration.

11. Use multiple different local/test images.

12. Each scene should visibly differ from surrounding scenes.

13. Assemble the video using real FFmpeg.

14. The final video must:

* be playable
* contain a video stream
* contain an audio stream
* contain narration
* contain multiple visual scenes
* have valid dimensions
* have duration greater than 30 seconds
* ideally be 1920×1080
* be non-empty
* be recognized correctly by `ffprobe`

15. Preserve the existing TubeForge architecture where practical.

16. Do not bypass the orchestrator merely to produce an isolated demo script unless necessary for debugging.

17. Existing checkpoint/resume behavior must continue working.

18. Existing job lease and ownership fencing must continue working.

19. Existing cancellation protections must continue working.

20. Atomic artifact promotion must remain intact.

---

# M24 Testing

Add automated tests for the new behavior.

Run relevant focused tests first.

Then run the complete existing test suite.

Finally execute one real local end-to-end smoke job.

Validate the generated file with real `ffprobe`.

Record at minimum:

```text
format duration
video codec
audio codec
width
height
fps
audio sample rate
file size
```

Save the smoke artifact underneath:

```text
artifacts/smoke/
```

Do not declare M24 complete from mocked FFmpeg/Piper tests alone.

A real generated video must exist.

---

# M24 Completion Criteria

M24 is complete only when:

```text
fixed script
    ↓
Piper
    ↓
real WAV
    ↓
scene timing
    ↓
multiple visual scenes
    ↓
FFmpeg
    ↓
real validated MP4
```

passes locally.

Once M24 passes, immediately continue to M25.

Do not stop and wait for user approval.

---

# M25 — Real Multi-Scene Visual Pipeline

## Goal

Replace the crude current visual implementation with a reusable visual pipeline capable of producing scene-specific visuals.

The system should no longer create a single sheet containing context text for the whole video.

## Architecture

Create a clean visual-provider abstraction.

Conceptually:

```text
Scene
  ↓
visual_description
  ↓
VisualProvider
  │
  ├── LocalTestVisualProvider
  ├── StockImageProvider      [optional/future]
  └── ImageGenerationProvider [optional/future]
  ↓
scene image
  ↓
validation
  ↓
video renderer
```

Names may differ if the current TubeForge architecture has better conventions.

Prefer adapting existing architecture over introducing unnecessary new abstractions.

---

# M25 Required Behavior

Each scene must be independently capable of selecting or producing its own image.

Example conceptual scene:

```json
{
  "scene_id": 1,
  "narration": "Ancient Rome became one of the most powerful civilizations in history.",
  "visual_description": "cinematic reconstruction of ancient Rome at sunset",
  "image_path": "artifacts/scenes/scene_001.jpg"
}
```

A second scene must reference a different visual:

```json
{
  "scene_id": 2,
  "narration": "But centuries of political instability gradually weakened the empire.",
  "visual_description": "dark Roman senate chamber with political conflict",
  "image_path": "artifacts/scenes/scene_002.jpg"
}
```

---

# M25 Local Test Visual Provider

Create a deterministic provider usable in tests and offline environments.

It may:

* use bundled test images
* generate simple synthetic images
* select from locally available assets
* use properly licensed offline test assets

It must NOT require:

* OpenAI image APIs
* paid image APIs
* paid stock subscriptions

The test provider exists primarily to prove TubeForge's visual pipeline.

---

# M25 Image Validation

Before accepting an image:

* file must exist
* file must be non-zero
* image must decode successfully
* dimensions must be known
* dimensions must be positive
* format must be supported
* image must comply with the project's existing media validation policy

Invalid images must not be promoted into final artifact locations.

Preserve existing atomic-validation semantics.

---

# M25 Visual Rendering

Improve the visual quality enough that the generated smoke video resembles a real slideshow/video rather than a debugging artifact.

Implement simple motion if practical:

* slow zoom
* slow pan
* Ken Burns-style movement
* crossfade between scenes

Do not spend excessive time building sophisticated animation.

Reliability is more important than cinematic complexity.

Minimum requirement:

```text
scene 1 → image A
scene 2 → image B
scene 3 → image C
...
```

A video that merely changes between legitimate images is acceptable.

A single text-filled sheet is not.

---

# M25 Optional Enhancements

Only attempt these after core M25 functionality passes:

* burned subtitles
* simple scene transitions
* subtle zoom/pan
* background music support
* text overlays
* title card

Do not allow optional enhancements to break the core pipeline.

---

# M25 Testing

Add tests proving:

1. different scenes can resolve to different image paths
2. invalid images are rejected
3. validated assets are promoted correctly
4. checkpoint recovery revalidates existing visual artifacts appropriately
5. rendering receives the correct scene/image mapping
6. final rendered video visibly consists of multiple scenes

Run existing asset/orchestrator/render tests.

Then rerun the end-to-end real smoke video.

Validate it again with `ffprobe`.

---

# M25 Completion Criteria

M25 is complete only when:

* at least 6 scenes exist
* at least 6 scene visual assignments exist
* multiple different scene images actually appear in the produced video
* no single context/debug sheet is being used as the final visual output
* real FFmpeg rendering passes
* existing tests remain passing

Once M25 passes, immediately continue to M26.

---

# M26 — Pluggable LLM Script Generation

## Goal

Replace the hardcoded test-script requirement with a reusable script-generation provider layer.

TubeForge must support both:

1. **Codex CLI**
2. **free/open-source local LLM providers**

Do not hard-wire TubeForge directly to a single model provider.

---

# Required Architecture

Create an interface similar conceptually to:

```text
ScriptGenerator
       │
       ├── FixedScriptProvider
       │
       ├── CodexCLIProvider
       │
       └── OllamaProvider
```

Exact class and module names should follow existing project conventions.

The rest of TubeForge should consume a normalized script result and should not need to care which LLM produced it.

---

# Normalized Script Structure

The generated result should contain enough information for video production.

At minimum:

```json
{
  "title": "Why the Roman Empire Collapsed",
  "hook": "Rome did not fall in a single day.",
  "scenes": [
    {
      "scene_id": 1,
      "narration": "At its peak, Rome controlled enormous territory.",
      "visual_description": "cinematic aerial reconstruction of ancient Rome"
    }
  ]
}
```

The system may define a richer schema if one already exists.

---

# Script Validation

Never trust raw LLM output directly.

Validate:

* valid structured output
* title exists
* scenes exist
* minimum scene count
* narration exists for every scene
* visual description exists for every scene
* no blank scenes
* reasonable total narration size
* unique/ordered scene identifiers

Malformed LLM output must fail clearly rather than being silently passed to FFmpeg.

---

# Codex CLI Provider

Implement a provider that can invoke Codex CLI non-interactively.

Conceptually:

```bash
codex exec "..."
```

Use subprocess execution safely.

Requirements:

* configurable executable path
* timeout
* capture stdout
* capture stderr
* check exit code
* reject empty output
* parse structured output
* provide useful errors
* avoid shell injection
* do not use `shell=True` unless absolutely necessary
* do not put secrets into generated prompts

The provider should work with the user's locally authenticated Codex CLI.

Do not require an OpenAI API key for this provider.

---

# Codex Prompt Requirements

Ask Codex to output only the expected structured format.

Example conceptual prompt:

```text
Generate a YouTube video script about:

{topic}

Target duration:
60–90 seconds

Generate at least 6 scenes.

For every scene provide:

- narration
- visual_description

Return valid JSON only.

Do not include Markdown.
Do not include commentary.
```

Use the project's actual schema.

---

# Codex Provider Test

If the Codex CLI is authenticated and working on the host, execute at least one real script-generation smoke test.

Example topic:

```text
Why the Roman Empire Collapsed
```

Validate the returned result with the same production schema validator.

Do not declare Codex CLI integration complete based solely on mocked subprocess tests if a real CLI invocation is available.

---

# Open-Source LLM Support

Implement support for an open-source/local inference backend.

Prefer Ollama because it is simple and widely supported.

Architecture should allow configuration similar to:

```text
LLM_PROVIDER=ollama

OLLAMA_BASE_URL=http://localhost:11434

OLLAMA_MODEL=<configured model>
```

Do not assume Ollama must be running on the same server.

It must be possible to point TubeForge to:

```text
http://another-machine-on-the-lan:11434
```

The Debian server may therefore orchestrate TubeForge while another machine performs LLM inference.

---

# Ollama Provider Requirements

Implement:

* configurable endpoint
* configurable model
* connection timeout
* inference timeout
* structured prompt
* response parsing
* normalized output schema
* retry only where appropriate
* useful failure messages

Do not make a specific large model mandatory.

The implementation should work with any compatible Ollama model capable of producing the required schema.

---

# Resource Constraints

The current server may not be capable of running a good large model locally.

Therefore:

DO NOT make installation or successful execution of a large Ollama model on this server a condition for completion.

Instead:

* implement the provider
* add mocked provider tests
* optionally validate against a very small model if practical
* allow remote Ollama endpoints

Do not waste hours trying to run a 7B+ model on unsuitable hardware.

---

# Fixed Script Provider

Keep the deterministic fixed-script provider.

It is important for:

* automated tests
* offline testing
* deterministic smoke tests
* debugging failures independently from LLM output

The existence of Codex/Ollama support must not make the test suite dependent on live LLM inference.

---

# Provider Configuration

The active provider should be configurable.

Conceptually:

```text
SCRIPT_PROVIDER=fixed
```

or:

```text
SCRIPT_PROVIDER=codex
```

or:

```text
SCRIPT_PROVIDER=ollama
```

The default for automated tests should remain deterministic.

---

# M26 End-to-End Validation

Once Codex CLI integration works, execute:

```text
topic
   ↓
Codex CLI
   ↓
structured script
   ↓
schema validation
   ↓
Piper narration
   ↓
scene visuals
   ↓
FFmpeg
   ↓
real video
```

Generate at least one actual video from an LLM-produced script if Codex CLI authentication is available.

This is the primary M26 real smoke test.

Save the resulting artifact under:

```text
artifacts/smoke/
```

Use a filename clearly identifying the LLM smoke test.

For example:

```text
artifacts/smoke/codex_generated_smoke.mp4
```

---

# M26 Testing

Add tests covering:

* provider selection
* fixed provider
* Codex subprocess invocation
* Codex timeout
* Codex non-zero exit
* malformed Codex output
* structured output validation
* Ollama success response
* Ollama unavailable
* Ollama timeout
* malformed Ollama response
* normalized provider output
* orchestrator integration

Use mocks for automated provider tests.

Use real Codex CLI only for smoke/integration validation.

---

# Autonomous Execution Rules

You are operating autonomously overnight.

Do not stop after making one change.

Do not stop merely because a unit test fails.

Do not stop merely because Docker fails to start.

Do not stop merely because FFmpeg produces an error.

Investigate.

Read logs.

Find the root cause.

Fix it.

Rerun validation.

Continue.

---

# Working Loop

Use this general loop:

```text
inspect current state
        ↓
identify highest-priority incomplete requirement
        ↓
implement smallest correct change
        ↓
run focused tests
        ↓
failure?
   ↓ yes        ↓ no
diagnose      continue
   ↓
fix
   ↓
rerun
        ↓
checkpoint progress
        ↓
next requirement
```

Do not repeatedly redesign working code.

Build incrementally.

---

# Dependency Handling

You may install safe local dependencies required for this mission.

Examples:

* FFmpeg
* ffprobe
* Piper
* Piper voice/model files
* Python dependencies
* test dependencies

Prefer project/container dependency management if that is already how TubeForge is structured.

Do not alter unrelated system services.

Do not install large optional LLM models just because time remains.

---

# Docker

TubeForge currently runs using Docker Compose.

Inspect:

```bash
docker compose config
docker compose ps
docker compose logs
```

Determine whether required tooling should live:

* inside the worker image
* inside another TubeForge image
* on the host

Prefer reproducibility.

If Piper/FFmpeg are production runtime dependencies, favor making them part of the appropriate Docker image rather than relying solely on undocumented manual host installation.

Do not break existing Compose services.

---

# Existing Reliability Guarantees

Preserve all existing safety work.

Do not regress:

* renewable worker leases
* global heavy-work lease
* stale worker fencing
* checkpoint ownership
* state-transition ownership
* render artifact ownership
* cancellation
* atomic file promotion
* checkpoint resume
* durable approvals
* renderer provenance
* media validation

Run the existing associated tests after significant pipeline changes.

---

# Git Safety

Before making changes inspect:

```bash
git status --short
git diff
```

Do not discard existing user work.

Do not execute:

```bash
git reset --hard
git clean -fd
```

Do not push anything to a remote repository.

Commits are optional unless repository instructions explicitly require them.

---

# Paid Services

Do not use:

* OpenAI API billing
* paid image APIs
* paid TTS APIs
* paid stock media APIs

Codex CLI authenticated using the user's existing Codex/ChatGPT access is allowed.

Local/open-source tooling is allowed.

---

# Time Management

This is approximately an 8-hour autonomous session.

Prioritize in this order:

## Priority 1

Produce a genuine playable narrated MP4.

## Priority 2

Produce real multi-scene visual behavior.

## Priority 3

Integrate Codex CLI script generation.

## Priority 4

Implement clean Ollama/open-source provider support.

## Priority 5

Improve tests, resilience and documentation.

Do not spend the majority of the session polishing minor details while a later milestone remains completely unimplemented.

---

# Progress File

Maintain:

```text
AUTONOMOUS_PROGRESS.md
```

Update it throughout the session, not only at the end.

It should contain:

```text
current milestone
completed requirements
current implementation
tests run
test results
smoke results
known failures
current blockers
next action
```

This allows another Codex invocation to continue correctly if the current invocation ends.

---

# Failure Handling

If something cannot be completed, distinguish between:

## Fixable Local Failure

Examples:

* package missing
* wrong command
* incorrect config
* failing test
* bad FFmpeg arguments
* malformed generated JSON
* incorrect path
* container build failure

Fix it and continue.

## Genuine External Blocker

Examples:

* Codex authentication unavailable
* service quota exhausted
* required external service inaccessible
* hardware fundamentally incapable of required operation

Document the blocker.

Continue working on other milestones that do not depend on it.

Do not stop the entire mission because one optional provider is unavailable.

---

# Final End-to-End Target

The desired final flow is:

```text
Topic
  ↓
ScriptProvider
  │
  ├── Fixed
  ├── Codex CLI
  └── Ollama
  ↓
Validated structured script
  ↓
Scenes
  ├── narration
  └── visual description
  ↓
Piper TTS
  ↓
real narration
  ↓
VisualProvider
  ↓
different scene visuals
  ↓
FFmpeg
  ↓
real narrated multi-scene MP4
```

---

# Final Validation

Before declaring overall SUCCESS:

1. Run relevant focused tests.

2. Run the complete test suite.

3. Run one deterministic fixed-script real-video smoke test.

4. Run one Codex-generated script smoke test if authenticated Codex CLI is available.

5. Validate generated videos with real `ffprobe`.

6. Confirm audio and video streams exist.

7. Confirm output duration is greater than 30 seconds.

8. Confirm dimensions are valid.

9. Confirm multiple scene visuals are being rendered.

10. Confirm generated files are non-zero and playable.

11. Confirm restart/checkpoint behavior has not obviously regressed.

12. Confirm worker safety tests still pass.

---

# Final Report

Write the final report to:

```text
AUTONOMOUS_PROGRESS.md
```

Include:

## M24

* implementation
* files changed
* Piper details
* FFmpeg details
* tests
* smoke result
* ffprobe result

## M25

* visual-provider architecture
* scene-image handling
* validation
* tests
* smoke result

## M26

* ScriptProvider architecture
* Codex CLI integration
* Ollama integration
* structured-output validation
* tests
* real Codex invocation result if available

## Overall

* complete test-suite result
* generated artifact paths
* exact ffprobe results
* remaining risks
* known limitations
* recommended next milestone

---

# Success Marker

Only after ALL mandatory requirements that are locally achievable have passed, create:

```text
.autonomous_success
```

Do not create this marker because:

* code compiled
* unit tests alone passed
* mocks passed
* one milestone passed
* Codex believes implementation looks correct

The marker means the real pipeline has been exercised and independently validated.

---

# Definition of Overall SUCCESS

Success means TubeForge can demonstrate:

```text
Codex-generated or deterministic script
              ↓
       validated scenes
              ↓
          Piper TTS
              ↓
         real narration
              ↓
    multiple scene visuals
              ↓
            FFmpeg
              ↓
       real playable video
```

with no paid API required.

Additionally:

```text
FixedScriptProvider = working
CodexCLIProvider     = working when authenticated
OllamaProvider       = implemented and tested
Piper                = working
FFmpeg               = working
multi-scene visuals  = working
automated tests      = passing
real smoke test      = passing
```

Do not wait for further instructions between M24, M25 and M26.

Complete M24 and continue immediately to M25.

Complete M25 and continue immediately to M26.

Use the available overnight execution window productively.

