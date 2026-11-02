#!/bin/bash
set -euo pipefail
PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ ! -x "$PROJECT/.venv/bin/python" ]]; then
  echo 'Falta .venv. Seguí los pasos del README.' >&2
  exit 2
fi
cd "$PROJECT"
exec "$PROJECT/.venv/bin/python" -m garmin_auto_coach sync --initial-days 90 --lookback-days 14 --wellness-days 14 --download-originals
