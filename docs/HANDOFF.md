# HANDOFF — read this first (Codex and Claude)

Last updated: 2026-10-22 by Claude · branch `dev` · see `git log -3` for the checkpoint.
Rules live in `AGENTS.md`. Evidence log `AUTONOMOUS_PROGRESS.md` is local-only and small (append-only; archives `_N` — do **not** read them).
Full review of the project (why videos look bad, phases): `docs/REVIEW_2026-10-21_END_TO_END.md`.
Content-quality review (script, hook, engagement, voice, music, visuals → actionable steps): `docs/REVIEW_2026-10-22_CONTENT_QUALITY.md`.

## Goal
Scheduled/user-briefed AI Shorts → local render (Kokoro TTS, Python/FFmpeg) → review → upload to
YouTube/Instagram across channels. The AI (Codex *or* Claude) is only the "brain": it returns a
strict JSON script + scene plan; all pixels, audio and encoding are local and cost no tokens.

## Working rules for the relay
1. Start: `git status`, `git log -5 --oneline`, read this file. One agent on the branch at a time.
2. Commit at every green checkpoint; before stopping (or near your token limit) commit and edit
   **Next step** below with a concrete file/command.
3. Judge video work by looking at frames: `ffmpeg -i x.mp4 -vf "fps=1/3,scale=270:480,tile=6x2" -frames:v 1 sheet.png`, then view the PNG.
4. Python with renderer deps: `.venv-benchmark/bin/python` (`PYTHONPATH=src`). Heavy renders: run in background.
5. Do not publish anything. Do not reset script-attempt allowances.

## Architecture in one screen
- Dashboard (`api/app.py`, port 62065) → durable job → worker (`workers/`, Docker) → `pipeline/orchestrator.py` state machine.
- **Script owner** is per job (`ContentRequest.script_owner`, `codex` default | `claude`), chosen in the Creator Studio form.
  - Codex: root-owned host runner behind `/run/tubeforge-codex/codex.sock` (needs sudo to redeploy).
  - Claude: user-level runner `scripts/run_claude_runner.sh` → `data/run/claude/claude.sock`
    (`src/tubeforge/host_claude_runner.py`; CLI binary resolved from the VS Code extension or `TUBEFORGE_CLAUDE_BIN`).
    Start it before using Claude jobs (`systemctl --user` unit in `docs/tubeforge-claude-runner.service`).
  - Routing: `providers/content/factory.py::ScriptOwnerRouter`. Config: `pipeline.claude` in `config/production.yaml`.
- **Reference Shorts path** (`m6-content-v8`, 9:16, 25–45 s): package carries `reference_short` scenes.
  Orchestrator branches to `pipeline/reference_short.py` → `rendering/shorts/` (layout, timeline, audio, encode).
  Legacy path (`rendering/preview.py`, `providers/media/local_graphics.py`) remains only for old jobs.
- Preview = 720×1280 draft; final = 1080×1920. Both pass the library's QA (decode, loudness −15..−13 LUFS, TP ≤ −1.5).

