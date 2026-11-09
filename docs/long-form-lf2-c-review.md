# LF2 phase C acceptance

Phase C is **VERIFIED** locally on `codex/long-form-reference-plan` as of 9 November 2026. The signed-in Studio workflow links a captured revision to an exact preparation, shows the script and evidence, and saves an explicit review decision. [Operator workflow](operations/long-form-scripts.md)

- **19 focused checks passed** across the new review API, existing authentication and reference intake, Studio, and the normal format guard. The long-form profile is routed to script preparation before normal job creation or execution.
- Signed-in Chromium ran at 1440, 820 and 390 pixels. It queued preparations from an actual saved intake revision in an isolated database, ran the worker through synthetic host receipts, inspected narration, additions, usage and rejected output, and downloaded the bound bundle.
- Delayed reads could not revert a durable approval or cancellation. Exact duplicate preparation preserved the allowance. A stale review hash and missing CSRF token were refused. Retained attempt output and validation reasons stayed accessible after the recent activity window rolled over.
- The app-screen inspector reported **0 failures and 2 warnings**. The navigation label follows the existing Studio shell. Queue controls and the open narration have independent heights so opening chapters does not stretch the queue panel. Screenshot review corrected the default Codex label and phone margins.

Evidence is stored locally in `artifacts/review/long-form-lf2-c-browser/`, including `acceptance.log`, `review.json`, signed-in screenshots, and the inspector report. The approvals and rejections in those artifacts apply to synthetic test scripts. Phase D requires a bounded real CLI preparation of the selected 3Blue1Brown reference and a full review of the resulting script and usage. [LF2 phase plan](long-form-lf2-plan.md)
