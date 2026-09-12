# Overnight decisions

- Queue scheduling creates ordinary `pipeline_jobs`; it never runs rendering itself.
- Topic reservation is performed in the same short database transaction as job
  creation so competing scheduler processes cannot consume a topic twice.
- Existing lease/checkpoint/approval machinery stays authoritative for worker work.
- External publication is never triggered by the scheduler implementation alone;
  existing approval and publisher configuration policies still apply.
- Dashboard access uses opaque database sessions and Argon2id hashes. Auth is
  explicitly configured, with no default administrator or password; the CLI
  creates the first administrator after migrations.
- The quality gate is a FINAL_READY checkpoint. It revalidates the promoted
  artifact immediately before publication preparation so a stale/corrupt final
  cannot reach publisher code; warnings remain visible without blocking.
- OAuth credential envelopes use Fernet authenticated encryption with
  `TUBEFORGE_ACCOUNT_ENCRYPTION_KEY`; account listing APIs never expose tokens.
- Scheduler polling is a separate lightweight Compose service. It has no worker
  or rendering privileges and only invokes the existing transactional schedule
  service to create ordinary jobs.
- The operations UI extends the existing dashboard at runtime to avoid a risky
  template rewrite. It sends the same authenticated API requests used by other
  clients and supplies the CSRF header when an auth cookie is present.
- Generic publisher dispatch has its own durable attempt receipt rather than
  overloading the historical YouTube publication record. A job/account/artifact
  hash is its idempotency fence; unsupported platform adapters are recorded,
  never treated as success.
- Platform variants are persisted in the publication package as plans. Portrait
  entries clearly require a derivative; no renderer claims a portrait output
  until that derivative artifact is actually generated and quality-gated.
