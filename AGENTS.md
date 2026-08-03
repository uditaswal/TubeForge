# Codex Project Instructions

## Mission

Build TubeForge: a self-hosted, provider-agnostic pipeline that plans, creates,
edits, reviews, repurposes, and publishes long-form YouTube videos and vertical
clips. The first deployment targets a Linux homelab with 4 GB RAM and a 1 TB
HDD, controlled from a phone or laptop over a private Tailscale connection.

The full product specification is `docs/YouTube_Automation_Agent_Design.docx`. Treat
that document as the source of truth for product scope. This file contains the
day-to-day engineering rules.

## Priorities

1. Reliability and recoverability.
2. Human approval before external publishing.
3. Minimal Codex/model usage per completed video.
4. Provider portability.
5. Low resource use on a 4 GB server.
6. Maintainability for one operator.

## Required architecture

- Use Python 3.12 for the application and FastAPI for the web interface.
- Use Pydantic models for configuration and all stage-to-stage contracts.
- Start with SQLite in WAL mode and SQLAlchemy/Alembic. Keep repository code
  portable to PostgreSQL.
- Use FFmpeg for video/audio composition; do not process frames in Python when
  FFmpeg can perform the operation.
- Run native tools such as FFmpeg, Piper, whisper.cpp, and Codex through narrow,
  validated wrappers.
- Deploy using Docker Compose. Persist the database, media, credentials, and
  Codex authentication outside the container's writable layer.
- Run only one production job at a time by default.
- Install Tailscale on the host. Do not expose the dashboard directly to the
  public internet.

Prefer this package layout:

```text
src/tubeforge/
  api/              # FastAPI routes and schemas
  core/             # configuration, errors, logging, state machine
  db/               # models, repositories, migrations
  domain/           # provider-neutral contracts
  providers/
    content/         # Codex, later OpenAI/Copilot-compatible adapters
    voice/           # Piper, ElevenLabs, later other TTS adapters
    media/           # licensed asset sources
    publishing/      # YouTube and Instagram adapters
  pipeline/          # deterministic stage orchestration
  rendering/         # FFmpeg command construction and templates
  workers/           # job claiming, retries, cancellation
tests/
```

## Deterministic-first and low-token rules

Model calls are scarce planning operations, not the workflow engine.

- Prefer one structured content-generation call per video that returns a
  validated `ContentPackage`: research notes, cited claims, script, scene plan,
  metadata, thumbnail brief, and clip candidates.
- Never use Codex/model calls for polling, file moves, database updates,
  rendering, subtitle formatting, retries, uploads, or routine validation.
- Reuse approved scripts, transcripts, timestamps, scene plans, and prior
  outputs. Do not regenerate a complete package to repair one field.
- Cache responses by normalized input, prompt version, provider, and model.
- Use JSON Schema/Pydantic validation and bounded repair of invalid fields.
- Keep prompts versioned, short, and assembled from only the context required
  for that stage. Do not send logs, binaries, transcripts, or source documents
  wholesale when a small excerpt or structured summary is sufficient.
- Batch compatible work when it reduces calls without producing oversized
  prompts.
- Implement normal application logic in Python. Do not solve repeatable runtime
  behavior by repeatedly invoking `codex exec`.
- Record usage and generation provenance per job when the provider exposes it.

## Provider boundaries

All external capabilities must sit behind small typed interfaces. Pipeline code
must not import provider SDKs directly.

At minimum define provider-neutral contracts for:

- `ContentProvider.generate_package(request) -> ContentPackage`
- `VoiceProvider.synthesize(request) -> VoiceResult`
- `MediaProvider.search(request) -> list[AssetCandidate]`
- `Publisher.upload(request) -> PublishResult`

Switching an implemented provider should be configuration-only. A new provider
may add an adapter, authentication, and contract tests, but must not require
changes to unrelated pipeline stages. Never leak provider response formats
beyond the adapter.

Initial defaults:

- Content: Codex CLI authenticated through the user's ChatGPT plan.
- Voice: Piper.
- Captions: whisper.cpp or narration-derived timings where reliable.
- Rendering: FFmpeg.
- Database: SQLite.
- Publishing: YouTube Data API; Instagram support is later and optional.

Do not assume ChatGPT-plan access includes OpenAI API credits. Paid providers
must be optional and disabled unless credentials and explicit configuration are
present.

## Pipeline and state rules

Model the workflow as resumable, idempotent stages, broadly:

```text
topic -> content package -> script approval -> assets -> voice -> captions
      -> preview render -> final approval -> final render -> private upload
      -> publish approval -> publish -> clips -> clip approvals -> clip uploads
```

- Persist stage state and artifact paths after every successful stage.
- A restart must resume from the last valid checkpoint, not restart the video.
- Every stage must be safe to retry or must detect an existing valid output.
- Write generated artifacts to temporary paths and atomically move them into
  place only after validation.
