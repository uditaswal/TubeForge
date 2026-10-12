# TubeForge implementation order — proposed for review

12 October 2026

This is the fine-grained task sequence derived from [the publishing and video design](tubeforge-publishing-design.md). **The operator approved tasks 5–7 in this order on 12 October 2026; later tasks remain open for review.** The design supplies detailed contracts; [docs/STATUS.md](../docs/STATUS.md) remains the sole record of current implementation state, blockers and validation evidence. A task appearing here does not imply that its existing code is absent or verified. Reuse current TubeForge contracts and evidence before adding code.

The requested priorities are: improve generated-video quality first, update stream clipping second last, and migrate the dashboard to Next.js last. Earlier operator-facing changes still require truthful controls in the current dashboard. Live platform posts and paid API calls require their applicable authorization; local work can proceed while an external gate remains open.

| Order | Task | Acceptance evidence | Depends on / boundary |
|---|---|---|---|
| 1 | Inventory TubeForge generation and relevant local donor code | Current contracts, changed paths, donor revisions, reusable ideas and remaining gaps recorded | Preserve existing skill, job, lease, approval and render work; reuse donor implementations under the operator’s stated permission |
| 2 | Define narration-linked scenes in the existing video plan | Every beat has a concrete subject, visual purpose and on-screen treatment; focused plan/consumer tests | Use the canonical `yt-script` skill and current script provider; no second writer stack |
| 3 | Acquire or create relevant, permitted visuals | Complete asset manifest and contact sheet; inspect scene relevance, provenance and rights | Prefer existing/local/licensed routes; no paid provider without its own authorization |
| 4 | Render and inspect one finished video | Watch/listen to the whole MP4; timecoded review of substance, pacing, visuals, captions, sound and technical gates | A schema check or fixture render alone is insufficient creative evidence |
| 5 | Replace or regenerate one scene | One-scene edit produces a new revision; unaffected assets are reused; affected timing/audio/captions rebuild | Preserve checkpoints, cancellation, ownership fencing and atomic promotion |
| 6 | Enforce exact revision approval after scene changes | Previous approval becomes stale; reviewed final bytes match the artifact selected for rendering/delivery | Verify signed-in review in the current dashboard |
| 7 | Produce and inspect a second distinct topic | Same selected channel profile, complete video and timecoded creative review | Proves the visual approach generalizes beyond one script |
| 8 | Add approved generated videos to the canonical library | Exact approved revision, hash, source lineage and review history are available to Compose | No automatic publication |
| 9 | Finish manual local-video upload and Compose review | Real staged file, exact accounts/metadata/visibility snapshot, signed-in submission and durable result | Reuse existing upload, asset and delivery APIs; local test success is separate from remote success |
| 10 | Verify YouTube API setup | Project, consent screen, API enablement, redirect URI, requested scopes and test-account readiness recorded | No upload or publish is required for setup verification |
| 11 | Verify YouTube account connection | Authorized OAuth identity, scopes, encrypted token storage, refresh and reconnect evidence | Reuse existing connection code where proven |
| 12 | Verify YouTube video upload and reconciliation | Authorized test upload, remote ID, processing state and requested visibility checked | Never infer published from an accepted upload response |
| 13 | Verify YouTube future scheduling | Eligible private video, future `publishAt`, cancellation limits and final visibility checked | Separate live scheduling evidence from private upload evidence |
| 14 | Select the supported Instagram API contract | Chosen Instagram Login or Facebook Login route, account type, permissions, media and staging requirements documented | Do not substitute Page-token examples for a different login route |
| 15 | Set up and verify the Instagram API app | Selected login product, app configuration, redirect URI, permissions, review/test-account status and publishing capability recorded | External app approval may remain blocked while local adapter work proceeds |
| 16 | Implement/verify Instagram account connection | Authorized remote identity, scopes, token refresh/reconnect and capability checks | No browser-stored credentials |
| 17 | Implement/verify Instagram media publish and reconciliation | HTTPS staging, container creation/processing, publication receipt and uncertain-outcome recovery with authorized account | Respect platform fetch lifetime and publishing limits |
| 18 | Prove independent results per destination | Retry a failed destination without re-uploading a successful one; audit unresolved/skipped outcomes | Preserve immutable selected accounts and delivery identity |
| 19 | Add folder catalog and file eligibility | Approved mounts, validated media, fingerprints, priority/exclusion and indexed eligible list | No traversal/symlink escape or silent source switching |
| 20 | Add daily slot planning and reservations | Timezone conversion, next five slots, exclusive claims, immutable occurrence snapshot and missed/empty policy | No double selection or burst after downtime |
| 21 | Add safe archival and recovery | Two distinct files, rename deduplication, restart, partial retry, archive-copy failure and archive-only repair | Archive only after required destination completion; retain staged media while needed |
| 22 | Add versioned publishing profiles/presets | Two accounts/profiles, locks and overrides, frozen settings for existing jobs, future-only updates | Do not replace current channel voice profiles |
| 23 | Add bounded generation batches | Small restarted batch reuses completed scripts/media/renders; limits and cancellation verified | Begin only after both inspected videos meet quality bar |
| 24 | Add measured video insights | Available authorized metrics map to actual rendered scene times; unavailable data is explicit | No invented analytics or causal growth claims |
| 25 | Update stream clipping | Review a self-contained unused source window, portrait output, provenance and overlap reservation; send approved clip through shared library/delivery path | This is the second-last task; avoid a separate publisher path |
| 26 | Migrate the dashboard to Next.js | Incremental screen replacement with real APIs; signed-in desktop/mobile/keyboard tests, auth/session continuity and silent refresh | This is the last task; keep FastAPI, workers and DB authoritative |