## Status (use AGENTS.md labels)
| Item | Status | Evidence |
|---|---|---|
| Claude as script owner (runner, router, API field, Studio selector) | IMPLEMENTED | Live Claude scripts through the dashboard API (3 jobs, ~$0.4–0.8 list price each); `tests/test_script_owner.py`. Studio selector exists but was not browser-tested. |
| Orchestrator uses `rendering/shorts` for `m6-content-v8` jobs | IMPLEMENTED | Dashboard job `41e2ee9a…` rendered through it (below) |
| Dashboard-generated Rust Short, 720×1280 preview, motion + icons | IMPLEMENTED (preview only) | below; creative acceptance by the operator is still open |
| Script-writer picker in Studio: Sonnet 5.5 medium (default), Opus 5.5 high, Codex GPT-5.6 Sol | IMPLEMENTED | `script_model` on `/api/videos`; `/api/content-profiles` lists models; Sonnet job `8c23e099…` end to end |
| Hook/script craft: prompt block + scored hook gate (≥58) + repairable skill/layout checks | IMPLEMENTED | Sonnet hooks scored 56–70 vs 42 before; selected "76% memory bugs, then what?" (67). Gate lives in `providers/content/youtube_skills.hook_gate` and `validate_video_package` |
| Motion layer (`rendering/shorts/motion.py`) + 22 procedural icons (`icons.py`) | IMPLEMENTED | stills + full encode inspected |
| Preview approval → 1080×1920 final → quality gate for reference jobs | IMPLEMENTED | Job `8c23e099…` (22 Oct): final.mp4 1080×1920, 34.2 s, library QA + `quality_report` passed; contact sheet `final-sheet.png`. Operator has not watched it. |
| Publication prep for reference jobs | IMPLEMENTED | Same job reached `publication_approval_required` (metadata, thumbnail, platform variants built; `_reference_timing`, thumbnail bound to final checksum). Nothing approved or published. Thumbnail is still the legacy bitmap-text placeholder. |
| Engagement debate comment (`metadata.engagement_comment`) | IMPLEMENTED (backend only) | Writer prompt (v8 only) asks for one provocative-but-fair pinned-comment question; contract rejects links/@/#/non-questions; carried into `publication_package.metadata`. Not generated in a live job yet; nothing posts it. |
| Content quality step 1 (review §9: pacing, craft gate, comment CTA, fonts, no placeholders) | IMPLEMENTED | Job `b1c3a6b5…` (Sonnet, 1 attempt, $0.21): 92 words, 35.6 s, −14.2 LUFS, 6 narration gaps ≥0.25 s (was 14), ~155 wpm (was 139); stance + challenge CTA + counter-argument pinned comment; `review-sheet.png` inspected. 2/7 scenes on estimated alignment — needs a listen. Operator has not watched it. |
| Real-imagery plates (review §6/§9a: Pixabay B-roll, source-page screenshots with marker highlight, typed code cards) | IMPLEMENTED | Job `90625bb5…` (Sonnet, 1 attempt): hook/CTA on Pixabay video, 3 scenes with captured source paragraphs, 1 Rust code card, 76→24 % stat kept as animated chart; preview 33.9 s, −14.2 LUFS, RTF 13.4, 844 MB RSS; `review-sheet.png` inspected. Later change (not re-rendered): screenshot viewport 820→540 px so quoted text is large — verified separately on Google's post. Operator has not watched it. |
| Writers' room (review §3 S1–S5, R1–R4): angle pass → draft with format recipe → editor pass, Claude runner only | IMPLEMENTED | Own one-call allowances (`salt` `angle`/`editor`, limit 1) on top of the 2-attempt draft allowance; angle failure or an editor output that fails validation silently keeps the draft (`provenance.writers_room`). Hook floor 30 (hookscore only a floor; report voice is now a craft error). Acceptance jobs on fresh GitHub blog/DevClass/InfoQ sources: `74c809b2…` (draft only), `c93f4c29…` (angle ok; editor rejected for a 7-word scene — the editor now gets one repair and the prompt keeps scenes at 8–15 words; **editor applied-path not yet seen in a live job**). Previews 37.6 s / −14.25 LUFS / 786 MB; 4 of 5 source screenshots captured, 1 fell back (quote not found). `socket_timeout_seconds` raised to 900 and `reservation_seconds` to 1800 for the longer run. |
| Instagram publisher | NOT STARTED | |

## Render evidence
Latest (Sonnet 5.5 medium, new hook gate): job `8c23e099f53640688fb8c26957ea4e57`, preview 720×1280, 34.2 s, −14.3 LUFS, `review-sheet.png` next to it; script generation 2.2 min, ~$0.38 list price.
Earlier: job `41e2ee9a44d6428885a387714a4788e8` (Claude-owned, preset `reference-short`, created/approved/rendered via the
signed-in dashboard API on 22 Oct; script approved only for a local test render, **nothing published**):
`data/artifacts/41e2…/preview.mp4` — 720×1280, 30 fps, 34.0 s, H.264/AAC 48 kHz, −14.3 LUFS, TP −2.5 dBFS,
full decode OK, Whisper forced alignment on 6/7 scenes (1 estimated — needs listening review),
render 11× realtime, peak RSS 0.64 GB. Review images next to it: `review-sheet.png` (2-s timeline), `motion-stills.png`.
Observed: readable hook, big count-up stats, icon badges, placeholders before each reveal, captions below the
graphics, sources on screen, CTA. Still weak: only boxes/stats/icons (no photos or illustrations), DejaVu type,
lower ~25% of the frame is platform-reserved space. The operator has **not** watched it yet.
Earlier job `6ddea03e…` (before motion) is the baseline for comparison.

