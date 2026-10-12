# Docker tutorial benchmark sources

This is the local benchmark renderer and its accepted content, separate from the production worker. It does not publish or bypass production jobs/approvals.

- `brief.json`: the full topic/audience/language/length/source brief sent to the production Codex runner.
- `content-package.json`: the accepted 115-word narration, sources/claims, hook alternatives and scene intent. Only ordered `script_sections[].narration` becomes speech.
- `topic.json`: visual layout data, local voice and speed. It references the package rather than duplicating narration.
- `produce.py`: local Kokoro narration, Whisper transcript alignment, original ducked sound bed, Pillow terminal frames and checked FFmpeg encode. The local rendering approach and terminal/caption separation were informed by the user-supplied Claude scripts; see the benchmark guide for attribution and limitations.
- `capture_demo.py`: optional execution of the five-command disposable Docker exercise, with collision refusal and cleanup of only its own container.
- `verify.py`: checks the actual final bytes, source/audio hashes, dimensions, duration, decode, caption completeness/ordering and audio level.
- `requirements.lock`: versions actually used in the isolated Python 3.13 benchmark environment. Models, media and local environments are ignored, not vendored.

## Local reproduction

Run from the project root. Requires FFmpeg/ffprobe and DejaVu Sans/Mono fonts at the paths in `produce.py`. Existing Kokoro weights are `models/kokoro-v1.0.int8.onnx` and `models/voices-v1.0.bin`. Review and provision model files according to their upstream terms; the scripts never install dependencies automatically.

```sh
python3 -m venv .venv-benchmark
.venv-benchmark/bin/pip install -r examples/docker-short-benchmark/requirements.lock
```

Provision the local Whisper `base.en` alignment cache once (network download of model weights, no remote inference):

```sh
.venv-benchmark/bin/python -c "from faster_whisper import WhisperModel; WhisperModel('base.en', device='cpu', compute_type='int8', download_root='data/benchmark/models')"
```

Then:

```sh
.venv-benchmark/bin/python examples/docker-short-benchmark/produce.py prepare
.venv-benchmark/bin/python examples/docker-short-benchmark/produce.py stills
# Inspect the contact sheet and full-size frames before encoding.
.venv-benchmark/bin/python examples/docker-short-benchmark/produce.py render
.venv-benchmark/bin/python examples/docker-short-benchmark/verify.py
```

The final is `artifacts/benchmark/docker-short/final/docker-short.mp4`. That directory also retains the exact timeline, aligned words, narration WAV, final mix, source/output hashes, ffprobe record and visual sheets. Voice synthesis is cached by text, voice, speed and model hash. Final render refuses a stale topic/package identity or changed phrase audio. Text bounds are checked in every rendered frame. A successful encode is inspected before atomic promotion from `.partial.mp4`.

The optional command capture is explicit and creates an unexposed `demo` container only when that name is unused:

```sh
python3 examples/docker-short-benchmark/capture_demo.py --execute --output data/benchmark/docker-short/docker-command-evidence.json
```

The terminal listing is deliberately condensed and labelled; the log excerpt omits its path prefix and is labelled. Whisper sometimes collapses an article to a zero-length boundary; those words stay in the adjacent measured group and highlight together. This is audio-based alignment, not proof of sample-accurate phoneme boundaries. ASR and signal measurements cannot establish subjective voice quality. See [the review guide](../../docs/DOCKER_SHORT_BENCHMARK_GUIDE.md) and [plan/evidence](../../design_doc/docker-short-benchmark.md).
