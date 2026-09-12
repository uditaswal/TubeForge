# TubeForge overnight build plan

## Audit (2026-08-31)

TubeForge already provides a durable SQLite/Alembic job store, lease-fenced worker
claims, checkpoint artifacts, approval gates, FFmpeg/ffprobe rendering, Piper and
fake voice providers, fake/Wikimedia media providers, content provider adapters,
YouTube publication lifecycle records, analytics/learning records, a FastAPI
dashboard, and a source-clipping path.  The existing orchestrator is the sole
owner of expensive generation work and must remain so.

| Requested capability | Existing foundation | Overnight work |
| --- | --- | --- |
| VideoPlan | `ContentPackage`, scenes, durable content artifact | Add a compact durable VideoPlan projection/checkpoint without replacing package contracts. |
| Queue/schedules | durable jobs and worker leases | Add topic/schedule/run tables, atomic reservation and scheduler service/API. |
| Dashboard auth | private-by-convention dashboard only | Add local admin/session primitives, bootstrap CLI, and opt-in production enforcement. |
| Visual router | asset provider/acquisition fallback | Formalize a deterministic fallback router on top of the existing asset path. |
| Quality gate | render probes and validation | Add structured final-artifact gate before publication. |
| Accounts/publishers | YouTube/fake publisher and publication records | Add account model/token envelope and dispatcher contracts; live OAuth adapters remain credential-blocked. |

## Execution order

1. Queue, schedule leasing, and a scheduler-to-normal-job vertical slice.
2. VideoPlan and visual routing/checkpoint integration.
3. Quality gate and offline FFmpeg smoke validation.
4. Authentication, account storage/encryption, API/dashboard operations.
5. Platform contracts, operator documentation, full regression and Compose checks.
