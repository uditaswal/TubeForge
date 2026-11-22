# HANDOFF — read this first (Codex and Claude)

**Hard limit: 60 lines.** Current focus, open items, next command. Detail goes in the linked doc, history in git
(previous long versions: `git show 01dad7f:docs/HANDOFF.md`, or `dev` before the 23 Nov merge). Rules: `AGENTS.md`. Docs index: `docs/README.md`.

## Goal
Operator drops a link or brief → AI Short / clip / long script → local render (Kokoro TTS, Python/FFmpeg) → review → approved upload
to several social accounts. The AI (Codex or Claude) only returns a strict JSON script + scene plan; pixels, audio and encoding are local.

## Current focus (one at a time)
**Publish the first private YouTube Short end to end** (the connected YouTube channel, private only: `youtube_api_audited` is off).
Everything not listed under "Open" is frozen.

## Architecture in one screen
- Dashboard (`api/app.py`, port 62065, loopback; operator uses an SSH tunnel) → durable job → worker (`workers/`, Docker) → `pipeline/orchestrator.py`.
- Script owner per job (`codex` default | `claude`): Codex host runner `/run/tubeforge-codex/codex.sock` (sudo to redeploy); Claude user runner = systemd user unit `tubeforge-claude-runner` (`data/run/claude/claude.sock`; linger is on, so it survives SSH loss). `scripts/restart_stack.sh` restarts it through systemd.
- Studio "Start from a link" (`api/link_intake_ui.py`): Clip it / Reference Short / Long video, via the existing intake APIs.
- Accounts: one account (person/brand, `account_groups`) owns one connection per platform (`social_accounts.group_id`); pickers show the account with select-all.
- Reference Shorts (9:16, 30–120 s): `pipeline/reference_short.py` → `rendering/shorts/`. Preview 720×1280, final 1080×1920; QA −15..−13 LUFS, TP ≤ −1.5.
- Batch plans (`api/batch*.py`): import → strictly FIFO queue → Day review (`/batch/review`). Spend cap 40 calls / $8 / 24 h.
- Settings `/settings` (`docs/settings.md`); exact-script mode (`pipeline/exact_fit.py`); clips (`docs/clips.md`).

## Open (status label — next action)
1. **Private YouTube upload — IMPLEMENTED, live NOT DONE.** Uploads only accept a short approved in Day review, and none is eligible (the 4 Nov shorts lack an audio-licence record). Next: Day review → story-cache → Regenerate (its accepted script should be reused, no Claude call) → approve the script in Generations → approve the render in Day review → create the draft and submit as private. Operator authorized that one private post. `docs/publishing-backend-review.md`, contracts in `docs/publishing-api-contracts.md`.
2. **Job `642dc2b2…` (LeetCode) is at `preview_ready`:** its preview was re-rendered after the earlier approval, so the operator must approve the new preview in Generations. A stale approval now backs off (`approval_stale` event, 60 s) instead of looping.
3. **Instagram setup — operator task.** `TUBEFORGE_INSTAGRAM_APP_ID` must be the numeric Instagram app ID from Meta (not `tubeforge`); rotate the app secret that was pasted in chat; register the redirect URI; add testers while the Meta app is in Development mode. Publishing stays frozen.
4. **Secrets hardening — planned, not started** (operator said later): `chmod 600 .env`; root-only secrets + Docker file secrets; agent runs as a separate OS user.
5. **Clips — merged to `dev`.** Clip jobs now get thumbnails (with operator notes saved) and Generations shows source and clip titles. Deferred: performance loop and clip-editor decision (`docs/clips.md`, "Later") — remind the operator.
6. **Reference Shorts reconciliation — IMPLEMENTED.** Review the final, then verify the signed-in production flow without publishing. `docs/reference-shorts-plan.md`.
7. **Long-form LF2 D — BLOCKED** on the operator installing the reviewed host wheel (sudo). `docs/long-form-lf2-d-codex-preflight.md`.
8. **Script audit P5 — IMPLEMENTED,** before/after NOT MEASURED; needs a go-ahead for one Claude call (state cost first). `docs/original-script-audit.md`.
9. **Stack:** rebuild with `scripts/restart_stack.sh` after each merge to `dev` (the 22 Nov build predates the login/thumbnail button fixes and this merge).

## Frozen (do not work on until the operator reopens)
Instagram publishing (16 Nov) · Docker runner qualification · landscape/LF3 · provider auto-fallback · thumbnail `safe_region`.

## Next command
Operator: `scripts/restart_stack.sh`, then Day review as in Open 1. Agent: after the approval, create the draft (`POST /api/publishing/drafts`) and submit it as private.

## Gotchas
- Batch queue is strictly FIFO: a script at `script_approval_required` blocks every later job. Deleting the job unblocks; rejecting does not.
- Two-attempt allowance per exact source packet: change brief/sources, never reset counts. Identical accepted requests reuse the cached script.
- Sources: small HTTPS html/plain pages on allowlisted hosts; < 2 usable sources triggers a research call; prompt cap 90,000 chars.
- Claude runner imports code at start: restart it after prompt/layout changes; restart `web` + `worker` after schema changes.
- Full suite ≈ 18 min (run in background); `tests/test_pipeline_orchestrator.py` alone ≈ 29 min. Known host-only failure: `test_voice_preview_is_synthesized_once…` (no `piper`). Fresh worktrees need `models/` symlinked.
- Dashboard test login: temporary admin via `docker compose exec web tubeforge create-admin`; delete it and its sessions (`admin_users`, `auth_sessions`) afterwards.
