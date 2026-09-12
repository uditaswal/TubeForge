# TubeForge Status

Last reviewed: 2026-09-13
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
| Local generation/rendering | IN PROGRESS | Per-job visual-source selection now routes generated scene art or rights-safe Wikimedia stock through the same asset manifest; focused regression and an FFmpeg smoke remain required. |
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

1. Run focused API, visual-routing, asset, and renderer tests; fix all failures.
2. Generate and inspect a local-art video smoke after the visual-source change.
3. Exercise the stock selection with a public-domain/CC0 Wikimedia source in a
   controlled environment and inspect its asset manifest.
4. Run the complete suite and Compose configuration check in the current image.
5. Commit the validated batch and update this release record with evidence.

## Update protocol

- Update this file whenever a milestone state, blocker, release gate, or next
  task changes.
- Every `DONE` item requires a linked test/artifact/command result.
- Append detailed command output and investigation history to
  `AUTONOMOUS_PROGRESS.md`; do not duplicate it here.
