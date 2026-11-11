# Publishing backend review

## Current checkpoint: P1 local implementation

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
The full suite has not been run.

The local quota is conservative, not a Google quota balance: it retains reservations
for uncertain or pre-upload failures and does not include calls from other clients.
The disclosure decision currently requires an approved Day-review final and its
registered disclosure artifact. Quota exhaustion is a terminal local failure in this
checkpoint; the requested operations pause/recovery behavior remains to be built.

The project `.env` is missing `TUBEFORGE_ACCOUNT_ENCRYPTION_KEY`,
`TUBEFORGE_GOOGLE_OAUTH_CLIENT_ID`, `TUBEFORGE_GOOGLE_OAUTH_CLIENT_SECRET` and
`TUBEFORGE_GOOGLE_OAUTH_REDIRECT_URI`. A real private upload needs those values, a
named approved final and the operator's go-ahead for that exact post. Its Google
snapshot, processing, thumbnail and downloaded remote frames remain unverified.
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

Cross-posting, scheduling, provider backoff/jitter beyond the container hint,
default worker startup and the seven-day fake soak remain **NOT STARTED**.
