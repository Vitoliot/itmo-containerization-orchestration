#!/usr/bin/env bash

set -euo pipefail

if [ "$#" -ne 4 ]; then
  echo "Usage: $0 <owner> <repository> <failed-run-id> <head-sha>" >&2
  exit 2
fi

owner="$1"
repository="$2"
run_id="$3"
head_sha="$4"
webhook_url="${N8N_WEBHOOK_URL:-http://127.0.0.1:5678/webhook/ci-failure}"

if ! [[ "$run_id" =~ ^[0-9]+$ ]]; then
  echo "failed-run-id must be numeric" >&2
  exit 2
fi

jq -n \
  --arg owner "$owner" \
  --arg repository "$repository" \
  --argjson run_id "$run_id" \
  --arg head_sha "$head_sha" \
  '{
    action: "completed",
    workflow_run: {
      id: $run_id,
      status: "completed",
      conclusion: "failure",
      head_sha: $head_sha,
      repository: {
        name: $repository,
        owner: {login: $owner}
      }
    },
    repository: {
      name: $repository,
      owner: {login: $owner}
    }
  }' | curl --fail-with-body --silent --show-error \
    --max-time 600 \
    --request POST \
    --header 'Content-Type: application/json' \
    --data-binary @- \
    "$webhook_url"

echo
