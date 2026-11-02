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


## Runtime-aware health diagnostics

The health checker resolves `GARMIN_PRIVATE_DIR` and `GARMIN_EXPORT_DIR` from
process environment variables first, then `.env`, falling back to the project
folders. Relative directory values are resolved from the repository root,
matching the daily runner. It parses configuration locally but **does not
print or export secrets or configured paths**.

On macOS, the default check also invokes `launchctl print` to verify the job
is loaded in the current user's GUI session; its raw output is never shown.
The existing plist validation still verifies the configured 07:00 schedule.
A registered job is not proof that an individual run succeeded; check recent
sync metadata and OS logs when diagnosing failures. Custom `--launch-agent`
fixtures skip the active-service check, making tests safe and deterministic.

These checks are read-only. They neither load nor unload jobs, synchronize
Garmin data, update checkpoints, or change scheduled times.