## Practical grouping

## Task 4 execution gate — one finished Short

| Phase | User-visible outcome | Acceptance test and retained evidence | Out of scope |
| --- | --- | --- | --- |
| 4A. Preview inspection and caption repair | The Docker image/container preview has readable, faithful command captions and visuals tied to the narration. | Inspect the entire 30–55-second preview, compare burned captions with the approved narration and command visuals, run focused caption/render tests, and retain a timecoded review. | Final approval, publication, new script provider. |
| 4B. Exact-preview approval and final render | The reviewed preview advances through the existing approval gate into one 1080×1920 MP4. | Approval identity equals the reviewed preview manifest; the final manifest binds the same content, audio, captions and asset hashes; ffprobe and quality gate pass. | Publication or delivery to any platform. |
| 4C. Finished-video acceptance | The complete final Short is available for local review with a concrete creative pass/fail report. | Watch and listen to the full final video; inspect substance, pacing, visuals, captions and sound at timecodes; verify signed-in dashboard review and record artifacts/results in the design, status and evidence log. | Second topic and one-scene replacement (tasks 5–7). |

Current 4A state: **VERIFIED**, with [inspection evidence](../docs/TASK4_VIDEO_REVIEW.md). The fresh dashboard job has a registered 43.016-second corrected preview that preserves CLI punctuation and phrase boundaries; every one of its 99 caption events fits the 18-character portrait width gate. The operator confirmed clear narration in the unchanged source.

Historical 4B blocker: the former single-graph 1080×1920 candidate was killed by a confirmed 1 GiB worker OOM. The operator subsequently chose bounded-memory rendering and authorized a temporary review login with cleanup. The earlier unapproved account-creation attempt was rejected by automatic approval review; it created no account.

Operator decision on 12 October 2026: implement bounded-memory rendering under the existing 1 GiB worker profile; a temporary local review login may be created for signed-in verification and must be removed with its session afterward. Phase 4B now has three ordered substeps:

Current 4B update: **4B-1, 4B-2 and 4B-3 VERIFIED**. A real 43.033-second 1080×1920 H.264/AAC [production final](../docs/TASK4_VIDEO_REVIEW.md) rendered under the existing 1 GiB worker limit. Signed-in production job `9df50ade54724d3ba7dd9e96e6521e88` saved the exact revised script, approved its corrected preview identity, and bound that approval and all input hashes in the registered final manifest. The temporary review account/session was removed and the revoked token returned HTTP 401. Current-worktree focused suite: 57 passed in 746.51 seconds. Visual, caption, audio-signal and technical checks passed; the operator watched/listened to the complete final and reported good voice, pacing, captions and visuals with no defect. No publication.

