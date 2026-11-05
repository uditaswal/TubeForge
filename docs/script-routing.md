# Script routing

Apply the current database migrations before starting updated processes
(`alembic upgrade head`). Routing defaults are stored in the local database;
changes affect future jobs and do not rewrite jobs already in the queue or review.

The authenticated `GET /api/script-routing` returns the current policy, revision,
saved actor/time, and mode availability. `PUT /api/script-routing` accepts:

```json
{"mode":"codex_only","preferred_model":"gpt-sol","expected_revision":0}
```

Use the revision returned by GET. A stale revision returns a conflict and requires
a reload. Writes require the signed-in session's CSRF token. Every save creates
an audit-history row. Modes are `claude_only`, `codex_only`, and `automatic`;
Claude modes require the Claude runner to be configured. Preferred models are
`gpt-sol`, `sonnet-medium`, or `opus`, restricted to the chosen mode.

Manual, batch, and scheduled submissions inherit the saved mode. Each new job
stores its selected policy, so a later policy change does not retarget it.
Before cancelling a membership, review existing queued jobs as well as the saved
default. Source-clip jobs do not require a script writer.

Implementation checkpoint: durable API/job policy is tested. Automatic router
behavior and dashboard controls are still being implemented; this document does
not authorize live generation, publication, or changes to script allowances.
