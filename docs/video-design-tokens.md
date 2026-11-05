# Shared video design tokens

Status: **IMPLEMENTED**; local seven-template rendering and geometry checks pass.
Full-video creative acceptance remains separate.

The existing classic HyperFrames renderer can take an explicit
`render_options.json` `design_tokens` declaration. The shared decorator applies
entity colours, dim-to-light reveals at the existing word anchors, a persistent
two-part anchor headline, phrase caption pills and a source footnote. It preserves
approved narration, captions, semantic scene types and cue indices. Token data
is included in the render-options identity and the render report.

```json
{"design_tokens":{"version":"reference-design-v1","entity_colors":{"System A":"#ffb870","System B":"#79e8b0"},"anchor_headline":["REQUEST","ROUTING"],"dim_opacity":0.22}}
```

This is an explicit library/benchmark option. Existing jobs keep their visual
output; Studio has no new token control. Story and PIL paths reject this option
rather than silently ignoring it. Colour values must be readable six-digit hex
colours, names must be distinct, and the anchor must fit its safe width. The
existing renderer and exact-artifact approval gates still apply.

## Local evidence, 5 November 2026

- `PYTHONPATH=src .venv-benchmark/bin/python -m pytest -q tests/test_design_tokens.py tests/test_hyperframes_compose.py tests/test_hyperframes_routing.py tests/test_reference_shorts.py`: **29 passed**.
- `scripts/benchmark_design_tokens.py --hyperframes-bin <installed-binary>`
  renders hook, big_stat, before_after, flow, checklist, terminal and loop through
  the real HyperFrames CLI. All seven pass its runtime/layout/contrast checks and
  full FFmpeg decode. Fixtures explicitly label their synthetic content and
  estimated timing; there is no generated factual narration or audio.
- Local evidence: `artifacts/review/design-tokens-v1-20261105/`, including each
  `check.json`, encoded clip, inspected frame, token identity, and
  `review-manifest.json`. A browser geometry check found every visible text/card/
  badge inside x=60..930, y=200..1500 on the 1080×1920 canvas.
- Inspected encoded frames show consistent orange System A and green System B,
  readable caption pills, retained spaces inside coloured checklist text and
  stat bars clear of the right rail. The encoded final stat frame reaches 2×;
  a browser seek with callbacks suppressed is not evidence of count-up output.
- CLI advisory warnings include its 28px reading-text preference for the 26px
  source footnote and existing badge subcomposition guidance. No runtime/layout/
  contrast failures remain. A full narrated video and operator phone/watch review
  are still required before **VERIFIED** or default rollout.
