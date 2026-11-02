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
    """Backward-compatible entrypoint for the offline export pipeline."""
    from .export_service import ExportDependencies, generate_exports as run_exports

    dependencies = ExportDependencies(
        activity_columns=ACTIVITY_COLUMNS,
        wellness_columns=WELLNESS_COLUMNS,
        local_today=local_today,
        now=lambda: datetime.now(LOCAL_TZ),
        week_summary=week_summary,
        coach_context=coach_context,
    )
    return run_exports(private_dir, export_dir, goals=goals, today=today, deps=dependencies)
