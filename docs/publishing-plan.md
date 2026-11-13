# Publishing plan: YouTube + Instagram upload pipeline

Branch: `feature/publish-pipeline` (from `dev` `088928b`, worktree `../tubeforge-publish`).
Status: **NOT STARTED** (plan only, 11 Nov 2026).
Goal: an approved final from Day review or Publishing goes, without manual file handling, to the
operator's YouTube channel and Instagram professional account. It goes first as private or
immediate posts, then at scheduled slots. Each post's remote state is verified and shown in Studio.

The operator's only job is to create the platform credentials (section 1) and to review or approve
in Studio. Claude and Codex do everything else.

## 0. What already exists (on `dev`)

| Piece | File | State |
|---|---|---|
| Google OAuth connect (state + PKCE, channel confirm page, encrypted envelope) | `security/google_oauth.py`, `security/oauth_state.py`, `api/app.py` `/api/oauth/youtube/*` | IMPLEMENTED, never run with real creds |
| Token refresh with fencing | `security/account_credentials.py` (`GoogleCredentialRefresher`, `AccountCredentialManager`) | IMPLEMENTED |
| Drafts → reviewed identity → submit | `pipeline/manual_publish.py`, `/api/publishing/drafts*` | IMPLEMENTED (YouTube-only gate in `submit`/`actions`) |
| Durable delivery queue, leases, unknown-outcome reconcile/resume | `pipeline/delivery_queue.py`, `pipeline/delivery_executor.py` | IMPLEMENTED |
| YouTube resumable upload + thumbnail + inspect | `providers/publishing/account_youtube.py` | IMPLEMENTED, no live upload yet |
| Publisher worker (Compose profile `publishing`) | `publishing_worker/main.py` | IMPLEMENTED, registers `youtube` only |
| Instagram | only account profile rows, caption length check, `_matches` stub | **NOT STARTED** |
| Scheduling at slots (`publishAt`, Instagram slot submit) | design doc §Scheduling | **NOT STARTED** |
| Day review → publish hand-off | `pipeline/publication_batch_export.py` (local staged export only) | NOT STARTED |

Known gaps in the YouTube path:
- The OAuth redirect must be `https://`, but the dashboard is loopback-only behind an SSH tunnel.
- `selfDeclaredMadeForKids` and `containsSyntheticMedia` are never sent. Without them YouTube falls
  back to channel defaults, and the altered-content disclosure would be missing.
- `categoryId` is hard-coded to `22`.
- There is no Shorts check (≤ 3 min, 9:16) and no quota accounting (an upload costs about 1,600 of
  10,000 units per day).

## 1. Operator: credentials only (one-time)

All values go in the project `.env` (git-ignored, read by Compose). Never paste them in chat or commit them.

**Shared**
- `TUBEFORGE_ACCOUNT_ENCRYPTION_KEY`: generate with
  `.venv-benchmark/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
  Back it up: losing it means reconnecting every account.

**YouTube (Google Cloud Console)**
1. Create a project and enable **YouTube Data API v3** (also YouTube Analytics API if you want stats later).
2. OAuth consent screen: External, Testing mode, and add your Google account as a test user.
   Scopes: `youtube.upload`, `youtube.readonly`.
3. Credentials → OAuth client ID → **Web application**. Authorized redirect URI:
   `http://127.0.0.1:62065/oauth/youtube/callback` (Google allows loopback http; see D1).
4. Put the values in `.env`: `TUBEFORGE_GOOGLE_OAUTH_CLIENT_ID`, `TUBEFORGE_GOOGLE_OAUTH_CLIENT_SECRET`,
   `TUBEFORGE_GOOGLE_OAUTH_REDIRECT_URI`.
5. **Submit the YouTube API Services audit form** (the "Audit and quota extension" form) when you
   set up the client. Google locks uploads from unaudited projects to **private**, and the audit
   takes weeks. Private uploads still work for phases P1–P3.

**Instagram (Meta for Developers)**
1. The Instagram account must be **Professional** (Business or Creator). A Facebook Page is not needed with Instagram Login.
2. Create an app (type Business) → add product **Instagram → API setup with Instagram login**.
3. Permissions: `instagram_business_basic`, `instagram_business_content_publish`. App stays in
   Development mode. Add your Instagram account under App roles → Instagram testers, and accept
   the invite in the Instagram app (Settings → Website permissions → Apps and websites).
