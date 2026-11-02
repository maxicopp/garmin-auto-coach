# Synchronization resilience: current behavior

These tests document current Garmin synchronization behavior using synthetic,
offline data. They do not exercise a real Garmin account or make network calls.

## Established behavior

- Activity search pagination handles multiple pages without dropping entries.
- Invalid activity identifiers are skipped.
- Unchanged activity digests avoid repeated detail downloads.
- A failed detail request leaves the previously stored record unchanged.
- Invalid original ZIP responses are not cached and do not stop activity sync.
- If an individual wellness request fails, a previously cached value is reused
  when available. Other wellness fields may still be refreshed.
- An unhandled failure before the final checkpoint write leaves the previous
  `state.json` checkpoint in place. Already written individual records may
  remain and be revisited on the next synchronization.

## Known limits (not changed by this PR)

- The application does not implement its own retry/backoff policy for Garmin
  requests. Any retries provided by the external API client are independent.
- Per-field wellness errors are caught and reported; a run can complete with
  missing wellness fields and still advance its synchronization checkpoint.
- Unit tests cannot establish actual Garmin API uptime or authentication success.
- This PR adds tests and documentation only; it does not change synchronization
  algorithms, persisted schemas, CLI behavior, report formats, or schedules.

## Verification

Run from the repository root in the configured Python environment:

```bash
python -B -m unittest discover -s tests -v
```

Do not replace approved golden fixtures to make tests pass. Apply any future
network reliability changes in a separate PR after defining expected behavior.
