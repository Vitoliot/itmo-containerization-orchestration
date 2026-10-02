#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
API_DIR="$ROOT/api"
CGROUP="/sys/fs/cgroup/${CGROUP_NAME:-mydocker}"
VENV="${VENV:-/tmp/lab1-venv}"
SECCOMP="${SECCOMP:-/tmp/seccomp-run}"
HOST_IP="${HOST_IP:-10.200.1.1}"
CONT_IP="${CONT_IP:-10.200.1.2}"
PORT="${PORT:-8080}"
READY="/tmp/mydocker-ready.$$"

die() { echo "mydocker: $*" >&2; exit 1; }

command -v unshare >/dev/null || die "нужен unshare"
command -v ip >/dev/null || die "нужен ip"
command -v setpriv >/dev/null || die "нужен setpriv"
[[ -x "$VENV/bin/uvicorn" ]] || die "нет $VENV"
[[ -x "$SECCOMP" ]] || die "нет $SECCOMP"
[[ -f "$API_DIR/main.py" ]] || die "нет main.py"

sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0 >/dev/null
sudo ip link del veth-host 2>/dev/null || true
rm -f "$READY"
sudo mkdir -p "$CGROUP"

echo 100M | sudo tee "$CGROUP/memory.max" >/dev/null
echo 0 | sudo tee "$CGROUP/memory.swap.max" >/dev/null
echo '50000 100000' | sudo tee "$CGROUP/cpu.max" >/dev/null
echo 64 | sudo tee "$CGROUP/pids.max" >/dev/null


echo $$ | sudo tee "$CGROUP/cgroup.procs" >/dev/null


unshare --pid --mount --net --uts --ipc --user --map-root-user --fork -- bash -c "
set -e
mount -t proc proc /proc
hostname mydocker

# ждём, пока хост сунет нам veth-cont
for i in \$(seq 1 100); do
  if ip link show veth-cont >/dev/null 2>&1; then
    break
  fi
  sleep 0.1
done
ip link show veth-cont >/dev/null 2>&1 || { echo 'mydocker: veth-cont так и не пришёл' >&2; exit 1; }

ip link set lo up
ip addr add ${CONT_IP}/24 dev veth-cont
ip link set veth-cont up

# сигнал хосту: сеть готова
touch '$READY'

cd '$API_DIR'
exec setpriv --bounding-set=-all --inh-caps=-all --ambient-caps=-all -- \
  '$SECCOMP' \
  '$VENV/bin/uvicorn' main:app --host 0.0.0.0 --port '$PORT'
" &
UNSHARE_PID=$!
sleep 0.3

NS_PID="$(pgrep -P "$UNSHARE_PID" | head -n1 || true)"
[[ -n "$NS_PID" ]] || die "не нашёл PID внутри unshare"
echo "$NS_PID" | sudo tee "$CGROUP/cgroup.procs" >/dev/null


sudo ip link add veth-host type veth peer name veth-cont
sudo ip link set veth-cont netns "$NS_PID"
sudo ip addr add "${HOST_IP}/24" dev veth-host
sudo ip link set veth-host up


for i in $(seq 1 100); do
  [[ -f "$READY" ]] && break
  sleep 0.1
done
[[ -f "$READY" ]] || die "контейнер не поднял сеть"
rm -f "$READY"

cleanup() {
  kill "$UNSHARE_PID" 2>/dev/null || true
  wait "$UNSHARE_PID" 2>/dev/null || true
  sudo ip link del veth-host 2>/dev/null || true
}
trap cleanup EXIT

echo "mydocker: host PID=$NS_PID"
echo "mydocker: curl http://${CONT_IP}:${PORT}/health"
echo "mydocker: Ctrl+C остановит"


wait "$UNSHARE_PID"
