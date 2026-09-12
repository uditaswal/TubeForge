# TubeForge Status

Last reviewed: 2026-09-12  
Release target: R1 — Reliable Local Studio

`docs/STATUS.md` is the authoritative current-status record. Historical work
evidence belongs in `AUTONOMOUS_PROGRESS.md`; historical overnight planning is
retained under `docs/overnight/`.

## Release gates

| Gate | Status | Evidence | Blocker / next action |
| --- | --- | --- | --- |
| Automated regression suite | NEEDS REVALIDATION | Focused video-generation coverage: `19 passed` on 2026-09-12. A prior full run recorded `197 passed, 2 skipped`. | Run the complete suite in the current dependency image. |
| Database migrations | NEEDS REVALIDATION | Prior fresh SQLite migration reached revision `20260831_0019`. | Run fresh-install and upgrade-path tests from the current tree. |
| Local FFmpeg/Piper smoke | PASS | `tests/test_real_local_smoke.py -k fixed`: `1 passed` in 180.54s on 2026-09-12; inspected H.264/AAC 640x360 MP4, 73.318s. | Re-run after any renderer, narration, or asset-pipeline change. |
| Local Kokoro voice smoke | PASS | `af_bella` generated a valid 24 kHz local WAV (3.776 seconds) using the INT8 ONNX model on 2026-09-13. | Run a selected-voice job smoke after rebuilding the durable Compose image. |
| Docker/Compose runtime | READY FOR REVIEW | Local dashboard health check returns `{"status":"ok","database":"ok"}` and the matching local worker is rendering jobs. | Rebuild the durable Compose services from the current tree; the temporary source-mounted pair is for local validation. |
| Production dashboard auth | IN PROGRESS | Auth implementation and focused historical test evidence exist. | Validate the current API/UI behavior and document administrator bootstrap. |
| Publishing safety | IN PROGRESS | Approval gates, private/dry-run defaults, and durable dispatch records exist. | Validate reconciliation paths; live OAuth smoke needs operator credentials. |

## Active milestone

Validate and integrate the current uncommitted batch covering topic scheduling,
dashboard authentication, social accounts, publication dispatch, visual routing,
quality gates, platform-variant plans, and the local cinematic-render upgrade.
Do not begin additional product scope until this batch is tested, documented,
and committed coherently.

## Capability status

| Capability | Status | Remaining work |
| --- | --- | --- |
| Local generation/rendering | READY FOR REVIEW | Topic-to-final local flow is smoke-tested with Piper, HD deterministic scene art, captions, cinematic camera motion, the final quality gate, and selectable Kokoro narration with Piper fallback. Full regression is still required. |
| VideoPlan and visual routing | IN PROGRESS | Move render consumers from legacy `ContentPackage`; implement any required motion-graphics/derivative renderer. |
| Source clipping | NEEDS REVALIDATION | Re-run source acquisition/render smoke and validate deployment behavior. |
| Topic queue and scheduling | IN PROGRESS | Add schedule editing/history and validate concurrent scheduler/recovery behavior. |
| Dashboard and authentication | READY FOR REVIEW | Dashboard now shows creation times, activity, safe exact-script approval, manual narration revision, and a copyable Codex revision prompt. | Run full dashboard/browser regression; split embedded dashboard assets before further UI expansion. |
| YouTube publishing | BLOCKED | Operator OAuth credentials and private upload/reconciliation smoke required. |
| Instagram/Facebook publishing | TODO | Implement official Graph API adapters, then credentialed contract/sandbox tests. |
| Snapchat and other platforms | TODO | Retain manual handoff unless an approved official publishing API is available. |
| Growth/research/monetization | TODO | Source-backed research, fact checks, topic scoring, analytics, revenue attribution, and human-review policy. |

## Current blockers

1. `/usr/bin/python3` has no `pytest` or project dependencies.
2. Docker daemon access is denied for the current user.
3. Live OAuth validation requires operator-provided applications, approved
   permissions, redirects, and test credentials; none should be committed.

## Next five tasks

1. Run the complete suite, migration tests, and Compose check in the current
   dependency image; fix all failures.
2. Re-run and inspect the source-clip smoke after the current renderer changes.
3. Review the new local video look in the dashboard and tune caption/motion
   defaults only with an accompanying smoke artifact.
4. Commit the validated batch, recording commit IDs and evidence here.
5. Add CI and update the operator/deployment documentation before enabling live
   platform integrations.

## Update protocol

- Update this file whenever a milestone state, blocker, release gate, or next
  task changes.
- Every `DONE` item requires a linked test/artifact/command result.
- Append detailed command output and investigation history to
  `AUTONOMOUS_PROGRESS.md`; do not duplicate it here.
