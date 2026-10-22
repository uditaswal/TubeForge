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

## Phase 5 — Account-first channel queues (operator correction)
User-visible outcome: Scheduling opens with account cards; choosing a channel shows only that channel's queued topics, recent jobs and schedules, with add-topic and create-schedule actions in the same context.
Acceptance: two accounts have independent topic queues; a schedule can only reserve a topic from its own account; a disabled or missing account cannot silently send a topic elsewhere; legacy unassigned topics and schedules remain isolated; signed-in desktop and 390 px mobile layouts expose the account context and truthful empty/error states.
Evidence: migration on a populated local test DB, focused scheduler/API/UI tests, a live preview with two sample accounts and mobile review.
Out of scope: online app connection/upload, auto publication, changes to Claude's video renderer.

Current Phase 5 state: **IMPLEMENTED**. A populated-database migration retained unassigned items, which the UI exposes in a read-only card; account-isolation, scheduler, auth and publishing regression passed (28 tests), and the follow-up unassigned/API/UI check passed (7 tests). The account-first Scheduling script parses in V8; loopback desktop and phone previews load with separate Tech and History topics and schedules. Operator visual/mobile inspection remains pending. Next action: review the updated account-first layout and correct any interaction issues.

## Phase 6 — Queue and progress visibility
User-visible outcome: Studio and each account queue show queued topics, scheduled runs, and the actual state of active jobs, with a route to the generation record.
Acceptance: account queues remain isolated; job state comes from persisted jobs rather than inferred progress percentages; an empty queue and failed fetch are explicit; signed-in desktop and phone dashboards load.
Evidence: focused API/UI workflow tests, populated local preview, job-state inspection.
Out of scope: scheduler policy changes, remote upload, invented completion estimates.

## Phase 7 — Generation record and copy actions
User-visible outcome: Generations has its own page, and each job exposes its saved destination accounts, format, inputs, description, narration, and recorded Codex provenance with truthful copy actions.
Acceptance: exact saved account intent and request fields survive refresh; copy reports success/failure; absent script or exact command is labeled unavailable; job review actions still work.
Evidence: focused tests and signed-in dashboard inspection.
Out of scope: replaying Codex, exposing secrets, changing generation content.

## Phase 8 — Account defaults and simplified creation
User-visible outcome: operators can save an account as the initial creation destination and edit each account's default description in Accounts; clipping moves to its own page and optional music upload leaves the main creation path.
Acceptance: defaults persist across reloads and apply only as initial selections; per-video overrides still win; clipping and music actions retain their API behavior on desktop and phone.
Evidence: repository/API/UI tests and signed-in responsive smoke check.
Out of scope: remote account connections, publishing, global production config changes.

Current Phase 6 state: **VERIFIED**. The signed-in account queue test creates separate account schedules and jobs, records a stage event, and confirms the `/api/jobs` state/event plus dashboard queue controls; scheduler and auth regression passed (7 tests). Studio and Scheduling scripts parse in V8, and the refreshed phone preview returned HTTP 200. No progress percentage is inferred. Next action: build the dedicated generation record view and copy controls in Phase 7.

Current Phase 7 state: **IMPLEMENTED**. Generation metadata, saved-input API, narration copy and exact-command provenance are in place; existing jobs with no command record are labeled unavailable. A focused test reads a saved Codex command from a real local artifact record; the 48-test affected-workflow batch passed, rendered dashboard and new controls parse in V8, and the populated Tech/History preview responds on desktop and phone URLs. Operator visual review remains open. Next action: review the populated generation cards and record dialog on both widths.

Current Phase 8 state: **IMPLEMENTED**. One durable default account can be selected in Accounts, its description remains editable, and media tools have a separate page. A restart test confirms the default survives and disabled accounts cannot be selected; the 48-test affected-workflow batch passed. The preview shows one saved default account and both channel jobs. Operator desktop/phone visual review remains open. Next action: review creation, Accounts and Media tools on both widths before visual acceptance.
