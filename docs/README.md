# Documentation

Public documentation. Start with the [project README](../readme.md).

- [Reference-video intake operator workflow](operations/reference-intake.md) and [LF1 acceptance evidence](long-form-lf1-review.md) — real metadata/caption intake, supplied transcript fallback and immutable review; video generation remains a later phase
- [Long-form and reference-video implementation plan](long-form-reference-video-plan.md) — 10–15 minute production, original link-based adaptations, usage budgets and Codex/Claude task ownership (planned capability)
- [Long-form core task interfaces and acceptance](long-form-next-ten-core-tasks.md) — reference/usage/context/chapter contracts and local evidence for the next ten Codex tasks
- [Long-form editorial proposal](long-form-editorial-proposal.md) and [LF0 local acceptance evidence](long-form-lf0-acceptance.md) — story/packaging/prompt policy, frozen examples and next intake boundary
- [HANDOFF.md](HANDOFF.md) — current phase, next step and gotchas shared by the agents working on the repo
- [../design/DESIGN.md](../design/DESIGN.md) — dashboard design system: tokens, component recipes, workflows for changing the UI; living guide in `design/guide.html`
- [clips.md](clips.md) — the Clips page and clip jobs: how they work, limits, worker modes, what is deferred
- [operations/logging.md](operations/logging.md) — rotating JSON application logs: files, fields, retention, redaction
- [operations/api-workflow.md](operations/api-workflow.md) — reviewing and approving a job through the API
- [operations/platform-integrations.md](operations/platform-integrations.md) — YouTube, Meta and other platform setup
- [script-naturalness-plan.md](script-naturalness-plan.md) — plan to make scripts less robotic (review of three outside repos, mapped review points, phases P0–P4)
- [publishing-plan.md](publishing-plan.md) — YouTube + Instagram upload pipeline: operator credentials, phases P1–P5, Claude/Codex split
- [batch-plans.md](batch-plans.md) — batch plans: import, queue, day review, staged export, overnight schedule
- [deploy/](deploy) — systemd units and runtime notes for the Codex and Claude script runners; `scripts/restart_stack.sh` restarts the whole stack
- [SHORT_FORM_VIDEO_RULEBOOK.md](SHORT_FORM_VIDEO_RULEBOOK.md) — the video quality standard every render is judged against
- [../SECURITY.md](../SECURITY.md) — secrets handling, scanning, reporting

- [Before-upload channel safety checklist](channel-safety-checklist.md)

- [Video direction review](video-direction-review.md) — advisory scene/channel context and local benchmark evidence
