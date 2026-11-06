# Next ten Codex core tasks

Scope agreed from the active request to perform the next ten Codex tasks. Parent contract: `90314ba`. These complete core prerequisites within LF0 without taking Claude's editorial/prompt/UI files. Implementation status belongs only to the current design plan; this file defines acceptance and evidence.

| ID | Outcome | Dependencies | Acceptance / evidence |
|---|---|---|---|
| C01 | Canonical public YouTube reference URL contract | existing long-form profile | Equivalent watch/short URLs canonicalize; malformed/credential/private/arbitrary-host URLs fail |
| C02 | Timestamped transcript and reference snapshot contract | C01 | Finite bounded ordered cues, language/origin/metadata and unavailable-transcript truthfulness |
| C03 | Deterministic reference identity and exact-brief cache key | C02 | Same content stable, semantic changes invalidate, capture time retained separately |
| C04 | Strict proposed intake request/status projection | C01–03 | No client approval/hash injection; ready/needs-input/failed states consistent; schema fixtures |
| C05 | Validate a reference snapshot against planning and script | C02–03 | Hash, URL/language/identity integrity; changed/missing evidence fails without approval mutation |
| C06 | Bounded stage/call and narration-attempt accounting | accepted lean envelope | Persistable immutable attempt records; research once, narration twice total, auxiliary calls cannot rewrite narration |
| C07 | Aggregate observed usage without inventing missing totals | C06 | Mixed/unknown token/cost fields remain explicitly incomplete; no subscription conversion |
| C08 | Compact source-context builder with hard UTF-8 bounds | source packet provenance, C03 | Exact source IDs/excerpts, no silent truncation; oversized context fails; repeat use stable |
| C09 | Export chapters from measured section starts | approved package/chapter mapping | Absolute timeline, 00:00, strictly ordered ≥10s chapters, no guessed timestamps |
| C10 | Combined local preflight smoke and regression evidence | C01–09 | Synthetic reference→plan→approved-package identity→bounded context/budget→measured chapters; adversarial failures; no live service |

Allowed implementation paths: new `domain/reference_video.py`, `domain/long_form_budget.py`, `pipeline/long_form_reference.py`, `pipeline/long_form_budget.py`, `pipeline/long_form_chapters.py`, existing `pipeline/long_form_contracts.py` as needed, focused tests/fixtures and shared integration records. Forbidden lane paths: production narration skills, content prompts/youtube_skills, Claude editorial proposal and dashboard UI. No API endpoint, migration or preset registration is part of these contract tasks. Proposed HTTP-facing shapes remain explicitly unregistered until LF1 UI/API work can land together.

Each task uses the existing long-form and ContentPackage identities. Test artifacts use temporary directories, never the local production database. Test fixtures are synthetic, never operator approval or creative evidence. Acceptance requires focused tests plus one combined smoke, not a claim that full long-form generation works. Full LF0 still requires editorial/description-policy reconciliation before LF1.
