# Forensic audit: the original "API rate limiting" Short

Status (9 Nov 2026): **P5 audit and advisory checks IMPLEMENTED** on `claude/script-audit` (unit/fixture tests plus a real-artifact inspection of the original video).
**NOT MEASURED:** any new generation, any listening A/B, any render of the rewrite. Nothing here is approved or published, and the rewrite below is a hand-written **draft**, not a claim of a better video.
Plan: `docs/script-naturalness-plan.md` (Round 3). Builds on, and does not redo, P0/P1/P2/Round 2.

## 0. Evidence used

| Item | Value |
| --- | --- |
| Original | Batch job `batch-caaacb77d5659ea27ce1292d20f45c6f6b6f857c30d4ad97`, short `ms1-pilot-rate-limit-v2` |
| Written | 2 Nov 2026 23:39 UTC by Claude `sonnet-medium` (medium effort), prompt template `m6-content-v8`, prompt 67,348 chars, recorded `attempts: 3`, 210.8 s; written **before** the P2 and Round 2 prompt changes of 6 Nov |
| Verbatim copy | `tests/fixtures/scripts/api_rate_limiting_original.json` (narration, scene templates, claim ids, source ids, delivery cues = none, on-screen text kept apart) |
| Narration source of truth | `content_package.json` `script_sections[].narration`; it equals `reference_short.scenes[].vo` in all 12 scenes. Captions (`captions-display.srt`) and on-screen text were not used as narration. No transcription was needed. |
| Video inspected | `final.mp4`, 49.7 s, contact sheet at 5 s steps plus frames inside scenes 3, 5 and 6 |
| Earlier attempt | `ms1-pilot-rate-limit` (`batch-b44add80…`) failed twice: `package.reference_short.scenes.10.cta: CTA headline must be the follow request or comment prompt present in narration` (a `cta` final scene despite `ending: loop`). Left in `failed_validation`, allowance not reset. |

`qa_check.py` on the artifact folder: PASS duration (49.7 s), speaking-rate (153 words / 49.7 s = **3.08 words/s**, band 1.9 to 3.2), loudness (−14.2 LUFS, −2.5 dBTP), loop-ending, audio-clipping/silence/level-jumps, sfx-variety, licence trail, thumbnails, description. WARN: dead-stretch (scene 7 terminal, 3.3 s), music-under-speech (87 stretches). QA measures delivery, not whether the script reads naturally; the video passed all of it.

## 1. Before and after, sentence by sentence

Every original sentence is quoted exactly (a test enforces this). "Kind" uses: formal, generic, long, repetitive, unnecessary; *defines* = states what a thing is, *explains* = shows why or how it works for the viewer.
The improved wording is the draft in `tests/fixtures/scripts/api_rate_limiting_rewrite_draft.json`; it keeps every claim id (c1 to c7, c9, c10), all three source ids and the figure 429.

