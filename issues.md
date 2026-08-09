# TubeForge audit — 4 August 2026

Scope: static review of the current working tree against `AGENTS.md` and `docs/YouTube_Automation_Agent_Design.docx`. No application code was changed and the test suite was not run, to avoid adding to the already-dirty generated pytest artifacts in this working tree.

Priorities: **P0** blocks safe operation, **P1** is required for the stated initial product, **P2** is important hardening or maintainability work.

## P0 — fix before a worker is used

### I-01: Long stages lose their lease and can run concurrently

- Evidence: `WorkerService.run_once()` claims a job once, then calls the synchronous orchestrator without a heartbeat. `worker.lease_seconds` defaults to 300 seconds, while preview and final render timeouts default to 900 and 1,800 seconds respectively (`workers/service.py`, `core/config.py`).
- Impact: a render, Codex call, asset download, or narration that lasts beyond five minutes becomes reclaimable. A second worker can then process the same job and issue duplicate provider work; future uploads would be particularly unsafe.
- Recommendation: run a bounded heartbeat independently of stage work, fail safely if it cannot renew ownership, and make the lease longer than the largest non-interruptible operation as a fallback.
- Missing tests: expiry during each long stage; two workers competing after expiry; failed heartbeat; worker shutdown while the heartbeat is active.

### I-02: The worker repeatedly claims final and approval-waiting jobs

- Evidence: `JobRepository.claim_oldest_eligible()` excludes states named `PREVIEW_APPROVAL_REQUIRED`, `PUBLISH_APPROVAL_REQUIRED`, and `PUBLISHED`, but those states do not exist. Actual `PREVIEW_READY` and `FINAL_READY` are therefore included in the runnable list (`db/repositories.py`, `domain/states.py`). Script approval is excluded, but preview approval is not.
- Impact: a polling worker will repeatedly claim/release completed jobs and jobs waiting for preview approval. This wastes SQLite writes/CPU, starves genuine work in an oldest-first queue, and makes operational status noisy.
- Recommendation: define one explicit runnable-state set, shared with the state machine, and include only states that can advance without a human decision. Add a terminal completed/published state when upload support lands.
- Missing tests: exact claimability matrix for every `JobState`, including `PREVIEW_READY`, `FINAL_READY`, failures, cancellation, retry time, and an empty-worker polling loop.

### I-03: Provider selection is coupled incorrectly across content and voice

- Evidence: `pipeline.provider` accepts `fake|codex|piper`. Choosing `codex` returns a Codex content provider but a fake voice provider; choosing `piper` returns a Piper voice provider but the content factory falls through to Codex. (`core/config.py`, `providers/content/factory.py`, `providers/voice/factory.py`.)
- Impact: there is no supported configuration for the required initial pairing of Codex content plus Piper narration. Choosing Piper unexpectedly invokes Codex and validation only checks Piper, so the Codex executable is not validated.
- Recommendation: split provider selection into independent `content.provider`, `voice.provider`, and `media.provider` settings; validate every selected adapter and construct them in one composition root.
- Missing tests: every valid provider combination; unsupported combinations; startup validation of all selected executables/models; no accidental external adapter construction in fake/test configuration.

## P1 — required to meet the stated product and safety contract

### I-04: No usable job, approval, or artifact API/UI exists

- Evidence: the FastAPI app exposes only `GET /healthz` (`api/app.py`), and `main.py` only constructs that app. There are no routes for job creation, script review/editing, approvals, artifact playback/download, cancellation, retry recovery, or status.
- Impact: the specified phone/laptop workflow cannot be performed; approval records can only be inserted by internal code or direct database access.
- Recommendation: add authenticated, private dashboard/API flows before treating the pipeline as operable. Bind all mutation endpoints to audited identities and explicit approval/recovery actions.
- Missing tests: auth/allowlist enforcement; request validation; job lifecycle endpoints; approval identity binding; cancellation and retry permissions; artifact path traversal prevention; health degradation responses.

### I-05: The pipeline stops at `FINAL_READY`; private upload and separate public approval are absent

- Evidence: the state machine terminates at `FINAL_READY` and the orchestrator never calls its `_upload_once()` helper. Although `ApprovalGate.PUBLIC_PUBLISH` and `PublishRequest` exist, no pipeline states/transitions implement private upload, receipt checkpointing, processing polling, or public publication.
- Impact: FR-010, FR-015, and the required publish approval/audit path are not implemented. The unused helper risks giving a false impression of upload safety.
- Recommendation: implement private upload, durable receipt reconciliation, processing state, explicit public-publish/schedule approval, and a terminal published state as separate idempotent stages. Keep disabled until real adapter and approval paths are covered.
- Missing tests: crash before/after remote upload acceptance; a pending idempotency reservation requiring reconciliation; duplicate request after timeout; private-only default; public/scheduled approval rejection; polling retry/backoff; receipt persistence and redaction.

