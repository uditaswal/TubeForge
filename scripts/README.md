# Development helpers

Run these scripts from the repository root. They are developer tools, not
production worker entry points.

| Script | Purpose | Preconditions |
| --- | --- | --- |
| `test_offline_workflow.sh` | Fake-provider local pipeline smoke; automatically approves local gates | Isolated stack, authentication disabled, fake content/voice/media, publishing disabled |
| `test_script_config.sh` | Example invocation of the offline smoke helper | Same isolated environment |
| `render_scene_fixture.py` | Render a script-bound scene fixture and six-tile contact sheet for local visual review | Project Python environment, FFmpeg, and a fixture with exact package/source hashes; output belongs under ignored `data/` or `artifacts/smoke/` |
| `check_word_annotation.py` | Compare independent audio-only word marks with a scene's rendered candidate timing; report p95/maximum drift and fail the gate when either limit is exceeded | Exported annotation JSON, candidate JSON, render manifest, exact WAV/MP4 and the explicit job-global scene origin in seconds |
| `codex_overnight.sh` | Historical autonomous development supervisor | Requires a supplied `OVERNIGHT_MISSION.md`; unavailable by default |

`run_codex_overnight.sh` is a separate historical development runner using
`docs/HANDOFF.md` (run it as `bash scripts/run_codex_overnight.sh`; the old
root-level shim was removed). It is not used for production scripts.
Neither development runner should be invoked merely to validate repository
cleanup. Generated output under `autonomous_logs/` and `.codex-overnight/` is
local-only. Production commands are in [the operator guide](../readme.md) and
[the authenticated API guide](../docs/operations/api-workflow.md).

`render_scene_fixture.py` also requires `--database` and `--job-id`. It reads
the local TubeForge database to check the exact script approval and latest
recorded package/source hashes before rendering; a sidecar's own approval field
is never sufficient. It does not create a pipeline job or publish media.

For the timing audit, run `python3 scripts/check_word_annotation.py ANNOTATION.json
CANDIDATE.json RENDER-MANIFEST.json SCENE.wav SCENE.mp4 --candidate-origin-seconds SECONDS
--output AUDIT.json` after the reviewer exports marks. The tool checks the
annotation method, reviewer name, audio/video hashes, exact word labels and
ordinals, scene ID, the candidate/video hashes recorded in the render manifest,
and every boundary before computing drift. The origin is
required because production timing is job-global while the review audio is
scene-local; it must come from the scene's render timeline, never from a
guessed first-word timestamp. The command exits nonzero on a failed timing
threshold or invalid evidence. Keep the annotation and audit under ignored
local artifacts unless there is an explicit reason to version a redacted
fixture. No AI-generated or same-model word marks count as independent review.
