# TubeForge

TubeForge is a self-hosted, approval-gated video-production pipeline. It
creates durable generation jobs, produces narration/captions/media renders,
records review and publication checkpoints, and exposes a local Creator Studio
dashboard. It also supports a bounded source-clip workflow for turning an
operator-supplied public video URL into vertical clips.

TubeForge is safe by default: no credential is stored in configuration, YouTube
publishing is disabled/dry-run by default, and public publication requires an
explicit approval path. Live platform publishing requires operator-provided
OAuth applications and credentials.

## Current status

See the [current project plan and release status](design_doc/tubeforge-publishing-design.md#11-current-release-status-and-next-action)
for validation evidence, blockers, and next tasks. See
`AUTONOMOUS_PROGRESS.md` (local-only, gitignored; rotated per `AGENTS.md`) for the append-only work log.
The same project plan defines forward work and acceptance checks. Superseded plans,
reviews and the old dashboard prototype were removed on 25 Oct 2026 and remain in git history.

## Included capabilities

- SQLite/Alembic persistence with worker leases, ownership fencing, checkpoints,
  retries, cancellation, and atomic artifact promotion.
- Content-provider, media-provider, voice-provider, and publishing boundaries;
  deterministic/fake adapters support offline testing.
- Local FFmpeg rendering with paced four-direction camera motion, native
  portrait storyboard graphics or rights-safe public-domain/CC0 Wikimedia stock,
  configurable local narration, word-highlight captions, licensed/ducked
  background music, final-artifact quality
  checks, publication metadata/thumbnail preparation, and source clips.
- Dashboard authentication, audited approvals/activity, topic queue, schedules,
  encrypted social-account credential envelopes, and durable dispatch receipts.

Some capabilities are intentionally incomplete: live Meta publishing and
authenticated live YouTube smoke validation.
See the current project plan before relying on them.

## Local development

Use Python 3.12 or 3.13. From the repository root:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
python -m alembic upgrade head
python -m pytest
```

On Windows, activate with `.\.venv\Scripts\Activate.ps1` instead.

The default configuration in `config/default.yaml` is local, credential-free,
and uses SQLite. Select another configuration with `TUBEFORGE_CONFIG`.

## Local services

Run TubeForge as native processes from the repository root with the project
environment active. The production configuration keeps database, model,
artifact, and cache paths relative to this checkout. Start each process in its
own terminal after installing the Piper model and running migrations; set the
configuration variable in every terminal:

```bash
TUBEFORGE_CONFIG=config/production.yaml alembic upgrade head
TUBEFORGE_CONFIG=config/production.yaml python -m tubeforge.tts_server
TUBEFORGE_CONFIG=config/production.yaml uvicorn tubeforge.main:app --host 127.0.0.1 --port 62065
TUBEFORGE_CONFIG=config/production.yaml python -m tubeforge.workers.main
TUBEFORGE_CONFIG=config/production.yaml python -m tubeforge.scheduling.main
```

Keep the Piper endpoint private. Production authentication uses secure cookies,
so put the dashboard behind a trusted HTTPS proxy for remote access.

Compose is an optional reference deployment for the same services; it is not
required by the application runtime:

```bash
docker compose up --build
```

The services write generated files using your local user identity, so completed
generations can be safely removed from the dashboard. If your local UID/GID is
not `1000:1000`, export `TUBEFORGE_HOST_UID` and `TUBEFORGE_HOST_GID` before
starting Compose.

The sole documented developer dashboard URL is
[`http://127.0.0.1:62065`](http://127.0.0.1:62065). Compose binds it to
loopback only; do not use transient IDE/app-preview URLs or introduce another
host dashboard port. Before enabling production authentication, migrate the
database and create the first administrator:

For the repeatable homeserver boot, service check, SSH tunnel, and recovery
procedure, use the
[`TubeForge homeserver operator guide`](docs/operations/homeserver.md).

```bash
tubeforge create-admin --username <name>
```

Use a production-only `TUBEFORGE_ACCOUNT_ENCRYPTION_KEY` for any OAuth account
credential envelopes. Never commit credentials, OAuth tokens, or Piper models.

### Publishing account connection (Phase 1 in progress)

In **Publishing accounts**, add local YouTube, Instagram, Snapchat, or X/Twitter
profiles with a friendly account name (for example, Virtual World Master), a
category (for example, Tech), and a default video description. Multiple profiles
can share a platform or name. Edit these defaults for future videos; existing
video plans retain the account name, category, and description captured when
they were created. A local profile remains **unconfigured** until its exact
platform identity has been verified. Snapchat and X/Twitter have planning
profiles only; this setup adds no live connection or upload.

In **Create video**, use **Where this video should go** to select exact account
profiles. Enter an optional **Video description** to apply it to every selected
account; leave it blank to use each account's own default. The description is
saved even if no destination is selected. These choices are stored with the
generation and appear in **Compose manual post** when its final video is ready.
Scene revisions inherit the saved destination and description snapshot.
Connected YouTube/Instagram accounts with supported manual draft handling are
preselected with the saved description. Other planned accounts remain visible
with their current connection/support state. Review every destination's title,
description or caption before saving a separate publishing draft. Video
creation never starts an upload.

Creator Studio separates **Studio** (queue overview and creation),
**Generations** (saved jobs and review), **Scheduling** (account topic queues
and schedules), **Accounts** (local profiles and connections), **Media tools**
(source clipping and licensed music upload), and **Publishing** (drafts and
delivery activity).
On phones, open **Menu** to switch sections; Escape or the backdrop closes it.
The URL hash preserves the selected section when reloading. Background job
updates continue without replacing an open form or dialog.

Studio shows queued topics and actual job states across accounts. In Scheduling,
each account queue shows all its topics, saved schedules, the current job state
and latest recorded stage. **Open generation** leads to that job's saved record.
Generations labels each job's format, duration and planned platform accounts.
**Inputs & script** shows the saved brief, source links, description and
account snapshots, with copy buttons for inputs and available narration. A
Codex command appears only for runs whose exact arguments were recorded;
older runs say that the command was not recorded. The command's temporary
output paths are historical and are not replay actions.

In Accounts, **Set as default** saves one local account as the initial
destination selection for new videos. You can change the selection per video.
Edit an account profile to change its default video description; a custom
description on a video or schedule overrides it. Neither action changes an
already saved job or schedule.

In **Scheduling**, choose an account card first. Each account has its own topic
queue and generation schedules. Add one topic per line to that account; its
schedules take only its ready topics. Create a schedule under that same account
with a format, voice profile, duration, cron and timezone. Its optional video
description overrides the account default for generated jobs. Account identity,
category and effective description are saved with each job for later draft
review. Disabled accounts keep their existing topics and schedules visible but
block new work. Existing unassigned topics and schedules appear in a read-only
**Unassigned items** card and remain separate from account queues. Scheduling a
video never uploads it.

Creator Studio now lists publishing accounts and reports their stored state.
It enables **Connect YouTube** only when dashboard login, an encryption key,
and a Google OAuth web application are configured. The browser is redirected
to Google; after TubeForge discovers the authorized channel, the operator must
confirm its exact channel ID before the encrypted credential is saved. A
reconnection must discover the same channel ID. An account connection alone
does not enable an upload.

Creator Studio now offers **Compose manual post** for finished local videos and
verified destination accounts. Select and preview one video, check the exact account
identities, and enter a YouTube title and description or an Instagram caption
for each destination. **Save publishing draft** validates and copies the final
MP4 into content-addressed staging, then saves a separate metadata and account
snapshot for each destination. The draft list shows persisted states, the staged
video, exact account metadata, a bounded destination-attempt history, errors and
remote receipt when present. The history omits encrypted upload-session details.
Saving a draft does not upload or schedule a post. For a YouTube-only draft with
private visibility, review the staged video and every destination detail, check
the exact-review box, then choose **Submit private YouTube post**. This queues
the reviewed snapshot for the live publisher worker; it does not mean the
remote video has been published. **Refresh publishing activity** reads durable
per-destination results. Mixed-platform and Instagram drafts cannot yet be
submitted. A finished video can be drafted only
once per account in the default edition.

The publisher worker is an opt-in Compose service. With a stable
`TUBEFORGE_ACCOUNT_ENCRYPTION_KEY` available to Compose and migrations applied,
start it using `docker compose --profile publishing up -d publisher-worker`.
It supports YouTube deliveries only at present and will process any already
queued YouTube destinations. Studio shows whether a recent publisher heartbeat
exists; an online heartbeat is operational presence, not proof that an upload
or public post succeeded. The submit control is enabled only while the web
service has the encryption key and a YouTube-capable worker has a recent
heartbeat. Queued YouTube posts are private by default. An unknown remote
outcome remains blocked for reconciliation; TubeForge will not automatically
start a replacement upload. For a YouTube destination with an uncertain
outcome and a saved session, **Inspect saved remote session** queues a read-only
status check. If that check confirms an incomplete upload, **Continue saved
upload session** explicitly queues transmission of only the missing bytes to
the same session. Both actions show a pending state until the worker records a
durable result; a missing session or unresolved outcome never triggers a fresh
upload automatically.

After reconnecting the exact YouTube account, **Resume after account
reconnect** releases its blocked destination. A delivery with no remote session
returns to the pending queue; one with a remote ID returns to read-only
verification. A saved session without a remote ID stays uncertain and requires
the inspect action above. Other destinations retain their own results.

Supply these environment variables to the web process through a protected
local deployment secret source (the project `.env` path is ignored by Git):

- `TUBEFORGE_ACCOUNT_ENCRYPTION_KEY` — a stable Fernet key kept outside the
  database, with a separate recoverable backup.
- `TUBEFORGE_GOOGLE_OAUTH_CLIENT_ID` and
  `TUBEFORGE_GOOGLE_OAUTH_CLIENT_SECRET` — from a Google OAuth **Web
  application** whose YouTube Data API access is configured.
- `TUBEFORGE_GOOGLE_OAUTH_REDIRECT_URI` — the exact registered HTTPS URL ending
  in `/oauth/youtube/callback` on this Studio instance. The local loopback
  dashboard URL remains `http://127.0.0.1:62065`; it is not an HTTPS callback.

TubeForge requests YouTube upload and read-only scopes to identify the channel
and preserve offline access. Google may restrict uploads from an unverified API
project to private visibility; check the actual application's audit and consent
status before relying on public scheduling. The account API rejects direct
browser-supplied OAuth tokens and remote account IDs. Existing accounts created
through that older path without remote validation appear as **verification
required** until reconnected. Instagram connection is not yet available, so
Instagram draft selection is not yet an operator-ready flow.

### Create a dashboard login account

From the repository root with the project environment active, create the first
administrator against the configured local database:

```bash
TUBEFORGE_CONFIG=config/production.yaml tubeforge create-admin --username operator
```

For the optional Compose reference deployment, use
`docker compose exec web tubeforge create-admin --username operator`.

Replace `operator` with your preferred username (3–100 characters). Enter a
password of at least 12 characters at the hidden prompt. Then sign in to
Creator Studio using that username and password. This dashboard account is
separate from the dedicated Codex service account and its ChatGPT login.

The command creates an account; it does not reset an existing password. If it
reports `administrator already exists`, use the existing credentials or choose
a different username to create another administrator. Accounts persist in the
configured database across service restarts. Do not put passwords in documentation or
pass them on the command line.

### Private remote access with Tailscale

When TubeForge runs on a Debian home server, keep its dashboard listener bound
to loopback and use Tailscale Serve for remote access from devices in the same
Tailnet. This does not open a LAN or public dashboard port. Run the following on the Debian
server, from the repository root, after installing and signing in to
Tailscale:

```bash
sudo systemctl enable --now tailscaled
sudo tailscale up
sudo tailscale serve --https=443 http://127.0.0.1:62065
tailscale serve status
```

Open the HTTPS URL reported by `tailscale serve status` on a Tailnet-enrolled
device. The production configuration enables dashboard login and secure
cookies, so do not replace this with an insecure HTTP proxy. Verify the
deployment before use with `curl -fsS http://127.0.0.1:62065/healthz` on the
server; it must return `{"status":"ok","database":"ok"}`. If no
administrator exists yet, create one interactively with
`TUBEFORGE_CONFIG=config/production.yaml tubeforge create-admin --username <name>`.

## Local narrator voices

Production uses the configured Piper voice through a private local HTTP
service. The service loads the ONNX model once; the worker sends phrase text,
then validates and caches the returned WAV against the configured voice and
model hashes. This avoids starting a Piper process for every phrase and uses
no hosted speech API. Kokoro remains an optional local provider when explicitly
selected in configuration.

Choose a voice in **New generation** and use **Preview voice** to hear the
same local provider before creating a job. The first request stores a stable
WAV under `data/artifacts/voice-previews/`; later clicks reuse that exact local
file without synthesizing again. A preview reports an error when its
model/runtime is not available; it does not contact a hosted text-to-speech
service.

The Piper service needs the matching `en_US-lessac-medium.onnx` model and
`en_US-lessac-medium.onnx.json` sidecar configured in `config/production.yaml`.
Model files are operator-supplied and ignored by Git. `pipeline.piper.server_url`
defaults to loopback; set `TUBEFORGE_PIPER_SERVER_URL` to the private address
used by a deployment. The synthesis service binds to `127.0.0.1:5000` by
default. The optional Compose reference overrides its bind to the private
project network and publishes no host port. Keep the unauthenticated synthesis
endpoint on a trusted private network and never expose it publicly.

## Source-grounded writer

This production pipeline uses **Codex** for creative decisions. A local LLM is
not an approved production script provider and must not be used for generation,
automatic retries, or quality acceptance unless the operator explicitly
approves it for that specific run. Production script generation uses the
restricted host-side Codex runner over `/run/tubeforge-codex/codex.sock`; it
uses only the dedicated `tubeforge-codex` account and its private `CODEX_HOME`.
Source excerpts and brief fields are treated as data. Known role-spoofing or
instruction-override text is rejected before reserving a Codex attempt; the
job shows a validation failure in Studio so the source can be corrected.
It invokes only the root-owned pinned `@openai/codex@0.149.0` runtime at
`/opt/tubeforge-codex-runner/codex-runtime`; it never uses the operator's NVM
tree or Codex authentication. Ollama is not configured or
wired into the production Compose workflow.
The fixed script model is `gpt-5.6-sol` with no automatic model fallback. Each
exact source packet permits at most two host-side CLI launches, each bounded
to eight minutes; failed launches count. Usage draws from the dedicated
ChatGPT sign-in's plan allowance or credits, not an API key.
At the 2026-09-28 operator check, the dedicated account offered
`gpt-5.6-sol` but not `gpt-6-sol`. The 2026-10-11 installed host runner produced a new, reviewed skill-enabled
`gpt-5.6-sol` script; generation and source/tool provenance are verified.
Finished-video quality remains subject to the Shorts acceptance checks. Do not reset an exhausted source packet or
silently substitute a new one.

In **New generation**, **Approved source notes** are the minimum durable source
packet. An optional source URL must include its title and an exact operator-
approved excerpt; TubeForge does not silently scrape that page. During script
review, Creator Studio shows the exact saved sources above the narration. The
writer must use only those excerpts, and typed claims retain their source IDs
and human-review flags.

New Generation also accepts a separate **Creative angle** and **Audience**.
For a reviewed multi-source brief, open **Use multiple approved sources** and
paste an ordered JSON array of one to eight objects containing unique
`source_id`, `title`, `url`, and exact `excerpt` fields. With that packet,
**Brief notes** are writing direction and are not converted into an extra
source; leave the legacy single-source URL/title/excerpt fields blank. The
ordered source IDs and exact excerpts are part of the request identity, so
editing either creates a different generation request. Captured timestamps and
excerpt hashes are retained in the source-packet checkpoint for provenance but
do not change the v7 generation key for identical source text.

With `pipeline.sources.research_enabled: true` (production configuration), a v7
brief containing only notes first uses the host Codex runner's `ResearchSourcesV1`
operation. You supply the topic and angle; Codex checks the premise with live web
search and selects two or three primary pages. Local Python fetches public HTTPS
text (no private hosts or redirects), keeps at most 5,000 characters per page,
across a 10,000-character total packet budget, and saves URLs, retrieval times and content hashes. Pages with fewer than 200 readable characters are excluded with a recorded reason; at least two distinct substantive pages must remain. Brief notes are hypotheses,
not factual evidence; narration must qualify unsupported claims. Explicit source
packets keep their existing exact-source behavior and are not silently replaced.

Research uses the existing Codex model with one invocation per exact brief,
an eight-minute limit and a prompt budget of at most six searches. Search count
is recorded, not enforced as a tool-call quota. Successful research results are
cached under the host runner's `research-cache/`; the worker saves `source_research`
and `source_packet` checkpoints and shows research start/completion in Activity.
This adds one model call before writing, not model-driven media execution.
Fetch failure blocks before narration; restarting reuses the saved research result.
The existing two-attempt script allowance still applies to the researched packet.
The host runner wheel must be updated with the worker; an older host fails
preflight before a research invocation. Existing approved/failed jobs are not
rewritten or automatically requeued by enabling research.

For new `m6-content-v7` jobs, TubeForge captures each approved excerpt with its
source ID, capture time and SHA-256 of the exact text before the writer runs.
The packet and effective request are saved as checkpoints, so retries use the
same evidence even if channel configuration changes. When no supplied excerpt
exists, `pipeline.sources.channel_approved` may provide per-channel source
references with approved excerpts in local configuration. With neither, the
job is blocked for insufficient sources before a model or TTS call. Optional
allowlisted HTTPS retrieval remains disabled by default; it is a separate
fallback for references without excerpts. For supplied-source jobs, broad web discovery is not used; notes-only research is the separate bounded path above.
Existing jobs keep their saved source packets and approvals.

Creator Studio uses the configured Codex content prompt version for new jobs.
For envelope-based generation, Codex returns creative content without echoing
the input request. Python attaches the exact trusted request before validating
claims and source references. Conflicting legacy request echoes are rejected.
This reduces output tokens and prevents copied-source drift; it does not change
source evidence, acceptance gates, or the two-attempt allowance.

Structured generation constrains scene layouts and their compatible reveal cues for
both widescreen and Shorts. Descriptive visual direction belongs in composition,
not the renderer layout ID; unused motion cues must be null.
Generation prompts state the same narration word limits checked on output.
A 60-second widescreen script requires 90–240 narration words, with a writing
target of about 162. Prompt changes must be deployed to the host runner, not
only to Docker: from the repository root run
`sudo /opt/tubeforge-codex-runner/venv/bin/pip install --force-reinstall --no-deps .`
and then `sudo systemctl restart tubeforge-codex-runner.service`.
TubeForge validates that prompt locally before counting an invocation. The
two-attempt limit for an exact source packet is TubeForge's safety rule, not a
Codex account quota. A previously failed job keeps its recorded failure;
after a configuration correction, create a new job with a reviewed source
packet rather than assuming the old job resumed.

For Shorts, script validation requires a concise opening hook, complete
sentence endings, duration-calibrated word count, and a concrete final call to
action. Invalid output is never checkpointed. Any retry must follow the
delivery guardrails in `AGENTS.md`; manual Shorts revisions must pass the same
structural quality checks and always require approval of the new exact artifact.
Any Codex CLI or Claude integration must retain these source, structure, and
approval requirements.

## Visual sources

Each video in Creator Studio has a **Visuals** choice:

- **Generate local scene art** creates one durable, scene-specific image for
  each approved scene. The storyboard retains a subject, purpose, composition,
  display text and explanatory visual elements next to narration. FFmpeg draws
  terminal, package, branch, comparison or sequence layouts from those reviewed
  fields at 1080×1920 for Shorts. Terminal scenes display the approved command
  and concise output in a dedicated terminal pane; longer approved commands
  wrap to two lines, while content that still cannot fit fails for revision.
  Explicit scene layout IDs currently
  support `terminal`, `flow_diagram`, `comparison`, `timeline` and `source_card`.
  These are reusable layouts filled from each job's scene plan; no video script
  is stored in the renderer. Explicit-layout packages require all scenes to use
  supported IDs and are bound to the exact script gate and source packet.
  When an accepted scene plan includes spoken-word reveal cues, the local
  renderer can reveal hook/close choices, terminal actions, flow branches,
  comparisons, timelines and source details during the matching narration.
  Comparison scenes can show both side panels before their consequence bar;
  that order is part of the approved scene data and render identity. Scenes
  without cues retain their earlier rendering path. Captured test packages
  prove these layouts; automatic production writing of the cues remains a
  separate acceptance stage in the [project plan](design_doc/tubeforge-publishing-design.md).
  A closing scene without a factual claim may have no source citation. A complete asset-stage manifest and contact
  sheet record scene order, hashes and rights information. Existing approved
  scripts without the new fields use search terms as fallback labels and need
  visual review. FFmpeg adds paced camera moves and crisp cuts.
  Deploy the updated host wheel and rebuild the web/worker image before using
  these new fields in production.
- **Rights-safe stock (Wikimedia Commons)** searches only Wikimedia Commons and
  accepts only public-domain or CC0 candidates that satisfy the asset policy.
  If the search is unavailable or none qualify, the hybrid provider falls back
  explicitly to local generated CC0 scene graphics so the job can render without
  weakening the licence policy. The asset manifest preserves the requested
  stock source, the resolved local source, and the reason for the fallback.

Creator Studio displays generation and activity timestamps in India Standard
Time (IST), regardless of the browser's own timezone.

Open a job's **Activity** view to see recorded stage durations and download its
diagnostic JSONL. The signed-in API also exposes `/api/jobs/{job_id}/diagnostics`
and `/api/jobs/{job_id}/diagnostics.jsonl`. Measurements begin with jobs run by
the updated worker; older jobs may show no measured stages. The reported
`memory.peak` includes page cache and spans the container's lifetime, so its
stage readings are attribution snapshots rather than isolated per-job peaks.
Performance targets are currently advisory. The diagnostic retains retry count
and the job's current failure reason without treating a scheduled retry as a
completed stage.

TubeForge does not scrape or reuse Google Image results. Google is a search
engine, not a licence/provenance provider, so its results cannot safely pass
the pipeline's reuse checks. Every selected visual is checksummed, retained in
the job's asset manifest, and revalidated before rendering or resuming.

For Shorts, the visual gate rejects non-portrait or undersized stock, unsupported
graphics versions or mixed palettes, missing palette identity, repeated scene bytes, repetitive
camera motion, visual holds over three seconds, and captions outside the
configured safe area. Landscape stock which cannot meet the portrait source
floor falls back to the local storyboard graphics provider before it can be used.
Saved scenes may use different supported graphics versions when they share one
palette; the quality report lists the versions used.

## Licensed background music

Creator Studio exposes **Background music** and **Add licensed music**. An
upload requires the source URL, the actual licence name and terms URL, whether
credit is required, the exact credit line, and an explicit confirmation that
the terms permit the intended YouTube publishing use. Generic labels such as
“free” or “royalty-free” are rejected because they are not licences.

Uploaded audio is decoded locally before it enters the catalog, checksummed,
and stored under `data/music/` with an atomic `catalog.json` rights record.
This directory is machine-local and ignored by Git. The worker resolves the
approved record again before every preview/final render. FFmpeg places the bed
at 16% level, side-chain ducks it under speech, limits the combined output, and
records the exact track checksum and licence in the render manifest. Required
attribution is appended to publication metadata before approval.

Production Shorts preview and final set `audio_normalization_enabled` on. The
renderer analyzes the narration or approved music mix, applies a measured
second-pass normalization targeting −13.5 LUFS / −2.5 dBTP plus a limiter to both preview and final, then checks the encoded
AAC against −15 to −13 LUFS and a true peak no higher than −1.0 dBTP before
promoting the artifact. The pre/post measurements and processing version are
stored in the preview/final manifest. A real local-Piper fixture smoke passed
at −14.74 LUFS, −2.14 dBTP and 48 kHz after the encoded-AAC gate. Full
production-job listening, independent caption timing and live-job validation
remain pending.
An isolated CC0 music acceptance fixture and its source/rights record are kept
under `tests/fixtures/production/music/`; the downloaded audio stays in ignored
`data/` and is never bundled into the application image.

## YouTube Shorts workflow

Choose **YouTube Short (9:16)** in **New generation** to use the dedicated
portrait workflow. The preset accepts a 30–120-second writing target and defaults to 45 seconds. For portrait jobs, the measured narration and final video must be 30–120 seconds; a difference from the requested target is recorded rather than rejected.
It preserves the existing widescreen preset rather than changing its behavior.

Shorts previews are rendered at 540×960. Approved finals are rendered at
1080×1920, 30 fps with H.264 video and AAC audio. The production profile uses
the original local waveform aligner to place approved words within each
generated WAV; those word positions are estimates, and an independent encoded
audio audit found they do not yet meet the planned timing target. The experimental
`whisper-base-en-dtw-v1` provider requires a locally pinned English model and
the optional `alignment` package; it aligns the approved transcript to actual
speech and blocks collapsed or ambiguous boundaries. It is not installed or
enabled in the production image while its one-scene gate is unverified. The
experimental provider records each full alignment execution against the exact
script, narration and model identity. Decode timeouts and transient model
execution faults enter the worker's lease-free retry queue with 30/60/120-second
backoff. If the approved tokens match but the primary alignment collapses a
word to zero duration, one predefined `normalized-overlap-v1` configuration
is immediately eligible on the same script/audio/model. It normalizes Unicode
apostrophes in the alignment prompt and extends measured clause windows by
0.35 seconds; the approved display words never change. At most three executions
per configuration and four overall are recorded. The immediate switch does not
advance the transient-failure backoff count: its first later recoverable fault
waits 30 seconds. This special schedule applies only during voice alignment.
Invalid audio, missing model
files, token ambiguity and a failed alternate block without estimated-timing
substitution. Studio shows scheduled retries with the next attempt time;
exhausted attempts remain failed and cannot produce an approved final. This
alternate mapped one isolated accepted Git phrase, but the optional provider
remains disabled until independent word timing and a full-job gate pass. The
final quality gate checks structural alignment against the assembled
audio, rejects a first word after three seconds, rejects visual holds over
three seconds, and validates portrait caption margins and line widths.

Shorts use large uppercase ASS captions near the lower-middle safe area,
anchored at x=490 with a 470 px bottom margin to clear the action rail and
bottom controls. The currently spoken word is yellow and surrounding words remain white. Scene
holds are deterministically divided into shorter camera moves, so a long
narration scene does not become one static shot. Source-grounded production
writing, the fixed portrait visual system, and licensed music decisions are
recorded in
[`docs/SHORTS_WORKFLOW.md`](docs/SHORTS_WORKFLOW.md).

## Script owner and the reference Shorts path

**Script writer.** Each video job records which AI writes its script. Creator Studio's
*New video* form has a **Script writer (AI model)** selector: *Claude Sonnet 5.5 · medium effort*
(default), *Claude Opus 5.5 · high effort*, or *Codex · gpt-5.6-sol*. The API field is
`script_model` (`sonnet-medium` | `opus` | `gpt-sol`) on `POST /api/videos`. Reference Shorts also
reject weak hooks (yt-script hook score below 58) and scenes whose text will not fit the phone layout;
Claude repairs such rejections once within its two-attempt limit. Codex runs through
the root-owned host runner (`docs/deploy/codex-runner-runtime.md`). Claude runs
through a user-level runner that uses the installed Claude Code CLI with **no tools**
(research alone gets web search):

```bash
scripts/run_claude_runner.sh          # foreground; or the systemd --user unit in docs/
```

The runner listens on `data/run/claude/claude.sock` (visible to the worker as
`/app/data/run/claude/claude.sock`) and is enabled by `pipeline.claude.enabled` in the
config. It uses the same prompt, schema, validation and two-attempt limit as Codex, and
repairs a failed domain validation once (each call counts against the limit). The CLI
binary is resolved from `TUBEFORGE_CLAUDE_BIN`, `PATH`, or the VS Code extension.

**Reference Shorts** (`reference-short` preset, prompt `m6-content-v8`): 9:16,
6–20 scenes (scaled to length), about 2.5–2.85 narration words per target second (measured speech rate ~2.9 words/s), 30–90 seconds (default 60, 25–90 enforced by the renderer). The writer returns only semantic scene
JSON (template, text, optional `icon` from a fixed set, reveal anchors). The shared
`rendering/shorts` library owns all geometry, Kokoro speech + Whisper forced alignment,
motion (entrances, count-ups, scene transitions, push-in, moving background), audio
mastering (−14 LUFS, ≤−2.5 dBTP) and QA. The preview is a 720×1280 draft; the final is
1080×1920. The worker needs ≥2 GB RAM (`compose.yaml`) and the image extras
`alignment` and `reference-renderer` (rebuild after pulling: `docker compose build`).

`pipeline.reference_short.renderer` accepts `pil` (default) or `hyperframes`.
The HyperFrames route is an opt-in **PROTOTYPE** that renders one clip per scene,
joins them at 30 fps, and muxes the same mastered audio through the existing QA
gate. It needs a HyperFrames CLI on `PATH` or `TUBEFORGE_HYPERFRAMES_BIN`, plus
Node and Chromium in the worker image; the current `Dockerfile` has Chromium but
not Node/HyperFrames. The reviewed 720×1280 preview and exact worker-image
proposal are in `docs/video-quality/av-quality-implementation-log.md` §Phase 4.
The HyperFrames builders currently omit PIL's stock/source/code plates and
display options, and `terminal` has only a SYNTHETIC fixture. Keep `pil` for
production until the operator reviews the full preview and these gaps are resolved.

For a local speech-quality trial, `pipeline.reference_short` accepts
`spoken_profile: spoken-v1`, a `pronunciation_lexicon` mapping one displayed
token to one or more spoken words, `speech_group_size: 2`, and
`voice_processing: gentle-v1`. All default to the original per-scene path with
no spoken expansion or voice processing. The trial preserves reviewed narration
and captions; `voice-manifest.json` records spoken text, applied substitutions,
word mappings, profile identity and raw/processed voice hashes. Re-render and
listen to the complete video after changing these settings. Inspect caption
timing, scene seams, pronunciation and music balance before accepting it.

## Shorts production standard

TubeForge’s Shorts workflow accepts a complete 30–120 second video exported at
1080×1920 (9:16). Production scripts use Codex CLI or Claude. Local LLMs are
not production script providers unless the operator approves one for a
specific run.

The production Shorts final profile uses H.264 CRF 18. Memory-bounded renders
encode temporary scene clips at CRF 14 before the captioned final pass, reducing
compression of small text across the two encodes. `video_crf` is configurable
per render profile; lower values increase quality and file size. Shorts finals
require at least 84 px word-highlight captions, matching the phone-first
minimum in `docs/SHORT_FORM_VIDEO_RULEBOOK.md`; invalid smaller overrides fail
configuration validation. Final AAC is encoded and verified at 48 kHz. Preview
and long-form caption sizing remain separate.

A Short is ready for review only after a real video has been rendered and
manually inspected for:

- a source-grounded, non-repetitive script with a strong opening and clear
  viewer-directed ending;
- readable, correctly timed captions and varied vertical visuals;
- intelligible narration with appropriately mixed music;
- documented music licensing and any required attribution; and
- a working signed-in dashboard workflow.

Passing automated tests or producing schema-valid script data does not
establish creative quality. Retain the rendered video and a concise pass/fail
report with concrete evidence.
Portrait highlighted captions preserve punctuation in technical tokens such as
`--name`, `-d` and `nginx:alpine`, stay within their narration phrase, and wrap
within the configured safe-area line width. The first corrected Docker example
and its unresolved final-render gate were recorded in the former
`docs/TASK4_VIDEO_REVIEW.md` (git history).

## Application logs

All services write rotating, redacted JSON-lines logs to `data/logs/<service>.log` (rolled to `<service>.1.log`, `.2.log`… at 10 MB, deleted after 5 days; git-ignored). Details, fields and OpsDetective hook-up: [docs/operations/logging.md](docs/operations/logging.md).

## Creator Studio UI contract

For newly rendered reference Shorts, Generations → Generation record shows
timestamped audio signal warnings for the narration and the encoded preview or
final. Open the full audio report there for scene numbers, time ranges, artifact
hashes and whether the warning list was capped. Silence, clipping and level
changes are advisory checks; listen to the whole video before approving it.
Older and widescreen generations may have no audio report.

Dashboard/API changes ship together. Any operator-visible workflow must have a
working control, accurate pending/success/failure feedback, silent background
refresh after initial load, and responsive dark-theme behavior. Reviews,
revisions, deletion, rendering, and publishing must show durable backend state
rather than optimistic completion. The complete contributor requirements are
in `AGENTS.md`.

## Validation expectations

Run the relevant unit tests after every change. Before declaring a release
ready, run the full test suite, migrations, Compose configuration check, and an
appropriate FFmpeg/Piper smoke test; inspect the produced artifact with
`ffprobe`. The complete rules are in `AGENTS.md`.

## Repository hygiene

Before committing, review `git status --short` and update `.gitignore` if the
work created new generated artifacts, local data, caches, model files, logs,
credentials, or editor/OS files. Verify a new rule with
`git check-ignore -v <path>` where practical. Do not add broad rules that hide
source code, migrations, fixtures, or intentionally versioned configuration.

## YouTube content skills

The eleven canonical YouTube content skills live once under `.agents/skills/`:
yt-script, yt-package, yt-seo, yt-shorts, yt-plan, yt-chapters, yt-edit,
yt-retention, yt-viral, yt-audit and yt-comment. Read a skill before invoking it in Codex (for example,
`$yt-script` or `$yt-package`). Supporting scripts resolve their own resources
against their folder; application code does the same, independently of its
working directory. Python 3.12/3.13 runs the standard-library scoring tools:

```bash
python3 .agents/skills/yt-script/hookscore.py --json --hook "Your supplied hook"
python3 .agents/skills/yt-package/title.py --json --title "Your title" --thumb "CHECK FIRST"
```

### Connected writing skills

The canonical script skill is `.agents/skills/yt-script/` only. Its `SKILL.md`
references `automation.md`; hook formulas and `hookscore.py` are preserved.
Downloaded repository copies are not edited or consulted by the runtime.
Writing rules live in this skill, while the application enforces schema,
source-failure separation, ordered narration, and exact-artifact approval.

New v6 calls return a structured result with either `status: ready`, a
ContentPackage and null reason, or `status: insufficient_sources`, null package
and a concrete reason. Insufficient sources are blocked in `failed_validation`
and shown as “Blocked: insufficient sources”; no script, TTS or automatic retry
is created. Missing approved excerpts fail before a model call. Malformed JSON,
missing fields and production panels inside narration fail validation; raw Codex
replies are never used as speech. Only ordered `script_sections[].narration`
feeds TTS. v6 rejects malformed packages without model repair calls.

For an unclaimed `failed_validation` job paused at asset acquisition or initial preview rendering (before any preview exists), or a ready preview with no preview approval,
Studio may show **Retry approved media stages** only when the exact script approval
still matches and the saved content/source checkpoints pass their hashes and the
current scene-contract validator. The action requires the signed-in dashboard
session and CSRF token, records an audit event, and resumes from asset acquisition;
it does not regenerate narration or change the approval. Other validation
failures, missing/corrupt checkpoints, and stale approvals remain failed and
require correction before a new job or retry can proceed.

During script review, “Copy Codex prompt” prepares an explicit skill-loaded
revision brief with the exact current package, full source context, format and
voice. This prepares a prompt for an operator's external Codex session; it does
not claim to have run Codex or saved a revision. Review the returned narration
array, enter each section, save the revision, then approve its new exact identity.
Unsupported revisions must be rejected rather than pasted into narration.

The Studio's “Revise one scene” action opens the saved storyboard and that
scene's narration, visual layout and direction. The layout selector supports
flow diagrams, comparisons, timelines, source cards and terminal scenes;
compatible word-anchored reveal cues stay attached to the revised layout.
Saving creates a separate job paused at script review; the original video and
its approvals remain unchanged. Review and approve the child's exact script
before its worker rebuild, then inspect and approve its new preview. Unchanged
accepted scene assets and phrase audio are reused only after their hashes and
request identities are revalidated.
The generation record also shows audio and video signal diagnostics from the
durable render QA artifact. Video diagnostics identify sustained black intervals
and possible frozen intervals by time and scene; a static card can be intentional.
The final render fails on sustained black output before artifact promotion.
When a reference Short requests stock, eligible local Pixabay assets are ranked
by visual-query tag coverage and prior-shot variety. Its plate manifest retains
the chosen asset's source, license and ranking explanation for visual review;
metadata matching alone does not establish that the footage illustrates a claim.
This scene-revision flow is currently **IMPLEMENTED**; its real production
artifact acceptance is tracked in the current project plan.

Every submitted generation/repair prompt records its SHA256, resource hashes,
automation mode and skill identifier in invocation provenance. Deploy the rebuilt
wheel to the dedicated host runner after any canonical skill change; the worker
refuses a resource mismatch before generating. Changing prompt versions does
not authorize resetting or reusing exhausted source packets.


The configured `m6-content-v7` path embeds the canonical **yt-script** skill,
**om-short-production**, **om-storyboard**, **yt-package** and its title
checker, and **yt-seo** in each Codex prompt. Python validates the selected
Codex hook and reports heuristic hook scores; it never rewrites narration.
For vertical Shorts, the prompt requires a sharp opening, six ordered scenes,
an exact hook shown on frame one, word-anchored visual reveals, display-ready
labels, and a final CTA whose exact words appear in narration and the closing
scene. Python
compiles the bounded JSON scene contract into the existing animated graphics,
caption, audio and render stages. **om-video-quality** remains the required
post-render inspection standard; production readiness is not claimed until a
real final video passes it. These resources are
included in the deployment wheel under `tubeforge/content_skills/`. The isolated
host account receives instructions through the fixed prompt; it needs neither
this checkout nor the developer's home or interactive skill discovery. Compose
also mounts the canonical skills read-only for worker/web source deployments.
The fixed Codex CLI provider, model, source grounding, two-invocation limit,
eight-minute timeout, review gates and publishing policies remain in effect.
Older prompt versions and their resource hashes remain readable for existing
jobs. A prompt version change does not authorize reusing exhausted source
packets. Incomplete scene contracts fail validation before asset acquisition.

- **yt-script:** five hook candidates, Codex-selected spoken hook, narration,
  scene visual directions and on-screen text. Python runs the hook scorer as a
  review signal without replacing Codex's selected hook or narration.
- **yt-package:** ten coordinated title options, thumbnail text of at most
  three words, visual brief and accessibility description. Application Python
  executes the title checker for every title against the selected thumbnail.
  The script-review dialog shows the top three title checks against the first
  thumbnail text option, with the remaining checks available in an expandable
  list. It also shows all hook scores, marks the selected opening, and states
  that no title/thumbnail pair has been selected. The model's first title
  remains the proposed publication title; these warnings are review signals,
  not performance predictions or approvals.
- **yt-seo:** a search-facing description, appropriate hashtags in that
  description and at most fifteen relevant tags. It cannot invent resource
  links or chapter timestamps. Chapters retain the application's supported
  section-based schema.

Scores are heuristic review signals, not predictions of views. Tool failures,
missing resources and malformed content fail explicitly before downstream
processing. The worker checks local resources and a no-model host preflight
before reserving/counting a new v5/v6 invocation. The host must report identical
resource hashes. Local/preflight failures do not spend an invocation; actual
failed CLI launches retain the existing counting policy. Accepted results
retain resource hashes, executed-tool reports, selection and usage in the
cache and the job's `content_generation_evidence` checkpoint. Revisions require
fresh exact-script approval; the review endpoint recalculates checks on current
bytes and reports stale/invalid hook checks rather than claiming success.

### Channel voice configuration

Profiles are project-managed, non-secret application configuration in
`config/production.yaml` (or the file selected by `TUBEFORGE_CONFIG`):

```yaml
pipeline:
  codex:
    prompt_template_version: m6-content-v7
    default_channel_identity: engineering
    voice_profiles:
      default: "Clear, practical and conversational; no hype or invented experience."
      engineering: "Speak to working engineers. Explain tradeoffs with concrete supplied examples. Avoid sales language."
      cooking: "Use warm, direct kitchen instructions. Explain unfamiliar terms. Never invent recipe results."
```

A missing identity-specific profile uses the configured `default` profile, or
TubeForge's built-in clear, practical, conversational default. It never pauses
an unattended job for conversational setup. Identity and resolved voice text
are saved in the immutable request, keeping channels and cache entries separate.
This is writing voice; the existing **Voice** selector still controls local TTS.
Channel identities do not connect OAuth accounts or authorize publication.

In Creator Studio, select **Channel voice profile**, format and duration,
enter approved source notes (and an exact excerpt for an optional source URL),
and create a generation. Shorts remain 9:16, 30–120 seconds, with an immediate
hook and concise payoff. Widescreen jobs retain their requested long-form
format/duration. **Review script and sources** shows narration, scenes, title
and thumbnail options, metadata and real hook/title reports. Inspect grounding
and creative quality, then use the existing exact-script approval controls.
Review the preview before approving final rendering. Publication remains a
separate approval and configured integration.

New Studio schedules save the channel/format/duration selected above their
controls. Scheduled review policy remains unchanged. API schedules/topics may
set `options.channel_identity`, `aspect_ratio`, `preset_name` and
`duration_seconds`; topic options override schedule options. The scheduler uses
the configured supported prompt version, not the obsolete `topic-queue-v1`.
Invalid scheduled briefs are recorded as `invalid_request` without reserving a
topic or invoking Codex. Simple bulk-topic titles alone are not a verified
factual source packet: supply substantive approved notes before production use.

### Deployment and verified limits

**IMPLEMENTED:** production integration, score-based selection, channel
profiles, scheduler propagation and dashboard review. Focused offline tests and
installed-wheel resource checks pass. A real Codex package and actual signed-in
Chromium script review are **VERIFIED**. Preview rendering is **VERIFIED** for
the earlier 40.663s 540×960 artifact, whose visual checks and operator
narration review passed. Its former single-graph 1080×1920 export hit the
1 GiB worker memory limit. The operator later authorized bounded-memory
rendering. Production job `9df50ade54724d3ba7dd9e96e6521e88` passed signed-in
script and exact-preview approval, then registered a 43.033s 1080×1920 final
under the unchanged 1 GiB limit. Its manifest binds the approved preview and
accepted script/audio/captions/assets; visual, caption and technical checks are
recorded in the former `docs/TASK4_VIDEO_REVIEW.md` (git history). The full
Shorts workflow is **VERIFIED** for this finished local Short: the operator
watched and listened to the complete final and reported good voice, pacing,
captions and visuals with no defect. The job is at publication approval; no
publication approval was given.
Rejected host drafts are retained in generation-cache failure evidence without
being accepted or granting another invocation. FFmpeg input decoders, filters
and encoder all respect the configured thread limit to bound render memory.

After reviewing the changes, an administrator must install the built wheel
and restart the runner from the repository root:

```bash
sudo /opt/tubeforge-codex-runner/venv/bin/pip install --force-reinstall --no-deps artifacts/wheels/tubeforge-0.1.0-py3-none-any.whl
sudo systemctl restart tubeforge-codex-runner.service
```

The wheel must include `tubeforge/content_skills/`; an editable source install
is unsuitable for the protected host account. Recreate the application services
with `docker compose up -d --build web worker scheduler` after the host is ready.
The only documented local dashboard is http://127.0.0.1:62065. No verification
upload is authorized by installing this integration.

**Installed only:** yt-shorts (supplied long-form repurposing), yt-plan
(calendars), yt-chapters (appropriate transcripts), yt-edit (timestamped edit
recommendations), yt-retention (real retention exports), yt-viral (real public
channel listings), yt-audit (actual channel/video data), and yt-comment
(supplied comments). They are available to developers but do not automatically
run on every application job. Analytics retrieval, trend/source research,
transcription, rendering, narration and live publishing require their own
application dependencies, supplied data and authorization. Skills provide
content instructions and supporting tools, not those integrations.

See [current project status](design_doc/tubeforge-publishing-design.md#11-current-release-status-and-next-action) for acceptance evidence and next actions.

## Repository layout and local artifacts

For a read-only inventory before any artifact-retention change, run
`PYTHONPATH=src python3 -m tubeforge.pipeline.retention_inventory` from the
repository root. It reports local artifact/cache sizes and protects all
pre-existing files; `cleanup_candidates` is zero until managed retention and
ownership checks are implemented. Host cgroup memory may be unavailable.
Inside the worker, the reported `memory.peak` covers the container's lifetime,
not an individual video.

Project content skills and their referenced tools live in `.agents/skills/`
and are versioned with the application. See [the documentation index](docs/README.md)
and [development helpers](scripts/README.md) for operational guides and scripts.
Planning briefs live in `docs/planning/`; authenticated curl examples live in
`docs/operations/`. Source, migrations, tests, fixtures, model metadata and
reviewed deployment configuration remain versioned.

Generated smoke media, deployment wheels, runtime databases/logs, downloaded
model weights and machine-local credentials stay ignored. Removing their Git
tracking preserves local copies; operators still provision model weights as
specified above. Earlier commits may contain these artifacts; this cleanup does
not rewrite repository history. Never commit `.env`, `.aws/`, `.codex/`, cookie
jars or generated acceptance output.

## Short-form rulebook and local benchmark

The [topic-independent short-form rulebook](docs/SHORT_FORM_VIDEO_RULEBOOK.md)
sets the layout, caption, audio, source and final-media checks for future work.
The separate [reference audit](docs/DOCKER_SHORT_BENCHMARK_REVIEW.md) records
the supplied video's strengths, limitations and attachment review.
`.agents/skills/om-short-production/` makes the project production standard
reusable as a production-readiness skill. It applies after `yt-script` accepts
narration and before/alongside storyboard and rendering work; it does not write
replacement narration or alter approvals. The reviewed
`.agents/skills/viral-short-form/` provides optional craft references; canonical
production narration still uses `yt-script`. The active
[benchmark plan](design_doc/docker-short-benchmark.md) tracks the finished-video
acceptance work separately from unfinished publishing tasks 6–7.

The [revised local Short](artifacts/benchmark/docker-short/final/docker-short.mp4)
has an original synthesized music bed configured in its topic JSON, speech
ducking, action effects and a two-pass loudness mix. [Reusable benchmark
source](examples/docker-short-benchmark/README.md) includes the original
Codex-written narration and operator-directed follow revision, topic data,
local voice/alignment, music provenance and final-byte
verification commands. Its encoded video passed technical and visual checks;
subjective listening acceptance is pending. This benchmark renderer is not yet
part of the production worker. Generated media remains local and ignored by Git.

The newer [Claude pipeline profile](docs/CLAUDE_PIPELINE_REVIEW.md) is being
integrated in `tubeforge.rendering.shorts`. Its semantic templates, local speech
preparation, alignment, music and encoder are native Python components. Install
their optional dependencies with `pip install -e '.[dev,reference-renderer,kokoro,alignment]'`
in the project virtual environment; model weights remain local configuration.
The profile targets 25–90 seconds (preset default 60), 1080×1920 finals and 720×1280 drafts. It is
**not yet available as a verified dashboard workflow**; see the current plan for
integration and real-video acceptance. Existing approved jobs keep their original
contracts. Updated narration/production skills require rebuilding and checking
the host runner wheel before using them in an isolated deployed runner.

Animated landscape scenes receive local word timing and native 16:9 layouts. The default waveform timing remains an estimate requiring listening review; it is not independently measured word alignment.

Ready, unapproved previews can use the same media-stage refresh after a renderer repair; approved previews require the revision workflow. Animated landscape captions use short word-timed ASS chunks below the diagrams. Production preview and final profiles both normalize audio and measure the encoded result.