### I-06: Content editing and rejection cannot return to the smallest affected stage

- Evidence: the content package is persisted once as `content_package.json`. There is no script revision model/API, rejection reason, invalidation graph, or transition back from `SCRIPT_APPROVAL_REQUIRED`/`PREVIEW_READY`.
- Impact: the required human review loop cannot correct a script or preview; changing content manually would leave scene, claim, narration, render, and approval identities stale.
- Recommendation: model immutable package/script revisions and explicit invalidation from an approved edit or rejection. Preserve prior artifacts and audit records, then regenerate only dependent checkpoints.
- Missing tests: script edit invalidates assets onward; preview rejection only invalidates the selected stage/dependents; old approval cannot authorize a changed preview; restart during invalidation; revision audit history.

### I-07: Rendering supports only image-like scene inputs and omits required outputs/QC

- Evidence: `PreviewRenderer` builds a looping image input for every timeline segment, despite configuration allowing media type `video`; preview and final reuse the same renderer. There is no thumbnail or vertical-clip renderer, and validation checks basic streams/duration but not black frames, audio loudness, caption legibility, or thumbnail output (`rendering/preview.py`).
- Impact: allowed video assets can fail or be rendered incorrectly. FR-007, FR-008, FR-011, and FR-012 are incomplete, and “final” is only a larger version of the preview template.
- Recommendation: explicitly support or reject each configured media type, use distinct versioned profiles/templates for preview/final/vertical/thumbnail, and add deterministic QC appropriate to each artifact.
- Missing tests: image and video timeline fixtures; mixed assets; zero/one/many segments; FFprobe assertions for codecs, streams, dimensions and duration; cancellation cleanup; black/silence/loudness failure; thumbnail and 9:16 fixture renders.

### I-08: Configuration is not actually wired into the orchestrator

- Evidence: the orchestrator constructor defaults to fresh `PreviewRenderConfig`, `FinalRenderConfig`, a hard-coded `AssetLimits` allowlist, and an asset cache rooted at `artifact_root.parent / "cache" / "assets"`. The settings' preview, final, media, and configured cache-root values are not passed through a composition root (`pipeline/orchestrator.py`).
- Impact: configured resource limits, license policy, renderer settings and storage placement can silently differ from runtime behavior. This violates configuration-only provider portability and makes safe deployments unpredictable.
- Recommendation: build all providers, limits, renderer profiles, paths and repositories from validated `Settings` in one application/worker factory; remove production defaults that encode policy.
- Missing tests: non-default settings propagate to every adapter/renderer; configured allowlists accepted/rejected; cache/artifact paths; default config end-to-end composition; no hard-coded host/license remains effective.

### I-09: No source ingestion, retrieval snapshot, or bounded source packet

- Evidence: `ContentRequest` accepts source metadata directly and the Codex prompt uses it, but there is no source ingestor/provider, stored source content hash, retrieval metadata, deduplication, allowlist, extraction, or `source_packet.json`.
- Impact: factual claims cannot be audited against immutable retrieved evidence; prompt-injection and excessive-context safeguards in the design are missing.
- Recommendation: add a typed source-ingestion boundary that fetches only allowed URLs, stores snapshots and hashes, extracts bounded text, labels it untrusted, and passes a compact source packet to content generation.
- Missing tests: URL/redirect/size/content-type policy; duplicate sources; hostile source text; extraction limits; snapshot integrity; claim-to-source linkage after restart.

### I-10: Deployment, persistence, and operations requirements are absent

- Evidence: no `Dockerfile`, Compose file, container health check, retention policy, backup job, disk-space health endpoint, or graceful worker loop is present. The README still says the scaffold has no providers/media/publishing, which is now inaccurate.
- Impact: the requested self-hosted 4 GB homelab deployment is not reproducible or recoverable, and operators have no disk/queue/auth/failure visibility.
- Recommendation: add development-safe Compose assets and runbook, persisted volumes outside the image layer, storage guard/retention/backup configuration, and operational health metrics before homelab deployment.
- Missing tests: Compose validation; fresh/restart persistence; insufficient disk prevents work before writes; retention never deletes masters/receipts; backup/restore; graceful shutdown while claimed; health reports queue/disk/auth.

## P2 — correctness, performance, and maintainability hardening

### I-11: External-operation reservation can become permanently stuck

- Evidence: `_upload_once()` reserves a unique idempotency key before invoking the publisher. If the process dies after the provider receives the request but before `complete()`, all retries get “pending reconciliation”; the record has no lease, expiry, remote lookup data, or reconciliation workflow (`pipeline/orchestrator.py`, `db/repositories.py`).
- Impact: this correctly avoids blind duplicate uploads but can block a video forever and provides no safe recovery path.
- Recommendation: persist operation state, attempt/lease data and provider correlation information; reconcile remotely or require a recorded operator decision before a new idempotency key is allowed.