4. Business login settings → redirect URI `https://localhost:62443/oauth/instagram/callback` (see D1).
5. Put the values in `.env`: `TUBEFORGE_INSTAGRAM_APP_ID`, `TUBEFORGE_INSTAGRAM_APP_SECRET`,
   `TUBEFORGE_INSTAGRAM_OAUTH_REDIRECT_URI`.

After that: `scripts/restart_stack.sh`, open Studio → Accounts → Connect, approve on the platform, and confirm the exact channel or account shown.

## 2. Decisions (recommendation first)

- **D1 OAuth callback over the SSH tunnel (resolved for Instagram by `scripts/local_tls_proxy.py`).** *Recommended:* accept `http://127.0.0.1`/`localhost`
  redirects for Google only (Google permits loopback). Meta requires https, so add an opt-in
  loopback TLS listener on the same port (self-signed `localhost` certificate, created by a script).
  The fallback for Instagram is to paste the long-lived token from the Meta dashboard ("Generate
  token") into a write-only form. Nothing is ever exposed publicly.
- **D2 Instagram video transfer.** *Recommended:* Graph API **resumable upload**
  (`upload_type=resumable` → `rupload.facebook.com`), which sends bytes from local disk. The design
  doc's "serve the asset over public HTTPS" option would expose a port. Not chosen.
- **D3 Default visibility.** YouTube `private` until the audit passes, then `publishAt` scheduled.
  Instagram has no private mode: every Instagram publish is public at once, so its submit always
  needs an explicit per-post confirmation.
- **D4 Autopublish.** Never by default. Approving in Day review marks a post *ready to schedule*.
  The operator still clicks Schedule (one click per day is fine). An opt-in "auto-schedule approved
  posts for plan X" stays off until P5 is VERIFIED.

## 3. Phases

One phase at a time. Each phase needs its acceptance evidence before the next one starts.

### P1: YouTube private upload works end to end. Owner: **Codex** (wrote the delivery core)
- Outcome: one approved Short is uploaded as **private** to the real channel from Studio, verified
  `processed`, with its thumbnail. Studio shows the remote link.
- Work:
  - D1 loopback redirect for Google.
  - Send `selfDeclaredMadeForKids=false` (configurable), `containsSyntheticMedia` from
    `disclosure_record.json`, and the category from config.
  - Shorts preflight: ≤ 180 s, 9:16, size limit.
  - Quota ledger (units per day, refuse before the cap).
  - Publisher worker readiness in `/api/publishing/status`.
  - Operator runbook in `docs/operations/platform-integrations.md`.
- Acceptance:
  - Unit tests with a fake httpx transport for every new field.
  - One real private upload. Its `videos.list` snapshot matches the reviewed title, description
    and privacy, and the remote frames are checked against the local final.
  - Signed-in Studio flow tested in Chromium.
- Out of scope: Instagram, scheduling, public visibility.

### P2: Instagram connect + Reels publish. Owner: **Claude**
**Status: IMPLEMENTED on `claude/publish-instagram` (HTTPS callback front added, D1 resolved); fake-transport and temp-stack browser tests pass; live check BLOCKED on operator the Meta credentials and a go-ahead for one real post. Review: `docs/instagram-publishing-review.md`.**
- Outcome: Studio connects the Instagram professional account and publishes one approved Reel
  through the same drafts → submit → delivery queue. Studio shows the permalink.
- Work:
  - `security/instagram_oauth.py`: Instagram Login, code → short-lived → long-lived (60 d) token,
    `/me` identity check.
  - `InstagramCredentialRefresher` (refresh when under 10 days remain).
  - `providers/publishing/account_instagram.py` implementing `DestinationAdapter`:
    - open session = REELS container with `upload_type=resumable`;
    - upload = rupload bytes, then poll `status_code`, then `media_publish`;
    - inspect = `/{media-id}?fields=permalink,caption,owner`;
    - `inspect_session` = container status.
  - Container 24 h lifetime and the 100 posts / 24 h limit (`content_publishing_limit`).
  - Worker registers `instagram`. API gates `submit`/`actions`/`status` become per-platform
    instead of YouTube-only.
  - Studio Connect button, the public-post confirmation (D3), and a caption/hashtag preview
    (2,200 chars, 30 hashtags).
- Acceptance:
  - Adapter tests on a fake transport, covering the publish-twice guard and unknown outcomes.
  - **Codex reviews** the adapter against the executor's lease and unknown-outcome invariants.
  - One real Reel publish after the operator confirms that exact post. The permalink is opened
    and the remote caption matches.
  - Studio tested at desktop, tablet and mobile widths.
- Out of scope: Facebook Reels, carousel or story posts, comments.

### P3: Cross-post from one review. Owners: **Claude** (UI) + **Codex** (backend)
- Outcome: in Day review / Publishing, one approved final makes one draft with both destinations,
  each with its own platform metadata (YouTube title + description + tags; Instagram caption +
  hashtags), all from `publication_suggest.py`. The operator reviews it once and submits once.
- Codex: draft creation from a day-review approval (checksum-bound, reusing
  `publication_batch_export` identity) and per-destination metadata defaults.
- Claude: Day review "Prepare post" action, destination chips and per-platform editors, and
  per-destination state chips (queued → uploading → processing → published / needs attention /
  reconnect).
- Acceptance: one real final posted to both platforms from one review. The Activity log shows both
  outcomes, and a forced failure on one destination leaves the other intact.

### P4: Scheduled publishing at slots. Owner: **Codex** (backend) + **Claude** (UI)
- Outcome: the operator schedules approved posts to the plan's slots (13:00 / 19:00 IST). Posts
  go out on time without the operator present.
- Codex:
  - `scheduled_for` on deliveries (migration).
  - YouTube: upload early as private with `status.publishAt` (needs the audit; until then, a
    clear "audit pending: private only" state).
  - Instagram: the worker starts the container at slot − 30 min and publishes at the slot.
  - Late policy: 30 min grace, then missed; never burst-publish after downtime.
  - Enforce the M-S7 cadence guard at schedule time (warn, operator overrides).
  - Pause and cancel pending.
- Claude: Publishing calendar (day/week), drag-free "Schedule to next free slot", and states for
  missed or paused posts.
- Acceptance: a frozen-clock test suite, plus one real scheduled private YouTube post and one real
  scheduled Instagram post landing within 2 min of their slots.

### P5: Operations hardening. Split
- **Claude:**
  - Alerts in Studio for `auth_required`, token expiring in under 10 days, quota near the cap, and
    missed slots.
  - Reconnect flow for both platforms.
  - Runbook and readme updates.
  - Remote snapshot verification shown with a "remote differs" warning.
- **Codex:**
  - Publisher worker added to `scripts/restart_stack.sh` / Compose default profile.
  - Backoff with provider hints (`Retry-After`, Instagram `x-app-usage`).
  - A 7-day dry run with a fake adapter at plan volume, checking no duplicate and no lost post.
- Acceptance:
  - 7-day soak (fake adapter) has 0 duplicates and 0 lost posts.
  - One real week of scheduled private YouTube posts and the operator's chosen Instagram posts.
  - The operator's sign-off makes publishing **VERIFIED**.

Later (not in this plan): YouTube/Instagram analytics ingestion into channel reports, Facebook Reels, public YouTube once the audit passes (only a config flip if P4 holds).

## 4. Relay order and hand-offs

1. Operator: section 1 credentials (any time; P1 can start with fakes before they exist).
2. Codex P1 ∥ Claude P2 (separate files; the only shared edit is the platform gate in `api/app.py`.
   Claude takes that edit and Codex reviews it).
3. P3 after P1 and P2 are VERIFIED. Then P4, then P5.
4. Each agent works on a sub-branch off `feature/publish-pipeline` (`codex/publish-youtube`,
   `claude/publish-instagram`) and merges back after review.
   `feature/publish-pipeline` → `dev` → `main` only with the operator's explicit approval each time.
5. Live calls: every real upload or publish in P1–P4 is a separate operator go-ahead for that exact
   post. Agents never publish publicly on their own (`AGENTS.md`: "publish anything to YouTube" is
   forbidden without it).

## 5. Risks

- YouTube audit not passed → no public or scheduled visibility. Private posts are still fine.
  Mitigation: submit the form on day 1.
- Meta app in Development mode works only for app-role accounts. That is enough for the operator's
  own account; publishing to other people's accounts would need App Review. Not planned.
- Instagram posts cannot be made private, so a wrong post is public at once. Mitigation: the
  explicit confirmation (D3), and P2's first real test uses a throwaway Professional account if the
  operator has one.
- Host load: uploads are I/O only and run in the separate publisher worker, under 768 MB.
