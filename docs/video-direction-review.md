# M4 video direction review

Status: **IMPLEMENTED**. Full-video creative acceptance remains pending.

New jobs save a bounded snapshot of the preceding twelve local briefs on the
same channel before narration generation. Restart/retry reuses that snapshot;
its absence on an older job is explicit. It never enters factual sources,
research notes or the writer's request/cache key, and cannot reset allowances.
This is local editorial memory, not published history or measured performance.

`video_direction_report.json` and the asset-stage storyboard expose versioned,
structured scene purpose, subject, composition, original layout, reveal anchors,
narration hashes, adjacent layout repetition and similar recent angles. They are
advisory. Approved scene layouts are never changed randomly. In **Generations →
Revise one scene**, the signed-in reviewer sees warnings for the selected scene
and channel-context availability. A saved edit still creates a separate draft
requiring fresh review; this report changes no approvals.

The current scope supplies direction evidence to the existing human review
workflow. It does not automatically inject previous angles into the writer
prompt or silently revise an accepted script.

## Validation

Final focused group: **92 passed, 7 skipped**, one existing Starlette 422
naming-deprecation warning. The seven skips are the optional captured-media
animated smoke tests; separate actual video evidence is below.

```sh
PYTHONPATH=src .venv-benchmark/bin/python -m pytest -q \
 tests/test_provider_fallback.py tests/test_provider_routing_api.py \
 tests/test_script_routing_ui.py tests/test_video_direction.py \
 tests/test_scene_contracts.py tests/test_animated_card.py \
 tests/test_animated_teaching.py tests/test_qa_check_skill.py \
 tests/test_channel_reports.py \
 tests/test_pipeline_orchestrator.py::test_topic_research_checkpoint_survives_restart_without_regeneration \
 tests/test_pipeline_orchestrator.py::test_ownership_loss_during_content_generation_cannot_promote_checkpoint_or_state \
 tests/test_api_workflow.py::test_every_inline_dashboard_script_parses
```

Isolated signed-in Chromium, with stub providers: direction review loaded and
reopened without script exceptions; desktop 1280×900, tablet 768×1024 and mobile
390×844 had no horizontal overflow. Inspected screenshots are under
`artifacts/review/video-direction-20261105/`. Warnings follow the scene selection
and remain inside the existing scrolling dialog. The existing exact-script and
scene-edit approval actions are preserved.

A broader renderer/pipeline test run was terminated with exit 143 before its
summary; it is not counted as passing. The focused final group above passed.

## PHP landscape benchmark

The operator approved the exact 148-word revision proposal
`eb1a30e5b416b9693609af7bf806ee12d7f66460b48185a10c6caf33656ba239`
on 5 November 2026. The versioned fixture records that approval as narration for
this local benchmark only. It removes the unsupported “Black October” nickname
and qualifies the NCSC exposure advice. The parent package is checksum-bound;
original production job, source packet, artifacts, approvals and allowances are
unchanged. This benchmark does not enable the retired landscape production flow.

```sh
PYTHONPATH=src .venv-benchmark/bin/python scripts/benchmark_php_m4.py \
 --parent data/artifacts/2c9db459cc68455f9691fcfc70584a7e \
 --output artifacts/review/php-m4-landscape-20261105-v2
.venv-benchmark/bin/python .agents/skills/om-video-quality/qa_check.py \
 artifacts/review/php-m4-landscape-20261105-v2
```

Unchanged phrases reuse checksum-matched original audio. Changed approved
phrases use local Kokoro, with no script-provider or research call. Native
landscape scenes retain explicit word anchors and a newly bound scene contract;
this candidate's visuals still need fresh review. Its word edges use the existing
waveform-span/weighted alignment, not independently measured forced alignment.
The required QA helper now reads actual encoded loudness from native render
manifests as well as reference-Short reports, with a focused pass/fail test.

## Day review data check for Claude

M-S6/M-S7 already expose versioned entries, linked short IDs, channels, dates,
opening text/formula, layout family, music/voice, heuristic scores/repeated phrases,
severity and cadence counts/spacing thresholds. Unknown historical production
fields stay unknown. These are sufficient for warning cards and links to shorts.

Remaining presentation/interface gaps (recorded for Claude; no Day UI built here):

- `day` selects the repetition window, while cadence currently covers all plan
  entries. A selected-day page must filter relevant warnings or label that scope.
- Cadence is a conservative warn-only check on all close publishes. It is not a
  typed combined “similar AND close” verdict; that requires joining repetition
  and cadence ID pairs. Never label a warning as a publication block.
- Cadence warnings omit the resolved per-channel timezone/config for explaining
  local-day boundaries; repetition's missing-layout/music/voice values need an
  explicit unknown state rather than a clean bill of health.
- These reports describe planned publish metadata/local renders, not confirmed
  remote publication or platform-policy compliance.
