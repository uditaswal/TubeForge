# Multi-account setup feature

Branch: `codex/multi-account-setup`. This worktree starts at committed `dev` HEAD and leaves Claude's uncommitted `dev` work untouched.

Current feature status: **VERIFIED** for local account profiles, generation
intent, and finished-video draft handoff. Signed-in API/UI coverage and the
real local H.264/FFprobe/staged-draft smoke passed. Live platform connections,
Snapchat/X draft creation, and any upload are outside this branch.

## Phase 1 — Account profiles
User-visible outcome: create named YouTube, Instagram, Snapchat, and X accounts with a category and default video description; clearly show connection state.
Acceptance: authenticated account API/UI tests prove distinct accounts, persistence, validation, and no browser claim of a live connection.
Evidence: focused tests and signed-in Studio inspection.
Out of scope: OAuth, credentials, and live platform calls.

## Phase 2 — Creation intent
User-visible outcome: select one or more destination accounts and a per-video description when creating a video. Save exact account/category/description snapshots with the job.
Acceptance: durable job and intent are committed together, invalid account IDs are rejected, and defaults apply only when the description is omitted.
Evidence: API and repository tests, including restart/readback.
Out of scope: changing script generation or automatic publishing.

## Phase 3 — Finished video handoff
User-visible outcome: a finished video exposes its saved destination intent in the manual post composer, where the operator can review and save a draft.
Acceptance: signed-in dashboard test and local final-artifact smoke prove the choices survive to a ready video; draft creation still requires the existing review path.
Evidence: focused tests, artifact inspection, current-status entry, and progress log.
Out of scope: any online platform integration or upload.
