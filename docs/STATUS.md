# TubeForge Status

Last reviewed: 2026-09-13
Release target: R1 — Reliable Local Studio

`docs/STATUS.md` is the authoritative current-status record. Historical work
evidence belongs in `AUTONOMOUS_PROGRESS.md`; historical overnight planning is
retained under `docs/overnight/`.

## Release gates

| Gate | Status | Evidence | Blocker / next action |
| --- | --- | --- | --- |
| Automated regression suite | PASS | `215 passed, 2 skipped` in 20:45 on 2026-09-13 in `tubeforge-local-media:smoke`; includes visual-source routing, asset safety, worker, renderer, migration, and publishing-safety coverage. | Re-run after the next product change. |
| Database migrations | NEEDS REVALIDATION | Prior fresh SQLite migration reached revision `20260831_0019`. | Run fresh-install and upgrade-path tests from the current tree. |
| Local FFmpeg/Piper smoke | PASS | `tests/test_real_local_smoke.py -k fixed`: `1 passed` in 171.74s on 2026-09-13; inspected H.264/AAC 640x360 MP4, 73.736s, with six generated image scenes. | Re-run after any renderer, narration, or asset-pipeline change. |
| Local Kokoro voice smoke | PASS | `af_bella` generated a valid 24 kHz local WAV (3.776 seconds) using the INT8 ONNX model on 2026-09-13. | Run a selected-voice job smoke after rebuilding the durable Compose image. |
| Docker/Compose runtime | READY FOR REVIEW | Rebuilt web and worker images on 2026-09-13; Compose migration completed, both services are running, and `GET http://127.0.0.1:62065/healthz` returned `{"status":"ok","database":"ok"}`. | Sign in and exercise the Visuals selector with a stock-selected job. |
| Production dashboard auth | IN PROGRESS | Auth implementation, redesigned local sign-in flow, and focused API/UI coverage exist. | Rebuild the current dependency image and run the focused dashboard/auth suite plus a browser check. |
| Publishing safety | IN PROGRESS | Approval gates, private/dry-run defaults, and durable dispatch records exist. | Validate reconciliation paths; live OAuth smoke needs operator credentials. |

## Active milestone

Implement and validate per-generation visual-source selection: local generated
scene art or rights-safe public-domain/CC0 stock. The feature must preserve
asset provenance, checkpoint recovery, renderer validation, and the Creator
Studio workflow. Google Image scraping is deliberately out of scope because it
cannot establish the reuse rights required by the asset policy.

## Capability status

| Capability | Status | Remaining work |
| --- | --- | --- |
| Local generation/rendering | READY FOR REVIEW | Per-job visual-source selection routes generated scene art or rights-safe Wikimedia stock through the same asset manifest. Focused and full regression, live stock acquisition, and a generated-art FFmpeg/Piper smoke passed on 2026-09-13. A stock-selected full-video smoke is still required before marking this milestone DONE. |
| VideoPlan and visual routing | IN PROGRESS | Move render consumers from legacy `ContentPackage`; implement any required motion-graphics/derivative renderer. |
| Source clipping | NEEDS REVALIDATION | Re-run source acquisition/render smoke and validate deployment behavior. |
| Topic queue and scheduling | IN PROGRESS | Add schedule editing/history and validate concurrent scheduler/recovery behavior. |
| Dashboard and authentication | READY FOR REVIEW | Dashboard now shows creation times, activity, safe exact-script approval, manual narration revision, a copyable Codex revision prompt, local voice previews, and a responsive sign-in flow. `127.0.0.1:62065` is the single documented local dashboard URL. | Run full dashboard/browser regression; split embedded dashboard assets before further UI expansion. |
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

1. Exercise an end-to-end stock-selected job, retaining its asset manifest and
   final MP4 for inspection.
2. Sign in to the rebuilt Studio and validate the Visuals selector at
   `http://127.0.0.1:62065`.
3. Re-run fresh-install and upgrade-path migration tests in the current image.
4. Re-run and inspect the source-clip smoke after the current renderer changes.
5. Commit the validated batch and update this release record with evidence.

## Update protocol

- Update this file whenever a milestone state, blocker, release gate, or next
  task changes.
- Every `DONE` item requires a linked test/artifact/command result.
- Append detailed command output and investigation history to
  `AUTONOMOUS_PROGRESS.md`; do not duplicate it here.
