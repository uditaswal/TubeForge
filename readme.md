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

See [docs/STATUS.md](docs/STATUS.md) for the authoritative release state,
validation evidence, blockers, and next tasks. See
[AUTONOMOUS_PROGRESS.md](AUTONOMOUS_PROGRESS.md) for the append-only work log.
The [publishing and dashboard implementation plan](design_doc/tubeforge-publishing-design.md)
defines the forward work and acceptance checks. The [earlier delivery plan](docs/planning/publishing-delivery-plan.md)
retains inventory and acceptance evidence. The [dashboard prototype](design_doc/tubeforge-dashboard.html)
is illustrative; it is not the current Creator Studio interface.

## Included capabilities

- SQLite/Alembic persistence with worker leases, ownership fencing, checkpoints,
  retries, cancellation, and atomic artifact promotion.
- Content-provider, media-provider, voice-provider, and publishing boundaries;
  deterministic/fake adapters support offline testing.
- Local FFmpeg rendering with paced four-direction camera motion, native
  portrait storyboard graphics or rights-safe public-domain/CC0 Wikimedia stock,
  selectable Kokoro narration with a reliable Piper
  fallback, highlighted captions, licensed/ducked background music, final-artifact quality
  checks, publication metadata/thumbnail preparation, and source clips.
- Dashboard authentication, audited approvals/activity, topic queue, schedules,
  encrypted social-account credential envelopes, and durable dispatch receipts.

Some capabilities are intentionally incomplete: live Meta publishing and
authenticated live YouTube smoke validation.
See `docs/STATUS.md` before relying on them.

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

Compose starts migration, web, worker, and scheduler services:

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

```bash
tubeforge create-admin --username <name>
```

Use a production-only `TUBEFORGE_ACCOUNT_ENCRYPTION_KEY` for any OAuth account
credential envelopes. Never commit credentials, OAuth tokens, or Piper models.

### Publishing account connection (Phase 1 in progress)

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

Supply these environment variables to the Compose web service through a
protected local deployment secret source (the project `.env` path is ignored
by Git):

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

### Create a dashboard login account in Docker

Run this in the Debian server's SSH terminal while the Compose web service is
running:

```bash
cd /home/uditaswal/docker/tubeforge/Youtube_Video_Producer
sudo docker compose exec web tubeforge create-admin --username operator
```

Replace `operator` with your preferred username (3–100 characters). Enter a
password of at least 12 characters at the hidden prompt. Then sign in to
Creator Studio using that username and password. This dashboard account is
separate from the dedicated Codex service account and its ChatGPT login.

The command creates an account; it does not reset an existing password. If it
reports `administrator already exists`, use the existing credentials or choose
a different username to create another administrator. Accounts persist in the
Compose-mounted database across container restarts; recreating containers does
not require recreating your account. Do not put passwords in documentation or
pass them on the command line.

### Private remote access with Tailscale

When TubeForge runs on a Debian home server, keep Compose bound to loopback and
use Tailscale Serve for remote access from devices in the same Tailnet. This
does not open a LAN or public dashboard port. Run the following on the Debian
server, from the repository root, after installing and signing in to
Tailscale:

```bash
sudo systemctl enable --now tailscaled
sudo tailscale up
sudo docker compose up -d --build
sudo tailscale serve --https=443 http://127.0.0.1:62065
tailscale serve status
```

Open the HTTPS URL reported by `tailscale serve status` on a Tailnet-enrolled
device. The production configuration enables dashboard login and secure
cookies, so do not replace this with an insecure HTTP proxy. Verify the
deployment before use with `curl -fsS http://127.0.0.1:62065/healthz` on the
server; it must return `{"status":"ok","database":"ok"}`. If no
administrator exists yet, create one interactively with
`sudo docker compose exec web tubeforge create-admin --username <name>`.

## Local narrator voices

Creator Studio offers three natural, free local Kokoro voices (`af_bella`,
`af_sarah`, and `am_michael`) plus **Piper reliable fallback**. The selected
voice is stored with the generation job. If a selected Kokoro synthesis cannot
run, TubeForge automatically produces that phrase with Piper rather than
failing the job.

