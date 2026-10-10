#!/bin/sh
# Run before every `fly deploy` of SUFRA OS (deploy_fly.sh does this for you).
set -e
cd "$(dirname "$0")/.."
VENUE_SRC="${SUFRA_360_DIR:-../sufra-360}/venue"

# A consistent snapshot of the live database, WAL included. Copying nova.db
# on its own would silently drop whatever is still sitting in nova.db-wal.
rm -f deploy/seed.db
sqlite3 nova.db ".backup 'deploy/seed.db'"
echo "[prepare] database snapshot: $(du -h deploy/seed.db | cut -f1)"

# SUFRA OS builds its table registry from the room SUFRA 360 draws.
rm -rf deploy/venue
mkdir -p deploy/venue
cp "$VENUE_SRC"/*.json deploy/venue/
echo "[prepare] venue files: $(ls deploy/venue | tr '\n' ' ')"
