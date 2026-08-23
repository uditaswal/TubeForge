# TubeForge manual offline-workflow commands

This guide runs a **safe offline smoke test** against the Docker Compose stack.
It assumes the web API is bound to `127.0.0.1:8081`, all providers are fake,
and YouTube publishing is disabled. It creates a new job and never alters or
deletes earlier jobs or artifacts.

For a fully automatic version of this sequence, use:

```bash
BASE_URL=http://127.0.0.1:8081 ACTOR=uditaswal \
  bash scripts/test_offline_workflow.sh
```

Use the commands below when you want to review each checkpoint yourself.

## 1. Set shell variables and check service health

```bash
BASE=http://127.0.0.1:8081
ACTOR=uditaswal

curl -fsS "$BASE/healthz" | jq
```

Expected result:

```json
{"status":"ok","database":"ok"}
```

This proves that the web process can reach SQLite. Do not create a job until
this endpoint succeeds.

## 2. Create a new safe offline job

```bash
JOB=$(
  curl -fsS -X POST "$BASE/api/jobs" \
    -H 'Content-Type: application/json' \
    -d '{
      "topic":"How rain forms",
      "angle":"A short educational offline smoke test",
      "target_duration_seconds":30,
      "language":"en-IN",
      "audience":"general",
      "prompt_version":"offline-smoke-v1",
      "sources":[
        {
          "source_id":"rain-reference",
          "url":"https://example.invalid/rain",
          "title":"Operator-supplied offline reference"
        }
      ]
    }' | jq -er '.id'
)

printf 'Job ID: %s\n' "$JOB"
```

Every POST creates a new immutable job. This makes retries and operator
decisions auditable; do not try to reuse a completed job to create another
video.

## 3. Inspect job state

```bash
curl -fsS "$BASE/api/jobs/$JOB" | jq
```

The worker should reach `script_approval_required`. The worker runs
asynchronously, so repeat the command until that state appears. If a job has
`failure_message`, inspect it before approving anything.

## 4. Download and review the generated script package

```bash
curl -fsS "$BASE/api/jobs/$JOB/artifacts/content_package" | jq | less
```

This retrieves the registered content package, containing the script, claims,
scene plan, metadata, and source references. Review it before allowing asset,
voice, and rendering work to proceed.

## 5. Approve the script

```bash
curl -fsS -X POST "$BASE/api/jobs/$JOB/approvals/script" \
  -H 'Content-Type: application/json' \
  -d "$(jq -n --arg actor "$ACTOR" \
    '{status:"approved",actor:$actor}')" | jq
```

The script gate is the first human approval. It prevents downstream asset,
voice, and rendering work until an operator accepts the plan.

Wait for the preview:

```bash
until [[ "$(curl -fsS "$BASE/api/jobs/$JOB" | jq -r '.state')" == "preview_ready" ]]; do
  curl -fsS "$BASE/api/jobs/$JOB" | jq
  sleep 2
done
```

## 6. Retrieve and review the preview

```bash
curl -fsS "$BASE/api/jobs/$JOB/artifacts/preview.mp4" -o "preview-$JOB.mp4"
curl -fsS "$BASE/api/jobs/$JOB/artifacts/preview_manifest" | jq
```

`preview.mp4` is the physical filename. The API also accepts the logical name
`preview`. The manifest supplies the `render_identity`, a digest of approved
inputs. It prevents approval of an old preview after narration, captions,
assets, or render inputs changed.

## 7. Approve the exact preview you reviewed

```bash
PREVIEW_ID=$(
  curl -fsS "$BASE/api/jobs/$JOB/artifacts/preview_manifest" |
  jq -er '.render_identity'
)

curl -fsS -X POST "$BASE/api/jobs/$JOB/approvals/preview" \
  -H 'Content-Type: application/json' \
  -d "$(jq -n --arg actor "$ACTOR" --arg id "$PREVIEW_ID" \
    '{status:"approved",actor:$actor,reviewed_identity:$id}')" | jq
```

