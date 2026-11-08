# LF1: real reference intake

Parent: `f554541`, feature branch `codex/long-form-reference-plan`. LF0 design acceptance: `long-form-lf0-acceptance.md`. Current status remains in the single internal design tracker.

User-visible outcome: submit a public YouTube reference, inspect captured metadata and timestamped captions with provenance/limitations, supply a transcript if captions are missing, and retain immutable revisions for later writing. No source footage, paid transcription, writer call, generation approval or publication occurs.

Implementation sequence within this phase:

1. Safe bounded metadata/caption fetch and parser: canonical YouTube URLs only, public DNS/redirect controls, byte/time bounds, truthful language/access/missing-caption failures, no role-spoofing text handed to future writers.
2. Durable intake/cache/revision repository in the existing SQLite DB: atomic exact-request dedup, immutable completed revisions, leased/fenced worker acquisition, restart recovery, audited retry/supplied-transcript revision and no stale-owner promotion.
3. Existing worker integration and authenticated API: web only queues durable work, no direct fetching; read/list/detail/transcript/export, optimistic revision actions and existing session/CSRF protection.
4. Existing Studio UI: navy shell, reference form/history/details, transcript fallback and honest progress/errors. Poll silently without replacing edits or dialogs; desktop/tablet/mobile and keyboard behavior.
5. Acceptance: focused extractor/repository/API/UI tests, migration upgrade/downgrade tests, signed-in real Chromium, one live public-reference smoke, and inspected persisted snapshot/report. Explicitly separate fixture extraction from live retrieval.

Required evidence: extraction tests (captions, no captions, unavailable, language, malformed/oversized text, prompt-control data, private/redirect URLs, timeout); exact-request/cache/retry/revision/lease tests; signed-in API and CSRF tests; desktop/tablet/mobile screenshots and no JS/overflow; a real public link captured via the actual extractor; canonical snapshot/source hashes and preserved history after revision. LF1 acceptance does not require a generated long-form video.

Screen question: “Is this reference ready to use as context, and what is missing?” The largest region is the captured title/state/transcript, with limitations adjacent. Existing brand takes precedence over a new visual direction. Reuse the labelled sidebar/topbar, muted borders, readable transcript and one principal intake action. No invented KPIs or thumbnails, and no readiness/approval claims beyond durable state.

Out of scope: primary-source research, script generation, AI improvement analysis, landscape rendering, new publisher/integration, paid APIs and copying reference media. LF1 can expose a deterministic observation brief of captured material, clearly labelled reference context; it cannot claim a substantive editorial improvement without the subsequent grounded analysis.
