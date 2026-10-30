# Application logs

Every TubeForge process writes JSON-lines logs (one JSON object per line) to `data/logs/`
(`/app/data/logs` in Docker — the existing `./data` bind mount; `data/` and `*.log` are git-ignored).
The same lines also go to stderr, so `docker compose logs` still works.

| File | Process |
| --- | --- |
| `web.log` | dashboard/API (`uvicorn`) |
| `worker.log` | job worker (render pipeline) |
| `scheduler.log` | scheduler |
| `publisher.log` | publishing worker |
| `claude-runner.log` | host Claude script runner |

## Rotation and retention
`<name>.log` is the live file. When it reaches `TUBEFORGE_LOG_MAX_MB` (default 10) it becomes
`<name>.1.log`, the previous `.1` becomes `.2`, and so on. Rotated files older than
`TUBEFORGE_LOG_RETENTION_DAYS` (default 5) are deleted at start-up, on rollover and hourly.
Other knobs: `TUBEFORGE_LOG_DIR`, `TUBEFORGE_LOG_LEVEL`, `TUBEFORGE_LOG_HEARTBEAT_SECONDS` (default 60, 0 = off).

## What a line contains
`ts` (UTC ISO-8601), `level`, `service`, `logger`, `pid`, `msg`, `rss_mb` (process memory),
`job_id` (every line emitted while a job runs), `request_id` (HTTP requests; also returned as `x-request-id`),
plus event fields:

- `event: http_request` — `method`, `path` (no query string), `status`, `duration_ms`, `client`.
- `event: outbound_http` — calls to external services (`host`, `path` without query, `status`, `duration_ms`, `error`).
- `event: job_claimed | job_state | job_run_finished | job_error | job_exception` — worker lifecycle;
  `job_state` carries `previous_state` and `previous_state_duration_ms` (time spent per stage);
  `job_run_finished` carries `duration_ms` and process stats.
- `event: process_stats` — every minute: `rss_mb`, `rss_peak_mb`, `threads`, `open_fds`, `cpu_seconds`.
- Errors: `level` ERROR/WARNING, `error_type`, `traceback`.

## Sensitive data
Bearer/Basic credentials, `password|secret|token|api_key|authorization|cookie=…` values, OAuth `code`/`state`/`key`
query parameters, `sk-…`, Google `ya29.`/`1//`, GitHub and JWT tokens are replaced with `[REDACTED]`,
and extra fields whose names look sensitive are redacted. Script text, request bodies and query strings are not logged.
This is best-effort pattern redaction; do not log secrets deliberately.

## Connecting OpsDetective
OpsDetective (`~/docker/projects/OpsDetective`) currently ingests OTLP/HTTP and its Collector discards
telemetry until its M1 storage pipeline exists, so file-based log ingestion is not wired yet. When it is,
mount `data/logs` read-only into the Collector and point a `filelog` receiver at it:

```yaml
receivers:
  filelog:
    include: [ /var/log/tubeforge/*.log ]
    operators:
      - type: json_parser
        timestamp: { parse_from: attributes.ts, layout: '%Y-%m-%dT%H:%M:%S.%f%z' }
        severity: { parse_from: attributes.level }
      - type: move
        from: attributes.service
        to: resource["service.name"]
```
with `- /home/uditaswal/docker/tubeforge/Youtube_Video_Producer/data/logs:/var/log/tubeforge:ro` on the Collector service.
The `filelog` receiver follows `<name>.log` across rotation to `<name>.N.log`.
