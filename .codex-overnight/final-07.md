Continued the publisher architecture milestone.

Implemented:

- Migration `20260831_0019_publication_attempts.py`.
- Generic provider-neutral [dispatch.py](/home/uditaswal/docker/tubeforge/Youtube_Video_Producer/src/tubeforge/pipeline/dispatch.py):
  - durable per-job/account publication attempts
  - idempotency key per job/account/artifact
  - attempt counts and sanitized errors
  - retry eligibility for transient failures
  - explicit `unsupported` outcome when no platform adapter exists
- Local fake multi-target dispatch coverage:
  - duplicate dispatch reuses its durable receipt
  - unsupported Snapchat adapter is not falsely reported as success

Validation:

```text
Dispatcher test: 1 passed in 5.55s
Fresh migration head: 1 passed, 4 deselected in 13.45s
docker compose config --quiet: passed
git diff --check: passed
```

Updated all overnight tracking documents. Live YouTube/Meta/Snap adapter wiring remains clearly blocked on OAuth apps, approved scopes, credentials, and platform eligibility; no live publication was attempted.