### I-12: Renderer command construction has unbounded input/filter scaling

- Evidence: a scene becomes an FFmpeg input/filter fragment and all inputs are assembled into one process (`rendering/preview.py`). There is no configured maximum scene/phrase count, command length, or staged composition strategy.
- Impact: long scripts can exceed command-line/filter limits or consume more RAM/CPU than the 4 GB target permits, despite a one-job queue.
- Recommendation: bound package scene counts in contracts, benchmark a representative 6–12 minute job, and render in deterministic chunks or an FFmpeg concat workflow when the threshold is exceeded.
- Missing tests: maximum allowed scene count; command length boundary; synthetic long render benchmark/timeout; memory/disk budget regression.

### I-13: Checksums read whole files into memory in several pipeline paths

- Evidence: `PipelineOrchestrator._checksum()` and Piper's `_checksum()` use `Path.read_bytes()`, unlike the streaming renderer checksum.
- Impact: a large narration/video/cache artifact can cause avoidable memory spikes on the 4 GB host.
- Recommendation: centralize a streaming SHA-256 helper and use it everywhere.
- Missing tests: multi-chunk checksum equivalence and a guard that rejects reintroducing whole-file reads for large artifacts.

### I-14: `max_active_jobs` is declarative only

- Evidence: `WorkerConfig.max_active_jobs` is fixed to one but `WorkerService` has no shared admission control and no long-running service entrypoint.
- Impact: multiple worker processes can run jobs concurrently; the declared single-job homelab limit is not enforced by configuration.
- Recommendation: enforce a database-backed global heavy-work lease/admission policy and expose the active worker/job in operational status.
- Missing tests: two worker instances; crash/reclaim; no second heavy stage while one lease is active; configuration validation.

### I-15: Migrations and persistence constraints lack critical regression coverage

- Evidence: the newest approval migration is not covered by an upgrade-from-previous-revision test. Models lack database foreign keys/unique constraints for artifacts and approvals beyond their primary keys, so orphaned rows and duplicate `(job_id, stage, name)` artifacts are possible.
- Impact: retries can overwrite an ambiguous checkpoint and relational integrity relies entirely on application behavior.
- Recommendation: add targeted constraints/indexes through migrations and test fresh install plus upgrade from every prior schema, including downgrade where supported.
- Missing tests: migration 0005→0006; duplicate artifact rejection; orphan approval/artifact rejection; concurrent repository operations; SQLite WAL recovery after interrupted transaction.

### I-16: Test suite is heavily fake-based and misses real native-tool boundaries

- Evidence: orchestrator tests use `OfflineRenderer`, `OfflineAssembler`, and `OfflineProbe`; no tests target `rendering/preview.py`, `rendering/audio.py`, the Piper adapter, or worker service. Existing tests therefore prove stage ordering more than executable FFmpeg/Piper behavior.
- Impact: command/filter, codec, font, duration, cancellation and filesystem defects can reach the first homelab run.
- Recommendation: retain fakes for fast unit tests, but add a tiny offline FFmpeg fixture suite and adapter contract tests (Piper can remain mocked when its binary is unavailable).

### I-17: Generated test outputs are staged/deleted and repository hygiene is broken

- Evidence: `git status --short` shows a large number of added/deleted files under `.pytest-*` and `.test-tmp`; the repository scan also produced access warnings for these directories. They are not effectively ignored.
- Impact: large binaries and local databases can be committed accidentally, reviews become noisy, and test cleanup is unreliable.
- Recommendation: remove generated test data only with explicit owner approval, then add narrow ignore rules and configure pytest `basetemp` outside the repository or under one ignored directory.
- Missing tests/checks: clean-tree test-run check and CI assertion that no generated media/database files are tracked.

### I-18: Coding style and public documentation have drifted

- Evidence: newer modules compact imports, statements and class definitions onto single lines (`rendering/preview.py`), while the rest of the project is formatted normally. The README describes a much older scaffold.
- Impact: reviewability and maintenance suffer; the docs mislead operators about available/absent capabilities.
- Recommendation: enforce the configured formatter/linter in CI and update README/setup documentation alongside each implemented milestone.

## Suggested implementation order

1. I-01, I-02, I-03, and I-08: make job ownership, state claimability, composition, and provider configuration correct before enabling a worker.
2. I-04, I-06, I-09: build the human-controlled, auditable input/review path.
3. I-07 and I-16: validate the deterministic media pipeline with real tiny fixtures, then add thumbnails/clips/QC.
4. I-05 and I-11: add private upload and reconciliation before any public publishing capability.
5. I-10 and I-14 through I-18: make the homelab deployment operational and maintainable.
