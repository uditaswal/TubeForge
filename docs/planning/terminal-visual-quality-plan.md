# Terminal visual quality phase

| Phase | User-visible outcome | Acceptance evidence | Out of scope |
|---|---|---|---|
| 1. Command scene visual and encode | Approved command and result appear as a legible portrait terminal; final H.264 encode retains small text | Focused provider/renderer tests, rendered 1080×1920 frame and encoded sample inspected at phone scale, exact display strings retained, full sample decode | Narration changes, audio mixing, dashboard changes |
| 2. Motion and timing | Command entry and result reveal follow narration in the production renderer | End-to-end 30–55 second Short, representative frame and caption checks | Generated B-roll |
| 3. Final creative review | Full Short meets the Claude reference's clarity and sound bar | Decode, loudness, safe-area and human listening/comparison review | Publication |

Current phase: 1 VERIFIED in the homeserver checkout: 67 relevant tests passed in its one-off Compose container. A three-second 1080×1920 H.264/AAC bounded render decoded fully; its encoded frame was inspected for command, output and caption separation. The production worker was not restarted, so running jobs still use their loaded code/configuration. Phase 2 is NOT STARTED. The existing Docker benchmark is an example renderer, not yet the production video pipeline. This plan keeps changes tied to the approved `ScenePlan` and existing asset hashes.
