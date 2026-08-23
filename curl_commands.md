BASE=http://127.0.0.1:8081

NEW_JOB=$(
  curl -fsS -X POST "$BASE/api/jobs" \
    -H 'Content-Type: application/json' \
    -d '{
      "topic":"How rain forms",
      "angle":"A short educational explainer",
      "target_duration_seconds":30,
      "language":"en-IN",
      "audience":"general",
      "prompt_version":"test-v1",
      "sources":[
        {
          "source_id":"rain-reference",
          "url":"https://example.invalid/rain",
          "title":"Operator-supplied reference"
        }
      ]
    }' | jq -r '.id'
)

printf 'New job: %s\n' "$NEW_JOB"

------------

approval:
curl -fsS "$BASE/api/jobs/$NEW_JOB" | jq

------

Approve the script:
curl -fsS -X POST "$BASE/api/jobs/$NEW_JOB/approvals/script" \
  -H 'Content-Type: application/json' \
  -d '{"status":"approved","actor":"uditaswal"}'
  
  ---
  JOB=$NEW_JOB
  
  
  --- check status
  curl -s "$BASE/api/jobs/$JOB" | jq