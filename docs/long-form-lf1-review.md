# LF1 intake acceptance — 8 November 2026

Branch: `codex/long-form-reference-plan`, implementation parent `f554541`. Scope and acceptance were written in [LF1 plan](long-form-lf1-plan.md); operator instructions are in [Reference intake](operations/reference-intake.md). Current phase status belongs to the internal design tracker.

A signed-in operator can queue a public YouTube reference, inspect metadata and timestamped transcript context, supply missing text, download the exact hashed snapshot, inspect immutable history and request a fresh capture or cancel pending work. The existing worker handles acquisition; web handlers do not fetch sources. The source-linked improvement worksheet is a provisional review aid, not AI analysis, research, factual approval or a script.

## Requirement/evidence audit

| Requirement | Inspected evidence |
| --- | --- |
| Canonical public URL, safe DNS/TLS/redirects and bounded acquisition | `tests/test_reference_intake_extractor.py`: private/foreign destinations, DNS deadline, redirect rejection, header/stream byte limits, encoding, absolute deadline, exact video identity, caption formats, language, unavailable/malformed data, role-control rejection and cancellation |
| Durable dedup/cache/revisions | `tests/test_reference_intake_repository.py`: concurrent identical creation, shared capture claim, cache reuse, explicit fresh retrieval, supplied metadata reuse, unchanged old hashes and stale revision rejection |
| Leases, ownership, restart/cancel safety | Repository tests reject expired/reclaimed/cancelled owners and recover pending work after shutdown; `tests/test_reference_intake_worker.py` checks integration with the existing worker loop and shutdown before generation |
| Matching authenticated API | `tests/test_reference_intake_api.py`: sign-in/CSRF, durable queuing without web fetch, configured channels, strict inputs, bounded body, revisions, exact export hash and no generation jobs |
| Source-bound compact proposed brief | `tests/test_reference_intake_brief.py`: deterministic snapshot identity, exact indexed excerpts/timestamps, provisional proposals, bounded output and no invented proposals without text; six live excerpts compared with canonical source cues |
| Compact history | Repository test forbids full-detail loading during list projection and checks that history omits cues/supplied text; only selected detail/export carries the transcript |
| Schema/migration compatibility | Frozen request/read schema checks pass; migration tests upgrade from 0032, add only the two intake tables, downgrade and upgrade again without changing existing tables. Planning schema refreshed for the already-present `operator_script` field |
| Signed-in responsive workflow | Real Chromium acceptance at 1440×1000, 820×1180 and 390×844: navigation, queue, missing captions, invalid/SRT fallback, old revisions, hashed download, fresh capture, cancellation, reload, failure preservation, drafts/open disclosure preservation, mobile menu/Escape, no overflow or JS exceptions |
| Asynchronous review safety | Chromium delays selection GETs, mutation responses and a pre-cancel pending GET: actions stay disabled during selection load, responses cannot replace a different selected reference, and a stale pending read cannot undo confirmed cancellation |
| Real public-reference intake | Actual extractor captured metadata for `https://www.youtube.com/watch?v=aircAruvnKk`: 3Blue1Brown, “But what is a neural network? \| Deep learning chapter 1”, 1,120 seconds. Public caption response was empty, producing `needs_input` with retained metadata |
| Real supplied fallback and immutable manifest | Creator's public SRT supplied as a new revision: 286 cues, original text retained, zero fallback fetches, unchanged revision 1, duplicate reuse, no generation jobs and exact canonical export SHA-256 `03ea3e0fe8ed448960f6a51041999c69405dac0c77f67c351b7b13446abe80d5` |
| Actual artifact/UI inspection | Canonical snapshot, both revision responses, live worksheet, source indexes, live signed-in screenshots and all six visual-inspector fold/contact-sheet images opened; source title/origin/limitations remain readable and transcript scroll is bounded |

Validation: **333 passed** in the relevant long-form, runner, worker, auth, API, Studio, contract, acquisition and migration group; **2 passed** in the additional worker-entrypoint group; **1 passed** in the final opt-in three-viewport Chromium workflow. The voice-cache regression test replaces synthesis with `FakeVoiceProvider`; it now uses an available executable for startup validation rather than depending on host Piper. No production voice/provider behavior changed.

Browser command:

```bash
TUBEFORGE_REFERENCE_BROWSER=1 PYTHONPATH=src .venv-benchmark/bin/python -m pytest -q --tb=short -o faulthandler_timeout=60 tests/test_reference_intake_browser.py
```

Local ignored evidence:

- `artifacts/review/reference-intake-lf1-validation-20261108/`: validation logs and reproducible test command.
- `artifacts/review/reference-intake-lf1-browser-20261108/`: fixture-browser screenshots and viewport report; fixtures are labelled synthetic.
- `artifacts/review/reference-intake-lf1-live-20261108-b/`: live SQLite intake, original/corrected supplied SRT, `revision-1.json`, `revision-2.json`, `snapshot.json`, `brief.json`, `report.json`, live signed-in screenshots and rendered DOM/visual-inspector report.
- `artifacts/review/reference-intake-lf1-live-20261108/`: earlier failed network attempt, retained separately rather than overwritten.

## Live-caption and timing limits

Successful live automatic caption retrieval is **not proven**. The tested YouTube track returned empty text; fixture tests prove parsing/capture when caption text is accessible. The application reports this honestly and supports the supplied fallback. It does not obtain access tokens/cookies, bypass restrictions, transcribe paid media or treat the title as watched content.

The supplied SRT came from the [creator's public captions repository](https://github.com/3b1b/captions/blob/main/2017/neural-networks/english/captions.srt). The original file had two invalid intervals: cue 214 ended before its start, and cue 273 had zero duration. The unmodified input was rejected. For this intake test only, an explicitly corrected operator file gave these cues positive 1 ms intervals; `report.json` records exact before/after times and both file hashes. No words were changed, and the application did not perform this repair. This proves storage/validation/fallback, not audio alignment, transcript accuracy or creative acceptance.

## Visual review

The app-screen inspector measured **0 FAIL / 3 WARN** on the script-free DOM captured from the real signed-in live artifact at 1440/768/390. Its report and six images were inspected; the inspector process ended with exit 143 during cleanup after writing the result, so the report, not a claimed zero process exit, is the evidence.

The content/state/transcript region answers “what was captured and what is missing?”; native controls, origin and limitations are legible. The form and context share column edges, and the transcript stays within its scroll region. Colour marks the primary action, current navigation and durable state; no invented performance metrics appear. Cue coverage is a union of intervals and explicitly does not mean accuracy/completeness.

Warnings retained with reasons: the small “Workspace” label belongs to the shared shell; unequal panel bottoms follow independent form/history versus variable-length review content and avoid stretching empty panels; the phone edge-text measurement follows the existing shell gutter and remains readable in the actual viewport capture. The operator's existing navy system takes precedence over choosing a new palette.

## Remaining phases

LF2 must add primary-source research, substantive reference analysis, production profile/prompt admission, bounded durable writer accounting and grounded script review. Ready intake is context only; it is not converted to a generated ContentRequest or narration approval by LF1. Landscape rendering, full-duration QA, packaging and 10/15-minute creative pilots remain later phases. No skill/prompt resources, paid APIs, live writer calls, production deployment, merge, push or publication occurred.
