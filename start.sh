#!/usr/bin/env bash
# Prospect Solution launcher for Linux and macOS.
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install --disable-pip-version-check -q -r requirements.txt
.venv/bin/python -m playwright install chromium
exec .venv/bin/python -m app "$@"
