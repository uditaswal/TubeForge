# Creator Studio UI update

Reference: `design_doc/tubeforge-dashboard.html` supplies the visual language and navigation pattern. It contains simulated browser state; production controls continue to use TubeForge's existing HTTP APIs and durable records. Work stays on `codex/multi-account-setup`, leaving Claude's `dev` worktree untouched.

## Phase 1 — Studio shell
User-visible outcome: a clear sidebar and top bar organize real generation, publishing, account and scheduling workflows without hiding controls or interrupting background refresh.
Acceptance: signed-in Studio renders the four destinations, navigation works by keyboard and URL hash, and existing controls remain in the DOM with unchanged API calls.
Evidence: focused auth/UI tests and script syntax validation.
Out of scope: new backend capabilities, prototype analytics, publishing automation and a stack rewrite.

## Phase 2 — Responsive visual system
User-visible outcome: the reference's restrained navy, mint and purple hierarchy carries through forms, job cards, account rows, draft review and dialogs. On phones, the sidebar becomes an accessible drawer and forms become one column.
Acceptance: desktop and mobile widths show no horizontal overflow or clipped actions; focus, disabled, loading, empty and error states remain legible.
Evidence: rendered desktop/mobile preview plus focused UI checks and existing workflow tests.
Out of scope: simulated content, new platform connections and video quality work.

## Phase 3 — Review handoff
User-visible outcome: the operator can inspect the working feature branch dashboard and its phone-sized preview side by side with the reference.
Acceptance: the operator reviews the concrete UI and feedback is addressed before visual acceptance is recorded.
Evidence: preview URLs/tabs, test results, project status and progress log.
Out of scope: merging into Claude's concurrent `dev` work or deploying a production dashboard.

Current state: Phase 1 **VERIFIED** (`tests/test_auth.py`: 2 passed; Studio script parses in V8). Phase 2 **IMPLEMENTED**: 22 focused auth/account/publishing tests passed, V8 syntax passed after the drawer focus update, and desktop/390 px interactive preview URLs returned HTTP 200. Visual and horizontal-overflow acceptance still need browser inspection with the operator. Phase 3 **IMPLEMENTED**: both previews were opened in Codex and shared for review; operator feedback is pending. Next action: address review findings, then record visual acceptance.

## Phase 4 — Per-schedule destinations (operator feedback)
User-visible outcome: each schedule can select its own local platform accounts and optional video description, and the Scheduling tab shows the saved choices.
Acceptance: creating two schedules with different account choices preserves each plan; a scheduled job atomically snapshots the selected account names, categories and effective descriptions; a disabled or missing account fails the run without consuming its topic. Mobile account choices remain usable with keyboard and touch.
Evidence: focused API/repository/UI tests, scheduler regression, signed-in dashboard response and refreshed phone preview.
Out of scope: online platform connection, automatic publishing, changing the topic queue's scheduling policy or Claude's video renderer.

Current Phase 4 state: **IMPLEMENTED**. The full focused dashboard, scheduler, account and publishing regression passed (26 tests); the Scheduling script parses in V8; refreshed desktop and phone previews returned HTTP 200. Browser inspection of the Scheduling tab on a real phone width and operator feedback remain pending. Next action: review the updated tab with the operator and address any visual or interaction issues.
