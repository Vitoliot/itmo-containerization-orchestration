#!/usr/bin/env bash
set -euo pipefail
for cmd in docker kind kubectl helm python3; do
  command -v "$cmd" >/dev/null || { echo "Missing command: $cmd" >&2; exit 1; }
done
if ! docker info >/dev/null 2>&1; then
  echo "Docker daemon is unavailable (user permissions?)" >&2
  exit 1
fi
printf 'kubectl: '; kubectl version --client -o yaml | grep gitVersion | head -1
printf 'kind: '; kind version
printf 'helm: '; helm version --short
echo 'Prerequisites detected. Verify available RAM >= 8 GiB for 3-node kind + monitoring.'
