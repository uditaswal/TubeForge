# Track E implementation plan

Approved scope: `provider-fallback-contract.md`, operator approval 5 November 2026.
All checks use stub runners; no live script generation or paid calls.

1. Durable policy: add the three routing modes to the existing authenticated
   video-creation API and immutable job request; preserve legacy serialization.
   Acceptance: create/reload jobs for each mode, disabled-provider and auth/CSRF
   failures, stable generation identities. Evidence: focused API/domain tests.
   No provider selection behavior changes before Claude's error-code commit.
2. Router: rebase on Claude's committed codes, then implement one-shot fallback,
   shared source-packet allowance, cached replay/restart and actual-provider
   evidence on package/job. Acceptance: stub transports, disallowed-error matrix,
   concurrency/legacy allowance tests, grounding validation and no repeated
   research. Research remains on the preferred owner without automatic replay.
3. Dashboard: add mode/preferred-writer controls with truthful pending/error/
   disabled behavior using the existing authenticated creation API. Acceptance:
   UI-runtime tests and isolated signed-in desktop/mobile browser inspection.
   Update setup/operator docs and HANDOFF, then commit the review checkpoint.
4. Only after Track E is reviewable: inspect the M4/design-token acceptance
   requirements and produce/inspect the required local artifacts. Separately
   audit the M-S6/M-S7 data contract; record UI gaps in HANDOFF without changing
   Claude's Day review UI.

No uploads, remote pushes, merges, allowance resets, local production LLMs, or
changes to Claude's runner/error-code lane.
