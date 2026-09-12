# Historical overnight status

> Superseded as the current-status source by [`docs/STATUS.md`](../STATUS.md).
> This snapshot is retained as historical evidence for the overnight work.

| ID | Scope | Status | Tests | Commit/hash | Notes |
| --- | --- | --- | --- | --- | --- |
| A | Audit and tracking docs | DONE | repository inspection | — | Existing worker safety mechanisms identified. |
| B | VideoPlan | IN_PROGRESS | changed-source syntax pass | — | Typed durable projection is checkpointed; render consumers still use legacy package. |
| C | Visual Router | IN_PROGRESS | `test_visual_router` | — | Strategy/fallback is persisted with each asset decision; motion-graphics renderer remains future work. |
| E | Quality gate | DONE | quality + orchestration tests | — | Durable pre-FINAL_READY gate blocks missing/corrupt media and captions; black-frame analysis is an explicit warning. |
| F | Dashboard authentication | DONE | `test_auth` | — | Argon2id bootstrap/login/session/CSRF/rate limit test passes; production config requires explicit admin bootstrap. |
| G/H | Accounts/publisher dispatcher | IN_PROGRESS | account + dispatcher tests pass | — | Encrypted accounts and idempotent generic dispatch receipts complete; orchestration targets/live OAuth adapters remain. |
| M/N | Topic queue and schedules | IN_PROGRESS | reservation/bulk/tick tests pass | — | Atomic reservation, dedicated scheduler service, bulk queue UI, and schedule creation UI; history/edit remains. |
| O/P/Q/R | Dashboard, variants, compatibility | IN_PROGRESS | platform variant unit test passes | — | Operations controls plus persisted platform variants; actual 9:16 derivative renderer remains. |