| Substep | User-visible outcome | Acceptance test / artifact | Out of scope |
| --- | --- | --- | --- |
| 4B-1. Bounded final renderer | The same approved Short can export at 1080×1920 without a simultaneous multi-scene filter graph. | Real inspection-only 30–55s H.264/AAC render under the 1 GiB worker limit, ffprobe and sampled frames; focused cancellation, cleanup, identity and audio-mix tests. | Dashboard mutation and publication. |
| 4B-2. Signed-in corrected preview | A fresh production job carries corrected caption bytes through the existing script and preview approvals. | Authenticated API/dashboard events show source-packet cache use, exact script identity, 540×960 preview identity, operator inspection and approval; temporary account/session cleanup is demonstrated. | Live platform APIs. |
| 4B-3. Finished-video proof | The exact reviewed revision produces a local 1080×1920 final. | Final manifest binds the approved preview and accepted content/audio/captions/assets; quality gate, full audiovisual inspection and timecoded report pass. | Publish or tasks 5–7. |

- **2–4:** one storyboard-to-finished-video quality slice; inspect the first complete artifact before extending the feature.
- **5–7:** scene repair and a second-topic check share revision, reuse and creative-review evidence.
- **8–9:** the library bridge and Compose review can share exact-artifact tests.
- **10–13:** YouTube API setup, connection, upload and scheduling have separate acceptance gates. Connection, upload and scheduling can reuse the same authorized test account and upload history.
- **14–17:** Instagram API selection, app setup, connection and publishing have separate gates; complete local adapter work while external app access is pending.
- **19–21:** catalog, scheduler and archive recovery can share two real local test files and restart scenarios.

Before each implementation slice, define its user-visible outcome, focused test, real artifact or receipt, and explicit scope boundary in the main design plan. Update that plan, `docs/STATUS.md` and `AUTONOMOUS_PROGRESS.md` with actual evidence after meaningful changes. Tasks 1–3 were authorized on 12 October 2026. Do not treat the remaining sequence as accepted until the operator reviews its order.

## Tasks 5–7 execution gate — scene revision and second-topic proof

The operator authorized tasks 5–7 on 12 October 2026. Work in order and record each phase's acceptance before advancing. Keep the existing production writer, channel profile, worker fencing, checkpoint safety and review workflow. No publication or paid provider is in scope.

| Phase | User-visible outcome | Acceptance test and retained evidence | Out of scope |
| --- | --- | --- | --- |
| 5. Replace one scene | The Studio can save a new, inspectable scene revision and rebuild its preview while reusing unchanged scenes. | Signed-in scene edit; before/after package and storyboard identities; one changed asset, unchanged asset hashes retained; affected narration/timing/captions rebuilt as required; focused API/worker tests and a real preview inspected. | Publication, second topic, broad editor controls. |
| 6. Exact revision approval | The previous script/preview approval cannot authorize changed scene bytes; the new preview/final bind the approved revision. | Test stale identity rejection and worker fencing; signed-in review of new preview and final manifests; verify selected final bytes and publication package identity. | Live upload or a new approval system. |
| 7. Second distinct topic | A second source-grounded Short in the same profile reaches a complete local final and creative review. | Actual Codex production invocation with canonical skill preflight, source/claim and script quality review, exact approvals, full 30–55s 1080×1920 MP4 inspection, signed-in dashboard flow and timecoded report. | Automatic batch generation, live publication, provider switch. |

Current phase: **5 VERIFIED; 6 in progress**. The Studio editor created signed-in production child `8481109b…` with the same reviewed one-scene content hash as [the inspected 43.179-second child preview](../docs/TASK5_SCENE_REVIEW.md), leaving the accepted parent unchanged. Five of six asset hashes and eleven of twelve phrase-audio hashes were reused in the rendered child; narration, timing and captions were rebuilt. The authenticated Studio page, edit API, child script and activity, and preview artifact returned successfully. Current-worktree regression: 77 passed; final focused rerun: 2 passed. Phase 6 now tests stale approval and exact final binding.
