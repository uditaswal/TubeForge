Continued the scheduler operational milestone.

Implemented:

- Dedicated scheduler process: [main.py](/home/uditaswal/docker/tubeforge/Youtube_Video_Producer/src/tubeforge/scheduling/main.py)
- New `scheduler` service in [compose.yaml](/home/uditaswal/docker/tubeforge/Youtube_Video_Producer/compose.yaml)
- Scheduler configuration in `Settings` and `config/default.yaml`:
  - poll interval
  - topic reservation duration
- Added due-tick regression coverage to ensure a schedule fires once and advances its next run.

Safety preserved:

- Scheduler only invokes the existing transactional topic-to-job reservation.
- It never performs rendering, publishing, or heavy worker operations.
- Existing worker lease/fencing remains authoritative.

Validation:

```text
Scheduler reservation: 1 passed, 1 deselected in 12.50s
Scheduler due-tick: 1 passed, 1 deselected in 12.96s
docker compose config --quiet: passed
git diff --check: passed
```

Updated overnight status, test results, decisions, and autonomous progress. The worktree remains resumable and intentionally uncommitted due to existing user changes.