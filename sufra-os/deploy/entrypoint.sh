#!/bin/sh
# Runs on every boot of the hosted SUFRA OS.
set -e
mkdir -p /data/uploads /data/generated

# First boot only: the volume is empty, so start from the snapshot that was
# taken when the image was built. Every later boot keeps what is on the volume.
# The marker (not the database file) is what says "this volume was seeded", so
# a database left behind by a boot that crashed before it finished is replaced
# once, and kept aside rather than deleted.
if [ ! -f /data/.seeded ]; then
  echo "[entrypoint] seeding the database from the build snapshot"
  [ -f /data/nova.db ] && mv /data/nova.db /data/nova.db.pre-seed
  rm -f /data/nova.db-wal /data/nova.db-shm
  cp /srv/os/deploy/seed.db /data/nova.db
  touch /data/.seeded
fi

# Staff photos, menu photos and generated images are written under
# app/static. Point those folders at the volume so they survive a redeploy.
for d in uploads generated; do
  src="/srv/os/app/static/$d"
  if [ ! -L "$src" ]; then
    [ -d "$src" ] && cp -Rn "$src/." "/data/$d/" 2>/dev/null || true
    rm -rf "$src"
    ln -s "/data/$d" "$src"
  fi
done

# An empty host listens on every interface, IPv4 and IPv6 both. Fly's public
# proxy arrives over IPv4 and its private network (how SUFRA 360 reaches this
# app) over IPv6; "--host ::" was tested and answers IPv6 only.
exec uvicorn app.main:app --host '' --port 8123 --proxy-headers --forwarded-allow-ips '*'
