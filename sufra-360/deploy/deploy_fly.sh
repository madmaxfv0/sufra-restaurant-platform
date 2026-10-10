#!/bin/sh
# Put SUFRA 360 and SUFRA OS on Fly.io. Safe to run again to ship an update.
#
#   sh deploy/deploy_fly.sh                       uses sufra-360 / sufra-os
#   sh deploy/deploy_fly.sh my-360 my-os          if those names are taken
#
# Before the first run:  install flyctl, then `fly auth login`.
set -e
APP_360="${1:-sufra-360}"
APP_OS="${2:-sufra-os}"
REGION="${FLY_REGION:-fra}"
DIR_360="$(cd "$(dirname "$0")/.." && pwd)"
DIR_OS="${SUFRA_OS_DIR:-$DIR_360/../sufra-os}"

command -v fly >/dev/null || { echo "flyctl is not installed: https://fly.io/docs/flyctl/install/"; exit 1; }
fly auth whoami >/dev/null || { echo "Not signed in. Run: fly auth login"; exit 1; }
[ -d "$DIR_OS/app" ] || { echo "SUFRA OS not found at $DIR_OS (set SUFRA_OS_DIR)"; exit 1; }

echo "== SUFRA OS -> https://$APP_OS.fly.dev"
cd "$DIR_OS"
SUFRA_360_DIR="$DIR_360" sh deploy/prepare.sh
fly status -a "$APP_OS" >/dev/null 2>&1 || fly apps create "$APP_OS"
fly volumes list -a "$APP_OS" | grep -q sufra_os_data \
  || fly volumes create sufra_os_data --size 1 --region "$REGION" -a "$APP_OS" --yes
# the key that signs staff QR logins: keep the one already in use, never print it
if [ -f .staff-qr.key ]; then
  fly secrets set --stage -a "$APP_OS" SUFRA_STAFF_QR_KEY="$(cat .staff-qr.key)" >/dev/null
fi
fly deploy -a "$APP_OS" --ha=false \
  --env SUFRA_360_ORIGIN="https://$APP_360.fly.dev" \
  --env SUFRA_PUBLIC_URL="https://$APP_OS.fly.dev"

echo "== SUFRA 360 -> https://$APP_360.fly.dev"
cd "$DIR_360"
fly status -a "$APP_360" >/dev/null 2>&1 || fly apps create "$APP_360"
# SUFRA 360 talks to the OS over Fly's private network, not the public internet
fly deploy -a "$APP_360" --ha=false \
  --env SUFRA_OS_BASE="http://$APP_OS.internal:8123"

echo
echo "Guests:  https://$APP_360.fly.dev"
echo "Staff:   https://$APP_OS.fly.dev"
