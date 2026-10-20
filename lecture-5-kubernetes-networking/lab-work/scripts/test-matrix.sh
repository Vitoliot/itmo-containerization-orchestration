#!/usr/bin/env bash
# Reports expected vs actual, exits 1 if any mismatch. Requires ready nettest Pods.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${OUT:-$HERE/../results/matrix.csv}"
mkdir -p "$(dirname "$OUT")"
printf 'source,destination,expected,actual,result\n' > "$OUT"
failures=0
check() {
  local source="$1" dest="$2" expected="$3"
  shift 3
  if "$@" >/dev/null 2>&1; then actual=ALLOW; else actual=DENY; fi
  if [[ "$actual" == "$expected" ]]; then result=PASS; else result=FAIL; failures=$((failures+1)); fi
  printf '%s,%s,%s,%s,%s\n' "$source" "$dest" "$expected" "$actual" "$result" | tee -a "$OUT"
}
api='shop-shop-api.app.svc.cluster.local'
pg='shop-postgres-rw.app.svc.cluster.local'
py_pg='import socket; s=socket.create_connection(("shop-postgres-rw.app.svc.cluster.local",5432),3); s.close()'
py_api='import socket; s=socket.create_connection(("shop-shop-api.app.svc.cluster.local",8080),3); s.close()'
check client api ALLOW kubectl exec -n nettest client -- curl -fsS --max-time 4 "http://$api:8080/health"
check intruder api DENY kubectl exec -n nettest intruder -- curl -fsS --max-time 3 "http://$api:8080/health"
check api postgres ALLOW kubectl exec -n app deploy/shop-shop-api -- python -c "$py_pg"
check worker postgres ALLOW kubectl exec -n app deploy/shop-shop-worker -- python -c "$py_pg"
check intruder postgres DENY kubectl exec -n nettest intruder -- nc -z -w 3 "$pg" 5432
check worker api DENY kubectl exec -n app deploy/shop-shop-worker -- python -c "$py_api"
printf 'Mismatches: %d\n' "$failures"
exit $((failures > 0))
