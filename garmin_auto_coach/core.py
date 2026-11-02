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










def find_key(obj: Any, *keys: str) -> Any:
    """Case-sensitive lookup on a limited tree; never invent a metric."""
    if isinstance(obj, dict):
        for key in keys:
            if key in obj and obj[key] is not None:
                return obj[key]
        for value in obj.values():
            if isinstance(value, dict):
                found = find_key(value, *keys)
                if found is not None:
                    return found
    return None


def as_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
        if out == float('inf') or out == float('-inf') or out != out:
            return None
        return out
    except (ValueError, TypeError):
        return None


def rounded(value: Any, digits: int = 1) -> float | None:
    val = as_number(value)
    return round(val, digits) if val is not None else None


def iso_date(value: Any) -> str:
    if isinstance(value, str):
        m = re.match(r'^\d{4}-\d{2}-\d{2}', value)
        if m:
            return m.group()
    return ''


def activity_kind(summary: dict, detail: dict) -> str:
    tp = summary.get('activityType') or detail.get('activityType') or {}
    if isinstance(tp, dict):
        return str(tp.get('typeKey') or tp.get('typeName') or 'unknown')
    return str(tp)


def activity_row(item: dict) -> dict:
    summary = item.get('search') or {}
    detail = item.get('detail') or {}
    if not isinstance(summary, dict):
        summary = {}
    if not isinstance(detail, dict):
        detail = {}
    # Search endpoint returns summary DTO, detail usually holds summaryDTO.
    dt_summary = detail.get('summaryDTO') if isinstance(detail.get('summaryDTO'), dict) else {}
    merged = {**summary, **dt_summary}
    activity_id = summary.get('activityId') or detail.get('activityId') or ''
    seconds = as_number(find_key(merged, 'duration', 'elapsedDuration'))
    moving = as_number(find_key(merged, 'movingDuration'))
    distance = as_number(find_key(merged, 'distance'))
    speed = as_number(find_key(merged, 'averageSpeed'))
    pace = 1000 / speed / 60 if speed and speed > 0 else (
        (moving or seconds) / (distance / 1000) / 60 if distance and distance > 0 and (moving or seconds) else None
    )
    timestamp = summary.get('startTimeLocal') or detail.get('startTimeLocal') or summary.get('startTimeGMT') or ''
    return {
        'date': iso_date(timestamp),
        'activity_id': activity_id,
        'name': summary.get('activityName') or detail.get('activityName') or '',
        'type': activity_kind(summary, detail),
        'distance_km': rounded(distance / 1000, 3) if distance is not None else None,
        'duration_min': rounded(seconds / 60, 1) if seconds is not None else None,
        'moving_min': rounded(moving / 60, 1) if moving is not None else None,
        'pace_min_km': rounded(pace, 2),
        'average_hr_bpm': rounded(find_key(merged, 'averageHR', 'averageHeartRate'), 0),
        'max_hr_bpm': rounded(find_key(merged, 'maxHR', 'maxHeartRate'), 0),
        'ascent_m': rounded(find_key(merged, 'elevationGain', 'totalAscent'), 0),
        'descent_m': rounded(find_key(merged, 'elevationLoss', 'totalDescent'), 0),
        'average_cadence_spm': rounded(find_key(merged, 'avgRunningCadenceInStepsPerMinute', 'averageRunningCadenceInStepsPerMinute', 'averageRunCadence'), 0),
        'aerobic_te': rounded(find_key(merged, 'aerobicTrainingEffect'), 1),
        'anaerobic_te': rounded(find_key(merged, 'anaerobicTrainingEffect'), 1),
        'average_power_w': rounded(find_key(merged, 'avgPower', 'averagePower'), 0),
    }


def wellness_row(item: dict) -> dict:
    sleep = item.get('sleep') or {}
    hrv = item.get('hrv') or {}
    battery = item.get('body_battery') or {}
    sleep_dto = sleep.get('dailySleepDTO', sleep) if isinstance(sleep, dict) else {}
    if not isinstance(sleep_dto, dict):
        sleep_dto = {}
    hrv_summary = hrv.get('hrvSummary', hrv) if isinstance(hrv, dict) else {}
    if not isinstance(hrv_summary, dict):
        hrv_summary = {}
    score = find_key(sleep_dto, 'overallSleepScore', 'sleepScore')
    sleep_scores = sleep.get('sleepScores') if isinstance(sleep, dict) else None
    if not isinstance(sleep_scores, dict):
        sleep_scores = sleep_dto.get('sleepScores')
    if score is None and isinstance(sleep_scores, dict):
        overall = sleep_scores.get('overall') or sleep_scores.get('overallScore')
        score = overall.get('value', overall.get('score')) if isinstance(overall, dict) else overall
    if isinstance(score, dict):
        score = score.get('value') or score.get('score')
    if score is None and isinstance(sleep, dict):
        score = find_key(sleep, 'overallSleepScore', 'sleepScore')
        if isinstance(score, dict):
            score = score.get('value') or score.get('score')
    total_seconds = as_number(find_key(sleep_dto, 'sleepTimeSeconds', 'totalSleepSeconds'))
    # No fallback to time in bed: it is not equivalent to sleep duration.
    bb = battery[0] if isinstance(battery, list) and battery and isinstance(battery[0], dict) else battery
    return {
        'date': item.get('date', ''),
        'sleep_hours': rounded(total_seconds / 3600, 2) if total_seconds is not None else None,
        'sleep_score': rounded(score, 0),
        'hrv_last_night_ms': rounded(find_key(hrv_summary, 'lastNightAvg'), 1),
        'hrv_weekly_avg_ms': rounded(find_key(hrv_summary, 'weeklyAvg'), 1),
        'hrv_status': hrv_summary.get('status') or '',
        'body_battery_charged': rounded(find_key(bb, 'chargedValue'), 0),
        'body_battery_drained': rounded(find_key(bb, 'drainedValue'), 0),
    }






