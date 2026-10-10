#!/bin/zsh
set -e
cd "$(dirname "$0")"
echo "Starting SUFRA from: $PWD"
if [ ! -x .venv/bin/python3 ]; then
  echo "Creating local Python environment..."
  python3 -m venv .venv
fi
source .venv/bin/activate
if ! python3 -c 'import uvicorn, fastapi, sqlmodel, jinja2, numpy, qrcode, cryptography' >/dev/null 2>&1; then
  echo "Installing SUFRA requirements..."
  python3 -m pip install --upgrade pip
  python3 -m pip install -r deploy/requirements.lock
fi
python3 start_all.py
