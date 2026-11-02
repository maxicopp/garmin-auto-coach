"""Pure normalization/reporting functions for Garmin Personal API responses.

Garmin API models may add or omit fields; missing measurements remain blank.
No location points or GPS tracks are copied to the shareable CSV/Markdown reports.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

# Backward-compatible re-exports; callers of core.py keep working.
from .storage import (atomic_json, atomic_text, json_file, digest, load_rows, csv_output)

# Re-export the original normalization API for existing callers.
# Dedicated pure Markdown renderers; legacy functions below remain stable.
from . import reporting

from .normalization import (
    find_key, as_number, rounded, iso_date, activity_kind,
    activity_row, wellness_row, is_running,
)

LOCAL_TZ = ZoneInfo('America/Argentina/Buenos_Aires')

ACTIVITY_COLUMNS = [
    'date', 'activity_id', 'name', 'type', 'distance_km', 'duration_min',
    'moving_min', 'pace_min_km', 'average_hr_bpm', 'max_hr_bpm',
    'ascent_m', 'descent_m', 'average_cadence_spm', 'aerobic_te',
    'anaerobic_te', 'average_power_w',
]
WELLNESS_COLUMNS = [
    'date', 'sleep_hours', 'sleep_score', 'hrv_last_night_ms',
    'hrv_weekly_avg_ms', 'hrv_status', 'body_battery_charged',
    'body_battery_drained',
]


def local_today() -> date:
    return datetime.now(LOCAL_TZ).date()


def fmt(value: Any, decimals: int = 1) -> str:
    return reporting.fmt(value, decimals)


def week_summary(rows: list[dict], weeks: int = 8, today: date | None = None) -> str:
    return reporting.week_summary(rows, weeks=weeks, today=today or local_today())


def coach_context(activities: list[dict], wellness: list[dict], goals: str, today: date | None = None) -> str:
    return reporting.coach_context(activities, wellness, goals, today=today or local_today())


def generate_exports(private_dir: Path, export_dir: Path, goals: str = '', today: date | None = None) -> dict:
    activities = sorted(load_rows(private_dir / 'activities', activity_row), key=lambda r: (r.get('date',''), str(r.get('activity_id',''))))
    wellness = sorted(load_rows(private_dir / 'wellness', wellness_row), key=lambda r: r.get('date',''))
    csv_output(export_dir / 'activities.csv', ACTIVITY_COLUMNS, activities)
    csv_output(export_dir / 'wellness.csv', WELLNESS_COLUMNS, wellness)
    atomic_text(export_dir / 'weekly_summary.md', week_summary(activities, today=today))
    atomic_text(export_dir / 'coach_context.md', coach_context(activities, wellness, goals, today=today))
    # Analytical outputs. All series are reduced to aggregates; no GPS position is shared.
    from .fit_analysis import fit_reports, FIT_FIELDS, LAP_FIELDS
    from .analytics import compute, make_report, WEEKLY_COLUMNS
    fit_data, laps = fit_reports(private_dir, activities)
    csv_output(export_dir / 'fit_metrics.csv', FIT_FIELDS, fit_data)
    csv_output(export_dir / 'laps.csv', LAP_FIELDS, laps)
    metrics = compute(activities, wellness, fit_data, today or local_today())
    csv_output(export_dir / 'weekly_metrics.csv', WEEKLY_COLUMNS, metrics['weekly'])
    atomic_json(export_dir / 'training_metrics.json', metrics)
    atomic_text(export_dir / 'training_analysis.md', make_report(metrics, goals))
    index = {'generated_at': datetime.now(LOCAL_TZ).isoformat(), 'activities': len(activities), 'wellness_days': len(wellness), 'source': 'Garmin Connect Personal API', 'privacy': 'No GPS track points in exported files', 'version': '0.2', 'fit_ok': sum(r.get('fit_status') == 'ok' for r in fit_data), 'fit_missing': sum(r.get('fit_status') == 'not_downloaded' for r in fit_data)}
    atomic_json(export_dir / 'latest_sync.json', index)
    return index