Choose a voice in **New generation** and use **Preview voice** to hear the
same local provider before creating a job. The first request stores a stable
WAV under `data/artifacts/voice-previews/`; later clicks reuse that exact local
file without synthesizing again. A preview reports an error when its
model/runtime is not available; it does not contact a hosted text-to-speech
service.

Kokoro uses an ONNX model and a voice pack mounted from `./models/`; they are
intentionally ignored by Git. Production expects
`kokoro-v1.0.int8.onnx` and `voices-v1.0.bin` in that directory. The Docker
image installs the lightweight `kokoro-onnx` runtime; download model assets
only from the configured trusted release and verify a local synthesis before
using them for production jobs.

## Source-grounded writer

Production scripts must use **Codex CLI** or **Claude**. A local LLM is not an
approved production script provider and must not be used for generation,
automatic retries, or quality acceptance unless the operator explicitly
approves it for that specific run. Production script generation uses the
restricted host-side Codex runner over `/run/tubeforge-codex/codex.sock`; it
uses only the dedicated `tubeforge-codex` account and its private `CODEX_HOME`.
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

Creator Studio uses the configured Codex content prompt version for new jobs.
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
  fields at 1080×1920 for Shorts. A complete asset-stage manifest and contact
  sheet record scene order, hashes and rights information. Existing approved
  scripts without the new fields use search terms as fallback labels and need
  visual review. FFmpeg adds paced camera moves and crisp cuts.
  Deploy the updated host wheel and rebuild the web/worker image before using
  these new fields in production; see [visual pipeline handoff](docs/VIDEO_VISUAL_INVENTORY.md).
- **Rights-safe stock (Wikimedia Commons)** searches only Wikimedia Commons and
  accepts only public-domain or CC0 candidates that satisfy the asset policy.
  If the search is unavailable or none qualify, the hybrid provider falls back
  explicitly to local generated CC0 scene graphics so the job can render without
  weakening the licence policy. The asset manifest preserves the requested
  stock source, the resolved local source, and the reason for the fallback.

Creator Studio displays generation and activity timestamps in India Standard
Time (IST), regardless of the browser's own timezone.

TubeForge does not scrape or reuse Google Image results. Google is a search
engine, not a licence/provenance provider, so its results cannot safely pass
the pipeline's reuse checks. Every selected visual is checksummed, retained in
the job's asset manifest, and revalidated before rendering or resuming.

For Shorts, the visual gate rejects non-portrait or undersized stock, mixed
generated styles, missing palette identity, repeated scene bytes, repetitive
camera motion, visual holds over three seconds, and captions outside the
configured safe area. Landscape stock which cannot meet the portrait source
floor falls back to the local storyboard graphics provider before it can be used.

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

## YouTube Shorts workflow

Choose **YouTube Short (9:16)** in **New generation** to use the dedicated
portrait workflow. The preset accepts 30–55 seconds and defaults to 45 seconds.
It preserves the existing widescreen preset rather than changing its behavior.

Shorts previews are rendered at 540×960. Approved finals are rendered at
1080×1920, 30 fps with H.264 video and AAC audio. A local waveform aligner
binds every approved narration word to its generated WAV before captions are
rendered. The final quality gate verifies that alignment against the assembled
audio, rejects a first word after three seconds, rejects visual holds over
three seconds, and validates portrait caption margins and line widths.

Shorts use large uppercase ASS captions near the lower-middle safe area. The
currently spoken word is yellow and surrounding words remain white. Scene
holds are deterministically divided into shorter camera moves, so a long
narration scene does not become one static shot. Source-grounded production
writing, the fixed portrait visual system, and licensed music decisions are
recorded in
[`docs/SHORTS_WORKFLOW.md`](docs/SHORTS_WORKFLOW.md).

## Shorts production standard

TubeForge’s Shorts workflow targets a complete 30–55 second video exported at
1080×1920 (9:16). Production scripts use Codex CLI or Claude. Local LLMs are
not production script providers unless the operator approves one for a
specific run.

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
and its unresolved final-render gate are recorded in
[`docs/TASK4_VIDEO_REVIEW.md`](docs/TASK4_VIDEO_REVIEW.md).

## Creator Studio UI contract

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

