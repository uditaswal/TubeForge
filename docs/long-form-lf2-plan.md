# LF2: grounded writing and durable budgets

Parent checkpoint: `2c69f63`, branch `codex/long-form-reference-plan`. Current status belongs to the internal design tracker. LF2 consumes exact LF1 snapshot revisions and stops at script review; rendering remains LF3.

## Requirements and implementation phases

| Phase | Operator-visible outcome | Acceptance and required evidence | Out of scope |
| --- | --- | --- | --- |
| A: scoped profile and stage contracts | A 600–900-second landscape script can be preflighted with explicit source/reference identities, chapters, usage bounds and canonical creative resources | Strict typed draft/review envelopes; five hooks/ten titles; complete canonical resource hashes and installed-wheel parity; measured prompt/schema/wire sizes and token-admission tests; existing Short schemas/prompts remain stable | Provider launches, rendering |
| B: durable grounded preparation | One preparation researches once, fetches primary pages locally, drafts once, receives an independent review and uses at most one narration repair, retaining rejected output and usage | Atomic reservations in existing DB under worker fencing, maximum five total calls/two narration attempts; provider/model/restart cannot reset allowance; host idempotent receipts and lost-response reconciliation; unknown dispatch/usage blocks rather than reruns; capture original HTTP and excerpt hashes; fault-injection and concurrent-worker tests | Per-chapter retries, silent provider switches, auxiliary narration rewrites |
| C: signed-in review and exact decisions | Start from a ready reference, inspect source-linked script/chapters, improvement/originality findings, top hooks/titles, measured-or-unknown usage, rejected drafts and exact approval/rejection | Matching authenticated API/CSRF and navy Studio UI; immutable artifact identity and durable decisions; silent refresh preserves edits/dialogs; signed-in desktop/tablet/mobile browser tests with delayed responses, failure and exhaustion states | Starting an unsupported long-form render or implying model review is approval |
| D: real script acceptance | One original 10-minute script demonstrates the complete LF2 path | Explicitly bounded authorized Codex CLI or Claude trial; actual reference transcript plus independently fetched primary pages; complete script read for grounding, usefulness/originality and hooks; actual local hook/title reports, measured usage and immutable rejected-attempt evidence if applicable; installed host/wheel resource parity | Video creative acceptance, publishing, claiming subscription quota percentages |

Run relevant checks after each coherent phase; report its acceptance before starting the next. Implement one phase at a time. Stub success cannot close the real-script gate.

## Architecture and ownership

Use an isolated script-preparation service/repository inside the existing runtime, SQLite database and worker loop, following LF1's fenced ownership. Keep `ContentRequest` and `ContentPackage` canonical; a companion groups the exact ordered sections into chapters and binds source/reference identities. Do not introduce another VideoPlan or renderer.

Use new path-free one-call host operations for LF2. The normal `generate_package()` path and Claude's internal draft/editor/retry loop cannot be wrapped as one ledger call: each real invocation must reserve its stage durably first. Store a host receipt before launching, persist bounded output/usage afterward, and expose reconciliation without launching again. A pending/unknown receipt is never silently retried. Existing shared provider limits remain authoritative.

Research returns primary URLs/assessment, never narration or trusted excerpts. Local fetching builds the evidence packet, retaining both original-response hashes and native excerpt hashes. Source/ref text stays untrusted. Independent editorial review returns findings, not replacement narration. Repair consumes the second narration attempt. All outputs and reasons remain inspectable even when rejected. Exact operator approval is separate and cannot enqueue rendering until LF3 exists.

Core owner edits runtime/protocol/host/repository/worker wiring. Prompt/profile and review helpers live in new isolated modules and consume these typed contracts. Dashboard work consumes the frozen API projection. Claude can work on assigned isolated resources/tests on a separate branch; no simultaneous edits to shared files. No delegation for implementation is required by this plan.

## Budget and live-run gate

Enforce stage count, two narration attempts and conservative token reservations before dispatch; never present unknown usage as zero or a character estimate as a subscription measurement. Measure the full prompt, schema and expected output before proposing the real trial. Report provider/model, effective stage/token/output limits, existing shared allowance, fallback and acceptance test before launch. No paid API or local LLM is authorized. Request a concrete bounded CLI trial only after the implementation and preflight are reviewable.

The operator's TECHNETIUM reference has metadata but no accessible captions. A supplied transcript is needed for that reference; the earlier 3Blue1Brown capture is available as a fallback pilot if selected. This does not block independent implementation.
