#!/usr/bin/env bash
# Run a complete safe TubeForge smoke test against an already-running Compose stack.
# It creates a new job, automatically approves local gates, and never publishes.

set -Eeuo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8081}"
ACTOR="${ACTOR:-offline-smoke-test}"
TARGET_DURATION_SECONDS="${TARGET_DURATION_SECONDS:-30}"
POLL_SECONDS="${POLL_SECONDS:-2}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-300}"

for command in curl docker jq awk; do
  command -v "$command" >/dev/null || {
    printf 'Required command is unavailable: %s\n' "$command" >&2
    exit 2
  }
done

temporary_dir="$(mktemp -d -t tubeforge-offline-smoke.XXXXXX)"
trap 'rm -rf "$temporary_dir"' EXIT

api_get() {
  curl -fsS "$BASE_URL$1"
}

job_state() {
  api_get "/api/jobs/$JOB_ID" | jq -er '.state'
}

fail_if_terminal_error() {
  local current_state
  current_state="$(job_state)"
  case "$current_state" in
    failed_retryable|failed_validation|failed_exhausted|auth_required|cancelled)
      printf 'Job ended unexpectedly:\n' >&2
      api_get "/api/jobs/$JOB_ID" | jq >&2
      exit 1
      ;;
  esac
}

wait_for_state() {
  local expected="$1"
  local deadline=$((SECONDS + TIMEOUT_SECONDS))
  while (( SECONDS < deadline )); do
    fail_if_terminal_error
    if [[ "$(job_state)" == "$expected" ]]; then
      return 0
    fi
    sleep "$POLL_SECONDS"
  done
  printf 'Timed out waiting for %s. Current job payload:\n' "$expected" >&2
  api_get "/api/jobs/$JOB_ID" | jq >&2
  exit 1
}

approve() {
  local gate="$1"
  local identity="${2:-}"
  local payload
  if [[ -n "$identity" ]]; then
    payload="$(jq -n --arg actor "$ACTOR" --arg identity "$identity" \
      '{status:"approved", actor:$actor, reviewed_identity:$identity}')"
  else
    payload="$(jq -n --arg actor "$ACTOR" '{status:"approved", actor:$actor}')"
  fi
  curl -fsS -X POST "$BASE_URL/api/jobs/$JOB_ID/approvals/$gate" \
    -H 'Content-Type: application/json' \
    -d "$payload" | jq
}

printf 'Checking the API and safe offline configuration...\n'
api_get '/healthz' | jq
docker compose exec -T worker python -c '
from tubeforge.core.config import load_settings
settings = load_settings()
safe = (
    settings.pipeline.content_provider == "fake"
    and settings.pipeline.voice_provider == "fake"
    and settings.pipeline.media.provider == "fake"
    and not settings.pipeline.youtube.enabled
)
raise SystemExit(0 if safe else 1)
' || {
  printf 'Refusing to run: this script requires fake content, voice, media, and disabled YouTube publishing.\n' >&2
  exit 2
}

request="$(jq -n --argjson duration "$TARGET_DURATION_SECONDS" '
  {
    topic: "How rain forms",
    angle: "A short educational offline smoke test",
    target_duration_seconds: $duration,
    language: "en-IN",
    audience: "general",
    prompt_version: "offline-smoke-v1",
    sources: [{
      source_id: "rain-reference",
      url: "https://example.invalid/rain",
      title: "Operator-supplied offline reference"
    }]
  }
')"

JOB_ID="$(curl -fsS -X POST "$BASE_URL/api/jobs" -H 'Content-Type: application/json' -d "$request" | jq -er '.id')"
printf 'Created job: %s\n' "$JOB_ID"

wait_for_state 'script_approval_required'
printf 'Approving script...\n'
approve 'script'

wait_for_state 'preview_ready'
preview_identity="$(api_get "/api/jobs/$JOB_ID/artifacts/preview_manifest" | jq -er '.render_identity')"
printf 'Approving preview identity: %s\n' "$preview_identity"
approve 'preview' "$preview_identity"

wait_for_state 'publication_approval_required'
publication_identity="$(api_get "/api/jobs/$JOB_ID/artifacts/publication_package" | jq -er '.publication_identity')"
printf 'Approving publication package identity: %s\n' "$publication_identity"
approve 'publication_preparation' "$publication_identity"

wait_for_state 'publication_ready'

printf 'Testing registered artifact retrieval...\n'
curl -fsS "$BASE_URL/api/jobs/$JOB_ID/artifacts/final.mp4" -o "$temporary_dir/final.mp4"
test -s "$temporary_dir/final.mp4"

printf 'Validating final video inside the worker container...\n'
probe="$(docker compose exec -T worker ffprobe -v error \
  -show_entries stream=codec_type,codec_name,width,height \
  -show_entries format=duration,size \
  -of json "/app/data/artifacts/$JOB_ID/final.mp4")"
printf '%s\n' "$probe" | jq
printf '%s\n' "$probe" | jq -e --argjson target "$TARGET_DURATION_SECONDS" '
  (.format.duration | tonumber) as $duration
  | ([.streams[] | select(.codec_type == "video" and (.width | tonumber) > 0 and (.height | tonumber) > 0)] | length == 1)
  and ([.streams[] | select(.codec_type == "audio")] | length == 1)
  and ($duration >= ($target * 0.80))
  and ($duration <= ($target * 1.20))
' >/dev/null || {
  printf 'Final video does not meet the stream or requested-duration acceptance criteria.\n' >&2
  exit 1
}

printf '\nPASS: Offline workflow completed safely.\n'
printf 'Job ID: %s\n' "$JOB_ID"
printf 'Final state: publication_ready\n'
printf 'Final artifact: data/artifacts/%s/final.mp4\n' "$JOB_ID"
