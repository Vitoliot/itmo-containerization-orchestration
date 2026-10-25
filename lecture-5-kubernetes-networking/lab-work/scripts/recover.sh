#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
CHART="$HERE/../chart/shop"
helm upgrade shop "$CHART" -n app -f "$CHART/values.yaml" --set networkPolicy.enabled=true
kubectl rollout status -n app deployment/shop-shop-api --timeout=180s
kubectl rollout status -n app deployment/shop-shop-worker --timeout=180s
echo 'Baseline zero-trust policies restored; rerun test-matrix.sh and order-check.sh.'
