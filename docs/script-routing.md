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

In Studio, expand **Script routing defaults**, choose a mode and default writer,
then choose **Save routing defaults**. Wait for the saved confirmation. The
per-video writer list is limited to the saved mode; automatic mode treats that
choice as the preferred writer. Unsaved changes, pending requests and unavailable
policies block generation until saved or reloaded. A stale save requires reload.
Actor/time information identifies the last confirmed save. Form reset after a
successful submission preserves the confirmed routing policy.

Automatic routing tries the other enabled writer once on confirmed
`quota_exhausted` or `runner_unavailable` signals. It never falls back on
`authentication_failed`, legacy `unavailable`, timeout, cancellation, invalid
output, quality/grounding failures, insufficient sources or exhausted allowances.
Consumed attempts remain shared across provider/model choices. Research is not
repeated on fallback. A failed fallback shows both redacted causes and never
cycles back after restart. Accepted cache replay does not contact a cancelled
runner again.

The package and job Activity record the actual writer, successful-writer usage,
per-attempt evidence and fallback reason; the Generations card identifies a
fallback writer. Unknown failed-call usage is not invented. Real Claude CLI/API
rate-limit errors that lack a structured signal remain `invalid_output`; message
text is never parsed to infer quota exhaustion.

Local acceptance uses stub runners and isolated browser tests; see
[the review](provider-fallback-review.md). No live generation or publication is
authorized by changing this setting.
