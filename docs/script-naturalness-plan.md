# Plan: less robotic scripts, without reworking the pipeline

Status: **NOT STARTED** (plan only, 5 Nov 2026). Owner of phases: Claude unless marked Codex.
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

## 6. Decisions needed from the operator

1. Authorize the P2 reference-set generation (Claude calls, within the existing cap) when P0 and P1 are done.
2. After P2, say which gates to promote in P3 (default: only zero-false-positive checks).
3. Confirm the `ms1-pilot-rate-limit-v2` Short should be treated as a regression fixture, not published as is.
