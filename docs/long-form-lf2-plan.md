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

The operator selected the available 3Blue1Brown capture for real-script acceptance. Its supplied transcript remains unverified reference context; independent primary sources must ground the new script. The TECHNETIUM reference has metadata but no accessible captions and still needs a supplied transcript.

## LF2 D unblock sequence

The installed Codex runner passed preflight and returned a library book-sorting draft with 35,506 reported tokens. Local validation rejected its optional engagement comment because it did not pose a question. The repair exited without a completed result or known usage. Preserve the terminal run and its allowance.

| Order | Owner and outcome | Acceptance evidence | Out of scope |
| --- | --- | --- | --- |
| 1 | Codex. Persist actionable runner failure diagnostics. | Offline replay of a failed CLI exit and timeout produces bounded, redacted receipts. Reopening a receipt cannot launch again. | Live calls or allowance changes. |
| 2 | Codex. Fix the output contract using the saved draft. | Replay the actual draft offline. Make optional comment handling explicit. Verify that a comment-only defect does not require regenerating narration and that the result still goes to independent review. | Weakening grounding or creative gates. |
| 3 | Claude can take a separate branch. Make the dedicated writer runner reproducible with Docker. | Clean build, dedicated persistent auth and receipts, pinned dependencies and tokenizer data, and zero-call socket preflight. | Changes to LF2 validation, prompts, receipt format or the active deployment. |
| 4 | Codex. Integrate the fixes and qualify one ten-minute script. | Reviewable exact preflight and separately authorized pilot. Inspect the complete script, grounding, originality, hook/title scores and independent review. Report observed usage and unknowns separately. | Reusing the terminal allowance or claiming a five-hour quota percentage. |
| 5 | Follow the existing LF3–LF6 gates after LF2 D acceptance. | Inspect a real landscape ten-minute render with timed narration, thumbnail and final QA before qualifying fifteen minutes. | Publishing. |

Steps 1–2 own the writer application and its tests. Step 3 owns container build, Compose and deployment documentation and uses the existing socket interface.

Steps 1 and 2 are locally **VERIFIED**. The saved book-sorting draft passed local validation with six chapters and 1,452 unchanged narration words after omitting the invalid comment. The hook and title scorers ran. A simulated workflow verified that an invalid optional comment reaches independent review without a narration repair. The original pilot remains terminal and LF2 D remains **BLOCKED** pending the dedicated runner and live acceptance.

Step 3 is **BLOCKED** on the current host. The isolated image built with the pinned Codex CLI, Pillow and tokenizer data. Its startup probe exited before opening the socket because Bubblewrap could not create a namespace under the container runtime policy. See [Docker qualification](deploy/codex-runner-runtime.md#dedicated-docker-runner-qualification). Next, qualify a compatible policy or prepare the bounded acceptance run on the restricted host service while Docker qualification continues.

Step 4 preparation is **IMPLEMENTED**. The revised held-out book brief is staged with no calls and an exact 32,026-unit draft reservation. The restricted host preflight found a stale prompt. The reviewed wheel matches locally. Install it and verify the exact installed preflight before authorizing the new 100,000-unit pilot. See [revised pilot preflight](long-form-lf2-d-codex-preflight.md#revised-held-out-book-pilot).
