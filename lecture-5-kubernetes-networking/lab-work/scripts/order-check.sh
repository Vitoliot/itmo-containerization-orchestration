#!/usr/bin/env bash
# Demonstrates actual API -> PostgreSQL <- worker workflow.
set -euo pipefail
API='http://shop-shop-api.app.svc.cluster.local:8080'
order=$(kubectl exec -n nettest client -- curl -fsS --max-time 5 -X POST "$API/order" -H 'Content-Type: application/json' -d '{"item":"lab5-network-test"}')
order_id=$(printf '%s' "$order" | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
printf 'Order created: %s\n' "$order"
for ((i=1;i<=30;i++)); do
  current=$(kubectl exec -n nettest client -- curl -fsS --max-time 5 "$API/orders/$order_id")
  status=$(printf '%s' "$current" | python3 -c 'import sys,json;print(json.load(sys.stdin)["status"])')
  echo "Order $order_id: $status"
  if [[ "$status" == 'processed' ]]; then
    echo 'PASS: worker processed order via PostgreSQL'
    exit 0
  fi
  sleep 1
done
echo 'FAIL: order stayed pending (investigate worker -> PostgreSQL)' >&2
exit 1