def is_running(row: dict) -> bool:
    kind = str(row.get('type') or '').lower()
    return 'running' in kind or kind in {'run', 'trail_run', 'trailrunning'}


def fmt(value: Any, decimals: int = 1) -> str:
    n = as_number(value)
    return f'{n:.{decimals}f}' if n is not None else 's/d'


def week_summary(rows: list[dict], weeks: int = 8, today: date | None = None) -> str:
    today = today or local_today()
    by_week: dict[date, list[dict]] = defaultdict(list)
    for row in rows:
        if not is_running(row):
            continue
        try:
            d = date.fromisoformat(row['date'])
        except (ValueError, KeyError, TypeError):
            continue
        start = d.fromordinal(d.toordinal() - d.weekday())
        by_week[start].append(row)
    this_monday = date.fromordinal(today.toordinal() - today.weekday())
    lines = [
        '# Resumen de entrenamiento de Garmin',
        '',
        f'Generado el {today.isoformat()}. Semanas: lunes a domingo. Solo actividades de running/trail.',
        'Los datos reflejan únicamente lo registrado y descargado; s/d significa sin datos.',
        '',
        '| Semana (lunes) | Salidas | Kilómetros | Minutos | Desnivel positivo (m) | Fondo máximo (km) |',
        '|---|---:|---:|---:|---:|---:|',
    ]
    for idx in reversed(range(weeks)):
        week = date.fromordinal(this_monday.toordinal() - idx * 7)
        w = by_week.get(week, [])
        km = sum(as_number(r.get('distance_km')) or 0 for r in w)
        mins = sum(as_number(r.get('duration_min')) or 0 for r in w)
        climb = sum(as_number(r.get('ascent_m')) or 0 for r in w)
        longest = max((as_number(r.get('distance_km')) or 0 for r in w), default=0)
        lines.append(f'| {week.isoformat()} | {len(w)} | {km:.2f} | {mins:.0f} | {climb:.0f} | {longest:.2f} |')
    lines += ['', '## Notas', '- La semana en curso puede estar incompleta.', '- Sin interpretación médica ni diagnóstico de sobreentrenamiento.', '']
    return '\n'.join(lines)


def coach_context(activities: list[dict], wellness: list[dict], goals: str, today: date | None = None) -> str:
    today = today or local_today()
    last_activities = [r for r in activities if r.get('date') and r['date'] <= today.isoformat()]
    last_activities.sort(key=lambda r: (r.get('date',''), str(r.get('activity_id',''))), reverse=True)
    well = sorted((r for r in wellness if r.get('date')), key=lambda r: r['date'], reverse=True)
    text = [
        '# Contexto para análisis de entrenamientos', '',
        f'Fecha de referencia: {today.isoformat()} (America/Argentina/Buenos_Aires)',
        f'Objetivos declarados: {goals or "No definidos"}', '',
        '## Últimas 12 actividades',
        '| Fecha | Tipo | Distancia km | Minutos | Ritmo min/km | FC media | Desnivel + m |',
        '|---|---|---:|---:|---:|---:|---:|',
    ]
    for a in last_activities[:12]:
        text.append(f"| {a['date']} | {a.get('type','')} | {fmt(a.get('distance_km'),2)} | {fmt(a.get('duration_min'),0)} | {fmt(a.get('pace_min_km'),2)} | {fmt(a.get('average_hr_bpm'),0)} | {fmt(a.get('ascent_m'),0)} |")
    text += ['', '## Recuperación reciente', '| Fecha | Sueño h | Puntuación sueño | HRV anoche ms | HRV estado |', '|---|---:|---:|---:|---|']
    for r in well[:10]:
        text.append(f"| {r['date']} | {fmt(r.get('sleep_hours'),2)} | {fmt(r.get('sleep_score'),0)} | {fmt(r.get('hrv_last_night_ms'),1)} | {r.get('hrv_status') or 's/d'} |")
    text += [
        '', '## Instrucciones sugeridas para el análisis',
        'Evaluá progresión semanal, carga de running, desnivel y recuperación.',
        'No inferir zonas de entrenamiento sin umbrales individuales confirmados.',
        'No diagnosticar lesión ni sobreentrenamiento solo a partir de estas métricas.',
        'Si faltan datos, indicarlo expresamente. Considerar terreno, sensaciones y objetivos.',
        '',
    ]
    return '\n'.join(text)


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
