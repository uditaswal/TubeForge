# Plan: less robotic scripts, without reworking the pipeline

Status (6 Nov 2026): **P0 IMPLEMENTED** (advisory checks, `craft.py::naturalness_problems`, scorecard rhythm signals), **P1 IMPLEMENTED**
(`layout.py::caption_groups`; unit/frame-test evidence only, no real-render inspection yet), **P2 IMPLEMENTED and live on `dev`** (merged `190a4f2` after the operator authorized the reference-set run; trialled on two briefs, 7 Claude calls, $1.78; evidence in `docs/script-naturalness-evidence.md`; not operator-reviewed),
**P3, P4 NOT STARTED**. Owner of phases: Claude unless marked Codex.

Finding while implementing P2: the editor pass told the model to keep at most one number per scene and to drop other figures from the voice-over,
which works against the review's "specific figure in the hook, one running example". The P2 branch changes that to two numbers per scene (matching the
existing hard gate `MAX_NUMBERS_PER_SCENE = 2`) and keeps the four-per-video cap.
Known limits of P0: it cannot judge hook strength (a hook with a strong consequence but no figure is accepted via scale words like "one"/"millions"),
and it does not flag a fact-dump script (other gates do); promote nothing to a gate until the reference set shows zero false positives.
Inputs: a review of the `ms1-pilot-rate-limit-v2` Short, a prompt suggested by another Claude session,
and a safety review of three public repositories. Nothing here changes the JSON envelope, the render
pipeline, the two-attempt allowance or `yt-script` (the sole production narration skill, hash-bound).

## 1. Repository review (5 Nov 2026, shallow clones in an isolated scratch folder, nothing executed)

