#!/usr/bin/env bash
# Start SUFRA OS and SUFRA 360 together on a local demo database.
#
#   scripts/start_demo.sh
#
# First run: creates .venv, installs the pinned dependencies and seeds
# sufra-os/nova.db with synthetic data. The demo staff PINs are printed once,
# when the database is seeded. Delete sufra-os/nova.db to seed again.
#
# Ports can be changed:  OS_PORT=9123 S360_PORT=9013 scripts/start_demo.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"
OS_PORT="${OS_PORT:-8123}"
S360_PORT="${S360_PORT:-8013}"

[ -d .venv ] || "$PY" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r sufra-os/deploy/requirements.lock

export NOVA_SEED_DEMO=1
export SUFRA_360_ORIGIN="http://127.0.0.1:$S360_PORT"
export SUFRA_OS_BASE="http://127.0.0.1:$OS_PORT"

(cd sufra-os && exec uvicorn app.main:app --port "$OS_PORT") &
OS_PID=$!
trap 'kill "$OS_PID" 2>/dev/null || true' EXIT

for _ in $(seq 1 60); do
  curl -sf "http://127.0.0.1:$OS_PORT/api/build" >/dev/null && break
  sleep 1
done

echo
echo "  Staff apps (SUFRA OS):   http://127.0.0.1:$OS_PORT"
echo "  Guest 3D venue (360):    http://127.0.0.1:$S360_PORT"
echo "  Ctrl+C stops both."
echo
cd sufra-360 && uvicorn app.main:app --port "$S360_PORT"