| Original wording | Problem | Improved wording | Reason |
| --- | --- | --- | --- |
| Your rate limiter is a speed bump, not a wall. | **Hook.** Abstract metaphor, no figure and no named product in the voice (AWS and 429 appear only as chips); "X, not Y" slogan that is repeated in scenes 8 and 11 and the loop. Generic; defines nothing yet gives no reason to care. | You hit your API Gateway limit. A 429 still isn't guaranteed. | Names the product and a figure, states a stake the viewer can test, and leaves it open (c2, c4). |
| Expect a hard wall? | Rhetorical question that exists only to be denied next; unnecessary. Delete. | *(deleted)* | The hook already made the point; the next fact can start the scene. |
| That is not it. | Filler ("that is not it" is on the P0 filler list); stiff "That is" where a person says "That's". Delete. | *(deleted)* | Says nothing; the time goes to the mechanism. |
| The token bucket allows controlled bursts. | **Definition first** and documentation voice: lifts Gravitee's phrase (c6 "allows controlled bursts of traffic") before the viewer has seen a bucket. Defines, does not explain. | But the bucket holds spare tokens, so a burst can spend them all at once. | The mechanism arrives after the picture, as a consequence ("so"), and it is the surprising part (c2, c6). |
| Picture a bucket full of tokens. | Good idea, but the voice says "picture" while the screen shows a stack of boxes (FULL BUCKET, REQUEST ARRIVES, TOKEN SPENT), not a bucket; the diagram only appears seconds into the line. | Here's why. Every request you send spends one token from a bucket. | Puts the viewer's own action first and merges the analogy with the one good explaining sentence (c1). |
| Every request you send spends one token. | The strongest explanatory sentence in the script (it explains, addresses the viewer, c1). Keep; it arrives at 8 s. | *(merged into the line above)* | Keep it, earlier, in contracted spoken form. |
| The bucket refills at a steady pace. | Documentation voice, abstract subject ("The bucket"); "bucket" starts sentences in 5 scenes. | Tokens drip back in at a constant rate, so your average stays smooth. | Makes the refill the cause of the smooth average instead of two disconnected facts (c7, c6). |
| Slow and steady. | Filler slogan; the 3-word "punch" the writer prompt asks for, with nothing to punch. Delete. | *(deleted)* | A punch line needs a fact behind it. |
| Your average traffic stays smooth. | Right idea in the wrong place: a result stated as a separate sentence. | *(merged into the refill line)* | One idea per sentence, joined by "so". |
| Here is the catch. | Filler (on the list) and stiff "Here is"; on screen this is a blank FRONT-LOADED SPIKE card for about two seconds. Delete. | *(deleted)* | The catch is the next sentence; say it. |
| A full bucket lets a whole burst through first. | The real payoff (c2), but it comes at scene 5 of 12, after the myth, the definition and the refill. Explains. | *(see the "But the bucket holds spare tokens…" line)* | The surprise should sit right after the setup, not after the filler. |
| Extra traffic gets in. | Restates the previous sentence in other words; unnecessary. Delete. | *(deleted)* | Redundant: the burst already got in. |
| Your API takes it before the gate starts refusing anyone. | "Gate" is a third image (bucket, wall, gate); long and indirect. | Only when the tokens run out does API Gateway start throttling your clients. | Says what happens, in order, and names the product (c3). |
| Only then do clients get a 429 error, which means too many requests. | The right fact, ending in a glossary clause ("which means") read as a definition. 429 is spoken as a number and appears on screen. | That's when the 429 shows up. It just means too many requests. | Two short spoken beats instead of one documentation sentence (c3); 429 now appears in two scenes. |
| AWS calls the limit a target, not a ceiling. | The actual thesis (c4, "best-effort, targets rather than ceilings"), landing at scene 8; "AWS calls" is attribution in the voice (the P0 attribution pattern does not match "calls"); second use of the slogan frame. | Even then, AWS treats the limit as a target, not a guarantee. | Keeps the one slogan that carries the thesis, in plain words. |
| Think soft, not hard. | Echo of the line before and of the hook (third slogan); on the P0 filler list. Delete. | *(deleted)* | Nothing new. |
| Other factors can push traffic past the limit too, so your safety net leaks. | Vague ("other factors", the source is vague too, c5) and a mixed metaphor (net that leaks). | Bursts aren't the only leak. AWS admits some requests slip past anyway. | Stays inside what c5 supports; does not pretend to name the factors. |
| You choose the rate and the burst yourself. | Fine and addresses the viewer; weak because no value is shown or said (the card shows `100` and `2000` that the voice never says). | So set the rate and the burst yourself, even for a single route. | Merges the fragment below; c9. |
| Even for each single route. | A sentence fragment; reads as an afterthought. | *(merged into the line above)* | One sentence. |
| A single bucket is a speed bump, so stack account and method limits. | Third use of the hook's metaphor; the payoff is a restatement, not a takeaway. | Remember the account and method limits, because API Gateway applies those too. | A new fact (c10), not the hook again. |
| Now you know why stacking limits matters, because | **Ending.** Announces that the lesson is over instead of giving an action; grammar slip ("limits matters"); the join with the hook reads "…matters, because your rate limiter is a speed bump, not a wall." | So stack your limits, because one gate is never enough, and | Ends on what to do, and the loop join reads "…is never enough, and you hit your API Gateway limit. A 429 still isn't guaranteed." (the join is acceptable, not elegant). |

