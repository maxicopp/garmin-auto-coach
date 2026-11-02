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

## Normalization boundary (second incremental refactor)

- `normalization.py`: pure helpers for Garmin activity and wellness data,
  numeric conversion, dates, and running classification. It depends only on
  Python's standard library.
- `core.py`: re-exports the same helper names for backward compatibility.
  Report generation, source files, CLI options, and output formats are unchanged.
- `storage.py`: remains responsible for local persistence and serialization.

Golden regression snapshots and offline unit tests must pass unchanged. Never
regenerate the approved golden baseline just to make a refactor pass.

## Reporting boundary (third incremental refactor)

- `reporting.py` renders weekly summaries and coach context from normalized
  inputs. It only imports pure normalization helpers; callers supply the
  reference date explicitly. No filesystem, API, or network access is required.
- `core.py` retains the same public `fmt`, `week_summary`, and `coach_context`
  signatures, and resolves the default date using the original `local_today`
  function before delegating to `reporting.py`.
- `core.generate_exports`, the existing timezone, CSV/JSON serialization,
  training formulas, FIT analysis, and Garmin synchronization stay untouched.

All committed golden regression snapshots must match exactly; do not regenerate
snapshots to make a refactor pass. Review the PR and its CI status before merge.
