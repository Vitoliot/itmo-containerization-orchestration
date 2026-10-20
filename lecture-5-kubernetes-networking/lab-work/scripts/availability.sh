#!/usr/bin/env bash
# Client is INSIDE cluster and calls Service via Kubernetes DNS, not Pod IP.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${OUT:-$HERE/../results/availability.csv}"
N="${1:-300}"
DELAY="${2:-0.4}"
mkdir -p "$(dirname "$OUT")"
kubectl exec -n nettest client -- sh -c '
  printf "timestamp,seq,http_code,success,failed\n"
  n="$1"; delay="$2"; i=1
  while [ "$i" -le "$n" ]; do
    ts=$(date +%s)
    code=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 3 http://shop-shop-api.app.svc.cluster.local:8080/health 2>/dev/null) || code=000
    if [ "$code" = "200" ]; then ok=1; bad=0; else ok=0; bad=1; fi
    printf "%s,%s,%s,%s,%s\n" "$ts" "$i" "$code" "$ok" "$bad"
    sleep "$delay"
    i=$((i+1))
  done
' sh "$N" "$DELAY" > "$OUT"
echo "CSV: $OUT"
awk -F, 'NR>1 {s+=$4;f+=$5} END {print "Succeeded:",s,"Failed:",f}' "$OUT"