- Use bounded retries with backoff for transient network failures. Authentication
  failures become `AUTH_REQUIRED`; validation failures require correction; do
  not retry either indefinitely.
- Store checksums and provenance for assets and important generated artifacts.
- Keep database transactions short. Never hold a transaction while calling a
  provider, running FFmpeg, or uploading media.
- Prevent two workers from claiming the same job.

## Safety, publishing, and copyright

- Never automatically make content public in the initial implementation.
- Upload to YouTube as private or unlisted only after preview approval.
- Require a separate explicit approval before public publishing or scheduling.
- Treat Instagram/YouTube publishing as an external side effect requiring an
  audit record and idempotency protection.
- Use only user-owned, licensed, or clearly permitted assets. Store source URL,
  author, licence, retrieval date, and required attribution.
- Do not build features for downloading and reposting unrelated creators'
  videos.
- Every factual claim intended for a video must retain its source and review
  status. Flag uncertain or time-sensitive claims for human review.
- Do not log OAuth tokens, API keys, cookies, Codex credentials, or full secret
  values. Never commit secrets or generated credential files.
- Validate paths and identifiers before invoking native commands. Use argument
  arrays; never build shell commands from untrusted strings.

## Homelab constraints

- Optimize for 4 GB RAM and limited CPU: sequential heavy stages, bounded
  queues, streaming downloads, and no in-memory video buffering.
- Configure FFmpeg and whisper.cpp thread counts; do not assume all host cores
  are available.
- Avoid Kubernetes, Redis, PostgreSQL, Celery, and multiple always-on services
  until measured requirements justify them.
- Add health checks, disk-space guards, graceful shutdown, and retention rules.
- Never delete source or finished media automatically without a configurable,
  recoverable retention policy.
- Keep SQLite on a local disk, not a network share or live-sync folder.

## Engineering workflow

Before changing code:

1. Read this file and the relevant portion of the design document or current
   implementation.
2. Inspect existing code, tests, configuration, and uncommitted changes.
3. State assumptions when requirements are ambiguous; ask before choices that
   affect publishing, cost, credentials, copyright, or data deletion.

While changing code:

- Make the smallest coherent change.
- Preserve provider boundaries and idempotency.
- Add type hints and focused docstrings for public interfaces and non-obvious
  behavior.
- Prefer standard-library or already-used dependencies. Explain any new runtime
  dependency and pin it appropriately.
- Do not perform unrelated rewrites or formatting churn.
- Do not edit generated media or database files as source code.

After changing code:

- Run focused tests, then the broader relevant suite.
- Run formatting, linting, and type checks configured by the repository.
- For FFmpeg changes, verify commands against a short synthetic fixture and use
  `ffprobe` to assert duration, streams, codecs, dimensions, and audio presence.
- For schema or migration changes, test a fresh database and an upgrade from the
  previous schema.
- For Docker changes, validate the Compose configuration and container health.
- Report what changed, what was verified, and any remaining manual step.

## Testing expectations

- Unit-test state transitions, schema validation, prompt assembly, FFmpeg
  argument construction, retry classification, and provider adapters.
- Use fakes for provider APIs and publishing in normal tests.
- Mark live-provider tests explicitly; never run billable or publishing tests by
  default.
- Keep at least one tiny end-to-end fixture that can create a short local video
  without network access.
- Test interruption and resume at every costly pipeline boundary.
- Test duplicate upload protection and approval enforcement.

## Configuration conventions

- Store non-secret defaults in versioned YAML or TOML.
- Read secrets from environment variables or mounted secret files.
- Validate configuration at startup and fail with actionable errors.
- Include explicit settings for provider selection, paths, concurrency, thread
  counts, upload privacy, approval requirements, retention, and feature flags.
- Example configuration must use fake values and safe defaults.

## Definition of done

A feature is complete only when it:

- follows the provider-neutral architecture;
- preserves resumability and idempotency;
- works within the default single-job homelab constraints;
- includes relevant automated tests;
- has safe failure behavior and useful logs;
- does not make external content public without explicit approval; and
- updates user-facing setup/configuration documentation when behavior changes.

## Development environment safety

Development normally occurs on a personal laptop. Unless the user explicitly
states that the current environment is the TubeForge homelab or authorizes
deployment:

- Treat the environment as development-only.
- Do not install system packages or modify host-level configuration.
- Do not start, stop, or modify Docker containers or system services.
- Do not run deployment, publishing, upload, OAuth, or production migration
  commands.
- Do not access real credentials or invoke live paid providers.
- Do not perform live YouTube or Instagram publishing tests.
- Use fake providers, temporary databases, synthetic media, and test fixtures.
- Commands for inspection, formatting, linting, type-checking, unit tests, and
  local non-publishing test builds are permitted.
- Before running a command that could alter the host outside the repository,
  consume paid services, or cause an external side effect, ask for explicit
  approval.

Production deployment commands may only be run after the user explicitly
confirms that Codex is connected to the intended homelab and requests the
deployment.