Added by the draft (no original counterpart): "Treat your limit as a rough guide, and put a second layer behind it." as the payoff line (opinion framed as the video's verdict, cites c4 and c10).

Delivery cues the original lacked and the draft would take (positions only, not applied; the fixture stays clean text): `[pause 0.4]` after "A 429 still isn't guaranteed." in the hook; `*run out*` in the throttling line; `[breath]` before "Even then,"; `[pause 0.4]` before the payoff line. Word counts are unchanged when tags are removed.

## 2. The nine failure patterns, checked against the original

| # | Pattern | Found in the original | Caught before this audit | Now |
| --- | --- | --- | --- | --- |
| 1 | Definition first | Yes: scene 2 states the bucket's behaviour ("allows controlled bursts") before any picture or stake; the hook is a metaphor with no consequence | Hook has no number/name (P0) | **Missed in general**; the specific lift is not caught either (the originality check needs 7-word shingles). Left to the editor pass (P4). |
| 2 | Documentation language | Yes: scenes 2, 4 and 7 ("allows controlled bursts", "refills at a steady pace", "which means too many requests") | No | Partly: the repeated-subject rule and the stiff-forms rule cover the symptoms, not the register itself |
| 3 | Missing conversational language | Yes: 0 contractions in 153 words, "That is not it", "Here is the catch" | Only "X not" forms (scene 2) | **Caught**: no contraction in N words; "that is/here is/you are" |
| 4 | Repetitive structures | Yes: three "X, not Y" slogans; "bucket" starts sentences in scenes 2, 3, 4, 5 and 11 | Only same-scene slogan echo ("Slow and steady") | **Caught**: slogan-frame rule (3+), repeated-subject rule (5+ scenes, topic nouns in the hook excluded) |
| 5 | Narrative progression | Partly: myth, mechanism, catch, refusal, caveat, dials, layers is a defensible arc, but scenes 5 and 6 say the same thing and scene 2 gives the conclusion first | Thesis restated (scene 11, P0) | Not algorithmic; flagged for the listener pass |
| 6 | Abstract explanations | Yes: "picture a bucket" is drawn as boxes; the burst is never shown with a number; the card shows `ThrottlingBurstLimit 100` and `ThrottlingRateLimit 2000` that no line says | On-screen figures never spoken (P0) | Unchanged (caught). The draft carries no invented values: the sources give 100 as an example only, so a running example still needs a source page with values. |
| 7 | Unnecessary information | Yes: "Expect a hard wall?", "That is not it.", "Extra traffic gets in.", "Think soft, not hard." | Filler list (2 of 4: "That is not it.", "Think soft, not hard.") | "Extra traffic gets in." is a restatement and is **not** detectable without semantics |
| 8 | Weak emphasis and pacing | Yes: zero delivery cues; 3.08 words/s, near the top of the QA band; four slogan "punches" instead of one real one | No | Cue count is in the scorecard; no gate (forcing cues makes them worse). See section 3, TTS. |
| 9 | Poor ending | Yes: "Now you know why stacking limits matters, because" | Loop join capitalisation only | **Caught**: closing announcements ("now you know", "so remember", "to sum up", …) |

The seven review points of the plan (section 3 of `script-naturalness-plan.md`) map as: 1 payoff recommends more of the leaky thing (prompt only, no check), 2 abstract hook (P0), 3 unspoken figures (P0), 4 filler/vague (P0, extended), 5 two mechanisms under one metaphor (prompt only), 6 route versus method (prompt only), 7 captions split mid-phrase (P1, fixed in the renderer).

## 3. Where each problem came from

Not everything is the model. Layers cited by file and function (line numbers drift; names are stable).

| Problem | Layer | Evidence |
| --- | --- | --- |
| Abstract hook, no figure | **Research + prompt.** The prompt demands "one concrete number, name or date taken from the sources" (`prompts.py::build_content_prompt`, SCRIPT CRAFT) but the three sources contain no example values; `research.py` ran once and could not supply any. The hook scorer `youtube_skills.py::hook_gate` accepted the line. | `source_packet.json`: only "429" and a truncated CLI sample carry numbers |
| Thesis said three times (hook, scene 11, loop) | **Prompt.** The writers' room block tells the model to "build the whole script around it and keep its verdict" (`prompts.py::writers_room_block`); the shared prompt told the writer to echo the hook (fixed in Round 2). | HANDOFF Round 2 note |
| Four slogan "punch" lines | **Prompt.** ANTI-SLOP says "mix one 3 to 5-word punch sentence into every two scenes" (`prompts.py`); with a documentation source and nothing to punch, the model writes "Slow and steady." This is a rule working as written against thin material. | scenes 2, 4, 5, 8 |
| Staccato, one fact per 8 to 15 words | **Output schema + prompt.** `domain/contracts.py` and the prompt force 8 to 15 words per scene and one claim per scene; a continuous explanation is cut into 12 fragments. | word counts per scene 10 to 15 |
| Documentation voice and definition first | **Research + claims.** Claim text is the source's wording (`c6`, `c7`), and the writer paraphrases claims scene by scene. The 7-word originality gate (`craft.py::originality_problems`) cannot see a 3-word lift. | scenes 2, 4, 7 |
| No contractions | **Prompt (before 6 Nov).** The contraction rule was added in Round 2; this script predates it. TTS does not cause it. | scorecard: 0.0 per 100 words |
| Vague "other factors" | **Research.** The AWS page itself says "other factors"; the writer had nothing to name (`craft.py::VAGUE_OTHER` now flags it). | claim c5 |
| On-screen `100`, `2000` never said | **Scene planning + schema.** A `code` visual may be added without any link to the narration; the layout accepts it (`rendering/shorts/layout.py::SceneRenderer`). | contact-sheet tile at 40 s (TWO DIALS card) |
| Picture of a bucket shown as boxes; FRONT-LOADED SPIKE blank under "Here is the catch" | **Scene planning + assembly.** The writer picked the `flow` template for an analogy (TEMPLATE CHOICE says flow is for paths and sequences) and its nodes reveal after the voice line starts. | frames at 9, 11, 16, 17 s |
| Source crop cut off mid-sentence with an "Ask AI" chip | **Video assembly.** Source capture (`pipeline/capture.py`); later work on `dev` changed the capture rules, but this render predates it. Needs a look at the next real source card, as the handoff says. | frame at 11 s |
| Captions break "NOT A / WALL" | **Renderer.** `rendering/shorts/layout.py::caption_groups`; fixed by P1. | plan section 3, point 7 |
| 3.08 words/s, 49.7 s for a 60 s request | **TTS + word budget.** `prompts.py::reference_word_budget` aims at 2.5 words/s ("aim_low = 2.5 × seconds") but its own docstring says the measured rate is 2.9 to 3.0; Kokoro at speed 1.15 with grouped speech and compressed pauses runs at 3.0 or more. The result is a video about 17 percent shorter than requested, spoken at the top of the QA band, with no room for a pause. | `qa_check.py` speaking-rate |
| Zero delivery cues | **Prompt.** The DELIVERY CUES rule is optional ("not every scene needs one"); the model used none. The cue machinery (`rendering/shorts/cues.py`, `delivery.py`) is not at fault. | scorecard `delivery_cues_total: 0` |
| "limits matters", announcement ending | **Prompt + loop rule.** The loop scene must be open-ended, so the model completes a half-sentence ("because"); `craft.py::loop_problems` and `loop_reads_as` only check capitalisation and punctuation, not grammar or content. | scene 12 |

Combined cause worth naming: 8 to 15 words per scene, one claim per scene, a "short punch" rule and a thin documentation-only source set together produce the choppy, slogan-heavy rhythm. TTS then makes it worse by reading it at 3 words a second with no cues. Changing only the prompt would not remove it.

## 4. Scores of the original (1 to 10)

| Category | Score | Evidence |
| --- | --- | --- |
| Conversational quality | 3 | 0 contractions in 153 words; "That is not it.", "Here is the catch."; documentation phrasing in scenes 2, 4, 7 |
| Hook strength | 4 | Memorable image, but no figure, no named product in the voice, no stake, and the idea is restated three times |
| Technical clarity | 6 | Every claim maps to a cited source and the mechanism is correct; held back by "other factors", "safety net leaks" and "limits matters" |
| Narrative flow | 4 | Conclusion first; scenes 5 and 6 repeat; payoff is a restatement; ending announces instead of advising |
| Sentence variety | 5 | Length variation 0.44 and distinct openings, but 3-word slogans in four scenes and three "X, not Y" frames |
| TTS suitability | 5 | No symbols or unsafe forms and the loudness is right; 3.08 words/s is near the QA ceiling, no cues, no pauses |
| Visual explainability | 4 | Good: the AWS quote highlight and the terminal. Poor: bucket drawn as boxes, an empty card under filler, unspoken `100/2000`, cropped source with "Ask AI" |

These scores are the author's judgement from the text, the QA output and the frames. Nobody has listened to the video for this audit, and the operator's own read remains the acceptance.

## 5. What was implemented

All advisory; nothing blocks a job or changes a prompt, the schema, the TTS settings or the renderer.

| File | Change |
| --- | --- |
| `src/tubeforge/providers/content/craft.py` | `spoken_craft_problems` (slogan frame, repeated sentence subject, no contractions, contractable forms, closing announcement), called from `naturalness_problems`; `rewrite_keeps_evidence` (claim ids, source ids and figures survive a rewrite) |
| `tests/test_script_audit.py` | 12 test cases: fixture is verbatim, every new rule flags the original, the older checks still flag their part, seven accepted scripts raise nothing new, unit cases for each rule, the rewrite draft is clean and keeps the evidence, the audit quotes every original sentence |
| `tests/fixtures/scripts/` | `api_rate_limiting_original.json`, `api_rate_limiting_rewrite_draft.json`, `accepted_scripts.json` (seven scripts the operator did not reject: Log4Shell trial 5, the Claude Code email Short and the five pilot Shorts) |
| `docs/script-naturalness-plan.md`, `docs/HANDOFF.md` | Round 3 spec and status |

False-positive check: the new rules were tuned on the seven accepted scripts. One flagged them wrongly at first (a topic noun, "nosql", that the script's own hook names, and a repeated verb "rotate"), so the repeated-subject rule excludes words in the hook and needs five scenes. One accepted script, the idempotency pilot, still raises "no contraction in 149 words"; that is a true positive (it genuinely has none), and the test records it rather than hiding it. Thresholds are tuned on eight scripts and are not proven; do not promote any of them to a gate (P3) without a larger reference set.

Not done, on purpose: a full `craft_problems` run on the rewrite (it needs a complete validated package, not a fixture), any render of the rewrite, any change to the prompt, the word budget or the TTS speed.

## 6. How the new output compares with the original

**NOT MEASURED.** No generation was run. The draft rewrite passes the advisory checks and the evidence check, has 150 words (original 153), 2.7 contractions per 100 words (original 0), the figure 429 in two scenes (original: one) and no reuse of the original's slogan. It has not been rendered, spoken or approved, and it is not claimed to be better. The honest next measurement is one go-ahead generation of the same brief with the current prompt (Round 2 plus this audit's advisories) and an operator listen of both.

## 7. Token and cost change

- **This audit:** 0 writer calls, 0 research calls, no paid API. Cost: none.
- **Original generation (inferred from the spend ledger window around 23:35 to 23:39 UTC on 2 Nov):** 4 Claude launches and about $0.56 in total for this brief (research, angle pass, writer attempts). The job's evidence file records only the final writer invocation: 67,348 prompt characters.
- **Prompt size now:** rebuilding the prompt from the job's saved request with the current code gives 66,709 characters, 639 fewer than recorded. That is **not** a like-for-like comparison: the rebuild omits the writers' room block the original call carried. Treat prompt size as unchanged within noise.
- **Effect of this audit's changes on future cost:** none. The new checks are deterministic and run after generation; they add no tokens, and as advisories they trigger no repair attempt.
- **What would raise cost:** promoting any of these checks to a gate (P3). A failed gate costs one repair call per attempt (about the price of a writer call). That is a decision for the operator.

## 8. Final report

1. **What was wrong:** an abstract, figure-free hook restated three times; documentation-style sentences (definition before reason to care); no contractions; slogan filler in four scenes; a duplicated and misplaced payoff; an ending that announces; on-screen figures never spoken; bucket drawn as boxes; 3.08 words/s with no cues.
2. **From the prompts:** the thin hook rule against sources with no figures, the writers' room "keep its verdict" instruction, the "short punch" rule, the optional cues rule, and the missing contraction rule (the last three were later addressed or partly addressed in Round 2).
3. **From the architecture:** research that found no example values, the one-claim-per-scene 8 to 15 word schema, a code visual with no link to the narration, template choice for analogies, a loop ending that checks only punctuation, and no editorial refinement stage.
4. **From TTS and timing:** the word budget plans for 2.5 words/s while the voice runs at 3.0 or more (video about 17 percent short, rushed); no delivery cues in use. The voice pronounced the words correctly; TTS did not cause the unnatural wording.
5. **Implemented:** section 5. **IMPLEMENTED** (unit and fixture tests plus inspection of the original's frames and QA output). Nothing is **VERIFIED**: that needs the operator's listen to a rendered rewrite.
6. **Comparison with a new output:** NOT MEASURED (no go-ahead generation).
7. **Cost:** audit free; future generation cost unchanged; gates would add repair calls.

Open decisions for the operator: (a) authorise one before/after generation of this brief (provider Claude `sonnet-medium`, about 4 launches and $0.50 to $0.60 by the ledger above, acceptance by listening to both); (b) whether to retune `reference_word_budget` to the measured 2.9 to 3.0 words/s (changes every script's length and needs its own plan); (c) whether to promote any advisory to a gate once the reference set is larger.
