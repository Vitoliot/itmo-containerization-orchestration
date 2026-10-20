#!/usr/bin/env bash
# Destroy ONE ready pod per interval. Wait for full deployment recovery before next deletion.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${OUT:-$HERE/../results/chaos.csv}"
COUNT="${1:-20}"
mkdir -p "$(dirname "$OUT")"
printf 'timestamp,workload,pod\n' > "$OUT"
for ((i=1;i<=COUNT;i++)); do
  kubectl rollout status -n app deploy/shop-shop-api --timeout=180s >/dev/null
  kubectl rollout status -n app deploy/shop-shop-worker --timeout=180s >/dev/null
  workload=$(printf 'api\nworker\n' | shuf -n1)
  pod=$(kubectl get pod -n app -l "app.kubernetes.io/name=$workload,app.kubernetes.io/instance=shop" -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' | shuf -n1)
  if [[ -z "$pod" ]]; then echo 'No pod found' >&2; exit 1; fi
  printf '%s,%s,%s\n' "$(date +%s)" "$workload" "$pod" | tee -a "$OUT"
  kubectl delete pod -n app "$pod" --wait=false >/dev/null
  sleep 6
done
echo "Events: $OUT"