## Next step
1. Operator watches `preview.mp4` (Studio → job → Watch preview) and gives creative feedback.
2. Operator watches `final.mp4` of job `8c23e099…` and decides on the publication gate (do NOT approve until watched). Then: real thumbnail from a final-video frame (current one is a placeholder), orchestrator-level test for the reference final→publication path.
3. Operator watches previews of `c93f4c29…` (fresh Microsoft Copilot-to-Rust story, real source screenshots) vs `90625bb5…` vs `b1c3a6b5…` vs `8c23e099…`. Next verify the editor pass applies in a live job (run a new brief, check `provenance.writers_room.editor.applied`). Then content review §9 steps 3–4: sound (A1 whole-narration synthesis, A4 voice/processing, A5 licensed music, A6 SFX) and visual depth (diagrams, versus template, beat-synced cuts, Claude frame review).
4. Image layer beyond icons: Wikimedia/stock photo slot per scene (rights path exists in `providers/media/`), better fonts.
5. Scheduler → private YouTube, then Instagram (hook gate/recipes are superseded by the content review's S1–S3).
6. **Codex v8 jobs now REQUIRE the host redeploy** (22 Oct): v8 prompts no longer embed the om-* skills, so the old wheel's preflight hashes differ from the worker's and the job stops before any model call. Codex (gpt-sol) host runner is the old wheel — its prompts lack the craft block/icons until redeployed, so the worker's new hook gate may reject Codex scripts: icons/phone-fit prompt text only reach Codex after the root redeploy
   (`docs/tubeforge-codex-runner-runtime.md`); Codex output is still validated by the worker (fit/word-count checks).

## Merge of `codex/multi-account-setup` into `dev` (22 Oct)
- Merged (commit `7266e5f`): account profiles, per-video/per-schedule destination snapshots, account-owned topic queues and schedules (migrations `20261022_0029`, `_0030`; head is `20261022_0030`), Studio shell/Scheduling/Generations UI. The Studio form now has both the script-writer picker and the destination fields in one `/api/videos` request wrapper.
- Post-merge full suite: 525 passed, 6 failed. Fixed (stale expectations/regression): migration head assertion, schedule script assertion (`channel_identity:voice.value`), Dockerfile install-line assertion, and an over-broad prompt-size wrapper in `host_runner.py`. Still failing, **already failing before this work** (checked at `f5497db`): `test_voice_preview_is_synthesized_once…` (host has no `piper` executable; passes in the worker image) and `test_shorts_renderer_is_portrait_30fps_and_caps_visual_holds` (legacy renderer filter graph vs expected `MarginV=470`).
- UI follow-ups for the Codex branch: the Generations view (`/api/jobs/{id}/studio-record`) shows exact CLI argv only for Codex CLI runs; Claude-owned jobs (writers' room, plates, `provenance.writers_room`, `plates_prepared` events) are not shown there yet.

## Plates / Pixabay (22 Oct) — operator notes
- Key lives in the untracked `.env` (`TUBEFORGE_PIXABAY_API_KEY`, template in `.env.example`); compose passes it to the **worker** only. Shared limiter state: `data/cache/pixabay/ratelimit.json` (80 req/min default, honours `X-RateLimit-*` and 429). Search results cached 24 h, files cached by asset id; per-asset evidence (id, page, author, licence) is in `reference/plates/manifest.json` and the job's `asset_manifest.plates`.
- Worker image now ships Chromium + Playwright (rebuild took ~38 min on this host: `docker compose build worker web migrate scheduler`). Capture only opens the job's own source URLs, refuses non-public addresses, and falls back to the template when blocked/quote not found. Screenshots show real page content incl. embedded images — commentary use, not a legal guarantee.
- Pixabay music is NOT used (Content ID risk); stock visuals only. Codex-owned jobs get no visuals until the Codex host runner is redeployed (old prompts).
- Not done: Pixabay credit in descriptions (not required), diagrams (review V6), animated line/cost charts beyond the existing big_stat bars, per-job visual toggle.

## UI follow-ups for the Codex UI branch (no UI was touched here)
- Show each scene's visual (stock query/clip, source quote + screenshot, code) in script review, allow removing a scene's visual, and show `plates_prepared` fallbacks (`events`, `reference/plates/manifest.json`) in the job activity. Show Pixabay evidence in publication review.
- Show `package.metadata.engagement_comment` in script review as an editable "Pinned comment (debate starter)" field; script approval covers it. Automatic/auto-review mode needs no extra step, so it is bypassed there. A per-job "skip comment" toggle would need an API field — not added.
- Show the comment in the publication review (`publication_package.metadata.engagement_comment`) with copy button; posting it needs a `commentThreads.insert` call and the YouTube `youtube.force-ssl` scope, neither implemented (manual paste for now).
- Script-writer picker already exists in the API (`script_model`); the UI selector for Claude Sonnet 5.5 / Opus 5.5 / Codex is the earlier follow-up.

## Source/voice/record UI edits (23 Oct; the Codex UI branch is merged, UI edits on `dev` are fine)
- `api/app.py`: the single-source fields and the JSON packet textarea are replaced by repeatable Sources rows in the Studio form (URL required; title and passage optional); a source with an empty passage is now read in full by `SourceIngestor` at request time (HTTPS, public hosts, no redirects, 24k chars); the form labels say so. `studio-record` returns `generation` (owner/model/effort/tokens/cost) and a reconstructed Claude command; the Generation record dialog (`generation_ui.py`) shows them. `voice_provider` is now `hybrid-http` (Kokoro voices + Piper HTTP fallback) so Kokoro voices with preview appear in the Narrator picker again. Job diagnostics line is formatted (durations, GiB/MiB, trivial stages hidden).

## Gotchas learned
- Kill/restart the Claude runner after *any* change to prompts/layout (it imports code at start): `scripts/run_claude_runner.sh`.
  Restart `web` and `worker` too after schema changes (they import `src` once).
- Failed generations burn the two-attempt allowance per exact request; change the brief to start a new request, never reset counts.
- Voice+alignment run fine at 2 GB; under heavy host swap Whisper can fail (now retried once, then logged estimate fallback).
- Worker image needs extras `alignment,reference-renderer` (`docker compose build worker web migrate scheduler` after pulling).
- Dashboard test login: create a temporary admin (`tubeforge create-admin`), delete it and its sessions afterwards.

## Open decisions for the operator
- Free stock media key (Pexels/Pixabay)? Not needed for icon/procedural visuals.
- Auto-fallback Codex⇄Claude when quota is exhausted (currently manual per-job choice only).
- Commit/branch policy for the large uncommitted working tree (nothing has been committed by Claude).
