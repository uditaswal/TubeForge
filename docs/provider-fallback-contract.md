# Provider fallback contract — proposal awaiting operator approval

Status: **BLOCKED** pending approval of the dashboard/router change. No runtime
behavior changes in this checkpoint. Tests for future implementation must use
stub runners; no live generation is authorized.

## Runner interface expected from Claude's lane

Extend `HostRunnerFailure.code` in the shared socket protocol with:

| Code | Meaning | Automatic fallback candidate |
| --- | --- | --- |
| `quota_exhausted` | Confirmed provider membership quota or configured spend/call cap | Yes, subject to remaining shared script allowance |
| `runner_unavailable` | Runner/service unavailable; no usable draft returned | Yes, subject to remaining shared script allowance |
| `authentication_failed` | Login, credential, subscription access or authorization failure | No; require operator action |

Keep `message` bounded and redacted and preserve the existing truthful
`invocation_started` field. All operations (preflight, research, generation) must
use the same categories. Do not infer a quota error from arbitrary message text.
The legacy `unavailable` code is ambiguous (currently mapped to authentication
failure); it must not become fallback-eligible merely by renaming its exception.
Timeout, cancellation, invalid output, quality rejection, source mismatch,
insufficient sources and allowance exhaustion never trigger automatic fallback.

## Proposed router and dashboard behavior

- Modes: Claude only, Codex only, automatic fallback. Persist the selected mode
  through a tested authenticated API; a job must retain its routing policy for
  restart/review. Existing jobs keep their exact selected owner unless the
  operator explicitly selects a different policy.
- Automatic mode tries the preferred owner, then the other enabled owner once
  on an eligible structured failure. Never cycle back to the first provider.
- An owner change must not reset an exhausted allowance, silently gain two more
  attempts, repeat topic research, or bypass grounding/creative acceptance.
  Consumed attempts remain consumed across providers for the same source packet.
  Research is still once per exact brief. Its failure path needs its own explicit
  acceptance test before automatic research fallback is enabled.
- A successful response binds the actual provider, usage and fallback reason to
  the job and accepted package. Owner-bound request validation, cache identity,
  lease fencing, cancellation and exact-artifact approvals must remain valid.
- A failed fallback surfaces both redacted causes. A disabled/cancelled membership
  is never contacted in its corresponding single-provider mode.

## Cost and acceptance proposal

Implementation and local tests: no paid calls, $0 incremental API spend. Future
membership-runner calls retain their existing caps; no live generation is included.
A writer prompt can reach 75,000 characters, roughly 19,000–25,000 input tokens,
plus variable output and existing editor calls. This is a planning estimate, not
a price quote or permission to spend.

Acceptance: stubbed routing/error taxonomy tests; single-provider isolation;
one-shot fallback; no fallback on validation/auth/cancel/timeout/exhaustion;
shared allowance and cache replay/restart tests; actual-provider provenance;
signed-in mode persistence and truthful pending/error/disabled states at desktop
and mobile sizes. Live end-to-end generation requires separate authorization.
