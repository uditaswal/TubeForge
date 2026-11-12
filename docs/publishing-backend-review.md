# Publishing backend review

## Current checkpoint: publishing backend

**IMPLEMENTED; live acceptance remains BLOCKED.** This branch accepts Google loopback
HTTP callbacks, binds an operator's Day-review disclosure decision to the exact final
and reviewed draft, checks Short media before credential refresh, sends the configured
category and made-for-kids setting and reviewed synthetic-media flag, and restricts the
account adapter to private uploads. A fenced, durable Pacific-day quota reservation
prevents concurrent TubeForge uploads from exceeding the configured local estimate.
Studio reports worker, OAuth, account and estimated quota readiness.

Evidence: the requested publishing/delivery/OAuth/account/scheduling regression
selection passed **99 tests**, with one opt-in Chromium check skipped in that run;
the signed-in Chromium check passed separately at 1440, 768 and 390 px without page
errors or horizontal overflow (`artifacts/review/publishing-p1-readiness/`). A real
locally encoded Short was driven through Day-review approval, draft submission, fake
YouTube transport, quota reservation and matching remote observation. The quota
migration upgraded, downgraded and re-upgraded on a temporary SQLite database. A
subsequent targeted group passed **16 tests** after tightening quota reservations.
The full suite passed: 1,140 passed, 34 skipped in 17m20s (`/tmp/tubeforge-publish-full-20261112.log`); skips include opt-in native and browser checks.

The local quota is conservative, not a Google quota balance: it retains reservations
for uncertain or pre-upload failures and does not include calls from other clients.
The disclosure decision currently requires an approved Day-review final and its
registered disclosure artifact. Quota exhaustion pauses the delivery for explicit operator resume.

The feature worktree has no `.env`. On 12 Nov the original project `.env` had nonempty entries for `TUBEFORGE_ACCOUNT_ENCRYPTION_KEY`, `TUBEFORGE_GOOGLE_OAUTH_CLIENT_ID`, `TUBEFORGE_GOOGLE_OAUTH_CLIENT_SECRET` and `TUBEFORGE_GOOGLE_OAUTH_REDIRECT_URI`; their validity and account connection have not been tested. A real private upload needs a named approved final and the operator's go-ahead for that exact post. Its Google snapshot, processing, thumbnail and downloaded remote frames remain unverified.
No external upload, publication, deployment, push or merge has occurred.

## Remaining work

The Instagram-shaped delivery core is **VERIFIED** for fake-backed local scope:
`tests/test_container_delivery.py` has eight passing cases including container expiry,
upload interruption, lost publish response, stale publish lease, publish-once guard
and bounded polling hints. The full requested publishing selection passed 106 tests
with one opt-in browser skip. Migration `20261111_0034` upgraded, downgraded and
re-upgraded on a temporary database. The adapter contract for Claude is in
`docs/HANDOFF.md`. Instagram OAuth, the real Instagram adapter and its per-platform
API gates remain Claude's work and have not been verified here.

P3 cross-post backend is **IMPLEMENTED**: a current approved Day-review identity
previews destination defaults and creates one checksum-bound two-platform draft,
with the reviewed thumbnail staged atomically. Instagram confirmation is explicit
and recorded in the service; the API gate and UI remain Claude's integration. Tests
cover stale approval, caption and hashtag limits, explicit confirmation and both
directions of destination-failure isolation: 17 focused tests passed. The requested
publishing regression selection passed 107 tests with one separately run browser skip.
A changed staged thumbnail is refused before upload. Real cross-posting remains
unverified and requires the operator's exact-post go-ahead.

P4 scheduling backend is **IMPLEMENTED**: per-delivery slots, an IST default, a
30-minute preparation window and late fence, durable cadence override and distinct
pending pause/resume/cancel actions. YouTube `publishAt` requires a recorded audit
setting and explicit future-public confirmation; missing/past times fail closed.
Ten frozen-clock/scheduling tests, a temporary-DB migration round trip and a signed-in
three-width audit/readiness browser check passed. Publishing regression: 117 passed,
one separately run browser skip. Real scheduling and Claude's calendar UI are unverified.

P5 backend is **IMPLEMENTED**: the worker starts by default and remains idle without a valid key; bounded provider hints and jitter, quota pause/resume, fenced reconnect state and downtime burst protection are covered by tests. The seven-day fake soak delivered 42 of 42 destinations with zero duplicates and zero losses (`artifacts/review/publishing-backend-soak-20261112/summary.json`). The signed-in readiness screen passed at 1440, 768 and 390 px (`artifacts/review/publishing-p5-readiness/`). A real scheduled week and operator sign-off remain unverified.

The reviewed parallel Instagram adapter at `claude/publish-instagram` commit `5ec244b` publishes during upload/resume, does not implement separate container inspection and publication, appends hashtags a second time, and treats quota exhaustion as retryable. It must be adapted to the protocol in `docs/HANDOFF.md`; the executor rejects its current interface before remote work. A published container without a provable media ID remains an unknown outcome. Claude owns that adapter, OAuth and the platform gate.

The original project `.env` also has nonempty `TUBEFORGE_INSTAGRAM_APP_ID`, `TUBEFORGE_INSTAGRAM_APP_SECRET` and `TUBEFORGE_INSTAGRAM_OAUTH_REDIRECT_URI`; their validity is untested. Live acceptance is blocked on integration, a named approved final and separate exact-post permission. The first private YouTube upload reserves an estimated 1,600 units by default.
