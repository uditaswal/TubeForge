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

## Included capabilities

- SQLite/Alembic persistence with worker leases, ownership fencing, checkpoints,
  retries, cancellation, and atomic artifact promotion.
- Content-provider, media-provider, voice-provider, and publishing boundaries;
  deterministic/fake adapters support offline testing.
- Local FFmpeg rendering with paced four-direction camera motion, native
  portrait motion-graphic scene art or rights-safe public-domain/CC0 Wikimedia stock,
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
`gpt-5.6-sol` but not `gpt-6-sol`. The `gpt-5.6-sol` switch remains
unverified until the host wheel is redeployed and a new, reviewed source
packet produces a valid script. Do not reset an exhausted source packet or
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
  each approved scene. Shorts use native 1080×1920 compositions built from one
  fixed midnight/cyan/violet/amber reference palette and four layout families.
  FFmpeg adds paced horizontal/vertical moves at two speeds and crisp cuts.
- **Rights-safe stock (Wikimedia Commons)** searches only Wikimedia Commons and
  accepts only public-domain or CC0 candidates that satisfy the asset policy.
  If the search is unavailable or none qualify, the hybrid provider falls back
  explicitly to local generated CC0 scene art so the job can render without
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
floor falls back to the local motion-graphics provider before it can be used.

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
