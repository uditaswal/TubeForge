# Documentation index

Agents: start with [HANDOFF.md](HANDOFF.md) and [AGENTS.md](../AGENTS.md); open the rest by exact path only when the task needs it.

## Current state
- [HANDOFF.md](HANDOFF.md) — phase, next step, open decisions (auto-loaded, keep it short)
- [handoff-notes.md](handoff-notes.md) — detailed status table, render evidence, per-feature notes
- [Project plan and release status](../design_doc/tubeforge-publishing-design.md#11-current-release-status-and-next-action) — single plan/status of record
- [backlog.md](backlog.md) — product ideas and operator requests (not commitments)

## Rules and contracts
- [CONTENT_SKILLS_CONTRACT.md](CONTENT_SKILLS_CONTRACT.md) — binding rules for skills, scripts, research, scene plans
- [SHORT_FORM_VIDEO_RULEBOOK.md](SHORT_FORM_VIDEO_RULEBOOK.md) — video quality and creative review
- [SHORTS_WORKFLOW.md](SHORTS_WORKFLOW.md) — Shorts product decisions and quality gates
- [../SECURITY.md](../SECURITY.md) — secrets, scanning, reporting

## Operations
- [Operator guide](../readme.md) — setup and day-to-day workflow
- [operations/homeserver.md](operations/homeserver.md) — homeserver startup and SSH-tunnel access
- [operations/api-workflow.md](operations/api-workflow.md) — authenticated API script review
- [operations/platform-integrations.md](operations/platform-integrations.md) — platform/OAuth contracts
- [deploy/codex-runner-runtime.md](deploy/codex-runner-runtime.md) — isolated Codex host runner; systemd units in `deploy/`

## Video quality
- [video-quality/milestones.md](video-quality/milestones.md) — Codex milestones M1–M4 and status
- [video-quality/evidence.md](video-quality/evidence.md) — M1–M3 acceptance evidence
- [video-quality/plan-m0-m9.md](video-quality/plan-m0-m9.md) — broader M0–M9 plan from reference videos

## Reviews (point-in-time, read on demand)
- [reviews/2026-10-21-end-to-end.md](reviews/2026-10-21-end-to-end.md), [reviews/2026-10-22-content-quality.md](reviews/2026-10-22-content-quality.md), [reviews/2026-10-23-reference-codebases.md](reviews/2026-10-23-reference-codebases.md)
- [reviews/2026-10-26-av-quality-hyperframes-voicestudio.md](reviews/2026-10-26-av-quality-hyperframes-voicestudio.md) — HyperFrames/VoiceStudio review: what to take for audio and video quality, phased plan
- [reviews/stream-clipper-assessment.md](reviews/stream-clipper-assessment.md) — MIT attribution for adapted clipping algorithms
- [reviews/openmontage/](reviews/openmontage/README.md) — OpenMontage review (provenance for `om-*` skills)
- [CLAUDE_PIPELINE_REVIEW.md](CLAUDE_PIPELINE_REVIEW.md), [DOCKER_SHORT_BENCHMARK_REVIEW.md](DOCKER_SHORT_BENCHMARK_REVIEW.md), [../design_doc/docker-short-benchmark.md](../design_doc/docker-short-benchmark.md) — kept at these paths because `.agents/skills` reference them (skills are hash-pinned)

## Removed history
Superseded plans, status archives, task reviews and the dashboard prototype were removed on 25 Oct 2026.
Find them with `git log --diff-filter=D --summary -- docs design_doc` and read one with `git show <commit>^:<path>`.
`AUTONOMOUS_PROGRESS.md` is a local-only, gitignored evidence log.