| Repo | Safety | Value | Decision |
| --- | --- | --- | --- |
| `langgptai/awesome-claude-prompts` | No code; 3 markdown files and images. No licence file. | Low: a link list plus a "Smart Dev" prompt and a persona prompt, none about scripts. | Not installed; nothing copied (no licence). |
| `AICMO/AiCMO-Marketing-Prompt-Collection` | 2,445 markdown prompts (Apache-2.0, 66 MB) plus two GitHub Actions workflows that need `PAT_TOKEN`/Claude OAuth secrets. No exfiltration patterns; "you are now…" hits are ordinary prompt wording. The workflows are not used. | Low for us: B2B-SaaS "Intelligence Engine" prompts, up to 70 KB each (our writer prompt ceiling is 75 KB) and jargon-heavy, which is the opposite of natural speech. | Not installed as skills. Optional idea mining only (Short-Form-Video, Developer-Content, Founder-Brand folders), never loaded into production prompts. |
| `yoanbernabeu/NanoThumbnail` | Browser app plus a local MCP server (loopback WebSocket, user's own key in the browser); no exfiltration found. It drives a **paid** image API (Nano Banana), which `AGENTS.md` forbids for this project, and needs npm. | Medium: its `craft.md` is a good thumbnail critique checklist. | MCP/app **not** installed. Checklist adapted (MIT, attributed) as `.agents/skills/om-thumbnail-craft/`. |

Why "install into Claude and Codex" is one folder: both agents read `.agents/skills/` through `AGENTS.md`;
the skill is outside the hashed prompt resources (`youtube_skills.RESOURCES`), so no wheel-hash or host
redeploy is needed. No third-party copy of a narration skill is added (contract: `yt-script` only).

## 2. Diagnosis: why the scripts read as robotic

The existing gates (`providers/content/craft.py`) reject bad patterns (clichés, report voice, fact dumps,
stacked questions, loop ending). Nothing yet rewards what a person does when explaining: one concrete
example carried through, one idea per line, a payoff that follows from the setup. Evidence: the
rate-limit v2 Short passed `qa_check.py` and the craft gates, yet the review found seven writing faults.
QA measures delivery, not whether the argument holds together.

## 3. The seven review points mapped onto what exists

| # | Review point | Already covered? | Gap and proposed change | Kind |
| --- | --- | --- | --- | --- |
| 1 | Payoff recommends more of the thing just shown to leak | No | Add to the writer FINAL CHECK and the editor's listener test: "if the video shows X is unreliable, the last scene names the source's recommended action, never more X". Cannot be a regex. | Prompt |
| 2 | Abstract hook that then restates itself ("speed bump, not a wall… not a hard wall") | Partly (`REPORT_VOICE`, hook scorer) | Advisory check: scene 1 has a number or named thing; first two sentences share ≥ 0.6 content words (reuse `heading_repeats` logic); phrases like "that is not it". | Deterministic + prompt |
| 3 | On-screen values never spoken (burst 100 / rate 2000 card, silent narration) | No | Check that every figure in a scene's display fields (code lines, big stat, chips) appears in that scene's narration (after `spoken-v1` expansion) or is the one declared example. | Deterministic |
| 4 | Filler and vague lines ("slow and steady", "other factors can…") | Partly (`BANNED_PHRASES`) | Add a small filler list and a regex for unnamed "other factors/things/reasons"; advisory first. | Deterministic |
| 5 | Two mechanisms blended under one metaphor | No | Writer rule and listener-test question: "does any line explain two causes with one image?". | Prompt |
| 6 | Mixed terms (route vs method) | No | Writer rule; topic-specific, so no regex. | Prompt |
| 7 | Captions split mid-phrase ("NOT A / WALL") | No | **Renderer, not writer**: `rendering/shorts/layout.py::caption_groups` is a greedy "3 words or 850 px" splitter. Make it phrase-aware (never end a group on an article/preposition/conjunction/auxiliary, break at sentence ends), keeping word order and count so alignment timings still map. No tokens. | Renderer |

## 4. What to take from the suggested prompt, and what to leave

Take (as plain rules added to the existing writer prompt and editor pass, `providers/content/prompts.py`
and `host_claude_runner.py`, within the 75 k character ceiling): rules 1–6 and 8 (concrete hook, one running
example used in narration and on screen, one idea per line, no filler or unnamed vagueness, sourced and
actionable payoff, one term per concept), and the worked examples from the review as short bad/good pairs.

Leave: the new JSON output (`running_example`, `scene` list, `caption_chunks`, `self_check` booleans),
because the envelope and geometry are owned by application code (the contract keeps geometry out of model
output) and a model grading itself "honestly" is not evidence; the `{{TARGET_SECONDS * 2.7}}` word formula,
because Kokoro pace and the ≤ 96-word profile already bound length; rule 7 (ending), already enforced by
`loop_problems`; and `{{placeholder}}` templating.

## 5. Phases (one at a time; each ends with evidence before the next)

| Phase | Outcome | Acceptance | Out of scope |
| --- | --- | --- | --- |
| **P0** advisory checks (no tokens) | `script_scorecard` reports points 2, 3, 4 plus naturalness signals: sentence-length variance, contraction rate, repeated sentence openings. Nothing blocks. | Fixtures from the review's rate-limit script flag 2, 3 and 4 correctly; the three accepted pilot packages and trial 5 produce no false alarms; unit tests in `tests/test_script_craft*.py`. | Any new gate; any prompt change. |
| **P1** phrase-aware captions (no tokens) | `caption_groups` breaks at phrase boundaries. | Unit tests: no group ends on a function word, sentence ends respected, flat word order unchanged, every group ≤ 850 px; a local preview re-render of rate-limit v2 inspected at the two cited places via an FFmpeg contact sheet. Changed pixels need a new approval of the exact render; nothing is auto-approved. | New fonts, layout or timing changes. |
| **P2** prompt rules | Rules from section 4 merged into the writer FINAL CHECK and listener-test editor. | Prompt size stays under the ceiling; M-SQ5 five-topic reference set (including a re-brief of the rate-limit topic) scored with `scripts/script_scorecard.py` before/after, then the operator reads or listens to the A/B pairs. Needs the operator's per-run authorization for the Claude calls (about 5–10, within the existing 40-call, $8 cap). | Raising spend caps; touching `yt-script`. |
| **P3** promote to gates | Only checks with zero false positives on the reference set become repairable `craft_problems` (the repair loop already handles them in one pass). | Reference-set run shows each gate fires on the bad script and passes the accepted ones. | Gating payoff or terminology (not decidable by regex). |
| **P4** voice pass | Rhythm guidance (contractions, short and long sentence mix, a person's point of view per channel voice profile) plus real use of the delivery cues from M-AU2. | Operator listening A/B on two scripts; no claim of improvement without it. | New TTS voices. |
| **P5** forensic audit of the original (no tokens unless authorized) | `docs/original-script-audit.md` and a permanent fixture of the exact original; every finding traced to a layer and turned into an advisory check. See "Round 3" below. | Fixture is the verbatim `ms1-pilot-rate-limit-v2` narration; each new check flags it and passes the accepted scripts (zero false positives); audit scores and the layer trace are written with evidence; no claim of a better script without a rendered, inspected artifact or the operator's read. | Any live writer call, gate promotion, prompt change or TTS change (those stay P2/P3/P4). |

## 6. Decisions needed from the operator

1. Authorize the P2 reference-set generation (Claude calls, within the existing cap) when P0 and P1 are done.
2. After P2, say which gates to promote in P3 (default: only zero-false-positive checks).
3. Confirm the `ms1-pilot-rate-limit-v2` Short should be treated as a regression fixture, not published as is.
4. Round 3 (P5): say whether a before/after generation of the rate-limit topic is authorized (provider, calls, cost are stated first); otherwise the comparison is reported as NOT MEASURED.

## Round 2 (6 Nov): reviewer feedback on the two P2 scripts

Implemented without a live run (advisory checks plus prompt text); validation needs a new generation and therefore the operator's go-ahead.

| Feedback | Where it went |
| --- | --- |
| Thesis said three times (hook, line 3, line 10); say it only in the hook and the loop line | Advisory check `craft.py::naturalness_problems` ("restates the hook's idea", by shared content word pairs); writer rule "Say the thesis at most twice"; editor sense check. **Root cause found:** the shared writer prompt (`prompts.py`) told the model the line before the loop must "echo the hook" and "land a verdict", which produced both the repeats and the "My verdict:" label. Both now ask for the action or consequence in new words. |
| Mechanism first, then how it breaks | Writer rule "Order"; editor check. Not machine-checkable. |
| Weak line instead of the running example; no figure anywhere | Advisory "no figure at all"; writer rule asks for the example's concrete values early. |
| Vague "real login checks" | Advisory check on "real/proper/actual + work/tools/checks"; writer rule "Name the thing". |
| "will not" is stiff | Advisory check for uncontracted forms; writer rule "Speak it". |
| "My verdict:", "AWS says so", "Stripe's blog calls…" | Advisory checks for reviewer labels and sources named in the voice-over; the writer prompt now keeps attributions on screen (source chip) unless the citation is the surprise. |
| Claim is v1-only | Writer rule "Scope the claim"; not machine-checkable. |
| Open last line must read into line 1 as one sentence | `craft.py::loop_reads_as` joins the two lines (scorecard key `loop_reads_as`) for the reviewer; grammar itself is not machine-checked. |

Found on the way: `scripts/script_scorecard.py` did not pass display fields, so its on-screen-figure check was silently skipped; fixed. With it fixed, the old rate-limit script is flagged for the 429 and "100, 2000" card the narration never says, which was the review's point 3.
Status: **IMPLEMENTED and live** (runner restarted 6 Nov 18:11), validated on one run (3 calls, $0.52; see `docs/script-naturalness-evidence.md`, Round 2): order, contractions, named tools, no labels or attributions, and the loop join are fixed; the running example with concrete values, the v1/v2 scope and a figure in the hook are not. The brief's sources must include a page with example values for the writer to use.

## Round 3 (8 Nov): forensic audit of the original script (P5, NOT STARTED)

Why: Round 2 fixed prompts from reviewer feedback, but nobody has recorded, sentence by sentence, *why* the original reads as unnatural or
which layer caused each fault. Without that, new checks and prompt rules are guesses and nothing keeps the rate-limit script from regressing.
Do not simply write a better script: understand the failure first, then lock it in as tests. Build on Round 2 and P0; do not redo them.

**Setup and limits.** Branch `claude/script-audit` cut from `dev`, in its own worktree; never commit on `main`, no push or merge unless asked.
Tests run with `PYTHONPATH=src .venv-benchmark/bin/python -m pytest` (the shared venv otherwise imports another checkout's code).
No live writer calls, web research, paid API, allowance reset or publishing. A before/after generation needs the operator's go-ahead with provider,
expected calls and cost, and the acceptance test stated first (AGENTS.md script-generation rule). Status labels exactly NOT STARTED / IMPLEMENTED /
VERIFIED / BLOCKED; nothing is VERIFIED without inspecting a real artifact.

**A. Extract and preserve the original (verbatim).**
- The original is the reviewed Short `ms1-pilot-rate-limit-v2` (job `batch-caaacb77d5659ea27ce1292d20f45c6f6b6f857c30d4ad97`); find its artifact folder
  with a targeted `data/tubeforge.db` query. Also record why the first attempt `ms1-pilot-rate-limit` (`batch-b44add80…`) was rejected (a `cta` final scene despite `ending: loop`).
- Narration comes from `content_package.json` `script_sections[].narration` and must equal `reference_short.scenes[].vo`. On-screen text (headings, chips,
  `captions-display.srt`, source quotes) is kept separate; captions are never treated as narration. Transcribe with local Whisper only if the package is
  missing, and mark doubtful segments "(uncertain)".
- Save it to `tests/fixtures/scripts/api_rate_limiting_original.json`: narration per scene, scene templates, claim ids, source ids, target seconds, delivery cues.

**B. Line-by-line analysis.** For each sentence record: text; what is wrong; why it sounds unnatural spoken; formal, generic, long, repetitive or unnecessary;
explains or only defines; a natural rewrite; whether to delete it. Investigate: definition-first opening (a relatable problem should come before the mechanism),
documentation voice, missing contractions and transitions, repeated sentence frames, narrative progression, abstractions that need an analogy, animation or
developer scenario, off-point sentences, pacing and emphasis (where a pause, punch line or `*stress*` belongs), and whether the ending gives a takeaway.
Map each finding to the seven review points in section 3 and mark which P0/Round 2 checks catch it and which miss it. Every rewrite keeps its claim ids,
source ids and numbers and must still be supported by the `source_packet.json` excerpts.

**C. Deliverable `docs/original-script-audit.md`.** Table | Original wording | Problem | Improved wording | Reason |; scores 1-10 with one line of evidence each for
conversational quality, hook strength, technical clarity, narrative flow, sentence variety, TTS suitability, visual explainability. Judge the video by frames
(FFmpeg contact sheet, view the PNG) and quote `.agents/skills/om-video-quality/qa_check.py` output for its artifact folder.

**D. Trace every problem to its layer (cite file and function), without assuming the LLM is at fault.** Candidates: writer prompt
(`providers/content/prompts.py::build_content_prompt` and the Round 2 clauses), research (`providers/content/research.py`), editor/listener pass, output schema
(`domain/contracts.py`: 8-15 words per scene, `reference_short` scenes), a missing editorial refinement stage, craft gates (`providers/content/craft.py`),
TTS and spoken form (`rendering/shorts/spoken.py`, lexicon, voice speed, grouped speech), caption grouping (`rendering/shorts/layout.py::caption_groups`), scene
planning, video assembly. Record combined causes too (for example 8-15-word scenes plus TTS pauses give a staccato delivery).

**E. Regression tests (advisory first).** The saved original is a permanent fixture. Extend `tests/test_script_naturalness.py`, `tests/test_script_craft.py`
and `craft.py::naturalness_problems` rather than adding a parallel system. Each new check must flag the original and must not flag the accepted scripts
(the Claude Code email Short, Log4Shell, trial 5, the three pilot packages); nothing becomes a gate until the reference set shows zero false positives (P3).
Checks to cover: definition-first opening, repeated sentence frames in consecutive scenes, generic AI filler, unnecessary or off-point sentences, missing
contractions, a rewrite that keeps every claim id, source id and number, and read-aloud suitability (words per scene with delivery tags removed). An improved
version, if written, is a second fixture that must pass the full craft gates and a technical-accuracy check; it is not called better without a rendered,
inspected artifact or the operator's read.

**F. Final report (end of the audit doc and in the reply).** What was wrong; which problems came from prompts, from the generation architecture, from TTS;
what was implemented (files, tests, advisory vs gate); how new output compares with the original (NOT MEASURED unless a go-ahead run happened); token and
cost change from `data/run/claude/usage-ledger.jsonl` and prompt size before/after, stated honestly; IMPLEMENTED vs VERIFIED.

**Wrap-up.** Focused tests, then the full suite once; report failures against the known pre-existing ones (`test_hyperframes_proto` word groups,
`test_local_media_packaging` worker image, `test_sources` redirects, two in `test_youtube_skills`, voice preview needs `piper`). Commit at the green checkpoint (no
AI-attribution trailers, never `--no-verify`), update "Next step" in `docs/HANDOFF.md`, post the review. Do not merge or push.
