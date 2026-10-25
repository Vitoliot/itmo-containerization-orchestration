#!/usr/bin/env bash
# Inject ONE randomly chosen fault THROUGH values/Helm, not kubectl patch.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
CHART="$HERE/../chart/shop"
FAULT=$(printf 'api-egress\nworker-egress\nwrong-port\ndns\n' | shuf -n1)
mkdir -p "$HERE/../results"
printf '%s\n' "$FAULT" > "$HERE/../results/.fault-answer.txt"
opts=(--set networkPolicy.enabled=true)
case "$FAULT" in
  api-egress) opts+=(--set networkPolicy.allowApiToPostgres=false);;
  worker-egress) opts+=(--set networkPolicy.allowWorkerToPostgres=false);;
  wrong-port) opts+=(--set networkPolicy.postgresPort=5433);;
  dns) opts+=(--set networkPolicy.allowDns=false);;
esac
helm upgrade shop "$CHART" -n app -f "$CHART/values.yaml" "${opts[@]}"
echo 'One fault injected. Diagnose via orders, matrix and Hubble; do not inspect results/.fault-answer.txt until after diagnosis.'
