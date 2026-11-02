# Local health diagnostics

`scripts/healthcheck.py` is an optional, read-only operational check. It does
not communicate with Garmin, run synchronization, change scheduled jobs,
read `.env` content, or read activity/FIT files.

Run from the repository root:

```bash
.venv/bin/python -B scripts/healthcheck.py
.venv/bin/python -B scripts/healthcheck.py --json
```

Checks include the presence (not contents) of `.env` and `.venv`, daily runner,
last successful synchronization date from `private-data/state.json`, last
export creation timestamp from `exports/latest_sync.json`, and the user's macOS
launchd configuration when running on macOS.

Exit codes: `0` when healthy, `1` if warnings are present, `2` if an error is
detected. An absent or stale record is a diagnostic warning, not proof that
Garmin data has been lost. On non-macOS systems, launchd validation is skipped.

No secrets, activity names, GPS coordinates, or identifiers are printed.
Existing CLI behavior, data models, exports, analytics, launchd configuration,
and sync logic are unchanged.