All eleven skills live once under `.agents/skills/`: yt-script, yt-package,
yt-seo, yt-shorts, yt-plan, yt-chapters, yt-edit, yt-retention, yt-viral,
yt-audit and yt-comment. Read a skill before invoking it in Codex (for example,
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

During script review, “Copy Codex prompt” prepares an explicit skill-loaded
revision brief with the exact current package, full source context, format and
voice. This prepares a prompt for an operator's external Codex session; it does
not claim to have run Codex or saved a revision. Review the returned narration
array, enter each section, save the revision, then approve its new exact identity.
Unsupported revisions must be rejected rather than pasted into narration.

The Studio's “Revise one scene” action opens the saved storyboard and that
scene's narration and visual direction. Saving creates a separate job paused at
script review; the original video and its approvals remain unchanged. Review
and approve the child's exact script before its worker rebuild, then inspect
and approve its new preview. Unchanged accepted scene assets and phrase audio
are reused only after their hashes and request identities are revalidated.
This scene-revision flow is currently **IMPLEMENTED**; its real production
artifact acceptance is tracked in `docs/STATUS.md`.

Every submitted generation/repair prompt records its SHA256, resource hashes,
automation mode and skill identifier in invocation provenance. Deploy the rebuilt
wheel to the dedicated host runner after any canonical skill change; the worker
refuses a resource mismatch before generating. Changing prompt versions does
not authorize resetting or reusing exhausted source packets.


The configured `m6-content-v6` generation path embeds **yt-script**, its 21
hook formulas and scoring implementation, **yt-package** and its title checker,
and **yt-seo** in each actual Codex generation prompt. These resources are
included in the deployment wheel under `tubeforge/content_skills/`. The isolated
host account receives instructions through the fixed prompt; it needs neither
this checkout nor the developer's home or interactive skill discovery. Compose
also mounts the canonical skills read-only for worker/web source deployments.
The fixed Codex CLI provider, model, source grounding, two-invocation limit,
eight-minute timeout, review gates and publishing policies remain in effect.
Older prompt versions remain readable for existing jobs; every new generation and repair invocation explicitly embeds the updated
yt-script skill, including legacy prompt templates. A new prompt version does not authorize reusing exhausted packets.
Current v6 output must provide a subject, purpose, composition and visual
elements for every scene; incomplete storyboards fail validation before asset
acquisition. The canonical automation skill asks for display-ready,
source-supported visual labels rather than placeholders; the renderer places
those labels into diagrams. Existing approved older packages remain readable.

- **yt-script:** five candidate hooks, narration, scene visual directions and
  on-screen text. Application Python executes the included hook scorer before
  selecting among the top two format-compatible candidates. It preserves the
  model's source-appropriate choice if it is a finalist; otherwise it uses the
  highest-scoring eligible candidate. Only the opening sentence changes.
- **yt-package:** ten coordinated title options, thumbnail text of at most
  three words, visual brief and accessibility description. Application Python
  executes the title checker for every title against the selected thumbnail.
  The model's first title remains the proposed publication title; warnings are
  visible during review rather than treated as performance predictions.
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
    prompt_template_version: m6-content-v6
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
and create a generation. Shorts remain 9:16, 30–55 seconds, with an immediate
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
recorded in [`docs/TASK4_VIDEO_REVIEW.md`](docs/TASK4_VIDEO_REVIEW.md). The full
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

See [the integration plan](docs/YOUTUBE_SKILLS_PLAN.md) and
[status](docs/STATUS.md) for current acceptance evidence and next actions.

## Repository layout and local artifacts

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
## Docker Short benchmark

The [benchmark guide](docs/DOCKER_SHORT_BENCHMARK_GUIDE.md) records the supplied
Claude video's strengths, limitations, attachment audit and reusable production
checks. The reviewed `.agents/skills/viral-short-form/` provides optional craft
references; canonical production narration still uses `yt-script`. The active
[benchmark plan](design_doc/docker-short-benchmark.md) tracks the finished-video
acceptance work separately from unfinished publishing tasks 6–7.

The [finished local Short](artifacts/benchmark/docker-short/final/docker-short.mp4)
is ready for review. [Reusable benchmark source](examples/docker-short-benchmark/README.md)
includes the exact accepted narration, topic data, local voice/alignment and
renderer, plus final-byte verification commands. Technical/visual checks passed;
subjective listening acceptance is pending. This benchmark renderer is not yet
part of the production worker. Generated media remains local and ignored by Git.
