# TubeForge

A self-hosted pipeline that turns a topic into a reviewed, upload-ready vertical Short. An AI model writes a strict-JSON script and scene plan; everything else — narration, captions, imagery, motion, mixing, encoding and quality checks — runs locally with Python and FFmpeg, so rendering costs no tokens. Nothing is published without an explicit human approval.

## What It Does

You brief a topic in the Creator Studio dashboard (or let a schedule pick one). TubeForge researches sources, has the AI write a script, and pauses for your approval. Approved scripts are narrated, aligned word by word, rendered as a 9:16 preview, then a 1080×1920 final. Each step is a durable job you can pause, retry or delete, and publication (YouTube first) stays behind its own approval gate and defaults to dry-run.

## Features

- 30–90 s vertical Shorts with word-timed captions, motion, icons, brand logos, real imagery and licensed background music
- Script owner chosen per job: Codex CLI or Claude, behind a host-side runner (no API keys in the app)
- Source-grounded writing with research, hook/craft quality gates and an optional writers' room revision pass
- Local narration (Kokoro, Piper) with Whisper word alignment
- Final-video quality checks: decodability, loudness (−15…−13 LUFS), true peak (≤ −1.5 dB)
- Dashboard with login, CSRF protection, audited approvals, topic queue, schedules and activity history
- Publishing preparation: title, description and thumbnail suggestions; encrypted OAuth credential envelopes; dry-run YouTube upload
- Structured, rotating, redacted application logs

## Engineering Highlights

- **Durable job pipeline.** A state machine with worker leases, ownership fencing, checkpoints, retries, cancellation and atomic artifact promotion, so a crashed worker never leaves half-written output.
- **Approval-gated by design.** Script, preview and publication are separate approvals bound to the exact reviewed artifact; edits require a fresh approval.
- **The AI is only the brain.** It returns validated JSON; all pixels, audio and encoding are deterministic local code. Failed generations have a bounded attempt allowance per request.
- **Secrets stay out.** No credentials in configuration, encrypted account envelopes, gitleaks on every commit and in CI, `pip-audit`, Dependabot.
- **Observable.** JSON-lines logs per service with job and request ids, stage timings, memory samples, HTTP status codes for inbound and outbound calls, and secret redaction.
- **Tested against real output.** Unit and integration tests plus an FFmpeg-based review of rendered frames and audio before a video counts as done.

## Architecture

```text
Dashboard / API (FastAPI)
        |
        v
SQLite + Alembic  <-->  Scheduler (topics, schedules)
        |
        v
Worker (leased jobs) --> Pipeline state machine
        |                   research -> script (AI) -> approval -> voice + alignment
        |                   -> preview render -> approval -> final render -> QA
        |                   -> publication prep -> approval -> upload
        v
Host script runner (Codex / Claude CLI over a Unix socket)
Local services: Piper TTS server, FFmpeg, headless Chromium for source captures
```

Services run under Docker Compose: `web`, `worker`, `scheduler`, `piper-tts`, a one-shot `migrate`, and an optional `publisher-worker`.

## Trade-offs

- **SQLite** keeps setup trivial for a single-operator deployment; a multi-tenant service would need PostgreSQL.
- **Host-side AI runner** reuses an existing CLI login instead of storing API keys, at the cost of an extra process and socket to manage.
- **Local rendering** costs no tokens and is reproducible, but is bounded by the host CPU (a 60 s Short renders in minutes, not seconds).

## Tech Stack

Python 3.12/3.13 · FastAPI · SQLAlchemy 2 + Alembic (SQLite) · Pydantic · Docker Compose · FFmpeg · Pillow/NumPy renderer · Kokoro and Piper TTS · faster-whisper · Playwright/Chromium · pytest · pre-commit + gitleaks · GitHub Actions

Pillow code visuals use syntax-coloured editor cards with a following cursor and a bounded frame cache. Code visuals may supply reviewed `line_reveal_words` (one narration word index per line) for the Pillow motion renderer; these resolve against the saved alignment, retain its provenance and require a one-second finished-code hold. Unanchored code keeps proportional scene timing. Story/HyperFrames reject explicit code-line anchors. Story/HyperFrames use their own rendering path. Pillow hooks are visible on frame one, and loop endpoints reuse the opening frame during the closing speech tail. Local code-line anchors are not yet requested from production writers. New rendered outputs require the existing artifact review.

New source captures remove matching interactive Ask AI/Copy controls, including
controls in open shadow roots, and record the capture policy and hidden controls
in the plate manifest. Article text stays intact. Older captures and approved
outputs retain their existing identity; regenerated assets need a new render and
artifact review.

## Run Locally

Prerequisites: Docker with Compose, FFmpeg for host-side checks, and operator-supplied voice models in `models/` (they are large and not committed).

```bash
git clone https://github.com/uditaswal/TubeForge.git && cd TubeForge
cp .env.example .env              # fill in values; never commit .env
docker compose build              # large first build
docker compose up -d web worker scheduler
docker compose exec web python -m tubeforge.cli create-admin --username you
```

Open <http://127.0.0.1:62065> (bound to loopback only) and sign in. The AI script runner (Codex or Claude) is a separate host process; see [docs/deploy](docs/deploy). Configuration lives in `config/*.yaml`; select one with `TUBEFORGE_CONFIG`.

Development without Docker:

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
python -m alembic upgrade head
python -m pytest
```

Install the optional extras you need (`reference-renderer`, `kokoro`, `alignment`, `local-media`).

## Documentation

| Topic | Where |
| --- | --- |
| Index | [docs/README.md](docs/README.md) |
| Application logs and fields | [docs/operations/logging.md](docs/operations/logging.md) |
| Reviewing jobs through the API | [docs/operations/api-workflow.md](docs/operations/api-workflow.md) |
| Platform integrations (YouTube, Meta) | [docs/operations/platform-integrations.md](docs/operations/platform-integrations.md) |
| Running the script runners as services | [docs/deploy](docs/deploy) |
| Batch plans: import, queue, disclosure/rights review, staged export | [docs/batch-plans.md](docs/batch-plans.md) |
| Video quality standard | [docs/SHORT_FORM_VIDEO_RULEBOOK.md](docs/SHORT_FORM_VIDEO_RULEBOOK.md) |
| Security policy | [SECURITY.md](SECURITY.md) |

## Project Structure

```text
src/tubeforge/api/          Dashboard and HTTP API
src/tubeforge/pipeline/     State machine and stage orchestration
src/tubeforge/workers/      Leased job worker
src/tubeforge/scheduling/   Topic queue and schedules
src/tubeforge/providers/    Content, voice, media and publishing adapters
src/tubeforge/rendering/    Shorts renderer, audio, encoding, QA
src/tubeforge/core/         Configuration, runtime, logging
migrations/                 Alembic migrations
config/                     Default and production settings
tests/                      Unit and integration tests
.agents/skills/             Content skills used by the script writer
docs/                       Public documentation
```

## Status

Local rendering, review and approval workflows are working. Live YouTube upload is gated behind operator OAuth credentials and dry-run by default; Instagram publishing is not implemented. Operator-facing setup details beyond this page are in the `docs/` guides above.
