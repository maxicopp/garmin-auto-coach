# Architecture — first incremental refactor

The project remains a CLI. The initial improvement separates low-level file
operations from activity normalization and report generation.

- `storage.py`: local JSON/CSV persistence, atomic writes and content digests.
  It has **no dependencies on application modules**.
- `core.py`: legacy compatibility facade plus existing normalization and report
  composition. The six moved functions remain importable from `core.py`.
- `sync.py`: Garmin activity and wellness synchronization (unchanged).
- `fit_analysis.py`: FIT/ZIP parsing (unchanged).
- `analytics.py`: descriptive training metrics (unchanged).
- `__main__.py`: CLI and environment configuration (unchanged).

## Compatibility requirements

- Keep `doctor`, `sync`, `backfill-originals`, and `report` CLI behavior.
- Keep `.env`, `GARMIN_PRIVATE_DIR`, `GARMIN_EXPORT_DIR`, and
  `GARMIN_COACH_GOALS` semantics.
- Preserve JSON/CSV/Markdown encodings, line endings, filenames and values.
- Preserve incremental sync and existing local state/data.
- Never automatically update regression snapshots when running tests.

The next extraction (normalization, reports and orchestration) should be a
separate reviewable PR. CI must pass before merging this change into `main`.