After this approval, TubeForge produces `final.mp4`, creates final metadata and
a thumbnail, then waits at `publication_approval_required`.

```bash
until [[ "$(curl -fsS "$BASE/api/jobs/$JOB" | jq -r '.state')" == "publication_approval_required" ]]; do
  curl -fsS "$BASE/api/jobs/$JOB" | jq
  sleep 2
done
```

## 8. Review the final local publication package

```bash
curl -fsS "$BASE/api/jobs/$JOB/artifacts/final.mp4" -o "final-$JOB.mp4"
curl -fsS "$BASE/api/jobs/$JOB/artifacts/metadata" | jq
curl -fsS "$BASE/api/jobs/$JOB/artifacts/publication_package" | jq
```

The package contains title, description, tags, final-file path, thumbnail
details, and its `publication_identity`. This is a local-only checkpoint: no
YouTube API call has occurred.

Validate streams and duration using the FFmpeg tools bundled in the worker:

```bash
docker compose exec -T worker \
  ffprobe -v error \
  -show_entries stream=codec_type,codec_name,width,height \
  -show_entries format=duration,size \
  -of json \
  "/app/data/artifacts/$JOB/final.mp4" | jq
```

For the default 30-second smoke test, duration should be approximately
24–36 seconds. The output must contain both a video and an audio stream.

## 9. Approve the exact publication package

```bash
PUB_ID=$(
  curl -fsS "$BASE/api/jobs/$JOB/artifacts/publication_package" |
  jq -er '.publication_identity'
)

curl -fsS -X POST "$BASE/api/jobs/$JOB/approvals/publication_preparation" \
  -H 'Content-Type: application/json' \
  -d "$(jq -n --arg actor "$ACTOR" --arg id "$PUB_ID" \
    '{status:"approved",actor:$actor,reviewed_identity:$id}')" | jq
```

This confirms the exact final file, metadata, and thumbnail you reviewed. With
YouTube disabled, the expected final state is `publication_ready`; it does not
upload or publish anything.

```bash
until [[ "$(curl -fsS "$BASE/api/jobs/$JOB" | jq -r '.state')" == "publication_ready" ]]; do
  curl -fsS "$BASE/api/jobs/$JOB" | jq
  sleep 2
done

curl -fsS "$BASE/api/jobs/$JOB" | jq
```

## Optional: reject and revise a script

Reject only the script currently under review:

```bash
curl -fsS -X POST "$BASE/api/jobs/$JOB/approvals/script" \
  -H 'Content-Type: application/json' \
  -d "$(jq -n --arg actor "$ACTOR" \
    '{status:"rejected",actor:$actor}')" | jq
```

Then submit one revised valid `ContentPackage` JSON file which retains the
checkpointed request and sources:

```bash
SCRIPT_ID=$(curl -fsS -X POST "$BASE/api/jobs/$JOB/script-revision?actor=$ACTOR" \
  -H 'Content-Type: application/json' \
  --data-binary @revised-content-package.json | jq -er '.reviewed_identity')

curl -fsS -X POST "$BASE/api/jobs/$JOB/approvals/script" \
  -H 'Content-Type: application/json' \
  -d "$(jq -n --arg actor "$ACTOR" --arg id "$SCRIPT_ID" \
    '{status:"approved",actor:$actor,reviewed_identity:$id}')" | jq
```

The revision response supplies a new identity. Using it in approval ensures
the worker cannot apply approval for the rejected package to revised content.

## Useful diagnostics

```bash
docker compose ps
docker compose logs --tail=100 worker
docker compose logs --tail=100 web
curl -fsS "$BASE/healthz" | jq
curl -fsS "$BASE/api/jobs/$JOB" | jq
```

Updated workers emit JSON events including `job_claimed`, `state_transition`,
`waiting_for_approval`, `render_started`, and `render_completed`.
