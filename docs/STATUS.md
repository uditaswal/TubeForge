# TubeForge Status

Last reviewed: 2026-10-04
Release target: R1 — Reliable Local Studio

`docs/STATUS.md` is the authoritative current-status record. Historical work
evidence belongs in `AUTONOMOUS_PROGRESS.md`; historical overnight planning is
retained under `docs/overnight/`.

## Release gates

| Gate | Status | Evidence | Blocker / next action |
| --- | --- | --- | --- |
| Automated regression suite | NEEDS REVALIDATION | On 2026-09-29, `237 passed, 4 skipped` in the collectable suite after excluding three dashboard/API test files. The unfiltered suite could not collect those files because this test environment lacks `httpx2`. | Install the missing test dependency in a project test environment and rerun the complete suite. |
| Database migrations | PASS | Fresh SQLite migration and existing upgrade-path tests passed on 2026-09-28; the head is `20260927_0020` and its new generation-cache columns were checked (`35 passed` focused migration/runner/config tests). | Recheck after any further migration change. |
| Restricted host Codex runner | BLOCKED | The Studio prompt-version fix is deployed. A subsequent real response had 62 narration words for a 60-second brief, below the 90–240 requirement. The checkout now gives Codex explicit word budgets shared with validation and corrects retry reservation state; four focused tests passed in 16.82s. | Operator must reinstall the root-owned host wheel and restart its service to activate the prompt correction (commands in README). Then validate a bounded real script; prior exhausted counters remain unchanged. |
| Local FFmpeg/Piper smoke | PASS | Dedicated Shorts smoke: `1 passed, 2 deselected` in 284.99s on 2026-09-27. Retained output is 53.417s, 1080x1920, 30 fps H.264/AAC; its gate verified 168 locally aligned words and a 2.871s maximum visual hold. The earlier widescreen stock smoke also remains retained. | Use a non-fake production writer and complete signed-in browser acceptance. |
| Local Kokoro voice smoke | PASS | `af_bella` generated a valid 24 kHz local WAV (3.776 seconds) using the INT8 ONNX model on 2026-09-13. | Run a selected-voice job smoke after rebuilding the durable Compose image. |
| Docker/Compose runtime | READY FOR REVIEW | Recreated migration, web, worker, and scheduler services on 2026-09-13 with local-UID bind-mount ownership. The scheduler now also mounts the configured local models; all services are running and `GET http://127.0.0.1:62065/healthz` returned `{"status":"ok","database":"ok"}`. | Sign in and exercise the Visuals selector with a stock-selected job. |
| Production dashboard auth | IN PROGRESS | Auth implementation, script viewing, and safe artifact cleanup now have focused API/dashboard coverage (`7 passed`). | Run a browser workflow check after sign-in. |
| Publishing safety | IN PROGRESS | Approval gates, private/dry-run defaults, and durable dispatch records exist. | Validate reconciliation paths; live OAuth smoke needs operator credentials. |

## Active milestone

Deliver good-quality YouTube Shorts in ordered phases. Phase 1 (portrait
format, timing, pacing, and captions) is complete. Phase 2 now replaces the
production fake writer with a local, source-grounded provider and tightens the
reviewed script/source workflow. Later phases cover coherent portrait visuals,
licensed music/audio upload, and signed-in browser acceptance. See
`docs/SHORTS_WORKFLOW.md`.

## Capability status

| Capability | Status | Remaining work |
| --- | --- | --- |
| Dedicated Shorts rendering | DONE | The Studio preset enforces 30–55s; previews are portrait and finals are 1080x1920/30 fps. Local waveform-based word timing, highlighted safe-area ASS captions, <=3s visual holds, and final-media gates passed real Piper/FFmpeg acceptance. Evidence: `artifacts/smoke/shorts_piper_1080x1920_smoke.{mp4,wav,json}` and the contact sheet. |
| Local generation/rendering | READY FOR REVIEW | Per-job visual-source selection routes generated scene art or rights-safe Wikimedia stock through the same asset manifest. If Commons is unavailable or strict filtering yields no permissible result, the hybrid provider explicitly falls back to local generated CC0 art and records both requests and the reason in that manifest. Focused tests and a stock-selected FFmpeg/Piper smoke passed on 2026-09-13. |
| VideoPlan and visual routing | IN PROGRESS | Move render consumers from legacy `ContentPackage`; implement any required motion-graphics/derivative renderer. |
| Source clipping | NEEDS REVALIDATION | Re-run source acquisition/render smoke and validate deployment behavior. |
| Topic queue and scheduling | IN PROGRESS | Add schedule editing/history and validate concurrent scheduler/recovery behavior. |
| Dashboard and authentication | READY FOR REVIEW | Dashboard now shows creation and activity timestamps in IST, a read-only script view after script approval, safe exact-script editing during review, persistent voice previews, deletion for paused pre-publication jobs, and published-item local artifact cleanup that retains the audit record. `127.0.0.1:62065` is the single documented local dashboard URL. The documented Debian home-server access path keeps that binding private and uses Tailnet HTTPS proxying. | Run full dashboard/browser regression and the Tailnet browser acceptance after the Debian host enables `tailscaled`; split embedded dashboard assets before further UI expansion. |
| YouTube publishing | BLOCKED | Operator OAuth credentials and private upload/reconciliation smoke required. |
| Instagram/Facebook publishing | TODO | Implement official Graph API adapters, then credentialed contract/sandbox tests. |
| Snapchat and other platforms | TODO | Retain manual handoff unless an approved official publishing API is available. |
| Growth/research/monetization | TODO | Source-backed research, fact checks, topic scoring, analytics, revenue attribution, and human-review policy. |

## Current blockers

1. Live OAuth validation requires operator-provided applications, approved
   permissions, redirects, and test credentials; none should be committed.
2. Both host-side attempts for the original README-grounded packet failed
   before producing a script; that packet remains exhausted. Both attempts
   for the revised review-gates packet also failed before a script because
   Codex rejected successive schema constraints (`required`, then `format: uri`).
   The compatibility repair was deployed before the new caption-timing test.
   The operator chose a new caption-timing topic and approved one live test.
   That request reached the model but its output failed host validation because
   two fallback visuals exceeded 100 characters. The operator-approved narrow
   local normalizer is deployed and passed installed-wheel/socket checks. Its
   remaining attempt was found exhausted by the runner's durable ledger on
   2026-10-04 before any model call. Do not reset the allowance or reuse the
   packet; a substantively new source packet requires separate approval.
3. The full regression suite cannot collect three dashboard/API test files in
   the current test environment until `httpx2` is installed there.

## Next five tasks

1. Prepare and separately approve a substantively new source-grounded packet
   for the first bounded host attempt; inspect any resulting script for source
   grounding and creative quality.
2. Show the exact source packet beside the editable script in Creator Studio.
3. Implement coherent portrait scene composition and its visual-quality gate.
4. Add licensed music/attribution records, quiet ducked mixing, and dashboard
   audio upload.
5. Run full regression, migration, Compose, and signed-in browser acceptance;
   inspect and retain the finished Short while YouTube stays dry-run.

## Update protocol

- Update this file whenever a milestone state, blocker, release gate, or next
  task changes.
- Every `DONE` item requires a linked test/artifact/command result.
- Append detailed command output and investigation history to
  `AUTONOMOUS_PROGRESS.md`; do not duplicate it here.
