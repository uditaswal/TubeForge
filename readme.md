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
- Local FFmpeg rendering with subtle cinematic still-image motion, HD
  deterministic fallback art, selectable Kokoro narration with a reliable Piper
  fallback, captions, final-artifact quality
  checks, publication metadata/thumbnail preparation, and source clips.
- Dashboard authentication, audited approvals/activity, topic queue, schedules,
  encrypted social-account credential envelopes, and durable dispatch receipts.

Some capabilities are intentionally incomplete: live Meta publishing, real
portrait derivative rendering, and authenticated live YouTube smoke validation.
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

The dashboard is mapped to port `62065` by the production Compose file. Before
enabling production authentication, migrate the database and create the first
administrator:

```bash
tubeforge create-admin --username <name>
```

Use a production-only `TUBEFORGE_ACCOUNT_ENCRYPTION_KEY` for any OAuth account
credential envelopes. Never commit credentials, OAuth tokens, or Piper models.

## Local narrator voices

Creator Studio offers three natural, free local Kokoro voices (`af_bella`,
`af_sarah`, and `am_michael`) plus **Piper reliable fallback**. The selected
voice is stored with the generation job. If a selected Kokoro synthesis cannot
run, TubeForge automatically produces that phrase with Piper rather than
failing the job.

Kokoro uses an ONNX model and a voice pack mounted from `./models/`; they are
intentionally ignored by Git. Production expects
`kokoro-v1.0.int8.onnx` and `voices-v1.0.bin` in that directory. The Docker
image installs the lightweight `kokoro-onnx` runtime; download model assets
only from the configured trusted release and verify a local synthesis before
using them for production jobs.

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
