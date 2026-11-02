"""Offline export orchestration for Garmin training reports.

Composes storage, normalization, FIT analysis, and reporting without importing
from the compatibility facade in core.py. External time/date and legacy report
callbacks are injected to preserve behavior and existing mock/test seams.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Callable

from .normalization import activity_row, wellness_row
from .storage import atomic_json, atomic_text, csv_output, load_rows


@dataclass(frozen=True)
class ExportDependencies:
    activity_columns: list[str]
    wellness_columns: list[str]
    local_today: Callable[[], date]
    now: Callable[[], datetime]
    week_summary: Callable[..., str]
    coach_context: Callable[..., str]


def generate_exports(private_dir: Path, export_dir: Path, goals: str = '', today: date | None = None, *, deps: ExportDependencies) -> dict:
    activities = sorted(load_rows(private_dir / 'activities', activity_row), key=lambda r: (r.get('date',''), str(r.get('activity_id',''))))
    wellness = sorted(load_rows(private_dir / 'wellness', wellness_row), key=lambda r: r.get('date',''))
    csv_output(export_dir / 'activities.csv', deps.activity_columns, activities)
    csv_output(export_dir / 'wellness.csv', deps.wellness_columns, wellness)
    atomic_text(export_dir / 'weekly_summary.md', deps.week_summary(activities, today=today))
    atomic_text(export_dir / 'coach_context.md', deps.coach_context(activities, wellness, goals, today=today))
    # Analytical outputs. All series are reduced to aggregates; no GPS position is shared.
    from .fit_analysis import fit_reports, FIT_FIELDS, LAP_FIELDS
    from .analytics import compute, make_report, WEEKLY_COLUMNS
    fit_data, laps = fit_reports(private_dir, activities)
    csv_output(export_dir / 'fit_metrics.csv', FIT_FIELDS, fit_data)
    csv_output(export_dir / 'laps.csv', LAP_FIELDS, laps)
    metrics = compute(activities, wellness, fit_data, today or deps.local_today())
    csv_output(export_dir / 'weekly_metrics.csv', WEEKLY_COLUMNS, metrics['weekly'])
    atomic_json(export_dir / 'training_metrics.json', metrics)
    atomic_text(export_dir / 'training_analysis.md', make_report(metrics, goals))
    index = {'generated_at': deps.now().isoformat(), 'activities': len(activities), 'wellness_days': len(wellness), 'source': 'Garmin Connect Personal API', 'privacy': 'No GPS track points in exported files', 'version': '0.2', 'fit_ok': sum(r.get('fit_status') == 'ok' for r in fit_data), 'fit_missing': sum(r.get('fit_status') == 'not_downloaded' for r in fit_data)}
    atomic_json(export_dir / 'latest_sync.json', index)
    return index
