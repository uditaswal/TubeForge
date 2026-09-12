# Test results

| Time | Scope | Result | Notes |
| --- | --- | --- | --- |
| 2026-08-31 | Initial audit | PASS | Existing test suite not yet run in this session. |
| 2026-08-31 | Compose config | PASS | `docker compose config` rendered successfully. |
| 2026-08-31 | Queue test attempt | BLOCKED | Host Python lacks pip; existing image lacks new cron dependency. Container rebuild exceeded execution window. |
| 2026-08-31 | Auth/queue/migration focused tests | INCONCLUSIVE | Temporary container installed dependencies; test process emitted one pass but migration-heavy run exceeded the 30-second command window. |
| 2026-08-31 | Quality gate unit tests | PASS | `2 passed in 0.21s` in the project container. |
| 2026-08-31 | Offline pipeline integration | PASS | `1 passed in 24.36s`; verifies the new FINAL_READY quality checkpoint. |
| 2026-08-31 | Visual router + quality tests | PASS | `3 passed in 0.30s`; Compose configuration also passed. |
| 2026-08-31 | Account encryption test | PASS | `1 passed in 0.67s` in the project container. |
| 2026-08-31 | Scheduler reservation test | PASS | `1 passed, 1 deselected in 12.50s` with cron dependency injected into validation container. |
| 2026-08-31 | Scheduler due-tick test | PASS | `1 passed, 1 deselected in 12.96s`; a due schedule fires once then advances. |
| 2026-08-31 | Bulk topic repository test | PASS | `1 passed, 2 deselected in 6.42s`. |
| 2026-08-31 | Authentication API test | PASS | `1 passed in 18.82s`; login, session rejection, CSRF, and logout verified. |
| 2026-08-31 | Multi-target dispatcher test | PASS | `1 passed in 5.55s`; duplicate target dispatch reuses receipt and unsupported platform is explicit. |
| 2026-08-31 | Fresh migration head | PASS | `1 passed, 4 deselected in 13.45s`; fresh SQLite reaches revision `20260831_0019`. |
| 2026-08-31 | Platform variant planning | PASS | `1 passed in 0.20s`; master reuse and 9:16 derivative flags verified. |
| 2026-08-31 | Offline integration after variants | INCONCLUSIVE | Command window elapsed before summary; sequencing regression was fixed before retry. |
| 2026-08-31 | Final-ready quality sequencing | PASS | `1 passed, 36 deselected in 13.67s`; core orchestration reaches FINAL_READY with quality checkpoint. |
