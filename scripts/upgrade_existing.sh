#!/bin/bash
# Actualiza solo código; conserva la API key, el historial, los FIT, el .venv y la tarea launchd.
set -euo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${1:-$HOME/Projects/garmin-auto-coach}"
if [[ ! -d "$DEST/garmin_auto_coach" || ! -f "$DEST/.env" || ! -d "$DEST/.venv" ]]; then
  echo "No encontré una instalación existente con .env y .venv en: $DEST" >&2
  exit 2
fi
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$DEST/code-backups/pre-v02-$STAMP"
mkdir -p "$BACKUP"
cp -R "$DEST/garmin_auto_coach" "$BACKUP/"
cp -R "$DEST/scripts" "$BACKUP/"
if [[ -d "$DEST/tests" ]]; then cp -R "$DEST/tests" "$BACKUP/"; fi
if [[ -f "$DEST/requirements.txt" ]]; then cp "$DEST/requirements.txt" "$BACKUP/"; fi

mkdir -p "$DEST/garmin_auto_coach" "$DEST/scripts" "$DEST/tests"
rsync -a "$SRC/garmin_auto_coach/" "$DEST/garmin_auto_coach/"
rsync -a "$SRC/scripts/" "$DEST/scripts/"
rsync -a "$SRC/tests/" "$DEST/tests/"
cp "$SRC/requirements.txt" "$DEST/requirements.txt"
cp "$SRC/README.md" "$DEST/README.md"
cp "$SRC/AGENT_CONTEXT.md" "$DEST/AGENT_CONTEXT.md"
cd "$DEST"
"$DEST/.venv/bin/python" -m pip install -r requirements.txt
"$DEST/.venv/bin/python" -m unittest discover -s tests -v
"$DEST/.venv/bin/python" -m garmin_auto_coach report
printf '\nActualización v0.2 instalada. Código anterior: %s\n' "$BACKUP"
printf 'Se conservaron .env, private-data, exports y la tarea de las 07:00.\n'
printf 'Para descargar archivos FIT históricos: .venv/bin/python -m garmin_auto_coach backfill-originals --limit 50\n'
