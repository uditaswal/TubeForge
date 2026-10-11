# Local API review workflow

The developer dashboard is `http://127.0.0.1:62065`. Use the signed-in Studio
for creation, revisions and media review. These curl examples inspect an
existing job and approve only an explicitly reviewed script. They do not publish.
Run from the repository root with curl, jq and Python 3 installed.

## Sign in without recording credentials

```bash
BASE=http://127.0.0.1:62065
REVIEW_DIR=$(mktemp -d -t tubeforge-review.XXXXXX)
chmod 700 "$REVIEW_DIR"
trap 'rm -rf "$REVIEW_DIR"' EXIT
read -r -p 'Operator username: ' TF_OPERATOR
read -r -s -p 'Password: ' TF_PASSWORD
printf '\n'
export TF_OPERATOR TF_PASSWORD
python3 -c 'import json,os; print(json.dumps({"username":os.environ["TF_OPERATOR"],"password":os.environ["TF_PASSWORD"]}))' |
  curl --fail-with-body -sS -c "$REVIEW_DIR/cookies" \
    -H 'Content-Type: application/json' --data-binary @- "$BASE/login"
unset TF_PASSWORD
CSRF=$(awk '$6 == "tubeforge_csrf" {print $7}' "$REVIEW_DIR/cookies")
CSRF=$(python3 -c 'import sys,urllib.parse; print(urllib.parse.unquote(sys.argv[1]))' "$CSRF")
```

Cookie files are temporary credentials; do not commit them. Login must succeed
before proceeding. Do not disable production authentication to run examples.

## Inspect the job and exact revision

```bash
curl -fsS -b "$REVIEW_DIR/cookies" "$BASE/healthz" | jq
curl -fsS -b "$REVIEW_DIR/cookies" "$BASE/api/jobs" | jq
read -r -p 'Job ID to review: ' JOB
curl -fsS -b "$REVIEW_DIR/cookies" "$BASE/api/jobs/$JOB" | jq
curl -fsS -b "$REVIEW_DIR/cookies" "$BASE/api/jobs/$JOB/script" \
  -o "$REVIEW_DIR/script.json"
jq -r '.package.script_sections[].narration' "$REVIEW_DIR/script.json"
jq '.package.request.sources, .package.claims, .skill_checks' "$REVIEW_DIR/script.json"
```

Review the whole narration, source grounding and production directions. The
job must be waiting for script approval. A source-blocked job has no acceptable
script and must not be approved. Any saved revision requires a fresh review.

## Approve the reviewed script

Run this only after reviewing the saved response above:

```bash
jq --arg actor "$TF_OPERATOR" \
  '{status:"approved", actor:$actor, reviewed_identity:.reviewed_identity}' \
  "$REVIEW_DIR/script.json" |
  curl --fail-with-body -sS -b "$REVIEW_DIR/cookies" \
    -H 'Content-Type: application/json' -H "x-csrf-token: $CSRF" \
    --data-binary @- "$BASE/api/jobs/$JOB/approvals/script" | jq
curl -fsS -b "$REVIEW_DIR/cookies" "$BASE/api/jobs/$JOB/events" | jq
```

The stored identity pins approval to that revision. The worker produces a local
preview after durable approval; open it in Studio and inspect audio, pacing,
visuals and captions. Preview approval and publication are separate decisions;
this guide does not issue either one.

## Isolated offline smoke testing

`scripts/test_offline_workflow.sh` is a development helper for an isolated stack
with fake content/voice/media providers, publishing disabled and authentication
disabled. It automatically approves local gates and must not be pointed at
production. It checks provider/publishing settings before creating a job.
`scripts/test_script_config.sh` supplies example environment values. For current
production setup and approval policy, use [the operator guide](../../readme.md).
